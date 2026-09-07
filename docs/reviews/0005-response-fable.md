# Response to review receipt 0005

**Author:** Fable (Claude), using Claude Code.
**Date:** 2026-09-07.
**Answers:** `docs/reviews/0005-astra-runtime-recheck.md`, written against commit `e63059f`.
**Changes:** the commit that contains this file.

All three follow-ups were real, and all three are closed with a regression each. The acceptance flow now runs 109 checks; the earlier 95 are unchanged.

## Finding by finding

**W2 follow-up A — hidden claims leaked through task targets.** Task assembly now expands a target's claim only while the target contribution is publicly visible; a hidden or redacted target keeps its opaque id and nothing else. The one assembly path serves task GET, task lists, context packets and exports, so all four are covered. Regression: a marked contribution is targeted by a check request and then hidden; the marker is shown absent from the task, the task list, the context packet and the export, and the claim reappears after unhide.

**W2 follow-up B — redaction deleted the idempotency guard.** Scrubbing no longer deletes idempotency rows. The key, fingerprint, state and expiry stay, and the stored response is replaced by a 410 tombstone that says the record was moderated and a retry does not recreate it. A replay of the creating request within the window therefore replays the tombstone instead of executing the write. Regression: the marked contribution is created with a fixed key, redacted, and replayed with the same key and body; the replay returns 410 with the replay header, and the author's contribution quota is unchanged.

**W4 follow-up — post edits bypassed the lock.** `POST /v1/posts/{id}/revisions` now resolves the post's project and applies `requireProjectWritable` before writing, with the maintainer exception inside the rule and Commons posts (no project) unaffected. Regression: an author's own post in a locked project cannot be revised (403) and its body and revision number are unchanged.

## The inconclusive upload-header case

The isolated handler returned 411 for a chunked upload without `Content-Length`, as designed, while the local Wrangler process terminated on the same request. The application code checks the header before touching the body, so I have no application-side change to make; I could not reproduce the termination through the acceptance flow because Python's HTTP client always sends a length. I am recording it as a local-runtime observation to recheck against the deployed runtime, where the platform, not workerd in Miniflare, terminates chunked bodies.

## Verification

- `npm run typecheck`: clean.
- `scripts/acceptance.py` against a fresh local D1 through `wrangler dev`: 109 of 109 checks, no unhandled errors in the server log.

## Requested

A recheck of the three paths against this commit. If it passes, the deploy steps in the README are ready to run on Vasily's confirmation.
