"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const startup = require("../startup.js");

test("startup snapshots are monotonic and cannot announce readiness below 100", () => {
  const first = startup.normalizeSnapshot({ percent: 52, stage: "startup.startingGateway" });
  const stale = startup.normalizeSnapshot({ percent: 14, stage: "startup.verifying" }, first);
  assert.equal(stale.percent, 52);
  assert.equal(stale.ready, false);
  const ready = startup.normalizeSnapshot({ percent: 80, ready: true }, stale);
  assert.equal(ready.ready, true);
  assert.equal(ready.percent, 100);
});

test("browser milestones distinguish cold, warm, and failed startup", () => {
  assert.deepEqual(startup.browserSnapshot({ ready: false, checks: { gateway: true, db: false, inference: false } }, 0), {
    percent: 72, stage: "startup.openingData", ready: false, failed: false, retryable: false,
  });
  assert.equal(startup.browserSnapshot({ ready: false, checks: { gateway: true, db: true, inference: false } }, 0).percent, 82);
  assert.equal(startup.browserSnapshot({ ready: true, checks: { gateway: true, db: true, inference: true } }, 0).percent, 100);
  const failed = startup.failureSnapshot({ ...startup.START, percent: 72 }, 3);
  assert.equal(failed.failed, true);
  assert.equal(failed.retryable, true);
  assert.notEqual(failed.stage, "startup.ready");
});

test("the startup runtime exposes only a monotonic state transition API", () => {
  const source = require("node:fs").readFileSync(require.resolve("../startup.js"), "utf8");
  assert.match(source, /muta:startupchange/);
  assert.match(source, /detail: \{ \.\.\.current \}/);
});
