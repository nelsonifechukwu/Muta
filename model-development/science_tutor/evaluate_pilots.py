"""One hash-bound, inference-only science candidate; never grade or rank outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import time
import traceback
from collections.abc import Mapping
from pathlib import Path

try:
    from . import calibrate, train
except ImportError:
    import calibrate
    import train

FROZEN = {
    "train.py": "a800ca3bf599b234c4fa61f50a37b0638496269bd811a6656598cf5543291bd0",
    "tokenization.py": "93d251a9b0394cf9033622386ebbb352a3393cbe516f985795c5289f2a85bfd4",
    "calibrate.py": "1dbbfd2072516d39c60ac4ab90be03e8f23b4215f5a1da44aef3ed2745119a57",
}
DEEPSEEK_TREE = "6e7d20161a524c07c6affa8e89badc7dd23aab11d2fa4ab48fcdcb7e81666133"
PROFILES = {
    "qwen_native": {
        "template": "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f",
        "bases": set(train.BASE_TREES.values()),
        "tokenizer_files": train.TOKENIZER_FILES,
        "training_sources": {k: v for k, v in FROZEN.items() if k != "calibrate.py"},
    },
    "deepseek_native": {
        "template": "56a1447ad31926fdc21fb07e56e5642bd9c850c4f52d8c8af7bbe5f079a84f5f",
        "bases": {DEEPSEEK_TREE},
        "tokenizer_files": {
            "tokenizer.json": "88145e3c3249adc2546ede277e9819d6e405e19072456e4b521cbc724bd60773",
            "tokenizer_config.json": "8ac8c85fb242563c2260baec0909debd69d718af6a0b3d90e6cab62b4d341cd5",
        },
        "training_sources": {
            **{k: v for k, v in FROZEN.items() if k != "calibrate.py"},
            "deepseek_train.py": "ec5c8cadbbffd97ee3c35d3d62fa3bb476d9766efec9ad0ba67ee2eb760905c0",
            "deepseek_tokenization.py": "2ce5c3b66476a688d2035119959b7e72c515d97822bf165e4823f02b70e98d60",
        },
    },
}
GENERATION = {
    "batch_size": 8,
    "max_new_tokens": 1024,
    "context_length": 4096,
    "do_sample": False,
    "seed": 3407,
}
CHECKPOINT_FILES = {
    "adapter_model.safetensors",
    "adapter_config.json",
    "training-state.pt",
    "state.json",
    "COMPLETE.json",
}


def source_hashes():
    result = {
        name: train.file_receipt(Path(__file__).with_name(name))["sha256"]
        for name in {*FROZEN, "evaluate_pilots.py"}
    }
    if any(result[name] != sha for name, sha in FROZEN.items()):
        raise train.AdmissionError("frozen generation helper source changed")
    return result


def load_config(path, sha, candidate_id):
    ref = train.verify_ref({"path": str(Path(path).absolute()), "sha256": sha})
    config = train.read_json(path)
    if (
        set(config)
        != {
            "schema_version",
            "output",
            "gpu_lock",
            "prompts",
            "source_sha256",
            "generation",
            "candidates",
        }
        or config["schema_version"] != 1
    ):
        raise train.AdmissionError("unexpected generation campaign schema")
    if config["source_sha256"] != source_hashes() or train.canonical(
        config["generation"]
    ) != train.canonical(GENERATION):
        raise train.AdmissionError("generation source/protocol differs from frozen treatment")
    if not Path(config["output"]).is_absolute() or config["gpu_lock"] != calibrate.GPU_LOCK:
        raise train.AdmissionError("absolute output and shared Oracle lock required")
    if (
        not isinstance(config["candidates"], dict)
        or not config["candidates"]
        or candidate_id not in config["candidates"]
    ):
        raise train.AdmissionError("candidate is not in the frozen campaign")
    for name, candidate in config["candidates"].items():
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", name)
            or set(candidate) - {"profile", "chat_template_sha256", "base", "tokenizer", "adapter"}
            or not {"profile", "chat_template_sha256", "base", "tokenizer"} <= candidate.keys()
        ):
            raise train.AdmissionError("invalid candidate ID/schema")
        profile = PROFILES.get(candidate["profile"])
        if (
            profile is None
            or candidate["chat_template_sha256"] != profile["template"]
            or candidate["base"]["tree_sha256"] not in profile["bases"]
        ):
            raise train.AdmissionError("candidate parent/template differs from native profile")
    return config, config["candidates"][candidate_id], ref


def load_prompts(ref):
    train.verify_ref(ref)
    rows = []
    with Path(ref["path"]).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line, object_pairs_hook=train._pairs)
            if (
                not isinstance(row, dict)
                or set(row) != {"id", "messages"}
                or not isinstance(row["id"], str)
                or not row["id"].strip()
            ):
                raise train.AdmissionError(
                    "prompts permit only id/messages; answers/rubrics are forbidden"
                )
            messages = row["messages"]
            if not isinstance(messages, list) or not messages or len(messages) % 2 != 1:
                raise train.AdmissionError("full message history must end in a user turn")
            for index, message in enumerate(messages):
                if (
                    not isinstance(message, dict)
                    or set(message) != {"role", "content"}
                    or message["role"] != ("user" if index % 2 == 0 else "assistant")
                    or not isinstance(message["content"], str)
                    or not message["content"].strip()
                ):
                    raise train.AdmissionError(
                        "unaltered alternating user/assistant history required"
                    )
            rows.append(row)
    if len(rows) != 72 or len({row["id"] for row in rows}) != 72:
        raise train.AdmissionError("exactly 72 unique prompts required before any generation")
    train.verify_ref(ref)
    return rows


def verify_adapter(candidate):
    adapter = candidate.get("adapter")
    if adapter is None:
        return None
    if (
        set(adapter) - {"path", "tree_sha256", "parent_base_tree_sha256", "checkpoint_seal"}
        or adapter.get("parent_base_tree_sha256") != candidate["base"]["tree_sha256"]
    ):
        raise train.AdmissionError("adapter parent or schema mismatch")
    receipt = train.verify_ref(adapter, tree=True)
    root = Path(adapter["path"])
    cfg = train.read_json(root / "adapter_config.json")
    if (
        any(
            cfg.get(key) != value
            for key, value in {
                "peft_type": "LORA",
                "task_type": "CAUSAL_LM",
                "r": 16,
                "lora_alpha": 16,
                "lora_dropout": 0,
                "bias": "none",
            }.items()
        )
        or set(cfg.get("target_modules", [])) != train.TARGETS
    ):
        raise train.AdmissionError("adapter is not the frozen rank16 LoRA treatment")
    if "checkpoint_seal" not in adapter:
        if (
            adapter["tree_sha256"] != train.PILOT_TREE
            or candidate["base"]["tree_sha256"] != train.BASE_TREES["pilot_adapter"]
        ):
            raise train.AdmissionError(
                "only the exact original control adapter may lack a checkpoint seal"
            )
        return receipt
    seal_ref = adapter["checkpoint_seal"]
    if Path(seal_ref["path"]) != root / "COMPLETE.json":
        raise train.AdmissionError("checkpoint seal must be inside the exact checkpoint")
    train.verify_ref(seal_ref)
    seal = train.read_json(seal_ref["path"])
    files = receipt["files"]
    names = {row["path"] for row in files}
    if (
        not CHECKPOINT_FILES <= names
        or names - CHECKPOINT_FILES - {"README.md"}
        or any(row["bytes"] <= 0 for row in files)
        or seal.get("files") != [row for row in files if row["path"] != "COMPLETE.json"]
    ):
        raise train.AdmissionError("checkpoint file seal is incomplete or inconsistent")
    step = seal.get("step")
    if (
        step not in (63, 126)
        or root.name != f"checkpoint-{step}"
        or root.parent.name != "checkpoints"
    ):
        raise train.AdmissionError("only exact half/end checkpoints are admitted")
    resolved = train.read_json(root.parent.parent / "resolved-config.json")
    training_cfg = resolved["config"]
    if seal.get("config_sha256") != resolved["config_file"]["sha256"] or seal.get(
        "source_sha256"
    ) != {name: ref["sha256"] for name, ref in resolved["sources"].items()}:
        raise train.AdmissionError("checkpoint differs from resolved trainer identity")
    original_config = train.verify_ref(resolved["config_file"])
    if (
        train.read_json(original_config["path"]) != training_cfg
        or training_cfg["initialization"]["base"] != candidate["base"]
        or training_cfg["initialization"]["tokenizer"]["tree_sha256"]
        != candidate["tokenizer"]["tree_sha256"]
    ):
        raise train.AdmissionError("checkpoint original parent/tokenizer/config mismatch")
    if seal["source_sha256"] != PROFILES[candidate["profile"]]["training_sources"]:
        raise train.AdmissionError("checkpoint frozen native trainer source mismatch")
    state = train.read_json(root / "state.json")
    if (
        state.get("step") != step
        or state.get("consumed_trainable_tokens") != seal.get("consumed_trainable_tokens")
        or not isinstance(state.get("consumed_trainable_tokens"), int)
        or state["consumed_trainable_tokens"] <= 0
    ):
        raise train.AdmissionError("checkpoint state/seal mismatch")
    return receipt


def render_prompts(rows, tokenizer, candidate):
    if (
        hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
        != candidate["chat_template_sha256"]
    ):
        raise train.AdmissionError("loaded native template hash mismatch")
    if tokenizer.eos_token_id is None or tokenizer.pad_token_id is None:
        raise train.AdmissionError("explicit native EOS/padding IDs required")
    controls = (
        set(tokenizer.all_special_tokens)
        | set(tokenizer.get_added_vocab())
        | {"<think>", "</think>"}
    )
    rendered = []
    for row in rows:
        if any(
            control and control in message["content"]
            for message in row["messages"]
            for control in controls
        ):
            raise train.AdmissionError("literal template control in prompt message")
        kwargs = {"add_generation_prompt": True, "truncation": False, "padding": False}
        text = tokenizer.apply_chat_template(row["messages"], tokenize=False, **kwargs)
        ids = tokenizer.apply_chat_template(row["messages"], tokenize=True, **kwargs)
        if isinstance(ids, Mapping):
            ids = ids["input_ids"]
        if hasattr(ids, "tolist"):
            ids = ids.tolist()
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            if len(ids) != 1:
                raise train.AdmissionError("unexpected batched native tokenizer result")
            ids = ids[0]
        if (
            not isinstance(ids, list)
            or not ids
            or any(type(value) is not int or value < 0 for value in ids)
            or tokenizer.encode(text, add_special_tokens=False) != ids
        ):
            raise train.AdmissionError("native prompt rendering is not exactly token-stable")
        if len(ids) + GENERATION["max_new_tokens"] > GENERATION["context_length"]:
            raise train.AdmissionError(
                "complete prompt plus generation exceeds context; no truncation"
            )
        if candidate["profile"] == "deepseek_native" and not text.endswith("<think>\n"):
            raise train.AdmissionError("DeepSeek native reasoning generation prefix is missing")
        rendered.append({**row, "rendered_prompt": text, "prompt_ids": ids})
    return rendered


def prepare(config, candidate):
    rows = load_prompts(config["prompts"])
    base = train.verify_ref(candidate["base"], tree=True)
    tokenizer_ref = train.verify_ref(candidate["tokenizer"], tree=True)
    if (Path(candidate["base"]["path"]) / "adapter_config.json").exists():
        raise train.AdmissionError("base is an adapter directory")
    observed = {row["path"]: row["sha256"] for row in tokenizer_ref["files"]}
    if any(
        observed.get(name) != sha
        for name, sha in PROFILES[candidate["profile"]]["tokenizer_files"].items()
    ):
        raise train.AdmissionError("tokenizer bytes differ from native profile")
    adapter = verify_adapter(candidate)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        candidate["tokenizer"]["path"], local_files_only=True, trust_remote_code=False
    )
    tokenizer.padding_side = "left"
    rendered = render_prompts(rows, tokenizer, candidate)
    return tokenizer, rendered, {"base": base, "tokenizer": tokenizer_ref, "adapter": adapter}


def padded_batch(rows, pad_id):
    width = max(len(row["prompt_ids"]) for row in rows)
    ids, mask = [], []
    for row in rows:
        padding = width - len(row["prompt_ids"])
        ids.append([pad_id] * padding + row["prompt_ids"])
        mask.append([0] * padding + [1] * len(row["prompt_ids"]))
    return ids, mask


def continuation_record(raw_ids, *, eos_id, pad_id, tokenizer):
    if not raw_ids or len(raw_ids) > 1024 or any(type(value) is not int for value in raw_ids):
        raise train.AdmissionError("invalid generated token count/IDs")
    eos_index = next((i for i, token in enumerate(raw_ids) if token == eos_id), None)
    if eos_index is None:
        if len(raw_ids) != 1024:
            raise train.AdmissionError("generation stopped without EOS or token cap")
        active = raw_ids
        reason = "token_cap"
    else:
        active = raw_ids[: eos_index + 1]
        if any(token != pad_id for token in raw_ids[eos_index + 1 :]):
            raise train.AdmissionError("unexpected non-padding tokens after first EOS")
        reason = "eos"
    return {
        "generated_ids": raw_ids,
        "raw_continuation": tokenizer.decode(
            raw_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False
        ),
        "continuation": tokenizer.decode(
            active, skip_special_tokens=False, clean_up_tokenization_spaces=False
        ),
        "finish_reason": reason,
        "generated_tokens_through_eos": len(active),
        "batch_padding_tokens": len(raw_ids) - len(active),
        "eos_token_id": eos_id,
        "pad_token_id": pad_id,
    }


def load_model(candidate, torch):
    from transformers import AutoModelForCausalLM

    model = AutoModelForCausalLM.from_pretrained(
        candidate["base"]["path"],
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
        local_files_only=True,
        trust_remote_code=False,
    )
    loaded = {"operation": "bare_parent", "adapter_loads": 0, "merged": False}
    if candidate.get("adapter"):
        from peft import PeftModel

        model = PeftModel.from_pretrained(
            model, candidate["adapter"]["path"], is_trainable=False, autocast_adapter_dtype=True
        )
        if set(model.peft_config) != {"default"} or model.active_adapters != ["default"]:
            raise train.AdmissionError("requires exactly one active adapter")
        loaded = {
            "operation": "exact_adapter_once_on_original_parent",
            "adapter_loads": 1,
            "merged": False,
            **train.verify_loaded_adapter(model, candidate["adapter"]["path"], torch),
        }
    adapter_count = 0
    for name, parameter in model.named_parameters():
        if ".lora_" in name:
            if not re.fullmatch(r".+\.lora_[AB]\.default\.weight", name):
                raise train.AdmissionError("unexpected adapter parameter")
            parameter.data = parameter.data.float()
            adapter_count += 1
        elif parameter.is_floating_point() and parameter.dtype != torch.bfloat16:
            raise train.AdmissionError("base parameter is not BF16")
        parameter.requires_grad_(False)
    if bool(adapter_count) != bool(candidate.get("adapter")) or any(
        getattr(module, "merged_adapters", ()) for module in model.modules()
    ):
        raise train.AdmissionError("unexpected/missing/merged adapters")
    model.eval()
    model.config.use_cache = True
    return model.to("cuda:0"), loaded


def verify_responses(path, expected_ids, candidate_id):
    with Path(path).open(encoding="utf-8") as handle:
        rows = [json.loads(line, object_pairs_hook=train._pairs) for line in handle]
    if (
        len(rows) != 72
        or [row["id"] for row in rows] != expected_ids
        or any(row["candidate_id"] != candidate_id or not row["generated_ids"] for row in rows)
    ):
        raise train.AdmissionError("incomplete candidate; all 72 ordered results required")
    return train.file_receipt(path)


def run(args):
    config, candidate, config_ref = load_config(args.config, args.config_sha256, args.candidate)
    tokenizer, rows, identities = prepare(config, candidate)
    output = Path(config["output"]) / args.candidate
    output.mkdir(parents=True, exist_ok=False)
    try:
        train.write_new(
            output / "REQUEST.json",
            {
                "config": config_ref,
                "candidate": candidate,
                "identities": identities,
                "prompt_ref": config["prompts"],
                "source_sha256": config["source_sha256"],
                "pid": os.getpid(),
                "started_unix": time.time(),
            },
        )
        with calibrate.oracle_lock(config["gpu_lock"]):
            before = calibrate.host_snapshot()
            train.write_new(output / "host-before.json", before)
            import torch
            from transformers import GenerationConfig

            if (
                not torch.cuda.is_available()
                or torch.cuda.device_count() != 1
                or not torch.cuda.is_bf16_supported()
            ):
                raise train.AdmissionError("one BF16-capable CUDA device required")
            torch.manual_seed(3407)
            torch.cuda.manual_seed_all(3407)
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.backends.cudnn.benchmark = False
            model, initialized = load_model(candidate, torch)
            train.write_new(
                output / "initialized.json",
                {
                    "model": initialized,
                    "environment": train.environment_receipt(),
                    "host": calibrate.host_snapshot(own_pid=os.getpid()),
                },
            )
            for ref in (candidate["base"], candidate["tokenizer"]):
                train.verify_ref(ref, tree=True)
            verify_adapter(candidate)
            generation = GenerationConfig(
                max_new_tokens=1024,
                do_sample=False,
                num_beams=1,
                use_cache=True,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id,
                bos_token_id=model.config.bos_token_id,
            )
            result_path = output / "responses.jsonl"
            completed_ids = []
            with result_path.open("x", encoding="utf-8") as handle, torch.inference_mode():
                for offset in range(0, len(rows), 8):
                    batch = rows[offset : offset + 8]
                    padded, mask = padded_batch(batch, tokenizer.pad_token_id)
                    tensor = torch.tensor(padded, dtype=torch.long, device="cuda:0")
                    attention = torch.tensor(mask, dtype=torch.long, device="cuda:0")
                    started = time.monotonic()
                    with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                        returned = model.generate(
                            input_ids=tensor, attention_mask=attention, generation_config=generation
                        )
                    sequences = returned.detach().cpu().tolist()
                    # Preserve transport before validating any item; failures must not
                    # erase an offending response or the rest of its returned batch.
                    train.write_new(
                        output / "batches" / f"batch-{offset // 8:04d}.json",
                        {
                            "offset": offset,
                            "prompts": batch,
                            "padded_prompt_ids": padded,
                            "attention_mask": mask,
                            "returned_sequence_ids": sequences,
                            "config_sha256": config_ref["sha256"],
                            "candidate_id": args.candidate,
                        },
                    )
                    if len(sequences) != len(batch):
                        raise train.AdmissionError("generation returned wrong batch count")
                    elapsed = time.monotonic() - started
                    for row, prompt_ids, attention_row, generated in zip(
                        batch, padded, mask, sequences, strict=True
                    ):
                        if generated[: len(prompt_ids)] != prompt_ids:
                            raise train.AdmissionError(
                                "returned generation changed padded prompt IDs"
                            )
                        result = {
                            **row,
                            "candidate_id": args.candidate,
                            "profile": candidate["profile"],
                            "padded_prompt_ids": prompt_ids,
                            "attention_mask": attention_row,
                            "batch_seconds": elapsed,
                            **continuation_record(
                                generated[len(prompt_ids) :],
                                eos_id=tokenizer.eos_token_id,
                                pad_id=tokenizer.pad_token_id,
                                tokenizer=tokenizer,
                            ),
                        }
                        handle.write(
                            json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
                            + "\n"
                        )
                        handle.flush()
                        os.fsync(handle.fileno())
                        completed_ids.append(row["id"])
                    del returned, tensor, attention
            if (
                completed_ids != [row["id"] for row in rows]
                or len(completed_ids) != 72
                or result_path.stat().st_size == 0
            ):
                raise train.AdmissionError("incomplete candidate; all 72 required")
            load_config(args.config, args.config_sha256, args.candidate)
            train.verify_ref(config["prompts"])
            for ref in (candidate["base"], candidate["tokenizer"]):
                train.verify_ref(ref, tree=True)
            verify_adapter(candidate)
            result = {
                "status": "complete",
                "candidate_id": args.candidate,
                "config": config_ref,
                "source_sha256": source_hashes(),
                "prompts": config["prompts"],
                "completed_ids": completed_ids,
                "completed_count": 72,
                "ranking_performed": False,
                "responses": verify_responses(result_path, completed_ids, args.candidate),
                "host_after": calibrate.host_snapshot(own_pid=os.getpid()),
                "ended_unix": time.time(),
                "inventory": train.tree_receipt(output),
            }
            train.write_new(output / "COMPLETED.json", result)
            return result
    except BaseException as exc:
        train.write_new(
            output / "FAILED.json",
            {
                "status": "failed",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "automatic_retry": False,
                "partial_results_are_not_rankings": True,
                "time_unix": time.time(),
            },
        )
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)

    def stopped(signum, _frame):
        raise RuntimeError(f"received signal {signum}; no retry")

    signal.signal(signal.SIGTERM, stopped)
    print(json.dumps(run(args), sort_keys=True))


if __name__ == "__main__":
    main()
