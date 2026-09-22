"""Independent synthetic checks of the frozen development selection rules.

No campaign responses, models, network, or inference are used by this module.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "development_review_independent_selection",
    Path(__file__).with_name("development_review.py"),
)
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def score(m=50, s=20, t=20, *, correct=None, critical=0, caps=0):
    flags = [i < m for i in range(64)] if correct is None else list(correct)
    return {
        "M": m,
        "S": s,
        "T": t,
        "critical_cases": critical,
        "mc_correct": flags,
        "caps": caps,
    }


@pytest.fixture
def battery():
    roster = {}
    for number in range(1, 5):
        lineage = f"P{number}"
        roster[f"C{number}"] = {"lineage": lineage, "role": "control", "step": 0}
        for suffix, step in (("half", 63), ("end", 126)):
            roster[f"P{number}-{suffix}"] = {
                "lineage": lineage,
                "role": "pilot",
                "step": step,
            }
    return {candidate: score() for candidate in roster}, roster


def lineage(result, name="P1"):
    return next(row for row in result["lineages"] if row["lineage"] == name)


def candidate(result, name):
    return next(row for row in result["candidates"] if row["candidate_id"] == name)


@pytest.mark.parametrize(
    "m,s,t,numerator,percentage",
    [
        (0, 0, 0, 0, 0),
        (64, 0, 0, 64, 50),
        (0, 32, 32, 64, 50),
        (64, 32, 32, 128, 100),
        (49, 21, 21, 91, 71.09375),
    ],
)
def test_exact_index_and_full_component_report(battery, m, s, t, numerator, percentage):
    scores, roster = battery
    scores = {name: score(m, s, t) for name in scores}
    result = review.select_candidates(scores, roster)
    assert len(result["candidates"]) == 12
    assert {row["candidate_id"] for row in result["candidates"]} == set(roster)
    for row in result["candidates"]:
        assert (row["M"], row["S"], row["T"]) == (m, s, t)
        assert row["index_numerator"] == numerator
        assert row["index_percent"] == percentage


@pytest.mark.parametrize(
    "half,end,selected",
    [
        ((50, 20, 20), (49, 21, 21), "P1-end"),
        ((50, 20, 20), (51, 19, 20), "P1-end"),
        ((50, 19, 21), (50, 20, 20), "P1-end"),
        ((50, 20, 20), (50, 20, 20), "P1-half"),
    ],
)
def test_within_lineage_total_then_mc_then_science_then_earlier(battery, half, end, selected):
    scores, roster = battery
    scores["P1-half"] = score(*half)
    scores["P1-end"] = score(*end)
    row = lineage(review.select_candidates(scores, roster))
    assert row["candidate_id"] == selected
    assert row["selected_checkpoint"] == (63 if selected.endswith("half") else 126)


def test_paired_losses_are_gross_even_when_mc_total_improves(battery):
    scores, roster = battery
    # Control: items 0..49. Candidate: items 3..53, losing 3 and gaining 4.
    flags = [3 <= i < 54 for i in range(64)]
    scores["P1-end"] = score(51, 20, 20, correct=flags)
    result = review.select_candidates(scores, roster)
    row = lineage(result)
    assert row["candidate_id"] == "P1-end"
    assert row["paired_losses"] == 3
    assert row["paired_gains"] == 4
    assert row["eligible"] is False
    assert not any(name.startswith("P1-") for name in result["advance"])


@pytest.mark.parametrize("losses,eligible", [(0, True), (2, True), (3, False)])
def test_guard_boundary_and_no_fallback_to_eligible_sibling(battery, losses, eligible):
    scores, roster = battery
    flags = [losses <= i < 50 for i in range(64)]
    # Extra tutor points make end the selected checkpoint despite MC losses.
    scores["P1-end"] = score(50 - losses, 24, 24, correct=flags)
    result = review.select_candidates(scores, roster)
    row = lineage(result)
    assert row["candidate_id"] == "P1-end"
    assert row["paired_losses"] == losses
    assert row["paired_gains"] == 0
    assert row["eligible"] is eligible
    if not eligible:
        # Half has no regressions; it must not rescue the disqualified lineage.
        assert "P1-half" not in result["advance"]
        assert "P1-end" not in result["advance"]


@pytest.mark.parametrize(
    "control_cases,pilot_cases,eligible", [(0, 0, True), (1, 1, True), (2, 1, True), (1, 2, False)]
)
def test_critical_case_count_guard_and_signed_delta(battery, control_cases, pilot_cases, eligible):
    scores, roster = battery
    scores["C1"] = score(critical=control_cases)
    scores["P1-end"] = score(50, 21, 21, critical=pilot_cases)
    row = lineage(review.select_candidates(scores, roster))
    assert row["critical_case_delta"] == pilot_cases - control_cases
    assert row["eligible"] is eligible


def test_own_unchanged_control_for_historical_adapter_lineage(battery):
    scores, roster = battery
    # C2 is deliberately different; C3 shares all P3 MC successes and its error.
    flags = [i >= 14 for i in range(64)]
    scores["C3"] = score(correct=flags, critical=1)
    scores["P3-half"] = score(correct=flags, critical=1)
    scores["P3-end"] = score(50, 21, 21, correct=flags, critical=1)
    row = lineage(review.select_candidates(scores, roster), "P3")
    assert row["candidate_id"] == "P3-end"
    assert row["paired_losses"] == row["paired_gains"] == 0
    assert row["critical_case_delta"] == 0
    assert row["eligible"] is True


@pytest.mark.parametrize(
    "p1,p2,p3,expected",
    [
        ((50, 20, 20), (50, 20, 20), (50, 20, 20), ["P1-half", "P2-half"]),
        ((50, 20, 20), (50, 20, 20), (49, 21, 21), ["P3-half", "P1-half"]),
        ((50, 20, 20), (50, 20, 20), (51, 19, 20), ["P3-half", "P1-half"]),
        ((50, 20, 20), (50, 20, 20), (50, 21, 19), ["P3-half", "P1-half"]),
    ],
)
def test_cross_lineage_order_is_fixed_and_independent_of_input_order(battery, p1, p2, p3, expected):
    scores, roster = battery
    for number, values in enumerate((p1, p2, p3), start=1):
        scores[f"P{number}-half"] = score(*values)
        scores[f"P{number}-end"] = score(*values)
    scores = dict(reversed(list(scores.items())))
    roster = dict(reversed(list(roster.items())))
    result = review.select_candidates(scores, roster)
    assert [row["lineage"] for row in result["lineages"]] == ["P1", "P2", "P3", "P4"]
    assert result["advance"] == expected
    assert len({name.split("-")[0] for name in result["advance"]}) == len(result["advance"])


def test_cross_lineage_exact_tie_uses_lineage_order_not_checkpoint_step(battery):
    scores, roster = battery
    scores["P1-half"] = score(50, 19, 20)
    assert review.select_candidates(scores, roster)["advance"] == ["P1-end", "P2-half"]


@pytest.mark.parametrize("survivors", [0, 1, 2])
def test_advance_fewer_when_guards_exclude_lineages(battery, survivors):
    scores, roster = battery
    for number in range(survivors + 1, 5):
        scores[f"P{number}-end"] = score(50, 21, 21, critical=1)
    result = review.select_candidates(scores, roster)
    assert result["advance"] == [f"P{number}-half" for number in range(1, survivors + 1)]


def test_caps_remain_reported_without_becoming_an_unfrozen_selection_penalty(battery):
    scores, roster = battery
    scores["P1-half"]["caps"] = 72
    result = review.select_candidates(scores, roster)
    assert candidate(result, "P1-half")["caps"] == 72
    assert lineage(result)["candidate_id"] == "P1-half"
    assert result["advance"] == ["P1-half", "P2-half"]


def test_selection_does_not_mutate_inputs(battery):
    scores, roster = battery
    before = copy.deepcopy(battery)
    review.select_candidates(scores, roster)
    assert (scores, roster) == before


@pytest.mark.parametrize(
    "field,bad",
    [
        ("M", -1),
        ("M", 65),
        ("M", True),
        ("M", 50.0),
        ("M", "50"),
        ("S", -1),
        ("S", 33),
        ("S", False),
        ("S", 20.0),
        ("T", -1),
        ("T", 33),
        ("T", True),
        ("T", 20.0),
        ("critical_cases", -1),
        ("critical_cases", 9),
        ("critical_cases", True),
        ("critical_cases", 0.0),
        ("caps", -1),
        ("caps", 73),
        ("caps", False),
        ("caps", 0.0),
        ("S", float("nan")),
        ("T", float("inf")),
    ],
)
def test_invalid_aggregate_types_and_ranges_fail_closed(battery, field, bad):
    scores, roster = battery
    scores["P1-half"][field] = bad
    with pytest.raises((TypeError, ValueError)):
        review.select_candidates(scores, roster)


@pytest.mark.parametrize(
    "bad",
    [
        [True] * 63,
        [True] * 65,
        [1] * 50 + [0] * 14,
        [True] * 64,
        None,
        "true",
        tuple([True] * 50 + [False] * 14),
    ],
)
def test_mc_flags_require_exact_boolean_vector_matching_m(battery, bad):
    scores, roster = battery
    scores["P1-half"]["mc_correct"] = bad
    with pytest.raises((TypeError, ValueError)):
        review.select_candidates(scores, roster)


@pytest.mark.parametrize("field", ["M", "S", "T", "critical_cases", "mc_correct", "caps"])
def test_missing_score_field_fails_closed(battery, field):
    scores, roster = battery
    del scores["P1-half"][field]
    with pytest.raises((KeyError, TypeError, ValueError)):
        review.select_candidates(scores, roster)


@pytest.mark.parametrize(
    "field,bad",
    [("candidate_id", "C4"), ("lineage", "P4"), ("role", "control"), ("step", 126)],
)
def test_score_metadata_cannot_override_authoritative_candidate_identity(battery, field, bad):
    scores, roster = battery
    scores["P1-half"][field] = bad
    try:
        result = review.select_candidates(scores, roster)
    except (TypeError, ValueError):
        return  # Rejecting unexpected score metadata is also an acceptable defense.
    matches = [row for row in result["candidates"] if row["candidate_id"] == "P1-half"]
    assert len(matches) == 1
    assert {key: matches[0][key] for key in ("lineage", "role", "step")} == roster["P1-half"]


@pytest.mark.parametrize(
    "target,mutation",
    [("scores", "missing"), ("scores", "extra"), ("roster", "missing"), ("roster", "extra")],
)
def test_exact_complete_candidate_roster_required(battery, target, mutation):
    scores, roster = battery
    mapping = scores if target == "scores" else roster
    if mutation == "missing":
        del mapping["P4-end"]
    else:
        mapping["unexpected"] = copy.deepcopy(mapping["P4-end"])
    with pytest.raises((TypeError, ValueError)):
        review.select_candidates(scores, roster)


@pytest.mark.parametrize(
    "name,field,bad",
    [
        ("P1-half", "lineage", "P5"),
        ("P1-half", "lineage", "P2"),
        ("P1-half", "role", "control"),
        ("P1-half", "role", "unknown"),
        ("P1-half", "step", 126),
        ("P1-half", "step", 64),
        ("P1-half", "step", "63"),
        ("P1-half", "step", 63.0),
        ("C1", "step", False),
        ("C1", "step", 63),
        ("C1", "role", "pilot"),
    ],
)
def test_invalid_or_duplicate_lineage_slots_fail_closed(battery, name, field, bad):
    scores, roster = battery
    roster[name][field] = bad
    with pytest.raises((TypeError, ValueError)):
        review.select_candidates(scores, roster)


@pytest.mark.parametrize("field", ["lineage", "role", "step"])
def test_incomplete_roster_metadata_fails_closed(battery, field):
    scores, roster = battery
    del roster["P1-half"][field]
    with pytest.raises((TypeError, ValueError)):
        review.select_candidates(scores, roster)
