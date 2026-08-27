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
from collections.abc import Callable
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
    r"\b(?:interactive|adjust|slider|control|change|vary|step\s+through|toggle)\b",
    re.IGNORECASE,
)
_ANIMATION_SIGNAL = re.compile(
    r"\b(?:animate|animation|make\s+it\s+move|moving|play|motion)\b",
    re.IGNORECASE,
)
_STRUCTURAL_RELATIONSHIP_SIGNAL = re.compile(
    r"\b(?:web|network|flow|cycle|process|path|loop|pipeline|hierarchy|tree|graph|"
    r"architecture|relationship)\b|\bfrom\b.{0,100}\bto\b",
    re.IGNORECASE | re.DOTALL,
)
_EXPLICIT_ENTITY_CLAUSE = re.compile(
    r"\b(?:showing|linking|connecting|between)\b(?P<entities>[^.!?;]{1,220})",
    re.IGNORECASE,
)
_DIRECTIONAL_CHAIN = re.compile(
    r"\bfrom\b(?P<entities>[^.!?;]{1,220})",
    re.IGNORECASE,
)
_DIRECTIONAL_TAIL = re.compile(
    r"\b(?:and\s+)?(?:let\s+(?:me|us)\b|allow\b|enable\b|"
    r"with\s+(?:an?\s+)?(?:adjustable|interactive)\b|where\s+(?:i|we|the\s+user)\b)",
    re.IGNORECASE,
)
_ENTITY_SEPARATOR = re.compile(
    r"\s*(?:,|\band\b|\bto\b|\bthrough\b|\binto\b|\bthen\b|->|→)\s*",
    re.IGNORECASE,
)
_RELATIONSHIP_TERMS = frozenset(
    {
        "connection",
        "connections",
        "energy",
        "flow",
        "flows",
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
    r"(?:<\s*/?\s*(?:script|iframe|object|embed|svg|canvas|style|link)\b|"
    r"\bjavascript\s*:|\bon\w+\s*=|\beval\s*\(|\bnew\s+Function\b|"
    r"\bfunction\s*\([^)]*\)\s*\{|=>|```|\bgl_FragColor\b|#version\s+\d+|"
    r"https?\s*:|\bdata\s*:|\bfile\s*:|\burl\s*\(|@import\b|[\"\s]//[A-Za-z0-9])",
    re.IGNORECASE,
)
_TOPIC_STOPWORDS = frozenset(
    {
        "about",
        "adjust",
        "adjustable",
        "animate",
        "animation",
        "build",
        "change",
        "chart",
        "control",
        "create",
        "diagram",
        "draw",
        "explain",
        "from",
        "graph",
        "illustrate",
        "interactive",
        "make",
        "model",
        "picture",
        "please",
        "plot",
        "render",
        "show",
        "showing",
        "simulate",
        "sketch",
        "that",
        "their",
        "these",
        "this",
        "through",
        "unfamiliar",
        "visualise",
        "visualize",
        "where",
        "which",
        "with",
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
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", request.lower())
        if token not in _TOPIC_STOPWORDS
    }


def _entity_groups(value: str) -> list[frozenset[str]]:
    """Split a bounded natural-language entity list while retaining multi-word names."""
    groups: list[frozenset[str]] = []
    for part in _ENTITY_SEPARATOR.split(value):
        terms = _topic_terms(part).difference(_RELATIONSHIP_TERMS)
        if terms:
            group = frozenset(terms)
            if group not in groups:
                groups.append(group)
    return groups


def _directional_entity_groups(request: str) -> list[frozenset[str]]:
    """Extract the ordered entities in an explicit from-A-to-B chain."""
    match = _DIRECTIONAL_CHAIN.search(request)
    if not match:
        return []
    chain = _DIRECTIONAL_TAIL.split(match.group("entities"), maxsplit=1)[0]
    return _entity_groups(chain)


def _explicit_entity_groups(request: str) -> list[frozenset[str]]:
    """Extract concrete entity phrases, preferring an explicit ordered chain when present."""
    directional = _directional_entity_groups(request)
    if directional:
        return directional
    groups: list[frozenset[str]] = []
    for match in _EXPLICIT_ENTITY_CLAUSE.finditer(request):
        for group in _entity_groups(match.group("entities")):
            if group not in groups:
                groups.append(group)
    return groups


def _map_entity_nodes(
    entity_groups: list[frozenset[str]], layers: list[dict[str, Any]]
) -> dict[frozenset[str], str]:
    """Map each entity phrase to one unambiguous, entity-specific labelled node."""
    node_tokens = {
        str(layer["id"]): _topic_terms(str(layer.get("label", "")))
        for layer in layers
        if layer.get("type") == "node"
    }
    top_candidates: dict[frozenset[str], list[str]] = {}
    for entity in entity_groups:
        scores = {
            node_id: len(entity.intersection(tokens))
            for node_id, tokens in node_tokens.items()
        }
        best = max(scores.values(), default=0)
        top_candidates[entity] = [
            node_id for node_id, score in scores.items() if best > 0 and score == best
        ]

    # A catch-all label (for example "algae crab heron") is not distinct geometry for any
    # one entity.  Exclude nodes that are a best match for multiple requested entities.
    candidate_owners: dict[str, int] = {}
    for candidates in top_candidates.values():
        for node_id in candidates:
            candidate_owners[node_id] = candidate_owners.get(node_id, 0) + 1

    mapping: dict[frozenset[str], str] = {}
    for entity, candidates in top_candidates.items():
        specific = [node_id for node_id in candidates if candidate_owners[node_id] == 1]
        if len(specific) == 1:
            mapping[entity] = specific[0]
    return mapping


def _has_path(adjacency: dict[str, set[str]], start: str, target: str) -> bool:
    """Return whether a bounded directed graph contains a path from start to target."""
    pending = [start]
    visited: set[str] = set()
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        pending.extend(adjacency.get(node, set()).difference(visited))
    return False


def _plan_errors(candidate: object, request: str) -> list[dict[str, str]]:
    """Return stable machine-readable validation and semantic-oracle failures."""
    try:
        spec = validate_v2_spec(candidate)  # type: ignore[arg-type]
    except (VisualizationV2Error, TypeError, ValueError) as exc:
        return [{"code": "schema_invalid", "detail": str(exc)[:200]}]

    errors: list[dict[str, str]] = []
    serialized = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    if _FORBIDDEN_AUTHORED_SOURCE.search(serialized):
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
    if (
        len(grounded) < required_grounding
        or len(layer_matches) < required_layers
        or len(entity_nodes) != len(explicit_groups)
    ):
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
        relationship_grounded = bool(links) and all(layer.get("arrow") for layer in links)
        if relationship_grounded and explicit_groups:
            relationship_grounded = len(entity_nodes) == len(explicit_groups)
        if relationship_grounded and len(explicit_groups) > 1:
            undirected: dict[str, set[str]] = {}
            for link in links:
                start = str(link["from"])
                target = str(link["to"])
                undirected.setdefault(start, set()).add(target)
                undirected.setdefault(target, set()).add(start)
            mapped = [entity_nodes[group] for group in explicit_groups]
            relationship_grounded = all(
                _has_path(undirected, mapped[0], node_id) for node_id in mapped[1:]
            )
        directional_groups = _directional_entity_groups(request)
        if relationship_grounded and len(directional_groups) > 1:
            directed: dict[str, set[str]] = {}
            for link in links:
                directed.setdefault(str(link["from"]), set()).add(str(link["to"]))
            relationship_grounded = all(
                _has_path(directed, entity_nodes[start], entity_nodes[target])
                for start, target in pairwise(directional_groups)
            )
        if not relationship_grounded:
            errors.append(
                {
                    "code": "relationship_not_grounded",
                    "detail": (
                        "Graph and process requests require correctly directed paths connecting "
                        "each distinct requested entity node."
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
