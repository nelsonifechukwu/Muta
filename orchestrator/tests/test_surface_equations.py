"""Adversarial tests for the data-only mathematical-surface grammar."""

from __future__ import annotations

import math

import pytest

from orchestrator.gateway.surface_equations import (
    MAX_AST_DEPTH,
    SurfaceExpressionError,
    evaluate_surface_expression,
    extract_surface_expression,
    format_surface_expression,
    normalize_surface_expression,
    parse_surface_expression,
    phase_animation_expression,
)

EXACT_REQUEST = (
    'I want a diagram of this equation, "'
    r"z=4e^{-\frac{1}{4}y^{2}}\sin \left(2x\right)"
    '"'
)


def test_exact_latex_surface_is_normalized_without_losing_precedence() -> None:
    source = extract_surface_expression(EXACT_REQUEST)
    assert source == r"4e^{-\frac{1}{4}y^{2}}\sin \left(2x\right)"
    assert normalize_surface_expression(source) == "4e^(-((1)/(4))y^(2))sin(2x)"
    tree = parse_surface_expression(source)
    assert format_surface_expression(tree) == "4·e^(−¼·y²)·sin(2·x)"

    for y in (-4.0, -1.5, 0.0, 2.75, 4.0):
        assert evaluate_surface_expression(tree, x=0, y=y) == pytest.approx(0)
    assert evaluate_surface_expression(tree, x=math.pi / 4, y=0) == pytest.approx(4)
    assert evaluate_surface_expression(tree, x=-math.pi / 4, y=0) == pytest.approx(-4)

    at_peak = evaluate_surface_expression(tree, x=math.pi / 4, y=0)
    at_two = evaluate_surface_expression(tree, x=math.pi / 4, y=2)
    at_four = evaluate_surface_expression(tree, x=math.pi / 4, y=4)
    assert abs(at_peak) > abs(at_two) > abs(at_four) > 0
    # Swapping the axes would make the y = 0 sample vanish instead of reaching the crest.
    assert evaluate_surface_expression(tree, x=math.pi / 4, y=0) != pytest.approx(
        evaluate_surface_expression(tree, x=0, y=math.pi / 4)
    )


def test_exact_unicode_surface_with_a_presentation_suffix_stays_deterministic() -> None:
    source = extract_surface_expression("Plot z=4e^{−y²/4}sin(2x) as a 3D surface.")
    assert source == "4e^{−y²/4}sin(2x)"
    tree = parse_surface_expression(source)
    assert format_surface_expression(tree) == "4·e^(−y²/4)·sin(2·x)"
    assert evaluate_surface_expression(tree, x=math.pi / 4, y=0) == pytest.approx(4)


@pytest.mark.parametrize(
    "prompt_text",
    [
        r"Plot $z=4e^{-\frac{1}{4}y^{2}}\sin(2x)$.",
        r"Plot \(z=4e^{-\frac{1}{4}y^{2}}\sin(2x)\).",
        r"Plot \[z=4e^{-\frac{1}{4}y^{2}}\sin(2x)\].",
        r"Plot z=$4e^{-\frac{1}{4}y^{2}}\sin(2x)$.",
    ],
)
def test_balanced_math_delimiters_are_removed_from_the_extracted_rhs(prompt_text: str) -> None:
    source = extract_surface_expression(prompt_text)
    tree = parse_surface_expression(source)
    assert evaluate_surface_expression(tree, x=math.pi / 4, y=0) == pytest.approx(4)


def test_unbraced_single_digit_tex_fraction_is_safe_and_unambiguous() -> None:
    tree = parse_surface_expression(r"4e^{-\frac14 y^2}\sin(2x)")
    assert evaluate_surface_expression(tree, x=math.pi / 4, y=0) == pytest.approx(4)
    assert evaluate_surface_expression(tree, x=math.pi / 4, y=2) == pytest.approx(4 / math.e)
    with pytest.raises(SurfaceExpressionError):
        parse_surface_expression(r"\frac xy")


def test_power_binds_more_tightly_than_unary_minus() -> None:
    negative_square = parse_surface_expression("-y^2")
    parenthesized = parse_surface_expression("(-y)^2")
    assert evaluate_surface_expression(negative_square, x=0, y=3) == -9
    assert evaluate_surface_expression(parenthesized, x=0, y=3) == 9


@pytest.mark.parametrize(
    ("source", "x", "y", "expected"),
    [
        ("sin(x)+cos(y)", 0, 0, 1),
        ("exp(-(x^2+y^2))", 1, 0, math.exp(-1)),
        (r"\sqrt{x^2+y^2}", 3, 4, 5),
        ("2pi+3x-abs(y)", 2, -1, 2 * math.pi + 5),
        ("tanh(x*y)", 0.5, 2, math.tanh(1)),
    ],
)
def test_general_bounded_surface_family(source: str, x: float, y: float, expected: float) -> None:
    tree = parse_surface_expression(source)
    assert evaluate_surface_expression(tree, x=x, y=y) == pytest.approx(expected)


def test_animation_tree_is_typed_and_matches_the_base_at_time_zero() -> None:
    base = parse_surface_expression(r"4e^{-\frac{1}{4}y^{2}}\sin(2x)")
    animated = phase_animation_expression(base)
    assert animated is not None
    for x, y in ((0, 0), (math.pi / 4, 0), (-math.pi / 4, 2)):
        assert evaluate_surface_expression(animated, x=x, y=y, t=0) == pytest.approx(
            evaluate_surface_expression(base, x=x, y=y)
        )
    assert evaluate_surface_expression(
        animated, x=math.pi / 4, y=0, t=math.pi / 2
    ) == pytest.approx(0)


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os')",
        "x.constructor",
        "x=1",
        "sin(x,y)",
        "unknown(x)",
        r"\href{https://example.com}{x}",
        "1/0",
    ],
)
def test_executable_or_unsupported_syntax_never_evaluates(source: str) -> None:
    with pytest.raises(SurfaceExpressionError):
        tree = parse_surface_expression(source)
        evaluate_surface_expression(tree, x=1, y=1)


def test_expression_depth_and_request_length_are_bounded() -> None:
    nested = "(" * (MAX_AST_DEPTH + 2) + "x" + ")" * (MAX_AST_DEPTH + 2)
    with pytest.raises(SurfaceExpressionError):
        parse_surface_expression(nested)
    assert extract_surface_expression("diagram z=" + "x" * 401) is None
