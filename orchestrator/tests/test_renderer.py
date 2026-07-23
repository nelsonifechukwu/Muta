"""Renderer tests (TDD §7.5, scenario S5).

Two properties matter: model-emitted code cannot reach outside the plot (imports, builtins,
dunders), and a failure ends in words rather than a broken image — a judge who sees a red X
concludes the system is broken.
"""

from __future__ import annotations

import pytest

from orchestrator.tools.renderer import DiagramRenderer
from orchestrator.tools.sandbox import RENDERER_LIMITS, WorkerPool

matplotlib = pytest.importorskip("matplotlib", reason="renderer needs matplotlib")


@pytest.fixture(scope="module")
def renderer():
    pool = WorkerPool(1, RENDERER_LIMITS).start()
    yield DiagramRenderer(pool)
    pool.close()


def test_renders_a_plot_to_svg(renderer):
    outcome = renderer.render("ax.plot([0, 1, 2], [0, 1, 4])\nax.set_title('y = x^2')")
    assert outcome.ok
    assert outcome.svg.lstrip().startswith("<?xml") and "</svg>" in outcome.svg
    assert outcome.bytes < 512 * 1024  # the §7.5 cap


def test_numpy_is_available_because_diagrams_need_it(renderer):
    outcome = renderer.render("x = np.linspace(0, 3, 50)\nax.plot(x, x**2)")
    assert outcome.ok


@pytest.mark.parametrize(
    "code,reason",
    [
        ("import os\nos.listdir('/')", "import"),
        ("from subprocess import run", "import"),
        ("open('/etc/passwd').read()", "open"),
        ("eval('1+1')", "eval"),
        ("ax.__class__.__mro__", "dunder"),
        ("__import__('os')", "__import__"),
    ],
)
def test_escapes_are_refused_before_execution(renderer, code, reason):
    """Static rejection, not a runtime error: the snippet never runs, so a side effect in
    line 1 cannot happen while line 2 is being rejected."""
    outcome = renderer.render(code)
    assert not outcome.ok, reason
    assert "not allowed" in outcome.error


def test_a_syntax_error_is_reported_not_raised(renderer):
    outcome = renderer.render("ax.plot([0, 1]")
    assert not outcome.ok and "syntax error" in outcome.error


def test_runtime_failure_is_reported_with_the_exception(renderer):
    outcome = renderer.render("ax.plot(undefined_variable)")
    assert not outcome.ok and "NameError" in outcome.error


def test_repair_round_gets_the_error_text(renderer):
    seen: list[str] = []

    def repair(code: str, error: str) -> str:
        seen.append(error)
        return "ax.plot([0, 1], [0, 1])"

    outcome = renderer.render_with_repair("ax.plot(oops)", repair=repair)
    assert outcome.ok and outcome.attempts == 2
    assert "NameError" in seen[0], "the model has to see what broke to fix it"


def test_a_second_failure_degrades_to_words_not_a_broken_image(renderer):
    outcome = renderer.render_with_repair(
        "ax.plot(oops)",
        repair=lambda _c, _e: "ax.plot(still_oops)",
        describe=lambda: "A straight line rising from the origin at 45 degrees.",
    )
    assert not outcome.ok
    assert outcome.svg == ""
    assert "straight line" in outcome.fallback_text


def test_raw_svg_passthrough_strips_scripts(renderer):
    outcome = renderer.render(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>fetch("http://x")</script>'
        '<circle r="5"/></svg>',
        kind="svg",
    )
    assert outcome.ok
    assert "<script" not in outcome.svg and "<circle" in outcome.svg
