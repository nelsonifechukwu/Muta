const status = document.querySelector("#status");
const error = document.querySelector("#error");
const listen = window.__TAURI__?.event?.listen;

if (listen) {
  listen("backend-error", ({ payload }) => {
    status.textContent = "the personal education companion for every student at every level. powered by AI.";
    error.textContent = payload;
    error.hidden = false;
  });
}
