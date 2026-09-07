// Checks that the Workers-safe validator enforces the OpenAPI conditionals the same way the
// reviewers' probes do. Run after `npm run build:schemas`.
import { readFileSync } from 'node:fs';
import { Validator } from '@cfworker/json-schema';

const schemas = JSON.parse(readFileSync('src/generated/schemas.json', 'utf8'));
const validators = new Map();
function check(name, payload) {
  if (!validators.has(name)) validators.set(name, new Validator({ $ref: `#/components/schemas/${name}`, components: { schemas } }, '2020-12', false));
  const r = validators.get(name).validate(payload);
  return [r.valid, r.errors.slice(0, 3).map((e) => `${e.instanceLocation} ${e.error}`).join(' | ')];
}

const ULID = '01J8Z6R3G2X9K7M4N1P5Q8S2T6';
const NOTE = { tried: 'a', happened: 'b', limitations: 'c', next_step: 'd' };
const FIELDS = { would_refute: 'x', how_to_check: 'y' };
const INDEP = { execution: 'unknown', implementation: 'unknown', data: 'unknown', design: 'unknown' };
const receipt = (extra) => ({ kind: 'review', outcome: 'concerns', run_id: ULID, checked_md: 'c', not_checked_md: 'n', method_md: 'm', observations_md: 'o', independence: INDEP, relationships_md: 'none', ...extra });
const contribution = (extra) => ({ project_id: 'p', kind: 'result', title: 't', claim: 'c', note: NOTE, fields: FIELDS, run_id: ULID, ...extra });

const cases = [
  ['ContributionCreate valid result', 'ContributionCreate', contribution({}), true],
  ['ContributionCreate result without evidence', 'ContributionCreate', contribution({ fields: {} }), false],
  ['ContributionCreate prediction without spec', 'ContributionCreate', contribution({ kind: 'prediction' }), false],
  ['ContributionCreate prediction with spec', 'ContributionCreate', contribution({ kind: 'prediction', fields: {}, prediction: { statement: 's', outcome_spec_md: 'o', criteria_md: 'c', prior_access_md: 'p', deadline: '2027-01-01', resolver_id: ULID } }), true],
  ['ContributionCreate unknown field', 'ContributionCreate', contribution({ author_id: ULID }), false],
  ['ContributionCreate kind other minimal', 'ContributionCreate', contribution({ kind: 'other', fields: {} }), true],
  ['ContributorRegistration valid', 'ContributorRegistration', { handle: 'abc', display_name: 'A', kind: 'agent', agreed_skill_version: '1.1.1', credential: { token_hash: 'a'.repeat(64) } }, true],
  ['ContributorRegistration with author_id', 'ContributorRegistration', { handle: 'abc', display_name: 'A', kind: 'agent', agreed_skill_version: '1.1.1', credential: { token_hash: 'a'.repeat(64) }, author_id: ULID }, false],
  ['ContributorRegistration without credential', 'ContributorRegistration', { handle: 'abc', display_name: 'A', kind: 'agent', agreed_skill_version: '1.1.1' }, false],
  ['ReceiptCreate review concerns', 'ReceiptCreate', receipt({}), true],
  ['ReceiptCreate review with reproduction outcome', 'ReceiptCreate', receipt({ outcome: 'matched' }), false],
  ['ReceiptCreate reproduction matched', 'ReceiptCreate', receipt({ kind: 'reproduction', outcome: 'matched' }), true],
  ['ReceiptCreate external scored without evaluation', 'ReceiptCreate', receipt({ kind: 'external_evaluation', outcome: 'scored' }), false],
  ['ReceiptCreate external scored without score', 'ReceiptCreate', receipt({ kind: 'external_evaluation', outcome: 'scored', evaluation: { evaluator: 'e', evaluator_version: '1', submission_sha256: 'b'.repeat(64) } }), false],
  ['ReceiptCreate external scored complete', 'ReceiptCreate', receipt({ kind: 'external_evaluation', outcome: 'scored', evaluation: { evaluator: 'e', evaluator_version: '1', submission_sha256: 'b'.repeat(64), score: 1.5 } }), true],
  ['ReceiptCreate unknown field', 'ReceiptCreate', receipt({ author_id: ULID }), false],
  ['ArtifactCreate external without url', 'ArtifactCreate', { kind: 'document', name: 'n', storage: 'external', license: 'CC-BY-4.0' }, false],
  ['ArtifactCreate external with url', 'ArtifactCreate', { kind: 'document', name: 'n', storage: 'external', license: 'CC-BY-4.0', external_url: 'https://example.org/x' }, true],
  ['ArtifactCreate r2 without hash', 'ArtifactCreate', { kind: 'data', name: 'n', storage: 'r2', license: 'CC-BY-4.0', byte_size: 10 }, false],
  ['ArtifactCreate r2 complete', 'ArtifactCreate', { kind: 'data', name: 'n', storage: 'r2', license: 'CC-BY-4.0', byte_size: 10, claimed_sha256: 'c'.repeat(64) }, true],
  ['ResolutionCreate without disclosures', 'ResolutionCreate', { outcome: 'supported', run_id: ULID, checked_md: 'c', not_checked_md: 'n', method_md: 'm', observations_md: 'o' }, false],
  ['ResolutionCreate complete', 'ResolutionCreate', { outcome: 'supported', run_id: ULID, checked_md: 'c', not_checked_md: 'n', method_md: 'm', observations_md: 'o', independence: INDEP, relationships_md: 'none' }, true],
  ['RunDeclaration valid', 'RunDeclaration', { model: 'm', harness: 'h' }, true],
  ['RunDeclaration unknown field', 'RunDeclaration', { model: 'm', contributor_id: ULID }, false],
  ['ProjectCreate challenge without contract', 'ProjectCreate', { slug: 'ab', title: 't', kind: 'challenge', brief_md: 'b' }, false],
  ['ProjectCreate challenge with contract', 'ProjectCreate', { slug: 'ab', title: 't', kind: 'challenge', brief_md: 'b', contract: { body_md: 'rules', change_summary: 'first' } }, true],
  ['ModerationActionCreate set_tier without tier', 'ModerationActionCreate', { action: 'set_tier', target_type: 'contributor', target_id: ULID, public_reason: 'r' }, false],
];

let failed = 0;
for (const [label, schema, payload, want] of cases) {
  const [valid, errors] = check(schema, payload);
  const ok = valid === want;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : `  (valid=${valid}; ${errors})`}`);
}
console.log(failed ? `${failed} mismatches` : `all ${cases.length} validator cases agree`);
process.exit(failed ? 1 : 0);
