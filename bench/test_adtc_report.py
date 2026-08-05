"""Tests for the profiler-JSON adapter.

The load-bearing case is `test_ninety_degrees_penalised_despite_throttled_false`. Upstream
thermal.py sets throttled=True only at >=95 C, but the competition penalty is >85 C. Trusting
the profiler's flag alone silently loses 10 points in the 85-95 C band.
"""

from __future__ import annotations

import pytest

from bench.adtc import report
from bench.sampler import MemoryReport, ThermalReport


def _payload(**overrides) -> dict:
    data = {
        "throughput": {
            "tokens_per_second_generation": 12.5,
            "first_token_latency_ms": 430.0,
        },
        "memory": {
            "peak_rss_mb": 2048.0,
            "steady_state_rss_mb": 1536.0,
            "peak_vms_mb": 8000.0,
        },
        "cpu_thermal": {
            "cpu_percent_p99": 84.0,
            "core_temp_c_peak": None,
            "throttled": False,
        },
        "model_info": {"params_match": True},
    }
    for section, values in overrides.items():
        data.setdefault(section, {}).update(values)
    return data


def test_parses_the_scored_fields():
    run = report.from_profiler_json(_payload())
    assert run.tps_actual == 12.5
    assert run.peak_rss_gb == pytest.approx(2.0)
    assert run.steady_rss_gb == pytest.approx(1.5)
    assert run.first_token_latency_ms == 430.0
    assert run.source == "profiler"


def test_null_temperature_stays_none_and_scores_as_unknown():
    run = report.from_profiler_json(_payload())
    assert run.max_temp_c is None
    result = report.score_run(run, accuracy=50.0, label="t")
    assert result.thermal_unknown is True
    assert result.p_thermal == 0.0


def test_ninety_degrees_penalised_despite_throttled_false():
    # Upstream flags throttled only at >=95 C; the rule is >85 C. This must still cost 10.
    run = report.from_profiler_json(
        _payload(cpu_thermal={"core_temp_c_peak": 90.0, "throttled": False})
    )
    assert run.max_temp_c == 90.0
    assert run.throttled is False
    result = report.score_run(run, accuracy=50.0, label="hot")
    assert result.p_thermal == 10.0
    assert result.thermal_unknown is False


def test_upstream_throttled_flag_is_still_honoured():
    run = report.from_profiler_json(
        _payload(cpu_thermal={"core_temp_c_peak": 70.0, "throttled": True})
    )
    assert report.score_run(run, accuracy=50.0, label="throttled").p_thermal == 10.0


def test_missing_required_section_raises():
    data = _payload()
    del data["memory"]
    with pytest.raises(report.ProfilerReportError) as exc:
        report.from_profiler_json(data)
    assert "memory" in str(exc.value)


def test_missing_required_field_raises_rather_than_defaulting_to_zero():
    data = _payload()
    del data["throughput"]["tokens_per_second_generation"]
    with pytest.raises(report.ProfilerReportError):
        report.from_profiler_json(data)


def test_absent_thermal_section_is_tolerated_as_unknown():
    # cpu_thermal is not in the schema's required set; absence means unmeasured, not safe.
    data = _payload()
    del data["cpu_thermal"]
    run = report.from_profiler_json(data)
    assert run.max_temp_c is None
    assert run.throttled is False


def test_params_match_reads_the_fraud_check():
    assert report.params_match(_payload()) is True
    assert report.params_match(_payload(model_info={"params_match": False})) is False
    data = _payload()
    del data["model_info"]
    # Absent model_info means the profiler could not check; do not invent a failure.
    assert report.params_match(data) is True


def test_params_match_treats_null_as_uncheckable_not_fraud():
    # Since profiler 7adbe08 `fraud_check` returns None (JSON null) when the claim or the
    # GGUF header cannot be parsed. bool(None) would read that as fraud and abort the run
    # (autotest exit 3) — only an explicit False may fail.
    assert report.params_match(_payload(model_info={"params_match": None})) is True


def test_from_samplers_round_trips_the_product_path():
    run = report.from_samplers(
        MemoryReport(peak_rss_mb=3072.0, steady_state_rss_mb=2048.0, peak_vms_mb=9000.0),
        ThermalReport(cpu_percent_p99=91.0, core_temp_c_peak=None, throttled=False),
        tps_actual=9.25,
        source="product",
        tps_from_wall_clock=True,
    )
    assert run.peak_rss_gb == pytest.approx(3.0)
    assert run.source == "product"
    assert run.tps_from_wall_clock is True


def test_crash_scores_as_disqualified():
    run = report.from_samplers(
        MemoryReport(0.0, 0.0, 0.0),
        ThermalReport(0.0, None, False),
        tps_actual=0.0,
        source="product",
        oom_or_crash=True,
    )
    result = report.score_run(run, accuracy=0.0, label="crashed")
    assert result.disqualified is True
    assert result.s_total is None
