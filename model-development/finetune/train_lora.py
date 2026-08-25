#!/usr/bin/env python3
"""Train a completion-masked BF16 LoRA and optionally export a GGUF."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import time
from collections.abc import Mapping
from pathlib import Path


def common_prefix_length(left: list[int], right: list[int]) -> int:
    length = 0
    while length < min(len(left), len(right)) and left[length] == right[length]:
        length += 1
    return length


def message_content(text: str, *, multimodal: bool):
    """Return the content shape expected by text-only or multimodal processors."""
    if multimodal:
        return [{"type": "text", "text": text}]
    return text


def normalize_token_ids(value) -> list[int]:
    """Normalize tokenizer/processor output to one unbatched token-id list."""
    if isinstance(value, Mapping):
        value = value["input_ids"]
    if value and isinstance(value[0], list):
        if len(value) != 1:
            raise ValueError("expected one tokenized example")
        value = value[0]
    return list(value)


def architecture_peft_kwargs(*, multimodal: bool) -> dict[str, bool]:
    if not multimodal:
        return {}
    return {
        "finetune_vision_layers": False,
        "finetune_language_layers": True,
        "finetune_attention_modules": True,
        "finetune_mlp_modules": True,
    }


def join_raw_prompt_completion(prompt: str, completion: str) -> str:
    """Match lm-eval multiple-choice continuations, which begin with a space."""
    if not prompt or not completion or prompt[-1].isspace() or completion[0].isspace():
        return prompt + completion
    return prompt + " " + completion


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
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--eval-batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--eval-steps", type=int, default=100)
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument(
        "--qlora", action="store_true", help="Train LoRA adapters over a 4-bit base."
    )
    parser.add_argument(
        "--legacy-raw-concatenation",
        action="store_true",
        help="Reproduce the first sweep's Answer:choice boundary instead of lm-eval's Answer: choice.",
    )
    parser.add_argument(
        "--gguf-method",
        choices=["q4_0", "q4_k_m"],
        help="Export the trained model to this GGUF quant after merging.",
    )
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    from unsloth import FastLanguageModel  # noqa: I001
    import torch
    from datasets import load_dataset
    from transformers import DataCollatorForSeq2Seq, Trainer, TrainingArguments

    if args.skip_merge and args.gguf_method:
        parser.error("--gguf-method cannot be used with --skip-merge")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        revision=args.revision,
        max_seq_length=args.max_length,
        load_in_4bit=args.qlora,
        load_in_16bit=not args.qlora,
        full_finetuning=False,
        use_exact_model_name=True,
    )
    peft_kwargs = {
        "r": args.rank,
        "target_modules": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        "lora_alpha": args.rank,
        "lora_dropout": 0,
        "bias": "none",
        "use_gradient_checkpointing": "unsloth",
        "random_state": args.seed,
        "max_seq_length": args.max_length,
    }
    peft_kwargs.update(architecture_peft_kwargs(multimodal=hasattr(tokenizer, "image_processor")))
    model = FastLanguageModel.get_peft_model(model, **peft_kwargs)
    text_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)
    multimodal_chat = hasattr(tokenizer, "image_processor")

    datasets = load_dataset(
        "json",
        data_files={"train": str(args.train), "validation": str(args.validation)},
    )

    def tokenize(row):
        if row["mode"] == "chat":
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
            prompt_ids = tokenizer.apply_chat_template(
                prompt_messages,
                tokenize=True,
                add_generation_prompt=True,
            )
            full_ids = tokenizer.apply_chat_template(
                full_messages,
                tokenize=True,
                add_generation_prompt=False,
            )
        else:
            prompt_ids = text_tokenizer.encode(row["prompt"], add_special_tokens=True)
            raw_full_text = (
                row["prompt"] + row["completion"]
                if args.legacy_raw_concatenation
                else join_raw_prompt_completion(row["prompt"], row["completion"])
            )
            full_ids = text_tokenizer.encode(
                raw_full_text,
                add_special_tokens=True,
            )
        prompt_ids = normalize_token_ids(prompt_ids)
        full_ids = normalize_token_ids(full_ids)
        start = common_prefix_length(prompt_ids, full_ids)
        if start >= len(full_ids):
            raise ValueError(f"completion produced no tokens for {row['source']}")
        if len(full_ids) > args.max_length:
            overflow = len(full_ids) - args.max_length
            if start - overflow < 1:
                return {"input_ids": [], "attention_mask": [], "labels": []}
            full_ids = full_ids[overflow:]
            start -= overflow
        return {
            "input_ids": full_ids,
            "attention_mask": [1] * len(full_ids),
            "labels": [-100] * start + full_ids[start:],
        }

    tokenized = datasets.map(
        tokenize,
        remove_columns=datasets["train"].column_names,
        desc="tokenizing completion-masked examples",
    ).filter(lambda row: bool(row["input_ids"]))
    if not tokenized["train"] or not tokenized["validation"]:
        raise SystemExit("tokenization removed an entire split")

    training_args = TrainingArguments(
        output_dir=str(args.output / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        bf16=True,
        fp16=False,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.eval_steps,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        optim="adamw_8bit",
        seed=args.seed,
        data_seed=args.seed,
        report_to="none",
        prediction_loss_only=True,
        remove_unused_columns=False,
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
    result = trainer.train()
    evaluation = trainer.evaluate()

    adapter_dir = args.output / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    if not args.skip_merge:
        merged_dir = args.output / "merged_16bit"
        model.save_pretrained_merged(str(merged_dir), tokenizer, save_method="merged_16bit")
        if args.gguf_method:
            model.save_pretrained_gguf(
                str(args.output / "gguf"),
                tokenizer,
                quantization_method=args.gguf_method,
            )
    manifest = {
        "schema_version": 1,
        "model": args.model,
        "revision": args.revision,
        "seed": args.seed,
        "max_length": args.max_length,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "rank": args.rank,
        "training_method": "qlora_4bit" if args.qlora else "lora_bf16",
        "raw_completion_boundary": (
            "legacy_direct_concatenation"
            if args.legacy_raw_concatenation
            else "lm_eval_leading_space"
        ),
        "train_input": {
            "path": str(args.train),
            "sha256": sha256_file(args.train),
        },
        "validation_input": {
            "path": str(args.validation),
            "sha256": sha256_file(args.validation),
        },
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "max_steps": args.max_steps,
        "gguf_method": args.gguf_method,
        "train_rows": len(tokenized["train"]),
        "validation_rows": len(tokenized["validation"]),
        "train_metrics": result.metrics,
        "validation_metrics": evaluation,
        "elapsed_seconds": round(time.time() - started, 3),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
    }
    (args.output / "training-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
