"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

global.window = globalThis;
const saved = new Map();
global.localStorage = {
  getItem: (key) => saved.get(key) ?? null,
  setItem: (key, value) => saved.set(key, String(value)),
};
require("../africa-languages.js");
require("../locale-manifest.js");
require("../i18n.js");
require("../locales.js");

const i18n = globalThis.MutaI18n;

class FakeElement {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.dataset = {};
    this.textContent = "";
    this.value = "";
    this.disabled = false;
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

function fakeDocument(elementsBySelector = {}) {
  return {
    documentElement: { lang: "", dir: "" },
    querySelectorAll: (selector) => elementsBySelector[selector] || [],
    querySelector: (selector) => (elementsBySelector[selector] || [])[0] || null,
    createElement: (tag) => new FakeElement(tag),
  };
}

test("only complete packs become selectable", () => {
  const required = Object.keys(i18n.catalogs.en).sort();
  const supported = i18n.supportedDefinitions();
  assert.deepEqual(supported.map((locale) => locale.tag), ["ar", "sw", "yo", "en", "de"]);
  assert.deepEqual(
    supported.map((locale) => ({ tag: locale.tag, direction: locale.direction })),
    i18n.interfaceLocaleManifest,
  );
  for (const locale of supported) {
    assert.deepEqual(Object.keys(i18n.catalogs[locale.tag]).sort(), required);
  }
});

test("the actionable selector puts Auto first, then complete African packs", () => {
  const select = new FakeElement("select");
  const doc = fakeDocument({ "#setting-language": [select] });
  i18n.setLocale("en", { persist: false, doc });
  i18n.populateSelector(select, doc);

  assert.equal(select.children[0].value, "auto");
  assert.equal(select.children[0].textContent, "Auto");
  assert.equal(select.children[1].label, "African languages");
  const african = select.children[1].children;
  assert.deepEqual(african.map((option) => option.value), ["ar", "sw", "yo"]);
  assert.ok(african.every((option) => option.disabled === false));
  assert.deepEqual(select.children[2].children.map((option) => option.value), ["en", "de"]);
  assert.ok(african.every((option) => !option.textContent.includes("🇩🇪")));
});

test("the collapsed country coverage list exposes every candidate outside the selector", () => {
  const coverage = new FakeElement("div");
  const doc = fakeDocument({ "#language-coverage-list": [coverage] });
  i18n.setLocale("en", { persist: false, doc });
  i18n.populateCoverage(coverage, doc);
  const countries = coverage.children[0];
  assert.equal(countries.children.length, 54);
  const angola = countries.children.find((row) => row.children[0].textContent.endsWith("(AO)"));
  assert.ok(angola);
  assert.equal(angola.children[1].children.length, 3);
  assert.match(angola.children[1].children[0].textContent, /Português — translation pending/);
  const nigeria = countries.children.find((row) => row.children[0].textContent.endsWith("(NG)"));
  assert.ok(nigeria.children[1].children.some((pack) => /Naijíriá Píjin/.test(pack.textContent)));
});

test("Africa-54 coverage is explicit, complete, and ordered before additions", () => {
  const registry = i18n.africaRegistry;
  assert.equal(registry.countries.length, 54);
  assert.equal(new Set(registry.countries.map((country) => country.code)).size, 54);
  assert.equal(registry.languages.length, 85);
  assert.deepEqual(
    [...new Set(registry.countries.map((country) => country.code))].sort(),
    "AO BF BI BJ BW CD CF CG CI CM CV DJ DZ EG ER ET GA GH GM GN GQ GW KE KM LR LS LY MA MG ML MR MU MW MZ NA NE NG RW SC SD SL SN SO SS ST SZ TD TG TN TZ UG ZA ZM ZW".split(" ").sort(),
  );
  assert.equal(new Set(registry.languages.map((locale) => locale.tag)).size, 85);
  const definitions = new Map(i18n.localeDefinitions.map((locale) => [locale.tag, locale]));
  for (const country of registry.countries) {
    assert.match(country.code, /^[A-Z]{2}$/);
    assert.ok(country.name);
    assert.ok(country.languages.length > 0, `${country.name} needs a main language`);
    for (const tag of country.languages) {
      const locale = definitions.get(tag);
      assert.ok(locale, `${country.name} references missing ${tag}`);
      assert.ok(locale.autonym, `${tag} needs an autonym`);
      assert.doesNotThrow(() => Intl.getCanonicalLocales(tag));
      assert.ok(["ltr", "rtl"].includes(locale.direction));
      assert.equal(locale.baseline, "africa54");
      assert.ok(locale.countries.includes(country.code));
    }
  }
  const lastBaseline = i18n.localeDefinitions.findLastIndex(
    (locale) => locale.baseline === "africa54",
  );
  const firstAdditional = i18n.localeDefinitions.findIndex(
    (locale) => locale.baseline === "additional",
  );
  assert.ok(firstAdditional > lastBaseline);
  assert.deepEqual(registry.countries.find((country) => country.code === "AO").languages, ["pt", "umb", "kmb"]);
  assert.ok(registry.countries.find((country) => country.code === "BF").languages.includes("dyu"));
  assert.ok(registry.countries.find((country) => country.code === "KM").languages.includes("wni"));
  assert.ok(registry.countries.find((country) => country.code === "KM").languages.includes("wlc"));
  assert.ok(registry.countries.find((country) => country.code === "NA").languages.includes("kj"));
  assert.ok(registry.countries.find((country) => country.code === "NG").languages.includes("pcm"));
  assert.ok(registry.countries.find((country) => country.code === "SS").languages.includes("pga-Latn"));
  const juba = definitions.get("pga-Latn");
  assert.equal(juba.autonym, "Arabi Juba");
  assert.equal(juba.direction, "ltr");
  assert.equal(definitions.get("ttq-Latn").autonym, "Təmajəq");
  assert.equal(definitions.get("ts").autonym, "XiTsonga / Xitsonga");
  assert.equal(
    new Set(registry.countries.flatMap((country) => country.languages)).size,
    registry.languages.length,
  );
});

test("the published country matrix stays identical to the executable registry", () => {
  const markdown = fs.readFileSync(
    path.join(__dirname, "..", "..", "docs", "africa-54-language-coverage.md"),
    "utf8",
  );
  const documented = new Map();
  for (const match of markdown.matchAll(/^\| .+ \| ([A-Z]{2}) \| ([^|]+) \|$/gm)) {
    documented.set(match[1], match[2].split(",").map((tag) => tag.trim()));
  }
  assert.equal(documented.size, 54);
  for (const country of i18n.africaRegistry.countries) {
    assert.deepEqual(documented.get(country.code), country.languages, `${country.code} docs drift`);
  }
});

test("locale changes text, attributes, direction, interpolation, and persistence", () => {
  const heading = new FakeElement();
  heading.dataset.i18n = "settings.title";
  const close = new FakeElement("button");
  close.setAttribute("data-i18n-aria-label", "settings.close");
  const doc = fakeDocument({
    "[data-i18n]": [heading],
    "[data-i18n-aria-label]": [close],
  });

  assert.equal(i18n.setLocale("ar-EG", { doc }), true);
  assert.equal(i18n.languagePreference, "ar");
  assert.equal(i18n.responseLanguage, "ar");
  assert.equal(doc.documentElement.lang, "ar");
  assert.equal(doc.documentElement.dir, "rtl");
  assert.equal(heading.textContent, "الإعدادات");
  assert.equal(close.getAttribute("aria-label"), "إغلاق الإعدادات");
  assert.equal(i18n.t("model.loadingNamed", { model: "Qwen" }), "جارٍ تحميل Qwen…");
  assert.equal(saved.get(i18n.STORAGE_KEY), "ar");

  assert.equal(i18n.setLocale("de-DE", { persist: false, doc }), true);
  assert.equal(i18n.languagePreference, "de");
  assert.equal(doc.documentElement.lang, "de");
  assert.equal(doc.documentElement.dir, "ltr");
  assert.equal(heading.textContent, "Einstellungen");
  assert.equal(i18n.setLocale("not-a-locale", { persist: false, doc }), false);
});

test("startup uses a saved explicit locale, otherwise Auto resolves browser then English", () => {
  const doc = fakeDocument();
  const previousNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  try {
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: { languages: ["de-DE", "en-GB"] },
    });
    saved.set(i18n.STORAGE_KEY, "sw");
    assert.equal(i18n.initialize(doc), "sw");
    assert.equal(i18n.languagePreference, "sw");

    saved.delete(i18n.STORAGE_KEY);
    assert.equal(i18n.initialize(doc), "de");
    assert.equal(i18n.languagePreference, "auto");

    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: { languages: ["xx-YY"] },
    });
    assert.equal(i18n.initialize(doc), "en");
    assert.equal(i18n.languagePreference, "auto");
  } finally {
    saved.delete(i18n.STORAGE_KEY);
    if (previousNavigator) Object.defineProperty(globalThis, "navigator", previousNavigator);
    else delete globalThis.navigator;
    i18n.setLocale("en", { persist: false, doc });
  }
});

test("Auto persists as the response preference while the interface follows the browser", () => {
  const select = new FakeElement("select");
  const doc = fakeDocument({ "#setting-language": [select] });
  const previousNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  try {
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: { languages: ["de-DE", "en-GB"] },
    });
    assert.equal(i18n.setLocale("auto", { doc }), true);
    assert.equal(i18n.locale, "de");
    assert.equal(i18n.languagePreference, "auto");
    assert.equal(i18n.responseLanguage, "auto");
    assert.equal(doc.documentElement.lang, "de");
    assert.equal(select.value, "auto");
    assert.equal(saved.get(i18n.STORAGE_KEY), "auto");
  } finally {
    saved.delete(i18n.STORAGE_KEY);
    if (previousNavigator) Object.defineProperty(globalThis, "navigator", previousNavigator);
    else delete globalThis.navigator;
    i18n.setLocale("en", { persist: false, doc });
  }
});

test("every translation key used by authored markup exists and localization loads first", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const keys = [...html.matchAll(/data-i18n(?:-[a-z-]+)?="([^"]+)"/g)].map((match) => match[1]);
  assert.ok(keys.length > 30);
  for (const key of keys) assert.ok(Object.hasOwn(i18n.catalogs.en, key), `missing ${key}`);
  const scripts = [...html.matchAll(/<script src="([^"]+)"/g)].map((match) => match[1]);
  assert.ok(scripts[0].startsWith("africa-languages.js"));
  assert.ok(scripts[1].startsWith("locale-manifest.js"));
  assert.ok(scripts[2].startsWith("locale-bootstrap.js"));
  const africaIndex = scripts.findIndex((source) => source.startsWith("africa-languages.js"));
  const manifestIndex = scripts.findIndex((source) => source.startsWith("locale-manifest.js"));
  const bootstrapIndex = scripts.findIndex((source) => source.startsWith("locale-bootstrap.js"));
  const i18nIndex = scripts.findIndex((source) => source.startsWith("i18n.js"));
  const localesIndex = scripts.findIndex((source) => source.startsWith("locales.js"));
  const appIndex = scripts.findIndex((source) => source.startsWith("app.js"));
  assert.ok(
    africaIndex >= 0
      && manifestIndex >= 0
      && bootstrapIndex >= 0
      && i18nIndex >= 0
      && localesIndex >= 0
      && appIndex >= 0,
  );
  assert.ok(africaIndex < manifestIndex);
  assert.ok(manifestIndex < bootstrapIndex);
  assert.ok(africaIndex < i18nIndex);
  assert.ok(i18nIndex < localesIndex);
  assert.ok(localesIndex < appIndex);
});

test("the pre-paint bootstrap uses only complete packs and honors saved RTL preferences", () => {
  const script = fs.readFileSync(path.join(__dirname, "..", "locale-bootstrap.js"), "utf8");
  const run = ({ savedLocale, languages }) => {
    const context = {
      MutaInterfaceLocales: i18n.interfaceLocaleManifest,
      document: { documentElement: { lang: "", dir: "" } },
      localStorage: { getItem: () => savedLocale },
      navigator: { languages },
    };
    context.globalThis = context;
    vm.runInNewContext(script, context);
    return context.document.documentElement;
  };

  assert.deepEqual(
    { ...run({ savedLocale: "auto", languages: ["fr-FR"] }) },
    { lang: "en", dir: "ltr" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "auto", languages: ["ar-EG", "en"] }) },
    { lang: "ar", dir: "rtl" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "ar", languages: ["de-DE"] }) },
    { lang: "ar", dir: "rtl" },
  );
});

test("every literal runtime translation key exists", () => {
  for (const filename of ["app.js", "audio.js"]) {
    const script = fs.readFileSync(path.join(__dirname, "..", filename), "utf8");
    const keys = [...script.matchAll(/\bt\("([^"]+)"/g)].map((match) => match[1]);
    assert.ok(keys.length > 3, `${filename} should use the shared translator`);
    for (const key of keys) {
      assert.ok(Object.hasOwn(i18n.catalogs.en, key), `${filename} uses missing ${key}`);
    }
  }
});

test("preamble chunks cannot shadow the translator", () => {
  const script = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
  const start = script.indexOf("pushPreamble(chunk)");
  const body = script.slice(start, script.indexOf("pushThought", start));
  assert.ok(start > 0);
  assert.match(body, /announce\(t\("thinking\.warmingAnnouncement"\)\)/);
  assert.match(body, /preambleText\.textContent \+= chunk/);
  assert.doesNotMatch(script, /pushPreamble\(t\)/);
});
