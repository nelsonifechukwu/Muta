"""Conservative symbolic self-check of a tutor reply (the "verified tool calls" thesis, in a
form that needs no ground truth).

A free-form tutoring reply has no known "expected answer" to check against — but when the
model writes an explicit standalone identity like `x^2 - 1 = (x-1)(x+1)` or `12 * 7 = 84`,
that claim is checkable on its own: the two sides must be symbolically equivalent. This finds
those lines and verifies each with the SymPy sandbox.

The bar for "checkable" is deliberately high, because the expensive failure is the opposite
one — flagging a *correct* step as wrong (the verifier's own docs, §7.5). So a line qualifies
only if it is a bare `expr = expr` with math on both sides and no prose, no functions with
side-effects, and short. Most replies contain zero such lines → `checked=False`, and the UI
shows nothing. Only a genuine arithmetic/algebra contradiction produces `verified=False`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from orchestrator.tools.verifier import AnswerVerifier, looks_like_prose

# A candidate line: strip markdown/LaTeX wrappers, then require exactly one '=' (not ==, <=,
# >=, !=) with a non-empty side each. We validate the sides separately below.
_EQ = re.compile(r"^\s*(.+?)\s*=\s*(.+?)\s*$")
_MATHY = re.compile(r"^[0-9A-Za-z_.\s+\-*/^()²³⁴√]+$")
_HAS_OP_OR_DIGIT = re.compile(r"[0-9+\-*/^]")


def _clean_line(line: str) -> str:
    s = line.strip()
    # Peel common markdown/LaTeX list/emphasis/inline-math decoration.
    s = s.strip("*-• \t")
    s = s.strip("$` ")
    return s.strip()


def _is_checkable_equation(line: str) -> tuple[str, str] | None:
    s = _clean_line(line)
    if len(s) > 80 or "==" in s or "<=" in s or ">=" in s or "!=" in s or "≈" in s:
        return None
    if looks_like_prose(s):  # two consecutive words → it's a sentence, not an identity
        return None
    m = _EQ.match(s)
    if not m:
        return None
    lhs, rhs = m.group(1).strip(), m.group(2).strip()
    if not lhs or not rhs:
        return None
    # Both sides must be plain math tokens with at least one operator/digit, and the line must
    # have exactly one '=' (guard against a=b=c chains and assignment-looking prose).
    if s.count("=") != 1:
        return None
    for side in (lhs, rhs):
        if not _MATHY.match(side) or not _HAS_OP_OR_DIGIT.search(side):
            return None
    return lhs, rhs


@dataclass
class SelfCheckResult:
    checked: bool = False
    verified: bool = True
    failed: list[tuple[str, str]] = field(default_factory=list)  # (lhs, rhs) that didn't hold

    @property
    def note(self) -> str:
        if not self.checked or self.verified:
            return ""
        first = self.failed[0]
        return (
            f"One step doesn't look right to me — I get a different value for "
            f"`{first[0]} = {first[1]}`. Let's re-work that line together."
        )


def scan_claims(reply: str, *, max_claims: int = 6) -> list[tuple[str, str]]:
    """Cheap, sandbox-free scan for checkable equations. The chat path calls this first and
    only constructs the (fork-backed) verifier when it returns something — so an ordinary
    prose reply pays nothing."""
    if not reply or not reply.strip():
        return []
    claims: list[tuple[str, str]] = []
    for line in reply.splitlines():
        eq = _is_checkable_equation(line)
        if eq is not None:
            claims.append(eq)
        if len(claims) >= max_claims:
            break
    return claims


def self_check(verifier: AnswerVerifier, reply: str, *, max_claims: int = 6) -> SelfCheckResult:
    """Verify the explicit standalone equations in a reply. Returns checked=False when there
    were none to check (the common case, including every Socratic turn)."""
    claims = scan_claims(reply, max_claims=max_claims)
    if not claims:
        return SelfCheckResult()

    result = SelfCheckResult(checked=True, verified=True)
    any_checked = False
    for lhs, rhs in claims:
        outcome = verifier.check(lhs, rhs)
        if not outcome.checked:
            continue  # sandbox couldn't decide — never counts as a failure
        any_checked = True
        if not outcome.verified:
            result.verified = False
            result.failed.append((lhs, rhs))
    result.checked = any_checked
    return result
