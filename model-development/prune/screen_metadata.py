#!/usr/bin/env python3
"""Write a profiler-valid submission directory for one candidate GGUF.

The profiler's fraud check requires `parameters_estimate` within ±15 % of the tensor-table
count, so a pruned file must not inherit the 28-layer claim.

Usage: screen_metadata.py --base <round1 metadata.json> --gguf candidates/x.gguf \
           --manifest candidates/x.prune-manifest.json --out subs/x
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def parameter_estimate_label(params: int) -> str:
    if params >= 1_000_000_000:
        return f"{params / 1e9:.2f}B"
    return f"{round(params / 1e6)}M"


def build_metadata(base: dict, model_file: str, params: int, quantization: str) -> dict:
    meta = {k: v for k, v in base.items() if k not in ("model", "_runtime")}
    meta["model"] = {
        "name": model_file,
        "runtime": base["model"]["runtime"],
        "quantization": quantization,
        "parameters_estimate": parameter_estimate_label(params),
        "packaging": base["model"]["packaging"],
    }
    meta["_runtime"] = {"model_path": f"model/{model_file}"}
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="*.prune-manifest.json or export manifest with params_count",
    )
    parser.add_argument("--quantization", default="GGUF Q4_K_M")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--link", action="store_true", help="hard-link the GGUF instead of copying")
    args = parser.parse_args()
    base = json.loads(args.base.read_text(encoding="utf-8"))
    params = int(json.loads(args.manifest.read_text(encoding="utf-8"))["params_count"])
    (args.out / "model").mkdir(parents=True, exist_ok=True)
    target = args.out / "model" / args.gguf.name
    if not target.exists():
        if args.link:
            target.hardlink_to(args.gguf)
        else:
            shutil.copy2(args.gguf, target)
    meta = build_metadata(base, args.gguf.name, params, args.quantization)
    text = json.dumps(meta, indent=2, ensure_ascii=False) + "\n"
    (args.out / "metadata.json").write_text(text, encoding="utf-8")
    print(json.dumps(meta["model"], indent=2))


if __name__ == "__main__":
    main()
