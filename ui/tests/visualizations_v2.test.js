"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const viz = require("../visualizations.js");

const number = (value) => ({ type: "number", value });
const variable = (name) => ({ type: "variable", name });
const binary = (op, left, right) => ({ type: "binary", op, left, right });
const call = (name, ...args) => ({ type: "call", name, args });

function relationship() {
  return {
    type: "relationship",
    op: "=",
    left: variable("z"),
    right: binary(
      "*",
      binary("*", number(4), call("exp", binary("/", binary("^", variable("y"), number(2)), number(-4)))),
      call("sin", binary("*", number(2), variable("x"))),
    ),
  };
}

function surface(type = "explicit_surface") {
  return {
    version: 2,
    library: "three",
    renderer: "three",
    kind: "scene3d",
    family: type,
    title: "Safe V2 surface",
    aria_label: "A labelled three-dimensional mathematical surface.",
    text_fallback: "The surface uses x, y and vertical z axes with undefined samples omitted.",
    height: 480,
    controls: [
      { id: "orbit", label: "Rotate view", type: "button", value: 0 },
      { id: "reset_view", label: "Reset view", type: "button", value: 0 },
    ],
    budget: { max_points: 20000, max_triangles: 32000, max_fps: 30 },
    scene: {
      coordinate_system: "cartesian3d",
      layers: [{
        type,
        label: "z=4 exp(-y²/4) sin(2x)",
        relationship: relationship(),
        x_domain: [-5, 5], y_domain: [-5, 5], z_domain: [-5, 5],
        resolution: type === "explicit_surface" ? [49, 49] : [25, 25, 25],
      }],
    },
  };
}

function svgSpec() {
  return {
    version: 2, library: "d3", renderer: "svg", kind: "scene2d", family: "pythagoras",
    title: "Pythagoras", aria_label: "A labelled Pythagorean relationship.",
    text_fallback: "The square areas obey a² + b² = c².", height: 420,
    controls: [{ id: "a", label: "Side a", type: "range", value: 3, min: 1, max: 10, step: 0.1 }],
    budget: { max_points: 4096, max_triangles: 32000, max_fps: 30 },
    scene: { coordinate_system: "screen", layers: [
      { type: "node", id: "a2", x: 160, y: 200, width: 130, height: 58, label: "a²", color: "teal" },
      { type: "node", id: "sum", x: 400, y: 200, width: 180, height: 58, label: "a²+b²=c²", color: "orange" },
      { type: "link", from: "a2", to: "sum", arrow: true, label: "" },
    ] },
  };
}

test("accepts each V2 renderer pairing and preserves the serialized data boundary", () => {
  const svg = svgSpec();
  const canvas = structuredClone(svg);
  canvas.renderer = "canvas"; canvas.kind = "simulation2d"; canvas.family = "wave";
  canvas.scene.coordinate_system = "cartesian2d";
  canvas.scene.layers = [
    { type: "axes", x_label: "t", y_label: "y", grid: true },
    { type: "polyline", label: "wave", points: [[0, 0], [1, 1], [2, 0]], color: "teal" },
  ];
  for (const spec of [svg, canvas, surface()]) {
    const checked = viz.validateSpec(spec);
    assert.equal(checked.ok, true, checked.error);
    assert.deepEqual(checked.spec, spec);
  }
});

test("validates typed control bindings and declared Three triangle budgets", () => {
  const bound = svgSpec();
  bound.controls[0].binding = { target_label: "a²", effect: "scale" };
  assert.equal(viz.validateSpec(bound).ok, true);

  const missing = structuredClone(bound);
  missing.controls[0].binding.target_label = "missing";
  assert.match(viz.validateSpec(missing).error, /binding target/);

  const incompatible = structuredClone(bound);
  incompatible.controls[0].binding.effect = "radius";
  assert.match(viz.validateSpec(incompatible).error, /binding target/);

  const underdeclaredSurface = surface();
  underdeclaredSurface.budget.max_triangles = 1;
  assert.match(viz.validateSpec(underdeclaredSurface).error, /triangle budget/);

  const spheres = surface();
  spheres.controls = [];
  spheres.budget.max_triangles = 1;
  spheres.scene.layers = Array.from({ length: 24 }, (_, index) => ({
    type: "sphere", position: [index % 6, Math.floor(index / 6), 0], size: 0.2,
    label: `sample ${index}`, color: "blue",
  }));
  assert.match(viz.validateSpec(spheres).error, /triangle budget/);
});

test("evaluates the typed V2 AST without dynamic source execution", () => {
  const rhs = relationship().right;
  const at = (x, y) => viz.evaluateExpressionV2(rhs, { x, y, z: 0 });
  assert.ok(Math.abs(at(0, 2)) < 1e-12);
  assert.ok(Math.abs(at(Math.PI / 4, 0) - 4) < 1e-12);
  assert.ok(Math.abs(at(-Math.PI / 4, 0) + 4) < 1e-12);
  assert.ok(Math.abs(at(Math.PI / 4, 0)) > Math.abs(at(Math.PI / 4, 2)));
  const angle = call("atan2", variable("y"), variable("x"));
  assert.equal(viz.evaluateExpressionV2(angle, { x: 0, y: 1 }), Math.PI / 2);
});

test("validates bounded sampled particles, vector fields and scalar heatmaps", () => {
  const spec = svgSpec();
  spec.renderer = "canvas"; spec.kind = "simulation2d"; spec.family = "dense_fields";
  spec.scene.coordinate_system = "cartesian2d";
  spec.scene.layers = [
    { type: "axes", x_label: "x", y_label: "y", grid: true },
    { type: "particles", label: "samples", points: [[0, 0], [1, 1]], color: "purple" },
    { type: "vector_field", label: "F=(x,-y)", vectors: [[1, 1, 0.2, -0.2], [-1, 1, -0.2, -0.2]], color: "teal" },
    { type: "probe_vector", x_control: "a", y_control: "a", x_expression: variable("x"), y_expression: { type: "unary", op: "-", arg: variable("y") }, scale: 0.45, label: "movable field probe", color: "gold" },
    { type: "heatmap", label: "scalar field", x_domain: [-1, 1], y_domain: [-1, 1], rows: 2, columns: 2, values: [-1, 0, 0.5, 1], color: "orange" },
  ];
  assert.equal(viz.validateSpec(spec).ok, true);
  const badGrid = structuredClone(spec); badGrid.scene.layers[4].values.pop();
  assert.equal(viz.validateSpec(badGrid).ok, false);
  const zeroVector = structuredClone(spec); zeroVector.scene.layers[2].vectors[0] = [0, 0, 0, 0];
  assert.equal(viz.validateSpec(zeroVector).ok, false);
  const unknownProbeControl = structuredClone(spec); unknownProbeControl.scene.layers[3].x_control = "missing";
  assert.equal(viz.validateSpec(unknownProbeControl).ok, false);
});

test("validates explicit non-overlapping multi-panel membership", () => {
  const spec = svgSpec();
  spec.renderer = "canvas"; spec.kind = "simulation2d"; spec.family = "multi_panel";
  spec.scene.coordinate_system = "cartesian2d";
  spec.scene.layers = [
    { type: "axes", x_label: "x", y_label: "y", grid: true },
    { type: "polyline", label: "time series", points: [[0, 0], [1, 1]], color: "teal" },
    { type: "polyline", label: "phase portrait", points: [[0, 1], [1, 0]], color: "orange" },
    { type: "panel", id: "time", title: "Time series", x_label: "time", y_label: "value", members: ["time series"] },
    { type: "panel", id: "phase", title: "Phase portrait", x_label: "x", y_label: "dx/dt", members: ["phase portrait"] },
  ];
  assert.equal(viz.validateSpec(spec).ok, true);
  const ambiguous = structuredClone(spec); ambiguous.scene.layers[4].members.push("time series");
  assert.equal(viz.validateSpec(ambiguous).ok, false);
});

test("keeps eight parameter controls plus bounded animation transport controls", () => {
  const spec = svgSpec();
  spec.controls = Array.from({ length: 8 }, (_, index) => ({
    id: `parameter_${index}`,
    label: `Parameter ${index}`,
    type: "range",
    value: 0,
    min: 0,
    max: 1,
    step: 0.1,
  }));
  spec.controls.push(
    { id: "play", label: "Play", type: "button", value: 0 },
    { id: "pause", label: "Pause", type: "button", value: 0 },
    { id: "restart", label: "Restart", type: "button", value: 0 },
  );
  assert.equal(viz.validateSpec(spec).ok, true);

  const extraParameter = structuredClone(spec);
  extraParameter.controls.splice(8, 0, {
    id: "parameter_8", label: "Parameter 8", type: "range",
    value: 0, min: 0, max: 1, step: 0.1,
  });
  assert.equal(viz.validateSpec(extraParameter).ok, false);
});

test("rejects unsafe fields, functions, budgets, topology and prototype keys", () => {
  const unknown = surface(); unknown.script = "alert(1)";
  assert.equal(viz.validateSpec(unknown).ok, false);
  const unsafe = surface(); unsafe.scene.layers[0].relationship.right = call("constructor", variable("x"));
  assert.equal(viz.validateSpec(unsafe).ok, false);
  const oversized = surface("implicit_surface"); oversized.scene.layers[0].resolution = [65, 65, 65];
  assert.equal(viz.validateSpec(oversized).ok, false);
  const badLink = svgSpec(); badLink.scene.layers[2].to = "missing";
  assert.equal(viz.validateSpec(badLink).ok, false);
  const poisoned = JSON.parse('{"version":2,"__proto__":{"polluted":true}}');
  assert.equal(viz.validateSpec(poisoned).ok, false);
  assert.equal({}.polluted, undefined);
});

test("round-trips V2 fragments and extracts only a fully validated fence", () => {
  const spec = svgSpec();
  assert.deepEqual(viz.decodeSpec(viz.encodeSpec(spec)), spec);
  const source = `Explanation\n\n\`\`\`muta-viz\n${JSON.stringify(spec)}\n\`\`\``;
  const extracted = viz.extract(source);
  assert.equal(extracted.markdown, "Explanation");
  assert.deepEqual(extracted.visualizations, [spec]);
});
