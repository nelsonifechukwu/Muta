/* Pure image-upload response handling, kept executable in both the browser and Node tests. */
"use strict";

((global) => {
  const uploadFailure = () => ({ status: "failed", detailKey: "attachment.imageUploadFailed" });

  function interpret(httpOk, body) {
    if (!httpOk) {
      return typeof body?.detail === "string" && body.detail
        ? { status: "failed", detail: body.detail }
        : uploadFailure();
    }
    if (!body || typeof body !== "object" || typeof body.accepted !== "boolean") {
      return uploadFailure();
    }
    const attachmentId = body.attachment_id ?? null;
    if (body.accepted && typeof body.transcription === "string" && body.transcription) {
      return { status: "ready", attachmentId, transcription: body.transcription };
    }
    if (body.accepted) {
      return { status: "failed", attachmentId, detailKey: "attachment.photoEmpty" };
    }
    return typeof body.detail === "string" && body.detail
      ? { status: "failed", attachmentId, detail: body.detail }
      : { status: "failed", attachmentId, detailKey: "attachment.imageUnreadable" };
  }

  async function request(fetchImpl, url, options) {
    try {
      const response = await fetchImpl(url, options);
      let body;
      try {
        body = await response.json();
      } catch {
        return uploadFailure();
      }
      return interpret(response.ok, body);
    } catch {
      return uploadFailure();
    }
  }

  const api = { interpret, request };
  global.MutaVisionUpload = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
