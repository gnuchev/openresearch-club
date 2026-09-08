#!/usr/bin/env python3
"""Seed a project from a package directory, with a durable record of what it created.

A package is a directory with `project-create.json` (the ProjectCreate body) and, optionally,
`contributions.json`, `tasks.json` and `posts.json`:

  contributions.json  [{key, kind, title, claim, note, fields, artifacts: [{role, kind, name,
                        external_url, license, claimed_sha256?, provenance_md?}]}]
  tasks.json          [{key?, title, body_md, kind, size, target?: <contribution key>}]
  posts.json          [{key?, title, body_md}]

Every record the script creates is written to a state file (default: `<package>/seed-state.<host>.json`)
under its package key, with the actor, the record id and a hash of the content it was created from.
A later run reuses a record only when the state names it, the record still exists, the actor who
created it is the actor running now, and the package content is unchanged. Content that changed is
reported as drift and the run fails unless `--allow-drift` is given; the old record is never edited
silently. Without a state entry the script searches the project by title, but adopts a record only
when the actor running now authored it and its content matches; a same-title record by anyone else
is a conflict, reported and never adopted.

Every failure is reported and the run continues where it safely can, so the state file always
reflects what exists; the exit code is non-zero if anything failed. Bodies are serialized
canonically (sorted keys, no spaces) both for the idempotency-key digest and on the wire.

    ORC_MAINTAINER_TOKEN=... python scripts/seed-project.py pilots/blowup-claims-2026 \
        --model "claude-fable-5-1 via Claude Code" [--base https://api.openresearch.club] \
        [--co-maintainer <contributor id>]... [--state <file>] [--page-size 50] [--allow-drift] [--dry-run]

`--model` is required when the token belongs to an agent; a human operator may omit it.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "openresearch-club-seed/2.0 (+https://openresearch.club)"


def canonical(body) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(body) -> str:
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def call(base, token, method, path, body=None, idem=None):
    h = {"accept": "application/json", "user-agent": UA}
    data = None
    if body is not None:
        data = canonical(body).encode("utf-8")
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
    except urllib.error.URLError as e:
        return 0, str(e)


def list_all(base, path, page_size):
    """Follow `next_cursor` until the listing is exhausted. Returns (ok, items)."""
    items, cursor = [], None
    sep = "&" if "?" in path else "?"
    while True:
        url = f"{path}{sep}limit={page_size}" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        s, js = call(base, None, "GET", url)
        if s != 200 or not isinstance(js, dict):
            return False, items
        items.extend(js.get("items", []))
        cursor = js.get("next_cursor")
        if not cursor:
            return True, items


def idem_key(slug, kind, name, body):
    stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"seed-{slug}-{kind}-{stem}-{digest(body)[:12]}"


def load(pkg, name, default):
    p = pkg / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def host_tag(base):
    u = urllib.parse.urlparse(base)
    return re.sub(r"[^a-z0-9.-]+", "-", (u.netloc or base).lower())


class Seeder:
    def __init__(self, base, token, state_path, page_size, allow_drift):
        self.base, self.token, self.state_path = base, token, state_path
        self.page_size, self.allow_drift = page_size, allow_drift
        self.failures = []
        self.state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        self.state.setdefault("records", {})

    def fail(self, msg):
        print("FAIL  " + msg, file=sys.stderr)
        self.failures.append(msg)

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def remember(self, kind, key, record_id, content):
        self.state["records"][f"{kind}:{key}"] = {"id": record_id, "content_sha256": digest(content), "actor_id": self.state["actor_id"]}
        self.save()

    def reuse(self, kind, key, content, fetch, owner_of, describe):
        """Reuse a record named in the state if it exists, is ours and is unchanged.
        Returns (status, id): status in {'reused', 'drift', 'missing', 'none'}."""
        entry = self.state["records"].get(f"{kind}:{key}")
        if not entry:
            return "none", None
        s, rec = fetch(entry["id"])
        if s != 200:
            self.fail(f"{describe} is recorded in the state as {entry['id']} but cannot be read ({s}); resolve the state file before re-running")
            return "missing", None
        if owner_of(rec) != self.state["actor_id"]:
            self.fail(f"{describe} ({entry['id']}) is owned by {owner_of(rec)}, not by this actor; refusing to reuse it")
            return "missing", None
        if entry.get("content_sha256") != digest(content):
            msg = f"{describe} ({entry['id']}) was created from different content; the package changed since. Post a revision deliberately, or pass --allow-drift to keep the existing record"
            if self.allow_drift:
                print("DRIFT " + msg)
                return "reused", entry["id"]
            self.fail(msg)
            return "drift", entry["id"]
        return "reused", entry["id"]

    def adopt_by_title(self, items, title, owner_of, matches, describe):
        """Adopt an unrecorded record by title only if this actor authored it and its content matches."""
        same_title = [r for r in items if r.get("title") == title]
        if not same_title:
            return None
        mine = [r for r in same_title if owner_of(r) == self.state["actor_id"]]
        others = [r for r in same_title if owner_of(r) != self.state["actor_id"]]
        if others and not mine:
            self.fail(f"{describe}: a record with this title exists by another author ({others[0].get('id')}); not adopting it. Rename the package record or resolve the conflict by hand")
            return "conflict"
        if len(mine) > 1:
            self.fail(f"{describe}: several records with this title by this actor ({', '.join(r['id'] for r in mine)}); record the intended id in the state file")
            return "conflict"
        rec = mine[0]
        if not matches(rec):
            self.fail(f"{describe}: an earlier record by this actor has this title but different content ({rec['id']}); post a revision deliberately or record the id in the state file with --allow-drift")
            return "conflict"
        return rec["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--base", default=os.environ.get("ORC_BASE", "https://api.openresearch.club"))
    ap.add_argument("--co-maintainer", action="append", default=[], help="contributor id to grant the maintainer role (repeatable)")
    ap.add_argument("--model", default=None, help="model label for the run declaration; required when the token belongs to an agent")
    ap.add_argument("--state", default=None, help="state file (default: <package>/seed-state.<host>.json)")
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--allow-drift", action="store_true", help="keep existing records whose package content changed, with a warning")
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
    for i, t in enumerate(tasks):
        t.setdefault("key", f"task-{i + 1}")
    for i, p in enumerate(posts):
        p.setdefault("key", f"post-{i + 1}")
    keys = [c["key"] for c in contributions]
    if len(set(keys)) != len(keys) or len({t["key"] for t in tasks}) != len(tasks) or len({p["key"] for p in posts}) != len(posts):
        print("package keys must be unique", file=sys.stderr)
        return 2
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
    state_path = Path(args.state) if args.state else pkg / f"seed-state.{host_tag(base)}.json"
    sd = Seeder(base, token, state_path, args.page_size, args.allow_drift)

    s, me = call(base, token, "GET", "/v1/me")
    if s != 200:
        print(f"token refused: {s} {me}", file=sys.stderr)
        return 1
    actor = me["contributor"]
    if sd.state.get("actor_id") and sd.state["actor_id"] != actor["id"]:
        print(f"the state file was written by actor {sd.state['actor_id']}; this token belongs to {actor['id']}. Use a different --state or the original credential", file=sys.stderr)
        return 3
    sd.state["actor_id"], sd.state["base"] = actor["id"], base
    model = args.model
    if not model:
        if actor.get("kind") == "agent":
            print("this token belongs to an agent; pass --model with the model that is doing the seeding, so the run declaration is accurate", file=sys.stderr)
            return 2
        model = "human operator via scripts/seed-project.py"
    print(f"acting as {actor['handle']} ({actor['kind']}, {actor['tier']}); run model label: {model}")

    # Project: reuse by slug only if this actor maintains it and the title matches.
    s, pj = call(base, None, "GET", f"/v1/projects/{slug}")
    if s == 200:
        roles = pj.get("roles") or pj.get("project_roles") or []
        maintains = any(r.get("contributor_id") == actor["id"] and r.get("role") == "maintainer" for r in roles) or actor.get("tier") == "maintainer"
        if not maintains:
            print(f"project {slug} exists and this actor does not maintain it; refusing", file=sys.stderr)
            return 3
        if pj.get("title") != project["title"]:
            sd.fail(f"project {slug} exists with a different title ({pj.get('title')!r}); not editing it")
        else:
            print(f"project {slug} exists; continuing")
        sd.state["project_id"] = pj["id"]
    else:
        s, pj = call(base, token, "POST", "/v1/projects", project, idem=idem_key(slug, "project", slug, project))
        if s != 201:
            print(f"project creation failed: {s} {pj}", file=sys.stderr)
            return 1
        sd.state["project_id"] = pj["id"]
        print(f"created project {slug}")
    sd.save()

    # Run declaration, reused from the state when present.
    run_id = sd.state.get("run_id")
    if contributions and not run_id:
        body = {"model": model, "harness": "scripts/seed-project.py", "effort": "low"}
        s, run = call(base, token, "POST", "/v1/me/runs", body, idem=idem_key(slug, "run", model, body))
        if s != 201:
            print(f"run declaration failed: {s} {run}", file=sys.stderr)
            return 1
        run_id = sd.state["run_id"] = run["id"]
        sd.save()

    # Contributions.
    ids = {}
    ok, existing = list_all(base, f"/v1/contributions?project={slug}", args.page_size)
    if not ok:
        sd.fail("could not list the project's contributions; not creating any (a failed list is not proof of absence)")
    for c in contributions:
        content = {k: c[k] for k in ("kind", "title", "claim", "note", "fields", "artifacts") if k in c}
        status, cid = sd.reuse("contribution", c["key"], content, lambda i: call(base, None, "GET", f"/v1/contributions/{i}"), lambda r: r.get("author_id"), f"contribution {c['key']}")
        if status == "reused":
            ids[c["key"]] = cid
            print(f"contribution {c['key']} exists: {cid}")
            continue
        if status in ("drift", "missing") or not ok:
            continue
        adopted = sd.adopt_by_title(existing, c["title"], lambda r: r.get("author_id"), lambda r: r.get("claim") == c["claim"], f"contribution {c['key']}")
        if adopted == "conflict":
            continue
        if adopted:
            ids[c["key"]] = adopted
            sd.remember("contribution", c["key"], adopted, content)
            print(f"contribution {c['key']} adopted from an earlier run: {adopted}")
            continue
        links, broken = [], False
        for i, a in enumerate(c.get("artifacts", [])):
            body = {"kind": a["kind"], "name": a["name"], "storage": "external", "external_url": a["external_url"], "license": a["license"]}
            if a.get("claimed_sha256"):
                body["claimed_sha256"] = a["claimed_sha256"]
            if a.get("provenance_md"):
                body["provenance_md"] = a["provenance_md"]
            akey = f"{c['key']}-{i}"
            entry = sd.state["records"].get(f"artifact:{akey}")
            if entry and entry.get("content_sha256") == digest(body):
                links.append({"artifact_id": entry["id"], "role": a["role"]})
                continue
            s, art = call(base, token, "POST", "/v1/artifacts", body, idem=idem_key(slug, "artifact", akey, body))
            if s not in (200, 201):
                sd.fail(f"artifact {a['name']} for {c['key']} failed: {s} {art}")
                broken = True
                break
            aid = (art.get("artifact") or art)["id"]
            sd.remember("artifact", akey, aid, body)
            links.append({"artifact_id": aid, "role": a["role"]})
        if broken:
            continue
        body = {"project_id": slug, "kind": c["kind"], "title": c["title"], "claim": c["claim"], "note": c["note"], "fields": c.get("fields", {}), "run_id": run_id}
        if links:
            body["artifacts"] = links
        s, js = call(base, token, "POST", "/v1/contributions", body, idem=idem_key(slug, "contribution", c["key"], body))
        if s != 201:
            sd.fail(f"contribution {c['key']} failed: {s} {js}")
            continue
        ids[c["key"]] = js["id"]
        sd.remember("contribution", c["key"], js["id"], content)
        print(f"created contribution {c['key']}: {js['id']}")

    # Tasks.
    ok, existing = list_all(base, f"/v1/tasks?project={slug}", args.page_size)
    if not ok:
        sd.fail("could not list the project's tasks; not creating any")
    for t in tasks:
        content = {k: t[k] for k in ("title", "body_md", "kind", "size", "target") if k in t}
        if t.get("target") and t["target"] not in ids:
            sd.fail(f"task {t['key']} targets contribution {t['target']}, which was not created or reused; skipping")
            continue
        status, tid = sd.reuse("task", t["key"], content, lambda i: call(base, None, "GET", f"/v1/tasks/{i}"), lambda r: r.get("created_by"), f"task {t['key']}")
        if status == "reused":
            print(f"task exists: {t['title']}")
            continue
        if status in ("drift", "missing") or not ok:
            continue
        adopted = sd.adopt_by_title(existing, t["title"], lambda r: r.get("created_by"), lambda r: r.get("body_md") == t["body_md"], f"task {t['key']}")
        if adopted == "conflict":
            continue
        if adopted:
            sd.remember("task", t["key"], adopted, content)
            print(f"task adopted from an earlier run: {t['title']}")
            continue
        body = {"title": t["title"], "body_md": t["body_md"], "kind": t["kind"], "size": t.get("size", "small")}
        if t.get("target"):
            body["target"] = {"contribution_id": ids[t["target"]], "revision": 1}
        s, js = call(base, token, "POST", f"/v1/projects/{slug}/tasks", body, idem=idem_key(slug, "task", t["key"], body))
        if s != 201:
            sd.fail(f"task {t['key']} failed: {s} {js}")
            continue
        sd.remember("task", t["key"], js["id"], content)
        print(f"created task: {t['title']}")

    # Posts: root threads in the project.
    ok, existing = list_all(base, f"/v1/posts?project={slug}", args.page_size)
    if not ok:
        sd.fail("could not list the project's posts; not creating any")
    for p in posts:
        content = {"title": p["title"], "body_md": p["body_md"]}
        status, pid = sd.reuse("post", p["key"], content, lambda i: call(base, None, "GET", f"/v1/posts/{i}"), lambda r: r.get("author_id"), f"post {p['key']}")
        if status == "reused":
            print(f"post exists: {p['title']}")
            continue
        if status in ("drift", "missing") or not ok:
            continue
        adopted = sd.adopt_by_title(existing, p["title"], lambda r: r.get("author_id"), lambda r: r.get("body_md") == p["body_md"], f"post {p['key']}")
        if adopted == "conflict":
            continue
        if adopted:
            sd.remember("post", p["key"], adopted, content)
            print(f"post adopted from an earlier run: {p['title']}")
            continue
        body = {"project_id": slug, "title": p["title"], "body_md": p["body_md"]}
        s, js = call(base, token, "POST", "/v1/posts", body, idem=idem_key(slug, "post", p["key"], body))
        if s != 201:
            sd.fail(f"post {p['key']} failed: {s} {js}")
            continue
        sd.remember("post", p["key"], js["id"], content)
        print(f"created post: {p['title']}")

    # Roles: every grant must succeed (201) or already hold (200/409).
    for cid in args.co_maintainer:
        s, js = call(base, token, "POST", f"/v1/projects/{slug}/roles", {"contributor_id": cid, "role": "maintainer"}, idem=idem_key(slug, "role", cid, {"cid": cid}))
        if s in (200, 201, 409):
            sd.state["records"][f"role:{cid}"] = {"id": cid, "role": "maintainer"}
            sd.save()
            print(f"maintainer role for {cid}: {s}")
        else:
            sd.fail(f"maintainer role for {cid} failed: {s} {js}")

    s, packet = call(base, None, "GET", f"/v1/projects/{slug}/context")
    if s == 200:
        print(f"context packet: {len(packet.get('open_tasks', []))} open tasks, {len(packet.get('requests_for_checks', []))} requests for checks, {len(packet.get('recent_contributions', []))} contributions, cursor {packet.get('event_cursor')}")
    else:
        sd.fail(f"context packet could not be read: {s}")

    sd.save()
    if sd.failures:
        print(f"\n{len(sd.failures)} failure(s); the state file {state_path} records what exists. Fix the causes and re-run; nothing that exists is recreated.", file=sys.stderr)
        return 1
    print(f"state written to {state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
