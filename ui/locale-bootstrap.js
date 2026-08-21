/* Apply the saved/browser writing direction before CSS paints. The full catalogs and
 * interface translation load at the end of the document. */
"use strict";

(() => {
  const definitions = globalThis.MutaInterfaceLocales || [];
  const normalize = (value) => typeof value === "string"
    ? value.trim().replaceAll("_", "-").toLowerCase()
    : "";
  const match = (value, choices) => {
    const normalized = normalize(value);
    return choices.find((locale) => normalize(locale.tag) === normalized)
      || choices.find((locale) => normalize(locale.tag).split("-")[0] === normalized.split("-")[0])
      || null;
  };
  let saved = null;
  try {
    saved = globalThis.localStorage?.getItem("muta-ui-locale-v1");
  } catch {
    /* Storage can be unavailable in a locked-down browser. */
  }
  const defaultLocale = match("en", definitions);
  const savedPreference = match(saved, definitions);
  const followsBrowser = !normalize(saved) || normalize(saved) === "auto" || !savedPreference;
  const browserPreferences = globalThis.navigator?.languages || [globalThis.navigator?.language];
  // Auto and legacy/invalid hidden values follow the first complete browser-language pack.
  const locale = followsBrowser
    ? browserPreferences.map((preference) => match(preference, definitions)).find(Boolean)
      || defaultLocale
    : match(savedPreference.tag, definitions) || defaultLocale;
  document.documentElement.lang = locale.tag;
  document.documentElement.dir = locale.direction;
})();
