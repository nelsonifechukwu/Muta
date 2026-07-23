"""Sandbox worker — runs under `python -I -S` with rlimits already applied (TDD §7.5).

Protocol: one JSON request per stdin line, one JSON response per stdout line.

    {"op": "verify", "candidate": "2*x", "expected": "x+x"}
    -> {"ok": true, "value": {"equivalent": true, ...}}

Never imports SymPy or Matplotlib at module level: a warm worker should pay for the library
it is actually asked for, and the verifier pool has no business holding Matplotlib's ~80 MiB.

This file is executed, not imported, by `sandbox.py`.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys

MAX_SVG_BYTES = 512 * 1024  # TDD §7.5

# --- network denial (portable half; `unshare -rn` is the real one where available) --------


def _deny_network() -> None:
    import socket

    class _Denied(OSError):
        pass

    def _refuse(*_a, **_k):
        raise _Denied("network access is disabled inside the tool sandbox (TDD §7.5)")

    socket.socket = _refuse  # type: ignore[assignment]
    socket.create_connection = _refuse  # type: ignore[assignment]
    socket.getaddrinfo = _refuse  # type: ignore[assignment]


# --- LaTeX-ish → SymPy-ish ---------------------------------------------------------------

_LATEX_SUBS: list[tuple[str, str]] = [
    (r"\\left|\\right", ""),
    (r"\\!|\\,|\\;|\\quad|\\qquad", " "),
    (r"\\dfrac|\\tfrac|\\frac", r"\\frac"),
    (r"\\cdot|\\times", "*"),
    (r"\\div", "/"),
    (r"\\pi\b", "pi"),
    (r"\\infty", "oo"),
    (r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)"),
    (r"\\(sin|cos|tan|log|ln|exp|arcsin|arccos|arctan|sinh|cosh|tanh)\b", r"\1"),
    (r"\\le\b", "<="),
    (r"\\ge\b", ">="),
    (r"\\neq\b", "!="),
    (r"\\text\s*\{([^{}]*)\}", r"\1"),
    (r"\\degree|°", " degree"),
    (r"[{}]", " "),
    (r"\\[a-zA-Z]+", " "),  # anything left over: drop the command, keep the operands
]

#: Units are stripped when BOTH sides carry the same one — "12 cm" and "12 cm" are equal,
#: while "12 cm" and "12 m" must not be, so this never strips unilaterally.
_UNIT = re.compile(
    r"\s*(cm|mm|km|m|kg|g|mg|s|ms|min|hr?|h|N|J|W|V|A|K|mol|L|ml|cm\^?2|cm\^?3|m\^?2|m\^?3"
    r"|degrees?|degree|rad)\s*$",
    re.IGNORECASE,
)


def _expand_frac(text: str) -> str:
    """`\\frac{a}{b}` → `((a)/(b))`, innermost first so nesting works."""
    pattern = re.compile(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    for _ in range(8):  # bounded: a nesting depth of 8 in a tutoring answer is already odd
        new = pattern.sub(r"((\1)/(\2))", text)
        if new == text:
            break
        text = new
    return text


#: `sin^2(x)` means `(sin x)²`, not `sin` raised to a power then applied — the one piece of
#: mathematical notation where the exponent binds to the *result*. Rewritten before anything
#: else touches `^`, because afterwards the information is gone.
_TRIG_POWER = re.compile(r"\\?(sin|cos|tan|sec|csc|cot|sinh|cosh|tanh)\s*\^\s*(\d+)\s*\(([^()]+)\)")

#: `x^{2n}` → `x**(2n)`. Braces are dropped wholesale later, so grouping has to become
#: parentheses first or `e^{2x}` silently reads as `e**2 * x`.
_SUPERSCRIPT_GROUP = re.compile(r"\^\s*\{([^{}]*)\}")

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

#: `|x|` → `Abs(x)`. SymPy's parser has no notion of the vertical-bar convention, and a
#: student writing `|-7|` is not writing a syntax error.
_ABS = re.compile(r"\|([^|]+)\|")

_BOXED_ANY = re.compile(r"\\boxed\s*\{(.*)\}", re.DOTALL)


def normalise(text: str) -> str:
    """Turn a model's answer string into something SymPy's parser accepts."""
    out = str(text).strip()
    # A boxed value REPLACES the string rather than being substituted into it: "The answer
    # is \boxed{-3}" must normalise to "-3", not to "The answer is -3", which parses as
    # nothing and quietly degrades the whole check to a string comparison.
    boxed = _BOXED_ANY.search(out)
    if boxed:
        out = boxed.group(1)
    out = out.replace("$", "").strip()
    out = _ABS.sub(r"Abs(\1)", out)
    # Before _expand_frac: \dfrac/\tfrac are \frac with different display sizes, and an
    # unexpanded \dfrac loses its braces later and silently becomes "3 6".
    out = re.sub(r"\\[dt]frac\b", r"\\frac", out)
    out = _TRIG_POWER.sub(r"(\1(\3))**\2", out)
    out = _SUPERSCRIPT_GROUP.sub(r"**(\1)", out)
    out = _PERCENT.sub(r"((\1)/100)", out)
    out = _expand_frac(out)
    for pattern, repl in _LATEX_SUBS:
        out = re.sub(pattern, repl, out)
    out = out.replace("^", "**")
    out = re.sub(r"\s+", " ", out).strip()
    return out.rstrip(".")


def _split_unit(text: str) -> tuple[str, str]:
    match = _UNIT.search(text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), match.group(1).lower()


# --- verification -------------------------------------------------------------------------


def _parse(expr_text: str):
    from sympy.parsing.sympy_parser import (
        convert_xor,
        implicit_multiplication_application,
        parse_expr,
        standard_transformations,
    )

    transformations = standard_transformations + (implicit_multiplication_application, convert_xor)
    return parse_expr(expr_text, transformations=transformations, evaluate=True)


def _as_relation(text: str):
    """`x = 2` → (lhs - rhs). Returns None when the text is not an equation."""
    if text.count("=") != 1 or any(op in text for op in ("<=", ">=", "!=", "==")):
        return None
    lhs, rhs = text.split("=")
    return _parse(lhs) - _parse(rhs)


def _numeric_close(a, b, tolerance: float) -> bool | None:
    """Relative comparison for the rounding a marking scheme actually allows.

    Returns None when either side is not a number, so the caller falls through to symbolic
    comparison. Exists because "1/3" and "0.333" are not equal and a WAEC scheme that asked
    for 3 significant figures says they are — that judgement belongs to the caller (which
    passes a tolerance), never to the default.
    """
    if tolerance <= 0:
        return None
    try:
        fa, fb = float(a.evalf()), float(b.evalf())
    except (TypeError, ValueError, AttributeError):
        return None
    scale = max(abs(fa), abs(fb), 1e-12)
    return abs(fa - fb) / scale <= tolerance


def _equivalent(a, b, tolerance: float = 0.0) -> bool:
    """`equals` first (numeric sampling — decides many cases `simplify` chokes on), then a
    symbolic fallback. Both are wrapped: SymPy raises a wide variety of exceptions on
    adversarial input, and a verifier that crashes reads as "unverified", which is the safe
    direction but not one we want to reach by accident."""
    import sympy

    close = _numeric_close(a, b, tolerance)
    if close is not None:
        return close
    try:
        verdict = a.equals(b)
        if verdict is True:
            return True
        if verdict is False:
            return False
    except Exception:  # noqa: BLE001
        pass
    try:
        return bool(sympy.simplify(a - b) == 0)
    except Exception:  # noqa: BLE001
        return False


def _multi_answer(text: str) -> list[str] | None:
    """`x = 2, x = 3` / `2 or 3` → a set of answers. Order must not matter."""
    parts = re.split(r"\s*(?:,|;|\bor\b)\s*", text)
    parts = [p for p in (p.strip() for p in parts) if p]
    return parts if len(parts) > 1 else None


def op_verify(req: dict) -> dict:
    import sympy

    tolerance = float(req.get("tolerance", 0.0) or 0.0)
    raw_candidate, raw_expected = str(req.get("candidate", "")), str(req.get("expected", ""))
    candidate, expected = normalise(raw_candidate), normalise(raw_expected)
    cand_body, cand_unit = _split_unit(candidate)
    exp_body, exp_unit = _split_unit(expected)

    detail = ""
    if cand_unit and exp_unit and cand_unit != exp_unit:
        return {
            "equivalent": False,
            "normalized_candidate": candidate,
            "normalized_expected": expected,
            "detail": f"unit mismatch: {cand_unit} vs {exp_unit}",
        }
    if cand_unit == exp_unit:
        candidate, expected = cand_body or candidate, exp_body or expected

    equivalent = False
    try:
        cand_set, exp_set = _multi_answer(candidate), _multi_answer(expected)
        if cand_set and exp_set:
            if len(cand_set) != len(exp_set):
                equivalent = False
                detail = "different number of answers"
            else:
                remaining = list(exp_set)
                equivalent = True
                for item in cand_set:  # set comparison: order of roots is not information
                    match = next((r for r in remaining if _compare_single(item, r, tolerance)), None)
                    if match is None:
                        equivalent, detail = False, f"no match for {item!r}"
                        break
                    remaining.remove(match)
        else:
            equivalent = _compare_single(candidate, expected, tolerance)
    except (SyntaxError, TypeError, ValueError, AttributeError, sympy.SympifyError) as e:
        # Unparseable on either side: fall back to a normalised string comparison rather
        # than claiming a verification we did not perform.
        equivalent = candidate.replace(" ", "").lower() == expected.replace(" ", "").lower()
        detail = f"symbolic comparison unavailable ({type(e).__name__}); compared as text"

    return {
        "equivalent": bool(equivalent),
        "normalized_candidate": candidate,
        "normalized_expected": expected,
        "detail": detail,
    }


def _compare_single(candidate: str, expected: str, tolerance: float = 0.0) -> bool:
    rel_c, rel_e = _as_relation(candidate), _as_relation(expected)
    if rel_c is not None and rel_e is not None:
        import sympy

        if _equivalent(rel_c, rel_e, tolerance):
            return True
        # `2x = 4` and `x = 2` are the same equation scaled; a constant ratio proves it.
        try:
            ratio = sympy.simplify(rel_c / rel_e)
            return bool(ratio.is_number and ratio != 0)
        except Exception:  # noqa: BLE001
            return False
    if (rel_c is None) != (rel_e is None):
        # One is an equation, the other a bare value: compare the value against the
        # equation's solution set, which is what "x = 2" vs "2" means to a student.
        import sympy

        relation, value_text = (rel_c, expected) if rel_c is not None else (rel_e, candidate)
        try:
            symbols = sorted(relation.free_symbols, key=str)
            if len(symbols) == 1:
                solutions = sympy.solve(relation, symbols[0])
                value = _parse(value_text)
                return any(_equivalent(sol, value, tolerance) for sol in solutions)
        except Exception:  # noqa: BLE001
            return False
        return False
    return _equivalent(_parse(candidate), _parse(expected), tolerance)


def op_simplify(req: dict) -> dict:
    import sympy

    expr = _parse(normalise(str(req.get("expression", ""))))
    return {"simplified": str(sympy.simplify(expr)), "latex": sympy.latex(sympy.simplify(expr))}


# --- rendering ----------------------------------------------------------------------------

#: Names the renderer snippet may use. The model emits plotting code under a grammar; this
#: is the difference between "draw a triangle" and "read /etc/passwd" when a retrieved PDF
#: has been prompt-injected (§13).
_RENDER_ALLOWED_IMPORTS = {"numpy", "math", "matplotlib", "matplotlib.pyplot"}
_RENDER_FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars", "getattr", "setattr", "delattr"}


def check_code(code: str) -> str:
    """Static check before execution. Returns "" when the snippet is acceptable."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return f"syntax error: {e.msg} (line {e.lineno})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in {m.split(".")[0] for m in _RENDER_ALLOWED_IMPORTS}:
                    return f"import of {alias.name!r} is not allowed"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in {m.split(".")[0] for m in _RENDER_ALLOWED_IMPORTS}:
                return f"import from {node.module!r} is not allowed"
        elif isinstance(node, ast.Name) and node.id in _RENDER_FORBIDDEN_NAMES:
            return f"use of {node.id!r} is not allowed"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"attribute {node.attr!r} is not allowed"
    return ""


def op_render(req: dict) -> dict:
    kind = str(req.get("kind", "matplotlib")).lower()
    code = str(req.get("code", ""))
    if kind == "svg":
        svg = re.sub(r"<script.*?</script>", "", code, flags=re.DOTALL | re.IGNORECASE)
        if len(svg.encode()) > MAX_SVG_BYTES:
            raise ValueError(f"SVG exceeds {MAX_SVG_BYTES} bytes")
        return {"svg": svg, "kind": "svg"}
    if kind != "matplotlib":
        raise ValueError(f"unknown render kind {kind!r} (matplotlib|svg)")

    problem = check_code(code)
    if problem:
        raise ValueError(problem)

    import io

    import matplotlib

    matplotlib.use("Agg")  # never a display; the target box may not even have one
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    namespace = {"plt": plt, "np": np, "numpy": np, "fig": fig, "ax": ax, "__builtins__": _safe_builtins()}
    try:
        exec(compile(code, "<render>", "exec"), namespace)  # noqa: S102 — the jail is the point
        buf = io.StringIO()
        fig.savefig(buf, format="svg", bbox_inches="tight")
        svg = buf.getvalue()
    finally:
        plt.close(fig)
    if len(svg.encode()) > MAX_SVG_BYTES:
        raise ValueError(f"SVG exceeds {MAX_SVG_BYTES} bytes — reduce the plot's complexity")
    return {"svg": svg, "kind": "matplotlib"}


def _safe_builtins() -> dict:
    import builtins

    allowed = {
        "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "format",
        "int", "len", "list", "map", "max", "min", "pow", "print", "range", "reversed", "round",
        "set", "slice", "sorted", "str", "sum", "tuple", "zip", "True", "False", "None",
        "ValueError", "TypeError", "ZeroDivisionError", "Exception",
    }
    return {name: getattr(builtins, name) for name in allowed if hasattr(builtins, name)}


# --- test hooks (never reachable in production: the env var is not in sandbox_env) --------


def op_test(req: dict) -> dict:
    if os.environ.get("MUTA_SANDBOX_ALLOW_TEST_OPS") != "1":
        raise ValueError("test ops are disabled")
    mode = req.get("mode")
    if mode == "cpu":
        x = 0
        while True:
            x = (x + 1) % 1_000_003
    if mode == "memory":
        blocks = []
        while True:
            blocks.append(bytearray(16 * 1024 * 1024))
    if mode == "sleep":
        import time

        time.sleep(float(req.get("seconds", 30)))
        return {"slept": True}
    if mode == "network":
        import socket

        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return {"socket": "created"}
    raise ValueError(f"unknown test mode {mode!r}")


HANDLERS = {
    "ping": lambda _req: {"pong": True},
    "verify": op_verify,
    "simplify": op_simplify,
    "render": op_render,
    "_test": op_test,
}


def handle(request: dict) -> dict:
    op = request.get("op", "")
    handler = HANDLERS.get(op)
    if handler is None:
        return {"ok": False, "error": f"unknown op {op!r}"}
    try:
        return {"ok": True, "value": handler(request)}
    except Exception as e:  # noqa: BLE001 — a tool failure is data, not a crash
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    _deny_network()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            response = {"ok": False, "error": f"bad request: {e}"}
        else:
            response = handle(request)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
