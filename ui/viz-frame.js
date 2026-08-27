/* Trusted adapters for declarative model output. Model-authored JavaScript never runs here. */
"use strict";

(() => {
  const stage = document.getElementById("viz-stage");
  const errorEl = document.getElementById("viz-error");
  const replay = document.getElementById("viz-replay");
  const surfaceControls = document.getElementById("viz-surface-controls");
  const surfacePlay = document.getElementById("viz-surface-play");
  const surfacePause = document.getElementById("viz-surface-pause");
  const surfaceRestart = document.getElementById("viz-surface-restart");
  const t = (key, variables) => window.MutaI18n.t(key, variables);
  const reducedMotion = new URLSearchParams(window.location.search).get("motion") === "reduce"
    || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
    errorEl.textContent = message || t("visualization.failed");
    errorEl.hidden = false;
    replay.hidden = true;
    surfaceControls.hidden = true;
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

  function loadTrustedScript(path) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = path;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`${path} is not available in this offline bundle`));
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

  function renderDiagram(spec) {
    stage.replaceChildren();
    const width = 720;
    const height = Math.max(240, spec.height);
    const nodes = new Map(spec.nodes.map((node) => [node.id, node]));
    const svg = d3.select(stage).append("svg").attr("viewBox", `0 0 ${width} ${height}`)
      .attr("role", "img").attr("aria-label", spec.aria_label);
    svg.append("defs").append("marker").attr("id", "diagram-arrow")
      .attr("viewBox", "0 0 10 10").attr("refX", 8).attr("refY", 5)
      .attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto-start-reverse")
      .append("path").attr("d", "M 0 0 L 10 5 L 0 10 z").attr("fill", neutral);

    const linkLayer = svg.append("g").attr("class", "diagram-links");
    const boundaryDistance = (node, ux, uy) => {
      if (node.shape === "circle") return (node.size || 24) + 3;
      if (node.shape === "label") return 5;
      const halfWidth = (node.width || 150) / 2;
      const halfHeight = (node.height || 58) / 2;
      return 1 / Math.max(Math.abs(ux) / halfWidth, Math.abs(uy) / halfHeight, 0.001) + 3;
    };
    const lineFor = (link, offset = 0) => {
      const source = nodes.get(link.source);
      const target = nodes.get(link.target);
      const route = (link.via || []).map(([x, y]) => ({ x, y }));
      const first = route[0] || target;
      const last = route[route.length - 1] || source;
      const firstLength = Math.max(1, Math.hypot(first.x - source.x, first.y - source.y));
      const lastLength = Math.max(1, Math.hypot(target.x - last.x, target.y - last.y));
      const sourceUx = (first.x - source.x) / firstLength;
      const sourceUy = (first.y - source.y) / firstLength;
      const targetUx = (target.x - last.x) / lastLength;
      const targetUy = (target.y - last.y) / lastLength;
      const sourceInset = boundaryDistance(source, sourceUx, sourceUy);
      const targetInset = boundaryDistance(target, targetUx, targetUy);
      const points = [
        {
          x: source.x + sourceUx * sourceInset,
          y: source.y + sourceUy * sourceInset,
        },
        ...route,
        {
          x: target.x - targetUx * targetInset,
          y: target.y - targetUy * targetInset,
        },
      ];
      if (offset && route.length === 0) {
        const ox = -sourceUy * offset;
        const oy = sourceUx * offset;
        points.forEach((point) => { point.x += ox; point.y += oy; });
      }
      const line = linkLayer.append("polyline")
        .attr("points", points.map((point) => `${point.x},${point.y}`).join(" "))
        .attr("fill", "none")
        .attr("stroke", neutral).attr("stroke-width", 2)
        .attr("stroke-dasharray", link.bond === "dashed" ? "7 6" : null)
        .attr("marker-end", link.arrow && offset === 0 ? "url(#diagram-arrow)" : null);
      line.append("title").text(link.label || `${source.label} to ${target.label}`);
    };
    spec.links.forEach((link) => {
      if (link.bond === "double") [-3, 3].forEach((offset) => lineFor(link, offset));
      else if (link.bond === "triple") [-5, 0, 5].forEach((offset) => lineFor(link, offset));
      else lineFor(link);
      if (link.label) {
        const source = nodes.get(link.source);
        const target = nodes.get(link.target);
        linkLayer.append("text").attr("x", link.label_x ?? (source.x + target.x) / 2)
          .attr("y", link.label_y ?? (source.y + target.y) / 2 - 8).attr("text-anchor", "middle")
          .attr("class", "diagram-link-label").text(link.label);
      }
    });

    const nodeLayer = svg.append("g").attr("class", "diagram-nodes");
    spec.nodes.forEach((item, index) => {
      const node = nodeLayer.append("g").attr("transform", `translate(${item.x},${item.y})`)
        .attr("tabindex", 0).attr("role", "img").attr("aria-label", item.label);
      if (item.shape === "circle") {
        node.append("circle").attr("r", item.size || 24).attr("fill", color(item.color, index));
      } else if (item.shape === "rounded") {
        const nodeWidth = item.width || 150;
        const nodeHeight = item.height || 58;
        node.append("rect").attr("x", -nodeWidth / 2).attr("y", -nodeHeight / 2)
          .attr("width", nodeWidth).attr("height", nodeHeight).attr("rx", 14)
          .attr("fill", color(item.color, index));
      }
      node.append("text").attr("text-anchor", "middle").attr("y", 5)
        .attr("class", "diagram-node-label").text(item.label);
      node.append("title").text(item.label);
    });
    (spec.annotations || []).forEach((note) => {
      svg.append("text").attr("x", note.x).attr("y", note.y)
        .attr("text-anchor", "middle").attr("class", "diagram-annotation").text(note.text);
    });
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
    else if (spec.kind === "diagram") renderDiagram(spec);
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

  function surfaceObject(object) {
    const [xCount, yCount] = object.resolution;
    const [xMin, xMax] = object.x_domain;
    const [yMin, yMax] = object.y_domain;
    const [zMin, zMax] = object.z_domain;
    const xCenter = (xMin + xMax) / 2;
    const yCenter = (yMin + yMax) / 2;
    const zCenter = zMin <= 0 && zMax >= 0 ? 0 : (zMin + zMax) / 2;
    const xScale = 8 / (xMax - xMin);
    const yScale = 6 / (yMax - yMin);
    const zScale = 4.8 / Math.max(1e-9, zMax - zMin);
    const positions = new Float32Array(xCount * yCount * 3);
    const colors = new Float32Array(xCount * yCount * 3);
    const indices = [];
    for (let row = 0; row < yCount - 1; row += 1) {
      for (let column = 0; column < xCount - 1; column += 1) {
        const topLeft = row * xCount + column;
        const bottomLeft = (row + 1) * xCount + column;
        indices.push(topLeft, bottomLeft, topLeft + 1, bottomLeft, bottomLeft + 1, topLeft + 1);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setIndex(indices);
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.getAttribute("position").setUsage(THREE.DynamicDrawUsage);
    const lowColor = new THREE.Color(palette[0]);
    const middleColor = new THREE.Color(palette[3]);
    const highColor = new THREE.Color(palette[1]);

    const world = (x, y, z) => [
      (x - xCenter) * xScale,
      (z - zCenter) * zScale,
      (y - yCenter) * yScale,
    ];
    const update = (expression, phase = 0) => {
      for (let row = 0; row < yCount; row += 1) {
        const y = yMin + (yMax - yMin) * row / (yCount - 1);
        for (let column = 0; column < xCount; column += 1) {
          const x = xMin + (xMax - xMin) * column / (xCount - 1);
          let z;
          try {
            z = window.MutaViz.evaluateSurfaceExpression(expression, { x, y, t: phase });
          } catch {
            z = zCenter;
          }
          z = Math.max(zMin, Math.min(zMax, z));
          const vertex = row * xCount + column;
          const coordinate = world(x, y, z);
          positions[vertex * 3] = coordinate[0];
          positions[vertex * 3 + 1] = coordinate[1];
          positions[vertex * 3 + 2] = coordinate[2];
          const amount = Math.max(0, Math.min(1, (z - zMin) / (zMax - zMin)));
          const shade = amount < 0.5
            ? lowColor.clone().lerp(middleColor, amount * 2)
            : middleColor.clone().lerp(highColor, (amount - 0.5) * 2);
          colors[vertex * 3] = shade.r;
          colors[vertex * 3 + 1] = shade.g;
          colors[vertex * 3 + 2] = shade.b;
        }
      }
      geometry.getAttribute("position").needsUpdate = true;
      geometry.getAttribute("color").needsUpdate = true;
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();
    };
    update(object.expression, 0);

    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.58,
      metalness: 0.03,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.92,
    });
    const mesh = new THREE.Mesh(geometry, material);
    const wireMaterial = new THREE.MeshBasicMaterial({
      color: new THREE.Color(border), wireframe: true, transparent: true, opacity: 0.2,
    });
    const wire = new THREE.Mesh(geometry, wireMaterial);
    wire.renderOrder = 2;

    const axes = new THREE.Group();
    const axisMaterial = new THREE.LineBasicMaterial({ color: new THREE.Color(neutral) });
    const xOrigin = Math.max(yMin, Math.min(yMax, 0));
    const yOrigin = Math.max(xMin, Math.min(xMax, 0));
    const zOrigin = Math.max(zMin, Math.min(zMax, 0));
    const axisSegments = [
      [world(xMin, xOrigin, zOrigin), world(xMax, xOrigin, zOrigin)],
      [world(yOrigin, yMin, zOrigin), world(yOrigin, yMax, zOrigin)],
      [world(yOrigin, xOrigin, zMin), world(yOrigin, xOrigin, zMax)],
    ];
    axisSegments.forEach(([from, to]) => {
      const lineGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(...from), new THREE.Vector3(...to),
      ]);
      axes.add(new THREE.Line(lineGeometry, axisMaterial));
    });
    [["x", world(xMax, xOrigin, zOrigin)], ["y", world(yOrigin, yMax, zOrigin)], ["z", world(yOrigin, xOrigin, zMax)]]
      .forEach(([label, position]) => {
        const sprite = textSprite(label, neutral);
        sprite.scale.set(0.8, 0.3, 1);
        sprite.position.set(position[0] + 0.18, position[1] + 0.18, position[2] + 0.18);
        axes.add(sprite);
      });
    return { mesh, wire, axes, geometry, material, wireMaterial, update, world };
  }

  function renderThree(spec) {
    stage.replaceChildren();
    replay.hidden = true;
    surfaceControls.hidden = true;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.domElement.tabIndex = 0;
    renderer.domElement.setAttribute("role", "img");
    renderer.domElement.setAttribute("aria-label", `${spec.aria_label} ${t("visualization.rotateHint")}`);
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
    scene.add(group);
    const bounds = new THREE.Box3();
    const surfaces = [];
    spec.objects.forEach((object, index) => {
      if (object.type === "surface") {
        const surface = surfaceObject(object);
        group.add(surface.mesh, surface.wire, surface.axes);
        surface.mesh.updateMatrixWorld(true);
        bounds.expandByObject(surface.mesh);
        surfaces.push({ object, ...surface });
        return;
      }
      const shade = new THREE.Color(color(object.color, index));
      let mesh;
      if (object.type === "vector") {
        const from = new THREE.Vector3(...object.from);
        const delta = new THREE.Vector3(...object.to).sub(from);
        mesh = new THREE.ArrowHelper(delta.clone().normalize(), from, delta.length(), shade, 0.35, 0.2);
      } else if (object.type === "line") {
        const geometry = new THREE.BufferGeometry().setFromPoints(object.points.map((item) => new THREE.Vector3(...item)));
        mesh = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: shade }));
      } else {
        const size = object.size || (object.type === "point" ? 0.12 : 0.55);
        const geometry = object.type === "box"
          ? new THREE.BoxGeometry(size, size, size)
          : new THREE.SphereGeometry(size, 28, 18);
        mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: shade, roughness: 0.55 }));
        mesh.position.set(...(object.position || [0, 0, 0]));
      }
      group.add(mesh);
      mesh.updateMatrixWorld(true);
      bounds.expandByObject(mesh);
      if (object.label) {
        const label = textSprite(object.label, neutral);
        const anchor = object.label_position
          || (object.type === "vector" ? object.to : (object.position || [0, 0, 0]));
        const automaticOffset = object.label_position ? 0 : 0.35 + (index % 3) * 0.38;
        label.position.set(anchor[0] + (object.label_position ? 0 : 0.35), anchor[1] + automaticOffset, anchor[2]);
        group.add(label);
      }
    });
    if (!surfaces.length) group.add(new THREE.AxesHelper(3));
    group.updateMatrixWorld(true);
    const center = bounds.getCenter(new THREE.Vector3());
    const extent = Math.max(3, bounds.getSize(new THREE.Vector3()).length());
    camera.near = Math.max(0.01, extent / 1000);
    camera.far = Math.max(100, extent * 12);
    const cameraDistance = surfaces.length ? 1.35 : 2.2;
    camera.position.copy(center).add(
      new THREE.Vector3(1.8, 1.4, 2.2).normalize().multiplyScalar(extent * cameraDistance),
    );
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    let dragging = false;
    let previous = null;
    const pointerDown = (event) => {
      dragging = true;
      previous = [event.clientX, event.clientY];
      renderer.domElement.setPointerCapture(event.pointerId);
    };
    const pointerMove = (event) => {
      if (!dragging || !previous) return;
      group.rotation.y += (event.clientX - previous[0]) * 0.009;
      group.rotation.x += (event.clientY - previous[1]) * 0.009;
      previous = [event.clientX, event.clientY];
      renderer.render(scene, camera);
    };
    const pointerUp = () => { dragging = false; previous = null; };
    const keyDown = (event) => {
      const directions = { ArrowLeft: [-0.12, 0], ArrowRight: [0.12, 0], ArrowUp: [0, -0.12], ArrowDown: [0, 0.12] };
      const change = directions[event.key];
      if (!change) return;
      event.preventDefault();
      group.rotation.y += change[0];
      group.rotation.x += change[1];
      renderer.render(scene, camera);
    };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointermove", pointerMove);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.domElement.addEventListener("pointercancel", pointerUp);
    renderer.domElement.addEventListener("keydown", keyDown);
    const hint = document.createElement("span");
    hint.className = "viz-3d-hint";
    hint.textContent = t("visualization.dragRotate");
    stage.appendChild(hint);
    if (spec.notes?.length) {
      const notes = document.createElement("div");
      notes.className = "viz-3d-notes";
      notes.setAttribute("aria-label", t("visualization.orbitalRelationships"));
      spec.notes.forEach((value) => {
        const line = document.createElement("span");
        line.textContent = value;
        notes.appendChild(line);
      });
      stage.appendChild(notes);
    }
    if (surfaces.length) {
      const object = surfaces[0].object;
      const equation = document.createElement("div");
      equation.className = "viz-surface-equation";
      const expression = document.createElement("strong");
      expression.textContent = object.expression_text;
      const domains = document.createElement("span");
      const domainValue = (value) => {
        if (Math.abs(value - Math.PI) < 1e-5) return "π";
        if (Math.abs(value + Math.PI) < 1e-5) return "−π";
        return Number(value.toFixed(3)).toString();
      };
      domains.textContent = t("visualization.axisDomains", {
        x0: domainValue(object.x_domain[0]),
        x1: domainValue(object.x_domain[1]),
        y0: domainValue(object.y_domain[0]),
        y1: domainValue(object.y_domain[1]),
      });
      equation.append(expression, domains);
      stage.appendChild(equation);
    }
    const resize = () => {
      const width = Math.max(1, stage.clientWidth);
      const height = Math.max(1, stage.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(stage);
    // A static scene costs nothing while the learner reads. Pointer, keyboard, and resize
    // handlers render on demand; perpetual auto-spin would heat the scored CPU package forever.
    let animationFrame = 0;
    let playing = false;
    let elapsed = 0;
    let startedAt = 0;
    let lastDraw = 0;
    const animatedSurface = surfaces.find((surface) => surface.object.animation);
    const durationMs = (animatedSurface?.object.animation?.duration || 8) * 1000;
    const drawAnimation = (timestamp) => {
      animationFrame = 0;
      if (!playing || !renderActive() || !animatedSurface) return;
      if (!startedAt) startedAt = timestamp - elapsed;
      elapsed = Math.min(durationMs, timestamp - startedAt);
      if (timestamp - lastDraw >= 32 || elapsed >= durationMs) {
        lastDraw = timestamp;
        const progress = elapsed / durationMs;
        const animation = animatedSurface.object.animation;
        if (animation.mode === "phase") {
          animatedSurface.update(animation.expression, progress * Math.PI * 2);
        } else {
          group.rotation.y = progress * Math.PI * 2;
        }
        renderer.render(scene, camera);
      }
      if (elapsed >= durationMs) {
        playing = false;
        surfacePlay.disabled = false;
        surfacePause.disabled = true;
        return;
      }
      animationFrame = window.requestAnimationFrame(drawAnimation);
    };
    const startAnimation = () => {
      if (!animatedSurface || reducedMotion || playing) return;
      if (elapsed >= durationMs) {
        elapsed = 0;
        startedAt = 0;
        animatedSurface.update(animatedSurface.object.expression, 0);
      }
      playing = true;
      surfacePlay.disabled = true;
      surfacePause.disabled = false;
      startedAt = performance.now() - elapsed;
      if (!animationFrame && renderActive()) {
        animationFrame = window.requestAnimationFrame(drawAnimation);
      }
    };
    const pauseAnimation = () => {
      if (!playing) return;
      playing = false;
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      surfacePlay.disabled = false;
      surfacePause.disabled = true;
    };
    const restartAnimation = () => {
      pauseAnimation();
      elapsed = 0;
      startedAt = 0;
      if (!animatedSurface) return;
      animatedSurface.update(animatedSurface.object.expression, 0);
      if (animatedSurface.object.animation.mode === "orbit") group.rotation.y = 0;
      renderer.render(scene, camera);
      startAnimation();
    };
    if (animatedSurface && !reducedMotion) {
      surfaceControls.hidden = false;
      surfacePlay.onclick = startAnimation;
      surfacePause.onclick = pauseAnimation;
      surfaceRestart.onclick = restartAnimation;
      surfacePlay.disabled = true;
      surfacePause.disabled = false;
      startAnimation();
    }
    const removeActivity = onActivity((active) => {
      if (!active && animationFrame) {
        window.cancelAnimationFrame(animationFrame);
        animationFrame = 0;
      } else if (active && playing && !animationFrame) {
        startedAt = performance.now() - elapsed;
        animationFrame = window.requestAnimationFrame(drawAnimation);
      }
      if (active) renderer.render(scene, camera);
    });
    const cleanup = () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      playing = false;
      removeActivity();
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("pointermove", pointerMove);
      renderer.domElement.removeEventListener("pointerup", pointerUp);
      renderer.domElement.removeEventListener("pointercancel", pointerUp);
      renderer.domElement.removeEventListener("keydown", keyDown);
      group.traverse((child) => {
        child.geometry?.dispose?.();
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.filter(Boolean).forEach((material) => {
          material.map?.dispose?.();
          material.dispose?.();
        });
      });
      renderer.dispose();
      renderer.forceContextLoss?.();
    };
    window.addEventListener("beforeunload", cleanup, { once: true });
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
    } catch (error) {
      stage.dataset.vizError = `decode: ${String(error?.message || error).slice(0, 200)}`;
      fail(t("visualization.incomplete"));
      return;
    }
    const checked = window.MutaViz.validateSpec(parsed);
    if (!checked.ok) {
      stage.dataset.vizError = `validation: ${checked.error}`;
      fail(t("visualization.invalid"));
      return;
    }
    const spec = checked.spec;
    stage.setAttribute("aria-label", spec.aria_label);
    document.title = spec.title;
    try {
      await loadLibrary(spec.library);
      if (spec.version === 2) {
        replay.hidden = true;
        surfaceControls.hidden = true;
      await loadTrustedScript("viz-frame-v2.js?v=20260827-v2-51");
        await window.MutaVizV2.render(spec, {
          stage,
          palette,
          neutral,
          border,
          t,
          reducedMotion,
          renderActive,
          onActivity,
        });
      } else if (spec.library === "d3") renderD3(spec);
      else if (spec.library === "three") renderThree(spec);
      else renderAnimation(spec);
    } catch (error) {
      console.warn("Visualization rendering failed", error);
      stage.dataset.vizError = String(error?.message || error || "unknown rendering error").slice(0, 240);
      fail(t("visualization.failed"));
    }
  }

  void start();
})();
