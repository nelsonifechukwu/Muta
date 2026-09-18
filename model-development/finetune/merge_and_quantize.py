#!/usr/bin/env python3
"""Merge a Muta LoRA and export a provenance-bound Q4_K_M GGUF."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from campaign_io import CampaignInputError, inventory_tree, sha256_file


def _file_receipt(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise CampaignInputError(f"missing export input: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def verify_inputs(
    *, base: Path, base_lineage: Path, adapter: Path, training_manifest: Path
) -> dict[str, Any]:
    lineage = json.loads(base_lineage.read_text(encoding="utf-8"))
    observed_base = inventory_tree(base)
    if observed_base["tree_sha256"] != lineage["training_base"]["tree_sha256"]:
        raise CampaignInputError("merge base does not match its lineage receipt")
    training = json.loads(training_manifest.read_text(encoding="utf-8"))
    observed_adapter = inventory_tree(adapter)
    if observed_adapter["tree_sha256"] != training["adapter"]["tree_sha256"]:
        raise CampaignInputError("adapter does not match its training manifest")
    return {
        "base_lineage": _file_receipt(base_lineage),
        "base": observed_base,
        "adapter": observed_adapter,
        "training_manifest": _file_receipt(training_manifest),
    }


def export_commands(
    *, llama_cpp: Path, merged: Path, f16_gguf: Path, final_gguf: Path
) -> list[list[str]]:
    converter = llama_cpp / "convert_hf_to_gguf.py"
    quantizer = llama_cpp / "build/bin/llama-quantize"
    if not converter.is_file() or not quantizer.is_file():
        raise CampaignInputError("pinned llama.cpp converter or quantizer is missing")
    return [
        [
            sys.executable,
            str(converter),
            str(merged),
            "--outfile",
            str(f16_gguf),
            "--outtype",
            "f16",
        ],
        [str(quantizer), str(f16_gguf), str(final_gguf), "Q4_K_M"],
    ]


def _run_logged(command: list[str], log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log:
        log.write("COMMAND " + json.dumps(command) + "\n")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def _git_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--base-lineage", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--training-manifest", type=Path, required=True)
    parser.add_argument("--llama-cpp", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--keep-f16", action="store_true")
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "quantization-manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"completed export already exists: {manifest_path}")
    inputs = verify_inputs(
        base=args.base,
        base_lineage=args.base_lineage,
        adapter=args.adapter,
        training_manifest=args.training_manifest,
    )
    converter = args.llama_cpp / "convert_hf_to_gguf.py"
    quantizer = args.llama_cpp / "build/bin/llama-quantize"
    llama_receipt = {
        "root": str(args.llama_cpp.resolve()),
        "git_commit": _git_sha(args.llama_cpp),
        "converter": _file_receipt(converter),
        "quantizer": _file_receipt(quantizer),
    }

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    started = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        str(args.base),
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False)
    merged_model = model.merge_and_unload(safe_merge=True)
    merged = output / "merged-bf16"
    merged_model.save_pretrained(
        merged,
        safe_serialization=True,
        max_shard_size="5GB",
    )
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.tokenizer), use_fast=True, fix_mistral_regex=True
    )
    tokenizer.save_pretrained(merged)
    merged_inventory = inventory_tree(merged)

    f16_gguf = output / f"{args.model_name}-F16.gguf"
    final_gguf = output / f"{args.model_name}-Q4_K_M.gguf"
    commands = export_commands(
        llama_cpp=args.llama_cpp,
        merged=merged,
        f16_gguf=f16_gguf,
        final_gguf=final_gguf,
    )
    log_path = output / "merge-and-quantize.log"
    for command in commands:
        _run_logged(command, log_path)
    f16_receipt = _file_receipt(f16_gguf)
    final_receipt = _file_receipt(final_gguf)
    if not args.keep_f16:
        f16_gguf.unlink()

    manifest = {
        "schema_version": 1,
        "model_name": args.model_name,
        "quantization": "Q4_K_M",
        "inputs": inputs,
        "merged": merged_inventory,
        "f16_gguf": {**f16_receipt, "retained": args.keep_f16},
        "final_gguf": final_receipt,
        "llama_cpp": llama_receipt,
        "commands": commands,
        "log": _file_receipt(log_path),
        "host": platform.node(),
        "elapsed_seconds": round(time.time() - started, 3),
        "script": _file_receipt(Path(__file__)),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
