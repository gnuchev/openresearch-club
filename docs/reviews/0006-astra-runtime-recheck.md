# Review receipt 0006: three runtime follow-ups

**Reviewer:** Astra, using Codex.  
**Date:** September 7, 2026.  
**Target:** `46554c5367cfd5600206756de91fb239b6eebfef`.  
**Source tree:** `2041b270748d4bf29c738a80487129df1b104e19` (`src/`).  
**Kind / outcome:** `review` / `no_concerns`.  
**Disposition:** The three confirmed follow-ups in receipt 0005 are closed. The local review gate for these fixes passes; deployment remains subject to Vasily's confirmation.

This is a narrow recheck of the task-target visibility, redacted-request retry, and locked-post edit fixes. It does not rewrite the earlier receipts or claim that every possible runtime behavior has been verified.

## Verification

| Check | Result |
| --- | --- |
| TypeScript after generating the committed schemas | Pass |
| Runtime-validator smoke suite | 27/27 |
| Committed acceptance flow on fresh local D1 | 109/109 |
| Unchanged runtime-review runner from receipt 0004 | 15/15 |
| Focused W2/W4 recheck | 14/14 |

No unhandled application errors or D1 errors were found in the review server log. The fresh local persistence directory was `state-46554c5`; the API listened only on `127.0.0.1:8791`. The configuration had no public routes and used local D1, Durable Objects and R2 bindings.

[Acceptance and prior-probe evidence](R:/Coding/agent-science-challenge/docs/reviews/0006-runtime-probes.json) · [Focused evidence](R:/Coding/agent-science-challenge/docs/reviews/0006-focused-probes.json)

## Findings closed

**W2: hidden task targets.** The target's opaque reference remains, but its hidden claim is absent from individual task responses, task lists, context packets and exports. Unhiding the contribution restores claim expansion. The focused suite verifies all four projections and the unhide transition.

**W2: retry after redaction.** A retry using the original creation key and body returns a 410 tombstone instead of creating another contribution. The committed acceptance flow checks the replay header, and both suites check that contribution usage does not increase. Source inspection confirms that scrubbing retains the key, fingerprint, completion state and expiry while sanitizing the cached response.

**W4: edits under a lock.** An ordinary author cannot revise an existing post in a locked project: the request returns 403, and the text and revision number stay unchanged. The focused suite also confirms that a maintainer can edit its own post in the locked project and that a Commons post with no project can still be edited.

No remaining findings in these three paths.

## Upload-header observation and deployment boundary

The earlier chunked binary upload without Content-Length is **not marked passed** by this receipt. Receipt 0005 records that local Wrangler terminated on that request, while the isolated application handler returned 411 with mocked bindings. The cause of that local-runtime failure was not established. This narrow suite deliberately excludes that previously inconclusive transport case rather than relabeling it a success.

Carry the missing-length binary request into a controlled deployed-runtime smoke test after deployment is authorized. Deployment should also verify real D1 bindings, authentication/bootstrap, R2 upload and public delivery, and expected error responses. The existing limitations around crash recovery, snapshots, and actual restore remain documented; no new claim about them is made here.

No deployment, Cloudflare account mutation, real credential access or public-domain change was performed. Tokens for these tests existed only in memory/environment; the isolated database stored hashes. Application sources, the existing acceptance script, and all prior receipts were left unchanged.

## Reproduction

Use the isolated local configuration described in receipt 0004, with a fresh persistence subdirectory. Generate schemas, apply the migration locally, and start the Worker with the same state path and port 8791. The recorded run used Node 22.20.0, Wrangler 4.129.0 and bundled Python 3.12.14.

```text
python scripts/review_runtime_a1636aa.py --state-subdir state-46554c5 --output docs/reviews/0006-runtime-replay.json
python scripts/review_runtime_46554c5.py --output docs/reviews/0006-focused-replay.json
```

The first runner executes the committed 109-check acceptance script before replaying its 15 runtime cases. The [focused runner](R:/Coding/agent-science-challenge/scripts/review_runtime_46554c5.py) derives its fixtures from the unchanged receipt-0005 script, excludes the upload transport tests explicitly, and adds checks for all task projections, unhide, preserved quota, unchanged revision, and maintainer/Commons exceptions. It targets the same isolated `state-46554c5` directory.

Use fresh state for a full replay because registrations and quotas persist. Both evidence files identify the checked commit and source tree. This was a separate review execution from Fable's, with the same human operator and shared design; it is not independent-operator scientific corroboration.

The pilot documents remain complete as drafts and untouched by this recheck. The Schur baseline and checker still need verification before that draft becomes a frozen public challenge.
