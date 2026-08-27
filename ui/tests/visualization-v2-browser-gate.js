"use strict";

(async () => {
  const status = document.getElementById("status");
  const progress = document.getElementById("progress");
  const host = document.getElementById("frame-host");
  const output = document.getElementById("result");
  const parameters = new URLSearchParams(location.search);
  const theme = parameters.get("theme") === "dark" ? "dark" : "light";
  const limit = Math.max(1, Math.min(200, Number(parameters.get("limit") || 200)));
  const caseId = parameters.get("case");
  const report = parameters.get("report") === "1";
  const debug = parameters.get("debug") === "1";
  const holdout = parameters.get("holdout") === "1";
  const fixtureName = holdout
    ? "visualization-v2-user-holdout.json"
    : parameters.get("general") === "1"
    ? "visualization-v2-general-math.json"
    : parameters.get("followup") === "1" ? "visualization-v2-followups.json" : "visualization-v2-specs.json";
  const fixture = await fetch(`fixtures/${fixtureName}?v=${encodeURIComponent(parameters.get("cache") || "current")}`).then((response) => {
    if (!response.ok) throw new Error(`fixture request failed: ${response.status}`);
    return response.json();
  });
  const selected = caseId ? fixture.cases.filter((item) => item.id === caseId) : fixture.cases;
  const cases = selected.slice(0, limit);
  if (!cases.length) throw new Error(`unknown visualization case: ${caseId}`);
  progress.max = cases.length;
  const results = [];
  const errors = [];
  window.addEventListener("error", (event) => errors.push(String(event.message || event.error || "page error")));
  window.addEventListener("unhandledrejection", (event) => errors.push(String(event.reason || "unhandled rejection")));

  const encode = (spec) => {
    const bytes = new TextEncoder().encode(JSON.stringify(spec));
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
  };

  const semanticControlOutcome = (spec, evidence) => {
    const values = evidence?.control_values || {};
    const description = String(evidence?.state_description || "");
    const number = (id) => Number(values[id]);
    if (spec.family === "ideal_gas") {
      return ["pressure", "volume", "temperature"].every((id) => Number.isFinite(number(id)))
        && Math.abs(number("pressure") * number("volume") - number("temperature")) < 0.025;
    }
    if (spec.family === "triangle_angles") {
      return ["vertex_a", "vertex_b", "vertex_c"].every((id) => Number.isFinite(number(id)))
        && Math.abs(number("vertex_a") + number("vertex_b") + number("vertex_c") - 180) < 0.01;
    }
    if (spec.family === "vector_field") return description.includes("divergence ∇·F=0") && description.includes("curl");
    if (spec.family === "hash_table") {
      const key = Math.round(number("key")); const bucket = ((key % 5) + 5) % 5;
      return Number.isFinite(key) && description.includes(`bucket ${bucket}`) && description.includes(String(values.operation));
    }
    if (spec.family === "kalman_filter") {
      const match = description.match(/P⁻=([0-9]+(?:\.[0-9]+)?).*contracted P=([0-9]+(?:\.[0-9]+)?)/);
      return Boolean(match && Number(match[2]) < Number(match[1]));
    }
    if (spec.family === "decision_boundary") {
      const match = description.match(/fell from ([0-9.]+) to ([0-9.]+)/);
      return Boolean(match && Number(match[2]) < Number(match[1]) && description.includes("p=0.5"));
    }
    if (spec.family === "stack_queue" && values.operation === "remove") {
      return description.includes("newest-first") && description.includes("oldest-first");
    }
    if (spec.family === "neural_network") {
      const hasThird = spec.scene.layers.some((layer) => layer.type === "node" && layer.id === "h3");
      return description.includes("h₁=ReLU") && description.includes("sigmoid output")
        && (!hasThird || description.includes("h₃="));
    }
    if (spec.family === "spring_mass" && Object.hasOwn(values, "displacement")) {
      return description.includes("F=−kx=") && description.includes("opposite the displacement");
    }
    if (spec.family === "gradient_linked") return description.includes("both views") && description.includes("∇f=");
    if (spec.family === "gradient_descent") {
      const match = description.match(/loss x²\+2y²=([0-9.]+)/);
      return Boolean(match && Number.isFinite(Number(match[1])) && description.includes("both views"));
    }
    if (spec.family === "robot_localization") {
      const match = description.match(/position error ([0-9]+(?:\.[0-9]+)?)/);
      return Boolean(match && Number.isFinite(Number(match[1])) && description.includes("fused estimate"));
    }
    if (spec.family === "robot_forward_kinematics") return description.includes("end effector") && description.includes("cumulative joint angles");
    if (spec.family === "vector_field_3d") return description.includes("F=(−y,x,z)=") && description.includes("selected arrow matches");
    if (spec.family === "lorenz_attractor") return description.includes("500 samples") && description.includes("both lobes");
    if (spec.family === "electromagnetic_wave") return description.includes("E ⟂ B") && description.includes("k=E×B");
    if (spec.family === "binary_search") return /compare|found|absent|exhausted/.test(description);
    if (spec.family === "graph_traversal") return description.includes(String(values.algorithm || "").toUpperCase()) && description.includes(`step ${Math.round(number("step"))}`);
    if (spec.family === "standing_wave") return description.includes(`${Math.round(number("harmonic")) + 1} nodes`);
    if (spec.family === "nyquist") return description.includes("winding number") && /stable|unstable/.test(description);
    if (spec.family === "beam_bending") return description.includes("reactions sum") && description.includes("M(0)=M(L)=0");
    return true;
  };

  for (const [index, item] of cases.entries()) {
    status.textContent = `Rendering ${index + 1}/${cases.length}: ${item.id}`;
    const frame = document.createElement("iframe");
    frame.title = `QA render ${item.id}`;
    frame.sandbox = "allow-scripts allow-same-origin";
    frame.src = `../viz-frame.html?theme=${theme}#${encode(item.spec)}`;
    const started = performance.now();
    let messageEvidence = null;
    const receive = (event) => {
      if (event.source === frame.contentWindow && event.data?.type === "muta-viz-evidence") {
        messageEvidence = event.data.evidence;
      }
    };
    window.addEventListener("message", receive);
    host.replaceChildren(frame);
    await new Promise((resolve) => frame.addEventListener("load", resolve, { once: true }));
    const deadline = performance.now() + (item.spec.renderer === "three" ? 5000 : 2500);
    let evidence = null;
    while (performance.now() < deadline) {
      const encodedEvidence = frame.contentDocument?.getElementById("viz-stage")?.dataset.vizEvidence;
      if (encodedEvidence) {
        evidence = JSON.parse(encodedEvidence);
        break;
      }
      if (messageEvidence) {
        evidence = messageEvidence;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    const frameDocument = frame.contentDocument;
    const stage = frameDocument?.getElementById("viz-stage");
    const error = frameDocument?.getElementById("viz-error");
    // Exercise numeric/step inputs before selectors. Some selectors deliberately
    // change which numeric inputs are meaningful (for example heap insert value
    // versus extract-min), so DOM order would otherwise test an input only after
    // a previous control had disabled its semantic branch.
    const controls = [...(frameDocument?.querySelectorAll(".viz-v2-control input, .viz-v2-control select, .viz-v2-control button") || [])]
      .sort((left, right) => {
        const rank = (control) => control.tagName === "BUTTON" ? 2 : control.tagName === "SELECT" ? 1 : 0;
        return rank(left) - rank(right);
      });
    const canvas = frameDocument?.querySelector("canvas");
    const svg = frameDocument?.querySelector("svg");
    const visualPrimitiveCount = svg?.querySelectorAll("path,line,circle,rect,text").length || 0;
    const overflow = Boolean(stage && (stage.scrollWidth > stage.clientWidth + 1 || stage.scrollHeight > stage.clientHeight + 1));
    const namedControls = controls.every((control) => Boolean(control.getAttribute("aria-label")));
    const accessibleCanvas = !canvas || (canvas.getAttribute("role") === "img" && Boolean(canvas.getAttribute("aria-label")));
    const interactionResults = [];
    for (const control of controls) {
      const beforeInteraction = evidence;
      if (control.tagName === "SELECT") {
        control.selectedIndex = (control.selectedIndex + 1) % control.options.length;
        control.dispatchEvent(new frame.contentWindow.Event("input", { bubbles: true }));
      } else if (control.tagName === "BUTTON") {
        control.click();
      } else {
        const minimum = Number(control.min); const maximum = Number(control.max); const current = Number(control.value);
        const step = Math.max(Number(control.step) || 0, Number.EPSILON);
        let next = minimum + Math.round((0.73 * (maximum - minimum)) / step) * step;
        if (Math.abs(next - current) < step / 2) next = current + step <= maximum ? current + step : current - step;
        control.value = String(next);
        control.dispatchEvent(new frame.contentWindow.Event("input", { bubbles: true }));
      }
      const transportDelay = ["viz-v2-play", "viz-v2-restart"].includes(control.id) ? 80 : 20;
      await new Promise((resolve) => setTimeout(resolve, item.spec.renderer === "three" ? 90 : transportDelay));
      const afterEncoded = stage?.dataset.vizEvidence;
      const afterInteraction = afterEncoded ? JSON.parse(afterEncoded) : evidence;
      const stateChanged = Boolean(afterInteraction?.state_description && afterInteraction.state_description !== beforeInteraction?.state_description);
      const geometryChanged = Boolean(
        afterInteraction?.geometry_signature !== undefined
        && afterInteraction.geometry_signature !== beforeInteraction?.geometry_signature,
      );
      const visualStateChanged = Boolean(
        afterInteraction?.visual_state_signature !== undefined
        && afterInteraction.visual_state_signature !== beforeInteraction?.visual_state_signature,
      );
      const controlId = control.id.replace(/^viz-v2-/, "");
      const transport = ["play", "pause", "restart"].includes(controlId);
      const animationChanged = Boolean(
        afterInteraction?.animation_state !== beforeInteraction?.animation_state
        || afterInteraction?.animation_progress !== beforeInteraction?.animation_progress,
      );
      const revisionChanged = afterInteraction?.control_revision > (beforeInteraction?.control_revision || 0);
      const semanticOutcome = semanticControlOutcome(item.spec, afterInteraction);
      const passed = transport
        ? Boolean(revisionChanged && animationChanged && semanticOutcome)
        : Boolean(revisionChanged && stateChanged && semanticOutcome && (geometryChanged || visualStateChanged));
      interactionResults.push({ id: controlId, passed, revision_changed: revisionChanged, state_changed: stateChanged, semantic_outcome: semanticOutcome, geometry_changed: geometryChanged, visual_state_changed: visualStateChanged, animation_changed: animationChanged, transport });
      evidence = afterInteraction;
    }
    let visibleSemanticGeometry = { passed: true };
    if (item.spec.family === "double_slit") {
      const upperPath = frameDocument?.querySelector('[aria-label="upper-slit path"] path');
      const lowerPath = frameDocument?.querySelector('[aria-label="lower-slit path"] path');
      const screenPath = frameDocument?.querySelector('[aria-label="screen"] path');
      const endpoint = (path) => path?.getPointAtLength(path.getTotalLength());
      const upperEnd = endpoint(upperPath); const lowerEnd = endpoint(lowerPath);
      const screenStart = screenPath?.getPointAtLength(0);
      const screenEnd = endpoint(screenPath);
      const joined = Boolean(
        upperEnd && lowerEnd && screenStart && screenEnd
        && Math.abs(upperEnd.x - screenStart.x) < 0.5
        && Math.abs(lowerEnd.x - screenStart.x) < 0.5
        && Math.min(screenStart.y, screenEnd.y) <= upperEnd.y
        && upperEnd.y <= Math.max(screenStart.y, screenEnd.y),
      );
      visibleSemanticGeometry = {
        passed: joined,
        ray_endpoint_x: upperEnd?.x,
        screen_x: screenStart?.x,
      };
    }
    if (item.spec.family === "robot_arm") {
      const targetX = frameDocument?.getElementById("viz-v2-target_x");
      const targetY = frameDocument?.getElementById("viz-v2-target_y");
      for (const control of [targetX, targetY]) {
        if (!control) continue;
        control.value = "0";
        control.dispatchEvent(new frame.contentWindow.Event("input", { bubbles: true }));
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
      const target = frameDocument?.querySelector('[aria-label="unreachable target ×"]');
      const fill = target?.querySelector("rect")?.getAttribute("fill");
      const latestEvidence = stage?.dataset.vizEvidence;
      if (latestEvidence) evidence = JSON.parse(latestEvidence);
      visibleSemanticGeometry = {
        passed: Boolean(target && fill === "red" && String(evidence?.state_description || "").includes("unreachable")),
        target_aria_label: target?.getAttribute("aria-label"),
        target_fill: fill,
      };
    }
    const interactionChanged = controls.length === 0 || interactionResults.every((result) => result.passed);
    const geometryChanged = controls.length === 0 || interactionResults.every((result) => result.transport || result.geometry_changed || result.visual_state_changed);
    const realGeometry = item.spec.renderer === "svg"
      ? visualPrimitiveCount > 2 && evidence?.primitive_count > 2
      : item.spec.renderer === "canvas"
        ? evidence?.nontransparent_samples > 10
        : evidence?.triangles > 0 || evidence?.draw_calls > 0;
    const rendered = Boolean(
      evidence?.rendered && realGeometry && !error?.offsetParent && !overflow
      && controls.length === item.spec.controls.length && namedControls && accessibleCanvas
      && interactionChanged && visibleSemanticGeometry.passed,
    );
    results.push({
      id: item.id,
      rendered,
      evidence,
      elapsed_ms: Number((performance.now() - started).toFixed(2)),
      viewport: { width: frame.clientWidth, height: frame.clientHeight },
      theme,
      controls: controls.length,
      named_controls: namedControls,
      accessible_canvas: accessibleCanvas,
      interaction_changed: interactionChanged,
      geometry_changed: geometryChanged,
      interaction_results: interactionResults,
      visible_semantic_geometry: visibleSemanticGeometry,
      visual_primitive_count: visualPrimitiveCount,
      overflow,
      errors: error?.offsetParent ? [error.textContent.trim(), stage?.dataset.vizError, error.title].filter(Boolean) : [],
    });
    window.removeEventListener("message", receive);
    if (!debug) {
      frame.src = "about:blank";
      frame.remove();
    }
    progress.value = index + 1;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  const payload = {
    schema_version: 1,
    count: results.length,
    summary: {
      passed: results.filter((result) => result.rendered).length,
      failed: results.filter((result) => !result.rendered).length,
      page_errors: errors,
    },
    cases: results,
  };
  output.textContent = JSON.stringify(payload);
  if (report && (holdout || limit === 200)) {
    const response = await fetch(holdout ? "/__holdout" : "/__results", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) errors.push(`result upload failed: ${response.status}`);
  }
  document.documentElement.dataset.complete = "true";
  document.documentElement.dataset.passed = String(payload.summary.passed);
  status.textContent = `Complete: ${payload.summary.passed}/${results.length} rendered`;
})();
