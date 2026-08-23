# Voice turn response recovery

## Problem and evidence

The live microphone path transcribes and persists the student's utterance, but can leave the chat with no assistant response. Production evidence from 23 August shows the exact transcribed question persisted as a user message while no assistant message or active generation followed. The screenshot's audio chip identifies the WebSocket voice path rather than the audio-file upload path.

Two failures combine into the silent result:

1. A model stream that ends after reasoning but before answer content is treated as a successful turn, so only the user transcript is persisted. This is possible when a small thinking model reaches a clean stop without emitting its final-answer channel.
2. The browser handles `voice-turn-failed` by finalizing an empty assistant message, which removes the only durable indication that the turn failed; the toast is transient.

This work follows the ROADMAP's Tuesday 4 August voice input flow and Sprint 5 audio-response requirements. It preserves the contract-first boundary and does not change ASR or TTS model selection.

## Scope

- Reproduce the post-transcript failure in the WebSocket route with a focused regression test.
- Route a reasoning-only/empty stream through the existing bounded direct-answer recovery before the turn can complete.
- Keep a durable in-chat failure state when recovery is exhausted instead of finalizing an empty response.
- Treat an unexpected microphone WebSocket close as a durable failed reply; only an explicit student stop may finalize a partial response normally.
- Show queue/start state through the existing assistant placeholder so a submitted voice turn never appears inert.
- Leave wake-word activation, audio-upload transcription, and unrelated resource/citation work unchanged.

## Verification

- Run the focused gateway voice tests and UI voice-state regression tests.
- Run the relevant gateway and UI suites, followed by the full test suite if focused checks pass.
- Have an adversarial reviewer inspect the lifecycle, cancellation, and UI terminal states.
- Commit only this fix and its tests/plan, push `main`, deploy that commit to the GCP host, and verify readiness plus a complete live voice WebSocket turn.

## Deployment safety

The local worktree already contains unrelated user changes; they will remain unstaged. The GCP checkout has untracked benchmark artifacts; deployment will use a fast-forward pull and will not remove them. Before replacing the currently manual gateway process, confirm its command and configured model, then start the existing user service and verify the deployed commit and health endpoints.
