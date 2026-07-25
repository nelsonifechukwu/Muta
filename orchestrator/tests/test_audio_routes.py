"""Gateway audio routes — degraded paths work without sherpa/ffmpeg installed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import orchestrator.gateway.audio_routes as audio_routes
from orchestrator.audio.config import AudioConfig
from orchestrator.audio.engines import NullAsr, NullTts
from orchestrator.gateway.audio_routes import AudioStack, _split_sentences
from orchestrator.main import app

client = TestClient(app)


@pytest.fixture
def null_audio(monkeypatch):
    stack = AudioStack(config=AudioConfig.load(), asr=NullAsr(), tts=NullTts())
    monkeypatch.setattr(audio_routes, "get_audio", lambda: stack)
    return stack


def test_transcribe_503_when_asr_unavailable(null_audio):
    r = client.post("/v1/audio/transcribe", files={"audio": ("a.wav", b"RIFF....", "audio/wav")})
    assert r.status_code == 503
    assert "type the question" in r.json()["detail"]


def test_transcribe_appears_in_the_contract():
    assert "/v1/audio/transcribe" in app.openapi()["paths"]


def test_voice_ws_reports_asr_unavailable_and_closes(null_audio):
    with client.websocket_connect("/v1/audio/voice") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["reason"] == "asr-unavailable"
        assert "type your question" in msg["fallback"]


def test_mathspeech_seam_yields_plain_text():
    # The voice loop hands to_speech output to the synthesizer, which wants str —
    # regression for feeding it the SpokenSentence list directly (live TypeError).
    from orchestrator.audio.mathspeech import to_speech

    spoken = " ".join(p.text for p in to_speech("x^2 + 5x + 6 = 0. Factor it."))
    assert isinstance(spoken, str)
    assert spoken


def test_split_sentences():
    done, rest = _split_sentences("First point. Second one! And then")
    assert done == ["First point.", "Second one!"]
    assert rest == "And then"

    done, rest = _split_sentences("no boundary yet")
    assert done == []
    assert rest == "no boundary yet"
