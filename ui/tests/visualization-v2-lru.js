"use strict";

(async () => {
  const status = document.getElementById("status");
  const output = document.getElementById("result");
  const host = document.getElementById("host");
  const fixture = await fetch("tests/fixtures/visualization-v2-specs.json?v=lru-3").then((response) => response.json());
  const specs = fixture.cases.slice(0, 6).map((item) => item.spec);
  window.MutaViz.renderAll(host, specs);
  await new Promise((resolve) => setTimeout(resolve, 250));
  const frames = [...host.querySelectorAll(".muta-visualization-frame")];
  const restores = [...host.querySelectorAll(".muta-visualization-restore")];
  const active = () => frames.filter((frame) => !frame.hidden && !frame.src.endsWith("about:blank"));
  const initialActive = active().length;
  const visibleRestores = restores.filter((button) => !button.hidden);
  let restored = false;
  if (visibleRestores[0]) {
    const index = restores.indexOf(visibleRestores[0]);
    visibleRestores[0].click();
    await new Promise((resolve) => setTimeout(resolve, 120));
    restored = !frames[index].hidden && active().length === 4;
  }
  const payload = {
    total: frames.length,
    initial_active: initialActive,
    initial_suspended: visibleRestores.length,
    restored_with_cap_preserved: restored,
    passed: frames.length === 6 && initialActive === 4 && visibleRestores.length === 2 && restored,
  };
  window.MutaViz.cleanup(host);
  output.textContent = JSON.stringify(payload);
  if (new URLSearchParams(location.search).get("report") === "1") {
    const response = await fetch("/__lru", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) payload.passed = false;
  }
  status.textContent = payload.passed ? "PASS" : "FAIL";
  document.documentElement.dataset.complete = "true";
  document.documentElement.dataset.passed = String(payload.passed);
})();
