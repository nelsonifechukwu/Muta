(() => {
  "use strict";

  const themeToggle = document.getElementById("theme-toggle");
  window.MutaTheme?.bindToggle(themeToggle);

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

  const learningCarousel = document.querySelector("[data-learning-carousel]");
  const carouselInteraction = document.querySelector("[data-carousel-interaction]");
  const carouselTrack = document.querySelector("[data-carousel-track]");
  const learningSlides = Array.from(document.querySelectorAll("[data-learning-slide]"));
  const carouselTabs = Array.from(document.querySelectorAll("[data-carousel-tab]"));
  const carouselProgress = document.querySelector("[data-carousel-progress]");
  const carouselCount = document.querySelector("[data-carousel-count]");
  const carouselToggle = document.querySelector("[data-carousel-toggle]");
  const carouselToggleIcon = document.querySelector("[data-carousel-toggle-icon]");
  const carouselToggleLabel = document.querySelector("[data-carousel-toggle-label]");
  const carouselPrev = document.querySelector("[data-carousel-prev]");
  const carouselNext = document.querySelector("[data-carousel-next]");

  if (learningCarousel && carouselTrack && learningSlides.length && carouselTabs.length) {
    const AUTO_ADVANCE_MS = 9000;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const hoverCapable = window.matchMedia("(hover: hover)");
    let activeSlide = 0;
    let elapsed = 0;
    let lastFrame = performance.now();
    let userPaused = false;
    let pointerActive = false;
    let keyboardMode = false;
    let carouselVisible = !("IntersectionObserver" in window);
    let animationFrame = null;

    const isUsingCarousel = (element) => (
      carouselInteraction?.contains(element)
      || carouselToggle?.contains(element)
      || carouselPrev?.contains(element)
      || carouselNext?.contains(element)
    );

    const hasKeyboardFocus = () => keyboardMode && isUsingCarousel(document.activeElement);

    const temporarilyPaused = () => (
      pointerActive
      || (hoverCapable.matches && Boolean(carouselInteraction?.matches(":hover")))
      || hasKeyboardFocus()
    );

    const paused = () => (
      userPaused
      || reducedMotion.matches
      || temporarilyPaused()
      || !carouselVisible
      || document.hidden
    );

    const updateProgress = () => {
      if (carouselProgress) carouselProgress.style.transform = `scaleX(${Math.min(elapsed / AUTO_ADVANCE_MS, 1)})`;
    };

    const updateToggle = () => {
      if (!carouselToggle || !carouselToggleLabel || !carouselToggleIcon) return;
      carouselToggle.hidden = reducedMotion.matches;
      carouselToggleLabel.textContent = userPaused ? "Play" : "Pause";
      carouselToggleIcon.textContent = userPaused ? "▶" : "Ⅱ";
      carouselToggle.setAttribute("aria-label", userPaused ? "Play learning examples" : "Pause learning examples");
    };

    const setSlide = (nextIndex, { focusTab = false, resetClock = true } = {}) => {
      activeSlide = (nextIndex + learningSlides.length) % learningSlides.length;
      carouselTrack.style.transform = `translateX(-${activeSlide * 100}%)`;

      learningSlides.forEach((slide, index) => {
        const selected = index === activeSlide;
        slide.setAttribute("aria-hidden", String(!selected));
        slide.toggleAttribute("inert", !selected);
      });

      carouselTabs.forEach((tab, index) => {
        const selected = index === activeSlide;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
      });

      const currentTab = carouselTabs[activeSlide];
      const centredTabOffset = currentTab.offsetLeft - ((carouselTabs[0].parentElement.clientWidth - currentTab.offsetWidth) / 2);
      carouselTabs[0].parentElement.scrollTo({
        left: Math.max(centredTabOffset, 0),
        behavior: reducedMotion.matches ? "auto" : "smooth",
      });
      if (focusTab) currentTab.focus();
      if (carouselCount) carouselCount.textContent = `${String(activeSlide + 1).padStart(2, "0")} / ${String(learningSlides.length).padStart(2, "0")}`;
      if (resetClock) {
        elapsed = 0;
        updateProgress();
      }
    };

    const stopAnimation = () => {
      if (animationFrame === null) return;
      window.cancelAnimationFrame(animationFrame);
      animationFrame = null;
    };

    const advance = (now) => {
      animationFrame = null;
      if (paused()) return;
      const delta = Math.min(now - lastFrame, 100);
      lastFrame = now;
      elapsed += delta;
      if (elapsed >= AUTO_ADVANCE_MS) setSlide(activeSlide + 1);
      updateProgress();
      animationFrame = window.requestAnimationFrame(advance);
    };

    const syncAnimation = () => {
      const isPaused = paused();
      learningCarousel.classList.toggle("is-auto-paused", isPaused);
      if (isPaused) {
        stopAnimation();
        return;
      }
      if (animationFrame === null) {
        lastFrame = performance.now();
        animationFrame = window.requestAnimationFrame(advance);
      }
    };

    carouselTabs.forEach((tab, index) => {
      tab.addEventListener("click", () => setSlide(index));
      tab.addEventListener("keydown", (event) => {
        let nextIndex = null;
        if (event.key === "ArrowRight") nextIndex = index + 1;
        if (event.key === "ArrowLeft") nextIndex = index - 1;
        if (event.key === "Home") nextIndex = 0;
        if (event.key === "End") nextIndex = learningSlides.length - 1;
        if (nextIndex === null) return;
        event.preventDefault();
        setSlide(nextIndex, { focusTab: true });
      });
    });

    carouselPrev?.addEventListener("click", () => setSlide(activeSlide - 1));
    carouselNext?.addEventListener("click", () => setSlide(activeSlide + 1));
    carouselToggle?.addEventListener("click", () => {
      userPaused = !userPaused;
      updateToggle();
      syncAnimation();
    });

    document.addEventListener("keydown", () => {
      keyboardMode = true;
      syncAnimation();
    }, true);
    document.addEventListener("pointerdown", () => { keyboardMode = false; }, true);
    learningCarousel.addEventListener("pointerdown", () => {
      pointerActive = true;
      syncAnimation();
    });
    carouselInteraction?.addEventListener("pointerenter", syncAnimation);
    carouselInteraction?.addEventListener("pointerleave", syncAnimation);
    learningCarousel.addEventListener("focusin", syncAnimation);
    learningCarousel.addEventListener("focusout", syncAnimation);
    window.addEventListener("pointerup", () => {
      pointerActive = false;
      syncAnimation();
    });
    window.addEventListener("pointercancel", () => {
      pointerActive = false;
      syncAnimation();
    });
    window.addEventListener("blur", () => {
      pointerActive = false;
      syncAnimation();
    });
    document.addEventListener("visibilitychange", syncAnimation);

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(([entry]) => {
        carouselVisible = entry.isIntersecting;
        syncAnimation();
      }, { threshold: 0.18 }).observe(learningCarousel);
    }

    const onMotionPreference = () => {
      if (reducedMotion.matches) elapsed = 0;
      updateToggle();
      updateProgress();
      syncAnimation();
    };
    reducedMotion.addEventListener?.("change", onMotionPreference);

    setSlide(0);
    updateToggle();
    syncAnimation();
  }

  const perspectiveCopy = {
    organiser: {
      label: "The organiser",
      passage: "“By sunrise, the square answered our call; the crowd was ready, and change felt close enough to touch.”",
      clues: ["answered our call", "ready", "change"],
      feedback: "The organiser uses collective, hopeful language to make the gathering feel purposeful.",
    },
    witness: {
      label: "A witness",
      passage: "“By sunrise, the square was humming. I watched from my doorway as neighbours arrived, some smiling, some looking over their shoulders.”",
      clues: ["I watched", "some smiling", "looking over"],
      feedback: "The witness mixes observation with personal position, giving us detail but only from one doorway.",
    },
    reporter: {
      label: "The reporter",
      passage: "“Residents gathered in the central square shortly after sunrise, following notices circulated the previous evening.”",
      clues: ["residents", "shortly after", "following notices"],
      feedback: "The reporter favours verifiable time, place, and cause. The tone sounds neutral, but selection still shapes the account.",
    },
  };

  const perspectiveButtons = Array.from(document.querySelectorAll("[data-perspective]"));
  const voiceLabel = document.getElementById("voice-label");
  const voicePassage = document.getElementById("voice-passage");
  const languageClues = document.getElementById("language-clues");
  const humanitiesStatus = document.getElementById("humanities-status");

  perspectiveButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const copy = perspectiveCopy[button.dataset.perspective];
      if (!copy || !voiceLabel || !voicePassage || !languageClues || !humanitiesStatus) return;
      perspectiveButtons.forEach((choice) => choice.setAttribute("aria-pressed", String(choice === button)));
      voiceLabel.textContent = copy.label;
      voicePassage.textContent = copy.passage;
      humanitiesStatus.textContent = copy.feedback;
      languageClues.replaceChildren(...copy.clues.map((clue) => {
        const chip = document.createElement("span");
        chip.textContent = clue;
        return chip;
      }));
    });
  });

  const priceSlider = document.getElementById("price-slider");
  const unitsSlider = document.getElementById("units-slider");
  const priceOutput = document.getElementById("price-output");
  const unitsOutput = document.getElementById("units-output");
  const revenueValue = document.getElementById("revenue-value");
  const costValue = document.getElementById("cost-value");
  const profitValue = document.getElementById("profit-value");
  const revenueBar = document.getElementById("revenue-bar");
  const costBar = document.getElementById("cost-bar");
  const businessStatus = document.getElementById("business-status");

  if (priceSlider && unitsSlider) {
    const FIXED_COST = 6000;
    const UNIT_COST = 500;
    const naira = (value) => `₦${Math.abs(Math.round(value)).toLocaleString("en-NG")}`;

    const updateBusiness = () => {
      const price = Number(priceSlider.value);
      const units = Number(unitsSlider.value);
      const revenue = price * units;
      const totalCost = FIXED_COST + UNIT_COST * units;
      const profit = revenue - totalCost;
      const scale = Math.max(revenue, totalCost, 1) * 1.05;

      if (priceOutput) priceOutput.textContent = naira(price);
      if (unitsOutput) unitsOutput.textContent = String(units);
      if (revenueValue) revenueValue.textContent = naira(revenue);
      if (costValue) costValue.textContent = naira(totalCost);
      if (profitValue) {
        profitValue.textContent = `${profit >= 0 ? "+" : "−"}${naira(profit)}`;
        profitValue.dataset.state = profit >= 0 ? "profit" : "loss";
      }
      if (revenueBar) revenueBar.style.width = `${(revenue / scale) * 100}%`;
      if (costBar) costBar.style.width = `${(totalCost / scale) * 100}%`;
      priceSlider.setAttribute("aria-valuetext", naira(price));
      unitsSlider.setAttribute("aria-valuetext", `${units} notebooks`);
      if (businessStatus) {
        const result = profit >= 0 ? `profit is ${naira(profit)}` : `the loss is ${naira(profit)}`;
        businessStatus.textContent = `Revenue is ${naira(revenue)}. After ${naira(FIXED_COST)} fixed costs and ${naira(UNIT_COST)} per notebook, ${result}.`;
      }
    };

    priceSlider.addEventListener("input", updateBusiness);
    unitsSlider.addEventListener("input", updateBusiness);
    updateBusiness();
  }

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
