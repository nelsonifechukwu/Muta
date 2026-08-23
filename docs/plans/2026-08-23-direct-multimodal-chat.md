# Direct multimodal chat

**Date:** 2026-08-23
**Status:** ready for user review; local review branch only

## Problem

The browser currently sends an image to `/v1/tutor/vision` as soon as it is selected. That
route starts a separate Qwen3.5-4B CORE-VISION process, asks it to transcribe the image, and
later inserts the transcription into a text-only chat request. This is not the interaction the
composer presents: the thumbnail appears beside the question, but the selected tutor model
never receives the image.

The eager reader also owns a long-running auxiliary slot while the learner is still composing.
`POST /v1/models/select` refuses to reconfigure while that slot is active, so a slow or timed-out
read produces an apparently unrelated `409 Conflict` and the UI hides the useful server detail
behind “Model switch failed.”

## Decision

Images are attachments, not preprocessing jobs:

1. Selecting an image validates, normalises and stores it, then leaves a stable preview in the
   composer. It performs no model inference.
2. Sending the turn loads the learner-owned image bytes and places them with the learner's text
   in the selected model's OpenAI-compatible content array.
3. A model advertises image input only when its exact, hash-verified projector is installed and
   loaded. Text-only models remain selectable but reject image turns before any generation is
   reserved, with a recovery instruction naming the required action.
4. Qwen3.5-0.8B uses its own paired F16 projector. The old Qwen3.5-4B projector is not reused:
   projector/model pairing is part of the catalog's integrity boundary.
5. The user-visible model switch error preserves safe `409` detail. Since selection no longer
   runs CORE-VISION, an attached preview cannot hold the model-switch lifecycle open.

The legacy `/v1/tutor/vision` route remains as an upload-compatible alias for older clients, but
it no longer starts a reader or returns a transcription. New browser code uses
`POST /v1/attachments/images`.

## Invariants

- The prepared image is JPEG/PNG/WebP, at most 8 MiB on intake, no more than 20 megapixels or
  8192 px on either source dimension, EXIF-stripped and no larger than 1280 px on its longest
  side before storage or inference. At most two full-raster decode/resize jobs run concurrently.
- Attachment ownership is checked before image bytes enter a prompt. Unknown, cross-owner and
  non-image ids do not reach the model.
- A turn contains at most one image on the constrained CPU target. The gateway rejects a larger
  image set before capacity admission.
- The persisted learner message remains the exact typed text. Binary data URIs exist only in the
  in-memory request to loopback `llama-server` and are never written to conversation text or logs.
- An image-only turn is valid. The guarded image stays linked to its original user message and is
  replayed at that original position for follow-up turns and explicit regeneration; binary data
  still never enters the persisted message text.
- The user row and every attachment link commit in one transaction before inference. A failed or
  reused attachment id rolls the user row back, returns a safe retry message and starts no model
  request.
- The engine encodes an image within a validated 1024–2048 visual-token range. ChatEngine reserves
  the 2048-token ceiling (including when exact text counting is available), and every two-lane
  Compose profile supplies at least 4096 context tokens per lane so the real tutor prompt still
  leaves a useful reply budget.
- No push, merge to `main`, GCP change, or deployment occurs before user review.

## Work

1. Extend the catalog and runtime configuration with a verified per-model projector and exposed
   image-input capability; launch capable models with `--mmproj` and CPU-safe projector flags.
2. Add the upload-only image endpoint and a single attachment-resolution boundary shared by
   blocking and durable-stream chat paths.
3. Teach `ChatEngine` and `InferenceClient` to carry text/image content arrays without changing
   persisted message text, context fitting, cancellation or continuation semantics.
4. Replace the eager reader UI state with upload/ready state, keep the preview in the sent
   message, gate image selection by the active model, and show the exact model-switch recovery
   message.
5. Provision the pinned Qwen3.5-0.8B projector alongside the recommended model and document the
   capability distinction in the local model-selection guide.
6. Test upload guards and ownership, exact request payloads, unsupported models, regeneration,
   stream recovery, switch conflicts, UI response classification, keyboard/accessibility states,
   and the real `african billionaires.jpg` through a local Qwen3.5-0.8B + projector smoke.
7. Run the full Python and browser/Node suites, then obtain the required fresh adversarial review.

## Acceptance

- Selecting `african billionaires.jpg` finishes quickly with a stable thumbnail and starts no
  CORE-VISION process.
- Sending a question with that thumbnail produces one selected-model request whose current user
  content contains both the text and a guarded `data:image/...;base64,...` image part.
- A text-only active model returns a specific `409` before generation; the UI retains the draft
  and explains that an image-capable model must be selected.
- Model switching succeeds after image upload and reports a specific cause/recovery when another
  real generation prevents a transition.
- Full tests pass, related changes are grouped into local commits on
  `muta-multi-modal-inputs-v2`, and the branch is left unpushed for review.

## Verification

- Full Python suite: **1160 passed, 69 skipped, 1 deselected**. The skipped group is the
  Postgres-backed store suite because the local Docker daemon/Postgres service was unavailable;
  the portable SQLite store, transactional link, replay and concurrency regressions ran green.
- Browser-client Node suite: **68/68 passed**. Authored and `ui/dist` JS/CSS/i18n copies are
  byte-identical.
- Contract regenerated successfully; `docker compose config --quiet`, shell syntax checks and
  `git diff --check` pass.
- Real pinned b10035 smoke with `african billionaires.jpg`, Qwen3.5-0.8B Q4_0 and its verified
  projector returned the top-left card's **$28.5 billion** value, then answered **Nigeria** on a
  text-only follow-up without re-uploading. Engine logs showed the image request remained inside
  the 4096-token lane without truncation.
- Fresh adversarial review reports no remaining actionable or release-blocking findings. Its
  pinned exact-token measurement leaves **771 reply tokens** after the representative tutor
  prompt, 2048-token visual ceiling and 192-token safety reserve.
- Repository-wide Ruff remains a known pre-existing non-green gate (the changed-file set reports
  76 legacy findings, chiefly FastAPI dependency defaults); this change adds no claim that the
  existing lint baseline is clean.
