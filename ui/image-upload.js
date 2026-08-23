/* Pure attachment-upload response handling, executable in both browser and Node tests. */
"use strict";

((global) => {
  const uploadFailure = () => ({ status: "failed", detailKey: "attachment.imageUploadFailed" });

  function interpret(httpOk, body) {
    if (!httpOk) {
      return typeof body?.detail === "string" && body.detail
        ? { status: "failed", detail: body.detail }
        : uploadFailure();
    }
    if (
      !body
      || typeof body !== "object"
      || !Number.isInteger(body.attachment_id)
      || typeof body.mime !== "string"
      || !body.mime.startsWith("image/")
    ) {
      return uploadFailure();
    }
    return {
      status: "ready",
      attachmentId: body.attachment_id,
      mime: body.mime,
      width: Number(body.width) || 0,
      height: Number(body.height) || 0,
    };
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
  global.MutaImageUpload = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
