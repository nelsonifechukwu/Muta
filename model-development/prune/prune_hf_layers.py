#!/usr/bin/env python3
"""Delete decoder layers from a Qwen2 HF checkpoint and save a loadable, shallower model.

Usage: prune_hf_layers.py --source runs-prune/tutor-28L/merged_16bit --drop 8,9,10,11,12,13,14 \
           --output runs-prune/pruned-21L-contiguous \
           --bi ../../bench/measurements/prune-20260917/bi-tutor-28L-merged.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layer_selection = _load("layer_selection")


def prune_model(model, drop: list[int]) -> list[int]:
    """Remove `drop` from model.model.layers in place; renumber layer_idx; fix config."""
    from torch import nn

    layers = model.model.layers
    kept = layer_selection.kept_layer_indices(len(layers), drop)
    model.model.layers = nn.ModuleList([layers[i] for i in kept])
    for new_index, layer in enumerate(model.model.layers):
        if hasattr(layer, "self_attn") and hasattr(layer.self_attn, "layer_idx"):
            layer.self_attn.layer_idx = new_index
    model.config.num_hidden_layers = len(kept)
    if getattr(model.config, "max_window_layers", None) is not None:
        model.config.max_window_layers = min(model.config.max_window_layers, len(kept))
    if getattr(model.config, "layer_types", None):
        model.config.layer_types = [model.config.layer_types[i] for i in kept]
    return kept


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--drop", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--bi", type=Path, default=None, help="BI json used to choose --drop (provenance)"
    )
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    drop = sorted({int(x) for x in args.drop.split(",")})
    model = AutoModelForCausalLM.from_pretrained(args.source, dtype=torch.bfloat16)
    tokenizer = AutoTokenizer.from_pretrained(args.source)
    kept = prune_model(model, drop)
    args.output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output, safe_serialization=True)
    tokenizer.save_pretrained(args.output)
    manifest = {
        "schema_version": 1,
        "source": str(args.source),
        "drop": drop,
        "kept_layers": kept,
        "num_hidden_layers": len(kept),
        "params_count": int(sum(p.numel() for p in model.parameters())),
        "bi_json": str(args.bi) if args.bi else None,
        "bi_sha256": hashlib.sha256(args.bi.read_bytes()).hexdigest() if args.bi else None,
    }
    (args.output / "prune-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
