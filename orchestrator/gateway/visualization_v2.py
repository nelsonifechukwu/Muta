"""Safe, deterministic visualization engine V2.

The model may help choose a family, but the browser only receives this closed declarative
grammar.  There is deliberately no executable source, markup, URL, shader, or dynamic property
lookup in the protocol.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

SPEC_VERSION = 2
MAX_SPEC_BYTES = 48 * 1024
MAX_AST_NODES = 160
MAX_AST_DEPTH = 24
MAX_LAYERS = 96
MAX_POINTS = 4096
MAX_PARAMETER_CONTROLS = 8
TRANSPORT_CONTROL_IDS = frozenset({"play", "pause", "restart"})
TRANSPORT_CONTROL_LABELS = {"play": "Play", "pause": "Pause", "restart": "Restart"}
MAX_CONTROLS = MAX_PARAMETER_CONTROLS + len(TRANSPORT_CONTROL_IDS)
MAX_STATES = 12
MAX_IMPLICIT_CELLS = 32_768
MAX_TRIANGLES = 32_000
MAX_PARTICLES = 800
MAX_VECTOR_SAMPLES = 800
MAX_HEATMAP_CELLS = 4_096
CONTROL_BINDING_EFFECTS = frozenset({"translate_x", "translate_y", "scale", "radius"})

_BINDABLE_LAYER_EFFECTS: dict[str, frozenset[str]] = {
    "polyline": frozenset({"translate_x", "translate_y", "scale"}),
    "node": frozenset({"translate_x", "translate_y", "scale"}),
    "arrow": frozenset({"translate_x", "translate_y", "scale"}),
    "circle": CONTROL_BINDING_EFFECTS,
    "rect": frozenset({"translate_x", "translate_y", "scale"}),
    "particles": frozenset({"translate_x", "translate_y", "scale"}),
    "vector_field": frozenset({"translate_x", "translate_y", "scale"}),
}
_RENDERER_BINDABLE_TYPES: dict[str, frozenset[str]] = {
    "svg": frozenset(_BINDABLE_LAYER_EFFECTS),
    "canvas": frozenset({"polyline", "particles", "vector_field"}),
    "three": frozenset(),
}

_THREE_PRIMITIVE_TRIANGLES = {
    # Keep these estimates synchronized with the fixed renderer geometry in viz-frame-v2.js.
    "sphere": 720,
    "point": 720,
    "box": 12,
    "plane": 128,
    "vector": 32,
}
# Renderer-owned mesh work is part of the same authoritative budget as learner geometry.
# Explicit/implicit surfaces add at most twelve two-triangle text sprites (axis names/ticks),
# while the parametric-surface family adds one 16×12 sphere marker.
_THREE_SURFACE_LABEL_TRIANGLES = 24
_THREE_PARAMETRIC_MARKER_TRIANGLES = 352

_SAFE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_SAFE_FAMILY = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SAFE_COLOR = re.compile(
    r"(?:#[0-9a-fA-F]{3,8}|(?:rgb|hsl)a?\([0-9.,%\s-]+\)|"
    r"black|white|gray|grey|red|green|blue|orange|purple|teal|gold)\Z"
)
_LAYER_KEYS: dict[str, frozenset[str]] = {
    "axes": frozenset({"type", "x_label", "y_label", "grid"}),
    "polyline": frozenset({"type", "label", "points", "color"}),
    "node": frozenset({"type", "id", "x", "y", "width", "height", "label", "color"}),
    "link": frozenset({"type", "from", "to", "arrow", "label"}),
    "sphere": frozenset({"type", "position", "size", "label", "color"}),
    "box": frozenset({"type", "position", "size", "label", "color"}),
    "point": frozenset({"type", "position", "size", "label", "color"}),
    "vector": frozenset({"type", "from", "to", "label", "color"}),
    "line": frozenset({"type", "points", "label", "color"}),
    "plane": frozenset({"type", "normal", "constant", "label", "color"}),
    "explicit_surface": frozenset(
        {
            "type",
            "label",
            "relationship",
            "x_domain",
            "y_domain",
            "z_domain",
            "resolution",
            "animation",
        }
    ),
    "implicit_surface": frozenset(
        {
            "type",
            "label",
            "relationship",
            "x_domain",
            "y_domain",
            "z_domain",
            "resolution",
            "animation",
        }
    ),
    "parametric_surface": frozenset(
        {
            "type",
            "x_expression",
            "y_expression",
            "z_expression",
            "u_domain",
            "v_domain",
            "resolution",
            "label",
            "animation",
        }
    ),
    "arrow": frozenset({"type", "from", "to", "label", "color"}),
    "circle": frozenset({"type", "x", "y", "r", "label", "color"}),
    "rect": frozenset({"type", "x", "y", "width", "height", "label", "color"}),
    "text": frozenset({"type", "x", "y", "text", "color"}),
    "particles": frozenset({"type", "points", "color", "label"}),
    "vector_field": frozenset({"type", "vectors", "color", "label"}),
    "probe_vector": frozenset(
        {
            "type",
            "x_control",
            "y_control",
            "x_expression",
            "y_expression",
            "scale",
            "color",
            "label",
        }
    ),
    "heatmap": frozenset(
        {"type", "x_domain", "y_domain", "rows", "columns", "values", "color", "label"}
    ),
    "panel": frozenset({"type", "id", "title", "x_label", "y_label", "members"}),
}

_VARIABLES = frozenset({"x", "y", "z", "u", "v", "t"})
_CONSTANTS = {"pi": math.pi, "e": math.e}
_UNARY_FUNCTIONS = {
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
_BINARY_FUNCTIONS = {"atan2": math.atan2, "min": min, "max": max}
_VISUAL_WORDS = re.compile(
    r"\b(?:visuali[sz]e|diagram|plot|graph|chart|sketch|"
    r"animate|animation|make\s+it\s+move|render|"
    r"sch[eé]ma|dessin|tracer|graphique|grafu|chora|onyonyo|umfanekiso)\b",
    re.IGNORECASE,
)
_VISUAL_REQUEST_PHRASE = re.compile(
    r"\b(?:show|build|create|generate|make|model|map|track|trace|compare|draw|"
    r"illustrate|picture)\s+"
    r"(?:me\s+)?(?:a|an|the|this|that|these|those)?\s*"
    r"(?:interactive\s+|moving\s+|labelled\s+|labeled\s+)?"
    r"(?:diagram|visuali[sz]ation|plot|graph|chart|picture|sketch|map|simulation|model|"
    r"trajectory|field|surface|scene|animation|circle|triangle|square|rectangle|polygon|"
    r"angle|geometric\s+shape)\b",
    re.IGNORECASE,
)
_DIRECT_VISUAL_REQUEST = re.compile(
    r"(?:^|[.!?]\s+)(?:please\s+)?(?:can|could|would)\s+you\s+"
    r"(?:please\s+)?(?:visuali[sz]e|draw|plot|graph|chart|sketch|illustrate|map|simulate|model|animate|render)\b|"
    r"^\s*(?:\[[^\]]{1,48}\]\s*)?(?:please\s+)?(?:visuali[sz]e|diagram|draw|plot|graph|chart|sketch|illustrate|map|simulate|model|animate|render)\b|"
    r"\b(?:i\s+(?:want|need|would\s+like)|let\s+me\s+see)\s+(?:to\s+)?(?:see\s+)?"
    r"(?:a|an|the)?\s*(?:diagram|visuali[sz]ation|plot|graph|chart|picture|sketch|map|simulation|model|animation)\b|"
    r"\b(?:with|using)\s+(?:a|an|the)?\s*(?:[a-z-]+\s+){0,3}(?:diagram|plot|graph|chart|visuali[sz]ation|animation)\b|"
    r"\b(?:sch[eé]ma|dessin|tracer|graphique|grafu|chora|onyonyo|umfanekiso)\b",
    re.IGNORECASE,
)
_NON_VISUAL_CONTEXT = re.compile(
    r"\b(?:plot\s+twist|plot\s+of\s+(?:the\s+)?(?:novel|story|book)|graph\s+paper|"
    r"sketch\s+comedy|chart\s+a\s+course|draw\s+a\s+conclusion|simulate\s+a\s+conversation|"
    r"picture\s+this\s+as\s+a\s+proof|illustrate\s+(?:your|the)\s+reasoning\s+in\s+words|"
    r"model\s+(?:good|appropriate|expected)\s+behavio(?:u)?r|"
    r"map\s+(?:(?:this|the)\s+)?(?:concept\s+to\s+the\s+syllabus|curriculum|requirements?|stakeholders?|responsibilities)|"
    r"graph\s+theory|animate\s+(?:the\s+)?(?:discussion|prose|explanation)\s+with\s+examples)\b|"
    r"\b(?:definition|meaning)\s+of\s+(?:a\s+)?(?:graph|plot|diagram|model)\b|"
    r"\b(?:explain|describe|summari[sz]e|define)\b[^.!?]{0,120}\b(?:in|using)\s+(?:plain\s+)?(?:text|prose|words)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_VISUAL_VERB = re.compile(
    r"\b(?:show|build|create|generate|make|model|map|track|trace|compare|draw|"
    r"picture|illustrate|simulate)\b",
    re.IGNORECASE,
)
_NEGATIVE_VISUAL = re.compile(
    r"\b(?:no|do\s+not|don['’]t|without)\s+(?:(?:draw|show|make|generate)\s+)?"
    r"(?:a\s+)?(?:diagram|graph|plot|chart|visual|animation)\b|"
    r"\b(?:text\s+only|prose\s+only|show\s+(?:the\s+)?(?:proof|working|text))\b",
    re.IGNORECASE,
)
_ANIMATE_ONLY = re.compile(
    r"^\s*(?:please\s+)?(?:animate(?:\s+it)?|make\s+it\s+move|play\s+it|"
    r"animer(?:\s+ça)?|ihu\s+ya\s+na-emegharị)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_EXPLICIT_ANIMATION = re.compile(
    r"\b(?:animate(?:d|s|ing|ion)?|simulate(?:d|s|ing|ion)?|"
    r"make\s+(?:it|this|the\s+[a-z][\w-]*)\s+move|"
    r"show\s+(?:its|the)\s+motion|moving\s+(?:diagram|model|scene|system|point|particle|mass(?:[- ]spring)?))\b",
    re.IGNORECASE,
)
_EQUATION_SIGNAL = re.compile(r"(?:\bz\s*=|\b[xyz]\s*[²^]|\$\$|\\(?:sin|cos|sqrt|frac))")


class VisualizationV2Error(ValueError):
    """The requested scene is unsafe, unsupported, or outside deterministic budgets."""


@dataclass(frozen=True)
class VisualIntent:
    requested: bool
    family: str | None = None
    renderer: str | None = None
    animate_previous: bool = False
    reason: str = ""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str


def _latex_fraction(value: str) -> str:
    """Expand conservative braced TeX fractions without interpreting commands."""

    def group(start: int) -> tuple[str, int]:
        if start >= len(value) or value[start] != "{":
            raise VisualizationV2Error("fraction arguments must be braced")
        depth = 0
        for index in range(start, len(value)):
            if value[index] == "{":
                depth += 1
            elif value[index] == "}":
                depth -= 1
                if depth == 0:
                    return value[start + 1 : index], index + 1
            if depth > MAX_AST_DEPTH:
                raise VisualizationV2Error("expression nesting exceeds the budget")
        raise VisualizationV2Error("unclosed fraction argument")

    output: list[str] = []
    cursor = 0
    while cursor < len(value):
        if value.startswith(r"\frac", cursor):
            left, next_cursor = group(cursor + 5)
            right, cursor = group(next_cursor)
            output.append(f"(({_latex_fraction(left)})/({_latex_fraction(right)}))")
        else:
            output.append(value[cursor])
            cursor += 1
    return "".join(output)


def normalize_relationship(source: str) -> str:
    """Normalize a safe plain/LaTeX relationship while retaining mathematical meaning."""
    value = str(source or "").strip()
    if len(value) > 600:
        raise VisualizationV2Error("relationship is too long")
    # Text copied through JSON, Python string literals, PDFs, or word processors sometimes
    # turns the leading backslash of ``\frac``/``\right`` into the corresponding ASCII control
    # character (form feed/carriage return). Repair only these exact TeX command fragments; other
    # control characters remain invalid input and never reach the expression parser.
    value = value.replace("\f" + "rac", r"\frac").replace("\r" + "ight", r"\right")
    value = re.sub(r"(?<![A-Za-z\\])left\s*(?=\()", "", value)
    value = value.replace("$$", "").replace(r"\[", "").replace(r"\]", "")
    value = value.replace("−", "-").replace("–", "-").replace("×", "*").replace("·", "*")
    value = value.replace("²", "^2").replace("³", "^3").replace("π", "pi")
    value = re.sub(r"\\(?:left|right|,|!|;|:|quad|qquad)", "", value)
    value = re.sub(r"\\(?:cdot|times)", "*", value)
    value = re.sub(r"\\frac\s*([0-9A-Za-z])\s*([0-9A-Za-z])", r"((\1)/(\2))", value)
    value = _latex_fraction(value)
    value = re.sub(r"\\operatorname\s*\{\s*(atan2|exp|ln|log)\s*\}", r"\1", value)
    unary_names = "|".join(sorted(_UNARY_FUNCTIONS, key=len, reverse=True))
    value = re.sub(
        rf"\\({unary_names})\s*([xyzuvt])(?=\\|\W|$)",
        r"\1(\2)",
        value,
    )
    value = re.sub(r"\\arctan2\b", "atan2", value)
    for name in sorted((*_UNARY_FUNCTIONS, *_BINARY_FUNCTIONS), key=len, reverse=True):
        value = re.sub(rf"\\{name}\b", name, value)
    if "\\" in value:
        raise VisualizationV2Error("unsupported LaTeX command")
    value = re.sub(r"\^\s*\{", "^(", value)
    value = value.replace("{", "(").replace("}", ")")
    value = value.replace("[", "").replace("]", "")
    for _index in range(8):
        replaced = re.sub(r"\|([^|]+)\|", r"abs(\1)", value)
        if replaced == value:
            break
        value = replaced
    if "|" in value:
        raise VisualizationV2Error("absolute-value bars are unbalanced")
    value = re.sub(
        rf"\b({'|'.join(sorted(_UNARY_FUNCTIONS, key=len, reverse=True))})\s+([xyzuvt])\b",
        r"\1(\2)",
        value,
    )
    value = re.sub(r"\s+", "", value).rstrip(";,.:")
    if any(ord(character) < 32 for character in value):
        raise VisualizationV2Error("relationship contains unsupported control characters")
    if not value or len(value) > 500:
        raise VisualizationV2Error("relationship is empty or too long")
    return value


def _tokenize(value: str) -> list[_Token]:
    raw: list[_Token] = []
    cursor = 0
    while cursor < len(value):
        number = re.match(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value[cursor:])
        if number:
            raw.append(_Token("number", number.group(0)))
            cursor += len(number.group(0))
            continue
        name = re.match(r"[A-Za-z][A-Za-z0-9]*", value[cursor:])
        if name:
            identifier = name.group(0).lower()
            known = _UNARY_FUNCTIONS.keys() | _BINARY_FUNCTIONS.keys() | _CONSTANTS.keys()
            if identifier not in known and len(identifier) > 1:
                parts: list[str] = []
                remainder = identifier
                while remainder:
                    if remainder.startswith("pi"):
                        parts.append("pi")
                        remainder = remainder[2:]
                    elif remainder[0] in _VARIABLES or remainder[0] == "e":
                        parts.append(remainder[0])
                        remainder = remainder[1:]
                    else:
                        parts = []
                        break
                if parts:
                    raw.extend(_Token("name", part) for part in parts)
                else:
                    raw.append(_Token("name", identifier))
            else:
                raw.append(_Token("name", identifier))
            cursor += len(name.group(0))
            continue
        character = value[cursor]
        if character in "+-*/^(),":
            raw.append(_Token(character, character))
            cursor += 1
            continue
        raise VisualizationV2Error(f"unsupported expression character at {cursor}")
    if len(raw) > 240:
        raise VisualizationV2Error("expression has too many tokens")
    tokens: list[_Token] = []
    function_names = _UNARY_FUNCTIONS.keys() | _BINARY_FUNCTIONS.keys()
    for token in raw:
        if tokens:
            previous = tokens[-1]
            end_value = previous.kind in {"number", "name", ")"}
            start_value = token.kind in {"number", "name", "("}
            function_call = (
                previous.kind == "name" and previous.value in function_names and token.kind == "("
            )
            if end_value and start_value and not function_call:
                tokens.append(_Token("*", "*"))
        tokens.append(token)
    tokens.append(_Token("end", ""))
    return tokens


class _ExpressionParser:
    def __init__(self, value: str) -> None:
        self.tokens = _tokenize(value)
        self.index = 0
        self.nodes = 0
        self.depth = 0

    @property
    def current(self) -> _Token:
        return self.tokens[self.index]

    def take(self, kind: str) -> _Token | None:
        if self.current.kind != kind:
            return None
        token = self.current
        self.index += 1
        return token

    def need(self, kind: str) -> _Token:
        token = self.take(kind)
        if token is None:
            raise VisualizationV2Error(f"expected {kind}")
        return token

    def node(self, value: dict[str, Any]) -> dict[str, Any]:
        self.nodes += 1
        if self.nodes > MAX_AST_NODES:
            raise VisualizationV2Error("expression has too many operations")
        return value

    def parse(self) -> dict[str, Any]:
        result = self.additive()
        self.need("end")
        return result

    def additive(self) -> dict[str, Any]:
        result = self.multiplicative()
        while self.current.kind in {"+", "-"}:
            op = self.current.value
            self.index += 1
            result = self.node(
                {"type": "binary", "op": op, "left": result, "right": self.multiplicative()}
            )
        return result

    def multiplicative(self) -> dict[str, Any]:
        result = self.unary()
        while self.current.kind in {"*", "/"}:
            op = self.current.value
            self.index += 1
            result = self.node({"type": "binary", "op": op, "left": result, "right": self.unary()})
        return result

    def unary(self) -> dict[str, Any]:
        if self.take("+"):
            return self.unary()
        if self.take("-"):
            return self.node({"type": "unary", "op": "-", "arg": self.unary()})
        return self.power()

    def power(self) -> dict[str, Any]:
        result = self.primary()
        if self.take("^"):
            result = self.node({"type": "binary", "op": "^", "left": result, "right": self.unary()})
        return result

    def primary(self) -> dict[str, Any]:
        number = self.take("number")
        if number:
            value = float(number.value)
            if not math.isfinite(value) or abs(value) > 1e9:
                raise VisualizationV2Error("numeric literal is outside the budget")
            return self.node({"type": "number", "value": value})
        name = self.take("name")
        if name:
            if name.value in _VARIABLES:
                return self.node({"type": "variable", "name": name.value})
            if name.value in _CONSTANTS:
                return self.node({"type": "constant", "name": name.value})
            if name.value not in _UNARY_FUNCTIONS and name.value not in _BINARY_FUNCTIONS:
                raise VisualizationV2Error(f"unsupported name: {name.value}")
            self.need("(")
            args = [self.grouped_argument()]
            while self.take(","):
                args.append(self.grouped_argument())
            self.need(")")
            expected = 2 if name.value in _BINARY_FUNCTIONS else 1
            if len(args) != expected:
                raise VisualizationV2Error(f"{name.value} expects {expected} arguments")
            return self.node({"type": "call", "name": name.value, "args": args})
        if self.take("("):
            result = self.grouped_argument()
            self.need(")")
            return result
        raise VisualizationV2Error("expected a number, variable, function, or group")

    def grouped_argument(self) -> dict[str, Any]:
        self.depth += 1
        if self.depth > MAX_AST_DEPTH:
            raise VisualizationV2Error("expression nesting exceeds the budget")
        try:
            return self.additive()
        finally:
            self.depth -= 1


def parse_expression_v2(value: str) -> dict[str, Any]:
    return _ExpressionParser(value).parse()


def parse_relationship(source: str) -> dict[str, Any]:
    value = normalize_relationship(source)
    pieces = value.split("=")
    if len(pieces) != 2 or not all(pieces):
        raise VisualizationV2Error("a visualization relationship needs exactly one equals sign")
    left = parse_expression_v2(pieces[0])
    right = parse_expression_v2(pieces[1])
    return {"type": "relationship", "op": "=", "left": left, "right": right}


def evaluate_expression_v2(
    node: dict[str, Any], variables: dict[str, float], depth: int = 0
) -> float:
    if depth > MAX_AST_DEPTH:
        raise VisualizationV2Error("expression nesting exceeds the budget")
    kind = node.get("type")
    if kind == "number":
        result = float(node["value"])
    elif kind == "constant":
        result = _CONSTANTS[node["name"]]
    elif kind == "variable":
        result = float(variables.get(node["name"], 0.0))
    elif kind == "unary":
        result = -evaluate_expression_v2(node["arg"], variables, depth + 1)
    elif kind == "binary":
        left = evaluate_expression_v2(node["left"], variables, depth + 1)
        right = evaluate_expression_v2(node["right"], variables, depth + 1)
        operator = node["op"]
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        elif operator == "/":
            result = math.nan if abs(right) < 1e-12 else left / right
        elif operator == "^":
            try:
                result = left**right
            except (OverflowError, ValueError, ZeroDivisionError, TypeError) as error:
                raise VisualizationV2Error("expression result is undefined") from error
        else:
            raise VisualizationV2Error("unsupported binary operator")
    elif kind == "call":
        args = [evaluate_expression_v2(arg, variables, depth + 1) for arg in node["args"]]
        function = _BINARY_FUNCTIONS.get(node["name"]) or _UNARY_FUNCTIONS.get(node["name"])
        if function is None:
            raise VisualizationV2Error("unsupported function")
        try:
            result = function(*args)
        except (OverflowError, ValueError, ZeroDivisionError, TypeError) as error:
            raise VisualizationV2Error("expression result is undefined") from error
    else:
        raise VisualizationV2Error("invalid expression node")
    if (
        not isinstance(result, (int, float))
        or isinstance(result, bool)
        or not math.isfinite(result)
        or abs(result) > 1e9
    ):
        raise VisualizationV2Error("expression result is undefined or outside the budget")
    return float(result)


def relationship_residual(relationship: dict[str, Any], variables: dict[str, float]) -> float:
    return evaluate_expression_v2(relationship["left"], variables) - evaluate_expression_v2(
        relationship["right"], variables
    )


def _contains_variable(node: dict[str, Any], name: str) -> bool:
    if node.get("type") == "variable":
        return node.get("name") == name
    if node.get("type") == "binary":
        return _contains_variable(node["left"], name) or _contains_variable(node["right"], name)
    if node.get("type") == "unary":
        return _contains_variable(node["arg"], name)
    if node.get("type") == "call":
        return any(_contains_variable(arg, name) for arg in node["args"])
    return False


def _contains_call(node: dict[str, Any], names: set[str]) -> bool:
    if node.get("type") == "call":
        return node.get("name") in names or any(
            _contains_call(arg, names) for arg in node.get("args", [])
        )
    if node.get("type") == "binary":
        return _contains_call(node["left"], names) or _contains_call(node["right"], names)
    if node.get("type") == "unary":
        return _contains_call(node["arg"], names)
    return False


def _relationship_from_request(request: str) -> tuple[str, dict[str, Any]] | None:
    value = str(request or "")
    candidates: list[str] = []
    for pattern in (r"\$\$(.*?)\$\$", r"\\\[(.*?)\\\]"):
        candidates.extend(
            match.group(1)
            for match in re.finditer(pattern, value, re.DOTALL)
            if "=" in match.group(1)
        )
    candidates.extend(
        match.group(2) for match in re.finditer(r"([\"'`])([^\"'`]*=[^\"'`]*)\1", value, re.DOTALL)
    )
    lines = [line.strip().strip('"`') for line in value.splitlines()]
    for index, line in enumerate(lines):
        if "=" not in line:
            continue
        tail: list[str] = []
        for candidate_line in lines[index:]:
            if candidate_line in {"[", "]", "$$", r"\[", r"\]"}:
                continue
            if tail and re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{3,}", candidate_line):
                break
            tail.append(candidate_line)
        candidates.append("".join(tail))
        candidates.append(line)
    match = re.search(
        r"\b([xyz]\s*=\s*[^\n\"'`]+?)"
        r"(?=\s+(?:as|with)\s+(?:(?:an?|the)\s+)?"
        r"(?:3d|three[- ]dimensional|surface|diagram|plot|graph)\b|[.!?]\s*$|$)",
        value,
        re.IGNORECASE,
    )
    if match:
        candidates.append(match.group(1))
    visual_equation = re.search(
        r"\b(?:plot|graph|chart|draw|sketch|visuali[sz]e|show|illustrate|picture|render|"
        r"build|create|generate|make|model|map|track|trace|compare)\s+(?:me\s+)?"
        r"(?:(?:an?|the)\s+)?(?:(?:line|curve|circle|triangle|square|rectangle|polygon|"
        r"equation|plot|graph|chart|diagram)\s+)?(?:of\s+)?"
        r"([^\n.!?]*=[^\n.!?]*)",
        value,
        re.IGNORECASE,
    )
    if visual_equation:
        candidates.append(visual_equation.group(1))
    # A relationship may be wrapped in representation prose. Offer the closed parser a
    # second candidate with only allow-listed visual words removed; the relation itself
    # still has to pass the same typed AST parser and budgets.
    wrapped_candidates: list[str] = []
    for candidate in candidates:
        stripped = re.sub(
            r"^\s*(?:render|visuali[sz]e|plot|graph|chart|draw|sketch|show|illustrate|"
            r"picture|build|create|generate|make|model|map|track|trace|compare)\s+"
            r"(?:me\s+)?(?:(?:an?|the)\s+)?(?:(?:implicit|explicit)\s+)?"
            r"(?:(?:surface|curve|equation|plot|graph|diagram|line|circle|triangle|square|"
            r"rectangle|polygon)\s+)?(?:of\s+)?",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        # Keep a trailing annotation request from becoming part of the typed equation. This
        # accepts broad educational wording ("and show the roots", "label the radius") while
        # the retained left-hand expression still has to pass the closed AST parser.
        stripped = re.split(
            r"\s+(?:and\s+)?(?:label|show|mark|identify|annotate|highlight|indicate)\b",
            stripped,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        stripped = re.split(
            r"\s+as\s+(?:(?:an?|the)\s+)?(?:3d|three[- ]dimensional)\b",
            stripped,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        stripped = re.sub(
            r"\s+(?:as\s+)?(?:(?:an?|the)\s+)?(?:(?:implicit|explicit)\s+)?"
            r"(?:surface|curve|plot|graph|diagram)\s*$",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        if stripped and stripped != candidate:
            wrapped_candidates.append(stripped)
    candidates.extend(wrapped_candidates)
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            normalized = normalize_relationship(candidate)
            return normalized, parse_relationship(normalized)
        except VisualizationV2Error:
            continue
    return None


def _parametric_expressions_from_request(request: str) -> dict[str, dict[str, Any]] | None:
    text = str(request or "")
    if not re.search(r"\bparametric\b|[xyz]\s*\(\s*u\s*,\s*v\s*\)", text, re.IGNORECASE):
        return None
    expressions: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"\b([xyz])(?:\s*\(\s*u\s*,\s*v\s*\))?\s*=\s*(.+?)"
        r"(?=(?:[,;\n]\s*[xyz](?:\s*\(\s*u\s*,\s*v\s*\))?\s*=)|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        axis = match.group(1).lower()
        source = match.group(2).strip().strip('"` ')
        try:
            expressions[axis] = parse_relationship(f"{axis}={source}")["right"]
        except VisualizationV2Error:
            return None
    return expressions if set(expressions) == {"x", "y", "z"} else None


def _parametric_spec(expressions: dict[str, dict[str, Any]], label: str) -> dict[str, Any]:
    layer = {
        "type": "parametric_surface",
        "x_expression": expressions["x"],
        "y_expression": expressions["y"],
        "z_expression": expressions["z"],
        "u_domain": [-round(math.pi, 6), round(math.pi, 6)],
        "v_domain": [-2.0, 2.0],
        "resolution": [64, 32],
        "label": label[:160] or "parametric surface",
    }
    return {
        "version": SPEC_VERSION,
        "library": "three",
        "renderer": "three",
        "kind": "scene3d",
        "family": "parametric_surface",
        "title": "Interactive parametric surface",
        "aria_label": "Three-dimensional parametric surface with u and v sampling controls.",
        "text_fallback": "A bounded parametric surface generated from safe typed x(u,v), y(u,v), and z(u,v) expressions.",
        "height": 480,
        "controls": [
            {"id": "orbit", "label": "Rotate view", "type": "button", "value": 0},
            {"id": "reset_view", "label": "Reset view", "type": "button", "value": 0},
        ],
        "budget": {"max_points": 4096, "max_triangles": MAX_TRIANGLES, "max_fps": 30},
        "scene": {"coordinate_system": "cartesian3d", "layers": [layer]},
    }


def _assignment_expressions(
    request: str, variables: tuple[str, ...]
) -> dict[str, dict[str, Any]] | None:
    """Parse comma/newline separated assignments without accepting trailing prose."""
    text = str(request or "")
    starts = list(re.finditer(rf"\b({'|'.join(variables)})\s*=", text, re.IGNORECASE))
    expressions: dict[str, dict[str, Any]] = {}
    for index, match in enumerate(starts):
        name = match.group(1).lower()
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        source = text[match.end() : end].strip().strip(",; \n\t\"'`")
        source = re.split(
            r"\s+(?:with|as|on|using|and\s+(?:show|label|colour|color))\b",
            source,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        try:
            expressions[name] = parse_expression_v2(normalize_relationship(source))
        except VisualizationV2Error:
            continue
    return expressions if all(name in expressions for name in variables) else None


def _parenthesized_pair(request: str, prefix: str) -> tuple[str, str] | None:
    match = re.search(prefix + r"\s*\(", str(request or ""), re.IGNORECASE)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    comma = -1
    for index in range(start, len(request)):
        character = request[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                if comma < 0:
                    return None
                return request[start + 1 : comma], request[comma + 1 : index]
        elif character == "," and depth == 1 and comma < 0:
            comma = index
    return None


def _safe_sample(expression: dict[str, Any], variables: dict[str, float]) -> float | None:
    try:
        value = evaluate_expression_v2(expression, variables)
    except (VisualizationV2Error, ValueError, OverflowError, ZeroDivisionError, TypeError):
        return None
    return value if math.isfinite(value) and abs(value) <= 1_000_000 else None


def _chain_segments(segments: list[list[list[float]]]) -> list[list[list[float]]]:
    """Join marching-square segments into bounded polylines using quantized endpoints."""
    unused = [segment for segment in segments if len(segment) == 2]
    chains: list[list[list[float]]] = []

    def close(left: list[float], right: list[float]) -> bool:
        return abs(left[0] - right[0]) < 1e-5 and abs(left[1] - right[1]) < 1e-5

    while unused and len(chains) < MAX_LAYERS - 2:
        chain = unused.pop()
        changed = True
        while changed:
            changed = False
            for index, segment in enumerate(unused):
                if close(chain[-1], segment[0]):
                    chain.append(segment[1])
                    unused.pop(index)
                    changed = True
                    break
                if close(chain[-1], segment[1]):
                    chain.append(segment[0])
                    unused.pop(index)
                    changed = True
                    break
                if close(chain[0], segment[1]):
                    chain.insert(0, segment[0])
                    unused.pop(index)
                    changed = True
                    break
                if close(chain[0], segment[0]):
                    chain.insert(0, segment[1])
                    unused.pop(index)
                    changed = True
                    break
        chains.append(chain)
    return chains


def _marching_squares(
    sample: Any,
    *,
    level: float = 0.0,
    domain: tuple[float, float] = (-5.0, 5.0),
    cells: int = 48,
) -> list[list[list[float]]]:
    low, high = domain
    step = (high - low) / cells
    grid: list[list[float | None]] = []
    for row in range(cells + 1):
        y = low + row * step
        grid.append([sample(low + column * step, y) for column in range(cells + 1)])
    segments: list[list[list[float]]] = []
    edges = ((0, 1), (1, 2), (2, 3), (3, 0))
    for row in range(cells):
        for column in range(cells):
            x0, y0 = low + column * step, low + row * step
            corners = [
                ([x0, y0], grid[row][column]),
                ([x0 + step, y0], grid[row][column + 1]),
                ([x0 + step, y0 + step], grid[row + 1][column + 1]),
                ([x0, y0 + step], grid[row + 1][column]),
            ]
            hits: list[list[float]] = []
            for first, second in edges:
                point_a, value_a = corners[first]
                point_b, value_b = corners[second]
                if value_a is None or value_b is None:
                    continue
                residual_a, residual_b = value_a - level, value_b - level
                if residual_a == 0:
                    hits.append(point_a)
                elif residual_a * residual_b < 0:
                    ratio = abs(residual_a) / (abs(residual_a) + abs(residual_b))
                    hits.append(
                        [
                            round(point_a[0] + ratio * (point_b[0] - point_a[0]), 6),
                            round(point_a[1] + ratio * (point_b[1] - point_a[1]), 6),
                        ]
                    )
            if len(hits) == 2:
                segments.append(hits)
            elif len(hits) == 4:
                segments.extend(([hits[0], hits[1]], [hits[2], hits[3]]))
    return _chain_segments(segments)


def _curve_spec(
    family: str,
    title: str,
    layers: list[dict[str, Any]],
    fallback: str,
    *,
    renderer: str = "svg",
    controls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spec = {
        "version": SPEC_VERSION,
        "library": "d3",
        "renderer": renderer,
        "kind": "simulation2d" if renderer == "canvas" else "scene2d",
        "family": family,
        "title": title[:120],
        "aria_label": (title + ". " + fallback)[:500],
        "text_fallback": fallback[:1200],
        "height": 420,
        "controls": controls or [],
        "budget": {"max_points": MAX_POINTS, "max_triangles": 1, "max_fps": 30},
        "scene": {"coordinate_system": "cartesian2d", "layers": layers},
    }
    validate_v2_spec(spec)
    return spec


def _generic_2d_spec(
    request: str,
    normalized: str | None,
    relationship: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Compile bounded 2D equations and fields before any 3D fallback is considered."""
    text = str(request or "")
    pair = _parenthesized_pair(text, r"\b(?:f|field)\s*=")
    if pair:
        try:
            x_expression = parse_expression_v2(normalize_relationship(pair[0]))
            y_expression = parse_expression_v2(normalize_relationship(pair[1]))
        except VisualizationV2Error:
            return None
        vectors: list[list[float]] = []
        for y in (-3.0, -1.5, 0.0, 1.5, 3.0):
            for x in (-3.0, -1.5, 0.0, 1.5, 3.0):
                dx = _safe_sample(x_expression, {"x": x, "y": y})
                dy = _safe_sample(y_expression, {"x": x, "y": y})
                if dx is None or dy is None or (abs(dx) + abs(dy) < 1e-12):
                    continue
                magnitude = math.hypot(dx, dy)
                scale = 0.55 / max(0.55, magnitude)
                vectors.append([x, y, round(dx * scale, 6), round(dy * scale, 6)])
        if not vectors:
            return None
        layers = [
            {"type": "axes", "x_label": "x", "y_label": "y", "grid": True},
            {"type": "vector_field", "vectors": vectors, "label": "F(x,y)", "color": "purple"},
            {
                "type": "probe_vector",
                "x_control": "probe_x",
                "y_control": "probe_y",
                "x_expression": x_expression,
                "y_expression": y_expression,
                "scale": 0.45,
                "label": "F at movable probe",
                "color": "gold",
            },
        ]
        return _curve_spec(
            "vector_field",
            "Interactive vector field",
            layers,
            "A sampled vector field with a movable probe whose arrow evaluates the same typed field expression.",
            controls=[
                _control("probe_x", 0, "vector_field"),
                _control("probe_y", 1, "vector_field"),
            ],
        )

    polar_match = re.search(r"\br\s*=\s*([^\n;]+)", text, re.IGNORECASE)
    if polar_match:
        source = re.split(
            r"\s+(?:with|as|using|and\s+show)\b", polar_match.group(1), 1, flags=re.IGNORECASE
        )[0]
        source = re.sub(r"\btheta\b|θ", "t", source, flags=re.IGNORECASE)
        try:
            expression = parse_expression_v2(normalize_relationship(source))
        except VisualizationV2Error:
            return None
        points: list[list[float]] = []
        for index in range(241):
            angle = 2 * math.pi * index / 240
            radius = _safe_sample(expression, {"t": angle})
            if radius is not None:
                points.append([radius * math.cos(angle), radius * math.sin(angle)])
        if len(points) < 2:
            return None
        return _curve_spec(
            "polar_curve",
            "Polar curve",
            [
                {"type": "axes", "x_label": "x = r cos θ", "y_label": "y = r sin θ", "grid": True},
                {"type": "polyline", "label": "r(θ)", "points": points, "color": "orange"},
            ],
            "A polar curve sampled safely over θ from 0 to 2π.",
        )

    parametric = _assignment_expressions(text, ("x", "y"))
    if parametric and re.search(r"\bparametric\b|\bt\b", text, re.IGNORECASE):
        points = []
        for index in range(241):
            t = -math.pi + 2 * math.pi * index / 240
            x = _safe_sample(parametric["x"], {"t": t})
            y = _safe_sample(parametric["y"], {"t": t})
            if x is not None and y is not None:
                points.append([x, y])
        if len(points) < 2:
            return None
        return _curve_spec(
            "parametric_curve",
            "Parametric curve",
            [
                {"type": "axes", "x_label": "x(t)", "y_label": "y(t)", "grid": True},
                {"type": "polyline", "label": "(x(t), y(t))", "points": points, "color": "orange"},
            ],
            "A bounded parametric curve sampled from typed x(t) and y(t) expressions.",
        )

    if relationship is None or normalized is None:
        return None
    uses_z = _contains_variable(relationship["left"], "z") or _contains_variable(
        relationship["right"], "z"
    )
    contour = bool(re.search(r"\b(?:contour|heat\s*map|heatmap)\b", text, re.IGNORECASE))
    if not contour and re.search(
        r"\b(?:3d|three[- ]dimensional|surface|cylinder|cone|sphere|ellipsoid|torus|"
        r"hyperboloid|paraboloid)\b",
        text,
        re.IGNORECASE,
    ):
        return None
    if uses_z and not contour:
        return None
    axes = {"type": "axes", "x_label": "x", "y_label": "y", "grid": True}
    if contour:
        if relationship["left"] != {"type": "variable", "name": "z"}:
            return None
        expression = relationship["right"]
        size = 33
        domain = [-5.0, 5.0]
        values: list[float] = []
        finite: list[float] = []
        for row in range(size):
            y = domain[0] + (domain[1] - domain[0]) * row / (size - 1)
            for column in range(size):
                x = domain[0] + (domain[1] - domain[0]) * column / (size - 1)
                value = _safe_sample(expression, {"x": x, "y": y})
                if value is not None:
                    finite.append(value)
                values.append(value if value is not None else 0.0)
        if not finite:
            return None
        ordered = sorted(finite)
        levels = [ordered[int((len(ordered) - 1) * fraction)] for fraction in (0.25, 0.5, 0.75)]
        layers: list[dict[str, Any]] = [
            axes,
            {
                "type": "heatmap",
                "x_domain": domain,
                "y_domain": domain,
                "rows": size,
                "columns": size,
                "values": values,
                "color": "orange",
                "label": normalized,
            },
        ]
        sample = lambda x, y: _safe_sample(expression, {"x": x, "y": y})
        for level_index, level in enumerate(levels):
            for curve_index, points in enumerate(_marching_squares(sample, level=level, cells=32)):
                layers.append(
                    {
                        "type": "polyline",
                        "label": f"level {level:.3g}",
                        "points": points,
                        "color": ("teal", "gold", "purple")[level_index],
                    }
                )
                if len(layers) >= MAX_LAYERS:
                    break
            if len(layers) >= MAX_LAYERS:
                break
        return _curve_spec(
            "contour_map",
            "Contour and heat map",
            layers,
            f"Heat map and contour levels for {normalized}.",
            renderer="canvas",
        )

    left, right = relationship["left"], relationship["right"]
    if left == {"type": "variable", "name": "y"} and not _contains_variable(right, "y"):
        segments: list[list[list[float]]] = [[]]
        for index in range(321):
            x = -5 + 10 * index / 320
            y = _safe_sample(right, {"x": x})
            if y is None or abs(y) > 10_000 or (segments[-1] and abs(y - segments[-1][-1][1]) > 50):
                if segments[-1]:
                    segments.append([])
            else:
                segments[-1].append([x, y])
        curves = [segment for segment in segments if len(segment) >= 2]
        family = "explicit_curve"
    elif left == {"type": "variable", "name": "x"} and not _contains_variable(right, "x"):
        points = []
        for index in range(321):
            y = -5 + 10 * index / 320
            x = _safe_sample(right, {"y": y})
            if x is not None:
                points.append([x, y])
        curves = [points] if len(points) >= 2 else []
        family = "explicit_curve"
    else:
        sample = lambda x, y: (
            None
            if (left_value := _safe_sample(left, {"x": x, "y": y})) is None
            or (right_value := _safe_sample(right, {"x": x, "y": y})) is None
            else left_value - right_value
        )
        curves = _marching_squares(sample)
        family = "implicit_curve"
    if not curves:
        return None
    layers = [axes] + [
        {"type": "polyline", "label": normalized, "points": points, "color": "orange"}
        for points in curves[: MAX_LAYERS - 1]
    ]
    fallback = f"Two-dimensional plot of {normalized}."
    if family == "explicit_curve" and left == {"type": "variable", "name": "y"}:
        at_minus_one = _safe_sample(right, {"x": -1})
        at_zero = _safe_sample(right, {"x": 0})
        at_one = _safe_sample(right, {"x": 1})
        at_two = _safe_sample(right, {"x": 2})
        if None not in {at_minus_one, at_zero, at_one, at_two}:
            a = (at_one + at_minus_one - 2 * at_zero) / 2  # type: ignore[operator]
            b = (at_one - at_minus_one) / 2  # type: ignore[operator]
            c = at_zero
            quadratic_check = a * 4 + b * 2 + c  # type: ignore[operator]
            if abs(quadratic_check - at_two) < 1e-6:  # type: ignore[operator]
                if abs(a) < 1e-9 and re.search(r"slope|intercept", text, re.IGNORECASE):
                    layers.extend(
                        [
                            {
                                "type": "particles",
                                "points": [[0, c], [1, c + b]],
                                "label": f"y-intercept (0,{c:.3g})",
                                "color": "gold",
                            },
                            {
                                "type": "polyline",
                                "points": [[0, c], [1, c], [1, c + b]],
                                "label": f"slope rise/run = {b:.3g}/1",
                                "color": "purple",
                            },
                        ]
                    )
                    fallback += f" Slope {b:.3g}; y-intercept (0,{c:.3g})."
                elif abs(a) >= 1e-9 and re.search(
                    r"root|vertex|axis of symmetry", text, re.IGNORECASE
                ):
                    vertex_x = -b / (2 * a)
                    vertex_y = a * vertex_x * vertex_x + b * vertex_x + c
                    discriminant = b * b - 4 * a * c
                    roots = (
                        []
                        if discriminant < 0
                        else [
                            (-b - math.sqrt(discriminant)) / (2 * a),
                            (-b + math.sqrt(discriminant)) / (2 * a),
                        ]
                    )
                    layers.append(
                        {
                            "type": "particles",
                            "points": [[vertex_x, vertex_y], *[[root, 0] for root in roots]],
                            "label": f"vertex ({vertex_x:.3g},{vertex_y:.3g}); roots "
                            + (", ".join(f"{root:.3g}" for root in roots) or "none"),
                            "color": "gold",
                        }
                    )
                    layers.append(
                        {
                            "type": "polyline",
                            "points": [[vertex_x, vertex_y - 5], [vertex_x, vertex_y + 5]],
                            "label": f"axis of symmetry x={vertex_x:.3g}",
                            "color": "purple",
                        }
                    )
                    fallback += f" Vertex ({vertex_x:.3g},{vertex_y:.3g}); axis x={vertex_x:.3g}."
        if _contains_call(right, {"sin", "cos"}) and re.search(
            r"amplitude|wavelength|maxima|minimum|zero crossing", text, re.IGNORECASE
        ):
            sampled = curves[0]
            maximum = max(sampled, key=lambda point: point[1])
            minimum = min(sampled, key=lambda point: point[1])
            zeroes: list[list[float]] = []
            for first, second in pairwise(sampled):
                if first[1] == 0:
                    zeroes.append(first)
                elif first[1] * second[1] < 0:
                    ratio = abs(first[1]) / (abs(first[1]) + abs(second[1]))
                    zeroes.append([first[0] + ratio * (second[0] - first[0]), 0])
            amplitude = (maximum[1] - minimum[1]) / 2
            wavelength = zeroes[2][0] - zeroes[0][0] if len(zeroes) >= 3 else float("nan")
            layers.append(
                {
                    "type": "particles",
                    "points": [maximum, minimum, *zeroes[:5]],
                    "label": f"amplitude≈{amplitude:.3g}; wavelength≈{wavelength:.3g}; extrema and zero crossings",
                    "color": "gold",
                }
            )
            fallback += f" Amplitude about {amplitude:.3g} and wavelength about {wavelength:.3g}."
    if family == "implicit_curve" and re.search(r"centre|center|radius", text, re.IGNORECASE):
        sampled = [point for curve in curves for point in curve]
        x_low = min(point[0] for point in sampled)
        x_high = max(point[0] for point in sampled)
        y_low = min(point[1] for point in sampled)
        y_high = max(point[1] for point in sampled)
        centre = [(x_low + x_high) / 2, (y_low + y_high) / 2]
        radius = sum(math.dist(centre, point) for point in sampled) / len(sampled)
        radius_point = max(sampled, key=lambda point: point[0])
        layers.extend(
            [
                {
                    "type": "particles",
                    "points": [centre, radius_point],
                    "label": f"centre ({centre[0]:.3g},{centre[1]:.3g}) and radius point",
                    "color": "gold",
                },
                {
                    "type": "polyline",
                    "points": [centre, radius_point],
                    "label": f"radius≈{radius:.3g}",
                    "color": "purple",
                },
            ]
        )
        fallback += f" Centre ({centre[0]:.3g},{centre[1]:.3g}); radius about {radius:.3g}."
    return _curve_spec(family, "Interactive 2D equation", layers[:MAX_LAYERS], fallback)


_FAMILY_RULES: tuple[tuple[str, str, str], ...] = (
    (
        r"(?:3d|three[- ]dimensional).*vector field|vector field.*(?:3d|three[- ]dimensional|\(x\s*,\s*y\s*,\s*z\))",
        "vector_field_3d",
        "three",
    ),
    (r"lorenz(?: attractor| system)?", "lorenz_attractor", "three"),
    (
        r"electromagnetic wave|electric.*magnetic.*(?:wave|perpendicular|propagat)",
        "electromagnetic_wave",
        "three",
    ),
    (
        r"robot localization|noisy odometry|(?:odometry|fused robot pose).*uncertainty",
        "robot_localization",
        "canvas",
    ),
    (
        r"forward kinematics|(?:3|three)[- ]link manipulator|manipulator.*joint angles",
        "robot_forward_kinematics",
        "svg",
    ),
    (
        r"gradient descent|optimization trajectory|optimization.*(?:learning rate|minimum|linked surface)",
        "gradient_descent",
        "svg",
    ),
    (r"3d surface.*2d contour|2d contour.*3d surface", "gradient_linked", "svg"),
    (
        r"vector addition|vector sum|head[- ]to[- ]tail.*vectors?|geometrically show.*\+",
        "vector_addition",
        "svg",
    ),
    (
        r"binary representation|decimal.*binary|contribution of each bit|binary place[- ]value",
        "binary_representation",
        "svg",
    ),
    (r"lagrange multiplier|constraint.*gradients? align", "lagrange_multiplier", "svg"),
    (r"saddle vector field|vector field\s+f\s*=", "vector_field", "svg"),
    (r"membrane transport|diffusion.*active transport", "membrane_transport", "svg"),
    (r"moving sound source|wavefronts?.*source speed|doppler", "doppler", "canvas"),
    (r"decision boundary", "decision_boundary", "canvas"),
    (r"virtual[- ]address|page table|page fault", "virtual_memory", "svg"),
    (r"backprop|reverse gradients?|computational graph", "backprop_graph", "svg"),
    (r"nyquist curve|encirclements? of", "nyquist", "svg"),
    (r"magnitude and phase.*low-pass|low-pass.*cutoff", "bode_plot", "svg"),
    (r"simple harmonic|phase[- ]space", "harmonic_motion", "canvas"),
    (r"pythag|right[- ]angled triangle", "pythagoras", "svg"),
    (r"unit circle", "unit_circle", "svg"),
    (r"parabola|quadratic", "quadratic", "svg"),
    (
        r"straight lines|line intersection|(?:two|both|compare).{0,32}slopes?.{0,16}intercepts?",
        "line_intersection",
        "svg",
    ),
    (r"triangle.*interior angle|interior angle.*triangle", "triangle_angles", "svg"),
    (r"derivative|tangent line", "derivative_tangent", "svg"),
    (r"riemann|integral.*rectang", "riemann_sum", "svg"),
    (r"gradient|vector field", "gradient_field", "svg"),
    (
        r"two planes|plane.*intersection|intersection.*planes?",
        "plane_intersection",
        "three",
    ),
    (
        r"eigenvector|matrix transformation|transforms?.{0,32}coordinate grid|linear transform",
        "linear_transform",
        "svg",
    ),
    (r"projectile", "projectile", "svg"),
    (r"inclined plane|free[- ]body.*box", "inclined_plane", "svg"),
    (r"hooke|hanging mass|mass[- ]spring|spring.*restoring force", "spring_mass", "svg"),
    (r"colliding carts?|elastic collision", "elastic_collision", "svg"),
    (r"double pendulum", "double_pendulum", "canvas"),
    (r"pendulum", "pendulum", "svg"),
    (r"standing wave", "standing_wave", "svg"),
    (r"interference|superposition", "wave_interference", "canvas"),
    (r"transverse wave|travelling wave|traveling wave", "travelling_wave", "canvas"),
    (r"circular motion", "circular_motion", "svg"),
    (r"series and parallel|resistors?.*parallel", "series_parallel_circuit", "svg"),
    (r"simple (?:electric )?circuit|ohm['’]s law|battery.*resistor", "ohms_law_circuit", "svg"),
    (r"electric field.*vectors?|two point charges", "electric_field_vectors", "canvas"),
    (r"electric field|positive.*negative charge", "electric_field_lines", "canvas"),
    (r"magnetic field.*wire|current-carrying.*wire", "magnetic_field_wire", "svg"),
    (r"rc circuit|capacitor.*charging|charging and discharging", "rc_circuit", "svg"),
    (r"rlc circuit", "rlc_circuit", "svg"),
    (r"ac sinusoidal|phase lead|phase lag", "ac_phase", "svg"),
    (r"converging lens|lens equation|ray diagram", "converging_lens", "svg"),
    (r"refraction|snell", "refraction", "svg"),
    (r"ideal gas|pv=nrt", "ideal_gas", "svg"),
    (r"carnot", "carnot_cycle", "svg"),
    (
        r"atomic number|atom with|structure of an atom|(?:labelled|labeled|carbon) atom",
        "atom",
        "svg",
    ),
    (r"ionic bond|sodium and chlorine", "ionic_bond", "svg"),
    (r"molecular geometry|vsepr|sf₆|brf₅|h_?2o.*nh_?3.*ch_?4", "molecular_geometry", "three"),
    (r"energy profile|activation energy|exothermic", "reaction_profile", "svg"),
    (r"titration", "titration", "svg"),
    (r"molecular orbital", "molecular_orbitals", "svg"),
    (r"animal cell|organelle", "animal_cell", "svg"),
    (r"mitosis", "mitosis", "svg"),
    (r"circulatory|red blood cell|heart.*lungs", "circulation", "svg"),
    (r"action potential|sodium.*potassium channel", "action_potential", "svg"),
    (r"binary search tree", "binary_search_tree", "svg"),
    (r"binary search", "binary_search", "svg"),
    (r"dijkstra|shortest path", "dijkstra", "svg"),
    (r"stack and (?:a )?queue|lifo.*fifo", "stack_queue", "svg"),
    (r"cpu architecture|cache.*ram.*ssd|virtual address|page fault", "cpu_memory", "svg"),
    (r"sampling|aliasing|nyquist", "sampling_aliasing", "canvas"),
    (r"differential-drive|wheel velocit", "differential_drive", "canvas"),
    (r"neural network|backprop|decision boundary", "neural_network", "svg"),
    (r"complex plane|z\s*↦\s*z²", "complex_mapping", "svg"),
    (r"polar rose|polar plot", "polar_plot", "svg"),
    (r"fourier", "fourier_series", "svg"),
    (r"logistic[- ]map|bifurcation", "logistic_map", "canvas"),
    (r"lagrange multiplier", "lagrange_multiplier", "svg"),
    (r"m[öo]bius", "parametric_surface", "three"),
    (r"convolution", "convolution", "svg"),
    (r"kepler|eccentric satellite orbit", "kepler_orbit", "canvas"),
    (r"coupled oscillator|normal modes", "coupled_oscillators", "canvas"),
    (r"doppler", "doppler", "canvas"),
    (r"double[- ]slit", "double_slit", "svg"),
    (r"lorentz force|helical path", "lorentz_force", "three"),
    (r"blackbody|wien", "blackbody", "svg"),
    (r"t[-– ]s diagram|entropy.*cycle", "entropy_cycle", "canvas"),
    (r"benzene", "benzene", "svg"),
    (r"daniell|electrochemical", "electrochemical_cell", "svg"),
    (r"zero-.*first-.*second-order|chemical kinetics", "kinetics", "svg"),
    (r"phase diagram", "phase_diagram", "svg"),
    (r"le chatelier|equilibrium composition", "equilibrium_shift", "svg"),
    (r"michaelis|enzyme kinetics", "enzyme_kinetics", "svg"),
    (r"dna replication", "dna_replication", "svg"),
    (r"nephron", "nephron", "svg"),
    (r"lotka|predator.*prey", "predator_prey", "canvas"),
    (r"membrane transport", "membrane_transport", "svg"),
    (r"merge sort", "merge_sort", "svg"),
    (r"hash table", "hash_table", "svg"),
    (r"bfs.*dfs|dfs.*bfs", "graph_traversal", "svg"),
    (r"min-heap|heap property", "heap", "svg"),
    (r"recursi.*stack|factorial\(5\)", "recursion_stack", "svg"),
    (r"impulse response", "impulse_response", "svg"),
    (r"bode", "bode_plot", "svg"),
    (r"nyquist curve", "nyquist", "svg"),
    (r"pid", "pid_response", "svg"),
    (r"pwm|duty cycle", "pwm", "svg"),
    (r"spectrogram|chirp", "spectrogram", "canvas"),
    (r"robot arm|inverse kinematic", "robot_arm", "svg"),
    (r"kalman|covariance ellipse", "kalman_filter", "svg"),
    (r"truss", "truss", "svg"),
    (r"beam.*shear.*moment|beam bending", "beam_bending", "canvas"),
    (r"flow around a cylinder|streamlines", "fluid_flow", "canvas"),
    (r"heat diffusion", "heat_diffusion", "canvas"),
    (r"traffic light.*state|finite-state machine", "state_machine", "svg"),
    (r"sankey|energy audit", "energy_sankey", "svg"),
    (r"monte carlo.*density|uncertainty propagation", "uncertainty_propagation", "canvas"),
    (r"\b(?:circle|triangle|square|rectangle|polygon)\b", "basic_geometry", "svg"),
)


_FAMILY_LABELS: dict[str, tuple[str, ...]] = {
    "pythagoras": ("a²", "b²", "c²", "a² + b² = c²"),
    "projectile": ("launch", "trajectory", "velocity", "gravity"),
    "ohms_law_circuit": ("battery V", "switch", "resistor R", "ammeter I = V/R"),
    "series_parallel_circuit": ("source", "series path", "parallel branches", "return"),
    "converging_lens": ("object", "lens", "focal point", "image"),
    "refraction": ("incident ray", "normal", "refracted ray", "n₁ sin θ₁ = n₂ sin θ₂"),
    "atom": ("nucleus", "protons", "neutrons", "electron shells"),
    "ionic_bond": ("Na", "electron transfer", "Cl", "Na⁺ + Cl⁻"),
    "circulation": ("body", "right heart", "lungs", "left heart", "body"),
    "binary_search": ("sorted array", "midpoint", "discard half", "target"),
    "dijkstra": ("source", "frontier", "settled", "shortest path"),
    "cpu_memory": ("CPU", "registers/cache", "RAM", "storage"),
    "neural_network": ("inputs", "weighted hidden layer", "activation", "output"),
    "dna_replication": ("helicase", "leading strand", "lagging strand", "Okazaki fragments"),
    "electrochemical_cell": ("anode", "electron flow", "cathode", "salt bridge"),
    "energy_sankey": ("100 J input", "useful output", "heat", "sound"),
    "triangle_angles": ("vertex A", "vertex B", "vertex C", "A + B + C = 180°"),
    "linear_transform": ("input grid", "matrix A", "eigenvector direction", "transformed grid"),
    "inclined_plane": (
        "inclined surface",
        "weight mg ↓",
        "normal N ⟂ plane",
        "friction opposes motion",
    ),
    "spring_mass": ("support", "spring k", "mass m", "equilibrium kx = mg"),
    "elastic_collision": ("m₁u₁ + m₂u₂", "collision", "m₁v₁ + m₂v₂", "energy conserved"),
    "pendulum": ("pivot", "length L", "bob", "restoring force"),
    "magnetic_field_wire": (
        "current I",
        "right-hand rule",
        "circular B field",
        "reverse I → reverse B",
    ),
    "molecular_orbitals": ("H 1s", "constructive overlap", "σ bonding / σ* antibonding", "H 1s"),
    "animal_cell": ("cell membrane", "nucleus", "mitochondrion", "cytoplasm"),
    "mitosis": ("prophase", "metaphase", "anaphase", "telophase"),
    "binary_search_tree": ("smaller → left", "parent", "larger → right", "ordered tree"),
    "stack_queue": ("push/pop: LIFO", "stack", "queue", "enqueue/dequeue: FIFO"),
    "benzene": (
        "six-carbon ring",
        "alternating resonance",
        "delocalized π cloud",
        "equal C–C bonds",
    ),
    "phase_diagram": ("solid", "triple point", "liquid", "critical point / gas"),
    "equilibrium_shift": (
        "N₂ + 3H₂",
        "dynamic equilibrium",
        "2NH₃",
        "pressure favours fewer gas molecules",
    ),
    "nephron": ("glomerulus", "proximal tubule", "loop of Henle", "collecting duct"),
    "membrane_transport": (
        "high concentration",
        "membrane protein",
        "low concentration",
        "ATP for active transport",
    ),
    "merge_sort": ("split", "sort halves", "stable merge", "sorted output"),
    "hash_table": ("key", "hash function", "bucket", "collision chain"),
    "graph_traversal": ("source", "frontier", "visited set", "visit order"),
    "heap": ("minimum root", "parent ≤ children", "insert / bubble up", "extract / sift down"),
    "recursion_stack": ("factorial(5)", "recursive descent", "base case", "return-value unwind"),
    "virtual_memory": (
        "virtual address",
        "TLB / page table",
        "physical frame",
        "page fault → storage",
    ),
    "robot_arm": ("base", "link L₁", "elbow", "link L₂ → target"),
    "kalman_filter": ("prior estimate", "prediction covariance", "measurement", "updated estimate"),
    "truss": ("support reactions", "joint equilibrium", "tension members", "compression members"),
    "state_machine": ("red", "red + amber", "green", "amber → red"),
    "backprop_graph": ("inputs w,x,b", "u = wx+b", "y = u²", "reverse gradient ∂y/∂u"),
    "circular_motion": (
        "position r outward",
        "velocity tangent",
        "acceleration inward",
        "ω controls vector magnitudes",
    ),
    "entropy_cycle": (
        "isothermal expansion",
        "adiabatic expansion",
        "isothermal compression",
        "adiabatic compression",
    ),
}


def resolve_intent(request: str, previous_spec: dict[str, Any] | None = None) -> VisualIntent:
    text = str(request or "").strip()
    if not text or _NEGATIVE_VISUAL.search(text) or _NON_VISUAL_CONTEXT.search(text):
        return VisualIntent(False, reason="negative or empty visual intent")
    if _ANIMATE_ONLY.match(text):
        return VisualIntent(
            previous_spec is not None,
            family=str(previous_spec.get("family")) if previous_spec else None,
            renderer=str(previous_spec.get("renderer")) if previous_spec else None,
            animate_previous=previous_spec is not None,
            reason="anaphoric animation" if previous_spec else "no prior visualization artifact",
        )
    # Learners often paste a numbered Markdown exercise whose visual verb appears on a later
    # line after a bold title. The negative/non-visual guards above already reject semantic
    # false positives, so an allow-listed visual word anywhere in the bounded request is a
    # genuine signal; it need not be the first token in the whole message.
    visual_signal = bool(
        _VISUAL_WORDS.search(text)
        or _VISUAL_REQUEST_PHRASE.search(text)
        or _DIRECT_VISUAL_REQUEST.search(text)
    )
    for pattern, family, renderer in _FAMILY_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            explicit = visual_signal or bool(
                _AMBIGUOUS_VISUAL_VERB.search(text)
                or re.search(
                    r"\b(?:allow|approximate|display|place|update|operate|simultaneously)\b",
                    text,
                    re.IGNORECASE,
                )
            )
            if explicit:
                return VisualIntent(True, family, renderer, reason="topic family")
    relationship = _relationship_from_request(text)
    if relationship is not None and (
        visual_signal or _AMBIGUOUS_VISUAL_VERB.search(text) or _EQUATION_SIGNAL.search(text)
    ):
        return VisualIntent(True, "mathematical_surface", "three", reason="explicit relationship")
    return VisualIntent(visual_signal, "concept_process", "svg", reason="generic visual request")


_CONTROL_PRESETS: dict[tuple[str, str], tuple[float, float, float, float]] = {
    ("pythagoras", "a"): (3, 1, 10, 0.1),
    ("pythagoras", "b"): (4, 1, 10, 0.1),
    ("unit_circle", "angle"): (45, 0, 360, 1),
    ("quadratic", "a"): (1, -4, 4, 0.1),
    ("quadratic", "b"): (0, -8, 8, 0.1),
    ("quadratic", "c"): (0, -8, 8, 0.1),
    ("line_intersection", "m1"): (1, -5, 5, 0.1),
    ("line_intersection", "c1"): (0, -8, 8, 0.1),
    ("line_intersection", "m2"): (-1, -5, 5, 0.1),
    ("line_intersection", "c2"): (2, -8, 8, 0.1),
    ("triangle_angles", "vertex_a"): (60, 10, 160, 1),
    ("triangle_angles", "vertex_b"): (60, 10, 160, 1),
    ("triangle_angles", "vertex_c"): (60, 10, 160, 1),
    ("derivative_tangent", "x"): (1, -3, 3, 0.05),
    ("riemann_sum", "rectangles"): (8, 1, 40, 1),
    ("projectile", "angle"): (45, 5, 85, 1),
    ("projectile", "speed"): (20, 2, 60, 1),
    ("inclined_plane", "incline"): (30, 5, 60, 1),
    ("spring_mass", "spring_constant"): (12, 1, 30, 0.5),
    ("spring_mass", "mass"): (2, 0.25, 8, 0.25),
    ("spring_mass", "displacement"): (1, -3, 3, 0.1),
    ("elastic_collision", "mass_1"): (2, 0.5, 8, 0.5),
    ("elastic_collision", "velocity_1"): (3, -8, 8, 0.5),
    ("elastic_collision", "mass_2"): (3, 0.5, 8, 0.5),
    ("elastic_collision", "velocity_2"): (-1, -8, 8, 0.5),
    ("pendulum", "length"): (1, 0.2, 5, 0.05),
    ("pendulum", "angle"): (20, 1, 80, 1),
    ("double_pendulum", "angle_1"): (75, 20, 160, 1),
    ("double_pendulum", "angle_2"): (75.5, 20, 160, 0.1),
    ("travelling_wave", "amplitude"): (1, 0.1, 3, 0.1),
    ("travelling_wave", "wavelength"): (2, 0.4, 8, 0.1),
    ("travelling_wave", "frequency"): (1, 0.1, 5, 0.1),
    ("wave_interference", "phase"): (0, 0, 6.283, 0.05),
    ("rc_circuit", "resistance"): (4, 0.5, 20, 0.5),
    ("rc_circuit", "capacitance"): (2, 0.2, 10, 0.2),
    ("ideal_gas", "pressure"): (2, 0.5, 8, 0.1),
    ("ideal_gas", "volume"): (2, 0.5, 8, 0.1),
    ("ideal_gas", "temperature"): (4, 0.5, 12, 0.1),
    ("atom", "atomic_number"): (6, 1, 18, 1),
    ("ohms_law_circuit", "voltage"): (12, 0, 24, 0.5),
    ("ohms_law_circuit", "resistance"): (6, 0.5, 24, 0.5),
    ("refraction", "incident_angle"): (35, 0, 80, 1),
    ("titration", "titrant_volume"): (25, 0, 50, 0.5),
    ("sampling_aliasing", "signal_frequency"): (4, 0.5, 20, 0.5),
    ("sampling_aliasing", "sample_frequency"): (12, 1, 40, 1),
    ("logistic_map", "growth_rate"): (3.72, 0, 4, 0.01),
    ("logistic_map", "initial_value"): (0.21, 0.01, 0.99, 0.01),
    ("fourier_series", "terms"): (5, 1, 15, 1),
    ("pwm", "duty_cycle"): (0.45, 0.05, 0.95, 0.05),
    ("convolution", "shift"): (0, -4, 4, 0.1),
    ("impulse_response", "shift"): (0, -4, 4, 0.1),
    ("vector_field", "probe_x"): (1, -3, 3, 0.1),
    ("vector_field", "probe_y"): (1, -3, 3, 0.1),
    ("circular_motion", "angular_velocity"): (1, -4, 4, 0.1),
    ("binary_search_tree", "insert"): (6, 1, 15, 1),
    ("electrochemical_cell", "zinc_concentration"): (1, 0.1, 3, 0.1),
    ("electrochemical_cell", "copper_concentration"): (1, 0.1, 3, 0.1),
    ("phase_diagram", "temperature"): (0.55, 0, 1, 0.01),
    ("phase_diagram", "pressure"): (0.55, 0, 1, 0.01),
    ("equilibrium_shift", "pressure"): (1, 0.5, 5, 0.1),
    ("equilibrium_shift", "temperature"): (450, 250, 800, 10),
    ("hash_table", "key"): (17, 0, 99, 1),
    ("virtual_memory", "address"): (37, 0, 255, 1),
    ("kalman_filter", "noise"): (1, 0.1, 5, 0.1),
    ("kalman_filter", "process_noise"): (0.08, 0.01, 1, 0.01),
    ("converging_lens", "object_distance"): (2.5, 1.2, 5, 0.1),
    ("robot_arm", "target_x"): (2.5, -2.5, 2.5, 0.1),
    ("robot_arm", "target_y"): (1.5, -2.5, 2.5, 0.1),
    ("electric_field_lines", "charge_1"): (-1, -3, -0.2, 0.1),
    ("electric_field_lines", "charge_2"): (1, 0.2, 3, 0.1),
    ("electric_field_vectors", "test_x"): (0, -3, 3, 0.1),
    ("electric_field_vectors", "test_y"): (1.5, -3, 3, 0.1),
    ("electric_field_vectors", "positive_charge_x"): (-1, -3, -0.2, 0.1),
    ("electric_field_vectors", "negative_charge_x"): (1, 0.2, 3, 0.1),
    ("kinetics", "order"): (1, 0, 2, 1),
    ("kinetics", "rate_constant"): (0.35, 0.05, 1, 0.05),
    ("bode_plot", "cutoff"): (1, 0.1, 10, 0.1),
    ("blackbody", "temperature"): (2.2, 0.8, 3.5, 0.1),
    ("beam_bending", "load_position"): (5, 0.5, 9.5, 0.25),
    ("fluid_flow", "speed"): (1, 0.2, 3, 0.1),
    ("uncertainty_propagation", "mass_sigma"): (0.4, 0.02, 1, 0.02),
    ("uncertainty_propagation", "volume_sigma"): (0.18, 0.01, 0.8, 0.01),
    ("uncertainty_propagation", "samples"): (160, 40, 400, 20),
    ("energy_sankey", "efficiency"): (0.65, 0.05, 0.95, 0.05),
    ("double_slit", "slit_separation"): (1.2, 0.4, 2.4, 0.1),
    ("double_slit", "wavelength"): (0.5, 0.1, 1.5, 0.05),
    ("decision_boundary", "epoch"): (20, 1, 40, 1),
    ("decision_boundary", "learning_rate"): (0.2, 0.05, 0.5, 0.01),
    ("robot_forward_kinematics", "joint_1"): (25, -180, 180, 1),
    ("robot_forward_kinematics", "joint_2"): (-35, -180, 180, 1),
    ("robot_forward_kinematics", "joint_3"): (55, -180, 180, 1),
    ("vector_field_3d", "point_x"): (1, -2, 2, 1),
    ("vector_field_3d", "point_y"): (1, -2, 2, 1),
    ("vector_field_3d", "point_z"): (1, -2, 2, 1),
    ("lorenz_attractor", "sigma"): (10, 5, 20, 0.5),
    ("lorenz_attractor", "rho"): (28, 10, 40, 0.5),
    ("lorenz_attractor", "beta"): (2.667, 1, 4, 0.05),
    ("electromagnetic_wave", "amplitude"): (1, 0.2, 2, 0.1),
    ("electromagnetic_wave", "wavelength"): (3, 1, 6, 0.1),
    ("robot_localization", "odometry_noise"): (0.25, 0, 1, 0.05),
    ("robot_localization", "sensor_noise"): (0.2, 0, 1, 0.05),
    ("robot_localization", "step"): (30, 0, 60, 1),
    ("gradient_descent", "learning_rate"): (0.18, 0.02, 0.5, 0.01),
    ("gradient_descent", "step"): (8, 0, 16, 1),
}


def _control(control_id: str, index: int, family: str) -> dict[str, Any]:
    label = control_id.replace("_", " ").replace("m1", "slope 1").replace("m2", "slope 2")
    if control_id in {
        "mode",
        "load",
        "molecule",
        "algorithm",
        "operation",
        "bond_model",
        "elbow_mode",
        "orbital",
        "catalyst",
        "medium",
        "current_direction",
        "organelle",
        "segment",
        "transport_mode",
        "matrix",
    }:
        return {
            "id": control_id,
            "label": label.title(),
            "type": "select",
            "value": "default",
            "options": ["default", "alternate"],
        }
    if control_id in {"switch", "pedestrian_request"}:
        return {"id": control_id, "label": "Switch", "type": "button", "value": 0}
    if control_id in {"playback", "step"}:
        preset = _CONTROL_PRESETS.get((family, control_id))
        value, minimum, maximum, step = preset or (0, 0, 4, 1)
        return {
            "id": control_id,
            "label": label.title(),
            "type": "step",
            "value": value,
            "min": minimum,
            "max": maximum,
            "step": step,
        }
    value, minimum, maximum, step = _CONTROL_PRESETS.get(
        (family, control_id), (1 + index, 0, 10, 0.1)
    )
    return {
        "id": control_id,
        "label": label.title(),
        "type": "range",
        "value": value,
        "min": minimum,
        "max": maximum,
        "step": step,
    }


def _number_list_from_request(request: str, *, maximum: int = 15) -> list[float] | None:
    for match in re.finditer(r"\[([0-9eE+.,\-\s]+)\]", request):
        pieces = [piece.strip() for piece in match.group(1).split(",")]
        if not pieces or any(not piece for piece in pieces):
            continue
        try:
            values = [float(piece) for piece in pieces]
        except ValueError:
            continue
        if 1 <= len(values) <= maximum and all(math.isfinite(value) for value in values):
            return values
    return None


def _requested_target(request: str) -> float | None:
    match = re.search(
        r"\btarget(?:\s+value)?(?:\s*(?:=|is|of|for))?\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\b",
        request,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def _controls_for_request(request: str, family: str) -> list[dict[str, Any]]:
    aliases: dict[str, tuple[str, ...]] = {
        "pythagoras": ("a", "b"),
        "unit_circle": ("angle",),
        "basic_geometry": (),
        "quadratic": ("a", "b", "c"),
        "line_intersection": ("m1", "c1", "m2", "c2"),
        "triangle_angles": ("vertex_a", "vertex_b", "vertex_c"),
        "derivative_tangent": ("x",),
        "riemann_sum": ("rectangles",),
        "gradient_field": ("point_x", "point_y"),
        "plane_intersection": ("orbit",),
        "linear_transform": ("matrix",),
        "projectile": ("angle", "speed"),
        "inclined_plane": ("incline",),
        "spring_mass": ("spring_constant", "mass"),
        "elastic_collision": ("mass_1", "velocity_1", "mass_2", "velocity_2"),
        "pendulum": ("length", "angle"),
        "travelling_wave": ("amplitude", "wavelength", "frequency"),
        "wave_interference": ("phase",),
        "circular_motion": ("angular_velocity",),
        "harmonic_motion": ("spring_constant", "mass"),
        "double_pendulum": ("angle_1", "angle_2"),
        "ohms_law_circuit": ("voltage", "resistance", "switch"),
        "series_parallel_circuit": ("r1", "r2", "mode"),
        "electric_field_lines": ("charge_1", "charge_2"),
        "electric_field_vectors": ("test_x", "test_y"),
        "magnetic_field_wire": ("current_direction",),
        "rc_circuit": ("mode", "resistance", "capacitance"),
        "rlc_circuit": ("resistance", "inductance", "capacitance"),
        "ac_phase": ("load",),
        "converging_lens": ("object_distance",),
        "refraction": ("incident_angle", "medium"),
        "ideal_gas": ("pressure", "volume", "temperature"),
        "carnot_cycle": ("playback",),
        "atom": ("atomic_number",),
        "ionic_bond": ("playback",),
        "molecular_geometry": ("molecule",),
        "reaction_profile": ("catalyst",),
        "titration": ("titrant_volume",),
        "molecular_orbitals": ("orbital",),
        "animal_cell": ("organelle",),
        "mitosis": ("step",),
        "circulation": ("playback",),
        "action_potential": ("time",),
        "binary_search": ("target", "step"),
        "binary_search_tree": ("insert", "step"),
        "dijkstra": ("source", "destination", "step"),
        "stack_queue": ("operation", "step"),
        "cpu_memory": ("step",),
        "sampling_aliasing": ("signal_frequency", "sample_frequency"),
        "differential_drive": ("left_velocity", "right_velocity"),
        "neural_network": ("weight", "step"),
        "complex_mapping": ("point_angle", "point_radius"),
        "polar_plot": ("theta", "playback"),
        "fourier_series": ("terms",),
        "logistic_map": ("growth_rate", "initial_value"),
        "lagrange_multiplier": ("constraint_offset",),
        "parametric_surface": ("path_position", "playback"),
        "vector_field": ("probe_x", "probe_y"),
        "convolution": ("shift",),
        "kepler_orbit": ("eccentricity", "true_anomaly", "playback"),
        "coupled_oscillators": ("mode", "playback"),
        "standing_wave": ("harmonic",),
        "doppler": ("source_speed", "playback"),
        "double_slit": ("slit_separation", "wavelength"),
        "lorentz_force": ("charge", "field", "speed", "playback"),
        "blackbody": ("temperature",),
        "entropy_cycle": ("step",),
        "benzene": ("bond_model",),
        "electrochemical_cell": ("zinc_concentration", "copper_concentration"),
        "kinetics": ("order", "rate_constant"),
        "phase_diagram": ("temperature", "pressure"),
        "equilibrium_shift": ("pressure", "temperature"),
        "enzyme_kinetics": ("substrate", "inhibitor"),
        "dna_replication": ("step",),
        "nephron": ("segment",),
        "predator_prey": ("prey_growth", "predation", "playback"),
        "membrane_transport": ("transport_mode",),
        # A manual step control and the Play transport drive the same ordered
        # merge events.  A second playback stepper would be a duplicate state
        # control whose first change can leave the scene unchanged.
        "merge_sort": ("step",),
        "hash_table": ("key", "operation", "step"),
        "graph_traversal": ("algorithm", "step"),
        "heap": ("operation", "value", "step"),
        "recursion_stack": ("step",),
        "virtual_memory": ("address", "step"),
        "impulse_response": ("shift", "step"),
        "bode_plot": ("cutoff",),
        "nyquist": ("gain",),
        "pid_response": ("kp", "ki", "kd"),
        "pwm": ("duty_cycle",),
        "spectrogram": ("sweep_rate", "playback"),
        "robot_arm": ("target_x", "target_y", "elbow_mode"),
        "kalman_filter": ("noise", "step"),
        "truss": ("load",),
        "beam_bending": ("load_position",),
        "fluid_flow": ("speed",),
        "heat_diffusion": ("time", "playback"),
        "state_machine": ("pedestrian_request", "step"),
        "decision_boundary": ("epoch", "learning_rate"),
        "backprop_graph": ("w", "x", "b", "step"),
        "energy_sankey": ("efficiency",),
        "uncertainty_propagation": ("mass_sigma", "volume_sigma", "samples"),
        "vector_addition": (),
        "binary_representation": (),
        "robot_forward_kinematics": ("joint_1", "joint_2", "joint_3"),
        "vector_field_3d": ("point_x", "point_y", "point_z"),
        "lorenz_attractor": ("sigma", "rho", "beta"),
        "electromagnetic_wave": ("amplitude", "wavelength"),
        "robot_localization": ("odometry_noise", "sensor_noise", "step"),
        "gradient_descent": ("learning_rate", "step"),
        "gradient_linked": ("point_x", "point_y"),
    }
    names = aliases.get(family)
    if family == "spring_mass" and re.search(
        r"displacement|\bx\b.{0,20}change", request, re.IGNORECASE
    ):
        names = ("spring_constant", "displacement")
    if family == "electric_field_vectors" and re.search(
        r"(?:either charge|(?:positive|negative|source) charge.{0,30}move|move.{0,30}(?:positive|negative|source) charge)",
        request,
        re.IGNORECASE,
    ):
        names = ("positive_charge_x", "negative_charge_x", "test_x", "test_y")
    if family == "kalman_filter" and re.search(r"process noise", request, re.IGNORECASE):
        names = ("noise", "process_noise", "step")
    if names is None:
        requested = re.findall(
            r"\b(?:change|adjust|vary|move|select|toggle)\s+(?:the\s+)?([A-Za-z][A-Za-z _-]{0,24})",
            request,
            re.IGNORECASE,
        )
        names = tuple(
            re.sub(r"\W+", "_", item.strip().lower()).strip("_") for item in requested[:2]
        ) or ("step",)
    controls = [
        _control(name, index, family) for index, name in enumerate(names[:MAX_PARAMETER_CONTROLS])
    ]
    if family == "dijkstra":
        controls = [
            {
                "id": "source",
                "label": "Source node",
                "type": "select",
                "value": "A",
                "options": ["A", "B", "C", "D", "E", "F"],
            },
            {
                "id": "destination",
                "label": "Destination node",
                "type": "select",
                "value": "F",
                "options": ["A", "B", "C", "D", "E", "F"],
            },
            {
                "id": "step",
                "label": "Algorithm step",
                "type": "step",
                "value": 0,
                "min": 0,
                "max": 6,
                "step": 1,
            },
        ]
    if family == "linear_transform":
        controls = [
            {
                "id": "matrix",
                "label": "Matrix",
                "type": "select",
                "value": "identity",
                "options": ["identity", "shear", "scale"],
            }
        ]
    if family == "truss":
        controls = [
            {
                "id": "load",
                "label": "Downward load (kN)",
                "type": "range",
                "value": 50,
                "min": 10,
                "max": 100,
                "step": 5,
            }
        ]
    if family == "molecular_geometry" and controls:
        lowered = request.lower()
        if any(name in lowered for name in ("ch4", "ch₄", "nh3", "nh₃", "h2o", "h₂o")):
            options = ["ch4", "nh3", "h2o"]
        elif any(name in lowered for name in ("sf6", "sf₆", "brf5", "brf₅")):
            options = ["sf6", "brf5"]
        else:
            options = ["ch4", "nh3", "h2o", "sf6", "brf5"]
        controls[0] = {
            "id": "molecule",
            "label": "Molecule",
            "type": "select",
            "value": options[0],
            "options": options,
        }
    if family == "benzene" and controls:
        controls[0] = {
            "id": "bond_model",
            "label": "Bond model",
            "type": "select",
            "value": "localized",
            "options": ["localized", "delocalized"],
        }
    if family == "ac_phase" and controls:
        controls[0] = {
            "id": "load",
            "label": "AC load",
            "type": "select",
            "value": "resistive",
            "options": ["resistive", "capacitive", "inductive"],
        }
    if family == "rc_circuit" and controls:
        controls[0] = {
            "id": "mode",
            "label": "RC mode",
            "type": "select",
            "value": "charging",
            "options": ["charging", "discharging"],
        }
    if family == "series_parallel_circuit" and controls:
        controls[2] = {
            "id": "mode",
            "label": "Circuit mode",
            "type": "select",
            "value": "series",
            "options": ["series", "parallel"],
        }
    if family == "binary_search" and controls:
        items = _number_list_from_request(request) or [1, 3, 5, 7, 9, 11, 13]
        requested_target = _requested_target(request)
        default_target = requested_target if requested_target is not None else 11
        option_values = [*items]
        if default_target not in option_values:
            option_values.append(default_target)
        absent = max(items) + 1
        if absent not in option_values:
            option_values.append(absent)

        def display(value: float) -> str:
            return str(int(value)) if float(value).is_integer() else str(value)

        controls[0] = {
            "id": "target",
            "label": "Target value",
            "type": "select",
            "value": display(default_target),
            "options": [display(value) for value in option_values],
        }
    if family == "animal_cell" and controls:
        controls[0] = {
            "id": "organelle",
            "label": "Organelle",
            "type": "select",
            "value": "nucleus",
            "options": [
                "nucleus",
                "mitochondrion",
                "ribosome",
                "rough_er",
                "golgi",
                "lysosome",
            ],
        }
    if family == "magnetic_field_wire" and controls:
        controls[0] = {
            "id": "current_direction",
            "label": "Current direction",
            "type": "select",
            "value": "forward",
            "options": ["forward", "reverse"],
        }
    if family == "reaction_profile" and controls:
        controls[0] = {
            "id": "catalyst",
            "label": "Catalyst",
            "type": "select",
            "value": "off",
            "options": ["off", "on"],
        }
    if family == "molecular_orbitals" and controls:
        controls[0] = {
            "id": "orbital",
            "label": "Molecular orbital",
            "type": "select",
            "value": "bonding",
            "options": ["bonding", "antibonding"],
        }
    if family == "stack_queue" and controls:
        controls[0] = {
            "id": "operation",
            "label": "Operation",
            "type": "select",
            "value": "add",
            "options": ["add", "remove"],
        }
    if family == "refraction" and controls:
        controls[1] = {
            "id": "medium",
            "label": "Second medium",
            "type": "select",
            "value": "glass",
            "options": ["glass", "water"],
        }
    if family == "nephron" and controls:
        controls[0] = {
            "id": "segment",
            "label": "Nephron segment",
            "type": "select",
            "value": "proximal",
            "options": ["proximal", "descending_loop", "ascending_loop", "distal", "collecting"],
        }
    if family == "membrane_transport" and controls:
        controls[0] = {
            "id": "transport_mode",
            "label": "Transport mode",
            "type": "select",
            "value": "diffusion",
            "options": ["diffusion", "facilitated", "active"],
        }
    if family == "hash_table" and controls:
        controls[1] = {
            "id": "operation",
            "label": "Operation",
            "type": "select",
            "value": "insert",
            "options": ["insert", "lookup", "delete"],
        }
        controls[2]["max"] = 6
    if family == "graph_traversal" and controls:
        controls[0] = {
            "id": "algorithm",
            "label": "Traversal",
            "type": "select",
            "value": "bfs",
            "options": ["bfs", "dfs"],
        }
    if family == "merge_sort":
        for control in controls:
            if control["id"] in {"step", "playback"}:
                control["max"] = 20
    if family == "kalman_filter":
        for index, control in enumerate(controls):
            if control["id"] == "step":
                controls[index] = {
                    "id": "step",
                    "label": "Predict / update step",
                    "type": "step",
                    "value": 0,
                    "min": 0,
                    "max": 20,
                    "step": 1,
                }
                break
    if family == "heap" and controls:
        controls[0] = {
            "id": "operation",
            "label": "Heap operation",
            "type": "select",
            "value": "insert",
            "options": ["insert", "extract_min"],
        }
    if family == "recursion_stack" and controls:
        match = re.search(r"factorial\s*\(\s*(\d+)\s*\)", request, re.IGNORECASE)
        maximum = min(8, max(1, int(match.group(1)))) if match else 5
        controls[0]["max"] = 2 * maximum
    return controls


def _basic_geometry_layers(request: str) -> list[dict[str, Any]]:
    """Build a small, reusable Euclidean construction from an explicit shape noun."""
    text = str(request or "").casefold()
    layers: list[dict[str, Any]] = [{"type": "axes", "x_label": "x", "y_label": "y", "grid": True}]
    if "triangle" in text:
        points = [[-2.5, -1.5], [2.5, -1.5], [0, 2.5], [-2.5, -1.5]]
        label = "triangle boundary"
    elif "square" in text:
        points = [[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]]
        label = "square boundary"
    elif "rectangle" in text:
        points = [[-3, -1.75], [3, -1.75], [3, 1.75], [-3, 1.75], [-3, -1.75]]
        label = "rectangle boundary"
    elif "polygon" in text:
        points = [
            [
                2.6 * math.cos(math.pi / 2 + 2 * math.pi * index / 5),
                2.6 * math.sin(math.pi / 2 + 2 * math.pi * index / 5),
            ]
            for index in range(5)
        ]
        points.append(points[0])
        label = "regular pentagon boundary"
    else:
        points = [
            [3 * math.cos(2 * math.pi * index / 96), 3 * math.sin(2 * math.pi * index / 96)]
            for index in range(97)
        ]
        label = "circle x² + y² = 9"
    layers.append({"type": "polyline", "label": label, "points": points, "color": "orange"})
    if "circle" in text or not any(
        noun in text for noun in ("triangle", "square", "rectangle", "polygon")
    ):
        layers.append(
            {
                "type": "polyline",
                "label": "radius r = 3",
                "points": [[0, 0], [3, 0]],
                "color": "teal",
            }
        )
    return layers


def _classifier_state(epochs: int, learning_rate: float) -> dict[str, Any]:
    samples = [
        ([-3 + (index % 6) * 0.45, -1.8 + (index // 6) * 0.45], 0.0) for index in range(18)
    ] + [([0.7 + (index % 6) * 0.45, 0.25 + (index // 6) * 0.45], 1.0) for index in range(18)]
    hidden_weights = [[0.32, -0.28], [-0.18, 0.38]]
    hidden_biases = [0.0, 0.0]
    output_weights = [0.45, -0.4]
    output_bias = 0.0

    def predict(point: list[float]) -> tuple[list[float], float]:
        hidden = [
            math.tanh(sum(weight * value for weight, value in zip(weights, point)) + bias)
            for weights, bias in zip(hidden_weights, hidden_biases)
        ]
        logit = sum(weight * value for weight, value in zip(output_weights, hidden)) + output_bias
        probability = 1 / (1 + math.exp(-max(-40, min(40, logit))))
        return hidden, probability

    losses: list[list[float]] = []
    for epoch in range(max(0, epochs) + 1):
        probabilities = [predict(point)[1] for point, _label in samples]
        loss = -sum(
            label * math.log(max(1e-9, probability))
            + (1 - label) * math.log(max(1e-9, 1 - probability))
            for probability, (_point, label) in zip(probabilities, samples)
        ) / len(samples)
        losses.append([float(epoch), loss])
        if epoch == epochs:
            break
        grad_hidden_weights = [[0.0, 0.0], [0.0, 0.0]]
        grad_hidden_biases = [0.0, 0.0]
        grad_output_weights = [0.0, 0.0]
        grad_output_bias = 0.0
        for point, label in samples:
            hidden, probability = predict(point)
            delta_output = probability - label
            for hidden_index in range(2):
                grad_output_weights[hidden_index] += delta_output * hidden[hidden_index]
                delta_hidden = (
                    delta_output * output_weights[hidden_index] * (1 - hidden[hidden_index] ** 2)
                )
                grad_hidden_biases[hidden_index] += delta_hidden
                for input_index in range(2):
                    grad_hidden_weights[hidden_index][input_index] += (
                        delta_hidden * point[input_index]
                    )
            grad_output_bias += delta_output
        scale = learning_rate / len(samples)
        for hidden_index in range(2):
            output_weights[hidden_index] -= scale * grad_output_weights[hidden_index]
            hidden_biases[hidden_index] -= scale * grad_hidden_biases[hidden_index]
            for input_index in range(2):
                hidden_weights[hidden_index][input_index] -= (
                    scale * grad_hidden_weights[hidden_index][input_index]
                )
        output_bias -= scale * grad_output_bias
    return {"samples": samples, "loss": losses, "predict": predict}


def _plot_layers(family: str) -> list[dict[str, Any]]:
    axis_labels = {
        "projectile": ("horizontal distance (m)", "height (m)"),
        "ideal_gas": ("volume V", "pressure P"),
        "reaction_profile": ("reaction progress", "energy"),
        "titration": ("titrant volume", "pH"),
        "action_potential": ("time (ms)", "membrane voltage (mV)"),
        "kinetics": ("time", "concentration / linearized value"),
        "bode_plot": ("log₁₀(ω/ωc)", "magnitude (dB) / phase (°)"),
        "beam_bending": ("beam position", "shear / moment / deflection"),
        "kalman_filter": ("time step", "position"),
        "fluid_flow": ("x/a", "y/a"),
        "uncertainty_propagation": ("volume / density bin", "mass / frequency"),
        "sampling_aliasing": ("time (s)", "amplitude"),
        "spectrogram": ("time (s)", "frequency (Hz)"),
        "heat_diffusion": ("position", "temperature field"),
        "decision_boundary": ("feature 1", "feature 2"),
        "vector_field": ("x", "y"),
    }
    x_label, y_label = axis_labels.get(family, ("x", "y"))
    layers: list[dict[str, Any]] = [
        {"type": "axes", "x_label": x_label, "y_label": y_label, "grid": True}
    ]

    def add(label: str, points: list[list[float]], color: str = "orange") -> None:
        layers.append({"type": "polyline", "label": label, "points": points, "color": color})

    def panel(
        panel_id: str,
        title: str,
        x_label: str,
        y_label: str,
        *members: str,
    ) -> None:
        layers.append(
            {
                "type": "panel",
                "id": panel_id,
                "title": title,
                "x_label": x_label,
                "y_label": y_label,
                "members": list(members),
            }
        )

    xs = [-4 + index / 10 for index in range(81)]
    turns = [index * math.pi / 40 for index in range(81)]
    if family == "pythagoras":
        add("right triangle", [[0, 0], [3, 0], [3, 4], [0, 0]], "gold")
        add("square on a", [[0, 0], [3, 0], [3, -3], [0, -3], [0, 0]], "teal")
        add("square on b", [[3, 0], [3, 4], [7, 4], [7, 0], [3, 0]], "orange")
        add("square on c", [[0, 0], [3, 4], [-1, 7], [-4, 3], [0, 0]], "purple")
    elif family == "unit_circle":
        add("x² + y² = 1", [[math.cos(t), math.sin(t)] for t in turns])
        point = math.sqrt(0.5)
        add("radius to θ", [[0, 0], [point, point]], "purple")
        add("cos θ projection", [[0, 0], [point, 0], [point, point]], "teal")
    elif family == "vector_addition":
        layers.append(
            {
                "type": "vector_field",
                "vectors": [[0, 0, 3, 2], [3, 2, 1, 4], [0, 0, 4, 6]],
                "label": "a=(3,2), translated b=(1,4), resultant a+b=(4,6)",
                "color": "purple",
            }
        )
        add("head-to-tail construction", [[0, 0], [3, 2], [4, 6]], "teal")
        add("parallelogram completion", [[0, 0], [1, 4], [4, 6]], "gold")
    elif family in {"gradient_linked", "gradient_descent"}:
        surface_labels: list[str] = []
        contour_labels: list[str] = []
        for row in (-2, -1, 0, 1, 2):
            label = f"projected 3D surface row y={row}"
            surface_labels.append(label)
            add(
                label,
                [
                    [
                        x + 0.35 * row - 4.5,
                        0.18 * (x * x + (2 if family == "gradient_descent" else 1) * row * row)
                        + 0.35 * row,
                    ]
                    for x in xs
                ],
                "teal",
            )
        for contour in (0.8, 1.5, 2.3):
            label = f"2D contour f={contour:.1f}"
            contour_labels.append(label)
            vertical_scale = math.sqrt(2) if family == "gradient_descent" else 1
            add(
                label,
                [
                    [3.2 + contour * math.cos(t), contour * math.sin(t) / vertical_scale]
                    for t in turns
                ],
                "orange",
            )
        trajectory = []
        x_value, y_value = 2.4, 1.8
        for _step in range(17):
            trajectory.append([3.2 + x_value, y_value])
            x_value *= 0.64
            y_value *= 0.36 if family == "gradient_descent" else 0.58
        if family == "gradient_descent":
            surface_trajectory_label = "gradient-descent trajectory on projected surface"
            contour_trajectory_label = "gradient-descent trajectory on contour map"
            add(
                surface_trajectory_label,
                [
                    [
                        x_value + 0.35 * y_value - 4.5,
                        0.18 * (x_value * x_value + 2 * y_value * y_value) + 0.35 * y_value,
                    ]
                    for x_value, y_value in [
                        (2.4 * 0.64**step, 1.8 * 0.36**step) for step in range(17)
                    ]
                ],
                "gold",
            )
            add(contour_trajectory_label, trajectory, "purple")
            surface_members = [*surface_labels, surface_trajectory_label]
            contour_members = [*contour_labels, contour_trajectory_label]
        else:
            surface_probe_label = "surface probe at selected point"
            contour_probe_label = "contour probe and gradient direction"
            add(surface_probe_label, [[-3.8, 0.53], [-3.79, 0.54]], "gold")
            add(contour_probe_label, [[4.2, 1.0], [5.8, 2.6]], "purple")
            surface_members = [*surface_labels, surface_probe_label]
            contour_members = [*contour_labels, contour_probe_label]
        panel("surface", "Projected 3D surface", "x", "height z", *surface_members)
        panel(
            "contour",
            "Linked 2D contour map",
            "x",
            "y",
            *contour_members,
        )
    elif family == "robot_localization":
        times = [index / 10 for index in range(61)]
        true_path = [[time - 3, 1.2 * math.sin(time)] for time in times]
        odometry = [
            [x + 0.08 * index / 10, y + 0.18 * math.sin(index * 1.7)]
            for index, (x, y) in enumerate(true_path)
        ]
        estimate = [
            [0.72 * truth[0] + 0.28 * noisy[0], 0.72 * truth[1] + 0.28 * noisy[1]]
            for truth, noisy in zip(true_path, odometry)
        ]
        add("true pose trajectory", true_path, "teal")
        add("noisy odometry trajectory", odometry, "orange")
        add("Kalman/particle estimated pose", estimate, "purple")
        current = estimate[30]
        add(
            "uncertainty ellipse",
            [[current[0] + 0.55 * math.cos(t), current[1] + 0.3 * math.sin(t)] for t in turns],
            "gold",
        )
        add("sensor observations to landmarks", [current, [-2.4, 2.3], current, [2.5, 2.1]], "blue")
        layers.append(
            {
                "type": "particles",
                "points": [
                    [
                        current[0] + 0.45 * math.cos(index * 2.399),
                        current[1] + 0.25 * math.sin(index * 2.399),
                    ]
                    for index in range(48)
                ],
                "label": "localization particles",
                "color": "purple",
            }
        )
    elif family == "line_intersection":
        add("line 1", [[x, x] for x in xs])
        add("line 2", [[x, -x + 2] for x in xs], "teal")
    elif family == "linear_transform":
        for coordinate in (-3, -2, -1, 0, 1, 2, 3):
            add(f"vertical x={coordinate}", [[coordinate, -3], [coordinate, 3]], "teal")
            add(f"horizontal y={coordinate}", [[-3, coordinate], [3, coordinate]], "orange")
        add("basis e₁", [[0, 0], [1, 0]], "gold")
        add("basis e₂", [[0, 0], [0, 1]], "purple")
        add("invariant-direction test v₁", [[0, 0], [2, 0]], "gold")
        add("invariant-direction test v₂", [[0, 0], [0, 2]], "purple")
    elif family == "projectile":
        angle = math.radians(45)
        speed = 20
        flight = 2 * speed * math.sin(angle) / 9.81
        path = [
            [
                speed * math.cos(angle) * flight * index / 80,
                speed * math.sin(angle) * flight * index / 80 - 4.905 * (flight * index / 80) ** 2,
            ]
            for index in range(81)
        ]
        add("projectile path", path)
        peak = max(path, key=lambda point: point[1])
        layers.append(
            {
                "type": "particles",
                "points": [peak, path[-1]],
                "label": "maximum height and range",
                "color": "gold",
            }
        )
        velocity_time = flight * 0.35
        velocity_origin = [
            speed * math.cos(angle) * velocity_time,
            speed * math.sin(angle) * velocity_time - 4.905 * velocity_time**2,
        ]
        layers.append(
            {
                "type": "arrow",
                "from": velocity_origin,
                "to": [
                    velocity_origin[0] + 0.4 * speed * math.cos(angle),
                    velocity_origin[1] + 0.4 * (speed * math.sin(angle) - 9.81 * velocity_time),
                ],
                "label": "instantaneous velocity",
                "color": "purple",
            }
        )
    elif family == "quadratic":
        add("y = x²", [[x, x * x] for x in xs])
        add("axis of symmetry x = 0", [[0, 0], [0, 16]], "teal")
        layers.append(
            {
                "type": "particles",
                "points": [[0, 0], [0, 0]],
                "label": "vertex",
                "color": "gold",
            }
        )
        layers.append(
            {
                "type": "particles",
                "points": [[0, 0], [0, 0]],
                "label": "real roots",
                "color": "purple",
            }
        )
    elif family == "circular_motion":
        add("circular path", [[3 * math.cos(t), 3 * math.sin(t)] for t in turns])
        add("position r", [[0, 0], [3, 0]], "teal")
        add("velocity v tangent", [[3, 0], [3, 1.8]], "gold")
        add("centripetal acceleration", [[3, 0], [1.2, 0]], "purple")
    elif family == "riemann_sum":
        samples = [index * 0.05 for index in range(81)]
        add("y = x²", [[x, x * x] for x in samples])
        rectangles: list[list[float]] = []
        for index in range(8):
            left = index * 0.5
            right = left + 0.5
            height = left * left
            rectangles.extend([[left, 0], [left, height], [right, height], [right, 0]])
        add("left Riemann rectangles", rectangles, "teal")
    elif family == "derivative_tangent":
        add("f(x) = x³ − 3x", [[x, x**3 - 3 * x] for x in xs])
        add("tangent at x = 1, slope 0", [[x, -2] for x in xs], "teal")
    elif family in {"gradient_field", "lagrange_multiplier", "vector_field"}:
        contour_data = (
            ((math.sqrt(0.5), "teal"), (1.5, "orange"), (2.5, "purple"))
            if family == "lagrange_multiplier"
            else ((1, "teal"), (2, "orange"), (3, "purple"))
        )
        for contour_index, (radius, color_name) in enumerate(contour_data):
            add(
                (
                    "tangent contour through constrained minimum"
                    if family == "lagrange_multiplier" and contour_index == 0
                    else f"contour r={radius}"
                ),
                [[radius * math.cos(t), radius * math.sin(t)] for t in turns],
                color_name,
            )
        if family in {"gradient_field", "vector_field"}:
            add("gradient at probe", [[1, 2], [1.9, 3.8]], "gold")
        if family == "lagrange_multiplier":
            add("constraint x+y=c", [[-3, 4], [4, -3]], "gold")
            add("∇f at constrained minimum", [[0.5, 0.5], [1.4, 1.4]], "teal")
            add("λ∇g parallel to ∇f", [[0.5, 0.5], [1.4, 1.4]], "purple")
            layers.append(
                {
                    "type": "particles",
                    "points": [[0.5, 0.5], [0.501, 0.501]],
                    "label": "constrained minimum (c/2,c/2)",
                    "color": "gold",
                }
            )
        if family == "vector_field":
            vectors = []
            for y in (-3, -1.5, 0, 1.5, 3):
                for x in (-3, -1.5, 0, 1.5, 3):
                    if x == 0 and y == 0:
                        continue
                    vectors.append([x, y, 0.18 * x, -0.18 * y])
            layers.append(
                {
                    "type": "vector_field",
                    "vectors": vectors,
                    "label": "F=(x,−y) saddle field",
                    "color": "purple",
                }
            )
    elif family == "sampling_aliasing":
        sample_x = [index / 200 for index in range(201)]
        add("continuous signal", [[x, math.sin(2 * math.pi * 4 * x)] for x in sample_x])
        add(
            "aliased reconstruction",
            [[x, math.sin(2 * math.pi * 4 * x)] for x in sample_x],
            "teal",
        )
        layers.append(
            {
                "type": "particles",
                "points": [
                    [index / 12, math.sin(2 * math.pi * 4 * index / 12)] for index in range(13)
                ],
                "label": "sample locations",
                "color": "purple",
            }
        )
    elif family == "travelling_wave":
        crest = (math.pi / 2 - 0.15) / math.pi
        add("transverse displacement", [[x, math.sin(math.pi * x + 0.15)] for x in xs])
        add("equilibrium position", [[-4, 0], [4, 0]], "teal")
        add("wavelength crest-to-crest", [[crest, 1.25], [crest + 2, 1.25]], "purple")
        layers.append(
            {
                "type": "particles",
                "points": [[crest, 1], [crest + 1, -1]],
                "label": "crest and trough",
                "color": "gold",
            }
        )
    elif family == "standing_wave":
        add(
            "standing wave fixed at x=−4 and x=4",
            [[x, math.sin(math.pi * (x + 4) / 8)] for x in xs],
        )
        layers.append(
            {
                "type": "particles",
                "points": [[-4, 0], [4, 0]],
                "label": "nodes including fixed endpoints",
                "color": "gold",
            }
        )
        layers.append(
            {
                "type": "particles",
                "points": [[0, 1], [0.001, 1]],
                "label": "antinodes",
                "color": "purple",
            }
        )
    elif family == "wave_interference":
        wave_a = [[x, math.sin(math.pi * x)] for x in xs]
        wave_b = [[x, math.sin(math.pi * x + math.pi / 2)] for x in xs]
        add("wave A", wave_a)
        add("wave B", wave_b, "teal")
        add(
            "resultant A + B",
            [[left[0], left[1] + right[1]] for left, right in zip(wave_a, wave_b)],
            "purple",
        )
    elif family == "ac_phase":
        add("voltage v(t)", [[x, math.sin(math.pi * x)] for x in xs])
        add("current i(t)", [[x, math.sin(math.pi * x)] for x in xs], "teal")
    elif family == "harmonic_motion":
        samples = [index * 2 * math.pi / 80 for index in range(81)]
        add("displacement versus time", [[time, math.cos(time)] for time in samples], "orange")
        add(
            "phase space velocity versus displacement",
            [[math.cos(time), -math.sin(time)] for time in samples],
            "teal",
        )
        add(
            "spring and moving mass",
            [[-4, 0], [-3.6, 0.4], [-3.2, -0.4], [-2.8, 0.4], [-2.4, -0.4], [-2, 0], [1, 0]],
            "purple",
        )
        layers.append(
            {
                "type": "particles",
                "points": [[1, 0], [1.001, 0]],
                "label": "current moving mass",
                "color": "gold",
            }
        )
    elif family == "rc_circuit":
        times = [index / 10 for index in range(81)]
        add("capacitor voltage Vc(t)", [[time, 1 - math.exp(-time / 1.6)] for time in times])
        add("circuit current I(t)", [[time, math.exp(-time / 1.6) / 4] for time in times], "teal")
        layers.extend(
            [
                {
                    "type": "node",
                    "id": "rc_source",
                    "x": 505,
                    "y": 80,
                    "width": 100,
                    "height": 44,
                    "label": "DC source",
                    "color": "orange",
                },
                {
                    "type": "node",
                    "id": "rc_resistor",
                    "x": 620,
                    "y": 180,
                    "width": 100,
                    "height": 44,
                    "label": "resistor R",
                    "color": "teal",
                },
                {
                    "type": "node",
                    "id": "rc_capacitor",
                    "x": 505,
                    "y": 290,
                    "width": 110,
                    "height": 44,
                    "label": "capacitor C",
                    "color": "purple",
                },
                {
                    "type": "link",
                    "from": "rc_source",
                    "to": "rc_resistor",
                    "arrow": True,
                    "label": "I(t)",
                },
                {
                    "type": "link",
                    "from": "rc_resistor",
                    "to": "rc_capacitor",
                    "arrow": True,
                    "label": "charge",
                },
                {
                    "type": "link",
                    "from": "rc_capacitor",
                    "to": "rc_source",
                    "arrow": True,
                    "label": "return",
                },
            ]
        )
    elif family == "rlc_circuit":
        add(
            "damped transient",
            [[x + 4, 1 - math.exp(-(x + 4) / 1.8) * math.cos(5 * (x + 4))] for x in xs],
        )
        layers.extend(
            [
                {
                    "type": "node",
                    "id": "rlc_source",
                    "x": 500,
                    "y": 72,
                    "width": 92,
                    "height": 42,
                    "label": "source",
                    "color": "orange",
                },
                {
                    "type": "node",
                    "id": "rlc_r",
                    "x": 625,
                    "y": 150,
                    "width": 88,
                    "height": 42,
                    "label": "R = 1 Ω",
                    "color": "teal",
                },
                {
                    "type": "node",
                    "id": "rlc_l",
                    "x": 625,
                    "y": 265,
                    "width": 88,
                    "height": 42,
                    "label": "L = 2 H",
                    "color": "purple",
                },
                {
                    "type": "node",
                    "id": "rlc_c",
                    "x": 500,
                    "y": 345,
                    "width": 88,
                    "height": 42,
                    "label": "C = 3 F",
                    "color": "gold",
                },
                {
                    "type": "link",
                    "from": "rlc_source",
                    "to": "rlc_r",
                    "arrow": True,
                    "label": "i(t)",
                },
                {"type": "link", "from": "rlc_r", "to": "rlc_l", "arrow": True, "label": "series"},
                {"type": "link", "from": "rlc_l", "to": "rlc_c", "arrow": True, "label": "series"},
                {
                    "type": "link",
                    "from": "rlc_c",
                    "to": "rlc_source",
                    "arrow": True,
                    "label": "return",
                },
            ]
        )
    elif family == "ideal_gas":
        add(
            "isotherm PV = nRT",
            [[value, 4 / value] for value in [0.5 + i * 0.05 for i in range(80)]],
        )
        add("selected pressure", [[0.5, 2], [4.5, 2]], "teal")
        add("selected volume", [[2, 0.5], [2, 8]], "purple")
        layers.append(
            {
                "type": "particles",
                "points": [[2, 2], [2.001, 2]],
                "label": "consistent state P·V=T",
                "color": "gold",
            }
        )
    elif family == "carnot_cycle":
        add("isothermal expansion hot", [[1, 4], [3, 2.5]], "orange")
        add("adiabatic expansion", [[3, 2.5], [4, 1]], "teal")
        add("isothermal compression cold", [[4, 1], [1.5, 1.8]], "purple")
        add("adiabatic compression", [[1.5, 1.8], [1, 4]], "gold")
        add("current thermodynamic state", [[1, 4], [1.12, 4.12]], "gold")
    elif family == "entropy_cycle":
        pv_processes = (
            ("P–V hot isothermal expansion", [[1, 4], [1.6, 3.5], [2.3, 3.0], [3, 2.5]], "orange"),
            ("P–V adiabatic expansion", [[3, 2.5], [3.45, 1.8], [4, 1]], "teal"),
            (
                "P–V cold isothermal compression",
                [[4, 1], [3, 1.2], [2.2, 1.5], [1.5, 1.8]],
                "purple",
            ),
            ("P–V adiabatic compression", [[1.5, 1.8], [1.2, 2.7], [1, 4]], "gold"),
        )
        ts_processes = (
            ("T–S hot isothermal expansion", [[1, 4], [3, 4]], "orange"),
            ("T–S adiabatic expansion", [[3, 4], [3, 2]], "teal"),
            ("T–S cold isothermal compression", [[3, 2], [1, 2]], "purple"),
            ("T–S adiabatic compression", [[1, 2], [1, 4]], "gold"),
        )
        for label, points, color in (*pv_processes, *ts_processes):
            add(label, points, color)
        layers.extend(
            [
                {
                    "type": "particles",
                    "points": [[1, 4], [1.001, 4]],
                    "label": "P–V synchronized state",
                    "color": "red",
                },
                {
                    "type": "particles",
                    "points": [[1, 4], [1.001, 4]],
                    "label": "T–S synchronized state",
                    "color": "red",
                },
            ]
        )
        panel(
            "pv_cycle",
            "Pressure–volume cycle",
            "volume V",
            "pressure P",
            *(label for label, _points, _color in pv_processes),
            "P–V synchronized state",
        )
        panel(
            "ts_cycle",
            "Temperature–entropy cycle",
            "entropy S",
            "temperature T",
            *(label for label, _points, _color in ts_processes),
            "T–S synchronized state",
        )
    elif family == "reaction_profile":
        add("uncatalysed exothermic profile", [[x, -0.3 * x + 3 * math.exp(-(x**2))] for x in xs])
        add(
            "catalysed lower activation energy",
            [[x, -0.3 * x + 1.8 * math.exp(-(x**2))] for x in xs],
            "teal",
        )
    elif family == "titration":
        titrant_volumes = [index * 0.25 for index in range(201)]
        add(
            "pH curve",
            [
                [volume, 2 + 10 / (1 + math.exp(-0.35 * (volume - 25)))]
                for volume in titrant_volumes
            ],
        )
        add("selected titrant volume", [[25, 0], [25, 7]], "purple")
        layers.extend(
            [
                {
                    "type": "node",
                    "id": "burette",
                    "x": 560,
                    "y": 80,
                    "width": 70,
                    "height": 160,
                    "label": "burette: titrant",
                    "color": "teal",
                },
                {
                    "type": "node",
                    "id": "flask",
                    "x": 560,
                    "y": 320,
                    "width": 120,
                    "height": 90,
                    "label": "flask: analyte + indicator",
                    "color": "purple",
                },
                {
                    "type": "arrow",
                    "from": [595, 240],
                    "to": [595, 315],
                    "label": "measured titrant added",
                    "color": "gold",
                },
            ]
        )
    elif family == "action_potential":
        add(
            "membrane voltage",
            [[0, -70], [1, -70], [2, -55], [2.5, 30], [3.2, -20], [4, -80], [5.5, -70]],
        )
        action_times = [index * 5.5 / 80 for index in range(81)]
        add(
            "sodium channel conductance opens then closes",
            [[time, 80 * math.exp(-(((time - 2.5) / 0.38) ** 2)) - 90] for time in action_times],
            "teal",
        )
        add(
            "potassium channel conductance opens later",
            [[time, 55 * math.exp(-(((time - 3.3) / 0.72) ** 2)) - 90] for time in action_times],
            "orange",
        )
        add("time probe", [[1, -90], [1, -70]], "purple")
    elif family == "phase_diagram":
        add("solid–gas boundary", [[0.08, 0.08], [0.35, 0.35]], "teal")
        add("solid–liquid boundary", [[0.35, 0.35], [0.48, 0.96]], "purple")
        add("liquid–gas boundary", [[0.35, 0.35], [0.58, 0.53], [0.86, 0.78]], "orange")
        add("selected state (T,P)", [[0.55, 0], [0.55, 0.55]], "gold")
    elif family == "polar_plot":
        samples = [index * math.pi / 80 for index in range(161)]
        add(
            "r = cos(2θ)",
            [[math.cos(2 * t) * math.cos(t), math.cos(2 * t) * math.sin(t)] for t in samples],
        )
        layers.append(
            {
                "type": "particles",
                "points": [[1, 0], [-1, 0], [0, 1], [0, -1]],
                "label": "four radial maxima r=±1",
                "color": "gold",
            }
        )
        layers.append(
            {
                "type": "particles",
                "points": [
                    [
                        0.3 * math.cos(math.pi / 4 + k * math.pi / 2),
                        0.3 * math.sin(math.pi / 4 + k * math.pi / 2),
                    ]
                    for k in range(4)
                ],
                "label": "zero crossings r=0 at θ=π/4+kπ/2",
                "color": "purple",
            }
        )
        layers.append(
            {
                "type": "particles",
                "points": [[1, 0], [1.001, 0]],
                "label": "traversal point",
                "color": "orange",
            }
        )
    elif family == "fourier_series":
        add("square-wave target", [[x, 1 if math.sin(x) >= 0 else -1] for x in xs], "gray")
        for harmonic, color in ((1, "teal"), (3, "orange"), (5, "purple")):
            add(
                f"harmonic n={harmonic}",
                [[x, 4 * math.sin(harmonic * x) / (math.pi * harmonic)] for x in xs],
                color,
            )
        add(
            "odd-harmonic partial sum",
            [
                [x, sum(math.sin((2 * k + 1) * x) / (2 * k + 1) for k in range(5)) * 4 / math.pi]
                for x in xs
            ],
            "gold",
        )
        layers.append(
            {
                "type": "particles",
                "points": [[-math.pi, 1.18], [0, 1.18], [math.pi, 1.18]],
                "label": "Gibbs overshoot near jumps",
                "color": "red",
            }
        )
    elif family == "convolution":
        add("box pulse A", [[-1, 0], [-1, 1], [1, 1], [1, 0]], "teal")
        add("sliding box pulse B", [[-1, 0], [-1, 1], [1, 1], [1, 0]], "orange")
        add("current overlap area", [[-1, 0], [-1, 1], [1, 1], [1, 0], [-1, 0]], "purple")
        add("convolution result versus shift", [[x, max(0, 2 - abs(x))] for x in xs], "gold")
        layers.append(
            {
                "type": "particles",
                "points": [[0, 2], [0.001, 2]],
                "label": "current overlap-area value",
                "color": "red",
            }
        )
    elif family == "double_slit":
        slit_separation, wavelength = 1.2, 0.5
        slit_x, screen_x, slit_half_width = -2.0, 2.8, 0.12

        def slit_geometry(screen_y: float) -> tuple[list[float], list[float], list[float], float]:
            half_gap = slit_separation / 2
            upper = [slit_x, half_gap]
            lower = [slit_x, -half_gap]
            screen = [screen_x, screen_y]
            path_difference = abs(math.dist(screen, lower) - math.dist(screen, upper))
            return upper, lower, screen, path_difference

        add(
            "intensity",
            [[x, math.cos(math.pi * slit_geometry(x)[3] / wavelength) ** 2] for x in xs],
        )
        half_gap = slit_separation / 2
        add("opaque barrier upper", [[slit_x, 3], [slit_x, half_gap + slit_half_width]], "gray")
        add(
            "opaque barrier middle",
            [[slit_x, half_gap - slit_half_width], [slit_x, -half_gap + slit_half_width]],
            "gray",
        )
        add("opaque barrier lower", [[slit_x, -half_gap - slit_half_width], [slit_x, -3]], "gray")
        upper, lower, screen, path_difference = slit_geometry(1.2)
        add("upper-slit path", [[-3.5, 0], upper, screen], "teal")
        add("lower-slit path", [[-3.5, 0], lower, screen], "orange")
        add("screen", [[screen_x, -3], [screen_x, 3]], "purple")
        upper_length = math.dist(screen, upper)
        lower_length = math.dist(screen, lower)
        longer = lower if lower_length >= upper_length else upper
        path_length = math.dist(screen, longer)
        cue_length = min(0.9, path_difference * 3)
        cue_start = [
            screen[index] - cue_length * (screen[index] - longer[index]) / path_length
            for index in range(2)
        ]
        add("path difference Δℓ", [cue_start, screen], "gold")
    elif family == "blackbody":
        for temperature, color_name in ((1.2, "teal"), (1.7, "orange"), (2.2, "purple")):
            add(
                f"T={temperature}",
                [
                    [w, w**-5 / (math.exp(min(40, 5 / (w * temperature))) - 1)]
                    for w in [0.1 + i * 0.05 for i in range(80)]
                ],
                color_name,
            )
        peak_points = []
        for temperature in (1.2, 1.7, 2.2):
            curve = [
                [w, w**-5 / (math.exp(min(40, 5 / (w * temperature))) - 1)]
                for w in [0.1 + i * 0.05 for i in range(80)]
            ]
            peak_points.append(max(curve, key=lambda point: point[1]))
        layers.append(
            {
                "type": "particles",
                "points": peak_points,
                "label": "Wien peak markers λmax∝1/T",
                "color": "gold",
            }
        )
    elif family == "kinetics":
        times = [index / 10 for index in range(101)]
        rate = 0.35
        zero = [[time, max(0, 1 - rate * time)] for time in times]
        first = [[time, math.exp(-rate * time)] for time in times]
        second = [[time, 1 / (1 + rate * time)] for time in times]
        add("zero-order [A]", zero, "teal")
        add("first-order [A]", first, "orange")
        add("second-order [A]", second, "purple")
        add("zero-order linearized [A]", zero, "teal")
        add("first-order linearized ln[A]", [[time, -rate * time] for time in times], "orange")
        add("second-order linearized 1/[A]", [[time, 1 + rate * time] for time in times], "purple")
        add("selected reaction order", first, "gold")
    elif family == "enzyme_kinetics":
        concentrations = [index / 10 for index in range(101)]
        add(
            "Michaelis–Menten without inhibitor",
            [[value, value / (1.5 + value)] for value in concentrations],
            "orange",
        )
        add(
            "competitive inhibition apparent Kₘ",
            [[value, value / (3 + value)] for value in concentrations],
            "teal",
        )
        layers.append(
            {
                "type": "particles",
                "points": [[1, 1 / 2.5], [1, 1 / 4]],
                "label": "selected substrate rates",
                "color": "gold",
            }
        )
    elif family == "bode_plot":
        add("low-pass magnitude (dB)", [[x, -10 * math.log10(1 + 10 ** (2 * x))] for x in xs])
        add("low-pass phase (degrees)", [[x, -math.degrees(math.atan(10**x))] for x in xs], "teal")
    elif family == "nyquist":
        add(
            "Nyquist locus, winding number N=0",
            [[-0.25 + 0.2 * math.cos(t), 0.2 * math.sin(t)] for t in turns],
        )
        layers.append(
            {
                "type": "particles",
                "points": [[-1, 0], [-1, 0]],
                "label": "critical point −1+0j",
                "color": "gold",
            }
        )
    elif family == "pwm":
        points: list[list[float]] = []
        for index in range(20):
            points.extend([[index, 0], [index, 1], [index + 0.45, 1], [index + 0.45, 0]])
        add("PWM voltage", points)
        add("motor average voltage = duty × supply", [[0, 0.45], [20, 0.45]], "teal")
    elif family == "pid_response":
        times = [index / 10 for index in range(101)]
        kp, ki, kd = 1.0, 2.0, 3.0
        p_response = [
            [time, (kp / (1 + kp)) * (1 - math.exp(-(0.4 + kp / 5) * time))] for time in times
        ]
        pi_response = [
            [time, 1 - math.exp(-(0.35 + ki / 10) * time) * math.cos((0.8 + ki / 10) * time)]
            for time in times
        ]
        pid_response = [
            [
                time,
                1
                - math.exp(-(0.55 + kd / 8) * time)
                * (math.cos((0.9 + kp / 10) * time) + 0.25 * math.sin((0.9 + ki / 10) * time)),
            ]
            for time in times
        ]
        add("P response", p_response, "teal")
        add("PI response", pi_response, "orange")
        add("PID response", pid_response, "purple")
        rise = next((point for point in pid_response if point[1] >= 0.9), pid_response[-1])
        peak = max(pid_response, key=lambda point: point[1])
        final = pid_response[-1]
        add("rise time marker", [[rise[0], 0], [rise[0], rise[1]]], "gold")
        add("overshoot marker", [[peak[0], 1], peak], "orange")
        add("steady-state error marker", [[final[0], final[1]], [final[0], 1]], "teal")
    elif family == "impulse_response":
        add("finite input x[n] = [1,2,1]", [[0, 1], [1, 2], [2, 1]], "teal")
        add("flipped and shifted h[n] = [1,−1,2]", [[0, 2], [1, -1], [2, 1]], "purple")
        add(
            "convolution output y[n] = [1,1,1,3,2]",
            [[0, 1], [1, 1], [2, 1], [3, 3], [4, 2]],
            "orange",
        )
    elif family == "beam_bending":
        length, load, load_at, rigidity = 10.0, 10.0, 5.0, 100.0
        beam_x = [length * index / 100 for index in range(101)]
        left_reaction = load * (length - load_at) / length
        shear = [[x, left_reaction if x < load_at else left_reaction - load] for x in beam_x]
        moment = [
            [x, left_reaction * x if x <= load_at else left_reaction * x - load * (x - load_at)]
            for x in beam_x
        ]
        deflection = []
        for x in beam_x:
            if x <= load_at:
                value = (
                    -load
                    * (length - load_at)
                    * x
                    * (length**2 - (length - load_at) ** 2 - x**2)
                    / (6 * length * rigidity)
                )
            else:
                value = (
                    -load
                    * load_at
                    * (length - x)
                    * (length**2 - load_at**2 - (length - x) ** 2)
                    / (6 * length * rigidity)
                )
            deflection.append([x, value])
        add("simply supported beam", [[0, 0], [length, 0]], "teal")
        add("left pin support", [[-0.35, -0.5], [0, 0], [0.35, -0.5], [-0.35, -0.5]], "purple")
        add("right roller support", [[9.65, -0.5], [10, 0], [10.35, -0.5], [9.65, -0.5]], "purple")
        add("moving point load 10", [[load_at, 2], [load_at, 0]], "orange")
        add("left support reaction", [[0, -0.5], [0, left_reaction / 5]], "gold")
        add(
            "right support reaction", [[length, -0.5], [length, (load - left_reaction) / 5]], "gold"
        )
        add("shear V(x)", shear, "teal")
        add("bending moment M(x)", moment, "orange")
        add("deflection v(x)", deflection, "purple")
        panel(
            "beam_setup",
            "Simply supported beam",
            "beam position x",
            "load / reactions",
            "simply supported beam",
            "left pin support",
            "right roller support",
            "moving point load 10",
            "left support reaction",
            "right support reaction",
        )
        panel("shear", "Shear-force diagram", "beam position x", "V(x)", "shear V(x)")
        panel("moment", "Bending-moment diagram", "beam position x", "M(x)", "bending moment M(x)")
        panel("deflection", "Deflection diagram", "beam position x", "v(x)", "deflection v(x)")
    elif family == "kepler_orbit":
        add("trajectory", [[3 * math.cos(t), 1.8 * math.sin(t)] for t in turns])
        layers.append(
            {
                "type": "particles",
                "points": [[3, 0], [3.001, 0]],
                "label": "satellite at true anomaly",
                "color": "gold",
            }
        )
        add("radius vector", [[0, 0], [3, 0]], "teal")
        add("velocity vector tangent to orbit", [[3, 0], [3, 1]], "purple")
        add("acceleration vector toward focus", [[3, 0], [2, 0]], "orange")
        add("equal-area sweep sector", [[0, 0], [3, 0], [2.9, 0.7], [0, 0]], "gold")
    elif family == "differential_drive":
        add("robot trajectory", [[3 * math.cos(t), math.sin(t)] for t in turns])
        add(
            "robot body", [[-0.6, -0.4], [0.6, -0.4], [0.6, 0.4], [-0.6, 0.4], [-0.6, -0.4]], "teal"
        )
        add("left wheel", [[-0.45, -0.65], [0.45, -0.65]], "purple")
        add("right wheel", [[-0.45, 0.65], [0.45, 0.65]], "purple")
        add("instantaneous centre of curvature", [[0, 0], [0, 2]], "gold")
    elif family == "double_pendulum":

        def simulate(initial_degrees: float) -> tuple[list[list[float]], list[list[float]]]:
            state = [
                math.radians(initial_degrees),
                0.0,
                math.radians(-0.55 * initial_degrees),
                0.0,
            ]
            path: list[list[float]] = []
            arms: list[list[float]] = []
            for step in range(1601):
                theta1, omega1, theta2, omega2 = state
                if step % 20 == 0:
                    elbow = [math.sin(theta1), -math.cos(theta1)]
                    bob = [elbow[0] + math.sin(theta2), elbow[1] - math.cos(theta2)]
                    path.append(bob)
                    if step == 0:
                        arms = [[0, 0], elbow, bob]
                delta = theta1 - theta2
                denominator = max(0.1, 3 - math.cos(2 * delta))
                alpha1 = (
                    -3 * 9.81 * math.sin(theta1)
                    - 9.81 * math.sin(theta1 - 2 * theta2)
                    - 2 * math.sin(delta) * (omega2**2 + omega1**2 * math.cos(delta))
                ) / denominator
                alpha2 = (
                    2
                    * math.sin(delta)
                    * (2 * omega1**2 + 2 * 9.81 * math.cos(theta1) + omega2**2 * math.cos(delta))
                ) / denominator
                omega1 += 0.01 * alpha1
                omega2 += 0.01 * alpha2
                state = [
                    theta1 + 0.01 * omega1,
                    omega1,
                    theta2 + 0.01 * omega2,
                    omega2,
                ]
            return path, arms

        trajectory_a, arms_a = simulate(75)
        trajectory_b, arms_b = simulate(75.5)
        add("trajectory A: θ₀=75°", trajectory_a)
        add("trajectory B: θ₀=75.5°", trajectory_b, "teal")
        add("double-pendulum arms A", arms_a, "gold")
        add("double-pendulum arms B", arms_b, "purple")
    elif family == "electric_field_lines":
        charge_positions = (-1.0, 1.0)
        for seed_index in range(10):
            angle = 2 * math.pi * seed_index / 10
            x = charge_positions[0] + 0.16 * math.cos(angle)
            y = 0.16 * math.sin(angle)
            points = []
            for _step in range(120):
                points.append([x, y])
                field_x = field_y = 0.0
                for centre, charge in ((charge_positions[0], 1.0), (charge_positions[1], -1.0)):
                    dx, dy = x - centre, y
                    radius_squared = max(0.015, dx * dx + dy * dy)
                    gain = charge / (radius_squared * math.sqrt(radius_squared))
                    field_x += gain * dx
                    field_y += gain * dy
                magnitude = math.hypot(field_x, field_y)
                if magnitude < 1e-9:
                    break
                x += 0.055 * field_x / magnitude
                y += 0.055 * field_y / magnitude
                if math.hypot(x - charge_positions[1], y) < 0.16 or abs(x) > 4 or abs(y) > 4:
                    points.append([x, y])
                    break
            if len(points) >= 2:
                add("field line + → −", points, ("teal", "orange", "purple")[seed_index % 3])
        layers.append(
            {
                "type": "particles",
                "points": [[-1, 0], [1, 0]],
                "label": "+ and − charges",
                "color": "gold",
            }
        )
    elif family == "electric_field_vectors":
        x_expression = parse_expression_v2(
            "(x+1)/(((x+1)^2+y^2)^(3/2))-(x-1)/(((x-1)^2+y^2)^(3/2))"
        )
        y_expression = parse_expression_v2("y/(((x+1)^2+y^2)^(3/2))-y/(((x-1)^2+y^2)^(3/2))")
        vectors = []
        for y in (-3, -2, -1, 0, 1, 2, 3):
            for x in (-3, -2, -0.5, 0.5, 2, 3):
                dx = _safe_sample(x_expression, {"x": x, "y": y})
                dy = _safe_sample(y_expression, {"x": x, "y": y})
                if dx is None or dy is None or math.hypot(dx, dy) < 1e-9:
                    continue
                scale = 0.55 / max(0.55, math.hypot(dx, dy))
                vectors.append([x, y, dx * scale, dy * scale])
        layers.extend(
            [
                {
                    "type": "vector_field",
                    "vectors": vectors,
                    "label": "net electric field",
                    "color": "purple",
                },
                {
                    "type": "probe_vector",
                    "x_control": "test_x",
                    "y_control": "test_y",
                    "x_expression": x_expression,
                    "y_expression": y_expression,
                    "scale": 0.65,
                    "label": "net force on test charge",
                    "color": "gold",
                },
                {
                    "type": "particles",
                    "points": [[-1, 0], [1, 0]],
                    "label": "source charges + and −",
                    "color": "teal",
                },
            ]
        )
    elif family == "magnetic_field_wire":
        for radius, color_name in ((0.8, "teal"), (1.5, "orange"), (2.2, "purple")):
            add(
                f"magnetic field ring r={radius}",
                [[radius * math.cos(t), radius * math.sin(t)] for t in turns],
                color_name,
            )
        for radius, color_name in ((0.8, "teal"), (1.5, "orange"), (2.2, "purple")):
            add(
                f"direction arrow r={radius}",
                [[0, radius], [0.42, radius]],
                color_name,
            )
    elif family == "doppler":
        for index, (radius, color_name) in enumerate(
            ((2.2, "purple"), (1.5, "orange"), (0.8, "teal"))
        ):
            centre = 0.25 * (index - 1)
            add(
                "wavefront",
                [[centre + radius * math.cos(t), radius * math.sin(t)] for t in turns],
                color_name,
            )
        layers.append(
            {
                "type": "particles",
                "points": [[0, 0], [0.001, 0]],
                "label": "moving source",
                "color": "gold",
            }
        )
    elif family == "logistic_map":
        value = 0.21
        points = []
        for index in range(80):
            points.append([index, value])
            value = 3.72 * value * (1 - value)
        add("iterate xₙ versus n", points)
        identity = [[index / 80, index / 80] for index in range(81)]
        map_curve = [[index / 80, 3.72 * (index / 80) * (1 - index / 80)] for index in range(81)]
        add("identity y=x", identity, "teal")
        add("logistic map y=r x(1−x)", map_curve, "orange")
        cobweb = []
        value = 0.21
        for _ in range(32):
            next_value = 3.72 * value * (1 - value)
            cobweb.extend([[value, value], [value, next_value], [next_value, next_value]])
            value = next_value
        add("cobweb iteration", cobweb, "purple")
        bifurcation = []
        for column in range(45):
            growth = 2.8 + 1.2 * column / 44
            value = 0.21
            for _ in range(120):
                value = growth * value * (1 - value)
            for _ in range(12):
                value = growth * value * (1 - value)
                bifurcation.append([growth, value])
        layers.append(
            {
                "type": "particles",
                "points": bifurcation,
                "label": "bifurcation attractor samples",
                "color": "gold",
            }
        )
        panel("iterations", "Iterate history", "iteration n", "xₙ", "iterate xₙ versus n")
        panel(
            "cobweb",
            "Cobweb diagram",
            "xₙ",
            "xₙ₊₁",
            "identity y=x",
            "logistic map y=r x(1−x)",
            "cobweb iteration",
        )
        panel(
            "bifurcation",
            "Bifurcation behavior",
            "growth r",
            "long-run x",
            "bifurcation attractor samples",
        )
    elif family == "coupled_oscillators":
        add("in-phase normal-mode displacement", [[x, math.sin(x)] for x in xs])
        add(
            "out-of-phase normal-mode displacement",
            [[x, math.sin(x + math.pi)] for x in xs],
            "teal",
        )
        add(
            "three springs and two masses",
            [[-4, 0], [-3, 0.4], [-2, 0], [-1, -0.4], [0, 0], [1, 0.4], [2, 0], [3, -0.4], [4, 0]],
            "purple",
        )
        layers.append(
            {
                "type": "particles",
                "points": [[-1.25, 0], [1.25, 0]],
                "label": "two moving masses",
                "color": "gold",
            }
        )
    elif family == "predator_prey":
        prey, predator = 1.4, 0.8
        prey_series: list[list[float]] = []
        predator_series: list[list[float]] = []
        phase_series: list[list[float]] = []
        for step in range(161):
            time = step * 0.04
            prey_series.append([time, prey])
            predator_series.append([time, predator])
            phase_series.append([prey, predator])
            next_prey = max(0, prey + 0.04 * (0.45 * prey - 0.32 * prey * predator))
            next_predator = max(0, predator + 0.04 * (0.18 * prey * predator - 0.22 * predator))
            prey, predator = next_prey, next_predator
        add("prey population versus time", prey_series, "teal")
        add("predator population versus time", predator_series, "orange")
        add("predator-prey phase portrait", phase_series, "purple")
        panel(
            "populations",
            "Populations over time",
            "time",
            "population",
            "prey population versus time",
            "predator population versus time",
        )
        panel(
            "phase_portrait",
            "Predator–prey phase portrait",
            "prey population",
            "predator population",
            "predator-prey phase portrait",
        )
    elif family == "spectrogram":
        rows, columns = 18, 44
        values = []
        for row in range(rows):
            for column in range(columns):
                time = column / (columns - 1)
                center = 2 + 10 * time
                values.append(math.exp(-0.5 * ((row - center) / 1.35) ** 2))
        layers.append(
            {
                "type": "heatmap",
                "x_domain": [0, 1],
                "y_domain": [0, 18],
                "rows": rows,
                "columns": columns,
                "values": values,
                "label": "chirp energy",
                "color": "orange",
            }
        )
        add(
            "chirp waveform",
            [
                [x, math.sin(2 * math.pi * (2 * x + 5 * x * x))]
                for x in [i / 100 for i in range(101)]
            ],
        )
        panel(
            "time_frequency",
            "Time–frequency energy",
            "time (s)",
            "frequency (Hz)",
            "chirp energy",
        )
        panel(
            "waveform",
            "Chirp waveform",
            "time (s)",
            "amplitude",
            "chirp waveform",
        )
    elif family == "heat_diffusion":
        rows, columns = 8, 64
        values = []
        spread = math.sqrt(0.15 + 1 / 4)
        for _row in range(rows):
            for column in range(columns):
                position = -4 + 8 * column / (columns - 1)
                values.append(math.exp(-(position**2) / (2 * spread**2)) / spread)
        layers.append(
            {
                "type": "heatmap",
                "x_domain": [-4, 4],
                "y_domain": [0, 1],
                "rows": rows,
                "columns": columns,
                "values": values,
                "label": "temperature field",
                "color": "orange",
            }
        )
        add("temperature profile", [[x, math.exp(-0.45 * x * x)] for x in xs])
        panel(
            "temperature_field",
            "Temperature field",
            "position",
            "space / time",
            "temperature field",
        )
        panel(
            "temperature_profile",
            "Temperature profile",
            "position",
            "temperature",
            "temperature profile",
        )
    elif family == "fluid_flow":
        # Potential flow around a unit cylinder.  Each streamline is a contour of
        # ψ/U = y·(1-a²/r²), solved outside r=a so no segment crosses the body.
        flow_x = [-4 + 8 * index / 160 for index in range(161)]

        def streamline(seed: float) -> list[list[float]]:
            points: list[list[float]] = []
            sign = -1 if seed < 0 else 1
            target = abs(seed)
            for x in flow_x:
                boundary = math.sqrt(max(0.0, 1 - x * x))
                low, high = boundary + 1e-6, max(6.0, target + 2)
                for _ in range(52):
                    y = (low + high) / 2
                    stream_value = y * (1 - 1 / max(1e-12, x * x + y * y))
                    if stream_value < target:
                        low = y
                    else:
                        high = y
                points.append([x, sign * (low + high) / 2])
            return points

        for seed, color in ((0.35, "gold"), (0.8, "teal"), (1.4, "orange"), (2.2, "purple")):
            add(f"streamline ψ/U={seed}", streamline(seed), color)
            add(f"streamline ψ/U=−{seed}", streamline(-seed), color)
        add("free-stream speed cue", [[-3.8, -2.9], [-2.8, -2.9]], "gold")
        layers.append(
            {
                "type": "particles",
                "points": [[-1, 0], [1, 0]],
                "label": "stagnation points",
                "color": "gold",
            }
        )
    elif family == "decision_boundary":
        state = _classifier_state(20, 0.2)
        rows, columns = 16, 24
        layers.append(
            {
                "type": "heatmap",
                "x_domain": [-4, 4],
                "y_domain": [-3, 3],
                "rows": rows,
                "columns": columns,
                "values": [
                    state["predict"]([-4 + 8 * column / (columns - 1), -3 + 6 * row / (rows - 1)])[
                        1
                    ]
                    - 0.5
                    for row in range(rows)
                    for column in range(columns)
                ],
                "label": "class score regions",
                "color": "teal",
            }
        )
        layers.append(
            {
                "type": "particles",
                "points": [point for point, _label in state["samples"]],
                "label": "labelled training samples",
                "color": "purple",
            }
        )
        boundary = []
        for x in xs:
            candidates = [
                [-3 + 6 * index / 120, abs(state["predict"]([x, -3 + 6 * index / 120])[1] - 0.5)]
                for index in range(121)
            ]
            boundary.append([x, min(candidates, key=lambda record: record[1])[0]])
        add("decision boundary", boundary)
        add(
            "training loss versus epoch",
            state["loss"],
            "gold",
        )
        panel(
            "classification",
            "Classification regions",
            "feature 1",
            "feature 2",
            "class score regions",
            "labelled training samples",
            "decision boundary",
        )
        panel(
            "training_loss",
            "Training loss",
            "epoch",
            "loss",
            "training loss versus epoch",
        )
    elif family == "kalman_filter":
        truth: list[list[float]] = []
        measurements: list[list[float]] = []
        estimates: list[list[float]] = []
        priors: list[list[float]] = []
        prior_variances: list[float] = []
        posterior_variances: list[float] = []
        estimate, variance = 0.0, 1.5
        for step in range(21):
            actual = 0.5 * step + math.sin(0.4 * step)
            measurement = actual + math.sin(1.7 * step)
            prior = estimate + 0.5
            predicted_variance = variance + 0.08
            gain = predicted_variance / (predicted_variance + 1.0)
            estimate = prior + gain * (measurement - prior)
            variance = (1 - gain) * predicted_variance
            truth.append([step, actual])
            measurements.append([step, measurement])
            estimates.append([step, estimate])
            priors.append([step, prior])
            prior_variances.append(predicted_variance)
            posterior_variances.append(variance)
        add("true moving-point trajectory", truth, "gray")
        add("noisy measurements", measurements, "orange")
        add("Kalman estimate trajectory", estimates, "teal")

        def ellipse(centre: list[float], vertical_radius: float) -> list[list[float]]:
            return [
                [centre[0] + 0.25 * math.cos(angle), centre[1] + vertical_radius * math.sin(angle)]
                for angle in turns
            ]

        add(
            "predicted covariance ellipse P⁻",
            ellipse(priors[0], math.sqrt(prior_variances[0])),
            "purple",
        )
        add(
            "posterior covariance ellipse P",
            ellipse(estimates[0], math.sqrt(posterior_variances[0])),
            "gold",
        )
        layers.extend(
            [
                {
                    "type": "particles",
                    "points": [truth[0], [truth[0][0] + 0.001, truth[0][1]]],
                    "label": "current true point",
                    "color": "gray",
                },
                {
                    "type": "particles",
                    "points": [measurements[0], [measurements[0][0] + 0.001, measurements[0][1]]],
                    "label": "current noisy measurement",
                    "color": "orange",
                },
                {
                    "type": "particles",
                    "points": [estimates[0], [estimates[0][0] + 0.001, estimates[0][1]]],
                    "label": "current Kalman update",
                    "color": "gold",
                },
            ]
        )
    elif family == "uncertainty_propagation":

        def van_der_corput(index: int, base: int) -> float:
            result, denominator = 0.0, 1.0
            while index:
                index, remainder = divmod(index, base)
                denominator *= base
                result += remainder / denominator
            return result

        samples: list[list[float]] = []
        densities: list[float] = []
        for index in range(1, 161):
            u1 = max(1e-9, van_der_corput(index, 2))
            u2 = van_der_corput(index, 3)
            radius = math.sqrt(-2 * math.log(u1))
            mass = 10 + 0.4 * radius * math.cos(2 * math.pi * u2)
            volume = max(0.1, 4 + 0.18 * radius * math.sin(2 * math.pi * u2))
            samples.append([volume, mass])
            densities.append(mass / volume)
        low, high = min(densities), max(densities)
        bins = 24
        counts = [0] * bins
        for density in densities:
            slot = min(bins - 1, int((density - low) / max(1e-12, high - low) * bins))
            counts[slot] += 1
        total = sum(counts)
        width = (high - low) / bins
        add(
            "density histogram ρ=m/V",
            [
                [low + (slot + 0.5) * width, count / max(1, total) / width]
                for slot, count in enumerate(counts)
            ],
            "orange",
        )
        layers.append(
            {
                "type": "particles",
                "points": samples,
                "label": "sampled mass and positive volume pairs",
                "color": "teal",
            }
        )
        panel(
            "mass_volume",
            "Sampled mass and volume",
            "volume",
            "mass",
            "sampled mass and positive volume pairs",
        )
        panel(
            "density_histogram",
            "Density distribution",
            "density ρ=m/V",
            "probability density",
            "density histogram ρ=m/V",
        )
    elif family == "complex_mapping":
        for radius in (0.6, 1.2, 1.8):
            add(
                f"domain polar circle r={radius}",
                [[-3 + radius * math.cos(t), radius * math.sin(t)] for t in turns],
                "teal",
            )
            add(
                f"image polar circle r²={radius * radius:.2f}",
                [[3 + radius * radius * math.cos(t), radius * radius * math.sin(t)] for t in turns],
                "orange",
            )
        for ray in range(8):
            angle = ray * math.pi / 4
            add(
                f"domain ray θ={ray}",
                [[-3, 0], [-3 + 1.8 * math.cos(angle), 1.8 * math.sin(angle)]],
                "teal",
            )
            add(
                f"image ray 2θ={ray}",
                [[3, 0], [3 + 3.24 * math.cos(2 * angle), 3.24 * math.sin(2 * angle)]],
                "orange",
            )
        add("selected source z", [[-3, 0], [-2, 0]], "gold")
        add("selected image z²", [[3, 0], [4, 0]], "purple")
    else:
        add(family.replace("_", " "), [[x, math.sin(x) * math.exp(-0.08 * x * x)] for x in xs])
    return layers


def _schematic_layers(family: str, request: str = "") -> list[dict[str, Any]]:
    if family == "binary_representation":
        layers: list[dict[str, Any]] = []
        for index, (bit, power, contribution) in enumerate(
            ((1, 8, 8), (1, 4, 4), (0, 2, 0), (1, 1, 1))
        ):
            layers.append(
                {
                    "type": "node",
                    "id": f"bit_{power}",
                    "x": 135 + index * 145,
                    "y": 165,
                    "width": 118,
                    "height": 76,
                    "label": f"bit {bit} × {power} = {contribution}",
                    "color": "teal" if bit else "purple",
                }
            )
        layers.append(
            {
                "type": "node",
                "id": "sum",
                "x": 360,
                "y": 330,
                "width": 270,
                "height": 64,
                "label": "8 + 4 + 0 + 1 = 13₁₀ = 1101₂",
                "color": "orange",
            }
        )
        for power in (8, 4, 2, 1):
            layers.append(
                {
                    "type": "link",
                    "from": f"bit_{power}",
                    "to": "sum",
                    "arrow": True,
                    "label": "place-value contribution",
                }
            )
        return layers
    if family == "robot_forward_kinematics":
        lengths = (105.0, 90.0, 75.0)
        angles = [math.radians(value) for value in (25, -35, 55)]
        points = [[165.0, 330.0]]
        heading = 0.0
        for length, angle in zip(lengths, angles):
            heading += angle
            points.append(
                [
                    points[-1][0] + length * math.cos(heading),
                    points[-1][1] - length * math.sin(heading),
                ]
            )
        labels = ("base", "joint 1", "joint 2", "end effector")
        layers = [
            {
                "type": "node",
                "id": f"joint_{index}",
                "x": point[0],
                "y": point[1],
                "width": 104 if index < 3 else 150,
                "height": 50,
                "label": labels[index]
                if index < 3
                else f"end effector ({point[0]:.1f}, {point[1]:.1f})",
                "color": ("teal", "orange", "purple", "blue")[index],
            }
            for index, point in enumerate(points)
        ]
        for index, length in enumerate(lengths):
            layers.append(
                {
                    "type": "link",
                    "from": f"joint_{index}",
                    "to": f"joint_{index + 1}",
                    "arrow": False,
                    "label": f"L{index + 1}={length:.0f} px",
                }
            )
        return layers
    if family == "binary_search_tree":
        seed = (
            ("root", 8, 360, 70),
            ("left", 3, 210, 180),
            ("right", 11, 510, 180),
            ("left_left", 1, 125, 300),
            ("left_right", 5, 295, 300),
            ("right_left", 9, 425, 300),
            ("right_right", 13, 595, 300),
        )
        layers = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": 72,
                "height": 48,
                "label": str(value),
                "color": "teal" if node_id != "root" else "gold",
            }
            for node_id, value, x, y in seed
        ]
        layers.append(
            {
                "type": "node",
                "id": "candidate",
                "x": 345,
                "y": 405,
                "width": 106,
                "height": 48,
                "label": "insert 6",
                "color": "orange",
            }
        )
        for parent, child in (
            ("root", "left"),
            ("root", "right"),
            ("left", "left_left"),
            ("left", "left_right"),
            ("right", "right_left"),
            ("right", "right_right"),
        ):
            layers.append(
                {
                    "type": "link",
                    "from": parent,
                    "to": child,
                    "arrow": True,
                    "label": "smaller" if child.endswith("left") else "larger",
                }
            )
        layers.append(
            {
                "type": "link",
                "from": "root",
                "to": "candidate",
                "arrow": True,
                "label": "new-node placement",
            }
        )
        return layers
    if family == "stack_queue":
        layers = [
            {
                "type": "node",
                "id": "stack_title",
                "x": 185,
                "y": 55,
                "width": 180,
                "height": 44,
                "label": "Stack • LIFO",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "queue_title",
                "x": 535,
                "y": 55,
                "width": 180,
                "height": 44,
                "label": "Queue • FIFO",
                "color": "purple",
            },
        ]
        for index, value in enumerate(("A", "B", "C")):
            layers.append(
                {
                    "type": "node",
                    "id": f"stack_{index}",
                    "x": 185,
                    "y": 325 - index * 82,
                    "width": 122,
                    "height": 58,
                    "label": value,
                    "color": "teal",
                }
            )
            layers.append(
                {
                    "type": "node",
                    "id": f"queue_{index}",
                    "x": 405 + index * 130,
                    "y": 220,
                    "width": 104,
                    "height": 58,
                    "label": value,
                    "color": "orange",
                }
            )
        layers.extend(
            [
                {
                    "type": "link",
                    "from": "stack_0",
                    "to": "stack_1",
                    "arrow": True,
                    "label": "push upward",
                },
                {
                    "type": "link",
                    "from": "stack_1",
                    "to": "stack_2",
                    "arrow": True,
                    "label": "top / pop first",
                },
                {
                    "type": "link",
                    "from": "queue_0",
                    "to": "queue_1",
                    "arrow": True,
                    "label": "front / dequeue first",
                },
                {
                    "type": "link",
                    "from": "queue_1",
                    "to": "queue_2",
                    "arrow": True,
                    "label": "enqueue at rear",
                },
            ]
        )
        return layers
    if family == "neural_network":
        nodes = [
            ("x1", 90, 140, "input x₁=0.6", "teal"),
            ("x2", 90, 300, "input x₂=0.4", "teal"),
            ("h1", 345, 125, "h₁=ReLU(0.60)=0.60", "purple"),
            ("h2", 345, 315, "h₂=ReLU(0.18)=0.18", "purple"),
            ("output", 625, 220, "ŷ=sigmoid(0.464)=0.614", "gold"),
        ]
        three_hidden = bool(re.search(r"2\D{0,28}3\D{0,28}1", request))
        if three_hidden:
            nodes = [
                nodes[0],
                nodes[1],
                ("h1", 345, 105, "h₁=ReLU(0.60)=0.60", "purple"),
                ("h2", 345, 220, "h₂=ReLU(0.18)=0.18", "purple"),
                ("h3", 345, 335, "h₃=ReLU(0.34)=0.34", "purple"),
                ("output", 625, 220, "ŷ=sigmoid(0.583)=0.642", "gold"),
            ]
        layers = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": 132,
                "height": 56,
                "label": label,
                "color": color,
            }
            for node_id, x, y, label, color in nodes
        ]
        connections = [
            ("x1", "h1", "w₁₁ adjustable"),
            ("x2", "h1", "w₁₂=0.5"),
            ("x1", "h2", "w₂₁=−0.4"),
            ("x2", "h2", "w₂₂=0.8"),
            ("h1", "output", "v₁=0.9"),
            ("h2", "output", "v₂=−0.7"),
        ]
        if three_hidden:
            connections.extend(
                [
                    ("x1", "h3", "w₃₁=0.3"),
                    ("x2", "h3", "w₃₂=0.4"),
                    ("h3", "output", "v₃=0.35"),
                ]
            )
        for start, end, label in connections:
            layers.append({"type": "link", "from": start, "to": end, "arrow": True, "label": label})
        return layers
    if family == "equilibrium_shift":
        return [
            {
                "type": "node",
                "id": "reactants",
                "x": 170,
                "y": 90,
                "width": 190,
                "height": 54,
                "label": "N₂ + 3H₂ reactants",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "equilibrium",
                "x": 360,
                "y": 90,
                "width": 120,
                "height": 54,
                "label": "reversible ⇌",
                "color": "gold",
            },
            {
                "type": "node",
                "id": "products",
                "x": 550,
                "y": 90,
                "width": 180,
                "height": 54,
                "label": "2NH₃ product; fewer gas molecules",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "composition",
                "x": 360,
                "y": 355,
                "width": 240,
                "height": 58,
                "label": "equilibrium composition responds to P and T",
                "color": "orange",
            },
            {
                "type": "particles",
                "points": [[130, 180], [155, 205], [180, 180]],
                "label": "N₂ molecule population",
                "color": "teal",
            },
            {
                "type": "particles",
                "points": [[240, 180], [260, 205], [280, 180], [300, 205], [320, 180], [340, 205]],
                "label": "H₂ molecule population",
                "color": "blue",
            },
            {
                "type": "particles",
                "points": [[460, 180], [490, 205], [520, 180], [550, 205], [580, 180], [610, 205]],
                "label": "NH₃ molecule population",
                "color": "purple",
            },
            {
                "type": "link",
                "from": "reactants",
                "to": "equilibrium",
                "arrow": True,
                "label": "forward reaction",
            },
            {
                "type": "link",
                "from": "equilibrium",
                "to": "products",
                "arrow": True,
                "label": "forward reaction",
            },
            {
                "type": "link",
                "from": "products",
                "to": "equilibrium",
                "arrow": True,
                "label": "reverse reaction",
            },
            {
                "type": "link",
                "from": "equilibrium",
                "to": "reactants",
                "arrow": True,
                "label": "reverse reaction",
            },
            {
                "type": "link",
                "from": "products",
                "to": "composition",
                "arrow": True,
                "label": "higher pressure favors fewer gas molecules",
            },
            {
                "type": "link",
                "from": "reactants",
                "to": "composition",
                "arrow": True,
                "label": "temperature shifts equilibrium constant",
            },
        ]
    if family == "series_parallel_circuit":
        return [
            {
                "type": "node",
                "id": "source",
                "x": 100,
                "y": 215,
                "width": 128,
                "height": 58,
                "label": "source 12 V",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "r1",
                "x": 285,
                "y": 215,
                "width": 150,
                "height": 58,
                "label": "R₁=1 Ω",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "r2",
                "x": 455,
                "y": 215,
                "width": 150,
                "height": 58,
                "label": "R₂=2 Ω",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "return",
                "x": 630,
                "y": 215,
                "width": 142,
                "height": 58,
                "label": "return / meter",
                "color": "gold",
            },
            {
                "type": "link",
                "from": "source",
                "to": "r1",
                "arrow": True,
                "label": "series current",
            },
            {"type": "link", "from": "r1", "to": "r2", "arrow": True, "label": "same current"},
            {
                "type": "link",
                "from": "r2",
                "to": "return",
                "arrow": True,
                "label": "voltage drops add",
            },
            {
                "type": "link",
                "from": "return",
                "to": "source",
                "arrow": True,
                "label": "closed circuit",
            },
        ]
    if family == "binary_search":
        items = sorted(_number_list_from_request(request) or [1, 3, 5, 7, 9, 11, 13])
        display_items = ",".join(
            str(int(value)) if float(value).is_integer() else str(value) for value in items
        )
        return [
            {
                "type": "node",
                "id": "array",
                "x": 125,
                "y": 215,
                "width": 218,
                "height": 68,
                "label": f"[{display_items}]",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "comparison",
                "x": 340,
                "y": 115,
                "width": 196,
                "height": 64,
                "label": "compare midpoint",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "decision",
                "x": 340,
                "y": 315,
                "width": 204,
                "height": 64,
                "label": "discard one half",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "result",
                "x": 595,
                "y": 215,
                "width": 188,
                "height": 68,
                "label": "target result",
                "color": "gold",
            },
            {
                "type": "link",
                "from": "array",
                "to": "comparison",
                "arrow": True,
                "label": "choose midpoint",
            },
            {
                "type": "link",
                "from": "comparison",
                "to": "decision",
                "arrow": True,
                "label": "compare",
            },
            {
                "type": "link",
                "from": "decision",
                "to": "result",
                "arrow": True,
                "label": "shrink range / finish",
            },
        ]
    if family == "triangle_angles":
        return [
            {
                "type": "node",
                "id": "vertex_a",
                "x": 150,
                "y": 330,
                "width": 92,
                "height": 52,
                "label": "vertex A: 60°",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "vertex_b",
                "x": 570,
                "y": 330,
                "width": 92,
                "height": 52,
                "label": "vertex B: 60°",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "vertex_c",
                "x": 360,
                "y": 90,
                "width": 92,
                "height": 52,
                "label": "vertex C: 60°",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "angle_sum",
                "x": 360,
                "y": 390,
                "width": 210,
                "height": 42,
                "label": "A + B + C = 180°",
                "color": "gold",
            },
            {
                "type": "link",
                "from": "vertex_a",
                "to": "vertex_b",
                "arrow": False,
                "label": "side c",
            },
            {
                "type": "link",
                "from": "vertex_b",
                "to": "vertex_c",
                "arrow": False,
                "label": "side a",
            },
            {
                "type": "link",
                "from": "vertex_c",
                "to": "vertex_a",
                "arrow": False,
                "label": "side b",
            },
        ]
    if family == "mitosis":
        layers = [
            {
                "type": "node",
                "id": phase,
                "x": 115 + index * 165,
                "y": 65,
                "width": 130,
                "height": 46,
                "label": phase,
                "color": ("teal", "orange", "purple", "blue")[index],
            }
            for index, phase in enumerate(("prophase", "metaphase", "anaphase", "telophase"))
        ]
        layers.extend(
            {
                "type": "node",
                "id": f"chromosome{index}",
                "x": 300 + 40 * index,
                "y": 230,
                "width": 38,
                "height": 68,
                "label": f"X{index + 1}",
                "color": "gold",
            }
            for index in range(4)
        )
        layers.extend(
            {"type": "link", "from": start, "to": end, "arrow": True, "label": "next phase"}
            for start, end in (
                ("prophase", "metaphase"),
                ("metaphase", "anaphase"),
                ("anaphase", "telophase"),
                ("telophase", "prophase"),
            )
        )
        return layers
    if family == "circulation":
        return [
            {
                "type": "node",
                "id": "body",
                "x": 100,
                "y": 215,
                "width": 112,
                "height": 58,
                "label": "body tissues",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "right_heart",
                "x": 275,
                "y": 330,
                "width": 130,
                "height": 58,
                "label": "right heart",
                "color": "blue",
            },
            {
                "type": "node",
                "id": "lungs",
                "x": 455,
                "y": 215,
                "width": 105,
                "height": 58,
                "label": "lungs",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "left_heart",
                "x": 275,
                "y": 95,
                "width": 130,
                "height": 58,
                "label": "left heart",
                "color": "red",
            },
            {
                "type": "node",
                "id": "rbc",
                "x": 100,
                "y": 215,
                "width": 82,
                "height": 40,
                "label": "red blood cell",
                "color": "gold",
            },
            {
                "type": "link",
                "from": "body",
                "to": "right_heart",
                "arrow": True,
                "label": "deoxygenated blood",
            },
            {
                "type": "link",
                "from": "right_heart",
                "to": "lungs",
                "arrow": True,
                "label": "pulmonary artery",
            },
            {
                "type": "link",
                "from": "lungs",
                "to": "left_heart",
                "arrow": True,
                "label": "pulmonary veins",
            },
            {
                "type": "link",
                "from": "left_heart",
                "to": "body",
                "arrow": True,
                "label": "oxygenated blood",
            },
        ]
    if family == "spring_mass":
        return [
            {
                "type": "node",
                "id": "support",
                "x": 360,
                "y": 70,
                "width": 180,
                "height": 42,
                "label": "fixed support",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "mass",
                "x": 360,
                "y": 285,
                "width": 118,
                "height": 72,
                "label": "mass m = 2 kg",
                "color": "orange",
            },
            {
                "type": "link",
                "from": "support",
                "to": "mass",
                "arrow": False,
                "label": "spring k = 12 N/m",
            },
            {
                "type": "arrow",
                "from": [360, 285],
                "to": [360, 380],
                "label": "weight mg",
                "color": "purple",
            },
            {
                "type": "arrow",
                "from": [360, 285],
                "to": [360, 190],
                "label": "spring force kx",
                "color": "teal",
            },
            {
                "type": "arrow",
                "from": [485, 70],
                "to": [485, 285],
                "label": "equilibrium x=mg/k=1.64 m",
                "color": "gold",
            },
        ]
    if family == "pendulum":
        theta = math.radians(20)
        pivot = [310.0, 75.0]
        length = 185.0
        bob = [pivot[0] + length * math.sin(theta), pivot[1] + length * math.cos(theta)]
        arc = [
            [pivot[0] + 74 * math.sin(angle), pivot[1] + 74 * math.cos(angle)]
            for angle in [math.radians(-20 + index) for index in range(41)]
        ]
        return [
            {
                "type": "node",
                "id": "pivot",
                "x": pivot[0],
                "y": pivot[1],
                "width": 82,
                "height": 44,
                "label": "pivot",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "bob",
                "x": bob[0],
                "y": bob[1],
                "width": 76,
                "height": 62,
                "label": "bob",
                "color": "orange",
            },
            {"type": "link", "from": "pivot", "to": "bob", "arrow": False, "label": "L = 1.00 m"},
            {"type": "polyline", "label": "motion arc ±20°", "points": arc, "color": "purple"},
            {
                "type": "arrow",
                "from": bob,
                "to": [bob[0] - 70, bob[1] + 28],
                "label": "restoring component mg sinθ",
                "color": "gold",
            },
            {
                "type": "arrow",
                "from": [pivot[0], pivot[1]],
                "to": [pivot[0], pivot[1] + length],
                "label": "equilibrium",
                "color": "gray",
            },
        ]
    if family == "dna_replication":
        return [
            {
                "type": "node",
                "id": "fork",
                "x": 115,
                "y": 215,
                "width": 112,
                "height": 58,
                "label": "helicase fork",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "leading_primer",
                "x": 260,
                "y": 105,
                "width": 118,
                "height": 46,
                "label": "RNA primer",
                "color": "gold",
            },
            {
                "type": "node",
                "id": "leading",
                "x": 450,
                "y": 105,
                "width": 178,
                "height": 58,
                "label": "leading 5′→3′ continuous",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "lagging_primer",
                "x": 260,
                "y": 315,
                "width": 126,
                "height": 46,
                "label": "repeated RNA primers",
                "color": "gold",
            },
            {
                "type": "node",
                "id": "okazaki",
                "x": 455,
                "y": 315,
                "width": 174,
                "height": 58,
                "label": "Okazaki 5′→3′ fragments",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "ligase",
                "x": 630,
                "y": 315,
                "width": 112,
                "height": 48,
                "label": "ligase joins",
                "color": "blue",
            },
            {
                "type": "link",
                "from": "fork",
                "to": "leading_primer",
                "arrow": True,
                "label": "primer starts",
            },
            {
                "type": "link",
                "from": "leading_primer",
                "to": "leading",
                "arrow": True,
                "label": "polymerase 5′→3′",
            },
            {
                "type": "link",
                "from": "fork",
                "to": "lagging_primer",
                "arrow": True,
                "label": "fork exposes template",
            },
            {
                "type": "link",
                "from": "lagging_primer",
                "to": "okazaki",
                "arrow": True,
                "label": "polymerase 5′→3′",
            },
            {
                "type": "link",
                "from": "okazaki",
                "to": "ligase",
                "arrow": True,
                "label": "seal fragments",
            },
        ]
    if family == "nephron":
        segment_data = (
            ("glomerulus", 80, "glomerulus: filtration", "purple"),
            ("proximal", 205, "proximal: H₂O, Na⁺, glucose", "teal"),
            ("descending_loop", 330, "descending: H₂O", "blue"),
            ("ascending_loop", 455, "ascending: Na⁺; no water", "orange"),
            ("distal", 570, "distal: regulated Na⁺", "gold"),
            ("collecting", 660, "collecting: regulated H₂O", "purple"),
        )
        layers = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": 215 + (42 if index % 2 else -42),
                "width": 126,
                "height": 64,
                "label": label,
                "color": color,
            }
            for index, (node_id, x, label, color) in enumerate(segment_data)
        ]
        layers.extend(
            {
                "type": "link",
                "from": segment_data[index][0],
                "to": segment_data[index + 1][0],
                "arrow": True,
                "label": "filtrate",
            }
            for index in range(len(segment_data) - 1)
        )
        layers.extend(
            [
                {
                    "type": "node",
                    "id": "water_return",
                    "x": 245,
                    "y": 385,
                    "width": 116,
                    "height": 42,
                    "label": "H₂O → blood",
                    "color": "blue",
                },
                {
                    "type": "node",
                    "id": "sodium_return",
                    "x": 420,
                    "y": 385,
                    "width": 116,
                    "height": 42,
                    "label": "Na⁺ → blood",
                    "color": "orange",
                },
                {
                    "type": "node",
                    "id": "glucose_return",
                    "x": 595,
                    "y": 385,
                    "width": 126,
                    "height": 42,
                    "label": "glucose → blood",
                    "color": "gold",
                },
                {
                    "type": "link",
                    "from": "proximal",
                    "to": "water_return",
                    "arrow": True,
                    "label": "H₂O reabsorbed",
                },
                {
                    "type": "link",
                    "from": "descending_loop",
                    "to": "water_return",
                    "arrow": True,
                    "label": "H₂O reabsorbed",
                },
                {
                    "type": "link",
                    "from": "collecting",
                    "to": "water_return",
                    "arrow": True,
                    "label": "regulated H₂O",
                },
                {
                    "type": "link",
                    "from": "proximal",
                    "to": "sodium_return",
                    "arrow": True,
                    "label": "Na⁺ reabsorbed",
                },
                {
                    "type": "link",
                    "from": "ascending_loop",
                    "to": "sodium_return",
                    "arrow": True,
                    "label": "Na⁺ reabsorbed",
                },
                {
                    "type": "link",
                    "from": "distal",
                    "to": "sodium_return",
                    "arrow": True,
                    "label": "regulated Na⁺",
                },
                {
                    "type": "link",
                    "from": "proximal",
                    "to": "glucose_return",
                    "arrow": True,
                    "label": "glucose reabsorbed",
                },
            ]
        )
        return layers
    if family == "membrane_transport":
        return [
            {
                "type": "node",
                "id": "high",
                "x": 115,
                "y": 215,
                "width": 130,
                "height": 70,
                "label": "high concentration",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "diffusion",
                "x": 330,
                "y": 90,
                "width": 154,
                "height": 56,
                "label": "simple diffusion",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "facilitated",
                "x": 330,
                "y": 215,
                "width": 164,
                "height": 56,
                "label": "facilitated channel",
                "color": "blue",
            },
            {
                "type": "node",
                "id": "active",
                "x": 330,
                "y": 340,
                "width": 164,
                "height": 56,
                "label": "active pump + ATP",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "low",
                "x": 570,
                "y": 215,
                "width": 130,
                "height": 70,
                "label": "low concentration",
                "color": "gold",
            },
            {
                "type": "link",
                "from": "high",
                "to": "diffusion",
                "arrow": True,
                "label": "down gradient",
            },
            {
                "type": "link",
                "from": "diffusion",
                "to": "low",
                "arrow": True,
                "label": "no protein / ATP",
            },
            {
                "type": "link",
                "from": "high",
                "to": "facilitated",
                "arrow": True,
                "label": "down gradient",
            },
            {
                "type": "link",
                "from": "facilitated",
                "to": "low",
                "arrow": True,
                "label": "protein; no ATP",
            },
            {
                "type": "link",
                "from": "low",
                "to": "active",
                "arrow": True,
                "label": "against gradient",
            },
            {
                "type": "link",
                "from": "active",
                "to": "high",
                "arrow": True,
                "label": "ATP required",
            },
        ]
    if family == "hash_table":
        bucket_y = [80, 150, 220, 290, 360]
        layers = [
            {
                "type": "node",
                "id": "key",
                "x": 85,
                "y": 215,
                "width": 92,
                "height": 52,
                "label": "key 17",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "hash",
                "x": 225,
                "y": 215,
                "width": 118,
                "height": 52,
                "label": "h(k)=k mod 5",
                "color": "purple",
            },
        ]
        layers.extend(
            {
                "type": "node",
                "id": f"bucket{index}",
                "x": 405,
                "y": y,
                "width": 100,
                "height": 44,
                "label": f"bucket {index}",
                "color": "teal",
            }
            for index, y in enumerate(bucket_y)
        )
        layers.extend(
            [
                {
                    "type": "node",
                    "id": "chain_a",
                    "x": 535,
                    "y": 190,
                    "width": 116,
                    "height": 42,
                    "label": "chain key 2",
                    "color": "gold",
                },
                {
                    "type": "node",
                    "id": "chain_b",
                    "x": 650,
                    "y": 220,
                    "width": 88,
                    "height": 42,
                    "label": "key 7",
                    "color": "gold",
                },
                {
                    "type": "node",
                    "id": "chain_c",
                    "x": 535,
                    "y": 250,
                    "width": 88,
                    "height": 42,
                    "label": "key 12",
                    "color": "gold",
                },
                {
                    "type": "node",
                    "id": "chain_d",
                    "x": 650,
                    "y": 280,
                    "width": 106,
                    "height": 42,
                    "label": "insert key 17",
                    "color": "orange",
                },
                {
                    "type": "link",
                    "from": "key",
                    "to": "hash",
                    "arrow": True,
                    "label": "lookup / insert",
                },
                {
                    "type": "link",
                    "from": "hash",
                    "to": "bucket2",
                    "arrow": True,
                    "label": "17 mod 5 = 2",
                },
                {
                    "type": "link",
                    "from": "bucket2",
                    "to": "chain_a",
                    "arrow": True,
                    "label": "head",
                },
                {
                    "type": "link",
                    "from": "chain_a",
                    "to": "chain_b",
                    "arrow": True,
                    "label": "next",
                },
                {
                    "type": "link",
                    "from": "chain_b",
                    "to": "chain_c",
                    "arrow": True,
                    "label": "next",
                },
                {
                    "type": "link",
                    "from": "chain_c",
                    "to": "chain_d",
                    "arrow": True,
                    "label": "collision-chain tail",
                },
            ]
        )
        return layers
    if family == "graph_traversal":
        positions = {
            "A": (145, 215),
            "B": (300, 95),
            "C": (300, 335),
            "D": (480, 95),
            "E": (480, 335),
        }
        layers = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": 72,
                "height": 52,
                "label": node_id,
                "color": "teal",
            }
            for node_id, (x, y) in positions.items()
        ]
        for start, end in (("A", "B"), ("A", "C"), ("B", "D"), ("B", "E"), ("C", "E")):
            layers.append(
                {"type": "link", "from": start, "to": end, "arrow": False, "label": "edge"}
            )
        layers.append(
            {
                "type": "node",
                "id": "status",
                "x": 625,
                "y": 215,
                "width": 170,
                "height": 86,
                "label": "BFS frontier [A]; visited []",
                "color": "purple",
            }
        )
        return layers
    if family == "heap":
        requested = _number_list_from_request(request, maximum=6) or [1, 3, 5, 8, 9, 7]
        heap_values: list[float] = []
        for value in requested:
            heap_values.append(value)
            child = len(heap_values) - 1
            while child:
                parent = (child - 1) // 2
                if heap_values[parent] <= heap_values[child]:
                    break
                heap_values[parent], heap_values[child] = heap_values[child], heap_values[parent]
                child = parent
        node_layout = (
            ("root", 360, 75),
            ("left", 230, 190),
            ("right", 490, 190),
            ("left_left", 165, 315),
            ("left_right", 295, 315),
            ("right_left", 425, 315),
            ("right_right", 555, 315),
        )
        values = [(*node_layout[index], value) for index, value in enumerate(heap_values)]
        layers = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": 104 if index == 0 else 74,
                "height": 52,
                "label": f"minimum root {value:g}" if index == 0 else f"{value:g}",
                "color": "teal" if index else "gold",
            }
            for index, (node_id, x, y, value) in enumerate(values)
        ]
        if len(values) < len(node_layout):
            node_id, x, y = node_layout[len(values)]
            layers.append(
                {
                    "type": "node",
                    "id": node_id,
                    "x": x,
                    "y": y,
                    "width": 86,
                    "height": 52,
                    "label": "empty insert slot",
                    "color": "gray",
                }
            )
        ids = [record[0] for record in values]
        rendered_ids = [layer["id"] for layer in layers if layer["type"] == "node"]
        for child_index in range(1, len(rendered_ids)):
            label = "parent ≤ children" if child_index < len(ids) else "insertion position"
            layers.append(
                {
                    "type": "link",
                    "from": rendered_ids[(child_index - 1) // 2],
                    "to": rendered_ids[child_index],
                    "arrow": True,
                    "label": label,
                }
            )
        return layers
    if family == "energy_sankey":
        return [
            {
                "type": "node",
                "id": "input",
                "x": 115,
                "y": 215,
                "width": 190,
                "height": 104,
                "label": "100 J input",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "useful",
                "x": 560,
                "y": 100,
                "width": 160,
                "height": 70,
                "label": "65 J useful",
                "color": "gold",
            },
            {
                "type": "node",
                "id": "heat",
                "x": 560,
                "y": 225,
                "width": 126,
                "height": 58,
                "label": "26.25 J heat",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "sound",
                "x": 560,
                "y": 340,
                "width": 96,
                "height": 48,
                "label": "8.75 J sound",
                "color": "purple",
            },
            {"type": "link", "from": "input", "to": "useful", "arrow": True, "label": "65 J"},
            {"type": "link", "from": "input", "to": "heat", "arrow": True, "label": "26.25 J"},
            {"type": "link", "from": "input", "to": "sound", "arrow": True, "label": "8.75 J"},
        ]
    if family == "entropy_cycle":
        pv = (
            ("pv1", 120, 105, "P–V 1: hot isothermal"),
            ("pv2", 300, 105, "P–V 2: adiabatic expansion"),
            ("pv3", 300, 235, "P–V 3: cold isothermal"),
            ("pv4", 120, 235, "P–V 4: adiabatic compression"),
        )
        ts = (
            ("ts1", 430, 105, "T–S 1: hot isothermal"),
            ("ts2", 610, 105, "T–S 2: adiabatic expansion"),
            ("ts3", 610, 235, "T–S 3: cold isothermal"),
            ("ts4", 430, 235, "T–S 4: adiabatic compression"),
        )
        layers = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": 142,
                "height": 52,
                "label": label,
                "color": "teal" if node_id.startswith("pv") else "orange",
            }
            for node_id, x, y, label in (*pv, *ts)
        ]
        for prefix in ("pv", "ts"):
            for start, end, process in (
                (1, 2, "expansion"),
                (2, 3, "expansion"),
                (3, 4, "compression"),
                (4, 1, "compression"),
            ):
                layers.append(
                    {
                        "type": "link",
                        "from": f"{prefix}{start}",
                        "to": f"{prefix}{end}",
                        "arrow": True,
                        "label": process,
                    }
                )
        for state in range(1, 5):
            layers.append(
                {
                    "type": "link",
                    "from": f"pv{state}",
                    "to": f"ts{state}",
                    "arrow": False,
                    "label": "synchronized state",
                }
            )
        return layers
    if family == "electrochemical_cell":
        return [
            {
                "type": "node",
                "id": "anode",
                "x": 110,
                "y": 160,
                "width": 160,
                "height": 68,
                "label": "Zn anode: Zn → Zn²⁺ + 2e⁻",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "cathode",
                "x": 610,
                "y": 160,
                "width": 170,
                "height": 68,
                "label": "Cu cathode: Cu²⁺ + 2e⁻ → Cu",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "salt_bridge",
                "x": 360,
                "y": 300,
                "width": 180,
                "height": 58,
                "label": "salt bridge ion migration",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "voltage",
                "x": 360,
                "y": 80,
                "width": 150,
                "height": 52,
                "label": "E = 1.100 V",
                "color": "gold",
            },
            {
                "type": "link",
                "from": "anode",
                "to": "cathode",
                "arrow": True,
                "label": "electron flow",
            },
            {
                "type": "link",
                "from": "salt_bridge",
                "to": "anode",
                "arrow": True,
                "label": "NO₃⁻ anions migrate to anode",
            },
            {
                "type": "link",
                "from": "salt_bridge",
                "to": "cathode",
                "arrow": True,
                "label": "K⁺ cations migrate to cathode",
            },
            {
                "type": "link",
                "from": "voltage",
                "to": "cathode",
                "arrow": False,
                "label": "voltage readout",
            },
        ]
    if family == "merge_sort":
        values = _number_list_from_request(request) or [8, 3, 6, 2, 7, 1]

        def show(sequence: list[float]) -> str:
            return "[" + ",".join(f"{value:g}" for value in sequence) + "]"

        maximum_depth = max(1, math.ceil(math.log2(len(values))))
        layers: list[dict[str, Any]] = []
        internal: list[tuple[int, int, int, tuple[int, int], tuple[int, int]]] = []

        def centre(start: int, end: int) -> float:
            return 80 + 560 * ((start + end - 1) / 2) / max(1, len(values) - 1)

        def split(start: int, end: int, depth: int, node_id: str) -> None:
            segment = values[start:end]
            layers.append(
                {
                    "type": "node",
                    "id": node_id,
                    "x": centre(start, end),
                    "y": 45 + 55 * depth,
                    "width": max(82, min(180, 62 + 18 * len(segment))),
                    "height": 42,
                    "label": show(segment),
                    "color": "orange" if node_id == "input" else "teal",
                }
            )
            if end - start <= 1:
                return
            midpoint = (start + end + 1) // 2
            left = (start, midpoint)
            right = (midpoint, end)
            left_id = f"split_{start}_{midpoint}"
            right_id = f"split_{midpoint}_{end}"
            layers.extend(
                [
                    {
                        "type": "link",
                        "from": node_id,
                        "to": left_id,
                        "arrow": True,
                        "label": "recursive split",
                    },
                    {
                        "type": "link",
                        "from": node_id,
                        "to": right_id,
                        "arrow": True,
                        "label": "recursive split",
                    },
                ]
            )
            split(*left, depth + 1, left_id)
            split(*right, depth + 1, right_id)
            internal.append((start, end, depth, left, right))

        split(0, len(values), 0, "input")
        for start, end, depth, left, right in internal:
            merge_id = f"merge_{start}_{end}"
            left_id = (
                f"merge_{left[0]}_{left[1]}"
                if left[1] - left[0] > 1
                else f"split_{left[0]}_{left[1]}"
            )
            right_id = (
                f"merge_{right[0]}_{right[1]}"
                if right[1] - right[0] > 1
                else f"split_{right[0]}_{right[1]}"
            )
            layers.append(
                {
                    "type": "node",
                    "id": merge_id,
                    "x": centre(start, end),
                    "y": 285 + 48 * (maximum_depth - depth),
                    "width": max(100, min(210, 76 + 18 * (end - start))),
                    "height": 44,
                    "label": f"stable merge {show(sorted(values[start:end]))}",
                    "color": "purple",
                }
            )
            layers.extend(
                [
                    {
                        "type": "link",
                        "from": left_id,
                        "to": merge_id,
                        "arrow": True,
                        "label": "take smaller; left wins equal",
                    },
                    {
                        "type": "link",
                        "from": right_id,
                        "to": merge_id,
                        "arrow": True,
                        "label": "take smaller; left wins equal",
                    },
                ]
            )
        tagged = ",".join(
            f"{value:g}@{index}"
            for value, index in sorted((value, index) for index, value in enumerate(values))
        )
        root_merge = f"merge_0_{len(values)}" if len(values) > 1 else "input"
        layers.extend(
            [
                {
                    "type": "node",
                    "id": "output",
                    "x": 360,
                    "y": 500,
                    "width": 240,
                    "height": 46,
                    "label": f"sorted output {show(sorted(values))}",
                    "color": "gold",
                },
                {
                    "type": "node",
                    "id": "stability",
                    "x": 360,
                    "y": 550,
                    "width": 330,
                    "height": 40,
                    "label": f"stable identities {tagged}",
                    "color": "blue",
                },
                {
                    "type": "link",
                    "from": root_merge,
                    "to": "output",
                    "arrow": True,
                    "label": "stable output preserves original equal-key order",
                },
                {
                    "type": "link",
                    "from": "output",
                    "to": "stability",
                    "arrow": True,
                    "label": "audit equal-key origin order",
                },
            ]
        )
        return layers
    if family == "recursion_stack":
        match = re.search(r"factorial\s*\(\s*(\d+)\s*\)", request, re.IGNORECASE)
        maximum = min(8, max(1, int(match.group(1)))) if match else 5
        spacing = 540 / max(1, maximum - 1)
        calls = [
            (f"call{value}", 90 + (maximum - value) * spacing, 105, f"factorial({value})")
            for value in range(maximum, 0, -1)
        ]
        returns = [
            (f"return{value}", 90 + (value - 1) * spacing, 305, f"return {math.factorial(value)}")
            for value in range(1, maximum + 1)
        ]
        layers = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": 98,
                "height": 48,
                "label": label,
                "color": "teal" if node_id.startswith("call") else "orange",
            }
            for node_id, x, y, label in (*calls, *returns)
        ]
        for value in range(maximum, 1, -1):
            layers.append(
                {
                    "type": "link",
                    "from": f"call{value}",
                    "to": f"call{value - 1}",
                    "arrow": True,
                    "label": "recursive descent: push frame",
                }
            )
        layers.append(
            {"type": "link", "from": "call1", "to": "return1", "arrow": True, "label": "base case"}
        )
        for value in range(1, maximum):
            layers.append(
                {
                    "type": "link",
                    "from": f"return{value}",
                    "to": f"return{value + 1}",
                    "arrow": True,
                    "label": "return-value unwind: pop × caller n",
                }
            )
        return layers
    if family == "virtual_memory":
        return [
            {
                "type": "node",
                "id": "virtual",
                "x": 80,
                "y": 150,
                "width": 140,
                "height": 58,
                "label": "virtual address: page 2, offset 5",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "tlb",
                "x": 235,
                "y": 100,
                "width": 104,
                "height": 48,
                "label": "TLB",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "page_table",
                "x": 370,
                "y": 150,
                "width": 126,
                "height": 58,
                "label": "page table",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "frame",
                "x": 540,
                "y": 100,
                "width": 142,
                "height": 48,
                "label": "physical frame 7, offset 5",
                "color": "gold",
            },
            {
                "type": "node",
                "id": "storage",
                "x": 370,
                "y": 315,
                "width": 122,
                "height": 52,
                "label": "backing storage",
                "color": "blue",
            },
            {
                "type": "node",
                "id": "replacement",
                "x": 555,
                "y": 315,
                "width": 150,
                "height": 52,
                "label": "replace frame → retry",
                "color": "red",
            },
            {"type": "link", "from": "virtual", "to": "tlb", "arrow": True, "label": "TLB miss"},
            {
                "type": "link",
                "from": "tlb",
                "to": "page_table",
                "arrow": True,
                "label": "page-table lookup",
            },
            {
                "type": "link",
                "from": "page_table",
                "to": "frame",
                "arrow": True,
                "label": "resident hit",
            },
            {
                "type": "link",
                "from": "page_table",
                "to": "storage",
                "arrow": True,
                "label": "page fault",
            },
            {
                "type": "link",
                "from": "storage",
                "to": "replacement",
                "arrow": True,
                "label": "page-in replacement",
            },
            {
                "type": "link",
                "from": "replacement",
                "to": "frame",
                "arrow": True,
                "label": "preserve offset",
            },
        ]
    if family == "state_machine":
        return [
            {
                "type": "node",
                "id": "red",
                "x": 190,
                "y": 95,
                "width": 110,
                "height": 58,
                "label": "red",
                "color": "red",
            },
            {
                "type": "node",
                "id": "red_amber",
                "x": 530,
                "y": 95,
                "width": 130,
                "height": 58,
                "label": "red + amber",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "green",
                "x": 530,
                "y": 300,
                "width": 110,
                "height": 58,
                "label": "green",
                "color": "green",
            },
            {
                "type": "node",
                "id": "amber",
                "x": 190,
                "y": 300,
                "width": 130,
                "height": 58,
                "label": "amber",
                "color": "gold",
            },
            {"type": "link", "from": "red", "to": "red_amber", "arrow": True, "label": "timer"},
            {"type": "link", "from": "red_amber", "to": "green", "arrow": True, "label": "timer"},
            {
                "type": "link",
                "from": "green",
                "to": "amber",
                "arrow": True,
                "label": "timer / pedestrian request",
            },
            {"type": "link", "from": "amber", "to": "red", "arrow": True, "label": "timer"},
        ]
    if family == "backprop_graph":
        power_match = re.search(r"\)\s*(?:\^|\*\*)\s*(\d+)", request)
        power = min(5, max(2, int(power_match.group(1)))) if power_match else 2
        y_value, derivative = 5**power, power * 5 ** (power - 1)
        return [
            {
                "type": "node",
                "id": "inputs",
                "x": 85,
                "y": 205,
                "width": 128,
                "height": 58,
                "label": "w=1, x=2, b=3",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "u",
                "x": 245,
                "y": 205,
                "width": 118,
                "height": 58,
                "label": "u=wx+b=5",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "y",
                "x": 390,
                "y": 205,
                "width": 104,
                "height": 58,
                "label": f"y=u^{power}={y_value}",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "grad_u",
                "x": 535,
                "y": 205,
                "width": 148,
                "height": 58,
                "label": f"reverse gradient ∂y/∂u={derivative}",
                "color": "gold",
            },
            {
                "type": "node",
                "id": "grad_w",
                "x": 650,
                "y": 95,
                "width": 112,
                "height": 48,
                "label": f"∂y/∂w={derivative * 2}",
                "color": "blue",
            },
            {
                "type": "node",
                "id": "grad_x",
                "x": 650,
                "y": 205,
                "width": 112,
                "height": 48,
                "label": f"∂y/∂x={derivative}",
                "color": "blue",
            },
            {
                "type": "node",
                "id": "grad_b",
                "x": 650,
                "y": 315,
                "width": 112,
                "height": 48,
                "label": f"∂y/∂b={derivative}",
                "color": "blue",
            },
            {"type": "link", "from": "inputs", "to": "u", "arrow": True, "label": "forward"},
            {"type": "link", "from": "u", "to": "y", "arrow": True, "label": f"power {power}"},
            {"type": "link", "from": "y", "to": "grad_u", "arrow": True, "label": "reverse"},
            {"type": "link", "from": "grad_u", "to": "grad_w", "arrow": True, "label": "× x"},
            {"type": "link", "from": "grad_u", "to": "grad_x", "arrow": True, "label": "× w"},
            {"type": "link", "from": "grad_u", "to": "grad_b", "arrow": True, "label": "× 1"},
        ]
    if family == "inclined_plane":
        theta = math.radians(30)
        tangent = [math.cos(theta), -math.sin(theta)]
        normal = [-math.sin(theta), -math.cos(theta)]
        plane_start = [90.0, 345.0]
        contact = [
            plane_start[0] + 300 * tangent[0],
            plane_start[1] + 300 * tangent[1],
        ]
        origin = [contact[0] + 36 * normal[0], contact[1] + 36 * normal[1]]
        acceleration = max(0.0, 9.81 * (math.sin(theta) - 0.2 * math.cos(theta)))
        return [
            {
                "type": "arrow",
                "from": plane_start,
                "to": [plane_start[0] + 560 * tangent[0], plane_start[1] + 560 * tangent[1]],
                "label": "inclined plane θ=30°",
                "color": "gray",
            },
            {
                "type": "rect",
                "x": origin[0] - 52.5,
                "y": origin[1] - 34,
                "width": 105,
                "height": 68,
                "label": "box",
                "color": "orange",
            },
            {
                "type": "arrow",
                "from": origin,
                "to": [origin[0], origin[1] + 120],
                "label": "weight mg",
                "color": "purple",
            },
            {
                "type": "arrow",
                "from": origin,
                "to": [origin[0] + 105 * normal[0], origin[1] + 105 * normal[1]],
                "label": "normal N=mg cosθ",
                "color": "teal",
            },
            {
                "type": "arrow",
                "from": origin,
                "to": [origin[0] + 90 * tangent[0], origin[1] + 90 * tangent[1]],
                "label": "friction μN, μ=0.2",
                "color": "gold",
            },
            {
                "type": "arrow",
                "from": origin,
                "to": [origin[0] - 95 * tangent[0], origin[1] - 95 * tangent[1]],
                "label": f"resultant a={acceleration:.2f} m/s² down plane",
                "color": "red",
            },
        ]
    if family == "elastic_collision":
        return [
            {
                "type": "node",
                "id": "before_1",
                "x": 150,
                "y": 135,
                "width": 110,
                "height": 58,
                "label": "cart 1 before",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "before_2",
                "x": 360,
                "y": 135,
                "width": 110,
                "height": 58,
                "label": "cart 2 before",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "after_1",
                "x": 360,
                "y": 315,
                "width": 110,
                "height": 58,
                "label": "cart 1 after",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "after_2",
                "x": 570,
                "y": 315,
                "width": 110,
                "height": 58,
                "label": "cart 2 after",
                "color": "orange",
            },
            {"type": "arrow", "from": [150, 90], "to": [230, 90], "label": "u₁", "color": "teal"},
            {"type": "arrow", "from": [360, 90], "to": [320, 90], "label": "u₂", "color": "orange"},
            {"type": "arrow", "from": [360, 370], "to": [320, 370], "label": "v₁", "color": "teal"},
            {
                "type": "arrow",
                "from": [570, 370],
                "to": [650, 370],
                "label": "v₂",
                "color": "orange",
            },
        ]
    if family == "atom":
        turns = [2 * math.pi * index / 96 for index in range(97)]
        layers: list[dict[str, Any]] = [
            {
                "type": "polyline",
                "label": f"electron shell {shell}",
                "points": [[shell * math.cos(turn), shell * math.sin(turn)] for turn in turns],
                "color": ("teal", "orange", "purple")[shell - 1],
            }
            for shell in (1, 2, 3)
        ]
        layers.extend(
            [
                {
                    "type": "particles",
                    "points": [[0, 0], [0.08, 0]],
                    "label": "nuclear protons Z",
                    "color": "red",
                },
                {
                    "type": "particles",
                    "points": [[0, 0.08], [0.08, 0.08]],
                    "label": "nuclear neutrons N≈Z",
                    "color": "gold",
                },
                {
                    "type": "particles",
                    "points": [
                        [math.cos(2 * math.pi * index / 6), math.sin(2 * math.pi * index / 6)]
                        for index in range(6)
                    ],
                    "label": "electrons arranged by atomic number",
                    "color": "blue",
                },
            ]
        )
        return layers
    if family == "animal_cell":
        organelles = (
            ("membrane", 360, 215, 470, 310, "cell membrane", "teal"),
            ("nucleus", 300, 205, 128, 96, "nucleus: stores DNA", "purple"),
            ("mitochondrion", 470, 150, 132, 62, "mitochondrion: makes ATP", "orange"),
            ("ribosome", 475, 275, 106, 48, "ribosome: builds proteins", "gold"),
            ("rough_er", 215, 130, 118, 58, "rough ER: folds proteins", "blue"),
            ("golgi", 220, 300, 110, 58, "Golgi: sorts cargo", "orange"),
            ("lysosome", 390, 335, 106, 48, "lysosome: digests waste", "red"),
        )
        return [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "label": label,
                "color": color,
            }
            for node_id, x, y, width, height, label, color in organelles
        ]
    if family == "molecular_orbitals":
        return [
            {
                "type": "node",
                "id": "h_left",
                "x": 120,
                "y": 215,
                "width": 100,
                "height": 58,
                "label": "H 1s(A)",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "bonding",
                "x": 320,
                "y": 125,
                "width": 150,
                "height": 68,
                "label": "σ1s bonding: in phase",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "antibonding",
                "x": 320,
                "y": 305,
                "width": 170,
                "height": 68,
                "label": "σ*1s antibonding: node",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "h_right",
                "x": 560,
                "y": 215,
                "width": 100,
                "height": 58,
                "label": "H 1s(B)",
                "color": "teal",
            },
            {
                "type": "link",
                "from": "h_left",
                "to": "bonding",
                "arrow": True,
                "label": "constructive overlap",
            },
            {
                "type": "link",
                "from": "h_right",
                "to": "bonding",
                "arrow": True,
                "label": "lower energy",
            },
            {
                "type": "link",
                "from": "h_left",
                "to": "antibonding",
                "arrow": True,
                "label": "destructive overlap",
            },
            {
                "type": "link",
                "from": "h_right",
                "to": "antibonding",
                "arrow": True,
                "label": "higher energy",
            },
        ]
    if family == "ionic_bond":
        return [
            {
                "type": "node",
                "id": "sodium",
                "x": 125,
                "y": 215,
                "width": 120,
                "height": 64,
                "label": "Na: 2,8,1",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "electron",
                "x": 260,
                "y": 145,
                "width": 80,
                "height": 48,
                "label": "e⁻ transfer",
                "color": "gold",
            },
            {
                "type": "node",
                "id": "chlorine",
                "x": 500,
                "y": 215,
                "width": 120,
                "height": 64,
                "label": "Cl: 2,8,7",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "ions",
                "x": 360,
                "y": 345,
                "width": 180,
                "height": 58,
                "label": "Na⁺ attracts Cl⁻",
                "color": "purple",
            },
            {
                "type": "link",
                "from": "sodium",
                "to": "electron",
                "arrow": True,
                "label": "loses one electron",
            },
            {
                "type": "link",
                "from": "electron",
                "to": "chlorine",
                "arrow": True,
                "label": "gains one electron",
            },
            {
                "type": "link",
                "from": "chlorine",
                "to": "ions",
                "arrow": True,
                "label": "electrostatic attraction",
            },
        ]
    if family == "cpu_memory":
        return [
            {
                "type": "node",
                "id": "cpu",
                "x": 90,
                "y": 165,
                "width": 105,
                "height": 58,
                "label": "CPU request",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "cache",
                "x": 245,
                "y": 165,
                "width": 120,
                "height": 58,
                "label": "registers / cache",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "ram",
                "x": 420,
                "y": 165,
                "width": 110,
                "height": 58,
                "label": "RAM lookup",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "ssd",
                "x": 600,
                "y": 165,
                "width": 110,
                "height": 58,
                "label": "SSD storage",
                "color": "blue",
            },
            {
                "type": "node",
                "id": "retry",
                "x": 340,
                "y": 330,
                "width": 180,
                "height": 58,
                "label": "load page → retry CPU",
                "color": "gold",
            },
            {"type": "link", "from": "cpu", "to": "cache", "arrow": True, "label": "cache miss"},
            {"type": "link", "from": "cache", "to": "ram", "arrow": True, "label": "memory lookup"},
            {"type": "link", "from": "ram", "to": "ssd", "arrow": True, "label": "page fault"},
            {"type": "link", "from": "ssd", "to": "retry", "arrow": True, "label": "page-in"},
            {"type": "link", "from": "retry", "to": "cpu", "arrow": True, "label": "resume"},
        ]
    if family == "dijkstra":
        positions = {
            "A": (100, 210),
            "B": (255, 95),
            "C": (255, 315),
            "D": (430, 95),
            "E": (430, 315),
            "F": (610, 210),
        }
        layers: list[dict[str, Any]] = [
            {
                "type": "node",
                "id": node_id,
                "x": x,
                "y": y,
                "width": 74,
                "height": 58,
                "label": node_id,
                "color": "teal",
            }
            for node_id, (x, y) in positions.items()
        ]
        for start, end, weight in (
            ("A", "B", 4),
            ("A", "C", 2),
            ("B", "C", 1),
            ("B", "D", 5),
            ("C", "D", 8),
            ("C", "E", 10),
            ("D", "E", 2),
            ("D", "F", 6),
            ("E", "F", 3),
        ):
            layers.append(
                {"type": "link", "from": start, "to": end, "arrow": False, "label": str(weight)}
            )
        return layers
    if family == "benzene":
        positions = [
            (360 + 150 * math.cos(math.pi / 3 * index), 215 + 150 * math.sin(math.pi / 3 * index))
            for index in range(6)
        ]
        layers = [
            {
                "type": "node",
                "id": f"c{index + 1}",
                "x": x,
                "y": y,
                "width": 68,
                "height": 52,
                "label": f"C{index + 1}",
                "color": "teal",
            }
            for index, (x, y) in enumerate(positions)
        ]
        for index in range(6):
            layers.append(
                {
                    "type": "link",
                    "from": f"c{index + 1}",
                    "to": f"c{(index + 1) % 6 + 1}",
                    "arrow": False,
                    "label": "alternating / delocalized" if index == 0 else "",
                }
            )
        return layers
    if family == "refraction":
        centre = (360.0, 210.0)
        incident = math.radians(35)
        refracted = math.asin(math.sin(incident) / 1.5)
        positions = [
            (centre[0] - 180 * math.sin(incident), centre[1] - 180 * math.cos(incident)),
            centre,
            (centre[0] + 180 * math.sin(refracted), centre[1] + 180 * math.cos(refracted)),
            (555.0, 90.0),
        ]
        labels = ("incident ray", "normal / interface", "refracted ray", "n₁ sin θ₁ = n₂ sin θ₂")
        layers = [
            {
                "type": "node",
                "id": f"n{index}",
                "x": x,
                "y": y,
                "width": 150,
                "height": 50,
                "label": label,
                "color": ("orange", "teal", "purple", "blue")[index],
            }
            for index, ((x, y), label) in enumerate(zip(positions, labels))
        ]
        layers.extend(
            [
                {"type": "link", "from": "n0", "to": "n1", "arrow": True, "label": "air"},
                {"type": "link", "from": "n1", "to": "n2", "arrow": True, "label": "glass"},
                {"type": "link", "from": "n1", "to": "n3", "arrow": False, "label": "Snell's law"},
            ]
        )
        return layers
    if family == "converging_lens":
        return [
            {
                "type": "node",
                "id": "object",
                "x": 160,
                "y": 150,
                "width": 116,
                "height": 46,
                "label": "object",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "lens",
                "x": 360,
                "y": 230,
                "width": 54,
                "height": 190,
                "label": "convex lens",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "focal_left",
                "x": 280,
                "y": 230,
                "width": 58,
                "height": 38,
                "label": "F",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "focal_right",
                "x": 440,
                "y": 230,
                "width": 58,
                "height": 38,
                "label": "F′",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "image",
                "x": 493.333333,
                "y": 283.333333,
                "width": 116,
                "height": 46,
                "label": "real inverted image",
                "color": "blue",
            },
            {
                "type": "arrow",
                "from": [70, 230],
                "to": [650, 230],
                "label": "principal axis",
                "color": "gray",
            },
            {
                "type": "arrow",
                "from": [160, 150],
                "to": [360, 150],
                "label": "parallel incident ray",
                "color": "orange",
            },
            {
                "type": "arrow",
                "from": [360, 150],
                "to": [493.333333, 283.333333],
                "label": "refracts through F′",
                "color": "orange",
            },
            {
                "type": "arrow",
                "from": [160, 150],
                "to": [360, 230],
                "label": "central ray",
                "color": "purple",
            },
            {
                "type": "arrow",
                "from": [360, 230],
                "to": [493.333333, 283.333333],
                "label": "central ray undeviated",
                "color": "purple",
            },
        ]
    if family == "robot_arm":
        return [
            {
                "type": "node",
                "id": "base",
                "x": 240,
                "y": 330,
                "width": 92,
                "height": 54,
                "label": "base",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "elbow",
                "x": 276.334,
                "y": 184.467,
                "width": 88,
                "height": 50,
                "label": "elbow-up",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "end_effector",
                "x": 402.5,
                "y": 232.5,
                "width": 126,
                "height": 50,
                "label": "end effector (2.50, 1.50)",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "target",
                "x": 402.5,
                "y": 232.5,
                "width": 62,
                "height": 38,
                "label": "target ×",
                "color": "blue",
            },
            {"type": "link", "from": "base", "to": "elbow", "arrow": False, "label": "L₁ = 150 px"},
            {
                "type": "link",
                "from": "elbow",
                "to": "end_effector",
                "arrow": False,
                "label": "L₂ = 135 px",
            },
        ]
    if family == "kalman_filter":
        return [
            {
                "type": "node",
                "id": "prior",
                "x": 260,
                "y": 145,
                "width": 132.912,
                "height": 70,
                "label": "prior x=2, P⁻=2.00",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "measurement",
                "x": 540,
                "y": 145,
                "width": 118,
                "height": 60,
                "label": "measurement z=6, R=1.00",
                "color": "purple",
            },
            {
                "type": "node",
                "id": "estimate",
                "x": 446.667,
                "y": 295,
                "width": 111.394,
                "height": 50,
                "label": "update x=4.67, P=0.67",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "timeline",
                "x": 360,
                "y": 390,
                "width": 250,
                "height": 42,
                "label": "predict → measure → update",
                "color": "blue",
            },
            {
                "type": "link",
                "from": "prior",
                "to": "estimate",
                "arrow": True,
                "label": "prediction",
            },
            {
                "type": "link",
                "from": "measurement",
                "to": "estimate",
                "arrow": True,
                "label": "innovation",
            },
            {
                "type": "link",
                "from": "estimate",
                "to": "timeline",
                "arrow": True,
                "label": "posterior",
            },
        ]
    if family == "truss":
        return [
            {
                "type": "node",
                "id": "left_support",
                "x": 160,
                "y": 330,
                "width": 116,
                "height": 52,
                "label": "pin support",
                "color": "teal",
            },
            {
                "type": "node",
                "id": "apex",
                "x": 360,
                "y": 100,
                "width": 92,
                "height": 48,
                "label": "50 kN joint load",
                "color": "orange",
            },
            {
                "type": "node",
                "id": "right_support",
                "x": 560,
                "y": 330,
                "width": 116,
                "height": 52,
                "label": "roller support",
                "color": "teal",
            },
            {
                "type": "link",
                "from": "left_support",
                "to": "apex",
                "arrow": False,
                "label": "compression 33.1 kN",
            },
            {
                "type": "link",
                "from": "apex",
                "to": "right_support",
                "arrow": False,
                "label": "compression 33.1 kN",
            },
            {
                "type": "link",
                "from": "left_support",
                "to": "right_support",
                "arrow": False,
                "label": "tension 22.0 kN",
            },
            {
                "type": "arrow",
                "from": [360, 30],
                "to": [360, 88],
                "label": "50 kN downward",
                "color": "orange",
            },
            {
                "type": "arrow",
                "from": [160, 395],
                "to": [160, 345],
                "label": "25 kN reaction",
                "color": "purple",
            },
            {
                "type": "arrow",
                "from": [560, 395],
                "to": [560, 345],
                "label": "25 kN reaction",
                "color": "purple",
            },
        ]
    labels = _FAMILY_LABELS.get(family)
    if labels is None:
        words = [word for word in family.replace("_", " ").title().split() if word]
        labels = ("Input", " ".join(words) or "Concept", "Relationship", "Outcome")
    count = len(labels)
    cyclic = {"circulation", "mitosis", "state_machine", "entropy_cycle"}
    tree = {"binary_search_tree", "heap", "dijkstra", "graph_traversal"}
    radial = {"atom", "animal_cell", "benzene", "molecular_orbitals"}
    loop = {"ohms_law_circuit", "series_parallel_circuit", "electrochemical_cell"}
    if family in cyclic:
        positions = [(180, 120), (540, 120), (540, 290), (180, 290), (360, 360)][:count]
    elif family in tree:
        positions = [
            (360, 90),
            (210, 210),
            (510, 210),
            (120, 330),
            (300, 330),
            (450, 330),
            (600, 330),
        ][:count]
    elif family in radial:
        angles = [2 * math.pi * index / max(1, count) for index in range(count)]
        positions = [(360 + 210 * math.cos(angle), 215 + 135 * math.sin(angle)) for angle in angles]
    elif family in loop:
        positions = [(160, 120), (560, 120), (560, 300), (160, 300)][:count]
    elif family in {"inclined_plane", "pendulum", "spring_mass", "triangle_angles"}:
        positions = [(130, 330), (280, 245), (430, 160), (590, 265)][:count]
    else:
        positions = [
            (80 + index * (560 / max(1, count - 1)), 205 + (35 if index % 2 else -35))
            for index in range(count)
        ]
    layers: list[dict[str, Any]] = []
    for index, (label, (x, y)) in enumerate(zip(labels, positions)):
        layers.append(
            {
                "type": "node",
                "id": f"n{index}",
                "x": x,
                "y": y,
                "width": 130,
                "height": 58,
                "label": label,
                "color": ["teal", "orange", "purple", "blue"][index % 4],
            }
        )
        if index:
            layers.append(
                {
                    "type": "link",
                    "from": f"n{index - 1}",
                    "to": f"n{index}",
                    "arrow": True,
                    "label": "",
                }
            )
    if family in cyclic | loop and count > 2:
        layers.append(
            {
                "type": "link",
                "from": f"n{count - 1}",
                "to": "n0",
                "arrow": True,
                "label": "cycle" if family in cyclic else "return path",
            }
        )
    if family in tree and count >= 4:
        # Replace the chain with a branching hierarchy while retaining the same safe primitives.
        layers = [layer for layer in layers if layer["type"] != "link"]
        edges = [(0, 1), (0, 2), (1, 3)]
        if count > 4:
            edges.extend((1, 4), (2, 5), (2, 6))
        for start, end in edges:
            if end < count:
                layers.append(
                    {
                        "type": "link",
                        "from": f"n{start}",
                        "to": f"n{end}",
                        "arrow": True,
                        "label": "",
                    }
                )
    if family in radial and count > 2:
        layers = [layer for layer in layers if layer["type"] != "link"]
        for index in range(1, count):
            layers.append(
                {
                    "type": "link",
                    "from": "n0",
                    "to": f"n{index}",
                    "arrow": family != "benzene",
                    "label": "",
                }
            )
        if family == "benzene":
            for index in range(count):
                layers.append(
                    {
                        "type": "link",
                        "from": f"n{index}",
                        "to": f"n{(index + 1) % count}",
                        "arrow": False,
                        "label": "",
                    }
                )
    return layers


def _plane_layers_from_request(request: str) -> list[dict[str, Any]] | None:
    """Extract two independent linear planes and their exact intersection line."""
    candidates: list[str] = []
    candidates.extend(re.findall(r"\[([^\[\]]*=[^\[\]]*)\]", request, re.DOTALL))
    for segment in re.split(r"\band\b|[;\n]", request, flags=re.IGNORECASE):
        if "=" not in segment:
            continue
        match = re.search(
            r"(?<![A-Za-z0-9_.])([+\-]?\s*(?:(?:\d+(?:\.\d+)?)\s*\*?\s*)?"
            r"[xyz](?![A-Za-z])[^=]*=.*)$",
            segment.strip().strip("[]() `\"'"),
            re.IGNORECASE,
        )
        if match:
            candidates.append(match.group(1))

    planes: list[tuple[list[float], float, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            normalized = normalize_relationship(candidate)
            if normalized in seen:
                continue
            seen.add(normalized)
            relationship = parse_relationship(normalized)
            origin = relationship_residual(relationship, {"x": 0, "y": 0, "z": 0})
            normal = [
                relationship_residual(
                    relationship,
                    {"x": float(axis == 0), "y": float(axis == 1), "z": float(axis == 2)},
                )
                - origin
                for axis in range(3)
            ]
            if sum(value * value for value in normal) < 1e-12:
                continue
            # Reject nonlinear equations rather than drawing a plausible but wrong plane.
            for point in ((2.0, -1.0, 0.5), (-0.5, 1.5, -2.0)):
                actual = relationship_residual(
                    relationship, {"x": point[0], "y": point[1], "z": point[2]}
                )
                linear = origin + sum(normal[index] * point[index] for index in range(3))
                if abs(actual - linear) > 1e-8 * (1 + abs(actual)):
                    raise VisualizationV2Error("plane equation must be linear")
            planes.append((normal, -origin, normalized))
        except (VisualizationV2Error, ValueError, OverflowError):
            continue
        if len(planes) == 2:
            break
    if len(planes) != 2:
        return None

    first, second = planes
    n1, d1, label1 = first
    n2, d2, label2 = second
    direction = [
        n1[1] * n2[2] - n1[2] * n2[1],
        n1[2] * n2[0] - n1[0] * n2[2],
        n1[0] * n2[1] - n1[1] * n2[0],
    ]
    direction_norm = math.sqrt(sum(value * value for value in direction))
    if direction_norm < 1e-9:
        return None
    gram11 = sum(value * value for value in n1)
    gram12 = sum(n1[index] * n2[index] for index in range(3))
    gram22 = sum(value * value for value in n2)
    determinant = gram11 * gram22 - gram12 * gram12
    if abs(determinant) < 1e-12:
        return None
    alpha = (d1 * gram22 - d2 * gram12) / determinant
    beta = (d2 * gram11 - d1 * gram12) / determinant
    point = [alpha * n1[index] + beta * n2[index] for index in range(3)]
    unit = [value / direction_norm for value in direction]
    endpoints = [[point[index] + sign * 3 * unit[index] for index in range(3)] for sign in (-1, 1)]
    return [
        {"type": "plane", "normal": n1, "constant": d1, "label": label1, "color": "teal"},
        {"type": "plane", "normal": n2, "constant": d2, "label": label2, "color": "orange"},
        {"type": "line", "points": endpoints, "label": "intersection", "color": "purple"},
    ]


def _three_composition(family: str, request: str = "") -> list[dict[str, Any]]:
    if family == "vector_field_3d":
        layers: list[dict[str, Any]] = []
        for x in (-2.0, 0.0, 2.0):
            for y in (-2.0, 0.0, 2.0):
                for z in (-2.0, 0.0, 2.0):
                    vector = (-y, x, z)
                    magnitude = math.sqrt(sum(value * value for value in vector))
                    if magnitude < 1e-9:
                        continue
                    scale_value = 0.72 / magnitude
                    layers.append(
                        {
                            "type": "vector",
                            "from": [x, y, z],
                            "to": [
                                x + vector[0] * scale_value,
                                y + vector[1] * scale_value,
                                z + vector[2] * scale_value,
                            ],
                            "label": "sampled F=(-y,x,z)",
                            "color": "teal",
                        }
                    )
        layers.extend(
            [
                {
                    "type": "point",
                    "position": [1, 1, 1],
                    "size": 0.18,
                    "label": "selected point (1,1,1)",
                    "color": "gold",
                },
                {
                    "type": "vector",
                    "from": [1, 1, 1],
                    "to": [0.4, 1.6, 1.6],
                    "label": "local F=(-1,1,1)",
                    "color": "purple",
                },
            ]
        )
        return layers
    if family == "lorenz_attractor":
        sigma, rho, beta, dt = 10.0, 28.0, 8 / 3, 0.01
        x, y, z = 0.1, 0.0, 0.0
        points: list[list[float]] = []
        for step in range(620):
            dx = sigma * (y - x)
            dy = x * (rho - z) - y
            dz = x * y - beta * z
            x += dt * dx
            y += dt * dy
            z += dt * dz
            if step >= 120:
                points.append([x / 7, y / 7, (z - 24) / 7])
        return [
            {
                "type": "line",
                "points": points,
                "label": "Lorenz trajectory σ=10, ρ=28, β=8/3",
                "color": "orange",
            },
            {
                "type": "point",
                "position": points[-1],
                "size": 0.18,
                "label": "current state",
                "color": "gold",
            },
        ]
    if family == "electromagnetic_wave":
        samples = [-4 + 8 * index / 160 for index in range(161)]
        electric = [[x, math.sin(2 * math.pi * x / 3), 0] for x in samples]
        magnetic = [[x, 0, math.sin(2 * math.pi * x / 3)] for x in samples]
        return [
            {
                "type": "line",
                "points": electric,
                "label": "electric field E ⟂ propagation",
                "color": "orange",
            },
            {
                "type": "line",
                "points": magnetic,
                "label": "magnetic field B ⟂ E",
                "color": "teal",
            },
            {
                "type": "vector",
                "from": [-4, -1.6, -1.6],
                "to": [4, -1.6, -1.6],
                "label": "propagation k = E×B",
                "color": "purple",
            },
        ]
    if family == "molecular_geometry":
        return [
            {
                "type": "sphere",
                "position": [0, 0, 0],
                "size": 0.55,
                "label": "central atom",
                "color": "purple",
            },
            *[
                {"type": "vector", "from": [0, 0, 0], "to": point, "label": "bond", "color": "teal"}
                for point in ([2, 0, 0], [-2, 0, 0], [0, 2, 0], [0, -2, 0], [0, 0, 2], [0, 0, -2])
            ],
            {
                "type": "point",
                "position": [0, 0, 1.35],
                "size": 0.24,
                "label": "lone pair 1",
                "color": "gold",
            },
            {
                "type": "point",
                "position": [0, 0, -1.35],
                "size": 0.24,
                "label": "lone pair 2",
                "color": "gold",
            },
        ]
    if family == "plane_intersection":
        return _plane_layers_from_request(request) or []
    if family == "parametric_surface":
        return [
            {
                "type": "parametric_surface",
                "x_expression": parse_expression_v2("(1+(v/2)*cos(u/2))*cos(u)"),
                "y_expression": parse_expression_v2("(1+(v/2)*cos(u/2))*sin(u)"),
                "z_expression": parse_expression_v2("(v/2)*sin(u/2)"),
                "u_domain": [0, 6.283185],
                "v_domain": [-1, 1],
                "resolution": [64, 16],
                "label": "Möbius strip",
            }
        ]
    if family == "lorentz_force":
        points = [
            [2 * math.cos(t), t / 3 - 3, 2 * math.sin(t)]
            for t in [index * 0.16 for index in range(40)]
        ]
        return [
            {
                "type": "line",
                "points": points,
                "label": "charged-particle helix",
                "color": "orange",
            },
            {
                "type": "vector",
                "from": [2, -3, 0],
                "to": [2, -2, 0.8],
                "label": "velocity v",
                "color": "teal",
            },
            {
                "type": "vector",
                "from": [2, -3, 0],
                "to": [1, -3, 0],
                "label": "Lorentz force q(v×B)",
                "color": "purple",
            },
            {
                "type": "vector",
                "from": [0, -3, 0],
                "to": [0, -1.5, 0],
                "label": "uniform field B",
                "color": "gold",
            },
        ]
    return [
        {
            "type": "sphere",
            "position": [0, 0, 0],
            "size": 1,
            "label": family.replace("_", " "),
            "color": "teal",
        }
    ]


def _surface_domains(
    normalized: str, relationship: dict[str, Any], explicit: bool
) -> tuple[list[float], list[float], list[float]]:
    """Choose bounded domains from equation structure, never from prompt-specific IDs.

    Explicit surfaces retain every bounded finite sample. Implicit surfaces use a general
    coarse sign-change scan to fit all detected components rather than matching equation text.
    """
    x_domain = [-5.0, 5.0]
    y_domain = [-5.0, 5.0]
    if explicit:
        rhs = relationship["right"]
        finite: list[float] = []
        # Fit the independent-variable domain before clipping z. This keeps every finite
        # corner visible for fast-growing functions such as exp(x+y) and x⁴+y⁴ while using
        # the widest domain that stays inside the renderer's ±999 numeric budget.
        for extent_candidate in (5.0, 4.0, 3.0, 2.0, 1.0):
            candidate: list[float] = []
            for ix in range(25):
                x = -extent_candidate + 2 * extent_candidate * ix / 24
                for iy in range(25):
                    y = -extent_candidate + 2 * extent_candidate * iy / 24
                    try:
                        value = evaluate_expression_v2(rhs, {"x": x, "y": y, "z": 0})
                    except (VisualizationV2Error, ValueError, OverflowError):
                        continue
                    if math.isfinite(value) and abs(value) <= 1e9:
                        candidate.append(value)
            if candidate:
                finite = candidate
                x_domain = [-extent_candidate, extent_candidate]
                y_domain = [-extent_candidate, extent_candidate]
            if candidate and max(abs(value) for value in candidate) <= 900:
                break
        if not finite:
            return x_domain, y_domain, [-5.0, 5.0]
        low = min(finite)
        high = max(finite)
        low = min(low, 0.0)
        high = max(high, 0.0)
        if high - low < 1:
            center = (low + high) / 2
            low, high = center - 0.5, center + 0.5
        padding = 0.08 * (high - low)
        return (
            x_domain,
            y_domain,
            [
                round(max(-999.0, low - padding), 6),
                round(min(999.0, high + padding), 6),
            ],
        )

    if _contains_call(relationship["left"], {"sin", "cos", "tan"}) or _contains_call(
        relationship["right"], {"sin", "cos", "tan"}
    ):
        # Use one exact 2π period on every axis, with small unequal phase offsets. The offsets
        # avoid placing symmetric trigonometric zero sets exactly on a sampling vertex, which is
        # ambiguous for marching tetrahedra, while opposite faces remain mathematically identical.
        shifts = [math.pi / 62, math.pi / 93, math.pi / 155]
        return tuple([-math.pi + shift, math.pi + shift] for shift in shifts)  # type: ignore[return-value]

    extent = 8.0
    cells = 32
    step = 2 * extent / cells
    values: list[float | None] = [None] * ((cells + 1) ** 3)

    def offset(ix: int, iy: int, iz: int) -> int:
        return ix + (cells + 1) * (iy + (cells + 1) * iz)

    for iz in range(cells + 1):
        z = -extent + step * iz
        for iy in range(cells + 1):
            y = -extent + step * iy
            for ix in range(cells + 1):
                x = -extent + step * ix
                try:
                    values[offset(ix, iy, iz)] = relationship_residual(
                        relationship, {"x": x, "y": y, "z": z}
                    )
                except (VisualizationV2Error, ValueError, OverflowError):
                    values[offset(ix, iy, iz)] = None

    crossing_cells: list[tuple[int, int, int]] = []
    for iz in range(cells):
        for iy in range(cells):
            for ix in range(cells):
                cube = [
                    values[offset(ix + dx, iy + dy, iz + dz)]
                    for dx, dy, dz in (
                        (0, 0, 0),
                        (1, 0, 0),
                        (1, 1, 0),
                        (0, 1, 0),
                        (0, 0, 1),
                        (1, 0, 1),
                        (1, 1, 1),
                        (0, 1, 1),
                    )
                ]
                finite_cube = [value for value in cube if value is not None]
                if finite_cube and min(finite_cube) <= 0 <= max(finite_cube):
                    crossing_cells.append((ix, iy, iz))
    if not crossing_cells:
        return [-1.0, 1.0], [-1.0, 1.0], [-1.0, 1.0]

    domains: list[list[float]] = []
    for axis in range(3):
        # The compile-time scan and browser mesher use different grids. A three-cell guard
        # keeps a compact closed surface away from the renderer boundary even when its
        # extremum falls between coarse probe samples.
        low_index = max(0, min(cell[axis] for cell in crossing_cells) - 3)
        high_index = min(cells, max(cell[axis] for cell in crossing_cells) + 4)
        low = -extent + step * low_index
        high = -extent + step * high_index
        if high - low < 1.0:
            middle = (low + high) / 2
            low, high = middle - 0.5, middle + 0.5
        domains.append([round(low, 6), round(high, 6)])
    return domains[0], domains[1], domains[2]


def _surface_spec(
    normalized: str, relationship: dict[str, Any], *, animate: bool = False
) -> dict[str, Any]:
    left = relationship["left"]
    explicit = left == {"type": "variable", "name": "z"} and not _contains_variable(
        relationship["right"], "z"
    )
    x_domain, y_domain, z_domain = _surface_domains(normalized, relationship, explicit)
    layer: dict[str, Any] = {
        "type": "explicit_surface" if explicit else "implicit_surface",
        "label": normalized,
        "relationship": relationship,
        "x_domain": x_domain,
        "y_domain": y_domain,
        "z_domain": z_domain,
        # An even implicit lattice avoids placing the origin on every axis. Odd grids can
        # entirely miss small sign-changing pockets around an algebraic singularity.
        "resolution": [49, 49] if explicit else [32, 32, 32],
    }
    if animate:
        layer["animation"] = {"mode": "orbit", "duration": 8}
    return {
        "version": SPEC_VERSION,
        "library": "three",
        "renderer": "three",
        "kind": "scene3d",
        "family": "explicit_surface" if explicit else "implicit_surface",
        "title": "Interactive mathematical surface",
        "aria_label": f"Three-dimensional plot of {normalized}, with x, y, and z axes.",
        "text_fallback": (
            f"Surface {normalized}. Domains are x {x_domain[0]} to {x_domain[1]}, "
            f"y {y_domain[0]} to {y_domain[1]}, and z {z_domain[0]} to {z_domain[1]}. "
            "Undefined samples are left as gaps."
        ),
        "height": 480,
        "controls": [
            {"id": "orbit", "label": "Rotate view", "type": "button", "value": 0},
            {"id": "reset_view", "label": "Reset view", "type": "button", "value": 0},
        ],
        "budget": {"max_points": 20_000, "max_triangles": MAX_TRIANGLES, "max_fps": 30},
        "scene": {"coordinate_system": "cartesian3d", "layers": [layer]},
    }


def _add_initial_animation(spec: dict[str, Any], request: str) -> None:
    """Add bounded, user-controlled motion without removing parameter controls."""
    if not _EXPLICIT_ANIMATION.search(request) or _NEGATIVE_VISUAL.search(request):
        return
    layers = spec.get("scene", {}).get("layers", [])
    surface_animated = False
    for layer in layers:
        if layer.get("type") not in {
            "explicit_surface",
            "implicit_surface",
            "parametric_surface",
        }:
            continue
        phase_capable = layer.get("type") == "explicit_surface" and _contains_call(
            layer["relationship"]["right"], {"sin", "cos"}
        )
        layer["animation"] = {
            "mode": "phase" if phase_capable else "orbit",
            "duration": 8,
        }
        surface_animated = True
    if not surface_animated:
        spec["scene"]["animation"] = {"mode": "guided_reveal", "duration": 8}
    existing = {control["id"] for control in spec.get("controls", [])}
    for control_id, label in (("play", "Play"), ("pause", "Pause"), ("restart", "Restart")):
        if control_id not in existing:
            spec["controls"].append(
                {"id": control_id, "label": label, "type": "button", "value": 0}
            )


def compile_visualization_v2(
    request: str,
    *,
    previous_spec: dict[str, Any] | None = None,
    normalized_relationship: str | None = None,
) -> dict[str, Any] | None:
    """Compile a learner request into one validated, renderer-independent V2 artifact."""
    intent = (
        VisualIntent(
            True, "mathematical_surface", "three", reason="audited normalized relationship"
        )
        if normalized_relationship
        else resolve_intent(request, previous_spec)
    )
    if not intent.requested:
        return None
    if intent.animate_previous:
        if not previous_spec or previous_spec.get("version") != SPEC_VERSION:
            return None
        cloned = json.loads(json.dumps(previous_spec))
        cloned["title"] = f"Animated: {cloned['title']}"[:120]
        _add_initial_animation(cloned, request)
        validate_v2_spec(cloned)
        return cloned
    parametric = _parametric_expressions_from_request(request)
    if parametric is not None:
        spec = _parametric_spec(parametric, "parametric x(u,v), y(u,v), z(u,v)")
        _add_initial_animation(spec, request)
        validate_v2_spec(spec)
        return spec
    relationship_match = _relationship_from_request(request)
    relationship_source = normalized_relationship or (relationship_match or (None, None))[0]
    relationship = (
        parse_relationship(normalized_relationship)
        if normalized_relationship
        else (relationship_match or (None, None))[1]
    )
    # Named educational compositions own equations embedded in their prose. Generic 2D
    # parsing is only appropriate when no reusable semantic family was selected; otherwise a
    # valid but impoverished curve can erase requested roots, forces, linked views, and controls.
    two_dimensional = (
        _generic_2d_spec(request, relationship_source, relationship)
        if intent.family
        in {
            None,
            "concept_process",
            "mathematical_surface",
            "basic_geometry",
            "quadratic",
            "vector_field",
        }
        else None
    )
    if two_dimensional is not None:
        _add_initial_animation(two_dimensional, request)
        validate_v2_spec(two_dimensional)
        return two_dimensional
    # A recognised composition (for example, two intersecting planes) owns any equations
    # embedded in its request. Only a generic equation request falls through to the surface
    # compiler; otherwise the first parseable line would silently replace the whole system.
    if intent.family == "mathematical_surface" or (
        relationship_source and intent.family == "concept_process"
    ):
        if not relationship_source:
            return None
        relationship = relationship or parse_relationship(relationship_source)
        spec = _surface_spec(relationship_source, relationship)
        if re.search(r"clipp(?:ing|ed)?", request, re.IGNORECASE):
            z_domain = spec["scene"]["layers"][0]["z_domain"]
            spec["controls"].insert(
                0,
                {
                    "id": "clip_z",
                    "label": "Clipping height",
                    "type": "range",
                    "value": z_domain[1],
                    "min": z_domain[0],
                    "max": z_domain[1],
                    "step": max(0.01, round((z_domain[1] - z_domain[0]) / 40, 4)),
                },
            )
        _add_initial_animation(spec, request)
        validate_v2_spec(spec)
        return spec
    family = intent.family or "concept_process"
    renderer = intent.renderer or "svg"
    controls = _controls_for_request(request, family)
    if renderer == "three":
        layers = _three_composition(family, request)
        kind = "scene3d"
        library = "three"
        coordinate_system = "cartesian3d"
    elif renderer == "canvas":
        layers = _plot_layers(family)
        kind = "simulation2d"
        library = "d3"
        coordinate_system = "cartesian2d"
    else:
        plot_families = {
            "basic_geometry",
            "quadratic",
            "pythagoras",
            "line_intersection",
            "linear_transform",
            "derivative_tangent",
            "riemann_sum",
            "gradient_field",
            "vector_field",
            "unit_circle",
            "projectile",
            "circular_motion",
            "complex_mapping",
            "travelling_wave",
            "standing_wave",
            "wave_interference",
            "harmonic_motion",
            "magnetic_field_wire",
            "rc_circuit",
            "rlc_circuit",
            "ac_phase",
            "ideal_gas",
            "carnot_cycle",
            "reaction_profile",
            "titration",
            "action_potential",
            "phase_diagram",
            "sampling_aliasing",
            "polar_plot",
            "fourier_series",
            "lagrange_multiplier",
            "convolution",
            "double_slit",
            "blackbody",
            "kinetics",
            "enzyme_kinetics",
            "impulse_response",
            "bode_plot",
            "nyquist",
            "pid_response",
            "pwm",
            "beam_bending",
            "kalman_filter",
            "vector_addition",
            "gradient_descent",
            "gradient_linked",
            "robot_localization",
        }
        layers = (
            _basic_geometry_layers(request)
            if family == "basic_geometry"
            else _plot_layers(family)
            if family in plot_families
            else _schematic_layers(family, request)
        )
        kind = "scene2d"
        library = "d3"
        coordinate_system = "cartesian2d" if family in plot_families else "screen"
    title = family.replace("_", " ").title()
    semantic_labels: list[str] = []
    for layer in layers:
        candidate = layer.get("title") if layer.get("type") == "panel" else layer.get("label")
        if isinstance(candidate, str) and candidate.strip() and candidate not in semantic_labels:
            semantic_labels.append(candidate.strip())
    control_labels = [str(control.get("label", control["id"])) for control in controls]
    fallback_details = (
        "; ".join(semantic_labels[:14]) or "labelled input, relationship, and outcome"
    )
    controls_text = f" Adjustable controls: {', '.join(control_labels)}." if control_labels else ""
    spec = {
        "version": SPEC_VERSION,
        "library": library,
        "renderer": renderer,
        "kind": kind,
        "family": family,
        "title": title,
        "aria_label": f"Interactive {title.lower()} visualization with labelled relationships and controls.",
        "text_fallback": f"{title}. Visible layers: {fallback_details}.{controls_text}",
        "height": (
            590
            if any(layer.get("type") == "panel" for layer in layers)
            else 420
            if renderer != "three"
            else 480
        ),
        "controls": controls,
        "budget": {"max_points": MAX_POINTS, "max_triangles": MAX_TRIANGLES, "max_fps": 30},
        "scene": {"coordinate_system": coordinate_system, "layers": layers},
    }
    _add_initial_animation(spec, request)
    validate_v2_spec(spec)
    return spec


def _count_ast(node: dict[str, Any], depth: int = 0) -> int:
    if depth > MAX_AST_DEPTH or not isinstance(node, dict):
        raise VisualizationV2Error("invalid expression tree")
    kind = node.get("type")
    if not isinstance(kind, str):
        raise VisualizationV2Error("invalid expression node type")
    keys = set(node)
    if kind == "number":
        if (
            keys != {"type", "value"}
            or not _finite_number(node.get("value"), -1e9, 1e9)
        ):
            raise VisualizationV2Error("invalid numeric expression node")
        return 1
    if kind in {"variable", "constant"}:
        allowed = _VARIABLES if kind == "variable" else _CONSTANTS
        if (
            keys != {"type", "name"}
            or not isinstance(node.get("name"), str)
            or node["name"] not in allowed
        ):
            raise VisualizationV2Error("invalid named expression node")
        return 1
    if kind == "unary":
        if keys != {"type", "op", "arg"} or node.get("op") != "-":
            raise VisualizationV2Error("invalid unary expression node")
        return 1 + _count_ast(node["arg"], depth + 1)
    if kind == "binary":
        operation = node.get("op")
        if (
            keys != {"type", "op", "left", "right"}
            or not isinstance(operation, str)
            or operation not in {"+", "-", "*", "/", "^"}
        ):
            raise VisualizationV2Error("invalid binary expression node")
        return 1 + _count_ast(node["left"], depth + 1) + _count_ast(node["right"], depth + 1)
    if kind == "call":
        function = node.get("name")
        if not isinstance(function, str):
            raise VisualizationV2Error("invalid function expression node")
        arguments = node.get("args")
        expected = 2 if function in _BINARY_FUNCTIONS else 1
        if (
            keys != {"type", "name", "args"}
            or function not in _UNARY_FUNCTIONS | _BINARY_FUNCTIONS
            or not isinstance(arguments, list)
            or len(arguments) != expected
        ):
            raise VisualizationV2Error("invalid function expression node")
        return 1 + sum(_count_ast(arg, depth + 1) for arg in arguments)
    raise VisualizationV2Error("unsupported expression node")


def _validate_points(
    points: Any,
    dimensions: int,
    limit: int = MAX_POINTS,
    *,
    low: float = -1e6,
    high: float = 1e6,
) -> int:
    if not isinstance(points, list) or not 2 <= len(points) <= limit:
        raise VisualizationV2Error("point collection is outside the budget")
    for point in points:
        if (
            not isinstance(point, list)
            or len(point) != dimensions
            or not all(_finite_number(value, low, high) for value in point)
        ):
            raise VisualizationV2Error("point coordinate is invalid")
    return len(points)


def _finite_number(value: Any, low: float = -1e6, high: float = 1e6) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and low <= value <= high
    except (OverflowError, TypeError, ValueError):
        return False


def _safe_text(value: Any, limit: int = 160) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _validate_v2_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Strict server-side schema/resource validation for one V2 visualization."""
    if not isinstance(spec, dict):
        raise VisualizationV2Error("visualization is not an object or exceeds 48 KiB")
    try:
        serialized_spec = json.dumps(spec, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        raise VisualizationV2Error("visualization cannot be serialized") from None
    if len(serialized_spec.encode()) > MAX_SPEC_BYTES:
        raise VisualizationV2Error("visualization is not an object or exceeds 48 KiB")
    required = {
        "version",
        "library",
        "renderer",
        "kind",
        "family",
        "title",
        "aria_label",
        "text_fallback",
        "height",
        "controls",
        "budget",
        "scene",
    }
    if set(spec) != required or spec.get("version") != SPEC_VERSION:
        raise VisualizationV2Error("V2 visualization has unknown or missing fields")
    compatible = {
        "svg": ("d3", "scene2d"),
        "canvas": ("d3", "simulation2d"),
        "three": ("three", "scene3d"),
    }
    renderer = spec.get("renderer")
    if (
        not isinstance(renderer, str)
        or renderer not in compatible
        or (spec.get("library"), spec.get("kind")) != compatible[renderer]
    ):
        raise VisualizationV2Error("renderer/library/kind are incompatible")
    if not isinstance(spec.get("family"), str) or not _SAFE_FAMILY.fullmatch(spec["family"]):
        raise VisualizationV2Error("family is invalid")
    for field, limit in (
        ("title", 120),
        ("aria_label", 400),
        ("text_fallback", 1000),
    ):
        if (
            not isinstance(spec.get(field), str)
            or not spec[field].strip()
            or len(spec[field]) > limit
        ):
            raise VisualizationV2Error(f"{field} is invalid")
    if (
        not isinstance(spec.get("height"), int)
        or isinstance(spec["height"], bool)
        or not 240 <= spec["height"] <= 600
    ):
        raise VisualizationV2Error("height is outside the responsive frame budget")
    controls = spec.get("controls")
    if not isinstance(controls, list) or len(controls) > MAX_CONTROLS:
        raise VisualizationV2Error("too many controls")
    parameter_controls = [
        control
        for control in controls
        if isinstance(control, dict)
        and (
            not isinstance(control.get("id"), str)
            or control["id"] not in TRANSPORT_CONTROL_IDS
        )
    ]
    if len(parameter_controls) > MAX_PARAMETER_CONTROLS:
        raise VisualizationV2Error("too many parameter controls")
    ids: set[str] = set()
    for control in controls:
        control_type = control.get("type") if isinstance(control, dict) else None
        if not isinstance(control_type, str) or control_type not in {
            "range", "select", "step", "button"
        }:
            raise VisualizationV2Error("unsupported control")
        if set(control) - {
            "id",
            "label",
            "type",
            "value",
            "min",
            "max",
            "step",
            "options",
            "binding",
        }:
            raise VisualizationV2Error("control has unknown fields")
        control_id = control.get("id")
        if (
            not isinstance(control_id, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", control_id)
            or control_id in ids
        ):
            raise VisualizationV2Error("control IDs must be unique and safe")
        if not _safe_text(control.get("label"), 80):
            raise VisualizationV2Error("control needs an accessible label")
        if control_id in TRANSPORT_CONTROL_IDS and control_type != "button":
            raise VisualizationV2Error("animation transport controls must be buttons")
        if control_id in TRANSPORT_CONTROL_IDS and (
            control["label"].strip().casefold()
            != TRANSPORT_CONTROL_LABELS[control_id].casefold()
        ):
            raise VisualizationV2Error("animation transport labels must match their action")
        if control_type in {"range", "step"}:
            numeric_fields = {"id", "label", "type", "value", "min", "max", "step"}
            if set(control) not in (numeric_fields, numeric_fields | {"binding"}):
                raise VisualizationV2Error("numeric control fields are incomplete")
            if not all(
                _finite_number(control.get(field)) for field in ("value", "min", "max", "step")
            ):
                raise VisualizationV2Error("numeric control values are invalid")
            if not control["min"] <= control["value"] <= control["max"] or not (
                control["min"] < control["max"]
                and 0.000001 <= control["step"] <= control["max"] - control["min"]
            ):
                raise VisualizationV2Error("numeric control range is invalid")
            binding = control.get("binding")
            if binding is not None and (
                not isinstance(binding, dict)
                or set(binding) != {"target_label", "effect"}
                or not _safe_text(binding.get("target_label"), 160)
                or not isinstance(binding.get("effect"), str)
                or binding["effect"] not in CONTROL_BINDING_EFFECTS
            ):
                raise VisualizationV2Error("control binding is invalid")
        elif control_type == "select":
            if set(control) != {"id", "label", "type", "value", "options"}:
                raise VisualizationV2Error("select control fields are incomplete")
            options = control.get("options")
            if (
                not isinstance(options, list)
                or not 1 <= len(options) <= 12
                or not all(_safe_text(option, 48) for option in options)
                or len(set(options)) != len(options)
                or control.get("value") not in options
            ):
                raise VisualizationV2Error("select control options are invalid")
        elif set(control) != {"id", "label", "type", "value"} or control.get("value") not in (
            0,
            1,
            False,
            True,
        ):
            raise VisualizationV2Error("button control fields are invalid")
        ids.add(control_id)
    budget = spec.get("budget")
    if not isinstance(budget, dict) or set(budget) != {
        "max_points",
        "max_triangles",
        "max_fps",
    }:
        raise VisualizationV2Error("resource budget is incomplete")
    budget_limits = {
        "max_points": 20_000,
        "max_triangles": MAX_TRIANGLES,
        "max_fps": 30,
    }
    if not all(
        isinstance(budget.get(field), int)
        and not isinstance(budget[field], bool)
        and 1 <= budget[field] <= limit
        for field, limit in budget_limits.items()
    ):
        raise VisualizationV2Error("resource budget exceeds the runtime cap")
    scene = spec.get("scene")
    if not isinstance(scene, dict) or set(scene) not in (
        {"coordinate_system", "layers"},
        {"coordinate_system", "layers", "animation"},
    ):
        raise VisualizationV2Error("scene is invalid")
    if "animation" in scene:
        animation = scene["animation"]
        if (
            not isinstance(animation, dict)
            or set(animation) != {"mode", "duration"}
            or animation.get("mode") != "guided_reveal"
            or not _finite_number(animation.get("duration"), 2, 30)
        ):
            raise VisualizationV2Error("scene animation is invalid")
    coordinate_system = scene["coordinate_system"]
    if not isinstance(coordinate_system, str) or coordinate_system not in {
        "screen", "cartesian2d", "polar", "cartesian3d"
    }:
        raise VisualizationV2Error("coordinate system is unsupported")
    layers = scene.get("layers")
    if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_LAYERS:
        raise VisualizationV2Error("scene layer count is outside the budget")
    point_count = 0
    triangle_estimate = 0
    node_ids = [
        layer.get("id")
        for layer in layers
        if isinstance(layer, dict) and layer.get("type") == "node"
    ]
    node_count = sum(isinstance(layer, dict) and layer.get("type") == "node" for layer in layers)
    if (
        len(node_ids) != node_count
        or not all(isinstance(node_id, str) and _SAFE_ID.fullmatch(node_id) for node_id in node_ids)
        or len(set(node_ids)) != node_count
    ):
        raise VisualizationV2Error("node IDs must be unique")
    layer_ids = set(node_ids)
    labelled_layers = {
        layer.get("label")
        for layer in layers
        if isinstance(layer, dict)
        and layer.get("type") != "panel"
        and isinstance(layer.get("label"), str)
    }
    panel_ids: set[str] = set()
    assigned_panel_members: set[str] = set()
    for layer in layers:
        if not isinstance(layer, dict) or not isinstance(layer.get("type"), str):
            raise VisualizationV2Error("scene layer is invalid")
        layer_type = layer["type"]
        allowed_keys = _LAYER_KEYS.get(layer_type)
        if allowed_keys is None or not set(layer) <= allowed_keys:
            raise VisualizationV2Error("scene layer has unknown or unsupported fields")
        if "color" in layer and (
            not isinstance(layer["color"], str) or not _SAFE_COLOR.fullmatch(layer["color"])
        ):
            raise VisualizationV2Error("layer color is invalid")
        for text_field in ("label", "text"):
            if (
                text_field in layer
                and layer[text_field] != ""
                and not _safe_text(layer[text_field])
            ):
                raise VisualizationV2Error(f"layer {text_field} is invalid")
        if layer_type == "polyline":
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("polyline fields are incomplete")
            point_count += _validate_points(layer.get("points"), 2)
        elif layer_type == "line":
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("line fields are incomplete")
            point_count += _validate_points(
                layer.get("points"), 3, 512, low=-1000, high=1000
            )
        elif layer_type == "vector":
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("vector fields are incomplete")
            _validate_points(
                [layer.get("from"), layer.get("to")], 3, 2, low=-1000, high=1000
            )
            if layer["from"] == layer["to"]:
                raise VisualizationV2Error("vector must have non-zero length")
            triangle_estimate += _THREE_PRIMITIVE_TRIANGLES["vector"]
        elif layer_type in {"explicit_surface", "implicit_surface"}:
            if set(layer) not in {
                _LAYER_KEYS[layer_type] - {"animation"},
                _LAYER_KEYS[layer_type],
            }:
                raise VisualizationV2Error("surface fields are incomplete")
            relationship = layer.get("relationship")
            if (
                not isinstance(relationship, dict)
                or set(relationship) != {"type", "op", "left", "right"}
                or relationship.get("type") != "relationship"
                or relationship.get("op") != "="
            ):
                raise VisualizationV2Error("surface relationship is invalid")
            nodes = _count_ast(relationship["left"]) + _count_ast(relationship["right"])
            if nodes > MAX_AST_NODES:
                raise VisualizationV2Error("surface expression exceeds the AST budget")
            resolution = layer.get("resolution")
            expected_dimensions = 2 if layer_type == "explicit_surface" else 3
            if (
                not isinstance(resolution, list)
                or len(resolution) != expected_dimensions
                or not all(
                    isinstance(item, int) and not isinstance(item, bool) and 9 <= item <= 65
                    for item in resolution
                )
            ):
                raise VisualizationV2Error("surface resolution is invalid")
            work = math.prod(resolution)
            if layer_type == "implicit_surface" and work > MAX_IMPLICIT_CELLS:
                raise VisualizationV2Error("implicit solver work exceeds the budget")
            if layer_type == "explicit_surface" and work * nodes > 500_000:
                raise VisualizationV2Error("explicit surface work exceeds the budget")
            if layer_type == "explicit_surface":
                triangle_estimate += 2 * (resolution[0] - 1) * (resolution[1] - 1)
            else:
                # An accepted implicit surface must leave room for at least one finite triangle;
                # renderer-owned labels are reserved separately below.
                triangle_estimate += 1
            for axis in "xyz":
                domain = layer.get(f"{axis}_domain")
                if (
                    not isinstance(domain, list)
                    or len(domain) != 2
                    or not all(_finite_number(value, -1000, 1000) for value in domain)
                    or not domain[0] < domain[1]
                ):
                    raise VisualizationV2Error("surface domain is invalid")
            animation = layer.get("animation")
            if animation is not None and (
                not isinstance(animation, dict)
                or set(animation) != {"mode", "duration"}
                or not isinstance(animation.get("mode"), str)
                or animation["mode"] not in {"orbit", "phase"}
                or not _finite_number(animation.get("duration"), 2, 30)
            ):
                raise VisualizationV2Error("surface animation is not finite and controlled")
        elif layer_type == "parametric_surface":
            if set(layer) not in {
                _LAYER_KEYS[layer_type] - {"animation"},
                _LAYER_KEYS[layer_type],
            }:
                raise VisualizationV2Error("parametric surface fields are incomplete")
            resolution = layer.get("resolution")
            if (
                not isinstance(resolution, list)
                or len(resolution) != 2
                or not all(
                    isinstance(item, int) and not isinstance(item, bool) and 9 <= item <= 65
                    for item in resolution
                )
                or math.prod(resolution) > 4096
            ):
                raise VisualizationV2Error("unsupported or oversized parametric surface")
            expression_nodes = sum(
                _count_ast(layer.get(field))
                for field in ("x_expression", "y_expression", "z_expression")
            )
            if expression_nodes > MAX_AST_NODES:
                raise VisualizationV2Error("parametric expressions exceed the AST budget")
            triangle_estimate += 2 * (resolution[0] - 1) * (resolution[1] - 1)
            for axis in ("u", "v"):
                domain = layer.get(f"{axis}_domain")
                if (
                    not isinstance(domain, list)
                    or len(domain) != 2
                    or not all(_finite_number(value, -100, 100) for value in domain)
                    or not domain[0] < domain[1]
                ):
                    raise VisualizationV2Error("parametric domain is invalid")
            animation = layer.get("animation")
            if animation is not None and (
                not isinstance(animation, dict)
                or set(animation) != {"mode", "duration"}
                or not isinstance(animation.get("mode"), str)
                or animation["mode"] not in {"orbit", "phase"}
                or not _finite_number(animation.get("duration"), 2, 30)
            ):
                raise VisualizationV2Error("parametric animation is invalid")
        elif layer_type == "plane":
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("plane fields are incomplete")
            _validate_points(
                [layer.get("normal"), [0, 0, 0]], 3, 2, low=-1000, high=1000
            )
            if layer["normal"] == [0, 0, 0] or not _finite_number(layer.get("constant"), -1000, 1000):
                raise VisualizationV2Error("plane geometry is invalid")
            triangle_estimate += _THREE_PRIMITIVE_TRIANGLES["plane"]
        elif layer_type == "link":
            if set(layer) != _LAYER_KEYS[layer_type] or not isinstance(layer.get("arrow"), bool):
                raise VisualizationV2Error("link fields are invalid")
            source_id = layer.get("from")
            target_id = layer.get("to")
            if (
                not isinstance(source_id, str)
                or not isinstance(target_id, str)
                or source_id not in layer_ids
                or target_id not in layer_ids
            ):
                raise VisualizationV2Error("link references an unknown node")
        elif layer_type == "axes":
            if set(layer) != _LAYER_KEYS[layer_type] or not isinstance(layer.get("grid"), bool):
                raise VisualizationV2Error("axis fields are invalid")
            if not _safe_text(layer.get("x_label"), 80) or not _safe_text(layer.get("y_label"), 80):
                raise VisualizationV2Error("axis labels are invalid")
        elif layer_type == "node":
            if set(layer) != _LAYER_KEYS[layer_type] or not _SAFE_ID.fullmatch(
                str(layer.get("id", ""))
            ):
                raise VisualizationV2Error("node fields are invalid")
            if not all(_finite_number(layer.get(field), -10_000, 10_000) for field in ("x", "y")):
                raise VisualizationV2Error("node position is invalid")
            if not all(_finite_number(layer.get(field), 1, 2_000) for field in ("width", "height")):
                raise VisualizationV2Error("node dimensions are invalid")
            if not _safe_text(layer.get("label"), 160):
                raise VisualizationV2Error("node label is invalid")
        elif layer_type in {"sphere", "box", "point"}:
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("3D object fields are incomplete")
            _validate_points(
                [layer.get("position"), [0, 0, 0]], 3, 2, low=-1000, high=1000
            )
            if not _finite_number(layer.get("size"), 0.01, 100):
                raise VisualizationV2Error("3D object size is invalid")
            if not _safe_text(layer.get("label"), 160):
                raise VisualizationV2Error("3D object label is invalid")
            triangle_estimate += _THREE_PRIMITIVE_TRIANGLES[layer_type]
        elif layer_type in {"arrow", "circle", "rect", "text", "particles"}:
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error(f"{layer_type} fields are incomplete")
            if layer_type == "arrow":
                _validate_points([layer.get("from"), layer.get("to")], 2, 2)
            elif layer_type == "circle":
                if not all(
                    _finite_number(layer.get(field), -10_000, 10_000) for field in ("x", "y")
                ) or not _finite_number(layer.get("r"), 0.1, 2_000):
                    raise VisualizationV2Error("circle geometry is invalid")
            elif layer_type == "rect":
                if not all(
                    _finite_number(layer.get(field), -10_000, 10_000) for field in ("x", "y")
                ) or not all(
                    _finite_number(layer.get(field), 0.1, 2_000) for field in ("width", "height")
                ):
                    raise VisualizationV2Error("rectangle geometry is invalid")
            elif layer_type == "text":
                if not all(
                    _finite_number(layer.get(field), -10_000, 10_000) for field in ("x", "y")
                ) or not _safe_text(layer.get("text"), 160):
                    raise VisualizationV2Error("text position is invalid")
            else:
                point_count += _validate_points(layer.get("points"), 2, MAX_PARTICLES)
        elif layer_type == "vector_field":
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("vector field fields are incomplete")
            vectors = layer.get("vectors")
            if not isinstance(vectors, list) or not 1 <= len(vectors) <= MAX_VECTOR_SAMPLES:
                raise VisualizationV2Error("vector field count is outside the budget")
            for vector in vectors:
                if (
                    not isinstance(vector, list)
                    or len(vector) != 4
                    or not all(_finite_number(value, -10_000, 10_000) for value in vector)
                    or (vector[2] == 0 and vector[3] == 0)
                ):
                    raise VisualizationV2Error("vector field sample is invalid")
            point_count += 2 * len(vectors)
        elif layer_type == "probe_vector":
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("probe vector fields are incomplete")
            if not _SAFE_ID.fullmatch(str(layer.get("x_control", ""))) or not _SAFE_ID.fullmatch(
                str(layer.get("y_control", ""))
            ):
                raise VisualizationV2Error("probe vector control IDs are invalid")
            if layer["x_control"] not in ids or layer["y_control"] not in ids:
                raise VisualizationV2Error("probe vector controls are missing")
            nodes = _count_ast(layer.get("x_expression")) + _count_ast(layer.get("y_expression"))
            if nodes > MAX_AST_NODES or not _finite_number(layer.get("scale"), 0.01, 10):
                raise VisualizationV2Error("probe vector expression exceeds its budget")
            point_count += 2
        elif layer_type == "heatmap":
            if set(layer) != _LAYER_KEYS[layer_type]:
                raise VisualizationV2Error("heatmap fields are incomplete")
            rows = layer.get("rows")
            columns = layer.get("columns")
            values = layer.get("values")
            if (
                not isinstance(rows, int)
                or isinstance(rows, bool)
                or not isinstance(columns, int)
                or isinstance(columns, bool)
                or rows < 1
                or columns < 1
                or rows * columns > MAX_HEATMAP_CELLS
                or not isinstance(values, list)
                or len(values) != rows * columns
                or not all(_finite_number(value, -1_000_000, 1_000_000) for value in values)
            ):
                raise VisualizationV2Error("heatmap grid is invalid")
            for axis in ("x", "y"):
                domain = layer.get(f"{axis}_domain")
                if (
                    not isinstance(domain, list)
                    or len(domain) != 2
                    or not all(_finite_number(value, -10_000, 10_000) for value in domain)
                    or not domain[0] < domain[1]
                ):
                    raise VisualizationV2Error("heatmap domain is invalid")
            point_count += rows * columns
        elif layer_type == "panel":
            if (
                set(layer) != _LAYER_KEYS[layer_type]
                or not isinstance(layer.get("id"), str)
                or not _SAFE_ID.fullmatch(layer["id"])
            ):
                raise VisualizationV2Error("panel fields are invalid")
            if layer["id"] in panel_ids:
                raise VisualizationV2Error("panel IDs must be unique")
            if not all(
                _safe_text(layer.get(field), 80) for field in ("title", "x_label", "y_label")
            ):
                raise VisualizationV2Error("panel labels are invalid")
            members = layer.get("members")
            if (
                not isinstance(members, list)
                or not 1 <= len(members) <= 16
                or not all(_safe_text(member, 160) for member in members)
                or len(set(members)) != len(members)
                or not set(members) <= labelled_layers
                or assigned_panel_members.intersection(members)
            ):
                raise VisualizationV2Error("panel members are invalid or ambiguous")
            panel_ids.add(layer["id"])
            assigned_panel_members.update(members)
    if any(layer.get("type") in {"explicit_surface", "implicit_surface"} for layer in layers):
        triangle_estimate += _THREE_SURFACE_LABEL_TRIANGLES
    if spec["family"] == "parametric_surface":
        triangle_estimate += _THREE_PARAMETRIC_MARKER_TRIANGLES
    if point_count > budget["max_points"]:
        raise VisualizationV2Error("scene points exceed the declared budget")
    if triangle_estimate > budget["max_triangles"]:
        raise VisualizationV2Error("scene geometry exceeds the declared triangle budget")
    for control in parameter_controls:
        binding = control.get("binding")
        if binding is None:
            continue
        matches = [layer for layer in layers if layer.get("label") == binding["target_label"]]
        if len(matches) != 1:
            raise VisualizationV2Error("control binding target must be one unique labelled layer")
        target_type = matches[0]["type"]
        if target_type not in _RENDERER_BINDABLE_TYPES[spec["renderer"]]:
            raise VisualizationV2Error("control binding target is not rendered by this renderer")
        if binding["effect"] not in _BINDABLE_LAYER_EFFECTS.get(target_type, frozenset()):
            raise VisualizationV2Error("control binding effect is incompatible with its layer")
        if binding["effect"] in {"scale", "radius"} and control["min"] <= 0:
            raise VisualizationV2Error("scale and radius bindings require positive control values")
    transport_controls = [
        control for control in controls if control.get("id") in TRANSPORT_CONTROL_IDS
    ]
    has_animation = "animation" in scene or any("animation" in layer for layer in layers)
    if transport_controls or has_animation:
        transport_ids = {control["id"] for control in transport_controls}
        if (
            not has_animation
            or len(transport_controls) != len(TRANSPORT_CONTROL_IDS)
            or transport_ids != TRANSPORT_CONTROL_IDS
            or any(control["type"] != "button" for control in transport_controls)
        ):
            raise VisualizationV2Error(
                "animation requires one Play, Pause, and Restart button"
            )
    return json.loads(json.dumps(spec, ensure_ascii=False))


def validate_v2_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate one V2 spec and expose only the stable domain error type."""
    try:
        return _validate_v2_spec(spec)
    except VisualizationV2Error:
        raise
    except (KeyError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise VisualizationV2Error(f"visualization schema value is invalid: {exc}") from None


def iter_ast(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield expression nodes for QA without exposing a dynamic evaluator."""
    yield node
    if node.get("type") == "binary":
        yield from iter_ast(node["left"])
        yield from iter_ast(node["right"])
    elif node.get("type") == "unary":
        yield from iter_ast(node["arg"])
    elif node.get("type") == "call":
        for arg in node["args"]:
            yield from iter_ast(arg)
