# Review receipt 0003: contract revision 3

**Reviewer:** Astra, using Codex.  
**Date:** September 7, 2026.  
**Target:** `370f214f9996fb479c43fa1266bdb293ca14259f`.  
**Kind / outcome:** `review` / `no_concerns`.  
**Disposition:** R3 and R6 follow-ups closed. The contract is ready for the agreed local Worker implementation.

This is a narrow recheck of the two changes identified in review 0002, together with a replay of the expanded contract suite. Earlier receipts, their evidence, and their scripts remain unchanged. This receipt does not claim acceptance of a running service.

## Verified

**Expanded suite: 314 passed, 0 failed.** The unchanged second-review suite validates the OpenAPI document and its references, positive and negative payload fixtures, receipt kind/outcome combinations, response/export representation, and evidence-facet behavior. Its previously failing historical-objection case now passes. [Expanded results](R:/Coding/agent-science-challenge/docs/reviews/0003-expanded-probes.json)

**Focused suite: 72 passed, 0 failed.** The additional checks use SQLite with foreign keys enabled and synthetic records. [Focused results](R:/Coding/agent-science-challenge/docs/reviews/0003-narrow-probes.json)

- **R3 closed.** Challenge insertion rejects missing, stale, and future contract versions; accepts the current version; and allows an ordinary project to omit the field. Both first submissions and subsequent revisions are covered. Reading version 1, publishing version 2, and then submitting version 1 is rejected. Existing version-1 provenance remains intact. The API, guide, and invariant now require the client to state the version rather than having the server infer it.
- **R6 closed.** Open and answered objections against active, corrected, or withdrawn receipts move from the current count into the historical count when the contribution advances. Hidden/redacted receipts and resolved/withdrawn/hidden objections are excluded as documented. The focused suite checks all 50 combinations of current-versus-historical position, receipt status, and objection status.

The SQL metadata records API and skill version `1.1.1`. Contract versions 1 and 2 remain available in the fixture, and the final foreign-key check is clean.

The original first-review suite is not a current acceptance gate: its old fixture omits a challenge contract version, which the new trigger intentionally rejects. Its historical results remain preserved. I did not modify it to bypass the new rule.

## Scope and next step

No remaining findings in the two changes reviewed. Combined with review 0002's verified fixes, this clears the contract review gate for **registration → context packet → contribution → revision-bound receipt → events → export**, implemented locally against local D1.

The version-change check here is a sequential SQLite transaction-ordering test, not concurrent HTTP testing. Worker authorization, HTTP 400/409 mapping, transaction rollback, idempotent retries, quotas, actual export/import, and R2 behavior still require implementation tests. No Worker, deployed D1, bucket, credential, DNS setting, or research submission was exercised by this review.

Carry the version-change rejection and receipt-objection transition into the Worker's tests. The supplied bucket name remains `openscience`; Wrangler authentication is available according to the user's handoff. This review neither changes that setup nor requires it for the local contract checks.

## Provenance and replay

| Reviewed source | Git blob |
| --- | --- |
| `migrations/0001_init.sql` | `daac42fa74eeb191dc5abeef2b7c2c5b03c51333` |
| `api/openapi.yaml` | `98de7f1007f49e23cdd54f8e7dd2f587114e44bb` |
| `skill.md` | `ef808c38d54233135910c8190c2d24c217c2d76d` |
| `docs/data-model.md` | `b9672aedc22ecb98a8f0bd7b44c00c072e51b983` |

From the repository root:

```text
uv run --no-project --python 3.12 --with-requirements scripts/requirements-review.txt -- python scripts/review_contracts_v2.py --output docs/reviews/0003-expanded-replay.json
python scripts/review_contracts_v3.py --output docs/reviews/0003-narrow-replay.json
```

The recorded runs used the bundled Python 3.12.14 and SQLite 3.53.1. The expanded suite used the existing pinned review dependencies; the focused script uses only Python's standard library. Both reports include the target commit and source byte hashes. [Focused probe script](R:/Coding/agent-science-challenge/scripts/review_contracts_v3.py)

The execution was independent of Fable's tests, but both reviewers share the operator, source implementation, and earlier design. This is a separate review execution, not independent-operator scientific corroboration. The reviewed sources are unchanged, and this local receipt has not been posted to a club API.
