from __future__ import annotations

import pytest

from bench.judges_prompt_report import evaluate, execution_records, grade, write_report
from bench.judges_prompt_suite import prompts


def test_gate_one_suite_contains_the_ten_recovered_prompts():
    suite = prompts()
    assert len(suite) == 10
    assert len({prompt.id for prompt in suite}) == 10
    assert suite[0].text == suite[8].text
    assert "dS/dt = k * (T - S)" in suite[1].text
    assert "4 TOPS" in suite[2].text
    assert "₦1,850" in suite[9].text


def test_rice_rubric_accepts_the_complete_correct_solution():
    answer = """
    Cost = 40 × ₦1,850 = ₦74,000. After 25 kg, 15 kg remains.
    The reduced price is ₦2,300 × 0.85 = ₦1,955 per kg.
    Revenue is ₦57,500 + ₦29,325 = ₦86,825.
    Profit is ₦86,825 - ₦74,000 = ₦12,825, so percentage profit is 17.3%.
    Check by a different method: the weighted average selling price is ₦2,170.625;
    (2,170.625 - 1,850) × 40 = ₦12,825, again 17.3% of cost.
    """
    result = grade("human_05", answer)
    assert result["score"] == 10
    assert all(item["passed"] for item in result["items"])


def test_tops_rubric_rewards_underdetermination_not_a_fabricated_model_size():
    correct = """
    The 200 ms operation budget is 4 × 10^12 × 0.2 = 8 × 10^11 operations.
    The maximum parameter count cannot be determined from this information. We also need
    the output length, operations per parameter per generated token, numerical precision,
    and memory bandwidth. Two tokens per character is not enough to size the model.
    """
    fabricated = "The maximum parameter size is 800 billion parameters."
    assert grade("automated_03", correct)["score"] == 10
    assert grade("automated_03", fabricated)["score"] < 4


def test_evaluation_ranks_complete_responses_and_retains_model_labels():
    answer = "R = kP, where k is a positive constant and P is personalization. As P approaches zero, R approaches zero. As P approaches infinity, R grows without bound."
    rows = [
        {
            "id": "automated_01",
            "source": "automated",
            "model": "good.gguf",
            "model_sha256": "good",
            "answer": answer,
        },
        {
            "id": "automated_01",
            "source": "automated",
            "model": "bad.gguf",
            "model_sha256": "bad",
            "answer": "I do not know.",
        },
    ]
    summary, details = evaluate(rows, {"good.gguf": "Good", "bad.gguf": "Bad"})
    assert [row["model"] for row in summary] == ["Good", "Bad"]
    assert details[0]["model_label"] == "Good"
    assert all(row["rank"] is None for row in summary)
    assert all(row["status"] == "incomplete" for row in summary)


def response_row(model, prompt, answer=""):
    return {
        "id": prompt.id,
        "source": prompt.source,
        "model": model,
        "model_sha256": model,
        "answer": answer,
    }


def test_evaluation_rejects_duplicate_prompt_responses():
    row = response_row("model.gguf", prompts()[0])
    with pytest.raises(ValueError, match="duplicate judge response"):
        evaluate([row, row], {})


def test_evaluation_ranks_only_complete_models_even_if_partial_score_is_higher():
    complete = [response_row("complete.gguf", prompt) for prompt in prompts()]
    partial = response_row("partial.gguf", prompts()[3], "C. 6 × 500 = 3000.")
    summary, _ = evaluate([partial, *complete], {})
    assert summary[0]["model"] == "complete.gguf"
    assert summary[0]["status"] == "complete"
    assert summary[0]["rank"] == 1
    assert summary[1]["status"] == "incomplete"
    assert summary[1]["rank"] is None


def test_evaluation_rejects_mixed_artifact_hashes():
    first = response_row("model.gguf", prompts()[0])
    second = response_row("model.gguf", prompts()[1])
    second["model_sha256"] = "different"
    with pytest.raises(ValueError, match="different artifacts"):
        evaluate([first, second], {})


def test_evaluation_rejects_invalid_prompt_or_source():
    row = response_row("model.gguf", prompts()[0])
    row["source"] = "human judge"
    with pytest.raises(ValueError, match="mismatched source"):
        evaluate([row], {})


def test_empty_responses_receive_no_points():
    assert all(grade(prompt.id, "")["score"] == 0 for prompt in prompts())


def test_report_does_not_invent_a_hardware_or_runtime_configuration(tmp_path):
    summary, details = evaluate([response_row("model.gguf", prompts()[0])], {})
    report = tmp_path / "report.md"
    write_report(report, summary, details)
    text = report.read_text()
    assert "unspecified (legacy record)" in text
    assert "Generation settings: unrecorded" in text
    assert "Server version: `unrecorded`" in text
    assert "b10175" not in text
    assert "CPU only" not in text
    assert "Mac" not in text


def test_execution_metadata_uses_saved_settings_and_context():
    row = response_row("model.gguf", prompts()[0])
    row.update(
        hardware_context="mac_apple_m4_pro_24g_metal_pilot",
        settings={"context_size": 4096, "gpu_layers": 99, "temperature": 0, "max_tokens": 1024},
    )
    record = execution_records([row])[0]
    assert record["hardware_context"] == "mac_apple_m4_pro_24g_metal_pilot"
    assert record["server_settings"] == {"context_size": 4096, "gpu_layers": 99}
    assert record["generation_settings"] == {"temperature": 0, "max_tokens": 1024}


def test_execution_settings_can_be_recovered_from_matching_events():
    row = response_row("model.gguf", prompts()[0])
    row["server_sha256"] = "binary-hash"
    event = {
        "event": "model_start",
        "model": row["model"],
        "model_sha256": row["model_sha256"],
        "server_sha256": "binary-hash",
        "command": [
            "llama-server",
            "--threads",
            "2",
            "--ctx-size",
            "4096",
            "--n-gpu-layers",
            "0",
            "--jinja",
        ],
    }
    record = execution_records([row], [event])[0]
    assert record["server_settings"] == {
        "threads": "2",
        "context_size": "4096",
        "gpu_layers": "0",
        "jinja": True,
    }
    assert record["generation_settings"] == {}
    event["model_sha256"] = "different-artifact"
    assert execution_records([row], [event])[0]["server_settings"] == {}


def test_judge_aggregation_rejects_mixed_execution_contexts():
    first = response_row("first.gguf", prompts()[0])
    second = response_row("second.gguf", prompts()[0])
    first["hardware_context"] = "gcp_scalar"
    second["hardware_context"] = "mac_metal"
    with pytest.raises(ValueError, match="mixed hardware contexts"):
        evaluate([first, second], {})
