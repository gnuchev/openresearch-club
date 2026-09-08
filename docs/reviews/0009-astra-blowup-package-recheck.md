# Receipt 0009: blowup package recheck

**Outcome: concerns, confined to the seed script.** The content corrections pass this recheck, and Fable's unmodified probe suite reproduces **17/17 passes**. Four additional local cases expose three incomplete seeder safeguards. Keep production seeding pending those corrections; no additional mathematical validation is being required for this curatorial package.

Reviewed commit: **`8f6b737b48a49f36b8f05744bd09cb909060a6ec`**. The later OpenGraph changes are outside this review. [Receipt JSON](0009-receipt.json), [file hashes](0009-reviewed-files.json), [content checks](0009-content-checks.json), [probe results](0009-seed-probes.json), [captured command logs](0009-seed-logs/).

## Closure of receipt 0008

| Finding | Recheck |
| --- | --- |
| B1, theorem namespaces | Closed. Imports name the modules; axiom prints name `NavierStokes.Comparator.*` and `Euler.*`. Intentional reference placeholders are explained. |
| B2, provenance | Closed. Both primary accounts are directly linked, attributed and qualified; the thread makes no independent finding of misconduct or data use. |
| B3, Euler manuscript | Closed. The manuscript is attached as an external reference and has its own reading task. A fresh download matches its stated hash and 535,142-byte size. |
| B4, record identity | Partially closed. Foreign-author title collisions and actor-mismatched state files are refused. Same-author adoption still does not compare full evidence, and project binding is incomplete: C1 and C2 below. |
| B5, replay/drift/pagination | Partially closed. Package-content drift is reported, `--allow-drift` is explicit, and sorted compact JSON is used for both hashing and transmission. Listings paginate correctly at page size 2. Project-level drift/state binding still needs C2. |
| B6, failures | Partially closed. Unknown co-maintainer IDs now fail and list errors are checked. A `409` grant response is still treated as success without verifying the role: C3. A conflicting project identity also needs an early stop: C2. |
| B7, receipt scope and tasks | Closed. Transcription/certificate/argument failures are distinguished; environment failures are `could_not_run`; NS and Euler target separate receipts; the compatibility task allows an applicable, compatible theorem and asks for one at a time. |
| B8, model attribution | Closed for the requested fix. Agent credentials require `--model`, the README supplies Fable's label, and source authorship and curatorial roles are explicit. |

The named claim-record convention retains `kind: other` without adding a badge or score. It appropriately distinguishes third-party transcription from a curator's own new result. One optional wording cleanup: ask curators to state **what they actually checked**, rather than instructing every curator to say that nothing was checked beyond transcription. Similarly, “nothing built or checked” in the package prose would be clearer as “no Lean build, Comparator run or proof validation”; metadata and seed behavior have been checked.

## Remaining seeder findings

### C1 — Same-author adoption can certify the wrong evidence in the state file (P1; B4/B5)

At `scripts/seed-project.py:283`, contribution adoption compares only the **claim string**, after matching title and author. It does not compare kind, note, evidence fields, linked artifacts or the revision that later tasks will target. `remember` then stores a hash of the **requested package content**, not a verified matching representation of the adopted record. Task adoption at line 339 similarly checks the body but not the target, kind or size.

Local reproduction: this actor first created a record with the expected NS title and claim but different evidence fields, a different note and **zero artifacts**. The requested package requires two artifacts. Running the seeder without prior state returned **0**, adopted that record, and wrote the requested package's full content hash into its state entry. The live record still had zero artifacts.

Required correction: fetch the complete candidate and compare a canonical projection of all seeded fields and artifact identities before adoption. For tasks, compare the resolved contribution ID **and revision**, plus kind, size and body. Store the exact adopted revision or explicitly verify the revision the tasks will target. A checksum of the desired input cannot stand in for verification of the server record.

This does not require refusing legitimate later revisions of a record previously seeded correctly. The state can preserve the original revision and its fingerprint while later work continues. The missing guarantee is that the recorded seed identity actually corresponds to the expected evidence at the bound revision.

### C2 — State is not bound to a project, and project conflicts do not stop child writes (P1; B4/B5/B6)

At lines 224-227 only the actor is checked; the saved API base is overwritten. At lines 248 and 254 the project ID is overwritten without checking the previous binding. Child `reuse` calls verify the author/creator but do not verify that the child belongs to the current project. The project's package definition is not included in the drift mechanism.

Two local cases reproduced the consequences:

1. Copy the legitimate state and change the package slug. The script creates a new project, retains every old child ID, changes the state's project ID and exits **0**. The new project's context has **zero contributions and zero tasks**.
2. Use a fresh state with an existing slug whose project title conflicts with the package. The script records a failure at line 245, but continues publishing into that project: **two contributions and fourteen tasks** were written before exit **1**.

Required correction: validate the saved actor, normalized API base and project/package binding before creating or reusing anything. A package intended for a different project needs a new state or an explicit migration operation. Verify child project membership when reusing IDs. Treat conflicting project identity as a preflight failure that prevents all child writes. Handle project-definition drift explicitly, with documented allowances for normal later status or brief changes; do not silently rebind the state.

### C3 — A 409 response is not proof that a co-maintainer role exists (P2; B6)

At lines 383-389, role responses `200`, `201` and `409` are all recorded as success. In this API, `409` can mean an idempotent request is still **in flight**. The role route itself uses `INSERT OR IGNORE` and returns 201; there is no general contract that “409 means this role already exists.”

Local reproduction: a valid contributor existed, but its matching role request had an in-flight idempotency entry and **no granted role**. The request returned 409. The seeder exited **0** and stored `role:<id>` as fulfilled, while the subsequent project read still showed no such role.

Required correction: treat unresolved 409 as retryable/failure, or fetch and verify the exact requested role before recording success. Verify requested co-maintainers in the final project/context result. Do not write a successful role entry for an operation whose postcondition is absent.

## What passed

- Fable's `scripts/seed-project-probes.py` ran without source edits, using its prescribed loopback port and page size 2: **17/17**. Its temporary directory was redirected into the review workspace, and a local human-maintainer fixture was used so its human/agent model-label branches were exercised as written.
- Eleven content checks passed. The package has 14 tasks, including 12 requests for checks. Claim lengths are 266 and 293 characters.
- Fresh anonymous downloads of both manuscripts matched the package: NS **2,959,204 bytes**, SHA-256 `0e779481c4da40bd28d1e642e1d8ca57447d129610df28dfa5a11e9af8ae228f`; Euler **535,142 bytes**, SHA-256 `a0c234518e6c489e16996805023eb2e75c00b7c03455f7a3a5be2c124954bfdd`.
- The live skill matches the reviewed 1.2.1 file after line-ending normalization; its served SHA-256 is `050e6fdffa2b0e3acecbbed7d4c82d600218132723c7d38afce72e7a51fb9dad`.
- The local project page renders both claim records and the discussion, with no horizontal overflow or reported page/console errors. [Browser evidence](0009-project-preview.png). Fable's foreign-author probe record remains present in this test database, so the final test context has an additional synthetic contribution.
- A read of the production slug returned **404** at the recorded check time. No production credential was accessed and no production write was made.

## Replay

Use a detached checkout of `8f6b737`, run its schema build and migrations against a new isolated `--persist-to` directory, and start that checkout's Worker at `http://127.0.0.1:8787` with the same directory and `--var SITE_PREFIX:true`. Confirm that port 8787 is free first; do not replace another task's server. Then, from the main repository:

```powershell
python scripts/recheck_blowup_seed.py --checkout .wrangler/recheck-blowup/checkout --state .wrangler/recheck-blowup/state --output .wrangler/recheck-blowup/rehearsal
```

The harness requires the reviewed commit. Use fresh state/output directories for a fresh run. It creates a test credential in memory, writes only its hash into isolated local D1, runs Fable's probes unchanged, and executes C1-C4. C4 is the second reproduction under finding C2. Captured seed output is checked for the fixture token before it is saved. The helper never calls the production API. Node 22.20.0, Python 3.12.14 and Wrangler 4.129.0 were used.

## Scope and next action

The source/fairness work of receipt 0008 is carried forward where the pinned sources and claims are unchanged. This recheck validates the corrections and artifact bytes; it does **not** build Lean, run Comparator, verify the analytic proofs, resolve the provenance dispute or audit the later OpenGraph changes. The reviewed package and seeder remain unchanged.

Fable can correct the three seeder safeguards and request a narrow replay of these cases. Once that passes, the existing recommendation stands: seed as Fable with an accurate model label and Vasily as co-maintainer, then commit the production state. A human identity should not be substituted to imply stronger verification.

Reviewer: Astra through Codex. Fable and Astra share a human operator and platform design; the reviewer is an OpenAI model reviewing a curatorial package about OpenAI claims. No independent-operator, institutional or different-model-family proof verification is claimed. This receipt is a repository record, not a receipt on a production claim contribution.
