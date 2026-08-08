"""Audio on the gateway: `POST /v1/audio/transcribe` and the voice loop
`WS /v1/audio/voice` (TDD §7.2's designed-but-unbuilt `WS /v1/audio/stream`, realised).

Voice protocol (client ↔ server over one socket):
- client → text `{"type":"start","student_id","conversation_id":null|id,"mode":"socratic"}`
- client → binary frames: 16 kHz mono int16 PCM (~320 ms each)
- client → text `{"type":"stop"}` force the endpoint; `{"type":"barge"}` cancel the reply
- server → `{"type":"transcript","text","conversation_id"}` at the VAD endpoint
- server → `{"type":"reasoning"|"delta","text"}` while the model generates
- server → per sentence: `{"type":"tts_start","sample_rate"}`, binary PCM, `{"type":"tts_end"}`
- server → `{"type":"done"}`; on missing ASR `{"type":"error","reason":"asr-unavailable",…}`

Half-duplex by design: the client mutes its mic while the reply plays, and the server drops
mic frames while a reply is in flight — no echo cancellation needed for the MVP.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import subprocess
import threading
from dataclasses import dataclass

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from contracts.models import TranscribeResponse
from orchestrator.audio.config import AudioConfig
from orchestrator.audio.engines import AsrEngine, SileroVad, TtsEngine, load_engines
from orchestrator.audio.mathspeech import to_speech
from orchestrator.audio.vad import Endpointer
from orchestrator.gateway.deps import get_engine, load_prompt
from orchestrator.telemetry import get_hub
from runtime.chat import ChatEngine

log = logging.getLogger("muta.gateway.audio")

router = APIRouter()

SAMPLE_RATE = 16000
_SENTENCE_END = re.compile(r"(?<=[.!?:;])\s+")


@dataclass
class AudioStack:
    config: AudioConfig
    asr: AsrEngine
    tts: TtsEngine


_audio_stack: AudioStack | None = None
_audio_lock = threading.Lock()


def get_audio() -> AudioStack:
    """Load the ONNX engines once — but only cache success. Models can arrive after boot
    (late volume mount, post-boot fetch), and the old `lru_cache` latched the first probe's
    verdict for the life of the process: one early request condemned audio to 503 forever.
    ASR gates the retry; a missing TTS alone is a legitimate degraded mode not worth
    re-initialising a working ASR for."""
    global _audio_stack
    with _audio_lock:
        if _audio_stack is None or not _audio_stack.asr.available:
            config = AudioConfig.load()
            asr, tts = load_engines(config)
            _audio_stack = AudioStack(config=config, asr=asr, tts=tts)
        return _audio_stack


# ---------------------------------------------------------------------------
# POST /v1/audio/transcribe — uploaded files (webm/opus/m4a/mp3/wav → ffmpeg → ASR)
# ---------------------------------------------------------------------------


def _ffmpeg_to_pcm16k(data: bytes) -> bytes | None:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
            input=data,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 and proc.stdout else None


@router.post("/audio/transcribe", response_model=TranscribeResponse, tags=["audio"])
async def audio_transcribe(
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    engine: ChatEngine = Depends(get_engine),
) -> TranscribeResponse:
    """Uploaded audio → text. 503 when ASR is unavailable (the UI tells the student to
    type instead), 422 when ffmpeg can't decode the file."""
    stack = await run_in_threadpool(get_audio)  # first call loads ONNX models
    if not stack.asr.available:
        raise HTTPException(
            status_code=503,
            detail="speech recognition isn't available — type the question instead",
        )
    raw = await audio.read()
    pcm = await run_in_threadpool(_ffmpeg_to_pcm16k, raw)
    if pcm is None:
        raise HTTPException(status_code=422, detail="couldn't decode that audio file")
    text = await run_in_threadpool(stack.asr.transcribe_pcm, pcm)

    attachment_id: int | None = None
    try:
        attachment_id = await run_in_threadpool(
            engine.store.add_attachment,
            "audio",
            audio.content_type or "application/octet-stream",
            raw,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001 — persistence is best-effort; the transcript is the point
        attachment_id = None
    return TranscribeResponse(text=text, attachment_id=attachment_id)


# ---------------------------------------------------------------------------
# WS /v1/audio/voice — VAD → ASR → LLM → TTS, no extra clicks
# ---------------------------------------------------------------------------


def _rms_loud(pcm: bytes, threshold: float = 500.0) -> bool:
    """Energy gate for the no-Silero fallback (same policy as audio/service.py)."""
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return False
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) > threshold


def _split_sentences(buf: str) -> tuple[list[str], str]:
    parts = _SENTENCE_END.split(buf)
    if len(parts) <= 1:
        return [], buf
    return [p for p in parts[:-1] if p.strip()], parts[-1]


@router.websocket("/audio/voice")
async def audio_voice(ws: WebSocket) -> None:
    await ws.accept()
    # First-connection engine loads (ONNX models) must not stall the event loop.
    stack = await run_in_threadpool(get_audio)
    if not stack.asr.available:
        await ws.send_json(
            {"type": "error", "reason": "asr-unavailable", "fallback": "type your question"}
        )
        await ws.close()
        return

    # Handshake. A malformed or binary first frame closes politely, never a traceback.
    try:
        start = json.loads(await ws.receive_text())
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 — includes binary-first KeyError and bad JSON
        with contextlib.suppress(Exception):
            await ws.close()
        return
    student_id = start.get("student_id") or "voice-user"
    mode = start.get("mode") or "socratic"
    state = {"conversation_id": start.get("conversation_id")}

    vad = await run_in_threadpool(SileroVad, stack.config)
    endpointer = Endpointer(
        trailing_silence_seconds=stack.config.asr.vad.trailing_silence_seconds,
        max_utterance_seconds=stack.config.asr.vad.max_utterance_seconds,
    )
    buffer = bytearray()
    # Silence never pops a VAD segment, so an open quiet mic would grow this forever.
    # Keep only the trailing max-utterance window — the most any endpoint can consume.
    max_buffer_bytes = int(stack.config.asr.vad.max_utterance_seconds * SAMPLE_RATE * 2)
    cancel = asyncio.Event()
    respond_task: asyncio.Task | None = None

    async def speak(sentence: str) -> None:
        if not stack.tts.available or cancel.is_set():
            return
        # to_speech returns SpokenSentence objects ("x^2" → "x squared"); the synthesizer
        # wants plain text.
        spoken = " ".join(p.text for p in to_speech(sentence)).strip()
        if not spoken:
            return
        chunks = await run_in_threadpool(lambda: list(stack.tts.synthesize(spoken)))
        if not chunks or cancel.is_set():
            return
        await ws.send_json({"type": "tts_start", "sample_rate": stack.tts.sample_rate})
        for chunk in chunks:
            await ws.send_bytes(chunk)
        await ws.send_json({"type": "tts_end"})

    async def respond(utterance) -> None:
        """utterance: float32 samples (VAD segment) or int16 PCM bytes (fallback path)."""
        try:
            await _respond_inner(utterance)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a failed turn must be visible, not silent
            log.exception("voice turn failed")
            with contextlib.suppress(Exception):
                await ws.send_json(
                    {
                        "type": "error",
                        "reason": "voice-turn-failed",
                        "fallback": "type your question",
                    }
                )

    async def _respond_inner(utterance) -> None:
        if isinstance(utterance, (bytes, bytearray)):
            text = await run_in_threadpool(stack.asr.transcribe_pcm, bytes(utterance))
        else:
            text = await run_in_threadpool(stack.asr.transcribe_samples, utterance)
        if not text.strip():
            await ws.send_json({"type": "done", "heard": False})
            return

        # get_engine's first call constructs the Postgres store (can wait on the pool) and
        # stream_events_chat does several store round-trips before returning — threadpool
        # both so one cold voice request can't freeze every other client.
        engine = await run_in_threadpool(get_engine)
        cid, _mid, events = await run_in_threadpool(
            lambda: engine.stream_events_chat(
                student_id=student_id,
                message=text,
                conversation_id=state["conversation_id"],
                system_prompt=load_prompt(mode),
                mode=mode,
                title=text[:80],
            )
        )
        state["conversation_id"] = cid
        await ws.send_json({"type": "transcript", "text": text, "conversation_id": cid})

        hub = get_hub()
        hub.begin(cid)
        sentence_buf = ""
        try:
            async for kind, chunk in iterate_in_threadpool(events):
                if cancel.is_set():
                    break  # closes the generator → the partial reply is persisted
                hub.tick(cid)
                if kind == "reasoning":
                    await ws.send_json({"type": "reasoning", "text": chunk})
                    continue
                await ws.send_json({"type": "delta", "text": chunk})
                sentence_buf += chunk
                sentences, sentence_buf = _split_sentences(sentence_buf)
                for sentence in sentences:
                    await speak(sentence)
            if sentence_buf.strip() and not cancel.is_set():
                await speak(sentence_buf)
        finally:
            hub.end(cid)
        await ws.send_json({"type": "done"})

    async def _endpoint(utterance) -> None:
        nonlocal respond_task
        if respond_task is not None and not respond_task.done():
            respond_task.cancel()
            with contextlib.suppress(BaseException):
                await respond_task
        cancel.clear()
        respond_task = asyncio.create_task(respond(utterance))

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            # After a barge the old task may still be winding down — treat as not busy so
            # the student's next words aren't eaten.
            busy = (
                respond_task is not None and not respond_task.done() and not cancel.is_set()
            )
            frame = msg.get("bytes")
            if frame is not None:
                if busy:
                    continue  # half-duplex: mic frames during a reply are dropped
                buffer.extend(frame)
                if len(buffer) > max_buffer_bytes:
                    del buffer[: len(buffer) - max_buffer_bytes]
                if vad.available:
                    await run_in_threadpool(vad.accept, bytes(frame))
                    segment = vad.pop_segment()
                    if segment is not None:
                        buffer.clear()
                        await _endpoint(segment)
                else:
                    seconds = len(frame) / 2 / SAMPLE_RATE
                    if endpointer.accept(seconds, is_speech=_rms_loud(frame)):
                        utt = bytes(buffer)
                        had_speech = endpointer.had_speech
                        buffer.clear()
                        endpointer.reset()
                        if had_speech:
                            await _endpoint(utt)
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                kind = data.get("type")
                if kind == "stop" and not busy:
                    vad.flush()
                    segment = vad.pop_segment() if vad.available else None
                    utt = segment if segment is not None else bytes(buffer)
                    buffer.clear()
                    endpointer.reset()
                    if segment is not None or len(utt):
                        await _endpoint(utt)
                elif kind == "barge":
                    cancel.set()
    except WebSocketDisconnect:
        pass
    finally:
        cancel.set()
        if respond_task is not None:
            respond_task.cancel()
            try:
                await respond_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                log.exception("voice respond task failed during teardown")
