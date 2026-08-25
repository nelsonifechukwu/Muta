# Microphone speech-to-text restoration

## Outcome

The composer microphone records one question, converts it to editable text, and submits that
text through the same `/v1/chat` path as a typed question. The tutor answers in text. The
microphone does not enter the continuous ASR → LLM → TTS voice loop.

## Implementation

1. Add a `transcription_only` handshake mode to `/v1/audio/voice`. It runs the existing
   WebKit-safe PCM capture, VAD, and offline ASR, then returns the transcript without creating a
   conversation, starting inference, or synthesizing speech.
2. Make the microphone a one-shot control. A second click sends `stop` so the server flushes the
   captured audio; it must not close and discard the buffer. Show listening and transcribing
   feedback and disable the control while ASR is running.
3. Put the returned transcript in the composer and submit it through the ordinary text send
   function. This makes the recognized question and text response visible in the normal chat.
4. Cover the backend no-inference invariant and the client stop/transcript/send behavior with
   regression tests, then test a real packaged Mac build with spoken audio.

## Acceptance

- A mic click starts recording and announces the listening state.
- Silence, or a second mic click, produces a transcript instead of discarding the recording.
- The transcript is sent as a normal text question and is visible in the user bubble.
- The response is the ordinary streamed text response; no TTS playback begins.
- `transcription_only` never calls the chat engine or TTS on the audio WebSocket.
