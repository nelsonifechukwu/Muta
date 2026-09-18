#!/usr/bin/env python3
"""Train one provenance-complete Muta round-two BF16 LoRA candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import subprocess
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

from campaign_io import (
    CampaignInputError,
    inventory_tree,
    select_lowest_hash_indices,
    select_pilot_indices,
    sha256_file,
    verify_dataset_manifest,
)
from train_lora import common_prefix_length, message_content, normalize_token_ids

PRIVATE_SOURCES = frozenset({"waec_elearning", "cheetahwaec"})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--base-lineage", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--tokenizer-lineage", type=Path, required=True)
    parser.add_argument("--lineage", choices=("clean", "warm"), required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--validation-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--rank", type=int, choices=(8, 16, 32, 64), default=16)
    parser.add_argument("--lora-alpha", type=int)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=16)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--eval-steps", type=int, default=250)
    parser.add_argument("--save-steps", type=int)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--pilot-rows", type=int)
    parser.add_argument("--validation-rows", type=int)
    parser.add_argument(
        "--private-policy",
        choices=("include", "exclude"),
        default="include",
    )
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument("--dataloader-workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.max_length < 64:
        parser.error("--max-length must be at least 64")
    if args.pilot_rows is not None and args.pilot_rows < 1:
        parser.error("--pilot-rows must be positive")
    if args.validation_rows is not None and args.validation_rows < 1:
        parser.error("--validation-rows must be positive")
    if args.lora_alpha is None:
        args.lora_alpha = args.rank
    if args.save_steps is None:
        args.save_steps = args.eval_steps
    return args


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_receipt(repo: Path) -> dict[str, Any]:
    def git(*parts: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *parts],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    try:
        sha = git("rev-parse", "HEAD")
        status = git("status", "--porcelain=v1")
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", "--binary", "HEAD"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"available": False}
    return {
        "available": True,
        "commit": sha,
        "dirty": bool(status),
        "status": status.splitlines(),
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


def _package_versions() -> dict[str, str]:
    names = (
        "accelerate",
        "bitsandbytes",
        "datasets",
        "huggingface-hub",
        "matplotlib",
        "numpy",
        "peft",
        "safetensors",
        "torch",
        "transformers",
        "triton",
        "trl",
        "unsloth",
        "xformers",
    )
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _verify_lineage(path: Path, *, expected_lineage: str, model_path: Path) -> dict:
    lineage = json.loads(path.read_text(encoding="utf-8"))
    if lineage.get("lineage") != expected_lineage:
        raise CampaignInputError(
            f"lineage receipt says {lineage.get('lineage')!r}, expected {expected_lineage!r}"
        )
    expected_tree = lineage.get("training_base", {}).get("tree_sha256")
    if not expected_tree:
        raise CampaignInputError("lineage receipt has no training-base tree digest")
    observed = inventory_tree(model_path)
    if observed["tree_sha256"] != expected_tree:
        raise CampaignInputError("training-base tree digest does not match lineage receipt")
    return {"receipt": lineage, "receipt_sha256": sha256_file(path), "observed": observed}


def _verify_tokenizer(path: Path, *, lineage_path: Path) -> dict[str, Any]:
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    if lineage.get("lineage") != "clean":
        raise CampaignInputError("tokenizer lineage must be the clean upstream receipt")
    expected = {
        row["path"]: row
        for row in lineage["training_base"]["files"]
        if row["path"] in {"tokenizer.json", "tokenizer_config.json"}
    }
    if set(expected) != {"tokenizer.json", "tokenizer_config.json"}:
        raise CampaignInputError("clean lineage is missing tokenizer receipts")
    observed = {}
    for name, receipt in expected.items():
        target = path / name
        if not target.is_file() or sha256_file(target) != receipt["sha256"]:
            raise CampaignInputError(f"tokenizer receipt mismatch: {name}")
        observed[name] = {
            "path": str(target.resolve()),
            "bytes": target.stat().st_size,
            "sha256": receipt["sha256"],
        }
    return {
        "lineage_receipt_sha256": sha256_file(lineage_path),
        "files": observed,
    }


def _row_source(row: dict) -> str:
    if row.get("source_id"):
        return str(row["source_id"])
    provenance = row.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("source_id"):
        raise CampaignInputError(f"row {row.get('id')} has no provenance.source_id")
    return str(provenance["source_id"])


def projected_jsonl_rows(paths: list[str]):
    """Project heterogeneous records into one stable training schema."""
    for raw_path in paths:
        path = Path(raw_path)
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    yield {
                        "id": str(row["id"]),
                        "prompt": str(row["prompt"]),
                        "completion": str(row["completion"]),
                        "mode": str(row["mode"]),
                        "source_id": _row_source(row),
                    }
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise CampaignInputError(
                        f"invalid projected training row at {path}:{line_number}"
                    ) from exc


def _write_metrics(output: Path, log_history: list[dict[str, Any]]) -> None:
    metrics = output / "metrics.jsonl"
    with metrics.open("w", encoding="utf-8") as handle:
        for row in log_history:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    fields = sorted({key for row in log_history for key in row})
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(log_history)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    train = [(row.get("step"), row["loss"]) for row in log_history if "loss" in row]
    evaluation = [(row.get("step"), row["eval_loss"]) for row in log_history if "eval_loss" in row]
    if not train and not evaluation:
        raise RuntimeError("Trainer history contains no loss values")
    figure, axis = plt.subplots(figsize=(8, 5))
    if train:
        axis.plot(*zip(*train, strict=True), label="train", linewidth=1.5)
    if evaluation:
        axis.plot(*zip(*evaluation, strict=True), label="validation", marker="o")
    axis.set(xlabel="optimizer step", ylabel="loss", title="Muta fine-tuning loss")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "loss-curve.png", dpi=180)
    figure.savefig(output / "loss-curve.svg")
    plt.close(figure)


def _id_digest(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


def tokenize_chat_row(row, *, tokenizer, max_length: int) -> dict[str, list[int] | int]:
    """Apply the model template and mask every non-assistant token."""
    if row.get("mode") != "chat":
        raise CampaignInputError(f"row {row.get('id')} is not chat mode")
    multimodal_chat = hasattr(tokenizer, "image_processor")
    prompt_messages = [
        {
            "role": "user",
            "content": message_content(row["prompt"], multimodal=multimodal_chat),
        }
    ]
    full_messages = prompt_messages + [
        {
            "role": "assistant",
            "content": message_content(row["completion"], multimodal=multimodal_chat),
        }
    ]
    prompt_ids = normalize_token_ids(
        tokenizer.apply_chat_template(prompt_messages, tokenize=True, add_generation_prompt=True)
    )
    full_ids = normalize_token_ids(
        tokenizer.apply_chat_template(full_messages, tokenize=True, add_generation_prompt=False)
    )
    start = common_prefix_length(prompt_ids, full_ids)
    if start >= len(full_ids):
        raise CampaignInputError(f"completion produced no trainable tokens for row {row.get('id')}")
    if len(full_ids) > max_length:
        raise CampaignInputError(f"row {row.get('id')} tokenizes to {len(full_ids)} > {max_length}")
    return {
        "input_ids": full_ids,
        "attention_mask": [1] * len(full_ids),
        "labels": [-100] * start + full_ids[start:],
        "sequence_length": len(full_ids),
        "assistant_tokens": len(full_ids) - start,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "COMPLETED.json").exists():
        raise FileExistsError(f"completed run already exists: {output}")

    script_dir = Path(__file__).resolve().parent
    repo = script_dir.parents[1]
    dataset = verify_dataset_manifest(args.dataset_manifest)
    validation = verify_dataset_manifest(args.validation_manifest)
    lineage = _verify_lineage(
        args.base_lineage,
        expected_lineage=args.lineage,
        model_path=args.model,
    )
    tokenizer_receipt = _verify_tokenizer(args.tokenizer, lineage_path=args.tokenizer_lineage)
    resolved = {
        key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
    }
    resolved.update(
        {
            "dataset": dataset.receipt(),
            "validation": validation.receipt(),
            "lineage_receipt_sha256": lineage["receipt_sha256"],
            "tokenizer": tokenizer_receipt,
            "script_sha256": sha256_file(Path(__file__)),
            "campaign_io_sha256": sha256_file(script_dir / "campaign_io.py"),
            "git": _git_receipt(repo),
            "packages": _package_versions(),
        }
    )
    _json_write(output / "resolved-config.json", resolved)
    _json_write(
        output / "RUNNING.json",
        {"run_name": args.run_name, "started_unix": time.time()},
    )

    random.seed(args.seed)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from unsloth import FastLanguageModel  # noqa: I001
    import torch
    from datasets import Dataset, DatasetDict, Features, Value
    from transformers import AutoTokenizer, DataCollatorForSeq2Seq, Trainer, TrainingArguments

    torch.manual_seed(args.seed)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.model),
        max_seq_length=args.max_length,
        load_in_4bit=False,
        load_in_16bit=True,
        full_finetuning=False,
        use_exact_model_name=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.tokenizer),
        use_fast=True,
        fix_mistral_regex=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rank,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        max_seq_length=args.max_length,
    )
    features = Features(
        {
            "id": Value("string"),
            "prompt": Value("string"),
            "completion": Value("string"),
            "mode": Value("string"),
            "source_id": Value("string"),
        }
    )
    train = Dataset.from_generator(
        projected_jsonl_rows,
        gen_kwargs={"paths": [str(path) for path in dataset.shard_paths]},
        features=features,
    )
    validation_rows = Dataset.from_generator(
        projected_jsonl_rows,
        gen_kwargs={"paths": [str(path) for path in validation.shard_paths]},
        features=features,
    )
    if len(train) != dataset.row_count:
        raise CampaignInputError(
            f"loaded {len(train)} rows from a {dataset.row_count}-row artifact"
        )

    source_counts_before = Counter(_row_source(row) for row in train)
    if args.private_policy == "exclude":
        train = train.filter(
            lambda row: row["source_id"] not in PRIVATE_SOURCES,
            desc="excluding private-use exam rows",
        )
    source_counts = Counter(_row_source(row) for row in train)
    if args.private_policy == "exclude" and PRIVATE_SOURCES & source_counts.keys():
        raise CampaignInputError("private-source exclusion failed")
    if args.pilot_rows:
        indices = select_pilot_indices(train["id"], rows=args.pilot_rows, seed=args.seed)
        train = train.select(indices)
    if args.validation_rows:
        indices = select_lowest_hash_indices(
            validation_rows["id"],
            rows=args.validation_rows,
            seed=args.seed,
            namespace="validation-subset",
        )
        validation_rows = validation_rows.select(indices)
    train = train.shuffle(seed=args.seed)
    validation_rows = validation_rows.shuffle(seed=args.seed)
    training_source_counts = Counter(train["source_id"])
    raw = DatasetDict(train=train, validation=validation_rows)

    text_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)

    def tokenize(row):
        return tokenize_chat_row(row, tokenizer=tokenizer, max_length=args.max_length)

    tokenized = raw.map(
        tokenize,
        remove_columns=raw["train"].column_names,
        desc="tokenizing completion-masked chat examples",
    )
    if not tokenized["train"] or not tokenized["validation"]:
        raise CampaignInputError("tokenization removed an entire split")
    if min(tokenized["train"]["assistant_tokens"]) < 1:
        raise CampaignInputError("a training row has no assistant tokens")

    length_receipt = {
        split: {
            "rows": len(tokenized[split]),
            "sequence_tokens": sum(tokenized[split]["sequence_length"]),
            "assistant_tokens": sum(tokenized[split]["assistant_tokens"]),
            "max_sequence_tokens": max(tokenized[split]["sequence_length"]),
        }
        for split in ("train", "validation")
    }
    tokenized = tokenized.remove_columns(["sequence_length", "assistant_tokens"])

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    steps_per_epoch = math.ceil(
        len(tokenized["train"]) / (args.batch_size * args.gradient_accumulation * world_size)
    )
    planned_steps = (
        args.max_steps if args.max_steps > 0 else math.ceil(steps_per_epoch * args.epochs)
    )
    warmup_steps = math.ceil(planned_steps * args.warmup_ratio)

    training_args = TrainingArguments(
        output_dir=str(output / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        warmup_steps=warmup_steps,
        weight_decay=args.weight_decay,
        lr_scheduler_type="cosine",
        bf16=True,
        fp16=False,
        logging_steps=args.logging_steps,
        logging_first_step=True,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        optim="adamw_8bit",
        seed=args.seed,
        data_seed=args.seed,
        report_to="none",
        prediction_loss_only=True,
        remove_unused_columns=False,
        dataloader_num_workers=args.dataloader_workers,
    )
    collator = DataCollatorForSeq2Seq(
        tokenizer=text_tokenizer,
        padding=True,
        label_pad_token_id=-100,
        return_tensors="pt",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        data_collator=collator,
    )
    started = time.time()
    result = trainer.train(
        resume_from_checkpoint=(
            str(args.resume_from_checkpoint) if args.resume_from_checkpoint else None
        )
    )
    evaluation = trainer.evaluate()
    trainer.save_state()

    adapter_dir = output / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    _write_metrics(output, trainer.state.log_history)

    training_manifest = {
        "schema_version": 2,
        "run_name": args.run_name,
        "lineage": args.lineage,
        "base_lineage": lineage,
        "tokenizer": tokenizer_receipt,
        "seed": args.seed,
        "max_length": args.max_length,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "rank": args.rank,
        "lora_alpha": args.lora_alpha,
        "training_method": "lora_bf16",
        "completion_only_loss": True,
        "target_modules": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        "dataset": dataset.receipt(),
        "private_policy": args.private_policy,
        "source_counts_before_policy": dict(sorted(source_counts_before.items())),
        "source_counts_after_policy": dict(sorted(source_counts.items())),
        "training_source_counts": dict(sorted(training_source_counts.items())),
        "pilot_rows": args.pilot_rows,
        "validation_rows": args.validation_rows,
        "train_ordered_id_sha256": _id_digest(train["id"]),
        "validation_ordered_id_sha256": _id_digest(validation_rows["id"]),
        "validation": {
            **validation.receipt(),
        },
        "tokenization": length_receipt,
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "global_batch_per_gpu": args.batch_size * args.gradient_accumulation,
        "max_steps": args.max_steps,
        "planned_steps": planned_steps,
        "warmup_steps": warmup_steps,
        "train_metrics": result.metrics,
        "validation_metrics": evaluation,
        "trainer_global_step": trainer.state.global_step,
        "trainer_epoch": trainer.state.epoch,
        "elapsed_seconds": round(time.time() - started, 3),
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
            "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
            "packages": _package_versions(),
        },
        "git": _git_receipt(repo),
        "scripts": {
            "train_lora_round2.py": sha256_file(Path(__file__)),
            "campaign_io.py": sha256_file(script_dir / "campaign_io.py"),
            "train_lora.py": sha256_file(script_dir / "train_lora.py"),
        },
        "adapter": inventory_tree(adapter_dir),
        "metrics": {
            name: {
                "bytes": (output / name).stat().st_size,
                "sha256": sha256_file(output / name),
            }
            for name in (
                "metrics.jsonl",
                "metrics.csv",
                "loss-curve.png",
                "loss-curve.svg",
            )
        },
    }
    _json_write(output / "training-manifest.json", training_manifest)
    completed = {
        "run_name": args.run_name,
        "completed_unix": time.time(),
        "training_manifest_sha256": sha256_file(output / "training-manifest.json"),
    }
    _json_write(output / "COMPLETED.json", completed)
    (output / "RUNNING.json").unlink(missing_ok=True)
    return training_manifest


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        manifest = run(args)
    except BaseException as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        _json_write(
            args.output / "FAILED.json",
            {
                "run_name": args.run_name,
                "failed_unix": time.time(),
                "exception": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        raise
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
