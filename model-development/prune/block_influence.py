#!/usr/bin/env python3
"""Rank decoder layers by Block Influence and n-block angular distance.

Hooks capture each layer's residual-stream input and output directly, so the last layer is
measured before the final RMSNorm (HF's `output_hidden_states` would return it post-norm).

Usage (CPU, ~20 min on an M2 Pro for 132 × 512 tokens):
  block_influence.py --model Qwen/Qwen2.5-1.5B-Instruct \
      --revision 989aa7980e4cf806f80c7fef2b1adb7bc71aa306 \
      --calibration calibration.jsonl --blocks 4,7,9,11 \
      --protect-first 2 --protect-last 1 --dtype float32 --device cpu \
      --output ../../bench/measurements/prune-20260917/bi-qwen25-1.5b-instruct-base.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layer_selection


def new_stats(n_layers: int, blocks: list[int]) -> dict:
    return {
        "n_layers": n_layers,
        "tokens": 0,
        "cos_sum": [0.0] * n_layers,
        "ang_sum": {n: {start: 0.0 for start in range(n_layers - n + 1)} for n in blocks},
    }


def accumulate(stats: dict, ins: list[np.ndarray], outs: list[np.ndarray], blocks: list[int]) -> None:
    """Add one sequence's (tokens, hidden) layer inputs/outputs to the running sums."""
    n_layers = stats["n_layers"]
    assert len(ins) == len(outs) == n_layers
    tokens = ins[0].shape[0]
    stats["tokens"] += tokens
    for i in range(n_layers):
        stats["cos_sum"][i] += float(layer_selection.cosine_rows(ins[i], outs[i]).sum())
    stream = list(ins) + [outs[-1]]  # x^(0) … x^(L); x^(L) is the last layer's output
    for n in blocks:
        for start in range(n_layers - n + 1):
            c = np.clip(layer_selection.cosine_rows(stream[start], stream[start + n]), -1.0, 1.0)
            stats["ang_sum"][n][start] += float((np.arccos(c) / math.pi).sum())


def finalize(stats: dict, blocks: list[int], protect_first: int, protect_last: int) -> dict:
    tokens = stats["tokens"]
    bi = [1.0 - s / tokens for s in stats["cos_sum"]]
    block_distance = {
        str(n): {str(start): stats["ang_sum"][n][start] / tokens for start in stats["ang_sum"][n]}
        for n in blocks
    }
    selections = {"contiguous": {}, "lowest_bi": {}}
    for n in blocks:
        dist = {int(k): v for k, v in block_distance[str(n)].items()}
        selections["contiguous"][str(n)] = layer_selection.select_contiguous(
            dist, n, stats["n_layers"], protect_first, protect_last
        )
        selections["lowest_bi"][str(n)] = layer_selection.select_lowest_bi(
            bi, n, protect_first, protect_last
        )
    return {
        "n_layers": stats["n_layers"],
        "tokens": tokens,
        "bi": bi,
        "block_distance": block_distance,
        "selections": selections,
        "protect": {"first": protect_first, "last": protect_last},
    }


def collect_layer_io(model, input_ids):
    """Run one sequence and return per-layer (input, output) residual streams as numpy."""
    import torch

    ins: dict[int, np.ndarray] = {}
    outs: dict[int, np.ndarray] = {}
    hooks = []
    for i, layer in enumerate(model.model.layers):

        def pre(_module, args, kwargs, i=i):
            hidden = args[0] if args else kwargs["hidden_states"]
            ins[i] = hidden.detach()[0].float().cpu().numpy()

        def post(_module, _args, _kwargs, output, i=i):
            hidden = output[0] if isinstance(output, tuple) else output
            outs[i] = hidden.detach()[0].float().cpu().numpy()

        hooks.append(layer.register_forward_pre_hook(pre, with_kwargs=True))
        hooks.append(layer.register_forward_hook(post, with_kwargs=True))
    with torch.no_grad():
        model(input_ids=input_ids, use_cache=False)
    for hook in hooks:
        hook.remove()
    n = len(model.model.layers)
    return [ins[i] for i in range(n)], [outs[i] for i in range(n)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="HF id or local checkpoint directory")
    parser.add_argument("--revision", default=None)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--blocks", default="4,7,9,11")
    parser.add_argument("--protect-first", type=int, default=2)
    parser.add_argument("--protect-last", type=int, default=1)
    parser.add_argument("--dtype", choices=("float32", "bfloat16"), default="float32")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    blocks = [int(b) for b in args.blocks.split(",")]
    dtype = torch.float32 if args.dtype == "float32" else torch.bfloat16
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, revision=args.revision, dtype=dtype  # transformers 5.x name (was torch_dtype)
    ).to(args.device).eval()
    n_layers = len(model.model.layers)
    stats = new_stats(n_layers, blocks)
    rows = [json.loads(l) for l in args.calibration.read_text(encoding="utf-8").splitlines() if l]
    for index, row in enumerate(rows):
        ids = tokenizer(row["text"], return_tensors="pt", truncation=True, max_length=args.max_tokens)
        ins, outs = collect_layer_io(model, ids["input_ids"].to(args.device))
        accumulate(stats, ins, outs, blocks)
        if index % 10 == 0:
            print(f"{index + 1}/{len(rows)} sequences, {stats['tokens']} tokens", flush=True)
    result = finalize(stats, blocks, args.protect_first, args.protect_last)
    result.update(
        {
            "model": args.model,
            "revision": args.revision,
            "dtype": args.dtype,
            "max_tokens": args.max_tokens,
            "calibration": {
                "path": str(args.calibration),
                "sha256": hashlib.sha256(args.calibration.read_bytes()).hexdigest(),
                "rows": len(rows),
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("bi", "selections")}, indent=2))


if __name__ == "__main__":
    main()
