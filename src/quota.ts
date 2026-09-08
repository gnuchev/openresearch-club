import type { Env } from './env';
import type { Actor } from './lib/auth';
import { one, stmt } from './lib/db';
import { tooMany } from './lib/errors';
import { currentHour, nowIso, secondsUntilNextUtcDay, today } from './lib/ids';

/**
 * One Durable Object per contributor is the atomic authority for quota reservations. A Durable
 * Object processes one request at a time, so reserve/release cannot race. Counters are keyed by
 * UTC day (or hour for the request rate) and expire through the alarm below.
 */
export class QuotaAgent {
  constructor(private state: DurableObjectState, _env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const body = (await request.json()) as { op: 'reserve' | 'release' | 'read'; key: string; amount?: number; limit?: number };
    const amount = body.amount ?? 1;
    const current = (await this.state.storage.get<number>(body.key)) ?? 0;
    if (body.op === 'read') return Response.json({ ok: true, count: current });
    if (body.op === 'release') {
      const next = Math.max(0, current - amount);
      await this.state.storage.put(body.key, next);
      return Response.json({ ok: true, count: next });
    }
    if (body.limit !== undefined && current + amount > body.limit) {
      return Response.json({ ok: false, count: current }, { status: 429 });
    }
    await this.state.storage.put(body.key, current + amount);
    if ((await this.state.storage.getAlarm()) === null) await this.state.storage.setAlarm(Date.now() + 36 * 3600_000);
    return Response.json({ ok: true, count: current + amount });
  }

  /** Drop counters older than two days so storage stays bounded. */
  async alarm(): Promise<void> {
    const cutoff = new Date(Date.now() - 2 * 86400_000).toISOString().slice(0, 10);
    const all = await this.state.storage.list<number>();
    const stale = [...all.keys()].filter((k) => k.slice(0, 10) < cutoff);
    if (stale.length) await this.state.storage.delete(stale);
  }
}

export interface QuotaPolicy {
  tier: string;
  posts_per_day: number;
  contributions_per_day: number;
  revisions_per_day: number;
  receipts_per_day: number;
  objections_per_day: number;
  artifacts_per_day: number;
  upload_bytes_per_day: number;
  upload_bytes_total: number;
  active_leases: number;
  requests_per_hour: number;
  projects_per_day: number;
}

export type QuotaKind = 'posts' | 'contributions' | 'revisions' | 'receipts' | 'objections' | 'artifacts' | 'upload_bytes' | 'projects';

const policyCache = new Map<string, QuotaPolicy>();

export async function loadPolicy(env: Env, tier: string): Promise<QuotaPolicy> {
  const cached = policyCache.get(tier);
  if (cached) return cached;
  const row = await one<QuotaPolicy>(env, 'SELECT * FROM quota_policies WHERE tier = ?', tier);
  if (!row) throw new Error(`no quota policy for tier ${tier}`);
  policyCache.set(tier, row);
  return row;
}

export async function loadAllPolicies(env: Env): Promise<Record<string, QuotaPolicy>> {
  const rows = (await env.DB.prepare('SELECT * FROM quota_policies').all<QuotaPolicy>()).results;
  const out: Record<string, QuotaPolicy> = {};
  for (const r of rows) {
    const { tier, ...rest } = r;
    out[tier] = rest as QuotaPolicy;
    policyCache.set(tier, r);
  }
  return out;
}

async function call(env: Env, contributorId: string, payload: Record<string, unknown>): Promise<{ ok: boolean; count: number }> {
  const id = env.QUOTA.idFromName(contributorId);
  const res = await env.QUOTA.get(id).fetch('https://quota/', { method: 'POST', body: JSON.stringify(payload) });
  return (await res.json()) as { ok: boolean; count: number };
}

/** Reserve `amount` of a per-day quota. Returns a release function for use when the write fails. */
export async function reserveQuota(env: Env, actor: Actor, kind: QuotaKind, amount = 1): Promise<() => Promise<void>> {
  const policy = await loadPolicy(env, actor.tier);
  const limit = policy[`${kind}_per_day` as keyof QuotaPolicy] as number;
  const key = `${today()}:${kind}`;
  const r = await call(env, actor.id, { op: 'reserve', key, amount, limit });
  if (!r.ok) throw tooMany(`Daily quota for ${kind} reached for tier ${actor.tier}`, secondsUntilNextUtcDay());
  return async () => {
    await call(env, actor.id, { op: 'release', key, amount });
  };
}

/** Per-hour request rate for authenticated callers. */
export async function reserveRequest(env: Env, actor: Actor): Promise<void> {
  const policy = await loadPolicy(env, actor.tier);
  const r = await call(env, actor.id, { op: 'reserve', key: `${currentHour()}:requests`, amount: 1, limit: policy.requests_per_hour });
  if (!r.ok) throw tooMany(`Hourly request limit reached for tier ${actor.tier}`, 60);
}

/** Statement that records the day's usage in D1 (the audit trail behind the Durable Object). */
export function usageStmt(env: Env, contributorId: string, kind: QuotaKind, amount = 1): D1PreparedStatement {
  return stmt(
    env,
    `INSERT INTO quota_usage (contributor_id, day, ${kind}, updated_at) VALUES (?,?,?,?)
       ON CONFLICT(contributor_id, day) DO UPDATE SET ${kind} = ${kind} + excluded.${kind}, updated_at = excluded.updated_at`,
    contributorId,
    today(),
    amount,
    nowIso(),
  );
}
