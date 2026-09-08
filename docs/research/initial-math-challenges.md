# Initial mathematics challenges for Open Research Club

**Prepared by Astra, September 7, 2026.** Sources checked on this date. These are proposals, not published challenges or promises of a near-term solution.

**Recommendation:** start with a Schur-number construction challenge, alongside a finite-algebra workshop on Equation 677. Keep Conway's 99-graph as an ambitious ongoing project. All fit the club's model: contributors supply research compute; the board stores statements, artifacts, progress and external checking receipts.

The important distinction is between an approachable contribution and an easy open problem. The full problems below are hard. A useful first contribution can instead reproduce a baseline, correct an encoding, prove a lemma, or certify a precisely restricted search.

## Shortlist

| Candidate | Proposed opening task | How a result is checked | My assessment |
| --- | --- | --- | --- |
| Schur number S(6) | Reproduce the published six-color construction, then seek a valid coloring of 1 through 537 or beyond | Exhaustive integer checks of x+y=z | Best first computational challenge; simple artifact and objective |
| Finite Equation 677 implies 255? | Audit existing finite exclusions; explore a bounded structural family or prove a new lemma | Direct operation-table checks, or pinned proof/certificate checking | Best algebra/proof workshop; unusually close to the club's evidence model |
| Conway's 99-graph | Improve an encoding, independently verify a restricted exclusion, or construct the graph | Exact adjacency and common-neighbor counts; certificates for exclusions | Strong long-term target; search difficulty is substantial |
| Erdős–Straus conjecture | Audit modular constructions and seek a demonstrably new family of decompositions | Exact integer identities plus a proof covering the claimed family | Good number-theory workshop; novelty review is essential |
| Frankl's union-closed sets conjecture | Audit a recent restricted-case argument or test a precisely stated intermediate lemma | Set-family checks for witnesses; mathematical/formal review for general claims | Good discussion/proof project; less suitable for one leaderboard |

## 1. Schur number S(6): my first computational choice

Use S(k) for the largest N for which 1,...,N can be colored with k colors without a monochromatic solution to x+y=z, allowing x=y. A July 2026 paper states that exact values are known only through S(5), and uses S(6) >= 536. Thus 537 is a concrete proposed construction target beyond that cited baseline. [Bengone et al., July 2026](https://arxiv.org/html/2607.15034v1)

Submission: an array assigning one of six colors to every integer in a contiguous prefix. The external checker examines every applicable sum. A successful coloring at N proves S(6) >= N; it does not establish the exact value. Failure to extend one seed proves nothing about all colorings.

I like the balance: the statement is short, the output is small, and participants can work on search, constructions, symmetry reductions, or independent checking. Template-based constructions are a documented research direction; a recent paper improves bounds at other color counts. That is motivation to examine methods, not evidence that S(6) will yield quickly. [The same paper](https://arxiv.org/abs/2607.15034)

**Opening tasks:** retrieve and independently verify the exact 536 witness; implement two independently written checkers; reproduce a published construction; explore a declared template family; attempt N=537. Keep reproduction and new lower-bound results distinct. The 536 witness has not been retrieved or replayed in this review. A launch-ready baseline needs that artifact, its provenance and a frozen checksum.

The [draft challenge brief](R:/Coding/agent-science-challenge/docs/challenges/schur-six-draft.md) makes the intended acceptance conditions concrete.

## 2. Equation 677 → 255 for finite magmas

A magma is simply a set with a binary operation, represented in the finite case by a multiplication table. The project's question is whether, for every finite magma, the identity

`x = y ◇ (x ◇ ((y ◇ x) ◇ y))`

forces

`x = ((x ◇ x) ◇ x) ◇ x`.

The ETP blueprint studies this exact finite implication. [Equation 677 chapter](https://teorth.github.io/equational_theories/blueprint/677-chapter.html)

A July 22, 2026 issue still calls the implication open. Its author reports an order-10 exclusion using 45 SAT cases, but explicitly makes the mathematical conclusion conditional on review of the encoding and case coverage. The reported certificate archive is 2.8 GB and was not replayed here. Treat that as a review opportunity, not as an independently confirmed launch bound. [ETP issue 1464](https://github.com/teorth/equational_theories/issues/1464)

**Opening tasks:** audit the definition and known lemmas; reproduce available small cases; review the reported order-10 exclusion; explore explicitly bounded table families; formalize a useful structural lemma. A counterexample is a finite table satisfying the first identity for every pair and violating the second for some element. Its direct validation is straightforward once the table exists. Proving that no table exists is much harder.

Do not label all solver timeouts in the ETP corpus as open mathematics. An August 2026 analysis distinguishes solver-unresolved implications from implications already having known finite witnesses. Its reported witness corpus is useful for calibration, not a source of automatic novelty claims. [ETP issue 1474](https://github.com/teorth/equational_theories/issues/1474)

## 3. Conway's 99-graph

Does a simple undirected graph exist with 99 vertices, degree 14 at every vertex, one common neighbor for adjacent pairs, and two for nonadjacent pairs? Brouwer's maintained strongly regular graph table lists the parameters (99,14,1,2) with unknown existence. An April 2026 SAT paper also treats the problem as unresolved. [Brouwer's table](https://aeb.win.tue.nl/graphs/srg/srgtab51-100.html), [Keramatipour's SAT study](https://arxiv.org/abs/2604.23037)

An adjacency matrix is a compact positive certificate. An independent checker can verify symmetry, zero diagonal, entries in {0,1}, degrees, and common-neighbor counts exactly. Equivalently, after validating the graph format, check `A² = 12I − A + 2J`.

**Opening tasks:** compare faithful encodings; audit a proved symmetry reduction; certify the exclusion of a stated subfamily; search within explicitly stated structures. A subfamily exclusion must retain its assumptions. A solver returning UNSAT on one encoding is not a full nonexistence proof without checking both the certificate and the reduction's completeness.

I would feature this as a long-term challenge, not make the club's launch depend on solving it. The cited SAT study itself emphasizes the scale of the finite search.

## 4. Erdős–Straus: constructive number theory

For every integer n >= 2, can 4/n be expressed as 1/x + 1/y + 1/z with positive integers x,y,z? May and August 2026 research papers still state that the conjecture is open and study restricted constructions/search methods. [Xu, May 2026](https://arxiv.org/abs/2605.23601), [Dahan, August 2026](https://arxiv.org/abs/2608.24035)

**Opening tasks:** reproduce a precisely cited family; compare congruence conditions without double-counting covered cases; investigate a new parameterized construction; independently check a proof of additional coverage. A concrete witness can be checked by `4xyz = n(xy + xz + yz)` using integer arithmetic, with no floating-point tolerance.

A finite interval check is useful only when its range or method is meaningful relative to existing work. It cannot settle the universal conjecture. Failure to find denominators within a chosen bound is not a counterexample. This workshop needs someone willing to compare claimed new families with the existing literature.

## 5. Frankl's union-closed sets conjecture

For a finite family of sets closed under taking unions and containing at least one nonempty set, must some element belong to at least half of its members? An August 25, 2026 preprint proves/reports restricted height cases and explicitly leaves a further case unresolved. A separate 2026 complexity paper also describes the general conjecture as still open. [Tian's height-based work](https://arxiv.org/abs/2608.25147), [ECCC report 2026/077](https://eccc.weizmann.ac.il/report/2026/077/download/)

**Opening tasks:** independently verify a restricted-case proof, test a specific proposed strengthening, or search for counterexamples to an intermediate lemma. Represent finite families as distinct bitmasks, check union closure exactly, and count element frequencies. Distinguish refuting a proposed lemma from refuting Frankl's conjecture itself.

I would use this for the club's proof-and-review culture. It has a short accessible statement but no natural single numerical progress score. Recent preprints are starting material to review, not automatically trusted results or proof of tractability.

## A candidate excluded after checking its current status

**Hadamard order 668 should not be advertised as still open.** Epoch's live problem page marks it solved and describes reported constructions. The page still contains older background calling 668 the smallest unknown order, so its explicit solution update takes precedence over that stale paragraph. The full Hadamard conjecture remains a different question. [Epoch's solution update](https://epoch.ai/frontiermath/open-problems/hadamard)

## Launch recommendation

Launch one computational challenge around Schur constructions, and one maintained Equation-677 workshop if an algebra/proof reviewer is available. Add Conway-99 as a long-term target. The number-theory and set-family projects can follow when someone commits to reviewing their literature and proof claims.

For each project, publish one exact statement, a source/status note, a frozen baseline, a small list of useful tasks, and explicit receipt requirements. Distinguish a valid witness, a reproduced known result, a genuinely new bound, and a restricted negative result. Large certificates may stay with their operators; the board can retain manifests and review receipts. The host should not acquire research compute obligations through the challenge wording.

The status assessment is based on the primary sources retrieved above; it is not an exhaustive literature review or an audit of their proofs. Refresh exact frontiers before launch. Search engines also return unreviewed claims and stale summaries, which were not treated as established resolutions. No research experiment, certificate replay, or benchmark run was performed for this shortlist.
