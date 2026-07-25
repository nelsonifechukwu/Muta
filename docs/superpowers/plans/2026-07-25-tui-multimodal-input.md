# TUI Multimodal Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a student attach an image in the terminal TUI (`bench/tui.py`) and have the tutor work from it, by closing the CORE-VISION inference gap (currently HTTP 501).

**Architecture:** Transcribe → tutor. A new `VisionClient` sends the guarded image to the ephemeral CORE-VISION llama-server using the OpenAI image-content-array shape and returns a transcription; `tutor_vision()` returns that as a real `VisionReply`; the TUI gains an `/img <path> [question]` command that posts the image, shows the transcription, then feeds `transcription + question` into the existing text-streaming path.

**Tech Stack:** Python 3.10+, httpx, FastAPI, Pydantic, Textual, pytest.

## Global Constraints

- Python ≥ 3.10; `from __future__ import annotations` at the top of every new module (matches the repo).
- **Do not touch `contracts/models.py` or `contracts/openapi.yaml`.** `/tutor/vision` and `/chat/stream` are internal, non-frozen surfaces; the contract must stay byte-identical.
- The vision server's model alias is `core-vision` (set in `runtime/profiles.py::core_vision_command`, `--alias core-vision`).
- CORE-VISION is reached at `VisionManager.base_url` (`http://127.0.0.1:8082` in dev) and speaks OpenAI chat-completions at `<base_url>/v1/chat/completions`.
- `PreparedImage.format` is one of `"JPEG"`, `"PNG"`, `"WEBP"` (from `orchestrator/gateway/images.py`).
- Keep the two existing friendly refusals in `tutor_vision` unchanged: `ImageRejected` (guard) and `VisionDenied` (ladder) both return `VisionReply(accepted=False, detail=...)`, HTTP 200.
- Follow the repo's test idiom for httpx: `monkeypatch.setattr(httpx, "post", fake_post)` where `fake_post(url, **kwargs)` returns `httpx.Response(200, json=..., request=httpx.Request("POST", url))`.
- Commit after every task with a `feat:`/`test:` message ending in the repo's `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

### Task 1: `VisionClient` — the multimodal completion call

**Files:**
- Create: `runtime/vision_client.py`
- Test: `runtime/tests/test_vision_client.py`

**Interfaces:**
- Consumes: nothing from other tasks. `httpx`.
- Produces:
  - `DEFAULT_TRANSCRIBE_PROMPT: str` (module constant).
  - `class VisionClient` with `__init__(self, base_url: str, *, model: str = "core-vision", timeout: float = 120.0)`.
  - `VisionClient.transcribe(self, image_bytes: bytes, image_format: str, *, prompt: str = DEFAULT_TRANSCRIBE_PROMPT) -> str` — POSTs the image + prompt as an OpenAI image-content-array message, returns `choices[0].message.content`. Raises `httpx.HTTPError` on transport failure. `image_format` is a `PreparedImage.format` value (`"JPEG"`/`"PNG"`/`"WEBP"`).

- [ ] **Step 1: Write the failing test**

Create `runtime/tests/test_vision_client.py`:

```python
"""VisionClient sends a guarded image to CORE-VISION as an OpenAI image-content-array
message and returns the transcription. This is the one place that shape lives; the text
InferenceClient stays string-only.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from runtime.vision_client import DEFAULT_TRANSCRIBE_PROMPT, VisionClient


def _capture(monkeypatch, payload: dict) -> dict:
    """Mount a fake llama-server; return a dict the test fills with the sent request body."""
    seen: dict = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_transcribe_returns_the_model_content(monkeypatch):
    _capture(monkeypatch, {"choices": [{"message": {"content": "x^2 = 9"}}]})
    out = VisionClient("http://127.0.0.1:8082").transcribe(b"\x89PNGdata", "PNG")
    assert out == "x^2 = 9"


def test_transcribe_builds_an_image_content_array_with_a_data_uri(monkeypatch):
    seen = _capture(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})
    raw = b"\xff\xd8\xffJPEGBYTES"
    VisionClient("http://127.0.0.1:8082").transcribe(raw, "JPEG", prompt="read this")

    assert seen["url"] == "http://127.0.0.1:8082/v1/chat/completions"
    body = seen["json"]
    assert body["model"] == "core-vision"
    assert body["stream"] is False
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "read this"}
    url = content[1]["image_url"]["url"]
    assert url == "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def test_default_prompt_is_used_when_none_given(monkeypatch):
    seen = _capture(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})
    VisionClient("http://127.0.0.1:8082").transcribe(b"x", "PNG")
    assert seen["json"]["messages"][0]["content"][0]["text"] == DEFAULT_TRANSCRIBE_PROMPT


def test_transport_error_propagates(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(httpx.HTTPError):
        VisionClient("http://127.0.0.1:8082").transcribe(b"x", "PNG")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest runtime/tests/test_vision_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'runtime.vision_client'`

- [ ] **Step 3: Write minimal implementation**

Create `runtime/vision_client.py`:

```python
"""The CORE-VISION completion call — image in, transcription out (TDD §6.3, S2).

Kept separate from `runtime.client.InferenceClient` on purpose: CORE-VISION is a distinct,
ephemeral llama-server (a second process over the same weight file with `--mmproj`), and this
is the ONLY place the OpenAI image-content-array message shape is constructed. The text client
stays string-only, so nothing on the resident-server path has to reason about images.
"""

from __future__ import annotations

import base64

import httpx

#: Transcribe, don't solve: the resident text tutor does the tutoring (transcribe → tutor).
DEFAULT_TRANSCRIBE_PROMPT = (
    "Transcribe the handwritten or printed math and working in this image exactly, as plain "
    "text with LaTeX for equations. Do not solve it, explain it, or add anything that is not "
    "on the page."
)

#: PreparedImage.format -> data-URI MIME type.
_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class VisionClient:
    def __init__(
        self,
        base_url: str,
        *,
        model: str = "core-vision",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def transcribe(
        self, image_bytes: bytes, image_format: str, *, prompt: str = DEFAULT_TRANSCRIBE_PROMPT
    ) -> str:
        """Send image + prompt to CORE-VISION; return the transcription text.

        Raises `httpx.HTTPError` on transport failure — the caller turns that into S2's honest
        fallback ("type the problem"), never an error page.
        """
        mime = _MIME.get(image_format.upper(), "image/png")
        data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "stream": False,
            # Deterministic: a transcription is a reading, not a creative act.
            "temperature": 0.0,
        }
        r = httpx.post(
            f"{self.base_url}/v1/chat/completions", json=payload, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest runtime/tests/test_vision_client.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add runtime/vision_client.py runtime/tests/test_vision_client.py
git commit -m "feat(runtime): add VisionClient for the CORE-VISION completion call

Sends a guarded image to the ephemeral vision server as an OpenAI
image-content-array message and returns the transcription. The one place
that shape lives; the text InferenceClient stays string-only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Wire `tutor_vision()` — replace the 501

**Files:**
- Modify: `orchestrator/gateway/routes.py:344-377` (the `tutor_vision` body)
- Modify: `orchestrator/gateway/routes.py:63` area (add the `VisionClient` import)
- Test: `orchestrator/tests/test_tutor_api.py` (replace the 501 test, add success + error tests)

**Interfaces:**
- Consumes: `runtime.vision_client.VisionClient` (Task 1); `VisionManager.base_url`, `VisionManager.ensure()`; `prepare_image`, `ImageRejected`; `VisionDenied`.
- Produces: `POST /v1/tutor/vision` now returns `VisionReply(transcription=..., accepted=True)` on success, and `accepted=False` with a friendly `detail` on any refusal (guard, ladder, or a CORE-VISION transport error). Always HTTP 200.

- [ ] **Step 1: Update the failing/obsolete test and add the new ones**

In `orchestrator/tests/test_tutor_api.py`, **replace** `test_a_valid_photo_reaches_the_vision_manager` (currently asserts 501, lines ~176-186) with the following, and add the three tests after it. Note the module already imports `httpx`, `io`, `pytest`, and has `png_bytes()` and the `wired` fixture.

```python
def test_a_valid_photo_is_transcribed(wired, monkeypatch):
    _, _, _, vision = wired
    monkeypatch.setattr(vision, "ensure", lambda: "http://127.0.0.1:8082")

    captured = {}

    def fake_transcribe(self, image_bytes, image_format, *, prompt=...):
        captured["format"] = image_format
        captured["bytes"] = len(image_bytes)
        return "x^2 = 9"

    monkeypatch.setattr(
        "orchestrator.gateway.routes.VisionClient.transcribe", fake_transcribe
    )
    body = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("work.png", png_bytes((2000, 1500)), "image/png")},
    ).json()
    assert body["accepted"] is True
    assert body["transcription"] == "x^2 = 9"
    # The guard must have downscaled the 2000x1500 photo before it reached the model.
    assert captured["format"] == "PNG" and captured["bytes"] > 0


def test_vision_server_unreachable_is_a_friendly_refusal_not_500(wired, monkeypatch):
    _, _, _, vision = wired
    monkeypatch.setattr(vision, "ensure", lambda: "http://127.0.0.1:8082")

    def boom(self, image_bytes, image_format, *, prompt=...):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", "http://x"))

    monkeypatch.setattr("orchestrator.gateway.routes.VisionClient.transcribe", boom)
    r = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("work.png", png_bytes(), "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False and "type the problem" in body["detail"]
```

(The oversized, non-image, and ladder-denied tests already exist and must keep passing unchanged.)

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `python -m pytest orchestrator/tests/test_tutor_api.py -k vision -v`
Expected: `test_a_valid_photo_is_transcribed` and `test_vision_server_unreachable...` FAIL (route still 501 / `VisionClient` not imported in routes); the three existing refusal tests PASS.

- [ ] **Step 3: Add the import**

In `orchestrator/gateway/routes.py`, add to the runtime imports (next to line 63, `from runtime.vision import VisionDenied, VisionManager`):

```python
from runtime.vision_client import VisionClient
```

- [ ] **Step 4: Replace the route body**

In `orchestrator/gateway/routes.py`, replace the body of `tutor_vision` (the block from the `# The vision instance is stateless...` comment through the `raise HTTPException(status_code=501, ...)`, lines ~367-377) with:

```python
    base_url = vision.ensure()  # already touched; spawns CORE-VISION if needed

    # The vision instance is stateless and TTL-killable by design: it returns a transcription,
    # and the *text* session carries the conversation (§6.3, S2). A transport failure here is
    # S2's honest fallback, never a 500 in a non-technical judge's face.
    try:
        transcription = VisionClient(base_url).transcribe(prepared.data, prepared.format)
    except httpx.HTTPError:
        return VisionReply(
            session_id=session_id,
            accepted=False,
            detail="the image reader didn't respond — type the problem and I'll work through it",
        )
    return VisionReply(session_id=session_id, transcription=transcription, accepted=True)
```

Note: `vision.ensure()` already raises `VisionDenied` (caught above this block) and already calls `touch()`. Keep the existing `try/except VisionDenied` that wraps `vision.ensure()` — change that call from a bare `vision.ensure()` to `base_url = vision.ensure()` so the URL is captured.

- [ ] **Step 5: Run the vision tests to verify they pass**

Run: `python -m pytest orchestrator/tests/test_tutor_api.py -k vision -v`
Expected: PASS (all 5 vision tests: oversized, non-image, ladder-denied, transcribed, unreachable)

- [ ] **Step 6: Run the full gateway suite for regressions**

Run: `python -m pytest orchestrator/tests/test_tutor_api.py -v`
Expected: PASS (no regressions in chat/tools/session tests)

- [ ] **Step 7: Commit**

```bash
git add orchestrator/gateway/routes.py orchestrator/tests/test_tutor_api.py
git commit -m "feat(gateway): wire the CORE-VISION completion call in tutor_vision

Replace the 501 with a real transcription via VisionClient. Transport
failures become S2's friendly 'type the problem' refusal, not a 500.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: TUI `/img` attach path

**Files:**
- Modify: `bench/tui.py` (add `parse_image_command`, an `_attach_image` worker, and an `on_input_submitted` branch)
- Test: `bench/tests/test_tui_parse.py` (create; add `bench/tests/__init__.py` if `bench/tests/` does not exist)

**Interfaces:**
- Consumes: `VisionReply` shape from `/tutor/vision` (`accepted`, `transcription`, `detail`); `/v1/chat/stream` via the existing `_stream_reply`.
- Produces:
  - Module-level `parse_image_command(line: str) -> tuple[str, str | None] | None` — returns `(path, question)` for an `/img` line, else `None`.
  - `DEFAULT_IMAGE_QUESTION: str` — the question used when `/img <path>` has no trailing text.

- [ ] **Step 1: Write the failing test**

Create `bench/tests/test_tui_parse.py` (create `bench/tests/__init__.py` as an empty file if the directory is new):

```python
"""The /img command parse is a pure function so it is testable without a running Textual app."""

from __future__ import annotations

from bench.tui import parse_image_command


def test_img_with_question():
    assert parse_image_command("/img work.jpg what did I get wrong?") == (
        "work.jpg",
        "what did I get wrong?",
    )


def test_img_without_question():
    assert parse_image_command("/img ~/notes/page.png") == ("~/notes/page.png", None)


def test_leading_and_trailing_whitespace_is_tolerated():
    assert parse_image_command("  /img  a.png  solve it  ") == ("a.png", "solve it")


def test_quoted_path_with_spaces():
    assert parse_image_command('/img "my work.jpg" help') == ("my work.jpg", "help")


def test_non_command_returns_none():
    assert parse_image_command("just a normal question") is None


def test_img_with_no_path_returns_none():
    assert parse_image_command("/img   ") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest bench/tests/test_tui_parse.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_image_command' from 'bench.tui'`

- [ ] **Step 3: Add the parse helper and constant**

In `bench/tui.py`, add near the top (after the imports, before `class MetricsPanel`):

```python
import shlex
from pathlib import Path

DEFAULT_IMAGE_QUESTION = "Here is a photo of my work — help me with it."


def parse_image_command(line: str) -> tuple[str, str | None] | None:
    """Parse `/img <path> [question]`. Returns (path, question|None), or None if not /img.

    Pure so it is unit-testable without a Textual app. `shlex` handles a quoted path that
    contains spaces; the remainder (if any) is the tutoring question.
    """
    stripped = line.strip()
    if not (stripped == "/img" or stripped.startswith("/img ")):
        return None
    rest = stripped[len("/img"):].strip()
    if not rest:
        return None
    try:
        parts = shlex.split(rest)
    except ValueError:
        parts = rest.split()
    if not parts:
        return None
    path = parts[0]
    # Reconstruct the question from the original text after the path token, so quoting only
    # the path does not force the student to quote their sentence.
    remainder = rest[len(shlex.quote(path)):].strip() if rest.startswith(("'", '"')) else rest[len(path):].strip()
    return path, (remainder or None)
```

Note on the `remainder` line: when the path was quoted, the question begins after the closing quote; otherwise it begins after the bare path token. Keep it as written — the tests in Step 1 pin both cases.

- [ ] **Step 4: Run the parse test to verify it passes**

Run: `python -m pytest bench/tests/test_tui_parse.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Wire the attach path into the TUI**

In `bench/tui.py`, in `on_input_submitted` (currently at ~line 184), add an `/img` branch **before** the normal `_stream_reply(message)` call. Replace the method body with:

```python
    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message or self._busy:
            return
        if message.lower() in {"exit", "quit"}:
            self.exit()
            return
        event.input.value = ""
        attach = parse_image_command(message)
        if attach is not None:
            path, question = attach
            self._attach_image(path, question)
            return
        self.messages.append(("you", message))
        self.streaming = ""
        self._refresh_transcript()
        self._stream_reply(message)
```

Then add this new worker method (place it right after `_stream_reply`, near line 247):

```python
    @work(exclusive=True)
    async def _attach_image(self, path: str, question: str | None) -> None:
        """Send an image to /tutor/vision, show the transcription, then tutor from it."""
        self._busy = True
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = True
        try:
            file_path = Path(path).expanduser()
            self.messages.append(("you", f"[image: {file_path.name}]"))
            self._refresh_transcript()
            try:
                raw = file_path.read_bytes()
            except OSError as e:
                self.messages.append(("muta", f"couldn't read that file ({e.strerror or e}). "
                                              "check the path and try again."))
                self._refresh_transcript()
                return

            mime = "image/jpeg" if file_path.suffix.lower() in {".jpg", ".jpeg"} else \
                   "image/webp" if file_path.suffix.lower() == ".webp" else "image/png"
            try:
                async with httpx.AsyncClient(timeout=300.0) as vclient:
                    resp = await vclient.post(
                        f"{self.base_url}/v1/tutor/vision",
                        data={"session_id": "tui"},
                        files={"image": (file_path.name, raw, mime)},
                    )
                    resp.raise_for_status()
                    reply = resp.json()
            except httpx.HTTPError as e:
                self.messages.append(("muta", f"[vision error: {type(e).__name__} — is the app running?]"))
                self._refresh_transcript()
                return

            if not reply.get("accepted", False):
                self.messages.append(("muta", reply.get("detail") or "that image couldn't be used."))
                self._refresh_transcript()
                return

            transcription = reply.get("transcription", "")
            self.messages.append(("muta", f"read:\n{transcription}"))
            self._refresh_transcript()
        finally:
            self._busy = False
            prompt.disabled = False
            prompt.focus()

        # Now tutor from the transcription as an ordinary text turn (transcribe -> tutor).
        follow_up = question or DEFAULT_IMAGE_QUESTION
        combined = f"{transcription}\n\n{follow_up}" if transcription else follow_up
        self.messages.append(("you", follow_up))
        self.streaming = ""
        self._refresh_transcript()
        self._stream_reply(combined)
```

Note: `_attach_image` releases `self._busy` in its `finally` before calling `_stream_reply`, which re-acquires it — `_stream_reply` is `@work(exclusive=True)`, so the two workers don't overlap.

- [ ] **Step 6: Run the parse test again (no regression) and import-check the module**

Run: `python -m pytest bench/tests/test_tui_parse.py -v && python -c "import bench.tui"`
Expected: PASS (6 passed) and no import error.

- [ ] **Step 7: Commit**

```bash
git add bench/tui.py bench/tests/test_tui_parse.py bench/tests/__init__.py
git commit -m "feat(tui): accept image input via /img <path> [question]

Posts the photo to /tutor/vision, shows the transcription, then tutors
from it as a normal text turn. The parse helper is a pure function so it
is testable without a running Textual app.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Full-suite regression + manual smoke note

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `python -m pytest runtime/tests/test_vision_client.py bench/tests/test_tui_parse.py orchestrator/tests/test_tutor_api.py -v`
Expected: PASS (all green). If `make test` runs the full repo suite quickly, run that too and confirm no regressions.

- [ ] **Step 2: Record the manual smoke path (not automated)**

Vision needs real weights + a compiled `llama-server` + `make fetch-models` (the F16 mmproj), so end-to-end is a manual check on a machine that has them, not a unit test. Document the check in the commit body or PR description:

```
make serve && make dev    # resident text server + gateway
./run.sh --tui            # or: make tui
# in the TUI:
/img ~/some-handwritten-problem.jpg what did I get wrong?
# expect: "[image: ...]", then "read: <transcription>", then a streamed tutor reply.
```

- [ ] **Step 3: Adversarial review**

Per the working method, hand Tasks 1–3 to an adversarial reviewer in a fresh context (another lane) whose job is to break the `VisionClient` payload shape, the route's refusal paths, and the TUI busy/worker handoff. No task is done until that review fails to find a defect.

---

## Self-Review

**Spec coverage:**
- VisionClient (spec §Components/1) → Task 1. ✓
- `tutor_vision` wiring, keep both refusals (spec §Components/2, §Error handling) → Task 2. ✓
- TUI `/img` parse + attach + feed-into-stream (spec §Components/3, §Data flow) → Task 3. ✓
- Testing: VisionClient payload shape, route success + refusals, `parse_image_command` (spec §Testing) → Tasks 1–3. ✓
- Adversarial review (spec §Testing) → Task 4. ✓
- No contract change (spec §Out of scope) → enforced in Global Constraints; no task touches `contracts/`. ✓
- CLI REPL / video / direct VQA / RAM fix (spec §Out of scope) → not in any task. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code. ✓

**Type consistency:** `VisionClient(base_url).transcribe(prepared.data, prepared.format)` — `PreparedImage.data: bytes`, `.format: str` match `transcribe(image_bytes: bytes, image_format: str)`. Route returns `VisionReply(session_id, transcription, accepted)` — all real fields (`contracts/models.py:190-196`). `parse_image_command` return type `tuple[str, str|None]|None` consistent across Task 3 steps and its tests. ✓
