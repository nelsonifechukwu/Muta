/* Decide the first paint before the app bundle runs.

   This is presentation only: the backend still proves operator authority for every request.
   A loopback URL is the laptop's own Muta, so it opens the local shell immediately. Remote
   LAN addresses retain the account gate until their member session has been verified. */
(function bootstrapMutaAccess() {
  "use strict";

  const rawHostname = window.location.hostname.toLowerCase().replace(/\.$/, "");
  const hostname = rawHostname.startsWith("[") && rawHostname.endsWith("]")
    ? rawHostname.slice(1, -1)
    : rawHostname;
  const localOperator = hostname === "localhost"
    || hostname === "::1"
    || hostname.startsWith("127.")
    || window.location.protocol === "file:"
    || Boolean(window.__TAURI__);

  document.documentElement.dataset.mutaAccess = localOperator ? "operator" : "shared";
  window.MutaAccess = Object.freeze({ localOperator });
})();
