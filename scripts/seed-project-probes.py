"""Adversarial rehearsal of scripts/seed-project.py against a local Worker.

Mirrors the probes of receipts 0008 and 0009 (docs/reviews). Runs from the repository root against
a fresh local D1 on 127.0.0.1:8787, with ORC_MAINTAINER_TOKEN for a local maintainer. Case C3
inserts an in-flight idempotency row through `wrangler d1 execute --local`, so it needs the
local state that the Worker is using.

    npx wrangler d1 migrations apply openresearch-club --local
    python scripts/bootstrap-maintainer.py --handle you --display "You"
    npx wrangler dev --local --port 8787 --var SITE_PREFIX:true
    ORC_MAINTAINER_TOKEN=<token> python scripts/seed-project-probes.py
"""
import hashlib, json, os, runpy, secrets, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8787"
PKG = Path("pilots/blowup-claims-2026")
SCRATCH = Path(tempfile.mkdtemp(prefix="seed-probes-"))
TOKEN = os.environ["ORC_MAINTAINER_TOKEN"]
RESULTS = []
SEEDER = runpy.run_path("scripts/seed-project.py", run_name="not_main")


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"\n      {detail}"))


def call(method, path, body=None, token=None):
    h = {"accept": "application/json", "user-agent": "seed-probes/2.0"}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); h["content-type"] = "application/json"
    if token:
        h["authorization"] = "Bearer " + token
    if method in ("POST", "PATCH", "PUT"):
        h["idempotency-key"] = "probe-" + secrets.token_hex(8)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "null")


def seed(pkg, state, extra=(), token=None):
    cmd = [sys.executable, "scripts/seed-project.py", str(pkg), "--base", BASE, "--state", str(state), "--page-size", "2", *extra]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "ORC_MAINTAINER_TOKEN": token or TOKEN}
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    return p.returncode, p.stdout + p.stderr


def created(out):
    return sum(1 for line in out.splitlines() if line.startswith("created "))


def copy_pkg(name):
    d = SCRATCH / name
    shutil.copytree(PKG, d, ignore=shutil.ignore_patterns("seed-state.*"))
    return d


def d1(sql):
    p = subprocess.run(["npx", "wrangler", "d1", "execute", "openresearch-club", "--local", "--command", sql], capture_output=True, text=True, encoding="utf-8", shell=(os.name == "nt"))
    return p.returncode == 0, p.stdout + p.stderr


NOTE = {"tried": "x", "happened": "y", "limitations": "z", "next_step": "w"}
s, meta = call("GET", "/v1/meta")
s, me = call("GET", "/v1/me", token=TOKEN)
ME = me["contributor"]["id"]
state1 = SCRATCH / "state1.json"
package = json.loads((PKG / "contributions.json").read_text(encoding="utf-8"))
pkg_tasks = json.loads((PKG / "tasks.json").read_text(encoding="utf-8"))
pkg_posts = json.loads((PKG / "posts.json").read_text(encoding="utf-8"))
n_art = sum(len(c.get("artifacts", [])) for c in package)

# P0: first seed; every created record is verified against the server before it is recorded.
rc, out = seed(PKG, state1, ["--model", "probe-model"])
check("P0: first seed succeeds", rc == 0 and created(out) == 1 + len(package) + len(pkg_tasks) + len(pkg_posts), out[-600:])
check("P0: no token in output", TOKEN not in out)
st = json.loads(state1.read_text(encoding="utf-8"))
check("P0: state is bound to actor, base, slug and project and records every record with a verified fingerprint",
      st.get("actor_id") == ME and st.get("slug") == "blowup-claims-2026" and st.get("project_id") and st.get("base")
      and sum(k.startswith("contribution:") for k in st["records"]) == len(package) and sum(k.startswith("artifact:") for k in st["records"]) == n_art
      and sum(k.startswith("task:") for k in st["records"]) == len(pkg_tasks) and sum(k.startswith("post:") for k in st["records"]) == len(pkg_posts)
      and all("verified_sha256" in v for k, v in st["records"].items() if k.startswith(("contribution:", "task:", "post:")))
      and all(v.get("revision") == 1 for k, v in st["records"].items() if k.startswith("contribution:")), json.dumps(st)[:400])

# P1: unchanged replay with the state creates nothing; replay without a state adopts after full comparison.
rc, out = seed(PKG, state1, ["--model", "probe-model"])
check("P1a: replay with state creates nothing and exits 0", rc == 0 and created(out) == 0, out[-400:])
state2 = SCRATCH / "state2.json"
rc, out = seed(PKG, state2, ["--model", "probe-model"])
check("P1b: replay without state adopts by title+author after full comparison (paginated) and creates nothing",
      rc == 0 and created(out) == 0 and out.count("adopted") == len(package) + len(pkg_tasks) + len(pkg_posts), out[-600:])

# P2: a foreign author uses a title from a NEW package record; the seed must refuse to adopt it.
secret = secrets.token_hex(32)
s, reg = call("POST", "/v1/contributors", {"handle": "probe-foreign", "display_name": "probe-foreign", "kind": "agent", "agreed_skill_version": meta["skill_version"], "credential": {"token_hash": hashlib.sha256(secret.encode()).hexdigest()}})
assert s == 201, (s, reg)
FOREIGN = reg["contributor"]["id"]
s, run = call("POST", "/v1/me/runs", {"model": "foreign", "harness": "probe", "effort": "low"}, token=secret)
foreign_title = "Claim record: a third claim (probe)"
s, fc = call("POST", "/v1/contributions", {"project_id": "blowup-claims-2026", "kind": "other", "title": foreign_title, "claim": "foreign claim", "note": NOTE, "fields": {}, "run_id": run["id"]}, token=secret)
check("P2: foreign contribution with the new title exists", s == 201, str(fc)[:200])
pkg2 = copy_pkg("pkg-foreign")
contribs = json.loads((pkg2 / "contributions.json").read_text(encoding="utf-8"))
contribs.append({"key": "third", "kind": "other", "title": foreign_title, "claim": "our claim", "note": NOTE, "fields": {}, "artifacts": []})
(pkg2 / "contributions.json").write_text(json.dumps(contribs), encoding="utf-8")
tasks = json.loads((pkg2 / "tasks.json").read_text(encoding="utf-8"))
tasks.append({"key": "third-check", "title": "Check the third claim (probe)", "body_md": "b", "kind": "review", "size": "small", "target": "third"})
(pkg2 / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
rc, out = seed(pkg2, state1, ["--model", "probe-model"])
s, tl = call("GET", "/v1/tasks?project=blowup-claims-2026&checks=true&limit=200")
targets = [t["target"]["contribution_id"] for t in tl["items"] if t.get("target")]
check("P2: same-title record by another author is refused (exit 1, conflict reported)", rc == 1 and "another author" in out, out[-500:])
check("P2: no task targets the foreign contribution", fc["id"] not in targets)
check("P2: the dependent task was skipped, not created", "Check the third claim (probe)" not in [t["title"] for t in tl["items"]])

# P3: an edited claim with the same title is drift: fail without --allow-drift, reuse with it, never silently skip.
pkg3 = copy_pkg("pkg-drift")
contribs = json.loads((pkg3 / "contributions.json").read_text(encoding="utf-8"))
contribs[0]["claim"] = contribs[0]["claim"].replace("OpenAI reports", "OpenAI claims")
(pkg3 / "contributions.json").write_text(json.dumps(contribs), encoding="utf-8")
rc, out = seed(pkg3, state1, ["--model", "probe-model"])
check("P3a: edited claim is reported as drift and fails", rc == 1 and "different content" in out and created(out) == 0, out[-500:])
rc, out = seed(pkg3, state1, ["--model", "probe-model", "--allow-drift"])
check("P3b: with --allow-drift the record is kept with a warning, exit 0", rc == 0 and "DRIFT" in out and created(out) == 0, out[-500:])
rc, out = seed(pkg3, SCRATCH / "state3.json", ["--model", "probe-model"])
check("P3c: without state, a same-title record by this actor with different content is a conflict, not adopted", rc == 1 and "different content" in out, out[-500:])

# P4: an unknown co-maintainer fails the run and is not recorded.
rc, out = seed(PKG, state1, ["--model", "probe-model", "--co-maintainer", "01ARZ3NDEKTSV4RRFFQ69G5FAV"])
st = json.loads(state1.read_text(encoding="utf-8"))
check("P4: unknown co-maintainer id fails the run (exit 1) and records no role", rc == 1 and "not held" in out and "role:01ARZ3NDEKTSV4RRFFQ69G5FAV" not in st["records"], out[-400:])

# P5: canonical serialization: reordered keys give the same idempotency key and the same wire body.
a = {"title": "t", "body_md": "b"}; b = {"body_md": "b", "title": "t"}
check("P5: reordered keys hash and serialize identically", SEEDER["idem_key"]("s", "post", "n", a) == SEEDER["idem_key"]("s", "post", "n", b) and SEEDER["canonical"](a) == SEEDER["canonical"](b))

# P6: an agent token without --model is refused before any write; a human maintainer may omit it.
rc, out = seed(PKG, SCRATCH / "state-human.json", [])
check("P6: human maintainer may omit --model", rc == 0, out[-300:])
rc, out = seed(PKG, SCRATCH / "state-foreign.json", [], token=secret)
check("P6: agent token without --model is refused (exit 2)", rc == 2 and "pass --model" in out, out[-300:])

# P7: a state file written by one actor refuses another actor's token.
rc, out = seed(PKG, state1, ["--model", "foreign"], token=secret)
check("P7: a state file from another actor is refused (exit 3)", rc == 3 and "bound to actor" in out, out[-300:])

# C1 (receipt 0009): a same-author record with the expected title and claim but different evidence
# must not be adopted, and the state must never certify evidence the server does not show.
pkgc1 = copy_pkg("pkg-c1")
c1 = json.loads((pkgc1 / "contributions.json").read_text(encoding="utf-8"))
title_c1 = "Claim record: evidence probe (C1)"
c1.append({"key": "c1", "kind": "other", "title": title_c1, "claim": "the same claim", "note": NOTE, "fields": {"would_refute": "wanted", "how_to_check": "wanted"},
           "artifacts": [{"role": "manuscript", "kind": "document", "name": "c1.pdf", "external_url": "https://example.org/c1.pdf", "license": "proprietary-reference"}]})
(pkgc1 / "contributions.json").write_text(json.dumps(c1), encoding="utf-8")
t1 = json.loads((pkgc1 / "tasks.json").read_text(encoding="utf-8"))
t1.append({"key": "c1-check", "title": "Check the C1 record", "body_md": "b", "kind": "review", "size": "small", "target": "c1"})
(pkgc1 / "tasks.json").write_text(json.dumps(t1), encoding="utf-8")
s, myrun = call("POST", "/v1/me/runs", {"model": "probe", "harness": "probe", "effort": "low"}, token=TOKEN)
s, prior = call("POST", "/v1/contributions", {"project_id": "blowup-claims-2026", "kind": "other", "title": title_c1, "claim": "the same claim", "note": {"tried": "other", "happened": "other", "limitations": "other", "next_step": "other"}, "fields": {"would_refute": "different"}, "run_id": myrun["id"]}, token=TOKEN)
check("C1: prior same-author record with same title and claim but different evidence exists", s == 201, str(prior)[:200])
rc, out = seed(pkgc1, SCRATCH / "state-c1.json", ["--model", "probe-model"])
stc1 = json.loads((SCRATCH / "state-c1.json").read_text(encoding="utf-8"))
s, tl = call("GET", "/v1/tasks?project=blowup-claims-2026&checks=true&limit=200")
check("C1: same-author record with different evidence is a conflict, not adopted; dependent task skipped",
      rc == 1 and "different content or evidence" in out and "contribution:c1" not in stc1["records"] and prior["id"] not in [t["target"]["contribution_id"] for t in tl["items"] if t.get("target")], out[-600:])

# C1b: a task by this actor with the same title but a different target must not be adopted.
pkgc1b = copy_pkg("pkg-c1b")
t1b = json.loads((pkgc1b / "tasks.json").read_text(encoding="utf-8"))
t1b[0] = dict(t1b[0], target="euler-unforced")  # same title, different target
(pkgc1b / "tasks.json").write_text(json.dumps(t1b), encoding="utf-8")
rc, out = seed(pkgc1b, SCRATCH / "state-c1b.json", ["--model", "probe-model"])
check("C1b: a same-title task with a different target is a conflict, not adopted", rc == 1 and "different content or evidence" in out and created(out) == 0, out[-500:])

# C2a: a copied state with a changed package slug must be refused before anything is created.
pkgc2 = copy_pkg("pkg-c2")
pc = json.loads((pkgc2 / "project-create.json").read_text(encoding="utf-8"))
pc["slug"] = "blowup-claims-2026-copy"
(pkgc2 / "project-create.json").write_text(json.dumps(pc), encoding="utf-8")
shutil.copy(state1, SCRATCH / "state-c2a.json")
rc, out = seed(pkgc2, SCRATCH / "state-c2a.json", ["--model", "probe-model"])
s, gone = call("GET", "/v1/projects/blowup-claims-2026-copy")
check("C2a: a state bound to another slug is refused (exit 3) and no project is created", rc == 3 and "bound to package slug" in out and s == 404, out[-400:] + f" / GET copy: {s}")

# C2b: an existing slug whose project title conflicts with the package stops before any child write.
s, other = call("POST", "/v1/projects", {"slug": "c2b-existing", "title": "Somebody else's project", "kind": "project", "brief_md": "x"}, token=TOKEN)
assert s == 201, (s, other)
pkgc2b = copy_pkg("pkg-c2b")
pc = json.loads((pkgc2b / "project-create.json").read_text(encoding="utf-8"))
pc["slug"] = "c2b-existing"
(pkgc2b / "project-create.json").write_text(json.dumps(pc), encoding="utf-8")
rc, out = seed(pkgc2b, SCRATCH / "state-c2b.json", ["--model", "probe-model"])
s, ctx = call("GET", "/v1/projects/c2b-existing/context")
check("C2b: conflicting project identity stops the run (exit 3) with zero child writes",
      rc == 3 and "different identity" in out and s == 200 and not ctx["recent_contributions"] and not ctx["open_tasks"] and not ctx["requests_for_checks"], out[-400:])

# C2c: an allowed project drift (status or brief changed by a maintainer later) is reported and the run continues.
s, patched = call("PATCH", "/v1/projects/blowup-claims-2026", {"brief_md": "Brief edited later by a maintainer (probe)."}, token=TOKEN)
assert s == 200, (s, patched)
rc, out = seed(PKG, state1, ["--model", "probe-model"])
check("C2c: a later brief edit is reported as allowed drift and the replay still creates nothing", rc == 0 and "status or brief differs" in out and created(out) == 0, out[-400:])

# C3: a 409 from an in-flight idempotency row is not a granted role; the grant is verified by reading the project.
key = SEEDER["idem_key"]("blowup-claims-2026", "role", FOREIGN, {"cid": FOREIGN})
body_hash = hashlib.sha256(SEEDER["canonical"]({"contributor_id": FOREIGN, "role": "maintainer"}).encode("utf-8")).hexdigest()
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
later = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
ok, msg = d1(f"INSERT INTO idempotency_keys (scope, key, method, target, body_sha256, state, created_at, expires_at) VALUES ('{ME}', '{key}', 'POST', '/v1/projects/blowup-claims-2026/roles', '{body_hash}', 'in_flight', '{now}', '{later}')")
check("C3: in-flight idempotency row inserted for the role grant", ok, msg[-300:])
rc, out = seed(PKG, state1, ["--model", "probe-model", "--co-maintainer", FOREIGN])
st = json.loads(state1.read_text(encoding="utf-8"))
s, pj = call("GET", "/v1/projects/blowup-claims-2026")
held = any(r.get("contributor_id") == FOREIGN and r.get("role") == "maintainer" for r in pj.get("roles", []))
check("C3: a 409 in-flight response is a failure, not a recorded role", rc == 1 and "grant returned 409" in out and f"role:{FOREIGN}" not in st["records"] and not held, out[-400:])
ok, msg = d1(f"DELETE FROM idempotency_keys WHERE scope = '{ME}' AND key = '{key}'")
rc, out = seed(PKG, state1, ["--model", "probe-model", "--co-maintainer", FOREIGN])
st = json.loads(state1.read_text(encoding="utf-8"))
s, pj = call("GET", "/v1/projects/blowup-claims-2026")
held = any(r.get("contributor_id") == FOREIGN and r.get("role") == "maintainer" for r in pj.get("roles", []))
check("C3: after the row is gone the grant is made, verified by reading the project, and recorded", rc == 0 and held and f"role:{FOREIGN}" in st["records"], out[-400:])

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} probes passed" + (f"; failed: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
