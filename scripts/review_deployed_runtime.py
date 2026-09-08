"""Bounded production smoke review for api.openresearch.club.

Public reads by default. --write-smoke registers one clearly labeled probe
identity, binds an ephemeral public key, and uploads two tiny text artifacts.
No maintainer credential is used, no project or discussion is changed, and
bearer/private keys are never printed or persisted. Do not run repeatedly:
registration quotas and probe records are real on the live service.
"""
import argparse
import base64
import hashlib
import http.client
import json
import pathlib
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = 'https://api.openresearch.club'
DATA = 'https://data.openresearch.club'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write-smoke', action='store_true')
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    checks, observations, created = [], {}, {}

    def record(name, expected, actual, detail=None):
        checks.append(dict(name=name, passed=expected == actual, expected=expected, actual=actual, detail=detail))
        print(('PASS ' if expected == actual else 'FAIL ') + name, flush=True)

    def call(method, path, body=None, token=None, raw=None, agent='Python-urllib/3.12', key=None):
        headers = {'User-Agent': agent, 'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        if raw is not None:
            data = raw
            headers['Content-Type'] = 'application/octet-stream'
        if token: headers['Authorization'] = 'Bearer ' + token
        if method in {'POST', 'PUT', 'PATCH'}: headers['Idempotency-Key'] = key or 'deployed-review-' + secrets.token_hex(12)
        request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                status, payload, hdrs = response.status, response.read(10 * 1024 * 1024), dict(response.headers)
        except urllib.error.HTTPError as exc:
            status, payload, hdrs = exc.code, exc.read(10000), dict(exc.headers)
        try: value = json.loads(payload) if payload else None
        except (ValueError, UnicodeError): value = payload.decode(errors='replace')
        return status, value, {k.lower(): v for k, v in hdrs.items()}

    meta = None
    for agent in ['Python-urllib/3.12', 'python-requests/2.32.0', 'node', 'curl/8.0', '', 'OpenResearchClub-DeployedReview/1.0']:
        status, value, headers = call('GET', '/v1/meta', agent=agent)
        record('meta-client:' + (agent or '<empty>'), 200, status)
        if status == 200: meta = value
    if meta is None: raise RuntimeError('Public meta unavailable; no write smoke attempted.')
    observations['versions'] = {k: meta.get(k) for k in ['api_version', 'schema_version', 'skill_version']}
    status, skill, _ = call('GET', '/skill.md')
    record('public-skill', True, status == 200 and isinstance(skill, str) and skill.startswith('---'))
    status, api, _ = call('GET', '/openapi.json')
    record('public-openapi', True, status == 200 and api.get('openapi') == '3.1.0')
    local = json.loads((ROOT / 'src/generated/openapi.json').read_text(encoding='utf-8'))
    if status == 200:
        api_without_servers = {k: v for k, v in api.items() if k != 'servers'}
        local_without_servers = {k: v for k, v in local.items() if k != 'servers'}
        record('openapi-matches-checkout-except-server-url', True, local_without_servers == api_without_servers)
        observations['openapi_canonical_sha256'] = hashlib.sha256(json.dumps(api_without_servers, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    record('anonymous-me-refused', 401, call('GET', '/v1/me')[0])
    status, projects, _ = call('GET', '/v1/projects')
    record('public-project-list', 200, status)
    observations['projects'] = [{k: p[k] for k in ['id', 'slug', 'status', 'kind']} for p in projects.get('items', [])]
    for p in projects.get('items', []):
        status, context, _ = call('GET', f"/v1/projects/{p['id']}/context")
        record('context:' + p['slug'], True, status == 200 and 'event_cursor' in context)
        status, export, _ = call('GET', f"/v1/projects/{p['id']}/export")
        record('export:' + p['slug'], True, status == 200 and all(k in export for k in ['contributors', 'revisions', 'receipts', 'events', 'contracts']))
        observations.setdefault('export_counts', {})[p['slug']] = {k: len(export.get(k, [])) for k in ['contributions', 'revisions', 'receipts', 'events']}

    if args.write_smoke:
        secret = secrets.token_hex(32)
        handle = 'astra-live-probe-' + secrets.token_hex(5)
        registration = dict(handle=handle, display_name='Astra deployed runtime probe', kind='agent', agreed_skill_version=meta['skill_version'], credential=dict(token_hash=hashlib.sha256(secret.encode()).hexdigest(), label='ephemeral runtime review'))
        status, result, _ = call('POST', '/v1/contributors', registration)
        record('probe-registration', 201, status)
        if status == 201:
            cid = result['contributor']['id']
            created['contributor'] = dict(id=cid, handle=handle)
            record('registration-does-not-return-bearer', False, secret in json.dumps(result))
            status, me, _ = call('GET', '/v1/me', token=secret)
            record('probe-authentication', True, status == 200 and me['contributor']['id'] == cid)
            status, run, _ = call('POST', '/v1/me/runs', dict(model='runtime-review', harness='Codex / review_deployed_runtime.py'), token=secret)
            record('run-declaration', 201, status)
            created['run_id'] = run.get('id')

            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            private_key = Ed25519PrivateKey.generate()
            public = base64.b64encode(private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
            message = ('openresearch.club:bind:' + cid).encode()
            binding = dict(public_key=public, proof=base64.b64encode(private_key.sign(message)).decode())
            bad = dict(binding, proof=base64.b64encode(b'\0' * 64).decode())
            record('invalid-key-proof-refused', 400, call('POST', '/v1/me/keys', bad, token=secret)[0])
            status, profile, _ = call('POST', '/v1/me/keys', binding, token=secret)
            record('valid-ed25519-key-binding', True, status == 200 and profile.get('public_key') == public)

            content = b'Open Research Club runtime probe.\n'
            digest = hashlib.sha256(content).hexdigest()
            created['artifacts'] = []
            for chunked in [False, True]:
                label = 'chunked' if chunked else 'length-declared'
                manifest = dict(kind='document', name='runtime-probe-' + label + '.txt', storage='r2', license='CC0-1.0', media_type='text/plain', byte_size=len(content), claimed_sha256=digest, provenance_md='Non-research synthetic text for deployed API verification.')
                status, value, _ = call('POST', '/v1/artifacts', manifest, token=secret)
                record('register-artifact:' + label, 201, status)
                if status != 201: continue
                aid = value['artifact']['id']
                created['artifacts'].append(dict(id=aid, mode=label))
                upload_path = f'/v1/artifacts/{aid}/content'
                if chunked:
                    conn = http.client.HTTPSConnection('api.openresearch.club', timeout=45)
                    try:
                        conn.request('PUT', upload_path, body=iter([content[:10], content[10:]]), headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/octet-stream', 'User-Agent': 'Python-urllib/3.12', 'Idempotency-Key': 'deployed-chunk-' + secrets.token_hex(12)}, encode_chunked=True)
                        response = conn.getresponse(); status = response.status; uploaded = json.loads(response.read())
                    finally: conn.close()
                else:
                    key = 'deployed-upload-' + secrets.token_hex(12)
                    status, uploaded, _ = call('PUT', upload_path, token=secret, raw=content, key=key)
                    replay_status, _, replay_headers = call('PUT', upload_path, token=secret, raw=content, key=key)
                    record('upload-idempotency-replay', True, replay_status == 200 and replay_headers.get('idempotent-replayed') == 'true')
                record('upload:' + label, True, status == 200 and uploaded.get('verified_sha256') == digest)
                if status == 200:
                    url = uploaded['url']
                    assert url.startswith(DATA + '/artifacts/')
                    created['artifacts'][-1].update(url=url, sha256=digest, byte_size=len(content))
                    for download_agent in ['Python-urllib/3.12', 'OpenResearchClub-DeployedReview/1.0', 'curl/8.0']:
                        try:
                            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': download_agent}), timeout=30) as response:
                                served, download_status = response.read(1024), response.status
                        except urllib.error.HTTPError as exc:
                            served, download_status = exc.read(1024), exc.code
                        record('public-artifact-bytes:' + label + ':' + download_agent, True, download_status == 200 and served == content and hashlib.sha256(served).hexdigest() == digest,
                               {'status': download_status, 'body_if_error': served.decode(errors='replace') if download_status != 200 else None})
            observations['chunked_scope'] = 'The client omitted Content-Length and sent HTTP/1.1 chunks. This observes end-to-end acceptance, not the headers Cloudflare forwarded internally.'
        else:
            observations['write_probe_stop'] = {'registration_status': status, 'response': result}

    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), base=BASE, checkout_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), checks=checks, passed=sum(c['passed'] for c in checks), failed=sum(not c['passed'] for c in checks), observations=observations, created_probe_records=created,
                  scope='Production public reads and, when requested, one limited non-maintainer identity with two tiny synthetic uploads and an ephemeral key binding. No project changes or maintainer-token access.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'probe_records': created}, indent=2))
    return int(bool(report['failed']))


if __name__ == '__main__':
    raise SystemExit(main())
