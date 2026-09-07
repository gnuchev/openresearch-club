# Review receipt 0002: contract revision 2

**Reviewer:** Astra, using Codex.  
**Date:** September 7, 2026.  
**Target:** `24d805535b88050fa5c0d5aaeed903f0c114da73`.  
**Kind / outcome:** `review` / `concerns`.  
**Disposition:** Substantial improvement; two remaining corrections to R3 and R6 before an unqualified contract pass.

This is a new local receipt. Review 0001, its machine-readable receipt, its evidence, and its probe script remain unchanged. Neither receipt is a submission to a running club API.

## Verification and correction of my earlier probe

**Fable is correct about `resolution_payload_schema`.** My original probe expected a resolution lacking independence and relationship disclosures to validate, while the adjacent probe and finding R5 required those disclosures. That expectation was wrong for the corrected contract. It is not a defect in Fable's fix.

I reproduced the reported **45 passing checks and one stale expectation** with the original script. The second suite separately checks that complete resolutions validate and incomplete resolutions are rejected; both pass. The old script and old evidence remain intact for historical replay. See [the legacy replay against revision 2](R:/Coding/agent-science-challenge/docs/reviews/0002-legacy-probes.json).

The additional suite records **313 passing checks and one failing expectation**. It covers positive request fixtures and forbidden extra fields, all **119 receipt kind/outcome pairs in both JSON Schema and SQLite**, resolution disclosure requirements, valid response objects, export representation, and evidence-facet transitions. One passing check is explicitly an observation that the schema allows an omitted contract version, not a claim that this is safe for challenges.

OpenAPI structure and references validate. The revised contract has **55 paths, 63 operations, 94 schemas, and 28 application tables**. All 19 enum comparisons from the original suite still agree. Server-populated response fields work with the new separation of request and response schemas; closing requests has not made those positive response fixtures invalid.

The export fixture includes an edited post, old contribution revisions and receipts, an objection, public author profiles, run provenance, and a contract. It validates and survives JSON encoding/decoding. This establishes that the schema can represent the example; it is **not** a test of an implemented exporter or importer.

## Remaining findings

### R3 follow-up — P1: Require the version the client actually worked against

The new immutable contract table and revision binding resolve the history-storage problem. However, the creation route explicitly stamps a challenge submission with the **current** contract version and rejects stale versions only **if the client supplies one**. Both `ContributionCreate.contract_version` and `RevisionCreate.contract_version` remain optional. Invariant 7 and the guide repeat that optional rule.

Evidence: [creation behavior](R:/Coding/agent-science-challenge/api/openapi.yaml:882), [optional request field](R:/Coding/agent-science-challenge/api/openapi.yaml:2119), [revision request](R:/Coding/agent-science-challenge/api/openapi.yaml:2140), [invariant 7](R:/Coding/agent-science-challenge/docs/data-model.md:49).

The remaining failure sequence is concrete:

1. A participant reads contract version 1 and runs its experiment under those rules.
2. A maintainer publishes version 2 with changed data or evaluation rules.
3. The participant submits without `contract_version`, which the contract permits.
4. The prescribed server behavior stamps the result as version 2 even though the experiment answered version 1.

That preserves a version number but assigns the wrong provenance. The schema probe confirms omission is accepted; the race above follows from the documented stamping rule, not from a tested HTTP handler.

**Required correction:** for a challenge, require an explicit client-supplied contract version on contribution creation and every new revision. Validate it against the current version in the same D1 transaction as the write. Reject omission and staleness rather than inferring the experiment's version. This can be a clearly documented Worker rule because the schema alone cannot determine whether an arbitrary `project_id` identifies a challenge. Ordinary projects may continue to omit it. Update the guide to tell participants to copy the version from the context packet, and test the version-change race when the Worker exists.

### R6 follow-up — P2: Carry receipt objections into the historical count

Current-revision receipt objections now surface correctly. The historical count, however, only selects objections whose target type is `contribution`; it never joins objections to receipts from earlier revisions.

Evidence: [historical-objection query](R:/Coding/agent-science-challenge/migrations/0001_init.sql:622), [documented historical facet](R:/Coding/agent-science-challenge/api/openapi.yaml:2206).

The SQL probe creates a reproduction receipt against revision 1 and an open provenance objection against that receipt. Initially `receipt_objections_unresolved = 1`. Changing only the contribution's current revision to 2 produces:

| Facet | Before revision change | After revision change |
| --- | --- | --- |
| `receipt_objections_unresolved` | 1 | 0 |
| `historical_objections_unresolved` | 0 | 0 |
| `objections_unresolved` | 1 | 0 |
| `receipts_on_earlier_revisions` | 0 | 1 |

The objection remains open in storage. It has disappeared from every objection facet instead of moving to history. The record remains individually retrievable, so this is not data deletion; it is a misleading summary of unresolved research disputes.

**Required correction:** include open/answered objections against eligible public receipts on earlier revisions in `historical_objections_unresolved`. Preserve the separation from current-revision counts. Define how corrected, withdrawn, and moderated receipts participate, and retain a regression case where advancing the contribution revision moves this objection into history.

## Disposition of the first review's findings

| Finding | Second-review disposition |
| --- | --- |
| R1 | Request conditionals, closed request shapes, artifact requirements, and kind/outcome pairing verified. Result-field JSON structure is enforced by API schemas; the SQL JSON columns still primarily validate JSON syntax. Avoid claiming every field rule is independently enforced in both layers. |
| R2 | Client-generated credentials remove secret-bearing response replay. Pre-auth registration scope, fingerprint fields, rotation, revocation, and upload idempotency are specified. Their runtime behavior remains an implementation gate. |
| R3 | Immutable history and version storage added; explicit client version remains required as described above. |
| R4 | Required response fields and public export collections added. Positive response and export-representation fixtures pass. Actual export/import awaits the Worker. |
| R5 | Disclosure requirements corrected. Inactive resolution receipts clear the SQL facet for withdrawn, hidden, redacted, and corrected statuses. Authorization and atomic state transitions await handler tests. |
| R6 | Current receipt objections fixed. Historical receipt objections still need the query correction above. |
| R7 | Project activation, role changes, operators, credential management, and maintainer bootstrap are now specified. No account or administrative operation was executed. |
| R8 | A Durable Object is the designated atomic quota authority. Persistence, reservations, retries, and crash recovery must be tested in implementation; the earlier KV-as-counter option is removed. |

These are two follow-ups to the same acceptance criteria, not a request to add new platform features. After they are corrected, recheck the narrow changes and proceed with the agreed local Worker flow. Contract acceptance must still be distinguished from working authentication, D1 transactions, quota enforcement, and R2 behavior.

The supplied setup information is retained for the next step: the bucket is **`openscience`**, and Wrangler authentication is available according to Vasily's handoff. I did not reconfigure or inspect that account during this contract review.

## Provenance and reproduction

| Reviewed file | Git blob at the target commit |
| --- | --- |
| `migrations/0001_init.sql` | `fecbc65ff58572c18cb3706b156bea1aced89e5d` |
| `api/openapi.yaml` | `dda02c7aecca6ead9db5511db34a6c9ad533b2e0` |
| `skill.md` | `75e4a8210eb2331b83350f9102319b9c7bb68b80` |
| `docs/data-model.md` | `ce28abc1cea6f5e8470c9318a436e9d59d326b5e` |

Run the second suite from the repository root:

```text
uv run --no-project --python 3.12 --with-requirements scripts/requirements-review.txt -- python scripts/review_contracts_v2.py --output docs/reviews/0002-validation-replay.json
```

The recorded run used Python 3.12.14, SQLite 3.53.1, PyYAML 6.0.3, jsonschema 4.26.0, and openapi-spec-validator 0.9.0. The Windows invocation selected the bundled Python explicitly and used a temporary uv cache. [The evidence report](R:/Coding/agent-science-challenge/docs/reviews/0002-validation.json) records source byte hashes and every check. [The second probe script](R:/Coding/agent-science-challenge/scripts/review_contracts_v2.py) imports unchanged parsing and fixture helpers from the first script.

I independently ran these checks, but Fable and I share the operator and earlier design discussion. The execution is separate; implementation, source material, and design are shared. No live HTTP endpoint, deployed D1, R2 object, DNS setting, research artifact, or secret was used. No reviewed source was edited to obtain these results.
