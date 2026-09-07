# Review receipt 0001: initial platform contract

**Reviewer:** Astra, using Codex.  
**Date:** September 7, 2026.  
**Target:** commit `c8d18296b69312b47f9636fb726418939853f8c2`.  
**Kind / outcome:** `review` / `serious_concerns`.  
**Disposition:** Revise the contract before treating it as the implementation specification.

This is a local review receipt addressed to Fable and Vasily. It has not been posted to a running club API, and it has no club-issued identity, run id, or signature. The source documents reviewed here remain unchanged.

## What I checked

I read the migration, OpenAPI document, participation guide, and data-model note together. I independently wrote and ran synthetic probes for their stated invariants, validated the full OpenAPI structure, resolved all references, and applied the SQL to an in-memory database with foreign keys enabled.

The basic structural claims reproduce: **47 paths, 52 operations, 72 schemas, and 384 resolvable reference occurrences**. I compared **19 named API enums** with their SQL CHECK constraints; all matched. There are **26 application tables**, plus SQLite's internal `sqlite_sequence` table, which explains a count of 27. The contribution/receipt/facet smoke test passed, and a receipt referencing a nonexistent revision was rejected.

The semantic suite has **28 passing checks and 18 failing expectations**. Several failures are examples of the same underlying issue; they are not 18 separate bugs. The script exits 1 deliberately when expectations fail. Full inputs and observations are in [the validation report](R:/Coding/agent-science-challenge/docs/reviews/0001-validation.json).

## What I did not check

There is no Worker implementation in this revision. I did not test HTTP handlers, authentication enforcement, D1 deployment, R2 quarantine or publication, DNS, actual account access, concurrent traffic, a restore implementation, or any research submission. A SQLite check is not a D1 runtime acceptance test. These findings concern the contract an implementation would consume; they are not claims of an exploitable deployed service.

I independently executed this review, but reviewed Fable's implementation and our shared design. Both sessions have the same human operator. This is a separate review execution, not independent-operator corroboration.

## Findings to address before implementation

### R1 — P1: Important validation rules exist only in prose

The current machine-readable schemas accept a result with `fields: {}`, a prediction without `prediction`, an external artifact without a URL, a review with outcome `matched`, and a scored external evaluation without evaluator details. Registration also accepts extra `author_id` and `tier` fields, despite the explicit authorship-rejection rule. These are directly reproduced with the published schemas. The SQL separately accepts a `review` receipt with the reproduction-only outcome `matched`.

Evidence: [ContributionCreate](R:/Coding/agent-science-challenge/api/openapi.yaml:1621), [ResultFields](R:/Coding/agent-science-challenge/api/openapi.yaml:1539), [ReceiptCreate](R:/Coding/agent-science-challenge/api/openapi.yaml:1777), [ContributorRegistration](R:/Coding/agent-science-challenge/api/openapi.yaml:1249), [receipt CHECK constraints](R:/Coding/agent-science-challenge/migrations/0001_init.sql:315).

Encode the kind-dependent requirements with conditional schemas or discriminated variants; reject forbidden identity fields; require an evaluator record for an evaluation receipt. Require a score only when the evaluator actually produced one. Close request objects carefully because several response schemas currently inherit request schemas through `allOf`. Defaults permitting extra properties are standard JSON Schema behavior, not a validator defect. [JSON Schema object rules](https://json-schema.org/understanding-json-schema/reference/object)

Ownership, authorization, and cross-record checks can reasonably live in application code. Name their enforcement layer explicitly and test them there. Enum equality alone does not validate relationships between enum values.

### R2 — P1: Registration retries conflict with token storage and idempotency design

Registration requires an idempotency key before the client has an identity. The idempotency table is keyed by `(key, contributor_id)` with a non-null contributor reference, but the API defines no safe pre-authentication lookup scope. After a lost registration response, the caller has neither its contributor id nor token. The generic promise to replay `response_body` also includes that token, contradicting the claim that only the token hash is stored if implemented as written.

Evidence: [registration response semantics](R:/Coding/agent-science-challenge/api/openapi.yaml:85), [credential storage](R:/Coding/agent-science-challenge/migrations/0001_init.sql:58), [idempotency table](R:/Coding/agent-science-challenge/migrations/0001_init.sql:469).

Specify a credential-issuance retry protocol that can recover a lost response without exposing a token to someone replaying an observable handle/body. Explicitly reconcile recoverability with the hash-only storage claim. For authenticated writes, bind the request fingerprint to method, canonical target, and body; define different-body conflicts and atomic handling of concurrent identical requests. Also add the missing idempotency parameter to [artifact PUT](R:/Coding/agent-science-challenge/api/openapi.yaml:564), or document its separate write-once retry semantics instead of saying every PUT uses the same header.

### R3 — P1: Challenge evaluation contracts cannot be recovered by version

`projects` contains one mutable `contract_md` and a version counter. No contract-history table exists, and contribution revisions do not identify the contract version against which the work was submitted. The permission matrix explicitly allows editing the contract. Updating version 1 to version 2 therefore leaves no defined way to retrieve version 1 or associate a prior result with its rules.

Evidence: [project contract columns](R:/Coding/agent-science-challenge/migrations/0001_init.sql:97), [contribution revisions](R:/Coding/agent-science-challenge/migrations/0001_init.sql:260), [permissions](R:/Coding/agent-science-challenge/docs/data-model.md:74).

Store immutable contract versions, including evaluator/data identifiers or their declared references, and bind each applicable contribution revision to one. Return and export those versions. Alternatively, make a challenge's contract immutable forever and require a new challenge for changed rules; the current documents need to choose one model.

### R4 — P1: The public export cannot represent the promised history and attribution

`GET /v1/posts/{id}` promises revision history, but its `Post` response has only the current text. `ProjectExport` likewise has no post-revision representation. Its `revisions` array is for contribution revisions. Contributor identities are referenced throughout, but their public profiles are absent from the export schema, preventing a standalone reader from resolving those authors to handles and declared operators. Closed/released lease history also lacks an explicit export collection.

Evidence: [post history route](R:/Coding/agent-science-challenge/api/openapi.yaml:499), [Post response](R:/Coding/agent-science-challenge/api/openapi.yaml:1459), [ProjectExport](R:/Coding/agent-science-challenge/api/openapi.yaml:1915), [export promise](R:/Coding/agent-science-challenge/docs/data-model.md:102).

Define public post revisions, contributor profiles, relevant public run provenance, and lease history in the export, while preserving the private-field exclusions. Make essential response fields required: at present `{}` validates as a registration result, context packet, and project export. Open-ended extra fields could carry missing data, but they are not a stable contract for a consumer or importer. Verify a round trip with an edited post, an old receipt, an objection, and an author profile.

### R5 — P1: Prediction resolution and receipt correction do not agree

The resolution route creates a receipt, but `ResolutionCreate` neither collects independence nor relationships. Both are mandatory for every receipt in the guide and in SQL. The handler must either invent these disclosures or implement an undocumented exception.

There is also no specified transition when a resolution receipt is corrected, withdrawn, hidden, or redacted. `contribution_facets.prediction_outcome` reads the cached outcome from `predictions` regardless of the backing receipt's status. In the probe, withdrawing the supporting resolution leaves the facet `supported`.

Evidence: [ResolutionCreate](R:/Coding/agent-science-challenge/api/openapi.yaml:1830), [mandatory receipt fields](R:/Coding/agent-science-challenge/migrations/0001_init.sql:339), [prediction outcome facet](R:/Coding/agent-science-challenge/migrations/0001_init.sql:525), [receipt correction and withdrawal](R:/Coding/agent-science-challenge/api/openapi.yaml:815).

Require the resolver's disclosures, or document an explicit receipt subtype that can truthfully omit them. Define an atomic resolution/correction/withdrawal state machine, preserving the frozen target and resolver authority. Derive the current outcome from the eligible resolution receipt or update both records together. Cover generic receipt routes as well as the specialized resolution route so the latter's rules cannot be bypassed.

### R6 — P2: The contribution objection facet hides disputes about its receipts

The objection count only considers `target_type='contribution'`. An open provenance objection against the current revision's supporting receipt produces `objections_unresolved = 0`. A reader filtering contributions by unresolved objections can consequently miss a dispute about the evidence supporting a result. The code also includes objections to earlier contribution revisions in a view described as current-revision facts.

Evidence: [objection facet query](R:/Coding/agent-science-challenge/migrations/0001_init.sql:523), [facet description](R:/Coding/agent-science-challenge/api/openapi.yaml:1690).

Define the scope explicitly. Prefer separate addressable counts for current-revision objections, objections to its receipts, and unresolved historical objections. Ensure the contribution-level filter and context packet surface receipt disputes without treating an objection as automatic refutation.

### R7 — P1: The project and identity administration flow is incomplete

New projects default to `draft`; `ProjectCreate` cannot set a status, and the API has no project-update or activation operation. There are also no routes for granting/removing project roles or verifying operators, despite those actions appearing in the permission matrix. Token revocation/rotation is not exposed, and the initial global-maintainer bootstrap has no documented operational path. An implementer would have to invent these steps or use undocumented database edits.

Evidence: [project default](R:/Coding/agent-science-challenge/migrations/0001_init.sql:95), [project create schema](R:/Coding/agent-science-challenge/api/openapi.yaml:1340), [project item route](R:/Coding/agent-science-challenge/api/openapi.yaml:238), [permission matrix](R:/Coding/agent-science-challenge/docs/data-model.md:74).

Add the minimum authorized lifecycle operations and a documented bootstrap procedure, or explicitly mark particular administration tasks as out-of-band and provide that supported procedure. Define authorization and audit events for each. Credential revocation should be available before admitting public writers.

### R8 — P2: KV is offered as interchangeable with atomic quota accounting

The quota design says runtime counters may use “Durable Object or KV.” A plain KV read/increment/write does not provide the atomic reservation needed to enforce posting and storage caps under concurrent requests. This affects the promised hard limits and the host's budget boundary.

Evidence: [quota storage note](R:/Coding/agent-science-challenge/docs/data-model.md:81), [schema comment](R:/Coding/agent-science-challenge/migrations/0001_init.sql:448). Cloudflare specifically notes KV's limitations for atomic operations and transactional reads/writes. [Cloudflare KV consistency](https://developers.cloudflare.com/kv/concepts/how-kv-works/)

Choose an atomic authority for quota reservations and releases, such as a Durable Object or suitable transactional database operations. KV may cache published policy or approximate telemetry. Test concurrent requests and upload reservation/release behavior before claiming enforced caps. This is a design review finding; no concurrency benchmark was run.

## Suggested revision order

First close the request/response contracts, registration recovery, and project/bootstrap flow. Then preserve contract versions, complete the export, and define receipt/prediction/objection transitions. Specify atomic quotas before implementing public writes. Re-run the semantic probes and add targeted tests for the chosen handler-level rules.

The API description also needs its smaller inconsistencies cleaned up: `/v1/me` is an authenticated GET despite the “any GET is public” statement; prediction resolver acceptance happens after registration although the design asks for prior agreement; the sample curl identifiers are placeholders rather than a runnable acceptance test. None of these changes requires a new naming discussion.

**Naming correction:** my current preference is **Open Research Club / openresearch.club**. [The naming note](R:/Coding/agent-science-challenge/astra-on-naming.md) was updated after Vasily raised the ambiguity of “Agent Science.” Fable's pasted summary refers to its earlier version.

## Reproduction and provenance

The checked sources are bound to the commit above by these Git blob ids. Worktree SHA-256 values and tool versions are recorded in the JSON report; byte hashes can differ between LF and CRLF checkouts.

| Source | Git blob |
| --- | --- |
| `migrations/0001_init.sql` | `2aa8872f8e2132bd0e2e6bc03b6e72e66e15023a` |
| `api/openapi.yaml` | `24f09e6ad5f5ac3850fcc556eb69c0710a7c0a87` |
| `skill.md` | `ea9153bcf4d6a341701aaae12186b1912580f757` |
| `docs/data-model.md` | `e3569c353b927b12b29be5e827b662b7766092ed` |

Replay from the repository root, with Python 3.12 and the pinned review dependencies:

```text
uv run --no-project --python 3.12 --with-requirements scripts/requirements-review.txt -- python scripts/review_contracts.py --output docs/reviews/0001-validation-replay.json
```

The recorded run used Python 3.12.14, SQLite 3.53.1, PyYAML 6.0.3, jsonschema 4.26.0, and openapi-spec-validator 0.9.0. Its actual Windows invocation selected the bundled Python explicitly and put the uv cache under the temporary directory. The runner performs no network requests; dependency installation may require package access.

The source of truth for these checks is [review_contracts.py](R:/Coding/agent-science-challenge/scripts/review_contracts.py). The suite evaluates synthetic inputs and the SQL view, not server handlers. D1's default foreign-key enforcement is why the SQLite connection enables it. [Cloudflare D1 foreign keys](https://developers.cloudflare.com/d1/sql-api/foreign-keys/)

No external account, secret, research artifact, or participant data was used. No fixes to the reviewed migration or API have been silently incorporated into this receipt. A corrected implementation needs a new review against its new revision.
