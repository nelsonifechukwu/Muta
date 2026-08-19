"""Static safeguards for the report's evidence labels and profiler controls."""

import json
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parent
REPOSITORY = DASHBOARD.parents[1]


def test_report_names_all_evidence_lanes() -> None:
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    for label in (
        "Official profiler result",
        "Profiler-parity estimate",
        "Website-relative sensitivity",
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
