"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

global.window = globalThis;
global.localStorage = { getItem: () => null, setItem: () => {} };
require("../africa-languages.js");
require("../locale-manifest.js");
require("../i18n.js");
require("../locale-fr.js");
require("../locales.js");
require("../locale-generated.js");

const i18n = globalThis.MutaI18n;

class FakeElement {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.dataset = {};
    this.textContent = "";
    this.value = "";
  }

  set innerHTML(value) {
    assert.equal(value, "");
    this.children = [];
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }
}

function documentProfile(width) {
  const heading = new FakeElement("h1");
  heading.dataset.i18n = "empty.title";
  const helper = new FakeElement("small");
  helper.dataset.i18n = "settings.parallelHelp";
  const composer = new FakeElement("div");
  composer.setAttribute("data-i18n-aria-label", "composer.placeholder");
  const select = new FakeElement("select");
  const selectors = {
    "[data-i18n]": [heading, helper],
    "[data-i18n-title]": [],
    "[data-i18n-aria-label]": [composer],
    "[data-i18n-placeholder]": [],
    "[data-i18n-data-placeholder]": [],
    "#setting-language": [select],
  };
  return {
    width,
    heading,
    helper,
    composer,
    select,
    document: {
      documentElement: { lang: "", dir: "" },
      defaultView: { innerWidth: width },
      querySelectorAll: (selector) => selectors[selector] || [],
      querySelector: (selector) => (selectors[selector] || [])[0] || null,
      createElement: (tag) => new FakeElement(tag),
    },
  };
}

for (const [profile, width] of [["mobile", 390], ["desktop", 1440]]) {
  test(`${profile} runtime switches long, RTL, and multibyte locale content`, () => {
    const fixture = documentProfile(width);
    const { document, heading, helper, composer, select } = fixture;

    assert.equal(i18n.setLocale("ar", { persist: false, doc: document }), true);
    assert.equal(document.documentElement.lang, "ar");
    assert.equal(document.documentElement.dir, "rtl");
    assert.equal(heading.textContent, i18n.catalogs.ar["empty.title"]);
    assert.equal(helper.textContent, i18n.catalogs.ar["settings.parallelHelp"]);
    assert.equal(composer.getAttribute("aria-label"), i18n.catalogs.ar["composer.placeholder"]);
    assert.equal(select.value, "ar");

    assert.equal(i18n.setLocale("am", { persist: false, doc: document }), true);
    assert.equal(document.documentElement.lang, "am");
    assert.equal(document.documentElement.dir, "ltr");
    assert.match(heading.textContent, /[\u1200-\u137f]/u);
    assert.equal(helper.textContent, i18n.catalogs.am["settings.parallelHelp"]);
    assert.equal(select.value, "am");

    assert.equal(i18n.setLocale("de", { persist: false, doc: document }), true);
    assert.equal(document.documentElement.lang, "de");
    assert.equal(document.documentElement.dir, "ltr");
    assert.equal(helper.textContent, i18n.catalogs.de["settings.parallelHelp"]);
    assert.ok(helper.textContent.length > 80, "long translated helper must remain intact");
    assert.equal(select.value, "de");
    assert.equal(select.children[0].value, "auto");
    assert.ok(select.children.length >= 3, "Auto and grouped visible locales must remain available");
  });
}

test("authored mobile composer and generated prose retain automatic bidi isolation", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const app = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
  assert.match(html, /id="input"[^>]*\bdir="auto"/s);
  assert.match(app, /prose\.dir\s*=\s*"auto"/);
  assert.match(app, /thought\.dir\s*=\s*"auto"/);
});

test("localized visualization frame opts out of browser translation", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "viz-frame.html"), "utf8");
  assert.match(html, /<html[^>]*translate="no"[^>]*class="notranslate"/);
  assert.match(html, /<meta name="google" content="notranslate">/);
});
