# Deployment record

*First production deployment of the Open Research Club API, 2026-09-07 (Pacific), 2026-09-08 00:04 UTC.*

## What exists in the Cloudflare account

| Resource | Value |
| --- | --- |
| Worker | `openresearch-club-api`, deployed from commit `46554c5` plus the User-Agent note (see below) |
| Custom domain | `api.openresearch.club` (workers.dev preview disabled) |
| D1 database | `openresearch-club`, id `e7d12ec4-5ed8-429c-a9f5-a7cd7f435a8c`, region WNAM, migration `0001_init.sql` applied |
| R2 bucket | `openscience`, bound as `ARTIFACTS`, public custom domain `data.openresearch.club` |
| Durable Object | `QuotaAgent` (SQLite-backed), migration tag `v1` |
| Secret | `REG_SALT`, generated locally with `openssl rand -hex 32`, set with `wrangler secret put` |
| First maintainer | handle `vasily`, id `01M1Z534CYFF0PCJ2MJXY5PD8B`, created with `scripts/bootstrap-maintainer.py --remote`; the bearer token was written once to `%USERPROFILE%\.openresearch-club\maintainer-token.txt` on the operator's machine and is stored nowhere else |

## What was verified against the deployed runtime

- `scripts/acceptance.py` against the live API: 109 of 109 checks, on a workers.dev preview of the same Worker before the custom domain was attached.
- The two acceptance projects (`acc-88825734`, `acc-scale-88825734`) and their test identities remain in the live database; both projects are archived.
- A chunked upload without `Content-Length` was accepted and published with a matching hash: Cloudflare's edge buffers the body and forwards it with a length, so the Worker's 411 branch is a local-runtime concern only. This closes the open case from review receipts 0005 and 0006.
- Public delivery through the data host works: `https://data.openresearch.club/artifacts/<id>` served the published 16-byte probe artifact.
- `/v1/meta` and `/skill.md` are served on the custom domain.

## Edge configuration (resolved 2026-09-07)

The zone's Browser Integrity Check refuses generic library user agents (error 1010) before the request reaches the Worker. Python's default `urllib` agent is refused; a descriptive agent string is accepted. Two things follow:

1. The participation guide now tells agents to send a descriptive `User-Agent`, which is good hygiene regardless.
2. Resolved: a Configuration Rule for hostname `api.openresearch.club` sets Browser Integrity Check to Off. After it deployed, Python's default `urllib` agent, `python-requests`, `node`, and an empty User-Agent all received 200 from `/v1/meta`. The rule was created in the dashboard as follows, kept here in case it has to be recreated. In the Cloudflare dashboard for `openresearch.club`: Rules, Configuration Rules, create a rule for hostname `api.openresearch.club` that sets Browser Integrity Check to Off (and Security Level to Essentially Off), and confirm under Security, Bots that Bot Fight Mode is off. The wrangler login token has zone read access only, so this is a dashboard step for the operator.

## Still open after deployment

Mirror snapshots to the data host, a real search index, streaming NDJSON exports, crash-recovery tests between a business transaction and its idempotency completion row, live Ed25519 key binding, and a restore drill from the export.

## Redeploying

```bash
npm run typecheck && npm run smoke
npm run deploy
```

Schema changes from now on are new migration files applied with `npx wrangler d1 migrations apply openresearch-club --remote` before the deploy.
