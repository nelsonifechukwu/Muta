"""Static safeguards for the report's evidence labels and profiler controls."""

import json
import re
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
REPOSITORY = DASHBOARD.parents[1]


def test_report_uses_direct_technical_prose() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()
    combined = f"{html}\n{script}"

    for phrase in (
        "survives the laptop",
        "what the score rewards",
        "narrowing the field",
        "when file size misleads",
        "taught us where not to cut",
        "moved the frontier",
        "turns the usual format advice upside down",
        "what survived measurement",
        "one campaign, two runtime answers",
        "first thing a student notices",
        "something a classroom would feel",
    ):
        assert phrase not in combined.lower()

    assert re.search(r"\b(?:we|our|us)\b", combined, re.IGNORECASE) is None


def test_report_names_all_evidence_lanes() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    for label in (
        "Official profiler result",
        "Profiler-parity estimate",
        "Website-relative sensitivity",
        "Controlled AVX2 proxy",
        "Development result",
        "Mixed-machine archive",
    ):
        assert label in html or label in script

    assert "Est. profiler RSS mean ± SD" in script
    assert "Website-relative sensitivity only" in script


def test_operational_profiler_controls_remain_present() -> None:
    html = (DASHBOARD / "index.html").read_text()

    for element_id in (
        "campaign-table",
        "campaign-parity-table",
        "campaign-alternative-table",
        "campaign-avx2-score-table",
        "isa-score-chart",
        "overnight-avx2-score-chart",
        "overnight-avx2-table",
        "overnight-score-chart",
        "overnight-quant-chart",
        "overnight-finalist-table",
        "overnight-screen-table",
        "run-card",
        "run-log",
        "chart",
        "models-table",
        "quick-toggle",
        "modal",
    ):
        assert f'id="{element_id}"' in html


def test_static_verdict_matches_overnight_recommendation() -> None:
    campaign_path = (
        REPOSITORY
        / "bench/measurements/campaign-20260820-overnight/summary.json"
    )
    campaign = json.loads(campaign_path.read_text())
    model = campaign["finalists"][campaign["risk_adjusted_recommendation"]]["official"]
    html = (DASHBOARD / "index.html").read_text()

    assert model["model"] in html
    assert f'{model["s_total"]:.4f}' in html
    assert f'{model["tps"]:.2f} tok/s' in html
    assert f'{model["bytes"]:,} bytes' in html
    assert model["sha256"][:8] in html
    assert model["sha256"][-5:] in html


def test_tied_head_claim_uses_the_isolated_control() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "−175 MB · ARC-Easy 72% in both" in html
    assert "about 175 MB of file bytes" in script
    assert "about 175 MiB of file bytes" not in script
    assert "tied output head saving 255 MB" not in html


def test_unknown_temperature_is_not_rendered_as_a_pass() -> None:
    script = (DASHBOARD / "script.js").read_text()

    assert 'chip("neutral", "temperature unknown")' in script


def test_avx2_campaign_section_matches_comparison_artifact() -> None:
    comparison_path = (
        REPOSITORY
        / "bench/measurements/campaign-20260819/avx2-score-of-record/comparison.json"
    )
    comparison = json.loads(comparison_path.read_text())
    html = (DASHBOARD / "index.html").read_text()

    assert 'id="avx2-campaign"' in html
    assert "Updated seven-artifact AVX2 ledger" in html
    for feature in ("AVX", "AVX2", "FMA", "F16C"):
        assert f"<code>{feature}</code><strong>ON</strong>" in html
    for feature in ("NATIVE", "AVX-512"):
        assert f"<code>{feature}</code><strong>OFF</strong>" in html

    for item in comparison["models"]:
        assert item["model"] in html
        assert f'{item["scalar"]["pp512_tps"]:.4f}' in html
        assert f'{item["avx2"]["pp512_tps"]:.4f}' in html
        assert f'{item["scalar"]["tg128_tps"]:.4f}' in html
        assert f'{item["avx2"]["tg128_tps"]:.4f}' in html
        assert f'{item["delta"]["decode_speedup"]:.3f}×' in html
        assert f'{item["avx2"]["estimated_profiler_rss_mib"]:,.1f} MiB' in html
        assert f'{item["accuracy_proxy"]:.0f}%' in html
        assert f'{item["avx2"]["score"]["s_total"]:.4f}' in html

    winner = comparison["winners"]["avx2"]
    assert winner["model"] in html
    assert f'{winner["s_total"]:.4f}' in html
    assert "19 Aug AVX2 leader" in html
    assert comparison["avx2_binary_sha256"][:8] in html
    assert comparison["avx2_binary_sha256"][-5:] in html


def test_historical_dual_regime_chart_and_current_choice_are_explicit() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "Risk-adjusted submission recommendation" in html
    assert "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf" in html
    assert "Math-Expert Q4_K_M has the highest direct scalar and controlled AVX2 totals" in html
    assert 'class="isa-bar scalar' in script
    assert 'class="isa-bar avx2' in script
    assert "highest scalar total" in script
    assert "highest AVX2 total" in script
    assert "item.scalar.score.s_total" in script
    assert "item.avx2.score.s_total" in script


def test_latest_avx2_finalist_results_are_prominent_and_exact() -> None:
    campaign_path = (
        REPOSITORY
        / "bench/measurements/campaign-20260820-overnight/summary.json"
    )
    campaign = json.loads(campaign_path.read_text())
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    for entry in campaign["finalists"].values():
        avx2 = entry["avx2_fixed_15"]
        assert f'{avx2["pp512_tps"]:.4f}' in html
        assert f'{avx2["tg128_tps"]:.4f}' in html
        assert f'{avx2["estimated_profiler_rss_mib"]:.1f} MiB' in html
        assert f'{avx2["arc_easy_50"]["s_total"]:.4f}' in html
        assert f'{avx2["arc_easy_500"]["s_total"]:.4f}' in html or (
            f'{avx2["arc_easy_500"]["s_total"]:.4f}' in script
        )

    assert "AVX2 measured on tensor-identical source" in script
    assert "measured child tree + 45 MiB root estimate" in script
    assert "81.8803" in html
    assert "79.4104" in html
    assert "76.8104" in html
    assert "75.1803" in script


def test_scalar_profiler_ledger_includes_the_latest_finalists() -> None:
    campaign = json.loads((
        REPOSITORY
        / "bench/measurements/campaign-20260820-overnight/summary.json"
    ).read_text())
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "Six artifacts completed full scalar participant runs" in html
    for entry in campaign["official_profiler"]:
        assert entry["model"] in html
        assert f'{entry["s_total"]:.4f}' in html
        assert entry["sha256"][:8] in html
        assert entry["sha256"][-5:] in html
        assert entry["model"] in script


def test_compact_report_defaults_to_adopted_ledger_entries() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert 'data-ledger-filter="adopted" aria-pressed="true"' in html
    assert 'data-ledger-filter="all" aria-pressed="false"' in html
    assert 'renderLedger("adopted")' in script
    assert '<details class="card workspace-disclosure" id="campaign-card">' in html
    assert '<details class="card workspace-disclosure" id="campaign-avx2-score-card">' in html
