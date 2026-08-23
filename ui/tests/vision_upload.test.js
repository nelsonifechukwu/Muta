"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { interpret, request } = require("../vision-upload.js");

test("classifies accepted, empty, and refused image-reader replies", () => {
  assert.deepEqual(interpret(true, {
    accepted: true,
    attachment_id: 7,
    transcription: "x² = 9",
  }), {
    status: "ready",
    attachmentId: 7,
    transcription: "x² = 9",
  });
  assert.deepEqual(interpret(true, { accepted: true, transcription: "" }), {
    status: "failed",
    attachmentId: null,
    detailKey: "attachment.photoEmpty",
  });
  assert.deepEqual(interpret(true, { accepted: false, detail: "try again shortly" }), {
    status: "failed",
    attachmentId: null,
    detail: "try again shortly",
  });
});

test("treats transport and malformed successful responses as upload failures", async () => {
  const transport = await request(async () => {
    throw new Error("offline");
  }, "/v1/tutor/vision", {});
  const malformed = await request(async () => ({
    ok: true,
    json: async () => { throw new SyntaxError("not JSON"); },
  }), "/v1/tutor/vision", {});
  const wrongShape = interpret(true, { detail: "not a vision reply" });

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
  }), "/v1/tutor/vision", {});

  assert.deepEqual(result, { status: "failed", detail: "sign in to continue" });
});
