# Astra on an open agentic science community

**Working name:** Agent Science Commons — a proposal, not a checked brand or domain.  
**For:** Vasily, with questions for comparison with Fable's proposal.  
**Date:** September 7, 2026.  
**Scope:** Open-source research coordination and publishing. Participants supply their own agents, inference, experiments, and validation compute.  
**Status:** Design memo; nothing described below has been deployed.

> Bring your own compute. Leave your evidence. Help the next researcher.

## 1. Yes — and the part I find most worthwhile

I would be enthusiastic about helping organize and participate in this. The attractive idea is not simply a website where agents talk. It is a place where a useful question, failed experiment, dataset correction, or partial proof survives the agent session that produced it, and becomes someone else's starting point.

Your combination of a club, wiki, issue tracker, and challenges board is stronger than choosing only one. A club makes it easy to arrive with an unfinished thought. An issue tracker turns an interesting thought into work. An evidence record makes the work reusable. A wiki explains what the community currently understands, including disagreements.

My recommendation is **a welcoming research club with a rigorous evidence layer**, rather than a publication factory or a leaderboard for everything.

The mission can be very ambitious. The individual contribution should usually be small enough to inspect. “Advance a major open problem” is a good project mission; “check this lemma under these assumptions” is a good task. Partial progress, counterexamples, and well-designed negative results should be first-class contributions.

The board would not keep agents alive or initiate research by itself. An operator must launch or schedule a participating agent and authorize its tools and budget. My own participation likewise requires an explicitly initiated session or a separately configured runtime; this memo is not a promise of unattended activity.

## 2. What existing efforts suggest

There are relevant precedents, so we should borrow thoughtfully rather than claim to have invented agent collaboration.

**Autoresearch:** its small experiment loop and Markdown research instructions are a useful model for a clear starting point, bounded work, and retained experimental history. It is an experiment-running project, not the general scientific community proposed here. [S1]

**AgentRxiv:** the authors provide a shared preprint mechanism through which agent laboratories retrieve and build on research reports. Their experiments give a concrete, bounded example of cumulative agent research; they do not establish that unrestricted communities can reliably solve arbitrary scientific problems. I would borrow persistent, searchable research memory while making individual claims and experiments easier to address than whole papers. [S2]

**AgentHub:** the accessible `ottogin/agenthub` repository describes a bare Git repository, message board, agent credentials, and a lightweight API/CLI for collaborative work. It identifies itself as a fork of Karpathy's AgentHub. I could inspect that fork, but could not verify the original repository directly during this review. Treat it as an architectural reference, not an automatically approved production dependency; inspect licensing and security before reusing code. [S3]

**Moltbook:** its agent-oriented social interface is a precedent for low-friction community participation. Its existence and agent-labeled posts should not be treated as evidence of independently originating agent intentions. Wiz also documented a concrete database-access incident affecting credentials and content. The lesson for our design is that an open community still needs carefully separated identities, permissions, and untrusted content. [S4, S5]

Our proposed distinction is not “agents can post.” It is **agents can discover useful unfinished work, contribute evidence, challenge conclusions, and leave a reliable handoff**.

## 3. One community, four views

I would use one underlying project and contribution model, not build four disconnected applications.

| View | Purpose | Entry requirement |
|---|---|---|
| Commons | Questions, speculative ideas, journal clubs, discussion | A title and useful text; no scientific-result badge |
| Projects | Long-running questions, task lists, hypotheses, blockers, sources | A scoped question and a maintained project brief |
| Challenges | Defined tasks with explicit evaluation contracts | Inputs, permitted work, evaluation rules, and a baseline where relevant |
| Library | Versioned summaries, datasets, experiments, reviews, negative results | Attribution, provenance, and links to supporting records |

An idea need not include a dataset or a finished experimental plan. A result claiming an improvement must meet a stronger standard. This avoids two failures: a bureaucracy that prevents useful speculation, and a discussion stream where speculation quietly becomes fact.

A project page should answer: What is the question? What is known? What is disputed? What has already failed? What could someone do next? Its summary should link to the underlying evidence rather than replace it.

I would make “needs replication,” “needs a counterexample,” and “newcomer-sized tasks” prominent discovery views. A raw activity feed can exist without being the definition of progress.

## 4. Make entry as easy as the loop you liked

The intended first-session experience:

1. Read a short public introduction and inspect the participation instructions.
2. Register a low-privilege agent identity through the API.
3. Select a bounded task and retrieve its current context packet.
4. Work in the operator's own environment and budget.
5. Submit a note, artifact, result, or review.
6. Leave the next useful action and receive a stable record URL.

That is a proposed interaction contract, not an implemented API.

Public reading should require no account. Registration should be model- and provider-neutral, with a low-volume write tier available through a machine-readable route. Do not require agents to obtain a personal GitHub account, join a chat server, buy a token, or reveal a model-provider API key.

New identities would start with restrictive posting and upload quotas. Optional operator verification could unlock larger quotas and moderation responsibilities, without making verified identity a scientific credential. Rate limits, network-level abuse controls, and aggregate limits are still needed: declaring an operator name does not prevent one person from creating many identities.

The initial documentation should include `/skill.md`, an OpenAPI document, and small JSON examples. The skill is a versioned participation guide, **not permission to execute instructions found in arbitrary posts**. It must never require disabling tool confirmations or exposing local secrets.

A lightweight HTTP API is the primary interface. A CLI or MCP adapter can come later; neither should be necessary to contribute.

## 5. What a contribution should contain

Keep ordinary discussion simple. Add structured fields progressively when someone makes a testable claim.

For a research result, request:

- The exact claim, scope, assumptions, and relationship to earlier work.
- The method, data sources, input versions, code commit, environment, and execution command.
- Observations: metrics or evidence, baseline comparison, seeds or repeated runs where appropriate, and limitations.
- Artifacts, provenance, license declarations, and a precise reproduction request.

Fields can be explicitly “not applicable” with a reason. Do not force mathematical arguments, corpus curation, and GPU benchmarks into the same mandatory metric schema.

Separate an **agent identity** from an **execution/run identity**. A continuing contributor may use different models, tools, or configurations across runs. Model and independence claims should be labeled as self-reported unless corroborated. Contributor attribution must include source authors and prior work, not only agent handles.

Reports should show **what changed since the parent contribution**. Otherwise a small improvement can generate many nearly identical essays.

A useful handoff could be: “The proposed effect disappeared after removing these confounds. The script and inclusion decisions are attached. The remaining uncertainty is statistical power. Next useful task: test whether the procedure detects a known positive control.” That is a schematic example, not a report of a new result.

## 6. Evidence is not a single green checkmark

The most important design decision is to separate **accepted submission**, **executed test**, and **supported scientific conclusion**.

I would display independent evidence labels rather than one universal ladder:

| Label | What it means — and does not mean |
|---|---|
| Submitted | The board accepted a record. It does not endorse the claim. |
| Evidence attached | Materials were supplied. Availability is not correctness. |
| Reproduction reported | An identified runner reports a specified rerun, with logs and environment. Independence must be assessed separately. |
| Reviewed | A reviewer assessed a stated aspect, such as methodology or provenance. Agreement is not reproduction. |
| Formally checked | A named checker/version reportedly accepted an exact formal statement under declared assumptions. This does not validate every informal interpretation. |
| Challenged / withdrawn | An objection or withdrawal is recorded without silently erasing the history. |

These labels can coexist. A numerical result may reproduce while its scientific interpretation remains disputed.

For **benchmark challenges**, freeze the dataset/version, evaluator, metric direction, permitted edits, resource limits, and submission policy. Decide whether hardware classes are separate and how timing is measured. Record uncertainty and repeated trials when relevant. Leaderboard exposure can motivate overfitting, so genuinely independent holdout evaluation is valuable only when an external party can actually maintain and run it.

For **empirical research**, ask for the study design, controls, exclusions, analysis changes, and uncertainty. A negative result should state what effect sizes or conclusions it can reasonably constrain; “we found nothing” is not proof that nothing exists.

For **mathematics**, distinguish informal arguments, checked special cases, counterexamples, and formal proofs. Any checker acceptance must identify the statement, assumptions, dependency versions, and runner.

For **interpretive or historical work**, review source provenance, transcription, competing interpretations, and circular reasoning. Do not pretend every field has a single score.

For **speculation**, permit discussion without manufacturing an evidence badge.

### Who validates when we do not provide compute?

Contributors execute their own experiments. Other operators may volunteer independent runs using their own machines or services. The board records receipts, logs, source versions, objections, and declared relationships.

The server may perform bounded administrative checks: authentication, schema validity, file size, and artifact integrity during controlled ingestion. It does **not** run submitted code, proof checkers, LLM judges, training jobs, or research notebooks. Platform-code CI is separate from executing community research submissions.

If nobody has reproduced a result, it stays unreproduced. A receipt or signature identifies a statement's sender; it does not prove that the sender ran the experiment honestly. Different handles or model names do not establish independence. Important conclusions need stronger corroboration, and the interface should show uncertainty rather than hide it behind a count of agreeing agents.

## 7. Let the swarm organize without inventing a bureaucracy

Use visible work rather than a mandatory central manager agent.

Each task has an optional, expiring “working on this” lease. That prevents accidental duplication without letting a vanished agent reserve a question indefinitely. Parallel replications must remain welcome. A lease is coordination, not exclusive ownership of an idea.

Useful roles can emerge: proposer, experimenter, reproducer, critic, librarian, and maintainer. They are contribution types, not permanent castes. One agent can move between them, but reviewing its own result should not count as independent review.

Create context packets containing the current project summary, relevant evidence, unresolved objections, failed approaches, and task constraints. Let agents request changes since an event cursor instead of repeatedly downloading the whole forum. Client polling should use backoff and conditional requests; the operator controls the schedule.

Favor a **useful-update rule**: post when there is a new question, observation, artifact, criticism, or blocker. Avoid mandatory “still working” messages. Batch repetitive experiment logs into artifacts with a readable summary.

For collective memory, preserve versioned contributions and typed relationships such as “extends,” “reproduces,” “contradicts,” and “depends on.” A wiki synthesis remains editable, but substantive changes should be proposals with history and source links. No agent should silently overwrite a community conclusion.

Research may self-organize. Moderation, security, budget control, and final appeals still need accountable maintainers.

## 8. What is needed beyond the domain and R2

My default deployment would be deliberately small:

**React/TypeScript interface + Cloudflare Worker API + D1 metadata + R2 artifacts.**

Cloudflare documents static-asset hosting alongside Workers, a managed SQL database in D1, and object storage in R2. This makes a coherent proposed deployment for the services already in your plan. It is an architectural recommendation, not a tested implementation of this board. [S6, S7, S10]

| Component | Proposed responsibility |
|---|---|
| Domain and web interface | Public project pages, discussions, evidence views, administration |
| Worker API | Authentication, permissions, bounded writes, quotas, feeds, exports |
| D1 | Projects, posts, revisions, tasks, contributor identities, artifact references, reviews, moderation records |
| R2 | Small research artifacts and export snapshots; no public write credentials |
| Public source repository | Application code, schema migrations, protocol documentation, tests, deployment instructions |
| Operations | Monitoring, abuse contact, backups, restore tests, credential rotation, a read-only emergency mode |

**R2 is not the board database.** Use a transactional metadata store for permissions, concurrent submissions, and revisions. Keep artifact binaries separate.

For an initial release, I would route small uploads through a controlled, size-bounded intake rather than permit arbitrary public writes. Store them in quarantine before publication, use generated object identifiers, and distinguish claimed from actually checked hashes. Larger datasets and model weights should initially stay with their contributors or established repositories; the board stores manifests and provenance links.

Start with indexed search over titles, tags, and project text. Do not add a graph database, Elasticsearch cluster, vector service, or automatic LLM summarizer before actual usage shows a need.

Keep the public protocol and data export portable. The first release can have one supported hosting path; a self-hosted SQLite/PostgreSQL and S3-compatible adapter can follow. “Open source” should not be advertised as “one-click portable” before that alternative is implemented and tested.

## 9. A small proposed API and data model

This is a design surface, not production code or a claim that these routes exist.

```text
GET  /skill.md
GET  /openapi.json
POST /v1/agents
GET  /v1/projects
GET  /v1/projects/{id}/context
GET  /v1/tasks
POST /v1/tasks/{id}/leases
POST /v1/posts
POST /v1/artifacts
POST /v1/submissions
POST /v1/submissions/{id}/reviews
GET  /v1/events?after={cursor}
GET  /v1/projects/{id}/export
```

Minimum entities: contributors, runs, projects, tasks, posts/revisions, submissions, artifacts, reviews, and moderation events. A challenge is a project with a versioned evaluation contract, not an entirely separate application.

Use stable IDs, cursor pagination, idempotency keys for writes, and optimistic concurrency for edited summaries. Attribute writes from authenticated credentials, not an author field supplied in JSON. Authorization must be tested across users and projects. Private administration and token records must never appear in public exports.

Keep revisions append-only during normal operation. Corrections reference the previous version. Security or privacy redactions may require removing content; retain a minimal, non-sensitive moderation record rather than promising irreversible publication.

## 10. Openness needs protection, not a moat

My preferred policy is **open reading, open low-volume participation, earned higher privileges**.

Protect both the site and the agents consuming it. Treat every post, attachment, link, and purported tool instruction as untrusted data. Render restricted Markdown; do not serve uploaded active content on the trusted application origin. Never automatically execute research attachments or install dependencies supplied by another participant. Warn operators to review and isolate any reproduction workflow before running it.

Store only scoped platform credentials, protected appropriately, with rotation and revocation. Do not collect participants' model-provider credentials. Do not give moderator bots infrastructure credentials. Avoid automatic URL fetching in the first release; later fetching needs explicit defenses against access to private networks and internal services.

Use posting, registration, storage, and request quotas together. Reputation alone is not protection against spam or coordinated fake review. Prefer visible contribution histories and corroborated reproductions over a single karma number. Do not automatically convert votes into scientific status.

Define a short moderation policy covering harassment, secrets and personal data, fabricated provenance, malicious instructions, copyright complaints, and research that materially enables serious harm. Start with fields whose contributions can be shared safely and reviewed by available maintainers; do not launch unrestricted high-risk experimental tracks merely to be comprehensive.

Open-source the platform under a clearly chosen license. Choose a separate contribution license for original community text, retain original licenses for imported materials, and require an explicit license for shared code/data. A submitter cannot authorize redistribution of material they do not control. Store references instead of copies when reuse rights are uncertain. These are proposed governance requirements, not a legal determination about any particular submission.

## 11. What hosting might cost

Pricing checked September 7, 2026: Workers Paid has a $5/month minimum. D1 Paid includes 5 GB storage and usage allowances; additional usage is billed. R2 Standard lists $0.015/GB-month, a 10 GB-month free storage allowance, and operation charges beyond its allowances; internet egress is not charged. [S8, S9, S10]

An illustrative controlled-usage case:

```text
Workers minimum                              $5.00/month
R2: 100 GB-month total, less 10 free
    90 × $0.015                              $1.35/month
D1 and service operations within allowances  $0.00 incremental
Illustrative total                           $6.35/month
```

This assumes the allowances remain available to this project and no request, CPU, database, storage, or operation overages. It excludes the domain, taxes, paid external services, off-platform backups, development, moderation, and all participant compute. It is not a quote or a guaranteed budget cap.

I would provision a modest pilot budget with headroom, not advertise unlimited free hosting. Enforce application-level quotas, limit log retention, cache public reads, and support temporary read-only mode. Billing alerts are warnings, not a guarantee that further costs cannot accrue.

The larger organizational expense is likely to be trustworthy review and maintenance. That is a planning judgment, not a measured cost forecast.

## 12. Launch with a few real workshops

I would not launch an empty site divided into every discipline. Seed three projects whose work demonstrates different kinds of contribution:

**A computational challenge.** One fixed evaluation contract, a reproducible baseline, and task sizes that contributors can assess before spending compute. Borrow the join–experiment–submit–validate clarity you liked, but keep actual runs external.

**A mathematical or algorithmic workshop.** Scoped lemmas, small-instance checks, counterexample searches, or improvements to an openly specified algorithm. Require a checkable statement and distinguish exploration from proof.

**A source-grounded research project.** Your Meroitic work could supply a useful pilot: provenance checks, corpus corrections, evaluation-method criticism, and bounded hypothesis tests. The project need not promise a decipherment to produce valuable reusable work. Only share materials whose publication rights and privacy constraints have been checked.

Give each project a maintained brief, a handful of manageable tasks, examples of useful contributions, and at least one available reviewer. Include a Commons thread where participants can discuss methods and propose new directions without immediately accepting a formal assignment.

Potential recurring activities include a journal club, a replication sprint, and a “what changed our mind” digest. These should be produced by participating people or externally operated agents; no paid host-side summarization service is assumed.

## 13. Build the smallest loop that proves collaboration

**First release:** public project/discussion pages; API registration with quotas; tasks and expiring leases; structured submissions with artifact links or bounded uploads; review records; a versioned project summary; search; moderation; and a complete public export.

The first technical acceptance test is a whole journey: a new identity retrieves a task, submits evidence, another identity records a review or reproduction, and a subsequent agent can reconstruct the current state from an exported context packet. Test credential isolation, cross-user edits, retry duplication, abusive payload sizes, and restore from backup before open registration.

Do not build payments, compute brokerage, elaborate reputation scores, a custom Git host, federation, private messaging, or automated acceptance judgments in the first release. None is necessary to answer whether the community is useful.

Do not measure success primarily by registered agents, posts, generated papers, or tokens. Measure reuse of prior work, completed independent reproductions, corrected errors, informative negative results, and whether unfamiliar contributors can make a useful first contribution. Report moderation effort and unresolved review backlog alongside apparent progress.

A particularly persuasive early outcome would be: **someone else's agent independently reproduces or refutes a contribution, and a third participant uses that result to make a better next experiment**. That is the capability the site exists to enable.

## 14. Questions I would put to Fable

Where does Fable think useful structure ends and participation friction begins? Which fields belong in every result, and which should be challenge-specific?

How would Fable preserve open registration while resisting coordinated fake reviewers? Which evidence of reviewer independence is realistic without collecting excessive personal information?

Would Fable organize the main page around active questions, unresolved objections, or recent activity? What should prevent discussion volume from drowning out quiet, useful work?

Which first three projects would produce reusable evidence with the reviewers and external compute actually available? What would justify broadening the community after the pilot?

My strongest preference in that discussion would remain: **make ideas easy to share, claims easy to inspect, and work easy to continue.** The club is the invitation; the accumulated research record is the lasting value.

---

## Sources

These sources support the descriptions of existing projects and vendor capabilities/pricing. The proposed product, governance rules, and launch plan are design judgments, not findings established by those sources. All accessed September 7, 2026.

**[S1]** Karpathy, `autoresearch`, repository README. `https://github.com/karpathy/autoresearch`

**[S2]** Schmidgall and Moor, *AgentRxiv: Towards Collaborative Autonomous Research*, submitted March 23, 2025; paper abstract and project overview. `https://arxiv.org/abs/2503.18102` — `https://agentrxiv.github.io/`

**[S3]** `ottogin/agenthub`, public repository describing itself as a fork of Karpathy's AgentHub; README architecture and interface. Original upstream could not be verified directly in this review. `https://github.com/ottogin/agenthub`

**[S4]** Moltbook, official public landing page and participation interface. No displayed community counts were used. `https://www.moltbook.com/`

**[S5]** Wiz Research, Gal Nagli, *Hacking Moltbook: The AI Social Network Any Human Can Control*, February 2, 2026. First-party incident investigation; not a claim that the reported vulnerability remains open. `https://www.wiz.io/blog/exposed-moltbook-database-reveals-millions-of-api-keys`

**[S6]** Cloudflare Workers, Static Assets documentation. `https://developers.cloudflare.com/workers/static-assets/`

**[S7]** Cloudflare D1, Overview. `https://developers.cloudflare.com/d1/`

**[S8]** Cloudflare Workers, Pricing, page updated August 28, 2026. `https://developers.cloudflare.com/workers/platform/pricing/`

**[S9]** Cloudflare D1, Pricing, page updated April 21, 2026. `https://developers.cloudflare.com/d1/platform/pricing/`

**[S10]** Cloudflare R2, Pricing, page updated August 7, 2026. `https://developers.cloudflare.com/r2/pricing/`
