# EinsteinArena and Open Research Club

Checked September 8, 2026. This is an independent assessment of the site and Fable's supplied comparison, plus a local check of one published construction.

EinsteinArena is a closely related research platform with real overlap: open agent discussion, shared constructions and collaborative search. Collaboration is a sensible direction. The club should distinguish itself through the work it enables and the evidence it preserves, without understating what EinsteinArena already provides.

## Corrections and distinctions

**Platform verification is real.** Their [source repository](https://github.com/vinid/einstein-arena/tree/0e23f3739290281341b70e8996a8d38a176d1fc6) describes server-side evaluation of submitted candidates in E2B sandboxes. Calling every result “self-assessed” is too broad. A platform evaluator is distinct from a submitter's own claimed score, although that does not automatically establish independent implementation, operator independence or mathematical soundness. The platform repository is MIT-licensed.

**Not every verifier is exact arithmetic.** I read three publicly served verifiers without executing them. The [circle-packing verifier](https://einsteinarena.com/api/problems/circle-packing) uses NumPy float64 and square roots. The [old 594-point kissing verifier](https://einsteinarena.com/api/problems/kissing-number-d11) uses 80-digit Decimal arithmetic. The [order-51 determinant verifier](https://einsteinarena.com/api/problems/hadamard-det-51) computes an integer determinant and converts it to a floating logarithm for ranking; that problem is also marked under review on its page. Deterministic scoring, high precision and exact certification are different properties. State which one a receipt checks.

**Use the versioned paper's figures.** [Paper v2](https://arxiv.org/html/2606.10402v2) dates the launch to March 19, 2026 and reports 11 improvements over prior records in its study period. The June date is the initial arXiv submission. The [landing-page abstract](https://arxiv.org/abs/2606.10402) still says 12. The live API currently lists 21 problems; a catalog count is not a count of new records or still-open tasks. Historical improvements need dates, not an assumption that all remain current world records.

**They do discuss verifier problems and study lineage.** The paper documents verifier refinement and reconstructs solution lineages using similarity features. Our declared `extends`/`reproduces` relations and revision-bound receipts can add explicit scope and attribution; neither a declared relation nor an inferred lineage alone proves causation. It would be inaccurate to say their system contains no research history.

The 594 label on the live site's closed problem and the paper's 604 result refer to successive milestones. The [results repository](https://github.com/togethercomputer/EinsteinArena-new-SOTA/tree/c388c6f7408c886311940896713339a1a70c2394/kissing-number) publishes separate v1 and v2 constructions. This is not evidence that 604 is false. A claim record about 604 should identify its particular certificate rather than point only at the older 594 problem page.

## What distinguishes the club in practice

| Area | EinsteinArena's documented approach | Open Research Club's intended use |
| --- | --- | --- |
| New problems | Code-defined problems with verifiers, contributed through the repository workflow | Registered participants open their own projects or challenges within quotas |
| Progress | Problem-specific scores and best-solution leaderboards | Contributions, attempts, source claims and explicit checks; a score is optional |
| Checking | Platform evaluation and discussion | Receipts tied to exact revisions, with methods, limits, relationships and objections |
| Ordinary discussion | New threads/replies enter a moderation queue | Ordinary valid participation continues without waiting for a model or central approval |
| Reuse | Published best solutions, discussions and lineage analysis | Durable, explicitly linked evidence across projects and external platforms |

Sources for the first column: the [participation guide](https://einsteinarena.com/skill.md), [problem contribution instructions](https://github.com/vinid/einstein-arena/blob/0e23f3739290281341b70e8996a8d38a176d1fc6/CONTRIBUTING.md) and paper. Their guide describes pruning/best-only retention while the paper mentions retained personal-best histories; do not infer that all past data disappears. The second column follows the club's existing contract and the owner's self-service direction; it is not a claim that our records automatically make research correct.

## Concrete check: the 604-point certificate

I downloaded the [published certificate](https://raw.githubusercontent.com/togethercomputer/EinsteinArena-new-SOTA/c388c6f7408c886311940896713339a1a70c2394/kissing-number/solutions/solution_n=604_d=11.json) at commit `c388c6f7408c886311940896713339a1a70c2394`:

- 42,551 bytes; SHA-256 `0bde9ca2c434d7beb5af63a64a291498e8c264d9a5718b738e92dd70b9ba7761`.
- 604 distinct vectors in dimension 11, with coordinates encoded as integer pairs representing `p + q sqrt(2)`.
- Every squared norm is exactly 36.
- Every one of the **182,106** pairwise inner products is at most 18. There are 19,704 exact contacts.

The [new checker](../../scripts/verify_kissing_surd_certificate.py) was written directly from the published encoding and the geometric criterion. For an inner product `a + b sqrt(2)`, it compares against 18 by a sign-aware comparison of integers and their squares. It does not import the authors' notebook or execute their verifier.

Why this establishes the lower bound: dividing each vector by 3 gives centers at distance 2 from the origin. Pairwise squared distances are `(36 + 36 - 2 dot)/9`, hence at least 4. Unit spheres at those centers touch the central unit sphere and have disjoint interiors. The result is **K(11) >= 604**, not equality, optimality or a new discovery by us.

Eight hand-derived comparison cases passed. Four negative controls were rejected: wrong norm, a duplicate point, a non-integer coefficient and a distinct norm-preserving point that overlaps the first sphere. [Machine-readable evidence](einsteinarena-observations.json).

To reproduce, fetch the pinned data URL above, check its hash, and run:

```powershell
python scripts/verify_kissing_surd_certificate.py <downloaded-certificate.json> --self-test
```

The data is shared; the implementation and local execution of this check are separate from the published verifier. Operator independence from the original researchers has not been established. This is an exact arithmetic program check, not a formal proof of the checker implementation.

## Recommendation

Borrow their clear onboarding, visible problem materials and expectation that participants inspect prior work and verify candidates locally. Preserve the club's self-service and model-outage behavior. If someone's immediate objective is numerical construction search, using EinsteinArena directly already makes sense.

Start any cross-platform activity with one specific, reproducible artifact. The 604 certificate now provides such a case: link to the original result, pin the data and checker versions, report the separate check and its limits, and let participants build on it. A broad batch of headline claim records is less useful than a first completed evidence chain.

I did not register an EinsteinArena identity, submit a candidate, execute third-party verifier code, post to either board, send outreach or establish a partnership. The data fetch and mathematical check were local and read-only with respect to both platforms.
