import type { Context } from 'hono';
import type { AppEnv, Env } from '../env';
import * as S from '../serialize';
import { isGlobalMaintainer, projectRoles, type Actor } from './auth';
import { many, one, placeholders, stmt, type Row } from './db';
import { badRequest, conflict, forbidden, gone, notFound } from './errors';
import { nowIso, ULID_RE } from './ids';
import { assertValid } from './validate';

/** Parse the JSON body captured by the idempotency middleware and validate it against a named schema. */
export function body<T = any>(c: Context<AppEnv>, schema: string): T {
  const raw = c.get('rawBody');
  if (raw === undefined) throw badRequest('A JSON body is required');
  let parsed: unknown;
  try {
    parsed = raw.trim() === '' ? {} : JSON.parse(raw);
  } catch {
    throw badRequest('Body is not valid JSON');
  }
  return assertValid<T>(schema, parsed);
}

export function pageParams(c: Context<AppEnv>): { limit: number; cursor: string | null } {
  const limit = Math.min(200, Math.max(1, Number(c.req.query('limit') ?? 50) || 50));
  return { limit, cursor: c.req.query('cursor') ?? null };
}

/** Cursor pagination over ULID ids: the cursor is the last id of the previous page. */
export function pageOut<T extends { id: string }>(rows: T[], limit: number, mapper: (r: T) => unknown = (r) => r) {
  const items = rows.slice(0, limit);
  return { items: items.map(mapper), next_cursor: rows.length > limit ? items[items.length - 1].id : null };
}

// D1 binds at most 100 parameters per statement, so every id-list query runs in chunks.
const CHUNK = 80;

export async function chunkedRows(env: Env, ids: string[], build: (ph: string) => string, extra: unknown[] = []): Promise<Row[]> {
  const out: Row[] = [];
  for (let i = 0; i < ids.length; i += CHUNK) {
    const slice = ids.slice(i, i + CHUNK);
    out.push(...(await many(env, build(placeholders(slice.length)), ...slice, ...extra)));
  }
  return out;
}

// ---------------------------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------------------------

export async function loadProject(env: Env, key: string): Promise<Row> {
  const p = ULID_RE.test(key)
    ? await one(env, 'SELECT * FROM projects WHERE id = ?', key)
    : await one(env, 'SELECT * FROM projects WHERE slug = ?', key.toLowerCase());
  if (!p) throw notFound('Project not found');
  return p;
}

export function projectRoleRows(env: Env, projectId: string): Promise<Row[]> {
  return many(
    env,
    `SELECT pr.*, c.handle FROM project_roles pr JOIN contributors c ON c.id = pr.contributor_id WHERE pr.project_id = ? ORDER BY pr.created_at`,
    projectId,
  );
}

export async function currentContract(env: Env, project: Row): Promise<Row | null> {
  if (!project.contract_version) return null;
  return one(env, 'SELECT * FROM project_contracts WHERE project_id = ? AND version = ?', project.id, project.contract_version);
}

export async function projectFull(env: Env, project: Row) {
  return S.projectOut(project, await projectRoleRows(env, project.id), await currentContract(env, project));
}

/** Writes to a project need it active and unlocked, unless the actor maintains it. */
export function requireWritable(project: Row, actor: Actor, roles: Set<string>): void {
  const privileged = isGlobalMaintainer(actor) || roles.has('maintainer');
  if (privileged) return;
  if (project.safety_locked) throw forbidden('This project is locked for safety review');
  if (project.status !== 'active') throw conflict(`Project is ${project.status}, not active`);
}

/**
 * The one writability rule for every project-scoped write. Callers resolve the effective project
 * first (a reply from its parent, a receipt from its contribution, a lease from its task) and then
 * call this, so no indirect route bypasses a lock or a paused project.
 */
export async function requireProjectWritable(env: Env, actor: Actor, projectId: string): Promise<Row> {
  const project = await one(env, 'SELECT * FROM projects WHERE id = ?', projectId);
  if (!project) throw notFound('Project not found');
  requireWritable(project, actor, await projectRoles(env, project.id, actor.id));
  return project;
}

/**
 * Remove copied content from every public projection of a record when it is hidden or redacted:
 * the record's event payloads become a tombstone and cached idempotent responses that carried the
 * record are dropped. The rows themselves stay, as the contract's tombstone rule requires.
 */
export function scrubStmts(env: Env, entityType: string, entityId: string): D1PreparedStatement[] {
  return [
    stmt(env, `UPDATE events SET payload_json = '{"tombstone":true}' WHERE entity_type = ? AND entity_id = ?`, entityType, entityId),
    stmt(env, 'DELETE FROM idempotency_keys WHERE response_body LIKE ?', `%${entityId}%`),
  ];
}

// ---------------------------------------------------------------------------------------------
// Contributions, receipts, revisions
// ---------------------------------------------------------------------------------------------

export const RECEIPT_OBJECTIONS_SQL = `(SELECT COUNT(*) FROM objections o WHERE o.target_type = 'receipt' AND o.target_id = r.id AND o.status IN ('open','answered')) AS objections_unresolved`;
export const PUBLIC_RECEIPT_STATUSES = new Set(['active', 'corrected', 'withdrawn']);

export async function loadContribution(env: Env, id: string): Promise<Row> {
  const c = await one(env, 'SELECT * FROM contributions WHERE id = ?', id);
  if (!c) throw notFound('Contribution not found');
  if (c.status === 'hidden' || c.status === 'redacted') throw gone(`Contribution is ${c.status}`);
  return c;
}

export async function facetsFor(env: Env, ids: string[]): Promise<Map<string, Row>> {
  const rows = await chunkedRows(
    env,
    ids,
    (ph) =>
      `SELECT f.*, (SELECT COUNT(*) FROM tasks t WHERE t.target_contribution_id = f.contribution_id AND t.status = 'open') AS open_check_requests
         FROM contribution_facets f WHERE f.contribution_id IN (${ph})`,
  );
  return new Map(rows.map((r) => [r.contribution_id as string, r]));
}

async function groupBy(env: Env, ids: string[], build: (ph: string) => string, key: string, extra: unknown[] = []): Promise<Map<string, Row[]>> {
  const out = new Map<string, Row[]>();
  for (const r of await chunkedRows(env, ids, build, extra)) {
    const k = r[key] as string;
    if (!out.has(k)) out.set(k, []);
    out.get(k)!.push(r);
  }
  return out;
}

export function receiptsFor(env: Env, ids: string[]): Promise<Map<string, Row[]>> {
  return groupBy(
    env,
    ids,
    (ph) => `SELECT r.*, ${RECEIPT_OBJECTIONS_SQL} FROM receipts r WHERE r.contribution_id IN (${ph}) AND r.status IN ('active','corrected','withdrawn') ORDER BY r.created_at`,
    'contribution_id',
  );
}

export function relationsFor(env: Env, ids: string[]): Promise<Map<string, Row[]>> {
  return groupBy(env, ids, (ph) => `SELECT * FROM relations WHERE from_id IN (${ph}) ORDER BY created_at`, 'from_id');
}

export async function currentRevisionsFor(env: Env, ids: string[]): Promise<Map<string, Row>> {
  const rows = await chunkedRows(
    env,
    ids,
    (ph) => `SELECT r.* FROM contribution_revisions r JOIN contributions c ON c.id = r.contribution_id AND c.current_revision = r.revision WHERE c.id IN (${ph})`,
  );
  return new Map(rows.map((r) => [r.contribution_id as string, r]));
}

export async function briefsFor(env: Env, contributions: Row[]) {
  const ids = contributions.map((c) => c.id as string);
  const [revs, facets, receipts, relations] = await Promise.all([
    currentRevisionsFor(env, ids),
    facetsFor(env, ids),
    receiptsFor(env, ids),
    relationsFor(env, ids),
  ]);
  return contributions.map((c) =>
    S.contributionBriefOut(c, revs.get(c.id) ?? {}, facets.get(c.id) ?? {}, receipts.get(c.id) ?? [], relations.get(c.id) ?? []),
  );
}

export async function receiptFull(env: Env, r: Row) {
  const [run, links, correctedBy] = await Promise.all([
    one(env, 'SELECT * FROM runs WHERE id = ?', r.run_id),
    many(env, 'SELECT artifact_id, role FROM receipt_artifacts WHERE receipt_id = ? ORDER BY artifact_id', r.id),
    one(env, 'SELECT id FROM receipts WHERE corrects_receipt_id = ?', r.id),
  ]);
  if (r.objections_unresolved === undefined) {
    const o = await one<{ n: number }>(env, `SELECT COUNT(*) AS n FROM objections WHERE target_type = 'receipt' AND target_id = ? AND status IN ('open','answered')`, r.id);
    r = { ...r, objections_unresolved: o?.n ?? 0 };
  }
  return S.receiptOut({ ...r, corrected_by_receipt_id: correctedBy?.id ?? null }, run, links);
}

export async function revisionFull(env: Env, contributionId: string, revision: number) {
  const rev = await one(env, 'SELECT * FROM contribution_revisions WHERE contribution_id = ? AND revision = ?', contributionId, revision);
  if (!rev) throw notFound('Revision not found');
  const [run, artifacts, receiptRows] = await Promise.all([
    one(env, 'SELECT * FROM runs WHERE id = ?', rev.run_id),
    many(env, `SELECT a.*, ca.role FROM contribution_artifacts ca JOIN artifacts a ON a.id = ca.artifact_id WHERE ca.contribution_id = ? AND ca.revision = ? AND a.status = 'published' ORDER BY ca.role`, contributionId, revision),
    many(env, `SELECT r.*, ${RECEIPT_OBJECTIONS_SQL} FROM receipts r WHERE r.contribution_id = ? AND r.revision = ? AND r.status IN ('active','corrected','withdrawn') ORDER BY r.created_at`, contributionId, revision),
  ]);
  const receipts = await Promise.all(receiptRows.map((r) => receiptFull(env, r)));
  return S.revisionOut(env, rev, run, artifacts, receipts);
}

export async function contributionFull(env: Env, c: Row) {
  const [[brief], revision, prediction] = await Promise.all([
    briefsFor(env, [c]),
    revisionFull(env, c.id, c.current_revision),
    c.kind === 'prediction' ? one(env, 'SELECT * FROM predictions WHERE contribution_id = ?', c.id) : Promise.resolve(null),
  ]);
  return {
    ...brief,
    task_id: c.task_id ?? null,
    license: c.license,
    revision,
    prediction: prediction ? S.predictionOut(prediction) : null,
    withdrawn_at: c.withdrawn_at ?? null,
    withdrawn_reason: c.withdrawn_reason ?? null,
  };
}

// ---------------------------------------------------------------------------------------------
// Tasks, posts, objections
// ---------------------------------------------------------------------------------------------

export async function tasksFull(env: Env, tasks: Row[]) {
  if (!tasks.length) return [];
  const ids = tasks.map((t) => t.id as string);
  const leases = await chunkedRows(env, ids, (ph) => `SELECT * FROM leases WHERE task_id IN (${ph}) AND released_at IS NULL AND expires_at > ?`, [nowIso()]);
  const targets = [...new Set(tasks.map((t) => t.target_contribution_id).filter(Boolean))] as string[];
  const claims = await chunkedRows(
    env,
    targets,
    (ph) => `SELECT c.id, r.claim FROM contributions c JOIN contribution_revisions r ON r.contribution_id = c.id AND r.revision = c.current_revision WHERE c.id IN (${ph})`,
  );
  const claimMap = new Map(claims.map((r) => [r.id as string, r.claim as string]));
  return tasks.map((t) => S.taskOut(t, leases.filter((l) => l.task_id === t.id), claimMap.get(t.target_contribution_id) ?? null));
}

export async function postFull(env: Env, p: Row) {
  const revs = await many(env, 'SELECT * FROM post_revisions WHERE post_id = ? ORDER BY revision', p.id);
  return S.postOut(p, revs);
}

/** SQL expression giving the project an objection belongs to, from its target. */
export const OBJECTION_PROJECT_SQL = `CASE o.target_type
  WHEN 'contribution' THEN (SELECT project_id FROM contributions WHERE id = o.target_id)
  WHEN 'receipt' THEN (SELECT c.project_id FROM receipts r JOIN contributions c ON c.id = r.contribution_id WHERE r.id = o.target_id)
  WHEN 'post' THEN (SELECT project_id FROM posts WHERE id = o.target_id)
  WHEN 'summary' THEN o.target_id END`;

export async function objectionsFull(env: Env, rows: Row[]) {
  return Promise.all(
    rows.map(async (o) => {
      const responses = await many(env, `SELECT * FROM posts WHERE objection_id = ? AND status = 'visible' ORDER BY created_at`, o.id);
      return S.objectionOut(o, await Promise.all(responses.map((p) => postFull(env, p))));
    }),
  );
}

export async function loadObjection(env: Env, id: string): Promise<Row> {
  const o = await one(env, `SELECT o.*, ${OBJECTION_PROJECT_SQL} AS project_id FROM objections o WHERE o.id = ?`, id);
  if (!o) throw notFound('Objection not found');
  if (o.status === 'hidden') throw gone('Objection is hidden');
  return o;
}
