from bench.balanced_model_report import summarize
from bench.run_stem_prompt_suite import selected_option
from bench.stem_prompt_suite import prompts


def test_suite_has_balanced_unique_prompts() -> None:
    suite = prompts()
    assert len(suite) == 100
    assert len({row.id for row in suite}) == 100
    assert sum(row.subject == "math" for row in suite) == 50
    assert sum(row.subject == "science" for row in suite) == 50
    assert sum(row.format == "multiple_choice" for row in suite) == 50
    assert sum(row.format == "written" for row in suite) == 50


def test_multiple_choice_parser_prefers_final_explicit_answer() -> None:
    text = "I first considered A. The correct answer is C because 6 × 500 = 3,000."
    assert selected_option(text) == "C"


def test_multiple_choice_parser_returns_none_without_an_explicit_option() -> None:
    assert selected_option("Six times five hundred is three thousand naira.") is None


def test_multiple_choice_parser_uses_text_order_across_answer_patterns() -> None:
    assert selected_option("\\boxed{A}\nThe final answer is C.") == "C"
    assert selected_option("The answer is A.\n\\boxed{C}") == "C"


def test_multiple_choice_parser_accepts_bare_option() -> None:
    assert selected_option("C") == "C"
    assert selected_option("**C**") == "C"
    assert selected_option("(c)") == "C"


def test_final_answer_overrides_an_earlier_option_list() -> None:
    assert selected_option("A. 1000\nB. 2500\nC. 3000\nD. 3500\nAnswer: C") == "C"
    assert selected_option("A. First guess\nThe correct answer is C.") == "C"


def test_multiple_choice_parser_does_not_select_a_distractor_from_a_list() -> None:
    assert selected_option("A. 1000\nB. 2500\nC. 3000\nD. 3500") is None
    assert selected_option("The answer is a number calculated by multiplication.") is None


def test_multiple_choice_parser_leaves_ambiguous_or_invalid_answer_ungraded() -> None:
    assert selected_option("A. My first guess\nC. Another possibility") is None
    assert selected_option("The answer is A.\nThe final answer is E.") is None


def test_campaign_summary_uses_decode_samples_and_profiler_root_rss() -> None:
    throughput = [
        {
            "kind": "throughput",
            "ok": True,
            "model": "candidate.gguf",
            "model_sha256": "model-hash",
            "bench_identity": {"sha256": "binary-hash"},
            "peak_rss_tree_mb": 979,
            "profiler_python_overhead_mib_note": 45,
            "pp_avg_ts": 20,
            "tg_avg_ts": 10,
            "raw_bench_rows": [
                {"n_prompt": 512, "n_gen": 0, "samples_ts": [19, 21]},
                {"n_prompt": 0, "n_gen": 128, "samples_ts": [9, 11]},
            ],
        }
    ]
    accuracy = [
        {
            "kind": "accuracy",
            "ok": True,
            "model": "candidate.gguf",
            "benchmark": "arc_easy",
            "model_sha256": "model-hash",
            "samples": 500,
            "score": 0.8,
        }
    ]
    result = summarize(throughput, accuracy, {"candidate.gguf": "Candidate"})[0]
    assert result["scalar_pp512_tok_s"] == 20
    assert result["scalar_tg128_tok_s"] == 10
    assert result["estimated_profiler_peak_rss_mib"] == 1024
    assert result["s_total"] == 77.1429
