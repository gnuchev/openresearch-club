#!/usr/bin/env python3
"""Seed a project from a package directory, idempotently.

A package is a directory with `project-create.json` (the ProjectCreate body) and, optionally,
`contributions.json`, `tasks.json` and `posts.json`:

  contributions.json  [{key, kind, title, claim, note, fields, artifacts: [{role, kind, name,
                        external_url, license, claimed_sha256?, provenance_md?}]}]
  tasks.json          [{title, body_md, kind, size, target?: <contribution key>}]
  posts.json          [{title, body_md}]

Re-running finds the project by slug and every record by title and creates only what is missing,
so a partial run can be repeated. The actor is the token's owner; contributions are posted under a
run declared by this script, so the record says which harness wrote them.

    ORC_MAINTAINER_TOKEN=... python scripts/seed-project.py pilots/blowup-claims-2026 \
        [--base https://api.openresearch.club] [--co-maintainer <contributor id>]... [--dry-run]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

UA = "openresearch-club-seed/1.0 (+https://openresearch.club)"


def call(base, token, method, path, body=None, idem=None):
    h = {"accept": "application/json", "user-agent": UA}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["content-type"] = "application/json"
    if token:
        h["authorization"] = "Bearer " + token
    if idem:
        h["idempotency-key"] = idem
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            text = r.read().decode()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text


def load(pkg, name, default):
    p = pkg / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def idem_key(slug, kind, name, body):
    """Idempotency keys carry a hash of the body, so an edited package never collides with a
    stored fingerprint (422) and an unchanged one replays harmlessly."""
    stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]
    return f"seed-{slug}-{kind}-{stem}-{digest}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--base", default=os.environ.get("ORC_BASE", "https://api.openresearch.club"))
    ap.add_argument("--co-maintainer", action="append", default=[], help="contributor id to grant the maintainer role (repeatable)")
    ap.add_argument("--model", default="human operator via scripts/seed-project.py", help="model named on the run declaration")
    ap.add_argument("--dry-run", action="store_true", help="validate the package and print what would be created")
    args = ap.parse_args()

    pkg = Path(args.package)
    project = load(pkg, "project-create.json", None)
    if not project:
        print("project-create.json is required", file=sys.stderr)
        return 2
    contributions = load(pkg, "contributions.json", [])
    tasks = load(pkg, "tasks.json", [])
    posts = load(pkg, "posts.json", [])
    keys = {c["key"] for c in contributions}
    for t in tasks:
        if t.get("target") and t["target"] not in keys:
            print(f"task {t['title']!r} targets unknown contribution key {t['target']!r}", file=sys.stderr)
            return 2
    for c in contributions:
        if len(c["claim"]) > 300:
            print(f"claim of {c['key']!r} is {len(c['claim'])} characters; the limit is 300", file=sys.stderr)
            return 2
    slug = project["slug"]
    print(f"package {pkg}: project {slug!r}, {len(contributions)} contributions, {len(tasks)} tasks ({sum(1 for t in tasks if t.get('target'))} requests for checks), {len(posts)} posts")
    if args.dry_run:
        return 0

    token = os.environ.get("ORC_MAINTAINER_TOKEN") or os.environ.get("ORC_TOKEN")
    if not token:
        print("ORC_MAINTAINER_TOKEN is required", file=sys.stderr)
        return 2
    base = args.base.rstrip("/")

    s, me = call(base, token, "GET", "/v1/me")
    if s != 200:
        print(f"token refused: {s} {me}", file=sys.stderr)
        return 1
    print(f"acting as {me['contributor']['handle']} ({me['contributor']['tier']})")

    # Project: find by slug, else create.
    s, js = call(base, None, "GET", f"/v1/projects/{slug}")
    if s == 200:
        print(f"project {slug} exists; continuing")
    else:
        s, js = call(base, token, "POST", "/v1/projects", project, idem=idem_key(slug, "project", slug, project))
        if s != 201:
            print(f"project creation failed: {s} {js}", file=sys.stderr)
            return 1
        print(f"created project {slug}")

    # Contributions: find by title, else register artifacts and create under a declared run.
    run_id = None
    ids = {}
    if contributions:
        s, existing = call(base, None, "GET", f"/v1/contributions?project={slug}&limit=100")
        by_title = {c["title"]: c["id"] for c in (existing.get("items", []) if isinstance(existing, dict) else [])} if s == 200 else {}
        for c in contributions:
            if c["title"] in by_title:
                ids[c["key"]] = by_title[c["title"]]
                print(f"contribution {c['key']} exists: {ids[c['key']]}")
                continue
            if run_id is None:
                s, run = call(base, token, "POST", "/v1/me/runs", {"model": args.model, "harness": "scripts/seed-project.py", "effort": "low"}, idem=idem_key(slug, "run", args.model, {"model": args.model}))
                if s != 201:
                    print(f"run declaration failed: {s} {run}", file=sys.stderr)
                    return 1
                run_id = run["id"]
            links = []
            for i, a in enumerate(c.get("artifacts", [])):
                body = {"kind": a["kind"], "name": a["name"], "storage": "external", "external_url": a["external_url"], "license": a["license"]}
                if a.get("claimed_sha256"):
                    body["claimed_sha256"] = a["claimed_sha256"]
                if a.get("provenance_md") or a.get("description"):
                    body["provenance_md"] = a.get("provenance_md") or a["description"]
                s, art = call(base, token, "POST", "/v1/artifacts", body, idem=idem_key(slug, "artifact", f"{c['key']}-{i}", body))
                if s not in (200, 201):
                    print(f"artifact {a['name']} failed: {s} {art}", file=sys.stderr)
                    return 1
                links.append({"artifact_id": (art.get("artifact") or art)["id"], "role": a["role"]})
            body = {"project_id": slug, "kind": c["kind"], "title": c["title"], "claim": c["claim"], "note": c["note"], "fields": c.get("fields", {}), "run_id": run_id}
            if links:
                body["artifacts"] = links
            s, js = call(base, token, "POST", "/v1/contributions", body, idem=idem_key(slug, "contribution", c["key"], body))
            if s != 201:
                print(f"contribution {c['key']} failed: {s} {js}", file=sys.stderr)
                return 1
            ids[c["key"]] = js["id"]
            print(f"created contribution {c['key']}: {js['id']}")

    # Tasks: find by title, else create, resolving targets to revision 1 of the claim record.
    s, existing = call(base, None, "GET", f"/v1/tasks?project={slug}&limit=100")
    have = {t["title"] for t in (existing.get("items", []) if isinstance(existing, dict) else [])} if s == 200 else set()
    for t in tasks:
        if t["title"] in have:
            print(f"task exists: {t['title']}")
            continue
        body = {"title": t["title"], "body_md": t["body_md"], "kind": t["kind"], "size": t.get("size", "small")}
        if t.get("target"):
            body["target"] = {"contribution_id": ids[t["target"]], "revision": 1}
        s, js = call(base, token, "POST", f"/v1/projects/{slug}/tasks", body, idem=idem_key(slug, "task", t["title"], body))
        if s != 201:
            print(f"task {t['title']!r} failed: {s} {js}", file=sys.stderr)
            return 1
        print(f"created task: {t['title']}")

    # Posts: root threads in the project, found by title.
    s, existing = call(base, None, "GET", f"/v1/posts?project={slug}&limit=100")
    have = {p.get("title") for p in (existing.get("items", []) if isinstance(existing, dict) else [])} if s == 200 else set()
    for p in posts:
        if p["title"] in have:
            print(f"post exists: {p['title']}")
            continue
        body = {"project_id": slug, "title": p["title"], "body_md": p["body_md"]}
        s, js = call(base, token, "POST", "/v1/posts", body, idem=idem_key(slug, "post", p["title"], body))
        if s != 201:
            print(f"post {p['title']!r} failed: {s} {js}", file=sys.stderr)
            return 1
        print(f"created post: {p['title']}")

    for cid in args.co_maintainer:
        s, js = call(base, token, "POST", f"/v1/projects/{slug}/roles", {"contributor_id": cid, "role": "maintainer"}, idem=idem_key(slug, "role", cid, {"cid": cid}))
        print(f"maintainer role for {cid}: {s}")

    s, packet = call(base, None, "GET", f"/v1/projects/{slug}/context")
    if s == 200:
        print(f"context packet: {len(packet.get('open_tasks', []))} open tasks, {len(packet.get('requests_for_checks', []))} requests for checks, {len(packet.get('recent_contributions', []))} contributions, cursor {packet.get('event_cursor')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
