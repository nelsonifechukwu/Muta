"""Bearer-token identity: dev mode (token == id) and hardened HMAC-signed mode."""

from __future__ import annotations

import pytest

from orchestrator.gateway import auth


def test_dev_mode_token_is_the_student_id(monkeypatch):
    monkeypatch.delenv("MUTA_AUTH_SECRET", raising=False)
    assert auth.mint_token("student-42") == "student-42"
    assert auth.verify_token("student-42") == "student-42"
    assert auth.verify_token("") is None
    assert auth.verify_token(None) is None


def test_signed_mode_round_trips(monkeypatch):
    monkeypatch.setenv("MUTA_AUTH_SECRET", "top-secret")
    token = auth.mint_token("alice")
    assert token != "alice"  # opaque, signed
    assert auth.verify_token(token) == "alice"


def test_signed_mode_rejects_forgery(monkeypatch):
    monkeypatch.setenv("MUTA_AUTH_SECRET", "top-secret")
    # A raw id is not a valid signed token once a secret is configured.
    assert auth.verify_token("alice") is None
    # A token minted under a different secret does not verify here.
    monkeypatch.setenv("MUTA_AUTH_SECRET", "other-secret")
    other = auth.mint_token("alice")
    monkeypatch.setenv("MUTA_AUTH_SECRET", "top-secret")
    assert auth.verify_token(other) is None
    # Tampering with the signature fails.
    assert auth.verify_token(other[:-2] + "xy") is None


def test_rejects_oversized_or_empty_ids(monkeypatch):
    monkeypatch.delenv("MUTA_AUTH_SECRET", raising=False)
    with pytest.raises(ValueError):
        auth.mint_token("")
    with pytest.raises(ValueError):
        auth.mint_token("x" * (auth.MAX_STUDENT_ID + 1))
    assert auth.verify_token("x" * (auth.MAX_STUDENT_ID + 1)) is None
