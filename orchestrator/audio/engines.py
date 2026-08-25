"""ASR / TTS engine adapters (TDD §6.6).

sherpa-onnx is a compiled dependency that ships in the bundle, not a pip install — so every
engine here has a null twin. A dev box without sherpa (or a target box where the audio
models were not staged) gets `available=False` and the gateway degrades to text, which is
the C-7 rule: every failure mode ends at a working text tutor, never an error screen.

The engines are also where the utterance protocol lives: 16 kHz mono PCM in, incremental
transcript out, finalisation on a VAD endpoint.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from orchestrator.audio.config import AudioConfig

log = logging.getLogger("muta.audio")


@dataclass
class Transcript:
    text: str
    is_final: bool = False
    confidence: float = 1.0


class AsrEngine(Protocol):
    available: bool

    def accept(self, pcm: bytes) -> Transcript: ...
    def finalize(self) -> Transcript: ...
    def reset(self) -> None: ...


class TtsEngine(Protocol):
    available: bool
    sample_rate: int

    def synthesize(self, text: str, *, language: str = "en") -> Iterator[bytes]: ...


# --- null engines -------------------------------------------------------------------------


@dataclass
class NullAsr:
    """Reports unavailability honestly instead of returning empty transcripts that look like
    a student saying nothing."""

    reason: str = "sherpa-onnx not installed"
    available: bool = False

    def accept(self, pcm: bytes) -> Transcript:
        return Transcript("", is_final=False, confidence=0.0)

    def finalize(self) -> Transcript:
        return Transcript("", is_final=True, confidence=0.0)

    def reset(self) -> None:
        return None


@dataclass
class NullTts:
    reason: str = "sherpa-onnx not installed"
    available: bool = False
    sample_rate: int = 24000

    def synthesize(self, text: str, *, language: str = "en") -> Iterator[bytes]:
        return iter(())


# --- sherpa-onnx ---------------------------------------------------------------------------


@dataclass
class SherpaAsr:
    """Streaming Moonshine INT8 + Silero VAD (TDD §4.5, §4.6).

    Imported lazily and defensively: this module is imported by the gateway, and a missing
    audio stack must not stop the text tutor from booting.
    """

    config: AudioConfig
    available: bool = False
    _recognizer: object | None = field(default=None, repr=False)
    _stream: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        try:
            import sherpa_onnx
        except ImportError:
            log.info("sherpa-onnx unavailable — ASR degrades to text-only input")
            return
        model_dir = self.config.resolve(self.config.asr.model_dir)
        if not model_dir.is_dir():
            log.info("ASR model dir %s absent — ASR disabled", model_dir)
            return
        try:
            self._recognizer = self._build(sherpa_onnx, model_dir)
            self._stream = self._recognizer.create_stream()  # type: ignore[attr-defined]
            self.available = True
        except Exception as e:  # noqa: BLE001 — a broken model file must not crash the app
            log.warning("ASR init failed (%s) — degrading to text-only input", e)

    def _build(self, sherpa_onnx, model_dir):
        cfg = self.config.asr
        return sherpa_onnx.OfflineRecognizer.from_moonshine(
            preprocessor=str(model_dir / "preprocess.onnx"),
            encoder=str(model_dir / "encode.int8.onnx"),
            uncached_decoder=str(model_dir / "uncached_decode.int8.onnx"),
            cached_decoder=str(model_dir / "cached_decode.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=cfg.num_threads,
            decoding_method=cfg.decoding_method,
        )

    def accept(self, pcm: bytes) -> Transcript:
        if not self.available:
            return Transcript("", confidence=0.0)
        import numpy as np

        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._stream.accept_waveform(self.config.asr.sample_rate, samples)  # type: ignore[union-attr]
        return Transcript(self._current_text(), is_final=False)

    def finalize(self) -> Transcript:
        if not self.available:
            return Transcript("", is_final=True, confidence=0.0)
        self._recognizer.decode_stream(self._stream)  # type: ignore[union-attr]
        text = self._current_text()
        self.reset()
        return Transcript(text, is_final=True)

    def transcribe_pcm(self, pcm: bytes) -> str:
        """One-shot recognition on a dedicated stream — stateless, so concurrent callers
        (upload endpoint, voice websocket) never share partial transcripts."""
        if not self.available or not pcm:
            return ""
        import numpy as np

        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        return self.transcribe_samples(samples)

    def transcribe_samples(self, samples) -> str:
        if not self.available:
            return ""
        import numpy as np

        samples = np.asarray(samples, dtype=np.float32)
        # sherpa's Moonshine convolution rejects an empty waveform. Silero can expose an empty
        # segment when a learner stops a silent capture, so treat that as "not heard" instead of
        # invoking ONNX with shape {1,0} and printing a native exception into the desktop log.
        if samples.size == 0:
            return ""
        stream = self._recognizer.create_stream()  # type: ignore[attr-defined]
        stream.accept_waveform(self.config.asr.sample_rate, samples)
        self._recognizer.decode_stream(stream)  # type: ignore[union-attr]
        try:
            return str(stream.result.text).strip()
        except Exception:  # noqa: BLE001
            return ""

    def _current_text(self) -> str:
        try:
            return str(self._stream.result.text).strip()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            return ""

    def reset(self) -> None:
        if self.available and self._recognizer is not None:
            self._stream = self._recognizer.create_stream()  # type: ignore[attr-defined]


@dataclass
class SherpaTts:
    """Piper by default; Kokoro only in the solo-demo profile (D5)."""

    config: AudioConfig
    available: bool = False
    sample_rate: int = 24000
    _tts: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.sample_rate = self.config.tts.sample_rate
        try:
            import sherpa_onnx
        except ImportError:
            log.info("sherpa-onnx unavailable — replies will be text-only")
            return
        voice = self.config.tts.voice_for("en")
        if not voice:
            log.info("no TTS voice configured — replies will be text-only")
            return
        model = self.config.resolve(voice["model"])
        if not model.is_file():
            log.info("TTS voice %s absent — replies will be text-only", model)
            return
        try:
            # Exactly the instantiation scripts/verify_models.py proved against the pinned
            # voice: tokens.txt (NOT the .onnx.json), and espeak-ng-data as data_dir.
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(model),
                        tokens=str(self.config.resolve(voice["tokens"])),
                        data_dir=str(self.config.resolve(voice.get("data_dir", ""))),
                    ),
                    num_threads=self.config.tts.num_threads,
                ),
            )
            self._tts = sherpa_onnx.OfflineTts(tts_config)
            self.available = True
        except Exception as e:  # noqa: BLE001
            log.warning("TTS init failed (%s) — replies will be text-only", e)

    def synthesize(self, text: str, *, language: str = "en") -> Iterator[bytes]:
        if not self.available:
            return iter(())
        if self.config.tts.voice_for(language) is None:
            log.info("no voice for %s — caller should send text with a notice (S8)", language)
            return iter(())
        import numpy as np

        audio = self._tts.generate(text)  # type: ignore[union-attr]
        # The voice's true rate (joe is 22050 Hz) — playing PCM at the config's guess would
        # shift pitch and speed. The generated audio is the authority.
        rate = int(getattr(audio, "sample_rate", 0) or 0)
        if rate:
            self.sample_rate = rate
        pcm = (np.asarray(audio.samples) * 32767).astype(np.int16).tobytes()
        return iter([pcm])


@dataclass
class SileroVad:
    """Silero VAD via sherpa-onnx. A closed speech segment (speech, then enough silence)
    appears on the detector's queue — that queue becoming non-empty IS the endpoint signal.
    When the model/library is absent, `available=False` and callers fall back to the
    pure-Python `Endpointer` energy policy (vad.py)."""

    config: AudioConfig
    available: bool = False
    _vad: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        try:
            import sherpa_onnx
        except ImportError:
            log.info("sherpa-onnx unavailable — VAD falls back to the energy endpointer")
            return
        model = self.config.resolve(self.config.asr.vad.model)
        if not model.is_file():
            log.info("VAD model %s absent — falling back to the energy endpointer", model)
            return
        try:
            cfg = sherpa_onnx.VadModelConfig()
            cfg.silero_vad.model = str(model)
            cfg.silero_vad.threshold = self.config.asr.vad.threshold
            cfg.silero_vad.min_silence_duration = self.config.asr.vad.trailing_silence_seconds
            cfg.sample_rate = self.config.asr.sample_rate
            self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=120)
            self.available = True
        except Exception as e:  # noqa: BLE001
            log.warning("VAD init failed (%s) — falling back to the energy endpointer", e)

    def accept(self, pcm: bytes) -> None:
        if not self.available:
            return
        import numpy as np

        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._vad.accept_waveform(samples)  # type: ignore[union-attr]

    def pop_segment(self):
        """The oldest finished speech segment's float32 samples, or None."""
        if not self.available or self._vad.empty():  # type: ignore[union-attr]
            return None
        segment = self._vad.front  # type: ignore[union-attr]
        self._vad.pop()  # type: ignore[union-attr]
        return segment.samples

    def flush(self) -> None:
        if self.available:
            self._vad.flush()  # type: ignore[union-attr]

    def reset(self) -> None:
        if self.available:
            self._vad.reset()  # type: ignore[union-attr]


def load_engines(config: AudioConfig | None = None) -> tuple[AsrEngine, TtsEngine]:
    config = config or AudioConfig.load()
    asr: AsrEngine = SherpaAsr(config)
    tts: TtsEngine = SherpaTts(config)
    return (asr if asr.available else NullAsr()), (tts if tts.available else NullTts())
