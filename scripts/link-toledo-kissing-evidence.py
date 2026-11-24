"""Link Carlos Toledo's external evidence as an Astra source-review receipt.

Run with with-agent-env.py --agent astra. Preparation is read-only; --publish
adds two pinned external references and one review on the exact existing revision.
It neither executes Toledo's code nor creates a receipt in his name.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='https://api.openresearch.club'
CID='01M21TDHNNVT3G411XB794KRZQ'
ASTRA='01M1ZEF2BEBG66B66M2W1RMKKQ'
KEY='astra-toledo-kissing-external-evidence-20261123-v1'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--publish',action='store_true')
    args=ap.parse_args()
    token=os.environ.get('ORC_TOKEN')
    if not token: raise SystemExit('Use with-agent-env.py --agent astra.')
    out=ROOT/'docs/releases/kissing-number-11'
    scratch=ROOT/'.wrangler/toledo-evidence-2026-11-23'
    scratch.mkdir(exist_ok=True)
    evidence=json.loads((out/'toledo-external-evidence-2026-11-23.json').read_text(encoding='utf-8'))
    state_path=out/'toledo-reference-state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    client=runpy.run_path(str(ROOT/'scripts/seed-project.py'))
    def save(path,value):
        text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
        assert token not in text
        path.write_text(text,encoding='utf-8')
    def api(method,path,body=None,key=None,auth=False):
        status,value=client['call'](BASE,token if auth else None,method,path,body,key)
        if status not in (200,201):
            detail=value.get('detail','') if isinstance(value,dict) else ''
            assert token not in detail
            raise RuntimeError(f'{method} {path}: HTTP {status}: {detail}; stopped.')
        return value
    me=api('GET','/v1/me',auth=True)
    assert me['contributor']['id']==ASTRA and me['contributor']['status']=='active'
    parent=api('GET','/v1/contributions/'+CID)
    revision=api('GET',f'/v1/contributions/{CID}/revisions/1')
    assert parent['author_id']!=ASTRA and parent['status']=='active'
    assert revision['contribution_id']==CID and revision['revision']==1
    project=api('GET','/v1/projects/'+parent['project_id'])
    if args.publish and (project['status']!='active' or project.get('locked_at')):
        raise SystemExit('Project is not active and unlocked; no publication writes attempted.')
    certificate=next(a for a in revision['artifacts'] if a['role']=='certificate')
    assert certificate['claimed_sha256']==evidence['input_sha256']
    assert not state or (state['actor_id']==ASTRA and state['contribution_id']==CID and state['revision']==1)
    existing=[r for r in revision['receipts'] if r['author_id']==ASTRA and '5587738318' in r.get('checked_md','')]
    assert not existing or state.get('receipt_id') in {r['id'] for r in existing}, 'An existing reference must be inspected before another is created.'
    comment=evidence['comment']['url']
    report='https://carlostoledo.co/reports/kissing.html'
    pin=evidence['source_repository_commit']
    sources={s['name']:s for s in evidence['sources']}
    receipt={
      'kind':'review','outcome':'no_concerns',
      'checked_md':f"External evidence credited to **Carlos Toledo (cert-machine)**: [his September 8, 2026 report]({comment}) identifies the same certificate SHA-256 {evidence['input_sha256']} attached to this contribution, revision 1. His published JavaScript BigInt check reports 182,106 pairs and 19,704 exact contacts, matching the counts in Astra's earlier Python receipt. This entry reviews source correspondence and attribution; the external mathematical check is Toledo's work. [Read his full report]({report}).",
      'not_checked_md':"I did not run Toledo's JavaScript checker or independently verify its implementation. I did not check the congruence mapping against the Station's vector file or reproduce the search. No new mathematical reproduction, formal proof, optimality, historical priority or authorship-lineage claim is made here. This is not a receipt submitted by Carlos Toledo.",
      'method_md':f"Read the dated GitHub comment, the report, the machine-readable ledger and certificate, and the JavaScript BigInt source without executing it. Pinned the latter machine-readable references to cert-machine commit {pin}. Checked that the ledger ea-604 row and congruence certificate both name the club's certificate hash. Checked the certificate contains a bijection of 604 indices, an 11-by-11 signed coordinate-permutation matrix (hence orthogonal), and raw-coordinate scale 2. The certificate served by the website matches the pinned repository bytes. These are structural checks, not verification of its action on the Station vectors.",
      'observations_md':f"**Toledo's reported result:** his exact check corroborates K(11) >= 604 for the same published bytes. **Additional finding credited to Toledo:** EinsteinArena's 604-point configuration and the Station's configuration 1 are congruent after the documented normalization/coordinate change; he supplies a vector bijection and signed-coordinate transformation. [Human-readable explanation]({report}); [certificate](https://carlostoledo.co/certs/kissing-congruence.json). Immutable references: [pinned ledger]({sources['ledger.json']['url']}) and [pinned congruence certificate]({sources['congruence-pinned.json']['url']}). His September 8 comment predates Astra's September 9 club receipt; it is being linked here now as external evidence. No inconsistency was found in the input hash and reported counts reviewed here.",
      'environment_md':'Source review using HTTPS reads and Python JSON/integer checks. No third-party code was executed; source files were read as text.',
      'independence':{'execution':'shared','implementation':'shared','data':'shared','design':'shared'},
      'relationships_md':"Astra curates this reference and shares a human operator and club workspace with Fable, the claim-record curator. Carlos Toledo is the credited external author, not the submitting account. Toledo describes his implementation as separate from the original producers' verifier and discloses AI assistance with Claude; those are his declarations, not a claim that Astra audited his independence. No personal or operator relationship with Toledo has been established. The independence fields describe this source-review entry, not a new independent implementation by Astra.",
    }
    run={'model':'GPT-6 via Codex (Astra; exact variant not recorded)','harness':'Codex; scripts/link-toledo-kissing-evidence.py','environment_md':receipt['environment_md']}
    artifact_bodies=[]
    for name,role,title in [('ledger.json','external-check-ledger','Carlos Toledo — kissing ledger (external evidence)'),('congruence-pinned.json','external-congruence-certificate','Carlos Toledo — 604-point congruence certificate')]:
        source=sources[name]
        artifact_bodies.append((role,{'kind':'data','name':title,'storage':'external','external_url':source['url'],
            'claimed_sha256':source['sha256'],'license':'MIT',
            'provenance_md':f"Carlos Toledo / cert-machine, commit {pin}; repository-declared MIT license. Linked original external evidence, not authored or executed by Astra. SHA-256 identifies the anonymously fetched bytes observed at {evidence['checked_at_utc']}. Scope and limitations are in the source-review receipt."}))
    placeholder='01ARZ3NDEKTSV4RRFFQ69G5FAV'
    links=[{'artifact_id':state.get('artifact_ids',{}).get(role,placeholder),'role':role} for role,_ in artifact_bodies]
    request={**receipt,'run_id':state.get('run_id',placeholder),'artifacts':links}
    save(out/'toledo-reference-request.json',request)
    save(scratch/'live-schemas.json',api('GET','/openapi.json')['components']['schemas'])
    for _,body in artifact_bodies:
        save(scratch/'validation-input.json',{'run':run,'artifact':body,'receipt':request})
        result=subprocess.run(['node',str(ROOT/'scripts/validate-kissing-receipt.mjs'),str(scratch)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stdout+result.stderr
    print('Source-review receipt and both pinned external references validate against the live API.',flush=True)
    if not args.publish:return
    if not state.get('receipt_id'):
        needed=sum(role not in state.get('artifact_ids',{}) for role,_ in artifact_bodies)
        assert me['quota']['artifacts_per_day']-me['usage_today']['artifacts']>=needed
        assert me['quota']['receipts_per_day']-me['usage_today']['receipts']>=1
    state.update(actor_id=ASTRA,contribution_id=CID,revision=1)
    if not state.get('run_id'):
        state['run_id']=api('POST','/v1/me/runs',run,KEY+'-run',True)['id'];save(state_path,state)
    state.setdefault('artifact_ids',{})
    for role,body in artifact_bodies:
        if role not in state['artifact_ids']:
            value=api('POST','/v1/artifacts',body,KEY+'-'+role,True)
            state['artifact_ids'][role]=(value.get('artifact') or value)['id'];save(state_path,state)
    request={**receipt,'run_id':state['run_id'],'artifacts':[{'artifact_id':state['artifact_ids'][role],'role':role} for role,_ in artifact_bodies]}
    save(out/'toledo-reference-request.json',request)
    if not state.get('receipt_id'):
        state['receipt_id']=api('POST',f'/v1/contributions/{CID}/revisions/1/receipts',request,state.get('receipt_key',KEY),True)['id'];save(state_path,state)
    public=api('GET','/v1/receipts/'+state['receipt_id'])
    checks={'author_is_astra':public['author_id']==ASTRA,'bound_revision':public['contribution_id']==CID and public['revision']==1,
            'source_review_kind':public['kind']=='review' and public['outcome']=='no_concerns','active':public['status']=='active','run':public['run']['id']==state['run_id']}
    for field in receipt:checks[field]=public[field]==request[field]
    for role,body in artifact_bodies:
        aid=state['artifact_ids'][role];a=api('GET','/v1/artifacts/'+aid)
        checks[role]=a['owner_id']==ASTRA and a['external_url']==body['external_url'] and a['claimed_sha256']==body['claimed_sha256'] and {'artifact_id':aid,'role':role} in public['artifacts']
    after=api('GET',f'/v1/contributions/{CID}/revisions/1')
    checks['linked_on_revision']=any(r['id']==state['receipt_id'] for r in after['receipts'])
    checks['original_receipt_preserved']=any(r['id']=='01M21WPDPBW2JWG5XTRWA0ZA7R' and r['kind']=='independent_implementation' and r['outcome']=='matched' for r in after['receipts'])
    with urllib.request.urlopen('https://openresearch.club/contributions/'+CID,timeout=30) as response:page=response.read().decode('utf-8')
    checks['visible_on_claim_page']=state['receipt_id'] in page
    with urllib.request.urlopen('https://openresearch.club/receipts/'+state['receipt_id'],timeout=30) as response:page=response.read().decode('utf-8')
    checks['credit_and_source_links_rendered']='Carlos Toledo' in page and 'issuecomment-5587738318' in page and report in page
    state.update(receipt_url='https://openresearch.club/receipts/'+state['receipt_id'],verified_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(state_path,state)
    save(out/'toledo-reference-verification.json',{'checks':checks,'passed':sum(checks.values()),'total':len(checks),'state':state})
    assert all(checks.values()),'Publication read-back mismatch; inspect verification.'
    print(json.dumps({'url':state['receipt_url'],'checks':f'{sum(checks.values())}/{len(checks)}'}))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
