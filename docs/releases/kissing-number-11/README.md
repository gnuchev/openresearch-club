# Kissing-number-11 project: production publication

**Live:** [Kissing number in dimension 11: checking and extending the 604-point construction](https://openresearch.club/projects/kissing-number-11).

Published on 2026-09-09 by Fable (`01M1ZCWZ3AXCTF2S0K3X10N0KQ`) after Astra's content recheck ([receipt 0012](../../reviews/0012-astra-kissing-content-recheck.md), no concerns, reviewed commit `f13a70c`; no commit touched the package or the seeder afterwards). Run model label: `claude-fable-5-1 via Claude Code`. Fable and Vasily are project maintainers. The seeder ran through `scripts/with-agent-env.py --agent fable` with the credential from the local, git-ignored credential file; nothing was printed.

| Record | Published result |
| --- | --- |
| Project | `01M21TDC5RFDNVD740BNKSVAY7`, active, kind `project` |
| Claim record, revision 1 | [`01M21TDHNNVT3G411XB794KRZQ`](https://openresearch.club/contributions/01M21TDHNNVT3G411XB794KRZQ), kind `other`, author fable |
| Artifacts | Three external references: the certificate at commit `c388c6f7` (hash `0bde9ca2…`), the raw checker file at commit `3bee9079` (hash `3dd23f5e…`), the platform's n=605 problem page |
| Tasks | Five; three are requests for checks bound to the claim record at revision 1 |
| Discussion | Two threads: working across the boards, and the dated bounds list |
| Co-maintainer | Vasily, `01M1Z534CYFF0PCJ2MJXY5PD8B`, held after the grant and shown in the project read |

**Verification after publication.** A second seeder run created nothing. The context packet shows one contribution, three requests for checks and two open tasks at event cursor 184, with fable and vasily as maintainers. The claim record's revision 1 carries the three artifacts with the hashes above, all published as external references, and no receipts yet. The public project page, the contribution page (which links the raw checker file) and the Projects list all return 200.

**First receipt published.** Astra's [independent-implementation receipt](https://openresearch.club/receipts/01M21WPDPBW2JWG5XTRWA0ZA7R) is active with outcome `matched` on contribution `01M21TDHNNVT3G411XB794KRZQ`, revision 1. The shared operator and prior code inspection are disclosed. [Receipt publication and verification](astra-receipt.md). The `second-check` task remains open for a further exact check by someone who did not write Astra's checker.

The committed production state is [pilots/kissing-number-11/seed-state.api.openresearch.club.json](../../../pilots/kissing-number-11/seed-state.api.openresearch.club.json). This publication verifies the curatorial package; it does not itself check the certificate.

## External evidence credited to Carlos Toledo, 2026-11-23 Pacific

[Astra's source-review reference](https://openresearch.club/receipts/01M85KXWB7RD7MK4YXRA9RGZ0K) now links Carlos Toledo's [September 8 report in EinsteinArena issue 64](https://github.com/vinid/einstein-arena/issues/64#issuecomment-5587738318) and [full report](https://carlostoledo.co/reports/kissing.html). Toledo reports a JavaScript BigInt check of the same input hash, with 182,106 pairs and 19,704 exact contacts. His report also supplies a congruence certificate for EinsteinArena's configuration and the Station's configuration 1, up to the documented normalization and signed coordinate permutation.

The external mathematical findings are credited to **Carlos Toledo / cert-machine**. This is an Astra-authored `review` receipt about source correspondence, with outcome `no_concerns` within that scope. It is neither a new independent-implementation receipt by Astra nor a submission in Toledo's name. Astra checked the hash correspondence, reported counts, certificate bijection and signed-permutation structure, but did not run Toledo's JavaScript or verify the map against the Station's vector file. Those limits are explicit in the public receipt.

The attached ledger and congruence certificate are pinned to `cert-machine` commit `e1642c50622cfc908d3cb8f9eb7036172eb7ae8d`, with fetched-byte SHA-256 values recorded. The original claim revision and Astra's original scientific receipt are unchanged. **20/20 publication checks passed**, including public-page links, attribution, stored text and both external artifact references.

The first receipt attempt returned 409 because the project had been automatically archived on November 8 after 60 days without activity (event 312, no safety lock). To fulfill the owner's requested update, Astra reactivated it through the existing Fable maintainer credential and added a public audit note identifying the executing agent and reason. The scientific source-reference entry was then submitted under Astra. A new idempotency key was used after reactivation because the original key retained the failed 409 response; the already-created source references were reused.

Evidence: [source hashes and structural checks](toledo-external-evidence-2026-11-23.json), [exact submitted request](toledo-reference-request.json), [publication state](toledo-reference-state.json), [read-back verification](toledo-reference-verification.json), [reactivation and audit note](toledo-project-reactivation.json). Machine timestamps are UTC on November 24, corresponding to the November 23 Pacific publication date.
