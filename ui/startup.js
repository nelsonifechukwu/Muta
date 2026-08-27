/* Truthful startup readiness for browser exports and the Tauri desktop shell. */
"use strict";

((global) => {
  const START = Object.freeze({
    percent: 5,
    stage: "startup.opening",
    ready: false,
    failed: false,
    retryable: false,
  });

  function normalizeSnapshot(value = {}, previous = START) {
    const ready = value.ready === true;
    const requested = Number.isFinite(Number(value.percent)) ? Number(value.percent) : 0;
    return {
      percent: ready ? 100 : Math.max(previous.percent || 0, Math.min(99, requested)),
      stage: String(value.stage || previous.stage || START.stage),
      ready,
      failed: !ready && value.failed === true,
      retryable: !ready && value.retryable === true,
    };
  }

  function browserSnapshot(body, previous = START) {
    const checks = body?.checks || {};
    let next;
    if (body?.ready === true) {
      next = { percent: 100, stage: "startup.ready", ready: true };
    } else if (checks.inference === true) {
      next = { percent: 92, stage: "startup.finishing" };
    } else if (checks.db === true) {
      next = { percent: 82, stage: "startup.loadingTutor" };
    } else if (checks.gateway === true || body) {
      next = { percent: 72, stage: "startup.openingData" };
    } else {
      next = { percent: 64, stage: "startup.connecting" };
    }
    return normalizeSnapshot(next, previous);
  }

  function failureSnapshot(previous = START, failures = 1) {
    return normalizeSnapshot(failures >= 3
      ? { percent: previous.percent, stage: "startup.connecting", failed: true, retryable: true }
      : { percent: 64, stage: "startup.connecting" }, previous);
  }

  async function resolveStartupSnapshot({
    invoke,
    fetchReady,
    previous = START,
    onInvokeRejected,
  } = {}) {
    let tauriError = null;
    if (typeof invoke === "function") {
      try {
        return {
          snapshot: normalizeSnapshot(await invoke("startup_snapshot"), previous),
          transport: "tauri",
          tauriError,
        };
      } catch (error) {
        // Navigation from the bundled splash to the localhost app can retain
        // __TAURI__ while command access is unavailable. HTTP is authoritative
        // for that origin, so command rejection is not a startup failure.
        tauriError = error instanceof Error ? error : new Error(String(error));
        onInvokeRejected?.(tauriError);
      }
    }

    if (typeof fetchReady !== "function") {
      throw tauriError || new Error("No startup readiness transport is available");
    }
    const response = await fetchReady();
    if (!response?.ok) throw new Error(`HTTP ${response?.status || "unavailable"}`);
    return {
      snapshot: browserSnapshot(await response.json(), previous),
      transport: "http",
      tauriError,
    };
  }

  const api = {
    START,
    normalizeSnapshot,
    browserSnapshot,
    failureSnapshot,
    resolveStartupSnapshot,
  };
  global.MutaStartup = Object.freeze(api);
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!global.document?.querySelector) return;

  const shell = document.querySelector("#startup-readiness");
  const progress = document.querySelector("#startup-progress");
  const percent = document.querySelector("#startup-percent");
  const stage = document.querySelector("#startup-stage");
  const retry = document.querySelector("#startup-retry");
  const welcome = document.querySelector("#startup-welcome");
  const app = document.querySelector("#app");
  const tauriInvoke = global.__TAURI__?.core?.invoke;
  let tauriFastPath = typeof tauriInvoke === "function" ? tauriInvoke : null;
  let current = START;
  let transportFailures = 0;
  let timer = null;
  let requestController = null;
  let sampleGeneration = 0;
  let disposed = false;

  const text = (key, variables) => global.MutaI18n?.t?.(key, variables) || key;

  function applySnapshot(candidate) {
    current = normalizeSnapshot(candidate, current);
    document.documentElement.dataset.mutaReady = String(current.ready);
    shell.hidden = current.ready;
    welcome.hidden = current.ready;
    shell.setAttribute("aria-busy", String(!current.ready && !current.failed));
    progress.setAttribute("aria-valuenow", String(current.percent));
    progress.setAttribute(
      "aria-valuetext",
      text("startup.progress", {
        stage: text(current.stage),
        percent: current.percent,
      }),
    );
    progress.style.setProperty("--startup-progress", `${current.percent * 3.6}deg`);
    percent.textContent = `${current.percent}%`;
    stage.textContent = text(current.stage);
    retry.hidden = !current.retryable;
    if (!current.ready) app?.setAttribute("aria-busy", "true");
    else if (!app?.hasAttribute("inert")) app?.setAttribute("aria-busy", "false");
    document.dispatchEvent(new CustomEvent("muta:startupchange", {
      detail: { ...current },
    }));
  }

  async function fetchReady() {
    requestController?.abort();
    requestController = typeof AbortController === "function" ? new AbortController() : null;
    const controller = requestController;
    const timeout = global.setTimeout(() => controller?.abort(), 5000);
    try {
      return await fetch("/v1/ready", {
        cache: "no-store",
        signal: controller?.signal,
      });
    } finally {
      global.clearTimeout(timeout);
      if (requestController === controller) requestController = null;
    }
  }

  async function readSnapshot() {
    const result = await resolveStartupSnapshot({
      invoke: tauriFastPath,
      fetchReady,
      previous: current,
      onInvokeRejected: () => { tauriFastPath = null; },
    });
    return result.snapshot;
  }

  async function sample() {
    clearTimeout(timer);
    const generation = ++sampleGeneration;
    try {
      const snapshot = await readSnapshot();
      if (disposed || generation !== sampleGeneration) return;
      transportFailures = 0;
      applySnapshot(snapshot);
    } catch {
      if (disposed || generation !== sampleGeneration) return;
      transportFailures += 1;
      applySnapshot(failureSnapshot(current, transportFailures));
    }
    if (!disposed && !current.ready) {
      timer = global.setTimeout(sample, tauriFastPath ? 450 : 1200);
    }
  }

  retry.addEventListener("click", async () => {
    retry.disabled = true;
    transportFailures = 0;
    applySnapshot({
      percent: current.percent,
      stage: "startup.retrying",
      failed: false,
      retryable: false,
    });
    try {
      if (tauriFastPath) {
        try {
          await tauriFastPath("retry_startup");
        } catch {
          tauriFastPath = null;
        }
      }
    } finally {
      retry.disabled = false;
      void sample();
    }
  });

  document.addEventListener("muta:localechange", () => applySnapshot(current));
  global.addEventListener?.("pagehide", () => {
    disposed = true;
    sampleGeneration += 1;
    clearTimeout(timer);
    requestController?.abort();
    requestController = null;
  }, { once: true });
  applySnapshot(START);
  void sample();
})(globalThis);
