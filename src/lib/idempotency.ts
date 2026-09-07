import type { MiddlewareHandler } from 'hono';
import type { AppEnv } from '../env';
import { LIMITS } from '../env';
import { sha256hex } from './crypto';
import { one, stmt } from './db';
import { badRequest, conflict, HttpError, tooLarge, unauthorized, unprocessable } from './errors';
import { isoAfterHours, nowIso } from './ids';

interface KeyRow {
  scope: string;
  key: string;
  method: string;
  target: string;
  body_sha256: string;
  state: 'in_flight' | 'done';
  response_status: number | null;
  response_body: string | null;
  expires_at: string;
}

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH']);

/**
 * Read a request body without ever holding more than `limit` bytes. The declared Content-Length is
 * checked first, then the actual bytes as they stream; the read is cancelled the moment the limit
 * is passed. Workers have a fixed memory budget, so nothing may buffer a body before this check.
 */
export async function readBounded(req: Request, limit: number): Promise<ArrayBuffer> {
  const declared = req.headers.get('content-length');
  if (declared !== null && Number(declared) > limit) throw tooLarge(`Body exceeds the ${limit}-byte limit`);
  const reader = req.body?.getReader();
  if (!reader) return new ArrayBuffer(0);
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel().catch(() => undefined);
      throw tooLarge(`Body exceeds the ${limit}-byte limit`);
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out.buffer;
}

/**
 * Every write carries an Idempotency-Key scoped to the caller (or to the handle for registration)
 * and bound to a fingerprint of method, canonical path and body hash. The caller is identified
 * before any body is read, bodies are read through readBounded, and the in-flight row is written
 * before the handler runs, so two concurrent identical requests cannot both execute.
 */
export const idempotency = (): MiddlewareHandler<AppEnv> => async (c, next) => {
  const method = c.req.method.toUpperCase();
  if (!WRITE_METHODS.has(method)) return next();

  const key = c.req.header('idempotency-key');
  if (!key || key.length > 128) throw badRequest('Idempotency-Key header is required on every write (up to 128 characters)');

  const path = c.req.path;
  const actor = c.get('actor');
  const isRegistration = path === '/v1/contributors';
  if (!actor && !isRegistration) throw unauthorized();

  const binary = (c.req.header('content-type') ?? '').startsWith('application/octet-stream');
  let bodyHash: string;
  if (binary) {
    if (isRegistration) throw badRequest('Registration takes a JSON body');
    if (c.req.header('content-length') === undefined) throw new HttpError(411, 'Length Required', 'Uploads must declare Content-Length');
    const bytes = await readBounded(c.req.raw, LIMITS.artifact_max_bytes);
    c.set('rawBytes', bytes);
    bodyHash = await sha256hex(bytes);
  } else {
    const raw = new TextDecoder().decode(await readBounded(c.req.raw, LIMITS.json_body_max_bytes));
    c.set('rawBody', raw);
    bodyHash = await sha256hex(raw);
  }

  let scope: string;
  if (actor) scope = actor.id;
  else {
    let handle = '';
    try {
      handle = String(JSON.parse(c.get('rawBody') ?? '{}')?.handle ?? '').toLowerCase();
    } catch {
      /* validated by the handler */
    }
    scope = `registration:${handle}`;
  }

  const env = c.env;
  const now = nowIso();
  const existing = await one<KeyRow>(env, 'SELECT * FROM idempotency_keys WHERE scope = ? AND key = ?', scope, key);
  if (existing && existing.expires_at > now) {
    if (existing.method !== method || existing.target !== path || existing.body_sha256 !== bodyHash) {
      throw unprocessable('This Idempotency-Key was already used for a different request');
    }
    if (existing.state === 'in_flight') throw conflict('A request with this Idempotency-Key is still in flight', { 'Retry-After': '1' });
    const status = existing.response_status ?? 200;
    return new Response(existing.response_body ?? '', {
      status,
      headers: {
        'content-type': status >= 400 ? 'application/problem+json' : 'application/json',
        'idempotent-replayed': 'true',
      },
    });
  }
  if (existing) await stmt(env, 'DELETE FROM idempotency_keys WHERE scope = ? AND key = ?', scope, key).run();

  try {
    await stmt(
      env,
      'INSERT INTO idempotency_keys (scope, key, method, target, body_sha256, state, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)',
      scope,
      key,
      method,
      path,
      bodyHash,
      'in_flight',
      now,
      isoAfterHours(LIMITS.idempotency_hours),
    ).run();
  } catch {
    throw conflict('A request with this Idempotency-Key is still in flight', { 'Retry-After': '1' });
  }

  await next();
  const res = c.res;
  if (res.status >= 500) {
    await stmt(env, 'DELETE FROM idempotency_keys WHERE scope = ? AND key = ?', scope, key).run();
    return;
  }
  const text = await res.clone().text();
  await stmt(env, 'UPDATE idempotency_keys SET state = ?, response_status = ?, response_body = ? WHERE scope = ? AND key = ?', 'done', res.status, text, scope, key).run();
};
