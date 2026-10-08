"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  assignedConversationStyle,
  canApplyServerStyle,
  nextRepairVersion,
} = require("../teaching-style-policy.js");

test("a stale conversation GET cannot replace an unresolved local style intent", () => {
  assert.equal(canApplyServerStyle({
    currentVersion: 0,
    versionAtStart: 0,
    persistedVersionAtStart: 0,
  }), true);
  assert.equal(canApplyServerStyle({
    currentVersion: 1,
    versionAtStart: 0,
    persistedVersionAtStart: 0,
  }), false, "GET started before the click");
  assert.equal(canApplyServerStyle({
    currentVersion: 1,
    versionAtStart: 1,
    persistedVersionAtStart: 0,
  }), false, "GET started while the PUT was unresolved");
  assert.equal(canApplyServerStyle({
    currentVersion: 1,
    versionAtStart: 1,
    persistedVersionAtStart: 1,
  }), true, "GET started after the PUT committed");
});

test("a style chosen while a new-chat POST is pending follows the assigned conversation id", () => {
  assert.deepEqual(assignedConversationStyle("socratic", "hints"), {
    mode: "hints",
    needsConversationWrite: true,
  });
  assert.deepEqual(assignedConversationStyle("analogy", "analogy"), {
    mode: "analogy",
    needsConversationWrite: false,
  });
});

test("a reconciliation repair always advances beyond an already-persisted version", () => {
  assert.equal(nextRepairVersion(undefined), 1);
  assert.equal(nextRepairVersion(0), 1);
  assert.equal(nextRepairVersion(1), 2);
  assert.equal(nextRepairVersion(9), 10);
});
