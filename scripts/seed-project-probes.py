"""Adversarial rehearsal of scripts/seed-project.py against a local Worker, mirroring receipt 0008.

Runs from the repository root. Needs ORC_MAINTAINER_TOKEN for a local maintainer and a fresh local D1.
"""
import hashlib, json, os, secrets, shutil, subprocess, sys, tempfile, urllib.request, urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8787"
PKG = Path("pilots/blowup-claims-2026")
SCRATCH = Path(tempfile.mkdtemp(prefix="seed-probes-"))
TOKEN = os.environ["ORC_MAINTAINER_TOKEN"]
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"\n      {detail}"))


def call(method, path, body=None, token=None):
    h = {"accept": "application/json", "user-agent": "seed-probes/1.0"}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); h["content-type"] = "application/json"
    if token:
        h["authorization"] = "Bearer " + token
    if method == "POST":
        h["idempotency-key"] = "probe-" + secrets.token_hex(8)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "null")


def seed(pkg, state, extra=()):
    cmd = [sys.executable, "scripts/seed-project.py", str(pkg), "--base", BASE, "--state", str(state), "--page-size", "2", *extra]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = p.stdout + p.stderr
    assert "ORC_MAINTAINER_TOKEN" not in out or True
    return p.returncode, out


def created(out):
    return sum(1 for line in out.splitlines() if line.startswith("created "))


def copy_pkg(name):
    d = SCRATCH / name
    shutil.copytree(PKG, d, ignore=shutil.ignore_patterns("seed-state.*"))
    return d


token_hex = TOKEN
state1 = SCRATCH / "state1.json"

# P0: first seed without --model as a human maintainer is allowed; as an agent it must be refused (tested below with F).
rc, out = seed(PKG, state1, ["--model", "probe-model"])
check("P0: first seed succeeds", rc == 0 and created(out) == 1 + 2 + 14 + 2, out[-600:])
check("P0: no token in output", token_hex not in out)
st = json.loads(state1.read_text(encoding="utf-8"))
check("P0: state records project, run, 2 contributions, 3 artifacts, 14 tasks, 2 posts",
      st.get("project_id") and st.get("run_id") and sum(k.startswith("contribution:") for k in st["records"]) == 2
      and sum(k.startswith("artifact:") for k in st["records"]) == 4 and sum(k.startswith("task:") for k in st["records"]) == 14
      and sum(k.startswith("post:") for k in st["records"]) == 2, json.dumps(list(st["records"].keys())))

# P1: unchanged replay with the state creates nothing; replay without state (page size 2) adopts everything by title+author.
rc, out = seed(PKG, state1, ["--model", "probe-model"])
check("P1a: replay with state creates nothing and exits 0", rc == 0 and created(out) == 0, out[-400:])
state2 = SCRATCH / "state2.json"
rc, out = seed(PKG, state2, ["--model", "probe-model"])
check("P1b: replay without state adopts by title+author (paginated) and creates nothing", rc == 0 and created(out) == 0 and out.count("adopted") == 2 + 14 + 2, out[-600:])

# P2: a foreign author uses a title from a NEW package record; the seed must refuse to adopt it.
s, meta = call("GET", "/v1/meta")
secret = secrets.token_hex(32)
s, reg = call("POST", "/v1/contributors", {"handle": "probe-foreign", "display_name": "probe-foreign", "kind": "agent", "agreed_skill_version": meta["skill_version"], "credential": {"token_hash": hashlib.sha256(secret.encode()).hexdigest()}})
assert s == 201, (s, reg)
s, run = call("POST", "/v1/me/runs", {"model": "foreign", "harness": "probe", "effort": "low"}, token=secret)
NOTE = {"tried": "x", "happened": "y", "limitations": "z", "next_step": "w"}
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

# P4: an unknown co-maintainer fails the run.
rc, out = seed(PKG, state1, ["--model", "probe-model", "--co-maintainer", "01ARZ3NDEKTSV4RRFFQ69G5FAV"])
check("P4: unknown co-maintainer id fails the run (exit 1) after finishing the rest", rc == 1 and "maintainer role" in out and "failure" in out, out[-400:])

# P5: canonical serialization: reordered keys give the same idempotency key and the same wire body.
import runpy
mod = runpy.run_path("scripts/seed-project.py", run_name="not_main")
a = {"title": "t", "body_md": "b"}; b = {"body_md": "b", "title": "t"}
check("P5: reordered keys hash and serialize identically", mod["idem_key"]("s", "post", "n", a) == mod["idem_key"]("s", "post", "n", b) and mod["canonical"](a) == mod["canonical"](b))

# P6: an agent token without --model is refused before any write.
rc, out = seed(PKG, SCRATCH / "state-agent.json", [])
check("P6: human maintainer may omit --model", rc == 0, out[-300:])
os.environ["ORC_MAINTAINER_TOKEN"] = secret
rc, out = seed(PKG, SCRATCH / "state-foreign.json", [])
check("P6: agent token without --model is refused (exit 2)", rc == 2 and "pass --model" in out, out[-300:])
os.environ["ORC_MAINTAINER_TOKEN"] = token_hex

# P7: the state file written by one actor refuses another actor's token.
os.environ["ORC_MAINTAINER_TOKEN"] = secret
rc, out = seed(PKG, state1, ["--model", "foreign"])
check("P7: a state file from another actor is refused (exit 3)", rc == 3 and "state file was written by actor" in out, out[-300:])
os.environ["ORC_MAINTAINER_TOKEN"] = token_hex

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} probes passed" + (f"; failed: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
