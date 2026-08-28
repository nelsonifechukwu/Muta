"use strict";

(async () => {
  const parameters = new URLSearchParams(location.search);
  const theme = parameters.get("theme") === "dark" ? "dark" : "light";
  const motion = parameters.get("motion") === "reduce" ? "reduce" : "auto";
  const targetWidth = Math.max(320, Math.min(980, Number(parameters.get("width") || 980)));
  const targetHeight = Math.max(320, Math.min(600, Number(parameters.get("height") || 480)));
  const status = document.getElementById("status");
  const host = document.getElementById("matrix");
  host.style.width = `${targetWidth}px`; host.style.maxWidth = "100%";
  const output = document.getElementById("result");
  const [corpus, followups] = await Promise.all([
    fetch("fixtures/visualization-v2-specs.json?v=matrix-4").then((response) => response.json()),
    fetch("fixtures/visualization-v2-followups.json?v=matrix-4").then((response) => response.json()),
  ]);
  const select = (id) => corpus.cases.find((item) => item.id === id);
  const cubicCurve = {
    id: "regression-z-x3",
    spec: {
      version: 2, library: "d3", renderer: "svg", kind: "scene2d", family: "explicit_curve",
      title: "Interactive 2D equation", aria_label: "Two-dimensional plot of z=x cubed with x and z axes.",
      text_fallback: "Two-dimensional plot of z=x cubed from x=-5 to x=5.", height: 420, controls: [],
      budget: { max_points: 4096, max_triangles: 1, max_fps: 30 },
      scene: { coordinate_system: "cartesian2d", layers: [
        { type: "axes", x_label: "x", y_label: "z", grid: true },
        { type: "polyline", label: "z=x^3", points: [[-5,-125],[-4,-64],[-3,-27],[-2,-8],[-1,-1],[0,0],[1,1],[2,8],[3,27],[4,64],[5,125]], color: "orange" },
      ] },
    },
  };
  const items = [select("stem-001"), select("stem-048"), select("math-062"), cubicCurve, ...followups.cases].filter(Boolean);
  const encode = (spec) => {
    const bytes = new TextEncoder().encode(JSON.stringify(spec)); let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
  };
  const errors = [];
  addEventListener("error", (event) => errors.push(String(event.message || event.error || "page error")));
  addEventListener("unhandledrejection", (event) => errors.push(String(event.reason || "unhandled rejection")));
  const records = [];
  for (const item of items) {
    const article = document.createElement("article"); const heading = document.createElement("h2");
    heading.textContent = item.id; const frame = document.createElement("iframe"); frame.title = `Matrix render ${item.id}`;
    frame.style.height = `${targetHeight}px`;
    frame.sandbox = "allow-scripts allow-same-origin"; frame.src = `../viz-frame.html?theme=${theme}&motion=${motion}#${encode(item.spec)}`;
    article.append(heading, frame); host.appendChild(article);
    await new Promise((resolve) => frame.addEventListener("load", resolve, { once: true }));
    const stage = frame.contentDocument.getElementById("viz-stage");
    const deadline = performance.now() + 5000; let evidence = null;
    while (performance.now() < deadline) {
      if (stage.dataset.vizEvidence) { evidence = JSON.parse(stage.dataset.vizEvidence); break; }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    records.push({ item, article, frame, stage, evidence });
  }
  const results = [];
  for (const record of records) {
    const { item, article, frame, stage } = record; const documentValue = frame.contentDocument;
    let evidence = record.evidence; const controls = [...documentValue.querySelectorAll(".viz-v2-control input,.viz-v2-control select,.viz-v2-control button,.viz-view-controls button")];
    controls[0]?.focus();
    const focusStyle = controls[0] ? frame.contentWindow.getComputedStyle(controls[0]) : null;
    const focusVisible = !controls[0] || Number.parseFloat(focusStyle.outlineWidth || "0") > 0 || Number.parseFloat(focusStyle.borderWidth || "0") > 0;
    let keyboardChanged = false; let pointerHandlerChanged = false;
    const canvas = documentValue.querySelector(".viz-v2-three canvas");
    const interactivePlot = documentValue.querySelector("svg.viz-v2-interactive-plot");
    if (interactivePlot) {
      const before = evidence?.visual_state_signature;
      interactivePlot.dispatchEvent(new frame.contentWindow.KeyboardEvent("keydown", { key: "+", bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 30)); evidence = JSON.parse(stage.dataset.vizEvidence); keyboardChanged = evidence.visual_state_signature !== before;
      const pointerBefore = evidence?.visual_state_signature;
      interactivePlot.dispatchEvent(new frame.contentWindow.PointerEvent("pointerdown", { pointerId: 21, pointerType: "touch", clientX: 80, clientY: 120, bubbles: true }));
      interactivePlot.dispatchEvent(new frame.contentWindow.PointerEvent("pointerdown", { pointerId: 22, pointerType: "touch", clientX: 160, clientY: 120, bubbles: true }));
      interactivePlot.dispatchEvent(new frame.contentWindow.PointerEvent("pointermove", { pointerId: 22, pointerType: "touch", clientX: 190, clientY: 120, bubbles: true, cancelable: true }));
      interactivePlot.dispatchEvent(new frame.contentWindow.PointerEvent("pointermove", { pointerId: 22, pointerType: "touch", clientX: 220, clientY: 120, bubbles: true, cancelable: true }));
      interactivePlot.dispatchEvent(new frame.contentWindow.PointerEvent("pointerup", { pointerId: 21, pointerType: "touch", clientX: 80, clientY: 120, bubbles: true }));
      interactivePlot.dispatchEvent(new frame.contentWindow.PointerEvent("pointerup", { pointerId: 22, pointerType: "touch", clientX: 220, clientY: 120, bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 30)); evidence = JSON.parse(stage.dataset.vizEvidence); pointerHandlerChanged = evidence.visual_state_signature !== pointerBefore;
    } else if (canvas) {
      const before = evidence?.geometry_signature;
      canvas.dispatchEvent(new frame.contentWindow.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 30)); evidence = JSON.parse(stage.dataset.vizEvidence); keyboardChanged = evidence.geometry_signature !== before;
      const pointerBefore = evidence.geometry_signature;
      canvas.dispatchEvent(new frame.contentWindow.PointerEvent("pointerdown", { pointerId: 7, clientX: 80, clientY: 80, bubbles: true }));
      canvas.dispatchEvent(new frame.contentWindow.PointerEvent("pointermove", { pointerId: 7, clientX: 120, clientY: 96, bubbles: true }));
      canvas.dispatchEvent(new frame.contentWindow.PointerEvent("pointerup", { pointerId: 7, clientX: 120, clientY: 96, bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 30)); evidence = JSON.parse(stage.dataset.vizEvidence); pointerHandlerChanged = evidence.geometry_signature !== pointerBefore;
    } else if (controls.length) {
      const control = controls.find((candidate) => candidate.tagName !== "BUTTON") || controls[0];
      const signatureChanged = (before, after) => before?.geometry_signature !== after?.geometry_signature
        || before?.visual_state_signature !== after?.visual_state_signature
        || before?.animation_state !== after?.animation_state;
      const keyboardBefore = evidence;
      control.focus();
      control.dispatchEvent(new frame.contentWindow.KeyboardEvent("keydown", { key: control.tagName === "BUTTON" ? " " : "ArrowRight", bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 40)); evidence = JSON.parse(stage.dataset.vizEvidence); keyboardChanged = signatureChanged(keyboardBefore, evidence);
      const touchBefore = evidence;
      const touchControl = control.tagName === "BUTTON" && controls[1] ? controls[1] : control;
      touchControl.dispatchEvent(new frame.contentWindow.PointerEvent("pointerdown", { pointerId: 11, pointerType: "touch", clientX: 12, clientY: 12, bubbles: true, cancelable: true }));
      touchControl.dispatchEvent(new frame.contentWindow.PointerEvent("pointerup", { pointerId: 11, pointerType: "touch", clientX: 24, clientY: 12, bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 40)); evidence = JSON.parse(stage.dataset.vizEvidence); pointerHandlerChanged = signatureChanged(touchBefore, evidence)
        || (motion === "reduce" && evidence.animation_progress === 1 && Boolean(touchControl.getAttribute("aria-label")));
    } else {
      keyboardChanged = true; pointerHandlerChanged = true;
    }
    article.style.width = "300px"; await new Promise((resolve) => setTimeout(resolve, 70));
    const responsive = stage.scrollWidth <= stage.clientWidth + 1 && stage.scrollHeight <= stage.clientHeight + 1;
    const controlWrappers = [...documentValue.querySelectorAll(".viz-v2-controls,.viz-view-controls")];
    const controlsFullyVisible = controlWrappers.every((wrapper) => wrapper.scrollWidth <= wrapper.clientWidth + 1);
    const controlBounds = controls.map((control) => {
      const bounds = control.getBoundingClientRect();
      return { id: control.id, width: bounds.width, height: bounds.height };
    });
    const touchTargetReady = controls.length === 0 || controlBounds.every((bounds) => (
      bounds.width >= 44 && bounds.height >= 44
    ));
    const nativeTouchReady = controls.length === 0 || controls.every((control) => (
      ["INPUT", "SELECT", "BUTTON"].includes(control.tagName) && Boolean(control.getAttribute("aria-label"))
    ));
    article.style.width = "";
    let hiddenPaused = true; let resumed = true;
    const play = documentValue.getElementById("viz-v2-play");
    if (play) {
      play.click(); await new Promise((resolve) => setTimeout(resolve, 120)); evidence = JSON.parse(stage.dataset.vizEvidence);
      frame.contentWindow.postMessage({ type: "muta-viz-visibility", visible: false }, location.origin);
      await new Promise((resolve) => setTimeout(resolve, 50)); evidence = JSON.parse(stage.dataset.vizEvidence);
      const hiddenProgress = evidence.animation_progress; await new Promise((resolve) => setTimeout(resolve, 150)); evidence = JSON.parse(stage.dataset.vizEvidence);
      hiddenPaused = Math.abs(evidence.animation_progress - hiddenProgress) < 1e-9;
      frame.contentWindow.postMessage({ type: "muta-viz-visibility", visible: true }, location.origin);
      await new Promise((resolve) => setTimeout(resolve, 120)); evidence = JSON.parse(stage.dataset.vizEvidence);
      resumed = motion === "reduce"
        ? evidence.state_description.includes("Reduced motion") || evidence.animation_progress === 1
        : evidence.animation_progress > hiddenProgress || evidence.animation_progress === 1;
      documentValue.getElementById("viz-v2-pause")?.click();
    }
    results.push({ id: item.id, renderer: item.spec.renderer, rendered: Boolean(evidence?.rendered), responsive, controls_fully_visible: controlsFullyVisible, focus_visible: focusVisible, keyboard_handler_changed: keyboardChanged, synthetic_pointer_handler_changed: pointerHandlerChanged, native_touch_ready: nativeTouchReady, touch_target_ready: touchTargetReady, control_bounds: controlBounds, hidden_paused: hiddenPaused, resumed, accessible_description: Boolean(documentValue.querySelector(".viz-v2-fallback")), overflow: !responsive || !controlsFullyVisible, evidence });
  }
  const pageHorizontalOverflow = document.documentElement.scrollWidth > innerWidth + 1;
  const payload = {
    schema_version: 1, count: results.length, theme,
    viewport: { width: innerWidth, height: innerHeight },
    reduced_motion: motion === "reduce" || matchMedia("(prefers-reduced-motion: reduce)").matches,
    target_container: { width: targetWidth, height: targetHeight },
    simultaneous_frames: records.length,
    used_js_heap_bytes: performance.memory?.usedJSHeapSize || null,
    page_errors: errors, page_horizontal_overflow: pageHorizontalOverflow, cases: results,
    // Programmatically dispatched events exercise the internal handlers only. Trusted
    // keyboard/pointer input is recorded separately by the browser-skill QA artifact.
    passed: errors.length === 0 && !pageHorizontalOverflow && results.every((item) => item.rendered && item.responsive && item.controls_fully_visible && item.focus_visible && item.keyboard_handler_changed && item.native_touch_ready && item.touch_target_ready && item.hidden_paused && item.resumed && item.accessible_description),
  };
  output.textContent = JSON.stringify(payload); document.documentElement.dataset.complete = "true";
  document.documentElement.dataset.passed = String(payload.passed); status.textContent = payload.passed ? `Complete: ${results.length}/${results.length} matrix checks passed` : "Matrix checks failed";
  if (parameters.get("report") === "1") {
    const response = await fetch("/__matrix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) status.textContent = `Matrix result upload failed: ${response.status}`;
  }
})();
