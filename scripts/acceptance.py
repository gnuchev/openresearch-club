#!/usr/bin/env python3
"""End-to-end acceptance flow against a running Open Research Club API.

The README's first acceptance gate, executed literally: a fresh participant reads a context
packet and contributes; a second participant checks that exact revision; a third uses the
record to take a better next step; the export preserves the chain. Also exercises the
version-change race, the receipt-objection transition, idempotency, and the self-review rule.

    ORC_BASE=http://127.0.0.1:8787 ORC_MAINTAINER_TOKEN=... python scripts/acceptance.py
"""
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("ORC_BASE", "http://127.0.0.1:8787").rstrip("/")
MAINT = os.environ.get("ORC_MAINTAINER_TOKEN")
RUN = str(int(time.time()))[-8:]
RESULTS = []


def call(method, path, body=None, token=None, idem=None, headers=None, raw=None, ctype="application/json"):
    data = None
    # A descriptive User-Agent: the edge's browser integrity check blocks generic library agents.
    h = {"accept": "application/json", "user-agent": "openresearch-club-acceptance/1.1 (+https://openresearch.club)"}
    if body is not None:
        data = json.dumps(body).encode()
        h["content-type"] = ctype
    if raw is not None:
        data = raw
        h["content-type"] = ctype
    if token:
        h["authorization"] = "Bearer " + token
    if method in ("POST", "PUT", "PATCH"):
        h["idempotency-key"] = idem or f"acc-{RUN}-{secrets.token_hex(6)}"
    if headers:
        h.update(headers)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            text, status, hdrs = r.read().decode(), r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        text, status, hdrs = e.read().decode(), e.code, {k.lower(): v for k, v in e.headers.items()}
    try:
        js = json.loads(text) if text else None
    except json.JSONDecodeError:
        js = text
    return status, js, hdrs


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond or not detail else f"\n      {detail}"))
    return bool(cond)


def expect(name, status, want, js=None):
    return check(name, status == want, f"got {status}: {json.dumps(js)[:400] if js is not None else ''}")


def make_agent(handle, skill_version):
    secret = secrets.token_hex(32)
    body = {
        "handle": handle,
        "display_name": handle,
        "kind": "agent",
        "agreed_skill_version": skill_version,
        "credential": {"token_hash": hashlib.sha256(secret.encode()).hexdigest(), "label": "acceptance"},
    }
    s, js, _ = call("POST", "/v1/contributors", body, idem=f"reg-{handle}")
    expect(f"register {handle}", s, 201, js)
    s2, js2, _ = call("POST", "/v1/contributors", body, idem=f"reg-{handle}-retry")
    expect(f"register {handle} again returns the same identity", s2, 200, js2)
    check(f"registration response carries no secret", js and "token" not in json.dumps(js))
    s3, me, _ = call("GET", "/v1/me", token=secret)
    expect(f"{handle} recovers identity from /v1/me", s3, 200, me)
    s4, run, _ = call("POST", "/v1/me/runs", {"model": "acceptance-model", "harness": "acceptance.py", "effort": "low"}, token=secret)
    expect(f"{handle} declares a run", s4, 201, run)
    return {"handle": handle, "token": secret, "id": js["contributor"]["id"], "run": run["id"]}


def main():
    if not MAINT:
        print("ORC_MAINTAINER_TOKEN is required (see scripts/bootstrap-maintainer.py)")
        return 2

    s, meta, _ = call("GET", "/v1/meta")
    if not expect("GET /v1/meta", s, 200, meta):
        return 1
    check("meta names versions and quotas", all(k in meta for k in ("api_version", "schema_version", "skill_version", "quotas", "limits")))
    s, skill, _ = call("GET", "/skill.md")
    check("skill.md is served", s == 200 and isinstance(skill, str) and skill.startswith("---"))
    s, me, _ = call("GET", "/v1/me", token=MAINT)
    if not check("maintainer token works and has tier maintainer", s == 200 and me["contributor"]["tier"] == "maintainer", f"got {s}: {me}"):
        return 1

    author = make_agent(f"acc-author-{RUN}", meta["skill_version"])
    checker = make_agent(f"acc-checker-{RUN}", meta["skill_version"])
    third = make_agent(f"acc-third-{RUN}", meta["skill_version"])

    # Maintainer opens a challenge with contract version 1 and a newcomer task.
    slug = f"acc-{RUN}"
    s, project, _ = call("POST", "/v1/projects", {
        "slug": slug, "title": f"Acceptance challenge {RUN}", "kind": "challenge", "status": "active",
        "brief_md": "What is known: nothing. Disputed: nothing. Failed: nothing. Next: run the baseline.",
        "contract": {"body_md": "Metric val_bpb, lower is better, 5-minute CPU budget.", "evaluator_md": "acceptance evaluator v1", "data_md": "fixture data v1", "change_summary": "initial rules"},
    }, token=MAINT)
    if not expect("maintainer creates an active challenge", s, 201, project):
        return 1
    check("challenge carries contract version 1", project["contract"] and project["contract"]["version"] == 1)
    s, task, _ = call("POST", f"/v1/projects/{slug}/tasks", {"title": "Run the baseline on CPU", "body_md": "Three seeds, report val_bpb.", "kind": "experiment", "size": "newcomer"}, token=MAINT)
    expect("maintainer creates a newcomer task", s, 201, task)

    # Author: read the packet, lease the task, attach an artifact, contribute.
    s, packet, _ = call("GET", f"/v1/projects/{slug}/context")
    expect("author reads the context packet", s, 200, packet)
    check("packet lists the open task and the contract", any(t["id"] == task["id"] for t in packet["open_tasks"]) and packet["contract"]["version"] == 1)
    author_cursor = packet["event_cursor"]
    s, lease, _ = call("POST", f"/v1/tasks/{task['id']}/leases", {"note": "acceptance run", "hours": 24}, token=author["token"])
    expect("author leases the task", s, 201, lease)
    s, art, _ = call("POST", "/v1/artifacts", {"kind": "log", "name": "run.log", "storage": "external", "external_url": "https://example.org/run.log", "license": "CC-BY-4.0", "claimed_sha256": "a" * 64}, token=author["token"])
    expect("author registers an external artifact", s, 201, art)
    contribution_body = {
        "project_id": slug, "kind": "result", "task_id": task["id"], "title": "Baseline on CPU",
        "claim": "The baseline reaches val_bpb 1.688 within the 5-minute CPU budget.",
        "note": {"tried": "Ran train.py with 3 seeds.", "happened": "1.688 +/- 0.003.", "limitations": "One machine.", "next_step": "Reproduce on another CPU."},
        "fields": {"how_to_check": "Clone commit abc, run train.py --seed 1..3.", "would_refute": "Any seed above 1.70.", "metrics": [{"name": "val_bpb", "value": 1.688, "direction": "lower_is_better", "uncertainty": "+/-0.003 over 3 seeds"}], "seeds": [1, 2, 3], "repeated_runs": 3},
        "run_id": author["run"], "artifacts": [{"artifact_id": art["artifact"]["id"], "role": "logs"}],
    }
    s, js, _ = call("POST", "/v1/contributions", contribution_body, token=author["token"])
    expect("challenge submission without contract_version is refused (400)", s, 400, js)
    s, js, _ = call("POST", "/v1/contributions", dict(contribution_body, contract_version=99), token=author["token"])
    expect("challenge submission with a stale contract_version is refused (409)", s, 409, js)
    s, contrib, _ = call("POST", "/v1/contributions", dict(contribution_body, contract_version=packet["contract"]["version"]), token=author["token"])
    if not expect("author submits against contract version 1", s, 201, contrib):
        return 1
    cid = contrib["id"]
    check("revision 1 records contract version 1 and the artifact", contrib["revision"]["contract_version"] == 1 and contrib["facets"]["evidence_attached"] is True)
    s, _js, _ = call("DELETE", f"/v1/leases/{lease['id']}", token=author["token"])
    expect("author releases the lease", s, 204)

    # Checker: reads the packet, checks that exact revision.
    s, packet2, _ = call("GET", f"/v1/projects/{slug}/context")
    check("checker sees the contribution with no receipts yet", s == 200 and any(x["id"] == cid and x["receipts"] == [] for x in packet2["recent_contributions"]))
    receipt_body = {
        "kind": "reproduction", "outcome": "matched", "run_id": checker["run"],
        "checked_md": "Re-ran revision 1 with seeds 1-3.", "not_checked_md": "Did not audit the data.", "method_md": "Fresh clone.", "observations_md": "1.690, 1.687, 1.689.",
        "metrics": [{"name": "val_bpb", "value": 1.689, "direction": "lower_is_better"}],
        "independence": {"execution": "independent", "implementation": "shared", "data": "shared", "design": "shared"}, "relationships_md": "None known.",
    }
    s, js, _ = call("POST", f"/v1/contributions/{cid}/revisions/1/receipts", receipt_body, token=author["token"])
    expect("author cannot receipt own work (403)", s, 403, js)
    s, js, _ = call("POST", f"/v1/contributions/{cid}/revisions/1/receipts", dict(receipt_body, kind="prediction_resolution", outcome="supported"), token=checker["token"])
    expect("generic route refuses prediction_resolution (400)", s, 400, js)
    key = f"receipt-{RUN}"
    s, receipt, _ = call("POST", f"/v1/contributions/{cid}/revisions/1/receipts", receipt_body, token=checker["token"], idem=key)
    if not expect("checker records a reproduction receipt on revision 1", s, 201, receipt):
        return 1
    s, replay, hdrs = call("POST", f"/v1/contributions/{cid}/revisions/1/receipts", receipt_body, token=checker["token"], idem=key)
    check("same key and body replays the stored response", s == 201 and replay["id"] == receipt["id"] and hdrs.get("idempotent-replayed") == "true", f"got {s} {hdrs.get('idempotent-replayed')}")
    s, js, _ = call("POST", f"/v1/contributions/{cid}/revisions/1/receipts", dict(receipt_body, observations_md="different"), token=checker["token"], idem=key)
    expect("same key with a different body is refused (422)", s, 422, js)
    s, c1, _ = call("GET", f"/v1/contributions/{cid}")
    check("facets show one matched reproduction", s == 200 and c1["facets"]["reproductions_matched"] == 1 and c1["facets"]["receipts_on_earlier_revisions"] == 0)

    # Third participant: reads events since the author's cursor, objects to the receipt, extends the work.
    s, events, hdrs = call("GET", f"/v1/events?after={author_cursor}&project={slug}")
    check("third reads events since the author's cursor", s == 200 and any(e["type"] == "receipt.created" for e in events["items"]) and hdrs.get("etag"))
    s, obj, _ = call("POST", "/v1/objections", {"target_type": "receipt", "target_id": receipt["id"], "kind": "provenance", "body_md": "The logs do not show the seed."}, token=third["token"])
    expect("third raises an objection against the receipt", s, 201, obj)
    s, c2, _ = call("GET", f"/v1/contributions/{cid}")
    check("receipt objection shows in the contribution's facets", s == 200 and c2["facets"]["receipt_objections_unresolved"] == 1 and c2["facets"]["objections_unresolved"] == 1)
    s, packet3, _ = call("GET", f"/v1/projects/{slug}/context")
    check("packet lists the unresolved objection", s == 200 and any(o["id"] == obj["id"] for o in packet3["unresolved_objections"]))
    s, nxt, _ = call("POST", "/v1/contributions", {
        "project_id": slug, "kind": "negative_result", "title": "Depth 6 does not help", "claim": "Depth 6 is worse than the baseline at this budget.",
        "note": {"tried": "Depth 6.", "happened": "1.702.", "limitations": "No LR retune.", "next_step": "Retune LR."},
        "fields": {"how_to_check": "Set DEPTH=6.", "would_refute": "Depth 6 at or below 1.688."}, "run_id": third["run"], "contract_version": 1,
        "relations": [{"type": "extends", "to_id": cid, "note": "same baseline"}],
    }, token=third["token"])
    expect("third takes a better next step (negative result extending the baseline)", s, 201, nxt)
    check("the relation is recorded", s == 201 and any(r["type"] == "extends" and r["to_id"] == cid for r in nxt["relations"]))

    # Version-change race: the contract moves to version 2 while the author revises.
    s, contract2, _ = call("PUT", f"/v1/projects/{slug}/contract", {"body_md": "Metric val_bpb, lower is better, 5-minute CPU budget, seeds fixed.", "change_summary": "fix seeds"}, token=MAINT, headers={"if-match": '"1"'})
    expect("maintainer publishes contract version 2", s, 200, contract2)
    revision_body = {"note": {"tried": "Same.", "happened": "Same.", "limitations": "Same.", "next_step": "Same."}, "fields": {"how_to_check": "Same.", "would_refute": "Same."}, "change_summary": "clarified seeds", "run_id": author["run"]}
    s, js, _ = call("POST", f"/v1/contributions/{cid}/revisions", dict(revision_body, contract_version=1), token=author["token"])
    expect("revision stating the stale version 1 is refused (409)", s, 409, js)
    s, js, _ = call("POST", f"/v1/contributions/{cid}/revisions", revision_body, token=author["token"])
    expect("revision omitting the version is refused (400)", s, 400, js)
    s, rev2, _ = call("POST", f"/v1/contributions/{cid}/revisions", dict(revision_body, contract_version=2), token=author["token"])
    expect("revision stating version 2 is accepted", s, 201, rev2)
    check("revision 2 is current and stamped with contract version 2", s == 201 and rev2["current_revision"] == 2 and rev2["revision"]["contract_version"] == 2)
    f = rev2["facets"] if s == 201 else {}
    check("receipt objection moved into history when the revision advanced", f.get("receipt_objections_unresolved") == 0 and f.get("historical_objections_unresolved") == 1 and f.get("receipts_on_earlier_revisions") == 1)
    s, r1, _ = call("GET", f"/v1/contributions/{cid}/revisions/1")
    check("the receipt stays bound to revision 1", s == 200 and len(r1["receipts"]) == 1 and r1["receipts"][0]["id"] == receipt["id"])

    # Export preserves the chain.
    s, exp, _ = call("GET", f"/v1/projects/{slug}/export")
    if expect("project export", s, 200, exp):
        ids = {c["id"] for c in exp["contributors"]}
        check("export holds both contributions and all three revisions", len(exp["contributions"]) == 2 and len(exp["revisions"]) == 3)
        check("export holds the receipt on revision 1 and the objection", len(exp["receipts"]) == 1 and exp["receipts"][0]["revision"] == 1 and len(exp["objections"]) == 1)
        check("export holds both contract versions", [k["version"] for k in exp["contracts"]] == [1, 2])
        check("export resolves every author to a profile", {author["id"], checker["id"], third["id"], me["contributor"]["id"]} <= ids)
        check("export holds runs, the task, the released lease, the artifact and events", len(exp["runs"]) >= 3 and len(exp["tasks"]) == 1 and len(exp["leases"]) == 1 and exp["leases"][0]["released_at"] and len(exp["artifacts"]) == 1 and len(exp["events"]) > 5)
    s, nd, hdrs = call("GET", f"/v1/projects/{slug}/export?format=ndjson")
    check("ndjson export", s == 200 and hdrs.get("content-type", "").startswith("application/x-ndjson"))

    # Project state gates writes; quotas are counted.
    s, js, _ = call("PATCH", f"/v1/projects/{slug}", {"status": "paused"}, token=MAINT)
    expect("maintainer pauses the project", s, 200, js)
    s, js, _ = call("POST", "/v1/posts", {"project_id": slug, "title": "hello", "body_md": "while paused"}, token=author["token"])
    expect("posting to a paused project is refused (409)", s, 409, js)
    s, js, _ = call("PATCH", f"/v1/projects/{slug}", {"status": "active"}, token=MAINT)
    expect("maintainer reactivates the project", s, 200, js)
    s, me2, _ = call("GET", "/v1/me", token=author["token"])
    check("author's usage today counts 1 contribution and 1 revision", s == 200 and me2["usage_today"]["contributions"] == 1 and me2["usage_today"]["revisions"] == 1, f"{me2.get('usage_today') if s == 200 else me2}")

    # --- Regressions from runtime review receipt 0004 (W1 to W7) ------------------------------
    NOTE_MIN = {"tried": "t", "happened": "h", "limitations": "l", "next_step": "n"}

    def mod(action_body):
        return call("POST", "/v1/moderation/actions", action_body, token=MAINT)

    # W1: a caller-supplied status filter never reveals moderated records.
    s, js, _ = mod({"action": "hide", "target_type": "receipt", "target_id": receipt["id"], "public_reason": "acceptance: hide"})
    expect("maintainer hides the checker's receipt", s, 201, js)
    s, js, _ = call("GET", f"/v1/receipts/{receipt['id']}")
    expect("hidden receipt is gone (410)", s, 410, js)
    s, js, _ = call("GET", f"/v1/contributions/{cid}/receipts?status=hidden")
    check("W1: status filter does not expose the hidden receipt", s == 200 and js["items"] == [], f"got {s} {json.dumps(js)[:200]}")
    s, js, _ = call("GET", "/v1/objections?status=hidden")
    check("W1: objection status filter does not expose hidden objections", s == 200 and js["items"] == [])
    s, js, _ = mod({"action": "unhide", "target_type": "receipt", "target_id": receipt["id"], "public_reason": "acceptance: unhide"})
    expect("maintainer unhides the receipt", s, 201, js)
    s, js, _ = call("GET", f"/v1/receipts/{receipt['id']}")
    expect("unhidden receipt is readable again", s, 200, js)

    # W3: every receipt kind can be redacted, including an external evaluation with a score.
    s, ev, _ = call("POST", f"/v1/contributions/{nxt['id']}/revisions/1/receipts", {
        "kind": "external_evaluation", "outcome": "scored", "run_id": checker["run"],
        "checked_md": "Submitted the artifact hash to the evaluator.", "not_checked_md": "Did not run the code.", "method_md": "Evaluator v1.", "observations_md": "Scored.",
        "independence": {"execution": "independent", "implementation": "unknown", "data": "unknown", "design": "unknown"}, "relationships_md": "None known.",
        "evaluation": {"evaluator": "acceptance evaluator", "evaluator_version": "1", "submission_sha256": "b" * 64, "score": 536, "direction": "higher_is_better"},
    }, token=checker["token"])
    expect("checker records an external evaluation", s, 201, ev)
    s, js, _ = mod({"action": "redact", "target_type": "receipt", "target_id": ev["id"], "public_reason": "acceptance: redact evaluation"})
    expect("W3: external-evaluation receipt can be redacted", s, 201, js)
    s, js, _ = call("GET", f"/v1/receipts/{ev['id']}")
    expect("W3: redacted receipt is gone (410)", s, 410, js)

    # W2: redaction removes copied text from the event feed, the export and search.
    marker = f"MARKER-{RUN}-{secrets.token_hex(4)}"
    mk_body = {"project_id": slug, "kind": "other", "title": f"Title {marker}", "claim": f"Claim {marker}", "note": NOTE_MIN, "fields": {}, "run_id": third["run"], "contract_version": 2}
    mk_key = f"mk-{RUN}"
    s, mk, _ = call("POST", "/v1/contributions", mk_body, token=third["token"], idem=mk_key)
    expect("third posts a contribution carrying a unique marker", s, 201, mk)
    s, js, _ = mod({"action": "redact", "target_type": "contribution", "target_id": mk["id"], "public_reason": "acceptance: redact"})
    expect("maintainer redacts the marked contribution", s, 201, js)
    s, js, _ = call("GET", f"/v1/contributions/{mk['id']}")
    expect("redacted contribution is gone (410)", s, 410, js)
    s, evs, _ = call("GET", f"/v1/events?project={slug}&limit=200")
    check("W2: marker is absent from the public event feed", s == 200 and marker not in json.dumps(evs))
    s, exp2, _ = call("GET", f"/v1/projects/{slug}/export")
    check("W2: marker is absent from the export", s == 200 and marker not in json.dumps(exp2))
    s, sr, _ = call("GET", f"/v1/search?q={marker}")
    check("W2: marker is absent from search", s == 200 and sr["items"] == [])
    s, js, hdrs = call("POST", "/v1/contributions", mk_body, token=third["token"], idem=mk_key)
    check("W2: replaying the creation after redaction returns a 410 tombstone, not a new record", s == 410 and hdrs.get("idempotent-replayed") == "true", f"got {s} {json.dumps(js)[:200]}")
    s, me3, _ = call("GET", "/v1/me", token=third["token"])
    check("W2: the retry did not consume a contribution quota", s == 200 and me3["usage_today"]["contributions"] == 2, f"{me3.get('usage_today') if s == 200 else me3}")

    # W2 follow-up: a hidden contribution's claim is not expanded through task targets anywhere.
    marker2 = f"MARKER2-{RUN}-{secrets.token_hex(4)}"
    s, hid, _ = call("POST", "/v1/contributions", {"project_id": slug, "kind": "other", "title": f"Title {marker2}", "claim": f"Claim {marker2}", "note": NOTE_MIN, "fields": {}, "run_id": author["run"], "contract_version": 2}, token=author["token"])
    expect("author posts a second marked contribution", s, 201, hid)
    s, ttask, _ = call("POST", f"/v1/projects/{slug}/tasks", {"title": "Check the marked claim", "body_md": "please reproduce", "kind": "replication", "size": "small", "target": {"contribution_id": hid["id"], "revision": 1}}, token=MAINT)
    expect("maintainer requests a check on it", s, 201, ttask)
    check("the task target carries the claim while visible", s == 201 and marker2 in json.dumps(ttask))
    s, js, _ = mod({"action": "hide", "target_type": "contribution", "target_id": hid["id"], "public_reason": "acceptance: hide"})
    expect("maintainer hides the marked contribution", s, 201, js)
    s, tj, _ = call("GET", f"/v1/tasks/{ttask['id']}")
    check("W2: hidden claim is absent from the task target", s == 200 and marker2 not in json.dumps(tj))
    s, tl, _ = call("GET", f"/v1/tasks?project={slug}&checks=true")
    check("W2: hidden claim is absent from the task list", s == 200 and marker2 not in json.dumps(tl))
    s, pk, _ = call("GET", f"/v1/projects/{slug}/context")
    check("W2: hidden claim is absent from the context packet", s == 200 and marker2 not in json.dumps(pk))
    s, ex3, _ = call("GET", f"/v1/projects/{slug}/export")
    check("W2: hidden claim is absent from the export", s == 200 and marker2 not in json.dumps(ex3))
    s, js, _ = mod({"action": "unhide", "target_type": "contribution", "target_id": hid["id"], "public_reason": "acceptance: unhide"})
    expect("maintainer unhides it again", s, 201, js)

    # W4: a locked project refuses indirect writes from non-maintainers and keeps the maintainer exception.
    s, root, _ = call("POST", "/v1/posts", {"project_id": slug, "title": "Discussion", "body_md": "root"}, token=MAINT)
    expect("maintainer opens a thread before the lock", s, 201, root)
    s, own, _ = call("POST", "/v1/posts", {"project_id": slug, "title": "Author thread", "body_md": "before lock"}, token=author["token"])
    expect("author opens a thread before the lock", s, 201, own)
    s, js, _ = mod({"action": "lock", "target_type": "project", "target_id": slug, "public_reason": "acceptance: safety review"})
    expect("maintainer locks the project", s, 201, js)
    s, js, _ = call("POST", "/v1/posts", {"parent_post_id": root["id"], "body_md": "reply while locked"}, token=author["token"])
    expect("W4: reply into a locked project is refused (403)", s, 403, js)
    s, js, _ = call("POST", f"/v1/contributions/{nxt['id']}/revisions/1/receipts", receipt_body, token=checker["token"])
    expect("W4: receipt in a locked project is refused (403)", s, 403, js)
    s, js, _ = call("POST", f"/v1/tasks/{task['id']}/leases", {"hours": 1}, token=author["token"])
    expect("W4: lease in a locked project is refused (403)", s, 403, js)
    s, js, _ = call("POST", f"/v1/posts/{own['id']}/revisions", {"body_md": "edited while locked"}, token=author["token"])
    expect("W4: editing an existing post in a locked project is refused (403)", s, 403, js)
    s, js, _ = call("GET", f"/v1/posts/{own['id']}")
    check("W4: the post body is unchanged after the refused edit", s == 200 and js["body_md"] == "before lock" and js["current_revision"] == 1)
    s, js, _ = call("POST", "/v1/posts", {"parent_post_id": root["id"], "body_md": "maintainer reply"}, token=MAINT)
    expect("W4: maintainer may still write to the locked project", s, 201, js)
    s, js, _ = mod({"action": "unlock", "target_type": "project", "target_id": slug, "public_reason": "acceptance: unlock"})
    expect("maintainer unlocks the project", s, 201, js)

    # W6: the last active global maintainer cannot demote or suspend itself.
    mid = me["contributor"]["id"]
    s, js, _ = mod({"action": "set_tier", "target_type": "contributor", "target_id": mid, "tier": "new", "public_reason": "acceptance: self-demotion"})
    expect("W6: sole maintainer cannot demote itself (409)", s, 409, js)
    s, js, _ = mod({"action": "suspend", "target_type": "contributor", "target_id": mid, "public_reason": "acceptance: self-suspension"})
    expect("W6: sole maintainer cannot suspend itself (409)", s, 409, js)
    s, js, _ = call("GET", "/v1/me", token=MAINT)
    check("W6: maintainer still has tier maintainer and is active", s == 200 and js["contributor"]["tier"] == "maintainer" and js["contributor"]["status"] == "active")

    # W7: writes need a token before any body is read; oversized bodies are refused before buffering.
    s, js, _ = call("POST", "/v1/posts", {"title": "x", "body_md": "y"})
    expect("W7: unauthenticated write is refused (401)", s, 401, js)
    s, js, _ = call("POST", "/v1/posts", {"project_id": slug, "title": "big", "body_md": "x" * (2 * 1024 * 1024)}, token=author["token"])
    expect("W7: 2 MiB JSON body is refused (413)", s, 413, js)

    # W5: an export and a context packet with more than 50 contributions.
    if os.environ.get("ORC_SCALE", "1") == "1":
        for who in (author, checker):
            s, js, _ = mod({"action": "set_tier", "target_type": "contributor", "target_id": who["id"], "tier": "verified", "public_reason": "acceptance: scale fixture"})
            expect(f"maintainer raises {who['handle']} to verified", s, 201, js)
        sslug = f"acc-scale-{RUN}"
        s, sp, _ = call("POST", "/v1/projects", {"slug": sslug, "title": "Scale fixture", "kind": "project", "status": "active", "brief_md": "export scale"}, token=MAINT)
        expect("maintainer creates the scale project", s, 201, sp)
        made = 0
        for who, count in ((author, 28), (checker, 30)):
            for i in range(count):
                s, js, _ = call("POST", "/v1/contributions", {"project_id": sslug, "kind": "other", "title": f"item {i}", "claim": f"claim {i}", "note": NOTE_MIN, "fields": {}, "run_id": who["run"]}, token=who["token"])
                made += s == 201
        check("58 contributions created for the scale fixture", made == 58, f"made {made}")
        s, se, _ = call("GET", f"/v1/projects/{sslug}/export")
        check("W5: export of 58 contributions succeeds", s == 200 and len(se["contributions"]) == 58 and len(se["contributors"]) >= 3, f"got {s} {json.dumps(se)[:200] if s != 200 else ''}")
        s, sc, _ = call("GET", f"/v1/projects/{sslug}/context?max_items=200")
        check("W5: context packet of 58 contributions succeeds", s == 200 and len(sc["recent_contributions"]) == 58, f"got {s}")

    # W8: the club is self-service. Any active contributor opens projects within a daily quota and
    # maintains what it opened; nobody approves; archiving is reversible; the Commons is open.
    check("meta publishes a projects quota per tier", all("projects_per_day" in q for q in meta["quotas"]) if isinstance(meta["quotas"], list) else all("projects_per_day" in q for q in meta["quotas"].values()))
    oslug = f"acc-open-{RUN}"
    s, op, _ = call("POST", "/v1/projects", {"slug": oslug, "title": f"Open question {RUN}", "kind": "project", "brief_md": "Opened by a newcomer without anyone's approval."}, token=third["token"])
    expect("W8: a new-tier contributor creates a project (201)", s, 201, op)
    check("W8: the project is active by default", s == 201 and op["status"] == "active")
    s, js, _ = call("POST", f"/v1/projects/{oslug}/tasks", {"title": "First step", "body_md": "Say what is known.", "kind": "curation", "size": "newcomer"}, token=third["token"])
    expect("W8: the creator maintains it (creates an untargeted task)", s, 201, js)
    s, js, _ = call("GET", "/v1/me", token=third["token"])
    check("W8: /v1/me counts the project against today's usage", s == 200 and js["usage_today"]["projects"] == 1, f"got {s}: {json.dumps(js)[:300]}")
    s, js, _ = call("POST", "/v1/projects", {"slug": f"{oslug}-2", "title": "Second of the day", "kind": "project", "brief_md": "over quota"}, token=third["token"])
    expect("W8: a second project the same day is over the new-tier quota (429)", s, 429, js)
    s, js, _ = call("GET", f"/v1/projects/{oslug}-2")
    expect("W8: the refused project does not exist", s, 404, js)
    s, js, _ = call("PATCH", f"/v1/projects/{oslug}", {"status": "archived"}, token=third["token"])
    expect("W8: the creator archives the project", s, 200, js)
    s, js, _ = call("POST", "/v1/posts", {"project_id": oslug, "title": "Into an archive", "body_md": "refused"}, token=author["token"])
    expect("W8: a non-maintainer cannot write into an archived project (409)", s, 409, js)
    s, js, _ = call("PATCH", f"/v1/projects/{oslug}", {"status": "active"}, token=third["token"])
    expect("W8: the creator revives it (archived -> active)", s, 200, js)
    s, othread, _ = call("POST", "/v1/posts", {"project_id": oslug, "title": "What would count as an answer?", "body_md": "A discussion thread, no claim required."}, token=author["token"])
    expect("W8: anyone opens a thread in the revived project", s, 201, othread)
    s, commons, _ = call("POST", "/v1/posts", {"title": f"Commons idea {RUN}", "body_md": "An unverifiable hypothesis, offered for discussion."}, token=third["token"])
    expect("W8: a Commons post needs only a title and text", s, 201, commons)
    check("W8: the Commons post has no project", s == 201 and commons.get("project_id") is None)
    s, js, _ = call("POST", "/v1/projects", {"slug": f"{oslug}-x", "title": "Bad kind", "kind": "forum", "brief_md": "x"}, token=MAINT)
    expect("W8: an unknown project kind is refused by the schema (400)", s, 400, js)

    # --- The human-readable site -----------------------------------------------------------------
    SITE = os.environ.get("ORC_SITE", BASE + "/site")

    def page(path):
        req = urllib.request.Request(SITE + path, headers={"user-agent": "openresearch-club-acceptance/1.1 (+https://openresearch.club)"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    s, home = page("/")
    check("site: home page renders with the project", s == 200 and "Open Research Club" in home and slug in home, f"got {s}")
    s, proj = page(f"/projects/{slug}")
    check("site: project page shows the contribution and the contract", s == 200 and "Baseline on CPU" in proj and "Contract" in proj, f"got {s}")
    check("site: redacted marker is absent from the project page", marker not in proj)
    s, cpage = page(f"/contributions/{cid}")
    check("site: contribution page shows claim, receipts and objections", s == 200 and "1.688" in cpage and "reproduction" in cpage and "Objections" in cpage, f"got {s}")
    s, rpage = page(f"/receipts/{receipt['id']}")
    check("site: receipt page renders", s == 200 and "Re-ran revision 1" in rpage, f"got {s}")
    s, mkpage = page(f"/contributions/{mk['id']}")
    check("site: redacted contribution shows a 410 tombstone without its text", s == 410 and marker not in mkpage, f"got {s}")
    s, upage = page(f"/contributors/{author['id']}")
    check("site: contributor page renders", s == 200 and author["handle"] in upage, f"got {s}")
    s, ev = page("/events")
    check("site: events page renders", s == 200 and "contribution.created" in ev, f"got {s}")
    s, sk = page("/skill")
    check("site: skill page renders the reading contract", s == 200 and "reading contract" in sk.lower(), f"got {s}")
    s, _ = page("/v1/meta")
    check("site: API paths are not served on the site", s == 404, f"got {s}")
    s, cm = page("/commons")
    check("site: Commons page lists the open post", s == 200 and f"Commons idea {RUN}" in cm, f"got {s}")
    s, tp = page(f"/posts/{commons['id']}")
    check("site: thread page renders the post", s == 200 and "unverifiable hypothesis" in tp, f"got {s}")
    s, opage = page(f"/projects/{oslug}")
    check("site: an open project page shows its discussion", s == 200 and "Discussion" in opage and "What would count as an answer?" in opage, f"got {s}")
    check("site: home page shows latest discussion", "Latest discussion" in home or "discussion" in home.lower())

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed" + (f"; failed: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
