"""Diagram rendering from model-emitted code (TDD §7.5, scenario S5).

The model writes Matplotlib code; the sandbox runs it; the gateway gets an SVG string. On a
failure the model gets ONE repair round with stderr as the tool result — that is usually
enough for a missing variable or a bad axis call — and after that the answer degrades to a
text description.

Never a broken image: a judge who sees a red X concludes the system is broken, while a judge
who reads "here's the shape in words" concludes it is honest. Same failure, different
verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from orchestrator.tools.sandbox import RENDERER_LIMITS, WorkerPool, run_once

MAX_SVG_BYTES = 512 * 1024


@dataclass
class RenderOutcome:
    ok: bool
    svg: str = ""
    error: str = ""
    attempts: int = 0
    seconds: float = 0.0
    fallback_text: str = ""

    @property
    def bytes(self) -> int:
        return len(self.svg.encode())


class DiagramRenderer:
    def __init__(self, pool: WorkerPool | None = None) -> None:
        self.pool = pool

    def _run(self, kind: str, code: str):
        payload = {"kind": kind, "code": code}
        if self.pool is not None:
            return self.pool.submit("render", payload, timeout=RENDERER_LIMITS.wall_seconds)
        return run_once("render", payload, RENDERER_LIMITS)

    def render(self, code: str, *, kind: str = "matplotlib") -> RenderOutcome:
        result = self._run(kind, code)
        if not result.ok:
            return RenderOutcome(False, error=result.error or "render failed", attempts=1, seconds=result.seconds)
        svg = (result.value or {}).get("svg", "")
        return RenderOutcome(bool(svg), svg=svg, attempts=1, seconds=result.seconds)

    def render_with_repair(
        self,
        code: str,
        *,
        kind: str = "matplotlib",
        repair: Callable[[str, str], str] | None = None,
        describe: Callable[[], str] | None = None,
    ) -> RenderOutcome:
        """Render, and on failure give the model one repair round with the error text."""
        first = self.render(code, kind=kind)
        if first.ok or repair is None:
            if not first.ok and describe is not None:
                first.fallback_text = describe()
            return first

        repaired_code = repair(code, first.error)
        second = self.render(repaired_code, kind=kind)
        second.attempts = first.attempts + second.attempts
        if not second.ok and describe is not None:
            second.fallback_text = describe()
        return second
