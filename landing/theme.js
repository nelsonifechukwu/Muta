/* Shared local appearance preference. This script is deliberately blocking and tiny so the
 * resolved theme exists before CSS is requested; dark installations never flash a light frame. */
"use strict";

((global) => {
  const STORAGE_KEY = "muta-theme";
  const VALID_PREFERENCES = new Set(["system", "light", "dark"]);
  const DARK_QUERY = "(prefers-color-scheme: dark)";
  const THEME_COLORS = Object.freeze({ light: "#faf9f5", dark: "#191815" });
  let started = false;

  function normalizePreference(value) {
    return VALID_PREFERENCES.has(value) ? value : "system";
  }

  function safeStoredPreference() {
    try {
      return normalizePreference(global.localStorage?.getItem(STORAGE_KEY));
    } catch {
      return "system";
    }
  }

  function systemIsDark() {
    return Boolean(global.matchMedia?.(DARK_QUERY).matches);
  }

  function resolveTheme(preference, darkSystem = systemIsDark()) {
    const normalized = normalizePreference(preference);
    return normalized === "system" ? (darkSystem ? "dark" : "light") : normalized;
  }

  function applyPreference(preference, { persist = false, notify = true } = {}) {
    const normalized = normalizePreference(preference);
    const effective = resolveTheme(normalized);
    const root = global.document?.documentElement;
    const changed = root?.dataset.theme !== effective
      || root?.dataset.themePreference !== normalized;
    if (root) {
      root.dataset.theme = effective;
      root.dataset.themePreference = normalized;
      root.style.colorScheme = effective;
      const themeColor = global.document.querySelector('meta[name="theme-color"]');
      if (themeColor) themeColor.setAttribute("content", THEME_COLORS[effective]);
    }
    if (persist) {
      try {
        global.localStorage?.setItem(STORAGE_KEY, normalized);
      } catch {
        /* The active page can still change theme when storage is unavailable. */
      }
    }
    if (changed && notify && global.document && typeof global.CustomEvent === "function") {
      global.document.dispatchEvent(new global.CustomEvent("muta:themechange", {
        detail: { preference: normalized, theme: effective },
      }));
    }
    return Object.freeze({ preference: normalized, theme: effective });
  }

  function start() {
    if (started || !global.document) return;
    started = true;
    applyPreference(safeStoredPreference(), { notify: false });
    const media = global.matchMedia?.(DARK_QUERY);
    const onSystemChange = () => {
      if (normalizePreference(global.document.documentElement.dataset.themePreference) === "system") {
        applyPreference("system");
      }
    };
    if (typeof media?.addEventListener === "function") {
      media.addEventListener("change", onSystemChange);
    } else {
      media?.addListener?.(onSystemChange);
    }
    global.addEventListener?.("storage", (event) => {
      if (event.key === STORAGE_KEY || event.key === null) applyPreference(event.newValue);
    });
  }

  const api = Object.freeze({
    STORAGE_KEY,
    THEME_COLORS,
    applyPreference,
    normalizePreference,
    resolveTheme,
    safeStoredPreference,
    start,
    get preference() {
      return normalizePreference(global.document?.documentElement?.dataset.themePreference);
    },
    get theme() {
      return resolveTheme(this.preference);
    },
  });
  global.MutaTheme = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  start();
})(typeof window !== "undefined" ? window : globalThis);
