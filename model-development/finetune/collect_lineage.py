#!/usr/bin/env python3
"""Create an immutable lineage receipt for a clean or warm Muta training base."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

from campaign_io import CampaignInputError, inventory_tree, sha256_file

UPSTREAM_ID = "Qwen/Qwen2.5-1.5B-Instruct"
UPSTREAM_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
UPSTREAM_WEIGHT_SHA256 = "dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee"
INCUMBENT_GGUF_SHA256 = "a750d00d458c6ab38925364ea1413db00648449180941e47025736d09922e1eb"


def _file_receipt(path: Path) -> dict:
    path = path.resolve()
    if not path.is_file():
        raise CampaignInputError(f"missing lineage file: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def collect(
    *,
    lineage: str,
    training_base: Path,
    output: Path,
    incumbent_adapter: Path | None = None,
    incumbent_gguf: Path | None = None,
    incumbent_training_manifest: Path | None = None,
) -> dict:
    if lineage not in {"clean", "warm"}:
        raise CampaignInputError(f"unsupported lineage: {lineage}")
    base = inventory_tree(training_base)
    model_files = [row for row in base["files"] if row["path"] == "model.safetensors"]
    if len(model_files) != 1:
        raise CampaignInputError("training base must contain one root model.safetensors")
    receipt = {
        "schema_version": 1,
        "lineage": lineage,
        "created_unix": time.time(),
        "host": platform.node(),
        "upstream": {
            "model": UPSTREAM_ID,
            "revision": UPSTREAM_REVISION,
            "license": "Apache-2.0",
            "model_safetensors_sha256": UPSTREAM_WEIGHT_SHA256,
        },
        "training_base": base,
        "collector": _file_receipt(Path(__file__)),
    }
    if lineage == "clean":
        if model_files[0]["sha256"] != UPSTREAM_WEIGHT_SHA256:
            raise CampaignInputError("clean base weight hash is not the pinned upstream weight")
        if any((incumbent_adapter, incumbent_gguf, incumbent_training_manifest)):
            raise CampaignInputError("clean lineage cannot contain incumbent artifacts")
    else:
        if not all((incumbent_adapter, incumbent_gguf, incumbent_training_manifest)):
            raise CampaignInputError("warm lineage requires every incumbent artifact")
        gguf = _file_receipt(incumbent_gguf)
        if gguf["sha256"] != INCUMBENT_GGUF_SHA256:
            raise CampaignInputError("incumbent GGUF hash does not match the published Muta")
        receipt["prior_stage"] = {
            "description": "BF16 LoRA r16, 500 steps, licence-clean ARC/QASC MCQ mixture",
            "adapter": inventory_tree(incumbent_adapter),
            "training_manifest": _file_receipt(incumbent_training_manifest),
            "published_gguf": gguf,
            "published_huggingface_commit": "a27fa778dd40cf89fc9d66b18cd767e34892ec3a",
            "already_merged_into_training_base": True,
        }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"lineage receipt already exists: {output}")
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lineage", choices=("clean", "warm"), required=True)
    parser.add_argument("--training-base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--incumbent-adapter", type=Path)
    parser.add_argument("--incumbent-gguf", type=Path)
    parser.add_argument("--incumbent-training-manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(collect(**vars(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
