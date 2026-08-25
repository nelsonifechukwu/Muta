"""Audio engine wiring — the config bugs this branch fixed stay fixed."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from orchestrator.audio.config import DEFAULT_CONFIG, AudioConfig
from orchestrator.audio.engines import SherpaAsr, SherpaTts, SileroVad


def test_default_config_lives_next_to_the_package():
    # deploy/etc/audio.yaml is gone on this branch; the config of record ships with the code.
    assert DEFAULT_CONFIG == Path(__file__).resolve().parents[1] / "audio" / "audio.yaml"
    assert DEFAULT_CONFIG.is_file()


def test_yaml_resolves_the_underscore_vad_filename(tmp_path):
    cfg = AudioConfig.load(DEFAULT_CONFIG, root=tmp_path)
    # The fetched file is silero_vad.onnx — the dash name never existed on disk.
    assert cfg.asr.vad.model.endswith("silero_vad.onnx")
    assert cfg.resolve(cfg.asr.vad.model) == tmp_path / "models/asr/silero_vad.onnx"


def test_voice_entry_has_tokens_and_espeak_data():
    cfg = AudioConfig.load(DEFAULT_CONFIG)
    voice = cfg.tts.voice_for("en")
    assert voice["model"].endswith("en_US-joe-medium.onnx")
    assert voice["tokens"].endswith("tokens.txt")
    assert voice["data_dir"].endswith("espeak-ng-data")


class _Recorder:
    """Captures kwargs for any sherpa config class."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)


def _fake_sherpa(record: dict) -> types.ModuleType:
    mod = types.ModuleType("sherpa_onnx")

    def vits(**kwargs):
        record["vits"] = kwargs
        return _Recorder(**kwargs)

    mod.OfflineTtsVitsModelConfig = vits
    mod.OfflineTtsModelConfig = lambda **kw: _Recorder(**kw)
    mod.OfflineTtsConfig = lambda **kw: _Recorder(**kw)
    mod.OfflineTts = lambda cfg: object()
    return mod


def test_sherpa_tts_uses_tokens_txt_and_data_dir(monkeypatch, tmp_path):
    # The old code passed the voice's .onnx.json as tokens= and no data_dir — a real bug.
    record: dict = {}
    monkeypatch.setitem(sys.modules, "sherpa_onnx", _fake_sherpa(record))
    voice_dir = tmp_path / "models/tts/piper"
    voice_dir.mkdir(parents=True)
    (voice_dir / "en_US-joe-medium.onnx").touch()

    cfg = AudioConfig.load(DEFAULT_CONFIG, root=tmp_path)
    tts = SherpaTts(cfg)

    assert tts.available
    assert record["vits"]["tokens"].endswith("tokens.txt")
    assert record["vits"]["data_dir"].endswith("espeak-ng-data")


def test_silero_vad_degrades_without_sherpa(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "sherpa_onnx", None)  # import returns None → TypeError
    cfg = AudioConfig.load(DEFAULT_CONFIG, root=tmp_path)
    vad = SileroVad(cfg)
    assert vad.available is False
    vad.accept(b"\x00\x00" * 100)  # must be a silent no-op, never a crash
    assert vad.pop_segment() is None


def test_moonshine_does_not_decode_an_empty_vad_segment():
    class _Recognizer:
        def create_stream(self):
            raise AssertionError("empty audio must not reach Moonshine")

    asr = object.__new__(SherpaAsr)
    asr.config = AudioConfig.load(DEFAULT_CONFIG)
    asr.available = True
    asr._recognizer = _Recognizer()
    asr._stream = None

    assert asr.transcribe_samples([]) == ""
