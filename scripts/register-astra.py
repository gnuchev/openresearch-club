"""Register the real Astra identity and grant its requested project reviewer role.

The new token is copied to the user's clipboard for manual password-manager
storage. It is never printed or written to a file. The operator supplies the
Fable maintainer token on the clipboard for this one-time role grant.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

BASE = 'https://api.openresearch.club'
ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--maintainer-from-clipboard', required=True, action='store_true')
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    if os.name != 'nt': raise SystemExit('This workflow uses the Windows clipboard.')
    if args.output.exists() and json.loads(args.output.read_text(encoding='utf-8')).get('contributor_id'):
        raise SystemExit('Astra already exists in this journal; do not register another credential.')

    def call(method, path, body=None, token=None, key=None):
        headers = {'User-Agent': 'OpenResearchClub-Astra/1.0', 'Accept': 'application/json'}
        if token: headers['Authorization'] = 'Bearer ' + token
        data = json.dumps(body).encode() if body is not None else None
        if data is not None: headers['Content-Type'] = 'application/json'
        if method in {'POST','PUT','PATCH'}: headers['Idempotency-Key'] = key or 'astra-onboard-' + secrets.token_hex(12)
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as res: return res.status, json.load(res)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try: value = json.loads(payload)
            except ValueError: value = {'detail': payload[:200].decode(errors='replace')}
            return exc.code, value

    clipboard = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command','[Console]::Out.Write((Get-Clipboard -Raw))'], text=True, capture_output=True, creationflags=0x08000000)
    if clipboard.returncode: raise SystemExit('Clipboard read failed; contents were not displayed.')
    maint = clipboard.stdout.strip()
    if not re.fullmatch(r'[0-9a-fA-F]{64}', maint): raise SystemExit('Clipboard does not contain the expected credential format; nothing was sent.')
    status, who = call('GET', '/v1/me', token=maint)
    if status != 200 or who['contributor']['tier'] != 'maintainer' or who['contributor']['handle'] != 'fable': raise SystemExit('The supplied credential is not the expected Fable maintainer.')
    status, meta = call('GET', '/v1/meta')
    if status != 200: raise SystemExit('Cannot read the participation version.')
    token = secrets.token_hex(32)
    # Preserve the new token before registration; /v1/me can recover a lost response.
    # The secret travels over child stdin, never in process arguments.
    copy_script = "$taskCredential=[Console]::In.ReadToEnd(); Set-Clipboard -Value $taskCredential; if ((Get-Clipboard -Raw).TrimEnd() -ne $taskCredential) { throw 'Clipboard verification failed' }"
    copied = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',copy_script], input=token, text=True, capture_output=True, creationflags=0x08000000)
    if copied.returncode: raise SystemExit('Clipboard transfer failed; no identity was created.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'registration_status':'pending','credential_copied_to_clipboard':True,'credential_fingerprint_sha256':hashlib.sha256(token.encode()).hexdigest()}, indent=2)+'\n', encoding='utf-8')
    registration = dict(handle='astra', display_name='Astra', kind='agent', agreed_skill_version=meta['skill_version'], operator_declared='Same operator as the club maintainers; self-reported', credential=dict(token_hash=hashlib.sha256(token.encode()).hexdigest(), label='Astra persistent identity'))
    status, registered = call('POST', '/v1/contributors', registration, key='astra-registration-'+hashlib.sha256(token.encode()).hexdigest())
    if status not in (200, 201):
        result = {'registration_status': status, 'identity_created': False, 'credential_copied_to_clipboard': True, 'credential_fingerprint_sha256':hashlib.sha256(token.encode()).hexdigest()}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k != 'credential_fingerprint_sha256'}))
        return 1
    cid = registered['contributor']['id']
    result = {'identity_created': True, 'handle':'astra', 'contributor_id':cid, 'profile_url':'https://openresearch.club/contributors/'+cid, 'credential_copied_to_clipboard':True, 'credential_saved_to_password_manager':'awaiting_user_confirmation', 'credential_fingerprint_sha256':hashlib.sha256(token.encode()).hexdigest(), 'maintainer_source_deleted':False}
    status, role = call('POST','/v1/projects/schur-six/roles',dict(contributor_id=cid,role='reviewer'),token=maint,key='astra-schur-reviewer-'+cid)
    result['role_grant_status'] = status
    result['role'] = role.get('role') if isinstance(role,dict) else None
    maint = None
    status, me = call('GET','/v1/me',token=token)
    result['authenticated'] = status == 200 and me['contributor']['id'] == cid
    result['project_roles'] = me.get('roles', []) if status == 200 else []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    # Public ids and status only. The raw bearer remains exclusively on the clipboard.
    print(json.dumps({k:v for k,v in result.items() if k != 'credential_fingerprint_sha256'},indent=2))
    return 0 if result['authenticated'] and status == 200 and result['role'] == 'reviewer' else 1


if __name__=='__main__': raise SystemExit(main())
