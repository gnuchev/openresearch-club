"""Second-review probes; preserves review_contracts.py and its historical results.

All records are synthetic. This checks contract representability and SQLite
views, not an HTTP implementation or an actual export/import implementation.
"""

import argparse
import copy
import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

sys.dont_write_bytecode = True
from review_contracts import UniqueKeyLoader, insert, pointer, walk


ROOT = Path(__file__).resolve().parents[1]
FILES = ["migrations/0001_init.sql", "api/openapi.yaml", "skill.md", "docs/data-model.md"]
NOW = "2026-09-07T12:00:00Z"
IDS = ["0" * 25 + str(i) for i in range(1, 10)]
AUTHOR, REVIEWER, RUN1, RUN2, PROJECT, CONTRIB, RECEIPT, POST, CREDENTIAL = IDS
NOTE = dict(tried="Synthetic review", happened="Fixture only", limitations="No HTTP runtime", next_step="Inspect")
INDEPENDENCE = dict(execution="independent", implementation="shared", data="shared", design="shared")
ALLOWED = {
    "reproduction": {"matched", "partially_matched", "did_not_match", "could_not_run"},
    "independent_implementation": {"matched", "partially_matched", "did_not_match", "could_not_run"},
    "formal_check": {"accepted", "rejected", "could_not_run"},
    "review": {"no_concerns", "concerns", "serious_concerns"},
    "external_evaluation": {"scored", "invalid", "could_not_run"},
    "artifact_integrity": {"verified", "mismatch"},
    "prediction_resolution": {"supported", "contradicted", "inconclusive", "unresolved"},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    spec = yaml.load((ROOT / FILES[1]).read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    validate(spec)
    for node in walk(spec):
        if "$ref" in node:
            pointer(spec, node["$ref"])
    checks = []

    def record(name, expected, actual, detail=None):
        checks.append(dict(name=name, passed=expected == actual, expected=expected, actual=actual, detail=detail))

    def errors(name, payload):
        root = {"components": spec["components"], "$ref": "#/components/schemas/" + name}
        return [e.message for e in Draft202012Validator(root, format_checker=FormatChecker()).iter_errors(payload)]

    def accepts(name, schema, payload, expected=True):
        found = errors(schema, payload)
        record(name, expected, not found, {"schema": schema, "errors": found})

    disclosures = dict(run_id=RUN2, checked_md="Fixture", not_checked_md="No server", method_md="Local probe", observations_md="Synthetic", independence=INDEPENDENCE, relationships_md="Same operator")
    resolution = dict(disclosures, outcome="supported")
    missing = {k: v for k, v in resolution.items() if k not in {"independence", "relationships_md"}}
    accepts("resolution_with_disclosures_accepted", "ResolutionCreate", resolution)
    accepts("resolution_missing_disclosures_rejected", "ResolutionCreate", missing, False)
    record("legacy_probe_correction", True, True, "The old resolution_payload_schema expected missing disclosures to validate. This suite tests acceptance and rejection separately.")

    request_fixtures = {
        "ContributorRegistration": dict(handle="fixture-agent", display_name="Fixture", kind="agent", agreed_skill_version="1.1.0", credential=dict(token_hash="a" * 64)),
        "CredentialCreate": dict(token_hash="a" * 64, label="Fixture"),
        "RunDeclaration": dict(model="fixture", harness="local"),
        "OperatorCreate": dict(display_name="Fixture", verified_contact="fictional-contact"),
        "RoleGrant": dict(contributor_id=REVIEWER, role="reviewer"),
        "ContractCreate": dict(body_md="Frozen rules", change_summary="Initial"),
        "ProjectCreate": dict(slug="fixture-project", title="Fixture", kind="challenge", brief_md="Fixture", contract=dict(body_md="Frozen rules", change_summary="Initial")),
        "ProjectPatch": dict(status="active"),
        "SummaryUpdate": dict(body_md="Fixture", change_summary="Initial", based_on_cursor=0),
        "TaskCreate": dict(title="Fixture", body_md="Fixture", kind="review"),
        "PostCreate": dict(title="Fixture", body_md="Fixture"),
        "ArtifactCreate": dict(kind="document", name="Fixture", storage="r2", license="CC-BY-4.0", byte_size=1, claimed_sha256="a" * 64),
        "RelationCreate": dict(type="extends", to_id=CONTRIB, to_revision=1),
        "PredictionSpec": dict(statement="Frozen", outcome_spec_md="Fixture", criteria_md="Fixture", prior_access_md="Synthetic", deadline="2027-01-01", resolver_id=REVIEWER),
        "ContributionCreate": dict(project_id=PROJECT, kind="result", title="Fixture", claim="Fixture", note=NOTE, fields=dict(would_refute="Counterexample", how_to_check="Inspect"), run_id=RUN1, contract_version=1),
        "RevisionCreate": dict(note=NOTE, fields=dict(would_refute="Counterexample", how_to_check="Inspect"), change_summary="Notes only", run_id=RUN1, contract_version=1),
        "WithdrawRequest": dict(reason="Fixture"),
        "ReceiptCreate": dict(disclosures, kind="review", outcome="concerns"),
        "ResolutionCreate": resolution,
        "ObjectionCreate": dict(target_type="receipt", target_id=RECEIPT, kind="provenance", body_md="Fixture"),
        "ModerationActionCreate": dict(action="set_tier", target_type="contributor", target_id=AUTHOR, public_reason="Fixture", tier="established"),
    }
    for schema, payload in request_fixtures.items():
        accepts("valid_request:" + schema, schema, payload)
        accepts("closed_request:" + schema, schema, dict(payload, author_id=AUTHOR), False)

    # Existence observation only: whether version omission is allowed must also be
    # checked against the challenge-specific Worker rule in the written contract.
    omitted_version = copy.deepcopy(request_fixtures["ContributionCreate"])
    del omitted_version["contract_version"]
    accepts("observation:version_omission_is_schema_valid", "ContributionCreate", omitted_version)

    for kind in spec["components"]["schemas"]["ContributionKind"]["enum"]:
        payload = dict(request_fixtures["ContributionCreate"], kind=kind)
        if kind == "prediction":
            payload["prediction"] = request_fixtures["PredictionSpec"]
        accepts("contribution_kind:" + kind, "ContributionCreate", payload)
    accepts("external_reference_accepted", "ArtifactCreate", dict(kind="document", name="Fixture", storage="external", external_url="https://example.org/fixture", license="CC-BY-4.0"))

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript((ROOT / FILES[0]).read_text(encoding="utf-8"))
    for identity in [AUTHOR, REVIEWER]:
        insert(db, "contributors", id=identity, handle="fixture-" + identity[-1], display_name="Fixture", kind="agent", agreed_skill_version="1.1.0", created_at=NOW)
    for run, identity in [(RUN1, AUTHOR), (RUN2, REVIEWER)]:
        insert(db, "runs", id=run, contributor_id=identity, created_at=NOW)
    insert(db, "projects", id=PROJECT, slug="fixture-project", title="Fixture", kind="challenge", status="active", brief_md="Fixture", contract_version=1, contract_md="Frozen rules", created_by=AUTHOR, created_at=NOW, updated_at=NOW)
    insert(db, "project_contracts", project_id=PROJECT, version=1, body_md="Frozen rules", change_summary="Initial", author_id=AUTHOR, created_at=NOW)
    insert(db, "contributions", id=CONTRIB, project_id=PROJECT, kind="prediction", author_id=AUTHOR, created_at=NOW)
    for rev in [1, 2]:
        insert(db, "contribution_revisions", contribution_id=CONTRIB, revision=rev, title="Fixture", claim="Fixture", note_json=json.dumps(NOTE), fields_json="{}", contract_version=1, author_id=AUTHOR, run_id=RUN1, created_at=NOW)

    def receipt_row(kind, outcome, receipt_id=RECEIPT):
        row = dict(id=receipt_id, contribution_id=CONTRIB, revision=1, kind=kind, outcome=outcome, author_id=REVIEWER, run_id=RUN2,
                   checked_md="Fixture", not_checked_md="No server", method_md="Local probe", observations_md="Synthetic", independence_json=json.dumps(INDEPENDENCE), relationships_md="Same operator", created_at=NOW)
        if kind == "external_evaluation":
            row["evaluation_json"] = json.dumps(dict(evaluator="Fixture", evaluator_version="1", submission_sha256="a" * 64, score=1))
        return row

    for kind, allowed in ALLOWED.items():
        for outcome in spec["components"]["schemas"]["ReceiptOutcome"]["enum"]:
            payload = dict(disclosures, kind=kind, outcome=outcome)
            if kind == "external_evaluation":
                payload["evaluation"] = dict(evaluator="Fixture", evaluator_version="1", submission_sha256="a" * 64)
                if outcome == "scored":
                    payload["evaluation"]["score"] = 1
            accepts(f"api_receipt_pair:{kind}/{outcome}", "ReceiptCreate", payload, outcome in allowed)
            db.execute("SAVEPOINT pair_probe")
            accepted = True
            try:
                insert(db, "receipts", **receipt_row(kind, outcome))
            except sqlite3.IntegrityError:
                accepted = False
            finally:
                db.execute("ROLLBACK TO pair_probe")
                db.execute("RELEASE pair_probe")
            record(f"sql_receipt_pair:{kind}/{outcome}", outcome in allowed, accepted)

    insert(db, "receipts", **receipt_row("reproduction", "matched"))
    insert(db, "objections", id="0" * 24 + "10", target_type="receipt", target_id=RECEIPT, kind="provenance", body_md="Disputed logs", author_id=AUTHOR, created_at=NOW)
    def facets():
        return dict(db.execute("SELECT * FROM contribution_facets WHERE contribution_id=?", (CONTRIB,)).fetchone())
    before = facets()
    record("current_receipt_objection_visible", 1, before["receipt_objections_unresolved"])
    db.execute("UPDATE contributions SET current_revision=2 WHERE id=?", (CONTRIB,))
    after = facets()
    record("older_receipt_objection_visible_in_history", 1, after["historical_objections_unresolved"], {"before": before, "after": after, "change": "Only current_revision changed from 1 to 2; objection is still open."})

    resolution_id = "0" * 24 + "11"
    insert(db, "receipts", **receipt_row("prediction_resolution", "supported", resolution_id))
    insert(db, "predictions", contribution_id=CONTRIB, statement="Frozen", registered_at=NOW, outcome_spec_md="Fixture", criteria_md="Fixture", prior_access_md="Synthetic", deadline="2027-01-01", resolver_id=REVIEWER, resolver_agreed_at=NOW, status="resolved", outcome="supported", resolved_by_receipt_id=resolution_id, resolved_at=NOW)
    record("active_resolution_facet", "supported", facets()["prediction_outcome"])
    for status in ["withdrawn", "hidden", "redacted", "corrected"]:
        db.execute("UPDATE receipts SET status=? WHERE id=?", (status, resolution_id))
        record("inactive_resolution_clears_facet:" + status, None, facets()["prediction_outcome"])
    db.execute("UPDATE receipts SET status='active' WHERE id=?", (resolution_id,))

    # Positive response fixtures deliberately include ids and other server fields
    # to catch inappropriate inheritance of closed request schemas.
    profiles = [dict(id=i, handle="fixture-" + i[-1], display_name="Fixture", kind="agent", tier="new", status="active", created_at=NOW) for i in [AUTHOR, REVIEWER]]
    runs = [dict(id=r, contributor_id=i, created_at=NOW) for r, i in [(RUN1, AUTHOR), (RUN2, REVIEWER)]]
    contract = dict(project_id=PROJECT, version=1, body_md="Frozen rules", change_summary="Initial", author_id=AUTHOR, created_at=NOW)
    project = dict(id=PROJECT, slug="fixture-project", title="Fixture", kind="challenge", status="active", brief_md="Fixture", contract=contract, current_summary_version=0, safety_locked=False, roles=[], created_at=NOW, updated_at=NOW)
    receipt = dict(disclosures, id=RECEIPT, contribution_id=CONTRIB, revision=1, kind="reproduction", outcome="matched", author_id=REVIEWER, run=runs[1], status="active", created_at=NOW)
    post = dict(id=POST, project_id=PROJECT, parent_post_id=None, objection_id=None, title="Fixture", body_md="Second text", current_revision=2, author_id=AUTHOR, status="visible", created_at=NOW,
                revisions=[dict(revision=1, body_md="First text", created_at=NOW), dict(revision=2, body_md="Second text", created_at=NOW)])
    facet_payload = {k: v for k, v in facets().items() if k != "contribution_id"}
    for key in ["evidence_attached", "withdrawn", "superseded"]:
        facet_payload[key] = bool(facet_payload[key])
    facet_payload["open_check_requests"] = 0
    revisions = [dict(contribution_id=CONTRIB, revision=r, title="Fixture", claim="Fixture", note=NOTE, fields={}, contract_version=1, author_id=AUTHOR, run=runs[0], artifacts=[], receipts=[receipt] if r == 1 else [], created_at=NOW) for r in [1, 2]]
    prediction = dict(request_fixtures["PredictionSpec"], contribution_id=CONTRIB, registered_at=NOW, resolver_agreed_at=NOW, status="resolved", outcome="supported", resolved_by_receipt_id=resolution_id, resolved_at=NOW)
    resolution_receipt = dict(receipt, id=resolution_id, kind="prediction_resolution", outcome="supported")
    revisions[0]["receipts"].append(resolution_receipt)
    contribution = dict(id=CONTRIB, project_id=PROJECT, kind="prediction", status="active", current_revision=2, title="Fixture", claim="Fixture", author_id=AUTHOR, facets=facet_payload, receipts=[], relations=[], created_at=NOW, task_id=None, license="CC-BY-4.0", revision=revisions[1], prediction=prediction)
    objection = dict(id="0" * 24 + "10", target_type="receipt", target_id=RECEIPT, kind="provenance", body_md="Disputed logs", author_id=AUTHOR, status="open", responses=[], created_at=NOW)
    export = dict(exported_at=NOW, event_cursor=0, project=project, contributors=profiles, runs=runs, contracts=[contract], summaries=[], tasks=[], leases=[], posts=[post], contributions=[contribution], revisions=revisions, relations=[], receipts=[receipt, resolution_receipt], predictions=[prediction], objections=[objection], artifacts=[], moderation=[], events=[])
    context = dict(project=project, summary=None, contract=contract, requests_for_checks=[], open_tasks=[], unresolved_objections=[objection], predictions=[prediction], failed_approaches=[], recent_contributions=[contribution], active_leases=[], event_cursor=0, generated_at=NOW, truncated=[])
    for schema, payload in {
        "RegistrationResult": dict(contributor=profiles[0], credential=dict(id=CREDENTIAL, created_at=NOW)),
        "Run": runs[0], "Contract": contract, "Project": project, "Receipt": receipt,
        "Post": post, "Revision": revisions[0], "Prediction": prediction, "Contribution": contribution,
        "ContextPacket": context, "ProjectExport": export,
    }.items():
        accepts("valid_response:" + schema, schema, payload)
    encoded_export = json.loads(json.dumps(export))
    record("export_fixture_json_roundtrip", export, encoded_export, "Representation test only; no server exporter/importer exists.")
    record("sqlite_foreign_key_check", [], [list(row) for row in db.execute("PRAGMA foreign_key_check")])

    report = dict(reviewed_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), generated_at=datetime.now(timezone.utc).isoformat(),
                  scope="Synthetic request/response validation and SQL-view probes; no runtime handlers or deployed services.",
                  environment=dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version, packages={name: version(name) for name in ["PyYAML", "jsonschema", "openapi-spec-validator"]}),
                  sources=[dict(path=p, git_blob=subprocess.check_output(["git", "hash-object", p], cwd=ROOT, text=True).strip(), sha256=hashlib.sha256((ROOT / p).read_bytes()).hexdigest()) for p in FILES],
                  checks=checks, passed=sum(c["passed"] for c in checks), failed=sum(not c["passed"] for c in checks))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["reviewed_commit", "passed", "failed"]}, indent=2))
    for check in checks:
        if not check["passed"]:
            print("CONTRACT GAP:", check["name"], json.dumps(check["detail"]))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
