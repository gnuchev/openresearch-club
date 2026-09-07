# Review receipt 0004: first Worker runtime

**Reviewer:** Astra, using Codex.  
**Date:** September 7, 2026.  
**Target:** `a1636aa28e8c3a90e42cb899e382837315eb288e`.  
**Source tree:** `8d3c46a3a0b96694de5e29c8ef5f4c8b4392b61b` (`src/`).  
**Kind / outcome:** `review` / `serious_concerns`.  
**Disposition:** The demonstrated flow works locally. Fix the runtime findings below before public deployment.

This receipt examines implementation behavior, following the earlier contract reviews. It does not revise or withdraw their conclusions about the contracts they examined. All reviewed application sources remain unchanged.

## What reproduced

- TypeScript check passed after generating the schemas from the committed OpenAPI document.
- All **27 runtime-validator smoke cases** passed.
- The unchanged `scripts/acceptance.py` passed **62/62 checks** against a freshly initialized local D1 through the running Worker.
- The additional HTTP suite recorded **5 passing checks and 10 failing expectations**. Those expectations include several observations of the same bug; they are grouped into six reproduced findings below, followed by one source-review finding.

The tests used a separate Wrangler configuration, local persistence directory, and loopback port 8791. D1, Durable Objects, and R2 were local bindings. A synthetic maintainer was bootstrapped into that disposable database. Bearer secrets were generated in memory and passed to the acceptance process through its environment; no real account credentials or research artifacts were used.

[Final HTTP evidence, including the original acceptance output](R:/Coding/agent-science-challenge/docs/reviews/0004-runtime-probes.json)

## Findings

### W1 — P1: A public status filter bypasses hidden-receipt protection

After a maintainer hides a receipt, `GET /v1/receipts/{id}` correctly returns 410. However, an unauthenticated request to `GET /v1/contributions/{id}/receipts?status=hidden` returns 200 with the complete hidden receipt, including its text. The query replaces the public-visibility exclusion when a status parameter is supplied.

Evidence: [status-filter branch](R:/Coding/agent-science-challenge/src/routes/work.ts:448). Probe: `hidden_receipt_not_exposed_by_status_filter`.

Always intersect public filters with the allowed visibility set; expose moderated content only through a separately authorized interface if needed. Apply the same review to the objection-list status filter. A user-controlled query must not override moderation visibility.

### W2 — P1: Successful redaction leaves the original claim in public events and exports

I created a contribution whose title/claim contained a unique synthetic marker, then successfully redacted it. The marker remained readable without authentication in the project's event feed and its export. Creation copies the title and claim into `events.payload_json`; redaction only clears the revision rows, and the event serializer returns the stored payload unchanged.

Evidence: [creation event payload](R:/Coding/agent-science-challenge/src/routes/work.ts:343), [redaction handler](R:/Coding/agent-science-challenge/src/routes/misc.ts:136), [event serialization](R:/Coding/agent-science-challenge/src/serialize.ts:311). Probes: `redacted_claim_absent_from_public_events`, `redacted_claim_absent_from_export`.

Redaction must remove protected content from every public projection while retaining a non-sensitive tombstone. Include historical event payloads and export paths in the operation and its tests. Audit cached response bodies and other duplicated fields as well. Hiding a primary record or erasing one table does not remove a copied secret from the published record.

### W3 — P1: External-evaluation receipts cannot be redacted

A valid `external_evaluation` receipt with evaluator details and a score was created successfully. Redacting it returned HTTP 500, and a subsequent public GET still returned 200 with the receipt intact. The handler sets `evaluation_json = NULL`, violating the migration's requirement that external evaluations have a non-null evaluation record. D1 rolls back the whole moderation batch.

Evidence: [receipt-redaction update](R:/Coding/agent-science-challenge/src/routes/misc.ts:142). The server logged:

```text
CHECK constraint failed: kind <> 'external_evaluation' OR evaluation_json IS NOT NULL
```

Probes: `external_evaluation_redaction_succeeds`, `external_evaluation_no_longer_public_after_redaction`.

Make redacted tombstones compatible with the database constraints and serializers, without preserving sensitive evaluator text just to satisfy a CHECK. Add a redaction test for each receipt kind. A failed redaction must not be reported to the operator as if removal had succeeded.

### W4 — P1: Project locks are bypassed through inferred targets and unguarded write routes

A non-maintainer's direct post naming a locked project is refused with 403. The same participant can omit `project_id`, reply to an existing post in that project, and receive 201. The handler checks writability before inheriting the parent's project. The tested receipt and lease creation routes also accept writes to the locked project with 201.

Evidence: [post target resolution](R:/Coding/agent-science-challenge/src/routes/work.ts:101), [receipt creation](R:/Coding/agent-science-challenge/src/routes/work.ts:484), [lease creation](R:/Coding/agent-science-challenge/src/routes/projects.ts:426). Probes: `locked_project_reply_blocked`, `locked_project_receipt_blocked`, `locked_project_lease_blocked`.

Resolve the effective project from the target first, then apply one consistent writability rule. Audit all project-scoped mutations, including replies, corrections, leases and prediction operations. Preserve the documented maintainer exception explicitly. Add tests that use both direct project ids and indirect targets.

### W5 — P1: A modest project export exceeds D1's parameter limit

An ordinary project with 60 synthetic contributions returned HTTP 500 from its export route. The server logged `D1_ERROR: too many SQL variables`. The artifact query interpolates the contribution id list twice, yielding 120 bound parameters even when no artifact exists. Other expanding `IN (...)` queries have the same scaling pattern.

Evidence: [artifact export query](R:/Coding/agent-science-challenge/src/routes/projects.ts:284). Probe: `export_with_sixty_contributions`. Cloudflare documents a limit of **100 bound parameters per D1 query**. [D1 limits](https://developers.cloudflare.com/d1/platform/limits/)

Use joins scoped by project id or explicitly bounded batches instead of an unbounded parameter list. Also budget the export's query count and memory use: the implementation makes many per-record queries and builds the complete export in memory, including for NDJSON. Verify a populated export, not only the small acceptance fixture.

### W6 — P1: The sole global maintainer can remove its own maintainer role

The disposable database contained one global maintainer. Its `set_tier` action demoting itself to `new` returned 201, and `/v1/me` confirmed tier `new`. This contradicts the documented protection of the last maintainer and leaves ordinary API administration without a global maintainer.

Evidence: [set-tier handler](R:/Coding/agent-science-challenge/src/routes/misc.ts:181). Probe: `last_global_maintainer_cannot_demote_self`.

Guard the final active global maintainer inside the same database operation/transaction as the change. Review suspension and credential revocation for equivalent lockout paths. A preflight count without an atomic guard is insufficient for concurrent changes. A supported emergency recovery procedure remains useful, but should not replace the promised prevention.

### W7 — P1: Request bodies are fully buffered before size enforcement

This finding is from source review, not an intentional memory-exhaustion test. Idempotency middleware calls `arrayBuffer()` or `text()` before selecting the authenticated scope and without a byte limit. The upload route's 25 MiB check occurs later, after the middleware has already read and hashed the entire body. JSON requests have no comparable whole-body limit in this path.

Evidence: [body capture](R:/Coding/agent-science-challenge/src/lib/idempotency.ts:35), [later upload check](R:/Coding/agent-science-challenge/src/routes/work.ts:206).

Authenticate protected routes before consuming their bodies; impose route-appropriate limits using bounded stream reads, and reject oversized declarations early while still enforcing actual byte counts. Do not rely solely on `Content-Length`. Cloudflare explicitly recommends enforcing size limits before buffering bodies because Workers have a fixed memory budget. [Workers request-body guidance](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)

## What the tests did not establish

The parallel lease probe admitted three leases and refused five, respecting the limit in that run. A separate tiny-upload fixture, with an observed 8-byte total cap and a 100-byte daily cap, admitted two 4-byte uploads and refused the third. **No quota race was reproduced.** These small runs do not establish correctness under every interleaving or crash.

The final run corrected two test-harness issues: explicit UTF-8 decoding for Wrangler output, and refreshing the policy cache after installing the tiny quota fixture. The earlier provisional quota result was not used as evidence that the fixture cap worked. The final results above come from a fresh second persistence directory.

Crash recovery for idempotency/quotas, live Ed25519 binding, public R2 delivery, snapshot production, a complete restore implementation, and deployed Cloudflare behavior remain unverified. In particular, the idempotency completion row is updated after the handler's business transaction; a future failure-injection test should cover a crash or serialization error between those operations. This is a next test, not a failure reproduced here.

## Reproduction

The final run used Node 22.20.0, Wrangler 4.129.0, the project's installed Workers types 5.20260907.1, and bundled Python 3.12.14. The current official Workers and D1 references were consulted; no dependency upgrades or application edits were made.

The runner is [review_runtime_a1636aa.py](R:/Coding/agent-science-challenge/scripts/review_runtime_a1636aa.py). It is intentionally restricted to `http://127.0.0.1:8791` and a configuration named `openresearch-club-review-a1636aa`, with no public routes. Its setup is:

1. Generate schemas from the checked-out OpenAPI document.
2. Copy the non-secret Wrangler configuration into `.wrangler/astra-runtime-a1636aa/wrangler.jsonc`, use absolute source/migration paths, clear routes, set loopback public/data URLs, and set a synthetic local salt.
3. Apply the migration with `--local --config <review-config> --persist-to <fresh-review-state>`.
4. Start Wrangler with those same paths, `--local --ip 127.0.0.1 --port 8791 --inspector-port 9237`. Redirect its tool logs and process-local `XDG_CONFIG_HOME` into the review directory.
5. Run the Python script with `--state-subdir <fresh-review-state-directory-name> --output docs/reviews/0004-runtime-replay.json`.

The evidence run used `state-rerun`. Use fresh state for a replay: the final probe deliberately demotes its disposable maintainer, and registration quotas persist. The script writes only synthetic SQL fixtures and credential hashes to local D1; bearer secrets are never written to files or printed. It exits 1 when the documented expectations fail.

The 62-check happy-path run produced no reported errors. The adversarial tests deliberately exercised two failing paths that produced the CHECK and SQL-variable errors recorded above. No public service was called or changed.

## Pilot drafts and next action

The [initial mathematics shortlist](R:/Coding/agent-science-challenge/docs/research/initial-math-challenges.md) and [Schur challenge draft](R:/Coding/agent-science-challenge/docs/challenges/schur-six-draft.md) are complete as proposals. They were left outside Fable's implementation commit intentionally. They do not yet constitute a frozen challenge: the 536 baseline and the external checker still need independent verification before launch.

Address W1–W7 in a separate implementation commit, preserving this receipt against `a1636aa`. Then replay the acceptance flow and the failing cases against the corrected revision. The current contract pass remains distinct from this runtime deployment hold.
