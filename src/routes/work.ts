import { Hono } from 'hono';
import type { AppEnv, Env } from '../env';
import { LIMITS } from '../env';
import { hasProjectRole, projectRoles, requireActor, type Actor } from '../lib/auth';
import {
  body,
  briefsFor,
  contributionFull,
  loadContribution,
  loadObjection,
  loadProject,
  OBJECTION_PROJECT_SQL,
  objectionsFull,
  pageParams,
  postFull,
  PUBLIC_RECEIPT_STATUSES,
  receiptFull,
  requireProjectWritable,
  requireWritable,
  revisionFull,
  RECEIPT_OBJECTIONS_SQL,
} from '../lib/common';
import { sha256hex } from '../lib/crypto';
import { batch, constraintMessage, eventStmt, many, one, placeholders, stmt, type Row } from '../lib/db';
import { badRequest, conflict, forbidden, gone, notFound, tooLarge, tooMany } from '../lib/errors';
import { nowIso, secondsUntilNextUtcDay, today, ulid } from '../lib/ids';
import { validationErrors } from '../lib/validate';
import { loadPolicy, reserveQuota, usageStmt } from '../quota';
import * as S from '../serialize';

export const work = new Hono<AppEnv>();

const RESULT_KINDS = new Set(['result', 'attempt', 'negative_result', 'counterexample', 'correction', 'proof', 'dataset']);

async function requireOwnRun(env: Env, actor: Actor, runId: string): Promise<void> {
  if (!(await one(env, 'SELECT id FROM runs WHERE id = ? AND contributor_id = ?', runId, actor.id))) throw badRequest('run_id must be one of your declared runs');
}

async function checkArtifactLinks(env: Env, actor: Actor, links: Array<{ artifact_id: string; role: string }>): Promise<void> {
  for (const l of links) {
    const a = await one(env, 'SELECT owner_id, status FROM artifacts WHERE id = ?', l.artifact_id);
    if (!a) throw notFound(`Artifact ${l.artifact_id} not found`);
    if (a.owner_id !== actor.id) throw forbidden(`Artifact ${l.artifact_id} belongs to another contributor`);
    if (a.status !== 'published') throw conflict(`Artifact ${l.artifact_id} is ${a.status}, not published`);
  }
}

function contractVersionFor(project: Row, supplied: number | undefined): number | null {
  if (project.kind === 'challenge') {
    if (supplied === undefined) throw badRequest('contract_version is required for challenge submissions; copy it from the context packet');
    if (supplied !== project.contract_version) throw conflict(`contract_version ${supplied} is not current; the current contract version is ${project.contract_version}`);
    return supplied;
  }
  if (supplied !== undefined) throw badRequest('contract_version applies to challenges only');
  return null;
}

function mapConstraint(err: unknown): never {
  const m = constraintMessage(err);
  if (m?.includes('contract_version is not the current')) throw conflict('The contract changed while you worked; read the new version and resubmit');
  if (m?.includes('contract_version is required')) throw badRequest(m);
  throw err;
}

// ---------------------------------------------------------------------------------------------
// Posts
// ---------------------------------------------------------------------------------------------

work.get('/v1/posts', async (c) => {
  const env = c.env;
  const { limit, cursor } = pageParams(c);
  const where = [`p.status = 'visible'`];
  const params: unknown[] = [];
  const projectKey = c.req.query('project');
  const thread = c.req.query('thread');
  const objection = c.req.query('objection');
  if (thread) {
    where.push('(p.id = ? OR p.parent_post_id = ?)');
    params.push(thread, thread);
  } else if (objection) {
    where.push('p.objection_id = ?');
    params.push(objection);
  } else if (projectKey) {
    where.push('p.project_id = ? AND p.objection_id IS NULL');
    params.push((await loadProject(env, projectKey)).id);
  } else {
    where.push('p.project_id IS NULL AND p.objection_id IS NULL');
  }
  if (cursor) {
    where.push('p.id > ?');
    params.push(cursor);
  }
  const rows = await many(env, `SELECT p.* FROM posts p WHERE ${where.join(' AND ')} ORDER BY p.id LIMIT ?`, ...params, limit + 1);
  const items = await Promise.all(rows.slice(0, limit).map((p) => postFull(env, p)));
  return c.json({ items, next_cursor: rows.length > limit ? rows[limit - 1].id : null });
});

work.post('/v1/posts', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'PostCreate');
  // Resolve the effective project from the target first, then apply the one writability rule (W4).
  let projectId: string | null = null;
  if (req.parent_post_id) {
    const parent = await one(env, `SELECT * FROM posts WHERE id = ? AND status = 'visible'`, req.parent_post_id);
    if (!parent) throw notFound('Parent post not found');
    projectId = parent.project_id;
  } else if (req.objection_id) {
    const objection = await loadObjection(env, req.objection_id);
    projectId = objection.project_id;
  } else if (!req.title) throw badRequest('A thread root needs a title');
  if (req.project_id) {
    const project = await loadProject(env, req.project_id);
    if (projectId && projectId !== project.id) throw badRequest('project_id does not match the project of the parent');
    projectId = project.id;
  }
  if (projectId) await requireProjectWritable(env, actor, projectId);
  if (req.run_id) await requireOwnRun(env, actor, req.run_id);
  const release = await reserveQuota(env, actor, 'posts');
  const id = ulid();
  const now = nowIso();
  try {
    await batch(env, [
      stmt(env, 'INSERT INTO posts (id, project_id, parent_post_id, objection_id, title, body_md, current_revision, author_id, run_id, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', id, projectId, req.parent_post_id ?? null, req.objection_id ?? null, req.title ?? null, req.body_md, 1, actor.id, req.run_id ?? null, 'visible', now),
      stmt(env, 'INSERT INTO post_revisions (post_id, revision, body_md, created_at) VALUES (?,?,?,?)', id, 1, req.body_md, now),
      usageStmt(env, actor.id, 'posts'),
      eventStmt(env, { type: 'post.created', actor_id: actor.id, project_id: projectId, entity_type: 'post', entity_id: id, payload: { title: req.title ?? null, parent_post_id: req.parent_post_id ?? null, objection_id: req.objection_id ?? null } }),
    ]);
  } catch (e) {
    await release();
    throw e;
  }
  return c.json(await postFull(env, (await one(env, 'SELECT * FROM posts WHERE id = ?', id))!), 201);
});

work.get('/v1/posts/:id', async (c) => {
  const p = await one(c.env, 'SELECT * FROM posts WHERE id = ?', c.req.param('id'));
  if (!p) throw notFound('Post not found');
  if (p.status !== 'visible') throw gone(`Post is ${p.status}`);
  return c.json(await postFull(c.env, p));
});

work.post('/v1/posts/:id/revisions', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const p = await one(env, 'SELECT * FROM posts WHERE id = ?', c.req.param('id'));
  if (!p) throw notFound('Post not found');
  if (p.author_id !== actor.id) throw forbidden('Only the author revises a post');
  if (p.status !== 'visible') throw gone(`Post is ${p.status}`);
  const req = body(c, 'PostRevise');
  const revision = p.current_revision + 1;
  const now = nowIso();
  await batch(env, [
    stmt(env, 'INSERT INTO post_revisions (post_id, revision, body_md, created_at) VALUES (?,?,?,?)', p.id, revision, req.body_md, now),
    stmt(env, 'UPDATE posts SET body_md = ?, current_revision = ?, revised_at = ? WHERE id = ?', req.body_md, revision, now, p.id),
    eventStmt(env, { type: 'post.revised', actor_id: actor.id, project_id: p.project_id, entity_type: 'post', entity_id: p.id, revision, payload: {} }),
  ]);
  return c.json(await postFull(env, (await one(env, 'SELECT * FROM posts WHERE id = ?', p.id))!));
});

// ---------------------------------------------------------------------------------------------
// Artifacts
// ---------------------------------------------------------------------------------------------

work.post('/v1/artifacts', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'ArtifactCreate');
  if (req.storage === 'r2' && req.byte_size > LIMITS.artifact_max_bytes) throw tooLarge(`Artifacts are limited to ${LIMITS.artifact_max_bytes} bytes in this release`);
  const release = await reserveQuota(env, actor, 'artifacts');
  const id = ulid();
  const now = nowIso();
  const external = req.storage === 'external';
  try {
    await batch(env, [
      stmt(
        env,
        `INSERT INTO artifacts (id, owner_id, kind, name, media_type, byte_size, claimed_sha256, storage, r2_key, external_url, license, provenance_md, status, created_at, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
        id, actor.id, req.kind, req.name, req.media_type ?? null, req.byte_size ?? null, req.claimed_sha256 ?? null, req.storage, external ? null : `artifacts/${id}`, req.external_url ?? null, req.license, req.provenance_md ?? null, external ? 'published' : 'quarantined', now, external ? now : null,
      ),
      usageStmt(env, actor.id, 'artifacts'),
      eventStmt(env, { type: external ? 'artifact.published' : 'artifact.created', actor_id: actor.id, entity_type: 'artifact', entity_id: id, payload: { kind: req.kind, storage: req.storage, name: req.name } }),
    ]);
  } catch (e) {
    await release();
    throw e;
  }
  const row = (await one(env, 'SELECT * FROM artifacts WHERE id = ?', id))!;
  return c.json(
    { artifact: S.artifactOut(env, row), upload: external ? null : { method: 'PUT', url: `${env.PUBLIC_BASE}/v1/artifacts/${id}/content`, max_bytes: LIMITS.artifact_max_bytes } },
    201,
  );
});

work.put('/v1/artifacts/:id/content', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const a = await one(env, 'SELECT * FROM artifacts WHERE id = ?', c.req.param('id'));
  if (!a) throw notFound('Artifact not found');
  if (a.owner_id !== actor.id) throw forbidden('Only the owner uploads content');
  if (a.storage !== 'r2') throw conflict('This artifact is an external reference');
  const bytes = c.get('rawBytes');
  if (!bytes) throw badRequest('Send the bytes as application/octet-stream');
  const hash = await sha256hex(bytes);
  if (a.status === 'published') {
    if (hash === a.verified_sha256) return c.json(S.artifactOut(env, a));
    throw conflict('Different bytes were already published for this artifact');
  }
  if (a.status !== 'quarantined') throw conflict(`Artifact is ${a.status}`);
  if (bytes.byteLength > LIMITS.artifact_max_bytes) throw tooLarge('Upload exceeds the artifact size limit');
  if (bytes.byteLength !== a.byte_size || hash !== a.claimed_sha256) {
    await batch(env, [
      stmt(env, 'UPDATE artifacts SET status = ? WHERE id = ?', 'rejected', a.id),
      eventStmt(env, { type: 'artifact.rejected', actor_id: actor.id, entity_type: 'artifact', entity_id: a.id, payload: { reason: 'size or hash mismatch' } }),
    ]);
    throw conflict('Uploaded bytes do not match the declared size and SHA-256; the artifact is marked rejected');
  }
  const policy = await loadPolicy(env, actor.tier);
  const me = (await one(env, 'SELECT upload_bytes_total FROM contributors WHERE id = ?', actor.id))!;
  if ((me.upload_bytes_total ?? 0) + bytes.byteLength > policy.upload_bytes_total) throw tooLarge('Total upload quota for your tier reached');
  const release = await reserveQuota(env, actor, 'upload_bytes', bytes.byteLength);
  try {
    await env.ARTIFACTS.put(a.r2_key, bytes, { httpMetadata: { contentType: a.media_type ?? 'application/octet-stream' }, customMetadata: { artifact_id: a.id, owner_id: actor.id } });
    const now = nowIso();
    await batch(env, [
      stmt(env, 'UPDATE artifacts SET status = ?, verified_sha256 = ?, published_at = ? WHERE id = ?', 'published', hash, now, a.id),
      stmt(env, 'UPDATE contributors SET upload_bytes_total = upload_bytes_total + ? WHERE id = ?', bytes.byteLength, actor.id),
      usageStmt(env, actor.id, 'upload_bytes', bytes.byteLength),
      eventStmt(env, { type: 'artifact.published', actor_id: actor.id, entity_type: 'artifact', entity_id: a.id, payload: { byte_size: bytes.byteLength, sha256: hash } }),
    ]);
  } catch (e) {
    await release();
    throw e;
  }
  return c.json(S.artifactOut(env, (await one(env, 'SELECT * FROM artifacts WHERE id = ?', a.id))!));
});

work.get('/v1/artifacts/:id', async (c) => {
  const a = await one(c.env, 'SELECT * FROM artifacts WHERE id = ?', c.req.param('id'));
  if (!a) throw notFound('Artifact not found');
  if (a.status === 'removed') throw gone('Artifact was removed');
  return c.json(S.artifactOut(c.env, a));
});

// ---------------------------------------------------------------------------------------------
// Contributions
// ---------------------------------------------------------------------------------------------

work.get('/v1/contributions', async (c) => {
  const env = c.env;
  const { limit, cursor } = pageParams(c);
  const where = [`c.status NOT IN ('hidden','redacted')`];
  const params: unknown[] = [];
  const projectKey = c.req.query('project');
  if (projectKey) {
    where.push('c.project_id = ?');
    params.push((await loadProject(env, projectKey)).id);
  }
  const q = (name: string, sql: string) => {
    const v = c.req.query(name);
    if (v !== undefined) {
      where.push(sql);
      params.push(v);
    }
  };
  q('kind', 'c.kind = ?');
  q('author', 'c.author_id = ?');
  q('status', 'c.status = ?');
  q('contract_version', 'cr.contract_version = ?');
  const flag = (name: string, sqlTrue: string, sqlFalse: string) => {
    const v = c.req.query(name);
    if (v === 'true') where.push(sqlTrue);
    else if (v === 'false') where.push(sqlFalse);
  };
  flag('evidence_attached', 'f.evidence_attached = 1', 'f.evidence_attached = 0');
  flag('reproduction_reported', 'f.reproductions_reported > 0', 'f.reproductions_reported = 0');
  flag('independent_implementation_reported', 'f.independent_implementations_reported > 0', 'f.independent_implementations_reported = 0');
  flag('formal_check_reported', 'f.formal_checks_reported > 0', 'f.formal_checks_reported = 0');
  flag('objection_unresolved', 'f.objections_unresolved > 0', 'f.objections_unresolved = 0');
  flag('needs_check', `EXISTS (SELECT 1 FROM tasks t WHERE t.target_contribution_id = c.id AND t.status = 'open')`, `NOT EXISTS (SELECT 1 FROM tasks t WHERE t.target_contribution_id = c.id AND t.status = 'open')`);
  q('prediction_outcome', 'f.prediction_outcome = ?');
  if (cursor) {
    where.push('c.id > ?');
    params.push(cursor);
  }
  const rows = await many(
    env,
    `SELECT c.* FROM contributions c JOIN contribution_facets f ON f.contribution_id = c.id
       JOIN contribution_revisions cr ON cr.contribution_id = c.id AND cr.revision = c.current_revision
      WHERE ${where.join(' AND ')} ORDER BY c.id LIMIT ?`,
    ...params,
    limit + 1,
  );
  return c.json({ items: await briefsFor(env, rows.slice(0, limit)), next_cursor: rows.length > limit ? rows[limit - 1].id : null });
});

work.post('/v1/contributions', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'ContributionCreate');
  const project = await loadProject(env, req.project_id);
  const roles = await projectRoles(env, project.id, actor.id);
  requireWritable(project, actor, roles);
  const contractVersion = contractVersionFor(project, req.contract_version);
  await requireOwnRun(env, actor, req.run_id);
  if (req.task_id && !(await one(env, 'SELECT id FROM tasks WHERE id = ? AND project_id = ?', req.task_id, project.id))) throw notFound('Task not found in this project');
  await checkArtifactLinks(env, actor, req.artifacts ?? []);
  for (const rel of req.relations ?? []) {
    if (!(await one(env, 'SELECT id FROM contributions WHERE id = ?', rel.to_id))) throw notFound(`Related contribution ${rel.to_id} not found`);
  }
  if (req.kind === 'prediction') {
    const p = req.prediction;
    if (p.resolver_id === actor.id) throw badRequest('The resolver must not be the author');
    if (!(await one(env, `SELECT id FROM contributors WHERE id = ? AND status = 'active'`, p.resolver_id))) throw notFound('Resolver not found');
    const maxDeadline = new Date();
    maxDeadline.setUTCFullYear(maxDeadline.getUTCFullYear() + LIMITS.prediction_max_years);
    if (p.deadline <= today() || p.deadline > maxDeadline.toISOString().slice(0, 10)) throw badRequest(`deadline must be after today and within ${LIMITS.prediction_max_years} years`);
  }
  const release = await reserveQuota(env, actor, 'contributions');
  const id = ulid();
  const now = nowIso();
  const stmts: D1PreparedStatement[] = [
    stmt(env, 'INSERT INTO contributions (id, project_id, kind, author_id, task_id, license, status, current_revision, created_at) VALUES (?,?,?,?,?,?,?,?,?)', id, project.id, req.kind, actor.id, req.task_id ?? null, req.license ?? 'CC-BY-4.0', 'active', 1, now),
    stmt(
      env,
      'INSERT INTO contribution_revisions (contribution_id, revision, title, claim, note_json, note_md, fields_json, change_summary, contract_version, author_id, run_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
      id, 1, req.title, req.claim, JSON.stringify(req.note), req.note_md ?? null, JSON.stringify(req.fields ?? {}), null, contractVersion, actor.id, req.run_id, now,
    ),
  ];
  for (const l of req.artifacts ?? []) stmts.push(stmt(env, 'INSERT INTO contribution_artifacts (contribution_id, revision, artifact_id, role) VALUES (?,?,?,?)', id, 1, l.artifact_id, l.role));
  for (const rel of req.relations ?? []) {
    const rid = ulid();
    stmts.push(
      stmt(env, 'INSERT INTO relations (id, from_id, from_revision, type, to_id, to_revision, note, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)', rid, id, 1, rel.type, rel.to_id, rel.to_revision ?? null, rel.note ?? null, actor.id, now),
      eventStmt(env, { type: 'relation.created', actor_id: actor.id, project_id: project.id, entity_type: 'relation', entity_id: rid, payload: { from_id: id, type: rel.type, to_id: rel.to_id } }),
    );
  }
  if (req.kind === 'prediction') {
    const p = req.prediction;
    stmts.push(
      stmt(env, 'INSERT INTO predictions (contribution_id, statement, registered_at, outcome_spec_md, criteria_md, prior_access_md, deadline, resolver_id, status) VALUES (?,?,?,?,?,?,?,?,?)', id, p.statement, now, p.outcome_spec_md, p.criteria_md, p.prior_access_md, p.deadline, p.resolver_id, 'awaiting_resolver'),
      eventStmt(env, { type: 'prediction.frozen', actor_id: actor.id, project_id: project.id, entity_type: 'prediction', entity_id: id, payload: { deadline: p.deadline, resolver_id: p.resolver_id } }),
    );
  }
  stmts.push(
    usageStmt(env, actor.id, 'contributions'),
    eventStmt(env, { type: 'contribution.created', actor_id: actor.id, project_id: project.id, entity_type: 'contribution', entity_id: id, revision: 1, payload: { kind: req.kind, title: req.title, claim: req.claim, contract_version: contractVersion } }),
  );
  try {
    await batch(env, stmts);
  } catch (e) {
    await release();
    mapConstraint(e);
  }
  return c.json(await contributionFull(env, (await one(env, 'SELECT * FROM contributions WHERE id = ?', id))!), 201);
});

work.get('/v1/contributions/:id', async (c) => c.json(await contributionFull(c.env, await loadContribution(c.env, c.req.param('id')))));

work.get('/v1/contributions/:id/revisions/:revision', async (c) => {
  const contribution = await loadContribution(c.env, c.req.param('id'));
  return c.json(await revisionFull(c.env, contribution.id, Number(c.req.param('revision'))));
});

work.post('/v1/contributions/:id/revisions', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const contribution = await loadContribution(env, c.req.param('id'));
  if (contribution.author_id !== actor.id) throw forbidden('Only the author publishes revisions');
  if (contribution.status !== 'active') throw conflict(`Contribution is ${contribution.status}`);
  const project = (await one(env, 'SELECT * FROM projects WHERE id = ?', contribution.project_id))!;
  requireWritable(project, actor, await projectRoles(env, project.id, actor.id));
  const req = body(c, 'RevisionCreate');
  if (RESULT_KINDS.has(contribution.kind)) {
    const errors = validationErrors('ResultEvidenceRequirement', req.fields ?? {});
    if (errors.length) throw badRequest('Result-like contributions need would_refute and a way to check', errors.map((e) => ({ ...e, field: e.field ? `fields.${e.field}` : 'fields' })));
  }
  const contractVersion = contractVersionFor(project, req.contract_version);
  await requireOwnRun(env, actor, req.run_id);
  await checkArtifactLinks(env, actor, req.artifacts ?? []);
  const previous = (await one(env, 'SELECT * FROM contribution_revisions WHERE contribution_id = ? AND revision = ?', contribution.id, contribution.current_revision))!;
  const release = await reserveQuota(env, actor, 'revisions');
  const revision = contribution.current_revision + 1;
  const now = nowIso();
  const stmts: D1PreparedStatement[] = [
    stmt(
      env,
      'INSERT INTO contribution_revisions (contribution_id, revision, title, claim, note_json, note_md, fields_json, change_summary, contract_version, author_id, run_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
      contribution.id, revision, req.title ?? previous.title, req.claim ?? previous.claim, JSON.stringify(req.note), req.note_md ?? null, JSON.stringify(req.fields ?? {}), req.change_summary, contractVersion, actor.id, req.run_id, now,
    ),
    stmt(env, 'UPDATE contributions SET current_revision = ? WHERE id = ?', revision, contribution.id),
  ];
  for (const l of req.artifacts ?? []) stmts.push(stmt(env, 'INSERT INTO contribution_artifacts (contribution_id, revision, artifact_id, role) VALUES (?,?,?,?)', contribution.id, revision, l.artifact_id, l.role));
  stmts.push(
    usageStmt(env, actor.id, 'revisions'),
    eventStmt(env, { type: 'contribution.revised', actor_id: actor.id, project_id: project.id, entity_type: 'contribution', entity_id: contribution.id, revision, payload: { change_summary: req.change_summary, contract_version: contractVersion } }),
  );
  try {
    await batch(env, stmts);
  } catch (e) {
    await release();
    mapConstraint(e);
  }
  return c.json(await contributionFull(env, (await one(env, 'SELECT * FROM contributions WHERE id = ?', contribution.id))!), 201);
});

work.post('/v1/contributions/:id/withdraw', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const contribution = await loadContribution(env, c.req.param('id'));
  if (contribution.author_id !== actor.id) throw forbidden('Only the author withdraws a contribution');
  if (contribution.status !== 'active') throw conflict(`Contribution is ${contribution.status}`);
  await requireProjectWritable(env, actor, contribution.project_id);
  const req = body(c, 'WithdrawRequest');
  const now = nowIso();
  const stmts = [
    stmt(env, 'UPDATE contributions SET status = ?, withdrawn_at = ?, withdrawn_reason = ? WHERE id = ?', 'withdrawn', now, req.reason, contribution.id),
    eventStmt(env, { type: 'contribution.withdrawn', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'contribution', entity_id: contribution.id, payload: { reason: req.reason } }),
  ];
  if (contribution.kind === 'prediction') {
    stmts.push(
      stmt(env, `UPDATE predictions SET status = 'withdrawn' WHERE contribution_id = ? AND status IN ('awaiting_resolver','registered')`, contribution.id),
      eventStmt(env, { type: 'prediction.withdrawn', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'prediction', entity_id: contribution.id, payload: {} }),
    );
  }
  await batch(env, stmts);
  return c.json(await contributionFull(env, (await one(env, 'SELECT * FROM contributions WHERE id = ?', contribution.id))!));
});

work.post('/v1/contributions/:id/relations', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const contribution = await loadContribution(env, c.req.param('id'));
  if (contribution.author_id !== actor.id) throw forbidden('Only the author adds relations');
  await requireProjectWritable(env, actor, contribution.project_id);
  const req = body(c, 'RelationCreate');
  if (!(await one(env, 'SELECT id FROM contributions WHERE id = ?', req.to_id))) throw notFound('Related contribution not found');
  const id = ulid();
  await batch(env, [
    stmt(env, 'INSERT INTO relations (id, from_id, from_revision, type, to_id, to_revision, note, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)', id, contribution.id, contribution.current_revision, req.type, req.to_id, req.to_revision ?? null, req.note ?? null, actor.id, nowIso()),
    eventStmt(env, { type: 'relation.created', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'relation', entity_id: id, payload: { from_id: contribution.id, type: req.type, to_id: req.to_id } }),
  ]);
  return c.json(S.relationOut((await one(env, 'SELECT * FROM relations WHERE id = ?', id))!), 201);
});

// ---------------------------------------------------------------------------------------------
// Receipts
// ---------------------------------------------------------------------------------------------

work.get('/v1/contributions/:id/receipts', async (c) => {
  const env = c.env;
  const contribution = await loadContribution(env, c.req.param('id'));
  // A caller-supplied status filter is intersected with the public statuses; it never reveals moderated receipts (W1).
  const status = c.req.query('status');
  if (status && !PUBLIC_RECEIPT_STATUSES.has(status)) return c.json({ items: [] });
  const rows = status
    ? await many(env, `SELECT r.*, ${RECEIPT_OBJECTIONS_SQL} FROM receipts r WHERE r.contribution_id = ? AND r.status = ? ORDER BY r.revision, r.created_at`, contribution.id, status)
    : await many(env, `SELECT r.*, ${RECEIPT_OBJECTIONS_SQL} FROM receipts r WHERE r.contribution_id = ? AND r.status IN ('active','corrected','withdrawn') ORDER BY r.revision, r.created_at`, contribution.id);
  return c.json({ items: await Promise.all(rows.map((r) => receiptFull(env, r))) });
});

async function insertReceipt(env: Env, actor: Actor, contribution: Row, revision: number, req: any, kind: string, correctsId: string | null): Promise<string> {
  const id = ulid();
  const now = nowIso();
  const stmts: D1PreparedStatement[] = [
    stmt(
      env,
      `INSERT INTO receipts (id, contribution_id, revision, kind, outcome, author_id, run_id, checked_md, not_checked_md, method_md, observations_md, metrics_json, environment_md, independence_json, relationships_md, evaluation_json, status, corrects_receipt_id, created_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      id, contribution.id, revision, kind, req.outcome, actor.id, req.run_id, req.checked_md, req.not_checked_md, req.method_md, req.observations_md,
      req.metrics ? JSON.stringify(req.metrics) : null, req.environment_md ?? null, JSON.stringify(req.independence), req.relationships_md, req.evaluation ? JSON.stringify(req.evaluation) : null, 'active', correctsId, now,
    ),
  ];
  for (const l of req.artifacts ?? []) stmts.push(stmt(env, 'INSERT INTO receipt_artifacts (receipt_id, artifact_id, role) VALUES (?,?,?)', id, l.artifact_id, l.role));
  stmts.push(usageStmt(env, actor.id, 'receipts'));
  if (correctsId) {
    stmts.push(stmt(env, `UPDATE receipts SET status = 'corrected' WHERE id = ?`, correctsId));
    if (kind === 'prediction_resolution') {
      stmts.push(
        stmt(env, `UPDATE predictions SET outcome = ?, resolved_by_receipt_id = ?, resolved_at = ? WHERE contribution_id = ? AND resolved_by_receipt_id = ?`, req.outcome, id, now, contribution.id, correctsId),
        eventStmt(env, { type: 'prediction.resolved', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'prediction', entity_id: contribution.id, payload: { outcome: req.outcome, receipt_id: id, corrects: correctsId } }),
      );
    }
    stmts.push(eventStmt(env, { type: 'receipt.corrected', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'receipt', entity_id: id, revision, payload: { corrects: correctsId, kind, outcome: req.outcome } }));
  } else {
    stmts.push(eventStmt(env, { type: 'receipt.created', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'receipt', entity_id: id, revision, payload: { contribution_id: contribution.id, kind, outcome: req.outcome } }));
  }
  await batch(env, stmts);
  return id;
}

work.post('/v1/contributions/:id/revisions/:revision/receipts', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const contribution = await loadContribution(env, c.req.param('id'));
  const revision = Number(c.req.param('revision'));
  if (!(await one(env, 'SELECT 1 FROM contribution_revisions WHERE contribution_id = ? AND revision = ?', contribution.id, revision))) throw notFound('Revision not found');
  if (contribution.author_id === actor.id) throw forbidden('You cannot write a receipt on your own contribution');
  await requireProjectWritable(env, actor, contribution.project_id);
  const req = body(c, 'ReceiptCreate');
  if (req.kind === 'prediction_resolution') throw badRequest('Prediction resolutions are created through the resolution route by the agreed resolver');
  await requireOwnRun(env, actor, req.run_id);
  await checkArtifactLinks(env, actor, req.artifacts ?? []);
  const release = await reserveQuota(env, actor, 'receipts');
  let id: string;
  try {
    id = await insertReceipt(env, actor, contribution, revision, req, req.kind, null);
  } catch (e) {
    await release();
    throw e;
  }
  return c.json(await receiptFull(env, (await one(env, 'SELECT * FROM receipts WHERE id = ?', id))!), 201);
});

async function loadReceipt(env: Env, id: string): Promise<Row> {
  const r = await one(env, `SELECT r.*, ${RECEIPT_OBJECTIONS_SQL} FROM receipts r WHERE r.id = ?`, id);
  if (!r) throw notFound('Receipt not found');
  if (r.status === 'hidden' || r.status === 'redacted') throw gone(`Receipt is ${r.status}`);
  return r;
}

work.get('/v1/receipts/:id', async (c) => c.json(await receiptFull(c.env, await loadReceipt(c.env, c.req.param('id')))));

work.post('/v1/receipts/:id/corrections', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const old = await loadReceipt(env, c.req.param('id'));
  if (old.author_id !== actor.id) throw forbidden('Only the author corrects a receipt');
  if (old.status !== 'active') throw conflict(`Receipt is ${old.status}`);
  const req = body(c, 'ReceiptCreate');
  if (req.kind !== old.kind) throw conflict(`A correction keeps the kind ${old.kind}`);
  await requireOwnRun(env, actor, req.run_id);
  await checkArtifactLinks(env, actor, req.artifacts ?? []);
  const contribution = (await one(env, 'SELECT * FROM contributions WHERE id = ?', old.contribution_id))!;
  await requireProjectWritable(env, actor, contribution.project_id);
  const release = await reserveQuota(env, actor, 'receipts');
  let id: string;
  try {
    id = await insertReceipt(env, actor, contribution, old.revision, req, old.kind, old.id);
  } catch (e) {
    await release();
    throw e;
  }
  return c.json(await receiptFull(env, (await one(env, 'SELECT * FROM receipts WHERE id = ?', id))!), 201);
});

/** Statements that return a prediction to `registered` when its active resolution receipt goes away. */
export function unresolveStmts(env: Env, actorId: string, receipt: Row): D1PreparedStatement[] {
  if (receipt.kind !== 'prediction_resolution') return [];
  return [
    stmt(env, `UPDATE predictions SET status = 'registered', outcome = NULL, resolved_by_receipt_id = NULL, resolved_at = NULL WHERE contribution_id = ? AND resolved_by_receipt_id = ?`, receipt.contribution_id, receipt.id),
    eventStmt(env, { type: 'prediction.unresolved', actor_id: actorId, entity_type: 'prediction', entity_id: receipt.contribution_id, payload: { receipt_id: receipt.id } }),
  ];
}

work.post('/v1/receipts/:id/withdraw', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const r = await loadReceipt(env, c.req.param('id'));
  if (r.author_id !== actor.id) throw forbidden('Only the author withdraws a receipt');
  if (r.status !== 'active') throw conflict(`Receipt is ${r.status}`);
  const req = body(c, 'WithdrawRequest');
  const contribution = (await one(env, 'SELECT project_id FROM contributions WHERE id = ?', r.contribution_id))!;
  await requireProjectWritable(env, actor, contribution.project_id);
  await batch(env, [
    stmt(env, `UPDATE receipts SET status = 'withdrawn', withdrawn_reason = ? WHERE id = ?`, req.reason, r.id),
    ...unresolveStmts(env, actor.id, r),
    eventStmt(env, { type: 'receipt.withdrawn', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'receipt', entity_id: r.id, revision: r.revision, payload: { reason: req.reason } }),
  ]);
  return c.json(await receiptFull(env, await loadReceipt(env, r.id)));
});

// ---------------------------------------------------------------------------------------------
// Predictions
// ---------------------------------------------------------------------------------------------

work.get('/v1/predictions', async (c) => {
  const env = c.env;
  const { limit, cursor } = pageParams(c);
  const where = [`c.status NOT IN ('hidden','redacted')`];
  const params: unknown[] = [];
  const projectKey = c.req.query('project');
  if (projectKey) {
    where.push('c.project_id = ?');
    params.push((await loadProject(env, projectKey)).id);
  }
  for (const [name, sql] of [['status', 'p.status = ?'], ['resolver', 'p.resolver_id = ?'], ['due_before', 'p.deadline < ?']] as const) {
    const v = c.req.query(name);
    if (v) {
      where.push(sql);
      params.push(v);
    }
  }
  if (cursor) {
    where.push('p.contribution_id > ?');
    params.push(cursor);
  }
  const rows = await many(env, `SELECT p.* FROM predictions p JOIN contributions c ON c.id = p.contribution_id WHERE ${where.join(' AND ')} ORDER BY p.contribution_id LIMIT ?`, ...params, limit + 1);
  return c.json({ items: rows.slice(0, limit).map(S.predictionOut), next_cursor: rows.length > limit ? rows[limit - 1].contribution_id : null });
});

async function loadPrediction(env: Env, id: string): Promise<{ prediction: Row; contribution: Row }> {
  const contribution = await loadContribution(env, id);
  const prediction = await one(env, 'SELECT * FROM predictions WHERE contribution_id = ?', id);
  if (!prediction) throw notFound('This contribution is not a prediction');
  return { prediction, contribution };
}

work.post('/v1/predictions/:id/resolver', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const { prediction, contribution } = await loadPrediction(env, c.req.param('id'));
  if (contribution.author_id !== actor.id) throw forbidden('Only the author nominates a resolver');
  if (prediction.status !== 'awaiting_resolver') throw conflict(`Prediction is ${prediction.status}`);
  await requireProjectWritable(env, actor, contribution.project_id);
  const req = body(c, 'ResolverNomination');
  if (req.resolver_id === actor.id) throw badRequest('The resolver must not be the author');
  if (!(await one(env, `SELECT id FROM contributors WHERE id = ? AND status = 'active'`, req.resolver_id))) throw notFound('Resolver not found');
  await batch(env, [
    stmt(env, 'UPDATE predictions SET resolver_id = ?, resolver_agreed_at = NULL WHERE contribution_id = ?', req.resolver_id, contribution.id),
    eventStmt(env, { type: 'prediction.resolver_nominated', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'prediction', entity_id: contribution.id, payload: { resolver_id: req.resolver_id } }),
  ]);
  return c.json(S.predictionOut((await one(env, 'SELECT * FROM predictions WHERE contribution_id = ?', contribution.id))!));
});

work.post('/v1/predictions/:id/resolver-agreement', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const { prediction, contribution } = await loadPrediction(env, c.req.param('id'));
  if (prediction.resolver_id !== actor.id) throw forbidden('Only the nominated resolver accepts');
  if (prediction.status !== 'awaiting_resolver') throw conflict(`Prediction is ${prediction.status}`);
  await requireProjectWritable(env, actor, contribution.project_id);
  const now = nowIso();
  await batch(env, [
    stmt(env, `UPDATE predictions SET status = 'registered', resolver_agreed_at = ? WHERE contribution_id = ?`, now, contribution.id),
    eventStmt(env, { type: 'prediction.resolver_agreed', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'prediction', entity_id: contribution.id, payload: {} }),
  ]);
  return c.json(S.predictionOut((await one(env, 'SELECT * FROM predictions WHERE contribution_id = ?', contribution.id))!));
});

work.post('/v1/predictions/:id/resolution', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const { prediction, contribution } = await loadPrediction(env, c.req.param('id'));
  if (prediction.resolver_id !== actor.id || !prediction.resolver_agreed_at) throw forbidden('Only the agreed resolver resolves');
  if (prediction.status !== 'registered') throw conflict(`Prediction is ${prediction.status}`);
  await requireProjectWritable(env, actor, contribution.project_id);
  const req = body(c, 'ResolutionCreate');
  await requireOwnRun(env, actor, req.run_id);
  await checkArtifactLinks(env, actor, req.artifacts ?? []);
  const release = await reserveQuota(env, actor, 'receipts');
  const id = ulid();
  const now = nowIso();
  const stmts: D1PreparedStatement[] = [
    stmt(
      env,
      `INSERT INTO receipts (id, contribution_id, revision, kind, outcome, author_id, run_id, checked_md, not_checked_md, method_md, observations_md, metrics_json, environment_md, independence_json, relationships_md, status, created_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      id, contribution.id, contribution.current_revision, 'prediction_resolution', req.outcome, actor.id, req.run_id, req.checked_md, req.not_checked_md, req.method_md, req.observations_md,
      req.metrics ? JSON.stringify(req.metrics) : null, req.environment_md ?? null, JSON.stringify(req.independence), req.relationships_md, 'active', now,
    ),
    stmt(env, `UPDATE predictions SET status = 'resolved', outcome = ?, resolved_by_receipt_id = ?, resolved_at = ? WHERE contribution_id = ?`, req.outcome, id, now, contribution.id),
    usageStmt(env, actor.id, 'receipts'),
    eventStmt(env, { type: 'receipt.created', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'receipt', entity_id: id, revision: contribution.current_revision, payload: { contribution_id: contribution.id, kind: 'prediction_resolution', outcome: req.outcome } }),
    eventStmt(env, { type: 'prediction.resolved', actor_id: actor.id, project_id: contribution.project_id, entity_type: 'prediction', entity_id: contribution.id, payload: { outcome: req.outcome, receipt_id: id } }),
  ];
  for (const l of req.artifacts ?? []) stmts.push(stmt(env, 'INSERT INTO receipt_artifacts (receipt_id, artifact_id, role) VALUES (?,?,?)', id, l.artifact_id, l.role));
  try {
    await batch(env, stmts);
  } catch (e) {
    await release();
    throw e;
  }
  return c.json(S.predictionOut((await one(env, 'SELECT * FROM predictions WHERE contribution_id = ?', contribution.id))!), 201);
});

// ---------------------------------------------------------------------------------------------
// Objections
// ---------------------------------------------------------------------------------------------

work.get('/v1/objections', async (c) => {
  const env = c.env;
  const { limit, cursor } = pageParams(c);
  const where: string[] = [];
  const params: unknown[] = [];
  const projectKey = c.req.query('project');
  if (projectKey) {
    where.push(`(${OBJECTION_PROJECT_SQL}) = ?`);
    params.push((await loadProject(env, projectKey)).id);
  }
  for (const [name, sql] of [['target_type', 'o.target_type = ?'], ['target_id', 'o.target_id = ?']] as const) {
    const v = c.req.query(name);
    if (v) {
      where.push(sql);
      params.push(v);
    }
  }
  const status = c.req.query('status');
  if (status === 'hidden') return c.json({ items: [], next_cursor: null });
  if (status) {
    where.push('o.status = ?');
    params.push(status);
  } else where.push(`o.status IN ('open','answered')`);
  if (cursor) {
    where.push('o.id > ?');
    params.push(cursor);
  }
  const rows = await many(env, `SELECT o.*, ${OBJECTION_PROJECT_SQL} AS project_id FROM objections o WHERE ${where.join(' AND ')} ORDER BY o.id LIMIT ?`, ...params, limit + 1);
  return c.json({ items: await objectionsFull(env, rows.slice(0, limit)), next_cursor: rows.length > limit ? rows[limit - 1].id : null });
});

work.post('/v1/objections', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'ObjectionCreate');
  let projectId: string | null = null;
  switch (req.target_type) {
    case 'contribution': {
      const t = await loadContribution(env, req.target_id);
      if (req.target_revision && !(await one(env, 'SELECT 1 FROM contribution_revisions WHERE contribution_id = ? AND revision = ?', t.id, req.target_revision))) throw notFound('Target revision not found');
      projectId = t.project_id;
      break;
    }
    case 'receipt': {
      const r = await loadReceipt(env, req.target_id);
      projectId = (await one(env, 'SELECT project_id FROM contributions WHERE id = ?', r.contribution_id))!.project_id;
      break;
    }
    case 'post': {
      const p = await one(env, `SELECT * FROM posts WHERE id = ? AND status = 'visible'`, req.target_id);
      if (!p) throw notFound('Post not found');
      projectId = p.project_id;
      break;
    }
    case 'summary': {
      const p = await loadProject(env, req.target_id);
      if (req.target_revision && !(await one(env, 'SELECT 1 FROM project_summaries WHERE project_id = ? AND version = ?', p.id, req.target_revision))) throw notFound('Summary version not found');
      projectId = p.id;
      break;
    }
  }
  if (projectId) await requireProjectWritable(env, actor, projectId);
  if (req.run_id) await requireOwnRun(env, actor, req.run_id);
  const release = await reserveQuota(env, actor, 'objections');
  const id = ulid();
  try {
    await batch(env, [
      stmt(env, 'INSERT INTO objections (id, target_type, target_id, target_revision, kind, body_md, author_id, run_id, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)', id, req.target_type, req.target_id, req.target_revision ?? null, req.kind, req.body_md, actor.id, req.run_id ?? null, 'open', nowIso()),
      usageStmt(env, actor.id, 'objections'),
      eventStmt(env, { type: 'objection.created', actor_id: actor.id, project_id: projectId, entity_type: 'objection', entity_id: id, payload: { target_type: req.target_type, target_id: req.target_id, target_revision: req.target_revision ?? null, kind: req.kind } }),
    ]);
  } catch (e) {
    await release();
    throw e;
  }
  return c.json((await objectionsFull(env, [await loadObjection(env, id)]))[0], 201);
});

work.get('/v1/objections/:id', async (c) => c.json((await objectionsFull(c.env, [await loadObjection(c.env, c.req.param('id'))]))[0]));

work.post('/v1/objections/:id/resolve', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const o = await loadObjection(env, c.req.param('id'));
  if (o.status === 'resolved' || o.status === 'withdrawn') throw conflict(`Objection is already ${o.status}`);
  if (o.project_id) await requireProjectWritable(env, actor, o.project_id);
  const req = body(c, 'ObjectionResolve');
  let allowed = false;
  if (req.status === 'withdrawn') allowed = o.author_id === actor.id;
  else if (req.status === 'answered') {
    const targetAuthor =
      o.target_type === 'contribution'
        ? (await one(env, 'SELECT author_id FROM contributions WHERE id = ?', o.target_id))?.author_id
        : o.target_type === 'receipt'
          ? (await one(env, 'SELECT author_id FROM receipts WHERE id = ?', o.target_id))?.author_id
          : o.target_type === 'post'
            ? (await one(env, 'SELECT author_id FROM posts WHERE id = ?', o.target_id))?.author_id
            : null;
    allowed = targetAuthor === actor.id;
    if (!allowed && o.project_id) allowed = hasProjectRole(actor, await projectRoles(env, o.project_id, actor.id), 'maintainer', 'reviewer');
  } else if (req.status === 'resolved') {
    allowed = o.project_id ? hasProjectRole(actor, await projectRoles(env, o.project_id, actor.id), 'maintainer', 'reviewer') : actor.tier === 'maintainer';
  }
  if (!allowed) throw forbidden(`You may not mark this objection ${req.status}`);
  const now = nowIso();
  await batch(env, [
    stmt(env, 'UPDATE objections SET status = ?, resolved_at = ?, resolved_by = ?, resolution_md = ? WHERE id = ?', req.status, req.status === 'answered' ? null : now, req.status === 'answered' ? null : actor.id, req.resolution_md, o.id),
    eventStmt(env, { type: 'objection.resolved', actor_id: actor.id, project_id: o.project_id, entity_type: 'objection', entity_id: o.id, payload: { status: req.status } }),
  ]);
  return c.json((await objectionsFull(env, [await loadObjection(env, o.id)]))[0]);
});
