"""Answer verification — the cheapest hallucination fix available (TDD §7.5).

Protocol, in order:

1. extract the final answer from the model's prose (`\\boxed{}` and the conventions students
   and models actually use),
2. check equivalence in the sandbox (SymPy, timeout-bounded),
3. on mismatch, ONE retry with the failure injected as a hint at temperature 0 — the retry
   changes the *input*, never the dice, so a pass is information rather than luck,
4. on a second failure, say so: `"let's check this one together"`.

Step 4 is the load-bearing one. A tutor that presents an unverified answer as verified is
worse than one that admits doubt, and the judges are explicitly non-technical (C-7): the
failure mode has to be a working tutor, never an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from orchestrator.tools.sandbox import VERIFIER_LIMITS, SandboxResult, WorkerPool, run_once

#: Wording for an honest miss (§7.5). Phrased as an invitation, not an apology — the student
#: should end up working the problem with the tutor, not doubting the whole session.
HONEST_FALLBACK = (
    "I'm not certain about that final value — let's check this one together. "
    "Walk me through your working and I'll follow along step by step."
)

_BOXED = re.compile(r"\\boxed\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
_ANSWER_LINE = re.compile(
    r"(?:final\s+answer|the\s+answer\s+is|answer\s*[:=]|therefore|hence|so)\s*[:,]?\s*(.+)",
    re.IGNORECASE,
)
_TRAILING_JUNK = re.compile(r"^[\s*_`$]+|[\s*_`$.,;]+$")

#: Two consecutive words = prose. The distinction matters: `y = 3x + 2` is an answer that
#: happens to contain `=`, while `Therefore, y = 3x + 2` is a sentence containing an answer.
#: Splitting the former on `=` returns `3x + 2` and marks a correct student wrong.
_PROSE = re.compile(r"[A-Za-z]{3,}\s+[A-Za-z]{2,}")


def looks_like_prose(text: str) -> bool:
    return bool(_PROSE.search(text))


def extract_answer(text: str) -> str | None:
    """Pull the final answer out of a worked solution.

    Ordered by how much the convention *commits*: `\\boxed{}` is unambiguous, an explicit
    "the answer is" nearly so, a trailing equation only when the surrounding text is prose.
    Returning None is a real outcome — a Socratic turn deliberately has no final answer, and
    inventing one from the last equation on screen would send the verifier after the
    student's own working instead of the tutor's claim.
    """
    if not text or not text.strip():
        return None

    boxed = _BOXED.findall(text)
    if boxed:
        return _clean(boxed[-1])

    for line in reversed(text.strip().splitlines()):
        candidate = _peel_answer_prefix(line)
        if candidate and not candidate.endswith("?"):
            return candidate

    # Last resort, and only inside prose: a trailing `... = value`.
    for line in reversed(text.strip().splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if "=" in stripped and looks_like_prose(stripped):
            return _clean(stripped.rsplit("=", 1)[1]) or None
        return None
    return None


def _peel_answer_prefix(line: str) -> str | None:
    """Strip stacked lead-ins: "Therefore, the answer is 42" sheds both, not just the first."""
    current = line
    found = False
    for _ in range(3):
        match = _ANSWER_LINE.search(current)
        if not match:
            break
        current, found = match.group(1), True
    return _clean(current) if found else None


def _clean(text: str) -> str:
    out = _TRAILING_JUNK.sub("", text.strip())
    out = re.split(r"\s{2,}|\.\s|\bbecause\b|\bsince\b", out, maxsplit=1)[0]
    return out.strip()


@dataclass
class VerifyOutcome:
    """`checked=False` means we never got a verdict (no answer found, sandbox died). It is
    NOT the same as `verified=False`, and collapsing the two is how "unverified" silently
    becomes "wrong" in a marking report."""

    verified: bool
    checked: bool
    candidate: str | None = None
    expected: str | None = None
    normalized_candidate: str = ""
    normalized_expected: str = ""
    detail: str = ""
    attempts: int = 0
    seconds: float = 0.0

    @property
    def needs_retry(self) -> bool:
        return self.checked and not self.verified


class AnswerVerifier:
    """SymPy equivalence behind the sandbox. Uses a warm pool when given one (§7.5)."""

    def __init__(self, pool: WorkerPool | None = None, *, tolerance: float = 0.0) -> None:
        self.pool = pool
        self.tolerance = tolerance

    def _run(self, payload: dict[str, Any]) -> SandboxResult:
        if self.pool is not None:
            return self.pool.submit("verify", payload)
        return run_once("verify", payload, VERIFIER_LIMITS)

    def check(self, candidate: str, expected: str, *, tolerance: float | None = None) -> VerifyOutcome:
        result = self._run(
            {
                "candidate": candidate,
                "expected": expected,
                "tolerance": self.tolerance if tolerance is None else tolerance,
            }
        )
        if not result.ok:
            # A dead or timed-out sandbox must not read as "the student is wrong".
            return VerifyOutcome(
                verified=False,
                checked=False,
                candidate=candidate,
                expected=expected,
                detail=result.error or "verifier unavailable",
                attempts=1,
                seconds=result.seconds,
            )
        value = result.value or {}
        return VerifyOutcome(
            verified=bool(value.get("equivalent")),
            checked=True,
            candidate=candidate,
            expected=expected,
            normalized_candidate=value.get("normalized_candidate", ""),
            normalized_expected=value.get("normalized_expected", ""),
            detail=value.get("detail", ""),
            attempts=1,
            seconds=result.seconds,
        )

    def check_text(self, text: str, expected: str, **kw) -> VerifyOutcome:
        """Check a string that may be a bare answer *or* a sentence containing one.

        Extraction first, raw text second: `"Therefore the answer is 42."` and `"2x"` both
        have to work, and the caller (a tool call, a marking pass, a golden set) should not
        have to know which shape it holds.

        Prose with no extractable answer returns `checked=False`. Comparing a whole sentence
        as a string would return `verified=False`, which reads as "the student is wrong" when
        the truth is "there was no answer in there to check".
        """
        candidate = extract_answer(text)
        if candidate is None:
            if looks_like_prose(text):
                return VerifyOutcome(
                    verified=False,
                    checked=False,
                    candidate=None,
                    expected=expected,
                    detail="no final answer found in that text",
                )
            candidate = text
        return self.check(candidate, expected, **kw)

    def check_reply(self, reply: str, expected: str, **kw) -> VerifyOutcome:
        """Extract the answer from a reply, then check it."""
        candidate = extract_answer(reply)
        if candidate is None:
            return VerifyOutcome(
                verified=False,
                checked=False,
                expected=expected,
                detail="no final answer in the reply (Socratic turns often have none)",
            )
        return self.check(candidate, expected, **kw)

    def simplify(self, expression: str) -> str | None:
        payload = {"expression": expression}
        result = (
            self.pool.submit("simplify", payload)
            if self.pool is not None
            else run_once("simplify", payload, VERIFIER_LIMITS)
        )
        return (result.value or {}).get("simplified") if result.ok else None


def verify_with_retry(
    verifier: AnswerVerifier,
    reply: str,
    expected: str,
    *,
    regenerate: Callable[[str], str] | None = None,
) -> tuple[VerifyOutcome, str]:
    """The full §7.5 protocol. Returns (outcome, reply-to-send).

    `regenerate(hint)` re-runs the model at temperature 0 with the failure as context. Given
    None (or when it fails), the honest fallback is appended rather than the answer being
    presented as checked.
    """
    outcome = verifier.check_reply(reply, expected)
    if outcome.verified or not outcome.checked:
        return outcome, reply

    if regenerate is None:
        return outcome, f"{reply}\n\n{HONEST_FALLBACK}"

    hint = (
        f"Your final answer was {outcome.candidate!r}, which does not match the expected "
        f"result {expected!r}. Re-work the problem carefully, show the step where the "
        "discrepancy appears, and state the corrected final answer in \\boxed{}."
    )
    retried = regenerate(hint)
    second = verifier.check_reply(retried, expected)
    second.attempts = outcome.attempts + second.attempts
    if second.verified:
        return second, retried
    return second, f"{retried}\n\n{HONEST_FALLBACK}"
