"""Recheck 8f6b737: unchanged Fable probes plus independent state-integrity cases.

Requires that commit's Worker on 127.0.0.1:8787, with an isolated --persist-to
directory. Uses local test credentials generated in memory; never a production
token. The original probe source and seed package are not edited.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import secrets
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8787'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--checkout', type=Path, required=True)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    checkout, state, out = args.checkout.resolve(), args.state.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scratch = out / 'scratch'
    scratch.mkdir(exist_ok=True)
    expected = subprocess.check_output(['git', 'rev-parse', '8f6b737'], cwd=ROOT, text=True).strip()
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() == expected
    mod = runpy.run_path(str(checkout / 'scripts/seed-project.py'))
    boot = runpy.run_path(str(checkout / 'scripts/bootstrap-maintainer.py'))
    actor, credential = boot['ulid'](), boot['ulid']()
    token = secrets.token_hex(32)
    now = boot['now_iso']()
    env = os.environ.copy()
    env.update(ORC_MAINTAINER_TOKEN=token, PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
               TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch), NO_PROXY='127.0.0.1,localhost',
               WRANGLER_LOG_PATH=str(out / 'wrangler-fixtures.log'), WRANGLER_SEND_METRICS='false')
    observations = {'reviewed_commit': expected, 'base': BASE, 'independent_cases': {}}

    def sql(body, name):
        path = out / (name + '.sql')
        path.write_text(body, encoding='utf-8')
        # The SQL contains hashes and fixture metadata only; no raw credential.
        command_env = {k: v for k, v in env.items() if k not in {'ORC_MAINTAINER_TOKEN', 'ORC_TOKEN'}}
        p = subprocess.run(['node', str(ROOT / 'node_modules/wrangler/bin/wrangler.js'), 'd1', 'execute',
                            'openresearch-club', '--local', '--persist-to', str(state), '--config', str(checkout / 'wrangler.jsonc'),
                            '--file', str(path), '--json'], cwd=checkout, env=command_env,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert p.returncode == 0, 'Local fixture SQL failed: ' + p.stderr[:300]

    def call(method, path, body=None):
        status, result = mod['call'](BASE, token, method, path, body, 'recheck-' + secrets.token_hex(12) if body is not None else None)
        assert status in (200, 201), (method, path, status, result)
        return result

    def counts():
        for p in (state / 'v3/d1').rglob('*.sqlite'):
            with sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='contributors'").fetchone():
                    return {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
                            for t in ['projects', 'contributions', 'artifacts', 'tasks', 'posts', 'runs']}
        raise RuntimeError('The isolated database was not found.')

    def seed(name, package, state_file, extra=()):
        p = subprocess.run([sys.executable, str(checkout / 'scripts/seed-project.py'), str(package),
                            '--base', BASE, '--state', str(state_file), '--page-size', '2', '--model', 'probe-model', *extra],
                           cwd=checkout, env=env, capture_output=True, text=True, encoding='utf-8')
        text = p.stdout + p.stderr
        assert token not in text, 'A local credential appeared in the output.'
        (out / (name + '.txt')).write_text(text, encoding='utf-8')
        return p.returncode

    package = checkout / 'pilots/blowup-claims-2026'
    project = json.loads((package / 'project-create.json').read_text(encoding='utf-8'))
    claims = json.loads((package / 'contributions.json').read_text(encoding='utf-8'))

    def copy_package(name, slug):
        dest = out / name
        shutil.copytree(package, dest, ignore=shutil.ignore_patterns('seed-state.*'))
        pj = {**project, 'slug': slug}
        (dest / 'project-create.json').write_text(json.dumps(pj, ensure_ascii=False), encoding='utf-8')
        return dest, pj

    sql(f"INSERT INTO contributors (id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES ('{actor}','recheck-operator','Recheck fixture','human','maintainer','active','1.2.1','{now}');\n"
        f"INSERT INTO credentials (id,contributor_id,token_hash,label,scopes,created_at) VALUES ('{credential}','{actor}','{hashlib.sha256(token.encode()).hexdigest()}','local only','[\"read\",\"write\"]','{now}');", 'bootstrap-hash-only')

    p = subprocess.run([sys.executable, 'scripts/seed-project-probes.py'], cwd=checkout, env=env,
                       capture_output=True, text=True, encoding='utf-8')
    text = p.stdout + p.stderr
    assert token not in text
    (out / 'fable-probes.txt').write_text(text, encoding='utf-8')
    observations['fable_probe_exit'] = p.returncode
    observations['fable_probe_summary'] = [line for line in text.splitlines() if 'probes passed' in line]
    print('Fable probe replay:', observations['fable_probe_summary'], flush=True)
    assert p.returncode == 0, 'Read fable-probes.txt before continuing.'
    states = list(scratch.glob('seed-probes-*/state1.json'))
    assert len(states) == 1
    original_state = json.loads(states[0].read_text(encoding='utf-8'))

    # C1: same actor + title + claim, but materially different evidence and no artifacts.
    c1_pkg, c1_project = copy_package('same-author-different-evidence', 'recheck-evidence-adoption')
    call('POST', '/v1/projects', c1_project)
    run = call('POST', '/v1/me/runs', {'model': 'fixture', 'harness': 'recheck_blowup_seed.py'})
    current = call('POST', '/v1/contributions', {
        'project_id': c1_project['slug'], 'kind': 'other', 'title': claims[0]['title'], 'claim': claims[0]['claim'],
        'note': {'tried': 'Different evidence fixture', 'happened': 'No linked manuscripts', 'limitations': 'Fixture only', 'next_step': 'Check adoption'},
        'fields': {'how_to_check': 'Unrelated checker fixture', 'would_refute': 'Fixture mismatch'}, 'run_id': run['id'],
    })
    c1_state = out / 'c1-state.json'
    rc = seed('c1-adoption', c1_pkg, c1_state)
    recorded = json.loads(c1_state.read_text(encoding='utf-8'))
    live = call('GET', '/v1/contributions/' + current['id'])
    expected_content = {k: claims[0][k] for k in ['kind', 'title', 'claim', 'note', 'fields', 'artifacts']}
    observations['independent_cases']['C1'] = {
        'expectation': 'Reject adopting materially different evidence, despite the matching title and claim.',
        'exit_code': rc, 'adopted_fixture_id': recorded['records'].get('contribution:ns-theorem-1-1', {}).get('id') == current['id'],
        'live_artifact_count': len(live['revision']['artifacts']), 'expected_artifact_count': len(claims[0]['artifacts']),
        'state_hash_matches_requested_not_live_content': recorded['records'].get('contribution:ns-theorem-1-1', {}).get('content_sha256') == mod['digest'](expected_content),
        'pass': rc != 0,
    }

    # C2: a state file for project A must not be rebound to a new project B.
    c2_pkg, c2_project = copy_package('different-project', 'recheck-cross-project-state')
    c2_state = out / 'c2-state.json'
    c2_state.write_text(json.dumps(original_state), encoding='utf-8')
    rc = seed('c2-project-binding', c2_pkg, c2_state)
    packet = call('GET', '/v1/projects/' + c2_project['slug'] + '/context')
    rebound = json.loads(c2_state.read_text(encoding='utf-8'))
    observations['independent_cases']['C2'] = {
        'expectation': 'Refuse state from another project before creating/rebinding anything.', 'exit_code': rc,
        'project_id_changed_in_state': rebound['project_id'] != original_state['project_id'],
        'old_contribution_id_retained': rebound['records']['contribution:ns-theorem-1-1']['id'] == original_state['records']['contribution:ns-theorem-1-1']['id'],
        'new_project_contributions': len(packet['recent_contributions']),
        'new_project_tasks': len(packet['open_tasks']) + len(packet['requests_for_checks']), 'pass': rc != 0,
    }

    # C3: HTTP 409 can mean in-flight, not that a requested role exists.
    co_id = boot['ulid']()
    body = {'contributor_id': co_id, 'role': 'maintainer'}
    key = mod['idem_key'](project['slug'], 'role', co_id, {'cid': co_id})
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
    sql(f"INSERT INTO contributors (id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES ('{co_id}','recheck-co','Co fixture','human','new','active','1.2.1','{now}');\n"
        f"INSERT INTO idempotency_keys (scope,key,method,target,body_sha256,state,created_at,expires_at) VALUES ('{actor}','{key}','POST','/v1/projects/{project['slug']}/roles','{mod['digest'](body)}','in_flight','{now}','{expires}');", 'role-in-flight')
    c3_state = out / 'c3-state.json'
    c3_state.write_text(json.dumps(original_state), encoding='utf-8')
    rc = seed('c3-role-conflict', package, c3_state, ('--co-maintainer', co_id))
    roles = call('GET', '/v1/projects/' + project['slug'])['roles']
    written = json.loads(c3_state.read_text(encoding='utf-8'))
    observations['independent_cases']['C3'] = {
        'expectation': 'Return failure or verify the actual role after a 409, never claim a missing grant.',
        'exit_code': rc, 'actual_role_exists': any(r['contributor_id'] == co_id and r['role'] == 'maintainer' for r in roles),
        'state_claims_role_exists': 'role:' + co_id in written['records'], 'pass': rc != 0,
    }

    # Related project identity case: known conflicting metadata must stop child writes.
    c4_pkg, c4_project = copy_package('different-project-title', 'recheck-conflicting-project')
    call('POST', '/v1/projects', {**c4_project, 'title': 'A different project purpose'})
    rc = seed('c4-project-title', c4_pkg, out / 'c4-state.json')
    packet = call('GET', '/v1/projects/' + c4_project['slug'] + '/context')
    observations['independent_cases']['C4'] = {
        'expectation': 'Stop before publishing child content into a project whose title conflicts.', 'exit_code': rc,
        'contributions_written_after_conflict': len(packet['recent_contributions']),
        'tasks_written_after_conflict': len(packet['open_tasks']) + len(packet['requests_for_checks']),
        'pass': not packet['recent_contributions'] and not packet['open_tasks'] and not packet['requests_for_checks'],
    }
    observations['final_counts'] = counts()
    observations['local_token_in_captured_output'] = False
    (out / 'results.json').write_text(json.dumps(observations, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(observations, indent=2), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
