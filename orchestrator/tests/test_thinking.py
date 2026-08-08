"""Per-request thinking level: gateway mapping + the client payload it drives."""

from __future__ import annotations

from orchestrator.gateway.routes import _EXTENDED_MAX_TOKENS, _apply_thinking
from runtime.client import InferenceClient


def test_off_disables_thinking():
    assert _apply_thinking({}, "off") == {"enable_thinking": False}


def test_auto_enables_thinking():
    assert _apply_thinking({}, "auto") == {"enable_thinking": True}


def test_extended_enables_thinking_and_widens_the_budget():
    p = _apply_thinking({"max_tokens": 1200}, "extended")
    assert p["enable_thinking"] is True
    assert p["max_tokens"] == _EXTENDED_MAX_TOKENS


def test_none_leaves_the_server_default_untouched():
    assert "enable_thinking" not in _apply_thinking({"max_tokens": 1200}, None)


def test_client_payload_honours_a_per_request_thinking_override():
    client = InferenceClient(enable_thinking=True)
    payload = client._payload([], stream=False, enable_thinking=False, temperature=0.5)
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert "enable_thinking" not in payload  # popped, never sent as a bare top-level field
    assert payload["temperature"] == 0.5


def test_client_payload_defaults_to_the_client_setting():
    assert (
        InferenceClient(enable_thinking=True)._payload([], stream=False)["chat_template_kwargs"]
        == {"enable_thinking": True}
    )
