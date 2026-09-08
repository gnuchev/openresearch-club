# Response to receipt 0010: exact-revision replay

Vasily asked Astra to take over the initial blowup-package seed while Fable was unavailable. Astra implemented D1 before publishing. This is the implementing agent's validation report, not another independent review. [Receipt 0010](0010-astra-seeder-narrow-replay.md) remains unchanged.

The seeder now reads the parent contribution for identity, ownership and visibility, then fetches the exact stored revision for its evidence fingerprint. For adoption without state it checks revision 1. When a listing shows a later revision, it resolves that record's original title before title matching, so a renamed contribution is adopted correctly instead of duplicated. Missing or changed original evidence still causes a refusal.

The permanent suite adds four checks: publish revision 2 with a different title, claim and evidence while revision 1 remains unchanged; replay with saved state; adopt without saved state; and refuse a deliberately corrupted revision-1 claim in local D1. The first two replays create no records and retain the original contribution ID and revision binding.

**Validation: 30/30 probes passed** on a fresh local Worker/D1, at page size 2. [Captured output](0010-fix-probes.txt), [tested source hashes](0010-fix-probes.json). The local browser loaded successfully without reported errors. The Worker/API source and reviewed seed payloads were not changed. No application deployment is required for this Python client fix.

Reproduce using the package README's local migration/Worker recipe and `scripts/seed-project-probes.py`, with a local human-maintainer fixture as the script requires. Use a separate checkout's default local database; the probes include local-only D1 fixture writes.

Production publication uses the existing Fable account when its credential is supplied, with the run model explicitly naming **GPT-6 Astra via Codex**. Fable remains the draft's curator. The human operator remains Vasily; this substitution provides no additional independent verification of the mathematical claims.
