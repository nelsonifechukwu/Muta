"""Read-only remote reconciliation; preserve small metadata once, never infer."""
import hashlib
import json
import subprocess
from pathlib import Path

REMOTE = r'''
import hashlib, json, sys, time
from pathlib import Path
from types import SimpleNamespace
root = Path('/lambda/nfs/awf-tmp/muta/campaign-20260918/science-tutor-20260919')
release = root / 'release/development12-v1'
source = release / 'sources/generation_release.py'
assert hashlib.sha256(source.read_bytes()).hexdigest() == '2937b42e235eb5f242ea51f1c2805cd5a70246f1c073c5704f935a33844a590e'
sys.path.insert(0, str(source.parent))
import generation_release as g
args = SimpleNamespace(manifest=release/'manifest.json', manifest_sha256='b48ab3acf2805cc740bb55b1568a1d5677ba7ec8213c4c39272ae60a448eb3a0')
m, inv, config, ref = g.load_manifest(args)
g.verify_remote(inv, config)
ids = [p['id'] for p in g.evaluate.load_prompts(config['prompts'])]
checked = {cid:g.verify_candidate(config, m['config'], cid, ids) for cid in g.ORDER}
control = Path(m['host']['control'])
seal = g.train.read_json(control/'COMPLETED.json')
assert seal['status'] == 'complete' and seal['candidate_count'] == 12
assert seal['responses_per_candidate'] == 72 and seal['ranking_performed'] is False
assert seal['manifest'] == ref and seal['config'] == m['config'] and seal['candidates'] == checked
actual = g.train.tree_receipt(control)
files = [r for r in actual['files'] if r['path'] != 'COMPLETED.json']
digest = hashlib.sha256('\n'.join(f"{r['sha256']}  {r['path']}" for r in files).encode()).hexdigest()
assert seal['inventory'] == dict(root=str(control.resolve()), files=files, file_count=len(files), bytes=sum(r['bytes'] for r in files), tree_sha256=digest)
assert not list(control.rglob('FAILED.json'))
assert not list(Path(config['output']).rglob('FAILED.json'))
stdout = control.with_suffix('.stdout.log').read_bytes()
assert json.loads(stdout) == seal
completion = dict(schema_version=1, status='all12_complete', config_sha256=m['config']['sha256'], candidates={cid:dict(remote_root=str(Path(config['output'])/cid), completed_sha256=r['sha256']) for cid,r in checked.items()})
print(json.dumps(dict(completion_manifest=completion, queue_completion=seal, queue_completion_ref=g.train.file_receipt(control/'COMPLETED.json'), controller_stdout_ref=g.train.file_receipt(control.with_suffix('.stdout.log')), output_inventory=g.train.tree_receipt(config['output']), captured_unix=time.time(), checks=dict(frozen_source=True, original_model_and_checkpoint_hashes=True, all_864_response_raw_batch_joins=True, queue_inventory=True, controller_printed_return=True, no_failure_markers=True)), sort_keys=True))
'''


def main():
    base = Path('provenance/science-tutor-20260919/evaluation/development12-v1-capture')
    base.mkdir(exist_ok=False)
    run = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
         'ubuntu@129.213.31.157',
         'PYTHONDONTWRITEBYTECODE=1 /home/ubuntu/muta-finetune/.venv/bin/python -'],
        input=REMOTE.encode(), capture_output=True, timeout=300,
    )
    for name, content in [('remote-stdout.json', run.stdout), ('remote-stderr.log', run.stderr)]:
        with (base/name).open('xb') as f:
            f.write(content)
    if run.returncode:
        with (base/'FAILED.json').open('x') as f:
            json.dump({'returncode':run.returncode,'automatic_retry':False}, f)
        raise SystemExit(run.returncode)
    result = json.loads(run.stdout)
    for name, data in [('completion-manifest.json',result['completion_manifest']),
                       ('ROOT_RECONCILIATION.json', result)]:
        raw = (json.dumps(data, sort_keys=True, indent=2)+'\n').encode()
        with (base/name).open('xb') as f:
            f.write(raw)
        print(name, hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    main()
