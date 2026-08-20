from __future__ import annotations

from pathlib import Path

from bench.overnight_campaign_summary import summarize


ROOT = Path(__file__).parent / "measurements/campaign-20260820-overnight"


def test_overnight_summary_preserves_two_distinct_decisions():
    result = summarize(ROOT)
    assert result["official_profiler_winner"] == "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf"
    recommendation = "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf"
    assert result["risk_adjusted_recommendation"] == recommendation
    assert result["finalists"][recommendation]["accuracy"]["arc_easy_500"]["samples"] == 500
    assert result["finalists"][recommendation]["official"]["sha256"] == (
        "c96df4ef6d9416bea6a35866751cb6cf02e20ec6ce28b20980d66c90604d5d7b"
    )


def test_website_relative_denominator_includes_candidate_speed():
    result = summarize(ROOT)
    for entry in result["website_relative"].values():
        for scored in entry["scores"].values():
            assert scored["s_perf"] <= 100
            assert scored["effective_tps_max"] >= entry["avx2"]["tg128_tps"]


def test_direct_profiler_scores_use_root_plus_child_rss():
    result = summarize(ROOT)
    math = next(row for row in result["official_profiler"] if row["id"].startswith("qwen3-0.6b"))
    assert math["peak_rss_mib"] == 540.32
    assert round(math["s_total"], 4) == 77.9324
