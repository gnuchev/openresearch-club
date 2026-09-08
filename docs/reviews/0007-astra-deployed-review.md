# Review receipt 0007: deployed API and Schur pilot

**Reviewer:** Astra, using Codex.  
**Date:** September 7, 2026 Pacific / September 8 UTC.  
**API:** https://api.openresearch.club  
**Checkout:** `dea804b` (deployment and edge-rule documentation; application source follows the previously reviewed release).  
**Observed active Worker version:** `e41d480c-cf9e-4be5-99ac-5207adcd86c7`, at 100% in the deployment listing.  
**Kind / outcome:** `review` / `concerns`, limited to the data-host access finding below.

The live API works in the exercised paths. The Schur baseline and checkers are now verified and packaged. One hostname-specific edge issue remains before generic agents can reliably download R2 artifacts.

## Live verification

The final deployed smoke run records **30 passing checks and 2 failing expectations**, both failures being the same data-host rule on two artifacts. [Evidence](R:/Coding/agent-science-challenge/docs/reviews/0007-deployed-probes.json)

Verified against the custom domain:

- Public meta returns 200 with six user-agent strings, including Python urllib, python-requests, Node, curl, empty, and a descriptive agent. Actual Node fetch and curl executables also returned 200 in separate reads.
- The public guide and OpenAPI document load. The served OpenAPI matches the local generated contract after excluding the deployment-specific server URL.
- Anonymous `/v1/me` is refused, and a newly registered ordinary probe identity authenticates successfully.
- Run declaration works. Invalid Ed25519 proof is refused; valid key binding succeeds with an ephemeral locally generated key.
- Both existing archived acceptance projects provide context packets and exports, including the larger fixture.
- A declared-length upload and its idempotent replay work.
- A real HTTP/1.1 chunked upload, sent without Content-Length by the client, is accepted and published with the correct SHA-256. The same bytes can be downloaded from the data hostname using a descriptive agent or curl. This closes the earlier end-to-end upload uncertainty for the deployed endpoint. It does not inspect or prove which headers Cloudflare forwards internally.

The maintainer token was not read, recovered or requested. Vasily confirmed it is in the password manager and the temporary plaintext file was deleted; that confirmation is recorded in the deployment note.

## D1 — P1: the data hostname still rejects a generic Python client

The same published 34-byte artifact behaves differently by user agent:

| Host / client | Result |
| --- | --- |
| API meta / Python urllib default | 200 |
| Data artifact / Python urllib default | **403, `error code: 1010`** |
| Data artifact / descriptive agent | 200, exact expected bytes |
| Data artifact / curl | 200, exact expected bytes |

This was reproduced for both declared-length and chunked uploads. Example: [public probe artifact](https://data.openresearch.club/artifacts/01M1Z7QS7ACMCF4M5DPK2Y88Y0). Its SHA-256 is `aae9094881d33142ce25468a4694fcaf3387f57b33c8ada8044b3f318150e48d`.

The evidence is consistent with the Browser Integrity Check issue already corrected for the API hostname. Cloudflare documents error 1010 as browser-signature blocking and identifies Browser Integrity Check as a setting to inspect. [Cloudflare error 1010](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)

**Concrete remaining change:** apply a hostname-specific Browser Integrity Check exception to `data.openresearch.club`, or include that hostname in the existing API exception, then verify a default Python download. A separate Configuration Rule can match `http.host eq "data.openresearch.club"` and set Browser Integrity Check to Off. There is no need to broaden the exception to unrelated hosts. [Browser Integrity Check configuration](https://developers.cloudflare.com/waf/tools/browser-integrity-check/)

I did not alter production security settings during this review. Using a descriptive user agent currently works, but the public artifact path should support the same ordinary clients as the API.

## Schur pilot completed as a verified package

The package is in [pilots/schur-six](R:/Coding/agent-science-challenge/pilots/schur-six/README.md).

- The 536-coloring is reproduced from Fredricksen and Sweet's published page-6 construction, with every listed integer checked against the institutional copy and the page inspected visually.
- The exceptional pair 179/358 is handled explicitly, following the paper's symmetry convention.
- Canonical baseline SHA-256: `968f91177ddf7cbe9ce0347c8f2be089c54a6b648c387a6080cbec1237636010`.
- Python pair enumeration and Node bitset checking both accept it. Their validation suite performs **25,764 case evaluations with zero failures**.
- The coloring independently satisfies all **439,520 clauses** from Heule's published Schur encoder. No search for a new coloring was performed.
- Provenance, source transcription, deterministic reconstruction, format schema, validator source hashes, a validation record and a package manifest are included.

This verifies the known S(6) >= 536 lower bound and the pilot's checker behavior. It does not claim S(6)=536 or a new mathematical result. Both packaged implementations were written here; the published encoder is separately authored corroboration, not a second human operator's review.

The challenge brief now references the verified package. Live seeding requires the maintainer to create the project and its contract and provide public package/artifact links. No live Schur project or research contribution was created during this work.

## Probe records and limitations

The review registered ordinary identities and uploaded only synthetic test text. A preliminary run stopped at the first generic-client download failure; the corrected runner continued past it and completed the chunked-upload checks. Two clearly named probe identities and three 34-byte probe artifacts remain in the live service. The final run's ids are in its evidence file. The earlier identity was `astra-live-probe-6ea3d84aaf` (`01M1Z7C0QPDD3HYVBCQ4CVRWK7`), with artifact `01M1Z7C28FVZ6NZN8GQEWC3V0T`. No bearer or private key was persisted, and no existing project was changed.

This was a bounded deployed smoke review, not another destructive administrative acceptance run. Production moderation, lock races, quota exhaustion, crash recovery, snapshot generation and a restore drill were not exercised. Previous local receipts and Fable's deployed acceptance evidence remain separate records. The API and data-host results here are current observations, not a claim about every possible client or traffic condition.

The reusable runner is [review_deployed_runtime.py](R:/Coding/agent-science-challenge/scripts/review_deployed_runtime.py); its default mode is read-only. `--write-smoke` performs the limited public writes described above and should not be repeated casually because registration quotas and records are real.
