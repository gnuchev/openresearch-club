"""Replay receipt 0009 fixes at 0390c74 using an isolated local Worker.

Start that commit's Worker on 127.0.0.1:8787 with its DEFAULT local D1 directory.
Use an isolated checkout: Fable's unchanged suite invokes Wrangler against that
directory. This driver creates local fixture credentials in memory, runs the
26 original assertions, then checks independent boundary and revision cases.
No production credential or request is used.
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
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    checkout, out = args.checkout.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scratch = out / 'scratch'
    scratch.mkdir(exist_ok=True)
    expected = subprocess.check_output(['git', 'rev-parse', '0390c74'], cwd=ROOT, text=True).strip()
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
    results = {'reviewed_commit': expected, 'base': BASE, 'cases': []}

    def sql(body, name):
        path = out / (name + '.sql')
        path.write_text(body, encoding='utf-8')  # Fixture metadata and hashes only.
        command_env = {k: v for k, v in env.items() if k not in {'ORC_MAINTAINER_TOKEN', 'ORC_TOKEN'}}
        p = subprocess.run(['node', str(ROOT / 'node_modules/wrangler/bin/wrangler.js'), 'd1', 'execute',
                            'openresearch-club', '--local', '--file', str(path), '--json'],
                           cwd=checkout, env=command_env, capture_output=True, text=True, encoding='utf-8')
        assert p.returncode == 0, 'Local fixture SQL failed: ' + p.stderr[:300]

    def request(method, path, body=None):
        return mod['call'](BASE, token, method, path, body,
                           'narrow-' + secrets.token_hex(12) if body is not None else None)

    def call(method, path, body=None):
        status, result = request(method, path, body)
        assert status in (200, 201), (method, path, status, result)
        return result

    def counts():
        for path in (checkout / '.wrangler/state/v3/d1').rglob('*.sqlite'):
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='contributors'").fetchone():
                    return {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
                            for t in ['projects', 'contributions', 'artifacts', 'tasks', 'posts', 'runs', 'events']}
        raise RuntimeError('The isolated database was not found.')

    def seed(name, package, state_file, extra=()):
        p = subprocess.run([sys.executable, str(checkout / 'scripts/seed-project.py'), str(package),
                            '--base', BASE, '--state', str(state_file), '--page-size', '2',
                            '--model', 'review-fixture', *extra], cwd=checkout, env=env,
                           capture_output=True, text=True, encoding='utf-8')
        output = p.stdout + p.stderr
        assert token not in output, 'A local credential appeared in output.'
        (out / (name + '.txt')).write_text(output, encoding='utf-8')
        return p.returncode, output

    def check(name, passed, **evidence):
        results['cases'].append({'name': name, 'pass': bool(passed), **evidence})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))

    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    package = checkout / 'pilots/blowup-claims-2026'
    project = read(package / 'project-create.json')
    claims = read(package / 'contributions.json')

    def copy_package(name, slug):
        dest = out / name
        shutil.copytree(package, dest, ignore=shutil.ignore_patterns('seed-state.*'))
        pj = {**project, 'slug': slug}
        write(dest / 'project-create.json', pj)
        return dest, pj

    sql(f"INSERT INTO contributors (id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES ('{actor}','narrow-operator','Narrow replay fixture','human','maintainer','active','1.2.2','{now}');\n"
        f"INSERT INTO credentials (id,contributor_id,token_hash,label,scopes,created_at) VALUES ('{credential}','{actor}','{hashlib.sha256(token.encode()).hexdigest()}','local only','[\"read\",\"write\"]','{now}');", 'bootstrap-hash-only')
    p = subprocess.run([sys.executable, 'scripts/seed-project-probes.py'], cwd=checkout, env=env,
                       capture_output=True, text=True, encoding='utf-8')
    output = p.stdout + p.stderr
    assert token not in output
    (out / 'fable-probes.txt').write_text(output, encoding='utf-8')
    results.update(fable_exit=p.returncode, fable_summary=[s for s in output.splitlines() if 'probes passed' in s])
    print('Fable replay:', results['fable_summary'], flush=True)
    assert p.returncode == 0, 'Read fable-probes.txt before continuing.'
    states = list(scratch.glob('seed-probes-*/state1.json'))
    assert len(states) == 1
    original = read(states[0])

    # Original C1, replayed in a separate project with the actual first package claim.
    c1_pkg, c1_pj = copy_package('wrong-evidence', 'narrow-wrong-evidence')
    call('POST', '/v1/projects', c1_pj)
    run = call('POST', '/v1/me/runs', {'model': 'fixture', 'harness': 'recheck_seed_0390c74.py'})
    wrong = call('POST', '/v1/contributions', {
        'project_id': c1_pj['slug'], 'kind': claims[0]['kind'], 'title': claims[0]['title'], 'claim': claims[0]['claim'],
        'note': dict.fromkeys(['tried', 'happened', 'limitations', 'next_step'], 'Different fixture evidence'),
        'fields': {'how_to_check': 'Unrelated fixture'}, 'run_id': run['id'],
    })
    c1_state = out / 'c1-state.json'
    rc, output = seed('c1-evidence', c1_pkg, c1_state)
    recorded = read(c1_state)
    ok, tasks = mod['list_all'](BASE, '/v1/tasks?project=' + c1_pj['slug'], 2)
    adopted = any(v['id'] == wrong['id'] for k, v in recorded['records'].items() if k.startswith('contribution:'))
    targeted = any(t.get('target', {}).get('contribution_id') == wrong['id'] for t in tasks if t.get('target'))
    check('C1 independent: wrong evidence neither adopted nor targeted', rc == 1 and ok and not adopted and not targeted,
          exit_code=rc, adopted=adopted, targeted=targeted)

    c2_pkg, c2_pj = copy_package('other-slug', 'narrow-other-slug')
    c2_state = out / 'c2-slug-state.json'
    write(c2_state, original)
    before, state_before = counts(), c2_state.read_bytes()
    rc, _ = seed('c2-slug', c2_pkg, c2_state)
    absent = request('GET', '/v1/projects/' + c2_pj['slug'])[0]
    check('C2 slug binding: no writes and no state rewrite', rc == 3 and absent == 404 and before == counts() and state_before == c2_state.read_bytes(),
          exit_code=rc, project_get=absent, counts_before=before, counts_after=counts())

    for field, value in [('base', 'https://different.invalid'), ('project_id', boot['ulid']())]:
        state_file = out / ('c2-' + field + '-state.json')
        write(state_file, {**original, field: value})
        before, state_before = counts(), state_file.read_bytes()
        rc, _ = seed('c2-' + field, package, state_file)
        check('C2 ' + field + ' binding: no writes and no state rewrite',
              rc == 3 and before == counts() and state_before == state_file.read_bytes(), exit_code=rc)

    c2b_pkg, c2b_pj = copy_package('wrong-project-title', 'narrow-wrong-title')
    call('POST', '/v1/projects', {**c2b_pj, 'title': 'A different research purpose'})
    before = counts()
    rc, _ = seed('c2-title', c2b_pkg, out / 'c2-title-state.json')
    check('C2 project identity conflict: no child, run or event writes', rc == 3 and before == counts(),
          exit_code=rc, counts_before=before, counts_after=counts())

    # Even a state entry with a matching-looking fingerprint must name this project's child.
    foreign_state = copy.deepcopy(original)
    foreign_state['records']['contribution:' + claims[0]['key']]['id'] = wrong['id']
    foreign_path = out / 'c2-child-state.json'
    write(foreign_path, foreign_state)
    before = counts()
    rc, output = seed('c2-child', package, foreign_path)
    check('C2 child ownership: foreign-project contribution refused',
          rc == 1 and 'not to the bound project' in output and before == counts(), exit_code=rc)

    # Original C3 with a separate identity, including recovery after removal of the in-flight row.
    co_id = boot['ulid']()
    body = {'contributor_id': co_id, 'role': 'maintainer'}
    key = mod['idem_key'](project['slug'], 'role', co_id, {'cid': co_id})
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
    sql(f"INSERT INTO contributors (id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES ('{co_id}','narrow-co','Co fixture','human','new','active','1.2.2','{now}');\n"
        f"INSERT INTO idempotency_keys (scope,key,method,target,body_sha256,state,created_at,expires_at) VALUES ('{actor}','{key}','POST','/v1/projects/{project['slug']}/roles','{mod['digest'](body)}','in_flight','{now}','{expires}');", 'role-in-flight')
    role_path = out / 'c3-state.json'
    write(role_path, original)

    def role_held():
        return any(r['contributor_id'] == co_id and r['role'] == 'maintainer'
                   for r in call('GET', '/v1/projects/' + project['slug'])['roles'])

    rc, output = seed('c3-in-flight', package, role_path, ['--co-maintainer', co_id])
    check('C3 in-flight 409: failure without false role state',
          rc == 1 and 'grant returned 409' in output and not role_held() and 'role:' + co_id not in read(role_path)['records'], exit_code=rc)
    sql(f"DELETE FROM idempotency_keys WHERE scope='{actor}' AND key='{key}';", 'role-clear')
    rc, _ = seed('c3-recovery', package, role_path, ['--co-maintainer', co_id])
    check('C3 retry: actual role and recorded role agree',
          rc == 0 and role_held() and 'role:' + co_id in read(role_path)['records'], exit_code=rc)

    # The response promises unchanged bound revision 1 can coexist with legitimate later revisions.
    cid = original['records']['contribution:' + claims[0]['key']]['id']
    exact_before = call('GET', f'/v1/contributions/{cid}/revisions/1')
    latest_before = call('GET', '/v1/contributions/' + cid)
    revision = latest_before['revision']
    revised = {k: revision[k] for k in ['title', 'claim', 'note', 'fields']}
    revised.update(change_summary='Independent replay fixture: publish revision 2.', run_id=original['run_id'])
    revised['note'] = {**revised['note'], 'next_step': 'A legitimate later-revision fixture.'}
    call('POST', f'/v1/contributions/{cid}/revisions', revised)
    exact_after = call('GET', f'/v1/contributions/{cid}/revisions/1')
    revision_path = out / 'd1-revision-state.json'
    write(revision_path, original)
    before = counts()
    rc, output = seed('d1-later-revision', package, revision_path)
    unchanged = exact_before == exact_after
    check('D1 later revision: unchanged original revision remains reusable', rc == 0 and unchanged and before == counts(),
          exit_code=rc, original_revision_unchanged=unchanged, current_revision=call('GET', '/v1/contributions/' + cid)['current_revision'],
          refusal_lines=[line for line in output.splitlines() if 'no longer shows revision' in line], no_new_records=before == counts())

    results['passed'] = sum(c['pass'] for c in results['cases'])
    results['total'] = len(results['cases'])
    results['local_token_in_captured_output'] = False
    write(out / 'results.json', results)
    print(f"Independent cases: {results['passed']}/{results['total']}", flush=True)
    return 0 if results['passed'] == results['total'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
