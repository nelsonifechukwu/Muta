"""The learning twin — a student's persistent state (TDD §8.4).

`data/twins/{student}.json`: mastery per curriculum node, an error taxonomy, pace stats and
the last few session summaries. Two jobs, one artifact:

* **personalisation** — what the tutor knows about this student;
* **the session-summary layer of the prompt** (§7.3), which is also what a restore-miss
  re-prefills from (§8.3). Suspend/resume and personalisation ride the same file, so a twin
  that is stale or corrupt degrades both at once.

Hence: every write is atomic (tmp → fsync → rename). A half-written twin after a power cut in
a Nigerian classroom is not a hypothetical, and JSON that fails to parse would take the
student's history with it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
MAX_SUMMARIES = 5  # the last N, because this text goes into every prompt


@dataclass
class LearningTwin:
    student_id: str
    #: curriculum node -> mastery in [0, 1]
    mastery: dict[str, float] = field(default_factory=dict)
    #: error tag -> count (from marking, §6.5/S6)
    error_counts: dict[str, int] = field(default_factory=dict)
    #: rolling stats: turns, minutes, questions answered
    pace: dict[str, float] = field(default_factory=dict)
    summaries: list[str] = field(default_factory=list)
    version: int = SCHEMA_VERSION

    # --- updates ----------------------------------------------------------------------
    def record_mastery(self, node: str, score: float, *, weight: float = 0.3) -> float:
        """Exponentially-weighted update, so one lucky answer does not declare mastery and
        one slip does not erase it."""
        score = max(0.0, min(1.0, score))
        current = self.mastery.get(node)
        updated = score if current is None else (1 - weight) * current + weight * score
        self.mastery[node] = round(updated, 4)
        return self.mastery[node]

    def record_error(self, tag: str, count: int = 1) -> int:
        self.error_counts[tag] = self.error_counts.get(tag, 0) + count
        return self.error_counts[tag]

    def add_summary(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.summaries.append(text)
        del self.summaries[:-MAX_SUMMARIES]

    def bump(self, key: str, amount: float = 1.0) -> float:
        self.pace[key] = round(self.pace.get(key, 0.0) + amount, 3)
        return self.pace[key]

    # --- reads ------------------------------------------------------------------------
    def weakest(self, n: int = 3) -> list[str]:
        return [node for node, _ in sorted(self.mastery.items(), key=lambda kv: kv[1])[:n]]

    def top_errors(self, n: int = 3) -> list[str]:
        return [tag for tag, _ in sorted(self.error_counts.items(), key=lambda kv: -kv[1])[:n]]

    def prompt_summary(self, *, max_chars: int = 600) -> str:
        """The §7.3 session-summary layer. Deliberately short: it sits *after* the shared
        prefix, so every character here is per-student context that cannot be cache-reused."""
        parts: list[str] = []
        if weak := self.weakest():
            parts.append("Working on: " + ", ".join(weak) + ".")
        if errors := self.top_errors():
            parts.append("Recurring slips: " + ", ".join(errors) + ".")
        if self.summaries:
            parts.append("Last session: " + self.summaries[-1])
        text = " ".join(parts)
        return text[:max_chars].rstrip()


class TwinStore:
    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, student_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in student_id)
        return self.directory / f"{safe}.json"

    def load(self, student_id: str) -> LearningTwin:
        path = self.path_for(student_id)
        if not path.is_file():
            return LearningTwin(student_id=student_id)
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError:
            # A corrupt twin costs personalisation, not the session. Keep the bad file for
            # inspection rather than overwriting the evidence.
            path.rename(path.with_suffix(".json.corrupt"))
            return LearningTwin(student_id=student_id)
        raw.pop("student_id", None)
        known = {f for f in LearningTwin.__dataclass_fields__ if f != "student_id"}
        return LearningTwin(student_id=student_id, **{k: v for k, v in raw.items() if k in known})

    def save(self, twin: LearningTwin) -> Path:
        """tmp → fsync → rename. The rename is atomic on POSIX, so a reader sees either the
        old twin or the new one, never a truncated file."""
        path = self.path_for(twin.student_id)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.directory), prefix=".twin-", suffix=".json")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(asdict(twin), fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return path

    def all_ids(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.json"))
