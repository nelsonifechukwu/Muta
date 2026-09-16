"""Source-checked, ungraded views of scalar judge requests, including failed runs.

``load_gcp_captures`` reads each input once. ``render_gcp_capture`` renders only
that in-memory snapshot; it neither reads growing files nor assigns grades.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bench.campaign_gcp_reviews import GCP_BINARY, GCP_CONTEXT, GCP_SETTINGS, _final_text
from bench.judges_prompt_suite import prompts


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    data: bytes
    exists: bool

    @property
    def prefix(self) -> bytes:
        """Only newline-terminated records are committed to this snapshot."""
        return self.data[: self.data.rfind(b"\n") + 1]

    @property
    def lines(self) -> tuple[bytes, ...]:
        return tuple(self.prefix[:-1].split(b"\n")) if self.prefix else ()

    @property
    def metadata(self) -> dict:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "snapshot_sha256": _sha(self.data),
            "snapshot_bytes": len(self.data),
            "prefix_sha256": _sha(self.prefix),
            "prefix_bytes": len(self.prefix),
            "prefix_lines": len(self.lines),
            "uncommitted_tail_bytes": len(self.data) - len(self.prefix),
        }


@dataclass(frozen=True)
class CapturedLine:
    source_line: int
    raw: bytes

    @property
    def record(self) -> dict:
        value = json.loads(self.raw)
        if not isinstance(value, dict):
            raise TypeError("capture JSONL record must be an object")
        return value

    @property
    def sha256(self) -> str:
        return _sha(self.raw)


@dataclass(frozen=True)
class GcpCapture:
    artifact_json: str
    responses: tuple[CapturedLine, ...]
    events: tuple[CapturedLine, ...]
    response_source: SourceSnapshot
    event_source: SourceSnapshot

    @property
    def artifact(self) -> dict:
        return json.loads(self.artifact_json)

    @property
    def summary(self) -> dict:
        return _validate_capture(self)


@dataclass(frozen=True)
class CaptureBatch:
    models: tuple[GcpCapture, ...]
    responses: SourceSnapshot
    events: SourceSnapshot
    manifest_sha256: str

    @property
    def by_model(self) -> dict[str, GcpCapture]:
        return {capture.artifact["test_artifact"]: capture for capture in self.models}


def _snapshot(path: Path) -> SourceSnapshot:
    try:
        return SourceSnapshot(path, path.read_bytes(), True)
    except FileNotFoundError:
        return SourceSnapshot(path, b"", False)


def _records(source: SourceSnapshot) -> tuple[CapturedLine, ...]:
    result = []
    for number, raw in enumerate(source.lines, 1):
        if not raw.strip():
            raise ValueError("blank committed capture record")
        entry = CapturedLine(number, raw)
        _ = entry.record  # Reject malformed committed JSON before selecting models.
        result.append(entry)
    return tuple(result)


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("capture timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("capture timestamp must have a timezone")
    return parsed


def _number(value: object, *, integer: bool = False) -> None:
    if type(value) not in ((int,) if integer else (int, float)):
        raise ValueError("invalid capture numeric value")
    if not math.isfinite(value) or value < 0:
        raise ValueError("invalid capture numeric range")


def _execution(record: dict, artifact: dict) -> None:
    if record.get("model_sha256") != artifact["test_sha256"]:
        raise ValueError("capture model hash mismatch")
    if record.get("hardware_context") != GCP_CONTEXT or record.get("server_sha256") != GCP_BINARY:
        raise ValueError("capture scalar execution identity mismatch")
    settings = record.get("settings")
    if not isinstance(settings, dict) or settings != GCP_SETTINGS:
        raise ValueError("capture scalar settings mismatch")
    for key, expected in GCP_SETTINGS.items():
        value = settings[key]
        if isinstance(expected, bool):
            if type(value) is not bool:
                raise ValueError("capture boolean setting type mismatch")
        else:
            _number(value, integer=type(expected) is int)


def _command(event: dict, artifact: dict) -> None:
    command = event.get("command")
    if (
        not isinstance(command, list)
        or len(command) != 16
        or not all(isinstance(value, str) for value in command)
    ):
        raise ValueError("capture start command is missing or malformed")
    server, model = Path(command[0]), Path(command[2])
    if (
        not server.is_absolute()
        or server.name != "llama-server"
        or not model.is_absolute()
        or model.name != artifact["test_artifact"]
        or ".." in server.parts
        or ".." in model.parts
    ):
        raise ValueError("capture start command paths mismatch")
    expected = [
        command[0],
        "--model",
        command[2],
        "--host",
        "127.0.0.1",
        "--port",
        "18081",
        "--ctx-size",
        "4096",
        "--threads",
        "2",
        "--n-gpu-layers",
        "0",
        "--cache-ram",
        "256",
        "--jinja",
    ]
    if command != expected:
        raise ValueError("capture start command disagrees with pinned settings")


def _validate_capture(capture: GcpCapture) -> dict:
    artifact = capture.artifact
    name = artifact["test_artifact"]
    for source, selected in (
        (capture.response_source, capture.responses),
        (capture.event_source, capture.events),
    ):
        bound = tuple(entry for entry in _records(source) if entry.record.get("model") == name)
        if bound != selected:
            raise ValueError("capture selected records differ from source snapshot")
    expected = {p.id: p for p in prompts()}
    found = {}
    row_times = []
    for entry in capture.responses:
        if not 1 <= entry.source_line <= len(capture.response_source.lines):
            raise ValueError("capture response line out of range")
        if entry.raw != capture.response_source.lines[entry.source_line - 1]:
            raise ValueError("capture response snapshot binding mismatch")
        row = entry.record
        if row.get("model") != name:
            raise ValueError("capture response model mismatch")
        _execution(row, artifact)
        pid = row.get("id")
        if not isinstance(pid, str) or pid not in expected or pid in found:
            raise ValueError("unexpected or duplicate capture prompt ID")
        if any(row.get(k) != getattr(expected[pid], k) for k in ("text", "source", "title")):
            raise ValueError("capture canonical prompt metadata mismatch")
        if any(not isinstance(row.get(k), str) for k in ("answer", "reasoning_content")):
            raise ValueError("capture requires answer and reasoning strings")
        if row.get("finish_reason") not in {"stop", "length"}:
            raise ValueError("unsupported capture finish reason")
        usage = row.get("usage")
        if not isinstance(usage, dict):
            raise TypeError("capture usage must be an object")
        for key in ("completion_tokens", "prompt_tokens", "total_tokens"):
            _number(usage.get(key), integer=True)
        if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
            raise ValueError("capture token totals mismatch")
        if usage["completion_tokens"] > GCP_SETTINGS["max_tokens"]:
            raise ValueError("capture exceeds local token cap")
        _number(row.get("wall_s"))
        row_times.append(_time(row.get("ts")))
        _final_text(row["answer"])  # Fail closed on ambiguous literal think markup.
        found[pid] = row
    if row_times != sorted(row_times):
        raise ValueError("capture responses are out of time order")

    start = failure = stop = None
    last_time = None
    for entry in capture.events:
        if not 1 <= entry.source_line <= len(capture.event_source.lines):
            raise ValueError("capture event line out of range")
        if entry.raw != capture.event_source.lines[entry.source_line - 1]:
            raise ValueError("capture event snapshot binding mismatch")
        event = entry.record
        if event.get("model") != name or event.get("hardware_context") != GCP_CONTEXT:
            raise ValueError("capture event identity mismatch")
        current_time = _time(event.get("ts"))
        if last_time is not None and current_time < last_time:
            raise ValueError("capture events are out of time order")
        last_time = current_time
        kind = event.get("event")
        if kind == "model_start":
            if start is not None:
                raise ValueError("duplicate capture start event")
            _execution(event, artifact)
            _command(event, artifact)
            start = current_time
        elif kind == "model_failure":
            if start is None or stop is not None or failure is not None:
                raise ValueError("invalid capture failure lifecycle")
            if not isinstance(event.get("error"), str) or not event["error"]:
                raise ValueError("capture failure requires recorded error text")
            failure = current_time
        elif kind == "model_stop":
            if start is None or stop is not None:
                raise ValueError("invalid capture stop lifecycle")
            stop = current_time
        else:
            raise ValueError("unsupported scalar capture event")
    if start is not None and any(t < start for t in row_times):
        raise ValueError("capture response predates model start")
    terminal = failure if failure is not None else stop
    if terminal is not None and any(t > terminal for t in row_times):
        raise ValueError("capture response follows terminal model event")

    count = len(found)
    if failure is not None:
        status = "failed"
    elif count and start is None:
        status = "awaiting_start_event"
    elif count == len(expected) and stop is not None:
        status = "complete_unreviewed"
    elif count == len(expected):
        status = "awaiting_stop_event"
    elif stop is not None:
        status = "stopped_incomplete"
    elif start is not None:
        status = "partial" if count else "started_no_responses"
    else:
        status = "not_started"
    return {
        "model": name,
        "model_sha256": artifact["test_sha256"],
        "status": status,
        "response_count": count,
        "expected_count": len(expected),
        "missing_ids": [pid for pid in expected if pid not in found],
        "finished_final_count": sum(
            r["finish_reason"] == "stop" and bool(_final_text(r["answer"])) for r in found.values()
        ),
        "truncated_response_count": sum(r["finish_reason"] == "length" for r in found.values()),
        "failure_recorded": failure is not None,
        "start_recorded": start is not None,
        "stop_recorded": stop is not None,
        "response_snapshot": capture.response_source.metadata,
        "event_snapshot": capture.event_source.metadata,
    }


def load_gcp_captures(campaign: Path) -> CaptureBatch:
    """Load all manifest artifacts, without grades or guesses from another host."""
    campaign = campaign.resolve()
    manifest = (campaign / "artifacts.csv").read_bytes()
    artifacts = list(csv.DictReader(io.StringIO(manifest.decode("utf-8"))))
    by_name = {}
    for artifact in artifacts:
        name = artifact.get("test_artifact")
        if (
            not isinstance(name, str)
            or not name.lower().endswith(".gguf")
            or Path(name).name != name
            or "\\" in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
        ):
            raise ValueError("invalid capture artifact filename")
        if name in by_name:
            raise ValueError("duplicate capture artifact")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact.get("test_sha256", "")):
            raise ValueError("invalid capture artifact hash")
        by_name[name] = artifact
    response_source = _snapshot(campaign / "raw/judges-responses.jsonl")
    event_source = _snapshot(campaign / "raw/judges-events.jsonl")
    response_rows, event_rows = _records(response_source), _records(event_source)
    for entry in (*response_rows, *event_rows):
        if entry.record.get("model") not in by_name:
            raise ValueError("capture references model absent from manifest")
    running = None
    for entry in event_rows:
        event = entry.record
        if event.get("event") == "model_start":
            if running is not None:
                raise ValueError("overlapping scalar model lifecycle events")
            running = event["model"]
        elif event.get("event") == "model_stop":
            if running != event["model"]:
                raise ValueError("invalid scalar stop lifecycle")
            running = None
    captures = []
    for name, artifact in by_name.items():
        capture = GcpCapture(
            json.dumps(artifact, sort_keys=True),
            tuple(r for r in response_rows if r.record["model"] == name),
            tuple(r for r in event_rows if r.record["model"] == name),
            response_source,
            event_source,
        )
        _validate_capture(capture)
        captures.append(capture)
    return CaptureBatch(tuple(captures), response_source, event_source, _sha(manifest))


def _literal(text: str) -> str:
    fence = "`" * max(3, 1 + max((len(s) for s in re.findall(r"`+", text)), default=0))
    return f"{fence}text\n{text}\n{fence}"


def _label(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+.!|<>-])", r"\\\1", " ".join(text.splitlines()))


def render_gcp_capture(capture: GcpCapture) -> str:
    """Return capture-only Markdown; do not reread sources or write an output."""
    summary = _validate_capture(capture)
    records = {entry.record["id"]: entry for entry in capture.responses}
    lines = [
        f"# {_label(summary['model'])}: GCP scalar judge captures",
        "",
        f"Status: {summary['status']}. Captured responses: {summary['response_count']}/10.",
        "",
        "Capture only: no score, rank or correctness assessment is assigned. Missing responses are not zero scores. A saved response may contain no delivered final answer.",
        "",
        "This is the GCP scalar treatment: two CPU threads, no GPU, embedded chat template, no external system prompt, temperature 0, top-p 1 and seed 3407. The local output allowance is 1,024 tokens including reasoning, not an asserted official judge limit.",
        "",
        "## Source snapshot",
        "",
        _literal(json.dumps(summary, indent=2)),
        "",
        "## Recorded scalar lifecycle events",
        "",
    ]
    if not capture.events:
        lines += ["No scalar lifecycle event was captured in this snapshot.", ""]
    for event in capture.events:
        lines += [
            f"Source line {event.source_line}; SHA-256 {event.sha256}.",
            "",
            _literal(event.raw.decode("utf-8")),
            "",
        ]
    for prompt in prompts():
        lines += [
            f"## {prompt.id}: {prompt.title}",
            "",
            "### Prompt",
            "",
            _literal(prompt.text),
            "",
        ]
        entry = records.get(prompt.id)
        if entry is None:
            lines += [
                "**Missing response:** no saved scalar response for this prompt in this snapshot. No score assigned.",
                "",
            ]
            continue
        row = entry.record
        final_state = (
            "absent"
            if not _final_text(row["answer"])
            else ("finished" if row["finish_reason"] == "stop" else "partial")
        )
        lines += [
            f"Finish reason: {row['finish_reason']}. Output tokens: {row['usage']['completion_tokens']}. Final-text delivery: {final_state}.",
            "",
            f"Source line {entry.source_line}; SHA-256 {entry.sha256}.",
            "",
            "### Returned answer field (verbatim)",
            "",
            _literal(row["answer"]),
            "",
            "### Separate reasoning field (verbatim, ungraded)",
            "",
            _literal(row["reasoning_content"]),
            "",
        ]
    return "\n".join(lines) + "\n"
