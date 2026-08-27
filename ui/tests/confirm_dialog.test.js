"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../confirm-dialog.js");

function control(document) {
  const listeners = new Map();
  const attributes = new Map();
  return {
    disabled: false,
    isConnected: true,
    textContent: "",
    addEventListener(type, callback) { listeners.set(type, callback); },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    hasAttribute(name) { return attributes.has(name); },
    listener(type) { return listeners.get(type); },
    focus() { document.activeElement = this; },
  };
}

function fixture(onConfirm) {
  const document = { activeElement: null };
  const modal = control(document);
  const card = control(document);
  modal.hidden = true;
  modal.ownerDocument = document;
  modal.querySelector = () => card;
  const background = control(document);
  const cancelButton = control(document);
  const confirmButton = control(document);
  const copyElement = control(document);
  const errorElement = control(document);
  const successFocus = control(document);
  const dialog = create({
    modal,
    background,
    cancelButton,
    confirmButton,
    copyElement,
    errorElement,
    copyFor: ({ user }) => `Delete ${user}? Conversations and files are removed.`,
    onConfirm,
    successFocus,
    scheduleFocus: (callback) => callback(),
  });
  return {
    document, modal, card, background, cancelButton, confirmButton,
    copyElement, errorElement, successFocus, dialog,
  };
}

function key(key, shiftKey = false) {
  return {
    key,
    shiftKey,
    prevented: false,
    stopped: false,
    preventDefault() { this.prevented = true; },
    stopPropagation() { this.stopped = true; },
  };
}

test("Cancel is the safe default and Escape restores focus without deleting", () => {
  let confirmations = 0;
  const ui = fixture(async () => { confirmations += 1; return { ok: true }; });
  const opener = control(ui.document);
  ui.dialog.open({ user: "Ada", opener });

  assert.equal(ui.modal.hidden, false);
  assert.equal(ui.background.hasAttribute("inert"), true);
  assert.equal(ui.document.activeElement, ui.cancelButton);
  assert.match(ui.copyElement.textContent, /Ada/);

  const escape = key("Escape");
  ui.modal.listener("keydown")(escape);
  assert.equal(escape.prevented, true);
  assert.equal(escape.stopped, true);
  assert.equal(ui.modal.hidden, true);
  assert.equal(ui.background.hasAttribute("inert"), false);
  assert.equal(ui.document.activeElement, opener);
  assert.equal(confirmations, 0);
});

test("Tab stays trapped inside the modal in both directions", () => {
  const ui = fixture(async () => ({ ok: true }));
  ui.dialog.open({ user: "Bola", opener: control(ui.document) });
  ui.confirmButton.focus();
  const forward = key("Tab");
  ui.modal.listener("keydown")(forward);
  assert.equal(forward.prevented, true);
  assert.equal(ui.document.activeElement, ui.cancelButton);
  const backward = key("Tab", true);
  ui.modal.listener("keydown")(backward);
  assert.equal(backward.prevented, true);
  assert.equal(ui.document.activeElement, ui.confirmButton);
});

test("failed removal remains open with an actionable error and can be retried", async () => {
  let attempts = 0;
  const ui = fixture(async () => {
    attempts += 1;
    return attempts === 1 ? { ok: false, error: "Could not revoke this account." } : { ok: true };
  });
  ui.dialog.open({ user: "Chika", opener: control(ui.document) });

  await ui.confirmButton.listener("click")();
  assert.equal(ui.modal.hidden, false);
  assert.equal(ui.errorElement.textContent, "Could not revoke this account.");
  assert.equal(ui.confirmButton.disabled, false);
  assert.equal(ui.document.activeElement, ui.confirmButton);

  await ui.confirmButton.listener("click")();
  assert.equal(attempts, 2);
  assert.equal(ui.modal.hidden, true);
  assert.equal(ui.background.hasAttribute("inert"), false);
  assert.equal(ui.document.activeElement, ui.successFocus);
});
