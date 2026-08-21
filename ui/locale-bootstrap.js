/* Apply the saved/browser writing direction before CSS paints. The full catalogs and
 * interface translation load at the end of the document. */
"use strict";

(() => {
  const definitions = [
    ...(globalThis.MutaAfricaLanguages?.languages || []),
    { tag: "de", direction: "ltr" },
  ];
  const definitionsByTag = new Map(
    definitions.map((locale) => [locale.tag.toLowerCase(), locale]),
  );
  let saved = null;
  try {
    saved = globalThis.localStorage?.getItem("muta-ui-locale-v1");
  } catch {
    /* Storage can be unavailable in a locked-down browser. */
  }
  const preferences = [saved, ...(globalThis.navigator?.languages || [globalThis.navigator?.language])];
  const locale = preferences
    .filter((preference) => typeof preference === "string")
    .map((preference) => preference.trim().replaceAll("_", "-").toLowerCase())
    .map((preference) => definitionsByTag.get(preference)
      || definitionsByTag.get(preference.split("-")[0]))
    .find(Boolean) || definitionsByTag.get("en");
  document.documentElement.lang = locale.tag;
  document.documentElement.dir = locale.direction;
})();
