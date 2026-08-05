"""Adapt a profiler report (or our own samplers) into `bench.score.score()` inputs.

One rule dominates this module: **never let `throttled` be the sole thermal signal.** Upstream
`thermal.py` computes `throttled = peak_temp >= 95.0`, but the competition penalty applies
above **85 C**. A run peaking at 90 C therefore reports `throttled: false` while incurring the
-10 in reality. `score()` already knows the 85 C rule, so both `max_temp_c` and `throttled`
are passed through and it decides.

Second rule: a missing measurement raises. Defaulting an absent `tokens_per_second_generation`
to 0.0 would silently score a successful run as a catastrophic one.
"""

from __future__ import annotations

from dataclasses import dataclass

from bench.sampler import MemoryReport, ThermalReport
from bench.score import PROVISIONAL_TPS_MAX, ScoreResult, score


class ProfilerReportError(ValueError):
    """The profiler report is missing a field the score depends on."""


@dataclass(frozen=True)
class MeasuredRun:
    """One measured run, from either path, in a shape `score()` can consume."""

    source: str  # "profiler" (scored path) | "product" (the path that can OOM)
    tps_actual: float
    peak_rss_gb: float
    steady_rss_gb: float
    first_token_latency_ms: float | None
    max_temp_c: float | None
    throttled: bool
    cpu_percent_p99: float
    oom_or_crash: bool = False
    # True when TPS came from wall-clock rather than the engine's own timings. Recorded so a
    # derived number is never mistaken for a measured one.
    tps_from_wall_clock: bool = False


def _section(data: dict, name: str) -> dict:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ProfilerReportError(
            f"profiler report is missing the required '{name}' section; "
            "refusing to default it — a defaulted measurement is a wrong score"
        )
    return value


def _number(section: dict, key: str, where: str) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)):
        raise ProfilerReportError(f"profiler report is missing {where}.{key}")
    return float(value)


def from_profiler_json(data: dict) -> MeasuredRun:
    """Parse the official profiler's JSON output."""
    throughput = _section(data, "throughput")
    memory = _section(data, "memory")
    # cpu_thermal is optional in the schema. Absent means *unmeasured*, not *safe*.
    thermal = data.get("cpu_thermal") or {}

    temp = thermal.get("core_temp_c_peak")
    return MeasuredRun(
        source="profiler",
        tps_actual=_number(throughput, "tokens_per_second_generation", "throughput"),
        peak_rss_gb=_number(memory, "peak_rss_mb", "memory") / 1024.0,
        steady_rss_gb=_number(memory, "steady_state_rss_mb", "memory") / 1024.0,
        first_token_latency_ms=(
            float(throughput["first_token_latency_ms"])
            if isinstance(throughput.get("first_token_latency_ms"), (int, float))
            else None
        ),
        max_temp_c=float(temp) if isinstance(temp, (int, float)) else None,
        throttled=bool(thermal.get("throttled", False)),
        cpu_percent_p99=float(thermal.get("cpu_percent_p99") or 0.0),
    )


def from_samplers(
    memory: MemoryReport,
    thermal: ThermalReport,
    *,
    tps_actual: float,
    source: str,
    first_token_latency_ms: float | None = None,
    tps_from_wall_clock: bool = False,
    oom_or_crash: bool = False,
) -> MeasuredRun:
    """Build a run from our own samplers — the product path."""
    return MeasuredRun(
        source=source,
        tps_actual=tps_actual,
        peak_rss_gb=memory.peak_rss_gb,
        steady_rss_gb=memory.steady_state_rss_gb,
        first_token_latency_ms=first_token_latency_ms,
        max_temp_c=thermal.core_temp_c_peak,
        throttled=thermal.throttled,
        cpu_percent_p99=thermal.cpu_percent_p99,
        oom_or_crash=oom_or_crash,
        tps_from_wall_clock=tps_from_wall_clock,
    )


def score_run(
    run: MeasuredRun,
    *,
    accuracy: float,
    label: str,
    tps_max: float = PROVISIONAL_TPS_MAX,
) -> ScoreResult:
    """Score a measured run. Both thermal signals go in; score() applies the 85 C rule."""
    return score(
        accuracy=accuracy,
        tps_actual=run.tps_actual,
        peak_rss_gb=run.peak_rss_gb,
        tps_max=tps_max,
        max_temp_c=run.max_temp_c,
        throttled=run.throttled,
        oom_or_crash=run.oom_or_crash,
        label=label,
    )


def params_match(data: dict) -> bool:
    """Read the profiler's GGUF fraud check.

    Absent `model_info` means the profiler could not parse the header, not that we cheated.
    Since profiler 7adbe08, `fraud_check` returns None (JSON null) when the claim or header
    is unparseable — "uncheckable", not "fraud". `bool(None)` would turn that into a false
    alarm (autotest exit 3), so only an explicit False fails.
    """
    info = data.get("model_info")
    if not isinstance(info, dict) or "params_match" not in info:
        return True
    return info["params_match"] is not False
