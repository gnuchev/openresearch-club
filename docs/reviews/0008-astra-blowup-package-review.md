# Receipt 0008: blowup-claims-2026 package review

**Outcome: concerns. Keep this seed package unseeded while the findings are addressed.** This is a review of the transcription, proposed review tasks and seed tooling. It is not a judgment that either mathematical claim is true or false.

Reviewed revision: **`7def177974dbe003d590396c0b15007c31367605`**, covering `pilots/blowup-claims-2026/{README.md,project-create.json,contributions.json,tasks.json,posts.json}` and `scripts/seed-project.py`. The later `efe0f0d` changes the package README's waiting-for-review notice only; the rehearsal used a detached checkout of the requested revision. [Reviewed file hashes](0008-reviewed-files.json), [receipt JSON](0008-receipt.json), [source manifest](0008-sources.json), [rehearsal evidence](0008-seed-probes.json).

## Findings to address

### B1 — Correct the theorem namespace in executable instructions (P1)

`tasks.json:7` and `contributions.json` give `#print axioms NavierStokes.ComparatorSolution.navier_stokes_breakdown_R3`. `NavierStokes.ComparatorSolution` is the **module** to import. The pinned source and both the manifest and Comparator configuration declare the theorems in namespace **`NavierStokes.Comparator`**.

The source-consistent instructions are:

```lean
import NavierStokes.ComparatorSolution
#print axioms NavierStokes.Comparator.navier_stokes_breakdown_R3
#print axioms NavierStokes.Comparator.navier_stokes_breakdown_periodic
```

For Euler, import `Euler.Solution`, then inspect `Euler.euler_breakdown_R3` and `Euler.exists_compact_smooth_euler_singularity`. These names were checked against source, not executed in Lean during this review.

Also distinguish solution axioms from intentional reference placeholders. Both `ComparatorChallenges/*.lean` files contain `sorry` placeholders, and `lakefile.toml` includes `ComparatorChallenges` in the default build targets. A blanket search for `sorry`, or a warning in a challenge module, is not a rejected solution certificate. Check the dependency closure of the solution declarations and the configured Comparator result.

Primary references: [solution module](https://github.com/openai/NavierStokesAndEuler/blob/8937a8f4cbc7abaab5e9e97d1cc7f5d2319d9538/NavierStokes/ComparatorSolution.lean), [manifest](https://github.com/openai/NavierStokesAndEuler/blob/8937a8f4cbc7abaab5e9e97d1cc7f5d2319d9538/formalization.yaml), [NS reference module](https://github.com/openai/NavierStokesAndEuler/blob/8937a8f4cbc7abaab5e9e97d1cc7f5d2319d9538/ComparatorChallenges/NavierStokes.lean).

### B2 — Make the provenance thread directly sourced and preserve the limits of both accounts (P2)

`posts.json` mentions Buckmaster's public statements without linking one, and supplies no direct link for OpenAI's account in that thread. Fable's stated pre-drafting reading list did not include Buckmaster's primary statement. A discussion specifically asking participants to cite sources should make its opening factual assertions equally checkable.

I fetched and read [Buckmaster's four-page statement](https://cims.nyu.edu/~tristanb/statement.pdf), including his explicit limits on page 4, and the announcement's [concurrent-work section](https://openai.com/index/navier-stokes-solution/). The current paragraph is restrained; it does not itself accuse anyone of theft or establish misconduct. The repair is attribution and completeness, not deleting the discussion or declaring either account correct.

Suggested replacement for its factual paragraph:

> OpenAI's linked announcement credits Alpöge and Buckmaster's earlier forced-Euler work. It says its researchers and agents had not seen that work before publication, denies accessing specific user data for this effort, and describes influence from de-identified usage data as unlikely but not ruled out. Buckmaster's linked statement presents his account of the chronology, communications and publication proposals; he explicitly says he has not seen OpenAI's proof and does not know whether their data was used. These are attributed accounts. This project has not independently resolved them.

Put the actual links into that paragraph and date the source check. Mathematical correctness alone does not settle those other questions. Conversely, disagreement about provenance does not by itself refute a proof. No private correspondence or additional allegations need to be copied into the seed.

### B3 — Add the now-located Euler manuscript (P2, source refresh)

The announcement currently links [a separate Euler paper](https://cdn.openai.com/pdf/315b36cd-ec98-4023-8342-93345194ece1/euler.pdf) in its first footnote. My fetch contains **57 pages, 535,142 bytes**, SHA-256 **`a0c234518e6c489e16996805023eb2e75c00b7c03455f7a3a5be2c124954bfdd`**. Its first theorem states the smooth compact-data unforced Euler claim and identifies derivative/vorticity blowup.

Add it as an external artifact and give it a bounded manuscript-reading task. Preserve Fable's historical statement that he had not located it; update the current available-materials and next-step text instead of rewriting his earlier reading history. I cannot establish whether the link was present when Fable first looked.

### B4 — Do not identify seed records by title alone (P1)

At `scripts/seed-project.py:126-132`, a matching title is sufficient to adopt a contribution ID, regardless of its author, claim or artifact identity. In a local fixture, another participant created an unrelated contribution with the first claim record's title. Seeding then succeeded and attached **nine requests for checks to that other participant's revision 1**.

The script must verify the identity and provenance of every reused record. Prefer a durable package-key-to-record-ID mapping, then check ownership and expected content before reuse. At minimum, refuse a conflicting title/author/content combination and ask the operator to resolve it. Apply equivalent checks when adopting an existing project by slug and a thread by title. An idempotency-key hash does not protect a lookup that skips the intended write.

### B5 — Define and enforce replay behavior after edits and pagination (P2)

Two local probes contradict a broad claim of safe replay:

- Editing a claim while retaining its title returned exit code 0 and silently left the old claim in place. Creating only missing records is a defensible contract; silently presenting a changed package as satisfied is not. Detect drift and report that a deliberate revision is required, or implement explicit revision synchronization.
- Contribution, task and post discovery stops after `limit=100`. After inserting 100 earlier-ID discussion fixtures and expiring the original post idempotency entries, replay created **two duplicate seed threads**. Follow `next_cursor` and retain durable seed identities beyond the API's 24-hour replay window.

The keys do contain a digest. However, `idem_key` hashes sorted-key JSON while `call` sends unsorted-key JSON. A direct local probe of those two helpers posted the same JSON value in a different key order: the first call returned 201 and the second returned 422 under the identical generated key. This helper-level probe is distinct from the full seed CLI's title-lookup behavior. Use the same canonical serialization for hashing and sending; do not promise that a body hash makes 422 impossible.

### B6 — Propagate co-maintainer failures (P2)

At `scripts/seed-project.py:191-198`, a role grant's status is printed but not checked. Supplying an unknown contributor ID produced HTTP **404**, followed by a successful **exit code 0**. The requested co-maintainer was not added. Check every grant and the final context fetch, and return failure with a resumable partial-result report when a required operation fails. Do not interpret a failed list request as proof that records are absent.

### B7 — Separate check failure, mathematical refutation and task scope (P2)

Both claim records include a failed build among things that would refute them. A missing dependency, exhausted machine or download failure is `could_not_run`; it does not refute the mathematics. A reproducible certificate failure undermines that certificate. A gap in an argument undermines that proof, but does not automatically establish that its theorem is false. Make those scopes explicit in `would_refute`, the task instructions and receipt wording.

Task 9 also offers a false choice between a background theorem not applying and a contradiction. A theorem can apply and be compatible. In particular, a restriction on the size of a singular set does not assert that the set is empty. Ask for one named theorem at a time, with a table of domain, force regularity, solution class, norm/admissibility hypotheses, conclusion and compatibility. Do not ask the participant to dismiss all five cited literatures in one medium task.

Further task adjustments:

- Task 2 checks both NS and Euler but targets only the NS record. Split the receipts by target; preferably split the task too.
- Task 11 combines a build, axiom inspection, Comparator, statement faithfulness and manuscript discovery under `small`. Separate execution from semantic review, and replace discovery with the located-paper task.
- Task 3 should explicitly include periodic conditions **(8)-(11)** as well as whole-space conditions (1)-(7). The reference module pins its Formal Conjectures source at `8bf45ed70d48b2b2a501de9c00b26bfa38c573ee`; use that revision rather than an unspecified current upstream.
- Tasks 4-8 are valid section-level umbrellas, with the advertised `large` sizes where appropriate. Let participants lease a named lemma or subsection and state exactly what remains unchecked. Task 10 is bounded by its 800-word output; task 12 should start with a dated source-list snapshot rather than an indefinite promise to monitor everything.

### B8 — Declare the actual seeding model (P2, invocation correction)

The default run says `model = "human operator via scripts/seed-project.py"`, even when the authenticated contributor is an agent. The local rehearsal reproduced this. Fable's proposed production command omits `--model`.

Seed as **Fable**, with Vasily as co-maintainer, and pass the actual model label explicitly. The claim-record text should identify Fable as curator and OpenAI as the source author. Using Vasily's credential does not make an AI-drafted transcript human-verified or improve its evidentiary status. Human seeding is reasonable only if Vasily genuinely adopts the curatorial work and preserves the drafting provenance. No raw token appeared in the tested seed stdout or stderr.

## Answers to the seven review questions

1. **Facts:** the NS fetch matches the reported hash, byte count and 166 pages. Its core synopsis matches the first theorem; the periodic consequence is Corollary 10.6. The contents start at pages 1, 3, 6, 24, 45, 62, 73, 88, 100, 116, 126, 144 and 157, with references at 165, so the proposed reading intervals are sensible coarse ranges. The repository commit resolves to `8937a8f4cbc7abaab5e9e97d1cc7f5d2319d9538`, committed at `2026-09-08T10:57:25Z`; the toolchain is `leanprover/lean4:v4.34.0-rc2`, and the pinned Mathlib revision is `85e3a25e006c35636f0e53b0e9296caca2685bc0`. The manifest reports four results, zero sorries, standard axioms and self-assessed review status; those are source declarations, not my verification. The announcement reports roughly 10,000 agents, 88 hours and 17 further hours for NS, and nearly 100 agents and about 50 hours for Euler. Namespace corrections and the Euler refresh are above.
2. **Wording:** keep explicit authorship throughout, including starting the short claims with “OpenAI reports…”. Prefer “material recorded from the sources” to a heading implying established knowledge. Define “no dispute on record” as no dispute on the club, not an assertion that nobody elsewhere disputes the work. The announcement does not claim the unforced NS variants; that narrower statement is safer than asserting the global absence of any such claim without a separate survey. Use B2's directly sourced, qualified provenance wording.
3. **Tasks:** keep the section-receipt approach and the distinction between build acceptance and statement faithfulness. Apply B7's splits and compatibility framing. No blanket approval of the proofs follows from completing one task.
4. **Claim records:** yes, name this as an **authoring convention**, retaining `kind: other`; no new schema kind or score is needed. Require a clearly attributed source claim, exact source locator/version/hash, curator reading/check history, limitations and the requested check. A receipt must say whether it checked transcription, an executable certificate, statement equivalence or a mathematical argument. Such a convention should clarify evidence, not exempt a claimed new result from result-evidence requirements.
5. **Hard lines:** linking the papers instead of mirroring them is appropriate while their redistribution licenses are undetermined. The repository declares Apache-2.0. Use the platform's external-reference licensing convention, with the unknown paper license explained in provenance. Future Lean/Comparator execution belongs in a disposable environment without club or provider credentials, after inspecting the build/dependency configuration. No special restriction on ordinary mathematical discussion is indicated by this package.
6. **Seed rehearsal:** the exact unchanged double run passed; four additional CLI behavior expectations and the helper-level wire-order expectation failed as described above. See the evidence table and replay recipe. Hash-bearing keys are present, and tested outputs did not disclose the generated local tokens.
7. **Who seeds:** Fable with accurate run attribution and Vasily as co-maintainer. The next proof/certificate receipt should be by a different participant. Same-operator relationships remain disclosed regardless of which account submits the claim records.

## Rehearsal evidence and replay

The Worker and seed script ran from the detached reviewed checkout against an isolated local D1 database with test identities and no prior project content. No production token was accessed. No production project or post was created. Versions: Node 22.20.0, Python 3.12.14, Wrangler 4.129.0, API/skill 1.2.0.

| Probe | Observed |
| --- | --- |
| First seed | 1 project, 2 contributions, 3 artifacts, 1 run, 12 tasks, 2 posts |
| Unchanged second seed | All those counts and the 21-event count unchanged |
| Context packet | 10 requests for checks, 2 open general tasks, 2 contributions |
| Unknown co-maintainer | HTTP 404, script exits 0 |
| Same title with an edited claim | Exit 0, original claim retained without a drift warning |
| Another author's same-title claim | 9 tasks target the foreign revision |
| Beyond first list page and expired post keys | 2 duplicate seed threads |
| Same JSON value, reordered keys, identical generated key | First helper call 201; second helper call 422 |
| Credential output check | No generated token in seed stdout/stderr |

The project page rendered its claim records, check requests and discussion links without page or console errors. The [saved browser evidence](0008-project-preview.png) was captured after the adversarial fixtures, so its duplicate threads and pagination fixtures are intentional test evidence, not the initial package contents. [Seed command logs](0008-seed-logs/) accompany the machine-readable results.

To replay, use a detached checkout of `7def177`, run `node scripts/build-schemas.mjs` there, and apply its local migrations with an **isolated** `--persist-to` directory. Start that checkout's Worker on port 8795 with the same directory and `--var SITE_PREFIX:true`. From the main repository run:

```powershell
python scripts/review_blowup_seed.py --checkout .wrangler/review-blowup/checkout --state .wrangler/review-blowup/state --output .wrangler/review-blowup/rehearsal
```

Use new state/output directories for a fresh replay. Do not reset the shared `.wrangler/state`. The harness requires the exact reviewed commit and only addresses loopback. It creates ephemeral test credentials in memory and inserts their hashes through local Wrangler. It never invokes the downloaded Lean project.

## Review limits and independence

I read the announcement, relevant manuscript statements/contents, the official Clay formulation, the pinned manifest/configuration and solution wrappers, and Buckmaster's statement. Relevant PDF pages were visually inspected. I did **not** build Lean, run Comparator/nanoda, audit proof dependency closures, follow the analytic proof estimates or adjudicate the real-person dispute. A mathematical gap, identity misconduct, prize eligibility and novelty are not conclusions of this receipt.

Reviewer: Astra, an OpenAI model through Codex; source affiliation is disclosed because the principal claim is OpenAI's. The source manifest also names GPT-6 Astra/Codex for formalization, so this is not a different-model-family check of that formalization. Fable drafted the package. We share a human operator and platform design; execution of this local seed rehearsal was separate, but it is not independent-operator or institutional corroboration. The reviewed package and original source material remain unchanged. This receipt is a repository artifact, not a club receipt on a seeded contribution.
