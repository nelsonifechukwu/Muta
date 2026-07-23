"""Verifier tests (TDD T8 acceptance: 60-expression golden set, 100% correctness).

The golden set is the acceptance criterion, so it runs as one parametrised test per case —
a single "59/60 passed" assertion would hide *which* case regressed, and the negative cases
are the ones that matter most: a verifier that says yes to everything passes any
positive-only suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.tools.sandbox import VERIFIER_LIMITS, WorkerPool
from orchestrator.tools.verifier import (
    HONEST_FALLBACK,
    AnswerVerifier,
    extract_answer,
    verify_with_retry,
)

GOLDENS = Path(__file__).resolve().parent.parent / "tools" / "goldens" / "verify_goldens.json"
CASES = json.loads(GOLDENS.read_text())["cases"]


@pytest.fixture(scope="module")
def verifier():
    pool = WorkerPool(2, VERIFIER_LIMITS).start()
    yield AnswerVerifier(pool)
    pool.close()


def test_golden_set_is_the_promised_size_and_is_not_all_positive():
    assert len(CASES) == 60, "T8 promises 60 expressions"
    negatives = [c for c in CASES if not c["equivalent"]]
    assert len(negatives) >= 20, "a verifier that never says no is not a verifier"


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['candidate']} == {c['expected']}")
def test_golden(case, verifier):
    outcome = verifier.check_text(case["candidate"], case["expected"])
    assert outcome.checked, f"verifier gave no verdict: {outcome.detail}"
    assert outcome.verified is case["equivalent"], case["note"]


# --- extraction --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply,expected",
    [
        (r"So x = 5 and therefore \boxed{25}", "25"),
        (r"\boxed{\frac{1}{2}}", r"\frac{1}{2}"),
        ("Therefore, the answer is 42.", "42"),
        ("The answer is: -7", "-7"),
        ("Final answer: x = 3", "x = 3"),
        ("Working it out, we get y = 3x + 2", "3x + 2"),
    ],
)
def test_extracts_the_conventions_models_actually_use(reply, expected):
    assert extract_answer(reply) == expected


def test_a_bare_equation_is_the_answer_not_a_prefix_to_split():
    """`y = 3x + 2` is an answer containing `=`; splitting it would return `3x + 2` and mark
    a correct student wrong."""
    assert extract_answer("y = 3x + 2") is None
    assert extract_answer("x = 2, x = 3") is None


def test_socratic_turns_have_no_answer_to_extract():
    """The 50% accuracy term is tutoring quality, and a Socratic reply that never states the
    answer is correct behaviour — the verifier must not invent one from the student's own
    working."""
    assert extract_answer("What happens if you factor out the 2 first?") is None
    assert extract_answer("") is None


def test_multiple_boxes_take_the_last():
    assert extract_answer(r"first \boxed{1} then, correcting, \boxed{2}") == "2"


# --- outcomes ----------------------------------------------------------------------------


def test_unverified_is_not_the_same_as_wrong(verifier):
    """Collapsing "we could not check" into "the student is wrong" is how a marking report
    quietly becomes fiction."""
    outcome = verifier.check_reply("Have you tried completing the square?", "4")
    assert outcome.checked is False and outcome.verified is False
    assert "no final answer" in outcome.detail


def test_a_dead_sandbox_reports_unchecked_not_wrong():
    class DeadPool:
        def submit(self, *_a, **_k):
            from orchestrator.tools.sandbox import SandboxResult

            return SandboxResult(False, error="worker died", killed=True)

    outcome = AnswerVerifier(DeadPool()).check("2", "2")
    assert outcome.checked is False and outcome.verified is False


def test_tolerance_is_opt_in(verifier):
    assert verifier.check("0.333", "1/3").verified is False
    assert verifier.check("0.333", "1/3", tolerance=1e-2).verified is True


def test_simplify_round_trip(verifier):
    assert verifier.simplify("x + x") == "2*x"


# --- the §7.5 protocol -------------------------------------------------------------------


def test_correct_answer_passes_through_untouched(verifier):
    outcome, reply = verify_with_retry(verifier, r"So the answer is \boxed{4}", "4")
    assert outcome.verified and HONEST_FALLBACK not in reply


def test_one_retry_with_the_failure_injected(verifier):
    seen: list[str] = []

    def regenerate(hint: str) -> str:
        seen.append(hint)
        return r"Rechecking the sign: \boxed{4}"

    outcome, reply = verify_with_retry(verifier, r"\boxed{-4}", "4", regenerate=regenerate)
    assert outcome.verified and outcome.attempts == 2
    assert len(seen) == 1, "exactly one retry (§7.5), not a loop"
    assert "-4" in seen[0] and "4" in seen[0], "the retry must see what failed"


def test_second_failure_is_admitted_never_presented_as_verified(verifier):
    outcome, reply = verify_with_retry(
        verifier, r"\boxed{-4}", "4", regenerate=lambda _hint: r"Still \boxed{-4}"
    )
    assert not outcome.verified
    assert HONEST_FALLBACK in reply
    assert "check this one together" in reply  # C-7: judges are non-technical


def test_without_a_regenerator_it_falls_back_immediately(verifier):
    outcome, reply = verify_with_retry(verifier, r"\boxed{-4}", "4")
    assert not outcome.verified and HONEST_FALLBACK in reply
