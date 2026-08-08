"""Cloud boost wiring: env-gated client wrap, and the SSE done event names its source."""

from __future__ import annotations

from orchestrator.gateway import deps
from runtime.client import InferenceClient
from runtime.cloud import CloudFallbackClient

_CLOUD_ENV = ("MUTA_CLOUD_URL", "MUTA_CLOUD_MODEL", "MUTA_CLOUD_API_KEY")


def test_cloud_env_wires_the_fallback_client(monkeypatch):
    monkeypatch.setenv("MUTA_CLOUD_URL", "https://cloud.example")
    monkeypatch.setenv("MUTA_CLOUD_MODEL", "big-model")
    monkeypatch.setenv("MUTA_CLOUD_API_KEY", "sk-x")
    deps.get_engine.cache_clear()
    try:
        assert isinstance(deps.get_engine().client, CloudFallbackClient)
    finally:
        deps.get_engine.cache_clear()


def test_partial_cloud_env_stays_local(monkeypatch):
    """Two of three vars set is a misconfiguration, not a half-enabled cloud."""
    monkeypatch.setenv("MUTA_CLOUD_URL", "https://cloud.example")
    monkeypatch.setenv("MUTA_CLOUD_MODEL", "big-model")
    monkeypatch.delenv("MUTA_CLOUD_API_KEY", raising=False)
    deps.get_engine.cache_clear()
    try:
        assert isinstance(deps.get_engine().client, InferenceClient)
    finally:
        deps.get_engine.cache_clear()


def test_without_cloud_env_the_client_is_plain(monkeypatch):
    for key in _CLOUD_ENV:
        monkeypatch.delenv(key, raising=False)
    deps.get_engine.cache_clear()
    try:
        assert isinstance(deps.get_engine().client, InferenceClient)
    finally:
        deps.get_engine.cache_clear()
