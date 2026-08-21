/* Complete interface packs shared by the pre-paint bootstrap and the full i18n runtime.
 * Add a locale here only after its catalog contains every English interface key. */
"use strict";

(() => {
  const locales = Object.freeze([
    Object.freeze({ tag: "ar", direction: "rtl" }),
    Object.freeze({ tag: "sw", direction: "ltr" }),
    Object.freeze({ tag: "yo", direction: "ltr" }),
    Object.freeze({ tag: "en", direction: "ltr" }),
    Object.freeze({ tag: "de", direction: "ltr" }),
  ]);
  globalThis.MutaInterfaceLocales = locales;
  if (typeof module !== "undefined" && module.exports) module.exports = locales;
})();
