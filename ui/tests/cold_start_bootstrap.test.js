"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const appSource = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
const bootSource = appSource.slice(
  appSource.indexOf("async function bootChat()"),
  appSource.indexOf("\nvoid bootChat();"),
);

function bootstrapContext({ selected = null, loadResult = true, stallIndependent = false } = {}) {
  const events = [];
  const never = new Promise(() => {});
  const context = vm.createContext({
    localOperatorPage: false,
    sendBtn: { disabled: false },
    startupRoutingReady: false,
    ensureAuth: async () => {
      events.push("auth");
      return true;
    },
    refreshModelCatalog: () => {
      events.push("models:start");
      return stallIndependent ? never : Promise.resolve(true);
    },
    refreshSidebar: () => {
      events.push("sidebar");
      return stallIndependent ? never : Promise.resolve(true);
    },
    loadSettings: () => {
      events.push("settings:start");
      return stallIndependent ? never : Promise.resolve(true);
    },
    loadResources: () => {
      events.push("resources:start");
      return stallIndependent ? never : Promise.resolve(true);
    },
    recoverGenerations: async () => {
      events.push("generations");
      return true;
    },
    conversationFromLocation: () => selected,
    pendingRequestFromLocation: () => null,
    pendingStartsFor: () => [],
    loadConversation: async () => {
      events.push("conversation");
      return loadResult;
    },
    newChat: () => events.push("new-chat"),
    setConversationLocation: () => events.push("route"),
    restoreMessageQueue: () => events.push("queue"),
    syncComposerState: () => events.push("composer"),
    refreshPowerStatus: () => {},
    revalidateShareIdentity: () => {},
    sessionStorage: { getItem: () => null },
    window: {
      setInterval: () => 1,
      setTimeout,
    },
    document: { hidden: false },
  });
  context.settleStartupRouting = () => {
    context.startupRoutingReady = true;
    events.push("routing:ready");
  };
  return { context, events };
}

test("saved-chat bootstrap does not await model, settings, or resource discovery", async () => {
  const { context, events } = bootstrapContext({ stallIndependent: true });

  vm.runInContext(`${bootSource}\nglobalThis.bootPromise = bootChat();`, context);
  await context.bootPromise;

  assert.deepEqual(events, [
    "auth",
    "models:start",
    "composer",
    "queue",
    "sidebar",
    "settings:start",
    "resources:start",
    "generations",
    "routing:ready",
  ]);
  assert.equal(context.startupRoutingReady, true);
});

test("a transient selected-chat failure keeps initial routing locked for retry", async () => {
  const { context, events } = bootstrapContext({
    selected: "saved-chat",
    loadResult: null,
  });

  vm.runInContext(`${bootSource}\nglobalThis.bootPromise = bootChat();`, context);
  await context.bootPromise;

  assert.ok(events.includes("sidebar"));
  assert.ok(events.includes("conversation"));
  assert.ok(!events.includes("routing:ready"));
  assert.equal(context.startupRoutingReady, false);
});
