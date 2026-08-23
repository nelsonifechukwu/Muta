/* Trusted adapters for declarative model output. Model-authored JavaScript never runs here. */
"use strict";

(() => {
  const stage = document.getElementById("viz-stage");
  const errorEl = document.getElementById("viz-error");
  const replay = document.getElementById("viz-replay");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let parentVisible = true;
  const activityListeners = new Set();

  function renderActive() {
    return parentVisible && !document.hidden;
  }

  function notifyActivity() {
    const active = renderActive();
    activityListeners.forEach((listener) => listener(active));
  }

  function onActivity(listener) {
    activityListeners.add(listener);
    return () => activityListeners.delete(listener);
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || event.data?.type !== "muta-viz-visibility") return;
    parentVisible = event.data.visible !== false;
    notifyActivity();
  });
  document.addEventListener("visibilitychange", notifyActivity);
  const libraryFiles = Object.freeze({
    d3: "vendor/viz/d3.v7.9.0.min.js",
    three: "vendor/viz/three.r160.min.js",
    gsap: "vendor/viz/gsap.v3.13.0.min.js",
    anime: "vendor/viz/anime.v3.2.2.min.js",
    motion: "vendor/viz/motion.v11.11.13.js",
  });
  function resolvedColor(name) {
    // Custom properties preserve `light-dark(...)` as tokens. Resolve through a real element
    // before passing a colour to Canvas/WebGL, whose APIs do not parse that CSS function.
    const probe = document.createElement("span");
    probe.className = `viz-color-probe viz-color-probe-${name}`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  }

  const palette = [1, 2, 3, 4, 5, 6].map((index) => resolvedColor(index));
  const neutral = resolvedColor("text");
  const border = resolvedColor("border");

  function fail(message) {
    stage.replaceChildren();
    errorEl.textContent = message || "This visualization could not be drawn.";
    errorEl.hidden = false;
    replay.hidden = true;
  }

  function loadLibrary(name) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = libraryFiles[name];
      script.onload = resolve;
      script.onerror = () => reject(new Error(`${name} is not available in this offline bundle`));
      document.head.appendChild(script);
    });
  }

  function color(value, index = 0) {
    return typeof value === "string" ? value : palette[index % palette.length];
  }

  function paddedDomain(values) {
    let [low, high] = d3.extent(values);
    if (low === high) {
      const delta = Math.abs(low || 1) * 0.15;
      low -= delta;
      high += delta;
    }
    const pad = (high - low) * 0.08;
    return [low - pad, high + pad];
  }

  function addAxisLabels(svg, width, height, margin, spec) {
    if (spec.x_label) {
      svg.append("text")
        .attr("x", margin.left + (width - margin.left - margin.right) / 2)
        .attr("y", height - 7)
        .attr("text-anchor", "middle")
        .text(spec.x_label);
    }
    if (spec.y_label) {
      svg.append("text")
        .attr("transform", `translate(15 ${margin.top + (height - margin.top - margin.bottom) / 2}) rotate(-90)`)
        .attr("text-anchor", "middle")
        .text(spec.y_label);
    }
  }

  function addLegend(labels) {
    if (!labels.length) return;
    const legend = document.createElement("div");
    legend.className = "viz-legend";
    labels.forEach((label, index) => {
      const item = document.createElement("span");
      const swatch = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      swatch.setAttribute("viewBox", "0 0 10 10");
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", "5");
      dot.setAttribute("cy", "5");
      dot.setAttribute("r", "5");
      dot.setAttribute("fill", color(label.color, index));
      swatch.appendChild(dot);
      item.append(swatch, document.createTextNode(label.label));
      legend.appendChild(item);
    });
    stage.appendChild(legend);
  }

  function renderCartesian(spec) {
    const draw = () => {
      stage.replaceChildren();
      const width = Math.max(320, stage.clientWidth || 720);
      const height = Math.max(240, stage.clientHeight || spec.height);
      const margin = { top: 34, right: 22, bottom: 48, left: 64 };
      const svg = d3.select(stage).append("svg").attr("viewBox", `0 0 ${width} ${height}`)
        .attr("role", "img").attr("aria-label", spec.aria_label);
      const all = spec.series.flatMap((series) => series.points);
      const x = d3.scaleLinear().domain(paddedDomain(all.map((item) => item[0])))
        .range([margin.left, width - margin.right]);
      const y = d3.scaleLinear().domain(paddedDomain(all.map((item) => item[1])))
        .nice().range([height - margin.bottom, margin.top]);
      svg.append("g").attr("class", "grid")
        .attr("transform", `translate(${margin.left},0)`)
        .call(d3.axisLeft(y).tickSize(-(width - margin.left - margin.right)).tickFormat(""));
      svg.append("g").attr("class", "axis")
        .attr("transform", `translate(0,${height - margin.bottom})`).call(d3.axisBottom(x).ticks(width < 440 ? 4 : 7));
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(y).ticks(6));
      addAxisLabels(svg, width, height, margin, spec);
      spec.series.forEach((series, index) => {
        const stroke = color(series.color, index);
        if (spec.kind === "line") {
          svg.append("path").datum(series.points).attr("fill", "none").attr("stroke", stroke)
            .attr("stroke-width", 2.3)
            .attr("d", d3.line().x((item) => x(item[0])).y((item) => y(item[1])));
        }
        const marks = svg.append("g").selectAll("circle").data(series.points).join("circle")
          .attr("cx", (item) => x(item[0])).attr("cy", (item) => y(item[1]))
          .attr("r", spec.kind === "scatter" ? 4.5 : 3.2).attr("fill", stroke);
        marks.append("title").text((item) => `${series.label}: (${item[0]}, ${item[1]})`);
      });
      addLegend(spec.series);
    };
    draw();
    new ResizeObserver(draw).observe(stage);
  }

  function renderBars(spec) {
    const draw = () => {
      stage.replaceChildren();
      const width = Math.max(320, stage.clientWidth || 720);
      const height = Math.max(240, stage.clientHeight || spec.height);
      const margin = { top: 28, right: 18, bottom: 58, left: 64 };
      const svg = d3.select(stage).append("svg").attr("viewBox", `0 0 ${width} ${height}`)
        .attr("role", "img").attr("aria-label", spec.aria_label);
      const values = spec.data.map((item) => item.value);
      const low = Math.min(0, ...values);
      const high = Math.max(0, ...values);
      const y = d3.scaleLinear().domain(paddedDomain([low, high])).nice()
        .range([height - margin.bottom, margin.top]);
      const x = d3.scaleBand().domain(spec.data.map((item) => item.label))
        .range([margin.left, width - margin.right]).padding(0.24);
      svg.append("g").attr("class", "grid").attr("transform", `translate(${margin.left},0)`)
        .call(d3.axisLeft(y).tickSize(-(width - margin.left - margin.right)).tickFormat(""));
      svg.append("g").attr("class", "axis").attr("transform", `translate(0,${y(0)})`)
        .call(d3.axisBottom(x)).selectAll("text")
        .attr("transform", width < 460 ? "rotate(-28)" : null)
        .attr("text-anchor", width < 460 ? "end" : "middle");
      svg.append("g").attr("class", "axis").attr("transform", `translate(${margin.left},0)`).call(d3.axisLeft(y).ticks(6));
      addAxisLabels(svg, width, height, margin, spec);
      const bars = svg.append("g").selectAll("rect").data(spec.data).join("rect")
        .attr("x", (item) => x(item.label)).attr("width", x.bandwidth())
        .attr("y", (item) => y(Math.max(0, item.value)))
        .attr("height", (item) => Math.abs(y(item.value) - y(0)))
        .attr("fill", (item, index) => color(item.color, index)).attr("rx", 3);
      bars.append("title").text((item) => `${item.label}: ${item.value}`);
    };
    draw();
    new ResizeObserver(draw).observe(stage);
  }

  function renderForce(spec) {
    stage.replaceChildren();
    const width = Math.max(320, stage.clientWidth || 720);
    const height = Math.max(240, stage.clientHeight || spec.height);
    const nodes = spec.nodes.map((node) => ({ ...node }));
    const links = spec.links.map((link) => ({ ...link }));
    const svg = d3.select(stage).append("svg").attr("viewBox", `0 0 ${width} ${height}`)
      .attr("role", "img").attr("aria-label", spec.aria_label);
    const link = svg.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", border).attr("stroke-width", 1.6);
    const node = svg.append("g").selectAll("g").data(nodes).join("g");
    node.append("circle").attr("r", 14).attr("fill", (item, index) => color(item.color, index));
    node.append("text").attr("x", 18).attr("y", 4).text((item) => item.label || item.id);
    node.append("title").text((item) => item.label || item.id);
    const drawTick = () => {
      link.attr("x1", (item) => item.source.x).attr("y1", (item) => item.source.y)
        .attr("x2", (item) => item.target.x).attr("y2", (item) => item.target.y);
      node.attr("transform", (item) => `translate(${item.x},${item.y})`);
    };
    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((item) => item.id).distance(82))
      .force("charge", d3.forceManyBody().strength(-240))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(28))
      .on("tick", drawTick);
    if (reducedMotion) {
      simulation.stop();
      simulation.tick(240);
      drawTick();
    } else {
      onActivity((active) => {
        if (!active) simulation.stop();
        else if (simulation.alpha() > simulation.alphaMin()) simulation.restart();
      });
      if (!renderActive()) simulation.stop();
    }
    if (!reducedMotion) {
      node.call(d3.drag()
        .on("start", (event) => { if (!event.active) simulation.alphaTarget(0.3).restart(); event.subject.fx = event.subject.x; event.subject.fy = event.subject.y; })
        .on("drag", (event) => { event.subject.fx = event.x; event.subject.fy = event.y; })
        .on("end", (event) => { if (!event.active) simulation.alphaTarget(0); event.subject.fx = null; event.subject.fy = null; }));
    }
  }

  function renderD3(spec) {
    if (spec.kind === "line" || spec.kind === "scatter") renderCartesian(spec);
    else if (spec.kind === "bar") renderBars(spec);
    else renderForce(spec);
  }

  function textSprite(label, fill) {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.font = "28px sans-serif";
    context.fillStyle = fill;
    context.fillText(String(label).slice(0, 40), 4, 38);
    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(2.6, 0.65, 1);
    return sprite;
  }

  function renderThree(spec) {
    stage.replaceChildren();
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.domElement.tabIndex = 0;
    renderer.domElement.setAttribute("role", "application");
    renderer.domElement.setAttribute("aria-label", `${spec.aria_label} Use arrow keys to rotate.`);
    stage.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
    camera.position.set(6, 5, 8);
    camera.lookAt(0, 0, 0);
    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const light = new THREE.DirectionalLight(0xffffff, 2.2);
    light.position.set(4, 7, 6);
    scene.add(light);
    const group = new THREE.Group();
    group.add(new THREE.AxesHelper(3));
    scene.add(group);
    const points = [];
    spec.objects.forEach((object, index) => {
      const shade = new THREE.Color(color(object.color, index));
      let mesh;
      if (object.type === "vector") {
        const from = new THREE.Vector3(...object.from);
        const delta = new THREE.Vector3(...object.to).sub(from);
        mesh = new THREE.ArrowHelper(delta.clone().normalize(), from, delta.length(), shade, 0.35, 0.2);
        points.push(from, new THREE.Vector3(...object.to));
      } else if (object.type === "line") {
        const geometry = new THREE.BufferGeometry().setFromPoints(object.points.map((item) => new THREE.Vector3(...item)));
        mesh = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: shade }));
        object.points.forEach((item) => points.push(new THREE.Vector3(...item)));
      } else {
        const size = object.size || (object.type === "point" ? 0.12 : 0.55);
        const geometry = object.type === "box"
          ? new THREE.BoxGeometry(size, size, size)
          : new THREE.SphereGeometry(size, 28, 18);
        mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: shade, roughness: 0.55 }));
        mesh.position.set(...(object.position || [0, 0, 0]));
        points.push(new THREE.Vector3(...(object.position || [0, 0, 0])));
      }
      group.add(mesh);
      if (object.label) {
        const label = textSprite(object.label, neutral);
        const anchor = object.type === "vector" ? object.to : (object.position || [0, 0, 0]);
        label.position.set(anchor[0] + 0.35, anchor[1] + 0.35 + (index % 3) * 0.38, anchor[2]);
        group.add(label);
      }
    });
    group.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(group);
    const center = bounds.getCenter(new THREE.Vector3());
    const extent = Math.max(3, bounds.getSize(new THREE.Vector3()).length());
    camera.near = Math.max(0.01, extent / 1000);
    camera.far = Math.max(100, extent * 12);
    camera.position.copy(center).add(new THREE.Vector3(1.8, 1.4, 2.2).normalize().multiplyScalar(extent * 2.2));
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    let dragging = false;
    let previous = null;
    renderer.domElement.addEventListener("pointerdown", (event) => { dragging = true; previous = [event.clientX, event.clientY]; renderer.domElement.setPointerCapture(event.pointerId); });
    renderer.domElement.addEventListener("pointermove", (event) => {
      if (!dragging || !previous) return;
      group.rotation.y += (event.clientX - previous[0]) * 0.009;
      group.rotation.x += (event.clientY - previous[1]) * 0.009;
      previous = [event.clientX, event.clientY];
      renderer.render(scene, camera);
    });
    renderer.domElement.addEventListener("pointerup", () => { dragging = false; previous = null; });
    renderer.domElement.addEventListener("keydown", (event) => {
      const directions = { ArrowLeft: [-0.12, 0], ArrowRight: [0.12, 0], ArrowUp: [0, -0.12], ArrowDown: [0, 0.12] };
      const change = directions[event.key];
      if (!change) return;
      event.preventDefault();
      group.rotation.y += change[0];
      group.rotation.x += change[1];
      renderer.render(scene, camera);
    });
    const hint = document.createElement("span");
    hint.className = "viz-3d-hint";
    hint.textContent = "drag to rotate";
    stage.appendChild(hint);
    const resize = () => {
      const width = Math.max(1, stage.clientWidth);
      const height = Math.max(1, stage.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };
    resize();
    new ResizeObserver(resize).observe(stage);
    // A static scene costs nothing while the learner reads. Pointer, keyboard, and resize
    // handlers render on demand; perpetual auto-spin would heat the scored CPU package forever.
    onActivity((active) => { if (active) renderer.render(scene, camera); });
    window.addEventListener("beforeunload", () => {
      renderer.dispose();
    }, { once: true });
  }

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgElement(name, attributes = {}) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  function buildAnimationElement(element, index) {
    const group = svgElement("g", { "data-element-id": element.id });
    let shape;
    const fill = color(element.color, index);
    if (element.type === "circle") {
      shape = svgElement("circle", { cx: 0, cy: 0, r: element.r ?? 12, fill });
    } else if (element.type === "rect") {
      shape = svgElement("rect", { x: -(element.width ?? 60) / 2, y: -(element.height ?? 38) / 2, width: element.width ?? 60, height: element.height ?? 38, rx: 5, fill });
    } else if (element.type === "text") {
      shape = svgElement("text", { x: 0, y: 4, "text-anchor": "middle", fill });
      shape.textContent = element.text || element.label || element.id;
    } else {
      shape = svgElement("line", { x1: element.x1 ?? 0, y1: element.y1 ?? 0, x2: element.x2 ?? 80, y2: element.y2 ?? 0, stroke: fill, "stroke-width": element.stroke_width ?? 3, "stroke-linecap": "round" });
      if (element.type === "arrow") shape.setAttribute("marker-end", "url(#arrow-head)");
    }
    group.appendChild(shape);
    const base = { x: element.x ?? 0, y: element.y ?? 0, scale: 1, rotate: 0, opacity: 1 };
    return { group, base };
  }

  function applyState(node, state) {
    node.setAttribute(
      "transform",
      `translate(${state.x} ${state.y}) rotate(${state.rotate}) scale(${state.scale})`,
    );
    node.setAttribute("opacity", String(state.opacity));
  }

  function runAnimationTrack(library, node, base, track, onFinished) {
    const from = { ...base, ...(track.from || {}) };
    const to = { ...from, ...track.to };
    applyState(node, reducedMotion ? to : from);
    if (reducedMotion) return null;
    const update = (state) => applyState(node, state);
    if (library === "gsap") {
      const state = { ...from };
      return gsap.to(state, { ...to, duration: track.duration, delay: track.delay || 0, repeat: track.repeat || 0, yoyo: track.direction === "alternate", ease: "sine.inOut", onUpdate: () => update(state), onComplete: onFinished, onInterrupt: onFinished });
    }
    if (library === "anime") {
      const state = { ...from };
      return anime({ targets: state, ...to, duration: track.duration * 1000, delay: (track.delay || 0) * 1000, loop: (track.repeat || 0) + 1, direction: track.direction === "alternate" ? "alternate" : "normal", easing: "easeInOutSine", update: () => update(state), complete: onFinished });
    }
    const controls = Motion.animate(0, 1, {
      duration: track.duration,
      delay: track.delay || 0,
      repeat: track.repeat || 0,
      repeatType: track.direction === "alternate" ? "reverse" : "loop",
      ease: "easeInOut",
      onUpdate: (progress) => {
        const state = {};
        Object.keys(from).forEach((key) => { state[key] = from[key] + (to[key] - from[key]) * progress; });
        update(state);
      },
    });
    if (typeof controls.then === "function") controls.then(onFinished, onFinished);
    return controls;
  }

  function renderAnimation(spec) {
    stage.replaceChildren();
    const height = Math.max(240, spec.height);
    const svg = svgElement("svg", { viewBox: `0 0 720 ${height}`, preserveAspectRatio: "xMidYMid meet" });
    const defs = svgElement("defs");
    const marker = svgElement("marker", { id: "arrow-head", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
    marker.appendChild(svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: neutral }));
    defs.appendChild(marker);
    svg.appendChild(defs);
    const records = new Map();
    spec.elements.forEach((element, index) => {
      const record = buildAnimationElement(element, index);
      // Elements without a track are still part of the explanation (labels, axes, or a fixed
      // first vector). Put every element at its declared base position before animated tracks
      // selectively override their targets; otherwise static content piles up at SVG (0, 0).
      applyState(record.group, record.base);
      records.set(element.id, record);
      svg.appendChild(record.group);
    });
    stage.appendChild(svg);
    const controls = new Set();
    const stopControl = (control) => {
      if (!control) return;
      if (typeof control.kill === "function") control.kill();
      else if (typeof control.stop === "function") control.stop();
      else if (typeof control.cancel === "function") control.cancel();
      else if (typeof control.pause === "function") control.pause();
    };
    const stopAll = () => {
      [...controls].forEach(stopControl);
      controls.clear();
    };
    const play = () => {
      stopAll();
      spec.tracks.forEach((track) => {
        const record = records.get(track.target);
        let control = null;
        const finished = () => controls.delete(control);
        control = runAnimationTrack(spec.library, record.group, record.base, track, finished);
        if (control) controls.add(control);
      });
    };
    if (!reducedMotion) {
      replay.hidden = false;
      replay.onclick = play;
    }
    const syncControls = (active) => {
      controls.forEach((control) => {
        if (!active && typeof control.pause === "function") control.pause();
        else if (active && typeof control.resume === "function") control.resume();
        else if (active && typeof control.play === "function") control.play();
      });
    };
    onActivity(syncControls);
    window.addEventListener("beforeunload", stopAll, { once: true });
    play();
    if (!renderActive()) syncControls(false);
  }

  async function start() {
    let parsed;
    try {
      parsed = window.MutaViz.decodeSpec(window.location.hash.slice(1));
    } catch {
      fail("The visualization data was incomplete.");
      return;
    }
    const checked = window.MutaViz.validateSpec(parsed);
    if (!checked.ok) {
      fail("The visualization data was not valid.");
      return;
    }
    const spec = checked.spec;
    stage.setAttribute("aria-label", spec.aria_label);
    document.title = spec.title;
    try {
      await loadLibrary(spec.library);
      if (spec.library === "d3") renderD3(spec);
      else if (spec.library === "three") renderThree(spec);
      else renderAnimation(spec);
    } catch (error) {
      fail(error && error.message ? error.message : "This visualization could not be drawn.");
    }
  }

  void start();
})();
