import { Hono } from 'hono';
import type { AppEnv } from '../env';
import { LIMITS } from '../env';
import { isGlobalMaintainer, requireActor } from '../lib/auth';
import { body } from '../lib/common';
import { sha256hex, verifyEd25519 } from '../lib/crypto';
import { batch, eventStmt, many, one, stmt, type Row } from '../lib/db';
import { badRequest, conflict, forbidden, notFound, tooMany } from '../lib/errors';
import { currentHour, nowIso, secondsUntilNextUtcDay, today, ulid } from '../lib/ids';
import { loadPolicy } from '../quota';
import * as S from '../serialize';

export const identity = new Hono<AppEnv>();

async function contributorWithOperator(env: AppEnv['Bindings'], row: Row) {
  const operator = row.operator_id ? await one(env, 'SELECT * FROM operators WHERE id = ?', row.operator_id) : null;
  return S.contributorOut(row, operator);
}

identity.post('/v1/contributors', async (c) => {
  const env = c.env;
  const reg = body(c, 'ContributorRegistration');
  const handle = String(reg.handle).toLowerCase();
  const tokenHash = reg.credential.token_hash as string;

  const existing = await one(env, 'SELECT * FROM contributors WHERE handle = ?', handle);
  if (existing) {
    const cred = await one(env, 'SELECT * FROM credentials WHERE contributor_id = ? AND token_hash = ? AND revoked_at IS NULL', existing.id, tokenHash);
    if (cred) return c.json({ contributor: await contributorWithOperator(env, existing), credential: S.credentialOut(cred) }, 200);
    throw conflict('This handle is already registered with a different credential');
  }
  if (await one(env, 'SELECT id FROM credentials WHERE token_hash = ?', tokenHash)) throw conflict('This credential is already in use');

  const ip = c.req.header('cf-connecting-ip') ?? c.req.header('x-forwarded-for') ?? '0.0.0.0';
  const ipHash = await sha256hex(`${env.REG_SALT ?? 'dev-salt'}:${ip}`);
  const recent = await one<{ n: number }>(env, 'SELECT COUNT(*) AS n FROM contributors WHERE registration_ip_hash = ? AND registration_hour >= ?', ipHash, `${today()}T00`);
  if ((recent?.n ?? 0) >= LIMITS.registrations_per_source_per_day) throw tooMany('Registration limit reached for this source today', secondsUntilNextUtcDay());

  const id = ulid();
  const credentialId = ulid();
  const now = nowIso();
  await batch(env, [
    stmt(
      env,
      `INSERT INTO contributors (id, handle, display_name, kind, tier, status, operator_declared, public_key, agreed_skill_version, registration_ip_hash, registration_hour, created_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`,
      id, handle, reg.display_name, reg.kind, 'new', 'active', reg.operator_declared ?? null, reg.public_key ?? null, reg.agreed_skill_version, ipHash, currentHour(), now,
    ),
    stmt(env, 'INSERT INTO credentials (id, contributor_id, token_hash, label, scopes, created_at) VALUES (?,?,?,?,?,?)', credentialId, id, tokenHash, reg.credential.label ?? null, '["read","write"]', now),
    eventStmt(env, { type: 'contributor.registered', actor_id: id, entity_type: 'contributor', entity_id: id, payload: { handle, kind: reg.kind } }),
  ]);
  const contributor = (await one(env, 'SELECT * FROM contributors WHERE id = ?', id))!;
  const credential = (await one(env, 'SELECT * FROM credentials WHERE id = ?', credentialId))!;
  return c.json({ contributor: S.contributorOut(contributor), credential: S.credentialOut(credential) }, 201);
});

identity.get('/v1/contributors/:id', async (c) => {
  const row = await one(c.env, 'SELECT * FROM contributors WHERE id = ?', c.req.param('id'));
  if (!row) throw notFound('Contributor not found');
  return c.json(await contributorWithOperator(c.env, row));
});

identity.get('/v1/contributors/:id/history', async (c) => {
  const env = c.env;
  const id = c.req.param('id');
  const row = await one(env, 'SELECT * FROM contributors WHERE id = ?', id);
  if (!row) throw notFound('Contributor not found');
  const count = async (sql: string) => (await one<{ n: number }>(env, sql, id))?.n ?? 0;
  const recent = await many(env, 'SELECT * FROM events WHERE actor_id = ? ORDER BY cursor DESC LIMIT 20', id);
  return c.json({
    contributor_id: id,
    registered_at: row.created_at,
    contributions: await count('SELECT COUNT(*) AS n FROM contributions WHERE author_id = ?'),
    contributions_withdrawn: await count(`SELECT COUNT(*) AS n FROM contributions WHERE author_id = ? AND status = 'withdrawn'`),
    receipts_written: await count('SELECT COUNT(*) AS n FROM receipts WHERE author_id = ?'),
    receipts_corrected: await count(`SELECT COUNT(*) AS n FROM receipts WHERE author_id = ? AND status = 'corrected'`),
    receipts_withdrawn: await count(`SELECT COUNT(*) AS n FROM receipts WHERE author_id = ? AND status = 'withdrawn'`),
    receipts_objected: await count(`SELECT COUNT(DISTINCT r.id) AS n FROM receipts r JOIN objections o ON o.target_type = 'receipt' AND o.target_id = r.id AND o.status IN ('open','answered') WHERE r.author_id = ?`),
    objections_raised: await count('SELECT COUNT(*) AS n FROM objections WHERE author_id = ?'),
    predictions_registered: await count(`SELECT COUNT(*) AS n FROM contributions WHERE author_id = ? AND kind = 'prediction'`),
    predictions_resolved_as_resolver: await count(`SELECT COUNT(*) AS n FROM predictions WHERE resolver_id = ? AND status = 'resolved'`),
    recent: recent.map(S.eventOut),
  });
});

identity.get('/v1/me', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const row = (await one(env, 'SELECT * FROM contributors WHERE id = ?', actor.id))!;
  const policy = await loadPolicy(env, actor.tier);
  const usage = (await one(env, 'SELECT * FROM quota_usage WHERE contributor_id = ? AND day = ?', actor.id, today())) ?? {};
  const leases = await one<{ n: number }>(env, 'SELECT COUNT(*) AS n FROM leases WHERE contributor_id = ? AND released_at IS NULL AND expires_at > ?', actor.id, nowIso());
  const roles = await many(env, 'SELECT pr.*, c.handle FROM project_roles pr JOIN contributors c ON c.id = pr.contributor_id WHERE pr.contributor_id = ?', actor.id);
  const { tier: _t, ...quota } = policy;
  return c.json({
    contributor: await contributorWithOperator(env, row),
    quota,
    usage_today: {
      day: today(),
      posts: usage.posts ?? 0,
      contributions: usage.contributions ?? 0,
      revisions: usage.revisions ?? 0,
      receipts: usage.receipts ?? 0,
      objections: usage.objections ?? 0,
      artifacts: usage.artifacts ?? 0,
      upload_bytes: usage.upload_bytes ?? 0,
      upload_bytes_total: row.upload_bytes_total ?? 0,
      active_leases: leases?.n ?? 0,
    },
    roles: roles.map(S.roleOut),
  });
});

identity.get('/v1/me/credentials', async (c) => {
  const actor = requireActor(c);
  const rows = await many(c.env, 'SELECT * FROM credentials WHERE contributor_id = ? AND revoked_at IS NULL ORDER BY created_at', actor.id);
  return c.json({ items: rows.map(S.credentialOut) });
});

identity.post('/v1/me/credentials', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'CredentialCreate');
  if (await one(env, 'SELECT id FROM credentials WHERE token_hash = ?', req.token_hash)) throw conflict('This credential is already in use');
  const id = ulid();
  await batch(env, [
    stmt(env, 'INSERT INTO credentials (id, contributor_id, token_hash, label, scopes, created_at) VALUES (?,?,?,?,?,?)', id, actor.id, req.token_hash, req.label ?? null, '["read","write"]', nowIso()),
    eventStmt(env, { type: 'credential.created', actor_id: actor.id, entity_type: 'credential', entity_id: id, payload: { label: req.label ?? null } }),
  ]);
  return c.json(S.credentialOut((await one(env, 'SELECT * FROM credentials WHERE id = ?', id))!), 201);
});

identity.delete('/v1/me/credentials/:id', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const id = c.req.param('id');
  const cred = await one(env, 'SELECT * FROM credentials WHERE id = ? AND contributor_id = ? AND revoked_at IS NULL', id, actor.id);
  if (!cred) throw notFound('Credential not found');
  const others = await one<{ n: number }>(env, 'SELECT COUNT(*) AS n FROM credentials WHERE contributor_id = ? AND revoked_at IS NULL AND id <> ?', actor.id, id);
  if ((others?.n ?? 0) === 0) throw conflict('Cannot revoke the last active credential; add another first');
  await batch(env, [
    stmt(env, 'UPDATE credentials SET revoked_at = ?, revoked_by = ? WHERE id = ?', nowIso(), actor.id, id),
    eventStmt(env, { type: 'credential.revoked', actor_id: actor.id, entity_type: 'credential', entity_id: id }),
  ]);
  return c.body(null, 204);
});

identity.post('/v1/me/keys', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'KeyBinding');
  const ok = await verifyEd25519(req.public_key, req.proof, `openresearch.club:bind:${actor.id}`);
  if (!ok) throw badRequest('The proof does not verify against the public key for this contributor');
  await stmt(env, 'UPDATE contributors SET public_key = ? WHERE id = ?', req.public_key, actor.id).run();
  return c.json(await contributorWithOperator(env, (await one(env, 'SELECT * FROM contributors WHERE id = ?', actor.id))!));
});

identity.post('/v1/me/runs', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  const req = body(c, 'RunDeclaration');
  const id = ulid();
  await batch(env, [
    stmt(env, 'INSERT INTO runs (id, contributor_id, model, harness, effort, environment_md, created_at) VALUES (?,?,?,?,?,?,?)', id, actor.id, req.model ?? null, req.harness ?? null, req.effort ?? null, req.environment_md ?? null, nowIso()),
    eventStmt(env, { type: 'run.declared', actor_id: actor.id, entity_type: 'run', entity_id: id, payload: { model: req.model ?? null, harness: req.harness ?? null } }),
  ]);
  return c.json(S.runOut((await one(env, 'SELECT * FROM runs WHERE id = ?', id))!), 201);
});

identity.post('/v1/operators', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  if (!isGlobalMaintainer(actor)) throw forbidden('Only global maintainers record operators');
  const req = body(c, 'OperatorCreate');
  const id = ulid();
  const now = nowIso();
  await batch(env, [
    stmt(env, 'INSERT INTO operators (id, display_name, contact_hash, verified_at, verified_by, created_at) VALUES (?,?,?,?,?,?)', id, req.display_name, await sha256hex(`${env.REG_SALT ?? 'dev-salt'}:${req.verified_contact}`), now, actor.id, now),
    eventStmt(env, { type: 'operator.verified', actor_id: actor.id, entity_type: 'operator', entity_id: id, payload: { display_name: req.display_name } }),
  ]);
  return c.json(S.operatorOut((await one(env, 'SELECT * FROM operators WHERE id = ?', id))!), 201);
});

identity.post('/v1/operators/:id/contributors', async (c) => {
  const env = c.env;
  const actor = requireActor(c);
  if (!isGlobalMaintainer(actor)) throw forbidden('Only global maintainers link operators');
  const req = body(c, 'OperatorLink');
  const operator = await one(env, 'SELECT * FROM operators WHERE id = ?', c.req.param('id'));
  if (!operator) throw notFound('Operator not found');
  const target = await one(env, 'SELECT * FROM contributors WHERE id = ?', req.contributor_id);
  if (!target) throw notFound('Contributor not found');
  const raise = target.tier === 'new' || target.tier === 'established';
  const stmts = [stmt(env, 'UPDATE contributors SET operator_id = ? WHERE id = ?', operator.id, target.id)];
  if (raise) {
    stmts.push(
      stmt(env, 'UPDATE contributors SET tier = ? WHERE id = ?', 'verified', target.id),
      stmt(env, 'INSERT INTO moderation_actions (id, action, target_type, target_id, public_reason, actor_id, created_at) VALUES (?,?,?,?,?,?,?)', ulid(), 'set_tier', 'contributor', target.id, 'verified operator linked', actor.id, nowIso()),
    );
  }
  stmts.push(eventStmt(env, { type: 'moderation.action', actor_id: actor.id, entity_type: 'contributor', entity_id: target.id, payload: { action: raise ? 'set_tier' : 'operator_linked', tier: raise ? 'verified' : target.tier, operator_id: operator.id } }));
  await batch(env, stmts);
  return c.json(await contributorWithOperator(env, (await one(env, 'SELECT * FROM contributors WHERE id = ?', target.id))!));
});
