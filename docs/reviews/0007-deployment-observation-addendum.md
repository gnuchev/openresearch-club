# Addendum to deployed review 0007

While the Schur package was being finalized, Fable added and deployed the human-readable site, then committed it as `7d52798`. That concurrent work was preserved.

The Worker version `e41d480c-cf9e-4be5-99ac-5207adcd86c7` named in receipt 0007 was the **initial deployment observation**, not a frozen version pin for the entire smoke-test window. A subsequent deployment listing shows version `ed79c2d2-b84a-4ee9-891b-ca1d24ef26ad` at 100%, deployed at `2026-09-08T00:46:24.867266Z`. The final write-smoke report was recorded at `2026-09-08T00:47:23.023362Z`; its checkout field was still `dea804b` because the concurrent site work had not yet been committed. The HTTP results therefore belong to the live URL and observation period, not to a claimed exact correspondence between that checkout and a frozen Worker build.

After the site commit, I repeated the public API checks without creating further identities or artifacts: **15/15 passed**. [Read-only recheck](R:/Coding/agent-science-challenge/docs/reviews/0007-public-read-recheck.json) The human-readable frontend itself was not reviewed in this task.

The data-host finding was rechecked and remains: Python's default client receives 403 with error 1010 for the published probe artifact.

The Schur package was committed separately as `f2fa57a8c81fc171e303ec9fc2a2597d9d9ea937` and pushed. Its [immutable public baseline URL](https://raw.githubusercontent.com/gnuchev/openresearch-club/f2fa57a8c81fc171e303ec9fc2a2597d9d9ea937/pilots/schur-six/baseline-536.json) returned HTTP 200, **1,112 bytes**, with the expected SHA-256:

```text
968f91177ddf7cbe9ce0347c8f2be089c54a6b648c387a6080cbec1237636010
```

This addendum preserves the original receipt and clarifies deployment provenance. It does not erase the earlier observation or claim frontend acceptance.
