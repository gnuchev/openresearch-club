# Blowup claims for Navier–Stokes and Euler (September 2026): seed package

A ready-to-seed Open Research Club project for checking OpenAI's 2026-09-08 claim to have settled alternatives (C) and (D) of the Clay Navier–Stokes problem, and the unforced Euler blowup in the same repository. The project is a *project*, not a *challenge*: there is no evaluation contract, because there is no checker for a 166-page proof. The work is receipts.

Drafted by Fable on 2026-09-08 at Vasily's request. Not yet seeded: it waits for Astra's review (see `fable-review-request-blowup-claims.md` at the repository root).

## What is in the package

| File | Seeds |
| --- | --- |
| `project-create.json` | The project: slug `blowup-claims-2026`, kind `project`, brief with what is known, disputed, failed, next, and house rules. |
| `contributions.json` | Two claim records, kind `other`: the Navier–Stokes Theorem 1.1 and the unforced Euler result, each with `would_refute`, `how_to_check`, and external artifacts (manuscript with SHA-256, repository at the head commit). |
| `tasks.json` | Twelve opening tasks: two Lean builds, the Comparator run, the statement-faithfulness review, five reading receipts covering every section and appendix, a reconciliation with known theorems, a non-specialist explanation, and a curated public record. Ten are requests for checks targeting a claim record. |
| `posts.json` | Two discussion threads: one for provenance, priority and conduct, so they stay out of receipts; one for the dated list of public responses. |

## What was verified before drafting, and how

On 2026-09-08 Fable fetched and read: the announcement page (text supplied by Vasily), the manuscript's abstract, Theorem 1.1, table of contents and references (text extracted from the PDF; SHA-256 `0e779481c4da40bd28d1e642e1d8ca57447d129610df28dfa5a11e9af8ae228f`, 2,959,204 bytes), the repository README, `formalization.yaml`, `NavierStokes.lean`, `NavierStokes/ComparatorSolution.lean` and `ComparatorChallenges/NavierStokes.json`, and the repository's head commit through the GitHub API (`8937a8f4cbc7`, committed 2026-09-08T10:57:25Z). Nothing was built or checked; the claim records say so.

## Seeding

```bash
ORC_MAINTAINER_TOKEN=... python scripts/seed-project.py pilots/blowup-claims-2026 --co-maintainer <vasily-id>
```

The script is idempotent: a second run finds the project, the contributions, the tasks and the posts by slug and title and creates only what is missing. Add `--base http://127.0.0.1:8787` to rehearse against a local Worker.

## After seeding

The first receipt should be the Lean build by someone other than the seeding maintainer. The claim records are by the seeding maintainer, who is not an author of the work; a receipt on them is a check of the artifacts, never an endorsement of the claim.
