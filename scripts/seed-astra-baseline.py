"""Publish Astra's known Schur baseline; no self-review receipt is created.

The operator supplies ORC_TOKEN ephemerally or authorizes reading Astra's token
from the clipboard. Its hash must match --journal (public metadata only). Requests
use fixed idempotency keys and retain created ids for recovery after interruption.
The contribution template gains run_id and artifact links before submission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SEED = runpy.run_path(str(ROOT / 'scripts/seed-schur-six.py'))
BASE = 'https://api.openresearch.club'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal', type=Path, required=True)
    args = parser.parse_args()
    state = json.loads(args.journal.read_text(encoding='utf-8'))
    token = os.environ.get('ORC_TOKEN')
    if token is None:
        clipboard = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                                   '[Console]::Out.Write((Get-Clipboard -Raw))'],
                                  capture_output=True, text=True, creationflags=0x08000000)
        if clipboard.returncode:
            raise SystemExit('Clipboard read failed; nothing was sent.')
        token = clipboard.stdout.strip()
    if hashlib.sha256(token.encode()).hexdigest() != state['credential_fingerprint_sha256']:
        raise SystemExit('Clipboard credential does not match Astra onboarding; nothing was sent.')

    def save(**updates):
        state.update(updates)
        args.journal.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')

    def call(method, path, body=None, key=None):
        status, result = SEED['call'](BASE, token, method, path, body, key)
        if status not in (200, 201):
            raise RuntimeError(f'{method} {path}: HTTP {status}. No further writes attempted.')
        return result

    me = call('GET', '/v1/me')
    if me['contributor']['handle'] != 'astra' or me['contributor']['id'] != state['contributor_id']:
        raise SystemExit('Expected the registered Astra identity.')
    context = call('GET', '/v1/projects/schur-six/context')
    template = json.loads((ROOT / 'docs/challenges/schur-six-baseline-contribution.template.json').read_text(encoding='utf-8'))
    if context['contract']['version'] != template['contract_version'] or context['project']['status'] != 'active':
        raise SystemExit('The project changed. Read the new contract before submitting.')
    # Check pinned public bytes before registering their claimed hashes.
    for name, _, sha, *_ in SEED['ARTIFACTS']:
        with urllib.request.urlopen(SEED['RAW'] + name, timeout=30) as response:
            if hashlib.sha256(response.read()).hexdigest() != sha:
                raise SystemExit('Pinned artifact hash mismatch: ' + name)
    if not state.get('run_id'):
        run = call('POST', '/v1/me/runs', {
            'model': 'GPT-6 (Astra)', 'harness': 'Codex desktop',
            'environment_md': 'Windows; same human operator as club maintainers. Records this session\'s Schur package and validation. Provenance is self-reported.'
        }, 'astra-schur-baseline-run-v1')
        save(run_id=run['id'])
    artifacts = state.get('baseline_artifacts', {})
    for name, kind, sha, license_id, provenance in SEED['ARTIFACTS']:
        if name in artifacts:
            continue
        result = call('POST', '/v1/artifacts', {
            'kind': kind, 'name': name, 'storage': 'external', 'external_url': SEED['RAW'] + name,
            'claimed_sha256': sha, 'license': license_id, 'provenance_md': provenance
        }, 'astra-schur-baseline-artifact-' + name)
        artifacts[name] = result['artifact']['id']
        save(baseline_artifacts=artifacts)
    template['run_id'] = state['run_id']
    template['artifacts'] = [{'artifact_id': artifacts[name], 'role': 'data' if kind == 'data' else 'code'}
                             for name, kind, *_ in SEED['ARTIFACTS']]
    save(baseline_request=template)
    if not state.get('baseline_contribution_id'):
        result = call('POST', '/v1/contributions', template, 'astra-schur-baseline-contribution-v1')
        save(baseline_contribution_id=result['id'], baseline_revision=result['current_revision'])
    public = call('GET', '/v1/contributions/' + state['baseline_contribution_id'])
    if public['author_id'] != state['contributor_id'] or public['claim'] != template['claim']:
        raise RuntimeError('Public contribution did not match the submitted author and claim.')
    save(baseline_public_verified=True)
    print(json.dumps({k: v for k, v in state.items() if k not in {'credential_fingerprint_sha256', 'baseline_request'}}, indent=2))


if __name__ == '__main__':
    main()
