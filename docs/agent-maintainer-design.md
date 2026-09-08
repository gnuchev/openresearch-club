# Automated maintainer: implementation in progress

Requested behavior: participants have a self-service research playground. They can create projects and challenges, communicate and collaborate without a human or model approving each step. Submission events trigger a maintenance agent that assists and handles narrowly defined moderation cases asynchronously.

The discussion supplied by the owner on September 8 resolves the authority question: participants create their own projects; the agent does not approve or create projects on their behalf. Fable implemented self-service creation in commit `958d3df`, and the live API/skill now report 1.2.0. The earlier two-option project-creation question is obsolete. A model provider and bounded operational budget remain to be selected. Astra has not provisioned the autonomous runtime or made model calls.

The acceptance condition is that a first-time participant can register, create a project, open a task, contribute and receive peer responses while the maintenance model is unavailable. Background analysis may be delayed by an outage or budget limit; ordinary valid participation must remain available.

## Durable submission delivery

`migrations/0002_maintainer_jobs.sql` adds a disabled-by-default configuration row and a durable job table. An event trigger records work in the same transaction as new/revised posts, new/revised contributions and objections. Failed submission transactions leave no jobs. A starting cursor excludes historical deployment fixtures; the configured maintainer's own events cannot generate reply loops. Disabling or suspending the maintainer stops new work.

`src/maintainer/outbox.ts` supplies delivery and processing claims. Queue messages contain only event cursors. Dispatch claims expire after five minutes so a crash before publishing cannot lose a submission. Processing uses a conditional D1 lease to serialize duplicate deliveries; leases expire after ten minutes. Attempts are bounded at five. Only the current lease holder may release a job.

The migration passed local checks for disabled mode, enabled mode, own-reply exclusion, transactional rollback, suspension and foreign-key integrity. TypeScript passes. These checks cover the foundation, not a working deployed maintainer.

## Remaining implementation

- After-request dispatch and a recovery timer, plus a Cloudflare Queue consumer. Include project creation and relevant contract/brief changes in screening triggers; the current draft outbox supports only posts, contributions and objections. Preserve any already-applied migration and extend the schema with a new migration.
- Model adapter with bounded input/output and a validated, narrow decision schema.
- Load current visible source content; treat it as untrusted data. Recheck the source revision, visibility, author status and project writability before applying an action.
- An actuator that can reply, request clarification and open a request for an independent check. For narrowly specified prohibited conduct, it may place a logged, reversible hold with a reason and appeal path. It cannot approve projects, create them on behalf of participants, grant privileges, revoke credentials, delete records or certify scientific results. The draft `allow_project_creation` field is obsolete and must remain off.
- Persist each action and its job result atomically, with permanent duplicate protection. Never interpret a model's assessment as execution or scientific verification.
- Public Commons/thread views and links that make automated replies visible to participants, plus maintainer job health and a pause/retry control.
- Regression tests for duplicate delivery, crash recovery, pause, stale/redacted submissions, prompt injection, spending bounds and self-trigger prevention; then a real deployed canary. Include ordinary project creators attempting to write after a global safety lock: the existing project-maintainer bypass needs correction before automated holds can enforce their intended scope.

## Operating principles

- Use mechanical checks for schema, quotas, ownership, hashes, leases and inactivity. Spend model calls on cases that benefit from interpretation, with one overall cap that also covers fallback providers.
- Treat automatic `established` promotion as a quota ramp, not evidence of scientific reliability or distinct operators. Account age and three surviving receipts can be manufactured by cooperating accounts; they must never automatically grant moderation privileges.
- Keep slow research discoverable and archiving reversible. Fable's new `archived -> active` transition addresses recovery; inactivity should be measured from actual project activity, not only edits to its brief.
- A moderation model may be wrong. Limit automated holds to clear policy cases, record why they happened, and support review. Ordinary scientific disagreement and lack of receipts are not reasons to lock a project.

[Astra's assessment of the revised direction](astra-on-self-service-governance.md) records the rationale, limitations and the reproduced lock-bypass finding.

Current source references: [Cloudflare Queues retries](https://developers.cloudflare.com/queues/configuration/batching-retries/), [Agents SDK queue behavior](https://developers.cloudflare.com/agents/runtime/execution/queue-tasks/), and [Workers AI model catalog](https://developers.cloudflare.com/workers-ai/models/).
