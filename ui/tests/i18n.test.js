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
require("../locale-fr.js");
require("../locale-generated.js");
require("../locales.js");

const i18n = globalThis.MutaI18n;
const generatedMetadata = require("../locale-generated.meta.json");

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

test("only complete packs localize the interface", () => {
  const required = Object.keys(i18n.catalogs.en).sort();
  const supported = i18n.supportedDefinitions();
  assert.equal(supported.length, 28);
  assert.deepEqual(
    supported.map((locale) => ({ tag: locale.tag, direction: locale.direction })),
    i18n.interfaceLocaleManifest,
  );
  for (const locale of supported) {
    const catalog = i18n.catalogs[locale.tag];
    assert.deepEqual(Object.keys(catalog).sort(), required);
    assert.ok(Object.values(catalog).every((value) => typeof value === "string" && value.trim()));
    for (const key of required) {
      const placeholders = (value) => [...value.matchAll(/\{[a-zA-Z][\w]*\}/g)]
        .map((match) => match[0])
        .sort();
      assert.deepEqual(
        placeholders(catalog[key]),
        placeholders(i18n.catalogs.en[key]),
        `${locale.tag}:${key} placeholder parity`,
      );
    }
  }
});

test("machine-assisted packs retain provenance and hide every rejected registry tag", () => {
  const generatedTags = Object.keys(generatedMetadata.generated);
  const hiddenTags = Object.keys(generatedMetadata.hidden);
  assert.equal(generatedTags.length, 22);
  assert.equal(hiddenTags.length, 58);
  assert.equal(new Set([...generatedTags, ...hiddenTags]).size, 80);
  for (const tag of generatedTags) {
    const record = generatedMetadata.generated[tag];
    assert.match(record.provenance, /^(google-web(?:\+nllb:.*)?|nllb:)/);
    assert.equal(record.review, "machine-assisted-unreviewed");
    assert.equal(record.target.split("_", 1)[0], tag.split("-", 1)[0]);
    assert.ok(i18n.supportedDefinitions().some((locale) => locale.tag === tag));
    const catalog = i18n.catalogs[tag];
    for (const [key, value] of Object.entries(catalog)) {
      assert.doesNotMatch(value, /ZXQMUTA|86\d{8}|Translating\.\.\.|Translation results/);
      assert.doesNotMatch(value, /(?:^|\s)\d{3,4}\s*[:፡]/u, `${tag}:${key} merged row`);
      assert.doesNotMatch(
        value,
        /Couldn[’']t (?:start|stop)|Show more|Select the local tutor model|Web grounding (?:on|off)|sources will cited|I[’']m still listening|operator[’']s fixed inference-slot|shared tutor model|Enter to send|Ctrl\+Enter to interrupt|Ground answers|off by default|Tokens per second|Loading \{model\}|offline · local CPU|backend process tree|\(voice loop\)/i,
        `${tag}:${key} English/browser fragment`,
      );
      if (i18n.catalogs.en[key].length > 24) {
        assert.notEqual(value.trim(), i18n.catalogs.en[key].trim(), `${tag}:${key} untranslated`);
      }
    }
    for (const key of [
      "country.southAfrica",
      "nav.aboutMuta",
      "nav.home",
      "settings.general",
      "model.loadingNamed",
      "web.off",
      "badge.verified",
      "telemetry.throttleTitle",
    ]) {
      if (tag === "es" && key === "settings.general") continue;
      assert.notEqual(
        catalog[key].trim(),
        i18n.catalogs.en[key].trim(),
        `${tag}:${key} untranslated short UI label`,
      );
    }
    assert.notEqual(catalog["model.readyNew"].trim(), catalog["model.ready"].trim());
    assert.notEqual(catalog["settings.saveFailed"].trim(), catalog["voice.didNotCatch"].trim());
  }
  for (const tag of hiddenTags) {
    assert.ok(i18n.normalizeKnownLocale(tag), `${tag} must remain registered internally`);
    assert.equal(i18n.normalizeLocale(tag), null, `${tag} must remain hidden`);
    assert.ok(generatedMetadata.hidden[tag].length > 0);
  }
  const joinedAmharic = Object.values(i18n.catalogs.am).join(" ");
  assert.ok((joinedAmharic.match(/[\u1200-\u137f]/g) || []).length > 500);
  assert.ok(generatedMetadata.hidden.ti.includes("native-review:untranslated-english"));
  assert.ok(generatedMetadata.hidden.zgh.some((reason) => reason.startsWith("target-mismatch:")));
});

test("the selector puts Auto first and exposes only complete interface languages", () => {
  const select = new FakeElement("select");
  const doc = fakeDocument({ "#setting-language": [select] });
  i18n.setLocale("en", { persist: false, doc });
  i18n.populateSelector(select, doc);

  assert.equal(select.children[0].value, "auto");
  assert.equal(select.children[0].textContent, "Auto");
  assert.equal(select.children[1].label, "African languages");
  const african = select.children[1].children;
  const other = select.children[2].children;
  const options = [...african, ...other];
  assert.equal(options.length, i18n.supportedDefinitions().length);
  assert.deepEqual(
    options.map((option) => option.value),
    i18n.supportedDefinitions()
      .filter((locale) => locale.group === "african")
      .concat(i18n.supportedDefinitions().filter((locale) => locale.group === "other"))
      .map((locale) => locale.tag),
  );
  assert.ok(options.every((option) => option.disabled === false));
  for (const tag of ["am", "ha", "ig", "zu", "de"]) {
    assert.ok(options.some((option) => option.value === tag), `missing ${tag}`);
  }
  for (const tag of ["cri", "pga-Latn", "ttq-Latn", "wlc"]) {
    assert.ok(!options.some((option) => option.value === tag), `unsupported ${tag} is visible`);
  }
  assert.ok(options.every((option) => !/pending|review/i.test(option.textContent)));
  assert.ok(options.every((option) => !option.textContent.includes("🇩🇪")));
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

  assert.equal(i18n.setLocale("fr-FR", { persist: false, doc }), true);
  assert.equal(i18n.languagePreference, "fr");
  assert.equal(doc.documentElement.lang, "fr");
  assert.equal(doc.documentElement.dir, "ltr");
  assert.equal(heading.textContent, "Paramètres");
  assert.equal(close.getAttribute("aria-label"), "Fermer les paramètres");
  assert.equal(i18n.t("model.loadingNamed", { model: "Qwen" }), "Chargement de Qwen…");
  assert.equal(i18n.setLocale("not-a-locale", { persist: false, doc }), false);
});

test("a hidden registry language cannot become a UI preference", () => {
  const heading = new FakeElement();
  heading.dataset.i18n = "settings.title";
  const select = new FakeElement("select");
  const doc = fakeDocument({
    "[data-i18n]": [heading],
    "#setting-language": [select],
  });
  try {
    saved.delete(i18n.STORAGE_KEY);
    i18n.setLocale("fr", { persist: false, doc });
    assert.equal(i18n.setLocale("pga-Latn", { doc }), false);
    assert.equal(i18n.languagePreference, "fr");
    assert.equal(saved.has(i18n.STORAGE_KEY), false);
  } finally {
    saved.delete(i18n.STORAGE_KEY);
    i18n.setLocale("en", { persist: false, doc });
  }
});

test("startup uses a saved explicit locale, otherwise Auto resolves browser then English", () => {
  const doc = fakeDocument();
  const previousNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  try {
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: { languages: ["de-DE", "en-GB"] },
    });
    saved.set(i18n.STORAGE_KEY, "pga-Latn");
    assert.equal(i18n.initialize(doc), "de");
    assert.equal(i18n.languagePreference, "auto");

    saved.set(i18n.STORAGE_KEY, "sw");
    assert.equal(i18n.initialize(doc), "sw");
    assert.equal(i18n.languagePreference, "sw");

    saved.set(i18n.STORAGE_KEY, "fr");
    assert.equal(i18n.initialize(doc), "fr");
    assert.equal(i18n.languagePreference, "fr");

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
  assert.match(html, /<html\b[^>]*\btranslate="no"[^>]*\bclass="notranslate"/);
  assert.match(html, /<meta\s+name="google"\s+content="notranslate">/);
  assert.doesNotMatch(html, /language-review-note|africa-coverage-note|language-coverage-list/);
  const keys = [...html.matchAll(/data-i18n(?:-[a-z-]+)?="([^"]+)"/g)].map((match) => match[1]);
  assert.ok(keys.length > 30);
  for (const key of keys) assert.ok(Object.hasOwn(i18n.catalogs.en, key), `missing ${key}`);
  const scripts = [...html.matchAll(/<script src="([^"]+)"/g)].map((match) => match[1]);
  assert.ok(scripts[0].startsWith("access-bootstrap.js"));
  assert.ok(scripts[1].startsWith("africa-languages.js"));
  assert.ok(scripts[2].startsWith("locale-manifest.js"));
  assert.ok(scripts[3].startsWith("locale-bootstrap.js"));
  const africaIndex = scripts.findIndex((source) => source.startsWith("africa-languages.js"));
  const manifestIndex = scripts.findIndex((source) => source.startsWith("locale-manifest.js"));
  const bootstrapIndex = scripts.findIndex((source) => source.startsWith("locale-bootstrap.js"));
  const i18nIndex = scripts.findIndex((source) => source.startsWith("i18n.js"));
  const localesIndex = scripts.findIndex((source) => source.startsWith("locales.js"));
  const frenchIndex = scripts.findIndex((source) => source.startsWith("locale-fr.js"));
  const generatedIndex = scripts.findIndex((source) => source.startsWith("locale-generated.js"));
  const appIndex = scripts.findIndex((source) => source.startsWith("app.js"));
  assert.ok(
    africaIndex >= 0
      && manifestIndex >= 0
      && bootstrapIndex >= 0
      && i18nIndex >= 0
      && frenchIndex >= 0
      && generatedIndex >= 0
      && localesIndex >= 0
      && appIndex >= 0,
  );
  assert.ok(africaIndex < manifestIndex);
  assert.ok(manifestIndex < bootstrapIndex);
  assert.ok(africaIndex < i18nIndex);
  assert.ok(i18nIndex < frenchIndex);
  assert.ok(frenchIndex < localesIndex);
  assert.ok(frenchIndex < generatedIndex);
  assert.ok(generatedIndex < localesIndex);
  assert.ok(i18nIndex < localesIndex);
  assert.ok(localesIndex < appIndex);
});

test("the pre-paint bootstrap uses only complete packs and honors saved RTL preferences", () => {
  const script = fs.readFileSync(path.join(__dirname, "..", "locale-bootstrap.js"), "utf8");
  const run = ({ savedLocale, languages }) => {
    const context = {
      MutaAfricaLanguages: i18n.africaRegistry,
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
    { lang: "fr", dir: "ltr" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "auto", languages: ["ar-EG", "en"] }) },
    { lang: "ar", dir: "rtl" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "ar", languages: ["de-DE"] }) },
    { lang: "ar", dir: "rtl" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "fr", languages: ["en-GB"] }) },
    { lang: "fr", dir: "ltr" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "ig", languages: ["de-DE"] }) },
    { lang: "ig", dir: "ltr" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "pga-Latn", languages: ["de-DE"] }) },
    { lang: "de", dir: "ltr" },
  );
  assert.deepEqual(
    { ...run({ savedLocale: "not-a-locale", languages: ["de-DE"] }) },
    { lang: "de", dir: "ltr" },
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
