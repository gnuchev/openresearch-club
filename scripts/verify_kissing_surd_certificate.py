"""Check the published 604-point R^11 certificate using Python integers only.

Each coordinate is encoded by an integer pair (p, q), meaning p + q*sqrt(2).
Norm squared must be exactly 36, and each distinct pair's inner product <= 18.
Scaling all vectors by 1/3 therefore gives unit-sphere centers at radius 2 with
mutual distance >= 2. No downloaded verifier code is imported or executed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time


def surd_leq(a, b, limit):
    """Exact comparison a + b*sqrt(2) <= limit, with integer arguments."""
    c = limit - a
    if b == 0:
        return c >= 0
    if b > 0:
        return c >= 0 and 2 * b * b <= c * c
    return c >= 0 or c * c <= 2 * b * b


def inner_product(x, y):
    a = sum(x[k] * y[k] + 2 * x[k + 1] * y[k + 1] for k in range(0, 22, 2))
    b = sum(x[k] * y[k + 1] + x[k + 1] * y[k] for k in range(0, 22, 2))
    return a, b


def verify(data):
    if data.get('n') != 604 or data.get('dim') != 11:
        raise ValueError('Expected the n=604, dim=11 certificate.')
    vectors = data['vectors']
    if not isinstance(vectors, list) or len(vectors) != 604:
        raise ValueError('Expected 604 vectors.')
    for i, vector in enumerate(vectors):
        if not isinstance(vector, list) or len(vector) != 22:
            raise ValueError(f'Vector {i} must have 22 integer coefficients.')
        if any(type(x) is not int or x.bit_length() > 64 for x in vector):
            raise ValueError(f'Vector {i} has an invalid or oversized coefficient.')
        if inner_product(vector, vector) != (36, 0):
            raise ValueError(f'Vector {i} does not have exact squared norm 36.')
    if len({tuple(x) for x in vectors}) != 604:
        raise ValueError('Duplicate vectors.')
    checked = contacts = 0
    for i, x in enumerate(vectors):
        for j in range(i + 1, len(vectors)):
            a, b = inner_product(x, vectors[j])
            if not surd_leq(a, b, 18):
                raise ValueError(f'Overlapping pair {i}, {j}: inner product {a} + ({b})*sqrt(2) > 18.')
            checked += 1
            contacts += (a, b) == (18, 0)
    return {'valid': True, 'n': 604, 'dimension': 11, 'squared_norm': 36,
            'pairs_checked': checked, 'exact_contacts': contacts,
            'claim': 'K(11) >= 604', 'arithmetic': 'Python arbitrary-precision integers; no floating point or tolerance'}


def self_test(data):
    comparisons = [(18, 0, True), (19, 0, False), (18, 1, False), (18, -1, True),
                   (17, 1, False), (16, 1, True), (19, -1, True), (20, -1, False)]
    for a, b, expected in comparisons:
        assert surd_leq(a, b, 18) is expected
    rejected = []
    for case in ['wrong_norm', 'duplicate', 'non_integer', 'distinct_overlap']:
        bad = copy.deepcopy(data)
        if case == 'wrong_norm': bad['vectors'][0][0] = 5
        elif case == 'duplicate': bad['vectors'][1] = bad['vectors'][0].copy()
        elif case == 'non_integer': bad['vectors'][0][0] = True
        else:
            bad['vectors'][1] = [4, 0, 4, 0, 2, 0] + [0] * 16
            assert inner_product(bad['vectors'][1], bad['vectors'][1]) == (36, 0)
            assert inner_product(bad['vectors'][0], bad['vectors'][1]) == (24, 0)
        try:
            verify(bad)
        except ValueError:
            rejected.append(case)
        else:
            raise AssertionError('Accepted invalid control: ' + case)
    return {'comparison_cases_passed': len(comparisons), 'negative_controls_rejected': rejected}


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('Duplicate JSON key: ' + key)
        out[key] = value
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('certificate', type=Path)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    with args.certificate.open('rb') as file:
        raw = file.read(1_048_577)
    if len(raw) > 1_048_576:
        raise SystemExit('Certificate exceeds 1 MiB.')
    data = json.loads(raw, object_pairs_hook=unique_object)
    started = time.perf_counter()
    result = verify(data)
    result.update(artifact_sha256=hashlib.sha256(raw).hexdigest(), elapsed_seconds=time.perf_counter() - started)
    if args.self_test:
        result['self_test'] = self_test(data)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
