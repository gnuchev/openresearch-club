"""Local-only adversarial review of the first Worker implementation.

Requires the isolated review Worker/config described in receipt 0004. Creates
synthetic data. Tokens exist only in memory/environment; the database gets hashes.
Never point this at production or at a development database you want to preserve.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
CHECKS = []
SAMPLES = {}


def uid():
    alphabet = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
    return '01' + ''.join(secrets.choice(alphabet) for _ in range(24))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8791')
    ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--state-subdir', default='state', help='Fresh local state subdirectory under the isolated review directory')
    args = ap.parse_args()
    parsed = urllib.parse.urlsplit(args.base)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != 8791:
        raise SystemExit('This review is restricted to its isolated loopback server on port 8791.')
    review_dir = ROOT / '.wrangler/astra-runtime-a1636aa'
    config = review_dir / 'wrangler.jsonc'
    state = (review_dir / args.state_subdir).resolve()
    assert state.is_relative_to(review_dir.resolve()) and state != review_dir.resolve()
    cfg = json.loads(config.read_text(encoding='utf-8-sig'))
    assert cfg['name'] == 'openresearch-club-review-a1636aa' and not cfg['routes']
    run = secrets.token_hex(4)
    env = dict(os.environ, WRANGLER_LOG_PATH=str(review_dir / 'probe-tools.log'), WRANGLER_SEND_METRICS='false', XDG_CONFIG_HOME=str(review_dir / 'xdg'))

    def d1(sql):
        # Contains synthetic records and credential hashes only, never bearer secrets.
        path = review_dir / ('probe-' + secrets.token_hex(4) + '.sql')
        path.write_text(sql, encoding='utf-8')
        try:
            proc = subprocess.run(['node', str(ROOT / 'node_modules/wrangler/bin/wrangler.js'), 'd1', 'execute', 'openresearch-club', '--local', '--config', str(config), '--persist-to', str(state), '--file', str(path)], cwd=ROOT, env=env, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=90, creationflags=0x08000000 if os.name == 'nt' else 0)
            if proc.returncode:
                raise RuntimeError('Local D1 fixture command failed: ' + proc.stderr[-2000:])
        finally:
            path.unlink(missing_ok=True)

    def call(method, path, body=None, token=None, raw=None, headers=None, idem=None):
        h = {'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        if raw is not None:
            data = raw
            h['Content-Type'] = 'application/octet-stream'
        if token:
            h['Authorization'] = 'Bearer ' + token
        if method in {'POST', 'PUT', 'PATCH'}:
            h['Idempotency-Key'] = idem or 'review-' + secrets.token_hex(12)
        h.update(headers or {})
        req = urllib.request.Request(args.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                status, data = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, data = exc.code, exc.read()
        try:
            value = json.loads(data) if data else None
        except json.JSONDecodeError:
            value = data.decode(errors='replace')
        return status, value

    def ok(method, path, body=None, token=None, expected=201, **kwargs):
        status, value = call(method, path, body, token, **kwargs)
        if status != expected:
            raise RuntimeError(f'Fixture setup failed: {method} {path}: {status}, {str(value)[:300]}')
        return value

    def record(name, expected, actual, detail=None):
        CHECKS.append(dict(name=name, expected=expected, actual=actual, passed=expected == actual, detail=detail))
        print(('PASS ' if expected == actual else 'FAIL ') + name, flush=True)

    maint_token = secrets.token_hex(32)
    maint_id, cred_id = uid(), uid()
    d1(f"INSERT INTO contributors(id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES('{maint_id}','review-maint-{run}','Review maintainer','human','maintainer','active','1.1.1','{NOW}');\nINSERT INTO credentials(id,contributor_id,token_hash,label,scopes,created_at) VALUES('{cred_id}','{maint_id}','{hashlib.sha256(maint_token.encode()).hexdigest()}','review','[\"read\",\"write\"]','{NOW}');")
    acceptance_env = dict(env, ORC_BASE=args.base, ORC_MAINTAINER_TOKEN=maint_token)
    acceptance = subprocess.run([sys.executable, str(ROOT / 'scripts/acceptance.py')], cwd=ROOT, env=acceptance_env, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=180)
    SAMPLES['acceptance'] = dict(exit_code=acceptance.returncode, passed=len(re.findall(r'^PASS', acceptance.stdout, re.M)), failed=len(re.findall(r'^FAIL', acceptance.stdout, re.M)), stdout=acceptance.stdout, stderr=acceptance.stderr)
    record('original_acceptance_gate', 0, acceptance.returncode, {'passed': SAMPLES['acceptance']['passed'], 'failed': SAMPLES['acceptance']['failed']})
    if acceptance.returncode:
        raise RuntimeError('Original acceptance failed; inspect captured output before running more probes.')

    def agent(label):
        token = secrets.token_hex(32)
        obj = ok('POST', '/v1/contributors', dict(handle=f'review-{label}-{run}', display_name=label, kind='agent', agreed_skill_version='1.1.1', credential=dict(token_hash=hashlib.sha256(token.encode()).hexdigest())))
        run_obj = ok('POST', '/v1/me/runs', dict(model='synthetic-review', harness='review_runtime_a1636aa.py'), token)
        return dict(id=obj['contributor']['id'], token=token, run=run_obj['id'])

    reviewer, quota_actor = agent('reader'), agent('quota')
    maint_run = ok('POST', '/v1/me/runs', dict(model='synthetic-review', harness='review_runtime_a1636aa.py'), maint_token)['id']
    project = ok('POST', '/v1/projects', dict(slug='review-' + run, title='Runtime review', kind='project', status='active', brief_md='Synthetic fixtures only'), maint_token)
    pid = project['id']
    note = dict(tried='Synthetic probe', happened='Fixture only', limitations='Local review', next_step='Inspect')

    def contribution(marker):
        return ok('POST', '/v1/contributions', dict(project_id=pid, kind='result', title=marker, claim=marker, note=note, fields=dict(how_to_check='Inspect fixture', would_refute='Counterexample'), run_id=maint_run), maint_token)

    def receipt_body(marker, **changes):
        data = dict(kind='review', outcome='concerns', run_id=reviewer['run'], checked_md=marker, not_checked_md='No research executed', method_md='Synthetic', observations_md=marker, independence=dict.fromkeys(['execution', 'implementation', 'data', 'design'], 'unknown'), relationships_md='Same operator')
        data.update(changes)
        return data

    def moderate(action, target_type, target_id, **extra):
        return call('POST', '/v1/moderation/actions', dict(action=action, target_type=target_type, target_id=target_id, public_reason='Synthetic runtime review', **extra), maint_token)

    work = contribution('RUNTIME_VISIBLE_WORK_' + run)
    rid_path = f"/v1/contributions/{work['id']}/revisions/1/receipts"
    hidden_marker = 'RUNTIME_HIDDEN_RECEIPT_' + run
    receipt = ok('POST', rid_path, receipt_body(hidden_marker), reviewer['token'])
    assert moderate('hide', 'receipt', receipt['id'])[0] == 201
    direct_status, _ = call('GET', '/v1/receipts/' + receipt['id'])
    record('hidden_receipt_direct_access_blocked', 410, direct_status)
    status, value = call('GET', f"/v1/contributions/{work['id']}/receipts?status=hidden")
    record('hidden_receipt_not_exposed_by_status_filter', False, hidden_marker in json.dumps(value), {'http_status': status, 'receipt_id': receipt['id']})

    marker = 'RUNTIME_REDACTED_CLAIM_' + run
    redacted = contribution(marker)
    assert moderate('redact', 'contribution', redacted['id'])[0] == 201
    status, events = call('GET', f'/v1/events?project={pid}&limit=200')
    record('redacted_claim_absent_from_public_events', False, marker in json.dumps(events), {'http_status': status})
    status, exported = call('GET', f'/v1/projects/{pid}/export')
    record('redacted_claim_absent_from_export', False, marker in json.dumps(exported), {'http_status': status})

    external = ok('POST', rid_path, receipt_body('RUNTIME_EXTERNAL_EVALUATION_' + run, kind='external_evaluation', outcome='scored', evaluation=dict(evaluator='fixture', evaluator_version='1', submission_sha256='a' * 64, score=1)), reviewer['token'])
    status, value = moderate('redact', 'receipt', external['id'])
    record('external_evaluation_redaction_succeeds', 201, status, value)
    record('external_evaluation_no_longer_public_after_redaction', 410, call('GET', '/v1/receipts/' + external['id'])[0])

    parent = ok('POST', '/v1/posts', dict(project_id=pid, title='Parent', body_md='Fixture'), maint_token)
    task = ok('POST', f'/v1/projects/{pid}/tasks', dict(title='Task', body_md='Fixture', kind='review'), maint_token)
    assert moderate('lock', 'project', pid)[0] == 201
    direct_status, _ = call('POST', '/v1/posts', dict(project_id=pid, title='Blocked', body_md='Fixture'), reviewer['token'])
    record('locked_project_direct_post_blocked', 403, direct_status)
    status, _ = call('POST', '/v1/posts', dict(parent_post_id=parent['id'], body_md='Reply via inferred project'), reviewer['token'])
    record('locked_project_reply_blocked', 403, status)
    status, _ = call('POST', rid_path, receipt_body('Check during lock'), reviewer['token'])
    record('locked_project_receipt_blocked', 403, status)
    status, _ = call('POST', f"/v1/tasks/{task['id']}/leases", {}, reviewer['token'])
    record('locked_project_lease_blocked', 403, status)
    assert moderate('unlock', 'project', pid)[0] == 201

    tasks = [ok('POST', f'/v1/projects/{pid}/tasks', dict(title=f'Parallel task {i}', body_md='Fixture', kind='review'), maint_token) for i in range(8)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda t: call('POST', f"/v1/tasks/{t['id']}/leases", {}, quota_actor['token']), tasks))
    me = ok('GET', '/v1/me', token=quota_actor['token'], expected=200)
    record('parallel_leases_respect_limit', True, me['usage_today']['active_leases'] <= me['quota']['active_leases'], {'statuses': [s for s, _ in results], 'active': me['usage_today']['active_leases'], 'limit': me['quota']['active_leases']})

    # A tiny fixture cap reproduces total-upload reservation behavior without
    # allocating large payloads. Established policy has not been loaded yet.
    d1("UPDATE quota_policies SET upload_bytes_total=8,upload_bytes_per_day=100 WHERE tier='established';")
    published_policy = ok('GET', '/v1/meta', expected=200)['quotas']['established']
    if published_policy['upload_bytes_total'] != 8:
        raise RuntimeError('Tiny quota fixture was not installed; do not draw a quota conclusion.')
    assert moderate('set_tier', 'contributor', quota_actor['id'], tier='established')[0] == 201
    raw = b'1234'
    artifacts = [ok('POST', '/v1/artifacts', dict(kind='log', name=f'four-bytes-{i}', storage='r2', license='CC-BY-4.0', byte_size=4, claimed_sha256=hashlib.sha256(raw).hexdigest()), quota_actor['token'])['artifact'] for i in range(3)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        uploads = list(pool.map(lambda a: call('PUT', f"/v1/artifacts/{a['id']}/content", token=quota_actor['token'], raw=raw), artifacts))
    me = ok('GET', '/v1/me', token=quota_actor['token'], expected=200)
    if me['quota']['upload_bytes_total'] != 8:
        raise RuntimeError('Tiny quota fixture was not observed by the actor; quota probe is inconclusive.')
    record('parallel_uploads_respect_total_quota', True, me['usage_today']['upload_bytes_total'] <= me['quota']['upload_bytes_total'], {'statuses': [s for s, _ in uploads], 'bytes': me['usage_today']['upload_bytes_total'], 'limit': me['quota']['upload_bytes_total'], 'fixture_daily_limit':100})

    # Build a small, separate project to exercise project-export query scaling.
    large = ok('POST', '/v1/projects', dict(slug='review-scale-' + run, title='Export scale fixture', kind='project', status='active', brief_md='Synthetic'), maint_token)
    statements=[]
    for _ in range(60):
        cid=uid()
        statements.append(f"INSERT INTO contributions(id,project_id,kind,author_id,created_at) VALUES('{cid}','{large['id']}','other','{maint_id}','{NOW}');")
        statements.append(f"INSERT INTO contribution_revisions(contribution_id,revision,title,claim,note_json,fields_json,author_id,run_id,created_at) VALUES('{cid}',1,'Fixture','Fixture','{json.dumps(note)}','{{}}','{maint_id}','{maint_run}','{NOW}');")
    d1('\n'.join(statements))
    status, value = call('GET', f"/v1/projects/{large['id']}/export")
    record('export_with_sixty_contributions', 200, status, {'response_detail': value if status != 200 else {'contributions': len(value['contributions'])}})

    # Last, because this intentionally tests lockout of this disposable fixture.
    status, value = moderate('set_tier', 'contributor', maint_id, tier='new')
    record('last_global_maintainer_cannot_demote_self', 409, status, {'http_status':status})
    me_status, me = call('GET', '/v1/me', token=maint_token)
    SAMPLES['maintainer_after_demotion_attempt'] = {'http_status':me_status, 'tier':me.get('contributor',{}).get('tier') if isinstance(me,dict) else None}

    report = dict(reviewed_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), source_tree=subprocess.check_output(['git','rev-parse','HEAD:src'],cwd=ROOT,text=True).strip(), base=args.base,
                  scope='Isolated local Wrangler/Miniflare Worker with local D1, Durable Objects, and R2. Synthetic fixtures only; no deployment or production credentials.', state_subdir=args.state_subdir,
                  checks=CHECKS, passed=sum(c['passed'] for c in CHECKS), failed=sum(not c['passed'] for c in CHECKS), samples=SAMPLES)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['reviewed_commit','passed','failed']},indent=2))
    return int(bool(report['failed']))


if __name__=='__main__':
    raise SystemExit(main())
