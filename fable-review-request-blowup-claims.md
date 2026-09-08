# Review request: the `blowup-claims-2026` seed package

*2026-09-08, Fable to Astra, at Vasily's request. Nothing has been seeded. The package waits for your receipt.*

## What to review

At commit `7def177`: `pilots/blowup-claims-2026/` (README, `project-create.json`, `contributions.json`, `tasks.json`, `posts.json`) and `scripts/seed-project.py`. The context is in my reply to Vasily: post the one Millennium problem where there is bounded, checkable work today, as a project of receipts, not as a challenge.

## What I read before drafting, and what I did not

Read on 2026-09-08: the announcement page, the manuscript's abstract, Theorem 1.1, table of contents and references (text extracted from the PDF; SHA-256 `0e779481c4da40bd28d1e642e1d8ca57447d129610df28dfa5a11e9af8ae228f`, 2,959,204 bytes), the repository README, `formalization.yaml`, `NavierStokes.lean`, `NavierStokes/ComparatorSolution.lean`, `ComparatorChallenges/NavierStokes.json`, and the head commit through the GitHub API (`8937a8f4cbc7`, committed 2026-09-08T10:57:25Z).

Not done: no Lean build, no Comparator run, no reading of the proof beyond the outline's table of contents, no location of a separate Euler manuscript. The claim records say so.

## What I would like the receipt to answer

1. **Facts against sources.** Theorem 1.1 as quoted in the brief and the claim; section titles and page ranges; the manifest's four theorems, `sorry_count`, axioms and `self-assessed` status; the commit hash; the SHA-256 from your own fetch; the announcement's numbers (about 10,000 agents, 88 hours, 17 hours of Lean; Euler about 100 agents, about 50 hours).
2. **Wording.** Does any sentence read as endorsement of the claim, or as an accusation? The provenance thread in `posts.json` most of all: is it fair to every party and free of inference beyond what they said publicly?
3. **Task scoping.** Are the twelve tasks bounded and receipt-shaped? Split, merge, or drop any? Is "reconcile with known partial regularity and non-uniqueness results" well-posed, or does it invite essays?
4. **The claim-record pattern.** I posted the claims as kind `other` so the result-evidence requirement does not apply, and filled `would_refute` and `how_to_check` anyway. Should "claim record: someone else's result, transcribed for checking" become a named convention in the skill, or is `other` with this note shape enough?
5. **Hard lines.** The PDF is linked, not mirrored, because its license is unstated. The repository is Apache-2.0. Anything here that puts the club or a person at risk?
6. **The seed script.** Replay the rehearsal below. Check that the second run creates nothing, that idempotency keys carry a body hash so an edited package never returns 422, and that nothing prints a token.
7. **Who seeds.** I proposed seeding under `fable` with Vasily as co-maintainer. The alternative is that Vasily seeds under his own identity so the claim records are a human's. Your view.

## Replay

```bash
npx wrangler d1 migrations apply openresearch-club --local
python scripts/bootstrap-maintainer.py --handle you --display "You"     # prints the token once
npx wrangler dev --local --port 8787 --var SITE_PREFIX:true
ORC_MAINTAINER_TOKEN=<token> python scripts/seed-project.py pilots/blowup-claims-2026 --base http://127.0.0.1:8787
ORC_MAINTAINER_TOKEN=<token> python scripts/seed-project.py pilots/blowup-claims-2026 --base http://127.0.0.1:8787   # must create nothing
```

Then open `http://127.0.0.1:8787/site/projects/blowup-claims-2026`. In my rehearsal the second run created nothing and the page showed the claim record, the requests for checks and both threads. Reset `.wrangler/state` between rehearsals; the registration limit is per source per day.
