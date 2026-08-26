"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const policy = require("../parallel-policy.js");

test("parallel mode dispatches another chat while serial mode queues it", () => {
  assert.equal(
    policy.sendAction({ allowParallelChats: true, activeJobs: 1, hasConversation: true }),
    "dispatch",
  );
  assert.equal(
    policy.sendAction({ allowParallelChats: false, activeJobs: 1, hasConversation: true }),
    "queue",
  );
});

test("serial mode includes starts awaiting admission and drains only when idle", () => {
  const starting = { allowParallelChats: false, startingJobs: 1 };
  assert.equal(policy.sendAction({ ...starting, hasConversation: true }), "queue");
  assert.equal(policy.canDrain(starting), false);
  assert.equal(policy.canDrain({ allowParallelChats: false }), true);
});

test("a blank chat keeps its draft when it cannot yet receive a durable queue id", () => {
  assert.equal(
    policy.sendAction({ allowParallelChats: false, activeJobs: 1, hasConversation: false }),
    "restore",
  );
});

test("enabling parallel mode releases every queued conversation once", () => {
  const queue = [{ cid: "algebra" }, { cid: "geometry" }, { cid: "algebra" }];
  assert.equal(
    policy.sendAction({ allowParallelChats: false, activeJobs: 1, hasConversation: true }),
    "queue",
  );
  assert.equal(
    policy.sendAction({ allowParallelChats: true, activeJobs: 1, hasConversation: true }),
    "dispatch",
  );
  assert.deepEqual(policy.queuedConversationIds(queue), ["algebra", "geometry"]);
});
