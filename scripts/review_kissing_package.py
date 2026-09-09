"""Rehearse the kissing package at 9e9ba3b using local-only test identities.

Start that checkout's Worker on 127.0.0.1:8787 with its default local D1.
This creates ephemeral fixtures and local receipts, never production records.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8787'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checkout, out = args.checkout.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(['git','rev-parse','9e9ba3b'],cwd=ROOT,text=True).strip()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip() == commit
    seed = runpy.run_path(str(checkout/'scripts/seed-project.py'))
    boot = runpy.run_path(str(checkout/'scripts/bootstrap-maintainer.py'))
    tokens = [secrets.token_hex(32), secrets.token_hex(32)]
    actors = [boot['ulid'](), boot['ulid']()]
    now = boot['now_iso']()
    statements = []
    for i, handle in enumerate(['review-curator-fixture','review-checker-fixture']):
        tier = 'maintainer' if i == 0 else 'new'
        statements.append(f"INSERT INTO contributors (id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES ('{actors[i]}','{handle}','Local review fixture','agent','{tier}','active','1.2.3','{now}');")
        statements.append(f"INSERT INTO credentials (id,contributor_id,token_hash,label,scopes,created_at) VALUES ('{boot['ulid']()}','{actors[i]}','{hashlib.sha256(tokens[i].encode()).hexdigest()}','local fixture','[\"read\",\"write\"]','{now}');")
    fixture = out/'hash-only-fixtures.sql'
    fixture.write_text('\n'.join(statements),encoding='utf-8')
    env = {k:v for k,v in os.environ.items() if k not in {'ORC_TOKEN','ORC_MAINTAINER_TOKEN','ORC_ASTRA_TOKEN','ORC_FABLE_TOKEN'}}
    env.update(PYTHONIOENCODING='utf-8',PYTHONUTF8='1',WRANGLER_SEND_METRICS='false',WRANGLER_LOG_PATH=str(out/'wrangler.log'))
    process = subprocess.run(['node',str(ROOT/'node_modules/wrangler/bin/wrangler.js'),'d1','execute','openresearch-club','--local','--file',str(fixture),'--json'],cwd=checkout,env=env,capture_output=True,text=True,encoding='utf-8')
    assert process.returncode == 0, 'Local fixture creation failed.'
    package = checkout/'pilots/kissing-number-11'
    state_path = out/'state.json'
    results = {'reviewed_commit':commit,'base':BASE,'checks':{},'local_fixture_only':True}

    def check(name, value):
        results['checks'][name] = bool(value)
        print(('PASS ' if value else 'FAIL ')+name,flush=True)

    def request(method,path,body=None,index=None):
        return seed['call'](BASE,tokens[index] if index is not None else None,method,path,body,
                            'kissing-review-'+secrets.token_hex(12) if body is not None else None)

    def get(path):
        status, value = request('GET',path)
        assert status == 200, (path,status)
        return value

    def run(name,state):
        p = subprocess.run([sys.executable,'scripts/seed-project.py',str(package),'--base',BASE,
                            '--state',str(state),'--page-size','2','--model','GPT-6 Astra via Codex; local curator fixture'],
                           cwd=checkout,env={**env,'ORC_MAINTAINER_TOKEN':tokens[0]},capture_output=True,text=True,encoding='utf-8')
        output = p.stdout+p.stderr
        assert all(token not in output for token in tokens)
        (out/(name+'.txt')).write_text(output,encoding='utf-8')
        return p.returncode,output

    rc, output = run('first-seed',state_path)
    check('first_seed_succeeds',rc == 0)
    assert rc == 0, 'Inspect first-seed.txt before continuing.'
    state_bytes = state_path.read_bytes()
    state = json.loads(state_bytes)
    project = get('/v1/projects/kissing-number-11')
    check('state_identity_bound',state['project_id'] == project['id'] and state['actor_id'] == actors[0] and state['base'] == BASE)
    claim = json.loads((package/'contributions.json').read_text(encoding='utf-8'))[0]
    cid = state['records']['contribution:k11-604']['id']
    rec = get('/v1/contributions/'+cid)
    check('full_claim_projection_matches',seed['contribution_projection_from_server'](rec,1) == seed['contribution_projection_from_package'](claim))
    check('three_artifact_references',len(rec['revision']['artifacts']) == 3)
    tasks = json.loads((package/'tasks.json').read_text(encoding='utf-8'))
    for task in tasks:
        tid = state['records']['task:'+task['key']]['id']
        check('task:'+task['key'],seed['task_projection_from_server'](get('/v1/tasks/'+tid)) == seed['task_projection_from_package'](task,cid if task.get('target') else None))
    packet = get('/v1/projects/kissing-number-11/context')
    check('context_three_checks_two_tasks',len(packet['requests_for_checks']) == 3 and len(packet['open_tasks']) == 2)
    rc, output = run('unchanged-replay',state_path)
    check('replay_creates_nothing',rc == 0 and not any(line.startswith('created ') for line in output.splitlines()))
    check('replay_state_unchanged',state_path.read_bytes() == state_bytes)
    rc, output = run('stateless-adoption',out/'adopted-state.json')
    check('stateless_adoption_no_duplicates',rc == 0 and sum(' adopted from an earlier run after full comparison:' in line for line in output.splitlines()) == 8 and not any(line.startswith('created ') for line in output.splitlines()))

    receipt = {'kind':'independent_implementation','outcome':'matched','run_id':state['run_id'],
        'checked_md':'Local fixture: exercise the receipt author restriction on the exact seeded revision.',
        'not_checked_md':'This local API rehearsal is not a new mathematical check or a public receipt.',
        'method_md':'Submit this body once as the curator fixture, then as the separate checker fixture.',
        'observations_md':'Separate identities share this test operator and fixture data.',
        'independence':{'execution':'shared','implementation':'shared','data':'shared','design':'shared'},
        'relationships_md':'Both are ephemeral local test identities operated by Astra for this rehearsal.'}
    status, _ = request('POST',f'/v1/contributions/{cid}/revisions/1/receipts',receipt,0)
    check('curator_self_receipt_refused',status == 403)
    status, run_result = request('POST','/v1/me/runs',{'model':'GPT-6 Astra via Codex; local checker fixture','harness':'review_kissing_package.py'},1)
    assert status == 201
    status, received = request('POST',f'/v1/contributions/{cid}/revisions/1/receipts',{**receipt,'run_id':run_result['id']},1)
    check('separate_author_receipt_accepted',status == 201 and received.get('author_id') == actors[1] and received.get('revision') == 1)
    exported = get('/v1/projects/kissing-number-11/export')
    check('export_one_claim_five_tasks_two_posts',len(exported['contributions']) == 1 and len(exported['tasks']) == 5 and len(exported['posts']) == 2)
    check('export_one_separate_author_receipt',len(exported['receipts']) == 1 and exported['receipts'][0]['author_id'] == actors[1])
    results.update(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),project_id=project['id'],contribution_id=cid,
                   passed=sum(results['checks'].values()),total=len(results['checks']),tokens_in_output=False)
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':results['passed'],'total':results['total']}))
    return 0 if all(results['checks'].values()) else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
