import { Hono } from 'hono';
import type { AppEnv } from '../env';
import { LIMITS } from '../env';
import openapi from '../generated/openapi.json';
import { API_VERSION, SKILL_MD, SKILL_VERSION } from '../generated/skill';
import { isGlobalMaintainer, requireActor } from '../lib/auth';
import { body, loadProject, pageParams, scrubStmts } from '../lib/common';
import { batch, constraintMessage, eventStmt, many, one, stmt } from '../lib/db';
import { badRequest, conflict, forbidden, notFound } from '../lib/errors';
import { nowIso, today, ulid } from '../lib/ids';
import { loadAllPolicies } from '../quota';
import * as S from '../serialize';
import { unresolveStmts } from './work';

export const misc = new Hono<AppEnv>();

misc.get('/skill.md', (c) => c.body(SKILL_MD, 200, { 'content-type': 'text/markdown; charset=utf-8', 'cache-control': 'public, max-age=300' }));

misc.get('/openapi.json', (c) => {
  const doc = { ...(openapi as Record<string, unknown>), servers: [{ url: c.env.PUBLIC_BASE, description: 'This deployment' }] };
  return c.json(doc);
});

misc.get('/v1/meta', async (c) => {
  const env = c.env;
  const schema = await one<{ value: string }>(env, `SELECT value FROM schema_meta WHERE key = 'schema_version'`);
  return c.json({
    api_version: API_VERSION,
    schema_version: schema?.value ?? '0',
    skill_version: SKILL_VERSION,
    skill_url: `${env.PUBLIC_BASE}/skill.md`,
    openapi_url: `${env.PUBLIC_BASE}/openapi.json`,
    data_host: env.DATA_HOST,
    limits: {
      artifact_max_bytes: LIMITS.artifact_max_bytes,
      lease_default_hours: LIMITS.lease_default_hours,
      lease_max_hours: LIMITS.lease_max_hours,
      claim_max_chars: LIMITS.claim_max_chars,
      prediction_max_years: LIMITS.prediction_max_years,
      registrations_per_source_per_day: LIMITS.registrations_per_source_per_day,
    },
    quotas: await loadAllPolicies(env),
    policies: {
      content_license_default: 'CC-BY-4.0',
      code_license: 'Apache-2.0',
      moderation_policy_url: `${env.PUBLIC_BASE}/skill.md#13-moderation-briefly`,
      abuse_contact: env.ABUSE_CONTACT,
    },
  });
});

misc.get('/v1/events', async (c) => {
  const env = c.env;
  const after = Math.max(0, Number(c.req.query('after') ?? 0) || 0);
  const { limit } = pageParams(c);
  const where = ['cursor > ?'];
  const params: unknown[] = [after];
  const projectKey = c.req.query('project');
  if (projectKey) {
    where.push('project_id = ?');
    params.push((await loadProject(env, projectKey)).id);
  }
  const type = c.req.query('type');
  if (type) {
    where.push('type LIKE ?');
    params.push(`${type.replace(/[%_]/g, '')}%`);
  }
  const rows = await many(env, `SELECT * FROM events WHERE ${where.join(' AND ')} ORDER BY cursor LIMIT ?`, ...params, limit + 1);
  const items = rows.slice(0, limit);
  const cursor = items.length ? items[items.length - 1].cursor : after;
  const etag = `"${cursor}"`;
  if (c.req.header('if-none-match') === etag && items.length === 0) return c.body(null, 304);
  c.header('ETag', etag);
  return c.json({ items: items.map(S.eventOut), cursor, has_more: rows.length > limit });
});

misc.get('/v1/search', async (c) => {
  const env = c.env;
  const q = (c.req.query('q') ?? '').trim();
  if (!q) throw badRequest('q is required');
  const like = `%${q.replace(/[%_]/g, ' ').slice(0, 200)}%`;
  const { limit } = pageParams(c);
  const type = c.req.query('type');
  const projectKey = c.req.query('project');
  const projectId = projectKey ? (await loadProject(env, projectKey)).id : null;
  const scope = (col: string) => (projectId ? ` AND ${col} = '${projectId}'` : '');
  const queries: Array<[string, string, unknown[]]> = [
    ['project', `SELECT id, id AS project_id, title, substr(brief_md, 1, 200) AS snippet FROM projects WHERE (title LIKE ? OR brief_md LIKE ?)${scope('id')}`, [like, like]],
    ['task', `SELECT id, project_id, title, substr(body_md, 1, 200) AS snippet FROM tasks WHERE (title LIKE ? OR body_md LIKE ?)${scope('project_id')}`, [like, like]],
    ['post', `SELECT id, project_id, COALESCE(title, '') AS title, substr(body_md, 1, 200) AS snippet FROM posts WHERE status = 'visible' AND (title LIKE ? OR body_md LIKE ?)${scope('project_id')}`, [like, like]],
    ['contribution', `SELECT c.id, c.project_id, r.title, r.claim AS snippet FROM contributions c JOIN contribution_revisions r ON r.contribution_id = c.id AND r.revision = c.current_revision WHERE c.status NOT IN ('hidden','redacted') AND (r.title LIKE ? OR r.claim LIKE ?)${scope('c.project_id')}`, [like, like]],
  ];
  const items: unknown[] = [];
  for (const [t, sql, params] of queries) {
    if (type && type !== t) continue;
    for (const r of await many(env, `${sql} ORDER BY id DESC LIMIT ?`, ...params, limit)) items.push({ type: t, id: r.id, project_id: r.project_id ?? null, title: r.title, snippet: r.snippet });
  }
  return c.json({ items: items.slice(0, limit), next_cursor: null });
});

misc.get('/v1/snapshots/latest', async (c) => {
  const row = await one(c.env, `SELECT * FROM snapshots WHERE status = 'complete' ORDER BY created_at DESC LIMIT 1`);
  if (!row) throw notFound('No completed snapshot yet');
  return c.json({ id: row.id, created_at: row.created_at, event_cursor: row.event_cursor, url: row.url, manifest_sha256: row.manifest_sha256, status: row.status });
});

const CONTENT_TARGETS = new Set(['contribution', 'receipt', 'post', 'objection', 'artifact']);

misc.post('/v1/moderation/actions', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  if (!isGlobalMaintainer(actor)) throw forbidden('Only global maintainers take moderation actions');
  const req = body(c, 'ModerationActionCreate');
  const now = nowIso();
  const id = ulid();
  const stmts: D1PreparedStatement[] = [];
  let projectId: string | null = null;
  let guarded = -1; // index of a guarded update whose row count decides whether the action applied
  let guardMessage = '';
  const require = async (sql: string, ...params: unknown[]) => {
    const row = await one(env, sql, ...params);
    if (!row) throw notFound(`${req.target_type} not found`);
    return row;
  };

  switch (req.action) {
    case 'hide':
    case 'unhide':
    case 'redact': {
      if (!CONTENT_TARGETS.has(req.target_type)) throw badRequest(`${req.action} applies to content records`);
      const status = req.action === 'hide' ? 'hidden' : req.action === 'redact' ? 'redacted' : null;
      if (req.target_type === 'contribution') {
        const row = await require('SELECT * FROM contributions WHERE id = ?', req.target_id);
        projectId = row.project_id;
        if (status) stmts.push(stmt(env, 'UPDATE contributions SET status = ? WHERE id = ?', status, row.id));
        else if (row.status === 'hidden') stmts.push(stmt(env, `UPDATE contributions SET status = 'active' WHERE id = ?`, row.id));
        else throw conflict(`Contribution is ${row.status}; only hidden records can be unhidden`);
        if (status === 'redacted') stmts.push(stmt(env, `UPDATE contribution_revisions SET title = '[redacted]', claim = '[redacted]', note_json = '{}', note_md = NULL, fields_json = '{}' WHERE contribution_id = ?`, row.id));
        if (status) stmts.push(...scrubStmts(env, 'contribution', row.id));
      } else if (req.target_type === 'receipt') {
        const row = await require('SELECT * FROM receipts WHERE id = ?', req.target_id);
        projectId = (await one(env, 'SELECT project_id FROM contributions WHERE id = ?', row.contribution_id))?.project_id ?? null;
        if (status) {
          stmts.push(stmt(env, 'UPDATE receipts SET status = ? WHERE id = ?', status, row.id), ...unresolveStmts(env, actor.id, row), ...scrubStmts(env, 'receipt', row.id));
          // The tombstone keeps the migration's CHECK satisfied for external evaluations without keeping evaluator text (W3).
          if (status === 'redacted') stmts.push(stmt(env, `UPDATE receipts SET checked_md = '[redacted]', not_checked_md = '[redacted]', method_md = '[redacted]', observations_md = '[redacted]', metrics_json = NULL, environment_md = NULL, relationships_md = '[redacted]', evaluation_json = CASE WHEN kind = 'external_evaluation' THEN '{"redacted":true}' ELSE NULL END WHERE id = ?`, row.id));
        } else if (row.status === 'hidden') stmts.push(stmt(env, `UPDATE receipts SET status = 'active' WHERE id = ?`, row.id));
        else throw conflict(`Receipt is ${row.status}; only hidden records can be unhidden`);
      } else if (req.target_type === 'post') {
        const row = await require('SELECT * FROM posts WHERE id = ?', req.target_id);
        projectId = row.project_id;
        if (status) stmts.push(stmt(env, 'UPDATE posts SET status = ? WHERE id = ?', status, row.id), ...scrubStmts(env, 'post', row.id));
        else if (row.status === 'hidden') stmts.push(stmt(env, `UPDATE posts SET status = 'visible' WHERE id = ?`, row.id));
        else throw conflict(`Post is ${row.status}; only hidden records can be unhidden`);
        if (status === 'redacted') stmts.push(stmt(env, `UPDATE posts SET body_md = '[redacted]', title = CASE WHEN title IS NULL THEN NULL ELSE '[redacted]' END WHERE id = ?`, row.id), stmt(env, `UPDATE post_revisions SET body_md = '[redacted]' WHERE post_id = ?`, row.id));
      } else if (req.target_type === 'objection') {
        const row = await require('SELECT * FROM objections WHERE id = ?', req.target_id);
        if (status) stmts.push(stmt(env, `UPDATE objections SET status = 'hidden'${status === 'redacted' ? ", body_md = '[redacted]'" : ''} WHERE id = ?`, row.id), ...scrubStmts(env, 'objection', row.id));
        else if (row.status === 'hidden') stmts.push(stmt(env, `UPDATE objections SET status = 'open' WHERE id = ?`, row.id));
        else throw conflict(`Objection is ${row.status}; only hidden records can be unhidden`);
      } else {
        const row = await require('SELECT * FROM artifacts WHERE id = ?', req.target_id);
        if (!status) throw badRequest('Artifacts cannot be unhidden; upload again');
        stmts.push(stmt(env, `UPDATE artifacts SET status = 'removed' WHERE id = ?`, row.id));
        if (row.storage === 'r2' && row.r2_key) await env.ARTIFACTS.delete(row.r2_key);
      }
      break;
    }
    case 'suspend':
    case 'unsuspend': {
      if (req.target_type !== 'contributor') throw badRequest('suspend applies to contributors');
      await require('SELECT id FROM contributors WHERE id = ?', req.target_id);
      // The guard is inside the update itself: the last active global maintainer cannot be suspended (W6).
      const nextStatus = req.action === 'suspend' ? 'suspended' : 'active';
      guarded = stmts.push(stmt(env, `UPDATE contributors SET status = ? WHERE id = ? AND (? = 'active' OR tier <> 'maintainer' OR (SELECT COUNT(*) FROM contributors WHERE tier = 'maintainer' AND status = 'active' AND id <> ?) > 0)`, nextStatus, req.target_id, nextStatus, req.target_id)) - 1;
      guardMessage = 'This is the last active global maintainer; it cannot be suspended';
      break;
    }
    case 'lock':
    case 'unlock': {
      if (req.target_type !== 'project') throw badRequest('lock applies to projects');
      const project = await loadProject(env, req.target_id);
      projectId = project.id;
      req.target_id = project.id;
      stmts.push(stmt(env, 'UPDATE projects SET safety_locked = ?, updated_at = ? WHERE id = ?', req.action === 'lock' ? 1 : 0, now, project.id));
      break;
    }
    case 'set_tier': {
      if (req.target_type !== 'contributor') throw badRequest('set_tier applies to contributors');
      await require('SELECT id FROM contributors WHERE id = ?', req.target_id);
      // Demoting the last active global maintainer is refused inside the same statement (W6).
      guarded = stmts.push(stmt(env, `UPDATE contributors SET tier = ? WHERE id = ? AND (? = 'maintainer' OR tier <> 'maintainer' OR (SELECT COUNT(*) FROM contributors WHERE tier = 'maintainer' AND status = 'active' AND id <> ?) > 0)`, req.tier, req.target_id, req.tier, req.target_id)) - 1;
      guardMessage = 'This is the last active global maintainer; promote another maintainer first';
      break;
    }
    case 'revoke_credentials': {
      if (req.target_type !== 'contributor') throw badRequest('revoke_credentials applies to contributors');
      const target = await require('SELECT id, tier, status FROM contributors WHERE id = ?', req.target_id);
      if (target.tier === 'maintainer' && target.status === 'active') {
        const others = await one<{ n: number }>(env, `SELECT COUNT(*) AS n FROM contributors c WHERE c.tier = 'maintainer' AND c.status = 'active' AND c.id <> ? AND EXISTS (SELECT 1 FROM credentials k WHERE k.contributor_id = c.id AND k.revoked_at IS NULL)`, target.id);
        if (!others?.n) throw conflict('This is the last global maintainer with a usable credential; add another maintainer first');
      }
      stmts.push(stmt(env, 'UPDATE credentials SET revoked_at = ?, revoked_by = ? WHERE contributor_id = ? AND revoked_at IS NULL', now, actor.id, req.target_id));
      break;
    }
    case 'expire_prediction': {
      if (req.target_type !== 'prediction') throw badRequest('expire_prediction applies to predictions');
      const p = await require('SELECT p.*, c.project_id FROM predictions p JOIN contributions c ON c.id = p.contribution_id WHERE p.contribution_id = ?', req.target_id);
      projectId = p.project_id;
      if (!['awaiting_resolver', 'registered'].includes(p.status)) throw conflict(`Prediction is ${p.status}`);
      if (p.deadline >= today()) throw conflict('The deadline has not passed');
      stmts.push(
        stmt(env, `UPDATE predictions SET status = 'expired_unresolved' WHERE contribution_id = ?`, p.contribution_id),
        eventStmt(env, { type: 'prediction.expired', actor_id: actor.id, project_id: projectId, entity_type: 'prediction', entity_id: p.contribution_id, payload: {} }),
      );
      break;
    }
    case 'note':
      break;
    default:
      throw badRequest('Unknown action');
  }

  stmts.push(
    stmt(env, 'INSERT INTO moderation_actions (id, action, target_type, target_id, target_revision, public_reason, private_reason, actor_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)', id, req.action, req.target_type, req.target_id, req.target_revision ?? null, req.public_reason, req.private_reason ?? null, actor.id, now),
    eventStmt(env, { type: 'moderation.action', actor_id: actor.id, project_id: projectId, entity_type: req.target_type, entity_id: req.target_id, revision: req.target_revision ?? null, payload: { action: req.action, public_reason: req.public_reason, tier: req.tier ?? null } }),
  );
  let results: D1Result[];
  try {
    results = await batch(env, stmts);
  } catch (e) {
    const m = constraintMessage(e);
    if (m) throw conflict(`The action was not applied: ${m}`);
    throw e;
  }
  if (guarded >= 0 && !results[guarded].meta.changes) {
    // The guarded update did not apply. Remove the log rows the same batch wrote and report the conflict,
    // so a refused action is never presented as if it had happened.
    await batch(env, [
      stmt(env, 'DELETE FROM moderation_actions WHERE id = ?', id),
      stmt(env, 'DELETE FROM events WHERE cursor = ?', results[results.length - 1].meta.last_row_id),
    ]);
    throw conflict(guardMessage);
  }
  return c.json(S.moderationOut((await one(env, 'SELECT * FROM moderation_actions WHERE id = ?', id))!), 201);
});
