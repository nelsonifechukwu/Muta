"""Read source-bound scalar judges decisions; never infer or recompute grades."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bench.balanced_model_report import load_artifacts
from bench.judges_prompt_report import grade as rubric_definition
from bench.judges_prompt_suite import prompts as judge_prompts

GCP_CONTEXT = "x86_cloud_proxy_gcp_n2_custom_4_8192_2c4t_scalar_b10175"
GCP_BINARY = "379d824db41143559e5524bb8a84d543666fa8ccc1541bfbc0310fb698347d43"
GCP_SETTINGS = {
    "cache_ram_mib": 256,
    "context_size": 4096,
    "embedded_chat_template": True,
    "external_system_prompt": False,
    "gpu_layers": 0,
    "max_tokens": 1024,
    "seed": 3407,
    "temperature": 0.0,
    "threads": 2,
    "top_p": 1.0,
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _source_path(campaign: Path, value: str) -> Path:
    source = Path(value)
    if not source.is_absolute():
        source = campaign.parents[2] / source
    if source.resolve() != (campaign / "raw/judges-responses.jsonl").resolve():
        raise ValueError("review source is not the GCP scalar judges treatment")
    return source


def _prefix(campaign: Path, snapshot: dict) -> tuple[Path, list[bytes]]:
    source = _source_path(campaign, snapshot["path"])
    size = _integer(snapshot["bytes"], "snapshot bytes")
    with source.open("rb") as handle:
        data = handle.read(size)
    if not size or len(data) != size or _sha(data) != snapshot["sha256"]:
        raise ValueError("reviewed GCP source prefix changed")
    if not data.endswith(b"\n"):
        raise ValueError("reviewed prefix must end at a complete JSONL record")
    lines = data[:-1].split(b"\n")
    if len(lines) != _integer(snapshot["lines"], "snapshot lines") or not all(lines):
        raise ValueError("reviewed prefix line count mismatch")
    return source, lines


def _final_text(answer: str) -> str:
    """Exclude literal reasoning blocks, in addition to separate reasoning_content."""
    if "<think>" not in answer:
        return answer.strip()
    if answer.count("<think>") != 1 or answer.count("</think>") > 1:
        raise ValueError("ambiguous literal reasoning blocks")
    before, thinking = answer.split("<think>", 1)
    if before.strip():
        raise ValueError("unexpected final text before literal reasoning")
    return thinking.split("</think>", 1)[1].strip() if "</think>" in thinking else ""


def _execution(record: dict) -> None:
    if record.get("hardware_context") != GCP_CONTEXT:
        raise ValueError("record is not the pinned scalar GCP context")
    if record.get("server_sha256") != GCP_BINARY:
        raise ValueError("record is not the pinned scalar server")
    if record.get("settings") != GCP_SETTINGS:
        raise ValueError("record scalar settings mismatch")


def _criteria(entry: dict) -> int:
    criteria = entry.get("items", entry.get("criteria"))
    # Existing rubric helper supplies labels/weights only. Never pass model output.
    canonical = rubric_definition(entry["id"], "")["items"]
    if not isinstance(criteria, list) or [(c["criterion"], c["weight"]) for c in criteria] != [
        (c["criterion"], c["weight"]) for c in canonical
    ]:
        raise ValueError("manual criterion labels or weights differ from rubric")
    points = 0
    for criterion in criteria:
        weight = _integer(criterion["weight"], "criterion weight")
        if type(criterion["passed"]) is not bool:
            raise ValueError("manual criterion decision must be boolean")
        earned = weight if criterion["passed"] else 0
        for key in ("points", "points_awarded"):
            if key in criterion and _integer(criterion[key], key) != earned:
                raise ValueError("manual criterion awarded points mismatch")
        points += earned
    if points != _integer(entry["score"], "prompt score"):
        raise ValueError("manual prompt score sum mismatch")
    if entry.get("max_score") != 10:
        raise ValueError("manual prompt maximum mismatch")
    return points


def manual_gcp_judges(campaign: Path) -> dict[str, dict]:
    """Return validated manual scalar decisions keyed by exact artifact filename."""
    campaign = campaign.resolve()
    paths = sorted((campaign / "manual-judges-gcp").glob("*.json"))
    if not paths:
        return {}
    _, artifacts = load_artifacts(campaign / "artifacts.csv")
    artifact_map = {a["test_artifact"]: a for a in artifacts}
    if len(artifact_map) != len(artifacts):
        raise ValueError("duplicate artifact in model manifest")
    expected = {p.id: p for p in judge_prompts()}
    result = {}
    for path in paths:
        data = json.loads(path.read_text())
        if data.get("official_judge_score") is not False:
            raise ValueError("manual review must be labelled unofficial")
        snapshot = data["source_snapshot"]
        source, lines = _prefix(campaign, snapshot)
        raw = [json.loads(line) for line in lines]
        if "shared_execution" in data:
            _execution(data["shared_execution"])
        for model in data["models"]:
            name = model.get("artifact", model.get("model"))
            if name in result:
                raise ValueError(f"duplicate manual GCP model: {name}")
            if (
                name not in artifact_map
                or model["model_sha256"] != artifact_map[name]["test_sha256"]
            ):
                raise ValueError("manual GCP model manifest hash mismatch")
            entries = model["prompts"]
            if len(entries) != 10 or {p["id"] for p in entries} != set(expected):
                raise ValueError("manual GCP duplicate or missing canonical IDs")
            selected = [r for r in raw if r.get("model") == name]
            if len(selected) != 10 or {r["id"] for r in selected} != set(expected):
                raise ValueError("raw GCP duplicate or missing canonical IDs")
            if "source_path" in model and _source_path(campaign, model["source_path"]) != source:
                raise ValueError("model source differs from source snapshot")
            if model.get("source_sha256", snapshot["sha256"]) != snapshot["sha256"]:
                raise ValueError("model source hash differs from source snapshot")
            totals = {"automated": 0, "human judge": 0}
            finished = truncated = final_count = 0
            for entry in entries:
                line = _integer(entry["source_line"], "source line")
                if not 1 <= line <= len(lines):
                    raise ValueError("manual GCP source line out of range")
                record = raw[line - 1]
                if _sha(lines[line - 1]) != entry["record_sha256"]:
                    raise ValueError("manual GCP record byte hash mismatch")
                if record.get("id") != entry["id"] or record.get("model") != name:
                    raise ValueError("manual GCP source line identity mismatch")
                if record.get("model_sha256") != model["model_sha256"]:
                    raise ValueError("raw model hash differs from manifest")
                prompt = expected[entry["id"]]
                if any(record.get(k) != getattr(prompt, k) for k in ("text", "source", "title")):
                    raise ValueError("raw GCP canonical prompt text or metadata mismatch")
                _execution(record)
                for field, hash_key in (
                    ("answer", "answer_sha256"),
                    ("reasoning_content", "reasoning_sha256"),
                    ("text", "prompt_sha256"),
                ):
                    if not isinstance(record.get(field), str):
                        raise TypeError("invalid raw GCP response text")
                    if _sha(record[field].encode()) != entry.get(hash_key):
                        raise ValueError("manual GCP response content hash mismatch")
                if record["finish_reason"] not in {"stop", "length"}:
                    raise ValueError("unsupported GCP completion status")
                if entry["finish_reason"] != record["finish_reason"]:
                    raise ValueError("manual GCP finish reason mismatch")
                final = _final_text(record["answer"])
                has_final = bool(final)
                if "final_sha256" in entry and _sha(final.encode()) != entry["final_sha256"]:
                    raise ValueError("manual GCP extracted final hash mismatch")
                state = (
                    "finished"
                    if has_final and record["finish_reason"] == "stop"
                    else ("partial_final" if has_final else "absent")
                )
                if "final_output_status" in entry and entry["final_output_status"] != state:
                    raise ValueError("manual GCP final output status mismatch")
                legacy_state = {
                    "finished": "finished",
                    "partial_final": "truncated_final_fragment",
                    "absent": "reasoning_only",
                }[state]
                if "final_status" in entry and entry["final_status"] != legacy_state:
                    raise ValueError("manual GCP final status mismatch")
                for key in ("source", "title"):
                    if key in entry and entry[key] != record[key]:
                        raise ValueError("manual GCP prompt metadata mismatch")
                final_count += has_final
                finished += has_final and record["finish_reason"] == "stop"
                truncated += record["finish_reason"] == "length"
                points = _criteria(entry)
                if not has_final and points:
                    raise ValueError("reasoning-only response cannot earn final-answer points")
                totals[prompt.source] += points
            score = model.get("score", model.get("manual_total"))
            if _integer(score, "model score") != sum(totals.values()):
                raise ValueError("manual GCP model score sum mismatch")
            for key, actual in (
                ("automated_score", totals["automated"]),
                ("human_score", totals["human judge"]),
                ("finished_final_count", finished),
                ("truncated_response_count", truncated),
                ("any_final_text_count", final_count),
                ("reasoning_only_count", 10 - final_count),
                ("response_count", 10),
                ("max_score", 100),
            ):
                if _integer(model[key], key) != actual:
                    raise ValueError(f"manual GCP {key} mismatch")
            if "partial_final_count" in model and (
                _integer(model["partial_final_count"], "partial_final_count")
                != final_count - finished
            ):
                raise ValueError("manual GCP partial final count mismatch")
            result[name] = {
                "score": score,
                "total": score,
                "finished": finished,
                "truncated": truncated,
                "source": path,
                "model_sha256": model["model_sha256"],
                "records": {entry["id"]: entry for entry in entries},
                "raw_records": {record["id"]: record for record in selected},
                "response_source": source,
                "response_sha256": snapshot["sha256"],
                "response_prefix_bytes": snapshot["bytes"],
                "response_prefix_lines": snapshot["lines"],
            }
    return result
