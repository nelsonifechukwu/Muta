"""Materialize the predeclared 64 MC development rows for independent review."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/muta-science-tutor-20260919/pilot-v1/dev.jsonl'
DATA_SHA = '5db3f963901fb44c9399803a7d67b5694b5c5086827fede34fad1e71a2381db4'
OUTPUT = ROOT / 'provenance/science-tutor-20260919/evaluation/development64-v1'
SUBJECTS = ('biology', 'chemistry', 'physics', 'earth_environmental_science', 'integrated_science')


def rank(row):
    return hashlib.sha256(('3407:science-dev-v1:' + row['id']).encode()).hexdigest()


def select(rows):
    selected = []
    for subject in SUBJECTS:
        bucket = [r for r in rows if r['source'] == 'scienceqa' and r['subject'] == subject]
        if len(bucket) < 8:
            raise ValueError('insufficient subject coverage: ' + subject)
        selected.extend(sorted(bucket, key=rank)[:8])
    selected.extend(sorted((r for r in rows if r['source'] == 'sciq'), key=rank)[:24])
    if len(selected) != 64 or len({r['id'] for r in selected}) != 64:
        raise ValueError('invalid development count/identities')
    return selected


def main():
    raw = DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('source development artifact changed')
    selected = select([json.loads(line) for line in raw.splitlines()])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    for name, records in (
        ('review.jsonl', selected),
        ('prompts.jsonl', [{'id': r['id'], 'subject': r['subject'], 'messages': r['messages'][:-1]} for r in selected]),
    ):
        with (OUTPUT / name).open('x') as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    manifest = {'status': 'pending_independent_key_review', 'source_sha256': DATA_SHA,
                'selection_rule': 'SHA256(3407:science-dev-v1:<id>), 8 per five ScienceQA subjects plus 24 SciQ',
                'rows': 64, 'ids': [r['id'] for r in selected],
                'artifacts': {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in ('review.jsonl', 'prompts.jsonl')},
                'inference_performed': False}
    with (OUTPUT / 'manifest.json').open('x') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps({'output': str(OUTPUT), 'rows': 64, 'status': manifest['status']}))


if __name__ == '__main__':
    main()
