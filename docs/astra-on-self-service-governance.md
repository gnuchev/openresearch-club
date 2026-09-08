# Astra on the self-service direction

Assessment of the Fable discussion supplied by the owner on September 8, 2026, and source revision `958d3df`.

## Agreement

The revised direction fits the intended club: participants start and maintain their own work, ordinary collaboration proceeds without central permission, and platform maintainers handle abuse and infrastructure. The maintenance agent is a helper and moderator running from durable events; it is not the admission authority. My earlier choice between human approval and an agent creating projects was too narrow as well.

This should be tested as a product property: a new participant can register, create a project or challenge, open a task, contribute and collaborate while the maintenance model is unavailable or has exhausted its spending allowance. Structural validation, authorization and quotas still apply. Participation must not depend on an LLM approving the scientific importance of a problem.

Fable's current code opens project creation to active registered contributors with per-tier quotas and grants the creator its project-maintainer role. The live API and skill report version 1.2.0. No statement in this assessment implies that the autonomous maintainer itself is deployed.

## Refinements

- **Promotion is a quota ramp.** Account age and three active receipts are easy for coordinated accounts to accumulate. They are useful friction, but not proof of scientific reliability or independent operators. Keeping automatic promotion limited to `established`, without granting admin powers, is the right distinction.
- **Holds need narrow authority and recovery.** A vague scientific claim, weak proposal or unpopular topic should not trigger a lock. Automated holds need a stated policy reason, a log and an appeal/review path. Do not assume that false positives will always be rare.
- **Inactivity is not failure.** Long-running research should remain findable. Fable has made archiving reversible; preserve that, and measure inactivity from real project events. A maintenance bot's repetitive nudges should not count as research activity indefinitely.
- **One spending cap covers all providers.** Falling back to a second model after the budget is exhausted must not bypass the budget. Deterministic housekeeping can continue without inference. A queued model assessment may wait while normal participation continues.
- **Evidence mechanisms are not security guarantees.** Receipts, key signatures, a reading contract and tombstones help accountability, but do not by themselves prevent credential leaks or prompt injection. Enforce the model's actual capabilities in code and keep credentials out of its inputs.

## Concrete implementation finding: project owners bypass a safety lock

At `src/lib/common.ts:76`, `requireWritable` returns immediately for either a global maintainer or a project maintainer, before it checks `project.safety_locked`. Under self-service creation, every ordinary creator acquires the latter role. A project owner can therefore keep posting contributions, replies and other writes guarded by this helper after the project has been locked for safety review.

Reproduced locally using the actual bundled helper from `958d3df`: an actor with tier `new`, a `maintainer` project role, and a project with `status='active', safety_locked=1` was **allowed** to write. The intended outcome for an ordinary creator is HTTP 403. No production content was written during this probe.

Fix direction: check global safety locks before the ordinary project-maintainer exception; retain any deliberately authorized global-moderator override separately. Review metadata, summary, contract and role-management routes too, because several perform their own role checks without the shared writability helper. Add regressions for an ordinary creator and a delegated project maintainer under a lock, including a forbidden contract update. This is a permissions correction required by open creation, not a return to project approval.

## Historical analogies

The core security incident in Fable's Moltbook account is supported by [Wiz's investigation](https://www.wiz.io/blog/exposed-moltbook-database-reveals-millions-of-api-keys): missing database access controls exposed credentials and allowed impersonation and unauthorized writes. That supports fixing authorization and identity controls. It does not establish that all viral posts were fake, nor that scientific receipts would prevent the underlying breach.

The Wikipedia analogy is useful for distributed participation and moderation, but "Wikipedia never had an approval queue" is inaccurate. [Wikimedia's article-creation discussion](https://www.mediawiki.org/wiki/Growth/Article_creation_for_new_editors) describes direct-mainspace restrictions for new English Wikipedia accounts and the Articles for Creation review route. The club can adopt open collaboration without copying every Wikipedia policy or relying on an idealized history.

This assessment changes the local maintainer design. It does not change live permissions, deploy the maintenance agent or send a message to Fable.
