"""Audio configuration, loaded from `orchestrator/audio/audio.yaml` (TDD §6.6)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent / "audio.yaml"


@dataclass(frozen=True)
class VadConfig:
    # Underscore, matching what fetch_models actually writes (istupakov/silero-vad-onnx
    # ships `silero_vad.onnx`); the historical dash name never existed on disk.
    model: str = "models/asr/silero_vad.onnx"
    trailing_silence_seconds: float = 0.5
    max_utterance_seconds: float = 90.0
    threshold: float = 0.5


@dataclass(frozen=True)
class AsrConfig:
    engine: str = "sherpa-onnx"
    model_dir: str = "models/asr/moonshine-tiny-en-int8"
    chunk_seconds: float = 0.2
    sample_rate: int = 16000
    num_threads: int = 1
    decoding_method: str = "greedy_search"
    language: str = "en"
    vad: VadConfig = field(default_factory=VadConfig)


@dataclass(frozen=True)
class TtsConfig:
    engine: str = "piper"
    sample_rate: int = 24000
    num_threads: int = 1
    voices: dict[str, dict[str, str]] = field(default_factory=dict)
    premium: dict[str, Any] = field(default_factory=dict)

    def voice_for(self, language: str) -> dict[str, str] | None:
        """Voice for a language, or None — a missing voice is a text-only reply with a
        notice (S8), never a silent failure or a wrong-language voice."""
        return self.voices.get(language) or self.voices.get(language.split("-")[0])


@dataclass(frozen=True)
class AudioConfig:
    asr: AsrConfig = field(default_factory=AsrConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    root: Path = Path("/opt/tutor")

    def resolve(self, relative: str) -> Path:
        return self.root / relative

    @classmethod
    def load(cls, path: Path | str | None = None, *, root: Path | str | None = None) -> "AudioConfig":
        path = Path(path or os.environ.get("TUTOR_AUDIO_CONFIG") or DEFAULT_CONFIG)
        root = Path(root or os.environ.get("TUTOR_ROOT", "/opt/tutor"))
        if not path.is_file():
            return cls(root=root)  # defaults are a working config, not a stub
        raw = yaml.safe_load(path.read_text()) or {}
        asr_raw = dict(raw.get("asr") or {})
        vad_raw = dict(asr_raw.pop("vad", None) or {})
        tts_raw = dict(raw.get("tts") or {})
        return cls(
            asr=AsrConfig(**{**asr_raw, "vad": VadConfig(**vad_raw)}),
            tts=TtsConfig(**tts_raw),
            root=root,
        )
