"""One OpenAI-shaped client for local and cloud: api_key adds the bearer header,
template_kwargs=False drops the llama-server-only field strict providers reject."""

from __future__ import annotations

import httpx

from runtime.client import InferenceClient


def _capture_post(monkeypatch) -> dict:
    seen: dict = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        seen["json"] = json
        seen["headers"] = headers or {}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": {}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_api_key_becomes_a_bearer_header(monkeypatch):
    seen = _capture_post(monkeypatch)
    InferenceClient("http://cloud", api_key="sk-test").chat([{"role": "user", "content": "hi"}])
    assert seen["headers"].get("authorization") == "Bearer sk-test"


def test_no_api_key_means_no_auth_header(monkeypatch):
    seen = _capture_post(monkeypatch)
    InferenceClient("http://local").chat([{"role": "user", "content": "hi"}])
    assert "authorization" not in seen["headers"]


def test_template_kwargs_omitted_for_strict_providers(monkeypatch):
    seen = _capture_post(monkeypatch)
    InferenceClient("http://cloud", template_kwargs=False).chat([{"role": "user", "content": "hi"}])
    assert "chat_template_kwargs" not in seen["json"]


def test_template_kwargs_kept_by_default_for_llama_server(monkeypatch):
    seen = _capture_post(monkeypatch)
    InferenceClient("http://local").chat([{"role": "user", "content": "hi"}])
    assert seen["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_stream_carries_the_auth_header_too(monkeypatch):
    seen: dict = {}

    class _FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            yield "data: [DONE]"

    def fake_stream(method, url, json=None, timeout=None, headers=None):
        seen["headers"] = headers or {}
        return _FakeStream()

    monkeypatch.setattr(httpx, "stream", fake_stream)
    list(
        InferenceClient("http://cloud", api_key="sk-2").stream_events(
            [{"role": "user", "content": "hi"}]
        )
    )
    assert seen["headers"].get("authorization") == "Bearer sk-2"


def test_nonstreaming_generation_preserves_the_finish_reason(monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "So, in a simple"},
                        "finish_reason": "length",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = InferenceClient().chat_with_timings([{"role": "user", "content": "hi"}])
    assert result.text == "So, in a simple"
    assert result.finish_reason == "length"
