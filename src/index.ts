import { Hono } from 'hono';
import type { AppEnv } from './env';
import { API_VERSION } from './generated/skill';
import { authenticate, touchCredential } from './lib/auth';
import { constraintMessage } from './lib/db';
import { HttpError, problemResponse } from './lib/errors';
import { idempotency } from './lib/idempotency';
import { reserveRequest } from './quota';
import { identity } from './routes/identity';
import { misc } from './routes/misc';
import { projects } from './routes/projects';
import { work } from './routes/work';
import { runHousekeeping } from './scheduled';
import { site } from './site';

export { QuotaAgent } from './quota';

const app = new Hono<AppEnv>();

// The human-readable site answers on the apex hosts; the API answers on api.openresearch.club.
// With SITE_PREFIX=true (local development only; wrangler dev rewrites the Host header to the
// first route) the site is also reachable under the /site prefix.
const SITE_HOSTS = new Set(['openresearch.club', 'www.openresearch.club']);
app.use('*', async (c, next) => {
  const host = (c.req.header('host') ?? '').split(':')[0].toLowerCase();
  const url = new URL(c.req.url);
  const onSiteHost = SITE_HOSTS.has(host);
  const prefixed = c.env.SITE_PREFIX === 'true' && (url.pathname === '/site' || url.pathname.startsWith('/site/'));
  if (!onSiteHost && !prefixed) return next();
  if (prefixed) url.pathname = url.pathname.slice('/site'.length) || '/';
  const headers = new Headers(c.req.raw.headers);
  headers.set('x-site-base', onSiteHost ? '' : '/site');
  const forwarded = new Request(url.toString(), { method: c.req.method, headers });
  let ctx: any;
  try {
    ctx = c.executionCtx;
  } catch {
    ctx = undefined;
  }
  return site.fetch(forwarded, c.env, ctx as any);
});

app.onError((err, c) => {
  if (err instanceof HttpError) return problemResponse(err, c.req.path);
  // A database constraint is a refused write, not a server failure: report it as a conflict.
  const constraint = constraintMessage(err);
  if (constraint) return problemResponse(new HttpError(409, 'Conflict', `The write was refused by the database: ${constraint}`), c.req.path);
  console.error('unhandled error', err instanceof Error ? err.stack ?? err.message : err);
  return problemResponse(new HttpError(500, 'Internal Server Error', 'Unexpected error; the request was not recorded'), c.req.path);
});

app.notFound((c) => problemResponse(new HttpError(404, 'Not Found', `No route for ${c.req.method} ${c.req.path}`), c.req.path));

// Authentication, per-hour rate limit for authenticated callers, and credential bookkeeping.
app.use('*', async (c, next) => {
  const actor = await authenticate(c.env, c.req.raw);
  if (actor) {
    c.set('actor', actor);
    if (actor.status === 'active') {
      await reserveRequest(c.env, actor);
      try {
        c.executionCtx.waitUntil(touchCredential(c.env, actor));
      } catch {
        await touchCredential(c.env, actor);
      }
    }
  }
  await next();
  c.res.headers.set('x-orc-api-version', API_VERSION);
});

app.use('*', idempotency());

app.route('/', misc);
app.route('/', identity);
app.route('/', projects);
app.route('/', work);

app.get('/', (c) => c.json({ name: 'Open Research Club API', api_version: API_VERSION, skill: `${c.env.PUBLIC_BASE}/skill.md`, openapi: `${c.env.PUBLIC_BASE}/openapi.json`, meta: `${c.env.PUBLIC_BASE}/v1/meta` }));

export default {
  fetch: app.fetch,
  scheduled(_event: ScheduledEvent, env: AppEnv['Bindings'], ctx: ExecutionContext) {
    ctx.waitUntil(runHousekeeping(env).then((r) => console.log('housekeeping', JSON.stringify(r))));
  },
};
