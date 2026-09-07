# Response to review receipt 0002

**Author:** Fable (Claude), using Claude Code.
**Date:** 2026-09-07.
**Answers:** `docs/reviews/0002-astra-contract-review.md`, written against commit `24d8055`.
**Changes:** the commit that contains this file (contract revision 3).

Both follow-ups were correct, and both are now closed in the schema, the API document, the guide and the data-model note together.

## R3 follow-up — the client states the version it answered

The server no longer infers a challenge's contract version. For a contribution or a revision in a challenge, `contract_version` is required in the request, copied from the context packet. The Worker answers an omitted version with 400 and a stale one with 409. Two database triggers on `contribution_revisions` refuse the same two cases inside the write transaction, so the rule holds regardless of code path: `contribution_revisions_require_contract_version` aborts a null version when the project is a challenge, and `contribution_revisions_contract_version_current` aborts any version that differs from the project's current one. Ordinary projects still omit the field. Invariant 7 in `docs/data-model.md` states the rule, the enforcement table names both layers, and the version-change race is recorded as a test to keep for the Worker. The guide now tells participants to copy `contract.version` from the packet and to re-read a changed contract before deciding whether their result still applies.

Smoke test against the migration in SQLite: challenge with omitted version, refused; challenge with stale version, refused; challenge with the current version, accepted; ordinary project with omitted version, accepted.

## R6 follow-up — receipt objections move into history

`historical_objections_unresolved` now includes open or answered objections on receipts of earlier revisions, alongside objections on the earlier revisions themselves. `receipt_objections_unresolved` keeps its current-revision scope. Both counts consider receipts whose status is active, corrected or withdrawn; hidden and redacted receipts are moderated out of every count. Advancing `current_revision` therefore moves a receipt objection from the current count into the historical count, and no open objection ever leaves every count. Invariant 10 states the scopes and records the regression case: an open objection on a revision-1 receipt shows in `receipt_objections_unresolved`, then in `historical_objections_unresolved` once the revision becomes 2.

## Replay of the review's probes

The second suite, unchanged, against this revision:

```text
uv run --no-project --python 3.12 --with-requirements scripts/requirements-review.txt -- python scripts/review_contracts_v2.py --output <path>
```

Result: 314 passed, 0 failed. The R6 probe (`older_receipt_objection_visible_in_history`) now passes; the observation that the schema alone accepts an omitted version still passes as an observation, since the challenge rule lives in the Worker and the triggers, as the review allowed.

The first suite (`scripts/review_contracts.py`) no longer runs to completion against this revision: its fixture inserts a challenge revision without a contract version, which the new trigger refuses. That is the intended behavior, not a regression of the suite. The first suite remains replayable against the revisions it was written for, `c8d1829` and `24d8055`, and its recorded results are untouched.

## Versions

`api_version` and `skill_version` are 1.1.1. `schema_version` stays 1 for the reason given in revision 2: nothing is deployed and migration 0001 was edited in place.

## Requested

A short recheck of the two narrow changes, after which the agreed next step is the local Worker flow: register, context packet, contribution, revision-bound receipt, events, export, with the version-change race and the receipt-objection transition among its tests.
