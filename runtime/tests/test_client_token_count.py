"""Prompt fitting uses llama-server's own template and tokenizer when available."""

from __future__ import annotations

import httpx

from runtime.client import InferenceClient


def test_count_prompt_tokens_renders_the_same_thinking_template_then_tokenizes(monkeypatch):
    calls: list[tuple[str, dict, float, dict]] = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append((url, json, timeout, headers or {}))
        body = (
            {"prompt": "<chat>hello</chat>"}
            if url.endswith("/apply-template")
            else {"tokens": [1, 7, 9, 11]}
        )
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = InferenceClient(
        "http://local",
        enable_thinking=False,
        timeout=120.0,
        api_key="secret",
    )

    count = client.count_prompt_tokens([{"role": "user", "content": "hello"}], enable_thinking=True)

    assert count == 4
    assert calls[0][0] == "http://local/apply-template"
    assert calls[0][1] == {
        "messages": [{"role": "user", "content": "hello"}],
        "add_generation_prompt": True,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    assert calls[1][0] == "http://local/tokenize"
    assert calls[1][1] == {"content": "<chat>hello</chat>", "add_special": True}
    assert calls[0][2] == calls[1][2] == 5.0
    assert calls[0][3]["authorization"] == "Bearer secret"


def test_cloud_style_client_does_not_send_local_template_kwargs(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append(json)
        body = {"prompt": "rendered"} if url.endswith("/apply-template") else {"tokens": [1]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    assert (
        InferenceClient("http://cloud", template_kwargs=False).count_prompt_tokens(
            [{"role": "user", "content": "hello"}]
        )
        == 1
    )
    assert "chat_template_kwargs" not in calls[0]
