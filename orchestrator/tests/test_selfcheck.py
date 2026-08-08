"""Conservative symbolic self-check: catches explicit contradictions, never flags prose."""

from __future__ import annotations

from orchestrator.gateway.selfcheck import _is_checkable_equation, self_check
from orchestrator.tools.sandbox import ToolPools
from orchestrator.tools.verifier import AnswerVerifier


def test_recognises_only_bare_identities():
    assert _is_checkable_equation("12 * 7 = 84") == ("12 * 7", "84")
    assert _is_checkable_equation("- x^2 - 1 = (x-1)(x+1)") == ("x^2 - 1", "(x-1)(x+1)")
    # Prose, comparisons, chains, and questions are NOT checkable equations.
    assert _is_checkable_equation("Therefore the answer is 42") is None
    assert _is_checkable_equation("the area A = length times width") is None
    assert _is_checkable_equation("x == 4") is None
    assert _is_checkable_equation("a = b = c") is None
    assert _is_checkable_equation("What is 2 + 2?") is None
    assert _is_checkable_equation("This is a very long line of ordinary prose with an = sign in it somewhere") is None


def _verifier() -> AnswerVerifier:
    return AnswerVerifier(ToolPools().verifier)


def test_no_equations_means_not_checked():
    v = _verifier()
    r = self_check(v, "What do we know about the triangle? What is the base?")
    assert r.checked is False
    assert r.verified is True  # nothing to contradict
    assert r.note == ""


def test_correct_algebra_passes():
    v = _verifier()
    reply = "Let's expand.\n(x-1)(x+1) = x^2 - 1\nSo the factored form checks out."
    r = self_check(v, reply)
    assert r.checked is True
    assert r.verified is True
    assert r.note == ""


def test_a_wrong_step_is_caught_and_explained():
    v = _verifier()
    reply = "Adding them up:\n2 + 2 = 5\nso the total is 5."
    r = self_check(v, reply)
    assert r.checked is True
    assert r.verified is False
    assert r.failed == [("2 + 2", "5")]
    assert "doesn't look right" in r.note
