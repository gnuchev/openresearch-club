"""Review seed-project.py against a separately started, isolated local D1 Worker.

This harness only sends requests to loopback. Start the reviewed checkout with
the same --persist-to directory first. It generates test credentials in memory,
stores only their hashes, and never prints or saves their raw values. It does not
execute any downloaded Lean code or touch the production API.
"""
import argparse
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
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--checkout', type=Path, required=True)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--port', type=int, default=8795)
    args = ap.parse_args()
    checkout, state, output = args.checkout.resolve(), args.state.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = f'http://127.0.0.1:{args.port}'
    package = checkout / 'pilots/blowup-claims-2026'
    script = checkout / 'scripts/seed-project.py'
    expected = subprocess.check_output(['git', 'rev-parse', '7def177'], cwd=ROOT, text=True).strip()
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
    assert actual == expected, 'Use the reviewed commit for the replay.'
    bootstrap = runpy.run_path(str(checkout / 'scripts/bootstrap-maintainer.py'))
    seeder, visitor, missing = (bootstrap['ulid']() for _ in range(3))
    fixture_suffix = secrets.token_hex(4)
    token, visitor_token = secrets.token_hex(32), secrets.token_hex(32)
    now = bootstrap['now_iso']()
    result = {'reviewed_commit': actual, 'base': base, 'checks': {}, 'runs': {}}

    def sql(text, name):
        path = output / (name + '.sql')
        path.write_text(text, encoding='utf-8')
        env = os.environ.copy()
        env['WRANGLER_LOG_PATH'] = str(output / 'wrangler-fixtures.log')
        env['WRANGLER_SEND_METRICS'] = 'false'
        p = subprocess.run(['node', str(ROOT / 'node_modules/wrangler/bin/wrangler.js'), 'd1', 'execute',
                            'openresearch-club', '--local', '--persist-to', str(state), '--config', str(checkout / 'wrangler.jsonc'),
                            '--file', str(path), '--json'], cwd=checkout, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if p.returncode:
            raise RuntimeError('Local fixture command failed: ' + p.stderr[:600])

    def call(method, path, body=None, who=token):
        headers = {'Accept': 'application/json'}
        if who: headers['Authorization'] = 'Bearer ' + who
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
            headers['Idempotency-Key'] = 'review-' + secrets.token_hex(16)
        request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response: return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def snapshot():
        dbs = []
        for candidate in (state / 'v3/d1').rglob('*.sqlite'):
            with sqlite3.connect(candidate.as_uri() + '?mode=ro', uri=True) as database:
                if database.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contributors'").fetchone():
                    dbs.append(candidate)
        assert len(dbs) == 1
        with sqlite3.connect(dbs[0].as_uri() + '?mode=ro', uri=True) as db:
            return {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                    for table in ['projects', 'contributions', 'contribution_revisions', 'artifacts', 'runs', 'tasks', 'posts', 'events']}

    def seed(name, pkg=package, extra=()):
        env = os.environ.copy()
        env['ORC_MAINTAINER_TOKEN'] = token
        p = subprocess.run([sys.executable, str(script), str(pkg), '--base', base, *extra],
                           cwd=checkout, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        combined = p.stdout + p.stderr
        assert token not in combined and visitor_token not in combined, 'A credential appeared in seed output.'
        (output / (name + '.txt')).write_text(combined, encoding='utf-8')
        result['runs'][name] = {'exit_code': p.returncode, 'counts': snapshot(), 'output_file': name + '.txt'}
        return p

    def fixture_package(name, slug):
        path = output / name
        shutil.copytree(package, path, dirs_exist_ok=False)
        project = json.loads((path / 'project-create.json').read_text(encoding='utf-8'))
        project['slug'] = slug
        (path / 'project-create.json').write_text(json.dumps(project), encoding='utf-8')
        return path, project

    sql('\n'.join(
        f"INSERT INTO contributors (id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES ('{cid}','{handle}','{handle}','agent','{tier}','active','1.2.0','{now}');\n"
        f"INSERT INTO credentials (id,contributor_id,token_hash,label,scopes,created_at) VALUES ('{bootstrap['ulid']()}','{cid}','{hashlib.sha256(secret.encode()).hexdigest()}','local review','[\"read\",\"write\"]','{now}');"
        for cid, handle, tier, secret in [(seeder, 'review-seeder-' + fixture_suffix, 'maintainer', token), (visitor, 'review-visitor-' + fixture_suffix, 'new', visitor_token)]
    ), 'bootstrap-hashes-only')

    before = snapshot()
    first = seed('first')
    assert first.returncode == 0
    second = seed('second')
    first_counts, second_counts = result['runs']['first']['counts'], result['runs']['second']['counts']
    result['checks']['unchanged_second_run_creates_nothing'] = first_counts == second_counts
    result['checks']['first_counts_expected'] = all(first_counts[k] - before[k] == v for k, v in
        {'projects': 1, 'contributions': 2, 'artifacts': 3, 'runs': 1, 'tasks': 12, 'posts': 2}.items())
    _, ctx = call('GET', '/v1/projects/blowup-claims-2026/context')
    result['checks']['context_shape'] = len(ctx['requests_for_checks']) == 10 and len(ctx['open_tasks']) == 2 and len(ctx['recent_contributions']) == 2
    result['seeded_project_id'] = ctx['project']['id']
    _, full = call('GET', '/v1/contributions/' + ctx['recent_contributions'][0]['id'])
    result['declared_run'] = full['revision']['run']

    invalid_role = seed('invalid-co-maintainer', extra=('--co-maintainer', missing))
    result['checks']['invalid_co_maintainer_returns_failure'] = invalid_role.returncode != 0

    drift_path, _ = fixture_package('edited-package', 'blowup-claims-2026')
    claims = json.loads((drift_path / 'contributions.json').read_text(encoding='utf-8'))
    edited_claim = 'Edited package claim: this marker must not be silently ignored.'
    claims[0]['claim'] = edited_claim
    (drift_path / 'contributions.json').write_text(json.dumps(claims), encoding='utf-8')
    drift = seed('same-title-edit', drift_path)
    _, existing = call('GET', '/v1/contributions?project=blowup-claims-2026')
    result['checks']['same_title_edit_is_applied_or_reported'] = drift.returncode != 0 or any(c['claim'] == edited_claim for c in existing['items'])

    collision_path, collision_project = fixture_package('collision-package', 'review-title-collision')
    status, _ = call('POST', '/v1/projects', collision_project)
    assert status == 201
    status, run = call('POST', '/v1/me/runs', {'model': 'local fixture', 'harness': 'review_blowup_seed.py'}, who=visitor_token)
    assert status == 201
    initial_claim = json.loads((package / 'contributions.json').read_text(encoding='utf-8'))[0]
    status, foreign = call('POST', '/v1/contributions', {
        'project_id': collision_project['slug'], 'kind': 'other', 'title': initial_claim['title'],
        'claim': 'A different participant owns this conflicting claim.',
        'note': {'tried': 'fixture', 'happened': 'fixture', 'limitations': 'fixture', 'next_step': 'fixture'},
        'fields': {}, 'run_id': run['id'],
    }, who=visitor_token)
    assert status == 201
    collision = seed('foreign-title-collision', collision_path)
    _, tasks = call('GET', '/v1/tasks?project=' + collision_project['slug'])
    misdirected = [t['id'] for t in tasks['items'] if t['target'] and t['target']['contribution_id'] == foreign['id']]
    result['checks']['foreign_title_is_not_adopted'] = not misdirected
    result['foreign_title_targeted_tasks'] = len(misdirected)

    # Simulate a later replay beyond the first listing page and the API's 24h
    # idempotency window. These synthetic posts are confined to local D1.
    filler = []
    for i in range(100):
        pid = '0' + f'{i + 1:025d}'
        filler.append(f"INSERT INTO posts (id,project_id,title,body_md,current_revision,author_id,status,created_at) VALUES ('{pid}','{result['seeded_project_id']}','Pagination fixture {i}','fixture',1,'{seeder}','visible','{now}');")
        filler.append(f"INSERT INTO post_revisions (post_id,revision,body_md,created_at) VALUES ('{pid}',1,'fixture','{now}');")
    filler.append(f"UPDATE idempotency_keys SET expires_at='2000-01-01T00:00:00Z' WHERE scope='{seeder}' AND target='/v1/posts';")
    sql('\n'.join(filler), 'pagination-and-expired-keys')
    before_late = snapshot()
    late = seed('after-pagination-and-key-expiry')
    after_late = snapshot()
    result['checks']['late_replay_creates_no_duplicate_posts'] = after_late['posts'] == before_late['posts']
    result['late_duplicate_posts'] = after_late['posts'] - before_late['posts']
    seed_module = runpy.run_path(str(script))
    wire_a = {'title': 'Local wire ordering probe', 'body_md': 'Fixture only.'}
    wire_b = {'body_md': 'Fixture only.', 'title': 'Local wire ordering probe'}
    wire_key = seed_module['idem_key']('review', 'post', 'wire-order', wire_a)
    assert wire_key == seed_module['idem_key']('review', 'post', 'wire-order', wire_b)
    wire_first, _ = seed_module['call'](base, visitor_token, 'POST', '/v1/posts', wire_a, wire_key)
    wire_second, _ = seed_module['call'](base, visitor_token, 'POST', '/v1/posts', wire_b, wire_key)
    result['checks']['semantic_key_hash_prevents_wire_order_422'] = wire_second != 422
    result['wire_order_probe'] = {'first_status': wire_first, 'second_status': wire_second,
                                  'same_key': True, 'same_json_value': True, 'same_wire_bytes': False}
    result['checks']['seed_output_contains_no_token'] = True
    (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
