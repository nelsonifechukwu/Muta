"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const lifecycle = require("../release-lifecycle.js");

test("Host roster actions use the canonical id-addressed endpoints", () => {
  assert.equal(
    lifecycle.hostUserEndpoint("learner/id", "remove"),
    "/v1/share/host/users/learner%2Fid",
  );
  assert.equal(
    lifecycle.hostUserEndpoint("learner/id", "approve"),
    "/v1/share/host/users/learner%2Fid/approve",
  );
  assert.equal(
    lifecycle.hostUserEndpoint("learner/id", "reject"),
    "/v1/share/host/users/learner%2Fid/reject",
  );
});

test("Safari visual viewport metrics keep the shell above browser chrome and keyboard", () => {
  const phone = lifecycle.viewportMetrics({
    innerWidth: 375,
    innerHeight: 844,
    visualViewport: { width: 375, height: 500, offsetTop: 47, offsetLeft: 0 },
  });
  assert.deepEqual(phone, {
    width: 375,
    height: 500,
    top: 47,
    left: 0,
    bottomGap: 297,
    compact: false,
    composerRegionMax: 70,
  });

  const landscapeKeyboard = lifecycle.viewportMetrics({
    innerWidth: 844,
    innerHeight: 390,
    visualViewport: { width: 760, height: 210, offsetTop: 0, offsetLeft: 42 },
  });
  assert.equal(landscapeKeyboard.compact, true);
  assert.equal(landscapeKeyboard.composerRegionMax, 40);
  assert.equal(landscapeKeyboard.left, 42);
});

test("streaming follows only near the tail and resumes at the bottom", () => {
  assert.equal(
    lifecycle.isNearBottom({ scrollHeight: 1000, scrollTop: 410, clientHeight: 500 }),
    true,
  );
  assert.equal(
    lifecycle.isNearBottom({ scrollHeight: 1000, scrollTop: 300, clientHeight: 500 }),
    false,
  );
  assert.equal(
    lifecycle.isNearBottom({ scrollHeight: 1000, scrollTop: 500, clientHeight: 500 }),
    true,
  );
});

test("only terminal failures with valid partial content offer Continue", () => {
  assert.deepEqual(lifecycle.terminalFailure({ failed: true }, "worked steps"), {
    failed: true,
    partial: true,
    recoverable: true,
  });
  assert.equal(lifecycle.terminalFailure({ error: "boom" }, "").recoverable, false);
  assert.equal(lifecycle.terminalFailure({}, "worked steps").recoverable, false);
});

test("Stop distinguishes accepted cancellation, an already-terminal job, and failure", () => {
  assert.equal(lifecycle.stopResponse(200, { stopping: true }), "accepted");
  assert.equal(lifecycle.stopResponse(200, { stopping: false }), "already-terminal");
  assert.equal(lifecycle.stopResponse(404, {}), "already-terminal");
  assert.equal(lifecycle.stopResponse(503, {}), "failed");
});
