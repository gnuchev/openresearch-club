import { Hono } from 'hono';
import type { AppEnv, Env } from '../env';
import { LIMITS } from '../env';
import { hasProjectRole, isGlobalMaintainer, projectRoles, requireActor, tierAtLeast } from '../lib/auth';
import {
  body,
  briefsFor,
  chunkedRows,
  currentContract,
  loadProject,
  OBJECTION_PROJECT_SQL,
  objectionsFull,
  pageOut,
  pageParams,
  postFull,
  projectFull,
  projectRoleRows,
  facetsFor,
  receiptFull,
  RECEIPT_OBJECTIONS_SQL,
  requireProjectWritable,
  requireUnlocked,
  requireWritable,
  revisionFull,
  tasksFull,
} from '../lib/common';
import { batch, eventStmt, many, maxEventCursor, one, placeholders, stmt, type Row } from '../lib/db';
import { badRequest, conflict, forbidden, notFound } from '../lib/errors';
import { isoAfterHours, nowIso, ulid } from '../lib/ids';
import { loadPolicy, reserveQuota, usageStmt } from '../quota';
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

// Any active registered contributor may open a project or a challenge, within a per-tier daily
// quota. The creator becomes its maintainer. Nobody approves; maintainers moderate afterwards.
projects.post('/v1/projects', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'ProjectCreate');
  if (await one(env, 'SELECT id FROM projects WHERE slug = ?', req.slug)) throw conflict('Slug is already taken');
  const release = await reserveQuota(env, actor, 'projects');
  const id = ulid();
  const now = nowIso();
  const isChallenge = req.kind === 'challenge';
  const status = req.status ?? 'active';
  const stmts = [
    stmt(
      env,
      `INSERT INTO projects (id, slug, title, kind, status, brief_md, contract_md, contract_version, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
      id, req.slug, req.title, req.kind, status, req.brief_md, isChallenge ? req.contract.body_md : null, isChallenge ? 1 : 0, actor.id, now, now,
    ),
    stmt(env, 'INSERT INTO project_roles (project_id, contributor_id, role, granted_by, created_at) VALUES (?,?,?,?,?)', id, actor.id, 'maintainer', actor.id, now),
    usageStmt(env, actor.id, 'projects'),
    eventStmt(env, { type: 'project.created', actor_id: actor.id, project_id: id, entity_type: 'project', entity_id: id, payload: { slug: req.slug, kind: req.kind, status, title: req.title } }),
  ];
  if (isChallenge) {
    stmts.push(
      stmt(env, 'INSERT INTO project_contracts (project_id, version, body_md, evaluator_md, data_md, change_summary, author_id, created_at) VALUES (?,?,?,?,?,?,?,?)', id, 1, req.contract.body_md, req.contract.evaluator_md ?? null, req.contract.data_md ?? null, req.contract.change_summary, actor.id, now),
      eventStmt(env, { type: 'contract.published', actor_id: actor.id, project_id: id, entity_type: 'contract', entity_id: id, revision: 1, payload: { version: 1 } }),
    );
  }
  try {
    await batch(env, stmts);
  } catch (e) {
    await release();
    throw e;
  }
  return c.json(await projectFull(env, (await one(env, 'SELECT * FROM projects WHERE id = ?', id))!), 201);
});

projects.get('/v1/projects/:project', async (c) => c.json(await projectFull(c.env, await loadProject(c.env, c.req.param('project')))));

const TRANSITIONS: Record<string, string[]> = { draft: ['active'], active: ['paused', 'archived'], paused: ['active', 'archived'], archived: ['active'] };

projects.patch('/v1/projects/:project', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const project = await loadProject(env, c.req.param('project'));
  const roles = await projectRoles(env, project.id, actor.id);
  if (!hasProjectRole(actor, roles, 'maintainer')) throw forbidden('Only project maintainers update a project');
  requireUnlocked(project, actor);
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

/** The context packet, shared by the API route and the human-readable project page. */
export async function buildContextPacket(env: Env, project: Row, max: number) {
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
  return {
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
  };
}

projects.get('/v1/projects/:project/context', async (c) => {
  const project = await loadProject(c.env, c.req.param('project'));
  const max = Math.min(200, Math.max(1, Number(c.req.query('max_items') ?? 50) || 50));
  return c.json(await buildContextPacket(c.env, project, max));
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
  requireUnlocked(project, actor);
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
  requireUnlocked(project, actor);
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
  requireUnlocked(project, actor);
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
  requireUnlocked(project, actor);
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

/**
 * Complete public export of one project. Every query is scoped by the project id, never by an
 * expanding list of ids, so a populated project cannot approach D1's 100-parameter limit (W5).
 * One query per record type; the export is assembled in memory from those results.
 */
export async function exportProject(env: Env, project: Row) {
  const id = project.id;
  const PUB = `NOT IN ('hidden','redacted')`;

  const [contributions, revisionRows, receiptRows, receiptLinks, revisionArtifacts, artifacts, relations, predictions, contracts, summaries, tasks, leases, posts, postRevisions, objections, moderation, events, roleRows] =
    await Promise.all([
      many(env, `SELECT * FROM contributions WHERE project_id = ? AND status ${PUB} ORDER BY id`, id),
      many(env, `SELECT r.* FROM contribution_revisions r JOIN contributions c ON c.id = r.contribution_id WHERE c.project_id = ? AND c.status ${PUB} ORDER BY r.contribution_id, r.revision`, id),
      many(env, `SELECT r.*, ${RECEIPT_OBJECTIONS_SQL}, (SELECT x.id FROM receipts x WHERE x.corrects_receipt_id = r.id) AS corrected_by_receipt_id FROM receipts r JOIN contributions c ON c.id = r.contribution_id WHERE c.project_id = ? AND c.status ${PUB} AND r.status ${PUB} ORDER BY r.id`, id),
      many(env, `SELECT ra.receipt_id, ra.artifact_id, ra.role FROM receipt_artifacts ra JOIN receipts r ON r.id = ra.receipt_id JOIN contributions c ON c.id = r.contribution_id WHERE c.project_id = ? ORDER BY ra.receipt_id, ra.artifact_id`, id),
      many(env, `SELECT ca.contribution_id, ca.revision, ca.role, a.* FROM contribution_artifacts ca JOIN artifacts a ON a.id = ca.artifact_id JOIN contributions c ON c.id = ca.contribution_id WHERE c.project_id = ? AND a.status = 'published' ORDER BY ca.contribution_id, ca.revision, ca.role`, id),
      many(env, `SELECT DISTINCT a.* FROM artifacts a WHERE a.status = 'published' AND (a.id IN (SELECT ca.artifact_id FROM contribution_artifacts ca JOIN contributions c ON c.id = ca.contribution_id WHERE c.project_id = ?) OR a.id IN (SELECT ra.artifact_id FROM receipt_artifacts ra JOIN receipts r ON r.id = ra.receipt_id JOIN contributions c ON c.id = r.contribution_id WHERE c.project_id = ?)) ORDER BY a.id`, id, id),
      many(env, `SELECT rel.* FROM relations rel JOIN contributions c ON c.id = rel.from_id WHERE c.project_id = ? ORDER BY rel.id`, id),
      many(env, `SELECT p.* FROM predictions p JOIN contributions c ON c.id = p.contribution_id WHERE c.project_id = ? AND c.status ${PUB}`, id),
      many(env, 'SELECT * FROM project_contracts WHERE project_id = ? ORDER BY version', id),
      many(env, 'SELECT * FROM project_summaries WHERE project_id = ? ORDER BY version', id),
      many(env, 'SELECT * FROM tasks WHERE project_id = ? ORDER BY id', id),
      many(env, 'SELECT l.* FROM leases l JOIN tasks t ON t.id = l.task_id WHERE t.project_id = ? ORDER BY l.id', id),
      many(env, `SELECT * FROM posts WHERE project_id = ? AND status = 'visible' ORDER BY id`, id),
      many(env, `SELECT pr.* FROM post_revisions pr JOIN posts p ON p.id = pr.post_id WHERE p.project_id = ? AND p.status = 'visible' ORDER BY pr.post_id, pr.revision`, id),
      many(env, `SELECT o.*, ${OBJECTION_PROJECT_SQL} AS project_id FROM objections o WHERE o.status <> 'hidden' AND (${OBJECTION_PROJECT_SQL}) = ? ORDER BY o.id`, id),
      many(env, `SELECT m.* FROM moderation_actions m WHERE m.target_id = ? OR m.target_id IN (SELECT id FROM contributions WHERE project_id = ?) OR m.target_id IN (SELECT r.id FROM receipts r JOIN contributions c ON c.id = r.contribution_id WHERE c.project_id = ?) OR m.target_id IN (SELECT id FROM posts WHERE project_id = ?) OR m.target_id IN (SELECT o.id FROM objections o WHERE (${OBJECTION_PROJECT_SQL}) = ?) ORDER BY m.id`, id, id, id, id, id),
      many(env, 'SELECT * FROM events WHERE project_id = ? ORDER BY cursor', id),
      projectRoleRows(env, id),
    ]);

  const group = (rows: Row[], key: string) => {
    const m = new Map<string, Row[]>();
    for (const r of rows) {
      const k = String(r[key]);
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(r);
    }
    return m;
  };
  // Referenced people and runs are collected from the rows already in hand and loaded in chunks:
  // no compound SELECT (D1 caps its terms) and never more than 80 bound ids per statement.
  const contributorIds = new Set<string>();
  const add = (v: unknown) => {
    if (typeof v === 'string' && v) contributorIds.add(v);
  };
  add(project.created_by);
  for (const r of roleRows) add(r.contributor_id);
  for (const r of [...contracts, ...summaries, ...contributions, ...receiptRows, ...posts]) add(r.author_id);
  for (const r of relations) add(r.created_by);
  for (const r of predictions) add(r.resolver_id);
  for (const r of tasks) {
    add(r.created_by);
    add(r.closed_by);
  }
  for (const r of leases) add(r.contributor_id);
  for (const r of objections) {
    add(r.author_id);
    add(r.resolved_by);
  }
  for (const r of moderation) add(r.actor_id);
  for (const r of events) add(r.actor_id);
  const runIds = new Set<string>();
  for (const r of [...revisionRows, ...receiptRows, ...posts, ...objections]) if (typeof r.run_id === 'string' && r.run_id) runIds.add(r.run_id);
  const [contributorRows, runRows] = await Promise.all([
    chunkedRows(env, [...contributorIds], (ph) => `SELECT * FROM contributors WHERE id IN (${ph})`),
    chunkedRows(env, [...runIds], (ph) => `SELECT * FROM runs WHERE id IN (${ph})`),
  ]);
  contributorRows.sort((a, b) => (a.id < b.id ? -1 : 1));
  runRows.sort((a, b) => (a.id < b.id ? -1 : 1));

  const runsById = new Map(runRows.map((r) => [r.id as string, r]));
  const linksByReceipt = group(receiptLinks, 'receipt_id');
  const artifactsByRevision = group(revisionArtifacts.map((a) => ({ ...a, _key: `${a.contribution_id}:${a.revision}` })), '_key');
  const receiptsByRevision = group(receiptRows.map((r) => ({ ...r, _key: `${r.contribution_id}:${r.revision}` })), '_key');
  const receiptsByContribution = group(receiptRows, 'contribution_id');
  const relationsByFrom = group(relations, 'from_id');
  const postRevisionsByPost = group(postRevisions, 'post_id');
  const responsesByObjection = group(posts.filter((p) => p.objection_id), 'objection_id');
  const predictionsById = new Map(predictions.map((p) => [p.contribution_id as string, p]));
  const facets = await facetsFor(env, contributions.map((c) => c.id as string));

  const receiptOut = (r: Row) => S.receiptOut(r, runsById.get(r.run_id) ?? null, linksByReceipt.get(r.id) ?? []);
  const revisions = revisionRows.map((rev) => {
    const k = `${rev.contribution_id}:${rev.revision}`;
    return S.revisionOut(env, rev, runsById.get(rev.run_id) ?? null, artifactsByRevision.get(k) ?? [], (receiptsByRevision.get(k) ?? []).map(receiptOut));
  });
  const revisionByKey = new Map(revisions.map((r) => [`${r.contribution_id}:${r.revision}`, r]));
  const fullContributions = contributions.map((cRow) => {
    const current = revisionByKey.get(`${cRow.id}:${cRow.current_revision}`);
    const brief = S.contributionBriefOut(cRow, current ?? {}, facets.get(cRow.id) ?? {}, receiptsByContribution.get(cRow.id) ?? [], relationsByFrom.get(cRow.id) ?? []);
    const prediction = predictionsById.get(cRow.id);
    return { ...brief, task_id: cRow.task_id ?? null, license: cRow.license, revision: current, prediction: prediction ? S.predictionOut(prediction) : null, withdrawn_at: cRow.withdrawn_at ?? null, withdrawn_reason: cRow.withdrawn_reason ?? null };
  });
  const postOut = (p: Row) => S.postOut(p, postRevisionsByPost.get(p.id) ?? []);

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
    posts: posts.map(postOut),
    contributions: fullContributions,
    revisions,
    relations: relations.map(S.relationOut),
    receipts: receiptRows.map(receiptOut),
    predictions: predictions.map(S.predictionOut),
    objections: objections.map((o) => S.objectionOut(o, (responsesByObjection.get(o.id) ?? []).map(postOut))),
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
  await requireProjectWritable(env, actor, task.project_id);
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
  requireUnlocked((await one(env, 'SELECT * FROM projects WHERE id = ?', task.project_id))!, actor);
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
