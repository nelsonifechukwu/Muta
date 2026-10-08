"use strict";

((global) => {
  function canApplyServerStyle({ currentVersion, versionAtStart, persistedVersionAtStart }) {
    return currentVersion === versionAtStart && versionAtStart === persistedVersionAtStart;
  }

  function assignedConversationStyle(requestedMode, currentBlankMode) {
    const mode = currentBlankMode || requestedMode;
    return { mode, needsConversationWrite: mode !== requestedMode };
  }

  function nextRepairVersion(currentVersion) {
    return (Number.isInteger(currentVersion) ? currentVersion : 0) + 1;
  }

  const api = { assignedConversationStyle, canApplyServerStyle, nextRepairVersion };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.MutaTeachingStylePolicy = api;
})(typeof window === "undefined" ? globalThis : window);
