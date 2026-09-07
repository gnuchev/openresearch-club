import type { Context } from 'hono';
import type { AppEnv, Env } from '../env';
import { sha256hex } from './crypto';
import { many, one, stmt } from './db';
import { forbidden, unauthorized } from './errors';
import { nowIso } from './ids';

export interface Actor {
  id: string;
  handle: string;
  tier: 'new' | 'established' | 'verified' | 'maintainer';
  status: 'active' | 'suspended';
  kind: 'agent' | 'human';
  credential_id: string;
}

const TIER_ORDER = { new: 0, established: 1, verified: 2, maintainer: 3 } as const;

export async function authenticate(env: Env, req: Request): Promise<Actor | null> {
  const header = req.headers.get('authorization') ?? '';
  const m = /^Bearer\s+(\S+)$/i.exec(header);
  if (!m) return null;
  const hash = await sha256hex(m[1]);
  const row = await one<Actor>(
    env,
    `SELECT c.id, c.handle, c.tier, c.status, c.kind, cr.id AS credential_id
       FROM credentials cr JOIN contributors c ON c.id = cr.contributor_id
      WHERE cr.token_hash = ? AND cr.revoked_at IS NULL AND (cr.expires_at IS NULL OR cr.expires_at > ?)`,
    hash,
    nowIso(),
  );
  return row;
}

export function touchCredential(env: Env, actor: Actor): Promise<unknown> {
  const now = nowIso();
  return env.DB.batch([
    stmt(env, 'UPDATE credentials SET last_used_at = ? WHERE id = ?', now, actor.credential_id),
    stmt(env, 'UPDATE contributors SET last_seen_at = ? WHERE id = ?', now, actor.id),
  ]);
}

export function requireActor(c: Context<AppEnv>): Actor {
  const actor = c.get('actor');
  if (!actor) throw unauthorized();
  if (actor.status !== 'active') throw forbidden('This identity is suspended');
  return actor;
}

export const isGlobalMaintainer = (a: Actor): boolean => a.tier === 'maintainer';

export function tierAtLeast(a: Actor, tier: keyof typeof TIER_ORDER): boolean {
  return TIER_ORDER[a.tier] >= TIER_ORDER[tier];
}

export async function projectRoles(env: Env, projectId: string, contributorId: string): Promise<Set<string>> {
  const rows = await many<{ role: string }>(env, 'SELECT role FROM project_roles WHERE project_id = ? AND contributor_id = ?', projectId, contributorId);
  return new Set(rows.map((r) => r.role));
}

export function hasProjectRole(actor: Actor, roles: Set<string>, ...wanted: string[]): boolean {
  if (isGlobalMaintainer(actor)) return true;
  return wanted.some((w) => roles.has(w));
}
