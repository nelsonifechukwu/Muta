"""Convert the pinned untouched DeepSeek checkpoint to a local-use Q4_K_M GGUF."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path('/lambda/nfs/awf-tmp/muta/campaign-20260918/science-tutor-20260919')
BASE = ROOT / 'bases/deepseek-r1-distill-qwen-1.5b'
OUTPUT = ROOT / 'exports/deepseek-untouched-q4km-v1'
LLAMA = Path('/home/ubuntu/llama.cpp-b10175')
PYTHON = '/home/ubuntu/muta-finetune/.venv/bin/python'
TREE_SHA = '6e7d20161a524c07c6affa8e89badc7dd23aab11d2fa4ab48fcdcb7e81666133'
REVISION = 'ad9f0ae0864d7fbcd1cd905e3c6c5b069cc8b562'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def receipt(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'not a regular input: {path}')
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def write_new(name, obj):
    with (OUTPUT / name).open('x') as handle:
        json.dump(obj, handle, indent=2, sort_keys=True)
        handle.write('\n')


def verify_base():
    acquisition = json.loads((ROOT / 'configs/deepseek-acquisition-v1.json').read_text())
    if acquisition['status'] != 'complete' or acquisition['revision'] != REVISION or acquisition['tree_sha256'] != TREE_SHA:
        raise ValueError('wrong official acquisition identity')
    expected = {entry['path']: entry for entry in acquisition['files']}
    if {p.name for p in BASE.iterdir()} != set(expected):
        raise ValueError('base has unexpected files')
    for name, entry in expected.items():
        observed = receipt(BASE / name)
        if any(observed[key] != entry[key] for key in ('sha256', 'bytes')):
            raise ValueError(f'official input mismatch: {name}')
    return acquisition


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        acquisition = verify_base()
        converter = LLAMA / 'convert_hf_to_gguf.py'
        quantizer = LLAMA / 'build/bin/llama-quantize'
        intermediate = OUTPUT / 'DeepSeek-R1-Distill-Qwen-1.5B-BF16.gguf'
        final = OUTPUT / 'DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf'
        commands = [
            [PYTHON, str(converter), str(BASE), '--outfile', str(intermediate), '--outtype', 'bf16'],
            [str(quantizer), str(intermediate), str(final), 'Q4_K_M', '8'],
        ]
        sources = [receipt(Path(__file__)), receipt(converter), receipt(quantizer)]
        request = {'revision': REVISION, 'base_tree_sha256': TREE_SHA, 'adapter_applied': False,
                   'sources': sources, 'commands': commands, 'started_unix': time.time(),
                   'llama_cpp_commit': subprocess.check_output(['git', '-C', str(LLAMA), 'rev-parse', 'HEAD'], text=True).strip(),
                   'cuda_visible_devices': '', 'automatic_retry': False}
        if request['llama_cpp_commit'] != '60bccc3763395e01b039aa1ddeacc8cc0ea69f70':
            raise ValueError('unexpected llama.cpp revision')
        write_new('REQUEST.json', request)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='8', PYTHONDONTWRITEBYTECODE='1')
        for index, command in enumerate(commands):
            with (OUTPUT / f'step-{index + 1}.log').open('xb') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, check=True)
        verify_base()
        if [receipt(Path(record['path'])) for record in sources] != sources:
            raise ValueError('executed source changed')
        sys.path.insert(0, str(LLAMA / 'gguf-py'))
        import gguf
        reader = gguf.GGUFReader(str(final))
        metadata = {}
        for name in ('general.architecture', 'general.file_type', 'general.name', 'tokenizer.ggml.bos_token_id', 'tokenizer.ggml.eos_token_id', 'tokenizer.chat_template'):
            field = reader.fields.get(name)
            if field is not None:
                value = field.contents()
                metadata[name] = value.item() if hasattr(value, 'item') else value
        template = json.loads((BASE / 'tokenizer_config.json').read_text())['chat_template']
        expected = {'general.architecture': 'qwen2', 'general.file_type': 15,
                    'tokenizer.ggml.bos_token_id': 151646, 'tokenizer.ggml.eos_token_id': 151643,
                    'tokenizer.chat_template': template}
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError('GGUF architecture/quantization/native tokenizer metadata mismatch')
        del reader
        write_new('COMPLETED.json', {'status': 'complete', 'request': receipt(OUTPUT / 'REQUEST.json'),
                  'acquisition_revision': acquisition['revision'], 'adapter_applied': False,
                  'intermediate': receipt(intermediate), 'gguf': receipt(final), 'metadata': metadata,
                  'ended_unix': time.time()})
        print(json.dumps({'status': 'complete', 'gguf': receipt(final)}), flush=True)
    except BaseException as exc:
        write_new('FAILED.json', {'error': str(exc), 'traceback': traceback.format_exc(), 'automatic_retry': False})
        raise


if __name__ == '__main__':
    main()
