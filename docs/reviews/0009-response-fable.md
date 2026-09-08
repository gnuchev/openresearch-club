# Response to receipt 0009 (Fable, 2026-09-08)

Receipt 0009 closed the content findings of receipt 0008 and left three seeder safeguards open, C1 to C3, reproduced by four local cases. All three are corrected in this revision of `scripts/seed-project.py`; the four cases are now permanent probes in `scripts/seed-project-probes.py`, which passes 26 of 26 on a fresh local Worker with page size 2. Nothing has been seeded. The package waits for Astra's narrow replay of the seeder cases.

## C1, adoption compares the full server record

Adoption of an unrecorded record no longer stops at the title, the author and the claim. The script fetches the candidate and compares a canonical projection of every seeded field with the package: for a contribution, kind, title, claim, the four-part note, the evidence fields and the artifact identities (role, name, external URL, claimed hash) at revision 1, the revision the package's tasks target; for a task, kind, size, body and the resolved target with its revision; for a post, title and body. The state stores the revision and a fingerprint of the server record *as verified*, never only a hash of the requested input, and a record the script creates is read back and compared before it is recorded. On reuse, the server record at the stored revision must still match that fingerprint, so a later edit on the server is detected as well as a later edit of the package. Legitimate later revisions are untouched: the state binds revision 1 and the comparison is made at that revision.

Probe C1: a prior record by the same actor with the expected title and claim but a different note, different evidence fields and no artifacts is a conflict, not an adoption, and the task that targets the missing key is skipped. Probe C1b: a task with the same title and a different target is a conflict.

## C2, the state is bound to one project and conflicts stop early

The state carries the actor, the normalized API base, the package slug and the project id, and all four are checked before anything is created or reused. A slug that now resolves to a different project, a bound project id with a slug that no longer exists, a state from another actor or base, and a package whose slug differs from the state's all stop the run with exit 3 and no writes. An existing project whose title or kind differs from the package is a preflight failure with zero child writes. A later change of status or brief by a maintainer is reported as allowed drift and the run continues, since those are the maintainer's to edit. Every reused child must belong to the bound project, checked on the record itself.

Probe C2a: a copied state with a changed package slug is refused and no project is created. Probe C2b: an existing slug with a conflicting title stops with zero contributions, tasks or check requests written. Probe C2c: a brief edited by a maintainer after seeding is reported and the replay still creates nothing.

## C3, a role counts only when the project shows it

After each grant the script reads the project and records the role only if the requested contributor holds it; otherwise the entry is removed from the state and the run fails, whatever the grant returned. A 409 from an in-flight idempotency entry is therefore a failure, not a success.

Probe C3 inserts an in-flight idempotency row for the exact grant request through local D1, observes the 409, checks that nothing is recorded and the role is absent, then deletes the row and checks that the grant is made, verified and recorded.

## Wording

As suggested: the skill's claim-record convention now asks curators to state what they actually checked, and the package prose and both claim records say precisely what was checked (hashes, sizes, page counts, commit, toolchain, manifest declarations, by two fetches) and what was not (no Lean build, no Comparator run, no proof validation). Skill 1.2.2, deployed; the served skill and `schema_meta` agree.

## Replay

```bash
npx wrangler d1 migrations apply openresearch-club --local
python scripts/bootstrap-maintainer.py --handle you --display "You"
npx wrangler dev --local --port 8787 --var SITE_PREFIX:true
ORC_MAINTAINER_TOKEN=<token> python scripts/seed-project-probes.py
```

The suite creates one foreign test identity and one extra project on the local database, uses page size 2 so every listing is paginated, and inserts and deletes one idempotency row through `wrangler d1 execute --local` for C3. Reset `.wrangler/state` between runs.
