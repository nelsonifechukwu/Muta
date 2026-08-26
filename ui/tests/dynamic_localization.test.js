"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const dynamicLocalization = require("../dynamic-localization.js");

test("real Igbo to English switching rerenders resource and mapped Host warning state", () => {
  const resourceEmpty = { textContent: "" };
  const hostSaveState = { textContent: "" };
  const hostStatus = { warning: dynamicLocalization.HOST_CAPACITY_WARNING };
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
    host() {
      const warningKey = dynamicLocalization.hostWarningKey(hostStatus.warning);
      hostSaveState.textContent = warningKey
        ? i18n.t(warningKey)
        : hostStatus.warning || i18n.t("host.on");
    },
  });
  i18n.subscribe(rerender);

  assert.equal(i18n.setLocale("ig", { persist: false, doc: document }), true);
  assert.equal(resourceEmpty.textContent, "Enweghị akụrụngwa mmụta ugbu a.");
  assert.equal(
    hostSaveState.textContent,
    "Muta enweghị ike itinye otu nkata ụdị Host-mode na RAM dị ugbu a; mechie ngwa ndị ọzọ ma ọ bụ wụnye obere ụdị",
  );
  assert.equal(document.documentElement.lang, "ig");

  assert.equal(i18n.setLocale("en", { persist: false, doc: document }), true);
  assert.equal(resourceEmpty.textContent, "No learning resources yet.");
  assert.equal(hostSaveState.textContent, dynamicLocalization.HOST_CAPACITY_WARNING);
  assert.equal(document.documentElement.lang, "en");

  hostStatus.warning = "untrusted raw API warning";
  rerender();
  assert.equal(dynamicLocalization.hostWarningKey(hostStatus.warning), null);
  assert.equal(hostSaveState.textContent, "untrusted raw API warning");
});

test("the runtime contract enumerates every required dynamic surface", () => {
  assert.deepEqual(
    [...dynamicLocalization.SURFACES],
    ["resources", "host", "power", "model", "status"],
  );
});
