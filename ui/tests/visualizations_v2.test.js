"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const viz = require("../visualizations.js");
const schemaConformance = require("./fixtures/visualization-v2-schema-conformance.json");

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
  const invisible = structuredClone(bound);
  invisible.renderer = "canvas"; invisible.kind = "simulation2d";
  assert.match(viz.validateSpec(invisible).error, /binding target/);

  const underdeclaredSurface = surface();
  underdeclaredSurface.budget.max_triangles = 1;
  assert.match(viz.validateSpec(underdeclaredSurface).error, /triangle budget/);
  const surfaceMeshTriangles = 2 * 48 * 48;
  underdeclaredSurface.budget.max_triangles = surfaceMeshTriangles;
  assert.match(viz.validateSpec(underdeclaredSurface).error, /triangle budget/);
  underdeclaredSurface.budget.max_triangles = surfaceMeshTriangles + 24;
  assert.equal(viz.validateSpec(underdeclaredSurface).ok, true);

  const implicit = surface("implicit_surface");
  implicit.budget.max_triangles = 24;
  assert.match(viz.validateSpec(implicit).error, /triangle budget/);
  implicit.budget.max_triangles = 25;
  assert.equal(viz.validateSpec(implicit).ok, true);

  const parametric = surface();
  parametric.family = "parametric_surface";
  parametric.scene.layers = [{
    type: "parametric_surface",
    x_expression: call("cos", variable("u")), y_expression: call("sin", variable("u")),
    z_expression: variable("v"), u_domain: [0, 6.28], v_domain: [-1, 1],
    resolution: [17, 17], label: "cylinder",
  }];
  parametric.budget.max_triangles = 512;
  assert.match(viz.validateSpec(parametric).error, /triangle budget/);
  parametric.budget.max_triangles = 512 + 352;
  assert.equal(viz.validateSpec(parametric).ok, true);

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
  spec.scene.animation = { mode: "guided_reveal", duration: 6 };
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

test("rejects incomplete mislabeled numeric and static animation transport controls", () => {
  const animated = svgSpec();
  animated.scene.animation = { mode: "guided_reveal", duration: 6 };
  animated.controls = [
    { id: "play", label: "Play", type: "button", value: 0 },
    { id: "pause", label: "Pause", type: "button", value: 0 },
    { id: "restart", label: "Restart", type: "button", value: 0 },
  ];
  assert.equal(viz.validateSpec(animated).ok, true);

  const incomplete = structuredClone(animated); incomplete.controls.pop();
  assert.match(viz.validateSpec(incomplete).error, /canonical Play/);
  const mislabeled = structuredClone(animated); mislabeled.controls[0].label = "Delete diagram";
  assert.match(viz.validateSpec(mislabeled).error, /canonical Play/);
  const numeric = structuredClone(animated);
  numeric.controls[0] = { id: "play", label: "Play", type: "range", value: 0, min: 0, max: 1, step: 0.1 };
  assert.match(viz.validateSpec(numeric).error, /canonical Play/);
  const staticTransport = structuredClone(animated); delete staticTransport.scene.animation;
  assert.match(viz.validateSpec(staticTransport).error, /canonical Play/);
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

test("rejects unsafe family names and boolean numeric AST values", () => {
  const unsafeFamily = surface(); unsafeFamily.family = "not safe!";
  assert.match(viz.validateSpec(unsafeFamily).error, /metadata/);
  const nonCanonicalFamily = surface(); nonCanonicalFamily.family = "Not-safe";
  assert.match(viz.validateSpec(nonCanonicalFamily).error, /metadata/);
  const booleanAst = surface();
  booleanAst.scene.layers[0].relationship.right = { type: "number", value: true };
  assert.match(viz.validateSpec(booleanAst).error, /invalid number node/);
});

test("fails closed on the shared server-browser conformance mutations", () => {
  const balancedExpression = (leaves) => {
    if (leaves === 1) return variable("x");
    const half = Math.floor(leaves / 2);
    return binary("+", balancedExpression(half), balancedExpression(leaves - half));
  };
  const candidates = { none: surface() };

  let candidate = surface(); candidate.budget.max_points = 4096.5; candidates.fractional_budget = candidate;
  candidate = svgSpec(); candidate.controls[0].id = "Height"; candidates.unsafe_control_id = candidate;
  candidate = svgSpec(); candidate.controls[0].label = "x".repeat(81); candidates.oversize_control_label = candidate;
  candidate = surface(); candidate.scene.layers = [
    { type: "sphere", position: [1001, 0, 0], size: 1, label: "", color: "teal" },
  ]; candidates.invalid_sphere = candidate;
  candidate = surface(); candidate.scene.layers = [{
    type: "line", points: Array.from({ length: 513 }, (_, index) => [index, 0, 0]),
    label: "bounded line", color: "teal",
  }]; candidates.oversize_line = candidate;
  candidate = surface(); candidate.library = "d3"; candidate.renderer = "canvas";
  candidate.kind = "simulation2d"; candidate.scene = { coordinate_system: "screen", layers: [{
    type: "particles", points: Array.from({ length: 801 }, (_, index) => [index, 0]),
    label: "particles", color: "teal",
  }] }; candidates.oversize_particles = candidate;
  candidate = surface(); candidate.scene.layers[0].relationship.right = balancedExpression(64);
  candidate.scene.layers[0].resolution = [65, 65]; candidates.oversize_surface_work = candidate;
  candidate = surface(); candidate.scene.layers[0].animation = ["mode", "duration"];
  candidates.malformed_animation = candidate;
  candidate = surface(); candidate.scene.layers = [{
    type: "plane", normal: [0, 0, 1], constant: "oops", label: "plane", color: "teal",
  }]; candidates.malformed_plane = candidate;
  candidate = surface(); candidate.controls = [
    { id: "choice", label: "Choice", type: "select", value: "x", options: [{}] },
  ]; candidates.malformed_select = candidate;
  candidate = svgSpec(); candidate.controls[0].step = 1e-7; candidates.tiny_control_step = candidate;
  candidate = surface(); candidate.scene.layers = Array.from({ length: 96 }, (_, index) => ({
    type: "text", x: 0, y: index, text: "界".repeat(160), color: "teal",
  })); candidates.oversize_utf8 = candidate;
  candidate = surface(); delete candidate.scene.layers[0].z_domain; candidates.missing_layer_field = candidate;
  candidate = surface(); candidate.scene.layers[0].relationship.right = balancedExpression(81);
  candidate.scene.layers[0].resolution = [9, 9]; candidates.oversize_combined_ast = candidate;
  candidate = surface(); candidate.library = "d3"; candidate.renderer = "svg"; candidate.kind = "scene2d";
  candidate.scene = { coordinate_system: "screen", layers: [
    { type: "circle", x: 10001, y: 0, r: 2, label: "circle", color: "teal" },
  ] }; candidates.invalid_circle_position = candidate;
  candidate = structuredClone(candidate); candidate.scene.layers = [
    { type: "text", x: 0, y: 0, text: "", color: "teal" },
  ]; candidates.empty_text = candidate;
  candidate = surface(); candidate.renderer = []; candidates.malformed_renderer = candidate;
  candidate = svgSpec(); candidate.controls[0].type = {}; candidates.malformed_control_type = candidate;
  candidate = surface(); candidate.scene.coordinate_system = []; candidates.malformed_coordinate_system = candidate;
  candidate = surface(); candidate.scene.layers[0].relationship.right.type = {}; candidates.malformed_ast_type = candidate;
  candidate = surface(); candidate.scene.layers[0].relationship.right = {
    type: "call", name: {}, args: [variable("x")],
  }; candidates.malformed_ast_function = candidate;
  candidate = surface(); candidate.scene.layers[0].animation = { mode: {}, duration: 8 };
  candidates.malformed_animation_mode = candidate;
  candidate = surface(); candidate.library = "d3"; candidate.renderer = "svg"; candidate.kind = "scene2d";
  candidate.controls = []; candidate.scene = { coordinate_system: "screen", layers: [
    { type: "node", id: "a", x: 0, y: 0, width: 20, height: 20, label: "A", color: "teal" },
    { type: "node", id: "b", x: 40, y: 0, width: 20, height: 20, label: "B", color: "teal" },
    { type: "link", from: [], to: "b", arrow: true, label: "edge" },
  ] };
  candidates.malformed_link_id = candidate;
  candidate = svgSpec(); candidate.controls[0].binding = { target_label: "triangle", effect: {} };
  candidates.malformed_binding_effect = candidate;
  candidate = surface(); candidate.library = "d3"; candidate.renderer = "svg"; candidate.kind = "scene2d";
  candidate.scene = { coordinate_system: "screen", layers: [{
    type: "panel", id: "panel", title: "Panel", x_label: "x", y_label: "y", members: [{}],
  }] }; candidates.malformed_panel_members = candidate;
  candidate = surface(); candidate.renderer = ["three"]; candidates.renderer_array = candidate;
  candidate = surface(); candidate.family = ["explicit_surface"]; candidates.family_array = candidate;
  candidate = surface(); candidate.family = false; candidates.family_boolean = candidate;
  candidate = svgSpec(); candidate.controls[0].id = false; candidates.control_id_boolean = candidate;
  candidate = svgSpec(); candidate.controls[0].id = null; candidates.control_id_null = candidate;
  candidate = surface(); candidate.library = "d3"; candidate.renderer = "svg"; candidate.kind = "scene2d";
  candidate.scene = { coordinate_system: "screen", layers: [
    { type: "circle", x: 10, y: 10, r: 2, label: "circle", color: ["gold"] },
  ] }; candidates.color_array = candidate;
  candidate = surface(); candidate.library = "d3"; candidate.renderer = "svg"; candidate.kind = "scene2d";
  candidate.scene = { coordinate_system: "screen", layers: [
    { type: "node", id: ["n0"], x: 0, y: 0, width: 20, height: 20, label: "Node", color: "teal" },
  ] }; candidates.node_id_array = candidate;
  candidate = surface(); candidate.library = "d3"; candidate.renderer = "svg"; candidate.kind = "scene2d";
  candidate.scene = { coordinate_system: "screen", layers: [
    { type: "polyline", label: "trace", points: [[0, 0], [1, 1]], color: "teal" },
    { type: "panel", id: ["panel"], title: "Panel", x_label: "x", y_label: "y", members: ["trace"] },
  ] }; candidates.panel_id_array = candidate;
  candidate = surface(); candidate.scene.layers[0].relationship.right = { type: "number", value: 1e100 };
  candidates.large_ast_number = candidate;
  candidate = surface(); candidate.scene.layers = Array.from({ length: 60 }, (_, index) => ({
    type: "text", x: 0, y: index, text: "界".repeat(160), color: "teal",
  })); candidates.utf8_within_byte_budget = candidate;

  assert.deepEqual(new Set(schemaConformance.cases.map((item) => item.operation)), new Set(Object.keys(candidates)));
  for (const item of schemaConformance.cases) {
    assert.equal(viz.validateSpec(candidates[item.operation]).ok, item.accepted, item.id);
  }
});

test("generated type-mutation properties fail closed across the browser schema", () => {
  const mutationPaths = (value, prefix = []) => {
    const paths = [];
    if (value && typeof value === "object") {
      for (const [key, child] of Object.entries(value)) {
        const path = [...prefix, Array.isArray(value) ? Number(key) : key];
        const replacement = Array.isArray(child) ? {} : child && typeof child === "object"
          ? [] : typeof child === "string" ? [] : {};
        paths.push([path, replacement], ...mutationPaths(child, path));
      }
    }
    return paths;
  };
  const setPath = (target, path, replacement) => {
    let parent = target;
    for (const part of path.slice(0, -1)) parent = parent[part];
    parent[path.at(-1)] = replacement;
  };
  let mutationCount = 0;
  for (const base of [surface(), svgSpec()]) {
    for (const [path, replacement] of mutationPaths(base)) {
      const candidate = structuredClone(base);
      setPath(candidate, path, replacement);
      mutationCount += 1;
      assert.equal(viz.validateSpec(candidate).ok, false, path.join("."));
    }
  }
  assert.ok(mutationCount >= 100);
});

test("round-trips V2 fragments and extracts only a fully validated fence", () => {
  const spec = svgSpec();
  assert.deepEqual(viz.decodeSpec(viz.encodeSpec(spec)), spec);
  const source = `Explanation\n\n\`\`\`muta-viz\n${JSON.stringify(spec)}\n\`\`\``;
  const extracted = viz.extract(source);
  assert.equal(extracted.markdown, "Explanation");
  assert.deepEqual(extracted.visualizations, [spec]);
});
