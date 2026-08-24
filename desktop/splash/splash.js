const status = document.querySelector("#status");
const error = document.querySelector("#error");
const listen = window.__TAURI__?.event?.listen;

if (listen) {
  listen("backend-status", ({ payload }) => {
    status.textContent = payload;
  });
  listen("backend-error", ({ payload }) => {
    status.textContent = "Muta could not start.";
    error.textContent = payload;
    error.hidden = false;
    document.querySelector(".bar").hidden = true;
  });
}
