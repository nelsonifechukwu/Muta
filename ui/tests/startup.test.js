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

test("browser milestones distinguish gateway, database, and engine readiness", () => {
  assert.deepEqual(startup.browserSnapshot({ ready: false, checks: { gateway: true, db: false, inference: false } }, 0), {
    percent: 72, stage: "startup.openingData", ready: false, failed: false, retryable: false,
  });
  assert.equal(startup.browserSnapshot({ ready: false, checks: { gateway: true, db: true, inference: false } }, 0).percent, 82);
  assert.equal(startup.browserSnapshot({ ready: true, checks: { gateway: true, db: true, inference: true } }, 0).percent, 100);
  const failed = startup.failureSnapshot({ ...startup.START, percent: 72 }, 3);
  assert.equal(failed.failed, true);
  assert.equal(failed.retryable, true);
  assert.equal(failed.stage, "startup.connecting");
});

test("localhost readiness succeeds when the retained Tauri command rejects", async () => {
  let fetches = 0;
  const result = await startup.resolveStartupSnapshot({
    invoke: async () => {
      throw new Error("startup_snapshot is not allowed on this origin");
    },
    fetchReady: async () => {
      fetches += 1;
      return {
        ok: true,
        json: async () => ({
          ready: true,
          checks: { gateway: true, db: true, inference: true },
        }),
      };
    },
  });

  assert.equal(fetches, 1);
  assert.equal(result.snapshot.ready, true);
  assert.equal(result.snapshot.percent, 100);
  assert.equal(result.transport, "http");
  assert.match(result.tauriError.message, /not allowed/);
});

test("a terminal desktop snapshot remains authoritative and does not use HTTP", async () => {
  const result = await startup.resolveStartupSnapshot({
    invoke: async () => ({
      percent: 38,
      stage: "startup.verifying",
      failed: true,
      retryable: true,
    }),
    fetchReady: async () => assert.fail("HTTP fallback must not mask a real desktop failure"),
  });

  assert.equal(result.transport, "tauri");
  assert.equal(result.snapshot.stage, "startup.verifying");
  assert.equal(result.snapshot.failed, true);
});

test("retryable transport failure recovers as soon as HTTP readiness is healthy", async () => {
  let healthy = false;
  const fetchReady = async () => {
    if (!healthy) throw new Error("backend child unavailable");
    return {
      ok: true,
      json: async () => ({
        ready: true,
        checks: { gateway: true, db: true, inference: true },
      }),
    };
  };

  await assert.rejects(
    startup.resolveStartupSnapshot({ fetchReady }),
    /backend child unavailable/,
  );
  healthy = true;
  const recovered = await startup.resolveStartupSnapshot({ fetchReady });
  assert.equal(recovered.snapshot.ready, true);
});

test("the startup runtime exposes only a monotonic state transition API", () => {
  const source = require("node:fs").readFileSync(require.resolve("../startup.js"), "utf8");
  assert.match(source, /muta:startupchange/);
  assert.match(source, /detail: \{ \.\.\.current \}/);
});
