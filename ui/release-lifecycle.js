/* Pure release-lifecycle decisions shared by the browser client and Node regressions. */
"use strict";

((global) => {
  function hostUserEndpoint(userId, action) {
    const base = `/v1/share/host/users/${encodeURIComponent(userId)}`;
    return action === "remove" ? base : `${base}/${action}`;
  }

  function viewportMetrics({ visualViewport = null, innerHeight, innerWidth }) {
    const height = Number(visualViewport?.height || innerHeight || 0);
    const width = Number(visualViewport?.width || innerWidth || 0);
    const top = Number(visualViewport?.offsetTop || 0);
    const left = Number(visualViewport?.offsetLeft || 0);
    return {
      height,
      width,
      top,
      left,
      bottomGap: Math.max(0, Number(innerHeight || height) - height - top),
      compact: height > 0 && height < 240,
      composerRegionMax: Math.max(40, Math.min(112, height * 0.14)),
    };
  }

  function isNearBottom({ scrollHeight, scrollTop, clientHeight }, threshold = 96) {
    return Number(scrollHeight) - Number(scrollTop) - Number(clientHeight) <= threshold;
  }

  function terminalFailure(event, content) {
    const failed = Boolean(event?.error || event?.failed);
    const partial = Boolean(String(content || "").trim());
    return { failed, partial, recoverable: failed && partial };
  }

  function stopResponse(status, payload = {}) {
    if (status === 404 || (status >= 200 && status < 300 && payload.stopping !== true)) {
      return "already-terminal";
    }
    if (status >= 200 && status < 300 && payload.stopping === true) return "accepted";
    return "failed";
  }

  const api = Object.freeze({
    hostUserEndpoint,
    viewportMetrics,
    isNearBottom,
    terminalFailure,
    stopResponse,
  });
  global.MutaReleaseLifecycle = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
