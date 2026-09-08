import type { Env } from './env';
import { batch, eventStmt, many, stmt } from './lib/db';
import { nowIso } from './lib/ids';

const ARCHIVE_AFTER_DAYS = 60;
const PROMOTE_AFTER_DAYS = 7;
const PROMOTE_MIN_RECEIPTS = 3;

/**
 * Housekeeping that runs on a timer so the club needs nobody online:
 *  - active projects with no event for 60 days are archived (a maintainer can revive one);
 *  - `new` contributors registered for 7 days who wrote at least 3 standing receipts on others'
 *    work (distinct contributions; a contributor never receipts its own) are promoted to `established`. Every action is written to the public event log with no
 *    actor, so it is visibly automatic.
 */
export async function runHousekeeping(env: Env): Promise<{ archived: number; promoted: number }> {
  const now = nowIso();
  const archiveCutoff = nowIso(new Date(Date.now() - ARCHIVE_AFTER_DAYS * 86400_000));
  const promoteCutoff = nowIso(new Date(Date.now() - PROMOTE_AFTER_DAYS * 86400_000));

  const stale = await many(
    env,
    `SELECT id, slug FROM projects p WHERE p.status = 'active' AND p.created_at < ?
       AND NOT EXISTS (SELECT 1 FROM events e WHERE e.project_id = p.id AND e.occurred_at > ?)`,
    archiveCutoff,
    archiveCutoff,
  );
  const stmts: D1PreparedStatement[] = [];
  for (const p of stale) {
    stmts.push(
      stmt(env, `UPDATE projects SET status = 'archived', updated_at = ? WHERE id = ? AND status = 'active'`, now, p.id),
      eventStmt(env, { type: 'project.updated', actor_id: null, project_id: p.id, entity_type: 'project', entity_id: p.id, payload: { automatic: true, previous: { status: 'active' }, changed: ['status'], reason: `no activity for ${ARCHIVE_AFTER_DAYS} days` } }),
    );
  }

  const ready = await many(
    env,
    `SELECT c.id, c.handle FROM contributors c WHERE c.tier = 'new' AND c.status = 'active' AND c.created_at < ?
       AND (SELECT COUNT(DISTINCT r.contribution_id) FROM receipts r WHERE r.author_id = c.id AND r.status = 'active') >= ?`,
    promoteCutoff,
    PROMOTE_MIN_RECEIPTS,
  );
  for (const r of ready) {
    stmts.push(
      stmt(env, `UPDATE contributors SET tier = 'established' WHERE id = ? AND tier = 'new'`, r.id),
      eventStmt(env, { type: 'moderation.action', actor_id: null, entity_type: 'contributor', entity_id: r.id, payload: { action: 'set_tier', tier: 'established', automatic: true, public_reason: `${PROMOTE_MIN_RECEIPTS} standing receipts and ${PROMOTE_AFTER_DAYS} days since registration` } }),
    );
  }
  if (stmts.length) await batch(env, stmts);
  return { archived: stale.length, promoted: ready.length };
}
