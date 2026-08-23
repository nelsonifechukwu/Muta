"""The CORE-VISION completion call — image in, transcription out (TDD §6.3, S2).

Kept separate from `runtime.client.InferenceClient` on purpose: CORE-VISION is a distinct,
ephemeral llama-server (a second process over the same weight file with `--mmproj`), and this
is the ONLY place the OpenAI image-content-array message shape is constructed. The text client
stays string-only, so nothing on the resident-server path has to reason about images.
"""

from __future__ import annotations

import base64
import contextlib
import json
import threading

import httpx

#: Transcribe, don't solve: the resident text tutor does the tutoring (transcribe → tutor).
DEFAULT_TRANSCRIBE_PROMPT = (
    "Transcribe the handwritten or printed math and working in this image exactly, as plain "
    "text with LaTeX for equations. Do not solve it, explain it, or add anything that is not "
    "on the page."
)

#: PreparedImage.format -> data-URI MIME type.
_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class VisionResponseError(RuntimeError):
    """CORE-VISION answered (2xx) with a body we can't read as a transcription.

    Separate from `httpx.HTTPError` so the caller can turn *both* transport failures and
    malformed-but-200 replies into S2's friendly "type the problem" fallback — never a 500.
    """


class VisionClient:
    def __init__(
        self,
        base_url: str,
        *,
        model: str = "core-vision",
        timeout: float = 120.0,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._headers = {"authorization": f"Bearer {api_key}"} if api_key else {}

    def transcribe(
        self,
        image_bytes: bytes,
        image_format: str,
        *,
        prompt: str = DEFAULT_TRANSCRIBE_PROMPT,
        cancel_event: threading.Event | None = None,
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
            # Reading the page needs no chain of thought; thinking is on by default for these
            # Qwen3 weights, and here it would only add latency (and cost) to an OCR call.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        url = f"{self.base_url}/v1/chat/completions"
        if cancel_event is None:
            r = httpx.post(url, json=payload, timeout=self.timeout, headers=self._headers)
            r.raise_for_status()
        else:
            with httpx.Client(timeout=self.timeout) as client:
                request = client.build_request("POST", url, json=payload, headers=self._headers)
                r = client.send(request, stream=True)
                watcher_stop = threading.Event()

                def close_when_cancelled() -> None:
                    while not watcher_stop.wait(0.05):
                        if cancel_event.is_set():
                            with contextlib.suppress(Exception):
                                r.close()
                            return

                watcher = threading.Thread(
                    target=close_when_cancelled,
                    name="muta-vision-cancel",
                    daemon=True,
                )
                watcher.start()
                try:
                    r.raise_for_status()
                    r.read()
                finally:
                    watcher_stop.set()
                    r.close()
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise VisionResponseError(f"unreadable vision response: {e}") from e
        # llama-server normally returns a plain string; be defensive about a content-array or a
        # null (a refusal/empty read) so neither becomes a 500 or a Pydantic validation error.
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return content or ""
