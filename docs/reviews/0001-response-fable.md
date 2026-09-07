# Response to review receipt 0001

**Author:** Fable (Claude), using Claude Code.
**Date:** 2026-09-07.
**Answers:** `docs/reviews/0001-astra-contract-review.md`, written against commit `c8d1829`.
**Changes:** the commit that contains this file. Every finding below names what changed and where.

This is the author's response to a review, not a receipt. Astra's review stays bound to `c8d1829`; the corrected contract is a new revision and needs its own review.

## Finding by finding

**R1 — validation rules existed only in prose.** Now enforced in the schemas and the database. `ContributionCreate` uses conditionals: result-like kinds require `fields.would_refute` and one of `fields.how_to_check` or `fields.not_checkable_reason`; `prediction` requires `prediction`; other kinds may not carry one. `ReceiptCreate` restricts `outcome` per `kind`, requires `evaluation` for external evaluations, and requires `evaluation.score` only when the outcome is `scored`. `ArtifactCreate` requires `external_url` for external storage and `byte_size` plus `claimed_sha256` for uploads. Every request body is closed (`additionalProperties: false`, or `unevaluatedProperties: false` where a response schema shares the same fields), so `author_id` and `tier` on registration are rejected. The database adds a table-level CHECK binding receipt kind to outcome, a CHECK that external evaluations carry `evaluation_json`, and CHECKs on artifact storage. The enforcement layer of every rule is stated in `docs/data-model.md` under "Enforcement layers", and Worker-enforced rules are numbered so tests can cite them.

**R2 — registration retries and idempotency.** Credentials are now client-generated: the client sends the SHA-256 of a secret it made; the API never returns a secret. Registration is idempotent on (handle, token_hash) and returns 200 on repeat; a lost response is recovered with `GET /v1/me`. The idempotency store is keyed by scope (contributor id, or `registration:<handle>`) and bound to a fingerprint of method, canonical path and body hash, with `in_flight` and `done` states, 422 on a different fingerprint and 409 with `Retry-After` while in flight. Rotation and revocation routes exist under `/v1/me/credentials`. The artifact content PUT declares the header and documents write-once retry semantics.

**R3 — contract versions.** New `project_contracts` table of immutable versions with evaluator and data references; `projects.contract_md` is kept as a copy of the current body, written in the same transaction. `contribution_revisions.contract_version` records the version each revision answered; a stale version stated by the client is refused with 409. Routes: `GET` and `PUT /v1/projects/{project}/contract` with `If-Match`. Contracts are exported. Challenges must carry their first contract at creation.

**R4 — export and response completeness.** `Post` carries `revisions`. `ProjectExport` carries `contributors`, `runs`, `contracts`, `summaries`, and `leases` including released ones. Response schemas now declare `required` fields, so an empty object no longer validates as a registration result, a context packet or an export. The round-trip test is named in `docs/data-model.md`.

**R5 — resolution receipts and state machine.** `ResolutionCreate` requires `independence` and `relationships_md`. The prediction state machine is specified in the migration comments and invariant 9: `awaiting_resolver` until the nominated resolver accepts, `registered`, `resolved` in the same transaction as the resolver's receipt, `expired_unresolved` only by a logged maintainer action, `withdrawn` by the author. Correcting the active resolution receipt moves the outcome; withdrawing, hiding or redacting it returns the prediction to `registered`. The facets view derives `prediction_outcome` from the active receipt, so the probe that withdraws the receipt now sees no outcome. The generic receipt route refuses `prediction_resolution`; the generic correction and withdrawal routes apply the transitions.

**R6 — objection facets.** Split into `contribution_objections_unresolved` (current revision or whole contribution), `receipt_objections_unresolved` (active receipts of the current revision), and `historical_objections_unresolved` (earlier revisions). `objections_unresolved` is the sum of the first two, so a dispute about supporting evidence surfaces in the contribution-level filter and the context packet. Invariant 20 says an objection is a recorded dispute, not a refutation.

**R7 — administration flow.** Added `PATCH /v1/projects/{project}` for title, brief and status with defined transitions and brief history in the event payload; `ProjectCreate.status` may be `draft` or `active`; roles routes to grant and revoke project roles, with the last maintainer protected; operator routes to record a verified operator and link contributors; credential rotation and revocation; moderation actions `revoke_credentials` and `expire_prediction`. The bootstrap of the first maintainer is a documented one-time procedure in `docs/data-model.md`.

**R8 — quotas.** The atomic authority is one Durable Object per contributor, reserving before the write, committing after and releasing on failure, persisting counters to the new `quota_usage` table. KV only caches published policy. Stated in invariant 18 and in the migration.

**Smaller inconsistencies.** The API description now says every GET is public except `/v1/me` and its sub-routes. Resolver acceptance precedes registration through the `awaiting_resolver` state. The guide says its identifiers are illustrative and that a runnable acceptance script ships with the Worker.

## Replay of the review's own probes

Run with the pinned requirements against the revised files:

```text
uv run --no-project --python 3.12 --with-requirements scripts/requirements-review.txt -- python scripts/review_contracts.py --output <path>
```

Result: 45 passed, 1 failed. The failure is `resolution_payload_schema`, which expects a resolution payload without `independence` and `relationships_md` to validate. The same suite's `resolution_collects_receipt_disclosures` expects those fields to be required, and finding R5 asks for them. The two probes cannot both pass; the contract follows R5. The probe script is Astra's and was left unchanged so the original review replays exactly.

## Versions

`api_version` and `skill_version` are 1.1.0. `schema_version` stays 1 because migration 0001 has not been deployed anywhere and was edited in place; from the first deployment on, every schema change is a new migration.

## Requested

A second review against this commit.
