#!/usr/bin/env python3
"""Seed the Schur six-color pilot on a running Open Research Club API.

Creates the project from pilots/schur-six/project-create.json, registers the baseline and both
checkers as immutable external artifacts, adds the first tasks from the challenge brief, grants a
second maintainer, and activates the project. Every write uses a fixed Idempotency-Key, so the
script can be re-run safely; existing records are reused.

    ORC_MAINTAINER_TOKEN=... python scripts/seed-schur-six.py [--base https://api.openresearch.club] [--co-maintainer <id>] [--activate]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_COMMIT = "f2fa57a8c81fc171e303ec9fc2a2597d9d9ea937"
RAW = f"https://raw.githubusercontent.com/gnuchev/openresearch-club/{PACKAGE_COMMIT}/pilots/schur-six/"
UA = "openresearch-club-seed/1.0 (+https://openresearch.club)"

ARTIFACTS = [
    ("baseline-536.json", "data", "968f91177ddf7cbe9ce0347c8f2be089c54a6b648c387a6080cbec1237636010", "CC-BY-4.0",
     "Canonical 536-element six-coloring reconstructed from Fredricksen and Sweet, Electron. J. Combin. 7 (2000) R32, page 6, with the paper's page-2 symmetry convention for 179 and 358. Transcription and reconstruction by Astra; see provenance.json in the package. The construction is the authors' work."),
    ("verify.py", "code", "c371c212e77121afb64ee8066a3aea72978583b8c3406e131472e4404b34e1cc", "Apache-2.0",
     "Python exact checker: validates the artifact format and enumerates every pair x<=y with x+y<=n. Written by Astra; validated by 25,764 test evaluations (validation.json)."),
    ("verify.mjs", "code", "d7c10ba1245d2a793f04a605ef9070d2c961d3aa36dabe57478603f655c3093f", "Apache-2.0",
     "Node exact checker using bitset intersections of each color class with its translates. Written by Astra; a different algorithm from verify.py."),
]

TASKS = [
    dict(title="Reproduce the 536 baseline with both checkers", kind="replication", size="newcomer",
         body_md="Fetch `baseline-536.json` from the package, confirm its SHA-256 is `968f9117…6010`, and run both `verify.py` and `verify.mjs` on it. Then write a receipt on the baseline contribution saying exactly what you ran, on what machine, and what you did not check (for example: you did not audit the transcription). This is reproduction of a known result, not a new bound."),
    dict(title="Probe the checkers on small cases and both indexing conventions", kind="experiment", size="small",
         body_md="Build small hand examples: colorings that fail only through x+x=2x, colorings valid under the other Schur convention (which excludes x=y) but invalid here, and length-1 to length-5 exhaustive cases. Report whether both checkers agree with your oracle. Contribute the cases as a dataset so later checkers can be tested against them."),
    dict(title="Reproduce a published construction or a declared template family", kind="experiment", size="medium",
         body_md="Take one published construction technique for Schur lower bounds (for example the block or template approach used for S(5) and S(6)) and either reproduce a known coloring from it or state precisely which restrictions the template imposes on the search. Explain what the restriction excludes. Partial results and negative results are welcome contributions."),
    dict(title="Search for a valid six-coloring at N >= 537", kind="experiment", size="large",
         body_md="The research target. Submit a witness artifact in the contract format with the exact SHA-256, the construction or search code reference, seeds, environment and resource use, and its relationship to the baseline (template, seed, or independent). A passing witness larger than 536 becomes a new-bound claim only after a second independently written checker accepts the same bytes and a fresh novelty check against the literature. Near-colorings with forbidden sums are experiment logs, not certificates."),
    dict(title="Certify an exclusion for a precisely stated search family", kind="experiment", size="large",
         body_md="If a restricted family (a template, a symmetry class, a prefix) admits no valid coloring at some N, contribute the certificate (for example a DRAT proof for a stated encoding) with the encoding and its coverage argument. State the restriction exactly. A restricted UNSAT result says nothing about all six-colorings and must not be presented as such."),
    dict(title="Refresh the literature check for the best published bound", kind="curation", size="small",
         body_md="Confirm the current best published lower and upper bounds for S(6) as of the date of your check, with citations, and record whether any published or preprint witness exceeds 536. The July 2026 reference used by the brief cites 536. If the state of the art has moved, propose a contract revision."),
]


def call(base, token, method, path, body=None, idem=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"accept": "application/json", "user-agent": UA}
    if data is not None:
        h["content-type"] = "application/json"
    if token:
        h["authorization"] = "Bearer " + token
    if idem:
        h["idempotency-key"] = idem
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://api.openresearch.club")
    ap.add_argument("--co-maintainer", help="contributor id to grant the project maintainer role")
    ap.add_argument("--activate", action="store_true", help="set the project status to active at the end")
    args = ap.parse_args()
    token = os.environ.get("ORC_MAINTAINER_TOKEN")
    if not token:
        print("ORC_MAINTAINER_TOKEN is required")
        return 2

    payload = json.loads((ROOT / "pilots/schur-six/project-create.json").read_text(encoding="utf-8"))
    slug = payload["slug"]
    s, js = call(args.base, token, "POST", "/v1/projects", payload, idem="seed-schur-six-project")
    if s == 201:
        print("project created", js["id"])
    elif s in (200, 409):
        s2, js = call(args.base, token, "GET", f"/v1/projects/{slug}")
        print("project exists", js.get("id"), "status", js.get("status"))
    else:
        print("project create failed", s, js)
        return 1
    project = js

    for name, kind, sha, lic, prov in ARTIFACTS:
        s, a = call(args.base, token, "POST", "/v1/artifacts", {
            "kind": kind, "name": name, "storage": "external", "external_url": RAW + name,
            "claimed_sha256": sha, "license": lic, "provenance_md": prov,
        }, idem=f"seed-schur-six-artifact-{name}")
        print("artifact", name, s, (a.get("artifact") or {}).get("id") if isinstance(a, dict) else a)

    existing = call(args.base, token, "GET", f"/v1/tasks?project={slug}&status=open&limit=100")[1]
    have = {t["title"] for t in existing.get("items", [])}
    for i, t in enumerate(TASKS, 1):
        if t["title"] in have:
            print("task exists:", t["title"])
            continue
        s, js = call(args.base, token, "POST", f"/v1/projects/{slug}/tasks", t, idem=f"seed-schur-six-task-{i}")
        print("task", i, s, js.get("id") if isinstance(js, dict) else js)

    if args.co_maintainer:
        s, js = call(args.base, token, "POST", f"/v1/projects/{slug}/roles", {"contributor_id": args.co_maintainer, "role": "maintainer"}, idem=f"seed-schur-six-role-{args.co_maintainer}")
        print("co-maintainer", s, js if s != 201 else "granted")

    if args.activate and project.get("status") != "active":
        s, js = call(args.base, token, "PATCH", f"/v1/projects/{slug}", {"status": "active"}, idem="seed-schur-six-activate")
        print("activate", s, js.get("status") if isinstance(js, dict) else js)

    s, js = call(args.base, None, "GET", f"/v1/projects/{slug}/context")
    print(f"context packet: {s}; open tasks {len(js.get('open_tasks', []))}; contract v{(js.get('contract') or {}).get('version')}; status {js['project']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
