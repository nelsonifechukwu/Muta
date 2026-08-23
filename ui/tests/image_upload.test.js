"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { interpret, request } = require("../image-upload.js");

test("accepts one stored image attachment without a transcription stage", () => {
  assert.deepEqual(interpret(true, {
    attachment_id: 7,
    kind: "image",
    mime: "image/jpeg",
    width: 601,
    height: 751,
  }), {
    status: "ready",
    attachmentId: 7,
    mime: "image/jpeg",
    width: 601,
    height: 751,
  });
});

test("treats transport, malformed JSON, and wrong shapes as upload failures", async () => {
  const transport = await request(async () => {
    throw new Error("offline");
  }, "/v1/attachments/images", {});
  const malformed = await request(async () => ({
    ok: true,
    json: async () => { throw new SyntaxError("not JSON"); },
  }), "/v1/attachments/images", {});
  const wrongShape = interpret(true, { accepted: true, transcription: "legacy" });

  for (const result of [transport, malformed, wrongShape]) {
    assert.deepEqual(result, {
      status: "failed",
      detailKey: "attachment.imageUploadFailed",
    });
  }
});

test("keeps an actionable HTTP error returned by the server", async () => {
  const result = await request(async () => ({
    ok: false,
    json: async () => ({ detail: "sign in to continue" }),
  }), "/v1/attachments/images", {});

  assert.deepEqual(result, { status: "failed", detail: "sign in to continue" });
});
