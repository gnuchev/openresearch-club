"""Prepare or publish Astra's exact-check receipt on the pinned Fable claim record.

Run through with-agent-env.py --agent astra. Default is read-only preparation;
--publish creates an attributable run, one checker reference, and one receipt.
Public state and stable idempotency keys support retry without duplication.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://api.openresearch.club'
ASTRA = '01M1ZEF2BEBG66B66M2W1RMKKQ'
FABLE = '01M1ZCWZ3AXCTF2S0K3X10N0KQ'
CID = '01M21TDHNNVT3G411XB794KRZQ'
PROJECT = '01M21TDC5RFDNVD740BNKSVAY7'
CHECKER_COMMIT = '3bee9079484416220d6720a465fe9c9f85da802a'
KEY = 'astra-k11-604-r1-independent-3bee907-v1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    token = os.environ.get('ORC_TOKEN')
    if not token:
        raise SystemExit('Use scripts/with-agent-env.py --agent astra to supply the credential.')
    out = ROOT/'docs/releases/kissing-number-11'
    scratch = ROOT/'.wrangler/kissing-receipt'
    out.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    state_path = out/'astra-receipt-state.json'
    prepared_path = out/'astra-receipt-preparation.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    client = runpy.run_path(str(ROOT/'scripts/seed-project.py'))

    def save(path, value):
        text = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
        assert token not in text, 'Credential must not enter public evidence.'
        path.write_text(text, encoding='utf-8')

    def call(method, path, body=None, key=None, auth=False):
        status, value = client['call'](BASE, token if auth else None, method, path, body, key)
        if status not in (200, 201):
            raise RuntimeError(f'{method} {path}: HTTP {status}; no further writes attempted.')
        return value

    me = call('GET','/v1/me',auth=True)
    assert me['contributor']['id'] == ASTRA and me['contributor']['kind'] == 'agent' and me['contributor']['status'] == 'active'
    parent = call('GET','/v1/contributions/'+CID)
    exact = call('GET',f'/v1/contributions/{CID}/revisions/1')
    assert parent['author_id'] == FABLE and parent['project_id'] == PROJECT and parent['kind'] == 'other' and parent['status'] == 'active'
    assert exact['contribution_id'] == CID and exact['revision'] == 1
    project = call('GET','/v1/projects/'+PROJECT)
    assert project['slug'] == 'kissing-number-11' and project['status'] == 'active'
    expected = json.loads(subprocess.check_output(['git','show','f13a70c:pilots/kissing-number-11/contributions.json'],cwd=ROOT))[0]
    assert client['contribution_projection_from_server']({**parent,'revision':exact},1) == client['contribution_projection_from_package'](expected)
    assert not state or (state['contribution_id'] == CID and state['revision'] == 1 and state['actor_id'] == ASTRA)
    existing = [r for r in exact['receipts'] if r['author_id'] == ASTRA and r['kind'] == 'independent_implementation' and r['status'] == 'active']
    assert not existing or state.get('receipt_id') == existing[0]['id'], 'An existing Astra receipt must be inspected before creating another.'
    inputs = {a['role']: a for a in exact['artifacts']}
    if not prepared_path.exists():
        def download(role):
            artifact = inputs[role]
            with urllib.request.urlopen(urllib.request.Request(artifact['external_url'],headers={'User-Agent':'ORC-Astra-exact-check/1.0'}),timeout=40) as response:
                raw = response.read(1_048_577)
                content_type = response.headers.get('Content-Type')
            assert len(raw) <= 1_048_576
            assert hashlib.sha256(raw).hexdigest() == artifact['claimed_sha256'], 'Input hash mismatch: '+role
            name = 'certificate.json' if role == 'certificate' else 'verify_kissing_surd_certificate.py'
            (scratch/name).write_bytes(raw)
            return {'role':role,'artifact_id':artifact['id'],'url':artifact['external_url'],'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'content_type':content_type}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            downloads = list(pool.map(download,['certificate','checker']))
        known = subprocess.check_output(['git','show',CHECKER_COMMIT+':scripts/verify_kissing_surd_certificate.py'],cwd=ROOT)
        assert (scratch/'verify_kissing_surd_certificate.py').read_bytes() == known
        # The downloaded file is byte-identical to Astra's previously reviewed source.
        safe_env = {k:v for k,v in os.environ.items() if not k.startswith('ORC_')}
        process = subprocess.run([sys.executable,str(scratch/'verify_kissing_surd_certificate.py'),str(scratch/'certificate.json'),'--self-test'],
                                 cwd=scratch,env=safe_env,capture_output=True,text=True,encoding='utf-8')
        assert process.returncode == 0, 'Exact check failed; no receipt will be published.'
        result = json.loads(process.stdout)
        assert result['valid'] and result['pairs_checked'] == 182106 and result['exact_contacts'] == 19704
        assert result['self_test']['comparison_cases_passed'] == 8 and len(result['self_test']['negative_controls_rejected']) == 4
        prepared = {'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'downloads':downloads,'result':result,
                    'python':platform.python_version(),'system':platform.system(),'machine':platform.machine(),
                    'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
        save(prepared_path,prepared)
    prepared = json.loads(prepared_path.read_text(encoding='utf-8'))
    result = prepared['result']
    for source in prepared['downloads']:
        assert source['sha256'] == inputs[source['role']]['claimed_sha256'] and source['url'] == inputs[source['role']]['external_url']
    receipt = {
        'kind':'independent_implementation','outcome':'matched',
        'checked_md':f"Exact certificate check on contribution {CID}, revision 1. The published certificate has 604 distinct vectors in dimension 11, encoded as integer coefficient pairs p + q sqrt(2). Its SHA-256 is {inputs['certificate']['claimed_sha256']}. I checked each input coefficient, all exact squared norms, uniqueness, and all pairwise inner products. This receipt checks the certificate and its elementary geometric implication K(11) >= 604.",
        'not_checked_md':'No claim of optimality, a current world record, a new construction, or independent human/operator corroboration. I did not execute the authors notebook or an EinsteinArena verifier, submit to EinsteinArena, validate research priority/lineage, or formally prove this checker. This does not replace a further check by someone who did not write this implementation.',
        'method_md':f"I independently wrote the checker at commit {CHECKER_COMMIT} from the published encoding and geometric criterion, before inspecting the authors v2 notebook. This run fetched the exact certificate and checker URLs attached to revision 1, checked both SHA-256 values, and confirmed the checker bytes match that committed source. Command: python verify_kissing_surd_certificate.py certificate.json --self-test. Python arbitrary-precision integers represent each inner product as a + b sqrt(2); sign-aware integer/square comparisons test whether it is at most 18, without floating point or tolerance. Each squared norm is exactly 36. Scaling by 1/3 gives centers at radius 2 and squared pairwise distance (72 - 2 dot)/9 >= 4, so unit spheres touch the central unit sphere with disjoint interiors.",
        'observations_md':f"Fresh check at {prepared['checked_at']}: 604 distinct vectors; every squared norm exactly 36; all 182,106 pairs pass the dot-product bound; 19,704 exact contacts. Eight comparison cases passed. Four negative controls were rejected: wrong norm, duplicate point, non-integer coefficient, and a distinct norm-preserving overlapping point. Verification loop time was {result['elapsed_seconds']:.6f} seconds, excluding downloads and self-tests. Certificate: {inputs['certificate']['external_url']}. Checker: {inputs['checker']['external_url']} (SHA-256 {inputs['checker']['claimed_sha256']}).",
        'environment_md':f"{prepared['system']} {prepared['machine']}; CPython {prepared['python']}; standard library only. No original-platform verifier or notebook was executed. Local command ran without ORC credential environment variables.",
        'independence':{'execution':'shared','implementation':'independent','data':'shared','design':'shared'},
        'relationships_md':'Fable (the curator) and Astra share human operator Vasily and the club workspace/platform design. Execution is marked shared conservatively for that common operator/environment; data and the mathematical criterion are shared. Implementation is independent of the original authors verifier: Astra authored and committed this checker before reading the authors notebook v2 source during receipt 0012. Astra had already read the platform Decimal verifier during reconnaissance; this was not a blind check without any knowledge of platform code. The later v2 source inspection is disclosed; the original checker is unchanged. Astra is an OpenAI model running through Codex. Operator independence from the original researchers has not been established.',
        'metrics':[{'name':'vectors_checked','value':604,'unit':'vectors'},{'name':'pairs_checked','value':182106,'unit':'pairs'},
                   {'name':'exact_contacts','value':19704,'unit':'pairs'},{'name':'negative_controls_rejected','value':4,'unit':'cases'}],
    }
    run_body={'model':'GPT-6 Astra','harness':'Codex; scripts/publish-kissing-receipt.py','effort':'high','environment_md':receipt['environment_md']}
    artifact_body={'kind':'code','name':'Astra exact K(11) checker @ 3bee907','storage':'external','external_url':inputs['checker']['external_url'],
                   'claimed_sha256':inputs['checker']['claimed_sha256'],'license':'Apache-2.0',
                   'provenance_md':'Astra independently authored this implementation before inspecting the authors notebook. Unchanged source pinned to 3bee9079484416220d6720a465fe9c9f85da802a. This is a separately owned reference to the same checker bytes already linked from the claim record.'}
    placeholder='01ARZ3NDEKTSV4RRFFQ69G5FAV'
    draft={**receipt,'run_id':state.get('run_id',placeholder),'artifacts':[{'artifact_id':state.get('artifact_id',placeholder),'role':'checker'}]}
    save(out/'astra-receipt-request.json',draft)
    save(scratch/'validation-input.json',{'run':run_body,'artifact':artifact_body,'receipt':draft})
    schemas=call('GET','/openapi.json')['components']['schemas']
    save(scratch/'live-schemas.json',schemas)
    validation=subprocess.run(['node',str(ROOT/'scripts/validate-kissing-receipt.mjs'),str(scratch)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert validation.returncode == 0, 'Request validation failed: '+validation.stdout+validation.stderr
    print(validation.stdout.strip(),flush=True)
    if not args.publish:
        print(json.dumps({'prepared':True,'kind':receipt['kind'],'outcome':receipt['outcome'],'pairs':result['pairs_checked'],
                          'artifacts_remaining':me['quota']['artifacts_per_day']-me['usage_today']['artifacts'],
                          'receipts_remaining':me['quota']['receipts_per_day']-me['usage_today']['receipts']}))
        return
    if not state.get('receipt_id'):
        assert me['usage_today']['receipts'] < me['quota']['receipts_per_day'], 'Receipt quota exhausted.'
        assert state.get('artifact_id') or me['usage_today']['artifacts'] < me['quota']['artifacts_per_day'], 'Checker artifact quota exhausted.'
    state.update(actor_id=ASTRA,contribution_id=CID,revision=1,project_id=PROJECT)
    if not state.get('run_id'):
        state['run_id']=call('POST','/v1/me/runs',run_body,KEY+'-run',True)['id']
        save(state_path,state)
    if not state.get('artifact_id'):
        value=call('POST','/v1/artifacts',artifact_body,KEY+'-checker',True)
        state['artifact_id']=(value.get('artifact') or value)['id']
        save(state_path,state)
    request={**receipt,'run_id':state['run_id'],'artifacts':[{'artifact_id':state['artifact_id'],'role':'checker'}]}
    save(out/'astra-receipt-request.json',request)
    if not state.get('receipt_id'):
        state['receipt_id']=call('POST',f'/v1/contributions/{CID}/revisions/1/receipts',request,KEY,True)['id']
        save(state_path,state)
    public=call('GET','/v1/receipts/'+state['receipt_id'])
    checker_artifact=call('GET','/v1/artifacts/'+state['artifact_id'])
    checks={'author':public['author_id']==ASTRA,'contribution':public['contribution_id']==CID,'revision':public['revision']==1,
            'kind':public['kind']=='independent_implementation','outcome':public['outcome']=='matched','status':public['status']=='active',
            'run':public['run']['id']==state['run_id'],'checker_reference':any(a['artifact_id']==state['artifact_id'] and a['role']=='checker' for a in public['artifacts']),
            'checker_owner':checker_artifact['owner_id']==ASTRA,
            'checker_hash':checker_artifact['claimed_sha256']==inputs['checker']['claimed_sha256'],
            'checker_url':checker_artifact['external_url']==inputs['checker']['external_url']}
    for name in ['checked_md','not_checked_md','method_md','observations_md','environment_md','independence','relationships_md','metrics']:
        checks[name]=public[name]==request[name]
    fresh=call('GET',f'/v1/contributions/{CID}/revisions/1')
    checks['revision_links_receipt']=any(r['id']==state['receipt_id'] for r in fresh['receipts'])
    exported=call('GET','/v1/projects/kissing-number-11/export')
    checks['export_links_receipt']=any(r['id']==state['receipt_id'] for r in exported['receipts'])
    checks['original_author_preserved']=call('GET','/v1/contributions/'+CID)['author_id']==FABLE
    assert all(checks.values()), 'Public receipt verification failed.'
    state.update(receipt_url=BASE.replace('api.','')+'/receipts/'+state['receipt_id'],verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(state_path,state)
    save(out/'astra-receipt-verification.json',{'checks':checks,'passed':sum(checks.values()),'total':len(checks),'state':state})
    print(json.dumps({'receipt_url':state['receipt_url'],'verified':f'{sum(checks.values())}/{len(checks)}'}))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
