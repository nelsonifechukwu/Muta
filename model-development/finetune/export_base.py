#!/usr/bin/env python3
"""Export an untouched pinned base through the same GGUF path as the fine-tunes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gguf-method", choices=("q4_0", "q4_k_m"), required=True)
    parser.add_argument("--max-length", type=int, default=1024)
    args = parser.parse_args()

    from unsloth import FastLanguageModel

    args.output.mkdir(parents=True, exist_ok=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        revision=args.revision,
        max_seq_length=args.max_length,
        load_in_4bit=False,
        load_in_16bit=True,
        full_finetuning=False,
        use_exact_model_name=True,
    )
    model.save_pretrained_gguf(
        str(args.output),
        tokenizer,
        quantization_method=args.gguf_method,
    )
    candidates = sorted(args.output.parent.glob(f"{args.output.name}_gguf/*.gguf"))
    if len(candidates) != 1:
        raise RuntimeError(f"expected one exported GGUF, found {candidates}")
    gguf = candidates[0]
    manifest = {
        "schema_version": 1,
        "model": args.model,
        "revision": args.revision,
        "gguf_method": args.gguf_method,
        "max_length": args.max_length,
        "artifact": {
            "path": str(gguf),
            "bytes": gguf.stat().st_size,
            "sha256": sha256_file(gguf),
        },
    }
    (args.output.parent / f"{args.output.name}-export-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
