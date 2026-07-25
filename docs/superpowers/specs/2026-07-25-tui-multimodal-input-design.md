# Multimodal input for the TUI

**Date:** 2026-07-25
**Status:** approved, ready to implement
**Lane:** C (gateway) + Lane A (runtime vision client)

## Goal

Let a student attach an image (a photo of handwritten work) in the terminal TUI
(`bench/tui.py`) and have the tutor work from it. This closes the one remaining gap in the
vision path: the CORE-VISION *inference* call, currently stubbed as HTTP 501 in
`tutor_vision()`.

## Current state (what already works)

- **Image guard** — `orchestrator/gateway/images.py::prepare_image` (sniff, ≤8 MiB,
  JPEG/PNG/WebP, EXIF-transpose then strip, downscale longest side ≤1280). Tested.
- **CORE-VISION lifecycle** — `runtime/vision.py::VisionManager` (spawn / health-check /
  TTL-reap / ladder-deny), spawned via `runtime/profiles.py::core_vision_command`
  (`--mmproj`, port 8082). Tested.
- **The route** — `orchestrator/gateway/routes.py::tutor_vision` reads the upload, runs the
  guard, calls `vision.ensure()`, then **raises HTTP 501** ("mtmd completion call not wired").
- **The TUI** — `bench/tui.py::MutaTUI` is a text-only `/v1/chat/stream` client. No attach path.

The OpenAI image-content-array message shape (`content` as a list of `{type,...}` parts) exists
**nowhere** in the codebase; `runtime/client.py` types messages as `dict[str, str]`.

## Design decisions

- **Flow: transcribe → tutor.** CORE-VISION returns a transcription string; the resident text
  server does the tutoring. Matches the two-instance topology (D3) and `VisionReply.transcription`.
  Rejected: direct VQA (keeps mmproj in the conversation loop, off-topology).
- **Input: `/img <path> [question]`** slash command in the TUI input line. Explicit, terminal-native.
- **Front-end: `bench/tui.py` only.** The CLI REPL (`runtime/cli.py`) talks to `ChatEngine`
  in-process, not over HTTP; out of scope.
- **No contract change.** `/tutor/vision` already exists; like `/chat/stream` it is an internal
  (non-`/v1`-frozen) surface. `contracts/openapi.yaml` stays byte-identical.

## Components

### 1. `VisionClient` — `runtime/vision_client.py` (new)

The multimodal completion call, kept separate from the text `InferenceClient` because
CORE-VISION is a distinct, ephemeral server.

- `transcribe(image_bytes: bytes, image_format: str, *, prompt: str) -> str`
- Builds `messages=[{"role":"user","content":[{"type":"text","text":prompt},
  {"type":"image_url","image_url":{"url":"data:image/<fmt>;base64,<b64>"}}]}]`
- POSTs to `<base_url>/v1/chat/completions` (base_url from `VisionManager.base_url`), returns
  `choices[0].message.content`. No streaming (a short transcription; simplest).
- Raises `httpx.HTTPError` on transport failure — the caller turns it into a friendly refusal.
- A default transcription prompt lives here as a module constant (e.g. "Transcribe the
  handwritten math/work in this image exactly, as plain text/LaTeX. Do not solve it.").

### 2. `tutor_vision()` — `orchestrator/gateway/routes.py` (edit)

Replace the 501 body. After the existing guard + `vision.ensure()`:

```
try:
    text = VisionClient(vision.base_url).transcribe(prepared.data, prepared.format, prompt=...)
except httpx.HTTPError:
    return VisionReply(session_id=..., accepted=False,
                       detail="the vision reader didn't respond — type the problem and I'll help")
return VisionReply(session_id=..., transcription=text, accepted=True)
```

The two existing friendly refusals (`ImageRejected` → guard, `VisionDenied` → ladder) are
unchanged. `vision.touch()` is already handled inside `ensure()`.

### 3. TUI attach path — `bench/tui.py` (edit)

- **Pure parse helper** `parse_image_command(line) -> tuple[path, question] | None` (module-level,
  testable without Textual). Returns `None` when the line is not an `/img` command.
- `on_input_submitted`: if `parse_image_command` matches:
  - if file missing/unreadable → append a friendly `you`/`muta` note to the transcript, return.
  - else read bytes → `POST {base_url}/tutor/vision` (multipart: `session_id="tui"`,
    `image=(name, bytes, mime)`) in the existing async `@work` pattern.
  - if `accepted is False` → show `detail` in the transcript.
  - on success → append `read: <transcription>` to the transcript, then call the existing
    `_stream_reply("<transcription>\n\n<question>")` (question defaults to a "help me with this"
    string when omitted). Normal streaming + metrics + persistence follow unchanged.
- The attach round-trip reuses `self._busy` / disabled-input guarding so it can't overlap a
  stream.

## Data flow

```
/img page.jpg "what's wrong?"
  → TUI reads file
  → POST /tutor/vision (multipart)            [gateway]
      → prepare_image (guard)
      → vision.ensure()  (spawn CORE-VISION on :8082 if needed)
      → VisionClient.transcribe → CORE-VISION /v1/chat/completions (image+prompt)
      → VisionReply{transcription, accepted}
  → TUI shows "read: <transcription>"
  → _stream_reply(transcription + question)
      → POST /v1/chat/stream                  [resident text server, unchanged]
      → tokens stream into transcript, metrics panel updates
```

## Error handling

| Failure | Handling |
|---|---|
| File not found / unreadable (TUI) | Friendly transcript note, no request sent |
| Image too big / wrong format | `prepare_image` → `ImageRejected` → `accepted=False`, `detail` shown |
| Memory pressure (ladder) | `vision.ensure()` → `VisionDenied` → `accepted=False`, `detail` shown |
| CORE-VISION unreachable / errors | `VisionClient` raises `httpx.HTTPError` → `accepted=False`, friendly detail |
| Empty transcription | Returned as `accepted=True, transcription=""`; TUI still forwards the question |

## Testing

- `VisionClient.transcribe`: mock httpx transport, assert the content-array payload shape
  (data-URI prefix, base64 body, prompt text) and that it returns `choices[0].message.content`.
- `tutor_vision`: route test with a mocked `VisionManager` + `VisionClient` — success path,
  `ImageRejected` path, `VisionDenied` path, `httpx.HTTPError` path. All return 200 with the
  right `accepted`/`detail`/`transcription`.
- `parse_image_command`: pure-function tests — `/img p.jpg q` → `("p.jpg","q")`,
  `/img p.jpg` → `("p.jpg", None)`, non-command → `None`, quoted paths with spaces.
- Adversarial review (another lane) on the route + client before done, per the working method.

## Out of scope (YAGNI)

- Contract / `openapi.yaml` changes.
- Video → frames (the `ffmpeg_frames_command` already exists; not wired to the TUI).
- The CLI REPL (`runtime/cli.py`).
- Direct VQA / image-in-chat-history.
- Fixing the F16-mmproj 3.41 GiB-over-3.3-cap RAM deviation (#5) — vision is ephemeral/TTL-reaped;
  this build makes it functional, not RAM-clean. Noted, not addressed here.
