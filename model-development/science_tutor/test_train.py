"""Small admission/schedule/resume tests. No real GPU model is loaded."""

import argparse
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from science_tutor import train
from science_tutor.tokenization import digest


def row(name, group=None):
    return {
        "id": name,
        "group_id": group or name,
        "source": "fixture",
        "source_revision": "frozen",
        "source_id": name,
        "license": "CC0",
        "subject": "physics",
        "capabilities": ["causal"],
        "quality": {"status": "verified"},
        "messages": [
            {"role": "user", "content": "Why?"},
            {"role": "assistant", "content": "Because."},
        ],
    }


@pytest.fixture
def config(tmp_path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    (base / "config.json").write_text("{}")
    tokenizer = tmp_path / "tokenizer"
    tokenizer.mkdir()
    (tokenizer / "tokenizer.json").write_text("{}")
    (tokenizer / "tokenizer_config.json").write_text("{}")
    monkeypatch.setattr(
        train, "TOKENIZER_FILES", {p.name: train.sha256_file(p) for p in tokenizer.iterdir()}
    )
    base_ref = {"path": str(base), "tree_sha256": train.tree_receipt(base)["tree_sha256"]}
    monkeypatch.setitem(train.BASE_TREES, "upstream_fresh", base_ref["tree_sha256"])
    raw = {"train": [row("a"), row("b"), row("c")], "dev": [row("d")]}
    refs, admit = (
        {},
        {
            "schema_version": 1,
            "status": "admitted",
            "group_disjoint": True,
            "overlength_policy": "excluded_before_freeze",
        },
    )
    for split, rows in raw.items():
        path = tmp_path / f"{split}.jsonl"
        path.write_text("".join(json.dumps(x) + "\n" for x in rows))
        refs[split] = train.file_receipt(path)
        admit[split] = {
            "sha256": refs[split]["sha256"],
            "rows": len(rows),
            "row_ids_sha256": digest(sorted(r["id"] for r in rows)),
        }
    admission = tmp_path / "admission.json"
    train.write_new(admission, admit)
    refs["admission"] = train.file_receipt(admission)
    result = {
        "schema_version": 1,
        "run_id": "fixture",
        "output": str(tmp_path / "out"),
        "gpu_lock": str(tmp_path / "shared.lock"),
        "initialization": {
            "kind": "upstream_fresh",
            "base": base_ref,
            "tokenizer": {
                "path": str(tokenizer),
                "tree_sha256": train.tree_receipt(tokenizer)["tree_sha256"],
            },
        },
        "data": refs,
        "tokenization": {
            "max_length": 4096,
            "chat_template_sha256": train.hashlib.sha256(b"fixture").hexdigest(),
            "split_policy": "preserve_whole_conversation",
        },
        "training": {
            "seed": 19,
            "micro_batch_size": 1,
            "gradient_accumulation": 2,
            "effective_batch_size": 2,
            "max_steps": 2,
            "expected_trainable_tokens": 8,
            "learning_rate": 1e-5,
            "weight_decay": 0,
            "warmup_ratio": 0.03,
            "logging_steps": 1,
            "eval_batch_size": 1,
        },
        "lora": {"r": 16, "alpha": 16, "dropout": 0, "target_modules": sorted(train.TARGETS)},
    }

    class FakeAutoTokenizer:
        @classmethod
        def from_pretrained(cls, *_args, **kwargs):
            assert kwargs == {"local_files_only": True, "trust_remote_code": False}
            return types.SimpleNamespace(chat_template="fixture", pad_token_id=0)

    monkeypatch.setitem(
        sys.modules, "transformers", types.SimpleNamespace(AutoTokenizer=FakeAutoTokenizer)
    )

    def fake_tokens(messages, **_kwargs):
        return {
            "input_ids": [1, 2, 3],
            "labels": [-100, 2, 3],
            "attention_mask": [1, 1, 1],
            "trainable_tokens": 2,
            "sequence_tokens": 3,
            "assistant_turns": 1,
            "assistant_spans": [{"start": 1, "stop": 3}],
            "messages_sha256": digest(messages),
            "input_ids_sha256": digest([1, 2, 3]),
            "labels_sha256": digest([-100, 2, 3]),
        }

    monkeypatch.setattr(train, "tokenize_messages", fake_tokens)
    return result


def test_prepare_exact_counts_budget_and_no_hidden_exclusions(config):
    _tokenizer, data, schedule, receipt = train.prepare(config)
    assert len(data["train"]) == 3 and len(schedule) == 4
    assert receipt["counts"]["train"]["trainable_tokens"] == 6
    assert receipt["schedule"]["trainable_tokens"] == 8
    assert receipt["schedule"]["repeated_tail_rows"] == 1
    assert receipt["schedule"]["repeated_tail_trainable_tokens"] == 2
    assert receipt["counts"]["train"]["excluded_by_trainer"] == 0
    assert all("messages" not in r and "input_ids" not in r for r in receipt["row_receipts"])


def test_schedule_equal_across_microbatch_choices(config):
    first = train.prepare(config)[2:]
    config["training"].update(micro_batch_size=2, gradient_accumulation=1)
    second = train.prepare(config)[2:]
    assert first == second


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c["training"].update(gradient_accumulation=3),
        lambda c: c["training"].update(max_steps=3),
        lambda c: c["training"].update(expected_trainable_tokens=7),
        lambda c: c["training"].update(learning_rate=float("nan")),
        lambda c: c["training"].update(seed=True),
        lambda c: c["training"].update(expected_trainable_tokens=None),
        lambda c: c["tokenization"].update(split_policy="truncate"),
        lambda c: c["tokenization"].update(chat_template_sha256="0" * 64),
        lambda c: c["initialization"].update(adapter={}),
        lambda c: c["initialization"]["base"].update(tree_sha256="0" * 64),
        lambda c: c["data"]["train"].update(sha256="0" * 64),
        lambda c: c["lora"].update(dropout=0.1),
        lambda c: c["lora"].update(target_modules=["q_proj"]),
    ],
)
def test_config_or_admission_mismatch_fails_closed(config, change):
    change(config)
    with pytest.raises(train.AdmissionError):
        train.prepare(config)


def test_preflight_can_measure_unfrozen_budget_but_training_cannot(config):
    config["training"]["expected_trainable_tokens"] = None
    assert train.prepare(config, preflight=True)[3]["schedule"]["trainable_tokens"] == 8
    with pytest.raises(train.AdmissionError):
        train.prepare(config)


def test_group_leakage_is_detected_even_if_file_admitted(config):
    path = Path(config["data"]["dev"]["path"])
    path.write_text(json.dumps(row("d", group="a")) + "\n")
    config["data"]["dev"] = train.file_receipt(path)
    admission_path = Path(config["data"]["admission"]["path"])
    admission = train.read_json(admission_path)
    admission["dev"]["sha256"] = config["data"]["dev"]["sha256"]
    admission_path.write_text(json.dumps(admission))
    config["data"]["admission"] = train.file_receipt(admission_path)
    with pytest.raises(train.AdmissionError, match="group crosses"):
        train.prepare(config)


def test_common_tokenizer_hash_and_base_adapter_checks(config):
    tok = Path(config["initialization"]["tokenizer"]["path"])
    (tok / "tokenizer.json").write_text("changed")
    config["initialization"]["tokenizer"]["tree_sha256"] = train.tree_receipt(tok)["tree_sha256"]
    with pytest.raises(train.AdmissionError, match="common upstream"):
        train.prepare(config)


def test_rows_duplicate_missing_metadata_and_empty_file(tmp_path):
    path = tmp_path / "rows.jsonl"
    for content in [json.dumps(row("a")) + "\n" + json.dumps(row("a")), "", "{}\n", "\n"]:
        path.write_text(content)
        with pytest.raises(train.AdmissionError):
            train.load_rows(path)


def test_tree_inventory_refuses_symlinks_and_is_path_independent(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x").write_bytes(b"same")
    (b / "x").write_bytes(b"same")
    assert train.tree_receipt(a)["tree_sha256"] == train.tree_receipt(b)["tree_sha256"]
    (a / "link").symlink_to(b / "x")
    with pytest.raises(train.AdmissionError, match="symlink"):
        train.tree_receipt(a)


def test_shared_gpu_lock_is_nonblocking(tmp_path):
    path = tmp_path / "lock"
    with (
        train.exclusive_lock(path),
        pytest.raises(train.AdmissionError, match="already owned"),
        train.exclusive_lock(path),
    ):
        pass
    with train.exclusive_lock(path):
        pass


def test_write_receipts_never_overwrites(tmp_path):
    path = tmp_path / "receipt.json"
    train.write_new(path, {"original": True})
    with pytest.raises(FileExistsError):
        train.write_new(path, {"original": False})
    assert train.read_json(path) == {"original": True}


def make_checkpoint(output, step=1):
    path = output / "checkpoints" / f"checkpoint-{step}"
    path.mkdir(parents=True)
    (path / "adapter_model.safetensors").write_bytes(b"fixture")
    (path / "training-state.pt").write_bytes(b"fixture-state")
    files = train.tree_receipt(path)["files"]
    train.write_new(
        path / "COMPLETE.json",
        {"step": step, "config_sha256": "c", "source_sha256": {"train.py": "s"}, "files": files},
    )
    return path


def test_resume_exact_own_latest_complete_hash_bound_checkpoint(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    kwargs = {"output": tmp_path, "config_sha": "c", "source_hashes": {"train.py": "s"}}
    sha = train.tree_receipt(checkpoint)["tree_sha256"]
    assert train.verify_resume(checkpoint, sha, **kwargs)["step"] == 1
    with pytest.raises(train.AdmissionError, match="config/source"):
        train.verify_resume(checkpoint, sha, **{**kwargs, "config_sha": "changed"})
    with pytest.raises(train.AdmissionError, match="tree hash"):
        train.verify_resume(checkpoint, "0" * 64, **kwargs)
    make_checkpoint(tmp_path, 2)
    with pytest.raises(train.AdmissionError, match="latest"):
        train.verify_resume(checkpoint, sha, **kwargs)


def test_incomplete_checkpoint_blocks_resume(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    sha = train.tree_receipt(checkpoint)["tree_sha256"]
    (tmp_path / "checkpoints/checkpoint-2").mkdir()
    with pytest.raises(train.AdmissionError, match="incomplete"):
        train.verify_resume(
            checkpoint, sha, output=tmp_path, config_sha="c", source_hashes={"train.py": "s"}
        )


def test_preflight_never_loads_model_or_touches_gpu(config, monkeypatch):
    path = Path(config["output"]).parent / "config.json"
    train.write_new(path, config)
    monkeypatch.setattr(train, "train_loop", lambda *_a, **_k: pytest.fail("must not train"))
    result = train.run(
        argparse.Namespace(
            config=path,
            config_sha256=train.sha256_file(path),
            preflight_only=True,
            resume=None,
            resume_sha256=None,
            resume_reason=None,
        )
    )
    assert result["status"] == "preflight_only"
    assert not Path(config["gpu_lock"]).exists()
    assert not (Path(config["output"]) / "COMPLETED.json").exists()


def test_failure_is_recorded_and_no_implicit_retry(config, monkeypatch):
    path = Path(config["output"]).parent / "config.json"
    train.write_new(path, config)
    calls = []

    def fail(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("synthetic CUDA failure")

    monkeypatch.setattr(train, "train_loop", fail)
    args = argparse.Namespace(
        config=path,
        config_sha256=train.sha256_file(path),
        preflight_only=False,
        resume=None,
        resume_sha256=None,
        resume_reason=None,
    )
    with pytest.raises(RuntimeError, match="synthetic CUDA"):
        train.run(args)
    assert len(list((Path(config["output"]) / "failures").glob("*.json"))) == 1
    with pytest.raises(train.AdmissionError, match="explicit resume"):
        train.run(args)
    assert len(calls) == 1
    assert len(list((Path(config["output"]) / "failures").glob("*.json"))) == 2


def test_completed_run_seals_all_evidence_and_cannot_reexecute(config, monkeypatch):
    path = Path(config["output"]).parent / "config.json"
    train.write_new(path, config)
    monkeypatch.setattr(train, "train_loop", lambda *_args, **_kwargs: {"synthetic": True})
    args = argparse.Namespace(
        config=path,
        config_sha256=train.sha256_file(path),
        preflight_only=False,
        resume=None,
        resume_sha256=None,
        resume_reason=None,
    )
    result = train.run(args)
    assert result["status"] == "complete"
    files = result["run_inventory"]["files"]
    assert "COMPLETED.json" not in {r["path"] for r in files}
    assert "resolved-config.json" in {r["path"] for r in files}
    for record in files:
        assert train.sha256_file(Path(config["output"]) / record["path"]) == record["sha256"]
    with pytest.raises(train.AdmissionError, match="immutable"):
        train.run(args)


def test_padding_and_token_normalized_microbatch_gradient_cpu():
    torch = pytest.importorskip("torch")
    items = [
        {"input_ids": [1, 2, 3], "attention_mask": [1, 1, 1], "labels": [-100, 2, 3]},
        {"input_ids": [1, 3], "attention_mask": [1, 1], "labels": [-100, 3]},
    ]
    batch = train.collate(items, pad_token_id=0, torch_module=torch, device="cpu")
    assert batch["labels"].tolist() == [[-100, 2, 3], [-100, 3, -100]]
    assert batch["attention_mask"].tolist() == [[1, 1, 1], [1, 1, 0]]
    weights = torch.randn(4, 4, requires_grad=True)

    def loss(chunk):
        b = train.collate(chunk, pad_token_id=0, torch_module=torch, device="cpu")
        logits = weights[b["input_ids"]][:, :-1].contiguous()
        return torch.nn.functional.cross_entropy(logits.view(-1, 4), b["labels"][:, 1:].reshape(-1))

    loss(items).backward()
    full_gradient = weights.grad.clone()
    weights.grad = None
    (loss(items[:1]) * (2 / 3)).backward()
    (loss(items[1:]) * (1 / 3)).backward()
    assert torch.allclose(weights.grad, full_gradient, atol=1e-7)


def test_tiny_peft_cpu_checkpoint_exact_restore_and_next_update(tmp_path, monkeypatch):
    """No pretrained weights/GPU: tiny random Qwen, one CPU update, full resume."""
    torch = pytest.importorskip("torch")
    peft = pytest.importorskip("peft")
    transformers = pytest.importorskip("transformers")
    monkeypatch.setattr(torch.cuda, "get_rng_state_all", list)
    model_config = transformers.Qwen2Config(
        vocab_size=16,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=1,
        num_attention_heads=2,
        num_key_value_heads=2,
        max_position_embeddings=32,
        attention_dropout=0.0,
        tie_word_embeddings=False,
    )

    def fresh():
        torch.manual_seed(1)
        base = transformers.Qwen2ForCausalLM(model_config)
        return peft.get_peft_model(
            base,
            peft.LoraConfig(
                r=2,
                lora_alpha=2,
                lora_dropout=0,
                target_modules=sorted(train.TARGETS),
                bias="none",
                task_type="CAUSAL_LM",
            ),
        )

    model = fresh()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=0.001)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda _step: 1.0)
    batch = {
        "input_ids": torch.tensor([[1, 2, 3, 4]]),
        "attention_mask": torch.ones(1, 4, dtype=torch.long),
        "labels": torch.tensor([[-100, -100, 3, 4]]),
    }

    def update(m, opt, sched):
        m.train()
        opt.zero_grad(set_to_none=True)
        loss = m(**batch).loss
        assert torch.isfinite(loss)
        loss.backward()
        opt.step()
        sched.step()

    update(model, optimizer, scheduler)
    receipt = train.save_checkpoint(
        model,
        optimizer,
        scheduler,
        torch=torch,
        output=tmp_path,
        step=1,
        config_sha="config",
        source_hashes={"train.py": "source"},
        consumed_tokens=2,
    )
    checkpoint = Path(receipt["root"])
    assert (
        train.verify_resume(
            checkpoint,
            receipt["tree_sha256"],
            output=tmp_path,
            config_sha="config",
            source_hashes={"train.py": "source"},
        )["step"]
        == 1
    )
    torch.manual_seed(1)
    restored_base = transformers.Qwen2ForCausalLM(model_config)
    restored = peft.PeftModel.from_pretrained(restored_base, checkpoint, is_trainable=True)
    assert train.verify_loaded_adapter(restored, checkpoint, torch)["exact_tensor_values_loaded"]
    assert train._adapter_identity(restored, torch) == train._adapter_identity(model, torch)
    restored_optimizer = torch.optim.AdamW(
        [p for p in restored.parameters() if p.requires_grad], lr=0.001
    )
    restored_scheduler = torch.optim.lr_scheduler.LambdaLR(restored_optimizer, lambda _step: 1.0)
    state = torch.load(checkpoint / "training-state.pt", map_location="cpu", weights_only=False)
    restored_optimizer.load_state_dict(state["optimizer"])
    restored_scheduler.load_state_dict(state["scheduler"])
    update(model, optimizer, scheduler)
    update(restored, restored_optimizer, restored_scheduler)
    assert train._adapter_identity(restored, torch) == train._adapter_identity(model, torch)
