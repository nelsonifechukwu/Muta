/* Accessible in-app destructive confirmation for browser and desktop WebViews. */
"use strict";

((global) => {
  function create({
    modal,
    background,
    cancelButton,
    confirmButton,
    copyElement,
    errorElement,
    copyFor,
    onConfirm,
    successFocus,
    scheduleFocus = global.requestAnimationFrame?.bind(global) || ((callback) => callback()),
  }) {
    const dialog = modal.querySelector(".confirm-card");
    const ownerDocument = modal.ownerDocument || global.document;
    let pending = null;
    let busy = false;

    function setBusy(next) {
      busy = next;
      dialog?.setAttribute("aria-busy", String(next));
      cancelButton.disabled = next;
      confirmButton.disabled = next;
    }

    function refresh() {
      if (pending) copyElement.textContent = copyFor(pending);
    }

    function close({ restoreFocus = true } = {}) {
      const opener = pending?.opener;
      pending = null;
      setBusy(false);
      errorElement.textContent = "";
      modal.hidden = true;
      background.removeAttribute("inert");
      if (!restoreFocus) return;
      if (opener?.isConnected) opener.focus();
      else successFocus?.focus();
    }

    function open(value) {
      pending = value;
      setBusy(false);
      errorElement.textContent = "";
      refresh();
      background.setAttribute("inert", "");
      modal.hidden = false;
      scheduleFocus(() => cancelButton.focus());
    }

    cancelButton.addEventListener("click", () => {
      if (!busy) close();
    });
    modal.addEventListener("click", (event) => {
      if (!busy && event.target === modal) close();
    });
    modal.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!busy) close();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = [cancelButton, confirmButton].filter((control) => !control.disabled);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (!first) {
        event.preventDefault();
        dialog?.focus();
      } else if (event.shiftKey && ownerDocument.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && ownerDocument.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    confirmButton.addEventListener("click", async () => {
      const selected = pending;
      if (!selected || busy) return;
      setBusy(true);
      dialog?.focus();
      let result;
      try {
        result = await onConfirm(selected);
      } catch (error) {
        result = { ok: false, error: error?.message || String(error) };
      }
      if (result?.ok) {
        close({ restoreFocus: false });
        successFocus?.focus();
        return;
      }
      setBusy(false);
      errorElement.textContent = result?.error || "";
      confirmButton.focus();
    });

    return Object.freeze({
      open,
      close,
      refresh,
      isOpen: () => !modal.hidden,
      isBusy: () => busy,
    });
  }

  const api = Object.freeze({ create });
  global.MutaConfirmDialog = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
