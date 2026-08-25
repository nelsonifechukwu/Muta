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
  const OBJECT_TYPES = new Set(["sphere", "box", "point", "line", "vector"]);
  const DIAGRAM_SHAPES = new Set(["circle", "rounded", "label"]);
  const BOND_TYPES = new Set(["single", "double", "triple", "dashed"]);
  const TRACK_FIELDS = new Set(["x", "y", "scale", "rotate", "opacity"]);
  const MAX_SPEC_CHARS = 48 * 1024;
  const MAX_TREE_NODES = 2500;
  const SAFE_ID = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
  const SAFE_COLOR = /^(?:#[0-9a-fA-F]{3,8}|(?:rgb|hsl)a?\([0-9.,%\s-]+\)|black|white|gray|grey|red|green|blue|orange|purple|teal|gold)$/;
  const FORBIDDEN_KEYS = new Set(["__proto__", "prototype", "constructor"]);
  const FENCE = /(^|\n)( {0,3})```muta-viz[\t ]*\r?\n([\s\S]*?)\r?\n\2```[\t ]*(?=\r?\n|$)/g;
  // Qwen3-0.6B sometimes obeys the semantic marker but normalizes the unfamiliar fence into
  // display text plus a JSON fence. It is equally safe after strict schema validation, and
  // accepting this one exact degradation makes the shipped smoke model useful.
  const MARKED_JSON_FENCE = /(^|\n)( {0,3})\$\$muta-viz\$\$[\t ]*\r?\n\2```json[\t ]*\r?\n([\s\S]*?)\r?\n\2```[\t ]*(?=\r?\n|$)/g;

  function finiteNumber(value, min = -1e6, max = 1e6) {
    return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
  }

  function nonEmptyString(value, max) {
    return typeof value === "string" && value.trim().length > 0 && value.length <= max;
  }

  function point(value) {
    return Array.isArray(value) && value.length === 2 && value.every((item) => finiteNumber(item));
  }

  function vector3(value) {
    return Array.isArray(value)
      && value.length === 3
      && value.every((item) => finiteNumber(item, -1000, 1000));
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
    for (const object of spec.objects) {
      if (!object || !OBJECT_TYPES.has(object.type)) return "unsupported 3D object";
      if (object.type === "vector") {
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
    if (encoded.length > MAX_SPEC_CHARS) return { ok: false, error: "visualization is too large" };
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
    for (const label of [candidate.x_label, candidate.y_label]) {
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
    const visualizations = [];
    const consume = (input, pattern) => input.replace(
      pattern,
      (whole, leading, _indent, body) => {
        if (visualizations.length >= 1 || body.length > MAX_SPEC_CHARS) return whole;
        let candidate;
        try {
          candidate = JSON.parse(body);
        } catch {
          return whole;
        }
        const result = validateSpec(candidate);
        if (!result.ok) return whole;
        visualizations.push(result.spec);
        return leading;
      },
    );
    const markdown = consume(consume(source, FENCE), MARKED_JSON_FENCE);
    return { markdown: markdown.replace(/\n{3,}/g, "\n\n").trim(), visualizations };
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
      let source = frameUrl(spec);
      // Assign the local frame immediately. Tauri's WebKit can omit intersection callbacks for
      // sandboxed iframes inside the chat scroller; visibility observation is an optimization,
      // never a prerequisite for rendering the learner's visual.
      frame.src = source;
      const refreshTheme = () => {
        const nextSource = frameUrl(spec);
        if (source === nextSource) return;
        source = nextSource;
        frame.src = source;
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
          sendVisibility();
        }, { rootMargin: "160px 0px" });
        const onVisibility = () => sendVisibility();
        frame.addEventListener("load", sendVisibility);
        document.addEventListener("visibilitychange", onVisibility);
        observer.observe(frame);
        frame._mutaVizCleanup = () => {
          observer.disconnect();
          document.removeEventListener("visibilitychange", onVisibility);
          document.removeEventListener("muta:themechange", refreshTheme);
        };
      } else {
        frame._mutaVizCleanup = () => {
          document.removeEventListener("muta:themechange", refreshTheme);
        };
      }
      figure.append(heading, frame);
      container.appendChild(figure);
    }
  }

  const api = Object.freeze({
    MAX_SPEC_CHARS,
    cleanup,
    decodeSpec,
    encodeSpec,
    extract,
    frameUrl,
    renderAll,
    validateSpec,
  });
  global.MutaViz = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
