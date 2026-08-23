"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "theme.js"), "utf8");

function browserTheme({ stored = null, systemDark = false } = {}) {
  const root = { dataset: {}, style: {} };
  const meta = {
    content: "#faf9f5",
    setAttribute(name, value) { if (name === "content") this.content = value; },
  };
  const documentEvents = [];
  const document = {
    documentElement: root,
    querySelector: (selector) => selector === 'meta[name="theme-color"]' ? meta : null,
    dispatchEvent: (event) => { documentEvents.push(event); },
  };
  const mediaListeners = [];
  const media = {
    matches: systemDark,
    addEventListener: (name, listener) => { if (name === "change") mediaListeners.push(listener); },
  };
  const storageValues = new Map(stored == null ? [] : [["muta-theme", stored]]);
  const storageListeners = [];
  const window = {
    document,
    localStorage: {
      getItem: (key) => storageValues.get(key) ?? null,
      setItem: (key, value) => storageValues.set(key, value),
    },
    matchMedia: () => media,
    addEventListener: (name, listener) => { if (name === "storage") storageListeners.push(listener); },
    CustomEvent: class CustomEvent {
      constructor(type, init) { this.type = type; this.detail = init.detail; }
    },
  };
  const context = vm.createContext({ window, document, CustomEvent: window.CustomEvent });
  vm.runInContext(source, context, { filename: "theme.js" });
  return { api: window.MutaTheme, documentEvents, media, mediaListeners, meta, root, storageListeners, storageValues };
}

test("resolves the saved theme before paint and updates browser chrome", () => {
  const dark = browserTheme({ stored: "dark", systemDark: false });
  assert.deepEqual({ ...dark.root.dataset }, { theme: "dark", themePreference: "dark" });
  assert.equal(dark.root.style.colorScheme, "dark");
  assert.equal(dark.meta.content, "#191815");
  assert.equal(dark.documentEvents.length, 0, "bootstrap should not announce a user change");

  const invalid = browserTheme({ stored: "sepia", systemDark: true });
  assert.deepEqual({ ...invalid.root.dataset }, { theme: "dark", themePreference: "system" });
});

test("persists explicit choices and synchronizes storage changes from another tab", () => {
  const state = browserTheme({ stored: "system", systemDark: false });
  state.api.applyPreference("dark", { persist: true });
  assert.equal(state.storageValues.get("muta-theme"), "dark");
  assert.equal(state.root.dataset.theme, "dark");
  assert.equal(state.documentEvents.at(-1).detail.preference, "dark");
  assert.equal(state.documentEvents.at(-1).detail.theme, "dark");

  state.storageListeners[0]({ key: "muta-theme", newValue: "light" });
  assert.equal(state.root.dataset.theme, "light");
  assert.equal(state.root.dataset.themePreference, "light");

  state.media.matches = true;
  state.storageListeners[0]({ key: null, newValue: null });
  assert.equal(state.root.dataset.theme, "dark");
  assert.equal(state.root.dataset.themePreference, "system");
});

test("System follows operating-system changes while explicit choices remain fixed", () => {
  const state = browserTheme({ stored: "system", systemDark: false });
  state.media.matches = true;
  state.mediaListeners[0]();
  assert.equal(state.root.dataset.theme, "dark");

  state.api.applyPreference("light", { persist: true });
  state.media.matches = false;
  state.mediaListeners[0]();
  assert.equal(state.root.dataset.theme, "light");
  state.media.matches = true;
  state.mediaListeners[0]();
  assert.equal(state.root.dataset.theme, "light");
});

test("landing and chat use the exact same preference implementation", () => {
  const landing = fs.readFileSync(path.join(__dirname, "..", "..", "landing", "theme.js"));
  assert.deepEqual(landing, Buffer.from(source));
});
