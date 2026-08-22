"""Turn-local policy and constrained model pass for live visual explanations.

The tutor first writes ordinary prose. A second, schema-constrained completion translates the
learner's exact request and that prose into bounded declarative data. Separating the two jobs is
important for the 0.6B model: a concrete all-purpose example was copied verbatim and could silently
contradict the lesson, while mixed prose+JSON was frequently omitted or malformed.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from runtime.chat import ChatEngine
from runtime.client import Generation

log = logging.getLogger("muta.gateway.visualizations")

_EXPLICIT_VISUAL = re.compile(
    r"\b(?:visuali[sz](?:e|ation)|visual|graph|plot|chart|diagram|draw|sketch|curve|axes?|"
    r"interactive|rotate|animate|animation|3d|three[- ]dimensional|d3(?:\.js)?|three\.js|"
    r"gsap|anime\.js|motion\.js|graphique|trace[rz]?|dessin(?:er)?|grafu|igrafu|eserese|"
    r"ግራፍ|رسم\s+بياني)\b",
    re.IGNORECASE,
)
_NO_VISUAL = re.compile(
    r"(?:\b(?:do\s+not|don't|no|without)\b.{0,28}\b(?:visual|graph|plot|chart|diagram|"
    r"animation)\b|\btext\s+only\b)",
    re.IGNORECASE,
)
_UNSUPPORTED_VISUAL = re.compile(
    r"\b(?:pie\s+(?:chart|graph)|triangle.{0,24}diagram|diagram.{0,24}triangle)\b",
    re.IGNORECASE,
)
_EXPLANATION = re.compile(
    r"\b(?:explain|show|illustrate|demonstrate|help me understand|compare)\b", re.IGNORECASE
)
_SPATIAL_TOPIC = re.compile(
    r"\b(?:shape|trajectory|projectile|orbit|derivative|distribution|vector field|"
    r"coordinate plane|transformation|wave|network|relationship|change over time)\b",
    re.IGNORECASE,
)

_PROSE_TURN_INSTRUCTION = (
    "The learner requested an explanatory visual. Write at least two complete, mathematically "
    "consistent prose sentences that work without it. A separate trusted renderer pass will add "
    "the visual, so do not output JSON, code, a muta-viz fence, or library instructions."
)


def wants_live_visual(text: str) -> bool:
    """Trigger on an explicit request or a clearly visual explanatory topic."""
    value = str(text or "")
    if _NO_VISUAL.search(value):
        return False
    return bool(_EXPLICIT_VISUAL.search(value)) or bool(
        _EXPLANATION.search(value) and _SPATIAL_TOPIC.search(value)
    )


def select_library(text: str) -> str:
    """Choose one adapter from explicit wording; generic plots use D3."""
    value = str(text or "").lower()
    if "three.js" in value or re.search(r"\b(?:3d|three[- ]dimensional)\b", value):
        return "three"
    if re.search(r"\bgsap\b", value):
        return "gsap"
    if re.search(r"\banime(?:\.js)?\b", value):
        return "anime"
    if "motion.js" in value or re.search(r"\buse motion\b", value):
        return "motion"
    if re.search(r"\b(?:animate|animation)\b", value):
        return "anime"
    return "d3"


def select_kind(text: str, library: str | None = None) -> str:
    """Select a supported kind before generation so the grammar cannot drift to another one."""
    chosen = library or select_library(text)
    if chosen == "three":
        return "scene3d"
    if chosen != "d3":
        return "animation"
    value = str(text or "").lower()
    if re.search(r"\b(?:force|network|nodes?|connections?|linked)\b", value):
        return "force"
    if re.search(r"\b(?:bar|bars|histogram|categories|category)\b", value):
        return "bar"
    if re.search(r"\bscatter\b", value):
        return "scatter"
    return "line"


def _animation_field(text: str) -> str:
    value = str(text or "").lower()
    if re.search(r"\b(?:rotat|turn|spin)", value):
        return "rotate"
    if re.search(r"\b(?:scal\w*|grow\w*|shrink\w*|resiz\w*|size)\b", value):
        return "scale"
    if re.search(r"\b(?:fade|opacity|transparent)\b", value):
        return "opacity"
    if re.search(r"\b(?:vertical|upward|downward|up|down|y\s*=)", value):
        return "y"
    return "x"


def _animation_element_type(text: str) -> str:
    value = str(text or "").lower()
    if re.search(r"\b(?:rectangle|rect|box|square)\b", value):
        return "rect"
    if re.search(r"\barrow\b", value):
        return "arrow"
    if re.search(r"\bline\b", value):
        return "line"
    if re.search(r"\btext\b", value):
        return "text"
    return "circle"


def _three_object_type(text: str) -> str:
    value = str(text or "").lower()
    if re.search(r"\bvector\b", value):
        return "vector"
    if re.search(r"\b(?:line|path|trajectory)\b", value):
        return "line"
    if re.search(r"\b(?:box|cube)\b", value):
        return "box"
    if re.search(r"\b(?:point|coordinate)\b", value):
        return "point"
    return "sphere"


def _animation_duration(text: str) -> float:
    match = re.search(
        r"\b(?:over|for|duration(?:\s+of)?)\s*(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?)\b",
        str(text or ""),
        re.IGNORECASE,
    )
    if not match:
        return 2
    return min(30, max(0.05, float(match.group(1))))


def _animation_repeat(text: str) -> int:
    """Keep generated animation finite, even when the learner asks to see it loop."""
    value = str(text or "")
    explicit = re.search(
        r"\b(?:repeat|loop)\b[^.\n]{0,24}?\b(\d{1,2})\s*(?:times?)?\b",
        value,
        re.IGNORECASE,
    )
    if explicit:
        return min(3, max(0, int(explicit.group(1)) - 1))
    if re.search(r"\b(?:repeat|loop|again)\b", value, re.IGNORECASE):
        return 1
    return 0


def turn_instruction(text: str, language_instruction: str = "") -> str:
    """Keep the primary tutoring completion prose-only; the constrained pass owns the spec."""
    parts = [language_instruction.strip()] if language_instruction.strip() else []
    if wants_live_visual(text):
        parts.append(_PROSE_TURN_INSTRUCTION)
    return "\n\n".join(parts)


def _common_properties(library: str, kind: str) -> dict[str, Any]:
    return {
        "version": {"type": "integer", "enum": [1]},
        "library": {"type": "string", "enum": [library]},
        "kind": {"type": "string", "enum": [kind]},
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "aria_label": {"type": "string", "minLength": 1, "maxLength": 300},
        "height": {"type": "integer", "minimum": 240, "maximum": 600},
    }


def _point_schema(dimensions: int = 2) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "number", "minimum": -1000, "maximum": 1000},
        "minItems": dimensions,
        "maxItems": dimensions,
    }


def visualization_schema(library: str, kind: str, request: str = "") -> dict[str, Any]:
    """Strict llama-server response schema for one selected adapter/kind."""
    properties = _common_properties(library, kind)
    required = ["version", "library", "kind", "title", "aria_label", "height"]
    if library == "d3" and kind in {"line", "scatter"}:
        properties.update(
            {
                "x_label": {"type": "string", "maxLength": 80},
                "y_label": {"type": "string", "maxLength": 80},
                "series": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "minLength": 1, "maxLength": 80},
                            "points": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 200,
                                "items": _point_schema(),
                            },
                        },
                        "required": ["label", "points"],
                        "additionalProperties": False,
                    },
                },
            }
        )
        required.extend(["x_label", "y_label", "series"])
    elif library == "d3" and kind == "bar":
        properties["data"] = {
            "type": "array",
            "minItems": 1,
            "maxItems": 30,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "minLength": 1, "maxLength": 80},
                    "value": {"type": "number", "minimum": -1000000, "maximum": 1000000},
                },
                "required": ["label", "value"],
                "additionalProperties": False,
            },
        }
        required.append("data")
    elif library == "d3":
        properties.update(
            {
                "nodes": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"},
                            "label": {"type": "string", "maxLength": 80},
                        },
                        "required": ["id", "label"],
                        "additionalProperties": False,
                    },
                },
                "links": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                        },
                        "required": ["source", "target"],
                        "additionalProperties": False,
                    },
                },
            }
        )
        required.extend(["nodes", "links"])
    elif library == "three":
        object_type = _three_object_type(request)
        object_properties: dict[str, Any] = {
            "type": {"type": "string", "enum": [object_type]},
            "label": {"type": "string", "minLength": 1, "maxLength": 80},
        }
        object_required = ["type", "label"]
        if object_type == "vector":
            object_properties.update({"from": _point_schema(3), "to": _point_schema(3)})
            object_required.extend(["from", "to"])
        elif object_type == "line":
            object_properties["points"] = {
                "type": "array",
                "minItems": 2,
                "maxItems": 100,
                "items": _point_schema(3),
            }
            object_required.append("points")
        else:
            object_properties.update(
                {
                    "position": _point_schema(3),
                    "size": {"type": "number", "minimum": 0.01, "maximum": 100},
                }
            )
            object_required.extend(["position", "size"])
        properties["objects"] = {
            "type": "array",
            "minItems": 1,
            "maxItems": 40,
            "items": {
                "type": "object",
                "properties": object_properties,
                "required": object_required,
                "additionalProperties": False,
            },
        }
        required.append("objects")
    else:
        field = _animation_field(request)
        element_type = _animation_element_type(request)
        state_range = (
            {"type": "number", "minimum": 0, "maximum": 1}
            if field == "opacity"
            else {"type": "number", "minimum": 0.01, "maximum": 100}
            if field == "scale"
            else {"type": "number", "minimum": -10000, "maximum": 10000}
        )
        state_schema = {
            "type": "object",
            "properties": {field: state_range},
            "required": [field],
            "additionalProperties": False,
        }
        properties.update(
            {
                "elements": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "enum": ["subject"]},
                            "type": {"type": "string", "enum": [element_type]},
                            "x": {"type": "number", "minimum": -10000, "maximum": 10000},
                            "y": {"type": "number", "minimum": -10000, "maximum": 10000},
                            "r": {"type": "number", "minimum": 0.1, "maximum": 1000},
                            "width": {"type": "number", "minimum": 0.1, "maximum": 1000},
                            "height": {"type": "number", "minimum": 0.1, "maximum": 1000},
                            "text": {"type": "string", "maxLength": 160},
                        },
                        "required": ["id", "type", "x", "y"],
                        "additionalProperties": False,
                    },
                },
                "tracks": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "enum": ["subject"]},
                            "from": state_schema,
                            "to": state_schema,
                            "duration": {
                                "type": "number",
                                "enum": [_animation_duration(request)],
                            },
                            "delay": {"type": "number", "minimum": 0, "maximum": 30},
                            "repeat": {
                                "type": "integer",
                                "enum": [_animation_repeat(request)],
                            },
                            "direction": {"type": "string", "enum": ["normal", "alternate"]},
                        },
                        "required": ["target", "from", "to", "duration"],
                        "additionalProperties": False,
                    },
                },
            }
        )
        required.extend(["elements", "tracks"])
    return {
        "name": f"muta_{library}_{kind}",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def _generated_spec_is_usable(spec: object, library: str, kind: str, request: str = "") -> bool:
    """Cheap server-side mirror of invariants that would otherwise make the iframe reject."""
    if not isinstance(spec, dict):
        return False
    if (
        spec.get("version") != 1
        or spec.get("library") != library
        or spec.get("kind") != kind
        or not isinstance(spec.get("title"), str)
        or not isinstance(spec.get("aria_label"), str)
    ):
        return False
    height = spec.get("height")
    if not isinstance(height, int) or isinstance(height, bool) or not 240 <= height <= 600:
        return False
    if library == "d3" and kind in {"line", "scatter"}:
        return bool(spec.get("series"))
    if library == "d3" and kind == "bar":
        return bool(spec.get("data"))
    if library == "d3":
        nodes = spec.get("nodes")
        ids = {node.get("id") for node in nodes or [] if isinstance(node, dict)}
        return (
            len(ids) == len(nodes or [])
            and len(ids) >= 2
            and all(
                isinstance(link, dict) and link.get("source") in ids and link.get("target") in ids
                for link in spec.get("links") or []
            )
        )
    if library == "three":
        for item in spec.get("objects") or []:
            if not isinstance(item, dict):
                return False
            if item.get("type") == "vector" and (
                item.get("from") == item.get("to")
                or not isinstance(item.get("from"), list)
                or not isinstance(item.get("to"), list)
            ):
                return False
        return bool(spec.get("objects"))
    field = _animation_field(request)
    tracks = spec.get("tracks") or []
    targets = [track.get("target") for track in tracks if isinstance(track, dict)]
    ids = {element.get("id") for element in spec.get("elements") or [] if isinstance(element, dict)}
    return (
        bool(targets)
        and len(targets) == len(tracks) == len(set(targets))
        and all(target in ids for target in targets)
        and all(
            isinstance(track.get("duration"), (int, float))
            and 0.05 <= track["duration"] <= 30
            and isinstance(track.get("from"), dict)
            and isinstance(track.get("to"), dict)
            and set(track["from"]) == {field}
            and set(track["to"]) == {field}
            for track in tracks
        )
    )


def _normalize_generated_spec(spec: object, library: str, request: str) -> object:
    """Repair unambiguous unit/id slips without inventing teaching data."""
    if not isinstance(spec, dict):
        return spec
    if library == "d3":
        # This exact, common function is safer to verify deterministically than to accept a
        # one-sided sample that fails to show the U shape the explanation discusses.
        quadratic = re.search(
            r"\by\s*=\s*x(?:\s*(?:\^\s*2|²)|\s+squared)\b(?!\s*[+\-*/])",
            request,
            re.IGNORECASE,
        )
        if quadratic and spec.get("kind") == "line" and spec.get("series"):
            bounds = re.search(
                r"\bfrom\s*(-?\d+(?:\.\d+)?)\s+to\s*(-?\d+(?:\.\d+)?)\b",
                request,
                re.IGNORECASE,
            )
            low, high = (
                (-2.0, 2.0) if not bounds else (float(bounds.group(1)), float(bounds.group(2)))
            )
            if low > high:
                low, high = high, low
            step = (high - low) / 8 if high > low else 1
            xs = (
                [low + step * index for index in range(9)]
                if high > low
                else [low - 1, low, low + 1]
            )

            def clean(number: float) -> int | float:
                return int(number) if float(number).is_integer() else round(number, 4)

            spec["series"][0]["points"] = [[clean(x), clean(x * x)] for x in xs]
            spec["series"][0]["label"] = "y = x²"
        return spec
    if library == "three":
        return spec
    elements = spec.get("elements")
    tracks = spec.get("tracks")
    if not isinstance(elements, list) or not isinstance(tracks, list):
        return spec
    elements[:] = [item for item in elements if isinstance(item, dict)][:1]
    tracks[:] = [item for item in tracks if isinstance(item, dict)][:1]
    if not elements or not tracks:
        return spec
    elements[0]["id"] = "subject"
    elements[0]["type"] = _animation_element_type(request)
    field = _animation_field(request)
    explicit_layout = bool(re.search(r"\b[xy]\s*=|\(-?\d+\s*,\s*-?\d+\)", request, re.IGNORECASE))
    if not explicit_layout and field not in {"x", "y"}:
        elements[0]["x"] = 360
        elements[0]["y"] = max(40, int(spec.get("height", 300)) // 2)
    ids = ["subject"]
    for index, track in enumerate(tracks):
        if not isinstance(track, dict):
            continue
        if track.get("target") not in ids and ids:
            track["target"] = ids[min(index, len(ids) - 1)]
        # Duration is presentation timing, not lesson data. Pin it to the requested seconds or
        # a calm two-second default; tiny models otherwise confuse degrees/pixels/milliseconds.
        track["duration"] = _animation_duration(request)
        track["repeat"] = _animation_repeat(request)
    if field == "y":
        y_values = [
            state.get("y")
            for track in tracks
            for state in (track.get("from", {}), track.get("to", {}))
            if isinstance(state, dict) and isinstance(state.get("y"), (int, float))
        ]
        if y_values:
            spec["height"] = min(600, max(int(spec.get("height", 300)), int(max(y_values)) + 30))
    spec["title"] = f"Animated {_animation_element_type(request)} with {library}"
    summary = " ".join(str(request).split())[:240]
    spec["aria_label"] = f"Animated explanation of: {summary}"
    return spec


def generate_visualization(
    engine: ChatEngine,
    request: str,
    prose: str,
    *,
    cancel_event: Any | None = None,
    on_generation: Callable[[Generation], None] | None = None,
) -> dict[str, Any] | None:
    """Ask the loaded local model for data only, under a selected JSON grammar.

    CloudFallbackClient deliberately exposes its guaranteed local client: the renderer pass must
    not create a second, undisclosed egress of student text and must work identically offline.
    """
    if cancel_event is not None and cancel_event.is_set():
        return None
    if _UNSUPPORTED_VISUAL.search(request):
        log.info("visual request uses an unsupported primitive; returning prose only")
        return None
    library = select_library(request)
    kind = select_kind(request, library)
    schema = visualization_schema(library, kind, request)
    adapter_detail = ""
    if library == "three":
        adapter_detail = f" Required object type: {_three_object_type(request)}."
    elif library not in {"d3", "three"}:
        adapter_detail = (
            f" Required element type: {_animation_element_type(request)}; animate only the "
            f"{_animation_field(request)} field. Put the real start/end values in from/to, and "
            "use duration only for seconds."
        )
    messages = [
        {
            "role": "system",
            "content": (
                "You convert a learner's exact request and its finished explanation into one "
                "declarative teaching visualization. Return JSON only. Preserve every requested "
                "number, coordinate, category, direction, shape, and relationship; do not copy "
                "generic example data or add facts that contradict the explanation. Use concise "
                "titles and an aria label that describes the actual visual."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Selected renderer: {library}/{kind}.{adapter_detail}\n"
                f"LEARNER REQUEST:\n{request}\n\nFINISHED EXPLANATION:\n{prose}"
            ),
        },
    ]
    params = {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 1,
        "min_p": 0.0,
        "repeat_penalty": 1.0,
        "seed": 4242,
        "max_tokens": 480,
        "enable_thinking": False,
        "response_format": {"type": "json_schema", "json_schema": schema},
    }
    # Use the same exact-token fitter as tutoring turns. It preserves both ends of an oversized
    # learner message, where the concrete values and final request normally live, and prevents a
    # max-contract input plus long prose from overflowing the guaranteed per-lane context.
    stream = None
    started = time.monotonic()
    completion_chunks = 0
    try:
        messages, params = engine._fit_request(messages, params, protected_tail_messages=1)
        client = getattr(engine.client, "local", engine.client)
        stream = client.stream_events(messages, **params)
        content: list[str] = []
        for event, text in stream:
            if cancel_event is not None and cancel_event.is_set():
                return None
            if event == "content" and text:
                content.append(text)
                completion_chunks += 1
        if cancel_event is not None and cancel_event.is_set():
            return None
        raw = "".join(content)
        elapsed = time.monotonic() - started
        generation = Generation(
            text=raw,
            prompt_tokens=0,
            completion_tokens=completion_chunks,
            elapsed_s=elapsed,
            tokens_per_second=(completion_chunks / elapsed if completion_chunks and elapsed else 0),
            from_wall_clock=True,
        )
        if on_generation is not None:
            try:
                on_generation(generation)
            except Exception:
                log.warning("visualization telemetry callback failed", exc_info=True)
        log.info(
            "visualization generation completed for %s/%s in %.3fs (%d streamed chunks)",
            library,
            kind,
            elapsed,
            completion_chunks,
        )
        spec = _normalize_generated_spec(json.loads(raw), library, request)
    except Exception:  # prose remains a complete degraded response
        log.warning("visualization generation failed for %s/%s", library, kind, exc_info=True)
        return None
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    if cancel_event is not None and cancel_event.is_set():
        return None
    if not _generated_spec_is_usable(spec, library, kind, request):
        log.warning("visualization model returned unusable %s/%s data", library, kind)
        return None
    return spec


def append_visualization(prose: str, spec: dict[str, Any]) -> str:
    """Serialize in the durable reply protocol consumed by browser and history replay."""
    payload = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    return f"{prose.rstrip()}\n\n```muta-viz\n{payload}\n```"
