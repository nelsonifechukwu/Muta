"""Utterance endpointing (TDD §6.6, S12).

Deliberately separate from the VAD *model*: deciding "is this 200 ms of audio speech" is
Silero's job, and deciding "has the student finished talking" is a policy — half a second of
trailing silence ends an utterance, ninety seconds ends it regardless. Keeping the policy in
plain Python means the rule that protects the box from a forgotten open mic is unit-tested
rather than trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Endpointer:
    trailing_silence_seconds: float = 0.5
    max_utterance_seconds: float = 90.0

    speech_seconds: float = field(default=0.0, init=False)
    silence_seconds: float = field(default=0.0, init=False)
    total_seconds: float = field(default=0.0, init=False)
    started: bool = field(default=False, init=False)
    reason: str = field(default="", init=False)

    def accept(self, seconds: float, *, is_speech: bool) -> bool:
        """Feed one chunk. Returns True when the utterance is over."""
        self.total_seconds += seconds
        if is_speech:
            self.started = True
            self.speech_seconds += seconds
            self.silence_seconds = 0.0
        elif self.started:
            self.silence_seconds += seconds

        if self.started and self.silence_seconds >= self.trailing_silence_seconds:
            self.reason = "endpoint"
            return True
        if self.total_seconds >= self.max_utterance_seconds:
            # Hard cap: an open mic in a classroom is a 40-minute stream otherwise, and the
            # transcript is charged to a slot's context either way.
            self.reason = "max-duration"
            return True
        return False

    @property
    def had_speech(self) -> bool:
        return self.speech_seconds > 0

    def reset(self) -> None:
        self.speech_seconds = self.silence_seconds = self.total_seconds = 0.0
        self.started = False
        self.reason = ""
