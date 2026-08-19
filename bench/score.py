"""The scoring function — the compass every optimization is judged against.

    S_total = 0.50*S_acc + 0.30*S_perf + 0.20*S_eff - P_thermal

This module is a *decision tool*, not a scoreboard. The number that matters is rarely
`s_total`; it is the marginal rate — what a tok/s is worth against what a gigabyte costs —
because that is what says whether an optimization is worth doing before you do it.

A silent bug here misdirects a month of work (ROADMAP, Tue 14 Jul), so:

1. A disqualified run has `s_total = None` and **raises** on ordering. It can never be
   silently ranked against a working config; `sorted()` on a mixed list fails loudly.
2. Every numeric input must be **finite**. NaN sails through `min()`/`max()` clamps and
   silently produces the *best possible* score — see `_check_finite`.
3. The executable official profiler is the score-of-record: `S_perf =
   min(TPS/15, 1)*100`. The challenge webpage's cohort-relative formula is retained as an
   explicitly named sensitivity mode because the two public organiser sources conflict.

Verified against the ADTC profiler source (docs/rules-digest.md); read that before trusting
any assumption here. Note `peak_rss_gb` is **RSS**, not PSS: the profiler measures RSS, and
since RSS >= PSS under `mmap`, passing PSS would inflate `S_eff` in the flattering direction.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, get_args

log = logging.getLogger("muta.bench.score")

# --- Constants from the scoring function -------------------------------------------------
W_ACC = 0.50
W_PERF = 0.30
W_EFF = 0.20
RAM_BUDGET_GB = 7.0
THERMAL_LIMIT_C = 85.0
THERMAL_PENALTY = 10.0

# The executable profiler fixes TPS_REFERENCE at 15. The official challenge webpage instead
# defines TPS_max as the highest speed across all submissions. The default follows the profiler;
# `tps_max_provenance` and `performance_formula` preserve the alternative without blending it.
PROVISIONAL_TPS_MAX = 15.0

# Nothing on a 7 GB-budget laptop legitimately uses 70 GB. The profiler reports peak_rss_**mb**
# (docs/rules-digest.md), so MB-into-a-GB-parameter is the expected slip. Catch it.
_ABSURD_RAM_MULTIPLE = 10.0

TpsMaxProvenance = Literal["profiler_reference", "provisional_reference", "cohort_observed"]
PerformanceFormula = Literal["profiler_capped", "website_relative"]


def _check_finite(**values: float) -> None:
    """Reject NaN/inf before they reach a clamp.

    Not defensive padding. `min(100.0, nan)` returns `100.0`, so a NaN `peak_rss_gb` gets
    clamped into a *perfect* efficiency term and every later RAM optimization is then measured
    against fiction. NaN arrives the ordinary way: a missing `peak_rss_mb` in profiler JSON
    parsed as `float("nan")`.
    """
    for name, v in values.items():
        if not math.isfinite(v):
            raise ValueError(f"{name} must be finite, got {v!r}")


@dataclass(frozen=True)
class ExchangeRate:
    """Marginal points per unit of each resource — the reason this module exists.

    `profiler_capped` matches the official profiler README/code and is the default.
    `website_relative` reproduces the conflicting public challenge-page formula for a
    labelled sensitivity analysis only.

    The profiler fixes `tps_max` at 15, producing the project's 1 GB = 1.43 tok/s exchange
    below the cap. A different denominator is meaningful only in website-relative sensitivity.
    """

    pts_per_tps: float  # pre-cap for profiler mode; always linear for website-relative mode
    pts_per_gb: float  # negative: RAM costs points
    pts_per_accuracy_point: float
    tps_max: float
    tps_max_provenance: TpsMaxProvenance
    performance_formula: PerformanceFormula

    def s_perf_at(self, tps: float) -> float:
        """S_perf at a given throughput under the recorded formula."""
        ratio = tps / self.tps_max
        if self.performance_formula == "profiler_capped":
            ratio = min(ratio, 1.0)
        return 100.0 * ratio

    def delta_points(
        self,
        *,
        tps_before: float,
        delta_tps: float = 0.0,
        delta_ram_gb: float = 0.0,
        delta_accuracy: float = 0.0,
    ) -> float:
        """Points a change is worth **from a given operating point**.

        `tps_before` is required because profiler mode caps at 15. Website-relative mode is
        linear and therefore independent of the operating point.
        """
        _check_finite(
            tps_before=tps_before,
            delta_tps=delta_tps,
            delta_ram_gb=delta_ram_gb,
            delta_accuracy=delta_accuracy,
        )
        perf_gain = W_PERF * (self.s_perf_at(tps_before + delta_tps) - self.s_perf_at(tps_before))
        return (
            perf_gain
            + delta_ram_gb * self.pts_per_gb
            + delta_accuracy * self.pts_per_accuracy_point
        )

    def is_worth_it(
        self,
        *,
        tps_before: float,
        delta_tps: float = 0.0,
        delta_ram_gb: float = 0.0,
        delta_accuracy: float = 0.0,
    ) -> bool:
        """Does this change gain points? Strictly — exactly break-even is not worth it."""
        return (
            self.delta_points(
                tps_before=tps_before,
                delta_tps=delta_tps,
                delta_ram_gb=delta_ram_gb,
                delta_accuracy=delta_accuracy,
            )
            > 0
        )

    def break_even_tps(self, delta_ram_gb: float, tps_before: float | None = None) -> float:
        """tok/s gain that exactly pays for `delta_ram_gb` more RAM. Beat it strictly.

        With `tps_before=None` this is the linear figure — the ROADMAP's 1.43 × ΔRAM at the
        profiler reference. It is valid below the cap in profiler mode and everywhere in
        website-relative sensitivity mode.

        With `tps_before` given, the profiler cap is honoured. Website-relative mode has no
        saturation point, so its break-even remains the linear figure.
        """
        _check_finite(delta_ram_gb=delta_ram_gb)
        if self.pts_per_tps == 0:
            return float("inf")
        required_pts = abs(self.pts_per_gb) * delta_ram_gb
        linear = required_pts / self.pts_per_tps
        if (
            self.performance_formula == "website_relative"
            or tps_before is None
            or delta_ram_gb <= 0
        ):
            return linear
        _check_finite(tps_before=tps_before)
        headroom_pts = W_PERF * (100.0 - self.s_perf_at(tps_before))
        if required_pts > headroom_pts:
            return float("inf")  # unrecoverable: not enough S_perf left to buy
        return linear


def exchange_rate(
    tps_max: float = PROVISIONAL_TPS_MAX,
    tps_max_provenance: TpsMaxProvenance = "profiler_reference",
    ram_budget_gb: float = RAM_BUDGET_GB,
    performance_formula: PerformanceFormula = "profiler_capped",
) -> ExchangeRate:
    _check_finite(tps_max=tps_max, ram_budget_gb=ram_budget_gb)
    if tps_max <= 0:
        raise ValueError(f"tps_max must be > 0, got {tps_max}")
    if ram_budget_gb <= 0:
        raise ValueError(f"ram_budget_gb must be > 0, got {ram_budget_gb}")
    # Provenance exists so a number can't silently claim authority it doesn't have — so it has
    # to actually be one of the two things, not merely type-hinted as one.
    if tps_max_provenance not in get_args(TpsMaxProvenance):
        raise ValueError(
            f"tps_max_provenance must be one of {get_args(TpsMaxProvenance)}, "
            f"got {tps_max_provenance!r}"
        )
    if performance_formula not in get_args(PerformanceFormula):
        raise ValueError(
            f"performance_formula must be one of {get_args(PerformanceFormula)}, "
            f"got {performance_formula!r}"
        )
    if performance_formula == "profiler_capped":
        if tps_max != PROVISIONAL_TPS_MAX or tps_max_provenance != "profiler_reference":
            raise ValueError(
                "profiler_capped requires tps_max=15 and tps_max_provenance='profiler_reference'"
            )
    elif tps_max_provenance != "cohort_observed":
        raise ValueError("website_relative requires tps_max_provenance='cohort_observed'")
    return ExchangeRate(
        pts_per_tps=W_PERF * 100.0 / tps_max,
        pts_per_gb=-W_EFF * 100.0 / ram_budget_gb,
        pts_per_accuracy_point=W_ACC,
        tps_max=tps_max,
        tps_max_provenance=tps_max_provenance,
        performance_formula=performance_formula,
    )


class DisqualifiedComparison(TypeError):
    """Raised when a disqualified run is ordered against anything.

    A crashed config has no score. Letting it sort as 0.0 would rank it against working
    configs and quietly bury the crash — the failure the sentinel exists to prevent. See
    ROADMAP Tue 14 Jul: "never a number".
    """


@dataclass(frozen=True)
class ScoreResult:
    """One scored run.

    `s_total is None` iff `disqualified`. Ordering raises rather than lying.

    Known boundary, stated rather than hidden: the guard covers **ordering**. Code that reads
    `.s_total` off a disqualified run and sorts on that (`key=lambda r: r.s_total`) bypasses
    the guard — it then fails on `None` arithmetic rather than silently misranking, which is
    noisy but not the tidy error. Serialising with `asdict()` yields `s_total: None`, which a
    tool like pandas would coerce to NaN and rank: check `disqualified` before exporting.
    """

    label: str
    disqualified: bool
    disqualification_reason: str | None
    s_total: float | None
    s_acc: float | None
    s_perf: float | None
    s_eff: float | None
    p_thermal: float
    # Points each component actually contributed to s_total (weight applied).
    pts_from_acc: float | None
    pts_from_perf: float | None
    pts_from_eff: float | None
    exchange: ExchangeRate
    # Set when peak RSS exceeded the budget: S_eff clamps at 0, so the score alone can never
    # show how far over you went — and over budget risks an OOM kill, which is a
    # disqualification rather than a low score.
    over_budget: bool = False
    raw_s_eff: float | None = None
    # True when temperature was unmeasurable (the profiler allows null on cloud VMs). No
    # penalty is applied, but "we didn't measure it" must not read as "it was fine".
    thermal_unknown: bool = False
    # Read-only: this is the evidence for the score. A frozen result whose provenance can be
    # rewritten in place is not a record.
    inputs: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def _guard(self, other: object) -> None:
        if self.disqualified or (isinstance(other, ScoreResult) and other.disqualified):
            raise DisqualifiedComparison(
                "cannot order a disqualified run "
                f"({self.label!r} disqualified={self.disqualified}); "
                "a crashed config has no score and must not be ranked"
            )

    def __lt__(self, other: ScoreResult) -> bool:
        self._guard(other)
        return self.s_total < other.s_total  # type: ignore[operator]

    def __le__(self, other: ScoreResult) -> bool:
        self._guard(other)
        return self.s_total <= other.s_total  # type: ignore[operator]

    def __gt__(self, other: ScoreResult) -> bool:
        self._guard(other)
        return self.s_total > other.s_total  # type: ignore[operator]

    def __ge__(self, other: ScoreResult) -> bool:
        self._guard(other)
        return self.s_total >= other.s_total  # type: ignore[operator]

    def summary(self) -> str:
        if self.disqualified:
            return f"{self.label or 'run'}: DISQUALIFIED — {self.disqualification_reason}"
        parts = [
            f"S_total={self.s_total:.2f}",
            f"acc={self.s_acc:.1f}({self.pts_from_acc:+.2f})",  # type: ignore[arg-type]
            f"perf={self.s_perf:.1f}({self.pts_from_perf:+.2f})",  # type: ignore[arg-type]
            f"eff={self.s_eff:.1f}({self.pts_from_eff:+.2f})",  # type: ignore[arg-type]
        ]
        if self.p_thermal:
            parts.append(f"thermal={-self.p_thermal:+.1f}")
        if self.thermal_unknown:
            parts.append("temp=UNKNOWN")
        if self.over_budget:
            # Show raw_s_eff: clamped at 0.0, "slightly over budget" and "you passed MB instead
            # of GB" look identical.
            parts.append(f"OVER-BUDGET(raw_eff={self.raw_s_eff:.1f})")  # type: ignore[arg-type]
        return f"{self.label or 'run'}: " + " ".join(parts)


def score(
    *,
    accuracy: float,
    tps_actual: float,
    peak_rss_gb: float,
    tps_max: float = PROVISIONAL_TPS_MAX,
    tps_max_provenance: TpsMaxProvenance = "profiler_reference",
    performance_formula: PerformanceFormula = "profiler_capped",
    ram_budget_gb: float = RAM_BUDGET_GB,
    max_temp_c: float | None = None,
    throttled: bool = False,
    oom_or_crash: bool = False,
    label: str = "",
) -> ScoreResult:
    """Score one run.

    Args:
        accuracy: 0-100. Per docs/rules-digest.md this is an lm-eval score on the GGUF, not a
            measure of tutoring quality.
        tps_actual: generation (decode) tok/s. Prefill is not scored.
        peak_rss_gb: peak **RSS** of the whole process tree, in GB. Named for the metric rather
            than for "memory", because the profiler scores RSS and PSS would flatter us.
        tps_max: throughput reference. Defaults to the profiler's fixed 15.0.
        performance_formula: official-profiler capped formula by default. Use
            `website_relative` only for the conflicting challenge-page sensitivity case.
        max_temp_c: peak core temperature, or None if unmeasurable.
        oom_or_crash: OOM kill, sandbox crash, or illegal-instruction fault.
    """
    rate = exchange_rate(tps_max, tps_max_provenance, ram_budget_gb, performance_formula)
    inputs = MappingProxyType(
        {
            "accuracy": accuracy,
            "tps_actual": tps_actual,
            "peak_rss_gb": peak_rss_gb,
            "tps_max": tps_max,
            "performance_formula": performance_formula,
            "ram_budget_gb": ram_budget_gb,
            "max_temp_c": max_temp_c,
            "throttled": throttled,
            "oom_or_crash": oom_or_crash,
        }
    )

    # (1) Hard failure short-circuits everything — including validation, because a crash often
    # leaves garbage numbers behind and we must report the crash, not a ValueError about it.
    if oom_or_crash:
        reason = (
            "OOM kill / execution crash / illegal instruction — a hard failure, not a deduction"
        )
        log.error("%s: DISQUALIFIED — %s", label or "run", reason)
        return ScoreResult(
            label=label,
            disqualified=True,
            disqualification_reason=reason,
            s_total=None,
            s_acc=None,
            s_perf=None,
            s_eff=None,
            p_thermal=0.0,
            pts_from_acc=None,
            pts_from_perf=None,
            pts_from_eff=None,
            exchange=rate,
            inputs=inputs,
        )

    _check_finite(accuracy=accuracy, tps_actual=tps_actual, peak_rss_gb=peak_rss_gb)
    if max_temp_c is not None:
        _check_finite(max_temp_c=max_temp_c)
    if not 0.0 <= accuracy <= 100.0:
        raise ValueError(f"accuracy must be in [0, 100], got {accuracy}")
    if tps_actual < 0:
        raise ValueError(f"tps_actual must be >= 0, got {tps_actual}")
    if performance_formula == "website_relative" and tps_actual > tps_max:
        raise ValueError(
            "website_relative requires TPS_actual <= TPS_max; the candidate is part of the cohort"
        )
    if peak_rss_gb < 0:
        raise ValueError(f"peak_rss_gb must be >= 0, got {peak_rss_gb}")
    if peak_rss_gb > _ABSURD_RAM_MULTIPLE * ram_budget_gb:
        raise ValueError(
            f"peak_rss_gb={peak_rss_gb} is implausible against a {ram_budget_gb} GB budget — "
            "did you pass megabytes? The profiler reports peak_rss_mb."
        )

    if peak_rss_gb > ram_budget_gb:
        raw_s_eff = 100.0 * (ram_budget_gb - peak_rss_gb) / ram_budget_gb
        reason = f"peak RSS {peak_rss_gb:.2f} GB exceeds the {ram_budget_gb:.2f} GB hard budget"
        log.error("%s: DISQUALIFIED — %s", label or "run", reason)
        return ScoreResult(
            label=label,
            disqualified=True,
            disqualification_reason=reason,
            s_total=None,
            s_acc=None,
            s_perf=None,
            s_eff=None,
            p_thermal=0.0,
            pts_from_acc=None,
            pts_from_perf=None,
            pts_from_eff=None,
            exchange=rate,
            over_budget=True,
            raw_s_eff=raw_s_eff,
            thermal_unknown=max_temp_c is None,
            inputs=inputs,
        )

    # (2) Accuracy passes through.
    s_acc = accuracy

    # (3) Perf. The executable official profiler caps at its fixed 15 tok/s reference.
    s_perf = rate.s_perf_at(tps_actual)

    # (4) Efficiency. Over-budget runs returned a disqualification sentinel above.
    raw_s_eff = 100.0 * (ram_budget_gb - peak_rss_gb) / ram_budget_gb
    over_budget = raw_s_eff < 0
    s_eff = max(0.0, min(100.0, raw_s_eff))

    # (5) Thermal. Unknown temperature applies no penalty (matching the profiler, which allows
    # a null reading on cloud VMs) but is flagged so it can't pass as "measured and fine".
    thermal_unknown = max_temp_c is None
    over_temp = max_temp_c is not None and max_temp_c > THERMAL_LIMIT_C
    p_thermal = THERMAL_PENALTY if (over_temp or throttled) else 0.0

    # (6) Combine.
    pts_from_acc = W_ACC * s_acc
    pts_from_perf = W_PERF * s_perf
    pts_from_eff = W_EFF * s_eff
    s_total = pts_from_acc + pts_from_perf + pts_from_eff - p_thermal

    return ScoreResult(
        label=label,
        disqualified=False,
        disqualification_reason=None,
        s_total=s_total,
        s_acc=s_acc,
        s_perf=s_perf,
        s_eff=s_eff,
        p_thermal=p_thermal,
        pts_from_acc=pts_from_acc,
        pts_from_perf=pts_from_perf,
        pts_from_eff=pts_from_eff,
        exchange=rate,
        over_budget=over_budget,
        raw_s_eff=raw_s_eff,
        thermal_unknown=thermal_unknown,
        inputs=inputs,
    )


@dataclass(frozen=True)
class Comparison:
    """Which component moved, and by how many points of S_total."""

    label_a: str
    label_b: str
    delta_total: float
    delta_from_acc: float
    delta_from_perf: float
    delta_from_eff: float
    delta_from_thermal: float

    @property
    def driver(self) -> str:
        """The component that moved S_total most (by absolute points)."""
        candidates = {
            "accuracy": self.delta_from_acc,
            "throughput": self.delta_from_perf,
            "memory": self.delta_from_eff,
            "thermal": self.delta_from_thermal,
        }
        return max(candidates, key=lambda k: abs(candidates[k]))

    def summary(self) -> str:
        return (
            f"{self.label_b} vs {self.label_a}: {self.delta_total:+.2f} pts "
            f"(driven by {self.driver}; "
            f"acc {self.delta_from_acc:+.2f}, perf {self.delta_from_perf:+.2f}, "
            f"eff {self.delta_from_eff:+.2f}, thermal {self.delta_from_thermal:+.2f})"
        )


def compare(run_a: ScoreResult, run_b: ScoreResult) -> Comparison:
    """Point-attributed delta from `run_a` to `run_b`.

    Raises if either run is disqualified — there is nothing meaningful to compare.
    """
    for r in (run_a, run_b):
        if r.disqualified:
            raise DisqualifiedComparison(
                f"cannot compare against a disqualified run ({r.label!r}): "
                f"{r.disqualification_reason}"
            )
    # Both scales are derived from a denominator. Comparing across different ones attributes
    # the *change of yardstick* to a component, which reads as a free win.
    if run_a.exchange.tps_max != run_b.exchange.tps_max:
        log.warning(
            "comparing runs scored against different tps_max (%.2f vs %.2f) — "
            "their perf components are not on the same scale",
            run_a.exchange.tps_max,
            run_b.exchange.tps_max,
        )
    if run_a.exchange.performance_formula != run_b.exchange.performance_formula:
        log.warning(
            "comparing runs scored under different performance formulas (%s vs %s) — "
            "their perf components are not comparable",
            run_a.exchange.performance_formula,
            run_b.exchange.performance_formula,
        )
    budget_a = run_a.inputs.get("ram_budget_gb")
    budget_b = run_b.inputs.get("ram_budget_gb")
    if budget_a != budget_b:
        log.warning(
            "comparing runs scored against different ram_budget_gb (%s vs %s) — "
            "their efficiency components are not on the same scale",
            budget_a,
            budget_b,
        )
    return Comparison(
        label_a=run_a.label,
        label_b=run_b.label,
        delta_total=run_b.s_total - run_a.s_total,  # type: ignore[operator]
        delta_from_acc=run_b.pts_from_acc - run_a.pts_from_acc,  # type: ignore[operator]
        delta_from_perf=run_b.pts_from_perf - run_a.pts_from_perf,  # type: ignore[operator]
        delta_from_eff=run_b.pts_from_eff - run_a.pts_from_eff,  # type: ignore[operator]
        # P_thermal is subtracted, so a *smaller* penalty is a *positive* delta.
        delta_from_thermal=run_a.p_thermal - run_b.p_thermal,
    )
