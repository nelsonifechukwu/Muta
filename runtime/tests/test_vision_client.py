"""VisionClient sends a guarded image to CORE-VISION as an OpenAI image-content-array
message and returns the transcription. This is the one place that shape lives; the text
InferenceClient stays string-only.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from runtime.vision_client import (
    DEFAULT_TRANSCRIBE_PROMPT,
    VisionClient,
    VisionResponseError,
)


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


def test_thinking_is_disabled_for_the_transcription(monkeypatch):
    seen = _capture(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})
    VisionClient("http://127.0.0.1:8082").transcribe(b"x", "PNG")
    assert seen["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_transport_error_propagates(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(httpx.HTTPError):
        VisionClient("http://127.0.0.1:8082").transcribe(b"x", "PNG")


def test_a_malformed_200_body_raises_vision_response_error_not_keyerror(monkeypatch):
    # 200 OK but an error-shaped body (no `choices`). Must be a typed error the route catches,
    # never a bare KeyError that escapes to a 500.
    _capture(monkeypatch, {"error": "no slot free"})
    with pytest.raises(VisionResponseError):
        VisionClient("http://127.0.0.1:8082").transcribe(b"x", "PNG")


def test_null_content_becomes_empty_string_not_none(monkeypatch):
    # A null content would fail VisionReply.transcription: str validation -> 500. Coerce to "".
    _capture(monkeypatch, {"choices": [{"message": {"content": None}}]})
    assert VisionClient("http://127.0.0.1:8082").transcribe(b"x", "PNG") == ""


def test_content_array_is_flattened_to_text(monkeypatch):
    _capture(
        monkeypatch,
        {"choices": [{"message": {"content": [{"type": "text", "text": "x^2"}, {"type": "text", "text": " = 9"}]}}]},
    )
    assert VisionClient("http://127.0.0.1:8082").transcribe(b"x", "PNG") == "x^2 = 9"
