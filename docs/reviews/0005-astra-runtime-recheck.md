# Review receipt 0005: runtime fixes

**Reviewer:** Astra, using Codex.  
**Date:** September 7, 2026.  
**Target:** `e63059f97ddbe640a9b512d5ae33daaaa7c5c810`.  
**Source tree:** `ce0ae958613f06e9966bdc083417650eedb6bf26` (`src/`).  
**Kind / outcome:** `review` / `concerns`.  
**Disposition:** The original reproductions are fixed; three follow-ups in W2/W4 remain before the deployment gate clears.

The reviewed application sources and receipt 0004 remain unchanged. Tests used fresh isolated local persistence (`state-e63059f`) on loopback port 8791, with local D1, Durable Objects and R2. No account resources, public domain or deployment were changed.

## Verified improvements

- TypeScript passed and the runtime-validator smoke suite passed **27/27**.
- Fable's expanded acceptance flow passed **95/95**.
- The unchanged runtime-review runner from receipt 0004 passed **15/15**, including its 60-contribution export, hidden-receipt filter, external-evaluation redaction, project-lock and last-maintainer cases. [Replay evidence](R:/Coding/agent-science-challenge/docs/reviews/0005-runtime-probes.json)
- A chunked JSON request exceeding 1 MiB was rejected with 413, exercising the actual-byte limit without relying on a declared length.

This confirms the fixes to the reported cases. The follow-up checks below exercise other paths through the modified visibility, idempotency and writability rules.

## Remaining findings

### W2 follow-up A — P1: Hidden claims leak through task targets

Create a contribution with a unique marker in its claim, create a task targeting it, then hide the contribution. Its direct GET returns 410, but the task's public GET returns the hidden claim in `target.claim`. The same marker appears in the project's export through that task.

The task assembler fetches target claims without filtering the target contribution's visibility. [Target-claim query](R:/Coding/agent-science-challenge/src/lib/common.ts:228)

**Observed:** task GET 200 with the hidden marker; export GET 200 with the same marker. These are the `hidden_claim_absent_from_task_target` and `hidden_claim_absent_from_task_in_export` failures in the [edge-probe evidence](R:/Coding/agent-science-challenge/docs/reviews/0005-edge-probes.json).

**Correction:** apply the public visibility rule when expanding task targets. Keep an opaque reference or non-sensitive tombstone if needed, but do not return a hidden target's claim. Cover task lists, individual tasks, context packets and exports, all of which use this assembly path.

### W2 follow-up B — P1: Redaction deletes the idempotency guard and a retry recreates the content

Create a contribution using an idempotency key, redact it, and replay the identical creation request with the same credential, key, path and body. The replay returns 201 with a **different contribution id**, publishing a new copy of the redacted text.

`scrubStmts` deletes the entire matching idempotency row, including the fingerprint and completion state, rather than just removing its sensitive response body. The next request is consequently treated as a new write. [Cache scrubbing](R:/Coding/agent-science-challenge/src/lib/common.ts:100)

**Correction:** retain the idempotency key, request fingerprint and expiry. Sanitize its response or replace it with a non-disclosing terminal response, so a retry cannot execute the write again during the promised idempotency window. This does not prohibit an intentional new submission; it preserves the distinction between a retry and a new operation.

**Observed:** `redacted_create_retry_does_not_create_new_record` failed, with both the original and replacement ids recorded in the evidence. No intentional new key or changed body was supplied.

### W4 follow-up — P1: Editing an existing post bypasses a project lock

A non-maintainer creates a post, the project is locked, and that author calls `POST /v1/posts/{id}/revisions`. The request returns 200 and changes the post's body while the lock is active. The handler checks authorship and post visibility but does not call the new project-writability helper.

Evidence: [post revision handler](R:/Coding/agent-science-challenge/src/routes/work.ts:143). Both the expected 403 and the expected unchanged body failed in the edge suite.

**Correction:** resolve the post's project and apply `requireProjectWritable` before creating its revision. Retain the documented maintainer exception and allow ordinary Commons posts with no project. This closes a path missed when applying the shared rule to replies and other writes.

## W7 upload-header result: inconclusive through local Wrangler

The raw edge report contains **2 passing and 6 failing expectations**. Five failures are the observations of the three confirmed findings above. The sixth is a separate missing-Content-Length upload check: a chunked binary request produced HTTP 500 and the local Wrangler 4.129.0 process terminated with an empty error report. There was no application `unhandled error` entry establishing the cause.

To isolate the branch, I bundled the unchanged Worker and called it in Node with mocked authentication/quota bindings. With the Content-Length header absent, the handler returned the expected **411 Length Required**. [Adapter evidence](R:/Coding/agent-science-challenge/docs/reviews/0005-body-header-adapter.json)

The adapter result is not a workerd or authentication acceptance test. I am not labeling the 500 as a proven application defect, nor counting the HTTP check as passed. Recheck this case through the local development runtime before claiming full upload-header acceptance. W7's authentication ordering and bounded-reader implementation address the original buffering finding; the declared-size and chunked-JSON rejection cases pass.

## Disposition of W1–W7

| Finding | Recheck result |
| --- | --- |
| W1 | Original receipt and objection status-filter cases pass. |
| W2 | Original claim/event/export redaction case passes. Task-target expansion and idempotent retry need the two corrections above. |
| W3 | External-evaluation redaction now succeeds and direct access returns 410. |
| W4 | Tested replies, receipts and leases respect locks; existing post edits still bypass them. |
| W5 | Both the 58-contribution acceptance fixture and the separate 60-contribution export pass. |
| W6 | The original last-maintainer demotion case and the expanded self-suspension checks pass. Exhaustive concurrent credential/administration testing was not performed. |
| W7 | Bounded JSON reads and early authentication verified; binary missing-length HTTP outcome remains unclassified as described above. |

## Reproduction and limits

The original replay used the unchanged [runtime-review runner](R:/Coding/agent-science-challenge/scripts/review_runtime_a1636aa.py) with `--state-subdir state-e63059f --output docs/reviews/0005-runtime-probes.json`. It executed the committed 95-check acceptance script before its own cases. The fresh-state setup is the isolated configuration described in receipt 0004.

The [follow-up script](R:/Coding/agent-science-challenge/scripts/review_runtime_e63059f.py) runs against that same loopback configuration and state, adds synthetic fixture identities, and records the visibility/retry/lock checks plus the two stream cases. The final stream case terminated the local dev process in this run; port 8791 was subsequently confirmed closed.

The isolated handler check uses [review_worker_body_headers.mjs](R:/Coding/agent-science-challenge/scripts/review_worker_body_headers.mjs) after bundling the unchanged `src/index.ts` with the installed esbuild. Its DB and quota bindings are explicitly mocked. Runtime tools were Node 22.20.0, Wrangler 4.129.0 and bundled Python 3.12.14; no project dependency was upgraded.

Tokens existed only in memory/environment; local SQL fixtures stored hashes. The shared operator and earlier joint design mean this is a separate review execution, not independent-operator scientific corroboration. Crash recovery, public R2 delivery, snapshots, actual restore, and deployed behavior remain outside this recheck.

Fix the three confirmed paths in a separate commit, preserve this receipt against `e63059f`, and rerun the narrow cases. Deployment still requires Vasily's confirmation after the review gate clears. The pilot documents remain complete as drafts and unchanged by this review.
