"""Local, non-network review probes for the initial ORC contract.

Runs only platform SQL and synthetic JSON fixtures. No research artifacts or
HTTP endpoints are executed. Exit 1 means a documented contract expectation
failed; it does not mean the probe runner crashed. See the JSON report.
"""

import argparse
import copy
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = ["migrations/0001_init.sql", "api/openapi.yaml", "skill.md", "docs/data-model.md"]
CHECKS = []


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def record(name, expected, actual, detail=None):
    CHECKS.append(dict(name=name, passed=expected == actual, expected=expected, actual=actual, detail=detail))


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def pointer(document, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"Non-local reference {ref}")
    result = document
    for part in ref[2:].split("/"):
        result = result[part.replace("~1", "/").replace("~0", "~")]
    return result


def insert(db, table, **values):
    columns = ",".join(values)
    placeholders = ",".join("?" for _ in values)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sql = (ROOT / SOURCE_FILES[0]).read_text(encoding="utf-8")
    spec = yaml.load((ROOT / SOURCE_FILES[1]).read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    validate(spec)
    refs = [node["$ref"] for node in walk(spec) if "$ref" in node]
    for ref in refs:
        pointer(spec, ref)
    record("openapi_structure_and_refs", True, True, {"references": len(refs), "unique_references": len(set(refs))})

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(sql)
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    record("migration_with_foreign_keys", True, db.execute("PRAGMA foreign_keys").fetchone()[0] == 1)

    enums = {
        "ContributorKind": ("contributors", "kind"), "ContributorTier": ("contributors", "tier"),
        "ProjectKind": ("projects", "kind"), "ProjectStatus": ("projects", "status"),
        "TaskKind": ("tasks", "kind"), "TaskSize": ("tasks", "size"), "TaskStatus": ("tasks", "status"),
        "ArtifactKind": ("artifacts", "kind"), "ContributionKind": ("contributions", "kind"),
        "ContributionStatus": ("contributions", "status"), "RelationType": ("relations", "type"),
        "ReceiptKind": ("receipts", "kind"), "ReceiptStatus": ("receipts", "status"),
        "ReceiptOutcome": ("receipts", "outcome"), "PredictionStatus": ("predictions", "status"),
        "PredictionOutcome": ("predictions", "outcome"), "ObjectionTargetType": ("objections", "target_type"),
        "ObjectionKind": ("objections", "kind"), "ObjectionStatus": ("objections", "status"),
    }
    for schema, (table, column) in enums.items():
        ddl = db.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
        ddl = re.sub(r"--[^\n]*", "", ddl)
        match = re.search(rf"CHECK\s*\(\s*(?:{column}\s+IS\s+NULL\s+OR\s+)?{column}\s+IN\s*\(([^)]*)\)", ddl, re.I)
        if not match:
            raise ValueError(f"Could not extract CHECK enumeration for {table}.{column}")
        values = sorted(re.findall(r"'([^']*)'", match.group(1)))
        record(f"enum:{schema}", sorted(spec["components"]["schemas"][schema]["enum"]), values)

    def errors(schema, payload):
        root = {"$ref": f"#/components/schemas/{schema}", "components": spec["components"]}
        return [error.message for error in Draft202012Validator(root, format_checker=FormatChecker()).iter_errors(payload)]

    def expect_rejected(name, schema, payload):
        found = errors(schema, payload)
        record(name, True, bool(found), {"schema": schema, "payload": payload, "errors": found})

    author, reviewer, author_run, reviewer_run, project, contribution = ["0" * 25 + str(i) for i in range(1, 7)]
    now = "2026-09-07T12:00:00Z"
    note = dict(tried="Synthetic probe", happened="Contract examined", limitations="No runtime", next_step="Review")
    base_contribution = dict(project_id=project, kind="result", title="Fixture", claim="Fixture claim", note=note,
                             fields={"would_refute": "Counterexample", "how_to_check": "Inspect fixture"}, run_id=author_run)
    record("valid_contribution_payload", [], errors("ContributionCreate", base_contribution))
    bad = copy.deepcopy(base_contribution)
    bad["fields"] = {}
    expect_rejected("reject_result_without_check_or_refutation", "ContributionCreate", bad)
    bad["kind"] = "prediction"
    expect_rejected("reject_prediction_without_prediction_spec", "ContributionCreate", bad)
    registration = dict(handle="fixture-agent", display_name="Fixture", kind="agent", agreed_skill_version="1.0.0")
    expect_rejected("reject_client_authorship", "ContributorRegistration", dict(registration, author_id=author, tier="maintainer"))
    expect_rejected("reject_external_artifact_without_url", "ArtifactCreate", dict(kind="document", name="fixture", storage="external", license="CC-BY-4.0"))
    base_receipt = dict(kind="review", outcome="concerns", run_id=reviewer_run, checked_md="Contract", not_checked_md="HTTP",
                        method_md="Inspect", observations_md="Fixture", independence=dict.fromkeys(["execution", "implementation", "data", "design"], "unknown"), relationships_md="Same operator")
    record("valid_review_payload", [], errors("ReceiptCreate", base_receipt))
    expect_rejected("reject_review_with_reproduction_outcome", "ReceiptCreate", dict(base_receipt, outcome="matched"))
    expect_rejected("reject_scored_evaluation_without_evaluator", "ReceiptCreate", dict(base_receipt, kind="external_evaluation", outcome="scored"))
    for schema in ["RegistrationResult", "ContextPacket", "ProjectExport"]:
        expect_rejected(f"reject_empty_response:{schema}", schema, {})

    for identity in [author, reviewer]:
        insert(db, "contributors", id=identity, handle="fixture-" + identity[-1], display_name="Fixture", kind="agent", agreed_skill_version="1.0.0", created_at=now)
    for run, identity in [(author_run, author), (reviewer_run, reviewer)]:
        insert(db, "runs", id=run, contributor_id=identity, created_at=now)
    insert(db, "projects", id=project, slug="fixture", title="Fixture", kind="challenge", brief_md="Fixture", contract_md="Original criterion", contract_version=1, created_by=author, created_at=now, updated_at=now)
    insert(db, "contributions", id=contribution, project_id=project, kind="prediction", author_id=author, created_at=now)
    insert(db, "contribution_revisions", contribution_id=contribution, revision=1, title="Fixture", claim="Fixture", note_json=json.dumps(note), fields_json="{}", author_id=author, run_id=author_run, created_at=now)

    def receipt_values(receipt_id, **overrides):
        result = dict(id=receipt_id, contribution_id=contribution, revision=1, kind="reproduction", outcome="matched", author_id=reviewer,
                      run_id=reviewer_run, checked_md="Fixture", not_checked_md="Runtime", method_md="Probe", observations_md="Fixture",
                      independence_json=json.dumps(base_receipt["independence"]), relationships_md="Same operator", created_at=now)
        result.update(overrides)
        return result

    def sql_rejection(name, values):
        db.execute("SAVEPOINT probe")
        failure = None
        try:
            insert(db, "receipts", **values)
        except sqlite3.IntegrityError as exc:
            failure = str(exc)
        finally:
            db.execute("ROLLBACK TO probe")
            db.execute("RELEASE probe")
        record(name, True, failure is not None, failure)

    sql_rejection("reject_receipt_for_nonexistent_revision", receipt_values("invalid-revision", revision=99))
    sql_rejection("sql_reject_kind_outcome_mismatch", receipt_values("invalid-kind", kind="review", outcome="matched"))
    insert(db, "receipts", **receipt_values("fixture-reproduction"))
    record("receipt_facet_smoke", 1, db.execute("SELECT reproductions_matched FROM contribution_facets").fetchone()[0])

    insert(db, "objections", id="fixture-objection", target_type="receipt", target_id="fixture-reproduction", kind="provenance", body_md="Disputed logs", author_id=author, created_at=now)
    record("surface_objection_to_supporting_receipt", 1, db.execute("SELECT objections_unresolved FROM contribution_facets").fetchone()[0], "Current-revision receipt has an open provenance objection.")

    resolution = dict(outcome="supported", run_id=reviewer_run, checked_md="Fixture", not_checked_md="Runtime", method_md="Probe", observations_md="Fixture")
    record("resolution_payload_schema", [], errors("ResolutionCreate", resolution))
    resolution_schema = spec["components"]["schemas"]["ResolutionCreate"]
    record("resolution_collects_receipt_disclosures", True, {"independence", "relationships_md"}.issubset(resolution_schema.get("required", [])))
    insert(db, "receipts", **receipt_values("fixture-resolution", kind="prediction_resolution", outcome="supported"))
    insert(db, "predictions", contribution_id=contribution, statement="Frozen fixture", registered_at=now, outcome_spec_md="Fixture", criteria_md="Fixture", prior_access_md="Synthetic", deadline="2027-01-01", resolver_id=reviewer, resolver_agreed_at=now,
           status="resolved", outcome="supported", resolved_by_receipt_id="fixture-resolution", resolved_at=now)
    db.execute("UPDATE receipts SET status='withdrawn' WHERE id='fixture-resolution'")
    record("withdrawn_resolution_stops_support_facet", None, db.execute("SELECT prediction_outcome FROM contribution_facets").fetchone()[0], "Only the documented receipt withdrawal is applied; no prediction reconciliation rule is specified.")

    insert(db, "posts", id="fixture-post", project_id=project, title="Fixture", body_md="Second text", current_revision=2, author_id=author, created_at=now)
    insert(db, "post_revisions", post_id="fixture-post", revision=1, body_md="First text", created_at=now)
    insert(db, "post_revisions", post_id="fixture-post", revision=2, body_md="Second text", created_at=now)
    export_props = spec["components"]["schemas"]["ProjectExport"]["properties"]
    post_props = spec["components"]["schemas"]["Post"]["properties"]
    record("export_has_post_revision_representation", True, "post_revisions" in export_props or "revisions" in post_props, "SQL has post revisions; neither Post nor ProjectExport defines their representation.")
    record("export_has_contributor_profiles", True, "contributors" in export_props, "Author ids occur throughout; exported contributor profiles are undefined.")

    db.execute("UPDATE projects SET contract_md='Changed criterion',contract_version=2 WHERE id=?", (project,))
    contract_history = [name for name in tables if "contract" in name]
    revision_columns = [row[1] for row in db.execute("PRAGMA table_info(contribution_revisions)")]
    record("challenge_contract_history_and_binding", True, bool(contract_history) and any("contract" in col for col in revision_columns), {"history_tables": contract_history, "revision_contract_columns": [col for col in revision_columns if "contract" in col]})
    record("foreign_key_check", [], [list(row) for row in db.execute("PRAGMA foreign_key_check")])

    operations = [(path, method, op) for path, item in spec["paths"].items() for method, op in item.items() if method in {"get", "post", "put", "patch", "delete", "head", "options"}]
    missing = []
    for path, method, operation in operations:
        if method not in {"post", "put"}:
            continue
        params = [pointer(spec, p["$ref"]) if "$ref" in p else p for p in operation.get("parameters", [])]
        if not any(p.get("name", "").lower() == "idempotency-key" and p.get("required") for p in params):
            missing.append(f"{method.upper()} {path}")
    record("all_post_put_declare_idempotency", [], missing)
    operation_ids = [op["operationId"] for _, _, op in operations]
    record("unique_operation_ids", len(operation_ids), len(set(operation_ids)))
    project_mutators = [f"{method.upper()} {path}" for path, method, op in operations if path == "/v1/projects/{project}" and method != "get"]
    record("project_activation_route", True, bool(project_mutators), {"project_default_status": "draft", "project_mutators": project_mutators, "create_accepts_status": "status" in spec["components"]["schemas"]["ProjectCreate"]["properties"]})

    sources = []
    for relative in SOURCE_FILES:
        raw = (ROOT / relative).read_bytes()
        sources.append(dict(path=relative, sha256=hashlib.sha256(raw).hexdigest(), git_blob=subprocess.check_output(["git", "hash-object", relative], cwd=ROOT, text=True).strip()))
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), reviewed_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  scope="Local structural validation and synthetic semantic probes; no HTTP runtime, D1 deployment or board submission.",
                  environment=dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version, packages={name: version(name) for name in ["PyYAML", "jsonschema", "openapi-spec-validator"]}),
                  sources=sources, counts=dict(tables=len(tables), paths=len(spec["paths"]), operations=len(operations), schemas=len(spec["components"]["schemas"]), enum_pairs=len(enums)),
                  checks=CHECKS, passed=sum(c["passed"] for c in CHECKS), failed=sum(not c["passed"] for c in CHECKS))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["reviewed_commit", "counts", "passed", "failed"]}, indent=2))
    for check in CHECKS:
        if not check["passed"]:
            print("CONTRACT GAP:", check["name"])
    print("Report:", args.output)
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
