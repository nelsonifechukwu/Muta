"""Hash-bound, single-GPU BF16/FP32-LoRA SFT for the science-tutor campaign.

Run with --config FILE --config-sha256 SHA; --preflight-only never loads a model.
No downloads, automatic retries, truncation, adapter merging, final-holdout access,
or automatic checkpoint selection occur here. Exact full messages are retained.
The two saved checkpoints are candidates for *external* generated-dev review.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import signal
import time
import traceback
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

try:
    from .tokenization import canonical, digest, tokenize_messages
except ImportError:  # Direct, portable invocation on a training host.
    from tokenization import canonical, digest, tokenize_messages


BASE_TREES = {
    "upstream_fresh": "ae1baefcdac4c037b545696abffc1bd07824c109572163664333b5a5c0dda892",
    "muta_fresh": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
    "pilot_adapter": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
}
PILOT_TREE = "4ec07d3668e9a772573c7f6553319760af00fb28cc1c8743a3c8fe5ce97a0aff"
TOKENIZER_FILES = {
    "tokenizer.json": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "tokenizer_config.json": "5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583",
}
TARGETS = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
ROW_FIELDS = {
    "id",
    "group_id",
    "source",
    "source_revision",
    "source_id",
    "license",
    "subject",
    "capabilities",
    "quality",
    "messages",
}


class AdmissionError(ValueError):
    pass


def sha256_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            result.update(block)
    return result.hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise AdmissionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            AdmissionError(f"nonfinite JSON: {value}")
        ),
    )


def file_receipt(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise AdmissionError(f"not a regular, non-symlink file: {path}")
    return {"path": str(path.resolve()), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def tree_receipt(path):
    """Same SHA/path inventory convention as the frozen campaign, without imports."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise AdmissionError(f"not a non-symlink directory: {path}")
    files = []
    for entry in sorted(path.rglob("*")):
        if entry.is_symlink():
            raise AdmissionError(f"symlink in input tree: {entry}")
        if entry.is_file():
            files.append(
                {
                    "path": entry.relative_to(path).as_posix(),
                    "sha256": sha256_file(entry),
                    "bytes": entry.stat().st_size,
                }
            )
        elif not entry.is_dir():
            raise AdmissionError(f"special file in input tree: {entry}")
    if not files:
        raise AdmissionError(f"empty input tree: {path}")
    sha = hashlib.sha256(
        "\n".join(f"{x['sha256']}  {x['path']}" for x in files).encode()
    ).hexdigest()
    return {
        "root": str(path.resolve()),
        "tree_sha256": sha,
        "files": files,
        "file_count": len(files),
        "bytes": sum(x["bytes"] for x in files),
    }


def verify_ref(ref, *, tree=False):
    required = "tree_sha256" if tree else "sha256"
    if not isinstance(ref, dict) or not {"path", required} <= ref.keys():
        raise AdmissionError(f"reference needs path/{required}")
    if not Path(ref["path"]).is_absolute():
        raise AdmissionError("config paths must be absolute")
    observed = tree_receipt(ref["path"]) if tree else file_receipt(ref["path"])
    if observed[required] != ref[required]:
        raise AdmissionError(f"hash mismatch: {ref['path']}")
    return observed


def write_new(path, value):
    """Never overwrite even a failure, checkpoint or partial-attempt receipt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(
            json.dumps(
                value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
            ).encode()
            + b"\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def append_log(path, value):
    with Path(path).open("ab") as handle:
        handle.write(canonical(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    if path.is_symlink():
        raise AdmissionError("refusing a symlink lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AdmissionError(f"lock already owned: {path}") from exc
        # Never leave the shared lock held by a forked worker after parent failure.
        os.register_at_fork(after_in_child=lambda: handle.close() if not handle.closed else None)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _positive_int(value, name):
    if type(value) is not int or value < 1:
        raise AdmissionError(f"{name} must be a positive integer")


def validate_config(config, *, preflight=False):
    required = {
        "schema_version",
        "run_id",
        "output",
        "gpu_lock",
        "initialization",
        "data",
        "tokenization",
        "training",
        "lora",
    }
    if not isinstance(config, dict):
        raise AdmissionError("config must be a JSON object")
    if not required <= config.keys():
        raise AdmissionError(f"missing config keys: {sorted(required - config.keys())}")
    if set(config) - required - {"notes", "retry_of"}:
        raise AdmissionError("unknown config keys")
    if config["schema_version"] != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]+", config["run_id"]):
        raise AdmissionError("invalid schema version/run_id")
    for name in ("output", "gpu_lock"):
        if not Path(config[name]).is_absolute():
            raise AdmissionError(f"{name} must be absolute")
    init = config["initialization"]
    if init["kind"] not in BASE_TREES or init["base"]["tree_sha256"] != BASE_TREES[init["kind"]]:
        raise AdmissionError("initialization does not identify the exact campaign parent")
    if init["kind"] == "pilot_adapter":
        adapter = init.get("adapter", {})
        if (
            adapter.get("tree_sha256") != PILOT_TREE
            or adapter.get("parent_base_tree_sha256") != init["base"]["tree_sha256"]
        ):
            raise AdmissionError(
                "pilot adapter must match the exact winning pilot and original parent"
            )
    elif "adapter" in init:
        raise AdmissionError("fresh initializations cannot load an adapter")
    tok = config["tokenization"]
    if set(tok) != {"max_length", "chat_template_sha256", "split_policy"}:
        raise AdmissionError("unexpected tokenization config")
    _positive_int(tok["max_length"], "max_length")
    if tok["split_policy"] != "preserve_whole_conversation":
        raise AdmissionError("only preserve_whole_conversation is admitted")
    train = config["training"]
    expected = {
        "seed",
        "micro_batch_size",
        "gradient_accumulation",
        "effective_batch_size",
        "max_steps",
        "expected_trainable_tokens",
        "learning_rate",
        "weight_decay",
        "warmup_ratio",
        "logging_steps",
        "eval_batch_size",
    }
    if set(train) - expected - {"gradient_checkpointing"} or expected - train.keys():
        raise AdmissionError("unexpected or missing training config")
    for name in (
        "micro_batch_size",
        "gradient_accumulation",
        "effective_batch_size",
        "max_steps",
        "logging_steps",
        "eval_batch_size",
    ):
        _positive_int(train[name], name)
    if type(train["seed"]) is not int or not 0 <= train["seed"] < 2**32:
        raise AdmissionError("seed must be an unsigned 32-bit integer")
    if train["micro_batch_size"] * train["gradient_accumulation"] != train["effective_batch_size"]:
        raise AdmissionError("microbatch × accumulation differs from effective batch")
    if train["expected_trainable_tokens"] is not None or not preflight:
        _positive_int(train["expected_trainable_tokens"], "expected_trainable_tokens")
    for name in ("learning_rate", "weight_decay", "warmup_ratio"):
        value = train[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise AdmissionError(f"invalid {name}")
    if (
        train["learning_rate"] <= 0
        or train["weight_decay"] < 0
        or not 0 <= train["warmup_ratio"] <= 1
    ):
        raise AdmissionError("invalid learning rate/decay/warmup")
    lora = config["lora"]
    if set(lora) != {"r", "alpha", "dropout", "target_modules"}:
        raise AdmissionError("unexpected LoRA config")
    for name in ("r", "alpha"):
        _positive_int(lora[name], name)
    if (
        lora["dropout"] != 0
        or set(lora["target_modules"]) != TARGETS
        or len(lora["target_modules"]) != len(TARGETS)
    ):
        raise AdmissionError("campaign requires dropout 0 and the seven attention/MLP projections")
    if init["kind"] == "pilot_adapter" and (lora["r"], lora["alpha"]) != (16, 16):
        raise AdmissionError("pilot adapter rank/alpha must remain 16/16")
    if set(config["data"]) != {"train", "dev", "admission"}:
        raise AdmissionError("only admitted train/dev data may be accessed")


def load_rows(path):
    rows, ids = [], set()
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                raise AdmissionError(f"blank JSONL row at line {number}")
            row = json.loads(line, object_pairs_hook=_pairs)
            if not isinstance(row, dict) or not ROW_FIELDS <= row.keys():
                raise AdmissionError(f"incomplete row metadata at line {number}")
            for field in ROW_FIELDS - {"quality", "capabilities", "messages"}:
                if not isinstance(row[field], str) or not row[field].strip():
                    raise AdmissionError(f"invalid {field} at line {number}")
            if not isinstance(row["capabilities"], list) or not row["capabilities"]:
                raise AdmissionError("row has no capabilities")
            if row["id"] in ids:
                raise AdmissionError(f"duplicate row ID: {row['id']}")
            ids.add(row["id"])
            rows.append(row)
    if not rows:
        raise AdmissionError("empty dataset")
    return rows


def deterministic_schedule(rows, *, seed, effective_batch_size, max_steps):
    """One shuffled epoch plus a disclosed deterministic repeated tail, no drops."""
    required_steps = math.ceil(len(rows) / effective_batch_size)
    if max_steps != required_steps:
        raise AdmissionError(f"one epoch requires {required_steps} steps, not {max_steps}")
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    padding = max_steps * effective_batch_size - len(order)
    schedule = order + [order[i % len(order)] for i in range(padding)]
    repeated = schedule[len(order) :]
    return schedule, {
        "policy": "one shuffled epoch then repeated prefix to a full effective batch",
        "unique_rows": len(order),
        "scheduled_rows": len(schedule),
        "repeated_tail_rows": len(repeated),
        "repeated_tail_ids": [rows[i]["id"] for i in repeated],
        "scheduled_ids_sha256": digest([rows[i]["id"] for i in schedule]),
    }


def prepare(config, *, preflight=False):
    """Verify everything before model loading; return token arrays without copying text."""
    validate_config(config, preflight=preflight)
    refs = {name: verify_ref(ref) for name, ref in config["data"].items()}
    admission = read_json(config["data"]["admission"]["path"])
    if (
        admission.get("schema_version") != 1
        or admission.get("status") != "admitted"
        or admission.get("group_disjoint") is not True
        or admission.get("overlength_policy") != "excluded_before_freeze"
    ):
        raise AdmissionError("missing dataset admission/group-disjoint/overlength receipt")
    raw = {name: load_rows(config["data"][name]["path"]) for name in ("train", "dev")}
    for name, rows in raw.items():
        expected = {
            "sha256": refs[name]["sha256"],
            "rows": len(rows),
            "row_ids_sha256": digest(sorted(r["id"] for r in rows)),
        }
        if any(admission.get(name, {}).get(k) != v for k, v in expected.items()):
            raise AdmissionError(f"admission {name} binding mismatch")
    if {r["group_id"] for r in raw["train"]} & {r["group_id"] for r in raw["dev"]}:
        raise AdmissionError("a source/conversation group crosses train/dev")
    if {r["id"] for r in raw["train"]} & {r["id"] for r in raw["dev"]}:
        raise AdmissionError("row identity crosses train/dev")
    init = config["initialization"]
    identities = {name: verify_ref(init[name], tree=True) for name in ("base", "tokenizer")}
    tokenizer_files = {row["path"]: row["sha256"] for row in identities["tokenizer"]["files"]}
    if any(tokenizer_files.get(name) != sha for name, sha in TOKENIZER_FILES.items()):
        raise AdmissionError("all candidates must use the exact common upstream tokenizer files")
    base = Path(init["base"]["path"])
    if (base / "adapter_config.json").exists():
        raise AdmissionError("base cannot itself be an adapter")
    if init["kind"] == "pilot_adapter":
        identities["adapter"] = verify_ref(init["adapter"], tree=True)
        adapter_config = read_json(Path(init["adapter"]["path"]) / "adapter_config.json")
        expected = {
            "peft_type": "LORA",
            "task_type": "CAUSAL_LM",
            "r": 16,
            "lora_alpha": 16,
            "lora_dropout": 0,
            "bias": "none",
        }
        if (
            any(adapter_config.get(k) != v for k, v in expected.items())
            or set(adapter_config.get("target_modules", ())) != TARGETS
        ):
            raise AdmissionError("pilot adapter config incompatible with matched LoRA treatment")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        init["tokenizer"]["path"], local_files_only=True, trust_remote_code=False
    )
    template_sha = hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
    if template_sha != config["tokenization"]["chat_template_sha256"]:
        raise AdmissionError("chat template hash mismatch")
    if tokenizer.pad_token_id is None:
        raise AdmissionError("tokenizer lacks an explicit padding token")
    tokenized, counts, row_receipts = {}, {}, []
    for name, rows in raw.items():
        tokenized[name] = []
        for row in rows:
            tokens = tokenize_messages(
                row["messages"],
                tokenizer=tokenizer,
                max_length=config["tokenization"]["max_length"],
            )
            tokenized[name].append(tokens)
            row_receipts.append(
                {
                    "split": name,
                    "id": row["id"],
                    "group_id": row["group_id"],
                    "row_sha256": digest(row),
                    **{
                        k: v
                        for k, v in tokens.items()
                        if k not in {"input_ids", "attention_mask", "labels", "assistant_spans"}
                    },
                }
            )
        counts[name] = {
            "rows": len(rows),
            "conversations": len(rows),
            "source_groups": len({r["group_id"] for r in rows}),
            "sources": dict(Counter(r["source"] for r in rows)),
            "assistant_turns": sum(t["assistant_turns"] for t in tokenized[name]),
            "sequence_tokens": sum(t["sequence_tokens"] for t in tokenized[name]),
            "trainable_tokens": sum(t["trainable_tokens"] for t in tokenized[name]),
            "max_sequence_tokens": max(t["sequence_tokens"] for t in tokenized[name]),
            "truncated_rows": 0,
            "split_rows": 0,
            "excluded_by_trainer": 0,
        }
    train = config["training"]
    schedule, schedule_receipt = deterministic_schedule(
        raw["train"],
        seed=train["seed"],
        effective_batch_size=train["effective_batch_size"],
        max_steps=train["max_steps"],
    )
    budget = sum(tokenized["train"][i]["trainable_tokens"] for i in schedule)
    schedule_receipt.update(
        trainable_tokens=budget,
        sequence_tokens=sum(tokenized["train"][i]["sequence_tokens"] for i in schedule),
        repeated_tail_trainable_tokens=sum(
            tokenized["train"][i]["trainable_tokens"] for i in schedule[len(raw["train"]) :]
        ),
    )
    if (
        train["expected_trainable_tokens"] is not None
        and budget != train["expected_trainable_tokens"]
    ):
        raise AdmissionError(
            f"scheduled trainable-token budget {budget} differs from frozen expectation"
        )
    receipt = {
        "data": refs,
        "admission": admission,
        "initialization": identities,
        "tokenizer_class": type(tokenizer).__name__,
        "chat_template_sha256": template_sha,
        "counts": counts,
        "schedule": schedule_receipt,
        "row_receipts": row_receipts,
        "masking": "every assistant content plus closing EOS/template suffix; headers and all non-assistant tokens masked",
        "token_counting": "non-ignored labels after causal shift; padding excluded",
    }
    # The JSONL bytes must still match after parsing/tokenization, not just before.
    for ref in config["data"].values():
        verify_ref(ref)
    return tokenizer, tokenized, schedule, receipt


def collate(items, *, pad_token_id, torch_module, device):
    width = max(len(x["input_ids"]) for x in items)
    data = {"input_ids": [], "attention_mask": [], "labels": []}
    for item in items:
        length = len(item["input_ids"])
        for key, padding in (("input_ids", pad_token_id), ("attention_mask", 0), ("labels", -100)):
            data[key].append(item[key] + [padding] * (width - length))
    return {
        k: torch_module.tensor(v, dtype=torch_module.long, device=device) for k, v in data.items()
    }


def environment_receipt():
    versions = {}
    for name in ("torch", "transformers", "peft", "safetensors", "tokenizers", "accelerate"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hostname": platform.node(),
        "packages": versions,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
    }


def source_receipts():
    return {
        name: file_receipt(Path(__file__).with_name(name))
        for name in ("train.py", "tokenization.py")
    }


def verify_resume(checkpoint, expected_sha, *, output, config_sha, source_hashes):
    checkpoint = Path(checkpoint)
    if checkpoint.parent.resolve() != (output / "checkpoints").resolve():
        raise AdmissionError("resume must use this run's own checkpoint directory")
    if tree_receipt(checkpoint)["tree_sha256"] != expected_sha:
        raise AdmissionError("resume checkpoint tree hash mismatch")
    sealed = read_json(checkpoint / "COMPLETE.json")
    if sealed["config_sha256"] != config_sha or sealed["source_sha256"] != source_hashes:
        raise AdmissionError("resume config/source identity changed")
    for row in sealed["files"]:
        target = checkpoint / row["path"]
        if (
            target.parent.resolve() != checkpoint.resolve()
            or file_receipt(target)["sha256"] != row["sha256"]
            or target.stat().st_size != row["bytes"]
        ):
            raise AdmissionError("resume checkpoint file seal mismatch")
    expected_names = {row["path"] for row in sealed["files"]} | {"COMPLETE.json"}
    if {p.name for p in checkpoint.iterdir()} != expected_names:
        raise AdmissionError("resume checkpoint contains unsealed files")
    steps = []
    for path in (output / "checkpoints").iterdir():
        if not path.is_dir() or not (path / "COMPLETE.json").is_file():
            raise AdmissionError("incomplete checkpoint retained; diagnose before resume")
        steps.append(read_json(path / "COMPLETE.json")["step"])
    if sealed["step"] != max(steps):
        raise AdmissionError("resume must name the latest complete checkpoint")
    return sealed


def _adapter_identity(model, torch):
    from peft import get_peft_model_state_dict

    state = get_peft_model_state_dict(model)
    value = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        array = tensor.detach().cpu().contiguous()
        value.update(canonical([name, list(array.shape), str(array.dtype)]))
        value.update(array.view(torch.uint8).numpy().tobytes())
    return {"tensor_sha256": value.hexdigest(), "tensor_count": len(state)}


def verify_loaded_adapter(model, path, torch):
    """Prove all and only the saved adapter tensors were loaded, not merely named."""
    from peft import get_peft_model_state_dict
    from safetensors.torch import load_file

    source = load_file(str(Path(path) / "adapter_model.safetensors"), device="cpu")
    observed = get_peft_model_state_dict(model)
    if not source or set(source) != set(observed):
        raise AdmissionError("loaded adapter tensor keys do not match the exact source")
    for name, tensor in source.items():
        target = observed[name].detach().cpu()
        if (
            tensor.shape != target.shape
            or not bool(torch.isfinite(tensor).all())
            or not torch.equal(tensor.to(target.dtype), target)
        ):
            raise AdmissionError(f"loaded adapter value/shape mismatch: {name}")
    return {
        "source_safetensors_sha256": sha256_file(Path(path) / "adapter_model.safetensors"),
        "exact_tensor_values_loaded": True,
        "source_tensor_count": len(source),
    }


def initialize_model(config, *, torch, resume=None):
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM

    init = config["initialization"]
    model = AutoModelForCausalLM.from_pretrained(
        init["base"]["path"],
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    adapter_path = str(resume) if resume else (init.get("adapter") or {}).get("path")
    if adapter_path:
        # Exactly one trainable adapter, loaded once on the unmerged parent.
        model = PeftModel.from_pretrained(
            model, adapter_path, is_trainable=True, autocast_adapter_dtype=True
        )
        operation = "own_stage_checkpoint_once" if resume else "pilot_adapter_once_fresh_optimizer"
    else:
        cfg = config["lora"]
        model = get_peft_model(
            model,
            LoraConfig(
                r=cfg["r"],
                lora_alpha=cfg["alpha"],
                lora_dropout=cfg["dropout"],
                target_modules=cfg["target_modules"],
                bias="none",
                task_type="CAUSAL_LM",
            ),
        )
        operation = "fresh_lora_fresh_optimizer"
    if set(model.peft_config) != {"default"} or model.active_adapters != ["default"]:
        raise AdmissionError("requires one active default adapter")
    trainable = []
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            if not re.fullmatch(r".+\.lora_[AB]\.default\.weight", name):
                raise AdmissionError(f"unexpected trainable parameter: {name}")
            parameter.data = parameter.data.float()
            trainable.append(parameter)
        elif parameter.is_floating_point() and parameter.dtype != torch.bfloat16:
            raise AdmissionError(f"base tensor is not BF16: {name}")
    if not trainable or any(getattr(m, "merged_adapters", ()) for m in model.modules()):
        raise AdmissionError("no LoRA parameters or merged adapter found")
    if config["training"].get("gradient_checkpointing", True):
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    loaded = verify_loaded_adapter(model, adapter_path, torch) if adapter_path else {}
    return (
        model.to("cuda:0"),
        trainable,
        {
            "operation": operation,
            **loaded,
            "base_dtype": "bfloat16",
            "adapter_dtype": "float32",
            "trainable_parameters": sum(p.numel() for p in trainable),
            **_adapter_identity(model, torch),
        },
    )


def save_checkpoint(
    model, optimizer, scheduler, *, torch, output, step, config_sha, source_hashes, consumed_tokens
):
    path = output / "checkpoints" / f"checkpoint-{step}"
    path.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(path, safe_serialization=True)
    torch.save(
        {
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "torch_rng": torch.get_rng_state(),
            "cuda_rng": torch.cuda.get_rng_state_all(),
            "python_rng": random.getstate(),
            "step": step,
            "consumed_trainable_tokens": consumed_tokens,
        },
        path / "training-state.pt",
    )
    write_new(
        path / "state.json",
        {
            "step": step,
            "consumed_trainable_tokens": consumed_tokens,
            "adapter": _adapter_identity(model, torch),
        },
    )
    files = tree_receipt(path)["files"]
    write_new(
        path / "COMPLETE.json",
        {
            "schema_version": 1,
            "step": step,
            "config_sha256": config_sha,
            "source_sha256": source_hashes,
            "files": files,
            "consumed_trainable_tokens": consumed_tokens,
        },
    )
    return tree_receipt(path)


def evaluate(model, items, *, tokenizer, torch, batch_size):
    model.eval()
    weighted_loss, count = 0.0, 0
    with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        for offset in range(0, len(items), batch_size):
            chunk = items[offset : offset + batch_size]
            tokens = sum(row["trainable_tokens"] for row in chunk)
            batch = collate(
                chunk, pad_token_id=tokenizer.pad_token_id, torch_module=torch, device="cuda:0"
            )
            loss = float(model(**batch).loss.detach())
            if not math.isfinite(loss):
                raise RuntimeError("nonfinite development loss")
            weighted_loss += loss * tokens
            count += tokens
    model.train()
    return {
        "eval_loss": weighted_loss / count,
        "eval_trainable_tokens": count,
        "eval_rows": len(items),
        "metric": "assistant-token-weighted cross entropy",
    }


def train_loop(config, prepared, *, output, attempt, config_sha, sources, resume, resume_receipt):
    import torch
    from transformers import get_cosine_schedule_with_warmup

    tokenizer, data, schedule, prep = prepared
    if int(os.environ.get("WORLD_SIZE", "1")) != 1:
        raise AdmissionError("one process per GPU only; distributed launch is unsupported")
    if (
        not torch.cuda.is_available()
        or torch.cuda.device_count() != 1
        or not torch.cuda.is_bf16_supported()
    ):
        raise AdmissionError("exactly one visible BF16-capable CUDA GPU is required")
    opts = config["training"]
    random.seed(opts["seed"])
    torch.manual_seed(opts["seed"])
    torch.cuda.manual_seed_all(opts["seed"])
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    model, parameters, initialized = initialize_model(config, torch=torch, resume=resume)
    # Recheck input identities after loading to catch changes during model construction.
    for name in ("base", "tokenizer") + (
        ("adapter",) if config["initialization"]["kind"] == "pilot_adapter" else ()
    ):
        verify_ref(config["initialization"][name], tree=True)
    source_hashes = {k: v["sha256"] for k, v in sources.items()}
    if resume:
        verify_resume(
            resume,
            resume_receipt["tree_sha256"],
            output=output,
            config_sha=config_sha,
            source_hashes=source_hashes,
        )
    optimizer = torch.optim.AdamW(
        parameters,
        lr=opts["learning_rate"],
        weight_decay=opts["weight_decay"],
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=math.ceil(opts["max_steps"] * opts["warmup_ratio"]),
        num_training_steps=opts["max_steps"],
    )
    first_step, consumed = 0, 0
    if resume:
        # Only hash-verified locally generated state is unpickled; no remote checkpoint loading.
        state = torch.load(
            Path(resume) / "training-state.pt", map_location="cpu", weights_only=False
        )
        first_step, consumed = state["step"], state["consumed_trainable_tokens"]
        if first_step != resume_receipt["step"] or not 0 < first_step <= opts["max_steps"]:
            raise AdmissionError("resume step is not an own-stage checkpoint")
        expected_consumed = sum(
            data["train"][i]["trainable_tokens"]
            for i in schedule[: first_step * opts["effective_batch_size"]]
        )
        if consumed != expected_consumed:
            raise AdmissionError("resume token position does not match frozen schedule")
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        torch.set_rng_state(state["torch_rng"])
        torch.cuda.set_rng_state_all(state["cuda_rng"])
        random.setstate(state["python_rng"])
        expected_adapter = read_json(Path(resume) / "state.json")["adapter"]
        if _adapter_identity(model, torch) != expected_adapter:
            raise AdmissionError("resumed adapter tensor values differ from sealed checkpoint")
    write_new(
        output / "attempts" / f"{attempt}-initialized.json",
        {
            "initialization": initialized,
            "resume_step": first_step,
            "environment": environment_receipt(),
            "gpu": torch.cuda.get_device_name(0),
            "cuda_version": torch.version.cuda,
            "cudnn_version": torch.backends.cudnn.version(),
            "optimizer": "torch.optim.AdamW",
            "betas": [0.9, 0.999],
            "epsilon": 1e-8,
            "max_grad_norm": 1.0,
            "loss_normalization": "sum assistant-token CE / tokens in full effective batch",
            "microbatch_order": "stable descending sequence length within each fixed effective batch",
            "numeric_determinism": "seeded and fixed schedule; cross-host bit identity is not claimed",
        },
    )
    milestones = sorted({math.ceil(opts["max_steps"] / 2), opts["max_steps"]})
    checkpoints = []
    log_path = output / "attempts" / f"{attempt}-metrics.jsonl"
    append_log(
        log_path,
        {
            "kind": "session_start",
            "resume_step": first_step,
            "cumulative_trainable_tokens": consumed,
        },
    )
    model.train()
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    for step in range(first_step + 1, opts["max_steps"] + 1):
        indices = schedule[
            (step - 1) * opts["effective_batch_size"] : step * opts["effective_batch_size"]
        ]
        # Reordering only *within* an already frozen effective batch does not
        # change examples, token weights, or the step's mathematical objective.
        items = sorted(
            (data["train"][i] for i in indices),
            key=lambda row: row["sequence_tokens"],
            reverse=True,
        )
        total_tokens = sum(row["trainable_tokens"] for row in items)
        optimizer.zero_grad(set_to_none=True)
        weighted_loss = 0.0
        for offset in range(0, len(items), opts["micro_batch_size"]):
            chunk = items[offset : offset + opts["micro_batch_size"]]
            tokens = sum(row["trainable_tokens"] for row in chunk)
            batch = collate(
                chunk, pad_token_id=tokenizer.pad_token_id, torch_module=torch, device="cuda:0"
            )
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                loss = model(**batch).loss
            if not bool(torch.isfinite(loss)):
                raise RuntimeError(f"nonfinite training loss at step {step}")
            (loss * (tokens / total_tokens)).backward()
            weighted_loss += float(loss.detach()) * tokens / total_tokens
        grad_norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
        lr_used = optimizer.param_groups[0]["lr"]
        optimizer.step()
        scheduler.step()
        consumed += total_tokens
        if step == 1 or step % opts["logging_steps"] == 0 or step in milestones:
            append_log(
                log_path,
                {
                    "kind": "train_step",
                    "step": step,
                    "loss": weighted_loss,
                    "grad_norm": float(grad_norm),
                    "learning_rate": lr_used,
                    "effective_rows": len(items),
                    "trainable_tokens": total_tokens,
                    "cumulative_trainable_tokens": consumed,
                    "elapsed_seconds": time.monotonic() - started,
                },
            )
        if step in milestones:
            evaluation = evaluate(
                model,
                data["dev"],
                tokenizer=tokenizer,
                torch=torch,
                batch_size=opts["eval_batch_size"],
            )
            append_log(log_path, {"kind": "scheduled_dev", "step": step, **evaluation})
            checkpoints.append(
                save_checkpoint(
                    model,
                    optimizer,
                    scheduler,
                    torch=torch,
                    output=output,
                    step=step,
                    config_sha=config_sha,
                    source_hashes=source_hashes,
                    consumed_tokens=consumed,
                )
            )
    if consumed != prep["schedule"]["trainable_tokens"]:
        raise RuntimeError("consumed token budget differs from admitted deterministic schedule")
    surviving = sorted(
        (output / "checkpoints").glob("checkpoint-*"),
        key=lambda path: int(path.name.removeprefix("checkpoint-")),
    )
    if [read_json(path / "COMPLETE.json")["step"] for path in surviving] != milestones:
        raise RuntimeError("missing or unexpected half/end checkpoints")
    torch.cuda.synchronize()
    return {
        "completed_steps": opts["max_steps"],
        "resumed_from_step": first_step,
        "consumed_trainable_tokens": consumed,
        "session_checkpoints": checkpoints,
        "milestones": milestones,
        "checkpoint_selection": "deferred to external generated development review",
        "all_checkpoints": [tree_receipt(path) for path in surviving],
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(),
        "training_wall_seconds": time.monotonic() - started,
        "metrics": file_receipt(log_path),
    }


def run(args):
    config_ref = verify_ref(
        {"path": str(Path(args.config).absolute()), "sha256": args.config_sha256}
    )
    config = read_json(args.config)
    validate_config(config, preflight=args.preflight_only)
    output = Path(config["output"])
    if output.is_symlink():
        raise AdmissionError("output cannot be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    attempt = f"{time.time_ns()}-{os.getpid()}"
    # The output lock protects provenance even for CPU-only preflight.
    with exclusive_lock(output / ".run.lock"):
        if (output / "COMPLETED.json").exists():
            raise AdmissionError("completed run is immutable")
        try:
            sources = source_receipts()
            source_hashes = {k: v["sha256"] for k, v in sources.items()}
            if args.resume and (
                args.preflight_only or not args.resume_sha256 or not args.resume_reason
            ):
                raise AdmissionError(
                    "resume requires exact hash and explicit diagnosis/reason, not preflight"
                )
            if not args.resume and (args.resume_sha256 or args.resume_reason):
                raise AdmissionError("orphan resume hash/reason")
            frozen = output / "resolved-config.json"
            resumed = None
            if args.resume:
                prior = read_json(frozen)
                if (
                    prior["config"] != config
                    or prior["config_file"]["sha256"] != config_ref["sha256"]
                ):
                    raise AdmissionError("resume cannot change frozen config")
                if {k: v["sha256"] for k, v in prior["sources"].items()} != source_hashes:
                    raise AdmissionError("resume cannot change trainer source")
                resumed = verify_resume(
                    args.resume,
                    args.resume_sha256,
                    output=output,
                    config_sha=config_ref["sha256"],
                    source_hashes=source_hashes,
                )
                resumed["tree_sha256"] = args.resume_sha256
            elif frozen.exists() and not args.preflight_only:
                raise AdmissionError(
                    "existing attempt requires explicit resume; never retry automatically"
                )
            prepared = prepare(config, preflight=args.preflight_only)
            receipt = {
                "schema_version": 1,
                "config_file": config_ref,
                "config": config,
                "sources": sources,
                "environment": environment_receipt(),
                "prepared": prepared[3],
            }
            if args.resume and (
                prior["prepared"] != receipt["prepared"]
                or prior["environment"]["packages"] != receipt["environment"]["packages"]
            ):
                raise AdmissionError("resume tokenization/data or package versions changed")
            if args.preflight_only:
                path = output / "preflights" / f"{attempt}.json"
                write_new(path, receipt)
                return {
                    "status": "preflight_only",
                    "receipt": file_receipt(path),
                    "scheduled_trainable_tokens": prepared[3]["schedule"]["trainable_tokens"],
                }
            if not args.resume:
                write_new(frozen, receipt)
            write_new(
                output / "attempts" / f"{attempt}-request.json",
                {
                    "config_sha256": config_ref["sha256"],
                    "resume": str(args.resume) if args.resume else None,
                    "resume_sha256": args.resume_sha256,
                    "resume_reason": args.resume_reason,
                    "previous_failures": [
                        file_receipt(p) for p in sorted((output / "failures").glob("*.json"))
                    ],
                    "pid": os.getpid(),
                    "started_unix": time.time(),
                    "source_sha256": source_hashes,
                },
            )
            # Acquired nonblocking before any CUDA model/context is created.
            with exclusive_lock(config["gpu_lock"]):
                result = train_loop(
                    config,
                    prepared,
                    output=output,
                    attempt=attempt,
                    config_sha=config_ref["sha256"],
                    sources=sources,
                    resume=args.resume,
                    resume_receipt=resumed,
                )
            result.update(
                schema_version=1,
                status="complete",
                run_id=config["run_id"],
                config_sha256=config_ref["sha256"],
                resolved_config=file_receipt(frozen),
                ended_unix=time.time(),
                source_sha256=source_hashes,
            )
            if {k: v["sha256"] for k, v in source_receipts().items()} != source_hashes:
                raise AdmissionError("trainer source changed during the run")
            if sha256_file(args.config) != config_ref["sha256"]:
                raise AdmissionError("config bytes changed during the run")
            # Bind all attempts (including failed-session logs), not just the
            # successful final session. The terminal seal itself is excluded.
            result["run_inventory"] = tree_receipt(output)
            write_new(output / "COMPLETED.json", result)
            return result
        except BaseException as exc:
            write_new(
                output / "failures" / f"{attempt}.json",
                {
                    "status": "failed",
                    "run_id": config["run_id"],
                    "config_sha256": config_ref["sha256"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "time_unix": time.time(),
                    "preflight_only": args.preflight_only,
                    "resume": str(args.resume) if args.resume else None,
                    "automatic_retry": False,
                },
            )
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--resume-sha256")
    parser.add_argument("--resume-reason")
    args = parser.parse_args(argv)

    def stopped(signum, _frame):
        raise InterruptedError(f"received signal {signum}; no automatic retry")

    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    print(json.dumps(run(args), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
