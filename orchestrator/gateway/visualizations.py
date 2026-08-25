"""Turn-local policy and constrained model pass for live visual explanations.

The tutor first writes ordinary prose. A second, schema-constrained completion translates the
learner's exact request and that prose into bounded declarative data. Separating the two jobs is
important for the 0.6B model: a concrete all-purpose example was copied verbatim and could silently
contradict the lesson, while mixed prose+JSON was frequently omitted or malformed.
"""

from __future__ import annotations

import json
import logging
import math
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
_OUTPUT_IMAGE_REQUEST = re.compile(
    r"\b(?:draw|generate|create|make|show|need|want|see|give)\b.{0,36}"
    r"\b(?:image|picture|illustration|model)\b",
    re.IGNORECASE,
)
_NO_VISUAL = re.compile(
    r"(?:\b(?:do\s+not|don't|without)\b.{0,28}\b(?:visual|graph|plot|chart|diagram|"
    r"animation)\b|\bno\s+(?:(?:live|interactive)\s+)?(?:visual|graph|plot|chart|diagram|"
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
    r"coordinate plane|transformation|wave|phase shift|network|relationship|"
    r"change over time|anatomy|heart|circulation|molecule|molecular|hydrocarbon|"
    r"methane|ethane|ethene|ethylene|ethyne|acetylene|propane|butane|satellite|"
    r"chemical structure|structural formula)\b",
    re.IGNORECASE,
)
_VECTOR_TOPIC = re.compile(r"\bvectors?\b", re.IGNORECASE)
_VECTOR_ADDITION_TERM = re.compile(
    r"\b(?:addition|add(?:ing)?|sum|resultant|head[- ]to[- ]tail)\b", re.IGNORECASE
)
_ANAPHORIC_VISUAL = re.compile(
    r"(?:\b(?:it|this|that|same|again)\b|"
    r"\bwhere\s+(?:is|was)\s+(?:the\s+)?(?:diagram|visual|image|animation)\b)",
    re.IGNORECASE,
)
_ANIMATION_REQUEST = re.compile(
    r"\b(?:animate|animation|gsap|anime(?:\.js)?|motion(?:\.js)?)\b", re.IGNORECASE
)
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_VECTOR_TUPLE = re.compile(rf"[\[(]\s*({_NUMBER})\s*,\s*({_NUMBER})(?:\s*,\s*({_NUMBER}))?\s*[\])]")

_PHASE_SHIFT_TOPIC = re.compile(
    r"\b(?:phase\s+(?:shift|difference)|out\s+of\s+phase)\b", re.IGNORECASE
)
_PROJECTILE_TOPIC = re.compile(r"\b(?:projectile|ballistic|trajectory)\b", re.IGNORECASE)
_HEART_TOPIC = re.compile(r"\b(?:heart|cardiac|atria?|ventricles?|circulation)\b", re.IGNORECASE)
_HYDROCARBON_TOPIC = re.compile(
    r"\b(?:hydrocarbon|methane|ethane|ethene|ethylene|ethyne|acetylene|propane|butane)\b",
    re.IGNORECASE,
)
_SATELLITE_TOPIC = re.compile(r"\b(?:satellite|orbital?|orbiting)\b", re.IGNORECASE)
_VISUAL_REFUSAL = re.compile(
    r"(?:\b(?:cannot|can't|unable|not able|impossible)\b.{0,90}"
    r"\b(?:draw|render|generate|show|display|provide)\b.{0,50}"
    r"\b(?:diagrams?|images?|visuals?|animations?)\b|"
    r"\b(?:text[- ]based|purely text)\b.{0,100}"
    r"\b(?:diagrams?|images?|visuals?|animations?)\b|"
    r"\bcan only explain\b)",
    re.IGNORECASE | re.DOTALL,
)

_PROSE_TURN_INSTRUCTION = (
    "The learner explicitly requested an explanatory visual. Explain the requested subject "
    "accurately in at least two complete, mathematically consistent prose sentences. Never "
    "refuse the visual, claim that you are text-only, or say that you cannot draw, show, or "
    "display it: the application will add the live visual after your prose. A separate trusted "
    "renderer pass owns the visual, so do not output JSON, code, a muta-viz fence, or library "
    "instructions."
)


def wants_live_visual(text: str) -> bool:
    """Trigger on an explicit request or a clearly visual explanatory topic."""
    value = str(text or "")
    if _NO_VISUAL.search(value):
        return False
    return bool(_EXPLICIT_VISUAL.search(value) or _OUTPUT_IMAGE_REQUEST.search(value)) or bool(
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
    if _VECTOR_TOPIC.search(value):
        return "three"
    if re.search(r"\b(?:animate|animation)\b", value):
        return "anime"
    return "d3"


def _is_vector_addition(text: str) -> bool:
    return bool(_VECTOR_TOPIC.search(text) and _VECTOR_ADDITION_TERM.search(text))


def resolve_visualization_request(
    engine: ChatEngine,
    request: str,
    conversation_id: str | None = None,
) -> str:
    """Attach the preceding learner topic to a short visual follow-up.

    The current user and assistant rows have already been persisted when the visual pass runs.
    Looking only at the current text turns “animate it” into a generic moving circle; the most
    recent preceding user row supplies the subject without exposing unrelated older history.
    """
    value = str(request or "").strip()
    if not conversation_id or not _ANAPHORIC_VISUAL.search(value):
        return value
    try:
        rows = engine.store.get_messages(conversation_id, limit=8)
    except Exception:
        log.warning("could not resolve visualization follow-up context", exc_info=True)
        return value
    user_turns = [
        str(row.get("content") or "").strip()
        for row in rows
        if row.get("role") == "user" and str(row.get("content") or "").strip()
    ]
    if len(user_turns) < 2:
        return value
    return f"{user_turns[-2]}\n\nFOLLOW-UP VISUAL REQUEST: {value}"


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


def _clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 4)


def _format_vector(values: tuple[float, float, float], dimensions: int) -> str:
    shown = values[:dimensions]
    return "(" + ", ".join(str(_clean_number(value)) for value in shown) + ")"


def _vector_addition_operands(
    request: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float], int]:
    matches = list(_VECTOR_TUPLE.finditer(request))
    parsed: list[tuple[float, float, float]] = []
    dimensions = 2
    for match in matches[:2]:
        z_value = match.group(3)
        dimensions = max(dimensions, 3 if z_value is not None else 2)
        vector = (float(match.group(1)), float(match.group(2)), float(z_value or 0))
        if all(-500 <= value <= 500 for value in vector):
            parsed.append(vector)
    if len(parsed) != 2:
        return (2.0, 1.0, 0.0), (1.0, 2.0, 0.0), 2
    summed = tuple(parsed[0][index] + parsed[1][index] for index in range(3))
    if any(abs(value) > 1000 for value in summed):
        return (2.0, 1.0, 0.0), (1.0, 2.0, 0.0), 2
    return parsed[0], parsed[1], dimensions


def _three_vector_object(
    label: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> dict[str, Any]:
    if start == end:
        return {
            "type": "point",
            "label": label,
            "position": [_clean_number(value) for value in start],
            "size": 0.16,
        }
    return {
        "type": "vector",
        "label": label,
        "from": [_clean_number(value) for value in start],
        "to": [_clean_number(value) for value in end],
    }


def _vector_addition_three_spec(request: str) -> dict[str, Any]:
    first, second, dimensions = _vector_addition_operands(request)
    origin = (0.0, 0.0, 0.0)
    total = tuple(first[index] + second[index] for index in range(3))
    first_label = f"A = {_format_vector(first, dimensions)}"
    second_label = f"B = {_format_vector(second, dimensions)}"
    total_label = f"A + B = {_format_vector(total, dimensions)}"
    return {
        "version": 1,
        "library": "three",
        "kind": "scene3d",
        "title": "Vector addition: head to tail",
        "aria_label": (
            f"Interactive head-to-tail vector addition. {first_label} starts at the origin; "
            f"{second_label} starts at A's head; {total_label} runs from the origin to the "
            "final head. Drag or use arrow keys to rotate."
        ),
        "height": 380,
        "objects": [
            _three_vector_object(first_label, origin, first),
            _three_vector_object(second_label, first, total),
            _three_vector_object(total_label, origin, total),
        ],
    }


def _vector_addition_animation_spec(
    request: str,
    library: str,
) -> dict[str, Any]:
    first, second, dimensions = _vector_addition_operands(request)
    total = tuple(first[index] + second[index] for index in range(3))
    # The SVG adapters are two-dimensional. Preserve genuine 3D requests with the rotatable
    # Three.js scene instead of projecting away information the learner supplied.
    if dimensions == 3 and any(value != 0 for value in (first[2], second[2])):
        return _vector_addition_three_spec(request)

    math_points = [(0.0, 0.0), first[:2], total[:2]]
    min_x = min(point[0] for point in math_points)
    max_x = max(point[0] for point in math_points)
    min_y = min(point[1] for point in math_points)
    max_y = max(point[1] for point in math_points)
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    scale = min(420 / span_x, 210 / span_y, 90)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    def screen(point: tuple[float, float]) -> tuple[float, float]:
        return (
            round(360 + (point[0] - center_x) * scale, 3),
            round(165 - (point[1] - center_y) * scale, 3),
        )

    origin_xy = screen((0.0, 0.0))
    first_xy = screen(first[:2])
    total_xy = screen(total[:2])
    first_label = f"A = {_format_vector(first, dimensions)}"
    second_label = f"B = {_format_vector(second, dimensions)}"
    total_label = f"A + B = {_format_vector(total, dimensions)}"

    def arrow(
        element_id: str,
        base: tuple[float, float],
        delta: tuple[float, float],
    ) -> dict[str, Any]:
        if delta == (0.0, 0.0):
            return {
                "id": element_id,
                "type": "circle",
                "x": base[0],
                "y": base[1],
                "r": 7,
            }
        return {
            "id": element_id,
            "type": "arrow",
            "x": base[0],
            "y": base[1],
            "x1": 0,
            "y1": 0,
            "x2": round(delta[0], 3),
            "y2": round(delta[1], 3),
            "stroke_width": 5,
        }

    first_delta = (first_xy[0] - origin_xy[0], first_xy[1] - origin_xy[1])
    second_delta = (total_xy[0] - first_xy[0], total_xy[1] - first_xy[1])
    total_delta = (total_xy[0] - origin_xy[0], total_xy[1] - origin_xy[1])
    midpoint = lambda left, right: round((left + right) / 2, 3)
    repeat = _animation_repeat(request)
    return {
        "version": 1,
        "library": library,
        "kind": "animation",
        "title": "Vector addition: move B head to tail",
        "aria_label": (
            f"Replayable head-to-tail animation. {first_label}; {second_label} moves so its "
            f"tail meets A's head; then the resultant {total_label} appears."
        ),
        "height": 380,
        "elements": [
            arrow("vector_a", origin_xy, first_delta),
            arrow("vector_b", origin_xy, second_delta),
            arrow("resultant", origin_xy, total_delta),
            {
                "id": "label_a",
                "type": "text",
                "x": midpoint(origin_xy[0], first_xy[0]),
                "y": midpoint(origin_xy[1], first_xy[1]) - 18,
                "text": first_label,
            },
            {
                "id": "label_b",
                "type": "text",
                "x": midpoint(first_xy[0], total_xy[0]),
                "y": midpoint(first_xy[1], total_xy[1]) - 18,
                "text": second_label,
            },
            {
                "id": "label_sum",
                "type": "text",
                "x": midpoint(origin_xy[0], total_xy[0]),
                "y": midpoint(origin_xy[1], total_xy[1]) + 28,
                "text": total_label,
            },
        ],
        "tracks": [
            {
                "target": "vector_b",
                "from": {"x": origin_xy[0], "y": origin_xy[1], "opacity": 0.35},
                "to": {"x": first_xy[0], "y": first_xy[1], "opacity": 1},
                "duration": 1.6,
                "repeat": repeat,
                "direction": "normal",
            },
            {
                "target": "resultant",
                "from": {"opacity": 0},
                "to": {"opacity": 1},
                "duration": 0.9,
                "delay": 1.6,
                "repeat": repeat,
                "direction": "normal",
            },
        ],
    }


def _vector_addition_spec(request: str, current_request: str) -> dict[str, Any]:
    if _ANIMATION_REQUEST.search(current_request):
        library = select_library(current_request)
        if library in {"gsap", "anime", "motion"}:
            return _vector_addition_animation_spec(request, library)
    return _vector_addition_three_spec(request)


def _phase_shift_spec(request: str) -> dict[str, Any]:
    angle_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:°|degrees?|deg)\b", request, re.IGNORECASE)
    degrees = float(angle_match.group(1)) if angle_match else 90.0
    degrees = degrees % 360
    phase = math.radians(degrees)
    points_a: list[list[int | float]] = []
    points_b: list[list[int | float]] = []
    for index in range(33):
        x = (2 * math.pi * index) / 32
        points_a.append([round(x, 4), round(math.sin(x), 4)])
        points_b.append([round(x, 4), round(math.sin(x - phase), 4)])
    degree_label = _clean_number(degrees)
    return {
        "version": 1,
        "library": "d3",
        "kind": "line",
        "title": f"Sine-wave phase shift: {degree_label}°",
        "aria_label": (
            f"Two sine waves over one cycle. The second is shifted right by {degree_label} "
            "degrees, so matching peaks occur later along the horizontal axis."
        ),
        "height": 380,
        "x_label": "phase x (radians)",
        "y_label": "amplitude",
        "series": [
            {"label": "y = sin(x)", "points": points_a},
            {
                "label": f"y = sin(x − {degree_label}°)",
                "points": points_b,
            },
        ],
    }


def _projectile_spec(request: str) -> dict[str, Any]:
    speed_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:m/s|met(?:re|er)s?\s+per\s+second)\b",
        request,
        re.IGNORECASE,
    )
    angle_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:°|degrees?|deg)\b", request, re.IGNORECASE)
    speed = min(200.0, max(1.0, float(speed_match.group(1)) if speed_match else 20.0))
    angle = min(85.0, max(5.0, float(angle_match.group(1)) if angle_match else 45.0))
    gravity = 9.81
    theta = math.radians(angle)
    flight_time = (2 * speed * math.sin(theta)) / gravity
    points: list[list[int | float]] = []
    for index in range(25):
        elapsed = flight_time * index / 24
        x = speed * math.cos(theta) * elapsed
        y = max(0.0, speed * math.sin(theta) * elapsed - 0.5 * gravity * elapsed * elapsed)
        points.append([round(x, 3), round(y, 3)])
    speed_label = _clean_number(speed)
    angle_label = _clean_number(angle)
    return {
        "version": 1,
        "library": "d3",
        "kind": "line",
        "title": f"Projectile path: {speed_label} m/s at {angle_label}°",
        "aria_label": (
            f"A smooth parabolic projectile trajectory launched at {speed_label} metres per "
            f"second and {angle_label} degrees, using gravitational acceleration 9.81 metres "
            "per second squared and no air resistance."
        ),
        "height": 380,
        "x_label": "horizontal distance (m)",
        "y_label": "height (m)",
        "series": [{"label": "projectile", "points": points}],
    }


def _heart_spec() -> dict[str, Any]:
    return {
        "version": 1,
        "library": "d3",
        "kind": "diagram",
        "title": "Heart: double circulation",
        "aria_label": (
            "A labelled circulation schematic. Deoxygenated blood flows from the body through "
            "the right atrium and right ventricle to the lungs; oxygenated blood returns through "
            "the left atrium and left ventricle to the body."
        ),
        "height": 500,
        "nodes": [
            {
                "id": "lungs",
                "label": "Lungs",
                "x": 360,
                "y": 64,
                "shape": "rounded",
                "width": 130,
                "height": 54,
                "color": "teal",
            },
            {
                "id": "ra",
                "label": "Right atrium",
                "x": 210,
                "y": 190,
                "shape": "rounded",
                "width": 138,
                "height": 62,
                "color": "blue",
            },
            {
                "id": "rv",
                "label": "Right ventricle",
                "x": 210,
                "y": 330,
                "shape": "rounded",
                "width": 152,
                "height": 68,
                "color": "blue",
            },
            {
                "id": "la",
                "label": "Left atrium",
                "x": 510,
                "y": 190,
                "shape": "rounded",
                "width": 138,
                "height": 62,
                "color": "red",
            },
            {
                "id": "lv",
                "label": "Left ventricle",
                "x": 510,
                "y": 330,
                "shape": "rounded",
                "width": 152,
                "height": 68,
                "color": "red",
            },
            {
                "id": "body",
                "label": "Body tissues",
                "x": 360,
                "y": 450,
                "shape": "rounded",
                "width": 145,
                "height": 54,
                "color": "purple",
            },
        ],
        "links": [
            {
                "source": "body",
                "target": "ra",
                "label": "vena cava",
                "label_x": 100,
                "label_y": 365,
                "via": [[70, 450], [70, 190]],
                "arrow": True,
                "bond": "single",
            },
            {
                "source": "ra",
                "target": "rv",
                "label": "tricuspid valve",
                "label_x": 132,
                "label_y": 264,
                "arrow": True,
                "bond": "single",
            },
            {
                "source": "rv",
                "target": "lungs",
                "label": "pulmonary artery",
                "label_x": 245,
                "label_y": 115,
                "arrow": True,
                "bond": "single",
            },
            {
                "source": "lungs",
                "target": "la",
                "label": "pulmonary veins",
                "label_x": 505,
                "label_y": 115,
                "arrow": True,
                "bond": "single",
            },
            {
                "source": "la",
                "target": "lv",
                "label": "mitral valve",
                "label_x": 582,
                "label_y": 264,
                "arrow": True,
                "bond": "single",
            },
            {
                "source": "lv",
                "target": "body",
                "label": "aorta",
                "label_x": 468,
                "label_y": 416,
                "arrow": True,
                "bond": "single",
            },
        ],
        "annotations": [
            {"text": "deoxygenated blood", "x": 105, "y": 82},
            {"text": "oxygenated blood", "x": 615, "y": 82},
        ],
    }


def _hydrocarbon_identity(request: str) -> tuple[str, int, int, str]:
    value = request.lower()
    choices = [
        ("methane", 1, 1, "CH₄"),
        ("ethane", 2, 1, "C₂H₆"),
        ("ethene", 2, 2, "C₂H₄"),
        ("ethylene", 2, 2, "C₂H₄"),
        ("ethyne", 2, 3, "C₂H₂"),
        ("acetylene", 2, 3, "C₂H₂"),
        ("propane", 3, 1, "C₃H₈"),
        ("butane", 4, 1, "C₄H₁₀"),
    ]
    for name, carbons, bond, formula in choices:
        if re.search(rf"\b{re.escape(name)}\b", value):
            canonical = {"ethylene": "ethene", "acetylene": "ethyne"}.get(name, name)
            return canonical, carbons, bond, formula
    return "ethane", 2, 1, "C₂H₆"


def _hydrocarbon_spec(request: str) -> dict[str, Any]:
    name, carbon_count, chain_bond, formula = _hydrocarbon_identity(request)
    spacing = 130
    first_x = 360 - (carbon_count - 1) * spacing / 2
    carbon_y = 245
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for index in range(carbon_count):
        carbon_id = f"c{index + 1}"
        x = first_x + index * spacing
        nodes.append(
            {
                "id": carbon_id,
                "label": "C",
                "x": x,
                "y": carbon_y,
                "shape": "circle",
                "size": 27,
                "color": "gray",
            }
        )
        if index:
            links.append(
                {
                    "source": f"c{index}",
                    "target": carbon_id,
                    "bond": "single"
                    if index > 1
                    else {1: "single", 2: "double", 3: "triple"}[chain_bond],
                    "arrow": False,
                }
            )

        left_order = chain_bond if index == 1 else 1 if index > 1 else 0
        right_order = (
            chain_bond if index == 0 and carbon_count > 1 else 1 if index < carbon_count - 1 else 0
        )
        hydrogens = max(0, 4 - left_order - right_order)
        positions: list[tuple[float, float]] = []
        if carbon_count == 1:
            positions = [
                (x - 95, carbon_y),
                (x + 95, carbon_y),
                (x, carbon_y - 105),
                (x, carbon_y + 105),
            ]
        elif hydrogens == 3:
            outward = x - 95 if index == 0 else x + 95
            positions = [(outward, carbon_y), (x, carbon_y - 105), (x, carbon_y + 105)]
        elif hydrogens == 2:
            positions = [(x, carbon_y - 105), (x, carbon_y + 105)]
        elif hydrogens == 1:
            outward = x - 95 if index == 0 else x + 95
            positions = [(outward, carbon_y)]
        for hydrogen_index, (hx, hy) in enumerate(positions, start=1):
            hydrogen_id = f"h{index + 1}_{hydrogen_index}"
            nodes.append(
                {
                    "id": hydrogen_id,
                    "label": "H",
                    "x": hx,
                    "y": hy,
                    "shape": "circle",
                    "size": 21,
                    "color": "teal",
                }
            )
            links.append(
                {"source": carbon_id, "target": hydrogen_id, "bond": "single", "arrow": False}
            )
    return {
        "version": 1,
        "library": "d3",
        "kind": "diagram",
        "title": f"{name.capitalize()} structural formula ({formula})",
        "aria_label": (
            f"A displayed structural formula for {name}, {formula}. Carbon atoms have four "
            "bonds in total and every attached hydrogen completes a single bond."
        ),
        "height": 450,
        "nodes": nodes,
        "links": links,
        "annotations": [
            {"text": f"{name.capitalize()} · {formula}", "x": 360, "y": 42},
            {"text": "Each line is a shared electron-pair bond", "x": 360, "y": 418},
        ],
    }


def _satellite_orbit_spec() -> dict[str, Any]:
    orbit = [
        [
            round(3.2 * math.cos((2 * math.pi * index) / 48), 4),
            0,
            round(3.2 * math.sin((2 * math.pi * index) / 48), 4),
        ]
        for index in range(49)
    ]
    return {
        "version": 1,
        "library": "three",
        "kind": "scene3d",
        "title": "Satellite in circular orbit",
        "aria_label": (
            "A rotatable Earth-and-satellite scene. Gravity points inward and velocity is "
            "tangent to the orbit. For a circular orbit, v equals the square root of GM over r, "
            "and the period is two pi times the square root of r cubed over GM."
        ),
        "height": 430,
        "notes": ["Circular orbit: v = √(GM/r)", "Period: T = 2π√(r³/GM)"],
        "objects": [
            {
                "type": "sphere",
                "label": "Earth",
                "position": [0, 0, 0],
                "label_position": [-1.5, 1.7, 0],
                "size": 1.2,
                "color": "blue",
            },
            {
                "type": "line",
                "label": "orbit radius r",
                "label_position": [-3.2, 0.7, 0],
                "points": orbit,
                "color": "teal",
            },
            {
                "type": "box",
                "label": "satellite",
                "position": [3.2, 0, 0],
                "label_position": [3.3, 0.8, 0],
                "size": 0.35,
                "color": "gold",
            },
            {
                "type": "vector",
                "label": "gravity g",
                "from": [3.2, 0, 0],
                "to": [2.2, 0, 0],
                "label_position": [1.7, -0.65, 0],
                "color": "red",
            },
            {
                "type": "vector",
                "label": "velocity v",
                "from": [3.2, 0, 0],
                "to": [3.2, 0, 1.3],
                "label_position": [3.3, 0.25, 1.8],
                "color": "orange",
            },
        ],
    }


def _fallback_diagram(request: str) -> dict[str, Any]:
    topic = " ".join(str(request).replace("FOLLOW-UP VISUAL REQUEST:", "").split())
    topic = topic[:68].rstrip(".,!?;:") or "the requested concept"
    return {
        "version": 1,
        "library": "d3",
        "kind": "diagram",
        "title": f"Visual guide: {topic[:52]}",
        "aria_label": (
            f"A concept-map fallback for {topic}. It separates the given information, the key "
            "relationship, and the result to interpret without inventing numerical data."
        )[:300],
        "height": 360,
        "nodes": [
            {
                "id": "topic",
                "label": topic[:64],
                "x": 360,
                "y": 92,
                "shape": "rounded",
                "width": 260,
                "height": 64,
                "color": "orange",
            },
            {
                "id": "given",
                "label": "Given information",
                "x": 120,
                "y": 260,
                "shape": "rounded",
                "width": 150,
                "height": 54,
                "color": "teal",
            },
            {
                "id": "relation",
                "label": "Key relationship",
                "x": 360,
                "y": 260,
                "shape": "rounded",
                "width": 150,
                "height": 54,
                "color": "purple",
            },
            {
                "id": "meaning",
                "label": "Result and meaning",
                "x": 600,
                "y": 260,
                "shape": "rounded",
                "width": 155,
                "height": 54,
                "color": "blue",
            },
        ],
        "links": [
            {"source": "topic", "target": "given", "bond": "single", "arrow": True},
            {"source": "topic", "target": "relation", "bond": "single", "arrow": True},
            {"source": "topic", "target": "meaning", "bond": "single", "arrow": True},
        ],
        "annotations": [],
    }


def _semantic_visualization(request: str, current_request: str) -> dict[str, Any] | None:
    if _is_vector_addition(request):
        return _vector_addition_spec(request, current_request)
    if _PHASE_SHIFT_TOPIC.search(request):
        return _phase_shift_spec(request)
    if _PROJECTILE_TOPIC.search(request):
        return _projectile_spec(request)
    if _HEART_TOPIC.search(request):
        return _heart_spec()
    if _HYDROCARBON_TOPIC.search(request):
        return _hydrocarbon_spec(request)
    if _SATELLITE_TOPIC.search(request):
        return _satellite_orbit_spec()
    return None


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
        # Keep the grammar comfortably below the constrained pass's token ceiling. The browser
        # accepts larger hand-authored specs, but a tiny model tends to fill permissive arrays
        # to their maximum and can otherwise spend the entire decode budget listing points.
        series_limit = (
            2 if re.search(r"\b(?:compare|versus|vs\.?|both|two)\b", request, re.IGNORECASE) else 1
        )
        properties.update(
            {
                "x_label": {"type": "string", "maxLength": 80},
                "y_label": {"type": "string", "maxLength": 80},
                "series": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": series_limit,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "minLength": 1, "maxLength": 80},
                            "points": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 24,
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
            # The frame can replay richer hand-authored scenes, but a tiny model tends to fill
            # permissive arrays to their maximum. Eight objects fit the constrained decode budget.
            "maxItems": 8,
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
    if library == "d3" and kind == "diagram":
        nodes = spec.get("nodes")
        ids = {node.get("id") for node in nodes or [] if isinstance(node, dict)}
        return (
            len(ids) == len(nodes or [])
            and len(ids) >= 1
            and all(
                isinstance(link, dict) and link.get("source") in ids and link.get("target") in ids
                for link in spec.get("links") or []
            )
        )
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
    conversation_id: str | None = None,
    cancel_event: Any | None = None,
    on_generation: Callable[[Generation], None] | None = None,
) -> dict[str, Any] | None:
    """Ask the loaded local model for data only, under a selected JSON grammar.

    CloudFallbackClient deliberately exposes its guaranteed local client: the renderer pass must
    not create a second, undisclosed egress of student text and must work identically offline.
    """
    if cancel_event is not None and cancel_event.is_set():
        return None
    resolved_request = resolve_visualization_request(engine, request, conversation_id)
    semantic = _semantic_visualization(resolved_request, request)
    if semantic is not None:
        return semantic
    fallback = _fallback_diagram(resolved_request)
    if _UNSUPPORTED_VISUAL.search(resolved_request):
        log.info("visual request uses an unsupported primitive; returning a safe schematic")
        return fallback
    library = select_library(resolved_request)
    kind = select_kind(resolved_request, library)
    schema = visualization_schema(library, kind, resolved_request)
    adapter_detail = ""
    if library == "three":
        adapter_detail = f" Required object type: {_three_object_type(resolved_request)}."
    elif library not in {"d3", "three"}:
        adapter_detail = (
            f" Required element type: {_animation_element_type(resolved_request)}; animate only "
            f"the {_animation_field(resolved_request)} field. Put the real start/end values in "
            "from/to, and use duration only for seconds."
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
                f"LEARNER REQUEST:\n{resolved_request}\n\nFINISHED EXPLANATION:\n{prose}"
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
        "max_tokens": 320,
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
        spec = _normalize_generated_spec(json.loads(raw), library, resolved_request)
    except Exception:
        log.warning("visualization generation failed for %s/%s", library, kind, exc_info=True)
        return None if cancel_event is not None and cancel_event.is_set() else fallback
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    if cancel_event is not None and cancel_event.is_set():
        return None
    if not _generated_spec_is_usable(spec, library, kind, resolved_request):
        log.warning("visualization model returned unusable %s/%s data", library, kind)
        return fallback
    return spec


def _verified_visual_explanation(spec: dict[str, Any]) -> str:
    """Return checked teaching copy for the deterministic science constructions."""
    title = str(spec.get("title", ""))
    if title.startswith("Heart: double circulation"):
        return (
            "Deoxygenated blood returns from the body through the vena cava, right atrium, and "
            "right ventricle before the pulmonary artery carries it to the lungs. Oxygenated "
            "blood returns through the pulmonary veins, left atrium, and left ventricle; the "
            "aorta then carries it to the body."
        )
    if "structural formula" in title:
        return (
            f"The displayed {title.lower()} satisfies carbon's valency of four and hydrogen's "
            "valency of one. Each line represents one shared electron-pair bond; parallel lines "
            "show a double or triple carbon-carbon bond where applicable."
        )
    if title.startswith("Satellite in circular orbit"):
        return (
            "For a circular orbit, gravity supplies the centripetal force: GMm/r² = mv²/r, so "
            "v = √(GM/r). The period is T = 2πr/v = 2π√(r³/GM); therefore a larger orbital "
            "radius gives a lower orbital speed and a longer period."
        )
    if title.startswith("Sine-wave phase shift"):
        return (
            "The two waves have the same amplitude and period; only their horizontal timing is "
            "different. The labelled phase angle moves corresponding peaks and zero crossings "
            "by that fraction of one complete cycle without changing the wave's shape."
        )
    if title.startswith("Projectile path"):
        return (
            "With air resistance ignored, horizontal velocity stays constant while vertical "
            "velocity changes under the downward acceleration g = 9.81 m/s². Combining "
            "x = u cos(θ)t with y = u sin(θ)t − ½gt² produces the smooth parabolic path shown."
        )
    if title.startswith("Vector addition"):
        return (
            "Place the tail of the second vector at the head of the first without changing its "
            "length or direction. The resultant runs from the original tail to the final head, "
            "which is equivalent to adding corresponding vector components."
        )
    return ""


def _contradicts_verified_visual(prose: str, spec: dict[str, Any]) -> bool:
    """Reject a few high-cost misconceptions the deterministic construction can disprove.

    This is intentionally narrow: it is a safety barrier for the standard visuals, not a claim
    to understand arbitrary prose.  Unknown wording falls through to the existing completeness
    rule; explicit contradictions use the checked explanation instead.
    """
    title = str(spec.get("title", ""))
    value = " ".join(str(prose or "").split())
    if title.startswith("Satellite in circular orbit"):
        return bool(
            re.search(
                r"\b(?:larger|higher|greater)\s+(?:orbital\s+)?radius\b[^.!?]{0,90}"
                r"\b(?:higher|greater|faster)\s+(?:orbital\s+)?speed\b",
                value,
                re.IGNORECASE,
            )
            or re.search(
                r"\b(?:orbital|sideways)\s+speed\b[^.!?]{0,55}"
                r"\b(?:must|needs?|has|is|required|to)\b[^.!?]{0,30}"
                r"\b(?:constantly|continuously)\b[^.!?]{0,20}"
                r"\b(?:increase|decrease|change|get\s+faster|get\s+slower)\b",
                value,
                re.IGNORECASE,
            )
        )
    if title.startswith("Heart: double circulation"):
        return bool(
            re.search(
                r"\bblood\s+(?:flow\s+)?starts?\s+in\s+the\s+left\s+ventricle\b",
                value,
                re.IGNORECASE,
            )
            or re.search(
                r"\bpulmonary\s+artery\b[^.!?]{0,40}\boxygenated\b",
                value,
                re.IGNORECASE,
            )
            or re.search(
                r"\bpulmonary\s+veins?\b[^.!?]{0,40}\bdeoxygenated\b",
                value,
                re.IGNORECASE,
            )
        )
    if "structural formula" in title:
        expected_hydrogens = sum(
            1
            for node in spec.get("nodes") or []
            if isinstance(node, dict) and node.get("label") == "H"
        )
        words = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        count = re.search(
            r"\bhas\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
            r"\s+hydrogens?\b",
            value,
            re.IGNORECASE,
        )
        if count:
            stated = words.get(
                count.group(1).lower(), int(count.group(1)) if count.group(1).isdigit() else -1
            )
            return stated != expected_hydrogens
    if title.startswith("Sine-wave phase shift"):
        return bool(
            re.search(
                r"\bphase\s+(?:shift|angle)\b[^.!?]{0,60}\bchanges?\b[^.!?]{0,30}"
                r"\b(?:amplitude|period|frequency)\b",
                value,
                re.IGNORECASE,
            )
        )
    if title.startswith("Projectile path"):
        return bool(
            re.search(
                r"\bhorizontal\s+velocity\b[^.!?]{0,40}"
                r"\b(?:changes?|increases?|decreases?|accelerates?)\b",
                value,
                re.IGNORECASE,
            )
            or re.search(
                r"\bvertical\s+acceleration\b[^.!?]{0,35}\bupward\b",
                value,
                re.IGNORECASE,
            )
        )
    return False


def _visual_prose(prose: str, spec: dict[str, Any]) -> str:
    """Keep a complete lesson explanation; use checked copy only as a safe fallback.

    Standard visualizations have deterministic teaching copy because very small models sometimes
    emit a refusal or a single, contradictory sentence.  That copy must not replace an otherwise
    complete explanation: the diagram is supporting material, not the whole answer.
    """
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", str(prose or "")) if part.strip()]
    kept = [part for part in paragraphs if not _VISUAL_REFUSAL.search(part)]
    explanation = "\n\n".join(kept)
    verified = _verified_visual_explanation(spec)
    sentence_count = len(re.findall(r"[.!?](?=\s|$)", explanation))
    if explanation and (
        not verified or (sentence_count >= 2 and not _contradicts_verified_visual(explanation, spec))
    ):
        return explanation
    if verified:
        return verified
    if explanation:
        return explanation
    return (
        "The visual below shows the requested relationships directly. Follow its labels in "
        "order, then compare them with the governing quantities in the explanation."
    )


def append_visualization(prose: str, spec: dict[str, Any]) -> str:
    """Serialize in the durable reply protocol consumed by browser and history replay."""
    payload = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    return f"{_visual_prose(prose, spec).rstrip()}\n\n```muta-viz\n{payload}\n```"
