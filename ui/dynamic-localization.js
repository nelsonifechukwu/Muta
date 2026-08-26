/* Coordinate locale-sensitive surfaces that are rendered from live application state rather
 * than authored data-i18n nodes. Keeping the coordinator DOM-free makes the browser behavior
 * executable in the Node release gate. */
"use strict";

((global) => {
  const SURFACES = Object.freeze(["resources", "host", "power", "model", "status"]);

  function create(renderers = {}) {
    return function rerenderDynamicLocalization() {
      for (const surface of SURFACES) {
        if (typeof renderers[surface] === "function") renderers[surface]();
      }
    };
  }

  const api = Object.freeze({ SURFACES, create });
  global.MutaDynamicLocalization = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
