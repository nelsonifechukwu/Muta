"use strict";

((global) => {
  function busy({ activeJobs = 0, startingJobs = 0 } = {}) {
    return activeJobs > 0 || startingJobs > 0;
  }

  function sendAction({
    allowParallelChats = true,
    activeJobs = 0,
    startingJobs = 0,
    hasConversation = false,
  } = {}) {
    if (allowParallelChats || !busy({ activeJobs, startingJobs })) return "dispatch";
    return hasConversation ? "queue" : "restore";
  }

  function canDrain({ allowParallelChats = true, activeJobs = 0, startingJobs = 0 } = {}) {
    return allowParallelChats || !busy({ activeJobs, startingJobs });
  }

  function queuedConversationIds(items = []) {
    return [...new Set(items.map((item) => item?.cid).filter(Boolean))];
  }

  const api = Object.freeze({ busy, sendAction, canDrain, queuedConversationIds });
  global.MutaParallelPolicy = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
