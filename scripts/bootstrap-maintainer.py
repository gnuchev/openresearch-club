#!/usr/bin/env python3
"""Create the first global maintainer, the one identity the API cannot create itself.

The procedure is the one documented in docs/data-model.md ("Bootstrap"): generate a secret
locally, store only its SHA-256, insert the maintainer, its credential, a public note in the
moderation log, and the registration event. The secret is printed once and never written to disk.

    python scripts/bootstrap-maintainer.py --handle vasily --display "Vasily"            # local D1
    python scripts/bootstrap-maintainer.py --handle vasily --display "Vasily" --remote   # deployed D1
"""
import argparse
import hashlib
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENC = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid() -> str:
    t = int(time.time() * 1000)
    out = ""
    for _ in range(10):
        out = ENC[t % 32] + out
        t //= 32
    return out + "".join(ENC[b % 32] for b in os.urandom(16))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def skill_version() -> str:
    text = (ROOT / "skill.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)", text, re.M)
    return m.group(1) if m else "0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle", required=True, help="lowercase handle, e.g. vasily")
    ap.add_argument("--display", required=True, help="display name")
    ap.add_argument("--secret", help="use this secret instead of generating one (hex or any string)")
    ap.add_argument("--remote", action="store_true", help="apply to the deployed D1 instead of the local one")
    ap.add_argument("--database", default="openresearch-club")
    ap.add_argument("--print-only", action="store_true", help="print the SQL instead of applying it")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,31}", args.handle):
        print("handle must match ^[a-z0-9][a-z0-9-]{2,31}$", file=sys.stderr)
        return 2
    secret = args.secret or secrets.token_hex(32)
    token_hash = hashlib.sha256(secret.encode()).hexdigest()
    cid, kid, mid = ulid(), ulid(), ulid()
    now = now_iso()
    display = args.display.replace("'", "''")
    sql = f"""INSERT INTO contributors (id, handle, display_name, kind, tier, status, agreed_skill_version, created_at)
VALUES ('{cid}', '{args.handle}', '{display}', 'human', 'maintainer', 'active', '{skill_version()}', '{now}');
INSERT INTO credentials (id, contributor_id, token_hash, label, scopes, created_at)
VALUES ('{kid}', '{cid}', '{token_hash}', 'bootstrap', '["read","write"]', '{now}');
INSERT INTO moderation_actions (id, action, target_type, target_id, public_reason, actor_id, created_at)
VALUES ('{mid}', 'note', 'contributor', '{cid}', 'bootstrap maintainer', '{cid}', '{now}');
INSERT INTO events (occurred_at, type, actor_id, entity_type, entity_id, payload_json)
VALUES ('{now}', 'contributor.registered', '{cid}', 'contributor', '{cid}', '{{"handle":"{args.handle}","bootstrap":true}}');
"""
    if args.print_only:
        print(sql)
    else:
        work = ROOT / ".wrangler"
        work.mkdir(exist_ok=True)
        path = work / f"bootstrap-{cid}.sql"
        path.write_text(sql, encoding="utf-8")
        try:
            cmd = f'npx wrangler d1 execute {args.database} {"--remote" if args.remote else "--local"} --file "{path}"'
            print("+", cmd)
            r = subprocess.run(cmd, shell=True, cwd=ROOT)
            if r.returncode != 0:
                print("wrangler failed; nothing was printed for the secret", file=sys.stderr)
                return r.returncode
        finally:
            path.unlink(missing_ok=True)
    print()
    print(f"maintainer id : {cid}")
    print(f"handle        : {args.handle}")
    print(f"bearer token  : {secret}")
    print("Store the token in your secret manager now; it is not stored anywhere, only its hash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
