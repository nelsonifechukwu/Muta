"""Safe, bounded parser and evaluator for deterministic ``z = f(x, y)`` visuals.

The result is a tiny typed expression tree that can cross the existing visualization protocol.
It deliberately accepts less syntax than a CAS: no names outside the allow-list, no assignment,
attributes, collections, strings, or executable code.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

MAX_EXPRESSION_CHARS = 400
MAX_TOKENS = 192
MAX_AST_NODES = 128
MAX_AST_DEPTH = 24
MAX_ABS_RESULT = 1_000_000_000.0

_FUNCTIONS = {
    "abs": abs,
    "acos": math.acos,
    "asin": math.asin,
    "atan": math.atan,
    "cos": math.cos,
    "cosh": math.cosh,
    "exp": math.exp,
    "ln": math.log,
    "log": math.log,
    "sin": math.sin,
    "sinh": math.sinh,
    "sqrt": math.sqrt,
    "tan": math.tan,
    "tanh": math.tanh,
}
_VARIABLES = {"x", "y", "t"}
_CONSTANTS = {"e": math.e, "pi": math.pi}
_SURFACE_START = re.compile(r"\bz\s*=", re.IGNORECASE)
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_NAME = re.compile(r"[A-Za-z]+")


class SurfaceExpressionError(ValueError):
    """The expression is unsupported, unsafe, or outside the visualization bounds."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str


def extract_surface_expression(text: str) -> str | None:
    """Return the first explicit right-hand side of ``z = ...`` in a learner request."""
    value = str(text or "")
    match = _SURFACE_START.search(value)
    if not match:
        return None
    tail = value[match.end() :]
    tail = tail.split("\n\nFOLLOW-UP VISUAL REQUEST:", 1)[0]
    quote_positions = [position for quote in ('"', "'", "`") if (position := tail.find(quote)) >= 0]
    if quote_positions:
        tail = tail[: min(quote_positions)]
    tail = re.split(r"\n{2,}", tail, maxsplit=1)[0]
    tail = tail.strip().rstrip(";,.").strip()
    # The opening math delimiter commonly sits before ``z =`` and therefore outside the
    # extracted right-hand side. Remove a closing delimiter only when its matching opener is
    # present either immediately before ``z`` or at the start of the right-hand side. This is
    # deliberately balanced: an arbitrary trailing dollar/backslash is never discarded.
    prefix = value[: match.start()].rstrip()
    for opener, closer in ((r"\[", r"\]"), (r"\(", r"\)"), ("$$", "$$"), ("$", "$")):
        if (
            tail.startswith(opener)
            and tail.endswith(closer)
            and len(tail) > len(opener) + len(closer)
        ):
            tail = tail[len(opener) : -len(closer)].strip()
            break
        if prefix.endswith(opener) and tail.endswith(closer):
            tail = tail[: -len(closer)].strip()
            break
    if not tail or len(tail) > MAX_EXPRESSION_CHARS:
        return None
    return tail


def _group(text: str, start: int) -> tuple[str, int]:
    if start >= len(text) or text[start] != "{":
        raise SurfaceExpressionError("LaTeX command needs a braced argument")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
        if depth > MAX_AST_DEPTH:
            raise SurfaceExpressionError("expression is nested too deeply")
    raise SurfaceExpressionError("unclosed LaTeX group")


def _expand_fractions(text: str) -> str:
    def argument(start: int) -> tuple[str, int]:
        while start < len(text) and text[start].isspace():
            start += 1
        if start < len(text) and text[start] == "{":
            return _group(text, start)
        # TeX permits a single token without braces (for example ``\frac14``). Accept only one
        # numeric digit here: it is unambiguous, bounded, and covers the common fraction shorthand
        # without widening the grammar to arbitrary commands or names.
        if start < len(text) and text[start].isdigit():
            return text[start], start + 1
        raise SurfaceExpressionError("LaTeX fraction needs braced arguments or single digits")

    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text.startswith(r"\frac", cursor):
            numerator, after_numerator = argument(cursor + len(r"\frac"))
            denominator, after_denominator = argument(after_numerator)
            output.append(f"(({_expand_fractions(numerator)})/({_expand_fractions(denominator)}))")
            cursor = after_denominator
            continue
        output.append(text[cursor])
        cursor += 1
    return "".join(output)


def normalize_surface_expression(expression: str) -> str:
    """Convert a conservative LaTeX/plain-text subset to the parser's ordinary notation."""
    value = str(expression or "").strip()
    if not value or len(value) > MAX_EXPRESSION_CHARS:
        raise SurfaceExpressionError("expression is empty or too long")
    value = value.replace("−", "-").replace("–", "-").replace("×", "*").replace("·", "*")
    value = value.replace("²", "^2").replace("³", "^3").replace("π", "pi")
    value = re.sub(r"\\(?:left|right)", "", value)
    value = re.sub(r"\\(?:,|!|;|:|quad|qquad)", " ", value)
    value = re.sub(r"\\(?:cdot|times)", "*", value)
    value = re.sub(r"\\mathrm\s*\{\s*e\s*\}", "e", value)
    value = re.sub(r"\\operatorname\s*\{\s*(exp|ln|log)\s*\}", r" \1", value)
    value = _expand_fractions(value)
    for name in sorted(_FUNCTIONS, key=len, reverse=True):
        value = re.sub(rf"\\{name}\b", f" {name}", value)
    value = re.sub(r"\\sqrt\s*\{", " sqrt{", value)
    if "\\" in value:
        raise SurfaceExpressionError("unsupported LaTeX command")
    value = re.sub(r"\^\s*\{", "^(", value)
    value = value.replace("{", "(").replace("}", ")")
    value = re.sub(r"\s+", "", value)
    if not value or len(value) > MAX_EXPRESSION_CHARS:
        raise SurfaceExpressionError("normalized expression is empty or too long")
    return value


def _raw_tokens(expression: str) -> list[_Token]:
    tokens: list[_Token] = []
    cursor = 0
    while cursor < len(expression):
        number = _NUMBER.match(expression, cursor)
        if number:
            tokens.append(_Token("number", number.group(0)))
            cursor = number.end()
            continue
        name = _NAME.match(expression, cursor)
        if name:
            tokens.append(_Token("name", name.group(0).lower()))
            cursor = name.end()
            continue
        character = expression[cursor]
        if character in "+-*/^()":
            tokens.append(_Token(character, character))
            cursor += 1
            continue
        raise SurfaceExpressionError(f"unsupported character at position {cursor}")
    if len(tokens) > MAX_TOKENS:
        raise SurfaceExpressionError("expression has too many tokens")
    return tokens


def _tokenize(expression: str) -> list[_Token]:
    raw = _raw_tokens(expression)
    tokens: list[_Token] = []
    for token in raw:
        if tokens:
            previous = tokens[-1]
            ends_value = previous.kind in {"number", "name", ")"}
            starts_value = token.kind in {"number", "name", "("}
            function_call = (
                previous.kind == "name" and previous.value in _FUNCTIONS and token.kind == "("
            )
            if ends_value and starts_value and not function_call:
                tokens.append(_Token("*", "*"))
        tokens.append(token)
    if len(tokens) > MAX_TOKENS:
        raise SurfaceExpressionError("expression has too many tokens")
    tokens.append(_Token("end", ""))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.nodes = 0
        self.group_depth = 0

    def _node(self, node: dict[str, Any]) -> dict[str, Any]:
        self.nodes += 1
        if self.nodes > MAX_AST_NODES:
            raise SurfaceExpressionError("expression has too many operations")
        return node

    @property
    def current(self) -> _Token:
        return self.tokens[self.index]

    def accept(self, kind: str) -> _Token | None:
        if self.current.kind != kind:
            return None
        token = self.current
        self.index += 1
        return token

    def require(self, kind: str) -> _Token:
        token = self.accept(kind)
        if token is None:
            raise SurfaceExpressionError(f"expected {kind!r}")
        return token

    def parse(self) -> dict[str, Any]:
        node = self.additive()
        self.require("end")
        return node

    def additive(self) -> dict[str, Any]:
        node = self.multiplicative()
        while self.current.kind in {"+", "-"}:
            operator = self.current.value
            self.index += 1
            node = self._node(
                {"type": "binary", "op": operator, "left": node, "right": self.multiplicative()}
            )
        return node

    def multiplicative(self) -> dict[str, Any]:
        node = self.unary()
        while self.current.kind in {"*", "/"}:
            operator = self.current.value
            self.index += 1
            node = self._node(
                {"type": "binary", "op": operator, "left": node, "right": self.unary()}
            )
        return node

    def unary(self) -> dict[str, Any]:
        if self.current.kind in {"+", "-"}:
            operator = self.current.value
            self.index += 1
            argument = self.unary()
            if operator == "+":
                return argument
            return self._node({"type": "unary", "op": "-", "arg": argument})
        return self.power()

    def power(self) -> dict[str, Any]:
        node = self.primary()
        if self.accept("^"):
            node = self._node({"type": "binary", "op": "^", "left": node, "right": self.unary()})
        return node

    def primary(self) -> dict[str, Any]:
        number = self.accept("number")
        if number:
            value = float(number.value)
            if not math.isfinite(value) or abs(value) > MAX_ABS_RESULT:
                raise SurfaceExpressionError("numeric literal is out of range")
            return self._node({"type": "number", "value": value})
        name = self.accept("name")
        if name:
            if name.value in _FUNCTIONS:
                self.require("(")
                argument = self.grouped()
                return self._node({"type": "call", "name": name.value, "arg": argument})
            if name.value in _VARIABLES:
                return self._node({"type": "variable", "name": name.value})
            if name.value in _CONSTANTS:
                return self._node({"type": "constant", "name": name.value})
            raise SurfaceExpressionError(f"unsupported name: {name.value}")
        if self.accept("("):
            return self.grouped()
        raise SurfaceExpressionError("expected a number, variable, function, or parenthesized term")

    def grouped(self) -> dict[str, Any]:
        self.group_depth += 1
        if self.group_depth > MAX_AST_DEPTH:
            raise SurfaceExpressionError("expression is nested too deeply")
        try:
            node = self.additive()
            self.require(")")
            return node
        finally:
            self.group_depth -= 1


def parse_surface_expression(expression: str) -> dict[str, Any]:
    """Parse a safe expression and return its JSON-serializable typed AST."""
    normalized = normalize_surface_expression(expression)
    return _Parser(_tokenize(normalized)).parse()


def _evaluate(node: dict[str, Any], variables: dict[str, float], depth: int) -> float:
    if depth > MAX_AST_DEPTH:
        raise SurfaceExpressionError("expression is nested too deeply")
    kind = node.get("type")
    if kind == "number":
        result = float(node["value"])
    elif kind == "constant":
        result = _CONSTANTS[node["name"]]
    elif kind == "variable":
        result = float(variables[node["name"]])
    elif kind == "unary":
        if node.get("op") != "-":
            raise SurfaceExpressionError("unsupported unary operator")
        result = -_evaluate(node["arg"], variables, depth + 1)
    elif kind == "binary":
        left = _evaluate(node["left"], variables, depth + 1)
        right = _evaluate(node["right"], variables, depth + 1)
        operator = node.get("op")
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        elif operator == "/":
            if right == 0:
                raise SurfaceExpressionError("division by zero")
            result = left / right
        elif operator == "^":
            result = math.pow(left, right)
        else:
            raise SurfaceExpressionError("unsupported binary operator")
    elif kind == "call":
        function = _FUNCTIONS.get(node.get("name"))
        if function is None:
            raise SurfaceExpressionError("unsupported function")
        result = function(_evaluate(node["arg"], variables, depth + 1))
    else:
        raise SurfaceExpressionError("unsupported expression node")
    if not math.isfinite(result) or abs(result) > MAX_ABS_RESULT:
        raise SurfaceExpressionError("expression result is not finite or is out of range")
    return result


def evaluate_surface_expression(
    tree: dict[str, Any], *, x: float, y: float, t: float = 0.0
) -> float:
    """Evaluate a parsed surface tree for finite, explicitly supplied variables."""
    variables = {"x": float(x), "y": float(y), "t": float(t)}
    if not all(math.isfinite(value) and abs(value) <= 1000 for value in variables.values()):
        raise SurfaceExpressionError("surface variables are out of range")
    return _evaluate(tree, variables, 0)


def format_surface_expression(tree: dict[str, Any]) -> str:
    """Return compact Unicode maths for labels without exposing raw LaTeX commands."""
    superscripts = {2.0: "²", 3.0: "³"}
    fractions = {(1.0, 2.0): "½", (1.0, 4.0): "¼", (3.0, 4.0): "¾"}

    def render(node: dict[str, Any], parent_precedence: int = 0) -> str:
        kind = node["type"]
        if kind == "number":
            value = float(node["value"])
            return str(int(value)) if value.is_integer() else f"{value:g}"
        if kind == "constant":
            return "π" if node["name"] == "pi" else "e"
        if kind == "variable":
            return node["name"]
        if kind == "call":
            return f"{node['name']}({render(node['arg'])})"
        if kind == "unary":
            argument = render(node["arg"], 4)
            return f"−{argument}"
        operator = node["op"]
        precedence = {"+": 1, "-": 1, "*": 2, "/": 2, "^": 3}[operator]
        if operator == "/":
            left_node, right_node = node["left"], node["right"]
            if left_node["type"] == right_node["type"] == "number":
                key = (float(left_node["value"]), float(right_node["value"]))
                if key in fractions:
                    return fractions[key]
        if operator == "^" and node["right"]["type"] == "number":
            exponent = float(node["right"]["value"])
            if exponent in superscripts:
                return f"{render(node['left'], precedence)}{superscripts[exponent]}"
        left = render(node["left"], precedence)
        right = render(node["right"], precedence + (1 if operator in {"-", "/", "^"} else 0))
        symbol = "·" if operator == "*" else operator
        result = f"{left}{symbol}{right}"
        return f"({result})" if precedence < parent_precedence else result

    return render(tree)


def phase_animation_expression(tree: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``sin(u - t)``/``cos(u - t)`` animation data, or none for non-periodic trees."""
    changed = False

    def transform(node: dict[str, Any]) -> dict[str, Any]:
        nonlocal changed
        kind = node["type"]
        if kind == "binary":
            return {
                "type": "binary",
                "op": node["op"],
                "left": transform(node["left"]),
                "right": transform(node["right"]),
            }
        if kind == "unary":
            return {"type": "unary", "op": node["op"], "arg": transform(node["arg"])}
        if kind == "call":
            argument = transform(node["arg"])
            if node["name"] in {"sin", "cos"}:
                changed = True
                argument = {
                    "type": "binary",
                    "op": "-",
                    "left": argument,
                    "right": {"type": "variable", "name": "t"},
                }
            return {"type": "call", "name": node["name"], "arg": argument}
        return dict(node)

    result = transform(tree)
    return result if changed else None
