# Response to review receipt 0004

**Author:** Fable (Claude), using Claude Code.
**Date:** 2026-09-07.
**Answers:** `docs/reviews/0004-astra-runtime-review.md`, written against commit `a1636aa`.
**Changes:** the commit that contains this file. Every finding below names what changed and how it is now checked.

All seven findings were real, and all seven are closed. The acceptance flow (`scripts/acceptance.py`) now carries a regression for each one and runs 95 checks; the original 62 are unchanged.

## Finding by finding

**W1 — a status filter exposed hidden receipts.** Public list filters are now intersected with the public statuses. `GET /v1/contributions/{id}/receipts?status=hidden` and `GET /v1/objections?status=hidden` return empty lists, and the unfiltered lists select only active, corrected and withdrawn receipts. Invariant 21. Regression: hide a receipt, then confirm both filters return nothing and the direct GET returns 410.

**W2 — redacted text stayed in events and exports.** Hiding or redacting a contribution, receipt, post or objection now also replaces that record's event payloads with a tombstone and deletes any cached idempotent response that carried the record (`scrubStmts` in `src/lib/common.ts`). Invariant 16. Regression: a contribution with a unique marker is redacted, then the marker is shown absent from the project event feed, the export and search.

**W3 — external-evaluation receipts could not be redacted.** The redaction tombstone keeps a `{"redacted": true}` evaluation for external evaluations, so the migration's CHECK holds without keeping evaluator text. Database constraint failures are now reported as 409 conflicts, never as a success and never as a 500. Regression: an external evaluation with a score is redacted and then returns 410.

**W4 — locked projects accepted indirect writes.** Every project-scoped write now resolves its effective project first and calls one rule, `requireProjectWritable`: replies and objection responses from their parent, receipts, corrections, withdrawals and relations from their contribution, leases from their task, resolver nomination, agreement and resolution from their prediction, objections from their target. The maintainer exception is inside the rule. Invariant 22. Regression: with the project locked, a reply, a receipt and a lease from non-maintainers are refused with 403 and a maintainer's reply is accepted.

**W5 — a populated export exceeded D1's parameter limit.** The export is rewritten with project-scoped joins, one query per record type, assembled in memory; referenced contributors and runs are collected from the fetched rows and loaded in chunks of at most 80 ids. All other id-list queries (facets, receipts, relations, current revisions, task leases and claims) now run through the same chunking helper, so context packets scale the same way. The first attempt used a fifteen-branch `UNION`, which D1 refuses as "too many terms in compound SELECT"; the chunked approach avoids compound selects entirely. Invariant 23. Regression: a project with 58 contributions exports and produces a context packet.

**W6 — the sole global maintainer could demote itself.** The guard is now inside the update statement: demotion and suspension apply only when another active global maintainer exists, and revoking the credentials of the last maintainer with a usable credential is refused. If the guarded update changes no row, the moderation log and event written by the same batch are removed and the request returns 409, so a refused action is never presented as done. Invariant 19. Regression: the sole maintainer's self-demotion and self-suspension both return 409 and its tier and status are unchanged.

**W7 — bodies were buffered before size checks.** A write now needs a token before any body is read (registration excepted). Bodies are read through a bounded reader that checks the declared length first and then the actual bytes as they stream: 1 MiB for JSON, 25 MiB for uploads, and uploads without `Content-Length` are refused with 411. Invariant 23. Regression: an unauthenticated write returns 401 and a 2 MiB JSON body returns 413.

## Verification

- `npm run typecheck`: clean.
- `npm run smoke`: 27 of 27 validator cases agree.
- `scripts/acceptance.py` against a fresh local D1 through `wrangler dev`: 95 of 95 checks, no unhandled errors in the server log.

## Still open, as the receipt said

Crash recovery between the business transaction and the idempotency completion row, live Ed25519 key binding, public R2 delivery, snapshot production, restore, and deployed behaviour remain unverified. The export is still assembled in memory; streaming NDJSON is a later change.

## Requested

A recheck of the seven changes against this commit. After that the deploy steps in the README can run, on Vasily's confirmation.
