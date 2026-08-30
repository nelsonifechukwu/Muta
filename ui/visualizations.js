/* Parse model-authored visualization specs and mount them as sandboxed, declarative frames. */
"use strict";

((global) => {
  const LIBRARIES = new Set(["d3", "three", "gsap", "anime", "motion"]);
  const KINDS = Object.freeze({
    d3: new Set(["line", "scatter", "bar", "force", "diagram"]),
    three: new Set(["scene3d"]),
    gsap: new Set(["animation"]),
    anime: new Set(["animation"]),
    motion: new Set(["animation"]),
  });
  const ELEMENT_TYPES = new Set(["circle", "rect", "line", "arrow", "text"]);
  const OBJECT_TYPES = new Set(["sphere", "box", "point", "line", "vector", "surface"]);
  const DIAGRAM_SHAPES = new Set(["circle", "rounded", "label"]);
  const BOND_TYPES = new Set(["single", "double", "triple", "dashed"]);
  const TRACK_FIELDS = new Set(["x", "y", "scale", "rotate", "opacity"]);
  const MAX_SPEC_CHARS = 48 * 1024;
  const MAX_TREE_NODES = 2500;
  const MAX_STATIC_SURFACE_WORK = 500_000;
  const MAX_ANIMATED_SURFACE_WORK = 200_000;
  const V2_SURFACE_LABEL_TRIANGLES = 24;
  const V2_PARAMETRIC_MARKER_TRIANGLES = 352;
  const SAFE_ID = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
  const SAFE_FAMILY = /^[a-z][a-z0-9_]{0,63}$/;
  const SAFE_CONTROL_ID = /^[a-z][a-z0-9_]{0,31}$/;
  const SAFE_COLOR = /^(?:#[0-9a-fA-F]{3,8}|(?:rgb|hsl)a?\([0-9.,%\s-]+\)|black|white|gray|grey|red|green|blue|orange|purple|teal|gold)$/;
  const FORBIDDEN_KEYS = new Set(["__proto__", "prototype", "constructor"]);
  const SURFACE_FUNCTIONS = new Set([
    "abs", "acos", "asin", "atan", "cos", "cosh", "exp", "ln", "log", "sin", "sinh",
    "sqrt", "tan", "tanh",
  ]);
  const SURFACE_VARIABLES = new Set(["x", "y", "t"]);
  const SURFACE_CONSTANTS = new Set(["e", "pi"]);
  const SURFACE_BINARY = new Set(["+", "-", "*", "/", "^"]);
  const V2_RENDERERS = Object.freeze({
    svg: ["d3", "scene2d"],
    canvas: ["d3", "simulation2d"],
    three: ["three", "scene3d"],
  });
  const V2_LAYER_KEYS = Object.freeze({
    axes: new Set(["type", "x_label", "y_label", "grid"]),
    polyline: new Set(["type", "label", "points", "color"]),
    node: new Set(["type", "id", "x", "y", "width", "height", "label", "color"]),
    link: new Set(["type", "from", "to", "arrow", "label"]),
    sphere: new Set(["type", "position", "size", "label", "color"]),
    box: new Set(["type", "position", "size", "label", "color"]),
    point: new Set(["type", "position", "size", "label", "color"]),
    vector: new Set(["type", "from", "to", "label", "color"]),
    line: new Set(["type", "points", "label", "color"]),
    plane: new Set(["type", "normal", "constant", "label", "color"]),
    explicit_surface: new Set(["type", "label", "relationship", "x_domain", "y_domain", "z_domain", "resolution", "animation"]),
    implicit_surface: new Set(["type", "label", "relationship", "x_domain", "y_domain", "z_domain", "resolution", "animation"]),
    parametric_surface: new Set(["type", "x_expression", "y_expression", "z_expression", "u_domain", "v_domain", "resolution", "label", "animation"]),
    arrow: new Set(["type", "from", "to", "label", "color"]),
    angle_arc: new Set(["type", "cx", "cy", "r", "start_angle", "end_angle", "clockwise", "label", "color"]),
    circle: new Set(["type", "x", "y", "r", "label", "color"]),
    rect: new Set(["type", "x", "y", "width", "height", "label", "color"]),
    text: new Set(["type", "x", "y", "text", "color"]),
    particles: new Set(["type", "points", "color", "label"]),
    vector_field: new Set(["type", "vectors", "color", "label"]),
    probe_vector: new Set(["type", "x_control", "y_control", "x_expression", "y_expression", "scale", "color", "label"]),
    heatmap: new Set(["type", "x_domain", "y_domain", "rows", "columns", "values", "color", "label"]),
    panel: new Set(["type", "id", "title", "x_label", "y_label", "members"]),
  });
  const FENCE_START = /(^|\n)( {0,3})```muta-viz[\t ]*\r?\n/g;
  // Qwen3-0.6B sometimes obeys the semantic marker but normalizes the unfamiliar fence into
  // display text plus a JSON fence. It is equally safe after strict schema validation, and
  // accepting this one exact degradation makes the shipped smoke model useful.
  const MARKED_JSON_START = /(^|\n)( {0,3})\$\$muta-viz\$\$[\t ]*\r?\n\2```json[\t ]*\r?\n/g;

  function finiteNumber(value, min = -1e6, max = 1e6) {
    return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
  }

  function nonEmptyString(value, max) {
    return typeof value === "string" && value.trim().length > 0 && [...value].length <= max;
  }

  function point(value) {
    return Array.isArray(value) && value.length === 2 && value.every((item) => finiteNumber(item));
  }

  function vector3(value) {
    return Array.isArray(value)
      && value.length === 3
      && value.every((item) => finiteNumber(item, -1000, 1000));
  }

  function numberPair(value, min = -100, max = 100) {
    return Array.isArray(value) && value.length === 2
      && value.every((item) => finiteNumber(item, min, max)) && value[0] < value[1];
  }

  function validateSurfaceExpression(root) {
    let nodes = 0;
    const visit = (node, depth = 0) => {
      nodes += 1;
      if (nodes > 128) return "surface expression has too many operations";
      if (depth > 24) return "surface expression is nested too deeply";
      if (!node || typeof node !== "object" || Array.isArray(node)) {
        return "surface expression node is invalid";
      }
      if (node.type === "number") {
        return Object.keys(node).length === 2 && finiteNumber(node.value, -1e9, 1e9)
          ? "" : "surface number is invalid";
      }
      if (node.type === "variable") {
        return Object.keys(node).length === 2 && SURFACE_VARIABLES.has(node.name)
          ? "" : "surface variable is invalid";
      }
      if (node.type === "constant") {
        return Object.keys(node).length === 2 && SURFACE_CONSTANTS.has(node.name)
          ? "" : "surface constant is invalid";
      }
      if (node.type === "unary") {
        if (Object.keys(node).length !== 3 || node.op !== "-") return "surface unary operator is invalid";
        return visit(node.arg, depth + 1);
      }
      if (node.type === "binary") {
        if (Object.keys(node).length !== 4 || !SURFACE_BINARY.has(node.op)) {
          return "surface binary operator is invalid";
        }
        return visit(node.left, depth + 1) || visit(node.right, depth + 1);
      }
      if (node.type === "call") {
        if (Object.keys(node).length !== 3 || !SURFACE_FUNCTIONS.has(node.name)) {
          return "surface function is invalid";
        }
        return visit(node.arg, depth + 1);
      }
      return "surface expression type is invalid";
    };
    return visit(root);
  }

  function surfaceExpressionNodeCount(root) {
    let nodes = 0;
    const pending = [root];
    while (pending.length) {
      const node = pending.pop();
      nodes += 1;
      if (node.type === "binary") pending.push(node.left, node.right);
      else if (node.type === "unary" || node.type === "call") pending.push(node.arg);
    }
    return nodes;
  }

  function evaluateSurfaceExpression(node, variables = {}) {
    const visit = (current, depth = 0) => {
      if (depth > 24) throw new Error("surface expression is nested too deeply");
      let value;
      if (current.type === "number") value = current.value;
      else if (current.type === "constant") value = current.name === "e" ? Math.E : Math.PI;
      else if (current.type === "variable") value = Number(variables[current.name] ?? 0);
      else if (current.type === "unary") value = -visit(current.arg, depth + 1);
      else if (current.type === "binary") {
        const left = visit(current.left, depth + 1);
        const right = visit(current.right, depth + 1);
        if (current.op === "+") value = left + right;
        else if (current.op === "-") value = left - right;
        else if (current.op === "*") value = left * right;
        else if (current.op === "/") value = right === 0 ? NaN : left / right;
        else value = left ** right;
      } else if (current.type === "call") {
        const argument = visit(current.arg, depth + 1);
        const functions = {
          abs: Math.abs, acos: Math.acos, asin: Math.asin, atan: Math.atan, cos: Math.cos,
          cosh: Math.cosh, exp: Math.exp, ln: Math.log, log: Math.log, sin: Math.sin,
          sinh: Math.sinh, sqrt: Math.sqrt, tan: Math.tan, tanh: Math.tanh,
        };
        value = functions[current.name](argument);
      } else {
        throw new Error("unsupported surface expression node");
      }
      if (!Number.isFinite(value) || Math.abs(value) > 1e9) {
        throw new Error("surface expression result is not finite or is out of range");
      }
      return value;
    };
    return visit(node);
  }

  function validateTree(value) {
    let nodes = 0;
    const walk = (node, depth = 0) => {
      nodes += 1;
      if (nodes > MAX_TREE_NODES) return "visualization has too many values";
      if (depth > 9) return "visualization is nested too deeply";
      if (typeof node === "string") {
        return node.length <= 500 ? "" : "visualization text is too long";
      }
      if (typeof node === "number") return finiteNumber(node) ? "" : "number is out of range";
      if (typeof node === "boolean" || node === null) return "";
      if (Array.isArray(node)) {
        if (node.length > 500) return "visualization array is too long";
        for (const item of node) {
          const error = walk(item, depth + 1);
          if (error) return error;
        }
        return "";
      }
      if (!node || typeof node !== "object") return "unsupported visualization value";
      for (const [key, item] of Object.entries(node)) {
        if (FORBIDDEN_KEYS.has(key)) return `forbidden key: ${key}`;
        if (key.length > 64) return "visualization key is too long";
        // Surface ASTs have their own stricter node/depth/key validator. Treat the checked tree
        // as one data leaf here so the generic visualization depth cap does not reject ordinary
        // operator precedence nested inside an otherwise shallow spec.
        if (key === "expression" && item && typeof item === "object") {
          const expressionError = validateSurfaceExpression(item);
          if (expressionError) return expressionError;
          continue;
        }
        if (["color", "fill", "stroke", "background"].includes(key) && !SAFE_COLOR.test(item)) {
          return `unsafe color: ${String(item)}`;
        }
        const error = walk(item, depth + 1);
        if (error) return error;
      }
      return "";
    };
    return walk(value);
  }

  function validateD3(spec) {
    if (spec.kind === "line" || spec.kind === "scatter") {
      if (!Array.isArray(spec.series) || spec.series.length < 1 || spec.series.length > 6) {
        return "line and scatter plots need 1 to 6 series";
      }
      for (const series of spec.series) {
        if (!series || !nonEmptyString(series.label, 80)) return "each series needs a label";
        if (!Array.isArray(series.points) || series.points.length < 2 || series.points.length > 200) {
          return "each series needs 2 to 200 points";
        }
        if (!series.points.every(point)) return "plot points must be [x,y] number pairs";
      }
      return "";
    }
    if (spec.kind === "bar") {
      if (!Array.isArray(spec.data) || spec.data.length < 1 || spec.data.length > 30) {
        return "bar plots need 1 to 30 records";
      }
      for (const record of spec.data) {
        if (!record || !nonEmptyString(record.label, 80) || !finiteNumber(record.value)) {
          return "bar records need a label and numeric value";
        }
      }
      return "";
    }
    if (spec.kind === "diagram") {
      if (!Array.isArray(spec.nodes) || spec.nodes.length < 1 || spec.nodes.length > 40) {
        return "schematic diagrams need 1 to 40 nodes";
      }
      const ids = new Set();
      for (const node of spec.nodes) {
        if (!node || !SAFE_ID.test(node.id) || ids.has(node.id)) {
          return "schematic nodes need unique safe ids";
        }
        if (!nonEmptyString(node.label, 80) || !DIAGRAM_SHAPES.has(node.shape)) {
          return "schematic nodes need a label and supported shape";
        }
        if (!finiteNumber(node.x, 0, 1000) || !finiteNumber(node.y, 0, 1000)) {
          return "schematic node coordinates are out of range";
        }
        if (node.size !== undefined && !finiteNumber(node.size, 6, 80)) {
          return "schematic node size is out of range";
        }
        if (node.width !== undefined && !finiteNumber(node.width, 20, 280)) {
          return "schematic node width is out of range";
        }
        if (node.height !== undefined && !finiteNumber(node.height, 20, 160)) {
          return "schematic node height is out of range";
        }
        ids.add(node.id);
      }
      if (!Array.isArray(spec.links) || spec.links.length > 100) {
        return "schematic diagrams support up to 100 links";
      }
      for (const link of spec.links) {
        if (!link || !ids.has(link.source) || !ids.has(link.target)) {
          return "every schematic link must reference existing nodes";
        }
        if (link.bond !== undefined && !BOND_TYPES.has(link.bond)) {
          return "schematic link style is unsupported";
        }
        if (link.arrow !== undefined && typeof link.arrow !== "boolean") {
          return "schematic arrow must be true or false";
        }
        if (link.label !== undefined && !nonEmptyString(link.label, 80)) {
          return "schematic link label is invalid";
        }
        for (const coordinate of [link.label_x, link.label_y]) {
          if (coordinate !== undefined && !finiteNumber(coordinate, 0, 1000)) {
            return "schematic link label coordinate is invalid";
          }
        }
        if (link.via !== undefined && (
          !Array.isArray(link.via) || link.via.length > 4
          || !link.via.every((item) => Array.isArray(item) && item.length === 2
            && item.every((coordinate) => finiteNumber(coordinate, 0, 1000)))
        )) {
          return "schematic link route is invalid";
        }
      }
      if (spec.annotations !== undefined) {
        if (!Array.isArray(spec.annotations) || spec.annotations.length > 20) {
          return "schematic diagrams support up to 20 annotations";
        }
        for (const note of spec.annotations) {
          if (!note || !nonEmptyString(note.text, 120)
            || !finiteNumber(note.x, 0, 1000) || !finiteNumber(note.y, 0, 1000)) {
            return "schematic annotation is invalid";
          }
        }
      }
      return "";
    }
    if (!Array.isArray(spec.nodes) || spec.nodes.length < 2 || spec.nodes.length > 50) {
      return "force diagrams need 2 to 50 nodes";
    }
    const ids = new Set();
    for (const node of spec.nodes) {
      if (!node || !SAFE_ID.test(node.id) || ids.has(node.id)) {
        return "force nodes need unique safe ids";
      }
      ids.add(node.id);
    }
    if (!Array.isArray(spec.links) || spec.links.length < 1 || spec.links.length > 100) {
      return "force diagrams need 1 to 100 links";
    }
    if (!spec.links.every((link) => link && ids.has(link.source) && ids.has(link.target))) {
      return "every force link must reference existing nodes";
    }
    return "";
  }

  function validateThree(spec) {
    if (!Array.isArray(spec.objects) || spec.objects.length < 1 || spec.objects.length > 40) {
      return "3D scenes need 1 to 40 objects";
    }
    if (spec.notes !== undefined && (
      !Array.isArray(spec.notes) || spec.notes.length > 4
      || !spec.notes.every((note) => nonEmptyString(note, 120))
    )) {
      return "3D scene notes are invalid";
    }
    let surfaces = 0;
    for (const object of spec.objects) {
      if (!object || !OBJECT_TYPES.has(object.type)) return "unsupported 3D object";
      if (object.type === "surface") {
        surfaces += 1;
        if (surfaces > 1) return "3D scenes support one mathematical surface";
        if (!nonEmptyString(object.label, 120) || !nonEmptyString(object.expression_text, 240)) {
          return "mathematical surfaces need a concise equation label";
        }
        if (!numberPair(object.x_domain) || !numberPair(object.y_domain)) {
          return "surface x/y domains must be increasing bounded pairs";
        }
        if (!numberPair(object.z_domain, -1e9, 1e9)) {
          return "surface z domain must be an increasing finite pair";
        }
        if (!Array.isArray(object.resolution) || object.resolution.length !== 2
          || !object.resolution.every((item) => Number.isInteger(item) && item >= 17 && item <= 97)
          || object.resolution[0] * object.resolution[1] > 8192) {
          return "surface resolution is outside the safe rendering budget";
        }
        const expressionError = validateSurfaceExpression(object.expression);
        if (expressionError) return expressionError;
        const sampleCount = object.resolution[0] * object.resolution[1];
        if (sampleCount * surfaceExpressionNodeCount(object.expression) > MAX_STATIC_SURFACE_WORK) {
          return "surface expression and resolution exceed the safe rendering budget";
        }
        if (object.animation !== undefined) {
          const animation = object.animation;
          if (!animation || typeof animation !== "object" || Array.isArray(animation)
            || !["phase", "orbit"].includes(animation.mode)
            || !finiteNumber(animation.duration, 2, 30)) {
            return "surface animation is invalid";
          }
          if (animation.mode === "phase") {
            const animatedError = validateSurfaceExpression(animation.expression);
            if (animatedError) return animatedError;
            if (
              sampleCount * surfaceExpressionNodeCount(animation.expression)
              > MAX_ANIMATED_SURFACE_WORK
            ) {
              return "animated surface exceeds the safe per-frame rendering budget";
            }
          } else if (animation.expression !== undefined) {
            return "orbit animation cannot replace the surface equation";
          }
        }
      } else if (object.type === "vector") {
        if (!vector3(object.from) || !vector3(object.to)) return "vectors need from/to triples";
        if (object.from.every((value, index) => value === object.to[index])) {
          return "vectors must have non-zero length";
        }
      } else if (object.type === "line") {
        if (!Array.isArray(object.points) || object.points.length < 2 || object.points.length > 100) {
          return "3D lines need 2 to 100 points";
        }
        if (!object.points.every(vector3)) return "3D line points need three coordinates";
      } else if (!vector3(object.position || [0, 0, 0])) {
        return "3D object positions need three coordinates";
      }
      if (object.label_position !== undefined && !vector3(object.label_position)) {
        return "3D label positions need three coordinates";
      }
      if (object.size !== undefined && !finiteNumber(object.size, 0.01, 100)) {
        return "3D object size is out of range";
      }
    }
    return "";
  }

  function validateAnimation(spec) {
    if (!Array.isArray(spec.elements) || spec.elements.length < 1 || spec.elements.length > 30) {
      return "animations need 1 to 30 elements";
    }
    const ids = new Set();
    for (const element of spec.elements) {
      if (!element || !SAFE_ID.test(element.id) || ids.has(element.id)) {
        return "animation elements need unique safe ids";
      }
      if (!ELEMENT_TYPES.has(element.type)) return "unsupported animation element";
      for (const field of ["x", "y", "x1", "y1", "x2", "y2"]) {
        if (element[field] !== undefined && !finiteNumber(element[field], -10000, 10000)) {
          return `animation element ${field} is out of range`;
        }
      }
      for (const field of ["r", "width", "height", "stroke_width"]) {
        if (element[field] !== undefined && !finiteNumber(element[field], 0.1, 1000)) {
          return `animation element ${field} must be positive`;
        }
      }
      for (const field of ["text", "label"]) {
        if (element[field] !== undefined && !nonEmptyString(element[field], 160)) {
          return `animation element ${field} is invalid`;
        }
      }
      ids.add(element.id);
    }
    if (!Array.isArray(spec.tracks) || spec.tracks.length < 1 || spec.tracks.length > 60) {
      return "animations need 1 to 60 tracks";
    }
    const tracked = new Set();
    for (const track of spec.tracks) {
      if (!track || !ids.has(track.target)) return "animation track target does not exist";
      if (tracked.has(track.target)) return "use at most one animation track per element";
      tracked.add(track.target);
      if (!track.to || typeof track.to !== "object") return "animation tracks need a to object";
      const from = track.from && typeof track.from === "object" ? track.from : {};
      for (const state of [from, track.to]) {
        for (const [key, value] of Object.entries(state)) {
          if (!TRACK_FIELDS.has(key) || !finiteNumber(value, -10000, 10000)) {
            return `unsupported animation field: ${key}`;
          }
        }
      }
      if (!finiteNumber(track.duration, 0.05, 30)) return "track duration is out of range";
      if (track.delay !== undefined && !finiteNumber(track.delay, 0, 30)) {
        return "track delay is out of range";
      }
      if (track.repeat !== undefined && (
        !Number.isInteger(track.repeat) || track.repeat < 0 || track.repeat > 3
      )) {
        return "track repeat must be an integer from 0 to 3";
      }
      if (track.direction !== undefined && !["normal", "alternate"].includes(track.direction)) {
        return "track direction is unsupported";
      }
    }
    return "";
  }

  function validateV2Expression(root) {
    let count = 0;
    const visit = (node, depth = 0) => {
      count += 1;
      if (count > 160 || depth > 24 || !node || typeof node !== "object" || Array.isArray(node)) {
        return "V2 expression exceeds its shape budget";
      }
      const keys = Object.keys(node);
      if (keys.some((key) => FORBIDDEN_KEYS.has(key))) return "forbidden expression key";
      if (node.type === "number") {
        return keys.length === 2 && finiteNumber(node.value, -1e9, 1e9) ? "" : "invalid number node";
      }
      if (node.type === "variable") {
        return keys.length === 2 && ["x", "y", "z", "u", "v", "t"].includes(node.name) ? "" : "invalid variable node";
      }
      if (node.type === "constant") {
        return keys.length === 2 && ["e", "pi"].includes(node.name) ? "" : "invalid constant node";
      }
      if (node.type === "unary") {
        return keys.length === 3 && node.op === "-" ? visit(node.arg, depth + 1) : "invalid unary node";
      }
      if (node.type === "binary") {
        if (keys.length !== 4 || !SURFACE_BINARY.has(node.op)) return "invalid binary node";
        return visit(node.left, depth + 1) || visit(node.right, depth + 1);
      }
      if (node.type === "call") {
        const unary = SURFACE_FUNCTIONS.has(node.name);
        const binary = ["atan2", "min", "max"].includes(node.name);
        const expected = binary ? 2 : 1;
        if (keys.length !== 3 || (!unary && !binary) || !Array.isArray(node.args) || node.args.length !== expected) {
          return "invalid function node";
        }
        for (const argument of node.args) {
          const error = visit(argument, depth + 1);
          if (error) return error;
        }
        return "";
      }
      return "unsupported V2 expression node";
    };
    return visit(root);
  }

  function countV2ExpressionNodes(root) {
    if (root.type === "unary") return 1 + countV2ExpressionNodes(root.arg);
    if (root.type === "binary") {
      return 1 + countV2ExpressionNodes(root.left) + countV2ExpressionNodes(root.right);
    }
    if (root.type === "call") {
      return 1 + root.args.reduce((total, argument) => total + countV2ExpressionNodes(argument), 0);
    }
    return 1;
  }

  function evaluateExpressionV2(root, variables = {}) {
    const visit = (node, depth = 0) => {
      if (depth > 24) throw new Error("V2 expression is nested too deeply");
      let value;
      if (node.type === "number") value = node.value;
      else if (node.type === "constant") value = node.name === "e" ? Math.E : Math.PI;
      else if (node.type === "variable") value = Number(variables[node.name] ?? 0);
      else if (node.type === "unary") value = -visit(node.arg, depth + 1);
      else if (node.type === "binary") {
        const left = visit(node.left, depth + 1);
        const right = visit(node.right, depth + 1);
        if (node.op === "+") value = left + right;
        else if (node.op === "-") value = left - right;
        else if (node.op === "*") value = left * right;
        else if (node.op === "/") value = Math.abs(right) < 1e-12 ? NaN : left / right;
        else value = left ** right;
      } else if (node.type === "call") {
        const args = node.args.map((argument) => visit(argument, depth + 1));
        const functions = {
          abs: Math.abs, acos: Math.acos, asin: Math.asin, atan: Math.atan, atan2: Math.atan2,
          cos: Math.cos, cosh: Math.cosh, exp: Math.exp, ln: Math.log, log: Math.log,
          max: Math.max, min: Math.min, sin: Math.sin, sinh: Math.sinh, sqrt: Math.sqrt,
          tan: Math.tan, tanh: Math.tanh,
        };
        value = functions[node.name](...args);
      } else throw new Error("unsupported V2 expression node");
      if (!Number.isFinite(value) || Math.abs(value) > 1e9) throw new Error("V2 expression is undefined");
      return value;
    };
    return visit(root);
  }

  function validateV2Spec(candidate, encoded) {
    const exactKeys = (value, allowed) => value && typeof value === "object" && !Array.isArray(value)
      && Object.keys(value).every((key) => allowed.has(key) && !FORBIDDEN_KEYS.has(key));
    const top = new Set(["version", "library", "renderer", "kind", "family", "title", "aria_label", "text_fallback", "height", "controls", "budget", "scene"]);
    if (!exactKeys(candidate, top) || Object.keys(candidate).length !== top.size) return { ok: false, error: "V2 fields are incomplete" };
    const compatible = typeof candidate.renderer === "string" ? V2_RENDERERS[candidate.renderer] : null;
    if (!compatible || typeof candidate.library !== "string" || typeof candidate.kind !== "string"
      || candidate.library !== compatible[0] || candidate.kind !== compatible[1]) {
      return { ok: false, error: "V2 renderer and kind are incompatible" };
    }
    if (typeof candidate.family !== "string" || !SAFE_FAMILY.test(candidate.family) || !nonEmptyString(candidate.title, 120)
      || !nonEmptyString(candidate.aria_label, 400) || !nonEmptyString(candidate.text_fallback, 1000)) {
      return { ok: false, error: "V2 accessible metadata is invalid" };
    }
    if (!Number.isInteger(candidate.height) || candidate.height < 240 || candidate.height > 600) {
      return { ok: false, error: "V2 height is invalid" };
    }
    if (!Array.isArray(candidate.controls) || candidate.controls.length > 11) return { ok: false, error: "V2 has too many controls" };
    const transportControlIds = new Set(["play", "pause", "restart"]);
    if (candidate.controls.filter((control) => !transportControlIds.has(control?.id)).length > 8) {
      return { ok: false, error: "V2 has too many parameter controls" };
    }
    const controlIds = new Set();
    const controlKeys = new Set(["id", "label", "type", "value", "min", "max", "step", "options", "binding"]);
    const numericControlKeys = new Set(["id", "label", "type", "value", "min", "max", "step", "binding"]);
    const bindingEffects = new Set(["translate_x", "translate_y", "scale", "radius"]);
    for (const control of candidate.controls) {
      if (!exactKeys(control, controlKeys) || typeof control.id !== "string" || !SAFE_CONTROL_ID.test(control.id) || controlIds.has(control.id)
        || !nonEmptyString(control.label, 80) || !["range", "select", "step", "button"].includes(control.type)) {
        return { ok: false, error: "V2 control is invalid" };
      }
      if (control.type === "range" && (!exactKeys(control, numericControlKeys)
        || !finiteNumber(control.min) || !finiteNumber(control.max)
        || ![7, 8].includes(Object.keys(control).length) || !finiteNumber(control.value, control.min, control.max)
        || control.min >= control.max || !finiteNumber(control.step, 0.000001, control.max - control.min))) {
        return { ok: false, error: "V2 range control is invalid" };
      }
      if (control.type === "step" && (!exactKeys(control, numericControlKeys)
        || ![7, 8].includes(Object.keys(control).length)
        || !finiteNumber(control.min) || !finiteNumber(control.max) || control.min >= control.max
        || !finiteNumber(control.step, 0.000001, control.max - control.min)
        || !finiteNumber(control.value, control.min, control.max))) {
        return { ok: false, error: "V2 step control is invalid" };
      }
      if (control.binding !== undefined && ((!exactKeys(control.binding, new Set(["target_label", "effect"])))
        || Object.keys(control.binding).length !== 2
        || !nonEmptyString(control.binding.target_label, 160)
        || !bindingEffects.has(control.binding.effect)
        || !["range", "step"].includes(control.type))) {
        return { ok: false, error: "V2 control binding is invalid" };
      }
      if (control.type === "select" && (Object.keys(control).length !== 5
        || !Array.isArray(control.options) || control.options.length < 1 || control.options.length > 12
        || new Set(control.options).size !== control.options.length
        || !control.options.every((option) => nonEmptyString(option, 48))
        || !control.options.includes(control.value))) {
        return { ok: false, error: "V2 select control is invalid" };
      }
      if (control.type === "button" && (Object.keys(control).length !== 4 || ![0, 1, false, true].includes(control.value))) {
        return { ok: false, error: "V2 button control is invalid" };
      }
      controlIds.add(control.id);
    }
    const budgetKeys = new Set(["max_points", "max_triangles", "max_fps"]);
    if (!exactKeys(candidate.budget, budgetKeys) || Object.keys(candidate.budget).length !== 3
      || !Number.isInteger(candidate.budget.max_points) || candidate.budget.max_points < 1 || candidate.budget.max_points > 20000
      || !Number.isInteger(candidate.budget.max_triangles) || candidate.budget.max_triangles < 1 || candidate.budget.max_triangles > 32000
      || !Number.isInteger(candidate.budget.max_fps) || candidate.budget.max_fps < 1 || candidate.budget.max_fps > 30) {
      return { ok: false, error: "V2 resource budget is invalid" };
    }
    if (!exactKeys(candidate.scene, new Set(["coordinate_system", "layers", "animation"]))
      || !["screen", "cartesian2d", "polar", "cartesian3d"].includes(candidate.scene.coordinate_system)
      || !Array.isArray(candidate.scene.layers) || candidate.scene.layers.length < 1 || candidate.scene.layers.length > 96) {
      return { ok: false, error: "V2 scene is invalid" };
    }
    if (candidate.scene.animation !== undefined && (!exactKeys(candidate.scene.animation, new Set(["mode", "duration"]))
      || Object.keys(candidate.scene.animation).length !== 2
      || candidate.scene.animation.mode !== "guided_reveal"
      || !finiteNumber(candidate.scene.animation.duration, 2, 30))) {
      return { ok: false, error: "V2 scene animation is invalid" };
    }
    const nodeIds = new Set(candidate.scene.layers.filter((layer) => layer?.type === "node").map((layer) => layer.id));
    if (nodeIds.size !== candidate.scene.layers.filter((layer) => layer?.type === "node").length) {
      return { ok: false, error: "V2 node IDs must be unique" };
    }
    let points = 0;
    let triangleEstimate = 0;
    const labelledLayers = new Set(candidate.scene.layers.filter((layer) => layer?.type !== "panel" && nonEmptyString(layer?.label, 160)).map((layer) => layer.label));
    const panelIds = new Set();
    const panelMembers = new Set();
    for (const layer of candidate.scene.layers) {
      if (!layer || typeof layer !== "object" || Array.isArray(layer) || typeof layer.type !== "string") {
        return { ok: false, error: "V2 layer is unsupported" };
      }
      const allowed = V2_LAYER_KEYS[layer?.type];
      if (!allowed || !exactKeys(layer, allowed)) return { ok: false, error: "V2 layer is unsupported" };
      const animationOptional = ["explicit_surface", "implicit_surface", "parametric_surface"].includes(layer.type);
      const expectedKeyCount = allowed.size - (animationOptional && layer.animation === undefined ? 1 : 0);
      if (Object.keys(layer).length !== expectedKeyCount) {
        return { ok: false, error: "V2 layer fields are incomplete" };
      }
      for (const key of ["color"]) {
        if (layer[key] !== undefined && (typeof layer[key] !== "string" || !SAFE_COLOR.test(layer[key]))) return { ok: false, error: "V2 layer color is unsafe" };
      }
      for (const key of ["label", "text"]) {
        if (layer[key] !== undefined && layer[key] !== "" && !nonEmptyString(layer[key], 160)) {
          return { ok: false, error: `V2 layer ${key} is invalid` };
        }
      }
      if (["polyline", "line", "particles"].includes(layer.type)) {
        const dimensions = layer.type === "line" ? 3 : 2;
        const pointLimit = layer.type === "line" ? 512 : layer.type === "particles" ? 800 : 4096;
        const coordinateValid = layer.type === "line" ? vector3 : point;
        if (!Array.isArray(layer.points) || layer.points.length < 2 || layer.points.length > pointLimit
          || !layer.points.every((item) => coordinateValid(item) && item.length === dimensions)) {
          return { ok: false, error: "V2 point layer is invalid" };
        }
        points += layer.points.length;
      }
      if (layer.type === "vector_field") {
        if (!Array.isArray(layer.vectors) || layer.vectors.length < 1 || layer.vectors.length > 800
          || !layer.vectors.every((sample) => Array.isArray(sample) && sample.length === 4
            && sample.every((value) => finiteNumber(value, -10000, 10000))
            && (sample[2] !== 0 || sample[3] !== 0))) {
          return { ok: false, error: "V2 vector field is invalid" };
        }
        points += layer.vectors.length * 2;
      }
      if (layer.type === "probe_vector") {
        const expressionError = validateV2Expression(layer.x_expression) || validateV2Expression(layer.y_expression);
        if (expressionError || !SAFE_ID.test(layer.x_control) || !SAFE_ID.test(layer.y_control)
          || !controlIds.has(layer.x_control) || !controlIds.has(layer.y_control)
          || !finiteNumber(layer.scale, 0.01, 10)) {
          return { ok: false, error: expressionError || "V2 probe vector is invalid" };
        }
        points += 2;
      }
      if (layer.type === "heatmap") {
        if (!Number.isInteger(layer.rows) || !Number.isInteger(layer.columns)
          || layer.rows < 1 || layer.columns < 1 || layer.rows * layer.columns > 4096
          || !Array.isArray(layer.values) || layer.values.length !== layer.rows * layer.columns
          || !layer.values.every((value) => finiteNumber(value, -1000000, 1000000))
          || !numberPair(layer.x_domain, -10000, 10000) || !numberPair(layer.y_domain, -10000, 10000)) {
          return { ok: false, error: "V2 heatmap is invalid" };
        }
        points += layer.values.length;
      }
      if (layer.type === "panel") {
        if (typeof layer.id !== "string" || !SAFE_ID.test(layer.id) || panelIds.has(layer.id)
          || !nonEmptyString(layer.title, 80) || !nonEmptyString(layer.x_label, 80) || !nonEmptyString(layer.y_label, 80)
          || !Array.isArray(layer.members) || layer.members.length < 1 || layer.members.length > 16
          || new Set(layer.members).size !== layer.members.length
          || !layer.members.every((member) => nonEmptyString(member, 160) && labelledLayers.has(member) && !panelMembers.has(member))) {
          return { ok: false, error: "V2 panel is invalid or ambiguous" };
        }
        panelIds.add(layer.id);
        layer.members.forEach((member) => panelMembers.add(member));
      }
      if (layer.type === "vector" && (!vector3(layer.from) || !vector3(layer.to))) return { ok: false, error: "V2 vector is invalid" };
      if (layer.type === "vector" && layer.from.every((value, index) => value === layer.to[index])) return { ok: false, error: "V2 vector is zero length" };
      if (layer.type === "vector") triangleEstimate += 32;
      if (layer.type === "link" && (!nodeIds.has(layer.from) || !nodeIds.has(layer.to))) return { ok: false, error: "V2 link target is missing" };
      if (layer.type === "link" && typeof layer.arrow !== "boolean") return { ok: false, error: "V2 link direction is invalid" };
      if (layer.type === "axes" && (!nonEmptyString(layer.x_label, 80) || !nonEmptyString(layer.y_label, 80) || typeof layer.grid !== "boolean")) {
        return { ok: false, error: "V2 axes are invalid" };
      }
      if (layer.type === "node" && (typeof layer.id !== "string" || !SAFE_ID.test(layer.id) || !finiteNumber(layer.x, -10000, 10000)
        || !finiteNumber(layer.y, -10000, 10000) || !finiteNumber(layer.width, 1, 2000)
        || !finiteNumber(layer.height, 1, 2000) || !nonEmptyString(layer.label, 160))) {
        return { ok: false, error: "V2 node geometry is invalid" };
      }
      if (["sphere", "box", "point"].includes(layer.type) && (!vector3(layer.position)
        || !finiteNumber(layer.size, 0.01, 100) || !nonEmptyString(layer.label, 160))) {
        return { ok: false, error: "V2 3D object is invalid" };
      }
      if (layer.type === "sphere" || layer.type === "point") triangleEstimate += 720;
      if (layer.type === "box") triangleEstimate += 12;
      if (layer.type === "plane" && (!vector3(layer.normal)
        || layer.normal.every((value) => value === 0) || !finiteNumber(layer.constant, -1000, 1000))) {
        return { ok: false, error: "V2 plane is invalid" };
      }
      if (layer.type === "plane") triangleEstimate += 128;
      if (layer.type === "arrow" && (!point(layer.from) || !point(layer.to))) return { ok: false, error: "V2 arrow is invalid" };
      if (layer.type === "angle_arc" && (!finiteNumber(layer.cx, -10000, 10000)
        || !finiteNumber(layer.cy, -10000, 10000) || !finiteNumber(layer.r, 1, 2000)
        || !finiteNumber(layer.start_angle, -1080, 1080) || !finiteNumber(layer.end_angle, -1080, 1080)
        || typeof layer.clockwise !== "boolean" || !nonEmptyString(layer.label, 160))) {
        return { ok: false, error: "V2 angle arc is invalid" };
      }
      if (layer.type === "circle" && (!finiteNumber(layer.x, -10000, 10000) || !finiteNumber(layer.y, -10000, 10000) || !finiteNumber(layer.r, 0.1, 2000))) return { ok: false, error: "V2 circle is invalid" };
      if (layer.type === "rect" && (!finiteNumber(layer.x, -10000, 10000) || !finiteNumber(layer.y, -10000, 10000)
        || !finiteNumber(layer.width, 0.1, 2000) || !finiteNumber(layer.height, 0.1, 2000))) {
        return { ok: false, error: "V2 rectangle is invalid" };
      }
      if (layer.type === "text" && (!finiteNumber(layer.x, -10000, 10000) || !finiteNumber(layer.y, -10000, 10000) || !nonEmptyString(layer.text, 160))) return { ok: false, error: "V2 text is invalid" };
      if (["explicit_surface", "implicit_surface"].includes(layer.type)) {
        const relation = layer.relationship;
        if (!relation || Object.keys(relation).length !== 4 || relation.type !== "relationship" || relation.op !== "=") return { ok: false, error: "V2 relationship is invalid" };
        const expressionError = validateV2Expression(relation.left) || validateV2Expression(relation.right);
        if (expressionError) return { ok: false, error: expressionError };
        const expressionNodes = countV2ExpressionNodes(relation.left) + countV2ExpressionNodes(relation.right);
        if (expressionNodes > 160) return { ok: false, error: "V2 surface expression exceeds its AST budget" };
        const dimensions = layer.type === "explicit_surface" ? 2 : 3;
        if (!Array.isArray(layer.resolution) || layer.resolution.length !== dimensions
          || !layer.resolution.every((value) => Number.isInteger(value) && value >= 9 && value <= 65)
          || (dimensions === 3 && layer.resolution.reduce((a, b) => a * b, 1) > 32768)) {
          return { ok: false, error: "V2 surface resolution exceeds its budget" };
        }
        if (layer.type === "explicit_surface") {
          if (layer.resolution.reduce((a, b) => a * b, 1) * expressionNodes > MAX_STATIC_SURFACE_WORK) {
            return { ok: false, error: "V2 explicit surface work exceeds its budget" };
          }
          triangleEstimate += 2 * (layer.resolution[0] - 1) * (layer.resolution[1] - 1);
        } else {
          triangleEstimate += 1;
        }
        for (const axis of ["x", "y", "z"]) if (!numberPair(layer[`${axis}_domain`], -1000, 1000)) return { ok: false, error: "V2 surface domain is invalid" };
        if (layer.animation !== undefined && (!exactKeys(layer.animation, new Set(["mode", "duration"]))
          || !["orbit", "phase"].includes(layer.animation.mode) || !finiteNumber(layer.animation.duration, 2, 30))) {
          return { ok: false, error: "V2 surface animation is invalid" };
        }
      }
      if (layer.type === "parametric_surface" && ((validateV2Expression(layer.x_expression) || validateV2Expression(layer.y_expression) || validateV2Expression(layer.z_expression))
        || countV2ExpressionNodes(layer.x_expression) + countV2ExpressionNodes(layer.y_expression)
          + countV2ExpressionNodes(layer.z_expression) > 160
        || !numberPair(layer.u_domain, -100, 100) || !numberPair(layer.v_domain, -100, 100)
        || !Array.isArray(layer.resolution) || layer.resolution.length !== 2
        || !layer.resolution.every((value) => Number.isInteger(value) && value >= 9 && value <= 65)
        || layer.resolution.reduce((a, b) => a * b, 1) > 4096
        || (layer.animation !== undefined && (!exactKeys(layer.animation, new Set(["mode", "duration"]))
          || !["orbit", "phase"].includes(layer.animation.mode) || !finiteNumber(layer.animation.duration, 2, 30))))) {
        return { ok: false, error: "V2 parametric surface is invalid" };
      }
      if (layer.type === "parametric_surface") {
        triangleEstimate += 2 * (layer.resolution[0] - 1) * (layer.resolution[1] - 1);
      }
    }
    if (candidate.scene.layers.some((layer) => ["explicit_surface", "implicit_surface"].includes(layer.type))) {
      triangleEstimate += V2_SURFACE_LABEL_TRIANGLES;
    }
    if (candidate.family === "parametric_surface") triangleEstimate += V2_PARAMETRIC_MARKER_TRIANGLES;
    if (points > candidate.budget.max_points) return { ok: false, error: "V2 point budget exceeded" };
    if (triangleEstimate > candidate.budget.max_triangles) return { ok: false, error: "V2 triangle budget exceeded" };
    const bindable = {
      polyline: new Set(["translate_x", "translate_y", "scale"]),
      node: new Set(["translate_x", "translate_y", "scale"]),
      arrow: new Set(["translate_x", "translate_y", "scale"]),
      circle: bindingEffects,
      rect: new Set(["translate_x", "translate_y", "scale"]),
      particles: new Set(["translate_x", "translate_y", "scale"]),
      vector_field: new Set(["translate_x", "translate_y", "scale"]),
    };
    const rendererBindable = {
      svg: new Set(Object.keys(bindable)),
      canvas: new Set(["polyline", "particles", "vector_field"]),
      three: new Set(),
    };
    for (const control of candidate.controls.filter((item) => item.binding)) {
      const matches = candidate.scene.layers.filter((layer) => layer.label === control.binding.target_label);
      if (matches.length !== 1 || !rendererBindable[candidate.renderer].has(matches[0].type)
        || !bindable[matches[0].type]?.has(control.binding.effect)
        || (["scale", "radius"].includes(control.binding.effect) && control.min <= 0)) {
        return { ok: false, error: "V2 control binding target is invalid" };
      }
    }
    const transportLabels = new Map([
      ["play", "Play"], ["pause", "Pause"], ["restart", "Restart"],
    ]);
    const transportControls = candidate.controls.filter((control) => transportLabels.has(control.id));
    const hasAnimation = candidate.scene.animation !== undefined
      || candidate.scene.layers.some((layer) => layer.animation !== undefined);
    if (transportControls.length || hasAnimation) {
      const completeTransport = transportControls.length === transportLabels.size
        && new Set(transportControls.map((control) => control.id)).size === transportLabels.size;
      const validTransport = transportControls.every((control) => control.type === "button"
        && control.label.trim().toLocaleLowerCase() === transportLabels.get(control.id).toLocaleLowerCase());
      if (!hasAnimation || !completeTransport || !validTransport) {
        return { ok: false, error: "V2 animation requires canonical Play, Pause, and Restart buttons" };
      }
    }
    return { ok: true, spec: JSON.parse(encoded), error: "" };
  }

  function validateSpec(candidate) {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
      return { ok: false, error: "visualization must be a JSON object" };
    }
    let encoded;
    try {
      encoded = JSON.stringify(candidate);
    } catch {
      return { ok: false, error: "visualization cannot be serialized" };
    }
    if (new TextEncoder().encode(encoded).length > MAX_SPEC_CHARS) return { ok: false, error: "visualization is too large" };
    if (candidate.version === 2) return validateV2Spec(candidate, encoded);
    const treeError = validateTree(candidate);
    if (treeError) return { ok: false, error: treeError };
    if (candidate.version !== 1) return { ok: false, error: "unsupported visualization version" };
    if (!LIBRARIES.has(candidate.library)) return { ok: false, error: "unsupported library" };
    if (!KINDS[candidate.library].has(candidate.kind)) {
      return { ok: false, error: "renderer and kind are incompatible" };
    }
    if (!nonEmptyString(candidate.title, 120)) return { ok: false, error: "title is required" };
    if (!nonEmptyString(candidate.aria_label, 300)) {
      return { ok: false, error: "aria_label is required" };
    }
    if (!Number.isInteger(candidate.height) || candidate.height < 240 || candidate.height > 600) {
      return { ok: false, error: "height must be an integer from 240 to 600" };
    }
    for (const label of [candidate.x_label, candidate.y_label, candidate.z_label]) {
      if (label !== undefined && !nonEmptyString(label, 80)) {
        return { ok: false, error: "axis label is invalid" };
      }
    }
    const error = candidate.library === "d3"
      ? validateD3(candidate)
      : candidate.library === "three"
        ? validateThree(candidate)
        : validateAnimation(candidate);
    if (error) return { ok: false, error };
    // Clone through JSON so getters/prototypes supplied by another script cannot cross the frame
    // boundary even when validateSpec is called directly rather than through JSON.parse.
    return { ok: true, spec: JSON.parse(encoded), error: "" };
  }

  function extract(text) {
    const source = typeof text === "string" ? text : "";
    const blocks = (pattern) => Array.from(source.matchAll(pattern)).flatMap((opening) => {
      const bodyStart = opening.index + opening[0].length;
      const closing = new RegExp("\\r?\\n" + opening[2] + "```[\\t ]*(?=\\r?\\n|$)")
        .exec(source.slice(bodyStart));
      if (!closing) return [];
      return [{
        start: opening.index,
        end: bodyStart + closing.index + closing[0].length,
        leading: opening[1],
        body: source.slice(bodyStart, bodyStart + closing.index),
      }];
    });
    // Scan every opener independently. An unterminated legacy opener must not consume a later
    // server-owned opener and hide its otherwise-valid artifact.
    const matches = [...blocks(FENCE_START), ...blocks(MARKED_JSON_START)]
      .sort((left, right) => left.start - right.start);
    const accepted = [];
    for (const match of matches) {
      const body = match.body;
      if (body.length > MAX_SPEC_CHARS) continue;
      let candidate;
      try {
        candidate = JSON.parse(body);
      } catch {
        continue;
      }
      const result = validateSpec(candidate);
      if (result.ok) accepted.push({
        start: match.start,
        end: match.end,
        leading: match.leading,
        spec: result.spec,
      });
    }
    let cursor = 0;
    const prose = [];
    for (const match of accepted) {
      prose.push(source.slice(cursor, match.start), match.leading);
      cursor = match.end;
    }
    prose.push(source.slice(cursor));
    const markdown = prose.join("").replace(/\n{3,}/g, "\n\n").trim();
    const visualizations = accepted.length ? [accepted.at(-1).spec] : [];
    return { markdown, visualizations };
  }

  function encodeSpec(spec) {
    const bytes = new TextEncoder().encode(JSON.stringify(spec));
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function decodeSpec(encoded) {
    const maxEncodedChars = Math.ceil((MAX_SPEC_CHARS * 4) / 3) + 16;
    if (typeof encoded !== "string" || encoded.length > maxEncodedChars) {
      throw new Error("visualization fragment is too large");
    }
    const normalized = String(encoded || "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  function resolvedTheme() {
    return global.document?.documentElement?.dataset.theme === "dark" ? "dark" : "light";
  }

  function frameUrl(spec, theme = resolvedTheme()) {
    const safeTheme = theme === "dark" ? "dark" : "light";
    return `viz-frame.html?theme=${safeTheme}#${encodeSpec(spec)}`;
  }

  function cleanup(container) {
    if (!container || typeof container.querySelectorAll !== "function") return;
    container.querySelectorAll(".muta-visualization-frame").forEach((frame) => {
      if (typeof frame._mutaVizCleanup === "function") frame._mutaVizCleanup();
    });
  }

  const ACTIVE_FRAME_LIMIT = 4;
  const loadedFrames = new Set();

  function markFrameLoaded(frame) {
    loadedFrames.delete(frame);
    loadedFrames.add(frame);
    if (loadedFrames.size <= ACTIVE_FRAME_LIMIT) return;
    for (const candidate of loadedFrames) {
      if (candidate === frame) continue;
      candidate._mutaVizForceUnload?.();
      if (loadedFrames.size <= ACTIVE_FRAME_LIMIT) break;
    }
  }

  function renderAll(container, specs) {
    if (!container || !global.document) return;
    cleanup(container);
    container.querySelectorAll(".muta-visualization").forEach((node) => {
      node.remove();
    });
    for (const spec of specs || []) {
      const figure = document.createElement("figure");
      figure.className = "muta-visualization";
      figure.dataset.library = spec.library;
      const heading = document.createElement("figcaption");
      const title = document.createElement("strong");
      title.dir = "auto";
      title.textContent = spec.title;
      const badge = document.createElement("span");
      badge.textContent = spec.library === "three" ? "3D" : spec.library;
      heading.append(title, badge);
      const frame = document.createElement("iframe");
      frame.className = "muta-visualization-frame";
      // Safari/WebKit gives a script-enabled opaque-origin frame a blank WebGL/SVG surface.
      // The frame is a same-origin trusted renderer: model output crosses only as validated JSON,
      // its CSP disables network/form/child content, and it contains no eval or innerHTML sink.
      frame.sandbox = "allow-scripts allow-same-origin";
      frame.referrerPolicy = "no-referrer";
      frame.title = spec.aria_label;
      frame.style.height = `${spec.height}px`;
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "muta-visualization-restore";
      const restoreLabel = global.MutaI18n?.t?.("visualization.replay") || spec.title;
      restore.textContent = restoreLabel;
      restore.setAttribute("aria-label", [restoreLabel, spec.title].join(": "));
      restore.hidden = true;
      let source = frameUrl(spec);
      let loaded = true;
      let evictedForCapacity = false;
      let unloadTimer = 0;
      // Assign the local frame immediately. Tauri's WebKit can omit intersection callbacks for
      // sandboxed iframes inside the chat scroller; visibility observation is an optimization,
      // never a prerequisite for rendering the learner's visual.
      frame.src = source;
      frame._mutaVizIntersecting = true;
      const loadFrame = (manual = false) => {
        if (unloadTimer) { clearTimeout(unloadTimer); unloadTimer = 0; }
        if (evictedForCapacity && !manual) return;
        if (!loaded) { loaded = true; evictedForCapacity = false; restore.hidden = true; frame.hidden = false; frame.src = source; }
        markFrameLoaded(frame);
      };
      const unloadFrame = (force = false) => {
        if (!loaded || (!force && frame._mutaVizIntersecting)) return;
        loaded = false;
        evictedForCapacity = force;
        loadedFrames.delete(frame);
        frame.src = "about:blank";
        if (force) { frame.hidden = true; restore.hidden = false; }
      };
      frame._mutaVizUnload = unloadFrame;
      frame._mutaVizForceUnload = () => unloadFrame(true);
      restore.addEventListener("click", () => loadFrame(true));
      markFrameLoaded(frame);
      const refreshTheme = () => {
        const nextSource = frameUrl(spec);
        if (source === nextSource) return;
        source = nextSource;
        if (loaded) frame.src = source;
      };
      document.addEventListener("muta:themechange", refreshTheme);
      if (typeof global.IntersectionObserver === "function") {
        let intersecting = true;
        const sendVisibility = () => frame.contentWindow?.postMessage(
          { type: "muta-viz-visibility", visible: intersecting && !document.hidden },
          "*",
        );
        const observer = new IntersectionObserver((entries) => {
          intersecting = Boolean(entries[0]?.isIntersecting);
          frame._mutaVizIntersecting = intersecting;
          if (intersecting) loadFrame();
          else {
            evictedForCapacity = false;
            if (unloadTimer) clearTimeout(unloadTimer);
            unloadTimer = setTimeout(unloadFrame, 1200);
          }
          sendVisibility();
        }, { rootMargin: "160px 0px" });
        const onVisibility = () => sendVisibility();
        frame.addEventListener("load", sendVisibility);
        document.addEventListener("visibilitychange", onVisibility);
        observer.observe(frame);
        frame._mutaVizCleanup = () => {
          if (unloadTimer) clearTimeout(unloadTimer);
          frame._mutaVizIntersecting = false;
          unloadFrame();
          loadedFrames.delete(frame);
          observer.disconnect();
          document.removeEventListener("visibilitychange", onVisibility);
          document.removeEventListener("muta:themechange", refreshTheme);
        };
      } else {
        frame._mutaVizCleanup = () => {
          frame._mutaVizIntersecting = false;
          unloadFrame();
          loadedFrames.delete(frame);
          document.removeEventListener("muta:themechange", refreshTheme);
        };
      }
      figure.append(heading, frame, restore);
      container.appendChild(figure);
    }
  }

  const api = Object.freeze({
    MAX_SPEC_CHARS,
    cleanup,
    decodeSpec,
    encodeSpec,
    extract,
    evaluateSurfaceExpression,
    evaluateExpressionV2,
    frameUrl,
    renderAll,
    validateSpec,
  });
  global.MutaViz = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
