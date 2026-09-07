"""Narrow W2/W4 recheck derived from receipt 0005 fixtures; upload-header uncertainty is excluded explicitly."""
import argparse
import hashlib
import json
import os
import pathlib
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
from review_runtime_a1636aa import uid

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8791'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    review = ROOT / '.wrangler/astra-runtime-a1636aa'
    config = review / 'wrangler.jsonc'
    cfg = json.loads(config.read_text(encoding='utf-8-sig'))
    assert cfg['name'] == 'openresearch-club-review-a1636aa' and not cfg['routes']
    env = dict(os.environ, XDG_CONFIG_HOME=str(review/'xdg'), WRANGLER_LOG_PATH=str(review/'46554c5-edge-tools.log'), WRANGLER_SEND_METRICS='false')
    checks = []
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    suffix = secrets.token_hex(4)
    admin, author = {'id':uid(), 'token':secrets.token_hex(32)}, {'id':uid(), 'token':secrets.token_hex(32), 'run':uid()}
    sql = []
    for person, tier in [(admin,'maintainer'),(author,'new')]:
        sql.append(f"INSERT INTO contributors(id,handle,display_name,kind,tier,status,agreed_skill_version,created_at) VALUES('{person['id']}','edge-{tier}-{suffix}','Synthetic edge fixture','agent','{tier}','active','1.1.1','{now}');")
        sql.append(f"INSERT INTO credentials(id,contributor_id,token_hash,scopes,created_at) VALUES('{uid()}','{person['id']}','{hashlib.sha256(person['token'].encode()).hexdigest()}','[\"read\",\"write\"]','{now}');")
    sql.append(f"INSERT INTO runs(id,contributor_id,created_at) VALUES('{author['run']}','{author['id']}','{now}');")
    fixture = review/'edge-fixture.sql'
    fixture.write_text('\n'.join(sql),encoding='utf-8')
    try:
        run = subprocess.run(['node',str(ROOT/'node_modules/wrangler/bin/wrangler.js'),'d1','execute','openresearch-club','--local','--config',str(config),'--persist-to',str(review/'state-46554c5'),'--file',str(fixture)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,creationflags=0x08000000 if os.name=='nt' else 0)
        assert run.returncode==0,run.stderr[-1000:]
    finally:
        fixture.unlink(missing_ok=True)

    def call(method,path,body=None,actor=None,key=None):
        headers={'Content-Type':'application/json'}
        if actor:headers['Authorization']='Bearer '+actor['token']
        if method in {'POST','PUT','PATCH'}:headers['Idempotency-Key']=key or 'edge-'+secrets.token_hex(12)
        req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=30) as res:status,data=res.status,res.read()
        except urllib.error.HTTPError as exc:status,data=exc.code,exc.read()
        return status,json.loads(data) if data else None

    def need(method,path,body=None,actor=None,key=None,status=201):
        observed,data=call(method,path,body,actor,key)
        assert observed==status,(method,path,observed,data)
        return data

    def record(name,expected,actual,detail=None):
        checks.append(dict(name=name,expected=expected,actual=actual,passed=expected==actual,detail=detail))
        print(('PASS ' if expected==actual else 'FAIL ')+name,flush=True)

    project=need('POST','/v1/projects',dict(slug='edge-'+suffix,title='Edge tests',kind='project',status='active',brief_md='Synthetic'),admin)
    pid=project['id']
    note=dict(tried='Fixture',happened='Fixture',limitations='No research',next_step='Review')
    def contrib_body(marker):
        return dict(project_id=pid,kind='other',title=marker,claim=marker,note=note,fields={},run_id=author['run'])
    def moderate(action,target_type,target_id):
        return need('POST','/v1/moderation/actions',dict(action=action,target_type=target_type,target_id=target_id,public_reason='Synthetic edge test'),admin)

    hidden_marker='HIDDEN_TASK_TARGET_'+suffix
    hidden=need('POST','/v1/contributions',contrib_body(hidden_marker),author)
    task=need('POST',f'/v1/projects/{pid}/tasks',dict(title='Check target',body_md='No copied claim here',kind='review',target=dict(contribution_id=hidden['id'],revision=1)),admin)
    moderate('hide','contribution',hidden['id'])
    record('hidden_contribution_direct_blocked',410,call('GET','/v1/contributions/'+hidden['id'])[0])
    status,data=call('GET','/v1/tasks/'+task['id'])
    record('hidden_claim_absent_from_task_target',False,hidden_marker in json.dumps(data),{'status':status,'target':data.get('target')})
    status,data=call('GET',f'/v1/projects/{pid}/export')
    record('hidden_claim_absent_from_task_in_export',False,hidden_marker in json.dumps(data),{'status':status})
    for route in [f'/v1/tasks?project={pid}', f'/v1/projects/{pid}/context']:
        status,data=call('GET',route)
        record('hidden_claim_absent:'+route,False,hidden_marker in json.dumps(data),{'status':status})
    moderate('unhide','contribution',hidden['id'])
    status,data=call('GET','/v1/tasks/'+task['id'])
    record('unhidden_target_claim_restored',True,status==200 and hidden_marker in json.dumps(data))

    retry_marker='REDACTION_RETRY_'+suffix
    body=contrib_body(retry_marker)
    idem='edge-create-'+suffix
    original=need('POST','/v1/contributions',body,author,idem)
    moderate('redact','contribution',original['id'])
    quota_before=need('GET','/v1/me',actor=author,status=200)['usage_today']['contributions']
    status,replayed=call('POST','/v1/contributions',body,author,idem)
    new_id=replayed.get('id') if isinstance(replayed,dict) else None
    record('redacted_create_retry_does_not_create_new_record',False,status==201 and new_id not in {None,original['id']},{'status':status,'original_id':original['id'],'retry_id':new_id})
    record('redacted_retry_returns_tombstone',410,status)
    quota_after=need('GET','/v1/me',actor=author,status=200)['usage_today']['contributions']
    record('redacted_retry_preserves_quota',quota_before,quota_after)

    post=need('POST','/v1/posts',dict(project_id=pid,title='Before lock',body_md='Original'),author)
    moderate('lock','project',pid)
    status,data=call('POST',f"/v1/posts/{post['id']}/revisions",dict(body_md='Changed while locked'),author)
    record('locked_project_post_revision_refused',403,status)
    observed=need('GET','/v1/posts/'+post['id'],status=200)
    record('locked_project_post_unchanged','Original',observed['body_md'])
    record('locked_post_revision_unchanged',1,observed['current_revision'])
    admin_post=need('POST','/v1/posts',dict(project_id=pid,title='Maintainer exception',body_md='Before'),admin)
    status,_=call('POST',f"/v1/posts/{admin_post['id']}/revisions",dict(body_md='Maintainer edit'),admin)
    record('maintainer_may_edit_locked_project_post',200,status)
    commons=need('POST','/v1/posts',dict(title='Commons exception',body_md='Before'),author)
    status,_=call('POST',f"/v1/posts/{commons['id']}/revisions",dict(body_md='Commons edit'),author)
    record('commons_post_edit_unaffected',200,status)

    report=dict(reviewed_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_tree=subprocess.check_output(['git','rev-parse','HEAD:src'],cwd=ROOT,text=True).strip(),scope='Local-only HTTP edge cases for W2 and W4, on the isolated state-46554c5 database; synthetic credentials remain in memory.',checks=checks,passed=sum(c['passed'] for c in checks),failed=sum(not c['passed'] for c in checks))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['reviewed_commit','passed','failed']},indent=2))
    return int(bool(report['failed']))


if __name__=='__main__':
    raise SystemExit(main())
