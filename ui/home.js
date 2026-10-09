/* Home quick-starts. Each card is a shortcut to an existing control, never a second code path:
 * the composer, voice loop and Learn library keep their own state, policy and error handling. */
"use strict";

((global) => {
  const doc = global.document;
  if (!doc?.querySelector) return;

  function clickControl(selector) {
    const control = doc.querySelector(selector);
    if (!control || control.disabled) return false;
    control.click();
    return true;
  }

  const actions = {
    image: () => clickControl("#btn-image"),
    voice: () => clickControl("#btn-mic"),
    learn: () => clickControl("#unit-open"),
    // Learn loads its courses asynchronously and then selects its starting tab, so the tab is
    // passed in rather than clicked afterwards (a click would be overridden by "library").
    practice: () => (global.MutaLearning?.open
      ? (global.MutaLearning.open("practice"), true)
      : clickControl("#unit-open")),
  };

  // A quick-start mirrors its target's availability so a disabled microphone or a tutor that is
  // still loading never looks clickable on the home screen.
  function syncAvailability() {
    for (const card of doc.querySelectorAll("[data-home-action]")) {
      const target = { image: "#btn-image", voice: "#btn-mic" }[card.dataset.homeAction];
      card.disabled = Boolean(target && doc.querySelector(target)?.disabled);
    }
  }

  doc.querySelector(".home-actions")?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-home-action]");
    if (card && !card.disabled) actions[card.dataset.homeAction]?.();
  });

  const observer = new MutationObserver(syncAvailability);
  for (const selector of ["#btn-image", "#btn-mic"]) {
    const node = doc.querySelector(selector);
    if (node) observer.observe(node, { attributes: true, attributeFilter: ["disabled"] });
  }
  syncAvailability();
})(globalThis);
