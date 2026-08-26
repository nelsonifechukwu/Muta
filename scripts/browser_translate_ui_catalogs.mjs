/**
 * Browser-assisted UI catalog translator.
 *
 * This development helper is loaded by the Codex browser session and drives the visible Google
 * Translate text UI. It deliberately writes only an intermediate JSON cache; the Python catalog
 * generator performs the final acceptance checks before anything becomes learner-visible.
 */

import fs from "node:fs";
import vm from "node:vm";

const CACHE_PATH = "/tmp/muta-google-translations.json";
const SOURCE_PARAPHRASES = {
  "reply.startFailed": "The reply did not start. Your message is saved above.",
  "reply.stopFailed": "The reply is still running. I cannot stop it yet.",
  "voice.answerFailed": "The answer failed. I am still listening. Ask again.",
  "web.on": "Online sources are enabled. Sources will be cited when internet is available.",
};

function placeholders(text) {
  return [...String(text).matchAll(/\{([a-zA-Z][\w]*)\}/g)].map((match) => match[0]).sort();
}

function maskEntry(text, indexBase) {
  const masks = [];
  const masked = String(text).replace(/\{([a-zA-Z][\w]*)\}/g, (match) => {
    const sentinel = String(8600000000 + indexBase + masks.length);
    masks.push([sentinel, match]);
    return sentinel;
  });
  return { masked, masks };
}

function loadCatalog(repoRoot) {
  const sandbox = { module: { exports: {} }, console };
  sandbox.globalThis = sandbox;
  for (const relative of [
    "ui/africa-languages.js",
    "ui/locale-manifest.js",
    "ui/release-english.js",
    "ui/i18n.js",
  ]) {
    vm.runInNewContext(fs.readFileSync(`${repoRoot}/${relative}`, "utf8"), sandbox);
  }
  return sandbox.MutaI18n.catalogs.en;
}

export function createTranslationPipeline(tab, repoRoot) {
  const english = loadCatalog(repoRoot);
  const entries = Object.entries(english);
  const cache = fs.existsSync(CACHE_PATH)
    ? JSON.parse(fs.readFileSync(CACHE_PATH, "utf8"))
    : {};

  function makeChunks() {
    const chunks = [];
    let current = [];
    let size = 0;
    entries.forEach(([key, value], index) => {
      const { masked, masks } = maskEntry(value, index * 8);
      const line = `${String(index).padStart(3, "0")}: ${masked}`;
      if (current.length && size + line.length + 1 > 4300) {
        chunks.push(current);
        current = [];
        size = 0;
      }
      current.push({ index, key, line, masks });
      size += line.length + 1;
    });
    if (current.length) chunks.push(current);
    return chunks;
  }

  const chunks = makeChunks();
  const flatItems = chunks.flat();

  function restore(translated, item) {
    let value = translated;
    for (const [sentinel, placeholder] of item.masks) {
      value = value.split(sentinel).join(placeholder);
    }
    const expected = placeholders(english[item.key]);
    const alteredSentinels = [...value.matchAll(/\d{8,12}/g)];
    if (expected.length && alteredSentinels.length === expected.length) {
      let index = 0;
      value = value.replace(/\d{8,12}/g, () => expected[index++]);
    }
    return value;
  }

  function validateMessage(key, value) {
    const source = english[key];
    const reasons = [];
    if (!value || !value.trim()) reasons.push("empty");
    if (/ZXQMUTA[A-Z]+QXZ/.test(value) || /86\d{8}/.test(value)) reasons.push("sentinel");
    if (JSON.stringify(placeholders(value)) !== JSON.stringify(placeholders(source))) {
      reasons.push("placeholders");
    }
    if (source.length > 24 && value.length < Math.max(6, source.length * 0.18)) {
      reasons.push("too-short");
    }
    if (source.length > 24 && value.trim() === source.trim()) reasons.push("untranslated");
    if (value.length > Math.max(80, source.length * 6)) reasons.push("too-long");
    if (/(?:^|\s)\d{3,4}\s*[:፡]/u.test(value)) reasons.push("merged-row");
    if (/Couldn[’']t (?:start|stop)|Show more|Select the local tutor model|Web grounding on|sources will cited|I[’']m still listening/i.test(value)) {
      reasons.push("english-fragment");
    }
    return reasons;
  }

  async function waitForResult(marker) {
    const region = tab.playwright.getByRole("region", { name: "Translation results" });
    const markerPattern = new RegExp(`(?:^|\\n)${marker}\\s*:`);
    let raw = "";
    for (let attempt = 0; attempt < 80; attempt += 1) {
      await tab.playwright.waitForTimeout(120);
      raw = await region.innerText({ timeoutMs: 10000 });
      if (markerPattern.test(raw) && !raw.includes("Translating...")) break;
    }
    return raw;
  }

  async function translateSingle(item) {
    const source = SOURCE_PARAPHRASES[item.key] || english[item.key];
    const { masked, masks } = maskEntry(source, item.index * 8);
    const marker = String(700 + item.index);
    await tab.playwright.getByRole("combobox", { name: "Source text" }).fill(`${marker}: ${masked}`);
    const raw = await waitForResult(marker);
    const match = raw.match(new RegExp(`(?:^|\\n)${marker}\\s*:\\s*(\\S[\\s\\S]*?)$`));
    if (!match) return null;
    return restore(match[1].trim(), { ...item, masks });
  }

  async function translateSample(item) {
    const expected = placeholders(english[item.key]);
    const samples = ["17", "29", "43", "61"];
    let source = english[item.key];
    if (item.key === "thinking.seconds") source = "Thought for {seconds} seconds.";
    if (item.key === "thinking.minutes") {
      source = "Thought for {minutes} minutes and {seconds} seconds.";
    }
    if (item.key === "queue.discardedOne" || item.key === "queue.discardedMany") {
      source = "Discarded {count} queued messages.";
    }
    if (item.key === "queue.waitingSlot") {
      source = "Queue position {position}. Waiting for a free place.";
    }
    if (item.key === "web.title") {
      source = "Use online sources when internet is available (disabled by default).";
    }
    if (item.key === "web.label") source = "Use online sources";
    if (item.key === "web.on") {
      source = "Online sources are enabled. Sources will be cited when internet is available.";
    }
    expected.forEach((placeholder, index) => {
      source = source.split(placeholder).join(samples[index]);
    });
    const marker = String(1000 + item.index);
    await tab.playwright.getByRole("combobox", { name: "Source text" }).fill(`${marker}: ${source}`);
    const raw = await waitForResult(marker);
    const match = raw.match(new RegExp(`(?:^|\\n)${marker}\\s*:\\s*(\\S[\\s\\S]*?)$`));
    if (!match) return null;
    let translated = match[1].trim();
    for (let index = 0; index < expected.length; index += 1) {
      if (!translated.includes(samples[index])) return null;
      translated = translated.replace(samples[index], expected[index]);
    }
    return translated;
  }

  function validateResult(result) {
    result.errors = [];
    for (const [key, value] of Object.entries(result.messages)) {
      for (const reason of validateMessage(key, value)) result.errors.push(`${reason}:${key}`);
    }
  }

  function save() {
    fs.writeFileSync(CACHE_PATH, `${JSON.stringify(cache, null, 2)}\n`);
  }

  async function translateLocale(tag, targetCode) {
    await tab.goto(
      `https://translate.google.co.uk/?sl=en&tl=${encodeURIComponent(targetCode)}&op=translate`,
    );
    const result = {
      provenance: "google-web",
      target: targetCode,
      messages: {},
      errors: [],
      retried: [],
    };
    for (const chunk of chunks) {
      const source = chunk.map((item) => item.line).join("\n");
      await tab.playwright.getByRole("combobox", { name: "Source text" }).fill(source, {
        timeoutMs: 10000,
      });
      const lastMarker = String(chunk.at(-1).index).padStart(3, "0");
      const raw = (await waitForResult(lastMarker)).replace(/^Translation results\s*/, "");
      const found = new Map();
      const rowPattern = /(?:^|\n)(\d{3})\s*:\s*([\s\S]*?)(?=\n\d{3}\s*:|$)/g;
      let match;
      // Google can append a second, romanised transcript after the native-script translation.
      // The first row for an index is the requested-script result; later duplicates are aids for
      // pronunciation and must never replace the actual locale catalog.
      while ((match = rowPattern.exec(raw))) {
        const index = Number(match[1]);
        if (!found.has(index)) found.set(index, match[2].trim());
      }
      for (const item of chunk) result.messages[item.key] = restore(found.get(item.index) || "", item);
    }
    for (const item of flatItems) {
      if (validateMessage(item.key, result.messages[item.key]).length) {
        const retry = await translateSingle(item);
        result.retried.push(item.key);
        if (retry !== null) result.messages[item.key] = retry;
      }
      if (validateMessage(item.key, result.messages[item.key]).length) {
        const sample = await translateSample(item);
        if (sample !== null) result.messages[item.key] = sample;
      }
    }
    validateResult(result);
    cache[tag] = result;
    save();
    return {
      tag,
      targetCode,
      keys: Object.keys(result.messages).length,
      retried: result.retried.length,
      errors: result.errors,
    };
  }

  async function repairLocale(tag) {
    const result = cache[tag];
    await tab.goto(
      `https://translate.google.co.uk/?sl=en&tl=${encodeURIComponent(result.target)}&op=translate`,
    );
    const failedSet = new Set(
      result.errors.map((error) => error.split(":").slice(1).join(":")),
    );
    // A merged numbered row can shift its romanised duplicate into the following message. Repair
    // both sides singly so the cache cannot retain a plausible-looking, wrong-language neighbour.
    for (const key of [...failedSet]) {
      if (!validateMessage(key, result.messages[key]).includes("merged-row")) continue;
      const index = flatItems.findIndex((candidate) => candidate.key === key);
      if (index >= 0 && flatItems[index + 1]) failedSet.add(flatItems[index + 1].key);
    }
    const failed = [...failedSet];
    result.retried = [...new Set([...(result.retried || []), ...failed])];
    for (const key of failed) {
      const item = flatItems.find((candidate) => candidate.key === key);
      const retry = await translateSingle(item);
      if (retry !== null) result.messages[key] = retry;
      if (validateMessage(key, result.messages[key]).length) {
        const sample = await translateSample(item);
        if (sample !== null) result.messages[key] = sample;
      }
    }
    validateResult(result);
    save();
    return { tag, failed: failed.length, errors: result.errors };
  }

  async function extendLocale(tag, targetCode, onlyKeys = null) {
    const result = cache[tag] || {
      provenance: "google-web",
      target: targetCode,
      messages: {},
      errors: [],
      retried: [],
    };
    result.target = targetCode;
    const allowed = onlyKeys ? new Set(onlyKeys) : null;
    const missing = flatItems.filter(
      (item) => (!allowed || allowed.has(item.key)) && !Object.hasOwn(result.messages, item.key),
    );
    if (!missing.length) return { tag, added: 0, errors: result.errors || [] };
    await tab.goto(
      `https://translate.google.co.uk/?sl=en&tl=${encodeURIComponent(targetCode)}&op=translate`,
    );
    let pending = [];
    let pendingSize = 0;
    const batches = [];
    for (const item of missing) {
      if (pending.length && pendingSize + item.line.length + 1 > 4300) {
        batches.push(pending);
        pending = [];
        pendingSize = 0;
      }
      pending.push(item);
      pendingSize += item.line.length + 1;
    }
    if (pending.length) batches.push(pending);
    for (const batch of batches) {
      await tab.playwright.getByRole("combobox", { name: "Source text" }).fill(
        batch.map((item) => item.line).join("\n"),
        { timeoutMs: 10000 },
      );
      const lastMarker = String(batch.at(-1).index).padStart(3, "0");
      const raw = (await waitForResult(lastMarker)).replace(/^Translation results\s*/, "");
      const found = new Map();
      const rowPattern = /(?:^|\n)(\d{3})\s*:\s*([\s\S]*?)(?=\n\d{3}\s*:|$)/g;
      let match;
      while ((match = rowPattern.exec(raw))) {
        const index = Number(match[1]);
        if (!found.has(index)) found.set(index, match[2].trim());
      }
      for (const item of batch) result.messages[item.key] = restore(found.get(item.index) || "", item);
    }
    result.errors = [];
    for (const [key, value] of Object.entries(result.messages)) {
      for (const reason of validateMessage(key, value)) result.errors.push(`${reason}:${key}`);
    }
    cache[tag] = result;
    save();
    if (result.errors.length) await repairLocale(tag);
    return { tag, added: missing.length, errors: result.errors };
  }

  return {
    cache,
    chunks,
    english,
    extendLocale,
    repairLocale,
    translateLocale,
    validateMessage,
  };
}
