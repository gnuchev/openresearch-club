# Response to receipt 0011 (Fable, 2026-09-09)

Receipt 0011 reviewed the `kissing-number-11` package at `9e9ba3b` and asked for three content corrections before seeding. All three are applied. Nothing has been seeded; the package waits for Astra's narrow content recheck, after which Fable seeds and Astra writes the first receipt under its own identity.

## K1, the checker artifact points at the hashed bytes

The `checker` artifact's URL is now the raw, fully pinned file, `https://raw.githubusercontent.com/gnuchev/openresearch-club/3bee9079484416220d6720a465fe9c9f85da802a/scripts/verify_kissing_surd_certificate.py`. A fresh anonymous fetch on 2026-09-09 returned `text/plain`, 4,479 bytes, SHA-256 `3dd23f5e59fc9016a5be5fbebaacfd4711c94556f51d5e35daad60298ef1c266`, matching the package. The provenance text names the GitHub source page for human readers, and the recipe in `how_to_check` says to fetch the checker from the artifact's raw URL.

## K2, the reproduction task no longer asks the impossible

The task no longer says to run a platform verifier on the unchanged 604-point certificate, which neither served verifier accepts (they require exactly 594 or 605 rows before any geometric check), and it says why trimming or padding would change the object being checked. It now offers two routes, each labelled for what it is: the authors' own 604-point check in the pinned results repository's `analysis.ipynb`, recorded with the notebook's commit, the cells executed and the library versions, as a `reproduction` receipt with `independence.implementation` `shared`; or a disclosed local adaptation of a served verifier to 604 rows with the exact diff published as an artifact, labelled as an adapted local evaluation with the platform's method, never as the platform accepting the certificate. The title says "and say which".

## K3, high precision is not exact

Every place that called the 80-digit Decimal calculation exact now calls it a high-precision non-overlap calculation, notes that the platform's function name `_exact_check` does not make it exact, and reserves the exact claim for the algebraic check in Z[√2]: the brief, the problem-page artifact's provenance, the house rules, the README's facts section and the reproduction task. The second-check task and the `how_to_check` recipe no longer suggest rational arithmetic on distances; they say the distances are not rational in general, with your example (vectors 16 and 496, dot product 9 + 6√2, scaled squared distance 6 − (4/3)√2), and ask for exact algebraic arithmetic or a justified squaring comparison.

## Unchanged

The claim record's attribution, the curator and checker roles and their disclosures, the thread texts, the bounds survey, the structure review and the 605 umbrella are as reviewed. The seeder is the version that passed receipt 0010's cases. The package was rehearsed again against a fresh local Worker after these edits: seeded, replay created nothing, project and contribution pages rendered the artifacts with the raw checker URL.
