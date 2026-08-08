"""Per-request thinking level: gateway mapping + the client payload it drives."""

from __future__ import annotations

from orchestrator.gateway.routes import _EXTENDED_MAX_TOKENS, _apply_thinking
from runtime.client import InferenceClient


def test_off_disables_thinking():
    assert _apply_thinking({}, "off") == {"enable_thinking": False}


def test_auto_enables_thinking():
    assert _apply_thinking({}, "auto") == {"enable_thinking": True}


def test_extended_raises_the_per_request_reasoning_budget_and_widens_tokens():
    p = _apply_thinking({"max_tokens": 1200}, "extended", extended_budget=2048)
    assert p["enable_thinking"] is True
    assert p["reasoning_budget_tokens"] == 2048  # per-request cap, NOT an engine relaunch
    assert p["max_tokens"] == _EXTENDED_MAX_TOKENS


def test_auto_and_off_do_not_set_a_reasoning_budget():
    assert "reasoning_budget_tokens" not in _apply_thinking({}, "auto")  # launch default applies
    assert "reasoning_budget_tokens" not in _apply_thinking({}, "off")


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


def test_reasoning_budget_goes_to_the_local_engine():
    payload = InferenceClient()._payload([], stream=False, reasoning_budget_tokens=2048)
    assert payload["reasoning_budget_tokens"] == 2048


def test_reasoning_budget_is_dropped_for_strict_cloud_providers():
    # A strict cloud client (template_kwargs=False) must never receive llama-server-only fields.
    payload = InferenceClient(template_kwargs=False)._payload(
        [], stream=False, reasoning_budget_tokens=2048
    )
    assert "reasoning_budget_tokens" not in payload
    assert "chat_template_kwargs" not in payload
