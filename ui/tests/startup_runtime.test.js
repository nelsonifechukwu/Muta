"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function element() {
  const listeners = new Map();
  const attributes = new Map();
  return {
    hidden: false,
    disabled: false,
    textContent: "",
    style: { setProperty() {} },
    addEventListener(type, callback) { listeners.set(type, callback); },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    getAttribute(name) { return attributes.get(name) ?? null; },
    removeAttribute(name) { attributes.delete(name); },
    hasAttribute(name) { return attributes.has(name); },
    listener(type) { return listeners.get(type); },
  };
}

function startupRuntime({ invoke, fetchReady }) {
  const selectors = new Map([
    ["#startup-readiness", element()],
    ["#startup-progress", element()],
    ["#startup-percent", element()],
    ["#startup-stage", element()],
    ["#startup-retry", element()],
    ["#startup-welcome", element()],
    ["#app", element()],
  ]);
  const polls = [];
  const documentListeners = new Map();
  const document = {
    documentElement: { dataset: {} },
    querySelector(selector) { return selectors.get(selector); },
    addEventListener(type, callback) { documentListeners.set(type, callback); },
    dispatchEvent() {},
  };
  const context = {
    document,
    __TAURI__: { core: { invoke } },
    MutaI18n: { t: (key) => key },
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init.detail; } },
    AbortController,
    fetch: fetchReady,
    setTimeout(callback, delay) {
      if (delay === 1200 || delay === 450) polls.push(callback);
      return callback;
    },
    clearTimeout(callback) {
      const index = polls.indexOf(callback);
      if (index >= 0) polls.splice(index, 1);
    },
    addEventListener() {},
  };
  context.globalThis = context;
  vm.runInNewContext(fs.readFileSync(require.resolve("../startup.js"), "utf8"), context);
  return { context, selectors, polls };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

test("packaged local-origin transition falls back from rejected Tauri invoke to HTTP ready", async () => {
  const runtime = startupRuntime({
    invoke: async () => { throw new Error("command unavailable after navigation"); },
    fetchReady: async () => ({
      ok: true,
      json: async () => ({ ready: true, checks: { gateway: true, db: true, inference: true } }),
    }),
  });
  await settle();

  assert.equal(runtime.context.document.documentElement.dataset.mutaReady, "true");
  assert.equal(runtime.selectors.get("#startup-readiness").hidden, true);
  assert.equal(runtime.selectors.get("#startup-percent").textContent, "100%");
  assert.equal(runtime.selectors.get("#app").getAttribute("aria-busy"), "false");
});

test("a displayed transport failure recovers when Retry sees a healthy backend", async () => {
  let healthy = false;
  let invokes = 0;
  const runtime = startupRuntime({
    invoke: async () => {
      invokes += 1;
      throw new Error("command unavailable after navigation");
    },
    fetchReady: async () => {
      if (!healthy) throw new Error("gateway offline");
      return {
        ok: true,
        json: async () => ({ ready: true, checks: { gateway: true, db: true, inference: true } }),
      };
    },
  });
  await settle();
  for (let attempt = 1; attempt < 3; attempt += 1) {
    const poll = runtime.polls.shift();
    assert.equal(typeof poll, "function");
    await poll();
  }

  const retry = runtime.selectors.get("#startup-retry");
  assert.equal(retry.hidden, false);
  assert.equal(invokes, 1, "a rejected command is disabled for the localhost origin");
  assert.equal(runtime.selectors.get("#startup-stage").textContent, "startup.connecting");
  healthy = true;
  await retry.listener("click")();
  await settle();

  assert.equal(runtime.context.document.documentElement.dataset.mutaReady, "true");
  assert.equal(runtime.selectors.get("#startup-readiness").hidden, true);
  assert.equal(retry.disabled, false);
});
