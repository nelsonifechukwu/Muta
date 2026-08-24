"use strict";

(() => {
  if (!window.MutaAccess?.localOperator) return;

  const modal = document.querySelector("#product-consent-modal");
  const settings = document.querySelector("#product-analytics-settings");
  const toggle = document.querySelector("#setting-product-analytics");
  const state = document.querySelector("#product-analytics-state");
  const allow = document.querySelector("#product-consent-allow");
  const decline = document.querySelector("#product-consent-decline");
  const error = document.querySelector("#product-consent-error");
  const app = document.querySelector("#app");
  let lastFocus = null;
  let current = null;

  function statusText(status) {
    if (status.deletion_pending) return "Deletion is queued and will complete when this laptop is online.";
    if (status.consent === "granted") {
      return status.last_synced_at
        ? `Sharing is on · last synced ${new Date(status.last_synced_at).toLocaleString()}`
        : "Sharing is on · waiting for the next internet connection.";
    }
    if (status.consent === "declined") return "Sharing is off. Muta stays fully offline-capable.";
    return "No choice has been saved yet.";
  }

  function render(status) {
    current = status;
    settings.hidden = !status.configured;
    if (!status.configured) return;
    toggle.disabled = false;
    toggle.checked = status.consent === "granted";
    state.textContent = statusText(status);
    if (status.prompt_required) openModal();
  }

  function openModal() {
    if (!modal.hidden) return;
    lastFocus = document.activeElement;
    modal.hidden = false;
    app?.setAttribute("inert", "");
    allow.focus();
  }

  function closeModal() {
    modal.hidden = true;
    if (app?.getAttribute("aria-busy") === "false") app.removeAttribute("inert");
    if (lastFocus instanceof HTMLElement) lastFocus.focus();
  }

  async function readStatus() {
    try {
      const response = await fetch("/v1/product-analytics", { cache: "no-store" });
      if (!response.ok) return;
      render(await response.json());
    } catch {
      // A missing/offline analytics service cannot affect the local tutor.
    }
  }

  async function save(allowed) {
    allow.disabled = true;
    decline.disabled = true;
    toggle.disabled = true;
    error.textContent = "";
    try {
      const response = await fetch("/v1/product-analytics", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ allowed }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
      closeModal();
    } catch {
      if (!modal.hidden) error.textContent = "Muta could not save that choice. Please try again.";
      else state.textContent = "Muta could not save that privacy setting. Please try again.";
      toggle.checked = current?.consent === "granted";
    } finally {
      allow.disabled = false;
      decline.disabled = false;
      toggle.disabled = false;
    }
  }

  allow.addEventListener("click", () => void save(true));
  decline.addEventListener("click", () => void save(false));
  toggle.addEventListener("change", () => void save(toggle.checked));
  modal.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const focusable = [decline, allow].filter((button) => !button.disabled);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  });

  void readStatus();
})();
