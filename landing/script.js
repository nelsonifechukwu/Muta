(() => {
  "use strict";

  const navToggle = document.getElementById("nav-toggle");
  const mobileNav = document.getElementById("mobile-nav");

  const setMenu = (open) => {
    if (!navToggle || !mobileNav) return;
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    mobileNav.hidden = !open;
    document.body.classList.toggle("nav-open", open);
  };

  navToggle?.addEventListener("click", () => {
    setMenu(navToggle.getAttribute("aria-expanded") !== "true");
  });

  mobileNav?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => setMenu(false));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenu(false);
  });

  const desktopBreakpoint = window.matchMedia("(min-width: 1021px)");
  const resetDesktopMenu = (event) => {
    if (event.matches) setMenu(false);
  };
  desktopBreakpoint.addEventListener?.("change", resetDesktopMenu);

  const demoCopy = {
    ask: {
      prompt: "Before we touch a formula: when you look at a speedometer, what does 60 km/h describe?",
      answer: "How fast I am moving right now.",
      response: "Exactly. A derivative is the mathematical version of that “right now.” Want to watch it happen?",
      action: "Show me",
      href: "#lesson",
      status: "concept linked to the mini lab",
      statusIcon: "→",
    },
    photo: {
      prompt: "I can read the page. Which line feels wrong to you?",
      answer: "Line 4. I changed the sign, but I don't know why.",
      response: "Good catch. Let's check that transformation instead of restarting the whole problem.",
      action: "Check the step",
      href: "/chat/",
      status: "maths step checked locally",
      statusIcon: "✓",
    },
    voice: {
      prompt: "I'm listening. Tell me the part that feels strange.",
      answer: "If gravity pulls down, why doesn't the Moon fall?",
      response: "It is falling — sideways fast enough to keep missing Earth. Let's draw the orbit together.",
      action: "Keep talking",
      href: "/chat/",
      status: "voice processed locally",
      statusIcon: "∿",
    },
  };

  const demoPrompt = document.getElementById("demo-prompt");
  const demoAnswer = document.getElementById("demo-answer");
  const demoResponse = document.getElementById("demo-response");
  const demoAction = document.getElementById("demo-action");
  const demoStatusText = document.getElementById("demo-status-text");
  const demoStatusIcon = document.getElementById("demo-status-icon");
  const demoTabs = Array.from(document.querySelectorAll("[data-demo-mode]"));

  const selectDemoMode = (button) => {
    const copy = demoCopy[button.dataset.demoMode];
    if (!copy || !demoPrompt || !demoAnswer || !demoResponse || !demoAction) return;
    demoTabs.forEach((tab) => {
      const selected = tab === button;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    demoPrompt.textContent = copy.prompt;
    demoAnswer.textContent = copy.answer;
    demoResponse.textContent = copy.response;
    demoAction.childNodes[0].textContent = `${copy.action} `;
    demoAction.href = copy.href;
    if (demoStatusText) demoStatusText.textContent = copy.status;
    if (demoStatusIcon) demoStatusIcon.textContent = copy.statusIcon;
  };

  demoTabs.forEach((button, index) => {
    button.addEventListener("click", () => selectDemoMode(button));
    button.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const next = demoTabs[(index + direction + demoTabs.length) % demoTabs.length];
      next.focus();
      selectDemoMode(next);
    });
  });

  const canvas = document.getElementById("derivative-canvas");
  const slider = document.getElementById("derivative-slider");
  const readoutX = document.getElementById("readout-x");
  const readoutY = document.getElementById("readout-y");
  const readoutSlope = document.getElementById("readout-slope");
  const lessonStatus = document.getElementById("lesson-status");

  if (canvas && slider) {
    const ctx = canvas.getContext("2d");
    let pointX = Number(slider.value);
    let dragging = false;

    const draw = () => {
      if (!ctx) return;
      const rect = canvas.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;
      if (!width || !height) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);

      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const pad = Math.max(28, Math.min(42, width * 0.07));
      const plotWidth = width - pad * 1.45;
      const plotHeight = height - pad * 1.45;
      const xMax = 5;
      const yMax = 25;
      const px = (x) => pad + (x / xMax) * plotWidth;
      const py = (y) => height - pad - (y / yMax) * plotHeight;

      ctx.save();
      ctx.strokeStyle = "rgba(188,181,197,.12)";
      ctx.lineWidth = 1;
      for (let x = 0; x <= xMax; x += 1) {
        ctx.beginPath();
        ctx.moveTo(px(x), py(0));
        ctx.lineTo(px(x), py(yMax));
        ctx.stroke();
      }
      for (let y = 0; y <= yMax; y += 5) {
        ctx.beginPath();
        ctx.moveTo(px(0), py(y));
        ctx.lineTo(px(xMax), py(y));
        ctx.stroke();
      }

      ctx.strokeStyle = "rgba(248,243,233,.46)";
      ctx.beginPath();
      ctx.moveTo(px(0), py(yMax));
      ctx.lineTo(px(0), py(0));
      ctx.lineTo(px(xMax), py(0));
      ctx.stroke();

      ctx.fillStyle = "rgba(188,181,197,.7)";
      ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.fillText("0", px(0) - 12, py(0) + 15);
      ctx.fillText("x", px(xMax) - 2, py(0) + 15);
      ctx.fillText("y", px(0) - 15, py(yMax) + 5);

      ctx.strokeStyle = "#bd5d3a";
      ctx.lineWidth = 3;
      ctx.beginPath();
      for (let i = 0; i <= 100; i += 1) {
        const x = (i / 100) * xMax;
        const y = x * x;
        if (i === 0) ctx.moveTo(px(x), py(y));
        else ctx.lineTo(px(x), py(y));
      }
      ctx.stroke();

      const slope = 2 * pointX;
      const pointY = pointX * pointX;
      const tangentY = (x) => pointY + slope * (x - pointX);
      ctx.save();
      ctx.beginPath();
      ctx.rect(px(0), py(yMax), plotWidth, plotHeight);
      ctx.clip();
      ctx.strokeStyle = "#efb76c";
      ctx.lineWidth = 2;
      ctx.setLineDash([7, 6]);
      ctx.beginPath();
      ctx.moveTo(px(0), py(tangentY(0)));
      ctx.lineTo(px(xMax), py(tangentY(xMax)));
      ctx.stroke();
      ctx.restore();

      ctx.setLineDash([]);
      ctx.fillStyle = "#f8f3e9";
      ctx.beginPath();
      ctx.arc(px(pointX), py(pointY), 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#efb76c";
      ctx.lineWidth = 4;
      ctx.stroke();

      ctx.fillStyle = "#efb76c";
      ctx.font = "600 11px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.fillText(`slope ${slope.toFixed(1)}`, Math.min(px(pointX) + 12, width - 92), Math.max(py(pointY) - 12, 18));
      ctx.restore();
    };

    const update = (value, announce = true) => {
      pointX = Math.max(Number(slider.min), Math.min(Number(slider.max), Number(value)));
      slider.value = pointX.toFixed(1);
      const pointY = pointX * pointX;
      const slope = 2 * pointX;
      if (readoutX) readoutX.textContent = pointX.toFixed(1);
      if (readoutY) readoutY.textContent = pointY.toFixed(2);
      if (readoutSlope) readoutSlope.textContent = slope.toFixed(1);
      if (announce && lessonStatus) {
        lessonStatus.textContent = `At x = ${pointX.toFixed(1)}, the curve is rising ${slope.toFixed(1)} units for every step to the right.`;
      }
      draw();
    };

    const valueFromPointer = (event) => {
      const rect = canvas.getBoundingClientRect();
      const pad = Math.max(28, Math.min(42, rect.width * 0.07));
      const plotWidth = rect.width - pad * 1.45;
      const fraction = (event.clientX - rect.left - pad) / plotWidth;
      return Math.round(Math.max(0, Math.min(1, fraction)) * 41 + 4) / 10;
    };

    slider.addEventListener("input", () => update(slider.value));
    canvas.addEventListener("pointerdown", (event) => {
      dragging = true;
      canvas.setPointerCapture(event.pointerId);
      update(valueFromPointer(event));
    });
    canvas.addEventListener("pointermove", (event) => {
      if (dragging) update(valueFromPointer(event), false);
    });
    canvas.addEventListener("pointerup", (event) => {
      dragging = false;
      canvas.releasePointerCapture(event.pointerId);
      update(valueFromPointer(event));
    });
    canvas.addEventListener("pointercancel", () => { dragging = false; });

    if ("ResizeObserver" in window) new ResizeObserver(draw).observe(canvas);
    else window.addEventListener("resize", draw);
    update(pointX, false);
  }
})();
