"""Bounded local-model planning for genuinely unseen visualization compositions.

The local model never authors executable browser source.  It may only propose a closed subset
of the versioned V2 artifact grammar; the same strict validator used for deterministic scenes,
plus semantic grounding checks below, remains authoritative.  A rejected proposal receives one
structured repair attempt before the caller falls back to a deterministic safe schematic.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from itertools import pairwise
from typing import Any

from orchestrator.gateway.visualization_v2 import (
    CONTROL_BINDING_EFFECTS,
    TRANSPORT_CONTROL_IDS,
    VisualizationV2Error,
    validate_v2_spec,
)
from runtime.chat import ChatEngine
from runtime.client import Generation

log = logging.getLogger("muta.gateway.visualization_planner_v2")

MAX_PLANNER_ATTEMPTS = 2
MAX_PLANNER_LAYERS = 24
MAX_PLANNER_POINTS = 512

_COMPOSITION_SIGNAL = re.compile(
    r"\b(?:diagram|draw|sketch|illustrate|picture|visuali[sz]e|map|model|simulate|"
    r"flow|cycle|process|system|network|architecture|structure|topology|relationship)\b",
    re.IGNORECASE,
)
_LEGACY_DATA_VISUAL = re.compile(
    r"\b(?:bar\s+chart|histogram|scatter(?:\s+(?:plot|graph))?|pie\s+(?:chart|graph))\b",
    re.IGNORECASE,
)
_EXPLICIT_EQUATION_PLOT = re.compile(
    r"\b(?:plot|graph|chart)\b.{0,120}(?:[xyz]\s*=|\br\s*=)|"
    r"(?:[xyz]\s*=|\br\s*=).{0,120}\b(?:plot|graph|chart)\b",
    re.IGNORECASE | re.DOTALL,
)
_INTERACTION_SIGNAL = re.compile(
    r"\b(?:interactive|adjust|adjustable|sliders?|controls?|change|vary|"
    r"step\s+through|toggles?)\b",
    re.IGNORECASE,
)
_ANIMATION_SIGNAL = re.compile(
    r"\b(?:animate|animation|make\s+it\s+move|moving|play|motion)\b",
    re.IGNORECASE,
)
_STRUCTURAL_RELATIONSHIP_SIGNAL = re.compile(
    r"\b(?:web|network|flow|cycle|process|path|loop|pipeline|hierarchy|tree|graph|"
    r"architecture|relationship|link|linking|connect|connected|connecting)\b|"
    r"\bfrom\b.{0,100}\b(?:to|through|into|towards?|via|then)\b",
    re.IGNORECASE | re.DOTALL,
)
_ENTITY_INTRODUCER = re.compile(
    r"\b(?P<introducer>showing|linking|connecting|between|including|containing|"
    r"composed(?:\s+|\s*[-‐‑‒–—―−－]\s*)of|with)\b",
    re.IGNORECASE,
)
_DIRECTIONAL_CHAIN = re.compile(
    r"\bfrom\b(?P<entities>[^.!?;]{1,220}?)(?="
    r"(?:,\s*)?(?:and|then)\s+from\b|,\s*from\b|[.!?;]|$)",
    re.IGNORECASE,
)
_PERSPECTIVE_FROM = re.compile(r"\b(?:view|viewed|seen|looking)\s*$", re.IGNORECASE)
_PERSPECTIVE_CHAIN_HEAD = re.compile(
    r"^\s*(?:directly\s+)?(?:above|below|overhead|front|behind|the\s+(?:front|back|side)|"
    r"(?:(?:an?|the)\s+)?(?:top(?:[-‐‑‒–—―−－\s]?down)?|"
    r"bottom(?:[-‐‑‒–—―−－\s]?up)?|(?:left|right)[-‐‑‒–—―−－\s]?side|"
    r"side|front|rear|overhead|isometric|bird(?:['’]?s)?[-‐‑‒–—―−－\s]?eye)\s+"
    r"(?:view|viewpoint|perspective|angle)|"
    r"(?:(?:an?|the)\s+)?(?:\d{1,3}(?:\.\d+)?\s*(?:degree|degrees|°)\s+)?"
    r"(?:view|viewpoint|viewing\s+angle|perspective|elevation)\b)",
    re.IGNORECASE,
)
_DIRECTIONAL_TAIL = re.compile(
    r"\b(?:and\s+)?(?:let\s+(?:me|us)\b|allow\b|enable\b|"
    r"(?:an?\s+)?(?:adjustable|interactive)\b|"
    r"(?:an?\s+)?(?:directed|undirected|non[-\s]?directional)\b|"
    r"including\b|containing\b|composed(?:\s+|\s*[-‐‑‒–—―−－]\s*)of\b|"
    r"with\b|where\s+(?:i|we|the\s+user)\b)",
    re.IGNORECASE,
)
_DIRECTION_STEP = re.compile(
    r"\b(?:to|through|into|towards?|via|then)\b|->|→", re.IGNORECASE
)
_ENTITY_SEPARATOR = re.compile(
    r"\s*(?:,|\band\b|\bas\s+well\s+as\b|\bplus\b|\bwith\b|\bto\b|\bthrough\b|"
    r"\binto\b|\btowards?\b|\bvia\b|\bthen\b|->|→)\s*",
    re.IGNORECASE,
)
_SEMANTIC_TOKEN = re.compile(r"[A-Za-z](?:/[A-Za-z])+|[A-Za-z][A-Za-z0-9_-]*")
_WITH_PRESENTATION_CLAUSE = re.compile(
    r"^\s*(?:each\s+component\s+)?"
    r"(?:(?:clear|clearly|named|accessible|descriptive|colou?r[-\s]?coded)\s+)*"
    r"(?:labels?|labelled|labeled|annotated|annotations?|measurements?|"
    r"dimensions?|legends?|titles?|captions?)\b|"
    r"^\s*(?:high\s+contrast|(?:dark|light)(?:\s+and\s+(?:dark|light))?\s+themes?|"
    r"large\s+(?:text|type|fonts?)|(?:an?\s+)?(?:sliders?|controls?|toggles?|inputs?)\b)",
    re.IGNORECASE,
)
_REQUESTED_CONTROL_CLAUSE = re.compile(
    r"\b(?:an?\s+)?(?:(?:range|numeric|number)\s+)?"
    r"(?:sliders?|controls?|inputs?)\s+"
    r"(?:for|named|called|labelled|labeled|to\s+(?:adjust|vary|change))\s+"
    r"(?P<controls>[^.!?;]{1,160})",
    re.IGNORECASE,
)
_UNDIRECTED_SIGNAL = re.compile(r"\b(?:undirected|non[-\s]?directional)\b", re.IGNORECASE)
_UNDIRECTED_ENTITY_CLAUSE = re.compile(
    r"\b(?:undirected|non[-\s]?directional)\b\s*"
    r"(?:network|graph|component|link|edge|connection|path)?\s*"
    r"(?:between|connecting|linking|containing|with)?\s*"
    r"(?P<entities>[^.!?;]{1,220}?)(?="
    r"(?:,\s*|\s+)(?:and\s+|plus\s+)?(?:an?\s+)?directed\b|[.!?;]|$)",
    re.IGNORECASE,
)
_RELATIONSHIP_COMPONENT_BOUNDARY = re.compile(
    r"\b(?:and|plus)\s+(?:an?\s+)?(?:directed|undirected|non[-\s]?directional)\b",
    re.IGNORECASE,
)
_PRESENTATION_TERMS = frozenset(
    {
        "accessible",
        "annotation",
        "annotations",
        "caption",
        "captions",
        "clear",
        "clearly",
        "coded",
        "color",
        "colour",
        "contrast",
        "descriptive",
        "dimension",
        "dimensions",
        "dark",
        "font",
        "fonts",
        "high",
        "label",
        "labeled",
        "labelled",
        "labels",
        "large",
        "legend",
        "legends",
        "light",
        "measurement",
        "measurements",
        "named",
        "theme",
        "themes",
        "title",
        "titles",
        "type",
    }
)
_RELATIONSHIP_TERMS = frozenset(
    {
        "connection",
        "connections",
        "energy",
        "flow",
        "flows",
        "label",
        "labeled",
        "labelled",
        "labels",
        "link",
        "links",
        "path",
        "paths",
        "relationship",
        "relationships",
        "signal",
        "signals",
        "transfer",
    }
)
_FORBIDDEN_AUTHORED_SOURCE = re.compile(
    r"(?:<\s*/?\s*[A-Za-z][^>]{0,200}>|"
    r"\bjavascript\s*:|\bon\w+\s*=|\beval\s*\(|\bnew\s+Function\b|"
    r"\bfunction(?:\s+[A-Za-z_$][\w$]*)?\s*\(|"
    r"\b(?:const|let|var)\s+(?:[A-Za-z_$][\w$]*|\{[^}\r\n]{1,160}\}|"
    r"\[[^\]\r\n]{1,160}\])\s*=|"
    r"\bimport\s+(?:['\"]|(?:[A-Za-z_$][\w$]*|\*|\{)[^;]{0,160}\bfrom\b)|"
    r"(?:^|[\r\n])\s*import\s+[A-Za-z_][\w.]*"
    r"(?:\s+as\s+[A-Za-z_]\w*)?\s*(?:$|[\r\n;])|"
    r"(?:^|[\r\n])\s*from\s+[A-Za-z_][\w.]*\s+import\b|"
    r"(?:^|[\r\n])\s*(?:async\s+)?def\s+[A-Za-z_]\w*\s*\(|"
    r"\bclass\s+[A-Za-z_$][\w$]*\s*\{|"
    r"\b(?:require|importScripts|setTimeout|setInterval|requestAnimationFrame|"
    r"cancelAnimationFrame|fetch)\s*\(|"
    r"\bimport\s*\(|\bnew\s+[A-Za-z_$][\w$]*\s*\(|"
    r"\b(?:WebSocket|Worker|SharedWorker|XMLHttpRequest|EventSource)\s*\(|"
    r"\b(?:d3|THREE|gsap|motion)\s*(?:\.|\[)|\banime\s*\(|"
    r"\b(?:module\s*\.\s*exports|exports\s*\.|process\s*\.|Deno\s*\.|__import__\s*\()|"
    r"\bwhile\s*\([^)]{0,160}\)\s*(?:\{|[A-Za-z_$][\w$]*\s*\()|"
    r"\bfor\s*\([^)]{0,160}(?:;|\+\+|--)[^)]{0,160}\)\s*|"
    r"\bfor\s*\([^)]{0,160}\b(?:in|of)\b[^)]{0,160}\)\s*|"
    r"\b(?:console|Math|JSON|Object|Array|Promise)\s*\.\s*[A-Za-z_$][\w$]*\s*\(|"
    r"=>|```|\b(?:gl_FragColor|gl_Position|gl_PointSize|texture2D)\b|"
    r"#version\s+\d+|"
    r"\bvoid\s+main\s*\(|\b(?:alert|confirm|prompt)\s*\(|"
    r"\bprecision\s+(?:lowp|mediump|highp)\s+(?:float|int)\s*;|"
    r"\b(?:uniform|varying|attribute|vec[234]|mat[234]|sampler2D)\s+[A-Za-z_]\w*|"
    r"\b(?:document|window|globalThis|location|history|navigator)\s*"
    r"(?:\.|\[\s*['\"])|"
    r"(?:[#.][-\w]+|\b[A-Za-z][-\w]*(?:\s+[A-Za-z][-\w]*)?)\s*"
    r"\{\s*-?[-\w]+\s*:|"
    r"https?\s*:|\bdata\s*:[A-Za-z][^,\s]{0,100},|\bfile\s*://|"
    r"\burl\s*\(|@import\b|(?:^|[\"\s])//[A-Za-z0-9])",
    re.IGNORECASE,
)
_TOPIC_STOPWORDS = frozenset(
    {
        "about",
        "adjust",
        "adjustable",
        "above",
        "an",
        "and",
        "animate",
        "animation",
        "are",
        "as",
        "at",
        "be",
        "below",
        "between",
        "build",
        "by",
        "change",
        "chart",
        "coded",
        "color",
        "colour",
        "composed",
        "connecting",
        "control",
        "controls",
        "containing",
        "create",
        "diagram",
        "draw",
        "descriptive",
        "for",
        "explain",
        "from",
        "graph",
        "in",
        "including",
        "illustrate",
        "interactive",
        "is",
        "it",
        "linking",
        "make",
        "me",
        "model",
        "of",
        "on",
        "or",
        "picture",
        "please",
        "plot",
        "render",
        "show",
        "showing",
        "simulate",
        "sketch",
        "slider",
        "sliders",
        "that",
        "the",
        "their",
        "then",
        "these",
        "this",
        "through",
        "to",
        "unfamiliar",
        "us",
        "via",
        "view",
        "viewed",
        "visualise",
        "visualize",
        "we",
        "where",
        "which",
        "with",
        "you",
        "your",
    }
)


def should_use_semantic_planner(request: str) -> bool:
    """Reserve the model planner for unseen compositions, not deterministic data/equation paths."""
    value = str(request or "")
    return bool(
        _COMPOSITION_SIGNAL.search(value)
        and not _LEGACY_DATA_VISUAL.search(value)
        and not _EXPLICIT_EQUATION_PLOT.search(value)
    )


def _number_array(length: int, *, low: float = -10_000, high: float = 10_000) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "number", "minimum": low, "maximum": high},
        "minItems": length,
        "maxItems": length,
    }


def planner_schema_v2() -> dict[str, Any]:
    """Return the closed llama-server grammar for a safe V2 composition proposal.

    Surface expressions stay on the deterministic typed-AST compiler path.  The planner subset
    covers reusable 2D/3D primitives and relationships without recursive source-like fields.
    Per-primitive completeness and renderer compatibility are enforced after decoding by
    ``validate_v2_spec`` so validation failures can be repaired once with useful error codes.
    """
    point2 = _number_array(2)
    point3 = _number_array(3, low=-1000, high=1000)
    points2 = {
        "type": "array",
        "items": point2,
        "minItems": 2,
        "maxItems": 128,
    }
    points3 = {
        "type": "array",
        "items": point3,
        "minItems": 2,
        "maxItems": 128,
    }
    vector_sample = _number_array(4)
    layer_properties: dict[str, Any] = {
        "type": {
            "type": "string",
            "enum": [
                "axes",
                "polyline",
                "node",
                "link",
                "arrow",
                "circle",
                "rect",
                "text",
                "particles",
                "vector_field",
                "panel",
                "sphere",
                "box",
                "point",
                "vector",
                "line",
                "plane",
            ],
        },
        "id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"},
        "label": {"type": "string", "minLength": 1, "maxLength": 160},
        "text": {"type": "string", "minLength": 1, "maxLength": 160},
        "color": {
            "type": "string",
            "enum": [
                "black",
                "white",
                "gray",
                "red",
                "green",
                "blue",
                "orange",
                "purple",
                "teal",
                "gold",
            ],
        },
        "x": {"type": "number", "minimum": -10_000, "maximum": 10_000},
        "y": {"type": "number", "minimum": -10_000, "maximum": 10_000},
        "r": {"type": "number", "exclusiveMinimum": 0, "maximum": 2_000},
        "width": {"type": "number", "exclusiveMinimum": 0, "maximum": 2_000},
        "height": {"type": "number", "exclusiveMinimum": 0, "maximum": 2_000},
        "size": {"type": "number", "minimum": 0.01, "maximum": 100},
        "from": {"type": ["string", "array"]},
        "to": {"type": ["string", "array"]},
        "arrow": {"type": "boolean"},
        "points": {"type": "array", "minItems": 2, "maxItems": 128},
        "position": point3,
        "normal": point3,
        "constant": {"type": "number", "minimum": -1000, "maximum": 1000},
        "vectors": {
            "type": "array",
            "items": vector_sample,
            "minItems": 1,
            "maxItems": 128,
        },
        "x_label": {"type": "string", "minLength": 1, "maxLength": 80},
        "y_label": {"type": "string", "minLength": 1, "maxLength": 80},
        "grid": {"type": "boolean"},
        "title": {"type": "string", "minLength": 1, "maxLength": 80},
        "members": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 160},
            "minItems": 1,
            "maxItems": 16,
        },
    }
    # JSON-schema constrained decoding cannot express the dimension of ``from``, ``to`` and
    # ``points`` from the selected primitive without a costly union.  These safe array shapes
    # keep the grammar closed; the strict V2 validator then enforces the exact 2D/3D shape.
    layer_properties["from"] = {"anyOf": [{"type": "string", "maxLength": 64}, point2, point3]}
    layer_properties["to"] = {"anyOf": [{"type": "string", "maxLength": 64}, point2, point3]}
    layer_properties["points"] = {"anyOf": [points2, points3]}

    control = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,31}$"},
            "label": {"type": "string", "minLength": 1, "maxLength": 80},
            # Generic planner controls must either be numeric bindings or the three animation
            # transport buttons. Select controls need family-specific semantics and therefore
            # remain on deterministic compiler paths rather than becoming inert model output.
            "type": {"type": "string", "enum": ["range", "step", "button"]},
            "value": {"type": ["number", "string", "boolean"]},
            "min": {"type": "number", "minimum": -10_000, "maximum": 10_000},
            "max": {"type": "number", "minimum": -10_000, "maximum": 10_000},
            "step": {"type": "number", "exclusiveMinimum": 0, "maximum": 10_000},
            "options": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 48},
                "minItems": 1,
                "maxItems": 12,
            },
            "binding": {
                "type": "object",
                "properties": {
                    "target_label": {"type": "string", "minLength": 1, "maxLength": 160},
                    "effect": {
                        "type": "string",
                        "enum": sorted(CONTROL_BINDING_EFFECTS),
                    },
                },
                "required": ["target_label", "effect"],
                "additionalProperties": False,
            },
        },
        "required": ["id", "label", "type", "value"],
        "additionalProperties": False,
    }
    return {
        "name": "muta_visualization_v2_semantic_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "version": {"type": "integer", "enum": [2]},
                "library": {"type": "string", "enum": ["d3", "three"]},
                "renderer": {"type": "string", "enum": ["svg", "canvas", "three"]},
                "kind": {"type": "string", "enum": ["scene2d", "simulation2d", "scene3d"]},
                "family": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9_]{0,63}$",
                },
                "title": {"type": "string", "minLength": 1, "maxLength": 120},
                "aria_label": {"type": "string", "minLength": 1, "maxLength": 400},
                "text_fallback": {"type": "string", "minLength": 1, "maxLength": 1000},
                "height": {"type": "integer", "minimum": 240, "maximum": 600},
                "controls": {
                    "type": "array",
                    "items": control,
                    "maxItems": 8,
                },
                "budget": {
                    "type": "object",
                    "properties": {
                        "max_points": {"type": "integer", "enum": [MAX_PLANNER_POINTS]},
                        "max_triangles": {"type": "integer", "enum": [4096]},
                        "max_fps": {"type": "integer", "enum": [20]},
                    },
                    "required": ["max_points", "max_triangles", "max_fps"],
                    "additionalProperties": False,
                },
                "scene": {
                    "type": "object",
                    "properties": {
                        "coordinate_system": {
                            "type": "string",
                            "enum": ["screen", "cartesian2d", "polar", "cartesian3d"],
                        },
                        "layers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": layer_properties,
                                "required": ["type"],
                                "additionalProperties": False,
                            },
                            "minItems": 1,
                            "maxItems": MAX_PLANNER_LAYERS,
                        },
                        "animation": {
                            "type": "object",
                            "properties": {
                                "mode": {"type": "string", "enum": ["guided_reveal"]},
                                "duration": {"type": "number", "minimum": 2, "maximum": 30},
                            },
                            "required": ["mode", "duration"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["coordinate_system", "layers"],
                    "additionalProperties": False,
                },
            },
            "required": [
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
            ],
            "additionalProperties": False,
        },
    }


def _topic_terms(request: str) -> set[str]:
    terms: set[str] = set()
    for match in _SEMANTIC_TOKEN.finditer(request):
        raw = match.group(0)
        token = raw.lower()
        is_short_symbol = (
            "/" in raw
            or (
                2 <= len(raw) <= 3
                and (raw.isupper() or not raw.islower() and not raw.isupper())
            )
        )
        if (
            token not in _TOPIC_STOPWORDS
            and token not in _PRESENTATION_TERMS
            and (len(token) >= 4 or is_short_symbol)
        ):
            terms.add(token)
    return terms


def _entity_terms(value: str) -> set[str]:
    """Return concrete phrase tokens, including short acronyms and slash notation."""
    terms: set[str] = set()
    for match in _SEMANTIC_TOKEN.finditer(value):
        raw = match.group(0)
        token = raw.lower()
        uppercase_single = len(raw) == 1 and raw.isupper() and raw != "I"
        if (token not in _TOPIC_STOPWORDS or uppercase_single) and token not in _RELATIONSHIP_TERMS:
            terms.add(token)
    return terms


def _entity_groups(value: str) -> list[frozenset[str]]:
    """Split an ordered bounded entity list, retaining multi-word names and repeated steps."""
    groups: list[frozenset[str]] = []
    for part in _ENTITY_SEPARATOR.split(value):
        terms = _entity_terms(part)
        if terms:
            groups.append(frozenset(terms))
    return groups


def _directional_entity_chains(request: str) -> list[list[frozenset[str]]]:
    """Extract each ordered explicit from-A-to-B chain without presentation tails."""
    chains: list[list[frozenset[str]]] = []
    for match in _DIRECTIONAL_CHAIN.finditer(request):
        prefix = request[max(0, match.start() - 24) : match.start()]
        if _PERSPECTIVE_FROM.search(prefix):
            continue
        chain = _DIRECTIONAL_TAIL.split(match.group("entities"), maxsplit=1)[0]
        if _PERSPECTIVE_CHAIN_HEAD.search(chain) or not _DIRECTION_STEP.search(chain):
            continue
        groups = _entity_groups(chain)
        if len(groups) > 1:
            chains.append(groups)
    return chains


def _undirected_entity_components(request: str) -> list[list[frozenset[str]]]:
    """Extract explicitly undirected components whose links must not carry arrows."""
    components: list[list[frozenset[str]]] = []
    for match in _UNDIRECTED_ENTITY_CLAUSE.finditer(request):
        clause = _DIRECTIONAL_TAIL.split(match.group("entities"), maxsplit=1)[0]
        groups = _entity_groups(clause)
        if len(groups) > 1:
            components.append(groups)
    return components


def _explicit_entity_clauses(request: str) -> list[tuple[str, str]]:
    """Split entity introducers without letting one clause consume a later clause."""
    matches = list(_ENTITY_INTRODUCER.finditer(request))
    clauses: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        sentence_end = re.search(r"[.!?;]", request[match.end() :])
        stop = (
            match.end() + sentence_end.start()
            if sentence_end is not None
            else len(request)
        )
        if index + 1 < len(matches):
            stop = min(stop, matches[index + 1].start())
        clause = request[match.end() : stop][:220]
        if clause.strip():
            clauses.append((match.group("introducer").lower(), clause))
    return clauses


def _explicit_entity_groups(request: str) -> list[frozenset[str]]:
    """Extract the unique concrete phrases that each need their own labelled node."""
    groups: list[frozenset[str]] = []
    for chain in _directional_entity_chains(request):
        for group in chain:
            if group not in groups:
                groups.append(group)
    for introducer, raw_clause in _explicit_entity_clauses(request):
        # A clause such as "showing flow from A to B" is represented by the ordered chain
        # above. Keep any concrete prefix, then let later introducers be parsed separately.
        component_boundary = _RELATIONSHIP_COMPONENT_BOUNDARY.search(raw_clause)
        clause = (
            raw_clause[: component_boundary.start()]
            if component_boundary is not None
            else raw_clause
        )
        from_match = re.search(r"\bfrom\b", clause, re.IGNORECASE)
        if from_match and _DIRECTION_STEP.search(clause[from_match.end() :]):
            clause = clause[: from_match.start()]
        clause = _DIRECTIONAL_TAIL.split(clause, maxsplit=1)[0]
        if introducer == "with" and _WITH_PRESENTATION_CLAUSE.search(clause):
            continue
        extracted = _entity_groups(clause)
        if introducer == "with" and len(extracted) < 2:
            continue
        for group in extracted:
            if group not in groups:
                groups.append(group)
    return groups


def _requested_control_groups(request: str) -> list[frozenset[str]]:
    """Extract distinct learner-named parameters from explicit slider/control clauses."""
    groups: list[frozenset[str]] = []
    for match in _REQUESTED_CONTROL_CLAUSE.finditer(request):
        clause = _DIRECTIONAL_TAIL.split(match.group("controls"), maxsplit=1)[0]
        for group in _entity_groups(clause):
            if group not in groups:
                groups.append(group)
    return groups


def _unique_assignment(
    candidates: dict[frozenset[str], list[str]],
) -> dict[frozenset[str], str]:
    """Return the sole perfect bipartite assignment, or fail closed if absent/ambiguous."""
    groups = sorted(candidates, key=lambda group: (len(candidates[group]), -len(group)))

    def perfect(
        blocked: tuple[frozenset[str], str] | None = None,
    ) -> dict[frozenset[str], str] | None:
        owner: dict[str, frozenset[str]] = {}

        def place(group: frozenset[str], seen: set[str]) -> bool:
            for target in candidates[group]:
                if (group, target) == blocked or target in seen:
                    continue
                seen.add(target)
                previous = owner.get(target)
                if previous is None or place(previous, seen):
                    owner[target] = group
                    return True
            return False

        for group in groups:
            if not place(group, set()):
                return None
        return {group: target for target, group in owner.items()}

    assignment = perfect()
    if assignment is None:
        return {}
    if any(perfect((group, target)) is not None for group, target in assignment.items()):
        return {}
    return assignment


def _map_entity_nodes(
    entity_groups: list[frozenset[str]], layers: list[dict[str, Any]]
) -> dict[frozenset[str], str]:
    """Find one unique one-to-one assignment without accepting catch-all labels."""
    node_tokens = {
        str(layer["id"]): _entity_terms(str(layer.get("label", "")))
        for layer in layers
        if layer.get("type") == "node"
    }

    def is_catch_all(tokens: set[str]) -> bool:
        covered = [entity for entity in entity_groups if entity.issubset(tokens)]
        return any(
            not left.issubset(right) and not right.issubset(left)
            for index, left in enumerate(covered)
            for right in covered[index + 1 :]
        )

    candidates = {
        entity: [
            node_id
            for node_id, tokens in node_tokens.items()
            if entity.issubset(tokens) and not is_catch_all(tokens)
        ]
        for entity in entity_groups
    }
    return _unique_assignment(candidates)


def _map_control_groups(
    requested_groups: list[frozenset[str]], controls: list[dict[str, Any]]
) -> dict[frozenset[str], str]:
    """Map each requested parameter phrase to one distinct bound numeric control."""
    control_tokens = {
        str(control["id"]): _entity_terms(
            " ".join(
                (
                    str(control.get("label", "")),
                    str(control.get("binding", {}).get("target_label", "")),
                )
            )
        )
        for control in controls
    }
    candidates = {
        group: [
            control_id
            for control_id, tokens in control_tokens.items()
            if group.issubset(tokens)
        ]
        for group in requested_groups
    }
    return _unique_assignment(candidates)


def _has_path(
    adjacency: dict[str, set[str]], start: str, target: str, *, require_edge: bool = False
) -> bool:
    """Return whether a bounded directed graph contains a path from start to target."""
    if start == target and not require_edge:
        return True
    pending = [start]
    visited: set[str] = set()
    while pending:
        node = pending.pop()
        if node in visited:
            continue
        visited.add(node)
        for next_node in adjacency.get(node, set()):
            if next_node == target:
                return True
            if next_node not in visited:
                pending.append(next_node)
    return False


def _text_values(value: object) -> Iterator[str]:
    """Yield authored strings directly so JSON escaping cannot hide source syntax."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_values(child)


def _plan_errors(candidate: object, request: str) -> list[dict[str, str]]:
    """Return stable machine-readable validation and semantic-oracle failures."""
    try:
        spec = validate_v2_spec(candidate)  # type: ignore[arg-type]
    except (VisualizationV2Error, TypeError, ValueError) as exc:
        return [{"code": "schema_invalid", "detail": str(exc)[:200]}]

    errors: list[dict[str, str]] = []
    if any(_FORBIDDEN_AUTHORED_SOURCE.search(value) for value in _text_values(spec)):
        errors.append(
            {
                "code": "authored_source_forbidden",
                "detail": "Use declarative labels and primitives; source/markup/shader syntax is forbidden.",
            }
        )
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", spec["family"]):
        errors.append({"code": "family_invalid", "detail": "Use a safe lower_snake_case family."})

    layers = spec["scene"]["layers"]
    meaningful = [layer for layer in layers if layer.get("type") not in {"axes", "text", "panel"}]
    if not meaningful:
        errors.append(
            {
                "code": "geometry_missing",
                "detail": "Include at least one non-text visual primitive representing the subject.",
            }
        )

    if spec["renderer"] == "three":
        compatible = {"sphere", "box", "point", "vector", "line", "plane"}
        if spec["scene"]["coordinate_system"] != "cartesian3d" or any(
            layer.get("type") not in compatible for layer in layers
        ):
            errors.append(
                {
                    "code": "renderer_mismatch",
                    "detail": "Three scenes require cartesian3d and only 3D primitives.",
                }
            )
    else:
        compatible = {
            "axes",
            "polyline",
            "particles",
            "vector_field",
            "panel",
        }
        if spec["renderer"] == "svg":
            compatible.update({"node", "link", "arrow", "circle", "rect", "text"})
        if spec["scene"]["coordinate_system"] == "cartesian3d" or any(
            layer.get("type") not in compatible for layer in layers
        ):
            errors.append(
                {
                    "code": "renderer_mismatch",
                    "detail": "SVG/Canvas scenes require a 2D coordinate system and 2D primitives.",
                }
            )

    terms = _topic_terms(request)
    layer_matches = []
    for index, layer in enumerate(meaningful):
        label_tokens = _topic_terms(
            " ".join(str(layer.get(field, "")) for field in ("label", "text", "title"))
        )
        matches = terms.intersection(label_tokens)
        if matches:
            layer_matches.append((index, matches))
    grounded = (
        set().union(*(matches for _index, matches in layer_matches)) if layer_matches else set()
    )
    explicit_groups = _explicit_entity_groups(request)
    entity_nodes = _map_entity_nodes(explicit_groups, layers)
    required_grounding = min(3, len(terms))
    required_layers = min(2, required_grounding)
    topic_grounded = (
        len(entity_nodes) == len(explicit_groups)
        if explicit_groups
        else len(grounded) >= required_grounding and len(layer_matches) >= required_layers
    )
    if not topic_grounded:
        errors.append(
            {
                "code": "topic_not_grounded",
                "detail": (
                    "Represent concrete learner-request entities across distinct labelled geometry; "
                    f"matched {len(grounded)} of {required_grounding}, across "
                    f"{len(layer_matches)} of {required_layers} required layers, with "
                    f"{len(explicit_groups) - len(entity_nodes)} entity nodes ambiguous or missing."
                ),
            }
        )
    if _STRUCTURAL_RELATIONSHIP_SIGNAL.search(request):
        links = [layer for layer in meaningful if layer.get("type") == "link"]
        directional_chains = _directional_entity_chains(request)
        undirected_components = _undirected_entity_components(request)
        undirected_requested = bool(_UNDIRECTED_SIGNAL.search(request))
        relationship_grounded = bool(links)
        if (
            relationship_grounded
            and undirected_requested
            and not directional_chains
            and not undirected_components
        ):
            relationship_grounded = all(not layer.get("arrow") for layer in links)
        elif relationship_grounded and not directional_chains and not undirected_components:
            relationship_grounded = all(layer.get("arrow") for layer in links)
        if relationship_grounded and explicit_groups:
            relationship_grounded = len(entity_nodes) == len(explicit_groups)
        undirected: dict[str, set[str]] = {}
        non_directional: dict[str, set[str]] = {}
        if relationship_grounded:
            for link in links:
                start = str(link["from"])
                target = str(link["to"])
                undirected.setdefault(start, set()).add(target)
                undirected.setdefault(target, set()).add(start)
                if not link.get("arrow"):
                    non_directional.setdefault(start, set()).add(target)
                    non_directional.setdefault(target, set()).add(start)
        if relationship_grounded and len(explicit_groups) > 1:
            directional_entities = {
                group for chain in directional_chains for group in chain
            }
            undirected_entities = {
                group for component in undirected_components for group in component
            }
            extra_groups = [
                group
                for group in explicit_groups
                if group not in directional_entities and group not in undirected_entities
            ]
            if not directional_chains and not undirected_components:
                mapped = [entity_nodes[group] for group in explicit_groups]
                relationship_grounded = all(
                    _has_path(undirected, mapped[0], node_id) for node_id in mapped[1:]
                )
            elif extra_groups:
                component_nodes = [
                    entity_nodes[group]
                    for chain in directional_chains
                    for group in chain
                ] + [
                    entity_nodes[group]
                    for component in undirected_components
                    for group in component
                ]
                relationship_grounded = all(
                    any(
                        _has_path(undirected, entity_nodes[group], component_node)
                        for component_node in component_nodes
                    )
                    for group in extra_groups
                )
        if relationship_grounded and directional_chains:
            directed: dict[str, set[str]] = {}
            for link in links:
                if link.get("arrow"):
                    directed.setdefault(str(link["from"]), set()).add(str(link["to"]))
            relationship_grounded = all(
                all(
                    _has_path(
                        directed,
                        entity_nodes[start],
                        entity_nodes[target],
                        require_edge=True,
                    )
                    for start, target in pairwise(directional_groups)
                )
                for directional_groups in directional_chains
            )
        if relationship_grounded and undirected_components:
            relationship_grounded = all(
                all(
                    _has_path(
                        non_directional,
                        entity_nodes[component[0]],
                        entity_nodes[group],
                        require_edge=True,
                    )
                    for group in component[1:]
                )
                for component in undirected_components
            )
        if not relationship_grounded:
            errors.append(
                {
                    "code": "relationship_not_grounded",
                    "detail": (
                        "Graph and process requests require correctly directed or explicitly "
                        "undirected paths for each distinct requested entity component."
                    ),
                }
            )
    parameter_controls = [
        control
        for control in spec["controls"]
        if control["id"] not in TRANSPORT_CONTROL_IDS
        and control["type"] in {"range", "step"}
    ]
    unsupported_controls = [
        control
        for control in spec["controls"]
        if (
            control["id"] in TRANSPORT_CONTROL_IDS
            and control["type"] != "button"
            or control["id"] not in TRANSPORT_CONTROL_IDS
            and control["type"] not in {"range", "step"}
        )
    ]
    if unsupported_controls:
        errors.append(
            {
                "code": "control_unsupported",
                "detail": "Generic planner controls must be bound numeric range or step controls.",
            }
        )
    has_animation = "animation" in spec["scene"]
    if parameter_controls and any(control.get("binding") is None for control in parameter_controls):
        errors.append(
            {
                "code": "control_unbound",
                "detail": "Every parameter control must bind to one labelled layer and safe effect.",
            }
        )
    requested_control_groups = _requested_control_groups(request)
    mapped_control_groups = _map_control_groups(requested_control_groups, parameter_controls)
    if requested_control_groups and len(mapped_control_groups) != len(requested_control_groups):
        errors.append(
            {
                "code": "interaction_not_grounded",
                "detail": (
                    "Each named slider or control parameter needs one distinct bound numeric "
                    "control with a matching accessible label."
                ),
            }
        )
    if _INTERACTION_SIGNAL.search(request) and not (
        parameter_controls or "animation" in spec["scene"]
    ):
        errors.append(
            {
                "code": "interaction_missing",
                "detail": "The request asks for interaction; include at least one bounded named control.",
            }
        )
    if _ANIMATION_SIGNAL.search(request) and not has_animation:
        errors.append(
            {
                "code": "animation_missing",
                "detail": "Use guided_reveal plus accessible Play, Pause, and Restart buttons.",
            }
        )
    return errors


def _decode_candidate(
    engine: ChatEngine,
    messages: list[dict[str, str]],
    *,
    cancel_event: Any | None,
    on_generation: Callable[[Generation], None] | None,
) -> object | None:
    params = {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 1,
        "min_p": 0.0,
        "repeat_penalty": 1.0,
        "seed": 4242,
        "max_tokens": 1200,
        "enable_thinking": False,
        "response_format": {"type": "json_schema", "json_schema": planner_schema_v2()},
    }
    stream = None
    started = time.monotonic()
    chunks = 0
    try:
        fitted_messages, fitted_params = engine._fit_request(
            messages, params, protected_tail_messages=1
        )
        client = getattr(engine.client, "local", engine.client)
        stream_params = dict(fitted_params)
        if cancel_event is not None:
            stream_params["_muta_cancel_event"] = cancel_event
        stream = client.stream_events(fitted_messages, **stream_params)
        content: list[str] = []
        for event, text in stream:
            if cancel_event is not None and cancel_event.is_set():
                return None
            if event == "content" and text:
                content.append(text)
                chunks += 1
        if cancel_event is not None and cancel_event.is_set():
            return None
        raw = "".join(content)
        elapsed = time.monotonic() - started
        if on_generation is not None:
            generation = Generation(
                text=raw,
                prompt_tokens=0,
                completion_tokens=chunks,
                elapsed_s=elapsed,
                tokens_per_second=(chunks / elapsed if chunks and elapsed else 0),
                from_wall_clock=True,
            )
            try:
                on_generation(generation)
            except Exception:
                log.warning("semantic planner telemetry callback failed", exc_info=True)
        return json.loads(raw)
    except Exception:
        log.warning("semantic visualization proposal failed", exc_info=True)
        return None
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()


def plan_visualization_v2(
    engine: ChatEngine,
    request: str,
    prose: str,
    *,
    cancel_event: Any | None = None,
    on_generation: Callable[[Generation], None] | None = None,
) -> dict[str, Any] | None:
    """Produce one validated V2 composition through at most one repair attempt."""
    system = (
        "Plan one educational visualization as V2 JSON data only. Use only the schema's "
        "allow-listed primitives, controls, renderer hint, relationships, and optional "
        "guided_reveal animation. Never emit JavaScript, HTML, CSS, SVG markup, shaders, URLs, "
        "library source, or executable syntax. Preserve the learner's subject and directions. "
        "Every control needs an accessible label; every visual needs a useful text fallback."
    )
    base_user = (
        f"LEARNER REQUEST:\n{request}\n\nFINISHED EXPLANATION:\n{prose}\n\n"
        "Budget: at most 24 layers, 512 points, 4096 triangles, and 20 fps. "
        "Every non-transport parameter control must include a binding to one unique labelled "
        "layer using only translate_x, translate_y, scale, or radius."
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": base_user}]
    errors: list[dict[str, str]] = []
    for attempt in range(MAX_PLANNER_ATTEMPTS):
        if cancel_event is not None and cancel_event.is_set():
            return None
        if attempt:
            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        base_user
                        + "\n\nThe previous proposal was rejected. Return a complete replacement. "
                        + "Structured errors:\n"
                        + json.dumps(errors, ensure_ascii=False, separators=(",", ":"))
                    ),
                },
            ]
        candidate = _decode_candidate(
            engine,
            messages,
            cancel_event=cancel_event,
            on_generation=on_generation,
        )
        if candidate is None:
            return None
        errors = _plan_errors(candidate, request)
        if not errors:
            return validate_v2_spec(candidate)  # type: ignore[arg-type]
        log.info(
            "semantic visualization proposal rejected on attempt %d: %s",
            attempt + 1,
            ",".join(error["code"] for error in errors),
        )
    return None
