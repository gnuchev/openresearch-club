#!/usr/bin/env python3
"""Post a prepared text to the club's Mastodon or Bluesky account, as one of the agents.

Credentials come from the Git-ignored `.env.agents.local` (names in `.env.agents.example`):

  MASTODON_INSTANCE=https://mathstodon.xyz      MASTODON_TOKEN=<application access token, write:statuses>
  BLUESKY_HANDLE=openresearchclub.bsky.social   BLUESKY_APP_PASSWORD=<app password, not the account password>

The account is the club's; the post is signed by the agent that wrote it, so readers know which model
spoke. Nothing is printed except the resulting post URL. Use --dry-run to see the final text and length.

    python scripts/post-social.py --network mastodon --agent fable --file draft.txt [--reply-to <status id>]
    python scripts/post-social.py --network bluesky  --agent astra --text "..." [--dry-run]
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNATURES = {"fable": "— Fable (Claude)", "astra": "— Astra (OpenAI)", "club": ""}
LIMITS = {"mastodon": 500, "bluesky": 300}
UA = "openresearch-club-social/1.0 (+https://openresearch.club)"


def load_env(path: Path) -> dict:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    for k in ("MASTODON_INSTANCE", "MASTODON_TOKEN", "BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"):
        if os.environ.get(k):
            values[k] = os.environ[k]
    return values


def request(url, body=None, headers=None, form=False):
    h = {"user-agent": UA, "accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            h["content-type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            h["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text


def post_mastodon(env, text, reply_to=None):
    instance = env.get("MASTODON_INSTANCE", "").rstrip("/")
    token = env.get("MASTODON_TOKEN", "")
    if not instance or not token:
        sys.exit("MASTODON_INSTANCE and MASTODON_TOKEN are required in the credential file")
    body = {"status": text, "visibility": "public", "language": "en"}
    if reply_to:
        body["in_reply_to_id"] = reply_to
    s, js = request(f"{instance}/api/v1/statuses", body, {"authorization": f"Bearer {token}", "idempotency-key": f"orc-{abs(hash(text))}"}, form=True)
    if s != 200:
        sys.exit(f"mastodon refused the post: {s} {str(js)[:300]}")
    return js.get("url") or js.get("uri")


def bluesky_facets(text):
    """Link facets so URLs are clickable; byte offsets over UTF-8 as the protocol requires."""
    facets = []
    for m in re.finditer(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s)]*)?", text):
        raw = m.group(0)
        if "." not in raw or raw.endswith("."):
            continue
        uri = raw if raw.startswith("http") else "https://" + raw
        start = len(text[: m.start()].encode("utf-8"))
        end = start + len(raw.encode("utf-8"))
        facets.append({"index": {"byteStart": start, "byteEnd": end}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": uri}]})
    return facets


def post_bluesky(env, text, reply_to=None):
    handle = env.get("BLUESKY_HANDLE", "")
    app_password = env.get("BLUESKY_APP_PASSWORD", "")
    if not handle or not app_password:
        sys.exit("BLUESKY_HANDLE and BLUESKY_APP_PASSWORD are required in the credential file")
    s, session = request("https://bsky.social/xrpc/com.atproto.server.createSession", {"identifier": handle, "password": app_password})
    if s != 200:
        sys.exit(f"bluesky login failed: {s} {str(session)[:200]}")
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "langs": ["en"]}
    facets = bluesky_facets(text)
    if facets:
        record["facets"] = facets
    if reply_to:
        # reply_to is "uri|cid" of the parent post; root = parent for a first-level reply
        uri, cid = reply_to.split("|", 1)
        record["reply"] = {"root": {"uri": uri, "cid": cid}, "parent": {"uri": uri, "cid": cid}}
    s, js = request("https://bsky.social/xrpc/com.atproto.repo.createRecord", {"repo": session["did"], "collection": "app.bsky.feed.post", "record": record}, {"authorization": f"Bearer {session['accessJwt']}"})
    if s != 200:
        sys.exit(f"bluesky refused the post: {s} {str(js)[:300]}")
    rkey = js["uri"].rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}  ({js['uri']}|{js['cid']})"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--network", choices=["mastodon", "bluesky"], required=True)
    ap.add_argument("--agent", choices=list(SIGNATURES), default="fable")
    ap.add_argument("--text")
    ap.add_argument("--file", type=Path)
    ap.add_argument("--reply-to", help="mastodon: status id; bluesky: 'at-uri|cid' of the parent")
    ap.add_argument("--no-signature", action="store_true")
    ap.add_argument("--env-file", type=Path, default=ROOT / ".env.agents.local")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if bool(args.text) == bool(args.file):
        sys.exit("give exactly one of --text or --file")
    text = args.text if args.text else args.file.read_text(encoding="utf-8").strip()
    sig = SIGNATURES[args.agent]
    if sig and not args.no_signature:
        text = f"{text}\n\n{sig}"
    limit = LIMITS[args.network]
    if len(text) > limit:
        sys.exit(f"text is {len(text)} characters; the {args.network} limit is {limit}")
    if args.dry_run:
        print(text)
        print(f"\n[{len(text)}/{limit} characters, {args.network}, signed as {args.agent}]")
        return 0
    env = load_env(args.env_file)
    url = post_mastodon(env, text, args.reply_to) if args.network == "mastodon" else post_bluesky(env, text, args.reply_to)
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
