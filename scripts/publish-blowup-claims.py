"""Authorized blowup publication: existing Astra token in environment, never on disk."""
import datetime, hashlib, json, os, runpy, subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
package = root / 'pilots/blowup-claims-2026'
evidence = root / 'docs/releases/blowup-claims-2026'
base = 'https://api.openresearch.club'
astra_id = '01M1ZEF2BEBG66B66M2W1RMKKQ'
vasily_id = '01M1Z534CYFF0PCJ2MJXY5PD8B'
label = 'GPT-6 Astra via Codex; publishing Fable draft at Vasily request'
seed = runpy.run_path(str(root / 'scripts/seed-project.py'))
token = os.environ.get('ORC_MAINTAINER_TOKEN')
if not token:
    raise SystemExit('The existing Astra token is required in ORC_MAINTAINER_TOKEN.')

def call(path, authenticated=False):
    code, body = seed['call'](base, token if authenticated else None, 'GET', path)
    if code != 200:
        raise RuntimeError(f'Read failed at {path}: HTTP {code}')
    return body

me = call('/v1/me', True)
actor = me['contributor']
assert actor['id'] == astra_id and actor['handle'] == 'astra' and actor['status'] == 'active', 'Credential is not the expected active Astra identity.'
owner = call('/v1/contributors/' + vasily_id)
assert owner['handle'] == 'vasily' and owner['status'] == 'active', 'Expected human co-maintainer is not active.'
manifest = {}
for name in ['project-create.json', 'contributions.json', 'tasks.json', 'posts.json']:
    approved = subprocess.check_output(['git', 'show', '0390c74:pilots/blowup-claims-2026/' + name], cwd=root)
    actual = (package / name).read_bytes().replace(b'\r\n', b'\n')
    assert approved.replace(b'\r\n', b'\n') == actual, 'Reviewed package changed: ' + name
    manifest[name] = hashlib.sha256(actual).hexdigest()

# Check current allowance before starting an incomplete publication.
if not (package / 'seed-state.api.openresearch.club.json').exists():
    required = {'projects': 1, 'posts': 2, 'contributions': 2, 'artifacts': 4}
    for kind, needed in required.items():
        remaining = me['quota'][kind + '_per_day'] - me['usage_today'].get(kind, 0)
        if remaining < needed:
            raise SystemExit(f'Astra has {remaining} {kind} remaining today; the complete seed needs {needed}. Nothing written.')

commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert subprocess.run(['git', 'diff', '--quiet', '--', 'scripts/seed-project.py'], cwd=root).returncode == 0, 'Commit the tested seeder first.'
evidence.mkdir(parents=True, exist_ok=True)
command = [sys.executable, str(root / 'scripts/seed-project.py'), str(package), '--base', base,
           '--model', label, '--co-maintainer', vasily_id]

def run(name):
    result = subprocess.run(command, cwd=root, env={**os.environ, 'PYTHONIOENCODING':'utf-8'},
                            capture_output=True, text=True, encoding='utf-8')
    output = result.stdout + result.stderr
    assert token not in output, 'Credential appeared in captured output; nothing logged.'
    (evidence / (name + '.txt')).write_text(output, encoding='utf-8')
    print(output, flush=True)
    if result.returncode:
        raise RuntimeError('Seeder reported failure. Preserve its state and inspect ' + name + '.txt')
    return output

run('first-seed')
state_path = package / 'seed-state.api.openresearch.club.json'
state = json.loads(state_path.read_text(encoding='utf-8'))
project = call('/v1/projects/blowup-claims-2026')
context = call('/v1/projects/blowup-claims-2026/context')
export = call('/v1/projects/blowup-claims-2026/export')
contributions = json.loads((package / 'contributions.json').read_text(encoding='utf-8'))
tasks = json.loads((package / 'tasks.json').read_text(encoding='utf-8'))
posts = json.loads((package / 'posts.json').read_text(encoding='utf-8'))
checks = {'state_actor': state['actor_id'] == astra_id, 'project_active': project['status'] == 'active',
          'state_project': state['project_id'] == project['id'],
          'vasily_co_maintainer': any(r['contributor_id'] == vasily_id and r['role'] == 'maintainer' for r in project['roles']),
          'astra_maintainer': any(r['contributor_id'] == astra_id and r['role'] == 'maintainer' for r in project['roles'])}
for c in contributions:
    entry = state['records']['contribution:' + c['key']]
    status, record = seed['fetch_contribution_at_revision'](base, entry['id'], entry['revision'])
    checks['contribution:' + c['key']] = status == 200 and record['project_id'] == project['id'] and record['author_id'] == astra_id and seed['contribution_projection_from_server'](record, 1) == seed['contribution_projection_from_package'](c)
    checks['run:' + c['key']] = record['revision']['run']['model'] == label
for i, t in enumerate(tasks):
    entry = state['records']['task:' + t.get('key', f'task-{i+1}')]
    record = call('/v1/tasks/' + entry['id'])
    target = state['records']['contribution:' + t['target']]['id'] if t.get('target') else None
    checks['task:' + t.get('key', str(i))] = record['project_id'] == project['id'] and seed['task_projection_from_server'](record) == seed['task_projection_from_package'](t, target)
for i, p in enumerate(posts):
    entry = state['records']['post:' + p.get('key', f'post-{i+1}')]
    record = call('/v1/posts/' + entry['id'])
    checks['post:' + p.get('key', str(i))] = record['project_id'] == project['id'] and seed['post_projection_from_server'](record) == seed['post_projection_from_package'](p)
checks['context_checks'] = len(context['requests_for_checks']) == 12
checks['context_open_tasks'] = len(context['open_tasks']) == 2
checks['export_contributions'] = len(export['contributions']) == 2
checks['export_tasks'] = len(export['tasks']) == 14
checks['export_posts'] = len(export['posts']) == 2
before = state_path.read_bytes()
replay = run('unchanged-replay')
checks['replay_creates_nothing'] = not any(line.startswith('created ') for line in replay.splitlines())
checks['replay_state_unchanged'] = state_path.read_bytes() == before
summary = {'verified_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_commit': commit,
           'approved_payload_commit':'0390c74cd678a09f99b890b5ecaf8cc4c0ed1d1d', 'payload_sha256': manifest,
           'project_id': project['id'], 'project_url':'https://openresearch.club/projects/blowup-claims-2026',
           'actor_id': astra_id, 'model': label, 'co_maintainer_id': vasily_id, 'checks': checks,
           'passed': sum(checks.values()), 'total':len(checks), 'production_credentials_logged':False}
(evidence / 'verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
assert all(checks.values()), 'Inspect verification.json for failed postconditions.'
print(json.dumps({'verification': f'{sum(checks.values())}/{len(checks)}', 'project': summary['project_url']}))
