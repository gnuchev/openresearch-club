"""Run an ORC client with a selected credential from a Git-ignored local env file.

python scripts/with-agent-env.py --agent astra -- python scripts/seed-project.py PACKAGE --model "GPT-6 Astra via Codex"
The secret is passed through the child environment, never command arguments.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=['astra', 'fable'], default='astra')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env.agents.local')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('Provide a command after --.')
    key = 'ORC_' + args.agent.upper() + '_TOKEN'
    token = os.environ.get(key)
    if not token and args.env_file.exists():
        for line in args.env_file.read_text(encoding='utf-8-sig').splitlines():
            name, separator, value = line.partition('=')
            if separator and name.strip() == key:
                token = value.strip()
                if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
                    token = token[1:-1]
    if not token:
        parser.error(f'{key} is unavailable; supply it in the local env file or process environment.')
    # Both names are supported by existing club clients; both refer to this agent.
    env = {**os.environ, 'ORC_TOKEN': token, 'ORC_MAINTAINER_TOKEN': token}
    return subprocess.run(command, cwd=ROOT, env=env).returncode


if __name__ == '__main__':
    sys.exit(main())
