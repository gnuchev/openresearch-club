import type { Env } from '../env';
import { nowIso } from './ids';

export type Row = Record<string, any>;

export function stmt(env: Env, sql: string, ...params: unknown[]): D1PreparedStatement {
  return env.DB.prepare(sql).bind(...params);
}

export async function one<T = Row>(env: Env, sql: string, ...params: unknown[]): Promise<T | null> {
  const r = await stmt(env, sql, ...params).first<T>();
  return (r as T | null) ?? null;
}

export async function many<T = Row>(env: Env, sql: string, ...params: unknown[]): Promise<T[]> {
  const r = await stmt(env, sql, ...params).all<T>();
  return r.results as T[];
}

export async function batch(env: Env, stmts: D1PreparedStatement[]): Promise<D1Result[]> {
  if (stmts.length === 0) return [];
  return env.DB.batch(stmts);
}

export interface EventInput {
  type: string;
  actor_id?: string | null;
  project_id?: string | null;
  entity_type: string;
  entity_id: string;
  revision?: number | null;
  payload?: Record<string, unknown>;
}

export function eventStmt(env: Env, e: EventInput): D1PreparedStatement {
  return stmt(
    env,
    'INSERT INTO events (occurred_at, type, actor_id, project_id, entity_type, entity_id, revision, payload_json) VALUES (?,?,?,?,?,?,?,?)',
    nowIso(),
    e.type,
    e.actor_id ?? null,
    e.project_id ?? null,
    e.entity_type,
    e.entity_id,
    e.revision ?? null,
    JSON.stringify(e.payload ?? {}),
  );
}

export function parseJson<T = any>(text: string | null | undefined, fallback: T): T {
  if (text === null || text === undefined || text === '') return fallback;
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

export function placeholders(n: number): string {
  return Array.from({ length: n }, () => '?').join(',');
}

export async function maxEventCursor(env: Env): Promise<number> {
  const r = await one<{ c: number | null }>(env, 'SELECT MAX(cursor) AS c FROM events');
  return r?.c ?? 0;
}

/** Map a SQLite constraint failure raised by the migration's triggers or CHECKs to a message. */
export function constraintMessage(err: unknown): string | null {
  const text = err instanceof Error ? err.message : String(err);
  const m = /(contract_version is [^:]+|CHECK constraint failed[^:]*|UNIQUE constraint failed[^:]*|FOREIGN KEY constraint failed)/.exec(text);
  return m ? m[1] : null;
}
