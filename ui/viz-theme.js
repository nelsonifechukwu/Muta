/* Resolve the parent-selected appearance before the sandboxed frame stylesheet is fetched. */
"use strict";

(() => {
  const theme = new URLSearchParams(window.location.search).get("theme") === "dark"
    ? "dark"
    : "light";
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
})();
