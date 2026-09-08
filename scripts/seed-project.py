#!/usr/bin/env python3
"""Seed a project from a package directory, with a durable, verified record of what it created.

A package is a directory with `project-create.json` (the ProjectCreate body) and, optionally,
`contributions.json`, `tasks.json` and `posts.json`:

  contributions.json  [{key, kind, title, claim, note, fields, artifacts: [{role, kind, name,
                        external_url, license, claimed_sha256?, provenance_md?}]}]
  tasks.json          [{key?, title, body_md, kind, size, target?: <contribution key>}]
  posts.json          [{key?, title, body_md}]

The state file (default `<package>/seed-state.<host>.json`) is bound to one actor, one API base, one
package slug and one project id, and records every record the script created or adopted, by package
key, with the record id, the revision the package's tasks target, and a fingerprint of the *server*
record as verified at that revision. A record is reused only when the state names it, it still
exists, it belongs to the bound project, its author (or creator) is the actor running now, and the
package still describes the same content. Without a state entry, a same-title record is adopted only
when this actor authored it and the server record matches the package on every seeded field,
artifacts included; anything else is a conflict, reported and never adopted.

Package content that changed is drift: reported, and the run fails unless `--allow-drift` keeps
the existing record with a visible warning. The project definition is checked before any child
write: a slug bound to a different project, or a project whose title or kind differs from the
package, stops the run; a different status or brief is reported and allowed. Every failure is
reported; the run continues where it safely can; the exit code is non-zero if anything failed.
Bodies are serialized canonically (sorted keys, no spaces) for both the idempotency-key digest
and the wire.

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

UA = "openresearch-club-seed/3.0 (+https://openresearch.club)"


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


def normalize_base(base: str) -> str:
    u = urllib.parse.urlparse(base.strip().rstrip("/"))
    return f"{u.scheme.lower()}://{u.netloc.lower()}{u.path}"


def host_tag(base):
    u = urllib.parse.urlparse(base)
    return re.sub(r"[^a-z0-9.-]+", "-", (u.netloc or base).lower())


# ---------------------------------------------------------------------------------------------
# Projections: what the package asks for, and what the server record shows, in one comparable shape.
# ---------------------------------------------------------------------------------------------

def artifact_identity(a):
    return {"role": a.get("role"), "name": a.get("name"), "external_url": a.get("external_url"), "claimed_sha256": a.get("claimed_sha256")}


def contribution_projection_from_package(c):
    return {
        "kind": c["kind"], "title": c["title"], "claim": c["claim"], "note": c["note"], "fields": c.get("fields", {}),
        "artifacts": sorted((artifact_identity(a) for a in c.get("artifacts", [])), key=canonical),
    }


def contribution_projection_from_server(rec, revision):
    """The record as the server shows it at one revision; None if that revision cannot be read."""
    rev = rec.get("revision") if isinstance(rec.get("revision"), dict) else None
    if not rev or rev.get("revision") != revision:
        return None
    return {
        "kind": rec.get("kind"), "title": rev.get("title", rec.get("title")), "claim": rev.get("claim"), "note": rev.get("note"), "fields": rev.get("fields", {}),
        "artifacts": sorted((artifact_identity(a) for a in rev.get("artifacts", [])), key=canonical),
    }


def fetch_contribution_at_revision(base, record_id, revision=1):
    """Keep parent identity/visibility checks while reading the immutable seed revision."""
    status, parent = call(base, None, "GET", f"/v1/contributions/{record_id}")
    if status != 200 or not isinstance(parent, dict):
        return status, parent
    status, exact = call(base, None, "GET", f"/v1/contributions/{record_id}/revisions/{revision}")
    if status != 200 or not isinstance(exact, dict):
        return status, exact
    if exact.get("contribution_id") != record_id or exact.get("revision") != revision:
        return 0, {"error": "The exact revision response does not match the requested contribution and revision"}
    return 200, {**parent, "revision": exact}


def task_projection_from_package(t, target_id):
    return {"title": t["title"], "body_md": t["body_md"], "kind": t["kind"], "size": t.get("size", "small"), "target": ({"contribution_id": target_id, "revision": 1} if t.get("target") else None)}


def task_projection_from_server(rec):
    target = rec.get("target")
    return {"title": rec.get("title"), "body_md": rec.get("body_md"), "kind": rec.get("kind"), "size": rec.get("size"), "target": ({"contribution_id": target.get("contribution_id"), "revision": target.get("revision")} if target else None)}


def post_projection_from_package(p):
    return {"title": p["title"], "body_md": p["body_md"]}


def post_projection_from_server(rec):
    return {"title": rec.get("title"), "body_md": rec.get("body_md")}


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

    def remember(self, kind, key, record_id, package_projection, server_projection, revision=None):
        entry = {"id": record_id, "actor_id": self.state["actor_id"], "project_id": self.state["project_id"],
                 "package_sha256": digest(package_projection), "verified_sha256": digest(server_projection)}
        if revision is not None:
            entry["revision"] = revision
        self.state["records"][f"{kind}:{key}"] = entry
        self.save()

    def reuse(self, kind, key, package_projection, fetch, owner_of, project_of, server_projection, describe):
        """Reuse a record named in the state if it exists, belongs to the bound project, is ours, and
        both the package and the server record are unchanged. Returns (status, id, revision)."""
        entry = self.state["records"].get(f"{kind}:{key}")
        if not entry:
            return "none", None, None
        revision = entry.get("revision")
        s, rec = fetch(entry["id"], revision)
        if s != 200 or not isinstance(rec, dict):
            self.fail(f"{describe} is recorded in the state as {entry['id']} but cannot be read ({s}); resolve the state file before re-running")
            return "missing", None, None
        if project_of(rec) != self.state["project_id"]:
            self.fail(f"{describe} ({entry['id']}) belongs to project {project_of(rec)}, not to the bound project; refusing to reuse it")
            return "missing", None, None
        if owner_of(rec) != self.state["actor_id"]:
            self.fail(f"{describe} ({entry['id']}) is owned by {owner_of(rec)}, not by this actor; refusing to reuse it")
            return "missing", None, None
        shown = server_projection(rec, revision)
        if shown is None:
            self.fail(f"{describe} ({entry['id']}) no longer shows revision {revision}, the one the package's tasks target; resolve by hand")
            return "missing", None, None
        if digest(shown) != entry.get("verified_sha256"):
            self.fail(f"{describe} ({entry['id']}) differs on the server from what was verified when it was seeded (revision {revision}); resolve by hand")
            return "missing", None, None
        if entry.get("package_sha256") != digest(package_projection):
            msg = f"{describe} ({entry['id']}) was created from different content; the package changed since. Post a revision deliberately, or pass --allow-drift to keep the existing record"
            if self.allow_drift:
                print("DRIFT " + msg)
                return "reused", entry["id"], revision
            self.fail(msg)
            return "drift", entry["id"], revision
        return "reused", entry["id"], revision

    def adopt_by_title(self, items, title, owner_of, fetch, project_of, server_projection, package_projection, describe):
        """Adopt an unrecorded record by title only if this actor authored it in this project and the
        full server record matches the package. Returns an id, 'conflict', or None."""
        same_title = [r for r in items if r.get("title") == title]
        if not same_title:
            return None, None
        mine = [r for r in same_title if owner_of(r) == self.state["actor_id"]]
        others = [r for r in same_title if owner_of(r) != self.state["actor_id"]]
        if others and not mine:
            self.fail(f"{describe}: a record with this title exists by another author ({others[0].get('id')}); not adopting it. Rename the package record or resolve the conflict by hand")
            return "conflict", None
        if len(mine) > 1:
            self.fail(f"{describe}: several records with this title by this actor ({', '.join(r['id'] for r in mine)}); record the intended id in the state file")
            return "conflict", None
        s, rec = fetch(mine[0]["id"], 1)
        if s != 200 or not isinstance(rec, dict):
            self.fail(f"{describe}: candidate {mine[0]['id']} cannot be read ({s})")
            return "conflict", None
        if project_of(rec) != self.state["project_id"]:
            self.fail(f"{describe}: candidate {rec.get('id')} belongs to another project; not adopting it")
            return "conflict", None
        shown = server_projection(rec, 1)
        if shown is None or digest(shown) != digest(package_projection):
            self.fail(f"{describe}: an earlier record by this actor has this title but different content or evidence at revision 1 ({rec.get('id')}); post a revision deliberately or record the id in the state file")
            return "conflict", None
        return rec["id"], shown


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
    base = normalize_base(args.base)
    state_path = Path(args.state) if args.state else pkg / f"seed-state.{host_tag(base)}.json"
    sd = Seeder(base, token, state_path, args.page_size, args.allow_drift)

    # --- Preflight: the state binds one actor, one base, one package slug and one project. ---
    s, me = call(base, token, "GET", "/v1/me")
    if s != 200:
        print(f"token refused: {s} {me}", file=sys.stderr)
        return 1
    actor = me["contributor"]
    for field, value, what in (("actor_id", actor["id"], "actor"), ("base", base, "API base"), ("slug", slug, "package slug")):
        if sd.state.get(field) and sd.state[field] != value:
            print(f"the state file is bound to {what} {sd.state[field]!r}; this run is {value!r}. Use a different --state file, or a new state for a new project", file=sys.stderr)
            return 3
    model = args.model
    if not model:
        if actor.get("kind") == "agent":
            print("this token belongs to an agent; pass --model with the model that is doing the seeding, so the run declaration is accurate", file=sys.stderr)
            return 2
        model = "human operator via scripts/seed-project.py"
    print(f"acting as {actor['handle']} ({actor['kind']}, {actor['tier']}); run model label: {model}")

    s, pj = call(base, None, "GET", f"/v1/projects/{slug}")
    if s == 200:
        if sd.state.get("project_id") and sd.state["project_id"] != pj["id"]:
            print(f"the state file is bound to project {sd.state['project_id']}, but slug {slug!r} now resolves to {pj['id']}; refusing", file=sys.stderr)
            return 3
        roles = pj.get("roles") or []
        maintains = any(r.get("contributor_id") == actor["id"] and r.get("role") == "maintainer" for r in roles) or actor.get("tier") == "maintainer"
        if not maintains:
            print(f"project {slug} exists and this actor does not maintain it; refusing", file=sys.stderr)
            return 3
        if pj.get("title") != project["title"] or pj.get("kind") != project["kind"]:
            print(f"project {slug} exists with a different identity (title {pj.get('title')!r}, kind {pj.get('kind')!r}) than the package (title {project['title']!r}, kind {project['kind']!r}); nothing written. Use a new slug or a new state", file=sys.stderr)
            return 3
        if pj.get("status") != project.get("status", "active") or pj.get("brief_md") != project.get("brief_md"):
            print(f"NOTE  project {slug} exists; its status or brief differs from the package (allowed: maintainers edit those later). The package copy is not applied.")
        else:
            print(f"project {slug} exists; continuing")
    elif s == 404:
        if sd.state.get("project_id"):
            print(f"the state file is bound to project {sd.state['project_id']}, but slug {slug!r} does not exist on this base; refusing to create a new project under an old state", file=sys.stderr)
            return 3
        s, pj = call(base, token, "POST", "/v1/projects", project, idem=idem_key(slug, "project", slug, project))
        if s != 201:
            print(f"project creation failed: {s} {pj}", file=sys.stderr)
            return 1
        print(f"created project {slug}")
    else:
        print(f"project {slug} cannot be read ({s}); nothing written", file=sys.stderr)
        return 1
    sd.state.update({"actor_id": actor["id"], "base": base, "slug": slug, "project_id": pj["id"]})
    sd.save()
    project_id = pj["id"]

    # --- Run declaration, reused from the state when present. ---
    run_id = sd.state.get("run_id")
    if contributions and not run_id:
        body = {"model": model, "harness": "scripts/seed-project.py", "effort": "low"}
        s, run = call(base, token, "POST", "/v1/me/runs", body, idem=idem_key(slug, "run", model, body))
        if s != 201:
            print(f"run declaration failed: {s} {run}", file=sys.stderr)
            return 1
        run_id = sd.state["run_id"] = run["id"]
        sd.save()

    fetch_contribution = lambda i, revision=1: fetch_contribution_at_revision(base, i, revision)
    fetch_task = lambda i, _revision=None: call(base, None, "GET", f"/v1/tasks/{i}")
    fetch_post = lambda i, _revision=None: call(base, None, "GET", f"/v1/posts/{i}")
    project_of = lambda r: r.get("project_id")

    # --- Contributions. ---
    ids = {}
    ok, existing = list_all(base, f"/v1/contributions?project={slug}", args.page_size)
    # Listings show current titles. Recover original titles before matching seed records,
    # otherwise a legitimate rename at revision 2 can cause duplicate creation without state.
    if ok:
        for index, candidate in enumerate(existing):
            if candidate.get("current_revision") == 1:
                continue
            status, full = fetch_contribution(candidate["id"], 1)
            if status != 200 or contribution_projection_from_server(full, 1) is None:
                sd.fail(f"could not read original revision of listed contribution {candidate['id']} ({status}); not creating contributions")
                ok = False
                break
            existing[index] = {**candidate, "title": full["revision"]["title"]}
    if not ok:
        sd.fail("could not list the project's contributions; not creating any (a failed list is not proof of absence)")
    for c in contributions:
        wanted = contribution_projection_from_package(c)
        status, cid, _ = sd.reuse("contribution", c["key"], wanted, fetch_contribution, lambda r: r.get("author_id"), project_of, contribution_projection_from_server, f"contribution {c['key']}")
        if status == "reused":
            ids[c["key"]] = cid
            print(f"contribution {c['key']} exists: {cid}")
            continue
        if status in ("drift", "missing") or not ok:
            continue
        adopted, shown = sd.adopt_by_title(existing, c["title"], lambda r: r.get("author_id"), fetch_contribution, project_of, contribution_projection_from_server, wanted, f"contribution {c['key']}")
        if adopted == "conflict":
            continue
        if adopted:
            ids[c["key"]] = adopted
            sd.remember("contribution", c["key"], adopted, wanted, shown, revision=1)
            print(f"contribution {c['key']} adopted from an earlier run after full comparison: {adopted}")
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
            if entry and entry.get("package_sha256") == digest(body):
                links.append({"artifact_id": entry["id"], "role": a["role"]})
                continue
            s, art = call(base, token, "POST", "/v1/artifacts", body, idem=idem_key(slug, "artifact", akey, body))
            if s not in (200, 201):
                sd.fail(f"artifact {a['name']} for {c['key']} failed: {s} {art}")
                broken = True
                break
            aid = (art.get("artifact") or art)["id"]
            sd.remember("artifact", akey, aid, body, body)
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
        # Verify the server shows what was asked for, then bind the state to that.
        s2, full = fetch_contribution(js["id"])
        shown = contribution_projection_from_server(full, 1) if s2 == 200 and isinstance(full, dict) else None
        if shown is None or digest(shown) != digest(wanted):
            sd.fail(f"contribution {c['key']} was created as {js['id']} but the server record does not match the package at revision 1; not recording it as seeded. Inspect it by hand")
            continue
        ids[c["key"]] = js["id"]
        sd.remember("contribution", c["key"], js["id"], wanted, shown, revision=1)
        print(f"created contribution {c['key']}: {js['id']}")

    # --- Tasks. ---
    ok, existing = list_all(base, f"/v1/tasks?project={slug}", args.page_size)
    if not ok:
        sd.fail("could not list the project's tasks; not creating any")
    for t in tasks:
        if t.get("target") and t["target"] not in ids:
            sd.fail(f"task {t['key']} targets contribution {t['target']}, which was not created or reused; skipping")
            continue
        wanted = task_projection_from_package(t, ids.get(t.get("target")))
        status, tid, _ = sd.reuse("task", t["key"], wanted, fetch_task, lambda r: r.get("created_by"), project_of, lambda r, _rev: task_projection_from_server(r), f"task {t['key']}")
        if status == "reused":
            print(f"task exists: {t['title']}")
            continue
        if status in ("drift", "missing") or not ok:
            continue
        adopted, shown = sd.adopt_by_title(existing, t["title"], lambda r: r.get("created_by"), fetch_task, project_of, lambda r, _rev: task_projection_from_server(r), wanted, f"task {t['key']}")
        if adopted == "conflict":
            continue
        if adopted:
            sd.remember("task", t["key"], adopted, wanted, shown)
            print(f"task adopted from an earlier run after full comparison: {t['title']}")
            continue
        body = {"title": t["title"], "body_md": t["body_md"], "kind": t["kind"], "size": t.get("size", "small")}
        if t.get("target"):
            body["target"] = {"contribution_id": ids[t["target"]], "revision": 1}
        s, js = call(base, token, "POST", f"/v1/projects/{slug}/tasks", body, idem=idem_key(slug, "task", t["key"], body))
        if s != 201:
            sd.fail(f"task {t['key']} failed: {s} {js}")
            continue
        shown = task_projection_from_server(js)
        if digest(shown) != digest(wanted):
            sd.fail(f"task {t['key']} was created as {js['id']} but the server record does not match the package; not recording it as seeded")
            continue
        sd.remember("task", t["key"], js["id"], wanted, shown)
        print(f"created task: {t['title']}")

    # --- Posts: root threads in the project. ---
    ok, existing = list_all(base, f"/v1/posts?project={slug}", args.page_size)
    if not ok:
        sd.fail("could not list the project's posts; not creating any")
    for p in posts:
        wanted = post_projection_from_package(p)
        status, pid, _ = sd.reuse("post", p["key"], wanted, fetch_post, lambda r: r.get("author_id"), project_of, lambda r, _rev: post_projection_from_server(r), f"post {p['key']}")
        if status == "reused":
            print(f"post exists: {p['title']}")
            continue
        if status in ("drift", "missing") or not ok:
            continue
        adopted, shown = sd.adopt_by_title(existing, p["title"], lambda r: r.get("author_id"), fetch_post, project_of, lambda r, _rev: post_projection_from_server(r), wanted, f"post {p['key']}")
        if adopted == "conflict":
            continue
        if adopted:
            sd.remember("post", p["key"], adopted, wanted, shown)
            print(f"post adopted from an earlier run after full comparison: {p['title']}")
            continue
        body = {"project_id": slug, "title": p["title"], "body_md": p["body_md"]}
        s, js = call(base, token, "POST", "/v1/posts", body, idem=idem_key(slug, "post", p["key"], body))
        if s != 201:
            sd.fail(f"post {p['key']} failed: {s} {js}")
            continue
        shown = post_projection_from_server(js)
        if digest(shown) != digest(wanted):
            sd.fail(f"post {p['key']} was created as {js['id']} but the server record does not match the package; not recording it as seeded")
            continue
        sd.remember("post", p["key"], js["id"], wanted, shown)
        print(f"created post: {p['title']}")

    # --- Roles: a grant counts only when the project afterwards shows the role. ---
    for cid in args.co_maintainer:
        s, js = call(base, token, "POST", f"/v1/projects/{slug}/roles", {"contributor_id": cid, "role": "maintainer"}, idem=idem_key(slug, "role", cid, {"cid": cid}))
        s2, pj2 = call(base, None, "GET", f"/v1/projects/{slug}")
        holds = s2 == 200 and any(r.get("contributor_id") == cid and r.get("role") == "maintainer" for r in (pj2.get("roles") or []))
        if holds:
            sd.state["records"][f"role:{cid}"] = {"id": cid, "role": "maintainer", "project_id": project_id}
            sd.save()
            print(f"maintainer role for {cid}: held (grant returned {s})")
        else:
            sd.state["records"].pop(f"role:{cid}", None)
            sd.save()
            sd.fail(f"maintainer role for {cid} is not held after the grant (grant returned {s}: {js}); retry later or grant by hand")

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
