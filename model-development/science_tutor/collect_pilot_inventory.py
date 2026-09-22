"""Read-only remote pilot verification; print metadata, never model/training text."""
import copy
import hashlib
import json
import sys
from pathlib import Path

CAMPAIGN = Path('/lambda/nfs/awf-tmp/muta/campaign-20260918/science-tutor-20260919')
RELOCATION = CAMPAIGN / 'release/pilots-oracle-relocation-v1'
SOURCE_SHA = 'f87005775153aa3fcb84ed5c2993850dc6be64ae584fd5a958af460dcaf97e30'
CONFIGS = {
    'P1': ('pilots-v1', 'upstream_fresh', '75ecbd88bdd67a4c82215c9873f5c0024667ebe1b236bb77ee810f2b7d625084'),
    'P2': ('pilots-oracle-relocation-v1', 'muta_fresh', '3b673a7fa97722c3c8a41182247ebfbaaa4d5b084cdfc85ffd82d226ef8513a9'),
    'P3': ('pilots-oracle-relocation-v1', 'pilot_adapter', 'd5e82d6f963c3d574508a9a897835d334bbb0d0142051598187b9d69adbefab4'),
    'P4': ('pilots-v1', 'deepseek_fresh', 'f189abc2ccb704789ddd3688e5d6039f6e3206b6e86619a031732af9ce117a4b'),
}


def main():
    if sys.flags.optimize:
        raise RuntimeError('verification assertions require non-optimized Python')
    if hashlib.sha256((RELOCATION / 'sources/relocate_pilots.py').read_bytes()).hexdigest() != SOURCE_SHA:
        raise RuntimeError('reviewed verifier changed')
    sys.path.insert(0, str(RELOCATION / 'sources'))
    import relocate_pilots as verifier
    train = verifier.train
    sources = verifier.source_hashes()
    runs, controls, input_trees, control_verification = {}, {}, {}, {}
    for label, (release, kind, config_sha) in CONFIGS.items():
        config_ref = train.verify_ref({'path': str(CAMPAIGN / 'release' / release / 'configs' / (kind + '.json')), 'sha256': config_sha})
        cfg = train.read_json(config_ref['path'])
        output = Path(cfg['output'])
        assert output == CAMPAIGN / 'runs' / release / cfg['run_id']
        completion_ref = train.file_receipt(output / 'COMPLETED.json')
        completed = train.read_json(completion_ref['path'])
        expected_sources = {name: sources[name] for name in ('train.py', 'tokenization.py')}
        if label == 'P4':
            expected_sources.update({
                'deepseek_train.py': 'ec5c8cadbbffd97ee3c35d3d62fa3bb476d9766efec9ad0ba67ee2eb760905c0',
                'deepseek_tokenization.py': '2ce5c3b66476a688d2035119959b7e72c515d97822bf165e4823f02b70e98d60',
            })
        else:
            verifier.verify_terminal(cfg, config_sha, sources)
        assert completed['status'] == 'complete' and completed['run_id'] == cfg['run_id']
        assert completed['config_sha256'] == config_sha and completed['source_sha256'] == expected_sources
        assert completed['completed_steps'] == 126 and completed['resumed_from_step'] == 0
        assert completed['consumed_trainable_tokens'] == cfg['training']['expected_trainable_tokens']
        verifier.exact_inventory(output, completed['run_inventory'], excluded=('COMPLETED.json',))
        train.verify_ref(completed['metrics'])
        metrics = [json.loads(line) for line in Path(completed['metrics']['path']).read_text().splitlines()]
        steps = [row for row in metrics if row.get('kind') == 'train_step']
        assert [row['step'] for row in steps] == list(range(1, 127))
        cumulative = 0
        for row in steps:
            assert row['effective_rows'] == 64 and row['trainable_tokens'] > 0
            cumulative += row['trainable_tokens']
            assert row['cumulative_trainable_tokens'] == cumulative
        assert cumulative == cfg['training']['expected_trainable_tokens']
        control = CAMPAIGN / 'controls' / release / cfg['run_id']
        control_ref = train.file_receipt(control / 'COMPLETED.json')
        controller = train.read_json(control_ref['path'])
        assert controller['status'] == 'complete' and controller['trainer_completion'] == completion_ref
        if label == 'P4':
            # The executed native controller did not seal its own directory.
            # Preserve that limitation; do not invent an original inventory.
            assert controller['config_sha256'] == config_sha
            assert controller['source_sha256'] == expected_sources
            train.verify_ref(controller['qualification'])
            admission = train.read_json(control / 'training-admission.json')
            assert admission['qualification'] == controller['qualification']
            assert admission['config_sha256'] == config_sha
            assert admission['source_sha256'] == expected_sources
            control_verification[label] = {
                'mode': 'original_explicit_refs_verified_plus_retrospective_directory_snapshot',
                'original_control_inventory_existed': False,
                'observed_inventory': train.tree_receipt(control),
            }
        else:
            verifier.exact_inventory(control, controller['inventory'], excluded=('COMPLETED.json',))
            control_verification[label] = {'mode': 'original_control_inventory_verified'}
        init = cfg['initialization']
        for name in ('base', 'tokenizer', 'adapter'):
            if name not in init:
                continue
            ref = init[name]
            if ref['path'] not in input_trees:
                input_trees[ref['path']] = train.verify_ref(ref, tree=True)
            assert input_trees[ref['path']]['tree_sha256'] == ref['tree_sha256']
        checkpoints = []
        assert completed['milestones'] == [63, 126] and len(completed['all_checkpoints']) == 2
        for step, inventory in zip((63, 126), completed['all_checkpoints'], strict=True):
            checkpoint = output / 'checkpoints' / f'checkpoint-{step}'
            verifier.exact_inventory(checkpoint, inventory)
            seal_ref = train.file_receipt(checkpoint / 'COMPLETE.json')
            seal, state = (train.read_json(checkpoint / name) for name in ('COMPLETE.json', 'state.json'))
            assert seal['step'] == state['step'] == step
            assert seal['source_sha256'] == expected_sources and seal['config_sha256'] == config_sha
            assert seal['consumed_trainable_tokens'] == state['consumed_trainable_tokens']
            assert seal['consumed_trainable_tokens'] == steps[step - 1]['cumulative_trainable_tokens']
            assert seal['files'] == [f for f in inventory['files'] if f['path'] != 'COMPLETE.json']
            assert {'adapter_model.safetensors', 'adapter_config.json', 'training-state.pt', 'state.json', 'COMPLETE.json'} <= {f['path'] for f in inventory['files']}
            assert all(f['bytes'] > 0 for f in inventory['files'])
            checkpoints.append({'step': step, 'path': str(checkpoint), 'tree_sha256': inventory['tree_sha256'], 'checkpoint_seal': seal_ref})
        runs[label] = {
            'run_id': cfg['run_id'], 'configuration': cfg, 'config_ref': config_ref,
            'completion_ref': completion_ref, 'completion': completed,
            'control_completion_ref': control_ref, 'checkpoint_refs': checkpoints,
            'base': init['base'], 'tokenizer': init['tokenizer'],
        }
        control_candidate = {
            'profile': 'deepseek_native' if label == 'P4' else 'qwen_native',
            'chat_template_sha256': cfg['tokenization']['chat_template_sha256'],
            'base': copy.deepcopy(init['base']), 'tokenizer': copy.deepcopy(init['tokenizer']),
        }
        if 'adapter' in init:
            control_candidate['adapter'] = copy.deepcopy(init['adapter'])
            control_candidate['adapter']['parent_base_tree_sha256'] = init['base']['tree_sha256']
        controls['C' + label[1:]] = control_candidate
    result = {
        'schema_version': 1,
        'host': {
            'python': '/home/ubuntu/muta-finetune/.venv/bin/python',
            'release': str(CAMPAIGN / 'release/development12-v1'),
            'outputs': str(CAMPAIGN / 'evaluation/development12-v1'),
            'control': str(CAMPAIGN / 'controls/development12-v1'),
        },
        'controls': controls, 'runs': runs, 'input_trees': input_trees,
        'control_verification': control_verification,
        'remote_verification': {
            'all_run_inventories_verified': True, 'all_control_completions_verified': True,
            'all_input_trees_verified': True,
        },
        'collector': train.file_receipt(__file__),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
