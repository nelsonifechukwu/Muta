from __future__ import annotations

import importlib.util
import json
import sys
from math import isclose
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_dataset = _load("build_dataset")
train_lora = _load("train_lora")
build_metric_dataset = _load("build_metric_dataset")
export_base = _load("export_base")


def test_gsm8k_annotations_are_removed_but_reasoning_is_retained():
    result = build_dataset.clean_gsm8k_answer("48/2 = <<48/2=24>>24\n#### 24")
    assert result == "48/2 = 24\nFinal answer: 24"


def test_choice_text_uses_the_label_not_choice_position_assumptions():
    row = {"choices": {"label": ["B", "A"], "text": ["wrong", "right"]}, "answerKey": "A"}
    assert build_dataset.choice_text(row) == "right"


def test_verified_african_examples_are_nonempty_and_exclude_submission_prompt():
    rows = build_dataset.build_african_arithmetic()
    assert len(rows) == 240
    assert all(row["prompt"] and row["completion"] for row in rows)
    assert not any("24 identical crates for 18000" in row["prompt"] for row in rows)


def test_common_prefix_length_handles_boundary_divergence():
    assert train_lora.common_prefix_length([1, 2, 9], [1, 2, 3]) == 2


def test_message_content_uses_typed_blocks_for_multimodal_processor():
    assert train_lora.message_content("hello", multimodal=True) == [
        {"type": "text", "text": "hello"}
    ]
    assert train_lora.message_content("hello", multimodal=False) == "hello"


def test_normalize_token_ids_handles_mapping_and_singleton_batch():
    assert train_lora.normalize_token_ids({"input_ids": [1, 2]}) == [1, 2]
    assert train_lora.normalize_token_ids([[1, 2]]) == [1, 2]


def test_reasoning_profile_removes_replay_and_caps_mathdial():
    records = [
        {"source": "gsm8k_train"},
        {"source": "smoltalk_everyday_train"},
        *({"source": "mathdial_train"} for _ in range(800)),
    ]
    selected = build_dataset.select_profile(records, "reasoning-heavy")
    counts = {
        source: sum(row["source"] == source for row in selected)
        for source in ("gsm8k_train", "smoltalk_everyday_train", "mathdial_train")
    }
    assert counts == {
        "gsm8k_train": 1,
        "smoltalk_everyday_train": 0,
        "mathdial_train": 750,
    }


def test_multimodal_peft_flags_are_not_forwarded_to_text_model():
    assert train_lora.architecture_peft_kwargs(multimodal=False) == {}
    assert train_lora.architecture_peft_kwargs(multimodal=True) == {
        "finetune_vision_layers": False,
        "finetune_language_layers": True,
        "finetune_attention_modules": True,
        "finetune_mlp_modules": True,
    }


def test_raw_completion_boundary_matches_lm_eval_multiple_choice_requests():
    assert train_lora.join_raw_prompt_completion("Question: Why?\nAnswer:", "gravity") == (
        "Question: Why?\nAnswer: gravity"
    )
    assert train_lora.join_raw_prompt_completion("Answer: ", "gravity") == "Answer: gravity"
    assert train_lora.join_raw_prompt_completion("Answer:", " gravity") == "Answer: gravity"


def test_sha256_file_records_exact_training_input(tmp_path):
    source = tmp_path / "train.jsonl"
    source.write_bytes(b'{"prompt":"one"}\n')
    assert train_lora.sha256_file(source) == (
        "4fb3c07e96750f539487c72c8f38f7e9ea4197eba0573ea890fa6c05d5c59d98"
    )


def test_export_sha256_records_exact_control_artifact(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"control")
    assert export_base.sha256_file(artifact) == (
        "0fcd568a5cb9bdb4677b69354b11ee415af8f784519cff3da49a26f84eaee7f2"
    )


def test_campaign_artifact_manifest_is_complete_and_unique():
    manifest = json.loads((HERE / "results" / "artifacts.json").read_text())
    artifacts = manifest["artifacts"]
    assert len(artifacts) == 17
    assert len({row["id"] for row in artifacts}) == 17
    assert len({row["sha256"] for row in artifacts}) == 17
    assert {row["quantization"] for row in artifacts} == {"Q4_0", "Q4_K_M"}
    assert all(row["bytes"] > 0 for row in artifacts)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _fixed_15_total(accuracy_percent: float, tps: float, rss_mib: float) -> float:
    performance = min(tps / 15.0, 1.0) * 100.0
    efficiency = max(0.0, (7.0 - rss_mib / 1024.0) / 7.0) * 100.0
    return 0.5 * accuracy_percent + 0.3 * performance + 0.2 * efficiency


def test_finetune_summary_reproduces_raw_accuracy_throughput_and_scores():
    results = HERE / "results" / "benchmark"
    summary = json.loads((HERE / "results" / "summary.json").read_text())
    by_id = {row["id"]: row for row in summary["models"]}
    specs = (
        {
            "id": "qwen35",
            "candidate_model": "qwen35-bf16-r16-mcq-lr2e5-400-q4_0.gguf",
            "control_model": "qwen35-zero-lr-r16-control-q4_0.gguf",
            "candidate_accuracy": "qwen35-metric-mcq-accuracy500.jsonl",
            "control_accuracy": "qwen35-zero-lr-control-accuracy500.jsonl",
            "throughput": (
                "qwen35-metric-matched-throughput.jsonl",
                "qwen35-zero-lr-control-throughput.jsonl",
            ),
        },
        {
            "id": "qwen25",
            "candidate_model": "qwen25-bf16-r16-licensed-mcq-lr2e5-500-q4_k_m.gguf",
            "control_model": "qwen25-base-same-export-q4_k_m.gguf",
            "candidate_accuracy": "qwen25-licensed-mcq-accuracy500.jsonl",
            "control_accuracy": "qwen25-base-same-export-accuracy500.jsonl",
            "throughput": ("qwen25-licensed-mcq-matched-throughput.jsonl",),
        },
    )

    for spec in specs:
        model = by_id[spec["id"]]
        candidate_accuracy = _jsonl(results / spec["candidate_accuracy"])[0]
        control_accuracy = _jsonl(results / spec["control_accuracy"])[0]
        assert candidate_accuracy["ok"] and candidate_accuracy["samples"] == 500
        assert control_accuracy["ok"] and control_accuracy["samples"] == 500
        assert isclose(model["accuracy"]["candidate_percent"], candidate_accuracy["score"] * 100)
        assert isclose(model["accuracy"]["control_percent"], control_accuracy["score"] * 100)

        throughput_rows = [
            row
            for filename in spec["throughput"]
            for row in _jsonl(results / filename)
        ]
        assert all(row["ok"] for row in throughput_rows)
        for lane, build_marker in (("scalar", "/build-adtc/"), ("vector", "/build-avx2/")):
            for variant, model_name in (
                ("candidate", spec["candidate_model"]),
                ("control", spec["control_model"]),
            ):
                rows = [
                    row for row in throughput_rows
                    if row["model"] == model_name
                    and build_marker in row["bench_identity"]["path"]
                ]
                assert len(rows) == 2
                tps = sum(row["tg_avg_ts"] for row in rows) / len(rows)
                rss = sum(
                    row["peak_rss_tree_mb"] + row["profiler_python_overhead_mib_note"]
                    for row in rows
                ) / len(rows)
                assert isclose(model[lane][f"{variant}_tps"], tps, abs_tol=1e-7)
                assert isclose(model[lane][f"{variant}_peak_rss_mib"], rss, abs_tol=1e-7)
                total = _fixed_15_total(
                    model["accuracy"][f"{variant}_percent"], tps, rss
                )
                assert isclose(model[lane][f"{variant}_total"], total, abs_tol=5e-5)


def test_dataset_manifests_account_for_every_row():
    for name in (
        "dataset-manifest.json",
        "reasoning-dataset-manifest.json",
        "metric-mcq-dataset-manifest.json",
        "metric-licensed-mcq-dataset-manifest.json",
        "metric-hybrid-dataset-manifest.json",
        "metric-licensed-hybrid-dataset-manifest.json",
    ):
        manifest = json.loads((HERE / name).read_text())
        for split in ("train", "validation"):
            assert sum(manifest[split]["sources"].values()) == manifest[split]["rows"]
            assert len(manifest[split]["sha256"]) == 64
    reasoning = json.loads((HERE / "reasoning-dataset-manifest.json").read_text())
    assert "smoltalk_everyday_train" not in reasoning["train"]["sources"]


def test_licensed_profiles_exclude_openbookqa_from_training_and_provenance():
    for name in (
        "metric-licensed-mcq-dataset-manifest.json",
        "metric-licensed-hybrid-dataset-manifest.json",
    ):
        manifest = json.loads((HERE / name).read_text())
        assert "allenai/openbookqa" not in manifest["source_revisions"]
        assert "allenai/openbookqa" not in manifest["source_licenses"]
        assert "openbookqa_train" not in manifest["train"]["sources"]
        assert "openbookqa_train" not in manifest["validation"]["sources"]


def test_leakage_guard_rejects_exact_and_near_duplicate_questions():
    guard = build_metric_dataset.LeakageGuard(
        ["Which process converts liquid water into water vapour in the atmosphere?"]
    )
    assert guard.matches("Which process converts liquid water into water vapor in the atmosphere?")
    assert not guard.matches("What force keeps a planet in orbit around the Sun?")


def test_verified_openr1_trace_requires_both_quality_flags_and_prefers_shortest():
    row = {
        "generations": ["<think>" + "x" * 120 + "</think>", "y" * 90, "z" * 80],
        "correctness_math_verify": [True, True, False],
        "is_reasoning_complete": [True, True, True],
    }
    assert build_metric_dataset.verified_openr1_trace(row) == "y" * 90
    row["is_reasoning_complete"] = [False, False, True]
    assert build_metric_dataset.verified_openr1_trace(row) is None


def test_metric_mcq_uses_profiler_prompt_shape_and_answer_text():
    row = {
        "choices": {"label": ["A", "B"], "text": ["heat", "gravity"]},
        "answerKey": "B",
    }
    record = build_metric_dataset._raw_mcq(
        question="What keeps planets in orbit?", row=row, source="qasc_train"
    )
    assert record == {
        "prompt": "Question: What keeps planets in orbit?\nAnswer:",
        "completion": "gravity",
        "source": "qasc_train",
        "mode": "raw",
    }


def test_metric_source_licenses_are_explicit_including_unknowns():
    assert build_metric_dataset.SOURCE_LICENSES["allenai/qasc"] == "CC-BY-4.0"
    assert build_metric_dataset.SOURCE_LICENSES["allenai/openbookqa"] == "unknown"
