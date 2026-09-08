"""Exact six-color Schur witness checker. Standard library only; no execution of artifacts."""
import argparse
import hashlib
import json
import math
from pathlib import Path

MAX_BYTES = 1024 * 1024
MAX_N = 10000


def _integer(value):
    return type(value) is int or (type(value) is float and math.isfinite(value) and value.is_integer())


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-JSON numeric constant: ' + value)


def parse(data):
    if len(data) > MAX_BYTES:
        raise ValueError('Artifact exceeds 1 MiB')
    return json.loads(data.decode('utf-8'), object_pairs_hook=_object, parse_constant=_constant)


def verify(artifact):
    if type(artifact) is not dict or set(artifact) != {'format_version', 'n', 'colors'}:
        return {'valid': False, 'error': 'Expected exactly format_version, n, colors'}
    if not _integer(artifact['format_version']) or artifact['format_version'] != 1:
        return {'valid': False, 'error': 'Unsupported format_version'}
    n = artifact['n']
    if not _integer(n) or not 1 <= n <= MAX_N:
        return {'valid': False, 'error': 'n must be an integer from 1 to 10000'}
    n = int(n)
    colors = artifact['colors']
    if type(colors) is not list or len(colors) != n:
        return {'valid': False, 'error': 'colors must have exactly n entries'}
    if any(not _integer(c) or not 0 <= c <= 5 for c in colors):
        return {'valid': False, 'error': 'Each color must be an integer from 0 to 5; booleans are invalid'}
    colors = [int(c) for c in colors]
    checked = 0
    for x in range(1, n // 2 + 1):
        for y in range(x, n - x + 1):
            checked += 1
            z = x + y
            if colors[x - 1] == colors[y - 1] == colors[z - 1]:
                return {'valid': False, 'error': 'Monochromatic sum', 'counterexample': [x, y, z], 'color': colors[z - 1], 'pairs_checked': checked}
    return {'valid': True, 'n': n, 'colors_allowed': 6, 'class_sizes': [colors.count(c) for c in range(6)], 'pairs_checked': checked, 'claim': f'S(6) >= {n}'}


def verify_bytes(data):
    if len(data) > MAX_BYTES:
        return {'valid': False, 'error': 'Artifact exceeds 1 MiB'}
    try:
        result = verify(parse(data))
    except (ValueError, UnicodeError, RecursionError) as exc:
        result = {'valid': False, 'error': str(exc)}
    return dict(result, artifact_sha256=hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    try:
        with args.artifact.open('rb') as source:
            data = source.read(MAX_BYTES + 1)
    except OSError as exc:
        print(json.dumps({'valid': False, 'error': str(exc)}))
        return 2
    result = verify_bytes(data)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
