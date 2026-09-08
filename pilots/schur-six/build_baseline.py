"""Rebuild the published 536 witness from the checked page-6 transcription."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build():
    source = json.loads((ROOT / 'source-transcription.json').read_text(encoding='utf-8'))
    listed = source['listed_sets']
    assert len(listed) == 6 and source['mirror_sum'] == 537
    assert source['exceptional_singletons'] == {'179': 4, '358': 1}
    values = [x for group in listed for x in group]
    assert len(values) == len(set(values)) == 269
    assert set(values) == set(range(1, 269)) | {358}
    colors = [None] * 536
    for color, group in enumerate(listed):
        for x in group:
            # 179+179=358 forces the two exceptional entries to differ.
            for value in ([x] if x in (179, 358) else [x, 537 - x]):
                assert colors[value - 1] is None
                colors[value - 1] = color
    assert all(type(c) is int and 0 <= c <= 5 for c in colors)
    assert colors[178] == 3 and colors[357] == 0
    return {'format_version': 1, 'n': 536, 'colors': colors}


if __name__ == '__main__':
    data = (json.dumps(build(), separators=(',', ':')) + '\n').encode('utf-8')
    target = ROOT / 'baseline-536.json'
    target.write_bytes(data)
    print(json.dumps({'path': target.name, 'sha256': hashlib.sha256(data).hexdigest(), 'n': 536}))
