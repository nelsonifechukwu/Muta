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
    assert "the guaranteed winner" not in combined.lower()


def test_report_names_all_evidence_lanes() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    for label in (
        "Official profiler result",
        "Profiler-parity estimate",
        "Website-relative sensitivity",
        "Controlled vector proxy",
        "Development result",
        "Mixed-machine archive",
    ):
        assert label in html or label in script


def test_operational_profiler_controls_remain_present() -> None:
    html = (DASHBOARD / "index.html").read_text()

    for element_id in (
        "campaign-table",
        "campaign-parity-table",
        "campaign-alternative-table",
        "campaign-avx2-score-table",
        "model-extension-table",
        "model-extension-score-chart",
        "all-models-score-chart",
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
    campaign_path = REPOSITORY / "bench/measurements/campaign-20260820-overnight/summary.json"
    campaign = json.loads(campaign_path.read_text())
    model = campaign["finalists"][campaign["risk_adjusted_recommendation"]]["official"]
    html = (DASHBOARD / "index.html").read_text()

    assert model["model"] in html
    assert f"{model['s_total']:.4f}" in html
    assert f"{model['tps']:.2f} tok/s" in html
    assert "507.2 MB" in html


def test_current_artifact_diagram_uses_tensor_identity_control() -> None:
    html = (DASHBOARD / "index.html").read_text()

    assert "Qwen3.5 source quant" in html
    assert "320 model tensors compared" in html
    assert "all tensor payloads identical" in html
    assert (
        "The current recommendation differs from its Qwen3.5 source quant only in GGUF metadata"
        in html
    )


def test_all_current_visual_defaults_use_the_current_campaign_decision() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert (
        '{ name: "Qwen3.5 0.8B Q4_0 final", gb: 0.47, acc: 64, lane: "audit", selected: true }' in script
    )
    assert '{ name: "Qwen2.5 1.5B Q4_K_M", gb:' not in script
    assert 'Qwen3 1.7B Q4_K_M", gb: 0.96, acc: 72, lane: "audit", selected: true' not in script
    assert "82.8697" in html
    assert "Vector leader, n=500" in html
    assert "renderModelExtension(d.model_extension)" in script
    assert "entry.official.arc_easy_50" in script


def test_unknown_temperature_is_not_rendered_as_a_pass() -> None:
    script = (DASHBOARD / "script.js").read_text()

    assert 'chip("neutral", "temperature unknown")' in script


def test_current_comparison_is_the_complete_eight_model_screen() -> None:
    comparison = json.loads(
        (REPOSITORY / "bench/measurements/model-extension/summary.json").read_text()
    )
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()
    section = html.split('id="second-search"', 1)[1].split(
        '<section class="chapter" id="behaviour"', 1
    )[0]
    table_block = section.split('id="model-extension-score-chart"', 1)[1].split(
        "</details>", 1
    )[0]

    assert 'id="second-search"' in html
    for item in comparison["models"]:
        assert item["label"] in table_block
        assert f"{item['scalar']['s_total']:.4f}" in table_block
        assert f"{item['avx2']['s_total']:.4f}" in table_block
    assert "82.8697" in section
    assert "80.7697" in section
    assert "67.70" in section and "75.57" in section
    assert "<th>Decode gain</th>" in section
    assert "renderModelExtension" in script
    assert "verticalGroupedChart" in script
    assert 'data-orientation="vertical"' in script


def test_scalar_profiler_winner_and_submission_choice_are_distinguished() -> None:
    html = (DASHBOARD / "index.html").read_text()

    assert "Math-Expert 0.6B Q4_K_M" in html
    assert "77.9324" in html
    assert "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf" in html
    assert "72.7895" in html
    assert "The first scoreboard: Qwen3 1.7B wins, narrowly" in html


def test_engine_only_method_names_artifacts_and_submission_boundary() -> None:
    html = (DASHBOARD / "index.html").read_text()
    runtime = html.split('id="runtime"', 1)[1].split('id="remaining-methods"', 1)[0]

    assert "speculative decoding" in runtime.lower()
    assert "Draft-model speculation" in runtime
    assert "they never rank submission models" in runtime
    assert "None of this configuration travels with the submitted GGUF" in runtime


def test_remaining_methods_chapter_covers_all_six_topics() -> None:
    html = (DASHBOARD / "index.html").read_text()
    remaining = html.split('id="remaining-methods"', 1)[1].split(
        '<section class="chapter" id="scoreboard"', 1
    )[0]

    for method_id in (
        "mixed-precision",
        "pruning",
        "smaller-architectures",
        "distillation",
        "layout-repacking",
        "context-kv",
    ):
        assert f'id="{method_id}"' in remaining
    for phrase in (
        "Meaning and score hypothesis",
        "Artifacts and protocol",
        "Result and narrowing",
    ):
        assert remaining.count(phrase) == 6


def test_historical_dual_regime_chart_and_current_choice_are_explicit() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf" in html
    assert "80.7697" in html
    assert "63.8176" in html
    assert 'class="vgc-bar ${lane.className}' in script
    assert '{className: "scalar"' in script
    assert '{className: "avx2"' in script
    assert "item.scalar.score.s_total" in script
    assert "item.avx2.score.s_total" in script


def test_earlier_direct_profiler_finalists_remain_historical() -> None:
    campaign_path = REPOSITORY / "bench/measurements/campaign-20260820-overnight/summary.json"
    campaign = json.loads(campaign_path.read_text())
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    for entry in campaign["finalists"].values():
        assert entry["avx2_fixed_15"]["arc_easy_500"]["s_total"] > 0

    assert "avx.pp512_tps" in script
    assert "avx.tg128_tps" in script
    assert "avx.arc_easy_500.s_total" in script
    assert "45 MiB profiler-root estimate" in script
    assert "Widening the search finds a specialist" in html


def test_scalar_profiler_ledger_includes_the_latest_finalists() -> None:
    campaign = json.loads(
        (REPOSITORY / "bench/measurements/campaign-20260820-overnight/summary.json").read_text()
    )
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert "ran six candidates through the actual participant profiler" in html
    labels = {
        "Qwen3-0.6B-Math-Expert.Q4_K_M.gguf": "Math-Expert 0.6B Q4_K_M",
        "Muta-Tutor-Qwen3.5-0.8B-Q4_0-final.gguf": "Qwen3.5 0.8B Q4_0",
    }
    for entry in campaign["official_profiler"]:
        assert labels[entry["model"]] in html
        assert f"{entry['s_total']:.4f}" in html
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
        "a plain accuracy-by-scale study",
        "a second widening moves the vector leader",
        "is a small-sample estimate",
    ):
        assert progression_term in html.lower()


def test_visible_report_uses_plain_scalar_vector_language() -> None:
    html = (DASHBOARD / "index.html").read_text()
    visible_html = re.sub(r"<[^>]+>", " ", html).lower()

    assert "no-avx" not in visible_html

    assert "the  scalar configuration  is the supplied profiler build" in visible_html
    assert (
        "the  vector configuration  is a portable simd build with avx2, fma, and f16c enabled"
        in visible_html
    )
    after_definition = visible_html.split("from here on, this page just says scalar and vector", 1)[1]
    # The isa-policy build-flag badges (AVX2/FMA/F16C ON, NATIVE/AVX-512 OFF) are literal
    # compiler-flag names, not narrative prose, so they're allowed to keep appearing.
    prose_after_definition = re.sub(r"avx2\s+on|fma\s+on|f16c\s+on|native\s+off|avx-512\s+off", " ", after_definition)
    assert "avx2" not in prose_after_definition


def test_model_extension_and_horizontal_isa_chart_are_wired() -> None:
    extension = json.loads(
        (REPOSITORY / "bench/measurements/model-extension/summary.json").read_text()
    )
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert len(extension["models"]) == 8
    validated = next(item for item in extension["models"] if item["label"] == "Qwen2.5 1.5B")
    assert validated["accuracy_validation"]["samples"] == 500
    assert validated["accuracy_validation"]["accuracy_percent"] == 71.8
    assert validated["scalar"]["s_total_accuracy_500"] == 63.8176
    assert validated["avx2"]["s_total_accuracy_500"] == 80.7697
    for item in extension["models"]:
        assert item["label"] in html
        assert f"{item['avx2']['s_total']:.4f}" in html

    assert "function renderModelExtension(modelExtension)" in script
    assert "modelExtension.models" in script
    assert '$("model-extension-score-chart")' in script


def test_combined_all_models_chart_spans_both_explorations() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert 'id="all-models-score-chart"' in html
    assert "Every paired model, scalar versus vector" in html
    assert "function renderCombinedComparison(ladderModels, extensionModels)" in script
    assert "renderCombinedComparison(ladderModels, extensionModels)" in script
    assert 'group: "First exploration"' in script
    assert 'group: "Second exploration"' in script


def test_compact_report_defaults_to_adopted_ledger_entries() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert 'data-ledger-filter="adopted" aria-pressed="true"' in html
    assert 'data-ledger-filter="all" aria-pressed="false"' in html
    assert 'renderLedger("adopted")' in script
    assert '<details class="card workspace-disclosure" id="campaign-card">' in html
    assert 'id="campaign-avx2-score-table"' in html
