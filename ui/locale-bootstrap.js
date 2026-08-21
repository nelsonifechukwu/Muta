/* Apply the saved/browser writing direction before CSS paints. The full catalogs and
 * interface translation load at the end of the document. */
"use strict";

(() => {
  const definitions = globalThis.MutaInterfaceLocales || [];
  const definitionsByTag = new Map(
    definitions.map((locale) => [locale.tag.toLowerCase(), locale]),
  );
  let saved = null;
  try {
    saved = globalThis.localStorage?.getItem("muta-ui-locale-v1");
  } catch {
    /* Storage can be unavailable in a locked-down browser. */
  }
  // Auto is a response preference, not a catalog. Its pre-paint UI locale follows the browser.
  const savedInterfaceLocale = saved?.trim().toLowerCase() === "auto" ? null : saved;
  const preferences = [
    savedInterfaceLocale,
    ...(globalThis.navigator?.languages || [globalThis.navigator?.language]),
  ];
  const locale = preferences
    .filter((preference) => typeof preference === "string")
    .map((preference) => preference.trim().replaceAll("_", "-").toLowerCase())
    .map((preference) => definitionsByTag.get(preference)
      || definitionsByTag.get(preference.split("-")[0]))
    .find(Boolean) || definitionsByTag.get("en");
  document.documentElement.lang = locale.tag;
  document.documentElement.dir = locale.direction;
})();
