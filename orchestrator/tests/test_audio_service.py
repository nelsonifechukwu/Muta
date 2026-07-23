"""Audio service tests (TDD §6.6, S3, S12).

Driven with fake engines: the real ones are compiled sherpa-onnx binaries that ship in the
bundle, so what is testable here — and what actually breaks — is the protocol around them:
endpointing, the confirm checkpoint, and the degradation path when audio is absent.
"""

from __future__ import annotations

import json
import struct

import pytest
from fastapi.testclient import TestClient

from orchestrator.audio.config import AsrConfig, AudioConfig, TtsConfig, VadConfig
from orchestrator.audio.engines import NullAsr, NullTts, Transcript
from orchestrator.audio.service import create_app
from orchestrator.audio.vad import Endpointer


class FakeAsr:
    available = True

    def __init__(self, words: list[str]) -> None:
        self.words = list(words)
        self.heard: list[str] = []

    def accept(self, pcm: bytes) -> Transcript:
        if self.words:
            self.heard.append(self.words.pop(0))
        return Transcript(" ".join(self.heard))

    def finalize(self) -> Transcript:
        text = " ".join(self.heard)
        self.heard.clear()
        return Transcript(text, is_final=True)

    def reset(self) -> None:
        self.heard.clear()


class FakeTts:
    available = True
    sample_rate = 24000

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str, *, language: str = "en"):
        self.spoken.append(text)
        return iter([b"\x00\x01" * 8])


def config(**tts_kwargs) -> AudioConfig:
    return AudioConfig(
        asr=AsrConfig(vad=VadConfig(trailing_silence_seconds=0.4, max_utterance_seconds=2.0)),
        tts=TtsConfig(voices={"en": {"model": "voice.onnx"}}, **tts_kwargs),
    )


def pcm(seconds: float, *, loud: bool, rate: int = 16000) -> bytes:
    samples = int(seconds * rate)
    value = 20000 if loud else 0
    return struct.pack(f"<{samples}h", *([value] * samples))


# --- endpointing --------------------------------------------------------------------------


def test_half_a_second_of_silence_ends_an_utterance():
    ep = Endpointer(trailing_silence_seconds=0.5, max_utterance_seconds=90)
    assert ep.accept(0.2, is_speech=True) is False
    assert ep.accept(0.2, is_speech=False) is False
    assert ep.accept(0.2, is_speech=False) is False
    assert ep.accept(0.2, is_speech=False) is True
    assert ep.reason == "endpoint" and ep.had_speech


def test_silence_before_any_speech_never_endpoints():
    """Otherwise opening a microphone into a quiet room immediately submits an empty turn."""
    ep = Endpointer(trailing_silence_seconds=0.5)
    for _ in range(50):
        assert ep.accept(0.2, is_speech=False) is False
    assert not ep.had_speech


def test_hard_cap_stops_a_forgotten_open_mic():
    """S12: a 40-minute stream is charged to a slot's context; 90 s is the wall."""
    ep = Endpointer(trailing_silence_seconds=99, max_utterance_seconds=90)
    fired = any(ep.accept(1.0, is_speech=True) for _ in range(120))
    assert fired and ep.reason == "max-duration"


def test_endpointer_resets_between_utterances():
    ep = Endpointer(trailing_silence_seconds=0.4)
    ep.accept(0.2, is_speech=True)
    ep.reset()
    assert ep.total_seconds == 0 and not ep.started


# --- websockets ---------------------------------------------------------------------------


def test_asr_streams_partials_then_a_final_the_student_must_confirm():
    asr = FakeAsr(["solve", "x", "squared"])
    client = TestClient(create_app(config(), asr=asr, tts=FakeTts()))
    with client.websocket_connect("/asr") as ws:
        for _ in range(3):
            ws.send_bytes(pcm(0.2, loud=True))
            assert "partial" in json.loads(ws.receive_text())
        for _ in range(2):  # 0.4 s of silence → endpoint
            ws.send_bytes(pcm(0.2, loud=False))
        final = json.loads(ws.receive_text())

    assert final["final"] == "solve x squared"
    assert final["reason"] == "endpoint"
    # S3 trust checkpoint: the transcript is confirmed/edited before it enters the solution
    # path, because an ASR error that becomes a maths question wastes the student's turn.
    assert final["confirm"] is True


def test_asr_without_an_engine_says_so_and_offers_the_text_path():
    client = TestClient(create_app(config(), asr=NullAsr(), tts=FakeTts()))
    with client.websocket_connect("/asr") as ws:
        message = json.loads(ws.receive_text())
    assert message["error"] == "asr-unavailable" and "type your question" in message["fallback"]


def test_tts_normalises_math_and_streams_sentence_by_sentence():
    tts = FakeTts()
    client = TestClient(create_app(config(), asr=NullAsr(), tts=tts))
    with client.websocket_connect("/tts") as ws:
        ws.send_text(json.dumps({"text": r"First factorise. Then $x^2 = 9$.", "language": "en"}))
        messages = []
        while True:
            message = ws.receive()
            if "bytes" in message and message["bytes"] is not None:
                messages.append(("audio", message["bytes"]))
                continue
            payload = json.loads(message["text"])
            messages.append(("text", payload))
            if payload.get("done"):
                break

    assert tts.spoken == ["First factorise.", "Then x squared equals nine."]
    assert any(kind == "audio" for kind, _ in messages), "audio must actually stream"


def test_a_missing_voice_returns_a_notice_not_silence():
    """S8: a language without a voice gets a text reply plus a notice — silence reads as a
    broken system."""
    client = TestClient(create_app(config(), asr=NullAsr(), tts=FakeTts()))
    with client.websocket_connect("/tts") as ws:
        ws.send_text(json.dumps({"text": "Sannu", "language": "ha"}))
        payload = json.loads(ws.receive_text())
    assert payload["error"] == "voice-unavailable" and payload["language"] == "ha"


def test_capabilities_report_what_the_ui_may_offer():
    client = TestClient(create_app(config(), asr=NullAsr(), tts=NullTts()))
    body = client.get("/capabilities").json()
    assert body["asr"]["available"] is False and body["tts"]["available"] is False
    assert client.get("/health").json()["status"] == "ok", "audio absent is not audio broken"


# --- configuration ------------------------------------------------------------------------


def test_shipped_audio_yaml_parses_and_carries_the_policy_numbers():
    from orchestrator.audio.config import DEFAULT_CONFIG

    cfg = AudioConfig.load(DEFAULT_CONFIG, root="/opt/tutor")
    assert cfg.asr.vad.trailing_silence_seconds == 0.5
    assert cfg.asr.vad.max_utterance_seconds == 90.0
    assert cfg.asr.chunk_seconds == 0.2 and cfg.asr.sample_rate == 16000
    assert cfg.tts.engine == "piper"  # D5: Piper is the default everywhere
    assert cfg.resolve("models/tts/piper") == __import__("pathlib").Path("/opt/tutor/models/tts/piper")


def test_missing_config_file_yields_working_defaults(tmp_path):
    cfg = AudioConfig.load(tmp_path / "nope.yaml")
    assert cfg.asr.sample_rate == 16000 and cfg.tts.engine == "piper"


def test_voice_lookup_falls_back_to_the_base_language():
    cfg = TtsConfig(voices={"en": {"model": "a.onnx"}})
    assert cfg.voice_for("en-NG") == {"model": "a.onnx"}
    assert cfg.voice_for("yo") is None


@pytest.mark.parametrize("engine", [NullAsr(), NullTts()])
def test_null_engines_are_honest_about_why(engine):
    assert engine.available is False and engine.reason
