"""Narrow review-0003 probes for challenge version triggers and objection scopes.

Uses synthetic records in SQLite only. No HTTP, deployment, or research code.
The version-change case tests transaction ordering, not concurrent HTTP traffic.
"""

import argparse
import hashlib
import json
import platform
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["migrations/0001_init.sql", "api/openapi.yaml", "skill.md", "docs/data-model.md"]
NOW = "2026-09-07T12:00:00Z"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = []

    def record(name, expected, actual, detail=None):
        checks.append(dict(name=name, expected=expected, actual=actual, passed=expected == actual, detail=detail))

    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript((ROOT / SOURCES[0]).read_text(encoding="utf-8"))

    def insert(table, **values):
        db.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))

    for person in ["author", "reviewer"]:
        insert("contributors", id=person, handle=person, display_name=person, kind="agent", agreed_skill_version="1.1.1", created_at=NOW)
        insert("runs", id=person + "-run", contributor_id=person, created_at=NOW)
    for project, kind, contract_version in [("challenge", "challenge", 1), ("ordinary", "project", 0)]:
        insert("projects", id=project, slug=project, title=project, kind=kind, brief_md="Fixture", contract_version=contract_version, created_by="author", created_at=NOW, updated_at=NOW)
    insert("project_contracts", project_id="challenge", version=1, body_md="Rules one", change_summary="Initial", author_id="author", created_at=NOW)
    for contribution, project in [("work", "challenge"), ("empty", "challenge"), ("ordinary-work", "ordinary")]:
        insert("contributions", id=contribution, project_id=project, kind="result", author_id="author", created_at=NOW)

    def revision(contribution, number, contract_version):
        insert("contribution_revisions", contribution_id=contribution, revision=number, title="Fixture", claim="Fixture", note_json=json.dumps(dict(tried="Fixture", happened="Fixture", limitations="No runtime", next_step="Review")), fields_json=json.dumps(dict(how_to_check="Inspect", would_refute="Counterexample")), contract_version=contract_version, author_id="author", run_id="author-run", created_at=NOW)

    revision("work", 1, 1)

    def probe_version(name, contribution, number, supplied, should_accept):
        db.execute("SAVEPOINT version_probe")
        before = db.execute("SELECT count(*) FROM contribution_revisions").fetchone()[0]
        accepted, error = True, None
        try:
            revision(contribution, number, supplied)
        except sqlite3.IntegrityError as exc:
            accepted, error = False, str(exc)
        after = db.execute("SELECT count(*) FROM contribution_revisions").fetchone()[0]
        db.execute("ROLLBACK TO version_probe")
        db.execute("RELEASE version_probe")
        record(name, should_accept, accepted, {"supplied_version": supplied, "sqlite_error": error})
        record(name + ":row_count", before + int(should_accept), after)

    probe_version("first_challenge_revision_missing", "empty", 1, None, False)
    probe_version("first_challenge_revision_stale", "empty", 1, 0, False)
    probe_version("first_challenge_revision_future", "empty", 1, 99, False)
    probe_version("first_challenge_revision_current", "empty", 1, 1, True)
    probe_version("later_challenge_revision_missing", "work", 2, None, False)
    probe_version("ordinary_revision_missing", "ordinary-work", 1, None, True)

    previously_read_version = db.execute("SELECT contract_version FROM projects WHERE id='challenge'").fetchone()[0]
    insert("project_contracts", project_id="challenge", version=2, body_md="Rules two", change_summary="Changed", author_id="author", created_at=NOW)
    db.execute("UPDATE projects SET contract_version=2,contract_md='Rules two' WHERE id='challenge'")
    probe_version("first_submission_after_rules_changed", "empty", 1, previously_read_version, False)
    probe_version("later_revision_after_rules_changed", "work", 2, previously_read_version, False)
    probe_version("later_revision_current_rules", "work", 2, 2, True)
    record("earlier_contract_binding_preserved", 1, db.execute("SELECT contract_version FROM contribution_revisions WHERE contribution_id='work' AND revision=1").fetchone()[0])
    revision("work", 2, 2)

    insert("receipts", id="receipt-one", contribution_id="work", revision=1, kind="reproduction", outcome="matched", author_id="reviewer", run_id="reviewer-run", checked_md="Fixture", not_checked_md="HTTP", method_md="SQLite", observations_md="Fixture", independence_json=json.dumps(dict.fromkeys(["execution", "implementation", "data", "design"], "unknown")), relationships_md="Synthetic shared operator", created_at=NOW)
    insert("objections", id="objection-one", target_type="receipt", target_id="receipt-one", kind="provenance", body_md="Disputed fixture", author_id="author", created_at=NOW)
    for current_revision in [1, 2]:
        db.execute("UPDATE contributions SET current_revision=? WHERE id='work'", (current_revision,))
        for receipt_status in ["active", "corrected", "withdrawn", "hidden", "redacted"]:
            db.execute("UPDATE receipts SET status=? WHERE id='receipt-one'", (receipt_status,))
            for objection_status in ["open", "answered", "resolved", "withdrawn", "hidden"]:
                db.execute("UPDATE objections SET status=? WHERE id='objection-one'", (objection_status,))
                observed = list(db.execute("SELECT receipt_objections_unresolved,historical_objections_unresolved,objections_unresolved FROM contribution_facets WHERE contribution_id='work'").fetchone())
                eligible = receipt_status in {"active", "corrected", "withdrawn"} and objection_status in {"open", "answered"}
                expected = [int(eligible and current_revision == 1), int(eligible and current_revision == 2), int(eligible and current_revision == 1)]
                record(f"receipt_objection_scope:r{current_revision}/{receipt_status}/{objection_status}", expected, observed)
    record("foreign_key_check", [], [list(row) for row in db.execute("PRAGMA foreign_key_check")])
    record("contract_versions_retained", [1, 2], [row[0] for row in db.execute("SELECT version FROM project_contracts WHERE project_id='challenge' ORDER BY version")])
    record("api_skill_versions", {"api_version": "1.1.1", "skill_version": "1.1.1"}, dict(db.execute("SELECT key,value FROM schema_meta WHERE key IN ('api_version','skill_version')")))
    report = dict(reviewed_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), generated_at=datetime.now(timezone.utc).isoformat(),
                  scope="Two narrow fixes: SQLite insertion triggers and historical receipt-objection scopes; no HTTP or D1 deployment.",
                  environment=dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version),
                  sources=[dict(path=p, git_blob=subprocess.check_output(["git", "hash-object", p], cwd=ROOT, text=True).strip(), sha256=hashlib.sha256((ROOT / p).read_bytes()).hexdigest()) for p in SOURCES],
                  checks=checks, passed=sum(c["passed"] for c in checks), failed=sum(not c["passed"] for c in checks))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["reviewed_commit", "passed", "failed"]}, indent=2))
    for check in checks:
        if not check["passed"]:
            print("FAILED:", json.dumps(check))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
