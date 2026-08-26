"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const dynamicLocalization = require("../dynamic-localization.js");

test("real Igbo to English locale switching rerenders an existing resource empty node", () => {
  const resourceEmpty = { textContent: "" };
  const document = {
    documentElement: { lang: "", dir: "" },
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: () => ({ appendChild() {}, dataset: {}, setAttribute() {} }),
    dispatchEvent() {},
  };
  globalThis.window = globalThis;
  globalThis.document = document;
  globalThis.localStorage = { getItem: () => null, setItem() {} };
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { languages: ["en"] },
  });
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, options) { this.type = type; this.detail = options?.detail; }
  };

  require("../release-english.js");
  require("../locale-manifest.js");
  const i18n = require("../i18n.js");
  require("../locale-generated.js");

  const rerender = dynamicLocalization.create({
    resources() { resourceEmpty.textContent = i18n.t("resources.empty"); },
  });
  i18n.subscribe(rerender);

  assert.equal(i18n.setLocale("ig", { persist: false, doc: document }), true);
  assert.equal(resourceEmpty.textContent, "Enweghị akụrụngwa mmụta ugbu a.");
  assert.equal(document.documentElement.lang, "ig");

  assert.equal(i18n.setLocale("en", { persist: false, doc: document }), true);
  assert.equal(resourceEmpty.textContent, "No learning resources yet.");
  assert.equal(document.documentElement.lang, "en");
});

test("the runtime contract enumerates every required dynamic surface", () => {
  assert.deepEqual(
    [...dynamicLocalization.SURFACES],
    ["resources", "host", "power", "model", "status"],
  );
});
