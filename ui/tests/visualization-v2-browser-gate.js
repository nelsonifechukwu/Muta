"use strict";

(async () => {
  const status = document.getElementById("status");
  const progress = document.getElementById("progress");
  const host = document.getElementById("frame-host");
  const output = document.getElementById("result");
  const parameters = new URLSearchParams(location.search);
  const theme = parameters.get("theme") === "dark" ? "dark" : "light";
  const motion = parameters.get("motion") === "reduce" ? "reduce" : "auto";
  const targetWidth = Math.max(320, Math.min(760, Number(parameters.get("width") || 760)));
  document.querySelector("main").style.width = `${targetWidth}px`;
  document.querySelector("main").style.maxWidth = "100%";
  const limit = Math.max(1, Math.min(200, Number(parameters.get("limit") || 200)));
  const caseId = parameters.get("case");
  const report = parameters.get("report") === "1";
  const debug = parameters.get("debug") === "1";
  const bearings = parameters.get("bearings") === "1";
  const holdout = parameters.get("holdout") === "1" || bearings;
  const fixtureName = parameters.get("binding") === "1"
    ? "visualization-v2-planner-binding.json"
    : bearings
    ? "visualization-v2-bearings-holdout.json"
    : holdout
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

  const verifyInertStringBoundary = async () => {
    const strings = {
      title: "<script>globalThis.__mutaVizSinkProbe=true</script>",
      aria: "개체 P(t)와 ऊँचाई h(t): Await the next stage.",
      fallback: "selector { color:red } <?php echo 1 ?> https://example.invalid/payload.js",
      firstNode: "δelta\n('x') <img src=x onerror=globalThis.__mutaVizSinkProbe=true>",
      secondNode: "Await f(x): 개체 P(t)는 시간에 따라 증가합니다.",
      link: "export{x}; new Function('return 1')",
      control: "Await P(t) <?php echo 1 ?>",
      polyline: "direction arrow Await f(x)",
    };
    const spec = {
      version: 2,
      library: "d3",
      renderer: "svg",
      kind: "scene2d",
      family: "semantic_composition",
      title: strings.title,
      aria_label: strings.aria,
      text_fallback: strings.fallback,
      height: 420,
      controls: [{
        id: "population",
        label: strings.control,
        type: "range",
        value: 1,
        min: 0.1,
        max: 2,
        step: 0.1,
        binding: { target_label: strings.firstNode, effect: "scale" },
      }],
      budget: { max_points: 512, max_triangles: 4096, max_fps: 20 },
      scene: {
        coordinate_system: "screen",
        layers: [
          { type: "node", id: "source", x: 140, y: 180, width: 180, height: 58, label: strings.firstNode, color: "green" },
          { type: "node", id: "target", x: 470, y: 180, width: 180, height: 58, label: strings.secondNode, color: "orange" },
          { type: "link", from: "source", to: "target", arrow: true, label: strings.link },
          { type: "polyline", label: strings.polyline, points: [[0, 0], [1, 1], [2, 0]], color: "teal" },
        ],
      },
    };
    const frame = document.createElement("iframe");
    frame.title = "Inert planner string boundary test";
    frame.sandbox = "allow-scripts allow-same-origin";
    frame.src = `../viz-frame.html?theme=${theme}&motion=${motion}#${encode(spec)}`;
    host.replaceChildren(frame);
    await new Promise((resolve) => frame.addEventListener("load", resolve, { once: true }));
    const frameDocument = frame.contentDocument;
    const stage = frameDocument?.getElementById("viz-stage");
    const deadline = performance.now() + 2500;
    while (stage && !stage.dataset.vizEvidence && performance.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    const visibleText = [...(stage?.querySelectorAll("text,.viz-v2-control-label,.viz-v2-fallback p") || [])]
      .map((node) => node.textContent);
    const eventOrResourceAttributes = [...(stage?.querySelectorAll("*") || [])].flatMap((node) => (
      [...node.attributes]
        .map((attribute) => ({ name: attribute.name.toLowerCase(), value: attribute.value }))
        .filter(({ name, value }) => (
          (name.startsWith("on") || ["href", "src", "srcdoc", "style"].includes(name))
          && Object.values(strings).some((sourceText) => value.includes(sourceText))
        ))
    ));
    const evidence = stage?.dataset.vizEvidence ? JSON.parse(stage.dataset.vizEvidence) : null;
    const errorElement = frameDocument?.getElementById("viz-error");
    const renderError = stage?.dataset.vizError
      || (errorElement && !errorElement.hidden ? errorElement.textContent.trim() : "");
    const descriptivePolyline = [...(stage?.querySelectorAll("g.viz-v2-layer") || [])]
      .find((node) => node.getAttribute("aria-label") === strings.polyline);
    const descriptiveBehaviorAttributes = descriptivePolyline
      ? [...(descriptivePolyline.querySelector("path")?.attributes || [])]
        .filter((attribute) => ["marker-start", "marker-mid", "marker-end"].includes(attribute.name) && attribute.value)
        .map((attribute) => ({ name: attribute.name, value: attribute.value }))
      : [{ name: "missing-polyline", value: "" }];
    const result = {
      passed: Boolean(
        evidence?.rendered
        && visibleText.includes(strings.firstNode)
        && visibleText.includes(strings.secondNode)
        && visibleText.includes(strings.link)
        && visibleText.includes(strings.control)
        && visibleText.includes(strings.fallback)
        && stage?.getAttribute("aria-label") === strings.aria
        && frameDocument?.querySelector(".viz-v2-controls")?.getAttribute("aria-label")?.startsWith(strings.title)
        && frameDocument?.getElementById("viz-v2-population")?.getAttribute("aria-label") === strings.control
        && !stage?.querySelector("script,style,iframe,img,object,embed,link,form")
        && eventOrResourceAttributes.length === 0
        && descriptiveBehaviorAttributes.length === 0
        && frame.contentWindow.__mutaVizSinkProbe === undefined
        && window.__mutaVizSinkProbe === undefined
      ),
      literal_text_fields: visibleText.filter((value) => Object.values(strings).includes(value)),
      event_or_resource_attributes: eventOrResourceAttributes,
      descriptive_behavior_attributes: descriptiveBehaviorAttributes,
      child_markup_sink: Boolean(stage?.querySelector("script,style,iframe,img,object,embed,link,form")),
      frame_global_mutated: frame.contentWindow.__mutaVizSinkProbe !== undefined,
      parent_global_mutated: window.__mutaVizSinkProbe !== undefined,
      render_error: renderError,
    };
    frame.src = "about:blank";
    frame.remove();
    return result;
  };

  const inertStringBoundary = await verifyInertStringBoundary();
  if (!inertStringBoundary.passed) errors.push("proposal-controlled strings crossed an inert text boundary");

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
    if (spec.family === "semantic_composition") {
      return !description.includes("a² + b² = c²") && !description.includes("Two-link IK")
        && !description.includes("Shortest ");
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
    frame.src = `../viz-frame.html?theme=${theme}&motion=${motion}#${encode(item.spec)}`;
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
    if (item.spec.family === "magnetic_field_wire") {
      const directionMarkers = [...(frameDocument?.querySelectorAll('.viz-v2-layer path[marker-end="url(#v2-arrow)"]') || [])];
      visibleSemanticGeometry = {
        passed: directionMarkers.length === 3,
        visible_direction_arrowheads: directionMarkers.length,
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
    if (item.spec.family === "bearing_navigation") {
      const northArrows = [...(frameDocument?.querySelectorAll('[aria-label^="N at "]') || [])];
      const angleArcs = [...(frameDocument?.querySelectorAll(".viz-v2-angle-arc") || [])];
      const clockwiseArcs = angleArcs.filter((arc) => arc.dataset.clockwise === "true");
      const arrowheads = [...(frameDocument?.querySelectorAll('[marker-end="url(#v2-arrow)"]') || [])];
      const textHeights = [...(frameDocument?.querySelectorAll(".viz-v2-layer text") || [])]
        .map((node) => node.getBoundingClientRect().height)
        .filter((height) => Number.isFinite(height) && height > 0);
      const minimumTextHeight = textHeights.length ? Math.min(...textHeights) : 0;
      const visibleText = frameDocument?.body?.textContent || "";
      visibleSemanticGeometry = {
        passed: northArrows.length >= 1 && angleArcs.length >= 1 && clockwiseArcs.length >= 1
          && arrowheads.length >= 3 && /\d{3}°/.test(visibleText) && minimumTextHeight >= 8.5,
        north_arrow_count: northArrows.length,
        angle_arc_count: angleArcs.length,
        clockwise_arc_count: clockwiseArcs.length,
        arrowhead_count: arrowheads.length,
        minimum_text_height_px: Math.round(minimumTextHeight * 100) / 100,
      };
    }
    const interactionChanged = controls.length === 0 || interactionResults.every((result) => result.passed);
    const geometryChanged = controls.length === 0 || interactionResults.every((result) => result.transport || result.geometry_changed || result.visual_state_changed);
    const realGeometry = item.spec.renderer === "svg"
      ? visualPrimitiveCount > 2 && evidence?.primitive_count > 2
      : item.spec.renderer === "canvas"
        ? evidence?.nontransparent_samples > 10
        : evidence?.triangles > 0 || evidence?.draw_calls > 0;
    const gpuBudgetRespected = item.spec.renderer !== "three"
      || (Number.isFinite(evidence?.gpu_triangles)
        && evidence.gpu_triangles <= item.spec.budget.max_triangles);
    const rendered = Boolean(
      evidence?.rendered && realGeometry && !error?.offsetParent && !overflow
      && controls.length === item.spec.controls.length && namedControls && accessibleCanvas
      && interactionChanged && visibleSemanticGeometry.passed && gpuBudgetRespected,
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
      gpu_budget_respected: gpuBudgetRespected,
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
  const renderedCount = results.filter((result) => result.rendered).length;
  const passedCount = inertStringBoundary.passed ? renderedCount : Math.max(0, renderedCount - 1);
  const payload = {
    schema_version: 1,
    count: results.length,
    target_container_width: targetWidth,
    theme,
    reduced_motion: motion === "reduce",
    summary: {
      passed: passedCount,
      failed: results.length - passedCount,
      page_errors: errors,
    },
    inert_string_boundary: inertStringBoundary,
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
