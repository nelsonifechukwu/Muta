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
        "run-card",
        "run-log",
        "chart",
        "models-table",
        "quick-toggle",
        "modal",
    ):
        assert f'id="{element_id}"' in html


def test_static_verdict_matches_direct_campaign() -> None:
    campaign_path = (
        REPOSITORY
        / "bench/measurements/campaign-20260819/official-profiler/summary.json"
    )
    campaign = json.loads(campaign_path.read_text())
    winner = campaign["winners"]["15.0"]
    model = next(item for item in campaign["models"] if item["model"] == winner["model"])
    html = (DASHBOARD / "index.html").read_text()

    assert model["model"] in html
    assert f'{winner["s_total"]:.2f}' in html
    assert f'{model["tg_tps_mean"]:.2f} tok/s' in html
    assert f'{model["first_token_latency_ms"] / 1000:.2f} s' in html
    assert f'{model["model_bytes"]:,} bytes' in html
    assert model["model_sha256"][:8] in html
    assert model["model_sha256"][-5:] in html


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
    assert "Effect of CPU instruction configuration" in html
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
    assert "0.1666 points" in html
    assert comparison["avx2_binary_sha256"][:8] in html
    assert comparison["avx2_binary_sha256"][-5:] in html


def test_dual_regime_chart_and_current_choice_are_explicit() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "Selected model · portable AVX2 configuration" in html
    assert "Q4_K_M-tied.gguf" in html
    assert "Use Q4_0 with the published scalar participant image" in html
    assert 'class="isa-bar scalar' in script
    assert 'class="isa-bar avx2' in script
    assert "highest scalar total" in script
    assert "highest AVX2 total" in script
    assert "item.scalar.score.s_total" in script
    assert "item.avx2.score.s_total" in script
