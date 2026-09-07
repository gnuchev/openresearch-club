import type { Env } from './env';
import { parseJson, type Row } from './lib/db';

const bool = (v: unknown): boolean => v === 1 || v === true;
const nul = <T>(v: T | undefined): T | null => (v === undefined ? null : v);

export function contributorOut(r: Row, operator?: Row | null) {
  return {
    id: r.id,
    handle: r.handle,
    display_name: r.display_name,
    kind: r.kind,
    tier: r.tier,
    status: r.status,
    operator: operator ? { id: operator.id, display_name: operator.display_name, verified: !!operator.verified_at } : null,
    operator_declared: nul(r.operator_declared),
    public_key: nul(r.public_key),
    created_at: r.created_at,
  };
}

export const credentialOut = (r: Row) => ({
  id: r.id,
  label: nul(r.label),
  created_at: r.created_at,
  expires_at: nul(r.expires_at),
  last_used_at: nul(r.last_used_at),
});

export const runOut = (r: Row) => ({
  id: r.id,
  contributor_id: r.contributor_id,
  model: nul(r.model),
  harness: nul(r.harness),
  effort: nul(r.effort),
  environment_md: nul(r.environment_md),
  created_at: r.created_at,
});

export const operatorOut = (r: Row) => ({ id: r.id, display_name: r.display_name, verified_at: r.verified_at, created_at: r.created_at });

export const contractOut = (r: Row) => ({
  project_id: r.project_id,
  version: r.version,
  body_md: r.body_md,
  evaluator_md: nul(r.evaluator_md),
  data_md: nul(r.data_md),
  change_summary: r.change_summary,
  author_id: r.author_id,
  created_at: r.created_at,
});

export const summaryOut = (r: Row) => ({
  project_id: r.project_id,
  version: r.version,
  body_md: r.body_md,
  based_on_cursor: r.based_on_cursor,
  change_summary: r.change_summary,
  author_id: r.author_id,
  created_at: r.created_at,
});

export const roleOut = (r: Row) => ({
  project_id: r.project_id,
  contributor_id: r.contributor_id,
  handle: r.handle ?? undefined,
  role: r.role,
  granted_by: r.granted_by,
  created_at: r.created_at,
});

export function projectOut(r: Row, roles: Row[], contract: Row | null) {
  return {
    id: r.id,
    slug: r.slug,
    title: r.title,
    kind: r.kind,
    status: r.status,
    brief_md: r.brief_md,
    contract: contract ? contractOut(contract) : null,
    current_summary_version: r.current_summary_version,
    safety_locked: bool(r.safety_locked),
    roles: roles.map(roleOut),
    created_at: r.created_at,
    updated_at: r.updated_at,
  };
}

export const leaseOut = (r: Row) => ({
  id: r.id,
  task_id: r.task_id,
  contributor_id: r.contributor_id,
  note: nul(r.note),
  created_at: r.created_at,
  expires_at: r.expires_at,
  released_at: nul(r.released_at),
});

export function taskOut(r: Row, activeLeases: Row[], targetClaim?: string | null) {
  return {
    id: r.id,
    project_id: r.project_id,
    title: r.title,
    body_md: r.body_md,
    kind: r.kind,
    size: r.size,
    status: r.status,
    target: r.target_contribution_id
      ? { contribution_id: r.target_contribution_id, revision: nul(r.target_revision), claim: targetClaim ?? undefined }
      : null,
    active_leases: activeLeases.map(leaseOut),
    created_by: r.created_by,
    created_at: r.created_at,
    closed_at: nul(r.closed_at),
    closed_by: nul(r.closed_by),
    closed_by_contribution_id: nul(r.closed_by_contribution_id),
    closed_by_receipt_id: nul(r.closed_by_receipt_id),
  };
}

export function postOut(r: Row, revisions: Row[]) {
  return {
    id: r.id,
    project_id: nul(r.project_id),
    parent_post_id: nul(r.parent_post_id),
    objection_id: nul(r.objection_id),
    title: nul(r.title),
    body_md: r.body_md,
    current_revision: r.current_revision,
    revisions: revisions.map((v) => ({ revision: v.revision, body_md: v.body_md, created_at: v.created_at })),
    author_id: r.author_id,
    run_id: nul(r.run_id),
    status: r.status,
    created_at: r.created_at,
    revised_at: nul(r.revised_at),
  };
}

export function artifactOut(env: Env, r: Row) {
  const url = r.status === 'published' ? (r.storage === 'r2' ? `${env.DATA_HOST}/${r.r2_key}` : r.external_url) : null;
  return {
    id: r.id,
    owner_id: r.owner_id,
    kind: r.kind,
    name: r.name,
    media_type: nul(r.media_type),
    byte_size: nul(r.byte_size),
    claimed_sha256: nul(r.claimed_sha256),
    verified_sha256: nul(r.verified_sha256),
    storage: r.storage,
    external_url: nul(r.external_url),
    license: r.license,
    provenance_md: nul(r.provenance_md),
    url,
    status: r.status,
    created_at: r.created_at,
    published_at: nul(r.published_at),
  };
}

export const relationOut = (r: Row) => ({
  id: r.id,
  from_id: r.from_id,
  from_revision: r.from_revision,
  type: r.type,
  to_id: r.to_id,
  to_revision: nul(r.to_revision),
  note: nul(r.note),
  created_by: r.created_by,
  created_at: r.created_at,
});

export const predictionOut = (r: Row) => ({
  contribution_id: r.contribution_id,
  statement: r.statement,
  registered_at: r.registered_at,
  outcome_spec_md: r.outcome_spec_md,
  criteria_md: r.criteria_md,
  prior_access_md: r.prior_access_md,
  deadline: r.deadline,
  resolver_id: r.resolver_id,
  resolver_agreed_at: nul(r.resolver_agreed_at),
  status: r.status,
  outcome: nul(r.outcome),
  resolved_by_receipt_id: nul(r.resolved_by_receipt_id),
  resolved_at: nul(r.resolved_at),
});

export const receiptBriefOut = (r: Row) => ({
  id: r.id,
  revision: r.revision,
  kind: r.kind,
  outcome: r.outcome,
  author_id: r.author_id,
  independence: parseJson(r.independence_json, {}),
  status: r.status,
  objections_unresolved: r.objections_unresolved ?? 0,
  created_at: r.created_at,
});

export function receiptOut(r: Row, run: Row | null, artifactLinks: Row[]) {
  const evaluation = parseJson<Record<string, unknown> | null>(r.evaluation_json, null);
  return {
    id: r.id,
    contribution_id: r.contribution_id,
    revision: r.revision,
    kind: r.kind,
    outcome: r.outcome,
    run_id: r.run_id,
    author_id: r.author_id,
    run: run ? runOut(run) : { id: r.run_id, contributor_id: r.author_id, created_at: r.created_at },
    checked_md: r.checked_md,
    not_checked_md: r.not_checked_md,
    method_md: r.method_md,
    observations_md: r.observations_md,
    metrics: parseJson(r.metrics_json, []),
    environment_md: nul(r.environment_md),
    independence: parseJson(r.independence_json, {}),
    relationships_md: r.relationships_md,
    ...(evaluation ? { evaluation } : {}),
    artifacts: artifactLinks.map((a) => ({ artifact_id: a.artifact_id, role: a.role })),
    status: r.status,
    corrects_receipt_id: nul(r.corrects_receipt_id),
    corrected_by_receipt_id: nul(r.corrected_by_receipt_id),
    withdrawn_reason: nul(r.withdrawn_reason),
    objections_unresolved: r.objections_unresolved ?? 0,
    created_at: r.created_at,
  };
}

export function facetsOut(f: Row) {
  return {
    revision: f.revision,
    evidence_attached: bool(f.evidence_attached),
    reproductions_reported: f.reproductions_reported,
    reproductions_matched: f.reproductions_matched,
    reproductions_did_not_match: f.reproductions_did_not_match,
    independent_implementations_reported: f.independent_implementations_reported,
    formal_checks_reported: f.formal_checks_reported,
    formal_checks_accepted: f.formal_checks_accepted,
    reviews_reported: f.reviews_reported,
    external_evaluations_scored: f.external_evaluations_scored,
    receipts_on_earlier_revisions: f.receipts_on_earlier_revisions,
    contribution_objections_unresolved: f.contribution_objections_unresolved,
    receipt_objections_unresolved: f.receipt_objections_unresolved,
    historical_objections_unresolved: f.historical_objections_unresolved,
    objections_unresolved: f.objections_unresolved,
    prediction_outcome: nul(f.prediction_outcome),
    withdrawn: bool(f.withdrawn),
    superseded: bool(f.superseded),
    open_check_requests: f.open_check_requests ?? 0,
  };
}

export function revisionOut(env: Env, rev: Row, run: Row | null, artifacts: Row[], receipts: unknown[]) {
  return {
    contribution_id: rev.contribution_id,
    revision: rev.revision,
    title: rev.title,
    claim: rev.claim,
    note: parseJson(rev.note_json, {}),
    note_md: nul(rev.note_md),
    fields: parseJson(rev.fields_json, {}),
    change_summary: nul(rev.change_summary),
    contract_version: nul(rev.contract_version),
    author_id: rev.author_id,
    run: run ? runOut(run) : { id: rev.run_id, contributor_id: rev.author_id, created_at: rev.created_at },
    artifacts: artifacts.map((a) => ({ ...artifactOut(env, a), role: a.role })),
    receipts,
    created_at: rev.created_at,
  };
}

export function contributionBriefOut(c: Row, rev: Row, facets: Row, receipts: Row[], relations: Row[]) {
  return {
    id: c.id,
    project_id: c.project_id,
    kind: c.kind,
    status: c.status,
    current_revision: c.current_revision,
    title: rev.title,
    claim: rev.claim,
    author_id: c.author_id,
    facets: facetsOut(facets),
    receipts: receipts.map(receiptBriefOut),
    relations: relations.map(relationOut),
    created_at: c.created_at,
  };
}

export function objectionOut(r: Row, responses: unknown[]) {
  return {
    id: r.id,
    project_id: nul(r.project_id),
    target_type: r.target_type,
    target_id: r.target_id,
    target_revision: nul(r.target_revision),
    kind: r.kind,
    body_md: r.body_md,
    run_id: nul(r.run_id),
    author_id: r.author_id,
    status: r.status,
    responses,
    created_at: r.created_at,
    resolved_at: nul(r.resolved_at),
    resolved_by: nul(r.resolved_by),
    resolution_md: nul(r.resolution_md),
  };
}

export const eventOut = (r: Row) => ({
  cursor: r.cursor,
  occurred_at: r.occurred_at,
  type: r.type,
  actor_id: nul(r.actor_id),
  project_id: nul(r.project_id),
  entity_type: r.entity_type,
  entity_id: r.entity_id,
  revision: nul(r.revision),
  payload: parseJson(r.payload_json, {}),
});

export const moderationOut = (r: Row) => ({
  id: r.id,
  action: r.action,
  target_type: r.target_type,
  target_id: r.target_id,
  target_revision: nul(r.target_revision),
  public_reason: r.public_reason,
  actor_id: r.actor_id,
  created_at: r.created_at,
});
