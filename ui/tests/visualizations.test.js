"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const viz = require("../visualizations.js");

const line = {
  version: 1,
  library: "d3",
  kind: "line",
  title: "Quadratic curve",
  aria_label: "A line graph showing y equals x squared.",
  height: 340,
  x_label: "x",
  y_label: "y",
  series: [{ label: "y = x²", points: [[-1, 1], [0, 0], [1, 1]] }],
};

function fenced(spec) {
  return `Before the visual.\n\n\`\`\`muta-viz\n${JSON.stringify(spec)}\n\`\`\`\n\nAfter it.`;
}

const number = (value) => ({ type: "number", value });
const variable = (name) => ({ type: "variable", name });
const constant = (name) => ({ type: "constant", name });
const binary = (op, left, right) => ({ type: "binary", op, left, right });
const call = (name, arg) => ({ type: "call", name, arg });
const unary = (op, arg) => ({ type: "unary", op, arg });

const exactSurfaceExpression = binary(
  "*",
  binary(
    "*",
    number(4),
    binary(
      "^",
      constant("e"),
      binary(
        "*",
        unary("-", binary("/", number(1), number(4))),
        binary("^", variable("y"), number(2)),
      ),
    ),
  ),
  call("sin", binary("*", number(2), variable("x"))),
);

function surfaceSpec(animation) {
  const object = {
    type: "surface",
    label: "z = 4e^(-y²/4) sin(2x)",
    expression_text: "z = 4e^(-y²/4) sin(2x)",
    expression: exactSurfaceExpression,
    x_domain: [-Math.PI, Math.PI],
    y_domain: [-4, 4],
    z_domain: [-4, 4],
    resolution: [65, 49],
  };
  if (animation) object.animation = animation;
  return {
    version: 1,
    library: "three",
    kind: "scene3d",
    title: "Gaussian-windowed sine surface",
    aria_label: "A three-dimensional Gaussian-windowed sine surface with z vertical.",
    height: 460,
    x_label: "x",
    y_label: "y",
    z_label: "z",
    objects: [object],
  };
}

test("extracts one valid visualization and leaves the teaching prose", () => {
  const result = viz.extract(fenced(line));
  assert.equal(result.visualizations.length, 1);
  assert.deepEqual(result.visualizations[0], line);
  assert.equal(result.markdown, "Before the visual.\n\nAfter it.");
  assert.doesNotMatch(result.markdown, /muta-viz/);
});

test("malformed or invalid model output stays visible as code", () => {
  const malformed = "Explanation\n\n```muta-viz\n{bad json}\n```";
  assert.deepEqual(viz.extract(malformed), { markdown: malformed, visualizations: [] });

  const invalid = { ...line, library: "three" };
  const result = viz.extract(fenced(invalid));
  assert.equal(result.visualizations.length, 0);
  assert.match(result.markdown, /```muta-viz/);
});

test("accepts the smoke model's exact marker-plus-json fence degradation", () => {
  const source = `Explanation.\n\n$$muta-viz$$  \n\`\`\`json\n${JSON.stringify(line)}\n\`\`\``;
  const result = viz.extract(source);
  assert.equal(result.markdown, "Explanation.");
  assert.deepEqual(result.visualizations, [line]);
});

test("removes all valid artifacts and renders only the final server-owned position", () => {
  const source = `${fenced(line)}\n\n${fenced({ ...line, title: "Second" })}`;
  const result = viz.extract(source);
  assert.equal(result.visualizations.length, 1);
  assert.equal(result.visualizations[0].title, "Second");
  assert.doesNotMatch(result.markdown, /```muta-viz|"title":"Second"/);
  assert.equal((result.markdown.match(/Before the visual\./g) || []).length, 2);
});

test("a model-authored valid family before the trusted artifact cannot hijack extraction", () => {
  const untrusted = { ...line, title: "Model-selected Pythagoras" };
  const trusted = { ...line, title: "Trusted semantic composition" };
  const source = `Model prose\n\n\`\`\`muta-viz\n${JSON.stringify(untrusted)}\n\`\`\`\n\n`
    + `\`\`\`muta-viz\n${JSON.stringify(trusted)}\n\`\`\``;
  const result = viz.extract(source);
  assert.deepEqual(result.visualizations, [trusted]);
  assert.equal(result.markdown, "Model prose");
});

test("validates every supported renderer family", () => {
  const bar = {
    version: 1, library: "d3", kind: "bar", title: "Bars", aria_label: "Two bars.", height: 300,
    data: [{ label: "A", value: 1 }, { label: "B", value: 2 }],
  };
  const force = {
    version: 1, library: "d3", kind: "force", title: "Network", aria_label: "Two linked nodes.", height: 300,
    nodes: [{ id: "a" }, { id: "b" }], links: [{ source: "a", target: "b" }],
  };
  const diagram = {
    version: 1, library: "d3", kind: "diagram", title: "Heart flow",
    aria_label: "Blood flows from the right atrium to the right ventricle.", height: 360,
    nodes: [
      { id: "ra", label: "Right atrium", x: 180, y: 120, shape: "rounded", width: 140, height: 58, color: "blue" },
      { id: "rv", label: "Right ventricle", x: 180, y: 260, shape: "rounded", width: 150, height: 64, color: "blue" },
    ],
    links: [{ source: "ra", target: "rv", label: "tricuspid valve", bond: "single", arrow: true }],
    annotations: [{ text: "deoxygenated blood", x: 440, y: 180 }],
  };
  const scene = {
    version: 1, library: "three", kind: "scene3d", title: "Vector", aria_label: "A three dimensional vector.", height: 360,
    notes: ["v = √(GM/r)", "T = 2π√(r³/GM)"],
    objects: [{ type: "vector", from: [0, 0, 0], to: [1, 2, 3], label_position: [1, 2.4, 3] }],
  };
  const animation = (library) => ({
    version: 1, library, kind: "animation", title: "Motion", aria_label: "A moving dot.", height: 300,
    elements: [{ id: "dot", type: "circle", x: 10, y: 20 }],
    tracks: [{ target: "dot", to: { x: 100, opacity: 0.5 }, duration: 1 }],
  });

  for (const spec of [line, bar, force, diagram, scene, animation("gsap"), animation("anime"), animation("motion")]) {
    assert.equal(viz.validateSpec(spec).ok, true, `${spec.library}/${spec.kind}`);
  }
});

test("accepts deterministic vector-addition diagrams and replayable animations", () => {
  const scene = {
    version: 1,
    library: "three",
    kind: "scene3d",
    title: "Vector addition: head to tail",
    aria_label: "A and B are arranged head to tail, with their resultant from the origin.",
    height: 380,
    objects: [
      { type: "vector", label: "A = (2, 1)", from: [0, 0, 0], to: [2, 1, 0] },
      { type: "vector", label: "B = (1, 2)", from: [2, 1, 0], to: [3, 3, 0] },
      { type: "vector", label: "A + B = (3, 3)", from: [0, 0, 0], to: [3, 3, 0] },
    ],
  };
  assert.equal(viz.validateSpec(scene).ok, true);

  for (const library of ["gsap", "anime", "motion"]) {
    const animation = {
      version: 1,
      library,
      kind: "animation",
      title: "Vector addition: move B head to tail",
      aria_label: "B moves to the head of A before the resultant appears.",
      height: 380,
      elements: [
        { id: "vector_a", type: "arrow", x: 120, y: 250, x1: 0, y1: 0, x2: 140, y2: -70 },
        { id: "vector_b", type: "arrow", x: 120, y: 250, x1: 0, y1: 0, x2: 70, y2: -140 },
        { id: "resultant", type: "arrow", x: 120, y: 250, x1: 0, y1: 0, x2: 210, y2: -210 },
        { id: "label_sum", type: "text", x: 220, y: 170, text: "A + B = (3, 3)" },
      ],
      tracks: [
        { target: "vector_b", from: { x: 120, y: 250, opacity: 0.35 }, to: { x: 260, y: 180, opacity: 1 }, duration: 1.6 },
        { target: "resultant", from: { opacity: 0 }, to: { opacity: 1 }, duration: 0.9, delay: 1.6 },
      ],
    };
    assert.equal(viz.validateSpec(animation).ok, true, library);
  }
});

test("validates and evaluates the exact deterministic mathematical surface", () => {
  const spec = surfaceSpec();
  const checked = viz.validateSpec(spec);
  assert.equal(checked.ok, true, checked.error);
  const at = (x, y, t = 0, expression = exactSurfaceExpression) => (
    viz.evaluateSurfaceExpression(expression, { x, y, t })
  );
  for (const y of [-4, -1, 0, 2, 4]) assert.ok(Math.abs(at(0, y)) < 1e-12);
  assert.ok(Math.abs(at(Math.PI / 4, 0) - 4) < 1e-12);
  assert.ok(Math.abs(at(-Math.PI / 4, 0) + 4) < 1e-12);
  assert.ok(Math.abs(at(Math.PI / 4, 0)) > Math.abs(at(Math.PI / 4, 2)));
  assert.ok(Math.abs(at(Math.PI / 4, 2)) > Math.abs(at(Math.PI / 4, 4)));
});

test("accepts a bounded typed phase animation and rejects unsafe surface data", () => {
  const animatedExpression = structuredClone(exactSurfaceExpression);
  animatedExpression.right.arg = binary("-", animatedExpression.right.arg, variable("t"));
  const animated = surfaceSpec({ mode: "phase", duration: 8, expression: animatedExpression });
  const checked = viz.validateSpec(animated);
  assert.equal(checked.ok, true, checked.error);
  assert.equal(
    viz.evaluateSurfaceExpression(animatedExpression, { x: Math.PI / 4, y: 0, t: Math.PI / 2 }),
    0,
  );

  const unsafeFunction = surfaceSpec();
  unsafeFunction.objects[0].expression = call("constructor", variable("x"));
  assert.equal(viz.validateSpec(unsafeFunction).ok, false);

  const excessiveResolution = surfaceSpec();
  excessiveResolution.objects[0].resolution = [97, 97];
  assert.equal(viz.validateSpec(excessiveResolution).ok, false);

  const backwardsDomain = surfaceSpec();
  backwardsDomain.objects[0].x_domain = [2, -2];
  assert.equal(viz.validateSpec(backwardsDomain).ok, false);

  const unboundedAnimation = surfaceSpec({ mode: "phase", duration: 300, expression: animatedExpression });
  assert.equal(viz.validateSpec(unboundedAnimation).ok, false);

  const fullTree = (depth) => (
    depth === 0 ? number(1) : binary("+", fullTree(depth - 1), fullTree(depth - 1))
  );
  const expensiveStatic = surfaceSpec();
  expensiveStatic.objects[0].resolution = [97, 84];
  expensiveStatic.objects[0].expression = fullTree(5);
  assert.match(viz.validateSpec(expensiveStatic).error, /safe rendering budget/);

  const expensiveAnimated = surfaceSpec({
    mode: "phase", duration: 8, expression: fullTree(4),
  });
  expensiveAnimated.objects[0].resolution = [97, 84];
  assert.match(viz.validateSpec(expensiveAnimated).error, /per-frame rendering budget/);
});

test("rejects unsafe keys, oversized arrays, bad links, and animation fields", () => {
  const poisoned = JSON.parse(JSON.stringify(line).replace('{"version"', '{"__proto__":{},"version"'));
  assert.equal(viz.validateSpec(poisoned).ok, false);
  assert.equal(viz.validateSpec({ ...line, height: 900 }).ok, false);
  assert.equal(viz.validateSpec({ ...line, series: [{ label: "x", points: Array(201).fill([0, 0]) }] }).ok, false);

  const badForce = {
    version: 1, library: "d3", kind: "force", title: "Bad", aria_label: "Bad network.", height: 300,
    nodes: [{ id: "a" }, { id: "b" }], links: [{ source: "a", target: "missing" }],
  };
  assert.equal(viz.validateSpec(badForce).ok, false);

  const badDiagram = {
    version: 1, library: "d3", kind: "diagram", title: "Bad", aria_label: "Bad diagram.", height: 300,
    nodes: [{ id: "a", label: "A", x: 10, y: 10, shape: "circle" }],
    links: [{ source: "a", target: "missing", bond: "quadruple", arrow: true }],
  };
  assert.equal(viz.validateSpec(badDiagram).ok, false);

  const badAnimation = {
    version: 1, library: "gsap", kind: "animation", title: "Bad", aria_label: "Bad animation.", height: 300,
    elements: [{ id: "dot", type: "circle" }],
    tracks: [{ target: "dot", to: { filter: 4 }, duration: 1 }],
  };
  assert.equal(viz.validateSpec(badAnimation).ok, false);

  const badGeometry = {
    ...badAnimation,
    elements: [{ id: "dot", type: "circle", r: -2 }],
    tracks: [{ target: "dot", to: { x: 4 }, duration: 1, repeat: 0.5 }],
  };
  assert.equal(viz.validateSpec(badGeometry).ok, false);

  const unboundedAnimation = {
    ...badAnimation,
    elements: [{ id: "dot", type: "circle", r: 2 }],
    tracks: [{ target: "dot", to: { x: 4 }, duration: 1, repeat: -1 }],
  };
  assert.equal(viz.validateSpec(unboundedAnimation).ok, false);

  const duplicateTrack = {
    ...badAnimation,
    elements: [{ id: "dot", type: "circle", r: 2 }],
    tracks: [
      { target: "dot", to: { x: 4 }, duration: 1 },
      { target: "dot", to: { y: 4 }, duration: 1 },
    ],
  };
  assert.equal(viz.validateSpec(duplicateTrack).ok, false);

  const zeroVector = {
    version: 1, library: "three", kind: "scene3d", title: "Bad vector",
    aria_label: "A zero vector.", height: 300,
    objects: [{ type: "vector", from: [1, 1, 1], to: [1, 1, 1] }],
  };
  assert.equal(viz.validateSpec(zeroVector).ok, false);

  const badThreeNote = {
    ...zeroVector,
    notes: ["A".repeat(121)],
    objects: [{ type: "vector", from: [0, 0, 0], to: [1, 1, 1], label_position: [0, 1] }],
  };
  assert.equal(viz.validateSpec(badThreeNote).ok, false);
});

test("round-trips Unicode through a fragment-safe frame URL", () => {
  const unicode = { ...line, title: "Parabola — y = x²" };
  const encoded = viz.encodeSpec(unicode);
  assert.doesNotMatch(encoded, /[+/=]/);
  assert.deepEqual(viz.decodeSpec(encoded), unicode);
  const url = viz.frameUrl(unicode);
  assert.match(url, /^viz-frame\.html\?theme=light#[A-Za-z0-9_-]+$/);
  assert.match(viz.frameUrl(unicode, "dark"), /^viz-frame\.html\?theme=dark#/);
  assert.doesNotMatch(url, /Parabola|\{|\}/);
  assert.throws(() => viz.decodeSpec("A".repeat(70_000)), /too large/);
});
