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

    assert "proven winner" not in combined.lower()


def test_report_names_all_evidence_lanes() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    for label in (
        "Official profiler result",
        "Profiler-parity estimate",
        "Website-relative sensitivity",
        "Controlled vector CPU proxy",
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
    assert "507.2 MB" in html


def test_current_artifact_diagram_uses_tensor_identity_control() -> None:
    html = (DASHBOARD / "index.html").read_text()

    assert "Qwen3.5 source quant" in html
    assert "320 model tensors compared" in html
    assert "all tensor payloads identical" in html
    assert "The current recommendation differs from its Qwen3.5 source quant only in GGUF metadata" in html


def test_all_current_visual_defaults_use_the_current_campaign_decision() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert '{ name: "Qwen3.5 0.8B final", gb: 0.47, acc: 64, lane: "audit", selected: true }' in script
    assert '{ name: "Qwen2.5 1.5B Q4_K_M", gb: 1.04, acc: 71.8, samples: 500, lane: "audit", leader: true }' in script
    assert "Validated vector candidate" in html
    assert "82.8697" in html
    assert 'Qwen3 1.7B Q4_K_M", gb: 0.96, acc: 72, lane: "audit", selected: true' not in script
    assert "renderIsaComparison(d.campaign_avx2_score, d.overnight, d.model_extension)" in script
    assert "entry.official.arc_easy_50" in script


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

    assert 'id="instruction-set"' in html
    assert "fifteen models" in html
    for feature in ("AVX", "AVX2", "FMA", "F16C"):
        assert feature in html
    assert "Scalar configuration</code><strong>vector extensions disabled" in html
    assert "Vector configuration</code><strong>portable SIMD enabled" in html
    assert "<code>NATIVE</code><strong>OFF</strong>" not in html

    labels = {
        "muta-tutor-qwen3-1.7b-q4_0.gguf": "Qwen3 1.7B Q4_0",
        "Q4_K_M-tied.gguf": "Qwen3 1.7B Q4_K_M",
        "Q5_K_M-tied.gguf": "Qwen3 1.7B Q5_K_M",
        "IQ4_XS-tied.gguf": "Qwen3 1.7B IQ4_XS",
        "bitcpm4-8b-tq2_0-envocab.gguf": "BitCPM4 8B TQ2_0",
    }
    for item in comparison["models"]:
        assert labels[item["model"]] in html
        assert f'{item["scalar"]["pp512_tps"]:.4f}' in html
        assert f'{item["avx2"]["pp512_tps"]:.4f}' in html
        assert f'{item["scalar"]["tg128_tps"]:.4f}' in html
        assert f'{item["avx2"]["tg128_tps"]:.4f}' in html
        assert f'{item["delta"]["decode_speedup"]:.3f}×' in html
        assert f'{item["avx2"]["estimated_profiler_rss_mib"]:,.1f} MiB' in html
        assert f'{item["accuracy_proxy"]:.0f}%' in html
        assert f'{item["avx2"]["score"]["s_total"]:.4f}' in html

    winner = comparison["winners"]["avx2"]
    assert labels[winner["model"]] in html
    assert f'{winner["s_total"]:.4f}' in html
    assert "Quantization-ladder leader" in html


def test_historical_dual_regime_chart_and_current_choice_are_explicit() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "Risk-adjusted choice" in html
    assert "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf" in html
    assert "500-question check confirms Qwen2.5 1.5B as the vector candidate" in html
    assert "80.7697" in html
    assert "63.8176" in html
    assert '{className: "scalar"' in script
    assert '{className: "avx2"' in script
    assert "Highest scalar total" in script
    assert "Highest vector total" in script
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
        assert "avx.arc_easy_500.s_total" in script

    assert "Vector path measured on a tensor-identical parent quant" in script
    assert "45 MiB profiler-root estimate" in script
    assert "81.8803" in html
    assert "79.4104" in html
    assert "76.8104" in html
    assert "avx.arc_easy_500.s_total" in script


def test_scalar_profiler_ledger_includes_the_latest_finalists() -> None:
    campaign = json.loads((
        REPOSITORY
        / "bench/measurements/campaign-20260820-overnight/summary.json"
    ).read_text())
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "six quantized candidates through the participant profiler" in html
    labels = {
        "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf": "Math-Expert 0.6B Q4_K_M",
        "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf": "Qwen3.5 0.8B Q4_0",
    }
    for entry in campaign["official_profiler"]:
        assert labels[entry["model"]] in html
        assert f'{entry["s_total"]:.4f}' in html
        assert entry["model"] in script


def test_visible_report_omits_chronology_and_build_identifiers() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()
    visible_html = re.sub(r"<[^>]+>", " ", html).lower()

    for phrase in (
        "july",
        "august",
        "sha-256",
        "commit",
        "b10175",
        "profiler binary",
        "benchmark binary",
        "dated campaigns",
        "selected path",
        "pinned source",
        "exact artifact",
        "exact model",
        "overnight",
    ):
        assert phrase not in visible_html

    for visible_template in (
        "binary SHA-256",
        "SHA-256 ${",
        "campaign_date",
        "two dated campaigns",
        "fmt.when",
    ):
        assert visible_template not in script

    for progression_term in (
        "expanded search added",
        "broader paired cpu comparison",
        "500-question check confirms",
    ):
        assert progression_term in html.lower()


def test_visible_report_uses_plain_scalar_vector_language() -> None:
    html = (DASHBOARD / "index.html").read_text()
    visible_html = re.sub(r"<[^>]+>", " ", html).lower()

    for phrase in (
        "how we got here",
        "the story",
        "road one",
        "road two",
        "widened the net",
        "where we've landed",
        "teaching the file to behave",
        "the receipts",
        "no-avx",
    ):
        assert phrase not in visible_html

    assert "we call this the scalar configuration" in visible_html
    assert "q4_0 is the exception and still uses ssse3 simd" in visible_html
    assert "we call that the vector configuration" in visible_html


def test_model_extension_and_vertical_chart_system_are_complete() -> None:
    extension = json.loads((
        REPOSITORY / "bench/measurements/model-extension/summary.json"
    ).read_text())
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()
    css = (DASHBOARD / "style.css").read_text()

    assert len(extension["models"]) == 8
    assert extension["winner"]["s_total"] == 82.8697
    validated = next(item for item in extension["models"] if item["label"] == "Qwen2.5 1.5B")
    assert validated["accuracy_validation"]["samples"] == 500
    assert validated["accuracy_validation"]["accuracy_percent"] == 71.8
    assert validated["scalar"]["s_total_accuracy_500"] == 63.8176
    assert validated["avx2"]["s_total_accuracy_500"] == 80.7697
    for item in extension["models"]:
        assert item["label"] in html
        assert f'{item["scalar"]["pp512_tps"]:.4f}'[:5] in html
        assert f'{item["avx2"]["pp512_tps"]:.4f}'[:5] in html
        assert f'{item["scalar"]["tg128_tps"]:.4f}'[:5] in html
        assert f'{item["avx2"]["tg128_tps"]:.4f}'[:5] in html
        assert f'{item["avx2"]["s_total"]:.4f}' in html

    assert 'data-orientation="vertical"' in script
    assert "verticalGroupedChart" in script
    assert "CHART_PALETTE" in script
    assert ".chart-legend .scalar::before" in css
    assert ".chart-legend .avx2::before" in css
    assert ".chart-legend .official::before" in css


def test_compact_report_defaults_to_adopted_ledger_entries() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert 'data-ledger-filter="adopted" aria-pressed="true"' in html
    assert 'data-ledger-filter="all" aria-pressed="false"' in html
    assert 'renderLedger("adopted")' in script
    assert '<details class="card workspace-disclosure" id="campaign-card">' in html
    assert '<details class="card workspace-disclosure" id="campaign-avx2-score-card">' in html
