import { Hono } from 'hono';
import type { AppEnv, Env } from '../env';
import { LIMITS } from '../env';
import { hasProjectRole, isGlobalMaintainer, projectRoles, requireActor, tierAtLeast } from '../lib/auth';
import {
  body,
  briefsFor,
  currentContract,
  loadProject,
  OBJECTION_PROJECT_SQL,
  objectionsFull,
  pageOut,
  pageParams,
  postFull,
  projectFull,
  projectRoleRows,
  receiptFull,
  requireWritable,
  revisionFull,
  tasksFull,
} from '../lib/common';
import { batch, eventStmt, many, maxEventCursor, one, placeholders, stmt, type Row } from '../lib/db';
import { badRequest, conflict, forbidden, notFound } from '../lib/errors';
import { isoAfterHours, nowIso, ulid } from '../lib/ids';
import { loadPolicy } from '../quota';
import * as S from '../serialize';

export const projects = new Hono<AppEnv>();

const ifMatchVersion = (header: string | undefined): number => {
  const m = /^"?(\d+)"?$/.exec((header ?? '').trim());
  if (!m) throw badRequest('If-Match must carry the current version, quoted');
  return Number(m[1]);
};

// ---------------------------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------------------------

projects.get('/v1/projects', async (c) => {
  const { limit, cursor } = pageParams(c);
  const where: string[] = [];
  const params: unknown[] = [];
  for (const f of ['kind', 'status'] as const) {
    const v = c.req.query(f);
    if (v) {
      where.push(`${f} = ?`);
      params.push(v);
    }
  }
  if (cursor) {
    where.push('id > ?');
    params.push(cursor);
  }
  const rows = await many(c.env, `SELECT * FROM projects ${where.length ? 'WHERE ' + where.join(' AND ') : ''} ORDER BY id LIMIT ?`, ...params, limit + 1);
  const items = await Promise.all(rows.slice(0, limit).map((p) => projectFull(c.env, p)));
  return c.json({ items, next_cursor: rows.length > limit ? rows[limit - 1].id : null });
});

projects.post('/v1/projects', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  if (!isGlobalMaintainer(actor)) throw forbidden('Only global maintainers create projects');
  const req = body(c, 'ProjectCreate');
  if (await one(env, 'SELECT id FROM projects WHERE slug = ?', req.slug)) throw conflict('Slug is already taken');
  const id = ulid();
  const now = nowIso();
  const isChallenge = req.kind === 'challenge';
  const stmts = [
    stmt(
      env,
      `INSERT INTO projects (id, slug, title, kind, status, brief_md, contract_md, contract_version, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
      id, req.slug, req.title, req.kind, req.status ?? 'draft', req.brief_md, isChallenge ? req.contract.body_md : null, isChallenge ? 1 : 0, actor.id, now, now,
    ),
    stmt(env, 'INSERT INTO project_roles (project_id, contributor_id, role, granted_by, created_at) VALUES (?,?,?,?,?)', id, actor.id, 'maintainer', actor.id, now),
    eventStmt(env, { type: 'project.created', actor_id: actor.id, project_id: id, entity_type: 'project', entity_id: id, payload: { slug: req.slug, kind: req.kind, status: req.status ?? 'draft' } }),
  ];
  if (isChallenge) {
    stmts.push(
      stmt(env, 'INSERT INTO project_contracts (project_id, version, body_md, evaluator_md, data_md, change_summary, author_id, created_at) VALUES (?,?,?,?,?,?,?,?)', id, 1, req.contract.body_md, req.contract.evaluator_md ?? null, req.contract.data_md ?? null, req.contract.change_summary, actor.id, now),
      eventStmt(env, { type: 'contract.published', actor_id: actor.id, project_id: id, entity_type: 'contract', entity_id: id, revision: 1, payload: { version: 1 } }),
    );
  }
  await batch(env, stmts);
  return c.json(await projectFull(env, (await one(env, 'SELECT * FROM projects WHERE id = ?', id))!), 201);
});

projects.get('/v1/projects/:project', async (c) => c.json(await projectFull(c.env, await loadProject(c.env, c.req.param('project')))));

const TRANSITIONS: Record<string, string[]> = { draft: ['active'], active: ['paused', 'archived'], paused: ['active', 'archived'], archived: [] };

projects.patch('/v1/projects/:project', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const project = await loadProject(env, c.req.param('project'));
  const roles = await projectRoles(env, project.id, actor.id);
  if (!hasProjectRole(actor, roles, 'maintainer')) throw forbidden('Only project maintainers update a project');
  const req = body(c, 'ProjectPatch');
  if (req.status && req.status !== project.status && !TRANSITIONS[project.status].includes(req.status)) {
    throw conflict(`Cannot move a ${project.status} project to ${req.status}`);
  }
  const previous = { title: project.title, brief_md: project.brief_md, status: project.status };
  await batch(env, [
    stmt(env, 'UPDATE projects SET title = ?, brief_md = ?, status = ?, updated_at = ? WHERE id = ?', req.title ?? project.title, req.brief_md ?? project.brief_md, req.status ?? project.status, nowIso(), project.id),
    eventStmt(env, { type: 'project.updated', actor_id: actor.id, project_id: project.id, entity_type: 'project', entity_id: project.id, payload: { previous, changed: Object.keys(req) } }),
  ]);
  return c.json(await projectFull(env, (await one(env, 'SELECT * FROM projects WHERE id = ?', project.id))!));
});

projects.get('/v1/projects/:project/context', async (c) => {
  const env = c.env;
  const project = await loadProject(env, c.req.param('project'));
  const max = Math.min(200, Math.max(1, Number(c.req.query('max_items') ?? 50) || 50));
  const id = project.id;
  const truncated: string[] = [];
  const cut = <T>(name: string, rows: T[]): T[] => {
    if (rows.length > max) truncated.push(name);
    return rows.slice(0, max);
  };
  const [contract, summary, checks, open, objections, predictions, failed, recent, leases, cursor] = await Promise.all([
    currentContract(env, project),
    project.current_summary_version ? one(env, 'SELECT * FROM project_summaries WHERE project_id = ? AND version = ?', id, project.current_summary_version) : Promise.resolve(null),
    many(env, `SELECT * FROM tasks WHERE project_id = ? AND status = 'open' AND target_contribution_id IS NOT NULL ORDER BY created_at DESC LIMIT ?`, id, max + 1),
    many(env, `SELECT * FROM tasks WHERE project_id = ? AND status = 'open' AND target_contribution_id IS NULL ORDER BY created_at DESC LIMIT ?`, id, max + 1),
    many(env, `SELECT o.*, ${OBJECTION_PROJECT_SQL} AS project_id FROM objections o WHERE o.status IN ('open','answered') AND (${OBJECTION_PROJECT_SQL}) = ? ORDER BY o.created_at DESC LIMIT ?`, id, max + 1),
    many(env, `SELECT p.* FROM predictions p JOIN contributions c ON c.id = p.contribution_id WHERE c.project_id = ? AND c.status NOT IN ('hidden','redacted') AND p.status <> 'withdrawn' ORDER BY p.deadline LIMIT ?`, id, max + 1),
    many(
      env,
      `SELECT c.* FROM contributions c WHERE c.project_id = ? AND c.status = 'active' AND (c.kind = 'negative_result' OR EXISTS (
         SELECT 1 FROM receipts r WHERE r.contribution_id = c.id AND r.revision = c.current_revision AND r.status = 'active' AND r.kind = 'reproduction' AND r.outcome = 'did_not_match'))
       ORDER BY c.created_at DESC LIMIT ?`,
      id, max + 1,
    ),
    many(env, `SELECT * FROM contributions WHERE project_id = ? AND status NOT IN ('hidden','redacted') ORDER BY created_at DESC LIMIT ?`, id, max + 1),
    many(env, `SELECT l.* FROM leases l JOIN tasks t ON t.id = l.task_id WHERE t.project_id = ? AND l.released_at IS NULL AND l.expires_at > ? ORDER BY l.created_at DESC LIMIT ?`, id, nowIso(), max + 1),
    maxEventCursor(env),
  ]);
  return c.json({
    project: S.projectOut(project, await projectRoleRows(env, id), contract),
    summary: summary ? S.summaryOut(summary) : null,
    contract: contract ? S.contractOut(contract) : null,
    requests_for_checks: await tasksFull(env, cut('requests_for_checks', checks)),
    open_tasks: await tasksFull(env, cut('open_tasks', open)),
    unresolved_objections: await objectionsFull(env, cut('unresolved_objections', objections)),
    predictions: cut('predictions', predictions).map(S.predictionOut),
    failed_approaches: await briefsFor(env, cut('failed_approaches', failed)),
    recent_contributions: await briefsFor(env, cut('recent_contributions', recent)),
    active_leases: cut('active_leases', leases).map(S.leaseOut),
    event_cursor: cursor,
    generated_at: nowIso(),
    truncated,
  });
});

// Summaries -------------------------------------------------------------------------------------

projects.get('/v1/projects/:project/summary', async (c) => {
  const env = c.env;
  const project = await loadProject(env, c.req.param('project'));
  const version = Number(c.req.query('version') ?? project.current_summary_version);
  if (!version) throw notFound('This project has no summary yet');
  const row = await one(env, 'SELECT * FROM project_summaries WHERE project_id = ? AND version = ?', project.id, version);
  if (!row) throw notFound('Summary version not found');
  c.header('ETag', `"${row.version}"`);
  return c.json(S.summaryOut(row));
});

projects.put('/v1/projects/:project/summary', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const project = await loadProject(env, c.req.param('project'));
  const roles = await projectRoles(env, project.id, actor.id);
  if (!hasProjectRole(actor, roles, 'maintainer')) throw forbidden('Only project maintainers publish summaries');
  const expected = ifMatchVersion(c.req.header('if-match'));
  if (expected !== project.current_summary_version) throw conflict(`Summary version is ${project.current_summary_version}, not ${expected}`);
  const req = body(c, 'SummaryUpdate');
  const version = project.current_summary_version + 1;
  const now = nowIso();
  await batch(env, [
    stmt(env, 'INSERT INTO project_summaries (project_id, version, body_md, based_on_cursor, change_summary, author_id, created_at) VALUES (?,?,?,?,?,?,?)', project.id, version, req.body_md, req.based_on_cursor, req.change_summary, actor.id, now),
    stmt(env, 'UPDATE projects SET current_summary_version = ?, updated_at = ? WHERE id = ?', version, now, project.id),
    eventStmt(env, { type: 'summary.updated', actor_id: actor.id, project_id: project.id, entity_type: 'summary', entity_id: project.id, revision: version, payload: { change_summary: req.change_summary, based_on_cursor: req.based_on_cursor } }),
  ]);
  c.header('ETag', `"${version}"`);
  return c.json(S.summaryOut((await one(env, 'SELECT * FROM project_summaries WHERE project_id = ? AND version = ?', project.id, version))!));
});

// Contracts -------------------------------------------------------------------------------------

projects.get('/v1/projects/:project/contract', async (c) => {
  const env = c.env;
  const project = await loadProject(env, c.req.param('project'));
  const version = Number(c.req.query('version') ?? project.contract_version);
  if (!version) throw notFound('This project has no contract');
  const row = await one(env, 'SELECT * FROM project_contracts WHERE project_id = ? AND version = ?', project.id, version);
  if (!row) throw notFound('Contract version not found');
  c.header('ETag', `"${row.version}"`);
  return c.json(S.contractOut(row));
});

projects.put('/v1/projects/:project/contract', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const project = await loadProject(env, c.req.param('project'));
  const roles = await projectRoles(env, project.id, actor.id);
  if (!hasProjectRole(actor, roles, 'maintainer')) throw forbidden('Only project maintainers publish contract versions');
  if (project.kind !== 'challenge') throw conflict('Only challenges carry an evaluation contract');
  const expected = ifMatchVersion(c.req.header('if-match'));
  if (expected !== project.contract_version) throw conflict(`Contract version is ${project.contract_version}, not ${expected}`);
  const req = body(c, 'ContractCreate');
  const version = project.contract_version + 1;
  const now = nowIso();
  await batch(env, [
    stmt(env, 'INSERT INTO project_contracts (project_id, version, body_md, evaluator_md, data_md, change_summary, author_id, created_at) VALUES (?,?,?,?,?,?,?,?)', project.id, version, req.body_md, req.evaluator_md ?? null, req.data_md ?? null, req.change_summary, actor.id, now),
    stmt(env, 'UPDATE projects SET contract_version = ?, contract_md = ?, updated_at = ? WHERE id = ?', version, req.body_md, now, project.id),
    eventStmt(env, { type: 'contract.published', actor_id: actor.id, project_id: project.id, entity_type: 'contract', entity_id: project.id, revision: version, payload: { version, change_summary: req.change_summary } }),
  ]);
  c.header('ETag', `"${version}"`);
  return c.json(S.contractOut((await one(env, 'SELECT * FROM project_contracts WHERE project_id = ? AND version = ?', project.id, version))!));
});

// Roles -----------------------------------------------------------------------------------------

projects.post('/v1/projects/:project/roles', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const project = await loadProject(env, c.req.param('project'));
  const roles = await projectRoles(env, project.id, actor.id);
  if (!hasProjectRole(actor, roles, 'maintainer')) throw forbidden('Only project maintainers grant roles');
  const req = body(c, 'RoleGrant');
  const target = await one(env, 'SELECT id, handle FROM contributors WHERE id = ?', req.contributor_id);
  if (!target) throw notFound('Contributor not found');
  const now = nowIso();
  await batch(env, [
    stmt(env, 'INSERT OR IGNORE INTO project_roles (project_id, contributor_id, role, granted_by, created_at) VALUES (?,?,?,?,?)', project.id, target.id, req.role, actor.id, now),
    eventStmt(env, { type: 'role.granted', actor_id: actor.id, project_id: project.id, entity_type: 'contributor', entity_id: target.id, payload: { role: req.role } }),
  ]);
  const row = (await one(env, 'SELECT pr.*, c.handle FROM project_roles pr JOIN contributors c ON c.id = pr.contributor_id WHERE pr.project_id = ? AND pr.contributor_id = ? AND pr.role = ?', project.id, target.id, req.role))!;
  return c.json(S.roleOut(row), 201);
});

projects.delete('/v1/projects/:project/roles/:contributor_id/:role', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const project = await loadProject(env, c.req.param('project'));
  const roles = await projectRoles(env, project.id, actor.id);
  if (!hasProjectRole(actor, roles, 'maintainer')) throw forbidden('Only project maintainers revoke roles');
  const contributorId = c.req.param('contributor_id');
  const role = c.req.param('role');
  const existing = await one(env, 'SELECT * FROM project_roles WHERE project_id = ? AND contributor_id = ? AND role = ?', project.id, contributorId, role);
  if (!existing) throw notFound('Role not found');
  if (role === 'maintainer') {
    const n = await one<{ n: number }>(env, `SELECT COUNT(*) AS n FROM project_roles WHERE project_id = ? AND role = 'maintainer'`, project.id);
    if ((n?.n ?? 0) <= 1) throw conflict('The last maintainer of a project cannot be removed');
  }
  await batch(env, [
    stmt(env, 'DELETE FROM project_roles WHERE project_id = ? AND contributor_id = ? AND role = ?', project.id, contributorId, role),
    eventStmt(env, { type: 'role.revoked', actor_id: actor.id, project_id: project.id, entity_type: 'contributor', entity_id: contributorId, payload: { role } }),
  ]);
  return c.body(null, 204);
});

// Export ----------------------------------------------------------------------------------------

export async function exportProject(env: Env, project: Row) {
  const id = project.id;
  const contributions = await many(env, `SELECT * FROM contributions WHERE project_id = ? AND status NOT IN ('hidden','redacted') ORDER BY id`, id);
  const cids = contributions.map((r) => r.id as string);
  const inC = cids.length ? `IN (${placeholders(cids.length)})` : 'IN (NULL)';
  const revisionRows = cids.length ? await many(env, `SELECT * FROM contribution_revisions WHERE contribution_id ${inC} ORDER BY contribution_id, revision`, ...cids) : [];
  const receiptRows = cids.length ? await many(env, `SELECT * FROM receipts WHERE contribution_id ${inC} AND status NOT IN ('hidden','redacted') ORDER BY id`, ...cids) : [];
  const rids = receiptRows.map((r) => r.id as string);
  const inR = rids.length ? `IN (${placeholders(rids.length)})` : 'IN (NULL)';
  const [contracts, summaries, tasks, posts, relations, predictions, objections, moderation, events, artifacts] = await Promise.all([
    many(env, 'SELECT * FROM project_contracts WHERE project_id = ? ORDER BY version', id),
    many(env, 'SELECT * FROM project_summaries WHERE project_id = ? ORDER BY version', id),
    many(env, 'SELECT * FROM tasks WHERE project_id = ? ORDER BY id', id),
    many(env, `SELECT * FROM posts WHERE project_id = ? AND status = 'visible' ORDER BY id`, id),
    cids.length ? many(env, `SELECT * FROM relations WHERE from_id ${inC} ORDER BY id`, ...cids) : Promise.resolve([] as Row[]),
    cids.length ? many(env, `SELECT * FROM predictions WHERE contribution_id ${inC}`, ...cids) : Promise.resolve([] as Row[]),
    many(env, `SELECT o.*, ${OBJECTION_PROJECT_SQL} AS project_id FROM objections o WHERE o.status <> 'hidden' AND (${OBJECTION_PROJECT_SQL}) = ? ORDER BY o.id`, id),
    many(env, `SELECT * FROM moderation_actions WHERE target_id = ? OR target_id ${inC} OR target_id ${inR} ORDER BY id`, id, ...cids, ...rids),
    many(env, 'SELECT * FROM events WHERE project_id = ? ORDER BY cursor', id),
    cids.length
      ? many(
          env,
          `SELECT DISTINCT a.* FROM artifacts a WHERE a.status = 'published' AND (a.id IN (SELECT artifact_id FROM contribution_artifacts WHERE contribution_id ${inC})
             OR a.id IN (SELECT ra.artifact_id FROM receipt_artifacts ra JOIN receipts r ON r.id = ra.receipt_id WHERE r.contribution_id ${inC})) ORDER BY a.id`,
          ...cids, ...cids,
        )
      : Promise.resolve([] as Row[]),
  ]);
  const taskIds = tasks.map((t) => t.id as string);
  const leases = taskIds.length ? await many(env, `SELECT * FROM leases WHERE task_id IN (${placeholders(taskIds.length)}) ORDER BY id`, ...taskIds) : [];

  const revisions = await Promise.all(revisionRows.map((r) => revisionFull(env, r.contribution_id, r.revision)));
  const receipts = await Promise.all(receiptRows.map((r) => receiptFull(env, r)));
  const fullContributions = await Promise.all(contributions.map(async (cRow) => {
    const [brief] = await briefsFor(env, [cRow]);
    const current = revisions.find((r) => r.contribution_id === cRow.id && r.revision === cRow.current_revision);
    const prediction = predictions.find((p) => p.contribution_id === cRow.id);
    return { ...brief, task_id: cRow.task_id ?? null, license: cRow.license, revision: current, prediction: prediction ? S.predictionOut(prediction) : null, withdrawn_at: cRow.withdrawn_at ?? null, withdrawn_reason: cRow.withdrawn_reason ?? null };
  }));

  const contributorIds = new Set<string>([project.created_by]);
  const runIds = new Set<string>();
  for (const r of [...contributions, ...receiptRows, ...objections, ...posts, ...tasks, ...leases, ...contracts, ...summaries, ...moderation, ...relations]) {
    for (const k of ['author_id', 'created_by', 'contributor_id', 'actor_id', 'resolved_by', 'closed_by']) if (r[k]) contributorIds.add(r[k]);
  }
  for (const r of [...revisionRows, ...receiptRows, ...posts]) if (r.run_id) runIds.add(r.run_id);
  for (const p of predictions) contributorIds.add(p.resolver_id);
  const roleRows = await projectRoleRows(env, id);
  for (const r of roleRows) contributorIds.add(r.contributor_id);
  const cidList = [...contributorIds];
  const contributorRows = await many(env, `SELECT * FROM contributors WHERE id IN (${placeholders(cidList.length)}) ORDER BY id`, ...cidList);
  const runList = [...runIds];
  const runRows = runList.length ? await many(env, `SELECT * FROM runs WHERE id IN (${placeholders(runList.length)}) ORDER BY id`, ...runList) : [];
  for (const r of runRows) contributorIds.add(r.contributor_id);

  return {
    exported_at: nowIso(),
    event_cursor: events.length ? events[events.length - 1].cursor : 0,
    project: S.projectOut(project, roleRows, contracts.find((k) => k.version === project.contract_version) ?? null),
    contributors: contributorRows.map((r) => S.contributorOut(r)),
    runs: runRows.map(S.runOut),
    contracts: contracts.map(S.contractOut),
    summaries: summaries.map(S.summaryOut),
    tasks: await tasksFull(env, tasks),
    leases: leases.map(S.leaseOut),
    posts: await Promise.all(posts.map((p) => postFull(env, p))),
    contributions: fullContributions,
    revisions,
    relations: relations.map(S.relationOut),
    receipts,
    predictions: predictions.map(S.predictionOut),
    objections: await objectionsFull(env, objections),
    artifacts: artifacts.map((a) => S.artifactOut(env, a)),
    moderation: moderation.map(S.moderationOut),
    events: events.map(S.eventOut),
  };
}

projects.get('/v1/projects/:project/export', async (c) => {
  const project = await loadProject(c.env, c.req.param('project'));
  const data = await exportProject(c.env, project);
  if (c.req.query('format') === 'ndjson') {
    const lines: string[] = [];
    for (const [key, value] of Object.entries(data)) {
      if (Array.isArray(value)) for (const item of value) lines.push(JSON.stringify({ type: key, item }));
      else lines.push(JSON.stringify({ type: key, item: value }));
    }
    return c.body(lines.join('\n') + '\n', 200, { 'content-type': 'application/x-ndjson' });
  }
  return c.json(data);
});

// Tasks and leases -----------------------------------------------------------------------------

projects.post('/v1/projects/:project/tasks', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const project = await loadProject(env, c.req.param('project'));
  const roles = await projectRoles(env, project.id, actor.id);
  const req = body(c, 'TaskCreate');
  const privileged = hasProjectRole(actor, roles, 'maintainer', 'reviewer');
  if (!privileged) {
    if (!req.target) throw forbidden('Only project maintainers and reviewers create tasks without a target');
    if (!tierAtLeast(actor, 'established')) throw forbidden('Requests for checks need tier established or above');
  }
  requireWritable(project, actor, roles);
  let targetClaim: string | null = null;
  if (req.target) {
    const target = await one(env, 'SELECT c.*, r.claim FROM contributions c JOIN contribution_revisions r ON r.contribution_id = c.id AND r.revision = c.current_revision WHERE c.id = ? AND c.project_id = ?', req.target.contribution_id, project.id);
    if (!target) throw notFound('Target contribution not found in this project');
    if (req.target.revision && !(await one(env, 'SELECT 1 FROM contribution_revisions WHERE contribution_id = ? AND revision = ?', target.id, req.target.revision))) throw notFound('Target revision not found');
    targetClaim = target.claim;
  }
  const id = ulid();
  await batch(env, [
    stmt(env, 'INSERT INTO tasks (id, project_id, title, body_md, kind, size, status, target_contribution_id, target_revision, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', id, project.id, req.title, req.body_md, req.kind, req.size ?? 'small', 'open', req.target?.contribution_id ?? null, req.target?.revision ?? null, actor.id, nowIso()),
    eventStmt(env, { type: 'task.created', actor_id: actor.id, project_id: project.id, entity_type: 'task', entity_id: id, payload: { kind: req.kind, size: req.size ?? 'small', target: req.target ?? null } }),
  ]);
  const row = (await one(env, 'SELECT * FROM tasks WHERE id = ?', id))!;
  return c.json(S.taskOut(row, [], targetClaim), 201);
});

projects.get('/v1/tasks', async (c) => {
  const env = c.env;
  const { limit, cursor } = pageParams(c);
  const where: string[] = [];
  const params: unknown[] = [];
  const projectKey = c.req.query('project');
  if (projectKey) {
    where.push('t.project_id = ?');
    params.push((await loadProject(env, projectKey)).id);
  }
  for (const f of ['kind', 'size'] as const) {
    const v = c.req.query(f);
    if (v) {
      where.push(`t.${f} = ?`);
      params.push(v);
    }
  }
  where.push('t.status = ?');
  params.push(c.req.query('status') ?? 'open');
  if (c.req.query('checks') === 'true') where.push('t.target_contribution_id IS NOT NULL');
  if (c.req.query('unleased') === 'true') {
    where.push('NOT EXISTS (SELECT 1 FROM leases l WHERE l.task_id = t.id AND l.released_at IS NULL AND l.expires_at > ?)');
    params.push(nowIso());
  }
  if (cursor) {
    where.push('t.id > ?');
    params.push(cursor);
  }
  const rows = await many(env, `SELECT t.* FROM tasks t WHERE ${where.join(' AND ')} ORDER BY t.id LIMIT ?`, ...params, limit + 1);
  const items = await tasksFull(env, rows.slice(0, limit));
  return c.json({ items, next_cursor: rows.length > limit ? rows[limit - 1].id : null });
});

projects.get('/v1/tasks/:id', async (c) => {
  const row = await one(c.env, 'SELECT * FROM tasks WHERE id = ?', c.req.param('id'));
  if (!row) throw notFound('Task not found');
  return c.json((await tasksFull(c.env, [row]))[0]);
});

projects.post('/v1/tasks/:id/leases', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const task = await one(env, 'SELECT * FROM tasks WHERE id = ?', c.req.param('id'));
  if (!task) throw notFound('Task not found');
  if (task.status !== 'open') throw conflict('Task is not open');
  const req = body(c, 'LeaseCreate');
  const hours = Math.min(LIMITS.lease_max_hours, Math.max(1, Number(req.hours ?? LIMITS.lease_default_hours)));
  const now = nowIso();
  const existing = await one(env, 'SELECT * FROM leases WHERE task_id = ? AND contributor_id = ? AND released_at IS NULL AND expires_at > ?', task.id, actor.id, now);
  if (existing) {
    await stmt(env, 'UPDATE leases SET expires_at = ?, note = COALESCE(?, note) WHERE id = ?', isoAfterHours(hours), req.note ?? null, existing.id).run();
    return c.json(S.leaseOut((await one(env, 'SELECT * FROM leases WHERE id = ?', existing.id))!), 201);
  }
  const policy = await loadPolicy(env, actor.tier);
  const active = await one<{ n: number }>(env, 'SELECT COUNT(*) AS n FROM leases WHERE contributor_id = ? AND released_at IS NULL AND expires_at > ?', actor.id, now);
  if ((active?.n ?? 0) >= policy.active_leases) throw conflict(`You already hold ${policy.active_leases} active leases`);
  const id = ulid();
  await batch(env, [
    stmt(env, 'INSERT INTO leases (id, task_id, contributor_id, note, created_at, expires_at) VALUES (?,?,?,?,?,?)', id, task.id, actor.id, req.note ?? null, now, isoAfterHours(hours)),
    eventStmt(env, { type: 'lease.created', actor_id: actor.id, project_id: task.project_id, entity_type: 'lease', entity_id: id, payload: { task_id: task.id, hours } }),
  ]);
  return c.json(S.leaseOut((await one(env, 'SELECT * FROM leases WHERE id = ?', id))!), 201);
});

projects.delete('/v1/leases/:id', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const lease = await one(env, 'SELECT l.*, t.project_id FROM leases l JOIN tasks t ON t.id = l.task_id WHERE l.id = ?', c.req.param('id'));
  if (!lease) throw notFound('Lease not found');
  if (lease.contributor_id !== actor.id) throw forbidden('Only the holder releases a lease');
  if (lease.released_at) return c.body(null, 204);
  await batch(env, [
    stmt(env, 'UPDATE leases SET released_at = ? WHERE id = ?', nowIso(), lease.id),
    eventStmt(env, { type: 'lease.released', actor_id: actor.id, project_id: lease.project_id, entity_type: 'lease', entity_id: lease.id, payload: { task_id: lease.task_id } }),
  ]);
  return c.body(null, 204);
});

projects.post('/v1/tasks/:id/close', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const task = await one(env, 'SELECT * FROM tasks WHERE id = ?', c.req.param('id'));
  if (!task) throw notFound('Task not found');
  const roles = await projectRoles(env, task.project_id, actor.id);
  if (!hasProjectRole(actor, roles, 'maintainer', 'reviewer')) throw forbidden('Only project maintainers and reviewers close tasks');
  if (task.status !== 'open') throw conflict('Task is already closed');
  const req = body(c, 'TaskClose');
  if (req.contribution_id && !(await one(env, 'SELECT id FROM contributions WHERE id = ?', req.contribution_id))) throw notFound('Contribution not found');
  if (req.receipt_id && !(await one(env, 'SELECT id FROM receipts WHERE id = ?', req.receipt_id))) throw notFound('Receipt not found');
  const now = nowIso();
  await batch(env, [
    stmt(env, 'UPDATE tasks SET status = ?, closed_at = ?, closed_by = ?, closed_by_contribution_id = ?, closed_by_receipt_id = ? WHERE id = ?', req.status, now, actor.id, req.contribution_id ?? null, req.receipt_id ?? null, task.id),
    stmt(env, 'UPDATE leases SET released_at = ? WHERE task_id = ? AND released_at IS NULL', now, task.id),
    eventStmt(env, { type: 'task.closed', actor_id: actor.id, project_id: task.project_id, entity_type: 'task', entity_id: task.id, payload: { status: req.status, contribution_id: req.contribution_id ?? null, receipt_id: req.receipt_id ?? null, note: req.note ?? null } }),
  ]);
  return c.json((await tasksFull(env, [(await one(env, 'SELECT * FROM tasks WHERE id = ?', task.id))!]))[0]);
});
