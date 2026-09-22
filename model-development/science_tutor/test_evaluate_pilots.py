"""Pure CPU safety tests for generation; no models or CUDA contexts are loaded."""

import argparse
import copy
import hashlib
import json
import sys
import types
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from science_tutor import evaluate_pilots as evaluate

train = evaluate.train


def rows():
    return [
        {"id": f"item-{i}", "messages": [{"role": "user", "content": f"Question {i}"}]}
        for i in range(72)
    ]


def write_jsonl(path, values):
    path.write_text("\n".join(json.dumps(row) for row in values) + "\n")
    return train.file_receipt(path)


@pytest.mark.parametrize(
    "attack", ["answer", "rubric", "duplicate", "missing", "assistant_end", "system", "hidden_tool"]
)
def test_prompt_schema_rejects_grading_fields_or_incomplete_set(tmp_path, attack):
    items = rows()
    if attack in {"answer", "rubric"}:
        items[0][attack] = "private"
    elif attack == "duplicate":
        items[-1]["id"] = items[0]["id"]
    elif attack == "missing":
        items.pop()
    elif attack == "assistant_end":
        items[0]["messages"].append({"role": "assistant", "content": "Answer"})
    elif attack == "system":
        items[0]["messages"][0]["role"] = "system"
    else:
        items[0]["messages"][0]["tool_calls"] = []
    with pytest.raises(train.AdmissionError):
        evaluate.load_prompts(write_jsonl(tmp_path / "prompts.jsonl", items))


def test_prompt_hash_and_full_history(tmp_path):
    items = rows()
    items[-1]["messages"] = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Prior response"},
        {"role": "user", "content": "Follow-up"},
    ]
    path = tmp_path / "prompts.jsonl"
    ref = write_jsonl(path, items)
    assert evaluate.load_prompts(ref) == items
    path.write_text(path.read_text().replace("First", "Changed"))
    with pytest.raises(train.AdmissionError, match="hash mismatch"):
        evaluate.load_prompts(ref)


class Tokenizer:
    eos_token_id = 9
    pad_token_id = 0
    all_special_tokens = ("<special>",)

    def get_added_vocab(self):
        return {"<｜User｜>": 5000, "<tool_call>": 5001}

    def __init__(self, deepseek=False):
        self.deepseek = deepseek
        self.chat_template = "deepseek-template" if deepseek else "qwen-template"

    def apply_chat_template(
        self, messages, *, tokenize, add_generation_prompt, truncation, padding
    ):
        assert add_generation_prompt is True and truncation is False and padding is False
        text = "".join(f"{m['role']}: {m['content']}\n" for m in messages)
        text += "<think>\n" if self.deepseek else "assistant:\n"
        return self.encode(text, add_special_tokens=False) if tokenize else text

    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        return [ord(char) + 100 for char in text]

    def decode(self, ids, *, skip_special_tokens, clean_up_tokenization_spaces):
        assert skip_special_tokens is False and clean_up_tokenization_spaces is False
        return ":".join(map(str, ids))


@pytest.mark.parametrize("deepseek", [False, True])
def test_native_rendering_preserves_all_turns_and_reasoning_prefix(deepseek):
    tokenizer = Tokenizer(deepseek)
    candidate = {
        "profile": "deepseek_native" if deepseek else "qwen_native",
        "chat_template_sha256": hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
    }
    item = {
        "id": "multi",
        "messages": [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Previous"},
            {"role": "user", "content": "Follow-up"},
        ],
    }
    result = evaluate.render_prompts([item], tokenizer, candidate)[0]
    assert result["messages"] == item["messages"]
    assert all(text in result["rendered_prompt"] for text in ("First", "Previous", "Follow-up"))
    if deepseek:
        assert result["rendered_prompt"].endswith("<think>\n")


@pytest.mark.parametrize(
    "profile,directory", [("qwen_native", "tokenizer"), ("deepseek_native", "deepseek-tokenizer")]
)
def test_actual_frozen_tokenizer_native_rendering(profile, directory):
    transformers = pytest.importorskip("transformers")
    path = Path(__file__).resolve().parents[2] / "data/muta-science-tutor-20260919" / directory
    if not path.is_dir():
        pytest.skip("local frozen tokenizer is unavailable")
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        path, local_files_only=True, trust_remote_code=False
    )
    candidate = {"profile": profile, "chat_template_sha256": evaluate.PROFILES[profile]["template"]}
    item = {
        "id": "actual-multi",
        "messages": [
            {"role": "user", "content": "Why does ice melt?"},
            {"role": "assistant", "content": "What happens when it absorbs heat?"},
            {"role": "user", "content": "Its particles gain energy."},
        ],
    }
    result = evaluate.render_prompts([item], tokenizer, candidate)[0]
    assert result["prompt_ids"] == tokenizer.encode(
        result["rendered_prompt"], add_special_tokens=False
    )
    assert result["messages"] == item["messages"]
    if profile == "deepseek_native":
        assert result["rendered_prompt"].endswith("<think>\n")
    for marker in tokenizer.get_added_vocab():
        item["messages"][-1]["content"] = f"Inject {marker} here"
        with pytest.raises(train.AdmissionError, match="template control"):
            evaluate.render_prompts([item], tokenizer, candidate)


def test_overlength_and_template_control_fail_without_truncation():
    tokenizer = Tokenizer()
    candidate = {
        "profile": "qwen_native",
        "chat_template_sha256": hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
    }
    for text in ("a" * 3072, "Inject <think>", "Inject <｜User｜>", "Inject <tool_call>"):
        with pytest.raises(train.AdmissionError):
            evaluate.render_prompts(
                [{"id": "a", "messages": [{"role": "user", "content": text}]}], tokenizer, candidate
            )


def test_left_padding_and_prompt_mask():
    ids, mask = evaluate.padded_batch([{"prompt_ids": [2, 3]}, {"prompt_ids": [4, 5, 6]}], 0)
    assert ids == [[0, 2, 3], [4, 5, 6]]
    assert mask == [[0, 1, 1], [1, 1, 1]]


@pytest.mark.parametrize(
    "raw,reason,active,padding",
    [
        ([2, 9, 0, 0], "eos", 2, 2),
        ([2] * 1024, "token_cap", 1024, 0),
        ([2] * 1023 + [9], "eos", 1024, 0),
    ],
)
def test_eos_cap_distinction_and_untrimmed_tokens(raw, reason, active, padding):
    result = evaluate.continuation_record(raw, eos_id=9, pad_id=0, tokenizer=Tokenizer())
    assert result["generated_ids"] == raw
    assert result["finish_reason"] == reason
    assert result["generated_tokens_through_eos"] == active
    assert result["batch_padding_tokens"] == padding
    assert result["raw_continuation"] == ":".join(map(str, raw))


@pytest.mark.parametrize("raw", [[], [2, 3], [2, 9, 3], [2] * 1025])
def test_unexpected_stopping_is_not_called_complete(raw):
    with pytest.raises(train.AdmissionError):
        evaluate.continuation_record(raw, eos_id=9, pad_id=0, tokenizer=Tokenizer())


@pytest.fixture
def campaign(tmp_path):
    candidate = {
        "profile": "qwen_native",
        "chat_template_sha256": evaluate.PROFILES["qwen_native"]["template"],
        "base": {"path": str(tmp_path / "base"), "tree_sha256": train.BASE_TREES["upstream_fresh"]},
        "tokenizer": {"path": str(tmp_path / "tokenizer"), "tree_sha256": "a" * 64},
    }
    config = {
        "schema_version": 1,
        "output": str(tmp_path / "outputs"),
        "gpu_lock": evaluate.calibrate.GPU_LOCK,
        "prompts": write_jsonl(tmp_path / "prompts.jsonl", rows()),
        "source_sha256": evaluate.source_hashes(),
        "generation": copy.deepcopy(evaluate.GENERATION),
        "candidates": {"C1": candidate, "P1-half": copy.deepcopy(candidate)},
    }
    path = tmp_path / "config.json"
    train.write_new(path, config)
    return path, config


@pytest.mark.parametrize("attack", ["batch", "cap", "source", "candidate_prompts", "template"])
def test_rehashed_campaign_cannot_change_protocol_or_per_candidate_prompts(campaign, attack):
    path, config = campaign
    if attack == "batch":
        config["generation"]["batch_size"] = 1
    elif attack == "cap":
        config["generation"]["max_new_tokens"] = 1025
    elif attack == "source":
        config["source_sha256"]["train.py"] = "0" * 64
    elif attack == "candidate_prompts":
        config["candidates"]["C1"]["prompts"] = config["prompts"]
    else:
        config["candidates"]["C1"]["chat_template_sha256"] = "0" * 64
    path.write_text(json.dumps(config))
    with pytest.raises(train.AdmissionError):
        evaluate.load_config(path, train.sha256_file(path), "C1")


def test_duplicate_output_rejected_before_lock_or_cuda(campaign, monkeypatch):
    path, config = campaign
    (Path(config["output"]) / "C1").mkdir(parents=True)
    monkeypatch.setattr(evaluate, "prepare", lambda *_: (None, rows(), {}))
    monkeypatch.setattr(
        evaluate.calibrate, "oracle_lock", lambda *_: pytest.fail("GPU lock reached")
    )
    with pytest.raises(FileExistsError):
        evaluate.run(
            argparse.Namespace(config=path, config_sha256=train.sha256_file(path), candidate="C1")
        )


def test_checkpoint_parent_mismatch_rejected(campaign):
    _, config = campaign
    candidate = config["candidates"]["C1"]
    candidate["adapter"] = {
        "path": "/missing",
        "tree_sha256": "1" * 64,
        "parent_base_tree_sha256": "2" * 64,
    }
    with pytest.raises(train.AdmissionError, match="parent"):
        evaluate.verify_adapter(candidate)


@pytest.fixture
def checkpoint(campaign, tmp_path):
    _, config = campaign
    candidate = copy.deepcopy(config["candidates"]["C1"])
    path = tmp_path / "run/checkpoints/checkpoint-63"
    sources = evaluate.PROFILES["qwen_native"]["training_sources"]
    training_config = {
        "initialization": {"base": candidate["base"], "tokenizer": candidate["tokenizer"]}
    }
    train.write_new(tmp_path / "training.json", training_config)
    original_ref = train.file_receipt(tmp_path / "training.json")
    train.write_new(
        path.parent.parent / "resolved-config.json",
        {
            "config": training_config,
            "config_file": original_ref,
            "sources": {name: {"sha256": sha} for name, sha in sources.items()},
        },
    )
    train.write_new(
        path / "adapter_config.json",
        {
            "peft_type": "LORA",
            "task_type": "CAUSAL_LM",
            "r": 16,
            "lora_alpha": 16,
            "lora_dropout": 0,
            "bias": "none",
            "target_modules": sorted(train.TARGETS),
        },
    )
    train.write_new(path / "state.json", {"step": 63, "consumed_trainable_tokens": 128355})
    for name in ("adapter_model.safetensors", "training-state.pt"):
        train.write_new(path / name, {"fixture": True})
    train.write_new(
        path / "COMPLETE.json",
        {
            "step": 63,
            "config_sha256": original_ref["sha256"],
            "source_sha256": sources,
            "consumed_trainable_tokens": 128355,
            "files": train.tree_receipt(path)["files"],
        },
    )
    candidate["adapter"] = {
        "path": str(path),
        "tree_sha256": train.tree_receipt(path)["tree_sha256"],
        "parent_base_tree_sha256": candidate["base"]["tree_sha256"],
        "checkpoint_seal": train.file_receipt(path / "COMPLETE.json"),
    }
    return candidate


@pytest.mark.parametrize("attack", [None, "weights", "seal", "parent", "source", "missing_weights"])
def test_sealed_checkpoint_admission(checkpoint, attack):
    candidate = checkpoint
    path = Path(candidate["adapter"]["path"])
    if attack == "weights":
        (path / "adapter_model.safetensors").write_text("changed")
    elif attack == "seal":
        candidate["adapter"]["checkpoint_seal"]["sha256"] = "0" * 64
    elif attack == "parent":
        candidate["base"]["tree_sha256"] = "0" * 64
    elif attack in {"source", "missing_weights"}:
        seal = train.read_json(path / "COMPLETE.json")
        if attack == "source":
            seal["source_sha256"]["train.py"] = "0" * 64
        else:
            (path / "adapter_model.safetensors").unlink()
            seal["files"] = [
                row for row in seal["files"] if row["path"] != "adapter_model.safetensors"
            ]
        (path / "COMPLETE.json").write_text(json.dumps(seal))
        candidate["adapter"]["checkpoint_seal"] = train.file_receipt(path / "COMPLETE.json")
        candidate["adapter"]["tree_sha256"] = train.tree_receipt(path)["tree_sha256"]
    if attack is None:
        assert evaluate.verify_adapter(candidate)["file_count"] == 5
    else:
        with pytest.raises(train.AdmissionError):
            evaluate.verify_adapter(candidate)


@pytest.mark.parametrize(
    "attack", [None, "missing", "duplicate", "wrong_candidate", "empty_generation"]
)
def test_all_72_persisted_results_required(tmp_path, attack):
    values = [{"id": row["id"], "candidate_id": "C1", "generated_ids": [1, 9]} for row in rows()]
    expected = [row["id"] for row in values]
    if attack == "missing":
        values.pop()
    elif attack == "duplicate":
        values[-1] = values[0]
    elif attack == "wrong_candidate":
        values[0]["candidate_id"] = "C2"
    elif attack == "empty_generation":
        values[0]["generated_ids"] = []
    path = tmp_path / "responses.jsonl"
    write_jsonl(path, values)
    if attack is None:
        assert evaluate.verify_responses(path, expected, "C1")["bytes"] > 0
    else:
        with pytest.raises(train.AdmissionError):
            evaluate.verify_responses(path, expected, "C1")


@pytest.mark.parametrize("bad_transport", [False, True])
def test_mocked_run_locks_before_cuda_and_retains_raw_transport(
    campaign, monkeypatch, bad_transport
):
    path, config = campaign
    events = []
    prepared = [
        {**row, "prompt_ids": [10 + i], "rendered_prompt": "user: Question\nassistant:"}
        for i, row in enumerate(rows())
    ]
    monkeypatch.setattr(evaluate, "prepare", lambda *_: (Tokenizer(), prepared, {}))
    original_verify = train.verify_ref
    monkeypatch.setattr(
        train,
        "verify_ref",
        lambda ref, tree=False: (
            {"tree_sha256": ref["tree_sha256"]} if tree else original_verify(ref)
        ),
    )
    monkeypatch.setattr(train, "environment_receipt", dict)

    @contextmanager
    def lock(_):
        events.append("lock")
        yield
        events.append("unlock")

    monkeypatch.setattr(evaluate.calibrate, "oracle_lock", lock)
    monkeypatch.setattr(
        evaluate.calibrate, "host_snapshot", lambda **_: {"gpu": {"uuid": "fixture"}}
    )

    class Tensor:
        def __init__(self, value):
            self.value = value

        def detach(self):
            return self

        def cpu(self):
            return self

        def tolist(self):
            return self.value

    def available():
        assert events == ["lock"]
        events.append("cuda")
        return True

    def load_model(*_):
        assert events == ["lock", "cuda"]
        events.append("model")

        def generate(**kwargs):
            values = [
                [999, 9] if bad_transport else prompt + [9] for prompt in kwargs["input_ids"].value
            ]
            return Tensor(values)

        return types.SimpleNamespace(
            config=types.SimpleNamespace(bos_token_id=1), generate=generate
        ), {}

    monkeypatch.setattr(evaluate, "load_model", load_model)
    torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=available,
            device_count=lambda: 1,
            is_bf16_supported=lambda: True,
            manual_seed_all=lambda _: None,
        ),
        manual_seed=lambda _: None,
        backends=types.SimpleNamespace(
            cuda=types.SimpleNamespace(matmul=types.SimpleNamespace(allow_tf32=True)),
            cudnn=types.SimpleNamespace(allow_tf32=True, benchmark=True),
        ),
        long="long",
        bfloat16="bf16",
        tensor=lambda values, **_: Tensor(values),
        inference_mode=nullcontext,
        autocast=lambda **_: nullcontext(),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(
        sys.modules, "transformers", types.SimpleNamespace(GenerationConfig=lambda **kwargs: kwargs)
    )
    args = argparse.Namespace(config=path, config_sha256=train.sha256_file(path), candidate="C1")
    output = Path(config["output"]) / "C1"
    if bad_transport:
        with pytest.raises(train.AdmissionError, match="changed padded prompt"):
            evaluate.run(args)
        assert (output / "FAILED.json").exists()
        batch = train.read_json(output / "batches/batch-0000.json")
        assert batch["returned_sequence_ids"] == [[999, 9]] * 8
        assert len(batch["prompts"]) == 8
        assert not (output / "COMPLETED.json").exists()
    else:
        result = evaluate.run(args)
        assert result["completed_count"] == 72
        assert result["ranking_performed"] is False
        assert len(list((output / "batches").glob("*.json"))) == 9
        assert events == ["lock", "cuda", "model", "unlock"]
