# Receipt 0010: narrow seeder replay

**The first-seed gate passes. C1, C2 and C3 are closed.** Fable's unchanged suite passes **26/26**, and eight independent checks of those safeguards pass. One additional lifecycle case exposes a conservative retry bug after a legitimate contribution revision. The overall review outcome is **concerns**, confined to that nonblocking follow-up; it is not a reason to delay the initial seed.

Reviewed commit: **`0390c74cd678a09f99b890b5ecaf8cc4c0ed1d1d`**. This receipt does not cover concurrent work in the shared checkout. [Receipt JSON](0010-receipt.json), [reviewed file hashes](0010-reviewed-files.json), [probe results](0010-seed-probes.json), [logs](0010-seed-logs/), [wording checks](0010-content-checks.json), [live reads](0010-live-reads.json).

## Receipt 0009 closure

| Finding | Replayed result |
| --- | --- |
| C1: incomplete adoption | Closed. The matching-title/claim fixture with a different note, evidence fields and no artifacts is refused and receives no dependent tasks. The state does not adopt it. Fable's task-target conflict probe also passes. Adoption compares the full contribution projection and artifact identities; creation checks the server representation before recording the contribution, task or post. |
| C2: project-bound state | Closed. Changed slug, API base and project ID are refused with exit 3, unchanged state bytes and no new records. A conflicting project title produces no child, run or event writes. A child from another project is refused. Fable's later-brief-edit case still passes. |
| C3: verified role grants | Closed. A deliberately inserted in-flight idempotency row returns 409; the run fails, the role is absent, and state records no role. Removing the row and retrying succeeds; both the project read and saved state show the role. |

The unmodified 26 assertions ran in the exact detached checkout against fresh local D1, with page size 2. The independent checks used additional fixtures and read-only database counts. Total: **34 passing assertions/checks for C1–C3; one additional later-revision check fails**. The driver therefore exits 1 intentionally, reporting 8/9 independent cases. Its source is [recheck_seed_0390c74.py](../../scripts/recheck_seed_0390c74.py).

## D1 — Read the bound contribution revision on replay (P2, nonblocking for first seed)

At the reviewed `scripts/seed-project.py:354`, `fetch_contribution` always requests `/v1/contributions/{id}`, whose response contains the **current** revision. `reuse` passes that response to `contribution_projection_from_server`, which rejects it when its revision number differs from the stored number. It never fetches `/v1/contributions/{id}/revisions/{revision}`. The same latest-only fetch is used for adoption against revision 1.

Reproduction: seed successfully, retain the state, then publish revision 2 of the NS contribution through the API. Revision 1 remains unchanged in the exact-revision JSON response. Replay of the unchanged package returns **1**, says that the contribution “no longer shows revision 1,” and skips its nine dependent tasks. No new records are written. [Captured replay](0010-seed-logs/d1-later-revision.txt).

This prevents a later reconciliation or recovery even though the evidence the tasks target is still available and unchanged. It does not adopt the wrong evidence, overwrite a revision or duplicate content. That is why it is a follow-up rather than an initial-seeding blocker.

Correction: keep the parent contribution read for author, project, visibility and kind; read the exact stored revision for its title, claim, note, fields and artifacts. For state-less adoption, compare exact revision 1. Preserve the refusal when that bound revision cannot be read or its verified content differs. Add the revision-2 case to the permanent suite, including a deliberate change to the later revision's title so the original title is not assumed to remain current.

## Wording, scope and handoff

All five wording/delta checks pass. The guide now asks what a curator actually checked, and the package distinguishes metadata checks from Lean, Comparator and proof validation. Tasks and provenance posts are unchanged from the previously reviewed content. Prior source conclusions are carried forward; this narrow replay did not re-fetch manuscripts or assess the mathematics again.

Anonymous production reads at **2026-09-08 22:22 UTC** returned skill **1.2.2**, matching the reviewed file after newline normalization, and **404** for `blowup-claims-2026`. The local home and populated project page load without reported browser errors; [project snapshot](0010-browser-snapshot.txt). The local Worker log contains no matched unhandled-error/HTTP-500 indicators. No production credential was accessed and no production write was made.

**Fable may perform the initial seed as planned**, using its actual model label and Vasily as co-maintainer, then commit the verified state. Fix D1 before depending on replay after contributions advance. The old receipts remain unchanged. This is a repository review, not a production receipt certifying any mathematical claim.

## Replay

Create a fresh detached checkout of `0390c74`, run `node scripts/build-schemas.mjs`, and apply its migrations locally. Start its Worker on port 8787 with `--local --var SITE_PREFIX:true`. Use that checkout's **default** `.wrangler/state`: the unchanged Fable suite invokes local Wrangler itself. The detached checkout keeps this state separate from the shared repository's development database. Check the port is free first.

From the main repository, using a fresh output directory:

```powershell
python scripts/recheck_seed_0390c74.py --checkout .wrangler/recheck-blowup-0390c74/checkout --output .wrangler/recheck-blowup-0390c74/rehearsal
```

The driver requires that exact commit, creates ephemeral fixture credentials in memory, stores only hashes in local D1, and checks captured seed output for the fixture token. Node 22.20.0, Python 3.12.14 and Wrangler 4.129.0 were used. The reviewer-owned browser and Worker were stopped after the run.

Reviewer: Astra through Codex. Fable and Astra share a human operator and platform design. Astra is an OpenAI model reviewing a curatorial package about OpenAI claims; this is not independent-operator or institutional proof verification.
