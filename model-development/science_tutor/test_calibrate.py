"""CPU-only admission, memory-policy and backward-only diagnostic tests."""

import argparse
import ast
import json
import os
import sys
import types
from contextlib import nullcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from science_tutor import calibrate as cal


def config(tmp_path):
    return {
        "schema_version": 1,
        "run_id": "calibration-fixture",
        "output": str(tmp_path / "new-output"),
        "gpu_lock": cal.GPU_LOCK,
        "source_manifest": {"path": str(tmp_path / "sources.json"), "sha256": "a" * 64},
        "initialization": {
            "kind": "upstream_fresh",
            "base": {
                "path": str(tmp_path / "base"),
                "tree_sha256": cal.train.BASE_TREES["upstream_fresh"],
            },
            "tokenizer": {"path": str(tmp_path / "tokenizer"), "tree_sha256": "b" * 64},
        },
        "chat_template_sha256": "c" * 64,
    }


def test_bounded_matrix_and_no_optimizer_or_weight_save_calls():
    assert cal.LENGTHS == (512, 2048, 4096)
    assert cal.MICROBATCHES == (1, 2, 4)
    assert cal.WARMUP_ITERATIONS == 1 and cal.MEASURED_ITERATIONS == 2
    parsed = ast.parse(Path(cal.__file__).read_text())
    forbidden = {"step", "save_pretrained", "save_checkpoint", "AdamW", "SGD", "kill", "terminate"}
    assert (
        not {
            node.func.attr
            for node in ast.walk(parsed)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        & forbidden
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(gpu_lock="/tmp/unrelated.lock"),
        lambda value: value.update(output="relative"),
        lambda value: value.update(iterations=500),
        lambda value: value["initialization"].update(kind="pilot_adapter"),
        lambda value: value["initialization"].update(adapter={}),
        lambda value: value["initialization"]["base"].update(tree_sha256="0" * 64),
    ],
)
def test_cannot_expand_or_change_diagnostic_authority(tmp_path, change):
    value = config(tmp_path)
    cal.validate_config(value)
    change(value)
    with pytest.raises(cal.train.AdmissionError):
        cal.validate_config(value)


def test_real_common_tokenizer_fills_exact_lengths_without_control_injection():
    from transformers import AutoTokenizer

    default = Path(__file__).resolve().parents[2] / "data/muta-science-tutor-20260919/tokenizer"
    path = Path(os.environ.get("SCIENCE_TUTOR_TOKENIZER", default))
    if not path.is_dir():
        pytest.skip("common local upstream tokenizer is not staged")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    for length in cal.LENGTHS:
        row = cal.diagnostic_row(tokenizer, length)
        assert len(row["input_ids"]) == len(row["labels"]) == length
        assert row["active_sequence_tokens"] <= length
        assert row["explicit_padding_tokens"] < 8
        assert row["trainable_tokens"] == sum(token != -100 for token in row["labels"][1:])
        assert row["input_ids_sha256"] == cal.train.digest(row["input_ids"])
        assert row["labels_sha256"] == cal.train.digest(row["labels"])
        assert row["assistant_turns"] == 1 and row["diagnostic_only"]
        assert tokenizer.eos_token_id in row["input_ids"]


def test_gpu_csv_and_idle_admission_fail_closed(monkeypatch):
    gpu = "0, GPU-fixture, NVIDIA A100-SXM4-40GB, 40536, 39800\n"
    assert cal.parse_gpu_rows(gpu)[0]["total_bytes"] == 40536 * 1024**2
    with pytest.raises(cal.train.AdmissionError):
        cal.parse_gpu_rows("0, unexpected")

    def run(args, **kwargs):
        assert kwargs["check"] and kwargs["timeout"] == 15
        if args[0] == "ps":
            return types.SimpleNamespace(stdout="1000\n")
        return types.SimpleNamespace(
            stdout=gpu if "--query-gpu=" in args[1] else "123, GPU-fixture, 512\n"
        )

    monkeypatch.setattr(cal.subprocess, "run", run)
    with pytest.raises(cal.train.AdmissionError, match="not idle"):
        cal.host_snapshot()
    assert cal.host_snapshot(own_pid=123)["compute_processes"][0]["uid"] == 1000
    with pytest.raises(cal.train.AdmissionError, match="not idle"):
        cal.host_snapshot(own_pid=999)


def test_lock_exact_uid_owned_nonblocking_and_rejects_symlink(tmp_path, monkeypatch):
    lock = str(tmp_path / "lock")
    monkeypatch.setattr(cal, "GPU_LOCK", lock)
    monkeypatch.setattr(cal, "EXPECTED_UID", cal.os.getuid())
    with cal.oracle_lock(lock), pytest.raises(cal.train.AdmissionError, match="already owned"):  # noqa: SIM117
        with cal.oracle_lock(lock):
            pass
    with cal.oracle_lock(lock) as result:
        assert result["owner_uid"] == cal.os.getuid()
    target = tmp_path / "linked"
    target.symlink_to(lock)
    monkeypatch.setattr(cal, "GPU_LOCK", str(target))
    with pytest.raises(OSError), cal.oracle_lock(str(target)):
        pass


def test_memory_headroom_skips_anticipated_oom_and_uses_measurements():
    kwargs = {
        "microbatch": 1,
        "length": 512,
        "vocab_size": 151936,
        "total_bytes": 40 * cal.GIB,
        "free_bytes": 35 * cal.GIB,
        "measurements": [],
    }
    result = cal.memory_projection(**kwargs)
    assert result["admit"] and result["headroom_bytes"] == 6 * cal.GIB
    assert not cal.memory_projection(
        **{**kwargs, "microbatch": 4, "length": 4096, "free_bytes": 32 * cal.GIB}
    )["admit"]
    records = [
        {
            "status": "measured",
            "microbatch": 1,
            "sequence_length": 512,
            "peak_reserved_increment_bytes": 2 * cal.GIB,
        }
    ]
    observed = cal.memory_projection(**{**kwargs, "microbatch": 2, "measurements": records})
    assert observed["predicted_additional_bytes"] == pytest.approx(2 * cal.GIB * 2 * 1.35, abs=1)
    assert observed["measured_anchor"] == [1, 512]
    assert observed["heuristic_not_oom_guarantee"]


def test_recommendation_only_measured_eligible_fastest_not_largest():
    rows = [
        {
            "status": "measured",
            "microbatch": 1,
            "sequence_length": 512,
            "recommendation_eligible": True,
            "sequence_tokens_per_second": 200,
        },
        {
            "status": "measured",
            "microbatch": 2,
            "sequence_length": 512,
            "recommendation_eligible": True,
            "sequence_tokens_per_second": 100,
        },
        {
            "status": "measured",
            "microbatch": 4,
            "sequence_length": 512,
            "recommendation_eligible": False,
            "sequence_tokens_per_second": 500,
        },
        {"status": "skipped_anticipated_memory_limit", "microbatch": 4, "sequence_length": 4096},
    ]
    result = cal.recommendations(rows)
    assert [item["recommended_microbatch"] for item in result] == [1, None, None]


def test_source_manifest_binds_exact_three_modules(tmp_path):
    manifest = {
        "schema_version": 1,
        "source_revision": "test-only",
        "repository_head_commit": "a" * 40,
        "working_tree_source_snapshot": True,
        "files": {
            name: cal.train.sha256_file(Path(cal.__file__).with_name(name))
            for name in cal.SOURCE_NAMES
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    ref = cal.train.file_receipt(path)
    assert len(cal.verify_sources(ref)["observed_files"]) == 3
    manifest["files"]["train.py"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(cal.train.AdmissionError, match="source hash"):
        cal.verify_sources(cal.train.file_receipt(path))


def test_failed_admission_preserved_no_gpu_and_no_same_output_retry(tmp_path, monkeypatch):
    value = config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value))
    args = argparse.Namespace(config=path, config_sha256=cal.train.sha256_file(path))
    calls = []

    def fail(_config):
        calls.append(1)
        raise cal.train.AdmissionError("fixture admission failure")

    monkeypatch.setattr(cal, "prepare", fail)
    monkeypatch.setattr(
        cal, "host_snapshot", lambda **_kw: pytest.fail("GPU must not be inspected")
    )
    with pytest.raises(cal.train.AdmissionError):
        cal.run(args)
    failure = Path(value["output"]) / "FAILED.json"
    receipt = cal.train.read_json(failure)
    assert not receipt["automatic_retry"] and receipt["completed_cell_count"] == 0
    before = failure.read_bytes()
    with pytest.raises(FileExistsError):
        cal.run(args)
    assert failure.read_bytes() == before and calls == [1]


def test_actual_cpu_backward_does_not_update_parameters(monkeypatch):
    torch = pytest.importorskip("torch")
    fake_cuda = types.SimpleNamespace(
        empty_cache=lambda: None,
        synchronize=lambda: None,
        memory_reserved=lambda: 10,
        memory_allocated=lambda: 10,
        mem_get_info=lambda: (35 * cal.GIB, 40 * cal.GIB),
        reset_peak_memory_stats=lambda: None,
        max_memory_reserved=lambda: 100,
        max_memory_allocated=lambda: 90,
    )
    monkeypatch.setattr(torch, "cuda", fake_cuda)
    monkeypatch.setattr(torch, "autocast", lambda **_kw: nullcontext())
    collate = cal.train.collate
    monkeypatch.setattr(
        cal.train, "collate", lambda rows, **kw: collate(rows, **{**kw, "device": "cpu"})
    )

    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weights = torch.nn.Parameter(torch.randn(8, 8))

        def forward(self, input_ids, labels, attention_mask):
            logits = self.weights[input_ids][:, :-1].contiguous()
            return types.SimpleNamespace(
                loss=torch.nn.functional.cross_entropy(
                    logits.view(-1, 8), labels[:, 1:].reshape(-1)
                )
            )

    model = Toy()
    before = model.weights.detach().clone()
    row = {
        "input_ids": [1, 2, 3],
        "labels": [-100, 2, 3],
        "attention_mask": [1, 1, 1],
        "sequence_tokens": 3,
        "active_sequence_tokens": 3,
        "explicit_padding_tokens": 0,
        "trainable_tokens": 2,
    }
    result = cal.measure_cell(
        model, row, tokenizer=types.SimpleNamespace(pad_token_id=0), torch=torch, microbatch=2
    )
    assert torch.equal(before, model.weights)
    assert model.weights.grad is None
    assert len(result["forward_backward_seconds"]) == 2 and result["warmup_iterations"] == 1
    assert result["sequence_tokens_per_second"] > 0
