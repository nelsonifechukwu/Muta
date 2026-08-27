"""Bounded deterministic bearing and navigation planner for Visualization V2.

The parser maps natural navigation statements into one east/north coordinate model.  It emits
only the existing declarative scene grammar plus the typed ``angle_arc`` primitive; it has no
fixture imports, prompt-specific routes, executable source, or renderer access.
"""

from __future__ import annotations

import math
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

MAX_NAVIGATION_LEGS = 8
MAX_NAVIGATION_MAGNITUDE = 10_000.0

_VISUAL = re.compile(
    r"\b(?:draw|diagram|visuali[sz]e|show|plot|graph|chart|picture|sketch|illustrate|"
    r"map|simulate|model|animate|generate)\b|\bmake\s+it\s+move\b",
    re.IGNORECASE,
)
_NAVIGATION = re.compile(
    r"\bbearings?\b|three[- ]figure|clockwise\s+from\s+north|"
    r"\bdue\s+(?:north|south|east|west|northeast|northwest|southeast|southwest)\b|"
    r"\b(?:east|west)\b.{0,48}\b(?:north|south)\b|\btriangulat|\bintercept",
    re.IGNORECASE | re.DOTALL,
)
_NON_VISUAL = re.compile(
    r"\b(?:text|prose)\s+only\b|\bwithout\s+(?:a\s+)?(?:diagram|visual|graph|plot)\b|"
    r"\bshow\s+(?:me\s+)?(?:the\s+)?proof\b",
    re.IGNORECASE,
)
_BEARING = re.compile(
    r"\bbearing(?:\s+of|\s+is|\s*=|\s*:)?\s*\(?\s*(\d{1,3}(?:\.\d+)?)",
    re.IGNORECASE,
)
_ELIDED_BEARING = re.compile(
    r"\b(?:and|while)\s*\(?\s*(\d{1,3}(?:\.\d+)?)\s*°\s*\)?\s+from\b",
    re.IGNORECASE,
)
_DISTANCE_BEARING = re.compile(
    r"(\d+(?:\.\d+)?)\s*km\b.{0,96}?\bbearing(?:\s+of|\s+is|\s*=|\s*:)?\s*\(?\s*(\d{1,3}(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
_CARDINAL = {
    "north": 0.0,
    "northeast": 45.0,
    "east": 90.0,
    "southeast": 135.0,
    "south": 180.0,
    "southwest": 225.0,
    "west": 270.0,
    "northwest": 315.0,
}
_COLORS = {
    "route": "teal",
    "result": "purple",
    "construction": "orange",
    "north": "gray",
    "point": "gold",
}


@dataclass(frozen=True)
class Leg:
    start: str
    end: str
    distance: float
    bearing: float


@dataclass
class NavigationSolution:
    title: str
    points: dict[str, tuple[float, float]]
    legs: list[Leg] = field(default_factory=list)
    result_arrows: list[tuple[str, str, str]] = field(default_factory=list)
    north_points: list[str] = field(default_factory=list)
    bearing_arcs: list[tuple[str, float, float, bool, str]] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    summary: str = ""


def _normalized(text: str) -> str:
    value = text.replace("\\text{ km/h}", " km/h").replace("\\text{km/h}", " km/h")
    value = value.replace("\\text{ km}", " km").replace("\\text{km}", " km")
    value = value.replace("\\circ", "°").replace("^°", "°")
    value = value.replace("\\(", " ").replace("\\)", " ")
    value = value.replace("**", "")
    # Corpus entries may retain the following Markdown section delimiter. It is document
    # structure, not part of the navigation question, and must not alter intent resolution.
    value = re.split(r"\n\s*---\s*(?:\n|$)", value, maxsplit=1)[0]
    return re.sub(r"[ \t]+", " ", value)


def is_bearing_navigation_request(request: str) -> bool:
    if not isinstance(request, str) or not 1 <= len(request) <= 12_000:
        return False
    text = _normalized(request)
    return bool(_VISUAL.search(text) and _NAVIGATION.search(text) and not _NON_VISUAL.search(text))


def _finite(value: float) -> float:
    if not math.isfinite(value) or abs(value) > MAX_NAVIGATION_MAGNITUDE:
        raise ValueError("navigation value is outside the supported range")
    return value


def _bearing(value: float) -> float:
    return _finite(value) % 360.0


def _bearing_text(value: float) -> str:
    return f"{round(value) % 360:03d}°"


def _components(distance: float, bearing: float) -> tuple[float, float]:
    distance = _finite(distance)
    if distance <= 0:
        raise ValueError("distance must be positive")
    angle = math.radians(_bearing(bearing))
    return _finite(distance * math.sin(angle)), _finite(distance * math.cos(angle))


def _coordinate_bearing(east: float, north: float) -> float:
    if abs(east) + abs(north) < 1e-12:
        raise ValueError("a zero displacement has no bearing")
    return math.degrees(math.atan2(east, north)) % 360.0


def _distance_bearing_pairs(text: str) -> list[tuple[float, float]]:
    pairs = [
        (float(distance), _bearing(float(angle)))
        for distance, angle in _DISTANCE_BEARING.findall(text)
    ]
    if len(pairs) > MAX_NAVIGATION_LEGS:
        raise ValueError("too many navigation legs")
    return pairs


def _all_bearings(text: str) -> list[float]:
    # Include the conventional elided second ray in phrases such as
    # "bearing 040° from A and 320° from B", while ignoring unrelated degree values.
    positioned = [(match.start(), match.group(1)) for match in _BEARING.finditer(text)]
    positioned.extend((match.start(), match.group(1)) for match in _ELIDED_BEARING.finditer(text))
    positioned.sort(key=lambda item: item[0])
    return [_bearing(float(value)) for _, value in positioned]


def _direction_offset(text: str, axis: str) -> float | None:
    match = re.search(rf"(\d+(?:\.\d+)?)\s*km\s*\)?\s+({axis})\b", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    return -value if match.group(2).casefold() in {"west", "south"} else value


def _add(start: tuple[float, float], delta: tuple[float, float]) -> tuple[float, float]:
    return _finite(start[0] + delta[0]), _finite(start[1] + delta[1])


def _unique_point_names(text: str) -> list[str]:
    names: list[str] = []
    for name in re.findall(r"\(([A-Z])\)", text):
        if name not in names:
            names.append(name)
    return names


def _single_names(text: str) -> tuple[str, str]:
    names = _unique_point_names(text)
    for origin, destination in (("P", "Q"), ("A", "B"), ("H", "B")):
        if origin in names and destination in names:
            return origin, destination
    if "harbour" in text.casefold():
        return "Harbour", "Boat"
    if "ship" in text.casefold() and "lighthouse" in text.casefold():
        return "Ship", "Lighthouse"
    return "Start", "Finish"


def _single_leg_solution(text: str, *, with_components: bool = False) -> NavigationSolution | None:
    bearings = _all_bearings(text)
    cardinal = re.search(
        r"\bdue\s+(north|south|east|west|northeast|northwest|southeast|southwest)\b",
        text,
        re.IGNORECASE,
    )
    if not bearings and not cardinal:
        return None
    angle = bearings[0] if bearings else _CARDINAL[cardinal.group(1).casefold()]
    pairs = _distance_bearing_pairs(text)
    distance = pairs[0][0] if pairs else 10.0
    origin, destination = _single_names(text)
    finish = _components(distance, angle)
    annotations = [f"Bearing {_bearing_text(angle)} is measured clockwise from north."]
    result_arrows: list[tuple[str, str, str]] = []
    points = {origin: (0.0, 0.0), destination: finish}
    if with_components or re.search(r"how far\s+(?:north|south)|components?", text, re.IGNORECASE):
        corner = f"{destination} east component"
        points[corner] = (finish[0], 0.0)
        result_arrows.extend(
            [
                (origin, corner, f"east = {finish[0]:.2f} km"),
                (corner, destination, f"north = {finish[1]:.2f} km"),
            ]
        )
        annotations.append(
            f"east = {distance:g} sin {angle:g}° = {finish[0]:.2f} km; "
            f"north = {distance:g} cos {angle:g}° = {finish[1]:.2f} km."
        )
    direction = cardinal.group(1).casefold() if cardinal else None
    summary = (
        f"{direction.title()} corresponds to bearing {_bearing_text(angle)}."
        if direction
        else f"{destination} lies from {origin} on bearing {_bearing_text(angle)}."
    )
    return NavigationSolution(
        title="Bearing from north",
        points=points,
        legs=[Leg(origin, destination, distance, angle)],
        result_arrows=result_arrows,
        north_points=[origin],
        bearing_arcs=[(origin, 0.0, angle, True, _bearing_text(angle))],
        annotations=annotations,
        summary=summary,
    )


def _reverse_solution(text: str) -> NavigationSolution | None:
    bearings = _all_bearings(text)
    if not bearings:
        return None
    forward = bearings[0]
    reverse = (forward + 180.0) % 360.0
    origin, destination = _single_names(text)
    finish = _components(10.0, forward)
    misconception = "student" in text.casefold()
    annotations = [
        f"reverse bearing = ({_bearing_text(forward)} + 180°) mod 360° = {_bearing_text(reverse)}.",
    ]
    if misconception:
        claimed = bearings[1] if len(bearings) > 1 else None
        if claimed is not None and math.isclose(claimed, reverse, abs_tol=0.5):
            annotations.append(f"The student's claim {_bearing_text(claimed)} is correct.")
        elif claimed is not None:
            annotations.append(
                f"The claim is incorrect: {_bearing_text(reverse)}, not {_bearing_text(claimed)}, points directly back."
            )
    return NavigationSolution(
        title="Forward and reverse bearings",
        points={origin: (0.0, 0.0), destination: finish},
        legs=[Leg(origin, destination, 10.0, forward)],
        result_arrows=[(destination, origin, f"reverse {_bearing_text(reverse)}")],
        north_points=[origin, destination],
        bearing_arcs=[
            (origin, 0.0, forward, True, f"forward {_bearing_text(forward)}"),
            (destination, 0.0, reverse, True, f"reverse {_bearing_text(reverse)}"),
        ],
        annotations=annotations,
        summary=f"The reverse of {_bearing_text(forward)} is {_bearing_text(reverse)}.",
    )


def _coordinate_solution(text: str) -> NavigationSolution | None:
    east = _direction_offset(text, "east|west")
    north = _direction_offset(text, "north|south")
    if east is None or north is None:
        return None
    angle = _coordinate_bearing(east, north)
    origin, destination = _single_names(text)
    if "rescue station" in text.casefold():
        origin, destination = "Boat", "Rescue station"
    corner = "east/north corner"
    return NavigationSolution(
        title="Coordinates to bearing",
        points={origin: (0.0, 0.0), corner: (east, 0.0), destination: (east, north)},
        legs=[Leg(origin, destination, math.hypot(east, north), angle)],
        result_arrows=[
            (origin, corner, f"east = {east:g} km"),
            (corner, destination, f"north = {north:g} km"),
        ],
        north_points=[origin],
        bearing_arcs=[(origin, 0.0, angle, True, _bearing_text(angle))],
        annotations=[
            f"θ = atan2(east, north) = atan2({east:g}, {north:g}) = {angle:.2f}°.",
            f"Three-figure bearing = {_bearing_text(angle)}; quadrant comes from the signs of east and north.",
        ],
        summary=f"The displacement ({east:g} km east, {north:g} km north) has bearing {_bearing_text(angle)}.",
    )


def _route_solution(text: str, pairs: list[tuple[float, float]]) -> NavigationSolution:
    points: dict[str, tuple[float, float]] = {"Start": (0.0, 0.0)}
    legs: list[Leg] = []
    current = "Start"
    for index, (distance, angle) in enumerate(pairs, start=1):
        destination = "Finish" if index == len(pairs) else f"Turn {index}"
        points[destination] = _add(points[current], _components(distance, angle))
        legs.append(Leg(current, destination, distance, angle))
        current = destination
    east, north = points["Finish"]
    displacement = math.hypot(east, north)
    angle = _coordinate_bearing(east, north)
    component_text = "; ".join(
        f"leg {index}: E={_components(leg.distance, leg.bearing)[0]:.2f}, N={_components(leg.distance, leg.bearing)[1]:.2f} km"
        for index, leg in enumerate(legs, start=1)
    )
    return NavigationSolution(
        title="Navigation route and resultant",
        points=points,
        legs=legs,
        result_arrows=[
            ("Start", "Finish", f"resultant {displacement:.2f} km • {_bearing_text(angle)}")
        ],
        north_points=[leg.start for leg in legs],
        bearing_arcs=[
            (leg.start, 0.0, leg.bearing, True, _bearing_text(leg.bearing)) for leg in legs
        ]
        + [("Start", 0.0, angle, True, f"resultant {_bearing_text(angle)}")],
        annotations=[
            component_text,
            f"Σeast = {east:.2f} km; Σnorth = {north:.2f} km.",
            f"displacement = √(ΣE² + ΣN²) = {displacement:.2f} km; bearing = atan2(ΣE, ΣN) = {_bearing_text(angle)}.",
        ],
        summary=f"Final displacement is {displacement:.2f} km on bearing {_bearing_text(angle)}.",
    )


def _common_origin_solution(text: str, pairs: list[tuple[float, float]]) -> NavigationSolution:
    (distance_a, bearing_a), (distance_b, bearing_b) = pairs[:2]
    point_a = _components(distance_a, bearing_a)
    point_b = _components(distance_b, bearing_b)
    separation = math.dist(point_a, point_b)
    included = abs((bearing_b - bearing_a + 180) % 360 - 180)
    cosine_distance = math.sqrt(
        distance_a**2
        + distance_b**2
        - 2 * distance_a * distance_b * math.cos(math.radians(included))
    )
    return NavigationSolution(
        title="Two objects from a common origin",
        points={"H": (0.0, 0.0), "A": point_a, "B": point_b},
        legs=[Leg("H", "A", distance_a, bearing_a), Leg("H", "B", distance_b, bearing_b)],
        result_arrows=[("A", "B", f"AB = {separation:.2f} km")],
        north_points=["H"],
        bearing_arcs=[
            ("H", 0.0, bearing_a, True, _bearing_text(bearing_a)),
            ("H", 0.0, bearing_b, True, _bearing_text(bearing_b)),
        ],
        annotations=[
            f"included angle = |{bearing_b:g}° − {bearing_a:g}°| = {included:.1f}°.",
            f"AB² = {distance_a:g}² + {distance_b:g}² − 2({distance_a:g})({distance_b:g}) cos {included:.1f}°.",
            f"AB = {cosine_distance:.2f} km (coordinate check {separation:.2f} km).",
        ],
        summary=f"The objects are {separation:.2f} km apart.",
    )


def _endpoint_to_endpoint_solution(
    text: str, pairs: list[tuple[float, float]]
) -> NavigationSolution:
    (distance_b, bearing_b), (distance_c, bearing_c) = pairs[:2]
    point_b = _components(distance_b, bearing_b)
    point_c = _components(distance_c, bearing_c)
    east = point_c[0] - point_b[0]
    north = point_c[1] - point_b[1]
    distance = math.hypot(east, north)
    result_bearing = _coordinate_bearing(east, north)
    back_bearing = (bearing_b + 180) % 360
    difference = (result_bearing - back_bearing) % 360
    clockwise = difference <= 180
    interior = difference if clockwise else 360 - difference
    return NavigationSolution(
        title="Bearing between computed endpoints",
        points={"A": (0.0, 0.0), "B": point_b, "C": point_c},
        legs=[Leg("A", "B", distance_b, bearing_b), Leg("A", "C", distance_c, bearing_c)],
        result_arrows=[("B", "C", f"BC = {distance:.2f} km • {_bearing_text(result_bearing)}")],
        north_points=["A", "B"],
        bearing_arcs=[
            ("A", 0.0, bearing_b, True, f"A→B {_bearing_text(bearing_b)}"),
            ("A", 0.0, bearing_c, True, f"A→C {_bearing_text(bearing_c)}"),
            ("B", 0.0, result_bearing, True, f"bearing {_bearing_text(result_bearing)}"),
            ("B", back_bearing, result_bearing, clockwise, f"interior ∠ABC = {interior:.2f}°"),
        ],
        annotations=[
            f"C − B = ({east:.2f} km east, {north:.2f} km north).",
            f"bearing B→C = atan2({east:.2f}, {north:.2f}) = {_bearing_text(result_bearing)}.",
            f"Interior angle ∠ABC = {interior:.2f}°; it is not a bearing from north.",
        ],
        summary=f"C is {distance:.2f} km from B on bearing {_bearing_text(result_bearing)}.",
    )


def _ray_intersection_solution(text: str) -> NavigationSolution | None:
    bearings = _all_bearings(text)
    baseline_match = re.search(r"(\d+(?:\.\d+)?)\s*km\s*\)?\s+apart", text, re.IGNORECASE)
    if len(bearings) < 2 or not baseline_match:
        return None
    baseline = float(baseline_match.group(1))
    first, second = bearings[:2]
    baseline_direction = re.search(
        r"\bB\b.{0,48}?\bdue\s+(north|south|east|west)\s+of\s+\bA\b",
        text,
        re.IGNORECASE,
    )
    baseline_bearing = (
        _CARDINAL[baseline_direction.group(1).casefold()] if baseline_direction else 90.0
    )
    baseline_vector = _components(baseline, baseline_bearing)
    direction_a = _components(1.0, first)
    direction_b = _components(1.0, second)
    determinant = direction_a[0] * (-direction_b[1]) - (-direction_b[0]) * direction_a[1]
    if abs(determinant) < 1e-9:
        return None
    rhs_east, rhs_north = baseline_vector
    distance_a = (rhs_east * (-direction_b[1]) - (-direction_b[0]) * rhs_north) / determinant
    distance_b = (direction_a[0] * rhs_north - rhs_east * direction_a[1]) / determinant
    if distance_a <= 0 or distance_b <= 0:
        return None
    tower = _components(distance_a, first)
    return NavigationSolution(
        title="Triangulation from two bearing rays",
        points={"A": (0.0, 0.0), "B": baseline_vector, "T": tower},
        legs=[Leg("A", "T", distance_a, first), Leg("B", "T", distance_b, second)],
        result_arrows=[("A", "B", f"baseline {baseline:g} km")],
        north_points=["A", "B"],
        bearing_arcs=[
            ("A", 0.0, first, True, _bearing_text(first)),
            ("B", 0.0, second, True, _bearing_text(second)),
        ],
        annotations=[
            "The two positive bearing rays meet at T; negative ray parameters are rejected.",
            f"AT = {distance_a:.2f} km; BT = {distance_b:.2f} km.",
        ],
        summary=f"The tower is {distance_a:.2f} km from A and {distance_b:.2f} km from B.",
    )


def _interception_solution(text: str) -> NavigationSolution | None:
    pairs = _distance_bearing_pairs(text)
    speeds = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*km/h", text, re.IGNORECASE)]
    if not pairs or len(speeds) < 2:
        return None
    initial_distance, initial_bearing = pairs[0]
    target_speed, rescuer_speed = speeds[0], speeds[1]
    initial = _components(initial_distance, initial_bearing)
    numeric_direction = re.search(
        r"(?:travels?|moves?|moving|sails?|steams?).{0,64}?\bbearing"
        r"(?:\s+of|\s+is|\s*=|\s*:)?\s*\(?\s*(\d{1,3}(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    cardinal_direction = re.search(
        r"(?:travels?|moves?|moving|sails?|steams?)\s+(?:on\s+a\s+bearing\s+of\s+)?"
        r"(?:due\s+)?(north|south|east|west|northeast|northwest|southeast|southwest)\b",
        text,
        re.IGNORECASE,
    )
    if numeric_direction:
        target_bearing = _bearing(float(numeric_direction.group(1)))
    elif cardinal_direction:
        target_bearing = _CARDINAL[cardinal_direction.group(1).casefold()]
    else:
        target_bearing = 180.0
    target_velocity = _components(target_speed, target_bearing)
    # |p + vt|² = s²t². Select the earliest finite positive root.
    a = target_velocity[0] ** 2 + target_velocity[1] ** 2 - rescuer_speed**2
    b = 2 * (initial[0] * target_velocity[0] + initial[1] * target_velocity[1])
    c = initial[0] ** 2 + initial[1] ** 2
    roots: list[float] = []
    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            roots.append(-c / b)
    else:
        discriminant = b * b - 4 * a * c
        if discriminant >= 0:
            root = math.sqrt(discriminant)
            roots.extend(((-b - root) / (2 * a), (-b + root) / (2 * a)))
    positive = sorted(value for value in roots if math.isfinite(value) and value > 1e-9)
    if not positive:
        return None
    time = positive[0]
    intercept = _add(initial, (target_velocity[0] * time, target_velocity[1] * time))
    rescue_distance = rescuer_speed * time
    intercept_bearing = _coordinate_bearing(*intercept)
    return NavigationSolution(
        title="Earliest moving interception",
        points={"H": (0.0, 0.0), "Ship initial": initial, "Intercept": intercept},
        legs=[Leg("H", "Ship initial", initial_distance, initial_bearing)],
        result_arrows=[
            ("Ship initial", "Intercept", f"ship: {target_speed:g} km/h for {time:.2f} h"),
            (
                "H",
                "Intercept",
                f"rescue: {rescue_distance:.2f} km • {_bearing_text(intercept_bearing)}",
            ),
        ],
        north_points=["H"],
        bearing_arcs=[
            ("H", 0.0, initial_bearing, True, f"initial {_bearing_text(initial_bearing)}"),
            ("H", 0.0, intercept_bearing, True, f"intercept {_bearing_text(intercept_bearing)}"),
        ],
        annotations=[
            f"Solve |p + vt| = {rescuer_speed:g}t and choose the earliest positive root: t = {time:.3f} h.",
            f"Intercept = ({intercept[0]:.2f} km east, {intercept[1]:.2f} km north).",
            f"Rescue path = {rescue_distance:.2f} km on bearing {_bearing_text(intercept_bearing)}.",
        ],
        summary=f"Fastest interception is after {time:.3f} h on bearing {_bearing_text(intercept_bearing)}.",
    )


def _project(points: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    east_values = [point[0] for point in points.values()]
    north_values = [point[1] for point in points.values()]
    east_low, east_high = min(east_values), max(east_values)
    north_low, north_high = min(north_values), max(north_values)
    east_span = max(1.0, east_high - east_low)
    north_span = max(1.0, north_high - north_low)
    # Reserve the lower third for worked numeric annotations; geometry never expands into it.
    scale = min(480 / east_span, 200 / north_span)
    x_offset = 340 - scale * (east_low + east_high) / 2
    y_offset = 150 + scale * (north_low + north_high) / 2
    return {
        name: (round(x_offset + scale * east, 3), round(y_offset - scale * north, 3))
        for name, (east, north) in points.items()
    }


def _scene(solution: NavigationSolution) -> list[dict[str, Any]]:
    screen = _project(solution.points)
    layers: list[dict[str, Any]] = []
    for name in solution.north_points:
        x, y = screen[name]
        layers.append(
            {
                "type": "arrow",
                "from": [x, y],
                "to": [x, max(24.0, y - 64)],
                "label": f"N at {name}",
                "color": _COLORS["north"],
            }
        )
    for leg in solution.legs:
        layers.append(
            {
                "type": "arrow",
                "from": list(screen[leg.start]),
                "to": list(screen[leg.end]),
                "label": f"{leg.start}→{leg.end}: {leg.distance:.2f} km • {_bearing_text(leg.bearing)}",
                "color": _COLORS["route"],
            }
        )
    for start, end, label in solution.result_arrows:
        layers.append(
            {
                "type": "arrow",
                "from": list(screen[start]),
                "to": list(screen[end]),
                "label": label,
                "color": _COLORS["result"],
            }
        )
    arc_counts: dict[str, int] = {}
    for point, start, end, clockwise, label in solution.bearing_arcs:
        x, y = screen[point]
        local_index = arc_counts.get(point, 0)
        arc_counts[point] = local_index + 1
        layers.append(
            {
                "type": "angle_arc",
                "cx": x,
                "cy": y,
                "r": 28 + 30 * local_index,
                "start_angle": start,
                "end_angle": end,
                "clockwise": clockwise,
                "label": label,
                "color": _COLORS["construction"],
            }
        )
    for name, (x, y) in screen.items():
        layers.append(
            {"type": "circle", "x": x, "y": y, "r": 6, "label": name, "color": _COLORS["point"]}
        )
        layers.append({"type": "text", "x": x + 9, "y": y + 18, "text": name, "color": "black"})
    annotation_lines = [
        line
        for annotation in solution.annotations
        for line in textwrap.wrap(annotation, width=96, break_long_words=False)
    ][:4]
    for index, annotation in enumerate(annotation_lines):
        layers.append(
            {
                "type": "text",
                "x": 42,
                "y": 312 + 20 * index,
                "text": annotation[:160],
                "color": "black",
            }
        )
    return layers


def _solve(text: str) -> NavigationSolution | None:
    if "intercept" in text.casefold():
        return _interception_solution(text)
    if re.search(r"triangulat|observation stations?|two bearing rays?", text, re.IGNORECASE):
        return _ray_intersection_solution(text)
    coordinate = _coordinate_solution(text)
    if coordinate is not None:
        return coordinate
    pairs = _distance_bearing_pairs(text)
    if len(pairs) >= 2:
        if re.search(r"distance between|between the (?:boats?|objects?)", text, re.IGNORECASE):
            return _common_origin_solution(text, pairs)
        if re.search(r"bearing\s+of\s*\(?C\)?\s+from\s*\(?B\)?", text, re.IGNORECASE):
            return _endpoint_to_endpoint_solution(text, pairs)
        return _route_solution(text, pairs)
    reverse_requested = re.search(
        r"reverse bearing|student says|find\s+the\s+bearing\s+of.{0,48}\s+from|"
        r"what\s+is\s+the\s+bearing\s+of.{0,48}\s+from|mark\s+both\s+bearings",
        text,
        re.IGNORECASE,
    )
    if reverse_requested:
        reverse = _reverse_solution(text)
        if reverse is not None:
            return reverse
    return _single_leg_solution(
        text, with_components=bool(re.search(r"how far", text, re.IGNORECASE))
    )


def compile_bearing_navigation_v2(request: str) -> dict[str, Any] | None:
    if not is_bearing_navigation_request(request):
        return None
    text = _normalized(request)
    try:
        solution = _solve(text)
    except (ArithmeticError, ValueError):
        return None
    if solution is None:
        return None
    layers = _scene(solution)
    return {
        "version": 2,
        "library": "d3",
        "renderer": "svg",
        "kind": "scene2d",
        "family": "bearing_navigation",
        "title": solution.title[:120],
        "aria_label": f"Navigation diagram. {solution.summary}"[:240],
        "text_fallback": (f"{solution.summary} " + " ".join(solution.annotations))[:1200],
        "height": 500,
        "controls": [],
        "budget": {"max_points": 512, "max_triangles": 4096, "max_fps": 20},
        "scene": {"coordinate_system": "screen", "layers": layers},
    }


__all__ = [
    "compile_bearing_navigation_v2",
    "is_bearing_navigation_request",
]
