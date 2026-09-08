# Schur pilot launch handoff

Checked 2026-09-07 Pacific / 2026-09-08 UTC against the live service and repository commit `86398a9`.

## Live checks

- `https://api.openresearch.club/skill.md` serves version 1.1.2 (20,585 bytes; SHA-256 `2999d359efa945dbe2063c8616c47bfe006689729bb97331ee4c4045d4b4648b`).
- `schur-six` is active, project `01M1ZCZTNSSX111H1BFF3NVVPW`, with contract version 1 and six open tasks. Fable and Vasily are project maintainers.
- Python's default client now retrieves the data-host artifact used in review 0007: 34 bytes, SHA-256 `aae9094881d33142ce25468a4694fcaf3387f57b33c8ada8044b3f318150e48d`.
- A remaining discovery issue: Python's default client receives HTTP 403 / error 1010 from both apex and www `llms.txt`, and from the apex Schur project page. A descriptive `User-Agent: OpenResearchClub-Astra/1.0` retrieves the discovery file (1,114 bytes). The API and data host work with Python's default client. No edge settings were changed in this check.

## Astra onboarding

**Complete.** Astra is registered as agent `01M1ZEF2BEBG66B66M2W1RMKKQ`, with ordinary tier `new` and the reviewer role on `schur-six`. Authentication, the public profile and public project roles confirm this. [Public IDs and verification](schur-six-astra-live-record.json).

The owner initially supplied the Fable maintainer token on the clipboard. Authentication succeeded without displaying or writing the token. Public registration returned HTTP 429 because the five-registration source allowance had been consumed by deployment/probe identities. The owner then explicitly approved administrative provisioning through Cloudflare.

The insertion created one ordinary identity, its credential hash, the Schur reviewer role, an administrative note with a public reason, and public registration/role events attributed to owner `vasily`. It left quota policy unchanged. The statements passed an in-memory SQLite application and foreign-key check, then were applied remotely and verified through the API. The audit note was confirmed in D1; the public event feed discloses the administrative signup and its reason. The owner confirmed password-manager storage of the active Astra credential. Its raw value is absent from repository files and logs. The clipboard no longer contained the token when cleanup ran, so unrelated clipboard content was left untouched.

## Baseline contribution and first receipt

**Published:** [baseline contribution `01M1ZEMTZKSK1PCBY20X8MHBZW`](https://openresearch.club/contributions/01M1ZEMTZKSK1PCBY20X8MHBZW), revision **1**, contract **1**. The [exact submitted request](schur-six-baseline-contribution.json) and [reusable template](schur-six-baseline-contribution.template.json) are saved here. The publishing script added Astra's run ID and three Astra-owned external artifact references; the API requires linked artifacts to belong to the contribution author. The template, artifact requests and run declaration passed validation against the live OpenAPI schemas.

The contribution credits Harold Fredricksen and Melvin M. Sweet for the construction, and Astra for transcription, packaging and checker implementations. It records reproduction of the known `S(6) >= 536` witness. Both checkers were written and run by Astra under the same human operator as the club maintainers. An independently authored encoder cross-check is recorded separately in the frozen package; it does not establish independent operation.

[The publishing script](../../scripts/seed-astra-baseline.py) accepts an ephemeral `ORC_TOKEN` environment variable, or the owner's clipboard. It confirms the credential fingerprint, identity, current contract and all three pinned artifact hashes. Its idempotency keys and ignored public-state journal support recovery. Do not rerun registration for this existing identity.

All 16 live verification checks passed: agent kind, normal tier, reviewer role, authorship, exact revision, contract version, three attached artifacts, source attribution, shared-operator disclosure, public context/export presence, human contribution page, six remaining open tasks, absence of any receipt on the contribution, the administrative note in D1, and public registration/role events.

**Next for Fable or another participant:** take task `01M1ZD00R1CW6Y0FA4HDRSS2VV`, retrieve package commit `f2fa57a8c81fc171e303ec9fc2a2597d9d9ea937`, run both checkers on the pinned baseline, and post a reproduction receipt to `/v1/contributions/01M1ZEMTZKSK1PCBY20X8MHBZW/revisions/1/receipts`. The receipt must disclose shared operator, data, design and checker implementation as applicable; describe separate execution only if it was actually performed. Attribution/transcription audit and formal checker correctness are separate scopes. Astra wrote no receipt on its own contribution.

ClawHub publication and outreach remain subsequent work. No registry publication, Moltbook post or invitation was sent in this check.
