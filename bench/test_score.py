"""Tests for the compass.

The ROADMAP names the cases that matter (Tue 14 Jul): peak RAM > 7 GB, TPS > TPS_max, exactly
85.0 C, OOM sentinel propagation, break-even. Added from the profiler findings
(docs/rules-digest.md): the rate at tps_max != 15, and sorting a disqualified run. Added from
the adversarial review: NaN handling, the S_perf clamp's effect on verdicts, and the
attribution invariants in compare().

A silent bug in score.py misdirects a month, so these assert against numbers derived by hand
from the scoring function — never against whatever the code happens to return.
"""

from __future__ import annotations

import dataclasses

import pytest

from bench.score import (
    PROVISIONAL_TPS_MAX,
    RAM_BUDGET_GB,
    DisqualifiedComparison,
    ScoreResult,
    compare,
    exchange_rate,
    score,
)


def _ok(**overrides) -> ScoreResult:
    """A healthy baseline run; override one field per test."""
    kwargs = dict(accuracy=60.0, tps_actual=10.0, peak_rss_gb=4.0, max_temp_c=70.0)
    kwargs.update(overrides)
    return score(**kwargs)  # type: ignore[arg-type]


def _crashed(**overrides) -> ScoreResult:
    kwargs = dict(accuracy=99.0, tps_actual=99.0, peak_rss_gb=1.0, oom_or_crash=True, label="crashed")
    kwargs.update(overrides)
    return score(**kwargs)  # type: ignore[arg-type]


# --- The scoring function itself ---------------------------------------------------------


def test_components_match_hand_calculation():
    # acc=60 -> S_acc=60 -> 0.50*60 = 30.0
    # tps=10/15 -> S_perf=66.667 -> 0.30*66.667 = 20.0
    # ram=4/7 -> S_eff=(7-4)/7*100=42.857 -> 0.20*42.857 = 8.571
    # total = 58.571, no thermal penalty
    r = _ok()
    assert r.s_acc == pytest.approx(60.0)
    assert r.s_perf == pytest.approx(100 * 10 / 15)
    assert r.s_eff == pytest.approx(100 * 3 / 7)
    assert r.pts_from_acc == pytest.approx(30.0)
    assert r.pts_from_perf == pytest.approx(20.0)
    assert r.pts_from_eff == pytest.approx(8.5714, abs=1e-3)
    assert r.s_total == pytest.approx(58.5714, abs=1e-3)
    assert r.p_thermal == 0.0
    assert not r.disqualified


def test_roadmap_worked_example_4gb_to_3gb():
    """The ROADMAP's own illustration: 4 GB -> 3 GB moves S_eff 42.9 -> 57.1.

    If score.py disagrees with this, score.py is wrong.
    """
    a = _ok(peak_rss_gb=4.0, label="4gb")
    b = _ok(peak_rss_gb=3.0, label="3gb")
    assert a.s_eff == pytest.approx(42.857, abs=1e-2)
    assert b.s_eff == pytest.approx(57.143, abs=1e-2)

    c = compare(a, b)
    # 14.2857 S_eff points * 0.20 weight = 2.857 pts of S_total. (The ROADMAP rounds this to
    # 2.84 by using 14.2; the exact figure is 2.857.)
    assert c.delta_total == pytest.approx(2.857, abs=1e-2)
    assert c.driver == "memory"


# --- The ROADMAP's named edge cases -------------------------------------------------------


def test_peak_rss_over_budget_clamps_but_flags():
    """Over 7 GB: S_eff clamps at 0, but the run must not look merely mediocre."""
    r = _ok(peak_rss_gb=8.5)
    assert r.s_eff == 0.0
    assert r.over_budget is True
    assert r.raw_s_eff is not None and r.raw_s_eff < 0  # the truth is preserved
    assert r.pts_from_eff == 0.0
    assert not r.disqualified  # over budget is a *risk*, not itself a disqualification
    assert "raw_eff=-21.4" in r.summary()  # and the distance over is visible


def test_ram_exactly_at_budget_is_not_over():
    r = _ok(peak_rss_gb=RAM_BUDGET_GB)
    assert r.s_eff == 0.0
    assert r.over_budget is False  # boundary: == budget is within budget


def test_tps_above_tps_max_clamps_at_100():
    """Beating the fastest observed submission must not score above 100."""
    r = _ok(tps_actual=100.0)
    assert r.s_perf == 100.0
    assert r.pts_from_perf == pytest.approx(30.0)


def test_temp_exactly_85_is_not_penalised():
    """Boundary: the rule is `> 85`, not `>= 85`. One degree of slop here is 10 points."""
    assert _ok(max_temp_c=85.0).p_thermal == 0.0
    assert _ok(max_temp_c=85.01).p_thermal == 10.0


def test_throttled_penalises_even_when_cool():
    assert _ok(max_temp_c=50.0, throttled=True).p_thermal == 10.0


def test_thermal_penalty_subtracts_from_total():
    cool = _ok(max_temp_c=70.0)
    hot = _ok(max_temp_c=90.0)
    assert hot.s_total == pytest.approx(cool.s_total - 10.0)


def test_break_even_matches_roadmap_at_provisional_tps_max():
    """'1 GB = 1.43 tok/s' — the most-quoted number in the project."""
    rate = exchange_rate()
    assert rate.pts_per_tps == pytest.approx(2.0)
    assert rate.pts_per_gb == pytest.approx(-2.857, abs=1e-3)
    assert rate.pts_per_accuracy_point == 0.5
    assert rate.break_even_tps(1.0) == pytest.approx(1.4286, abs=1e-3)
    # A 1 GB draft model must beat 1.43 tok/s. Well below the clamp, so the linear rate holds.
    assert not rate.is_worth_it(tps_before=5.0, delta_tps=1.4, delta_ram_gb=1.0)
    assert rate.is_worth_it(tps_before=5.0, delta_tps=1.5, delta_ram_gb=1.0)


# --- OOM sentinel propagation -------------------------------------------------------------


def test_oom_returns_sentinel_not_a_number():
    r = _crashed()
    assert r.disqualified is True
    assert r.s_total is None  # never a number
    assert r.s_acc is None and r.s_perf is None and r.s_eff is None
    assert r.disqualification_reason and "hard failure" in r.disqualification_reason


def test_disqualified_run_cannot_be_ranked():
    """A crashed config must never sort against a live one.

    A great-looking crashed run (99 acc, 99 tps, 1 GB) would otherwise top the table.
    """
    good = _ok(label="good")
    crashed = _crashed()
    with pytest.raises(DisqualifiedComparison):
        _ = crashed < good
    with pytest.raises(DisqualifiedComparison):
        _ = good < crashed
    with pytest.raises(DisqualifiedComparison):
        sorted([good, crashed])  # must fail loudly, not silently misrank
    with pytest.raises(DisqualifiedComparison):
        max([good, crashed])


def test_compare_refuses_disqualified_runs():
    with pytest.raises(DisqualifiedComparison):
        compare(_ok(label="good"), _crashed())


def test_healthy_runs_still_sort_normally():
    lo = _ok(accuracy=10.0, label="lo")
    hi = _ok(accuracy=90.0, label="hi")
    assert [r.label for r in sorted([hi, lo])] == ["lo", "hi"]


def test_sorting_by_the_attribute_still_fails_rather_than_misranks():
    """`key=lambda r: r.s_total` bypasses the ordering guard.

    It must still fail — noisily, on None arithmetic — rather than rank the crash. This
    documents a known boundary of the guard; see ScoreResult's docstring.
    """
    with pytest.raises(TypeError):
        sorted([_ok(label="good"), _crashed()], key=lambda r: r.s_total)


# --- NaN: the crater the clamps opened (adversarial review) --------------------------------


def test_nan_peak_rss_is_rejected_not_clamped_to_a_perfect_score():
    """`min(100.0, nan)` returns 100.0 — a NaN would be clamped into the BEST score.

    Reachable the ordinary way: a missing peak_rss_mb in profiler JSON -> float("nan").
    Every later RAM optimization would then be measured against fiction.
    """
    with pytest.raises(ValueError, match="finite"):
        _ok(peak_rss_gb=float("nan"))


def test_nan_tps_is_rejected_so_it_cannot_poison_sorting():
    """A NaN s_total compares False both ways and silently mis-orders a bake-off table."""
    with pytest.raises(ValueError, match="finite"):
        _ok(tps_actual=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        _ok(tps_max=float("nan"))


def test_nan_temperature_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        _ok(max_temp_c=float("nan"))


def test_infinite_inputs_are_rejected():
    with pytest.raises(ValueError, match="finite"):
        _ok(peak_rss_gb=float("inf"))
    with pytest.raises(ValueError, match="finite"):
        exchange_rate(tps_max=float("inf"))


# --- The S_perf clamp changes verdicts (adversarial review) ---------------------------------


def test_verdict_honours_the_clamp_at_the_projects_actual_operating_point():
    """The tier-3 draft-model decision, at the 12-15 tok/s the target actually hits.

    A flat rate prices +5 tok/s at +10 pts and says ship it. But S_perf clamps at tps_max=15,
    so only 1 of those 5 tok/s is worth anything, and the 1 GB costs 2.86. It's a LOSS.
    """
    rate = exchange_rate()
    base = _ok(tps_actual=14.0, peak_rss_gb=4.0, label="base")
    draft = _ok(tps_actual=19.0, peak_rss_gb=5.0, label="+draft")

    actual = draft.s_total - base.s_total  # type: ignore[operator]
    assert actual == pytest.approx(-0.857, abs=1e-2)  # a real loss

    predicted = rate.delta_points(tps_before=14.0, delta_tps=5.0, delta_ram_gb=1.0)
    assert predicted == pytest.approx(actual, abs=1e-6)  # the compass agrees with reality
    assert rate.is_worth_it(tps_before=14.0, delta_tps=5.0, delta_ram_gb=1.0) is False

    # The same change well below the clamp IS worth it — the operating point is the whole story.
    assert rate.is_worth_it(tps_before=5.0, delta_tps=5.0, delta_ram_gb=1.0) is True


def test_delta_points_reproduces_the_actual_score_delta():
    """The predictor must equal the measurement, or it isn't a compass."""
    rate = exchange_rate()
    for tps_before, dtps, dram in [(5.0, 2.0, 1.0), (14.0, 5.0, 1.0), (10.0, -1.0, -0.5), (16.0, 3.0, 0.5)]:
        a = _ok(tps_actual=tps_before, peak_rss_gb=4.0)
        b = _ok(tps_actual=tps_before + dtps, peak_rss_gb=4.0 + dram)
        actual = b.s_total - a.s_total  # type: ignore[operator]
        assert rate.delta_points(tps_before=tps_before, delta_tps=dtps, delta_ram_gb=dram) == pytest.approx(actual, abs=1e-9)


def test_break_even_is_infinite_when_perf_is_already_capped():
    """At the clamp there is no throughput left to buy, so no RAM spend can pay for itself."""
    rate = exchange_rate()
    assert rate.break_even_tps(1.0, tps_before=15.0) == float("inf")
    assert rate.break_even_tps(1.0, tps_before=14.9) == float("inf")  # 0.02 pts of headroom
    assert rate.break_even_tps(1.0, tps_before=5.0) == pytest.approx(1.4286, abs=1e-3)
    # Without an operating point you get the linear-region figure — valid only below the clamp.
    assert rate.break_even_tps(1.0) == pytest.approx(1.4286, abs=1e-3)


def test_accuracy_can_be_traded_against_throughput():
    """The ROADMAP's other break-even: an accuracy technique that costs throughput.

    At tps_max=15, 1 tok/s = 2.0 pts and 1 accuracy point = 0.5 pts, so surrendering a tok/s
    needs 4 accuracy points to break even.
    """
    rate = exchange_rate()
    assert rate.is_worth_it(tps_before=10.0, delta_tps=-1.0, delta_accuracy=4.1) is True
    assert rate.is_worth_it(tps_before=10.0, delta_tps=-1.0, delta_accuracy=3.9) is False


# --- compare() attribution (adversarial review: a sign flip used to pass) -------------------


def test_thermal_delta_is_signed_against_the_penalty():
    """P_thermal is SUBTRACTED, so a smaller penalty is a positive delta.

    Previously untested: a sign flip and a hardcoded 0.0 both passed the whole suite.
    """
    cool = _ok(max_temp_c=70.0, label="cool")
    hot = _ok(max_temp_c=90.0, label="hot")
    assert compare(cool, hot).delta_from_thermal == -10.0  # going hot loses 10
    assert compare(hot, cool).delta_from_thermal == +10.0  # cooling down gains 10
    assert compare(cool, hot).driver == "thermal"


def test_delta_components_sum_to_delta_total():
    """The invariant that makes the whole attribution table trustworthy."""
    a = _ok(accuracy=50.0, tps_actual=8.0, peak_rss_gb=5.0, max_temp_c=90.0, label="a")
    b = _ok(accuracy=70.0, tps_actual=12.0, peak_rss_gb=3.0, max_temp_c=70.0, label="b")
    c = compare(a, b)
    assert (
        c.delta_from_acc + c.delta_from_perf + c.delta_from_eff + c.delta_from_thermal
    ) == pytest.approx(c.delta_total)


def test_driver_names_the_biggest_mover():
    base = _ok(accuracy=50.0, tps_actual=10.0, peak_rss_gb=4.0, label="base")
    assert compare(base, _ok(accuracy=90.0, tps_actual=10.0, peak_rss_gb=4.0)).driver == "accuracy"
    assert compare(base, _ok(accuracy=50.0, tps_actual=14.0, peak_rss_gb=4.0)).driver == "throughput"
    assert compare(base, _ok(accuracy=50.0, tps_actual=10.0, peak_rss_gb=1.0)).driver == "memory"


# --- The findings from docs/rules-digest.md ------------------------------------------------


def test_exchange_rate_varies_with_tps_max():
    """TPS_max is 'highest speed across all submissions', not a constant.

    The famous 1.43 break-even holds ONLY at the provisional 15. Hardcoding 2.0 pts/tok-s
    would misprice every RAM-spending optimization once the real cohort max is known.
    """
    at15 = exchange_rate(15.0)
    at30 = exchange_rate(30.0)
    assert at15.pts_per_tps == pytest.approx(2.0)
    assert at30.pts_per_tps == pytest.approx(1.0)  # a tok/s is worth half as much
    assert at30.break_even_tps(1.0) == pytest.approx(2.857, abs=1e-3)  # break-even doubles

    # RAM's cost is independent of tps_max — only the throughput side rescales.
    assert at15.pts_per_gb == pytest.approx(at30.pts_per_gb)

    # The sign flip: spending 1 GB for 2.0 tok/s wins at 15, loses at 30. (tps_before well
    # below both clamps so this isolates the rate, not the clamp.)
    assert at15.is_worth_it(tps_before=5.0, delta_tps=2.0, delta_ram_gb=1.0)
    assert not at30.is_worth_it(tps_before=5.0, delta_tps=2.0, delta_ram_gb=1.0)


def test_tps_max_provenance_is_carried_and_enforced():
    """A number must not silently claim authority it doesn't have."""
    assert exchange_rate().tps_max_provenance == "provisional_reference"
    r = score(
        accuracy=50.0, tps_actual=5.0, peak_rss_gb=3.0, tps_max=22.0,
        tps_max_provenance="cohort_observed",
    )
    assert r.exchange.tps_max_provenance == "cohort_observed"
    with pytest.raises(ValueError, match="provenance"):
        exchange_rate(tps_max_provenance="totally_made_up")  # type: ignore[arg-type]


def test_unknown_temperature_is_flagged_not_assumed_safe():
    """The profiler allows a null temp on cloud VMs. 'Unmeasured' must not read as 'fine'."""
    r = _ok(max_temp_c=None)
    assert r.thermal_unknown is True
    assert r.p_thermal == 0.0  # matches the profiler: no reading, no penalty
    assert "UNKNOWN" in r.summary()

    measured = _ok(max_temp_c=70.0)
    assert measured.thermal_unknown is False
    assert "UNKNOWN" not in measured.summary()


# --- Input validation / API misuse ---------------------------------------------------------


@pytest.mark.parametrize("bad", [-1.0, 101.0])
def test_accuracy_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        _ok(accuracy=bad)


def test_negative_inputs_raise():
    with pytest.raises(ValueError):
        _ok(tps_actual=-1.0)
    with pytest.raises(ValueError):
        _ok(peak_rss_gb=-1.0)
    with pytest.raises(ValueError):
        exchange_rate(tps_max=0.0)


def test_megabytes_passed_as_gigabytes_is_rejected():
    """The profiler reports peak_rss_**mb**, so this is the expected slip at the boundary.

    4200 (MB) would otherwise score a plausible-looking 50.00 and go into the log.
    """
    with pytest.raises(ValueError, match="megabytes"):
        _ok(peak_rss_gb=4200.0)


def test_validation_does_not_mask_disqualification():
    """A crashed run short-circuits before validation — we must report the crash, not a
    ValueError about the garbage it left behind."""
    r = score(accuracy=-5.0, tps_actual=float("nan"), peak_rss_gb=-1.0, oom_or_crash=True)
    assert r.disqualified is True


def test_inputs_record_is_immutable():
    """A frozen result whose evidence can be rewritten in place is not a record."""
    r = _ok()
    with pytest.raises(TypeError):
        r.inputs["peak_rss_gb"] = 999  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.label = "rewritten"  # type: ignore[misc]


def test_compare_warns_across_different_tps_max(caplog):
    a = score(accuracy=50.0, tps_actual=10.0, peak_rss_gb=3.0, tps_max=15.0, label="a")
    b = score(accuracy=50.0, tps_actual=10.0, peak_rss_gb=3.0, tps_max=30.0, label="b")
    with caplog.at_level("WARNING"):
        compare(a, b)
    assert "not on the same scale" in caplog.text


def test_compare_warns_across_different_ram_budget(caplog):
    """An identical run scored against a different budget reads as a free +5.71 pts."""
    a = score(accuracy=60.0, tps_actual=10.0, peak_rss_gb=4.0, ram_budget_gb=7.0, label="a")
    b = score(accuracy=60.0, tps_actual=10.0, peak_rss_gb=4.0, ram_budget_gb=14.0, label="b")
    with caplog.at_level("WARNING"):
        c = compare(a, b)
    assert "ram_budget_gb" in caplog.text
    assert c.delta_total > 0  # the phantom win the warning exists to explain


def test_over_budget_logs_a_warning(caplog):
    with caplog.at_level("WARNING"):
        _ok(peak_rss_gb=9.0, label="fat")
    assert "EXCEEDS" in caplog.text
    assert "disqualification risk" in caplog.text


def test_defaults_are_the_documented_constants():
    assert PROVISIONAL_TPS_MAX == 15.0
    assert RAM_BUDGET_GB == 7.0
