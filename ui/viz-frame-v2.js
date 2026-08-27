/* Deterministic renderer for the closed Muta visualization V2 grammar. */
"use strict";

((global) => {
  const SVG_NS = "http://www.w3.org/2000/svg";

  function element(name, attributes = {}, text = "") {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text) node.textContent = text;
    return node;
  }

  function html(name, className, text = "") {
    const node = document.createElement(name);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function extent(values) {
    const finite = values.filter(Number.isFinite);
    if (!finite.length) return [-1, 1];
    let low = Math.min(...finite);
    let high = Math.max(...finite);
    if (low === high) {
      const delta = Math.abs(low || 1) * 0.15;
      low -= delta;
      high += delta;
    }
    const padding = (high - low) * 0.08;
    return [low - padding, high + padding];
  }

  function scale(domain, range) {
    const span = domain[1] - domain[0] || 1;
    return (value) => range[0] + ((value - domain[0]) / span) * (range[1] - range[0]);
  }

  function paletteValue(context, value, index = 0) {
    return typeof value === "string" ? value : context.palette[index % context.palette.length];
  }

  function stateNumber(values, id, fallback) {
    const value = Number(values[id]);
    return Number.isFinite(value) ? value : fallback;
  }

  function doubleSlitGeometry(separation, screenY) {
    const slitX = -2; const screenX = 2.8; const halfGap = separation / 2;
    const upper = [slitX, halfGap]; const lower = [slitX, -halfGap];
    const screen = [screenX, screenY];
    const upperLength = Math.hypot(screenX - slitX, screenY - halfGap);
    const lowerLength = Math.hypot(screenX - slitX, screenY + halfGap);
    return { upper, lower, screen, upperLength, lowerLength, pathDifference: Math.abs(lowerLength - upperLength) };
  }

  function vectorFieldDiagnostics(spec, values) {
    const probe = spec.scene.layers.find((layer) => layer.type === "probe_vector");
    if (!probe) return null;
    const x = stateNumber(values, probe.x_control, 0); const y = stateNumber(values, probe.y_control, 0);
    const evaluate = (expression, px, py) => global.MutaViz.evaluateExpressionV2(
      expression, { x: px, y: py, z: 0, t: 0, u: 0, v: 0 },
    );
    try {
      const epsilon = 1e-4;
      const fx = evaluate(probe.x_expression, x, y); const fy = evaluate(probe.y_expression, x, y);
      const dFxDx = (evaluate(probe.x_expression, x + epsilon, y) - evaluate(probe.x_expression, x - epsilon, y)) / (2 * epsilon);
      const dFxDy = (evaluate(probe.x_expression, x, y + epsilon) - evaluate(probe.x_expression, x, y - epsilon)) / (2 * epsilon);
      const dFyDx = (evaluate(probe.y_expression, x + epsilon, y) - evaluate(probe.y_expression, x - epsilon, y)) / (2 * epsilon);
      const dFyDy = (evaluate(probe.y_expression, x, y + epsilon) - evaluate(probe.y_expression, x, y - epsilon)) / (2 * epsilon);
      const clean = (value) => Math.abs(value) < 5e-7 ? 0 : value;
      return { x, y, fx, fy, divergence: clean(dFxDx + dFyDy), curl: clean(dFyDx - dFxDy) };
    } catch {
      return null;
    }
  }

  function vanDerCorput(source, radix) {
    let value = 0; let denominator = 1; let index = source;
    while (index) { const remainder = index % radix; index = Math.floor(index / radix); denominator *= radix; value += remainder / denominator; }
    return value;
  }

  function uncertaintySamples(values) {
    const count = Math.max(40, Math.min(400, Math.round(stateNumber(values, "samples", 160))));
    const massSigma = Math.max(0.01, stateNumber(values, "mass_sigma", 0.4));
    const volumeSigma = Math.max(0.01, stateNumber(values, "volume_sigma", 0.18));
    return Array.from({ length: count }, (_unused, offset) => {
      const index = offset + 1; const u1 = Math.max(1e-9, vanDerCorput(index, 2)); const u2 = vanDerCorput(index, 3);
      const radius = Math.sqrt(-2 * Math.log(u1));
      return [Math.max(0.1, 4 + volumeSigma * radius * Math.sin(2 * Math.PI * u2)), 10 + massSigma * radius * Math.cos(2 * Math.PI * u2)];
    });
  }

  function numbersFromLabel(label) {
    const bracket = String(label || "").match(/\[([^\]]+)\]/);
    if (!bracket) return [];
    return bracket[1].split(",").map((value) => Number(value.trim())).filter(Number.isFinite);
  }

  function graphTraversalState(algorithm, requestedStep) {
    const adjacency = { A: ["B", "C"], B: ["A", "D", "E"], C: ["A", "E"], D: ["B"], E: ["B", "C"] };
    const depthFirst = String(algorithm || "bfs").toLowerCase() === "dfs";
    const frontier = ["A"]; const visited = [];
    const targetVisits = Math.max(0, Math.min(5, Math.round(requestedStep) + 1));
    while (frontier.length && visited.length < targetVisits) {
      const current = depthFirst ? frontier.pop() : frontier.shift();
      if (visited.includes(current)) continue;
      visited.push(current);
      const neighbours = adjacency[current].filter((node) => !visited.includes(node) && !frontier.includes(node));
      if (depthFirst) frontier.push(...neighbours.slice().reverse());
      else frontier.push(...neighbours);
    }
    return { visited, frontier: depthFirst ? frontier.slice().reverse() : frontier.slice() };
  }

  function bstInsertionState(layers, inserted) {
    const childIds = { root: ["left", "right"], left: ["left_left", "left_right"], right: ["right_left", "right_right"] };
    const records = new Map(layers.filter((layer) => layer.type === "node" && layer.id !== "candidate").map((layer) => [layer.id, { ...layer, value: Number(String(layer.label).match(/-?\d+(?:\.\d+)?/)?.[0]) }]));
    let current = "root"; const path = []; let parent = null; let side = 0; let duplicate = false;
    while (current && records.has(current)) {
      path.push(current); const record = records.get(current);
      if (inserted === record.value) { duplicate = true; parent = current; break; }
      side = inserted < record.value ? 0 : 1; parent = current;
      current = childIds[current]?.[side] || null;
    }
    const parentNode = records.get(parent) || records.get("root");
    const offset = parentNode.y < 100 ? 150 : parentNode.y < 220 ? 82 : 46;
    const candidate = duplicate
      ? { x: parentNode.x, y: parentNode.y + 68 }
      : { x: parentNode.x + (side ? offset : -offset), y: parentNode.y + 112 };
    return { path, parent, duplicate, candidate };
  }

  function neuralState(values, includeThird = false) {
    const x1 = 0.6; const x2 = 0.4; const weight = stateNumber(values, "weight", 1);
    const h1 = Math.max(0, weight * x1 + 0.5 * x2 - 0.2);
    const h2 = Math.max(0, -0.4 * x1 + 0.8 * x2 + 0.1);
    const h3 = Math.max(0, 0.3 * x1 + 0.4 * x2);
    const logit = 0.9 * h1 - 0.7 * h2 + (includeThird ? 0.35 * h3 : 0) + 0.05;
    return { x1, x2, weight, h1, h2, h3, output: 1 / (1 + Math.exp(-logit)) };
  }

  let classifierCache = null;
  function classifierState(values) {
    const epochs = Math.max(1, Math.min(40, Math.round(stateNumber(values, "epoch", 20))));
    const learningRate = Math.max(0.05, Math.min(0.5, stateNumber(values, "learning_rate", 0.2)));
    const key = `${epochs}:${learningRate.toFixed(4)}`;
    if (classifierCache?.key === key) return classifierCache;
    const samples = [
      ...Array.from({ length: 18 }, (_unused, index) => ({ point: [-3 + (index % 6) * 0.45, -1.8 + Math.floor(index / 6) * 0.45], label: 0 })),
      ...Array.from({ length: 18 }, (_unused, index) => ({ point: [0.7 + (index % 6) * 0.45, 0.25 + Math.floor(index / 6) * 0.45], label: 1 })),
    ];
    const hiddenWeights = [[0.32, -0.28], [-0.18, 0.38]]; const hiddenBiases = [0, 0]; const outputWeights = [0.45, -0.4]; let outputBias = 0;
    const predict = (point) => {
      const hidden = hiddenWeights.map((weights, index) => Math.tanh(weights[0] * point[0] + weights[1] * point[1] + hiddenBiases[index]));
      const logit = outputWeights[0] * hidden[0] + outputWeights[1] * hidden[1] + outputBias;
      return { hidden, probability: 1 / (1 + Math.exp(-Math.max(-40, Math.min(40, logit)))) };
    };
    const loss = [];
    for (let epoch = 0; epoch <= epochs; epoch += 1) {
      const probabilities = samples.map((sample) => predict(sample.point).probability);
      loss.push([epoch, -probabilities.reduce((sum, probability, index) => { const label = samples[index].label; return sum + label * Math.log(Math.max(1e-9, probability)) + (1 - label) * Math.log(Math.max(1e-9, 1 - probability)); }, 0) / samples.length]);
      if (epoch === epochs) break;
      const gradHiddenWeights = [[0, 0], [0, 0]]; const gradHiddenBiases = [0, 0]; const gradOutputWeights = [0, 0]; let gradOutputBias = 0;
      samples.forEach((sample) => { const { hidden, probability } = predict(sample.point); const deltaOutput = probability - sample.label; for (let h = 0; h < 2; h += 1) { gradOutputWeights[h] += deltaOutput * hidden[h]; const deltaHidden = deltaOutput * outputWeights[h] * (1 - hidden[h] ** 2); gradHiddenBiases[h] += deltaHidden; gradHiddenWeights[h][0] += deltaHidden * sample.point[0]; gradHiddenWeights[h][1] += deltaHidden * sample.point[1]; } gradOutputBias += deltaOutput; });
      const scale = learningRate / samples.length;
      for (let h = 0; h < 2; h += 1) { outputWeights[h] -= scale * gradOutputWeights[h]; hiddenBiases[h] -= scale * gradHiddenBiases[h]; hiddenWeights[h][0] -= scale * gradHiddenWeights[h][0]; hiddenWeights[h][1] -= scale * gradHiddenWeights[h][1]; }
      outputBias -= scale * gradOutputBias;
    }
    classifierCache = { key, epochs, learningRate, samples, loss, predict };
    return classifierCache;
  }

  function kalmanSequence(values) {
    const noise = Math.max(0.1, stateNumber(values, "noise", 1));
    const processNoise = Math.max(0.01, stateNumber(values, "process_noise", 0.08));
    let estimate = 0; let variance = 1.5; const records = [];
    for (let step = 0; step <= 20; step += 1) {
      const truth = 0.5 * step + Math.sin(0.4 * step);
      const measurement = truth + noise * Math.sin(1.7 * step);
      const prior = estimate + 0.5; const predictedVariance = variance + processNoise;
      const gain = predictedVariance / (predictedVariance + noise * noise);
      estimate = prior + gain * (measurement - prior); variance = (1 - gain) * predictedVariance;
      records.push({ step, truth, measurement, prior, predictedVariance, gain, estimate, variance });
    }
    return records;
  }

  function gradientDescentState(values) {
    const learningRate = Math.max(0.02, Math.min(0.5, stateNumber(values, "learning_rate", 0.18)));
    const requestedStep = Math.max(0, Math.min(16, Math.round(stateNumber(values, "step", 8))));
    let x = 2.4; let y = 1.8; const points = [];
    for (let step = 0; step <= 16; step += 1) {
      points.push({ x, y, loss: x * x + 2 * y * y });
      x -= learningRate * 2 * x;
      y -= learningRate * 4 * y;
    }
    return { learningRate, requestedStep, points, selected: points[requestedStep] };
  }

  function localizationState(values) {
    const odometryNoise = Math.max(0, Math.min(1, stateNumber(values, "odometry_noise", 0.25)));
    const sensorNoise = Math.max(0, Math.min(1, stateNumber(values, "sensor_noise", 0.2)));
    const requestedStep = Math.max(0, Math.min(60, Math.round(stateNumber(values, "step", 30))));
    const records = Array.from({ length: 61 }, (_unused, step) => {
      const time = step / 10;
      const truth = [time - 3, 1.2 * Math.sin(time)];
      const odometry = [
        truth[0] + odometryNoise * 0.032 * step,
        truth[1] + odometryNoise * 0.72 * Math.sin(step * 1.7),
      ];
      const sensor = [
        truth[0] + sensorNoise * 0.55 * Math.cos(step * 1.13),
        truth[1] + sensorNoise * 0.55 * Math.sin(step * 1.31),
      ];
      const odometryVariance = 0.01 + odometryNoise * odometryNoise;
      const sensorVariance = 0.01 + sensorNoise * sensorNoise;
      const sensorWeight = odometryVariance / (odometryVariance + sensorVariance);
      const estimate = [
        (1 - sensorWeight) * odometry[0] + sensorWeight * sensor[0],
        (1 - sensorWeight) * odometry[1] + sensorWeight * sensor[1],
      ];
      return { step, truth, odometry, sensor, estimate, sensorWeight };
    });
    const selected = records[requestedStep];
    const uncertainty = {
      x: 0.12 + 0.5 * Math.sqrt(0.01 + odometryNoise * sensorNoise),
      y: 0.1 + 0.34 * Math.sqrt(0.01 + odometryNoise * sensorNoise),
    };
    return { odometryNoise, sensorNoise, requestedStep, records, selected, uncertainty };
  }

  function forwardKinematicsState(values) {
    const lengths = [105, 90, 75];
    const angles = ["joint_1", "joint_2", "joint_3"].map((id, index) => stateNumber(values, id, [25, -35, 55][index]) * Math.PI / 180);
    const points = [[165, 330]]; let heading = 0;
    lengths.forEach((length, index) => {
      heading += angles[index];
      points.push([points.at(-1)[0] + length * Math.cos(heading), points.at(-1)[1] - length * Math.sin(heading)]);
    });
    return { lengths, angles, points, end: points.at(-1) };
  }

  function lorenzPoints(values) {
    const sigma = Math.max(5, Math.min(20, stateNumber(values, "sigma", 10)));
    const rho = Math.max(10, Math.min(40, stateNumber(values, "rho", 28)));
    const beta = Math.max(1, Math.min(4, stateNumber(values, "beta", 8 / 3)));
    const dt = 0.01; let x = 0.1; let y = 0; let z = 0; const points = [];
    for (let step = 0; step < 620; step += 1) {
      const dx = sigma * (y - x); const dy = x * (rho - z) - y; const dz = x * y - beta * z;
      x += dt * dx; y += dt * dy; z += dt * dz;
      if (step >= 120 && [x, y, z].every(Number.isFinite)) points.push([x / 7, y / 7, (z - 24) / 7]);
    }
    return { sigma, rho, beta, points: points.slice(0, 500) };
  }

  function electromagneticWavePoints(values, progress = 0) {
    const amplitude = Math.max(0.2, Math.min(2, stateNumber(values, "amplitude", 1)));
    const wavelength = Math.max(1, Math.min(6, stateNumber(values, "wavelength", 3)));
    const phase = progress * 2 * Math.PI;
    const samples = Array.from({ length: 161 }, (_unused, index) => -4 + 8 * index / 160);
    return {
      amplitude,
      wavelength,
      electric: samples.map((x) => [x, amplitude * Math.sin(2 * Math.PI * x / wavelength - phase), 0]),
      magnetic: samples.map((x) => [x, 0, amplitude * Math.sin(2 * Math.PI * x / wavelength - phase)]),
    };
  }

  function inclinedGeometry(values) {
    const theta = stateNumber(values, "incline", 30) * Math.PI / 180;
    const tangent = [Math.cos(theta), -Math.sin(theta)];
    const normal = [-Math.sin(theta), -Math.cos(theta)];
    const planeStart = [90, 345];
    const contact = [planeStart[0] + 300 * tangent[0], planeStart[1] + 300 * tangent[1]];
    const origin = [contact[0] + 36 * normal[0], contact[1] + 36 * normal[1]];
    return { theta, tangent, normal, planeStart, contact, origin };
  }

  function controlledPoints(family, layer, index, values) {
    const base = layer.points;
    const xs = base.map((point) => point[0]);
    if (family === "pythagoras") {
      const a = stateNumber(values, "a", 3); const b = stateNumber(values, "b", 4);
      if (index === 0) return [[0, 0], [a, 0], [a, b], [0, 0]];
      if (index === 1) return [[0, 0], [a, 0], [a, -a], [0, -a], [0, 0]];
      if (index === 2) return [[a, 0], [a, b], [a + b, b], [a + b, 0], [a, 0]];
      return [[0, 0], [a, b], [a - b, b + a], [-b, a], [0, 0]];
    }
    if (family === "unit_circle" && index > 0) {
      const angle = stateNumber(values, "angle", 45) * Math.PI / 180;
      const point = [Math.cos(angle), Math.sin(angle)];
      return index === 1 ? [[0, 0], point] : [[0, 0], [point[0], 0], point];
    }
    if (family === "quadratic") {
      const a = stateNumber(values, "a", 1); const b = stateNumber(values, "b", 0); const c = stateNumber(values, "c", 0);
      if (index === 0) return xs.map((x) => [x, a * x * x + b * x + c]);
      const vertexX = Math.abs(a) < 1e-9 ? 0 : -b / (2 * a);
      return [[vertexX, -10], [vertexX, 10]];
    }
    if (family === "line_intersection") {
      const slope = stateNumber(values, index === 0 ? "m1" : "m2", index === 0 ? 1 : -1);
      const intercept = stateNumber(values, index === 0 ? "c1" : "c2", index === 0 ? 0 : 2);
      return xs.map((x) => [x, slope * x + intercept]);
    }
    if (family === "linear_transform") {
      const matrix = String(values.matrix || "identity");
      const coefficients = matrix === "shear" ? [1, 0.7, 0, 1]
        : matrix === "scale" ? [1.6, 0, 0, 0.65] : [1, 0, 0, 1];
      if (layer.label === "invariant-direction test v₁") return [[0, 0], [2 * coefficients[0], 2 * coefficients[2]]];
      if (layer.label === "invariant-direction test v₂") {
        return matrix === "shear" ? [[0, 0], [2, 0]] : [[0, 0], [2 * coefficients[1], 2 * coefficients[3]]];
      }
      return base.map(([x, y]) => [coefficients[0] * x + coefficients[1] * y, coefficients[2] * x + coefficients[3] * y]);
    }
    if (family === "derivative_tangent" && index === 1) {
      const at = stateNumber(values, "x", 1); const f = at ** 3 - 3 * at; const slope = 3 * at * at - 3;
      return xs.map((x) => [x, f + slope * (x - at)]);
    }
    if (family === "riemann_sum" && index === 1) {
      const count = Math.max(1, Math.round(stateNumber(values, "rectangles", 8))); const width = 4 / count; const points = [];
      for (let bar = 0; bar < count; bar += 1) {
        const left = bar * width; const right = left + width; const height = left * left;
        points.push([left, 0], [left, height], [right, height], [right, 0]);
      }
      return points;
    }
    if (family === "gradient_field" && index === 3) {
      const px = stateNumber(values, "point_x", stateNumber(values, "probe_x", 1));
      const py = stateNumber(values, "point_y", stateNumber(values, "probe_y", 1));
      return [[px, py], [px + 0.45 * 2 * px, py + 0.45 * 2 * py]];
    }
    if (family === "gradient_linked") {
      const px = stateNumber(values, "point_x", 1); const py = stateNumber(values, "point_y", 1);
      if (layer.label === "surface probe at selected point") {
        const point = [px + 0.35 * py - 4.5, 0.18 * (px * px + py * py) + 0.35 * py];
        return [point, [point[0] + 0.015, point[1] + 0.015]];
      }
      if (layer.label === "contour probe and gradient direction") {
        const magnitude = Math.max(1, Math.hypot(2 * px, 2 * py));
        return [[3.2 + px, py], [3.2 + px + 0.9 * 2 * px / magnitude, py + 0.9 * 2 * py / magnitude]];
      }
    }
    if (family === "gradient_descent") {
      const descent = gradientDescentState(values);
      const selected = descent.points.slice(0, descent.requestedStep + 1);
      if (layer.label === "gradient-descent trajectory on projected surface") {
        return selected.map(({ x, y, loss }) => [x + 0.35 * y - 4.5, 0.18 * loss + 0.35 * y]);
      }
      if (layer.label === "gradient-descent trajectory on contour map") return selected.map(({ x, y }) => [3.2 + x, y]);
    }
    if (family === "robot_localization") {
      const localization = localizationState(values); const selected = localization.selected.estimate;
      if (layer.label === "true pose trajectory") return localization.records.map((record) => record.truth);
      if (layer.label === "noisy odometry trajectory") return localization.records.map((record) => record.odometry);
      if (layer.label === "Kalman/particle estimated pose") return localization.records.slice(0, localization.requestedStep + 1).map((record) => record.estimate);
      if (layer.label === "uncertainty ellipse") return base.map((_point, pointIndex) => {
        const angle = 2 * Math.PI * pointIndex / Math.max(1, base.length - 1);
        return [selected[0] + localization.uncertainty.x * Math.cos(angle), selected[1] + localization.uncertainty.y * Math.sin(angle)];
      });
      if (layer.label === "sensor observations to landmarks") return [selected, [-2.4, 2.3], selected, [2.5, 2.1]];
    }
    if (family === "pendulum") {
      const pivot = [250, 80];
      const length = 55 + 42 * stateNumber(values, "length", 1);
      const amplitude = Math.max(1, stateNumber(values, "angle", 20)) * Math.PI / 180;
      const period = 2 * Math.PI * Math.sqrt(Math.max(0.05, stateNumber(values, "length", 1)) / 9.81);
      const elapsed = stateNumber(values, "__animation_progress", 0) * 8;
      const angle = amplitude * Math.cos(2 * Math.PI * elapsed / period);
      return Array.from({ length: 41 }, (_unused, step) => {
        const phase = -amplitude + 2 * amplitude * step / 40;
        return [pivot[0] + 0.4 * length * Math.sin(phase), pivot[1] + 0.4 * length * Math.cos(phase)];
      });
    }
    if (family === "projectile") {
      const angle = stateNumber(values, "angle", 45) * Math.PI / 180; const speed = stateNumber(values, "speed", 20);
      const flight = Math.max(0.05, 2 * speed * Math.sin(angle) / 9.81);
      return Array.from({ length: 81 }, (_unused, step) => {
        const time = flight * step / 80;
        return [speed * Math.cos(angle) * time, Math.max(0, speed * Math.sin(angle) * time - 4.905 * time * time)];
      });
    }
    if (family === "circular_motion" && index > 0) {
      const omega = stateNumber(values, "angular_velocity", 1); const direction = omega < 0 ? -1 : 1; const speed = Math.max(0.25, Math.min(2.4, Math.abs(omega)));
      if (index === 1) return [[0, 0], [3, 0]];
      if (index === 2) return [[3, 0], [3, direction * 1.8 * speed]];
      return [[3, 0], [3 - 1.8 * speed * speed, 0]];
    }
    if (family === "harmonic_motion") {
      const spring = Math.max(0.1, stateNumber(values, "spring_constant", 1));
      const mass = Math.max(0.1, stateNumber(values, "mass", 2));
      const omega = Math.sqrt(spring / mass);
      if (index === 0) return base.map(([time]) => [time, Math.cos(omega * time)]);
      if (index === 1) return base.map((_point, step) => { const time = 2 * Math.PI * step / Math.max(1, base.length - 1); return [Math.cos(time), -omega * Math.sin(time)]; });
      const elapsed = stateNumber(values,"__animation_progress",0)*2*Math.PI;
      const displacement = Math.cos(omega*elapsed);
      return [[-4, 0], [-3.6, 0.4], [-3.2, -0.4], [-2.8, 0.4], [-2.4, -0.4], [-2, 0], [displacement, 0]];
    }
    if (family === "double_pendulum") {
      const initial = stateNumber(values, index % 2 ? "angle_2" : "angle_1", index % 2 ? 75.5 : 75);
      const state = [initial * Math.PI / 180, 0, -0.55 * initial * Math.PI / 180, 0]; const samples = [];
      for (let step = 0; step <= 1600; step += 1) {
        const [theta1, omega1, theta2, omega2] = state;
        if (step % 20 === 0) {
          const elbow = [Math.sin(theta1), -Math.cos(theta1)]; const bob = [elbow[0] + Math.sin(theta2), elbow[1] - Math.cos(theta2)];
          samples.push({ elbow, bob });
        }
        const delta = theta1 - theta2; const denominator = Math.max(0.1, 3 - Math.cos(2 * delta));
        const alpha1 = (-3*9.81*Math.sin(theta1) - 9.81*Math.sin(theta1-2*theta2) - 2*Math.sin(delta)*(omega2**2 + omega1**2*Math.cos(delta))) / denominator;
        const alpha2 = 2*Math.sin(delta)*(2*omega1**2 + 2*9.81*Math.cos(theta1) + omega2**2*Math.cos(delta)) / denominator;
        state[1] += 0.01 * alpha1; state[3] += 0.01 * alpha2; state[0] += 0.01 * state[1]; state[2] += 0.01 * state[3];
      }
      if (index < 2) return samples.map((sample) => sample.bob);
      const frame = Math.min(samples.length - 1, Math.floor(stateNumber(values, "__animation_progress", 0) * (samples.length - 1)));
      return [[0,0], samples[frame].elbow, samples[frame].bob];
    }
    if (family === "sampling_aliasing") {
      const signal = Math.max(0.1, stateNumber(values, "signal_frequency", 4));
      const sampleRate = Math.max(0.1, stateNumber(values, "sample_frequency", 12));
      if (index === 0) return xs.map((x) => [x, Math.sin(2 * Math.PI * signal * x)]);
      const alias = Math.abs(signal - Math.round(signal / sampleRate) * sampleRate);
      return xs.map((x) => [x, Math.sin(2 * Math.PI * alias * x)]);
    }
    if (family === "ac_phase") {
      const load = String(values.load || "resistive");
      const phase = index ? (load === "capacitive" ? Math.PI / 2 : load === "inductive" ? -Math.PI / 2 : 0) : 0;
      return xs.map((x) => [x, Math.sin(Math.PI * x + phase)]);
    }
    if (family === "travelling_wave") {
      const amplitude = stateNumber(values, "amplitude", 1);
      const wavelength = Math.max(0.1, stateNumber(values, "wavelength", 2));
      const frequency = stateNumber(values, "frequency", 1);
      if (index === 0) return xs.map((x) => [x, amplitude * Math.sin(2 * Math.PI * x / wavelength + frequency * 0.15)]);
      if (index === 1) return [[Math.min(...xs), 0], [Math.max(...xs), 0]];
      let crest = (Math.PI / 2 - frequency * 0.15) * wavelength / (2 * Math.PI);
      while (crest < Math.min(...xs) + 0.2) crest += wavelength;
      return [[crest, amplitude * 1.25], [crest + wavelength, amplitude * 1.25]];
    }
    if (family === "standing_wave") {
      const amplitude = stateNumber(values, "amplitude", 1);
      const harmonic = Math.max(1, Math.round(stateNumber(values, "harmonic", 1)));
      return xs.map((x) => [x, amplitude * Math.sin((Math.PI * harmonic * (x + 4)) / 8)]);
    }
    if (family === "wave_interference") {
      const phase = stateNumber(values, "phase", 0);
      if (index === 0) return xs.map((x) => [x, Math.sin(Math.PI * x)]);
      if (index === 1) return xs.map((x) => [x, Math.sin(Math.PI * x + phase)]);
      return xs.map((x) => [x, Math.sin(Math.PI * x) + Math.sin(Math.PI * x + phase)]);
    }
    if (family === "rc_circuit") {
      const tau = Math.max(0.15, stateNumber(values, "resistance", 1) * stateNumber(values, "capacitance", 2) / 5);
      const discharging = values.mode === "discharging";
      return xs.map((x) => {
        const time = Math.max(0, x);
        if (index === 0) return [time, discharging ? Math.exp(-time / tau) : 1 - Math.exp(-time / tau)];
        return [time, (discharging ? -1 : 1) * Math.exp(-time / tau) / Math.max(0.1, stateNumber(values, "resistance", 4))];
      });
    }
    if (family === "ideal_gas") {
      const temperature = Math.max(0.1, stateNumber(values, "temperature", 2));
      const pressure = Math.max(0.1, stateNumber(values, "pressure", 2));
      const volume = Math.max(0.1, stateNumber(values, "volume", 2));
      if (index === 0) return xs.map((x) => { const plottedVolume = Math.max(0.2, x); return [plottedVolume, temperature / plottedVolume]; });
      if (index === 1) return [[0.2, pressure], [8.2, pressure]];
      return [[volume, 0.1], [volume, Math.max(pressure, temperature / volume) * 1.15]];
    }
    if (family === "reaction_profile") {
      const catalysed = values.catalyst === "on";
      const barrier = index === 0 ? (catalysed ? 2.1 : 3) : 1.8;
      return xs.map((x) => [x, -0.3 * x + barrier * Math.exp(-x * x)]);
    }
    if (family === "carnot_cycle") {
      if (index < 4) return base;
      const states = [[1, 4], [3, 2.5], [4, 1], [1.5, 1.8]];
      const selected = states[Math.round(stateNumber(values, "playback", 0)) % states.length];
      return [selected, [selected[0] + 0.12, selected[1] + 0.12]];
    }
    if (family === "titration") {
      const volume = stateNumber(values, "titrant_volume", 25);
      if (index === 0) return base;
      const ph = 2 + 10 / (1 + Math.exp(-0.35 * (volume - 25)));
      return [[volume, 0], [volume, ph]];
    }
    if (family === "phase_diagram" && index === 3) {
      const temperature = stateNumber(values, "temperature", 0.55); const pressure = stateNumber(values, "pressure", 0.55);
      return [[temperature, 0], [temperature, pressure]];
    }
    if (family === "action_potential" && index === 3) {
      const time = stateNumber(values, "time", 1);
      const nearest = base.reduce((best, point) => Math.abs(point[0] - time) < Math.abs(best[0] - time) ? point : best, base[0]);
      return [[time, -90], [time, nearest[1]]];
    }
    if (family === "rlc_circuit") {
      const resistance = stateNumber(values, "resistance", 1); const inductance = Math.max(0.2, stateNumber(values, "inductance", 2));
      const capacitance = Math.max(0.2, stateNumber(values, "capacitance", 3));
      return xs.map((x) => [x, 1 - Math.exp(-resistance * Math.max(0, x) / (8 * inductance)) * Math.cos(Math.max(0, x) / Math.sqrt(inductance * capacitance / 20))]);
    }
    if (family === "polar_plot") {
      // The rose is the fixed locus r = cos(2θ).  Controls move the traversal
      // point over that locus; rotating the locus would invalidate the fixed
      // maxima and zero-crossing cues.
      return base;
    }
    if (family === "complex_mapping") {
      const angle = stateNumber(values, "point_angle", 1) * Math.PI / 5;
      const radius = Math.max(0.1, stateNumber(values, "point_radius", 2));
      if (layer.label === "selected source z") return [[-3, 0], [-3 + radius * Math.cos(angle), radius * Math.sin(angle)]];
      if (layer.label === "selected image z²") return [[3, 0], [3 + radius * radius * Math.cos(2 * angle), radius * radius * Math.sin(2 * angle)]];
      return base;
    }
    if (family === "lagrange_multiplier") {
      const constraint = stateNumber(values, "constraint_offset", 1);
      const optimum = constraint / 2;
      if (layer.label === "tangent contour through constrained minimum") { const radius=Math.abs(constraint)/Math.SQRT2; return Array.from({length:81},(_unused,step)=>{const angle=2*Math.PI*step/80; return [radius*Math.cos(angle),radius*Math.sin(angle)];}); }
      if (layer.label === "constraint x+y=c") return [[-3, constraint + 3], [4, constraint - 4]];
      if (["∇f at constrained minimum", "λ∇g parallel to ∇f"].includes(layer.label)) return [[optimum, optimum], [optimum + 0.9 * optimum, optimum + 0.9 * optimum]];
      return base;
    }
    if (family === "fourier_series") {
      const terms = Math.max(1, Math.round(stateNumber(values, "terms", 5)));
      if (layer.label !== "odd-harmonic partial sum") return base;
      return xs.map((x) => [x, Array.from({ length: terms }, (_unused, k) => Math.sin((2 * k + 1) * x) / (2 * k + 1)).reduce((sum, value) => sum + value, 0) * 4 / Math.PI]);
    }
    if (family === "convolution") {
      const shift = stateNumber(values, "shift", 0) + stateNumber(values, "step", 0) * 0.2;
      if (layer.label === "box pulse A") return base;
      if (layer.label === "sliding box pulse B") return base.map(([x,y])=>[x+shift,y]);
      if (layer.label === "current overlap area") { const left=Math.max(-1,shift-1); const right=Math.min(1,shift+1); return right>left ? [[left,0],[left,1],[right,1],[right,0],[left,0]] : [[shift,0],[shift+0.001,0]]; }
      return base;
    }
    if (family === "impulse_response") {
      if (index !== 1) return base;
      const shift = Math.round(stateNumber(values, "shift", 0) + stateNumber(values, "step", 0));
      return base.map(([sample, value]) => [sample + shift, value]);
    }
    if (family === "double_slit") {
      const separation = Math.max(0.2, stateNumber(values, "slit_separation", 1.2)); const wavelength = Math.max(0.1, stateNumber(values, "wavelength", 0.5));
      if (layer.label === "intensity") return xs.map((x) => { const geometry = doubleSlitGeometry(separation, x); return [x, Math.cos(Math.PI * geometry.pathDifference / wavelength) ** 2]; });
      if (layer.label === "opaque barrier upper") return [[-2,3],[-2,separation/2+0.12]];
      if (layer.label === "opaque barrier middle") return [[-2,separation/2-0.12],[-2,-separation/2+0.12]];
      if (layer.label === "opaque barrier lower") return [[-2,-separation/2-0.12],[-2,-3]];
      if (layer.label === "upper-slit path") return [[-3.5,0],doubleSlitGeometry(separation,1.2).upper,[2.8,1.2]];
      if (layer.label === "lower-slit path") return [[-3.5,0],doubleSlitGeometry(separation,1.2).lower,[2.8,1.2]];
      if (layer.label === "path difference Δℓ") {
        const geometry = doubleSlitGeometry(separation, 1.2);
        const longer = geometry.lowerLength >= geometry.upperLength ? geometry.lower : geometry.upper;
        const length = Math.max(1e-9, Math.hypot(geometry.screen[0] - longer[0], geometry.screen[1] - longer[1]));
        const cueLength = Math.min(0.9, geometry.pathDifference * 3);
        return [[geometry.screen[0] - cueLength * (geometry.screen[0] - longer[0]) / length, geometry.screen[1] - cueLength * (geometry.screen[1] - longer[1]) / length], geometry.screen];
      }
      return base;
    }
    if (family === "kepler_orbit") {
      const eccentricity = Math.max(0, Math.min(0.9, stateNumber(values, "eccentricity", 1) / 10));
      const theta = stateNumber(values, "true_anomaly", 0) * Math.PI / 10 + stateNumber(values, "playback", 0) * Math.PI / 8;
      const position = (angle) => { const radius = 3 * (1 - eccentricity * eccentricity) / (1 + eccentricity * Math.cos(angle)); return [radius * Math.cos(angle), radius * Math.sin(angle)]; };
      if (layer.label === "radius vector") return [[0, 0], position(theta)];
      if (layer.label === "velocity vector tangent to orbit") { const point = position(theta); const direction = [-Math.sin(theta), eccentricity + Math.cos(theta)]; const norm = Math.hypot(...direction) || 1; return [point, [point[0] + direction[0] / norm, point[1] + direction[1] / norm]]; }
      if (layer.label === "acceleration vector toward focus") { const point = position(theta); const norm = Math.hypot(...point) || 1; return [point, [point[0] - point[0] / norm, point[1] - point[1] / norm]]; }
      if (layer.label === "equal-area sweep sector") { const point = position(theta); const radius = Math.hypot(...point); const delta = Math.min(0.8, 0.7 / Math.max(0.2, radius * radius)); return [[0, 0], point, position(theta + delta), [0, 0]]; }
      return base.map((_point, step) => {
        const theta = 2 * Math.PI * step / Math.max(1, base.length - 1);
        const radius = 3 * (1 - eccentricity * eccentricity) / (1 + eccentricity * Math.cos(theta));
        return [radius * Math.cos(theta), radius * Math.sin(theta)];
      });
    }
    if (family === "coupled_oscillators") {
      const alternate = values.mode === "alternate";
      const motion = stateNumber(values, "playback", 0) * Math.PI / 8 + stateNumber(values, "__animation_progress", 0) * 2 * Math.PI;
      // The labelled reference traces always show both normal modes. The selector below
      // changes the physical mass motion without collapsing these teaching traces.
      const phase = (index ? Math.PI : 0) + motion;
      if (index >= 2) {
        const first = -1.25 + 0.42 * Math.sin(motion);
        const second = 1.25 + 0.42 * Math.sin(motion + (alternate ? Math.PI : 0));
        const spring = (start, end) => Array.from({ length: 13 }, (_unused, step) => {
          const ratio = step / 12;
          return [start + (end - start) * ratio, step === 0 || step === 12 ? 0 : (step % 2 ? 0.24 : -0.24)];
        });
        return [...spring(-4, first - 0.18), ...spring(first + 0.18, second - 0.18), ...spring(second + 0.18, 4)];
      }
      return xs.map((x) => [x, Math.sin(x + phase)]);
    }
    if (family === "doppler") {
      const speed = stateNumber(values, "source_speed", 1) / 4;
      const radius = 2.2 - 0.7 * index;
      const center = speed * (index - 1 + stateNumber(values, "playback", 0) / 4);
      return base.map((_point, step) => { const t = 2 * Math.PI * step / Math.max(1, base.length - 1); return [center + radius * Math.cos(t), radius * Math.sin(t)]; });
    }
    if (family === "electric_field_lines") {
      const leftPosition = Math.min(-0.2, stateNumber(values, "charge_1", -1)); const rightPosition = Math.max(0.2, stateNumber(values, "charge_2", 1));
      const angle = 2 * Math.PI * index / Math.max(1, 10);
      const points = []; let x = leftPosition + 0.16 * Math.cos(angle); let y = 0.16 * Math.sin(angle);
      for (let step = 0; step < 120; step += 1) {
        points.push([x, y]);
        const field = (cx, charge) => { const dx = x - cx; const r2 = Math.max(0.04, dx * dx + y * y); const gain = charge / (r2 * Math.sqrt(r2)); return [gain * dx, gain * y]; };
        const left = field(leftPosition, 1); const right = field(rightPosition, -1); const ex = left[0] + right[0]; const ey = left[1] + right[1]; const length = Math.hypot(ex, ey) || 1;
        x += 0.055 * ex / length; y += 0.055 * ey / length;
        if (Math.hypot(x - rightPosition, y) < 0.16 || Math.abs(x) > 4 || Math.abs(y) > 4) break;
      }
      return points.length >= 2 ? points : base;
    }
    if (family === "electric_field_vectors") {
      const px = stateNumber(values, "test_x", 1); const py = stateNumber(values, "test_y", 2);
      const origins = [[-2, 1.5], [2, 1.5], [px, py]];
      const origin = origins[index] || origins[0];
      const field = (cx, charge) => { const dx = origin[0] - cx; const dy = origin[1]; const r2 = Math.max(0.05, dx * dx + dy * dy); const gain = charge / (r2 * Math.sqrt(r2)); return [gain * dx, gain * dy]; };
      const left = field(-1, 1); const right = field(1, -1); const ex = left[0] + right[0]; const ey = left[1] + right[1]; const length = Math.hypot(ex, ey) || 1;
      return [origin, [origin[0] + 0.8 * ex / length, origin[1] + 0.8 * ey / length]];
    }
    if (family === "magnetic_field_wire") {
      if (index < 3) return base;
      const direction = values.current_direction === "reverse" ? -1 : 1;
      return [[0, base[0][1]], [0.42 * direction, base[0][1]]];
    }
    if (family === "blackbody") {
      const selected = Math.max(0.4, stateNumber(values, "temperature", 1));
      const temperature = index < 2 ? [1.2,1.7][index] : selected;
      return base.map((point) => { const w = Math.max(0.05, point[0]); return [w, w ** -5 / Math.max(1e-9, Math.exp(Math.min(40, 5 / (w * temperature))) - 1)]; });
    }
    if (family === "kinetics") {
      const order = Math.max(0, Math.min(2, Math.round(stateNumber(values, "order", 1))));
      const rate = Math.max(0.01, stateNumber(values, "rate_constant", 0.35));
      const concentration = (selected, time) => selected === 0
        ? Math.max(0, 1 - rate * time)
        : selected === 1 ? Math.exp(-rate * time) : 1 / (1 + rate * time);
      return base.map(([time]) => {
        if (index === 0) return [time, concentration(0, time)];
        if (index === 1) return [time, concentration(1, time)];
        if (index === 2) return [time, concentration(2, time)];
        if (index === 3) return [time, 1 - rate * time];
        if (index === 4) return [time, -rate * time];
        if (index === 5) return [time, 1 + rate * time];
        return [time, concentration(order, time)];
      });
    }
    if (family === "enzyme_kinetics") {
      const inhibitor = Math.max(0, stateNumber(values, "inhibitor", 2));
      const apparentKm = index === 0 ? 1.5 : 1.5 * (1 + inhibitor / 2);
      return base.map(([concentration]) => [concentration, concentration / (apparentKm + concentration)]);
    }
    if (family === "bode_plot") {
      const cutoff = Math.max(0.1, stateNumber(values, "cutoff", 1));
      return xs.map((x) => {
        const ratio = 10 ** x / cutoff;
        return [x, index === 0 ? -10 * Math.log10(1 + ratio ** 2) : -Math.atan(ratio) * 180 / Math.PI];
      });
    }
    if (family === "nyquist") {
      const gain = Math.max(0.1, stateNumber(values, "gain", 1));
      return base.map((point) => [gain * point[0], gain * point[1]]);
    }
    if (family === "pid_response") {
      const kp = Math.max(0, stateNumber(values, "kp", 1)); const ki = Math.max(0, stateNumber(values, "ki", 2)); const kd = Math.max(0, stateNumber(values, "kd", 3));
      const times = Array.from({ length: 101 }, (_unused, sample) => sample / 10);
      const responses = [0,1,2].map((responseIndex) => times.map((time) => {
        if (responseIndex === 0) return [time, (kp / Math.max(0.1, 1 + kp)) * (1 - Math.exp(-(0.4 + kp / 5) * time))];
        if (responseIndex === 1) return [time, 1 - Math.exp(-(0.35 + ki / 10) * time) * Math.cos((0.8 + ki / 10) * time)];
        return [time, 1 - Math.exp(-(0.55 + kd / 8) * time) * (Math.cos((0.9 + kp / 10) * time) + 0.25 * Math.sin((0.9 + ki / 10) * time))];
      }));
      if (index < 3) return responses[index];
      const pid = responses[2]; const rise = pid.find((point) => point[1] >= 0.9) || pid.at(-1);
      const peak = pid.reduce((best, point) => point[1] > best[1] ? point : best, pid[0]); const final = pid.at(-1);
      if (index === 3) return [[rise[0], 0], rise];
      if (index === 4) return [[peak[0], 1], peak];
      return [[final[0], final[1]], [final[0], 1]];
    }
    if (family === "beam_bending") {
      const length = 10; const load = 10; const at = Math.max(0.5, Math.min(9.5, stateNumber(values, "load_position", 5)));
      const leftReaction = load * (length - at) / length; const rigidity = 100;
      if (layer.label === "simply supported beam") return [[0,0],[length,0]];
      if (layer.label === "left pin support") return [[-0.35,-0.5],[0,0],[0.35,-0.5],[-0.35,-0.5]];
      if (layer.label === "right roller support") return [[9.65,-0.5],[10,0],[10.35,-0.5],[9.65,-0.5]];
      if (layer.label === "moving point load 10") return [[at,2],[at,0]];
      if (layer.label === "left support reaction") return [[0,-0.5],[0,leftReaction/5]];
      if (layer.label === "right support reaction") return [[length,-0.5],[length,(load-leftReaction)/5]];
      return base.map(([x]) => {
        if (layer.label === "shear V(x)") return [x, x < at ? leftReaction : leftReaction - load];
        if (layer.label === "bending moment M(x)") return [x, x <= at ? leftReaction * x : leftReaction * x - load * (x - at)];
        const deflection = x <= at
          ? -load * (length - at) * x * (length ** 2 - (length - at) ** 2 - x ** 2) / (6 * length * rigidity)
          : -load * at * (length - x) * (length ** 2 - at ** 2 - (length - x) ** 2) / (6 * length * rigidity);
        return [x, deflection];
      });
    }
    if (family === "logistic_map") {
      const growth = stateNumber(values, "growth_rate", 3.72); let value = stateNumber(values, "initial_value", 0.21);
      if (layer.label === "iterate xₙ versus n") return base.map((_point, step) => { const result = [step, value]; value = Math.max(0, Math.min(1, growth * value * (1 - value))); return result; });
      if (layer.label === "logistic map y=r x(1−x)") return base.map(([x])=>[x,growth*x*(1-x)]);
      if (layer.label === "cobweb iteration") { const points=[]; for(let step=0;step<32;step+=1){const next=growth*value*(1-value); points.push([value,value],[value,next],[next,next]); value=next;} return points; }
      return base;
    }
    if (family === "pwm") {
      const duty = stateNumber(values, "duty_cycle", 0.45);
      if (index === 1) return [[0, duty], [20, duty]];
      const points = [];
      for (let pulse = 0; pulse < 20; pulse += 1) points.push([pulse, 0], [pulse, 1], [pulse + duty, 1], [pulse + duty, 0]);
      return points;
    }
    if (family === "differential_drive") {
      const left = stateNumber(values, "left_velocity", 1); const right = stateNumber(values, "right_velocity", 2);
      const curvature = Math.abs(right - left) < 1e-6 ? 0 : (right - left) / Math.max(0.2, Math.abs(left + right));
      if (index === 0) return base.map((_point, step) => { const t = step / Math.max(1, base.length - 1); return Math.abs(curvature) < 1e-6 ? [6 * t - 3, 0] : [Math.sin(4 * curvature * t) / curvature, (1 - Math.cos(4 * curvature * t)) / curvature]; });
      if (index === 4) {
        const radius = Math.abs(curvature) < 1e-6 ? 8 : Math.max(-8, Math.min(8, 1 / curvature));
        return [[0, 0], [0, radius]];
      }
      return base;
    }
    if (family === "predator_prey") {
      const preyGrowth = Math.max(0.05, stateNumber(values, "prey_growth", 1) / 8);
      const predation = Math.max(0.05, stateNumber(values, "predation", 2) / 10);
      let prey = 1.4; let predator = 0.8; const series = [];
      for (let step = 0; step < base.length; step += 1) {
        series.push(index === 2 ? [prey, predator] : [step * 0.04, index === 0 ? prey : predator]);
        const nextPrey = Math.max(0, prey + 0.04 * (preyGrowth * prey - predation * prey * predator));
        const nextPredator = Math.max(0, predator + 0.04 * (0.18 * prey * predator - 0.22 * predator));
        prey = nextPrey; predator = nextPredator;
      }
      const playback = Math.round(stateNumber(values, "playback", 0)) % Math.max(1, series.length);
      return series.map((_point, seriesIndex) => series[(seriesIndex + playback) % series.length]);
    }
    if (family === "spectrogram") {
      const sweep = Math.max(0.1, stateNumber(values, "sweep_rate", 1)); const phase = stateNumber(values, "playback", 0) / 5;
      return xs.map((x) => [x, Math.sin(2 * Math.PI * (2 * x + 5 * sweep * x * x + phase))]);
    }
    if (family === "heat_diffusion") {
      const time = Math.max(0.05, stateNumber(values, "time", 1) + stateNumber(values, "playback", 0));
      const spread = Math.sqrt(0.2 + time / 3);
      return xs.map((x) => [x, Math.exp(-x * x / (2 * spread * spread)) / spread]);
    }
    if (family === "fluid_flow") {
      const speed = Math.max(0.05, stateNumber(values, "speed", 1));
      if (index === 8) return [[-3.8, -2.9], [-3.8 + speed, -2.9]];
      return base;
    }
    if (family === "decision_boundary") {
      const state = classifierState(values);
      if (layer.label.includes("training loss")) return state.loss;
      return xs.map((x) => {
        let best = [-3, Infinity];
        for (let sample = 0; sample <= 120; sample += 1) {
          const y = -3 + 6 * sample / 120; const residual = Math.abs(state.predict([x, y]).probability - 0.5);
          if (residual < best[1]) best = [y, residual];
        }
        return [x, best[0]];
      });
    }
    if (family === "kalman_filter") {
      const records = kalmanSequence(values); const selected = records[Math.max(0, Math.min(20, Math.round(stateNumber(values, "step", 0))))];
      if (layer.label === "true moving-point trajectory") return records.map((record)=>[record.step,record.truth]);
      if (layer.label === "noisy measurements") return records.map((record)=>[record.step,record.measurement]);
      if (layer.label === "Kalman estimate trajectory") return records.map((record)=>[record.step,record.estimate]);
      const centre = layer.label.includes("P⁻") ? [selected.step,selected.prior] : [selected.step,selected.estimate];
      const radius = Math.sqrt(layer.label.includes("P⁻") ? selected.predictedVariance : selected.variance);
      return base.map((_point,index)=>{const angle=2*Math.PI*index/Math.max(1,base.length-1); return [centre[0]+0.25*Math.cos(angle),centre[1]+radius*Math.sin(angle)];});
    }
    if (family === "uncertainty_propagation") {
      const densities = uncertaintySamples(values).map(([volume, mass]) => mass / volume);
      const low = Math.min(...densities); const high = Math.max(...densities); const bins = 24; const counts = Array(bins).fill(0);
      densities.forEach((density) => { const slot = Math.min(bins - 1, Math.floor((density - low) / Math.max(1e-12, high - low) * bins)); counts[slot] += 1; });
      const width = (high - low) / bins;
      return counts.map((count, slot) => [low + (slot + 0.5) * width, count / Math.max(1, densities.length) / Math.max(1e-12, width)]);
    }
    return base;
  }

  function evaluatedProbe(layer, values) {
    if (Object.hasOwn(values, "positive_charge_x") || Object.hasOwn(values, "negative_charge_x")) {
      const positive = stateNumber(values, "positive_charge_x", -1); const negative = stateNumber(values, "negative_charge_x", 1);
      const origin = [stateNumber(values, "test_x", (positive + negative) / 2), stateNumber(values, "test_y", 1.5)];
      const field = (centre, charge) => { const dx=origin[0]-centre; const dy=origin[1]; const r2=Math.max(0.05,dx*dx+dy*dy); const gain=charge/(r2*Math.sqrt(r2)); return [gain*dx,gain*dy]; };
      const left=field(positive,1); const right=field(negative,-1); const dx=left[0]+right[0]; const dy=left[1]+right[1]; const magnitude=Math.max(1,Math.hypot(dx,dy));
      return [origin,[origin[0]+0.65*dx/magnitude,origin[1]+0.65*dy/magnitude]];
    }
    const px = stateNumber(values, layer.x_control, 0);
    const py = stateNumber(values, layer.y_control, 0);
    try {
      const variables = { x: px, y: py, z: 0, t: 0, u: 0, v: 0 };
      const dx = global.MutaViz.evaluateExpressionV2(layer.x_expression, variables);
      const dy = global.MutaViz.evaluateExpressionV2(layer.y_expression, variables);
      const factor = layer.scale / Math.max(1, Math.hypot(dx, dy));
      return [[px, py], [px + dx * factor, py + dy * factor]];
    } catch {
      return [[px, py], [px + 0.001, py]];
    }
  }

  function controlledVectors(family, layer, values) {
    if (family !== "electric_field_vectors") return layer.vectors;
    const positive = stateNumber(values, "positive_charge_x", -1); const negative = stateNumber(values, "negative_charge_x", 1);
    return layer.vectors.map(([x, y]) => {
      const field = (centre, charge) => { const dx=x-centre; const r2=Math.max(0.05,dx*dx+y*y); const gain=charge/(r2*Math.sqrt(r2)); return [gain*dx,gain*y]; };
      const left=field(positive,1); const right=field(negative,-1); const dx=left[0]+right[0]; const dy=left[1]+right[1]; const scaleValue=0.55/Math.max(0.55,Math.hypot(dx,dy));
      return [x,y,dx*scaleValue,dy*scaleValue];
    });
  }

  function controlledParticles(family, layer, values) {
    if (family === "electric_field_vectors" && layer.label.includes("source charges")) {
      return [[stateNumber(values,"positive_charge_x",-1),0],[stateNumber(values,"negative_charge_x",1),0]];
    }
    if (family === "robot_localization") {
      const localization = localizationState(values); const centre = localization.selected.estimate;
      const spreadX = localization.uncertainty.x; const spreadY = localization.uncertainty.y;
      return Array.from({ length: Math.min(48, layer.points.length) }, (_unused, index) => {
        const angle = index * 2.399963; const radius = Math.sqrt((index + 0.5) / 48);
        return [centre[0] + spreadX * radius * Math.cos(angle), centre[1] + spreadY * radius * Math.sin(angle)];
      });
    }
    if (family === "harmonic_motion" && layer.label.includes("moving mass")) {
      const omega=Math.sqrt(Math.max(0.1,stateNumber(values,"spring_constant",1))/Math.max(0.1,stateNumber(values,"mass",2)));
      const displacement=Math.cos(omega*stateNumber(values,"__animation_progress",0)*2*Math.PI);
      return [[displacement,0],[displacement+0.001,0]];
    }
    if (family === "kalman_filter") {
      const records=kalmanSequence(values); const selected=records[Math.max(0,Math.min(20,Math.round(stateNumber(values,"step",0))))];
      const point=layer.label.includes("true") ? [selected.step,selected.truth] : layer.label.includes("measurement") ? [selected.step,selected.measurement] : [selected.step,selected.estimate];
      return [point,[point[0]+0.001,point[1]]];
    }
    if (family === "coupled_oscillators" && layer.label.includes("moving masses")) {
      const alternate = values.mode === "alternate";
      const motion = stateNumber(values, "playback", 0) * Math.PI / 8 + stateNumber(values, "__animation_progress", 0) * 2 * Math.PI;
      return [[-1.25 + 0.42 * Math.sin(motion), 0], [1.25 + 0.42 * Math.sin(motion + (alternate ? Math.PI : 0)), 0]];
    }
    if (family === "standing_wave") {
      const harmonic = Math.max(1, Math.round(stateNumber(values, "harmonic", 1)));
      if (layer.label.includes("nodes")) return Array.from({ length: harmonic + 1 }, (_unused, index) => [-4 + 8 * index / harmonic, 0]);
      return Array.from({ length: harmonic }, (_unused, index) => [-4 + 8 * (index + 0.5) / harmonic, index % 2 ? -1 : 1]);
    }
    if (family === "projectile") {
      const angle = stateNumber(values, "angle", 45) * Math.PI / 180;
      const speed = stateNumber(values, "speed", 20);
      const range = speed * speed * Math.sin(2 * angle) / 9.81;
      const maximum = speed * speed * Math.sin(angle) ** 2 / 19.62;
      return [[range / 2, maximum], [range, 0]];
    }
    if (family === "travelling_wave" && layer.label === "crest and trough") {
      const amplitude = stateNumber(values, "amplitude", 1);
      const wavelength = Math.max(0.1, stateNumber(values, "wavelength", 2));
      const phase = stateNumber(values, "frequency", 1) * 0.15;
      let crest = (Math.PI / 2 - phase) * wavelength / (2 * Math.PI);
      while (crest < -3.5) crest += wavelength;
      while (crest > 3.5) crest -= wavelength;
      return [[crest, amplitude], [crest + wavelength / 2, -amplitude]];
    }
    if (family === "atom" && layer.label.includes("electrons")) {
      const count = Math.max(1, Math.min(18, Math.round(stateNumber(values, "atomic_number", 6))));
      const shellCapacity = [2, 8, 8]; const points = []; let remaining = count;
      shellCapacity.forEach((capacity, shellIndex) => {
        const shellCount = Math.min(capacity, remaining); remaining -= shellCount;
        for (let electron = 0; electron < shellCount; electron += 1) {
          const angle = 2 * Math.PI * electron / Math.max(1, shellCount) + shellIndex * 0.23;
          points.push([(shellIndex + 1) * Math.cos(angle), (shellIndex + 1) * Math.sin(angle)]);
        }
      });
      return points;
    }
    if (family === "atom" && layer.label.includes("nuclear")) {
      const count = Math.max(1, Math.min(18, Math.round(stateNumber(values, "atomic_number", 6))));
      const neutron = layer.label.includes("neutrons");
      return Array.from({ length: count }, (_unused, index) => {
        const ring = Math.floor(Math.sqrt(index)); const angle = index * 2.399963; const radius = 0.08 + ring * 0.075;
        return [radius * Math.cos(angle) + (neutron ? 0.025 : -0.025), radius * Math.sin(angle)];
      });
    }
    if (family === "ideal_gas" && layer.label.includes("consistent state")) {
      const pressure = Math.max(0.1, stateNumber(values, "pressure", 2));
      const volume = Math.max(0.1, stateNumber(values, "volume", 2));
      const temperature = Math.max(0.1, stateNumber(values, "temperature", 4));
      return [[volume, pressure], [volume + 0.001, pressure + 0.001 * temperature]];
    }
    if (family === "lagrange_multiplier" && layer.label.includes("constrained minimum")) {
      const optimum = stateNumber(values, "constraint_offset", 1) / 2;
      return [[optimum, optimum], [optimum + 0.001, optimum + 0.001]];
    }
    if (family === "entropy_cycle" && layer.label.includes("synchronized state")) {
      const phase = Math.max(0, Math.round(stateNumber(values, "step", 0))) % 4;
      const states = layer.label.startsWith("P–V") ? [[1,4],[3,2.5],[4,1],[1.5,1.8]] : [[1,4],[3,4],[3,2],[1,2]];
      const point = states[phase]; return [point, [point[0] + 0.001, point[1]]];
    }
    if (family === "doppler" && layer.label.includes("moving source")) {
      const source = stateNumber(values, "source_speed", 1) * stateNumber(values, "playback", 0) / 16;
      return [[source, 0], [source + 0.001, 0]];
    }
    if (family === "kepler_orbit" && layer.label.includes("satellite")) {
      const eccentricity = Math.max(0, Math.min(0.9, stateNumber(values, "eccentricity", 1) / 10));
      const theta = stateNumber(values, "true_anomaly", 0) * Math.PI / 10 + stateNumber(values, "playback", 0) * Math.PI / 8;
      const radius = 3 * (1 - eccentricity * eccentricity) / (1 + eccentricity * Math.cos(theta));
      return [[radius * Math.cos(theta), radius * Math.sin(theta)], [radius * Math.cos(theta) + 0.001, radius * Math.sin(theta)]];
    }
    if (family === "electric_field_lines") return [[Math.min(-0.2, stateNumber(values, "charge_1", -1)), 0], [Math.max(0.2, stateNumber(values, "charge_2", 1)), 0]];
    if (family === "quadratic") {
      const a = stateNumber(values, "a", 1); const b = stateNumber(values, "b", 0); const c = stateNumber(values, "c", 0);
      const vertexX = Math.abs(a) < 1e-9 ? 0 : -b / (2 * a); const vertex = [vertexX, a * vertexX * vertexX + b * vertexX + c];
      if (layer.label === "vertex") return [vertex];
      const discriminant = b * b - 4 * a * c;
      if (Math.abs(a) < 1e-9 || discriminant < 0) return [];
      const root = Math.sqrt(discriminant);
      return [[(-b - root) / (2 * a), 0], [(-b + root) / (2 * a), 0]];
    }
    if (family === "enzyme_kinetics") {
      const substrate = Math.max(0, stateNumber(values, "substrate", 1));
      const inhibitor = Math.max(0, stateNumber(values, "inhibitor", 2));
      return [[substrate, substrate / (1.5 + substrate)], [substrate, substrate / (1.5 * (1 + inhibitor / 2) + substrate)]];
    }
    if (family === "uncertainty_propagation") {
      return uncertaintySamples(values);
    }
    if (family === "polar_plot" && layer.label === "traversal point") {
      const theta = (stateNumber(values,"theta",0)+18*stateNumber(values,"playback",0))*Math.PI/180; const radius=Math.cos(2*theta); const point=[radius*Math.cos(theta),radius*Math.sin(theta)]; return [point,[point[0]+0.001,point[1]]];
    }
    if (family === "fourier_series" && layer.label.includes("Gibbs")) {
      const terms=Math.max(1,Math.round(stateNumber(values,"terms",5))); const value=(x)=>Array.from({length:terms},(_u,k)=>Math.sin((2*k+1)*x)/(2*k+1)).reduce((sum,item)=>sum+item,0)*4/Math.PI; const epsilon=Math.PI/(2*(2*terms+1)); return [[-Math.PI+epsilon,value(-Math.PI+epsilon)],[epsilon,value(epsilon)],[Math.PI+epsilon,value(Math.PI+epsilon)]];
    }
    if (family === "convolution" && layer.label.includes("overlap-area")) {
      const shift=stateNumber(values,"shift",0)+stateNumber(values,"step",0)*0.2; const area=Math.max(0,2-Math.abs(shift)); return [[shift,area],[shift+0.001,area]];
    }
    if (family === "blackbody" && layer.label.includes("Wien")) {
      const temperatures=[1.2,1.7,Math.max(0.4,stateNumber(values,"temperature",2.2))]; return temperatures.map((temperature)=>{let best=[0.1,0]; for(let index=0;index<80;index+=1){const w=0.1+index*0.05; const y=w**-5/Math.max(1e-9,Math.exp(Math.min(40,5/(w*temperature)))-1); if(y>best[1]) best=[w,y];} return best;});
    }
    if (family === "equilibrium_shift" && layer.label.includes("molecule population")) {
      const pressure=Math.max(0.1,stateNumber(values,"pressure",1)); const temperature=Math.max(1,stateNumber(values,"temperature",450)); const product=pressure/(pressure+Math.exp((temperature-450)/180));
      const count=layer.label.startsWith("NH₃") ? Math.max(1,Math.round(2+10*product)) : layer.label.startsWith("H₂") ? Math.max(3,3*Math.round(1+3*(1-product))) : Math.max(1,Math.round(1+3*(1-product)));
      const centre=layer.label.startsWith("NH₃") ? 535 : layer.label.startsWith("H₂") ? 285 : 155;
      return Array.from({length:count},(_unused,index)=>[centre+(index%5-2)*24,190+Math.floor(index/5)*26]);
    }
    if (family !== "sampling_aliasing") return layer.points;
    const signal = Math.max(0.1, stateNumber(values, "signal_frequency", 4));
    const sampleRate = Math.max(1, Math.min(80, stateNumber(values, "sample_frequency", 12)));
    const count = Math.max(2, Math.round(sampleRate) + 1);
    return Array.from({ length: count }, (_unused, index) => {
      const time = index / (count - 1);
      return [time, Math.sin(2 * Math.PI * signal * time)];
    });
  }

  function controlledHeatmap(family, layer, values) {
    if (family === "spectrogram") {
      const sweep = Math.max(0.1, stateNumber(values, "sweep_rate", 1));
      return Array.from({ length: layer.rows * layer.columns }, (_unused, offset) => {
        const row = Math.floor(offset / layer.columns); const column = offset % layer.columns;
        const center = 2 + 10 * sweep * column / Math.max(1, layer.columns - 1);
        return Math.exp(-0.5 * ((row - center) / 1.35) ** 2);
      });
    }
    if (family === "heat_diffusion") {
      const time = Math.max(0.05, stateNumber(values, "time", 1));
      const spread = Math.sqrt(0.15 + time / 4);
      return Array.from({ length: layer.rows * layer.columns }, (_unused, offset) => {
        const column = offset % layer.columns;
        const position = layer.x_domain[0] + (layer.x_domain[1] - layer.x_domain[0]) * column / Math.max(1, layer.columns - 1);
        return Math.exp(-position * position / (2 * spread * spread)) / spread;
      });
    }
    if (family === "decision_boundary") {
      const state = classifierState(values);
      return Array.from({ length: layer.rows * layer.columns }, (_unused, offset) => {
        const row = Math.floor(offset / layer.columns); const column = offset % layer.columns;
        const x = layer.x_domain[0] + (layer.x_domain[1] - layer.x_domain[0]) * column / Math.max(1, layer.columns - 1);
        const y = layer.y_domain[0] + (layer.y_domain[1] - layer.y_domain[0]) * row / Math.max(1, layer.rows - 1);
        return state.predict([x, y]).probability - 0.5;
      });
    }
    return layer.values;
  }

  function stateDescription(spec, values) {
    const v = (id, fallback) => stateNumber(values, id, fallback);
    if (spec.family === "pythagoras") return `a = ${v("a", 3).toFixed(1)}, b = ${v("b", 4).toFixed(1)}, c = ${Math.hypot(v("a", 3), v("b", 4)).toFixed(2)}; a² + b² = c².`;
    if (spec.family === "quadratic") { const a = v("a", 1); const b = v("b", 0); const c = v("c", 0); const x = Math.abs(a) < 1e-9 ? NaN : -b / (2 * a); return `a=${a.toFixed(2)}, b=${b.toFixed(2)}, c=${c.toFixed(2)}; vertex (${Number.isFinite(x) ? x.toFixed(2) : "undefined"}, ${Number.isFinite(x) ? (a*x*x+b*x+c).toFixed(2) : "undefined"}).`; }
    if (spec.family === "line_intersection") { const denominator = v("m1",1)-v("m2",-1); return Math.abs(denominator)<1e-9 ? (Math.abs(v("c1",0)-v("c2",2))<1e-9 ? "The lines are identical." : "The lines are parallel.") : `Intersection x = ${((v("c2",2)-v("c1",0))/denominator).toFixed(2)}.`; }
    if (spec.family === "linear_transform") { const matrix=String(values.matrix||"identity"); return matrix === "shear" ? "Shear matrix: λ=1 is repeated, but only the x-axis supplies an independent real eigenvector." : matrix === "scale" ? "Diagonal scale: e₁ and e₂ keep direction with eigenvalues 1.60 and 0.65." : "Identity: every nonzero vector is an eigenvector with λ=1."; }
    if (spec.family === "vector_addition") return "Head-to-tail and parallelogram constructions agree: a=(3,2), b=(1,4), and a+b=(4,6).";
    if (spec.family === "binary_representation") return "Place values 8, 4, 2, 1 with bits 1, 1, 0, 1 give 8+4+0+1=13, so 13₁₀=1101₂.";
    if (spec.family === "gradient_linked") { const x=v("point_x",1); const y=v("point_y",1); return `Linked point (${x.toFixed(2)}, ${y.toFixed(2)}) has f=x²+y²=${(x*x+y*y).toFixed(3)} and gradient ∇f=(${(2*x).toFixed(2)}, ${(2*y).toFixed(2)}) in both views.`; }
    if (spec.family === "gradient_descent") { const descent=gradientDescentState(values); const point=descent.selected; return `Gradient descent step ${descent.requestedStep}: learning rate ${descent.learningRate.toFixed(2)}, point (${point.x.toFixed(3)}, ${point.y.toFixed(3)}), loss x²+2y²=${point.loss.toFixed(4)}; both views show the same trajectory.`; }
    if (spec.family === "robot_localization") { const localization=localizationState(values); const record=localization.selected; const error=Math.hypot(record.estimate[0]-record.truth[0],record.estimate[1]-record.truth[1]); return `Localization step ${localization.requestedStep}: true pose (${record.truth[0].toFixed(2)}, ${record.truth[1].toFixed(2)}), noisy odometry (${record.odometry[0].toFixed(2)}, ${record.odometry[1].toFixed(2)}), fused estimate (${record.estimate[0].toFixed(2)}, ${record.estimate[1].toFixed(2)}), position error ${error.toFixed(3)}.`; }
    if (spec.family === "robot_forward_kinematics") { const kinematics=forwardKinematicsState(values); return `Three-link forward kinematics gives end effector (${kinematics.end[0].toFixed(1)}, ${kinematics.end[1].toFixed(1)}) px from cumulative joint angles ${kinematics.angles.map((angle)=>`${(angle*180/Math.PI).toFixed(0)}°`).join(", ")}.`; }
    if (spec.family === "vector_field_3d") { const x=v("point_x",1); const y=v("point_y",1); const z=v("point_z",1); return `At (${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)}), F=(−y,x,z)=(${(-y).toFixed(1)}, ${x.toFixed(1)}, ${z.toFixed(1)}); the selected arrow matches the sampled 3D field.`; }
    if (spec.family === "lorenz_attractor") { const lorenz=lorenzPoints(values); return `Lorenz system σ=${lorenz.sigma.toFixed(1)}, ρ=${lorenz.rho.toFixed(1)}, β=${lorenz.beta.toFixed(3)}; the bounded deterministic trajectory has ${lorenz.points.length} samples across both lobes.`; }
    if (spec.family === "electromagnetic_wave") { const wave=electromagneticWavePoints(values); return `Electromagnetic wave amplitude ${wave.amplitude.toFixed(2)} and wavelength ${wave.wavelength.toFixed(2)}: E ⟂ B, both are perpendicular to propagation k=E×B.`; }
    if (spec.family === "projectile") { const a=v("angle",45)*Math.PI/180; const speed=v("speed",20); return `Range ${(speed*speed*Math.sin(2*a)/9.81).toFixed(1)} m; maximum height ${(speed*speed*Math.sin(a)**2/19.62).toFixed(1)} m.`; }
    if (spec.family === "spring_mass") {
      const spring=Math.max(0.1,v("spring_constant",12));
      if (Object.hasOwn(values,"displacement")) { const displacement=v("displacement",1); return `Hooke's law: k=${spring.toFixed(2)} N/m, x=${displacement.toFixed(2)} m, restoring force F=−kx=${(-spring*displacement).toFixed(2)} N, opposite the displacement.`; }
      return `Hooke equilibrium x=mg/k=${(9.81*v("mass",2)/spring).toFixed(2)} m; upward spring force balances weight.`;
    }
    if (spec.family === "ohms_law_circuit") return `${values.switch ? "Closed" : "Open"} switch: current I = ${values.switch ? "V/R = "+(v("voltage",12)/Math.max(0.01,v("resistance",6))).toFixed(2) : "0.00"} A (V=${v("voltage",12).toFixed(1)} V, R=${v("resistance",6).toFixed(1)} Ω).`;
    if (spec.family === "pendulum") return `Initial angle ${v("angle",20).toFixed(1)}°; small-angle period T = ${2*Math.PI*Math.sqrt(v("length",1)/9.81).toFixed(2)} s for L=${v("length",1).toFixed(2)} m.`;
    if (spec.family === "dna_replication") return `Replication step ${Math.max(Math.round(v("step",0)),Math.round(v("playback",0)))}: both new strands are synthesized 5′→3′; the lagging strand needs repeated primers and ligase-joined Okazaki fragments.`;
    if (spec.family === "nephron") return `Selected ${String(values.segment||"proximal").replaceAll("_"," ")}; arrows preserve filtrate order and labels distinguish water, sodium, and glucose reabsorption.`;
    if (spec.family === "membrane_transport") return `${String(values.transport_mode||"diffusion").replaceAll("_"," ")}: diffusion modes move down the concentration gradient; only active transport uses ATP to move against it.`;
    if (spec.family === "hash_table") { const key=Math.round(v("key",17)); return `${String(values.operation||"insert")} key ${key} at step ${Math.round(v("step",0))}; h(k)=k mod 5 selects bucket ${((key%5)+5)%5}, then separate-chain links are traversed.`; }
    if (spec.family === "graph_traversal") return `${String(values.algorithm||"bfs").toUpperCase()} traverses the same five-node graph; the highlighted nodes and frontier status advance at step ${Math.round(v("step",0))}.`;
    if (spec.family === "binary_search") {
      const items=numbersFromLabel(spec.scene.layers.find((layer)=>layer.id==="array")?.label); const target=v("target",11); const requestedStep=Math.round(v("step",0));
      const trace=[]; let low=0; let high=items.length-1;
      while(low<=high){const mid=Math.floor((low+high)/2); const value=items[mid]; trace.push({low,high,mid,value}); if(value===target) break; if(value<target) low=mid+1; else high=mid-1;}
      const current=trace[Math.min(Math.max(0,requestedStep),Math.max(0,trace.length-1))];
      if(!current) return `Binary search has no values for target ${target}.`;
      if(current.value===target) return `Step ${requestedStep}: found target ${target} at index ${current.mid}.`;
      const direction=current.value<target?"discard left half":"discard right half";
      return `Step ${requestedStep}: compare target ${target} with midpoint ${current.value}; ${direction}, shrinking [${current.low},${current.high}].`;
    }
    if (spec.family === "vector_field") { const diagnostic=vectorFieldDiagnostics(spec,values); return diagnostic ? `At probe (${diagnostic.x.toFixed(2)}, ${diagnostic.y.toFixed(2)}), F=(${diagnostic.fx.toFixed(3)}, ${diagnostic.fy.toFixed(3)}), divergence ∇·F=${diagnostic.divergence.toFixed(3)}, and scalar curl ∂Fᵧ/∂x−∂Fₓ/∂y=${diagnostic.curl.toFixed(3)}.` : "The field is undefined at the selected probe."; }
    if (spec.family === "double_slit") { const separation=Math.max(0.2,v("slit_separation",1.2)); const geometry=doubleSlitGeometry(separation,1.2); return `Slit separation ${separation.toFixed(2)} and wavelength ${Math.max(0.1,v("wavelength",0.5)).toFixed(2)} give exact geometric path difference Δℓ=${geometry.pathDifference.toFixed(3)} at the marked screen point; the intensity uses cos²(πΔℓ/λ).`; }
    if (spec.family === "coupled_oscillators") return `${String(values.mode||"default") === "alternate" ? "Out-of-phase" : "In-phase"} mass motion is selected at playback phase ${v("playback",0).toFixed(1)}; the two reference traces remain separated by π to compare both normal modes.`;
    if (spec.family === "heap") {
      const operation=String(values.operation||"insert"); const value=Math.round(v("value",4)); const step=Math.round(v("step",0));
      return operation === "insert"
        ? `Insert ${value}: place it at the next leaf, then bubble toward the root at step ${step}; every parent remains no greater than either child.`
        : `Extract the minimum root, move the last value to the root, then sift down at step ${step}; the heap property is restored.`;
    }
    if (spec.family === "binary_search_tree") { const inserted=Math.round(v("insert",6)); const step=Math.round(v("step",0)); const state=bstInsertionState(spec.scene.layers,inserted); return state.duplicate ? `Step ${step}: ${inserted} is already in the tree; the search path is ${state.path.join(" → ")} and no duplicate node is added.` : `Step ${step}: insert ${inserted}; compare along ${state.path.join(" → ")}, then attach it ${inserted < Number(String(spec.scene.layers.find((layer)=>layer.id===state.parent)?.label).match(/-?\d+/)?.[0]) ? "left" : "right"} of ${state.parent}.`; }
    if (spec.family === "stack_queue") { const operation=String(values.operation||"add"); const step=Math.max(0,Math.min(3,Math.round(v("step",0)))); return operation === "add" ? `After ${step+1} additions, the stack top and queue rear both receive the newest item; removal will pop newest from the stack but dequeue oldest from the queue.` : `After ${step} removals, the stack has removed newest-first (C,B,A) while the queue has removed oldest-first (A,B,C).`; }
    if (spec.family === "neural_network") { const hasThird=spec.scene.layers.some((layer)=>layer.type==="node"&&layer.id==="h3"); const state=neuralState(values,hasThird); return `Forward step ${Math.round(v("step",0))}: x₁=${state.x1}, x₂=${state.x2}; h₁=ReLU(${state.weight.toFixed(2)}x₁+0.5x₂−0.2)=${state.h1.toFixed(3)}, h₂=${state.h2.toFixed(3)}${hasThird ? `, h₃=${state.h3.toFixed(3)}` : ""}, and sigmoid output ŷ=${state.output.toFixed(3)}.`; }
    if (spec.family === "decision_boundary") { const state=classifierState(values); return `A bounded two-input, two-hidden-unit classifier completed ${state.epochs} batch-gradient epochs at learning rate ${state.learningRate.toFixed(2)}; cross-entropy fell from ${state.loss[0][1].toFixed(3)} to ${state.loss.at(-1)[1].toFixed(3)}, and the visible boundary is p=0.5.`; }
    if (spec.family === "energy_sankey") { const efficiency=Math.max(0,Math.min(1,v("efficiency",0.65))); return `100 J branches into ${(100*efficiency).toFixed(2)} J useful, ${(75*(1-efficiency)).toFixed(2)} J heat, and ${(25*(1-efficiency)).toFixed(2)} J sound; outputs total 100 J.`; }
    if (spec.family === "inclined_plane") { const theta=v("incline",30)*Math.PI/180; const mu=0.2; return `At θ=${v("incline",30).toFixed(0)}°, N=mg cosθ, friction μN with μ=${mu}, and downhill a=max(0,g(sinθ−μcosθ))=${Math.max(0,9.81*(Math.sin(theta)-mu*Math.cos(theta))).toFixed(2)} m/s².`; }
    if (spec.family === "elastic_collision") { const m1=Math.max(0.1,v("mass_1",2)); const u1=v("velocity_1",3); const m2=Math.max(0.1,v("mass_2",3)); const u2=v("velocity_2",-1); const v1=((m1-m2)*u1+2*m2*u2)/(m1+m2); const v2=(2*m1*u1+(m2-m1)*u2)/(m1+m2); const beforeP=m1*u1+m2*u2; const afterP=m1*v1+m2*v2; const beforeE=0.5*m1*u1*u1+0.5*m2*u2*u2; const afterE=0.5*m1*v1*v1+0.5*m2*v2*v2; return `Elastic result: v₁=${v1.toFixed(2)}, v₂=${v2.toFixed(2)}; Δp=${(afterP-beforeP).toExponential(1)}, ΔK=${(afterE-beforeE).toExponential(1)}.`; }
    if (spec.family === "travelling_wave") return `A=${v("amplitude",1).toFixed(2)}, λ=${v("wavelength",2).toFixed(2)}, f=${v("frequency",1).toFixed(2)}; crest and trough lie ±A from equilibrium.`;
    if (spec.family === "standing_wave") return `Harmonic n=${Math.round(v("harmonic",1))}: ${Math.round(v("harmonic",1))+1} nodes include both fixed endpoints, with ${Math.round(v("harmonic",1))} antinodes between them.`;
    if (spec.family === "doppler") return `Playback ${Math.round(v("playback",0))}: the moving source compresses wavefront spacing ahead and stretches it behind; source speed=${v("source_speed",1).toFixed(2)} display units.`;
    if (spec.family === "nyquist") { const gain=Math.max(0.1,v("gain",1)); const winding=Math.abs(1-0.25*gain)<0.2*gain ? 1 : 0; return `Gain ${gain.toFixed(2)}: winding number about −1 is N=${winding}; assuming no open-loop right-half-plane poles, the closed loop is ${winding ? "unstable" : "stable"}.`; }
    if (spec.family === "pid_response") { const kp=Math.max(0,v("kp",1)); const ki=Math.max(0,v("ki",2)); const kd=Math.max(0,v("kd",3)); const times=Array.from({length:101},(_u,i)=>i/10); const response=times.map((time)=>[time,1-Math.exp(-(0.55+kd/8)*time)*(Math.cos((0.9+kp/10)*time)+0.25*Math.sin((0.9+ki/10)*time))]); const rise=(response.find((point)=>point[1]>=0.9)||response.at(-1))[0]; const peak=response.reduce((best,point)=>point[1]>best[1]?point:best,response[0]); const final=response.at(-1)[1]; return `PID metrics: rise time ${rise.toFixed(2)} s, overshoot ${Math.max(0,(peak[1]-1)*100).toFixed(1)}%, steady-state error ${Math.abs(1-final).toFixed(3)}.`; }
    if (spec.family === "titration") { const volume=v("titrant_volume",25); const ph=2+10/(1+Math.exp(-0.35*(volume-25))); return `${volume.toFixed(1)} mL titrant added; curve and probe agree at pH ${ph.toFixed(2)}, with equivalence near 25 mL.`; }
    if (spec.family === "wave_interference") return `The purple resultant is A+B; phase difference ${v("phase",0).toFixed(2)} rad controls constructive and destructive interference.`;
    if (spec.family === "rc_circuit") return `${String(values.mode||"charging")} RC transient with τ=RC=${(v("resistance",4)*v("capacitance",2)/5).toFixed(2)} display units; voltage and current share the circuit state.`;
    if (spec.family === "ac_phase") { const load=String(values.load||"resistive"); return load === "capacitive" ? "Capacitive load: current leads voltage by 90°." : load === "inductive" ? "Inductive load: current lags voltage by 90°." : "Resistive load: current and voltage are in phase."; }
    if (spec.family === "magnetic_field_wire") return String(values.current_direction||"forward") === "reverse" ? "Current reversed: every visible B-field arrow reverses by the right-hand rule." : "Forward current: visible B-field arrows follow the right-hand rule.";
    if (spec.family === "ideal_gas") return `Coupled state P=${v("pressure",2).toFixed(2)}, V=${v("volume",2).toFixed(2)}, T=${v("temperature",4).toFixed(2)}; changing one control updates a dependent variable so P·V=T.`;
    if (spec.family === "atom") return `Atomic number Z=${Math.round(v("atomic_number",6))}: ${Math.round(v("atomic_number",6))} protons and ${Math.round(v("atomic_number",6))} electrons arranged into bounded shells.`;
    if (spec.family === "mitosis") return `Mitosis step ${Math.round(v("step",0))}: chromosomes condense, align, sister chromatids separate, then form two daughter nuclei.`;
    if (spec.family === "circulation") return `Playback ${Math.round(v("playback",0))}: one red blood cell moves body → right heart → lungs → left heart → body; oxygenation changes at the lungs.`;
    if (spec.family === "kepler_orbit") return `At true anomaly ${v("true_anomaly",0).toFixed(2)}, eccentricity ${Math.min(0.9,v("eccentricity",1)/10).toFixed(2)}, playback ${Math.round(v("playback",0))}: velocity is tangent, acceleration points to the focus, and the gold sweep uses a constant areal increment.`;
    if (spec.family === "entropy_cycle") return `Synchronized process ${Math.round(v("step",0))%4 + 1}: the same reversible state is highlighted on the P–V and T–S cycles.`;
    if (spec.family === "ionic_bond") return `Step ${Math.round(v("playback",0))}: sodium transfers one electron to chlorine, producing Na⁺ and Cl⁻ whose opposite charges attract.`;
    if (spec.family === "molecular_orbitals") return String(values.orbital||"bonding") === "antibonding" ? "σ*1s: destructive overlap creates an internuclear node and raises energy." : "σ1s: constructive 1s overlap concentrates density between nuclei and lowers energy.";
    if (spec.family === "animal_cell") { const organelle=String(values.organelle||"nucleus"); const functions={nucleus:"stores DNA",mitochondrion:"makes ATP",ribosome:"builds proteins",rough_er:"folds proteins",golgi:"sorts cargo",lysosome:"digests waste"}; return `${organelle.replaceAll("_"," ")}: ${functions[organelle] || "cell structure"}.`; }
    if (spec.family === "cpu_memory") return `Access step ${Math.round(v("step",0))}: CPU → cache → RAM; a miss triggers a page fault, SSD page-in, then CPU retry.`;
    if (spec.family === "sampling_aliasing") return v("sample_frequency",12) >= 2*v("signal_frequency",4) ? "Nyquist condition satisfied: sampling rate is at least twice the signal frequency." : "Aliasing: sampling rate is below twice the signal frequency.";
    if (spec.family === "molecular_geometry") {
      const molecule = String(values.molecule || "ch4");
      const descriptions = { ch4: "CH₄: tetrahedral, about 109.5°.", nh3: "NH₃: trigonal pyramidal, about 107°.", h2o: "H₂O: bent, about 104.5°.", sf6: "SF₆: octahedral, 90° and 180°.", brf5: "BrF₅: square pyramidal." };
      return descriptions[molecule] || spec.text_fallback;
    }
    if (spec.family === "dijkstra") {
      const result = dijkstraResult(spec.scene.layers, values);
      return result.path.length
        ? `Shortest ${result.path.join(" → ")} has total weight ${result.distance}. Settled: ${result.settled.join(", ") || "none"}.`
        : "No route exists between the selected nodes.";
    }
    if (spec.family === "differential_drive") { const left=v("left_velocity",1); const right=v("right_velocity",2); if (Math.abs(left-right)<1e-9) return "Equal wheel speeds produce a straight path; the instantaneous centre is at infinity."; const curvature=(right-left)/Math.max(0.2,Math.abs(left+right)); return `Wheel speeds (${left.toFixed(1)}, ${right.toFixed(1)}) give signed curvature ${curvature.toFixed(3)} and ICC radius ${(1/curvature).toFixed(2)}.`; }
    if (spec.family === "converging_lens") { const d=Math.max(1.2,v("object_distance",2.5)); const di=d/(d-1); return `Thin-lens check: 1/f = 1/dₒ + 1/dᵢ, with f = 1, dₒ = ${d.toFixed(2)}, dᵢ = ${di.toFixed(2)}, magnification = ${(-di/d).toFixed(2)}.`; }
    if (spec.family === "robot_arm") { const target=Math.hypot(v("target_x",2.5),v("target_y",1.5)); const radius=65*target; const reach=radius>=15-1e-6&&radius<=285+1e-6; return `Two-link IK: L₁ = 150 px, L₂ = 135 px; target radius ${radius.toFixed(1)} px; ${reach ? `${String(values.elbow_mode||"default") === "alternate" ? "elbow-down" : "elbow-up"} solution reaches the target` : "target is unreachable inside the 15 px inner workspace, so the arm stops at the nearest reachable point"}.`; }
    if (spec.family === "truss") { const load=v("load",50); return `Joint equilibrium: ${load.toFixed(0)} kN downward is balanced by ${(load/2).toFixed(1)} kN upward at each support.`; }
    if (spec.family === "kalman_filter") { const records=kalmanSequence(values); const record=records[Math.max(0,Math.min(20,Math.round(v("step",0))))]; return `Step ${record.step}, measurement noise ${v("noise",1).toFixed(2)}, process noise ${v("process_noise",0.08).toFixed(2)}: true position ${record.truth.toFixed(2)}, noisy measurement ${record.measurement.toFixed(2)}, prediction ${record.prior.toFixed(2)} with P⁻=${record.predictedVariance.toFixed(3)}, gain K=${record.gain.toFixed(3)}, update ${record.estimate.toFixed(2)} with contracted P=${record.variance.toFixed(3)}.`; }
    if (spec.family === "kinetics") return `All three integrated rate laws and their linearized forms are shown; selected order ${Math.round(v("order",1))}, k = ${v("rate_constant",0.35).toFixed(2)}.`;
    if (spec.family === "bode_plot") return `First-order low-pass magnitude and phase; at cutoff the response is −3.01 dB and −45°, cutoff ${v("cutoff",1).toFixed(2)}.`;
    if (spec.family === "beam_bending") return `Moving 10-unit point load at x = ${v("load_position",5).toFixed(2)}; reactions sum to the applied load and M(0)=M(L)=0.`;
    if (spec.family === "fluid_flow") return `Potential-flow streamlines remain outside the cylinder; stagnation points are at (−1,0) and (1,0), U = ${v("speed",1).toFixed(2)}.`;
    if (spec.family === "uncertainty_propagation") return `${Math.round(v("samples",160))} deterministic mass-volume samples with σₘ=${v("mass_sigma",0.4).toFixed(2)} and σᵥ=${v("volume_sigma",0.18).toFixed(2)}; every volume is positive and the density histogram represents ρ=m/V.`;
    if (spec.family === "pwm") return `Duty cycle ${(100*v("duty_cycle",0.45)).toFixed(0)}%; average output is the same fraction of supply voltage.`;
    const entries = Object.entries(values).map(([key, value]) => `${key.replaceAll("_", " ")} = ${value}`);
    return entries.length ? entries.join("; ") : spec.text_fallback;
  }

  function dijkstraResult(layers, values) {
    const ids = layers.filter((layer) => layer.type === "node").map((layer) => layer.id);
    const graph = new Map(ids.map((id) => [id, []]));
    layers.filter((layer) => layer.type === "link").forEach((layer) => {
      const weight = Number(layer.label);
      if (!Number.isFinite(weight) || weight < 0 || !graph.has(layer.from) || !graph.has(layer.to)) return;
      graph.get(layer.from).push([layer.to, weight]);
      graph.get(layer.to).push([layer.from, weight]);
    });
    const source = graph.has(String(values.source)) ? String(values.source) : ids[0];
    const destination = graph.has(String(values.destination)) ? String(values.destination) : ids.at(-1);
    const distance = new Map(ids.map((id) => [id, Infinity])); const previous = new Map(); const pending = new Set(ids); const settled = [];
    distance.set(source, 0);
    while (pending.size) {
      const current = [...pending].reduce((best, id) => distance.get(id) < distance.get(best) ? id : best);
      pending.delete(current); if (!Number.isFinite(distance.get(current))) break; settled.push(current);
      for (const [next, weight] of graph.get(current)) {
        if (distance.get(current) + weight < distance.get(next)) { distance.set(next, distance.get(current) + weight); previous.set(next, current); }
      }
    }
    const path = []; let cursor = destination;
    if (Number.isFinite(distance.get(destination))) {
      while (cursor !== undefined) { path.unshift(cursor); if (cursor === source) break; cursor = previous.get(cursor); }
    }
    const step = Math.max(0, Math.min(settled.length, Math.round(stateNumber(values, "step", 0))));
    return { source, destination, path, distance: distance.get(destination), distances: distance, settled: settled.slice(0, step) };
  }

  function controlledNode(spec, layer, index, values, changedId) {
    const node = { ...layer };
    const step = Math.max(0, Math.round(stateNumber(values, "step", stateNumber(values, "playback", 0))));

    if (spec.family === "robot_forward_kinematics") {
      const kinematics = forwardKinematicsState(values);
      const jointIndex = Number(layer.id.split("_")[1]);
      const point = kinematics.points[jointIndex];
      if (point) { node.x = point[0]; node.y = point[1]; }
      if (jointIndex === 3) node.label = `end effector (${kinematics.end[0].toFixed(1)}, ${kinematics.end[1].toFixed(1)})`;
      else if (jointIndex > 0) node.label = `joint ${jointIndex} • θ${jointIndex}=${(kinematics.angles[jointIndex - 1] * 180 / Math.PI).toFixed(0)}°`;
      return node;
    } else if (spec.family === "binary_search") {
      const arrayLayer = spec.scene.layers.find((candidate) => candidate.type === "node" && candidate.id === "array");
      const items = numbersFromLabel(arrayLayer?.label); const target = stateNumber(values, "target", 11);
      const trace = []; let low = 0; let high = items.length - 1;
      while (low <= high) {
        const mid = Math.floor((low + high) / 2); const value = items[mid];
        trace.push({ low, high, mid, value, outcome: value === target ? "found" : value < target ? "discard left" : "discard right" });
        if (value === target) break; if (value < target) low = mid + 1; else high = mid - 1;
      }
      if (!trace.length || trace.at(-1).value !== target) trace.push({ low, high, mid: -1, value: null, outcome: "not found" });
      const current = trace[Math.min(trace.length - 1, step)];
      const range = current.low <= current.high ? items.slice(current.low, current.high + 1) : [];
      const states = {
        array: `active range [${range.join(", ")}]`,
        comparison: current.mid >= 0 ? `compare ${target} with a[${current.mid}]=${current.value}` : `search exhausted for ${target}`,
        decision: current.outcome,
        result: current.outcome === "found" ? `found ${target} at index ${current.mid}` : current.outcome === "not found" ? `${target} is absent` : `next interval has ${current.outcome === "discard left" ? current.high-current.mid : current.mid-current.low} fewer candidates`,
      };
      node.label = states[layer.id] || node.label;
      if (layer.id === "array") node.width = 150 + 18 * range.length;
      if (layer.id === ["array","comparison","decision","result"][Math.min(3, step)]) { node.width += 18; node.height += 10; }
    } else if (spec.family === "ohms_law_circuit") {
      const voltage = stateNumber(values, "voltage", 12); const resistance = Math.max(0.1, stateNumber(values, "resistance", 6)); const current = values.switch ? voltage / resistance : 0;
      const states = [`battery ${voltage.toFixed(1)} V`, values.switch ? "switch closed" : "switch open", `resistor ${resistance.toFixed(1)} Ω`, `ammeter ${current.toFixed(2)} A`];
      node.label = states[index] || node.label;
      node.width = 130 + (index === 0 ? voltage * 2 : index === 2 ? resistance * 2 : index === 3 ? current * 12 : (values.switch ? 30 : 0));
      return node;
    } else if (spec.family === "series_parallel_circuit") {
      const r1 = Math.max(0.1, stateNumber(values, "r1", 1)); const r2 = Math.max(0.1, stateNumber(values, "r2", 2)); const parallel = values.mode === "parallel";
      const equivalent = parallel ? (r1 * r2) / (r1 + r2) : r1 + r2;
      const totalCurrent = 12 / equivalent;
      const states = parallel
        ? ["source 12 V", `R₁=${r1.toFixed(1)} Ω, V₁=12 V, I₁=${(12/r1).toFixed(2)} A`, `R₂=${r2.toFixed(1)} Ω, V₂=12 V, I₂=${(12/r2).toFixed(2)} A`, `R_eq=${equivalent.toFixed(2)} Ω, I_total=${totalCurrent.toFixed(2)} A`]
        : ["source 12 V", `R₁=${r1.toFixed(1)} Ω, V₁=${(totalCurrent*r1).toFixed(2)} V`, `R₂=${r2.toFixed(1)} Ω, V₂=${(totalCurrent*r2).toFixed(2)} V`, `R_eq=${equivalent.toFixed(2)} Ω, I=${totalCurrent.toFixed(2)} A`];
      node.label = states[index] || node.label; node.width = 130 + Math.min(120, equivalent * 7);
      const positions = parallel
        ? [{x:100,y:215},{x:360,y:125},{x:360,y:305},{x:630,y:215}]
        : [{x:100,y:215},{x:285,y:215},{x:455,y:215},{x:630,y:215}];
      Object.assign(node, positions[index] || {});
      return node;
    } else if (spec.family === "rc_circuit") {
      const resistance = Math.max(0.1, stateNumber(values, "resistance", 4));
      const capacitance = Math.max(0.1, stateNumber(values, "capacitance", 2));
      const labels = {
        rc_source: `DC source • ${String(values.mode || "charging")}`,
        rc_resistor: `resistor R=${resistance.toFixed(1)}`,
        rc_capacitor: `capacitor C=${capacitance.toFixed(1)}; τ=${(resistance * capacitance / 5).toFixed(2)}`,
      };
      node.label = labels[layer.id] || node.label;
      return node;
    } else if (spec.family === "rlc_circuit") {
      const labels = {
        rlc_source: "source",
        rlc_r: `R = ${stateNumber(values, "resistance", 1).toFixed(1)} Ω`,
        rlc_l: `L = ${stateNumber(values, "inductance", 2).toFixed(1)} H`,
        rlc_c: `C = ${stateNumber(values, "capacitance", 3).toFixed(1)} F`,
      };
      node.label = labels[layer.id] || node.label;
      return node;
    } else if (spec.family === "merge_sort") {
      const playback = Math.round(stateNumber(values, "playback", 0)); const phase = Math.max(step, playback);
      const eventNodes = spec.scene.layers.filter((candidate)=>candidate.type==="node");
      const eventIndex = eventNodes.findIndex((candidate)=>candidate.id===layer.id);
      const active = Math.min(eventNodes.length-1,Math.floor(phase/20*Math.max(1,eventNodes.length-1)));
      node.opacity = eventIndex <= active ? 1 : 0.18;
      if (eventIndex === active) { node.width += 20; node.height += 10; node.label = `${node.label} • current`; }
    } else if (spec.family === "recursion_stack") {
      const callNodes = spec.scene.layers.filter((candidate) => candidate.type === "node" && candidate.id.startsWith("call"));
      const maximum = Math.max(1, ...callNodes.map((candidate) => Number(candidate.id.slice(4))).filter(Number.isFinite));
      const activeDepth = Math.min(maximum, step + 1); const returnValue = Array.from({length:activeDepth},(_u,i)=>i+1).reduce((product,value)=>product*value,1);
      if (layer.id.startsWith("call")) node.label = `${layer.label}${Number(layer.id.slice(4)) === maximum-activeDepth+1 ? " • active frame" : ""}`;
      if (layer.id.startsWith("return")) node.label = `${layer.label}${Number(layer.id.slice(6)) === activeDepth ? ` • returning ${returnValue}` : ""}`;
    } else if (spec.family === "stack_queue") {
      const operation = String(values.operation || "add");
      const itemIndex = Number(layer.id.split("_")[1]);
      if (layer.id === "stack_title") { node.label = operation === "add" ? "Stack • push at top" : `Stack • pop ${["C","B","A","empty"][Math.min(3,step)]} first (LIFO)`; return node; }
      if (layer.id === "queue_title") { node.label = operation === "add" ? "Queue • enqueue at rear" : `Queue • dequeue ${["A","B","C","empty"][Math.min(3,step)]} first (FIFO)`; return node; }
      if (Number.isFinite(itemIndex)) {
        const present = operation === "add" ? itemIndex <= Math.min(2, step) : (layer.id.startsWith("stack_") ? itemIndex < 3-step : itemIndex >= step);
        node.label = present ? ["A","B","C"][itemIndex] : "empty";
        node.opacity = present ? 1 : 0.18;
        if (present && ((layer.id.startsWith("stack_") && itemIndex === (operation === "add" ? Math.min(2,step) : 2-step)) || (layer.id.startsWith("queue_") && itemIndex === (operation === "add" ? Math.min(2,step) : step)))) node.height += 10;
      }
    } else if (spec.family === "ionic_bond") {
      const phase = Math.max(0, Math.min(4, Math.round(stateNumber(values, "playback", 0))));
      if (layer.id === "electron") {
        node.x = 260 + phase * 52;
        node.label = phase < 3 ? "e⁻ moving Na → Cl" : "e⁻ accepted by Cl";
      }
      if (layer.id === "sodium" && phase >= 3) node.label = "Na⁺: lost e⁻";
      if (layer.id === "chlorine" && phase >= 3) node.label = "Cl⁻: gained e⁻";
      if (layer.id === "ions" && phase >= 4) { node.width += 35; node.label = "Na⁺ ⇄ Cl⁻ ionic attraction"; }
      return node;
    } else if (spec.family === "molecular_orbitals") {
      const selected = String(values.orbital || "bonding");
      if (layer.id === selected) { node.width += 32; node.height += 16; }
      return node;
    } else if (spec.family === "cpu_memory") {
      const states = {
        cpu: "CPU requests address",
        cache: step >= 1 ? "cache miss" : "registers / cache",
        ram: step >= 2 ? "RAM miss" : "RAM lookup",
        ssd: step >= 3 ? "page fault → SSD" : "SSD storage",
        retry: step >= 4 ? "page loaded into RAM → retry CPU" : "waiting for page-in",
      };
      node.label = states[layer.id] || node.label;
      if (["cpu", "cache", "ram", "ssd", "retry"][Math.min(4, step)] === layer.id) { node.width += 28; node.height += 14; }
      return node;
    } else if (spec.family === "dijkstra") {
      const result = dijkstraResult(spec.scene.layers, values);
      const distance = result.distances.get(layer.id);
      node.label = `${layer.id}\nd=${Number.isFinite(distance) ? distance : "∞"}`;
    } else if (spec.family === "heap") {
      const value = Math.round(stateNumber(values, "value", 4));
      const operation = String(values.operation || "insert");
      const ids = ["root","left","right","left_left","left_right","right_left","right_right"];
      const byId = new Map(spec.scene.layers.filter((candidate)=>candidate.type==="node").map((candidate)=>[candidate.id,candidate]));
      const seed = ids.map((id)=>Number(String(byId.get(id)?.label || "").match(/-?\d+(?:\.\d+)?/)?.[0])).filter(Number.isFinite);
      const bubbleUp = (seedValues) => { const items=seedValues.slice(); const states=[items.slice()]; items.push(value); states.push(items.slice()); let child=items.length-1; while(child>0){const parent=Math.floor((child-1)/2); if(items[parent]<=items[child]) break; [items[parent],items[child]]=[items[child],items[parent]]; child=parent; states.push(items.slice());} return states; };
      const extractMin = (seedValues) => { const items=seedValues.slice(); const states=[items.slice()]; if(items.length>1){items[0]=items.pop(); states.push(items.slice());} else items.length=0; let parent=0; while(true){const left=2*parent+1; const right=left+1; if(left>=items.length) break; const child=right<items.length&&items[right]<items[left]?right:left; if(items[parent]<=items[child]) break; [items[parent],items[child]]=[items[child],items[parent]]; parent=child; states.push(items.slice());} return states; };
      const states = operation === "insert" ? bubbleUp(seed) : extractMin(seed);
      const current = states[Math.min(states.length - 1, step)]; const heapIndex = ids.indexOf(layer.id);
      if (heapIndex >= 0) { node.label = heapIndex < current.length ? String(current[heapIndex]) : "empty"; node.opacity = heapIndex < current.length ? 1 : 0.22; }
      if (operation === "insert" && step === 0 && heapIndex === seed.length) {
        node.label = `candidate ${value}`; node.opacity = 1;
      }
      if (layer.id === "root") node.label = operation === "extract_min" && step > 0 ? `${current[0]} • extracted ${seed[0]}` : `${current[0]} • minimum`;
      const active = operation === "insert" ? ["right_right","right","root"] : ["root","left","left_left"];
      if (layer.id === active[Math.min(active.length - 1, step)]) { node.width += 22; node.height += 12; }
    } else if (spec.family === "binary_search_tree") {
      const inserted = Math.round(stateNumber(values, "insert", 6));
      const insertion = bstInsertionState(spec.scene.layers, inserted);
      if (layer.id === "candidate") {
        Object.assign(node, insertion.candidate);
        node.label = insertion.duplicate ? `${inserted} duplicate • not inserted` : `new node ${inserted}`;
        node.opacity = step >= insertion.path.length ? 1 : 0.18;
      } else if (insertion.path[Math.min(step, insertion.path.length - 1)] === layer.id) {
        node.width += 20; node.height += 12; node.label = `${node.label} • compare`;
      }
    } else if (spec.family === "dna_replication") {
      const playback = Math.round(stateNumber(values, "playback", 0)); const phase = Math.max(step, playback);
      const replicationOrder = ["fork", "leading_primer", "leading", "lagging_primer", "okazaki", "ligase"];
      if (layer.id === replicationOrder[Math.min(replicationOrder.length - 1, phase)]) { node.width += 24; node.height += 12; }
      if (layer.id === "fork") node.label = `helicase fork • step ${step} • playback ${playback}`;
      if (layer.id === "leading") node.label = "leading strand • 5′→3′ continuous";
      if (layer.id === "okazaki") node.label = "lagging strand • 5′→3′ Okazaki fragments";
      if (layer.id === "ligase" && phase >= 4) node.label = "DNA ligase seals fragments";
    } else if (spec.family === "nephron") {
      const selected = String(values.segment || "proximal");
      if (layer.id === selected) { node.width += 30; node.height += 16; node.label = `${node.label} • selected`; }
    } else if (spec.family === "membrane_transport") {
      const selected = String(values.transport_mode || "diffusion");
      if (layer.id === selected) { node.width += 34; node.height += 18; node.label = `${node.label} • selected`; }
    } else if (spec.family === "hash_table") {
      const key = Math.round(stateNumber(values, "key", 17)); const bucket = ((key % 5) + 5) % 5;
      if (layer.id === "key") node.label = `key ${key}`;
      if (layer.id === "hash") node.label = `h(${key})=${bucket}`;
      if (layer.id === `bucket${bucket}`) { node.width += 24; node.height += 12; node.label = `bucket ${bucket} • selected`; }
      if (layer.id.startsWith("chain_")) {
        const offset = { chain_a: 0, chain_b: 5, chain_c: 10 }[layer.id];
        const bucketY = [80,150,220,290,360][bucket];
        node.x = ["chain_b","chain_d"].includes(layer.id) ? 650 : 545; node.y = bucketY + ({chain_a:-45,chain_b:-15,chain_c:15,chain_d:45}[layer.id]);
        if (layer.id === "chain_d") {
          const operation=String(values.operation||"insert"); const completed=step>=6;
          node.label=operation === "lookup" ? `key ${key}${completed ? " • found" : " • seeking"}` : operation === "delete" ? `key ${key}${completed ? " • deleted" : " • locate to delete"}` : `insert key ${key}${completed ? " • linked" : " • pending"}`;
          if(operation === "delete" && completed) node.opacity=0.18;
        } else node.label = `key ${bucket + offset}`;
      }
      const lookupOrder = ["key", "hash", `bucket${bucket}`, "chain_a", "chain_b", "chain_c", "chain_d"];
      if (layer.id === lookupOrder[Math.min(lookupOrder.length - 1, step)]) node.height += 14;
    } else if (spec.family === "graph_traversal") {
      const algorithm = String(values.algorithm || "bfs").toUpperCase();
      const traversal = graphTraversalState(algorithm, step);
      if (layer.id === "status") node.label = `${algorithm} frontier [${traversal.frontier.join(",")}]; visited ${traversal.visited.join("→")}`;
      if (traversal.visited.includes(layer.id)) { node.width += 18; node.height += 10; node.label = `${node.label} • visited`; }
      else if (traversal.frontier.includes(layer.id)) { node.height += 8; node.label = `${node.label} • frontier`; }
    } else if (spec.family === "virtual_memory") {
      const address = Math.round(stateNumber(values, "address", 37)); const page = Math.floor(address / 16); const offset = address % 16;
      const states = {
        virtual: `virtual ${address} = page ${page} + offset ${offset}`,
        tlb: `TLB lookup for page ${page}`,
        page_table: `page-table entry ${page}`,
        frame: `frame ${(page * 3 + 1) % 16}, offset ${offset}`,
        storage: "backing storage on page fault",
        replacement: "replace frame, preserve offset, retry",
      };
      node.label = states[layer.id] || node.label;
      if (["virtual", "tlb", "page_table", "storage", "replacement", "frame"][Math.min(5, step)] === layer.id) { node.width += 24; node.height += 12; }
    } else if (spec.family === "kalman_filter") {
      const noise = Math.max(0.1, stateNumber(values, "noise", 1));
      const processNoise = Math.max(0.01, stateNumber(values, "process_noise", 0.08));
      const prior = 2; const measurement = 6; const predictedVariance = 1.92 + processNoise;
      const gain = predictedVariance / (predictedVariance + noise);
      const estimate = prior + gain * (measurement - prior);
      const posteriorVariance = (1 - gain) * predictedVariance;
      if (layer.id === "prior") Object.assign(node, { x: 120 + prior * 70, y: 145, width: 82 + 36 * Math.sqrt(predictedVariance), label: `prior x=${prior}, P⁻=${predictedVariance.toFixed(2)}` });
      if (layer.id === "measurement") Object.assign(node, { x: 120 + measurement * 70, y: 145, width: 82 + 36 * Math.sqrt(noise), label: `measurement z=${measurement}, R=${noise.toFixed(2)}` });
      if (layer.id === "estimate") Object.assign(node, { x: 120 + estimate * 70, y: 295, width: 82 + 36 * Math.sqrt(posteriorVariance), label: `update x=${estimate.toFixed(2)}, P=${posteriorVariance.toFixed(2)}` });
      if (layer.id === "timeline") node.label = `step ${step}: predict → measure → update; K=${gain.toFixed(3)}`;
      if (index === step % 4) node.height += 14;
      return node;
    } else if (spec.family === "electrochemical_cell") {
      const zinc = Math.max(0.01, stateNumber(values, "zinc_concentration", 1)); const copper = Math.max(0.01, stateNumber(values, "copper_concentration", 1)); const voltage = 1.1 - 0.0295 * Math.log(zinc / copper);
      const states = {
        anode: `Zn anode [Zn²⁺]=${zinc.toFixed(1)} M; Zn→Zn²⁺+2e⁻`,
        cathode: `Cu cathode [Cu²⁺]=${copper.toFixed(1)} M; Cu²⁺+2e⁻→Cu`,
        salt_bridge: "salt bridge: ions preserve neutrality",
        voltage: `E=${voltage.toFixed(3)} V`,
      };
      node.label = states[layer.id] || node.label; if (layer.id === "voltage") node.width = 150 + voltage * 30;
    } else if (spec.family === "equilibrium_shift") {
      const pressure = Math.max(0.1, stateNumber(values, "pressure", 1)); const temperature = Math.max(1, stateNumber(values, "temperature", 450)); const product = pressure / (pressure + Math.exp((temperature - 450) / 180));
      const states = ["N₂ + 3H₂", "⇌", "2NH₃ (fewer gas moles)", `NH₃ fraction ${product.toFixed(2)}`];
      node.label = states[index] || node.label; if (index === 3) node.width = 110 + product * 130;
    } else if (spec.family === "state_machine") {
      const requested = Boolean(values.pedestrian_request); const phase = Math.round(step) % 4;
      const states = ["red", "red + amber", requested ? "green • pedestrian request queued" : "green", "amber → red"];
      node.label = `${states[index] || node.label}${index === phase ? " • active" : ""}`;
    } else if (spec.family === "neural_network") {
      const hasThird = spec.scene.layers.some((candidate) => candidate.type === "node" && candidate.id === "h3");
      const state = neuralState(values, hasThird); const labels = {
        x1: `input x₁=${state.x1}`, x2: `input x₂=${state.x2}`,
        h1: `h₁=ReLU(·)=${state.h1.toFixed(3)}`, h2: `h₂=ReLU(·)=${state.h2.toFixed(3)}`,
        h3: `h₃=ReLU(·)=${state.h3.toFixed(3)}`,
        output: `ŷ=sigmoid(·)=${state.output.toFixed(3)}`,
      };
      node.label = labels[layer.id] || node.label;
      const activeColumns = [{x1:true,x2:true},{h1:true,h2:true,h3:hasThird},{output:true}][Math.min(2,step)] || {};
      if (activeColumns[layer.id]) { node.width += 20; node.height += 10; }
    } else if (spec.family === "backprop_graph") {
      const w = stateNumber(values, "w", 1); const xValue = stateNumber(values, "x", 2); const bias = stateNumber(values, "b", 3); const u = w * xValue + bias;
      const powerLink = spec.scene.layers.find((candidate)=>candidate.type==="link"&&candidate.from==="u"&&candidate.to==="y"); const power = Math.max(2,Math.min(5,Number(String(powerLink?.label||"power 2").match(/\d+/)?.[0])||2)); const yValue = u ** power; const derivative = power * u ** (power-1);
      const states = {
        inputs: `w=${w.toFixed(1)}, x=${xValue.toFixed(1)}, b=${bias.toFixed(1)}`,
        u: `u=wx+b=${u.toFixed(2)}`,
        y: `y=u^${power}=${yValue.toFixed(2)}`,
        grad_u: `∂y/∂u=${derivative.toFixed(2)}`,
        grad_w: `∂y/∂w=${(derivative*xValue).toFixed(2)}`,
        grad_x: `∂y/∂x=${(derivative*w).toFixed(2)}`,
        grad_b: `∂y/∂b=${derivative.toFixed(2)}`,
      };
      node.label = states[layer.id] || node.label;
    } else if (spec.family === "energy_sankey") {
      const efficiency = Math.max(0, Math.min(1, stateNumber(values, "efficiency", 0.65))); const useful = 100 * efficiency; const waste = 100 - useful;
      const amounts = { input: 100, useful, heat: waste * 0.75, sound: waste * 0.25 };
      const energyLabels = { input: "100 J input", useful: `${useful.toFixed(2)} J useful`, heat: `${amounts.heat.toFixed(2)} J heat`, sound: `${amounts.sound.toFixed(2)} J sound` };
      node.label = energyLabels[layer.id] || node.label;
      node.width = 90 + Math.max(12, amounts[layer.id] || 0);
    }

    if (spec.family === "truss" && layer.id === "apex") {
      const load = Math.max(10, stateNumber(values, "load", 50));
      node.label = `${load.toFixed(0)} kN joint load`;
      node.height = 44 + load / 5;
      return node;
    }
    if (spec.family === "robot_arm") {
      const base = { x: 240, y: 330 }; const scaleFactor = 65; const l1 = 150; const l2 = 135;
      const tx = base.x + scaleFactor * stateNumber(values, "target_x", 2.5);
      const ty = base.y - scaleFactor * stateNumber(values, "target_y", 1.5);
      const dx = tx - base.x; const dy = -(ty - base.y); const radius = Math.max(1e-6, Math.hypot(dx, dy));
      const targetReachable = radius >= Math.abs(l1-l2)-1e-6 && radius <= l1+l2+1e-6;
      const reachable = Math.max(Math.abs(l1-l2)+1e-6, Math.min(l1+l2-1e-6, radius));
      const px = dx * reachable / radius; const py = dy * reachable / radius;
      const cosSecond = Math.max(-1, Math.min(1, (reachable*reachable-l1*l1-l2*l2)/(2*l1*l2)));
      const sinSecond = (String(values.elbow_mode || "default") === "alternate" ? 1 : -1) * Math.sqrt(Math.max(0, 1-cosSecond*cosSecond));
      const second = Math.atan2(sinSecond, cosSecond);
      const first = Math.atan2(py, px) - Math.atan2(l2*sinSecond, l1+l2*cosSecond);
      const elbow = { x: base.x+l1*Math.cos(first), y: base.y-l1*Math.sin(first) };
      const end = { x: elbow.x+l2*Math.cos(first+second), y: elbow.y-l2*Math.sin(first+second) };
      if (layer.id === "base") Object.assign(node, base);
      if (layer.id === "elbow") Object.assign(node, elbow, { label: String(values.elbow_mode||"default") === "alternate" ? "elbow-down" : "elbow-up" });
      if (layer.id === "end_effector") Object.assign(node, end, { label: `${targetReachable ? "end effector" : "nearest reachable point"} (${((end.x-base.x)/scaleFactor).toFixed(2)}, ${((base.y-end.y)/scaleFactor).toFixed(2)})` });
      if (layer.id === "target") Object.assign(node, { x: tx, y: ty, label: targetReachable ? "target ×" : "unreachable target ×", color: targetReachable ? node.color : "red" });
      return node;
    }
    if (spec.family === "animal_cell") {
      const selected = String(values.organelle || "nucleus");
      const functions = {
        nucleus: "stores DNA", mitochondrion: "makes ATP", ribosome: "builds proteins",
        rough_er: "folds proteins", golgi: "sorts cargo", lysosome: "digests waste",
      };
      if (layer.id === selected) {
        node.width += 30; node.height += 18;
        node.label = `${layer.id.replaceAll("_", " ")}: ${functions[layer.id]}`;
      }
      return node;
    }
    if (spec.family === "circulation" && layer.id === "rbc") {
      const route = [[100, 215], [275, 330], [455, 215], [275, 95], [100, 215]];
      const progress = Math.max(0, stateNumber(values, "playback", 0));
      const segment = Math.floor(progress) % 4; const fraction = progress - Math.floor(progress);
      node.x = route[segment][0] + (route[segment + 1][0] - route[segment][0]) * fraction;
      node.y = route[segment][1] + (route[segment + 1][1] - route[segment][1]) * fraction;
      node.label = segment < 2 ? "RBC • deoxygenated" : "RBC • oxygenated";
      return node;
    }
    if (spec.family === "mitosis") {
      const phases = ["prophase", "metaphase", "anaphase", "telophase"];
      const phase = Math.max(0, Math.min(3, step));
      if (phases.includes(layer.id)) {
        if (layer.id === phases[phase]) { node.width += 24; node.height += 12; node.label = `${node.label} • active`; }
        return node;
      }
      if (layer.id.startsWith("chromosome")) {
        const chromosome = Number(layer.id.replace("chromosome", ""));
        const positions = phase === 0
          ? [[300,220],[340,190],[380,245],[420,205]]
          : phase === 1
            ? [[360,145],[360,195],[360,245],[360,295]]
            : phase === 2
              ? [[230,165],[490,165],[230,275],[490,275]]
              : [[220,180],[250,240],[470,180],[500,240]];
        Object.assign(node, { x: positions[chromosome][0], y: positions[chromosome][1], label: phase === 2 ? `chromatid ${chromosome + 1} separating` : `chromosome ${chromosome + 1}` });
      }
      return node;
    }
    if (spec.family === "pendulum") {
      const pivot = { x: 250, y: 80 };
      const length = 55 + 42 * stateNumber(values, "length", 1);
      const amplitude = stateNumber(values, "angle", 20) * Math.PI / 180;
      const period = 2 * Math.PI * Math.sqrt(Math.max(0.05, stateNumber(values, "length", 1)) / 9.81);
      const elapsed = stateNumber(values, "__animation_progress", 0) * 8;
      const angle = amplitude * Math.cos(2 * Math.PI * elapsed / period);
      const bob = { x: pivot.x + length * Math.sin(angle), y: pivot.y + length * Math.cos(angle) };
      if (layer.id === "pivot") Object.assign(node, pivot);
      if (layer.id === "bob") Object.assign(node, bob, { label: `bob • T=${(2*Math.PI*Math.sqrt(stateNumber(values,"length",1)/9.81)).toFixed(2)} s` });
      return node;
    }
    if (spec.family === "inclined_plane") {
      const angle = stateNumber(values, "incline", 1) * Math.PI / 20;
      const along = index * 135;
      Object.assign(node, { x: 100 + along * Math.cos(angle), y: 330 - along * Math.sin(angle) });
      return node;
    }
    if (spec.family === "spring_mass") {
      const spring = Math.max(0.2, stateNumber(values, "spring_constant", 1));
      if (Object.hasOwn(values, "displacement")) {
        const displacement = stateNumber(values, "displacement", 1); const extensionPixels = 75 + Math.abs(displacement) * 70;
        if (layer.id === "support") Object.assign(node, { x: 360, y: 70 });
        if (layer.id === "mass") Object.assign(node, { x: 360, y: 70 + extensionPixels, label: `displacement x=${displacement.toFixed(2)} m` });
        return node;
      }
      const mass = Math.max(0.2, stateNumber(values, "mass", 2));
      const extensionMetres = 9.81 * mass / spring;
      const extensionPixels = Math.min(260, 75 + extensionMetres * 70);
      if (layer.id === "support") Object.assign(node, { x: 360, y: 70 });
      if (layer.id === "mass") Object.assign(node, { x: 360, y: 70 + extensionPixels, label: `mass ${mass.toFixed(2)} kg • x=${extensionMetres.toFixed(2)} m` });
      return node;
    }
    if (spec.family === "triangle_angles" && layer.id === "angle_sum") {
      node.label = `A + B + C = ${(stateNumber(values,"vertex_a",60)+stateNumber(values,"vertex_b",60)+stateNumber(values,"vertex_c",60)).toFixed(0)}°`;
      return node;
    }
    if (spec.family === "triangle_angles" && index < 3) {
      let a = stateNumber(values, "vertex_a", 60) * Math.PI / 180;
      let b = stateNumber(values, "vertex_b", 60) * Math.PI / 180;
      const c = stateNumber(values, "vertex_c", 60) * Math.PI / 180;
      if (changedId === "vertex_a" && a + b >= Math.PI - 0.15) b = Math.max(0.15, Math.PI - 0.15 - a);
      if (changedId === "vertex_b" && a + b >= Math.PI - 0.15) a = Math.max(0.15, Math.PI - 0.15 - b);
      if (changedId === "vertex_c") a = Math.max(0.15, Math.PI - b - c);
      const baseLength = 360;
      const sinC = Math.max(0.15, Math.sin(Math.max(0.15, Math.PI - a - b)));
      const side = Math.min(460, baseLength * Math.sin(b) / sinC);
      const positions = [{ x: 160, y: 330 }, { x: 520, y: 330 }, { x: 160 + side * Math.cos(a), y: 330 - side * Math.sin(a) }];
      Object.assign(node, positions[index]);
      node.label = `vertex ${["A","B","C"][index]}: ${stateNumber(values,["vertex_a","vertex_b","vertex_c"][index],60).toFixed(0)}°`;
      return node;
    }
    if (spec.family === "refraction") {
      const center = { x: 360, y: 210 };
      const incident = stateNumber(values, "incident_angle", 35) * Math.PI / 180;
      const n2 = values.medium === "water" ? 1.33 : 1.5;
      const refracted = Math.asin(Math.min(0.999, Math.sin(incident) / n2));
      const positions = [
        { x: center.x - 180 * Math.sin(incident), y: center.y - 180 * Math.cos(incident) },
        center,
        { x: center.x + 180 * Math.sin(refracted), y: center.y + 180 * Math.cos(refracted) },
        { x: 555, y: 90 },
      ];
      Object.assign(node, positions[index] || node);
      return node;
    }
    if (spec.family === "converging_lens") {
      const distance = Math.max(1.2, stateNumber(values, "object_distance", 2));
      const focal = 1; const imageDistance = focal * distance / (distance - focal); const scaleFactor = 80;
      const objectTop = { x: 360 - distance * scaleFactor, y: 150 };
      const imageTop = { x: 360 + imageDistance * scaleFactor, y: 230 + (imageDistance / distance) * 80 };
      if (layer.id === "object") Object.assign(node, objectTop, { label: `object dₒ=${distance.toFixed(2)}f` });
      if (layer.id === "lens") Object.assign(node, { x: 360, y: 230 });
      if (layer.id === "focal_left") Object.assign(node, { x: 280, y: 230 });
      if (layer.id === "focal_right") Object.assign(node, { x: 440, y: 230 });
      if (layer.id === "image") Object.assign(node, imageTop, { label: `real image dᵢ=${imageDistance.toFixed(2)}f` });
      return node;
    }
    if (spec.family === "elastic_collision") {
      const m1 = Math.max(0.1, stateNumber(values, "mass_1", 2)); const u1 = stateNumber(values, "velocity_1", 3);
      const m2 = Math.max(0.1, stateNumber(values, "mass_2", 3)); const u2 = stateNumber(values, "velocity_2", -1);
      const v1 = ((m1 - m2) * u1 + 2 * m2 * u2) / (m1 + m2);
      const v2 = (2 * m1 * u1 + (m2 - m1) * u2) / (m1 + m2);
      const states = {
        before_1: [`cart 1: m=${m1.toFixed(1)}, u=${u1.toFixed(2)}`, m1, u1],
        before_2: [`cart 2: m=${m2.toFixed(1)}, u=${u2.toFixed(2)}`, m2, u2],
        after_1: [`cart 1: v=${v1.toFixed(2)}`, m1, v1],
        after_2: [`cart 2: v=${v2.toFixed(2)}`, m2, v2],
      };
      const [label, mass, velocity] = states[layer.id] || [node.label, 1, 0];
      node.label = label; node.width = 92 + 12 * mass; node.x += Math.max(-55, Math.min(55, velocity * 8));
      return node;
    }
    if (spec.family === "atom") {
      const atomicNumber = Math.max(1, Math.round(stateNumber(values, "atomic_number", 1)));
      if (index === 0) node.label = `nucleus Z=${atomicNumber}`;
      if (index === 3) { node.label = `${atomicNumber} electrons in shells`; node.width = 170 + Math.min(100, atomicNumber * 3); }
      return node;
    }
    return node;
  }

  function controlledArrow(spec, layer, values) {
    if (spec.family === "projectile") {
      const angle = stateNumber(values, "angle", 45) * Math.PI / 180;
      const speed = stateNumber(values, "speed", 20);
      const flight = 2 * speed * Math.sin(angle) / 9.81;
      const time = 0.35 * flight;
      const origin = [speed * Math.cos(angle) * time, speed * Math.sin(angle) * time - 4.905 * time * time];
      const velocity = [speed * Math.cos(angle), speed * Math.sin(angle) - 9.81 * time];
      return { ...layer, from: origin, to: [origin[0] + 0.4 * velocity[0], origin[1] + 0.4 * velocity[1]], label: `velocity (${velocity[0].toFixed(1)}, ${velocity[1].toFixed(1)}) m/s` };
    }
    if (spec.family === "spring_mass") {
      const spring = Math.max(0.2, stateNumber(values, "spring_constant", 12));
      if (Object.hasOwn(values, "displacement")) {
        const displacement=stateNumber(values,"displacement",1); const y=145+Math.abs(displacement)*70; const force=-spring*displacement;
        if (layer.label.startsWith("spring force")) return { ...layer, from:[360,y], to:[360,y-Math.sign(displacement||1)*Math.min(110,35+Math.abs(force)*2)], label:`restoring force F=−kx=${force.toFixed(2)} N` };
        if (layer.label.startsWith("weight")) return { ...layer, from:[360,y], to:[360,y+55], label:"applied displacement direction" };
        return { ...layer, from:[485,70], to:[485,y], label:`displacement x=${displacement.toFixed(2)} m` };
      }
      const mass = Math.max(0.2, stateNumber(values, "mass", 2));
      const extension = 9.81 * mass / spring;
      const y = 70 + Math.min(260, 75 + extension * 70);
      if (layer.label.startsWith("weight")) return { ...layer, from: [360, y], to: [360, y + 95], label: `weight ${(9.81*mass).toFixed(2)} N` };
      if (layer.label.startsWith("spring force")) return { ...layer, from: [360, y], to: [360, y - 95], label: `spring force ${(spring*extension).toFixed(2)} N` };
      return { ...layer, from: [485, 70], to: [485, y], label: `equilibrium x=${extension.toFixed(2)} m` };
    }
    if (spec.family === "pendulum") {
      const pivot = [250, 80]; const length = 55 + 42 * stateNumber(values, "length", 1);
      const amplitude = stateNumber(values, "angle", 20) * Math.PI / 180;
      const period = 2 * Math.PI * Math.sqrt(Math.max(0.05, stateNumber(values, "length", 1)) / 9.81);
      const elapsed = stateNumber(values, "__animation_progress", 0) * 8;
      const angle = amplitude * Math.cos(2 * Math.PI * elapsed / period);
      const bob = [pivot[0] + length * Math.sin(angle), pivot[1] + length * Math.cos(angle)];
      if (layer.label.startsWith("restoring")) return { ...layer, from: bob, to: [bob[0] - 70*Math.cos(angle), bob[1] + 70*Math.sin(angle)], label: `restoring mg sinθ` };
      return { ...layer, from: pivot, to: [pivot[0], pivot[1] + length], label: "equilibrium" };
    }
    if (spec.family === "inclined_plane") {
      const geometry = inclinedGeometry(values); const { theta, tangent, normal, planeStart, origin } = geometry;
      const frictionCoefficient = 0.2; const downhill = 9.81 * Math.sin(theta); const friction = frictionCoefficient * 9.81 * Math.cos(theta); const acceleration = Math.max(0, downhill - friction);
      if (layer.label.startsWith("inclined plane")) return { ...layer, from: planeStart, to: [planeStart[0] + 560 * tangent[0], planeStart[1] + 560 * tangent[1]], label: `inclined plane θ=${(theta * 180 / Math.PI).toFixed(0)}°` };
      if (layer.label.startsWith("weight")) return { ...layer, from: origin, to: [origin[0], origin[1] + 120], label: "weight mg" };
      if (layer.label.startsWith("normal")) return { ...layer, from: origin, to: [origin[0] + 105 * normal[0], origin[1] + 105 * normal[1]], label: `normal N=mg cosθ (${(9.81 * Math.cos(theta)).toFixed(2)} per kg)` };
      if (layer.label.startsWith("friction")) return { ...layer, from: origin, to: [origin[0] + 90 * tangent[0], origin[1] + 90 * tangent[1]], label: `friction μN, μ=${frictionCoefficient}` };
      if (layer.label.startsWith("resultant")) return { ...layer, from: origin, to: [origin[0] - 95 * tangent[0], origin[1] - 95 * tangent[1]], label: `a=g(sinθ−μcosθ)=${acceleration.toFixed(2)} m/s²` };
    }
    if (spec.family === "elastic_collision") {
      const m1 = Math.max(0.1, stateNumber(values, "mass_1", 2)); const u1 = stateNumber(values, "velocity_1", 3);
      const m2 = Math.max(0.1, stateNumber(values, "mass_2", 3)); const u2 = stateNumber(values, "velocity_2", -1);
      const v1 = ((m1 - m2) * u1 + 2 * m2 * u2) / (m1 + m2);
      const v2 = (2 * m1 * u1 + (m2 - m1) * u2) / (m1 + m2);
      const velocity = layer.label === "u₁" ? u1 : layer.label === "u₂" ? u2 : layer.label === "v₁" ? v1 : v2;
      return { ...layer, to: [layer.from[0] + Math.max(-95, Math.min(95, velocity * 20)), layer.from[1]], label: `${layer.label}=${velocity.toFixed(2)}` };
    }
    if (spec.family === "converging_lens") {
      const distance = Math.max(1.2, stateNumber(values, "object_distance", 2.5));
      const imageDistance = distance / (distance - 1); const objectTop = [360-distance*80,150]; const lensParallel=[360,150]; const lensCentre=[360,230]; const imageTop=[360+imageDistance*80,230+(imageDistance/distance)*80];
      if (layer.label === "parallel incident ray") return { ...layer, from: objectTop, to: lensParallel };
      if (layer.label === "refracts through F′") return { ...layer, from: lensParallel, to: imageTop };
      if (layer.label === "central ray") return { ...layer, from: objectTop, to: lensCentre };
      if (layer.label === "central ray undeviated") return { ...layer, from: lensCentre, to: imageTop };
    }
    if (spec.family === "truss") {
      const load = Math.max(10, stateNumber(values, "load", 50)); const reaction=load/2;
      if (layer.label.includes("downward")) return { ...layer, from:[360,88-Math.min(70,load)], to:[360,88], label:`${load.toFixed(0)} kN downward` };
      if (layer.label.includes("reaction")) return { ...layer, from:[layer.from[0],345+Math.min(60,reaction)], to:[layer.to[0],345], label:`${reaction.toFixed(1)} kN reaction` };
    }
    return layer;
  }

  function controlledRect(spec, layer, values) {
    if (spec.family !== "inclined_plane" || layer.label !== "box") return { ...layer, rotation: 0 };
    const { theta, origin } = inclinedGeometry(values);
    return {
      ...layer,
      x: origin[0] - layer.width / 2,
      y: origin[1] - layer.height / 2,
      rotation: -theta * 180 / Math.PI,
      rotation_origin: origin,
    };
  }

  function recordEvidence(stage, evidence) {
    global.__mutaVizEvidence = evidence;
    stage.dataset.vizEvidence = JSON.stringify(evidence);
  }

  function attachFallback(stage, spec) {
    const details = html("details", "viz-v2-fallback");
    const summary = html("summary", "", "Text description");
    const description = html("p", "", spec.text_fallback);
    details.append(summary, description);
    stage.appendChild(details);
  }

  function animationStatusText(description, status, progress) {
    const glyph = status === "playing" ? "▶" : status === "complete" ? "✓" : "⏸";
    return `${description} · ${glyph} ${Math.round(progress * 100)}%`;
  }

  function buildControls(stage, spec, onChange, translate) {
    if (!spec.controls.length) return { values: {}, inputs: new Map(), setPressed: () => {}, cleanup: () => {} };
    const wrapper = html("div", "viz-v2-controls");
    wrapper.setAttribute("role", "group");
    wrapper.setAttribute("aria-label", [spec.title, translate("visualization.controls")].join(": "));
    const values = {};
    const inputs = new Map();
    const listeners = [];
    spec.controls.forEach((control) => {
      const label = html("label", "viz-v2-control");
      const labelText = html("span", "viz-v2-control-label", control.label);
      let input;
      if (control.type === "select") {
        input = document.createElement("select");
        control.options.forEach((option) => {
          const item = document.createElement("option");
          item.value = option;
          item.textContent = option.replaceAll("_", " ");
          input.appendChild(item);
        });
        input.value = control.value;
      } else if (control.type === "button") {
        input = document.createElement("button");
        input.type = "button";
        input.textContent = control.label;
        input.setAttribute("aria-pressed", "false");
        labelText.hidden = true;
      } else {
        input = document.createElement("input");
        input.type = "range";
        input.min = control.min;
        input.max = control.max;
        input.step = control.step;
        input.value = control.value;
      }
      input.id = `viz-v2-${control.id}`;
      input.setAttribute("aria-label", control.label);
      values[control.id] = control.value;
      const output = html("output", "viz-v2-control-value", String(control.value));
      output.htmlFor = input.id;
      inputs.set(control.id, { input, output, control });
      const update = () => {
        if (control.type === "button") {
          const next = input.getAttribute("aria-pressed") !== "true";
          input.setAttribute("aria-pressed", String(next));
          values[control.id] = next ? 1 : 0;
          output.textContent = next ? "on" : "off";
        } else {
          values[control.id] = control.type === "select" ? input.value : Number(input.value);
          output.textContent = String(input.value);
        }
        onChange(values, control.id);
      };
      const eventName = control.type === "button" ? "click" : "input";
      input.addEventListener(eventName, update);
      listeners.push(() => input.removeEventListener(eventName, update));
      const stepControl = (direction, edge = null) => {
        if (control.type === "button") {
          input.click();
          return;
        }
        if (control.type === "select") {
          const boundary = edge === "start" ? 0 : edge === "end" ? input.options.length - 1 : input.selectedIndex + direction;
          input.selectedIndex = Math.max(0, Math.min(input.options.length - 1, boundary));
          update();
          return;
        }
        const minimum = Number(input.min); const maximum = Number(input.max); const step = Number(input.step) || 1;
        const next = edge === "start" ? minimum : edge === "end" ? maximum : Number(input.value) + direction * step;
        input.value = String(Math.max(minimum, Math.min(maximum, next)));
        update();
      };
      const keydown = (event) => {
        const positive = event.key === "ArrowRight" || event.key === "ArrowUp";
        const negative = event.key === "ArrowLeft" || event.key === "ArrowDown";
        const activate = control.type === "button" && (event.key === " " || event.key === "Enter");
        if (!positive && !negative && !activate && event.key !== "Home" && event.key !== "End") return;
        event.preventDefault();
        stepControl(positive || activate ? 1 : -1, event.key === "Home" ? "start" : event.key === "End" ? "end" : null);
      };
      input.addEventListener("keydown", keydown);
      listeners.push(() => input.removeEventListener("keydown", keydown));
      label.append(labelText, input, output);
      wrapper.appendChild(label);
    });
    stage.appendChild(wrapper);
    const setPressed = (id, pressed) => {
      const record = inputs.get(id);
      if (!record || record.control.type !== "button") return;
      record.input.setAttribute("aria-pressed", String(Boolean(pressed)));
      values[id] = pressed ? 1 : 0;
      record.output.textContent = pressed ? "on" : "off";
    };
    return { values, inputs, setPressed, cleanup: () => listeners.forEach((remove) => remove()) };
  }

  function synchronizeIdealGas(values, changedId, controls) {
    if (!controls || !["pressure", "volume", "temperature"].includes(changedId)) return;
    const ranges = { pressure: [0.5, 8], volume: [0.5, 8], temperature: [0.5, 12] };
    const assign = (id, raw) => {
      const record = controls.inputs.get(id); if (!record) return;
      const [minimum, maximum] = ranges[id];
      const value = Math.max(minimum, Math.min(maximum, raw));
      values[id] = value; record.input.value = String(value);
      record.output.textContent = Number(value.toFixed(3)).toString();
    };
    let pressure = stateNumber(values, "pressure", 2);
    let volume = stateNumber(values, "volume", 2);
    let temperature = stateNumber(values, "temperature", 4);
    if (changedId === "temperature") {
      pressure = temperature / volume;
      if (pressure < ranges.pressure[0] || pressure > ranges.pressure[1]) {
        pressure = Math.max(ranges.pressure[0], Math.min(ranges.pressure[1], pressure));
        volume = temperature / pressure; assign("volume", volume);
      }
      assign("pressure", pressure);
    } else {
      temperature = pressure * volume;
      if (temperature < ranges.temperature[0] || temperature > ranges.temperature[1]) {
        temperature = Math.max(ranges.temperature[0], Math.min(ranges.temperature[1], temperature));
        if (changedId === "pressure") { volume = temperature / pressure; assign("volume", volume); }
        else { pressure = temperature / volume; assign("pressure", pressure); }
      }
      assign("temperature", temperature);
    }
  }

  function synchronizeTriangle(values, changedId, controls) {
    if (!controls || !["vertex_a", "vertex_b", "vertex_c"].includes(changedId)) return;
    const others = ["vertex_a", "vertex_b", "vertex_c"].filter((id) => id !== changedId);
    const changed = stateNumber(values, changedId, 60);
    const remaining = Math.max(20, 180 - changed);
    const first = Math.max(10, Math.min(160, stateNumber(values, others[0], 60)));
    const adjustedFirst = Math.max(10, Math.min(remaining - 10, first));
    const updates = { [others[0]]: adjustedFirst, [others[1]]: remaining - adjustedFirst };
    Object.entries(updates).forEach(([id, value]) => {
      const record = controls.inputs.get(id); if (!record) return;
      values[id] = value; record.input.value = String(value); record.output.textContent = Number(value.toFixed(2)).toString();
    });
  }

  function createAnimationController(spec, context, controls, update) {
    const animation = spec.scene.animation;
    if (!animation) return { handle: () => {}, cleanup: () => {}, state: () => ({ status: "static", progress: 1 }) };
    const duration = animation.duration * 1000;
    const interval = 1000 / Math.max(1, Math.min(30, spec.budget.max_fps));
    let progress = 0; let elapsed = 0; let playing = false; let raf = 0; let last = 0; let lastDraw = 0; let observedFrameInterval = 0;
    const publish = () => update(progress, playing ? "playing" : progress >= 1 ? "complete" : "paused", observedFrameInterval);
    const stopFrame = () => { if (raf) cancelAnimationFrame(raf); raf = 0; };
    const tick = (now) => {
      raf = 0;
      if (!playing || !context.renderActive()) { last = 0; return; }
      if (!last) last = now;
      const delta = Math.max(0, now - last); last = now; elapsed = Math.min(duration, elapsed + delta); progress = elapsed / duration;
      if (now - lastDraw >= interval || progress >= 1) { observedFrameInterval = lastDraw ? now - lastDraw : 0; lastDraw = now; publish(); }
      if (progress >= 1) {
        playing = false; controls.setPressed("play", false); controls.setPressed("pause", true); publish();
      } else raf = requestAnimationFrame(tick);
    };
    const play = () => {
      if (context.reducedMotion) {
        progress = 1; elapsed = duration; playing = false;
        controls.setPressed("play", false); controls.setPressed("pause", true); publish(); return;
      }
      if (progress >= 1) { progress = 0; elapsed = 0; }
      playing = true; last = 0; controls.setPressed("play", true); controls.setPressed("pause", false);
      publish(); if (!raf && context.renderActive()) raf = requestAnimationFrame(tick);
    };
    const pause = () => { playing = false; last = 0; stopFrame(); controls.setPressed("play", false); controls.setPressed("pause", true); publish(); };
    const restart = () => { pause(); progress = 0; elapsed = 0; controls.setPressed("restart", false); controls.setPressed("pause", false); publish(); play(); };
    const handle = (id) => { if (id === "play") play(); else if (id === "pause") pause(); else if (id === "restart") restart(); };
    const removeActivity = context.onActivity((active) => {
      if (!active) { stopFrame(); last = 0; }
      else if (playing && !raf) { last = 0; raf = requestAnimationFrame(tick); }
    });
    publish();
    return { handle, cleanup: () => { stopFrame(); removeActivity(); }, state: () => ({ status: playing ? "playing" : progress >= 1 ? "complete" : "paused", progress }) };
  }

  function animationControlValues(spec, values, progress) {
    if (!spec.scene.animation || progress <= 0) return { ...values };
    const effective = { ...values };
    effective.__animation_progress = progress;
    spec.controls.forEach((control) => {
      if (!["step", "playback"].includes(control.id) || !["range", "step"].includes(control.type)) return;
      const minimum = Number(control.min); const maximum = Number(control.max); const step = Number(control.step) || 1;
      effective[control.id] = Math.min(maximum, minimum + Math.floor(progress * ((maximum - minimum) / step + 1)) * step);
    });
    return effective;
  }

  function svgScene(spec, context) {
    const stage = context.stage;
    const drawing = html("div", "viz-v2-drawing");
    const height = Math.max(260, spec.height - 104);
    const svg = element("svg", {
      viewBox: `0 0 720 ${height}`,
      preserveAspectRatio: "xMidYMid meet",
      role: "img",
      "aria-label": spec.aria_label,
    });
    const defs = element("defs");
    const marker = element("marker", { id: "v2-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
    marker.appendChild(element("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: context.neutral }));
    defs.appendChild(marker);
    svg.appendChild(defs);
    drawing.appendChild(svg);
    stage.appendChild(drawing);
    const layers = spec.scene.layers;
    const links = layers.filter((layer) => layer.type === "link");
    const nodeRecords = new Map();
    const state = html("p", "viz-v2-state");
    state.setAttribute("role", "status");
    state.setAttribute("aria-live", "polite");
    stage.appendChild(state);
    let controlRevision = 0;
    let latestControlValues = {};
    let latestChangedId = "";
    let animationProgress = spec.scene.animation ? 0 : 1;
    let animationStatus = spec.scene.animation ? "paused" : "static";
    let animationFrameInterval = 0;
    const redraw = (controlValues = {}, changedId = "") => {
      latestControlValues = animationControlValues(spec, controlValues, animationProgress);
      if (changedId) { controlRevision += 1; latestChangedId = changedId; }
      state.textContent = spec.scene.animation
        ? animationStatusText(stateDescription(spec, latestControlValues), animationStatus, animationProgress)
        : stateDescription(spec, latestControlValues);
      [...svg.querySelectorAll(".viz-v2-layer")].forEach((node) => node.remove());
      const fragment = document.createDocumentFragment();
      const polylineLayers = layers.filter((layer) => layer.type === "polyline");
      const controlled = new Map(polylineLayers.map((layer, polylineIndex) => [layer, controlledPoints(spec.family, layer, polylineIndex, latestControlValues)]));
      const particleLayers = layers.filter((layer) => layer.type === "particles");
      const particles = new Map(particleLayers.map((layer) => [layer, controlledParticles(spec.family, layer, latestControlValues)]));
      const vectorLayers = layers.filter((layer) => layer.type === "vector_field");
      const vectors = new Map(vectorLayers.map((layer) => [layer, controlledVectors(spec.family, layer, latestControlValues)]));
      const fieldPoints = vectorLayers.flatMap((layer) => vectors.get(layer).flatMap(([vx, vy, dx, dy]) => [[vx, vy], [vx + dx, vy + dy]]));
      const probes = new Map(layers.filter((layer) => layer.type === "probe_vector").map((layer) => [layer, evaluatedProbe(layer, latestControlValues)]));
      const plotPoints = [...controlled.values()].flat().concat([...particles.values()].flat(), fieldPoints, [...probes.values()].flat());
      const xDomain = extent(plotPoints.map((point) => point[0]));
      const yDomain = extent(plotPoints.map((point) => point[1]));
      const x = scale(xDomain, [62, 695]);
      const y = scale(yDomain, [height - 46, 22]);
      const stateControl = spec.controls.find((control) => ["step", "select"].includes(control.type));
      const stateValue = stateControl ? latestControlValues[stateControl.id] : null;
      const nodes = layers.filter((layer) => layer.type === "node");
      const renderedNodes = new Map(nodes.map((layer, nodeIndex) => [layer.id, controlledNode(spec, layer, nodeIndex, latestControlValues, latestChangedId)]));
      const activeNode = typeof stateValue === "number" ? Math.abs(Math.round(stateValue)) % Math.max(1, nodes.length) : stateValue === "alternate" ? Math.max(0, nodes.length - 1) : 0;
      let geometrySignature = 0;
      layers.forEach((layer, index) => {
        const color = paletteValue(context, layer.color, index);
        let node;
        if (layer.type === "axes") {
          node = element("g", { class: "viz-v2-layer viz-v2-axes" });
          for (let tick = 0; tick <= 8; tick += 1) {
            const gx = 62 + (633 * tick) / 8;
            const gy = 22 + ((height - 68) * tick) / 8;
            if (layer.grid) {
              node.append(element("line", { x1: gx, y1: 22, x2: gx, y2: height - 46, stroke: context.border, "stroke-width": 0.8 }));
              node.append(element("line", { x1: 62, y1: gy, x2: 695, y2: gy, stroke: context.border, "stroke-width": 0.8 }));
            }
          }
          node.append(element("line", { x1: 62, y1: height - 46, x2: 695, y2: height - 46, stroke: context.neutral, "stroke-width": 1.4 }));
          node.append(element("line", { x1: 62, y1: 22, x2: 62, y2: height - 46, stroke: context.neutral, "stroke-width": 1.4 }));
          node.append(element("text", { x: 378, y: height - 12, "text-anchor": "middle", fill: context.neutral }, layer.x_label || "x"));
          node.append(element("text", { x: 17, y: height / 2, transform: `rotate(-90 17 ${height / 2})`, "text-anchor": "middle", fill: context.neutral }, layer.y_label || "y"));
        } else if (layer.type === "polyline") {
          // The compiler owns mathematical state. Never invent a generic slider-to-geometry
          // mapping here: doing so can turn a correct curve into a visually plausible lie.
          const allPoints = controlled.get(layer) || layer.points;
          const points = spec.scene.animation ? allPoints.slice(0, Math.max(2, Math.ceil(allPoints.length * animationProgress))) : allPoints;
          points.forEach((point, pointIndex) => { geometrySignature += Math.round((point[0] * 17 + point[1] * 31) * (pointIndex + 1)); });
          const path = points.map((point, pointIndex) => `${pointIndex ? "L" : "M"}${x(point[0])},${y(point[1])}`).join(" ");
          let displayedCurveLabel = layer.label || "curve";
          if (spec.family === "nyquist" && displayedCurveLabel.includes("Nyquist")) {
            const gain = Math.max(0.1, stateNumber(latestControlValues, "gain", 1));
            const winding = Math.abs(1 - 0.25 * gain) < 0.2 * gain ? 1 : 0;
            displayedCurveLabel = `Nyquist locus • winding N=${winding} • ${winding ? "unstable" : "stable"}`;
          }
          node = element("g", { class: "viz-v2-layer", role: "img", "aria-label": displayedCurveLabel });
          node.append(element("path", { d: path, fill: "none", stroke: color, "stroke-width": 3, "stroke-linejoin": "round", "marker-end": layer.label.includes("direction arrow") ? "url(#v2-arrow)" : "" }));
          node.append(element("text", { x: 688, y: 34 + index * 18, "text-anchor": "end", fill: color }, displayedCurveLabel));
        } else if (layer.type === "particles") {
          node = element("g", { class: "viz-v2-layer", role: "img", "aria-label": layer.label });
          const displayed = particles.get(layer) || layer.points;
          displayed.forEach((point, pointIndex) => {
            node.append(element("circle", { cx: x(point[0]), cy: y(point[1]), r: 4, fill: color, stroke: context.neutral, "stroke-width": 1 }));
            geometrySignature += Math.round((point[0] * 23 + point[1] * 37) * (pointIndex + 1));
          });
        } else if (layer.type === "vector_field") {
          node = element("g", { class: "viz-v2-layer", role: "img", "aria-label": layer.label });
          vectors.get(layer).forEach(([vx, vy, dx, dy], vectorIndex) => {
            node.append(element("line", { x1: x(vx), y1: y(vy), x2: x(vx + dx), y2: y(vy + dy), stroke: color, "stroke-width": 1.8, "marker-end": "url(#v2-arrow)" }));
            geometrySignature += Math.round((vx * 11 + vy * 13 + dx * 17 + dy * 19) * (vectorIndex + 1));
          });
        } else if (layer.type === "probe_vector") {
          const [from, to] = probes.get(layer);
          node = element("g", { class: "viz-v2-layer", role: "img", "aria-label": layer.label });
          node.append(element("line", { x1: x(from[0]), y1: y(from[1]), x2: x(to[0]), y2: y(to[1]), stroke: color, "stroke-width": 4, "marker-end": "url(#v2-arrow)" }));
          node.append(element("circle", { cx: x(from[0]), cy: y(from[1]), r: 5, fill: color }));
          geometrySignature += Math.round((from[0] * 41 + from[1] * 43 + to[0] * 47 + to[1] * 53) * 100);
        } else if (layer.type === "node") {
          const displayed = renderedNodes.get(layer.id) || layer;
          const displayedColor = paletteValue(context, displayed.color, index);
          const nodeIndex = nodes.indexOf(layer);
          const dijkstra = spec.family === "dijkstra" ? dijkstraResult(layers, latestControlValues) : null;
          const selected = dijkstra
            ? [dijkstra.source, dijkstra.destination, ...dijkstra.settled].includes(layer.id)
            : stateControl && nodeIndex === activeNode;
          node = element("g", { class: "viz-v2-layer", tabindex: 0, role: "group", "aria-label": displayed.label, "data-active": selected ? "true" : "false" });
          const revealed = !spec.scene.animation || nodeIndex <= Math.floor(animationProgress * Math.max(0, nodes.length - 1));
          node.append(element("rect", { x: displayed.x - displayed.width / 2, y: displayed.y - displayed.height / 2, width: displayed.width, height: displayed.height, rx: 12, fill: displayedColor, opacity: revealed ? (displayed.opacity ?? (selected ? 1 : 0.86)) : 0.16, stroke: selected ? context.neutral : "none", "stroke-width": selected ? 4 : 0 }));
          node.append(element("text", { x: displayed.x, y: displayed.y + 5, "text-anchor": "middle", fill: "white", "font-weight": 700 }, displayed.label));
          const labelSignature = displayed.label.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0);
          geometrySignature += (nodeIndex + 1) * Math.round(displayed.x * 17 + displayed.y * 31 + displayed.width * 13 + displayed.height * 7 + labelSignature + (selected ? 101 : 0) + (revealed ? 503 : 0));
          nodeRecords.set(layer.id, displayed);
        } else if (layer.type === "link") {
          let from = nodeRecords.get(layer.from) || renderedNodes.get(layer.from);
          let to = nodeRecords.get(layer.to) || renderedNodes.get(layer.to);
          if (spec.family === "hash_table") {
            const key = Math.round(stateNumber(latestControlValues, "key", 17)); const bucket = ((key % 5) + 5) % 5;
            if (layer.from === "hash" && layer.to.startsWith("bucket")) to = renderedNodes.get(`bucket${bucket}`);
            if (layer.label === "head") from = renderedNodes.get(`bucket${bucket}`);
          }
          if (spec.family === "series_parallel_circuit" && String(latestControlValues.mode || "series") === "parallel") {
            const branchPairs = [["source","r1"],["r1","return"],["source","r2"],["r2","return"]];
            const pair = branchPairs[links.indexOf(layer)];
            if (pair) { from = renderedNodes.get(pair[0]); to = renderedNodes.get(pair[1]); }
          }
          if (!from || !to) return;
          node = element("g", { class: "viz-v2-layer" });
          const dijkstra = spec.family === "dijkstra" ? dijkstraResult(layers, latestControlValues) : null;
          const pathEdges = dijkstra ? new Set(dijkstra.path.slice(1).map((id, pathIndex) => [dijkstra.path[pathIndex], id].sort().join("|"))) : new Set();
          const onPath = pathEdges.has([layer.from, layer.to].sort().join("|"));
          let displayedLabel = layer.label; let linkColor = onPath ? context.palette[1] : context.neutral;
          let linkWidth = onPath ? 5 : 2;
          let linkDash = "";
          if (spec.family === "truss") {
            const load = Math.max(10, stateNumber(latestControlValues, "load", 50));
            const diagonal = load / (2 * Math.sin(Math.atan2(230, 200)));
            const bottom = diagonal * Math.cos(Math.atan2(230, 200));
            const compression = layer.from === "apex" || layer.to === "apex";
            displayedLabel = compression ? `compression ${diagonal.toFixed(1)} kN` : `tension ${bottom.toFixed(1)} kN`;
            linkColor = compression ? context.palette[1] : context.palette[0];
            linkWidth = 5;
          }
          if (spec.family === "spring_mass") displayedLabel = `spring k=${stateNumber(latestControlValues,"spring_constant",12).toFixed(1)} N/m`;
          if (spec.family === "pendulum") displayedLabel = `L=${stateNumber(latestControlValues,"length",1).toFixed(2)} m`;
          if (spec.family === "hash_table" && layer.from === "hash") { const key=Math.round(stateNumber(latestControlValues,"key",17)); displayedLabel=`${key} mod 5 = ${((key%5)+5)%5}`; }
          if (spec.family === "binary_search_tree" && layer.label === "new-node placement") {
            const insertion=bstInsertionState(layers,Math.round(stateNumber(latestControlValues,"insert",6)));
            from=renderedNodes.get(insertion.parent); to=renderedNodes.get("candidate");
            displayedLabel=insertion.duplicate ? "duplicate rejected" : "new-node placement";
            linkDash=stateNumber(latestControlValues,"step",0) >= insertion.path.length ? "" : "5 5";
          }
          if (spec.family === "neural_network") {
            const state=neuralState(latestControlValues, layers.some((candidate)=>candidate.type==="node"&&candidate.id==="h3"));
            if (layer.from === "x1" && layer.to === "h1") displayedLabel=`w₁₁=${state.weight.toFixed(2)}`;
            linkWidth=2+Math.min(5,Math.abs(layer.from === "x1"&&layer.to === "h1" ? state.weight : Number(String(displayedLabel).match(/-?\d+(?:\.\d+)?/)?.[0])||1)*2);
          }
          if (spec.family === "energy_sankey") {
            const efficiency = Math.max(0, Math.min(1, stateNumber(latestControlValues, "efficiency", 0.65)));
            const waste = 100 * (1 - efficiency);
            const amount = layer.to === "useful" ? 100 * efficiency : layer.to === "heat" ? 0.75 * waste : 0.25 * waste;
            displayedLabel = `${amount.toFixed(2)} J`;
            linkWidth = 2 + 0.13 * amount;
          }
          if (spec.family === "series_parallel_circuit") {
            const r1 = Math.max(0.1, stateNumber(latestControlValues, "r1", 1)); const r2 = Math.max(0.1, stateNumber(latestControlValues, "r2", 2));
            const parallel = String(latestControlValues.mode || "series") === "parallel";
            const equivalent = parallel ? r1*r2/(r1+r2) : r1+r2; const total = 12/equivalent;
            const labels = parallel
              ? [`I₁=${(12/r1).toFixed(2)} A`,`V₁=12 V`,`I₂=${(12/r2).toFixed(2)} A`,`V₂=12 V`]
              : [`I=${total.toFixed(2)} A`,`V₁=${(total*r1).toFixed(2)} V`,`V₂=${(total*r2).toFixed(2)} V`,`ΣV=12 V`];
            displayedLabel = labels[links.indexOf(layer)] || displayedLabel; linkWidth = 3;
          }
          if (spec.family === "benzene") {
            const delocalized = String(latestControlValues.bond_model || "localized") === "delocalized";
            const bondIndex = links.indexOf(layer);
            linkWidth = delocalized ? 4 : (bondIndex % 2 === 0 ? 6 : 2);
            linkDash = delocalized ? "7 4" : "";
            displayedLabel = bondIndex === 0 ? (delocalized ? "delocalized equal π bonds" : "localized alternating bonds") : "";
          }
          node.append(element("line", { x1: from.x, y1: from.y, x2: to.x, y2: to.y, stroke: linkColor, "stroke-width": linkWidth, "stroke-dasharray": linkDash, "marker-end": layer.arrow ? "url(#v2-arrow)" : "" }));
          if (displayedLabel) node.append(element("text", { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - 7, "text-anchor": "middle", fill: context.neutral, "font-weight": 700 }, displayedLabel));
          const numericLabel = Number(displayedLabel);
          const linkLabelSignature = Number.isFinite(numericLabel)
            ? numericLabel * 13
            : String(displayedLabel || "").split("").reduce((sum, character) => sum + character.charCodeAt(0), 0);
          geometrySignature += (onPath ? 1009 : 17) + linkLabelSignature + Math.round(linkWidth * 97);
        } else if (layer.type === "circle") {
          node = element("circle", { class: "viz-v2-layer", cx: layer.x, cy: layer.y, r: layer.r, fill: color });
        } else if (layer.type === "rect") {
          const displayed = controlledRect(spec, layer, latestControlValues);
          const transform = displayed.rotation_origin
            ? `rotate(${displayed.rotation} ${displayed.rotation_origin[0]} ${displayed.rotation_origin[1]})`
            : "";
          node = element("rect", { class: "viz-v2-layer", x: displayed.x, y: displayed.y, width: displayed.width, height: displayed.height, rx: 6, fill: color, transform });
          geometrySignature += Math.round(displayed.x * 11 + displayed.y * 13 + displayed.rotation * 17);
        } else if (layer.type === "text") {
          node = element("text", { class: "viz-v2-layer", x: layer.x, y: layer.y, fill: color }, layer.text);
        } else if (layer.type === "arrow") {
          const displayed = controlledArrow(spec, layer, latestControlValues);
          node = element("g", { class: "viz-v2-layer", role: "img", "aria-label": displayed.label });
          node.append(element("line", { x1: displayed.from[0], y1: displayed.from[1], x2: displayed.to[0], y2: displayed.to[1], stroke: color, "stroke-width": 3, "marker-end": "url(#v2-arrow)" }));
          if (displayed.label) node.append(element("text", { x: (displayed.from[0]+displayed.to[0])/2+7, y: (displayed.from[1]+displayed.to[1])/2-7, fill: context.neutral, "font-size": 12 }, displayed.label));
          geometrySignature += Math.round(displayed.from[0]*11+displayed.from[1]*13+displayed.to[0]*17+displayed.to[1]*19+displayed.label.length*23);
        }
        if (node) fragment.appendChild(node);
      });
      svg.appendChild(fragment);
      const primitives = svg.querySelectorAll("path,line,circle,rect,text").length;
      recordEvidence(stage, { rendered: primitives > 2, renderer: "svg", primitive_count: primitives, controls: spec.controls.length, family: spec.family, control_revision: controlRevision, control_values: latestControlValues, geometry_signature: geometrySignature, visual_state_signature: geometrySignature, animation_state: animationStatus, animation_progress: animationProgress, observed_frame_interval_ms: animationFrameInterval, state_description: state.textContent });
    };
    let animationController = null;
    let controls;
    controls = buildControls(stage, spec, (values, id) => {
      if (spec.family === "ideal_gas") synchronizeIdealGas(values, id, controls);
      if (spec.family === "triangle_angles") synchronizeTriangle(values, id, controls);
      redraw(values, id);
      animationController?.handle(id);
    }, context.t);
    animationController = createAnimationController(spec, context, controls, (progress, statusValue, frameInterval) => {
      animationProgress = progress; animationStatus = statusValue; animationFrameInterval = frameInterval; redraw(controls.values);
    });
    redraw(controls.values);
    attachFallback(stage, spec);
    const observer = new ResizeObserver(() => {
      svg.style.width = `${Math.max(1, drawing.clientWidth)}px`;
    });
    observer.observe(drawing);
    return () => { animationController.cleanup(); controls.cleanup(); observer.disconnect(); };
  }

  function canvasScene(spec, context) {
    const stage = context.stage;
    const drawing = html("div", "viz-v2-drawing");
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", spec.aria_label);
    drawing.appendChild(canvas);
    stage.appendChild(drawing);
    const state = html("p", "viz-v2-state");
    state.setAttribute("role", "status");
    state.setAttribute("aria-live", "polite");
    stage.appendChild(state);
    const ctx = canvas.getContext("2d", { alpha: true });
    let values = {};
    let controlRevision = 0;
    let animationProgress = spec.scene.animation ? 0 : 1;
    let animationStatus = spec.scene.animation ? "paused" : "static";
    let animationFrameInterval = 0;
    const draw = () => {
      values = animationControlValues(spec, values, animationProgress);
      const ratio = Math.min(2, global.devicePixelRatio || 1);
      const width = Math.max(320, drawing.clientWidth || 720);
      const panelDefinitions = spec.scene.layers.filter((layer) => layer.type === "panel");
      const stackedPanels = panelDefinitions.length > 1 && width < 700;
      const height = Math.max(240, drawing.clientHeight || spec.height - 110);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);
      let customGeometrySignature = 0;
      const polylines = spec.scene.layers.filter((layer) => layer.type === "polyline");
      const complete = polylines.map((layer, index) => controlledPoints(spec.family, layer, index, values));
      const controlled = spec.scene.animation ? complete.map((points) => points.slice(0, Math.max(2, Math.ceil(points.length * animationProgress)))) : complete;
      const particleLayers = spec.scene.layers.filter((layer) => layer.type === "particles");
      const particlePoints = particleLayers.map((layer) => controlledParticles(spec.family, layer, values));
      const vectorFields = spec.scene.layers.filter((layer) => layer.type === "vector_field");
      const vectorValues = vectorFields.map((layer) => controlledVectors(spec.family, layer, values));
      const probes = spec.scene.layers.filter((layer) => layer.type === "probe_vector").map((layer) => [layer, evaluatedProbe(layer, values)]);
      const heatmaps = spec.scene.layers.filter((layer) => layer.type === "heatmap");
      const defaultAxes = spec.scene.layers.find((layer) => layer.type === "axes") || { x_label: "x", y_label: "y" };
      const panels = panelDefinitions.length ? panelDefinitions : [{
        id: "main", title: spec.title, x_label: defaultAxes.x_label, y_label: defaultAxes.y_label,
        members: spec.scene.layers.map((layer) => layer.label).filter(Boolean),
      }];
      const gap = 14;
      const panelRects = panels.map((_panel, index) => {
        if (!stackedPanels && panels.length === 2) {
          const panelWidth = (width - gap * 3) / 2;
          return { x: gap + index * (panelWidth + gap), y: gap, width: panelWidth, height: height - gap * 2 };
        }
        const panelHeight = (height - gap * (panels.length + 1)) / panels.length;
        return { x: gap, y: gap + index * (panelHeight + gap), width: width - gap * 2, height: panelHeight };
      });
      const belongs = (panel, layer) => panel.members.includes(layer.label);
      panels.forEach((panel, panelIndex) => {
        const rect = panelRects[panelIndex];
        const left = rect.x + 48; const right = rect.x + rect.width - 12;
        const top = rect.y + 30; const bottom = rect.y + rect.height - 34;
        const lineIndices = polylines.map((_layer, index) => index).filter((index) => belongs(panel, polylines[index]));
        const particleIndices = particleLayers.map((_layer, index) => index).filter((index) => belongs(panel, particleLayers[index]));
        const vectorIndices = vectorFields.map((_layer, index) => index).filter((index) => belongs(panel, vectorFields[index]));
        const panelProbes = probes.filter(([layer]) => belongs(panel, layer));
        const panelHeatmaps = heatmaps.filter((layer) => belongs(panel, layer));
        const domainPoints = lineIndices.flatMap((index) => complete[index])
          .concat(particleIndices.flatMap((index) => particlePoints[index]))
          .concat(vectorIndices.flatMap((index) => vectorValues[index].flatMap(([vx, vy, dx, dy]) => [[vx, vy], [vx + dx, vy + dy]])))
          .concat(panelProbes.flatMap((record) => record[1]));
        panelHeatmaps.forEach((layer) => domainPoints.push([layer.x_domain[0], layer.y_domain[0]], [layer.x_domain[1], layer.y_domain[1]]));
        const xDomain = extent(domainPoints.map((point) => point[0]));
        const yDomain = extent(domainPoints.map((point) => point[1]));
        const mapX = scale(xDomain, [left, right]); const mapY = scale(yDomain, [bottom, top]);
        ctx.strokeStyle = context.border; ctx.lineWidth = 1; ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
        for (let grid = 1; grid < 5; grid += 1) {
          const yy = top + (bottom - top) * grid / 5;
          ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(right, yy); ctx.stroke();
        }
        ctx.fillStyle = context.neutral; ctx.font = "600 13px system-ui"; ctx.fillText(panel.title, rect.x + 8, rect.y + 17);
        ctx.font = "11px system-ui"; ctx.fillText(panel.x_label, Math.max(left, (left + right) / 2 - ctx.measureText(panel.x_label).width / 2), rect.y + rect.height - 8);
        ctx.save(); ctx.translate(rect.x + 12, (top + bottom) / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(panel.y_label, -ctx.measureText(panel.y_label).width / 2, 0); ctx.restore();
        panelHeatmaps.forEach((layer, heatmapIndex) => {
          const heatValues = controlledHeatmap(spec.family, layer, values);
          const maximum = Math.max(...heatValues.map((value) => Math.abs(value)), 1e-9);
          const cellWidth = (right - left) / layer.columns; const cellHeight = (bottom - top) / layer.rows;
          heatValues.forEach((value, offset) => {
            const row = Math.floor(offset / layer.columns); const column = offset % layer.columns;
            const strength = Math.min(1, Math.abs(value) / maximum);
            ctx.globalAlpha = 0.08 + 0.76 * strength;
            ctx.fillStyle = value < 0 ? context.palette[(heatmapIndex + 1) % context.palette.length] : paletteValue(context, layer.color, heatmapIndex);
            ctx.fillRect(left + column * cellWidth, top + (layer.rows - 1 - row) * cellHeight, cellWidth + 0.6, cellHeight + 0.6);
            customGeometrySignature += Math.round(value * 1000) * (offset + 1);
          });
          ctx.globalAlpha = 1;
        });
        lineIndices.forEach((index, legendIndex) => {
          const layer = polylines[index]; ctx.beginPath();
          controlled[index].forEach((point, pointIndex) => { if (pointIndex) ctx.lineTo(mapX(point[0]), mapY(point[1])); else ctx.moveTo(mapX(point[0]), mapY(point[1])); });
          ctx.strokeStyle = paletteValue(context, layer.color, index); ctx.lineWidth = 2.5; ctx.stroke();
          ctx.fillStyle = ctx.strokeStyle; ctx.font = "10px system-ui"; ctx.fillText(layer.label, left + 4, top + 11 + legendIndex * 12);
        });
        particleIndices.forEach((index) => {
          const layer = particleLayers[index]; ctx.fillStyle = paletteValue(context, layer.color, index + polylines.length);
          particlePoints[index].forEach((point, pointIndex) => { ctx.beginPath(); ctx.arc(mapX(point[0]), mapY(point[1]), 3.5, 0, Math.PI * 2); ctx.fill(); customGeometrySignature += Math.round((point[0] * 23 + point[1] * 37) * (pointIndex + 1)); });
        });
        vectorIndices.forEach((index) => {
          const layer = vectorFields[index]; ctx.strokeStyle = paletteValue(context, layer.color, index + polylines.length + particleLayers.length); ctx.fillStyle = ctx.strokeStyle;
          vectorValues[index].forEach(([vx, vy, dx, dy], vectorIndex) => { const startX = mapX(vx); const startY = mapY(vy); const endX = mapX(vx + dx); const endY = mapY(vy + dy); ctx.beginPath(); ctx.moveTo(startX, startY); ctx.lineTo(endX, endY); ctx.stroke(); const angle = Math.atan2(endY - startY, endX - startX); ctx.beginPath(); ctx.moveTo(endX, endY); ctx.lineTo(endX - 7 * Math.cos(angle - 0.45), endY - 7 * Math.sin(angle - 0.45)); ctx.lineTo(endX - 7 * Math.cos(angle + 0.45), endY - 7 * Math.sin(angle + 0.45)); ctx.closePath(); ctx.fill(); customGeometrySignature += Math.round((vx * 11 + vy * 13 + dx * 17 + dy * 19) * (vectorIndex + 1)); });
        });
        panelProbes.forEach(([layer, [from, to]], probeIndex) => { ctx.strokeStyle = paletteValue(context, layer.color, probeIndex + polylines.length + particleLayers.length + vectorFields.length); ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(mapX(from[0]), mapY(from[1])); ctx.lineTo(mapX(to[0]), mapY(to[1])); ctx.stroke(); ctx.beginPath(); ctx.arc(mapX(from[0]), mapY(from[1]), 5, 0, Math.PI * 2); ctx.fill(); customGeometrySignature += Math.round((from[0] * 41 + from[1] * 43 + to[0] * 47 + to[1] * 53) * 100); });
        if (spec.family === "fluid_flow") { ctx.beginPath(); ctx.arc(mapX(0), mapY(0), Math.abs(mapX(1) - mapX(0)), 0, Math.PI * 2); ctx.fillStyle = context.border; ctx.fill(); customGeometrySignature += Math.round(stateNumber(values, "speed", 1) * 1000); }
      });
      state.textContent = spec.scene.animation
        ? animationStatusText(stateDescription(spec, values), animationStatus, animationProgress)
        : stateDescription(spec, values);
      const pixels = ctx.getImageData(0, 0, Math.min(canvas.width, 256), Math.min(canvas.height, 128)).data;
      let coloured = 0;
      for (let index = 3; index < pixels.length; index += 16) if (pixels[index] > 0) coloured += 1;
      const geometrySignature = customGeometrySignature + controlled.flat().reduce((sum, point, index) => sum + Math.round((point[0] * 17 + point[1] * 31) * (index + 1)), 0);
      recordEvidence(stage, { rendered: coloured > 10, renderer: "canvas", nontransparent_samples: coloured, controls: spec.controls.length, family: spec.family, panel_count: panels.length, panel_titles: panels.map((panel) => panel.title), control_revision: controlRevision, control_values: values, geometry_signature: geometrySignature, visual_state_signature: geometrySignature, animation_state: animationStatus, animation_progress: animationProgress, observed_frame_interval_ms: animationFrameInterval, state_description: state.textContent });
    };
    let animationController = null;
    const controls = buildControls(stage, spec, (next, id) => { values = { ...next }; controlRevision += 1; draw(); animationController?.handle(id); }, context.t);
    values = controls.values;
    animationController = createAnimationController(spec, context, controls, (progress, statusValue, frameInterval) => { animationProgress = progress; animationStatus = statusValue; animationFrameInterval = frameInterval; draw(); });
    const observer = new ResizeObserver(draw);
    observer.observe(drawing);
    draw();
    attachFallback(stage, spec);
    return () => { animationController.cleanup(); controls.cleanup(); observer.disconnect(); };
  }

  function evaluateRelation(relation, variables) {
    const left = global.MutaViz.evaluateExpressionV2(relation.left, variables);
    const right = global.MutaViz.evaluateExpressionV2(relation.right, variables);
    return left - right;
  }

  function interpolateSurfaceEdge(a, b, va, vb) {
    const denominator = va - vb;
    const amount = Math.abs(denominator) < 1e-12 ? 0.5 : Math.max(0, Math.min(1, va / denominator));
    return [a[0] + (b[0] - a[0]) * amount, a[1] + (b[1] - a[1]) * amount, a[2] + (b[2] - a[2]) * amount];
  }

  function implicitTriangles(layer) {
    const [nx, ny, nz] = layer.resolution;
    const domains = [layer.x_domain, layer.y_domain, layer.z_domain];
    const point = (ix, iy, iz) => [
      domains[0][0] + ((domains[0][1] - domains[0][0]) * ix) / (nx - 1),
      domains[1][0] + ((domains[1][1] - domains[1][0]) * iy) / (ny - 1),
      domains[2][0] + ((domains[2][1] - domains[2][0]) * iz) / (nz - 1),
    ];
    const cache = new Float64Array(nx * ny * nz);
    const finite = new Uint8Array(cache.length);
    const offset = (ix, iy, iz) => ix + nx * (iy + ny * iz);
    for (let iz = 0; iz < nz; iz += 1) for (let iy = 0; iy < ny; iy += 1) for (let ix = 0; ix < nx; ix += 1) {
      const coordinate = point(ix, iy, iz);
      try {
        const residual = evaluateRelation(layer.relationship, { x: coordinate[0], y: coordinate[1], z: coordinate[2] });
        // A zero set passing through a lattice vertex is topologically ambiguous. Sample a
        // fixed, negligible positive iso-offset so every shared edge is classified the same
        // way; this avoids cracks without changing the educational surface at display scale.
        cache[offset(ix, iy, iz)] = residual - 1e-7;
        finite[offset(ix, iy, iz)] = 1;
      } catch { finite[offset(ix, iy, iz)] = 0; }
    }
    const corners = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
    const tetrahedra = [[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]];
    const triangles = [];
    outer: for (let iz = 0; iz < nz - 1; iz += 1) for (let iy = 0; iy < ny - 1; iy += 1) for (let ix = 0; ix < nx - 1; ix += 1) {
      const coordinates = corners.map(([dx, dy, dz]) => point(ix + dx, iy + dy, iz + dz));
      const indices = corners.map(([dx, dy, dz]) => offset(ix + dx, iy + dy, iz + dz));
      if (indices.some((index) => !finite[index])) continue;
      const values = indices.map((index) => cache[index]);
      for (const tetra of tetrahedra) {
        const append = (a, b, c) => {
          const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
          const ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
          const cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]];
          if (cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2 > 1e-18) triangles.push(a, b, c);
        };
        const inside = tetra.filter((vertex) => values[vertex] < 0);
        const outside = tetra.filter((vertex) => values[vertex] >= 0);
        if (inside.length === 1 || inside.length === 3) {
          const anchor = inside.length === 1 ? inside[0] : outside[0];
          const others = inside.length === 1 ? outside : inside;
          const points = others.map((vertex) => interpolateSurfaceEdge(coordinates[anchor], coordinates[vertex], values[anchor], values[vertex]));
          append(points[0], points[1], points[2]);
        } else if (inside.length === 2) {
          const p00 = interpolateSurfaceEdge(coordinates[inside[0]], coordinates[outside[0]], values[inside[0]], values[outside[0]]);
          const p01 = interpolateSurfaceEdge(coordinates[inside[0]], coordinates[outside[1]], values[inside[0]], values[outside[1]]);
          const p10 = interpolateSurfaceEdge(coordinates[inside[1]], coordinates[outside[0]], values[inside[1]], values[outside[0]]);
          const p11 = interpolateSurfaceEdge(coordinates[inside[1]], coordinates[outside[1]], values[inside[1]], values[outside[1]]);
          append(p00, p01, p10); append(p10, p01, p11);
        }
        if (triangles.length / 3 >= 32000) break outer;
      }
    }
    return triangles;
  }

  function explicitTriangles(layer, phaseOffset = 0) {
    const [nx, ny] = layer.resolution;
    const values = Array.from({ length: nx * ny }, () => null);
    const at = (ix, iy) => ix + nx * iy;
    for (let iy = 0; iy < ny; iy += 1) for (let ix = 0; ix < nx; ix += 1) {
      const x = layer.x_domain[0] + ((layer.x_domain[1] - layer.x_domain[0]) * ix) / (nx - 1);
      const y = layer.y_domain[0] + ((layer.y_domain[1] - layer.y_domain[0]) * iy) / (ny - 1);
      try {
        const relation = layer.relationship;
        const z = global.MutaViz.evaluateExpressionV2(relation.right, { x: x - phaseOffset, y, z: 0 });
        if (z >= layer.z_domain[0] && z <= layer.z_domain[1]) values[at(ix, iy)] = [x, y, z];
      } catch { values[at(ix, iy)] = null; }
    }
    const inView = (point) => point && point[2] >= layer.z_domain[0] && point[2] <= layer.z_domain[1];
    const sample = (x, y) => {
      try {
        const z = global.MutaViz.evaluateExpressionV2(layer.relationship.right, { x: x - phaseOffset, y, z: 0 });
        return inView([x, y, z]) ? [x, y, z] : null;
      } catch { return null; }
    };
    const denominatorNodes = [];
    const atan2Nodes = [];
    const tangentNodes = [];
    const collectDenominators = (node) => {
      if (!node || typeof node !== "object") return;
      if (node.type === "binary") {
        if (node.op === "/") denominatorNodes.push(node.right);
        collectDenominators(node.left); collectDenominators(node.right);
      } else if (node.type === "unary") collectDenominators(node.arg);
      else if (node.type === "call") {
        if (node.name === "atan2") atan2Nodes.push(node.args);
        if (node.name === "tan") tangentNodes.push(node.args[0]);
        node.args.forEach(collectDenominators);
      }
    };
    collectDenominators(layer.relationship.right);
    const expressionInterval = (node, bounds) => {
      if (!node || typeof node !== "object") return null;
      if (node.type === "number") return [node.value, node.value];
      if (node.type === "constant") { const value = node.name === "e" ? Math.E : Math.PI; return [value, value]; }
      if (node.type === "variable") return bounds[node.name] || [0, 0];
      if (node.type === "unary") { const value = expressionInterval(node.arg, bounds); return value ? [-value[1], -value[0]] : null; }
      if (node.type === "binary") {
        const left = expressionInterval(node.left, bounds); const right = expressionInterval(node.right, bounds);
        if (!left || !right) return null;
        if (node.op === "+") return [left[0] + right[0], left[1] + right[1]];
        if (node.op === "-") return [left[0] - right[1], left[1] - right[0]];
        if (node.op === "*") { const products = [left[0] * right[0], left[0] * right[1], left[1] * right[0], left[1] * right[1]]; return [Math.min(...products), Math.max(...products)]; }
        if (node.op === "/") {
          if (right[0] <= 0 && right[1] >= 0) return null;
          const quotients = [left[0] / right[0], left[0] / right[1], left[1] / right[0], left[1] / right[1]];
          return [Math.min(...quotients), Math.max(...quotients)];
        }
        if (node.op === "^" && right[0] === right[1] && Number.isInteger(right[0])) {
          const exponent = right[0];
          if (exponent < 0 && left[0] <= 0 && left[1] >= 0) return null;
          const powers = [left[0] ** exponent, left[1] ** exponent];
          if (exponent % 2 === 0 && left[0] <= 0 && left[1] >= 0) powers.push(0);
          return powers.every(Number.isFinite) ? [Math.min(...powers), Math.max(...powers)] : null;
        }
        return null;
      }
      if (node.type === "call") {
        const args = node.args.map((argument) => expressionInterval(argument, bounds));
        if (args.some((value) => !value)) return null;
        const first = args[0];
        if (node.name === "abs") return first[0] <= 0 && first[1] >= 0 ? [0, Math.max(-first[0], first[1])] : [Math.min(Math.abs(first[0]), Math.abs(first[1])), Math.max(Math.abs(first[0]), Math.abs(first[1]))];
        if (node.name === "exp") return [Math.exp(first[0]), Math.exp(first[1])];
        if (node.name === "ln" || node.name === "log") return first[0] > 0 ? [Math.log(first[0]), Math.log(first[1])] : null;
        if (node.name === "sqrt") return first[0] >= 0 ? [Math.sqrt(first[0]), Math.sqrt(first[1])] : null;
        if (["sin", "cos", "tanh"].includes(node.name)) return [-1, 1];
        if (node.name === "atan") return [Math.atan(first[0]), Math.atan(first[1])];
        if (node.name === "sinh") return [Math.sinh(first[0]), Math.sinh(first[1])];
        if (node.name === "cosh") return first[0] <= 0 && first[1] >= 0 ? [1, Math.max(Math.cosh(first[0]), Math.cosh(first[1]))] : [Math.min(Math.cosh(first[0]), Math.cosh(first[1])), Math.max(Math.cosh(first[0]), Math.cosh(first[1]))];
        if (node.name === "min") return [Math.min(args[0][0], args[1][0]), Math.min(args[0][1], args[1][1])];
        if (node.name === "max") return [Math.max(args[0][0], args[1][0]), Math.max(args[0][1], args[1][1])];
        return null;
      }
      return null;
    };
    const cellSamples = (a, c, expression, transform = (value) => value) => {
      const samples = [];
      for (let ix = 0; ix <= 4; ix += 1) for (let iy = 0; iy <= 4; iy += 1) {
        const x = a[0] + (c[0] - a[0]) * ix / 4;
        const y = a[1] + (c[1] - a[1]) * iy / 4;
        try { samples.push(transform(global.MutaViz.evaluateExpressionV2(expression, { x: x - phaseOffset, y, z: 0 }))); }
        catch { return null; }
      }
      return samples;
    };
    const crossesZero = (samples) => {
      if (!samples) return true;
      const low = Math.min(...samples); const high = Math.max(...samples);
      const scaleValue = Math.max(1, Math.abs(low), Math.abs(high));
      return low <= 0 && high >= 0 || Math.min(...samples.map(Math.abs)) < scaleValue * 1e-6;
    };
    const denominatorCrossesCell = (node, a, c) => {
      const interval = expressionInterval(node, { x: [a[0] - phaseOffset, c[0] - phaseOffset], y: [a[1], c[1]], z: [0, 0] });
      return !interval || (interval[0] <= 0 && interval[1] >= 0) || crossesZero(cellSamples(a, c, node));
    };
    const discontinuityCrossesCell = (a, c) => denominatorNodes.some((node) => denominatorCrossesCell(node, a, c))
      || tangentNodes.some((node) => crossesZero(cellSamples(a, c, node, Math.cos)))
      || atan2Nodes.some(([vertical, horizontal]) => crossesZero(cellSamples(a, c, vertical)) && crossesZero(cellSamples(a, c, horizontal)));
    const triangles = [];
    let rejectedDiscontinuityCells = 0;
    let rejectedUndefinedCells = 0;
    for (let iy = 0; iy < ny - 1; iy += 1) for (let ix = 0; ix < nx - 1; ix += 1) {
      const a = values[at(ix, iy)]; const b = values[at(ix + 1, iy)];
      const c = values[at(ix + 1, iy + 1)]; const d = values[at(ix, iy + 1)];
      if ([a, b, c, d].some(Boolean) && ![a, b, c, d].every(Boolean)) rejectedUndefinedCells += 1;
      if (a && b && c && d) {
        if (discontinuityCrossesCell(a, c)) { rejectedDiscontinuityCells += 1; continue; }
        const probes = [
          [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
          [(b[0] + c[0]) / 2, (b[1] + c[1]) / 2],
          [(c[0] + d[0]) / 2, (c[1] + d[1]) / 2],
          [(d[0] + a[0]) / 2, (d[1] + a[1]) / 2],
          [(a[0] + c[0]) / 2, (a[1] + c[1]) / 2],
        ];
        // A rational/trigonometric pole can sit between finite corner samples. Never bridge
        // such a discontinuity with a plausible-looking triangle.
        if (probes.some(([x, y]) => !sample(x, y))) { rejectedUndefinedCells += 1; continue; }
      }
      if (a && b && c) triangles.push(a, b, c);
      if (a && c && d) triangles.push(a, c, d);
    }
    triangles.diagnostics = {
      rejected_discontinuity_cells: rejectedDiscontinuityCells,
      rejected_undefined_cells: rejectedUndefinedCells,
      finite_triangles: Math.floor(triangles.length / 3),
    };
    return triangles;
  }

  function parametricTriangles(layer) {
    const [nu, nv] = layer.resolution;
    const points = [];
    const evaluate = (u, v) => [layer.x_expression, layer.y_expression, layer.z_expression].map((expression) => global.MutaViz.evaluateExpressionV2(expression, { u, v, x: 0, y: 0, z: 0 }));
    for (let iv = 0; iv < nv - 1; iv += 1) for (let iu = 0; iu < nu - 1; iu += 1) {
      const u0 = layer.u_domain[0] + ((layer.u_domain[1] - layer.u_domain[0]) * iu) / (nu - 1);
      const u1 = layer.u_domain[0] + ((layer.u_domain[1] - layer.u_domain[0]) * (iu + 1)) / (nu - 1);
      const v0 = layer.v_domain[0] + ((layer.v_domain[1] - layer.v_domain[0]) * iv) / (nv - 1);
      const v1 = layer.v_domain[0] + ((layer.v_domain[1] - layer.v_domain[0]) * (iv + 1)) / (nv - 1);
      let a; let b; let c; let d;
      try { a = evaluate(u0, v0); b = evaluate(u1, v0); c = evaluate(u1, v1); d = evaluate(u0, v1); }
      catch { continue; }
      points.push(a, b, c, a, c, d);
    }
    return points;
  }

  function meshTopology(triangles, layer = null) {
    const faceCount = Math.floor(triangles.length / 3);
    if (!faceCount) return { components: 0, vertices: 0, edges: 0, faces: 0, euler: 0, boundary_edges: 0, nonmanifold_edges: 0 };
    const parent = Array.from({ length: faceCount }, (_, index) => index);
    const find = (value) => {
      let root = value;
      while (parent[root] !== root) root = parent[root];
      while (parent[value] !== value) { const next = parent[value]; parent[value] = root; value = next; }
      return root;
    };
    const union = (left, right) => {
      const a = find(left); const b = find(right);
      if (a !== b) parent[b] = a;
    };
    // Interpolation reaches the same shared edge from opposite tetrahedra with small floating
    // error. Weld at 1e-7, far below the smallest sampling cell, without joining nearby sheets.
    const vertexKey = (point) => point.map((value) => Math.round(value * 10000000)).join(",");
    const owners = new Map();
    const vertices = new Set();
    const edgeIncidence = new Map();
    const edgeGeometry = new Map();
    const edgeOwners = new Map();
    for (let face = 0; face < faceCount; face += 1) {
      const facePoints = triangles.slice(face * 3, face * 3 + 3);
      const keys = facePoints.map(vertexKey);
      keys.forEach((key) => {
        vertices.add(key);
        if (owners.has(key)) union(face, owners.get(key)); else owners.set(key, face);
      });
      for (const [a, b] of [[0, 1], [1, 2], [2, 0]]) {
        const edge = keys[a] < keys[b] ? `${keys[a]}|${keys[b]}` : `${keys[b]}|${keys[a]}`;
        edgeIncidence.set(edge, (edgeIncidence.get(edge) || 0) + 1);
        if (!edgeGeometry.has(edge)) edgeGeometry.set(edge, [facePoints[a], facePoints[b]]);
        if (!edgeOwners.has(edge)) edgeOwners.set(edge, face);
      }
    }
    const components = new Set(parent.map((_value, index) => find(index))).size;
    const incidences = [...edgeIncidence.values()];
    const result = {
      components,
      vertices: vertices.size,
      edges: edgeIncidence.size,
      faces: faceCount,
      euler: vertices.size - edgeIncidence.size + faceCount,
      boundary_edges: incidences.filter((count) => count === 1).length,
      nonmanifold_edges: incidences.filter((count) => count > 2).length,
    };
    if (layer?.x_domain && layer?.y_domain && layer?.z_domain) {
      const domains = [layer.x_domain, layer.y_domain, layer.z_domain];
      const boundary = [...edgeIncidence.entries()].filter(([, count]) => count === 1);
      const seams = Array.from({ length: 3 }, () => [new Map(), new Map()]);
      const appendSeam = (map, key, edge) => {
        const entries = map.get(key) || [];
        entries.push(edge); map.set(key, entries);
      };
      let domainBoundaryEdges = 0;
      boundary.forEach(([edge]) => {
        const points = edgeGeometry.get(edge);
        if (!points) return;
        let assigned = false;
        for (let axis = 0; axis < 3; axis += 1) {
          const tolerance = Math.max(1e-7, (domains[axis][1] - domains[axis][0]) * 1e-6);
          for (let side = 0; side < 2; side += 1) {
            if (!points.every((point) => Math.abs(point[axis] - domains[axis][side]) <= tolerance)) continue;
            const signature = points.map((point) => point.filter((_value, index) => index !== axis).map((value) => Math.round(value * 1000000)).join(",")).sort().join("|");
            appendSeam(seams[axis][side], signature, edge); domainBoundaryEdges += 1; assigned = true; break;
          }
          if (assigned) break;
        }
        if (!assigned && points.every((point) => domains.some((domain, axis) => Math.abs(point[axis] - domain[0]) <= Math.max(1e-7, (domain[1] - domain[0]) * 1e-6) || Math.abs(point[axis] - domain[1]) <= Math.max(1e-7, (domain[1] - domain[0]) * 1e-6)))) domainBoundaryEdges += 1;
      });
      let matchedEdges = 0;
      seams.forEach(([low, high]) => low.forEach((lowEdges, key) => {
        const highEdges = high.get(key) || [];
        const paired = Math.min(lowEdges.length, highEdges.length);
        matchedEdges += 2 * paired;
        for (let index = 0; index < paired; index += 1) union(edgeOwners.get(lowEdges[index]), edgeOwners.get(highEdges[index]));
      }));
      result.periodic_boundary_edges = domainBoundaryEdges;
      result.periodic_matched_edges = matchedEdges;
      result.periodic_unmatched_edges = boundary.length - matchedEdges;
      result.periodic_components = new Set(parent.map((_value, index) => find(index))).size;
      let maximumPeriodicDelta = 0;
      for (let axis = 0; axis < 3; axis += 1) for (let first = 0; first <= 8; first += 1) for (let second = 0; second <= 8; second += 1) {
        const otherAxes = [0, 1, 2].filter((value) => value !== axis);
        const low = [0, 0, 0]; const high = [0, 0, 0];
        low[axis] = domains[axis][0]; high[axis] = domains[axis][1];
        low[otherAxes[0]] = high[otherAxes[0]] = domains[otherAxes[0]][0] + (domains[otherAxes[0]][1] - domains[otherAxes[0]][0]) * first / 8;
        low[otherAxes[1]] = high[otherAxes[1]] = domains[otherAxes[1]][0] + (domains[otherAxes[1]][1] - domains[otherAxes[1]][0]) * second / 8;
        try {
          const lowValue = evaluateRelation(layer.relationship, { x: low[0], y: low[1], z: low[2] });
          const highValue = evaluateRelation(layer.relationship, { x: high[0], y: high[1], z: high[2] });
          maximumPeriodicDelta = Math.max(maximumPeriodicDelta, Math.abs(lowValue - highValue));
        } catch { maximumPeriodicDelta = Infinity; }
      }
      result.periodic_function_max_delta = maximumPeriodicDelta;
    }
    return result;
  }

  function textSprite(text, color) {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    canvas.width = 256;
    canvas.height = 64;
    context.font = "600 26px system-ui";
    context.fillStyle = color;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(text, 128, 32);
    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true }));
    sprite.scale.set(1.3, 0.325, 1);
    return sprite;
  }

  function threeScene(spec, context) {
    const stage = context.stage;
    const drawing = html("div", "viz-v2-drawing viz-v2-three");
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    const clipControl = spec.controls.find((control) => control.id === "clip_z");
    const clippingPlane = clipControl ? new THREE.Plane(new THREE.Vector3(0, -1, 0), Number(clipControl.value)) : null;
    renderer.localClippingEnabled = Boolean(clippingPlane);
    renderer.setPixelRatio(Math.min(2, global.devicePixelRatio || 1));
    renderer.domElement.tabIndex = 0;
    renderer.domElement.setAttribute("role", "img");
    renderer.domElement.setAttribute("aria-label", [spec.aria_label, context.t("visualization.rotateHint")].join(" "));
    drawing.appendChild(renderer.domElement);
    stage.appendChild(drawing);
    const state = html("p", "viz-v2-state");
    state.setAttribute("role", "status");
    state.setAttribute("aria-live", "polite");
    stage.appendChild(state);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000);
    const group = new THREE.Group();
    scene.add(group, new THREE.HemisphereLight(0xffffff, 0x555555, 1.8));
    const directional = new THREE.DirectionalLight(0xffffff, 2.4);
    directional.position.set(5, 8, 7);
    scene.add(directional);
    const bounds = new THREE.Box3();
    let triangleCount = 0;
    let drawCalls = 0;
    let topology = null;
    let surfaceDiagnostics = null;
    let controlRevision = 0;
    let latestControlValues = {};
    const bondObjects = [];
    const lonePairObjects = [];
    let pathMarker = null;
    let lorentzLine = null;
    const lorentzVectors = new Map();
    const familyObjects = new Map();
    const surfaceRecords = [];
    let viewRevision = 0;
    let phaseProgress = 0;
    let raf = 0; let playing = false; let elapsed = 0; let lastTick = 0; let lastDraw = 0; let observedFrameInterval = 0;
    const toWorld = ([x, y, z]) => [x, z, y];
    spec.scene.layers.forEach((layer, index) => {
      const shade = new THREE.Color(paletteValue(context, layer.color, index));
      let object;
      if (["explicit_surface", "implicit_surface", "parametric_surface"].includes(layer.type)) {
        const triangles = layer.type === "explicit_surface" ? explicitTriangles(layer)
          : layer.type === "implicit_surface" ? implicitTriangles(layer) : parametricTriangles(layer);
        triangleCount += Math.floor(triangles.length / 3);
        if (triangles.diagnostics) surfaceDiagnostics = triangles.diagnostics;
        if (!triangles.length) throw new Error("surface has no finite triangles inside the selected domain");
        topology = meshTopology(triangles, layer);
        const positions = new Float32Array(triangles.length * 3);
        triangles.forEach((point, pointIndex) => positions.set(toWorld(point), pointIndex * 3));
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        const vertical = triangles.map((point) => point[2]);
        const low = Math.min(...vertical); const high = Math.max(...vertical);
        const lowColor = new THREE.Color(context.palette[1]);
        const middleColor = new THREE.Color(context.palette[3]);
        const highColor = new THREE.Color(context.palette[0]);
        const colours = new Float32Array(triangles.length * 3);
        vertical.forEach((value, vertex) => {
          const amount = Math.max(0, Math.min(1, (value - low) / Math.max(1e-9, high - low)));
          const shadeAtVertex = amount < 0.5
            ? lowColor.clone().lerp(middleColor, amount * 2)
            : middleColor.clone().lerp(highColor, (amount - 0.5) * 2);
          colours.set([shadeAtVertex.r, shadeAtVertex.g, shadeAtVertex.b], vertex * 3);
        });
        geometry.setAttribute("color", new THREE.BufferAttribute(colours, 3));
        geometry.computeVertexNormals();
        object = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.58, metalness: 0.02, side: THREE.DoubleSide, transparent: true, opacity: 0.94, clippingPlanes: clippingPlane ? [clippingPlane] : [] }));
        const wire = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: context.neutral, wireframe: true, transparent: true, opacity: 0.12, clippingPlanes: clippingPlane ? [clippingPlane] : [] }));
        wire.renderOrder = 2;
        group.add(wire);
        surfaceRecords.push({ layer, object, wire });
        drawCalls += 1;
      } else if (layer.type === "sphere" || layer.type === "point") {
        object = new THREE.Mesh(new THREE.SphereGeometry(layer.size || 0.2, 24, 16), new THREE.MeshStandardMaterial({ color: shade, roughness: 0.5 }));
        object.position.set(...toWorld(layer.position));
        if (spec.family === "molecular_geometry" && layer.label.startsWith("lone pair")) lonePairObjects.push(object);
      } else if (layer.type === "box") {
        object = new THREE.Mesh(new THREE.BoxGeometry(layer.size, layer.size, layer.size), new THREE.MeshStandardMaterial({ color: shade }));
        object.position.set(...toWorld(layer.position));
      } else if (layer.type === "line") {
        object = new THREE.Line(new THREE.BufferGeometry().setFromPoints(layer.points.map((point) => new THREE.Vector3(...toWorld(point)))), new THREE.LineBasicMaterial({ color: shade }));
        if (spec.family === "lorentz_force") lorentzLine = object;
      } else if (layer.type === "vector") {
        const origin = new THREE.Vector3(...toWorld(layer.from));
        const delta = new THREE.Vector3(...toWorld(layer.to)).sub(origin);
        object = new THREE.ArrowHelper(delta.clone().normalize(), origin, delta.length(), shade, 0.3, 0.18);
        if (spec.family === "molecular_geometry") bondObjects.push(object);
        if (spec.family === "lorentz_force") lorentzVectors.set(layer.label, object);
      } else if (layer.type === "plane") {
        const geometry = new THREE.PlaneGeometry(8, 8, 8, 8);
        const normal = new THREE.Vector3(...toWorld(layer.normal)).normalize();
        object = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: shade, side: THREE.DoubleSide, transparent: true, opacity: 0.34 }));
        object.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
        object.position.copy(normal.multiplyScalar(layer.constant / Math.max(1e-6, new THREE.Vector3(...layer.normal).length())));
      }
      if (object) {
        object.userData.vizLabel = layer.label || "";
        object.userData.vizType = layer.type;
        if (layer.label) {
          const records = familyObjects.get(layer.label) || [];
          records.push(object); familyObjects.set(layer.label, records);
        }
        group.add(object); object.updateMatrixWorld(true); bounds.expandByObject(object); drawCalls += 1;
      }
    });
    if (spec.family === "parametric_surface") {
      pathMarker = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 12), new THREE.MeshStandardMaterial({ color: new THREE.Color(context.palette[0]) }));
      group.add(pathMarker); bounds.expandByObject(pathMarker); drawCalls += 1;
    }
    const surfaceLayer = spec.scene.layers.find((layer) => ["explicit_surface", "implicit_surface"].includes(layer.type));
    if (surfaceLayer) {
      const axisMaterial = new THREE.LineBasicMaterial({ color: new THREE.Color(context.neutral) });
      const domains = [surfaceLayer.x_domain, surfaceLayer.y_domain, surfaceLayer.z_domain];
      const origins = [
        Math.max(domains[0][0], Math.min(domains[0][1], 0)),
        Math.max(domains[1][0], Math.min(domains[1][1], 0)),
        Math.max(domains[2][0], Math.min(domains[2][1], 0)),
      ];
      const axisGroup = new THREE.Group();
      const axisData = [
        ["x", [domains[0][0], origins[1], origins[2]], [domains[0][1], origins[1], origins[2]]],
        ["y", [origins[0], domains[1][0], origins[2]], [origins[0], domains[1][1], origins[2]]],
        ["z", [origins[0], origins[1], domains[2][0]], [origins[0], origins[1], domains[2][1]]],
      ];
      axisData.forEach(([label, from, to]) => {
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...toWorld(from)), new THREE.Vector3(...toWorld(to))]), axisMaterial);
        axisGroup.add(line);
        const labelSprite = textSprite(label, context.neutral);
        labelSprite.position.set(...toWorld(to));
        labelSprite.position.addScalar(0.22);
        axisGroup.add(labelSprite);
        const axisIndex = label === "x" ? 0 : label === "y" ? 1 : 2;
        [domains[axisIndex][0], 0, domains[axisIndex][1]].forEach((tickValue) => {
          if (tickValue < domains[axisIndex][0] || tickValue > domains[axisIndex][1]) return;
          const tickPosition = [...origins]; tickPosition[axisIndex] = tickValue;
          const tick = textSprite(Number(tickValue.toFixed(2)).toString(), context.neutral);
          tick.scale.set(0.78, 0.195, 1);
          tick.position.set(...toWorld(tickPosition));
          tick.position.x += 0.16; tick.position.y += 0.16;
          axisGroup.add(tick);
        });
      });
      group.add(axisGroup);
      const formula = html("div", "viz-v2-formula");
      const strong = html("strong", "", surfaceLayer.label);
      const cue = html("span", "", "Colour shows signed height; gaps mark undefined or out-of-view samples.");
      formula.append(strong, cue);
      drawing.appendChild(formula);
    } else {
      group.add(new THREE.AxesHelper(4));
    }
    const center = bounds.isEmpty() ? new THREE.Vector3() : bounds.getCenter(new THREE.Vector3());
    const extentSize = bounds.isEmpty() ? 5 : Math.max(2, bounds.getSize(new THREE.Vector3()).length());
    camera.near = Math.max(0.01, extentSize / 1000);
    camera.far = Math.max(100, extentSize * 12);
    camera.position.copy(center).add(new THREE.Vector3(1.6, 1.25, 1.9).normalize().multiplyScalar(extentSize * 1.7));
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    const resize = () => {
      const width = Math.max(1, drawing.clientWidth || 720);
      const height = Math.max(240, spec.height - 110);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
      const gl = renderer.getContext();
      const pixels = new Uint8Array(4 * 24 * 24);
      gl.readPixels(Math.max(0, Math.floor(renderer.domElement.width / 2) - 12), Math.max(0, Math.floor(renderer.domElement.height / 2) - 12), 24, 24, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      let nonzero = 0;
      for (let index = 0; index < pixels.length; index += 4) if (pixels[index] || pixels[index + 1] || pixels[index + 2] || pixels[index + 3]) nonzero += 1;
      const gpu = renderer.info.render;
      const submittedGeometry = gpu.calls > 0 && (gpu.triangles > 0 || gpu.lines > 0 || gpu.points > 0);
      const glError = gl.getError();
      let geometryState = Math.round(group.rotation.x * 100000) + Math.round(group.rotation.y * 100000) * 3;
      bondObjects.forEach((bond, index) => { const direction = bond.userData.vizDirection || [0, 0, 0]; geometryState += (index + 1) * (bond.visible ? 97 + Math.round(direction[0] * 101 + direction[1] * 211 + direction[2] * 307) : 0); });
      lonePairObjects.forEach((pair, index) => { geometryState += (index + 1) * (pair.visible ? 193 + Math.round(pair.position.x * 101 + pair.position.y * 211 + pair.position.z * 307) : 0); });
      if (pathMarker) geometryState += Math.round(pathMarker.position.x * 101 + pathMarker.position.y * 211 + pathMarker.position.z * 307);
      if (lorentzLine) { const positions = lorentzLine.geometry.getAttribute("position"); if (positions?.count) geometryState += Math.round(positions.getX(0) * 101 + positions.getY(positions.count - 1) * 211 + positions.getZ(0) * 307 + lorentzLine.rotation.y * 1000); }
      lorentzVectors.forEach((arrow, label) => {
        const direction = arrow.userData.vizDirection || [0, 0, 0];
        const labelSignature = label.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0);
        geometryState += Math.round(
          arrow.position.x * 101 + arrow.position.y * 211 + arrow.position.z * 307
          + direction[0] * 401 + direction[1] * 503 + direction[2] * 607 + labelSignature,
        );
      });
      familyObjects.forEach((objects, label) => {
        const labelSignature = label.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0);
        objects.forEach((object, index) => {
          geometryState += labelSignature + (index + 1) * Math.round(object.position.x * 101 + object.position.y * 211 + object.position.z * 307);
          const positions = object.geometry?.getAttribute?.("position");
          if (positions?.count) {
            const requestedDrawCount = object.geometry.drawRange?.count;
            const drawCount = Number.isFinite(requestedDrawCount) ? requestedDrawCount : positions.count;
            geometryState += Math.round(
              positions.getX(0) * 401 + positions.getY(0) * 503 + positions.getZ(0) * 607
              + positions.getX(positions.count - 1) * 701 + positions.getY(positions.count - 1) * 809 + positions.getZ(positions.count - 1) * 907
              + drawCount,
            );
          }
          const direction = object.userData.vizDirection;
          if (direction) geometryState += Math.round(direction[0] * 1013 + direction[1] * 1213 + direction[2] * 1423);
        });
      });
      geometryState += Math.round(phaseProgress * 1000003);
      geometryState += viewRevision * 15485863;
      if (clippingPlane) geometryState += Math.round(clippingPlane.constant * 10007);
      const visualStateSignature = geometryState;
      recordEvidence(stage, { rendered: drawCalls > 0 && submittedGeometry && glError === gl.NO_ERROR, renderer: "three", nonzero_pixel_samples: nonzero, draw_calls: drawCalls, gpu_calls: gpu.calls, gpu_triangles: gpu.triangles, gpu_lines: gpu.lines, gpu_points: gpu.points, gl_error: glError, triangles: triangleCount, topology, surface_diagnostics: surfaceDiagnostics, family: spec.family, control_revision: controlRevision, control_values: latestControlValues, geometry_signature: visualStateSignature, visual_state_signature: visualStateSignature, animation_state: playing ? "playing" : phaseProgress >= 1 ? "complete" : "paused", animation_progress: phaseProgress, observed_frame_interval_ms: observedFrameInterval, state_description: state.textContent });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(drawing);
    resize();
    let dragging = false; let previous = null;
    const pointerDown = (event) => {
      dragging = true; previous = [event.clientX, event.clientY];
      try { renderer.domElement.setPointerCapture(event.pointerId); } catch { /* synthetic QA events have no active pointer */ }
    };
    const pointerMove = (event) => {
      if (!dragging || !previous) return;
      group.rotation.y += (event.clientX - previous[0]) * 0.009;
      group.rotation.x += (event.clientY - previous[1]) * 0.009;
      previous = [event.clientX, event.clientY]; resize();
    };
    const pointerUp = () => { dragging = false; previous = null; };
    const keyDown = (event) => {
      const directions = { ArrowLeft: [-0.12, 0], ArrowRight: [0.12, 0], ArrowUp: [0, -0.12], ArrowDown: [0, 0.12] };
      if (!directions[event.key]) return;
      event.preventDefault(); group.rotation.y += directions[event.key][0]; group.rotation.x += directions[event.key][1]; resize();
    };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointermove", pointerMove);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.domElement.addEventListener("pointercancel", pointerUp);
    renderer.domElement.addEventListener("keydown", keyDown);
    const animated = Boolean(spec.scene.animation) || spec.scene.layers.some((layer) => layer.animation);
    const orbitEnabled = spec.controls.some((control) => control.id === "orbit");
    const duration = Math.max(2000, (spec.scene.layers.find((layer) => layer.animation)?.animation.duration || spec.scene.animation?.duration || 8) * 1000);
    const phaseMode = spec.scene.layers.some((layer) => layer.animation?.mode === "phase");
    const frameInterval = 1000 / Math.max(1, Math.min(30, spec.budget.max_fps));
    let transportControls = null;
    const labelledObject = (label) => familyObjects.get(label)?.[0] || null;
    const replaceLinePoints = (object, points) => {
      if (!object || points.length < 2) return;
      object.geometry.dispose();
      object.geometry = new THREE.BufferGeometry().setFromPoints(points.map((point) => new THREE.Vector3(...toWorld(point))));
    };
    const setArrow = (object, from, to) => {
      if (!object) return;
      const origin = new THREE.Vector3(...toWorld(from)); const delta = new THREE.Vector3(...toWorld(to)).sub(origin);
      const length = Math.max(0.001, delta.length()); const direction = delta.normalize();
      object.position.copy(origin); object.setDirection(direction); object.setLength(length, Math.min(0.3, length * 0.35), Math.min(0.18, length * 0.22));
      object.userData.vizDirection = direction.toArray();
    };
    const updateSurfacePhase = (progress) => {
      phaseProgress = progress;
      surfaceRecords.forEach((record) => {
        if (record.layer.type !== "explicit_surface" || record.layer.animation?.mode !== "phase") return;
        const span = record.layer.x_domain[1] - record.layer.x_domain[0];
        const triangles = explicitTriangles(record.layer, progress * span * 0.25);
        if (!triangles.length) return;
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(triangles.length * 3);
        triangles.forEach((point, pointIndex) => positions.set(toWorld(point), pointIndex * 3));
        geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        geometry.computeVertexNormals();
        record.object.geometry.dispose(); record.object.geometry = geometry;
        record.wire.geometry = geometry;
        topology = meshTopology(triangles, record.layer);
      });
    };
    const updateFamilyAnimation = (progress) => {
      phaseProgress = progress;
      if (spec.family === "vector_field_3d") {
        const base = [stateNumber(latestControlValues, "point_x", 1), stateNumber(latestControlValues, "point_y", 1), stateNumber(latestControlValues, "point_z", 1)];
        const angle = progress * 2 * Math.PI; const pointValues = [
          base[0] * Math.cos(angle) - base[1] * Math.sin(angle),
          base[0] * Math.sin(angle) + base[1] * Math.cos(angle),
          Math.max(-2.8, Math.min(2.8, base[2] * Math.exp(progress * 0.35))),
        ];
        const vector = [-pointValues[1], pointValues[0], pointValues[2]]; const magnitude = Math.max(1, Math.hypot(...vector));
        labelledObject("selected point (1,1,1)")?.position.set(...toWorld(pointValues));
        setArrow(labelledObject("local F=(-1,1,1)"), pointValues, pointValues.map((value, index) => value + 0.9 * vector[index] / magnitude));
      } else if (spec.family === "lorenz_attractor") {
        const line = labelledObject("Lorenz trajectory σ=10, ρ=28, β=8/3");
        const point = labelledObject("current state"); const positions = line?.geometry?.getAttribute("position");
        if (positions?.count) {
          const visible = Math.max(2, Math.min(positions.count, Math.ceil(positions.count * Math.max(0.004, progress))));
          line.geometry.setDrawRange(0, visible);
          point?.position.set(positions.getX(visible - 1), positions.getY(visible - 1), positions.getZ(visible - 1));
        }
      } else if (spec.family === "electromagnetic_wave") {
        const wave = electromagneticWavePoints(latestControlValues, progress);
        replaceLinePoints(labelledObject("electric field E ⟂ propagation"), wave.electric);
        replaceLinePoints(labelledObject("magnetic field B ⟂ E"), wave.magnetic);
      }
    };
    const tick = (now) => {
      raf = 0;
      if (!playing || !context.renderActive()) { lastTick = 0; return; }
      if (!lastTick) lastTick = now;
      elapsed = Math.min(duration, elapsed + Math.max(0, now - lastTick)); lastTick = now;
      const progress = elapsed / duration;
      if (now - lastDraw >= frameInterval || progress >= 1) {
        observedFrameInterval = lastDraw ? now - lastDraw : 0;
        lastDraw = now;
        latestControlValues = animationControlValues(spec, latestControlValues, progress);
        applyThreeControls(latestControlValues);
        if (phaseMode) updateSurfacePhase(progress);
        else if (["vector_field_3d", "lorenz_attractor", "electromagnetic_wave"].includes(spec.family)) updateFamilyAnimation(progress);
        else { phaseProgress = progress; group.rotation.y = progress * Math.PI * 2; }
        state.textContent = animationStatusText(stateDescription(spec, latestControlValues), progress >= 1 ? "complete" : "playing", progress);
        resize();
      }
      if (progress < 1) raf = requestAnimationFrame(tick);
      else { playing = false; transportControls?.setPressed("play", false); transportControls?.setPressed("pause", true); }
    };
    const play = () => {
      if ((!animated && !orbitEnabled) || playing) return;
      if (context.reducedMotion) {
        playing = false; elapsed = duration; phaseProgress = 1;
        if (phaseMode) updateSurfacePhase(1); else updateFamilyAnimation(1);
        state.textContent = animationStatusText(stateDescription(spec, latestControlValues), "complete", 1);
        transportControls?.setPressed("play", false); transportControls?.setPressed("pause", true); resize(); return;
      }
      if (elapsed >= duration) elapsed = 0;
      playing = true; lastTick = 0; transportControls?.setPressed("play", true); transportControls?.setPressed("pause", false);
      if (!raf && context.renderActive()) raf = requestAnimationFrame(tick);
    };
    const pause = () => { playing = false; lastTick = 0; if (raf) cancelAnimationFrame(raf); raf = 0; transportControls?.setPressed("play", false); transportControls?.setPressed("pause", true); resize(); };
    const restart = () => { pause(); elapsed = 0; phaseProgress = 0; group.rotation.y = 0; if (phaseMode) updateSurfacePhase(0); else updateFamilyAnimation(0); transportControls?.setPressed("restart", false); transportControls?.setPressed("pause", false); resize(); play(); };
    const resetView = () => { pause(); elapsed = 0; phaseProgress = 0; viewRevision += 1; group.rotation.set(0, 0, 0); if (phaseMode) updateSurfacePhase(0); else updateFamilyAnimation(0); transportControls?.setPressed("reset_view", false); resize(); };
    const applyThreeControls = (values) => {
      if (clippingPlane) clippingPlane.constant = stateNumber(values, "clip_z", Number(clipControl.value));
      if (spec.family === "plane_intersection") group.rotation.y = stateNumber(values, "orbit", 1) * Math.PI / 10;
      if (spec.family === "vector_field_3d") {
        const pointValues = [stateNumber(values, "point_x", 1), stateNumber(values, "point_y", 1), stateNumber(values, "point_z", 1)];
        const vector = [-pointValues[1], pointValues[0], pointValues[2]]; const magnitude = Math.max(1, Math.hypot(...vector));
        labelledObject("selected point (1,1,1)")?.position.set(...toWorld(pointValues));
        setArrow(labelledObject("local F=(-1,1,1)"), pointValues, pointValues.map((value, index) => value + 0.9 * vector[index] / magnitude));
      }
      if (spec.family === "lorenz_attractor") {
        const lorenz = lorenzPoints(values); const line = labelledObject("Lorenz trajectory σ=10, ρ=28, β=8/3");
        replaceLinePoints(line, lorenz.points);
        if (line) line.geometry.setDrawRange(0, line.geometry.getAttribute("position").count);
        const current = lorenz.points.at(-1); if (current) labelledObject("current state")?.position.set(...toWorld(current));
      }
      if (spec.family === "electromagnetic_wave") {
        const wave = electromagneticWavePoints(values, phaseProgress);
        replaceLinePoints(labelledObject("electric field E ⟂ propagation"), wave.electric);
        replaceLinePoints(labelledObject("magnetic field B ⟂ E"), wave.magnetic);
      }
      if (spec.family === "molecular_geometry" && bondObjects.length) {
        const molecule = String(values.molecule || "ch4");
        const directions = {
          ch4: [[1,1,1], [1,-1,-1], [-1,1,-1], [-1,-1,1]],
          nh3: [[1,-0.5,0.8], [-1,-0.5,0.8], [0,1,0.8]],
          h2o: [[1,0,0.78], [-1,0,0.78]],
          sf6: [[1,0,0], [-1,0,0], [0,1,0], [0,-1,0], [0,0,1], [0,0,-1]],
          brf5: [[1,0,0], [-1,0,0], [0,1,0], [0,-1,0], [0,0,1]],
        }[molecule] || [];
        bondObjects.forEach((bond, index) => {
          bond.visible = index < directions.length;
          if (bond.visible) { const direction = new THREE.Vector3(...toWorld(directions[index])).normalize(); bond.setDirection(direction); bond.setLength(2, 0.3, 0.18); bond.userData.vizDirection = direction.toArray(); }
        });
        const lonePairs = {
          ch4: [], nh3: [[0, 0, -1.35]], h2o: [[0.9, 0, -1.05], [-0.9, 0, -1.05]],
          sf6: [], brf5: [[0, 0, -1.35]],
        }[molecule] || [];
        lonePairObjects.forEach((pair, index) => {
          pair.visible = index < lonePairs.length;
          if (pair.visible) pair.position.set(...toWorld(lonePairs[index]));
        });
      }
      if (spec.family === "parametric_surface" && pathMarker) {
        const u = 2 * Math.PI * ((stateNumber(values, "path_position", 1) + stateNumber(values, "playback", 0)) % 10) / 10;
        const parametric = surfaceRecords.find((record) => record.layer.type === "parametric_surface")?.layer;
        const point = parametric ? [parametric.x_expression, parametric.y_expression, parametric.z_expression].map((expression) => global.MutaViz.evaluateExpressionV2(expression, { u, v: 0.7, x: 0, y: 0, z: 0 })) : [0, 0, 0];
        pathMarker.position.set(...toWorld(point));
      }
      if (spec.family === "lorentz_force" && lorentzLine) {
        const charge = Math.max(0.1, Math.abs(stateNumber(values, "charge", 1)));
        const field = Math.max(0.1, Math.abs(stateNumber(values, "field", 2)));
        const speed = Math.max(0.1, Math.abs(stateNumber(values, "speed", 3)));
        const radius = Math.max(0.05, Math.min(3.5, speed / (charge * field)));
        const pitch = Math.max(0.12, speed / (field * 12));
        const points = Array.from({ length: 100 }, (_unused, index) => { const t = index * 0.16; return new THREE.Vector3(...toWorld([radius * Math.cos(t), pitch * t - 3, radius * Math.sin(t)])); });
        lorentzLine.geometry.dispose(); lorentzLine.geometry = new THREE.BufferGeometry().setFromPoints(points);
        const phase = stateNumber(values, "playback", 0) * Math.PI / 8;
        const particle = [radius * Math.cos(phase), pitch * phase - 3, radius * Math.sin(phase)];
        const velocity = [-radius * Math.sin(phase), pitch, radius * Math.cos(phase)];
        const force = [-radius * Math.cos(phase) * charge * field, 0, -radius * Math.sin(phase) * charge * field];
        const setVector = (label, originValues, deltaValues, scaleValue=1) => { const arrow=lorentzVectors.get(label); if (!arrow) return; const origin=new THREE.Vector3(...toWorld(originValues)); const delta=new THREE.Vector3(...toWorld(deltaValues)); const length=Math.max(0.2,Math.min(2.4,delta.length()*scaleValue)); const direction=delta.normalize(); arrow.position.copy(origin); arrow.setDirection(direction); arrow.setLength(length,0.3,0.18); arrow.userData.vizDirection=direction.toArray(); };
        setVector("velocity v", particle, velocity, 0.65);
        setVector("Lorentz force q(v×B)", particle, force, 0.35);
      }
    };
    const controls = buildControls(stage, spec, (_values, id) => {
      latestControlValues = { ..._values };
      controlRevision += 1;
      state.textContent = stateDescription(spec, latestControlValues);
      applyThreeControls(latestControlValues);
      const changedControl = spec.controls.find((control) => control.id === id);
      if (id === "orbit" && changedControl?.type === "button") {
        viewRevision += 1;
        group.rotation.y += Math.PI / 12;
        resize();
        play();
      } else if (id === "play") play();
      else if (id === "pause") pause();
      else if (id === "restart") restart();
      else if (id === "reset_view") resetView();
      resize();
    }, context.t);
    transportControls = controls;
    latestControlValues = { ...controls.values };
    applyThreeControls(latestControlValues);
    state.textContent = stateDescription(spec, latestControlValues);
    resize();
    const removeActivity = context.onActivity((active) => {
      if (!active && raf) { cancelAnimationFrame(raf); raf = 0; lastTick = 0; }
      else if (active && playing && !raf) { lastTick = 0; raf = requestAnimationFrame(tick); }
      if (active) renderer.render(scene, camera);
    });
    attachFallback(stage, spec);
    return () => {
      pause(); controls.cleanup(); removeActivity(); observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("pointermove", pointerMove);
      renderer.domElement.removeEventListener("pointerup", pointerUp);
      renderer.domElement.removeEventListener("pointercancel", pointerUp);
      renderer.domElement.removeEventListener("keydown", keyDown);
      group.traverse((child) => {
        child.geometry?.dispose?.();
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.filter(Boolean).forEach((material) => { material.map?.dispose?.(); material.dispose?.(); });
      });
      renderer.dispose(); renderer.forceContextLoss?.();
    };
  }

  async function render(spec, context) {
    context.stage.replaceChildren();
    context.stage.classList.add("viz-v2-stage");
    let cleanup;
    if (spec.renderer === "svg") cleanup = svgScene(spec, context);
    else if (spec.renderer === "canvas") cleanup = canvasScene(spec, context);
    else cleanup = threeScene(spec, context);
    const completeCleanup = () => { cleanup?.(); context.stage.classList.remove("viz-v2-stage"); };
    global.addEventListener("beforeunload", completeCleanup, { once: true });
    global.parent?.postMessage?.({ type: "muta-viz-evidence", evidence: global.__mutaVizEvidence }, "*");
    return completeCleanup;
  }

  global.MutaVizV2 = Object.freeze({ render });
})(window);
