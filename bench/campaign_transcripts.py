"""Publish source-checked benchmark responses without recomputing model grades."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from bench.balanced_model_report import load_artifacts, read_jsonl
from bench.campaign_gcp_captures import load_gcp_captures, render_gcp_capture
from bench.campaign_gcp_reviews import GCP_BINARY, GCP_CONTEXT, GCP_SETTINGS, manual_gcp_judges
from bench.judges_prompt_report import grade as rubric_definition
from bench.judges_prompt_suite import prompts as judge_prompts
from bench.stem_prompt_suite import prompts as stem_prompts

MAC_CONTEXT = "apple_m4_pro_24gib_macos_metal_b10175"
MAC_BINARY = "f497d6b948174173f8159b6fa46c7b4816e2ecfd306ae9c0f7f11e6a7a79af88"


def expected_settings(stage: str) -> dict:
    common = {
        "threads": 2,
        "gpu_layers": 99,
        "cache_ram_mib": 256,
        "temperature": 0.0,
        "external_system_prompt": False,
    }
    if stage == "judges":
        return {
            **common,
            "context_size": 4096,
            "seed": 3407,
            "max_tokens": 1024,
            "embedded_chat_template": True,
            "top_p": 1.0,
        }
    if stage == "stem":
        return {
            **common,
            "context_size": 2048,
            "seed": 42,
            "max_tokens": {"multiple_choice": 256, "written": 512},
            "embedded_chat_template": False,
            "cache_prompt": False,
        }
    raise ValueError("unknown stage")


def read_snapshot(path: Path) -> tuple[list[dict], str | None]:
    if not path.exists():
        return [], None
    data = path.read_bytes()
    return (
        [json.loads(line) for line in data.decode().splitlines() if line.strip()],
        hashlib.sha256(data).hexdigest(),
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literal(text: str) -> str:
    """Keep generated Markdown/HTML and embedded fences inert and verbatim."""
    fence = "`" * max(3, 1 + max((len(x) for x in re.findall(r"`+", text)), default=0))
    return f"{fence}text\n{text}\n{fence}"


def link(target: Path, document: Path) -> str:
    return os.path.relpath(target, document.parent).replace(os.sep, "/")


def model_label(artifact: dict) -> str:
    name, quant = artifact["model"], artifact["quantization"]
    return name if quant.casefold() in name.casefold() else f"{name} · {quant}"


def validate_records(rows: list[dict], artifact: dict, stage: str, config: dict) -> dict[str, dict]:
    if (
        config.get("model") != artifact["test_artifact"]
        or config.get("model_sha256") != artifact["test_sha256"]
    ):
        raise ValueError("configuration model mismatch")
    if config.get("hardware_context") != MAC_CONTEXT or config.get("server_sha256") != MAC_BINARY:
        raise ValueError("configuration is not the pinned Mac treatment")
    if config.get("settings") != expected_settings(stage):
        raise ValueError("configuration settings mismatch")
    expected = {p.id: p for p in (judge_prompts() if stage == "judges" else stem_prompts())}
    result = {}
    contexts = set()
    binaries = set()
    settings = set()
    for row in rows:
        pid = row["id"]
        if pid not in expected or pid in result:
            raise ValueError(f"unexpected or duplicate prompt: {pid}")
        if row.get("model") != artifact["test_artifact"]:
            raise ValueError("model filename mismatch")
        if row.get("model_sha256") != artifact["test_sha256"]:
            raise ValueError("model hash mismatch")
        if row.get("text") != expected[pid].text:
            raise ValueError(f"prompt text mismatch: {pid}")
        context, binary = row.get("hardware_context"), row.get("server_sha256")
        if context != MAC_CONTEXT or binary != MAC_BINARY:
            raise ValueError("record execution provenance mismatch")
        if not isinstance(row.get("answer"), str) or not isinstance(row.get("finish_reason"), str):
            raise TypeError("missing or invalid returned-answer schema")
        if "reasoning_content" in row and not isinstance(row["reasoning_content"], str):
            raise TypeError("invalid reasoning field")
        contexts.add(context)
        binaries.add(binary)
        if stage == "judges":
            if row.get("settings") != expected_settings(stage):
                raise ValueError("judges settings mismatch")
            settings.add(json.dumps(row["settings"], sort_keys=True))
        result[pid] = row
    if len(contexts) > 1 or len(binaries) > 1 or len(settings) > 1:
        raise ValueError("mixed execution contexts")
    return result


def manual_judges(campaign: Path) -> dict[str, dict]:
    result = {}
    for path in sorted((campaign / "manual-judges").glob("*.json")):
        payload = json.loads(path.read_text())
        for model in payload.get("models", []):
            artifact = model.get("artifact", model.get("model"))
            source = Path(model.get("source_path", model.get("source_response_file", "")))
            if not source.is_absolute():
                source = campaign.parents[2] / source
            expected = model.get("source_sha256", model.get("response_file_sha256"))
            source_rows, source_digest = read_snapshot(source)
            if source_digest != expected or source_digest is None:
                raise ValueError(f"manual review source changed: {artifact}")
            # Join only main Mac records, never the pilot or a GCP replay.
            if (
                source.resolve()
                != (campaign / "mac-accuracy" / artifact / "judges/responses.jsonl").resolve()
            ):
                raise ValueError("manual judges source is not the main Mac treatment")
            if artifact in result:
                raise ValueError(f"duplicate manual judges review: {artifact}")
            records = model["prompts"]
            if {p["id"] for p in records} != {p.id for p in judge_prompts()} or len(records) != 10:
                raise ValueError("manual judges prompt coverage mismatch")
            config = json.loads((source.parent / "config.json").read_text())
            by_id = validate_records(
                source_rows,
                {"test_artifact": artifact, "test_sha256": model["model_sha256"]},
                "judges",
                config,
            )
            if len(by_id) != 10:
                raise ValueError("manual review attached to incomplete raw source")
            total = model.get("score", model.get("manual_total"))
            if total != sum(p["score"] for p in records):
                raise ValueError("manual judges sum mismatch")
            for p in records:
                criteria = p.get("items", p.get("criteria"))
                # Read labels and weights only. Keyword matches do not supply decisions.
                canonical = rubric_definition(p["id"], "")["items"]
                if [(c["criterion"], c["weight"]) for c in criteria] != [
                    (c["criterion"], c["weight"]) for c in canonical
                ]:
                    raise ValueError("manual criterion definitions mismatch")
                if any(type(c["passed"]) is not bool for c in criteria):
                    raise ValueError("manual criterion decision must be boolean")
                if sum(c["weight"] for c in criteria) != 10:
                    raise ValueError("manual rubric weight mismatch")
                if sum(c["weight"] for c in criteria if c["passed"]) != p["score"]:
                    raise ValueError("manual criterion sum mismatch")
            result[artifact] = {
                "total": total,
                "records": {p["id"]: p for p in records},
                "source": path,
                "model_sha256": model["model_sha256"],
                "response_sha256": source_digest,
            }
    return result


def manual_stem(campaign: Path) -> dict[str, dict]:
    """Validate completed Mac semantic ledgers; do not infer or assign any grade."""
    _, artifacts = load_artifacts(campaign / "artifacts.csv")
    artifact_map = {a["test_artifact"]: a for a in artifacts}
    expected = {p.id: p for p in stem_prompts()}
    result = {}
    for path in sorted((campaign / "manual-stem-mac").glob("*.json")):
        data = json.loads(path.read_text())
        model = data["model"]
        if model in result:
            raise ValueError("duplicate manual STEM model")
        artifact = artifact_map[model]
        if data["model_sha256"] != artifact["test_sha256"]:
            raise ValueError("manual STEM model hash mismatch")
        source = Path(data["source"]["path"])
        if not source.is_absolute():
            source = campaign.parents[2] / source
        if (
            source.resolve()
            != (campaign / "mac-accuracy" / model / "stem/responses.jsonl").resolve()
        ):
            raise ValueError("manual STEM source is not the main Mac treatment")
        rows, fingerprint = read_snapshot(source)
        if fingerprint != data["source"]["sha256"] or fingerprint is None:
            raise ValueError("manual STEM source changed")
        config = json.loads((source.parent / "config.json").read_text())
        by_id = validate_records(rows, artifact, "stem", config)
        entries = data["results"]
        if len(by_id) != 100 or len(entries) != 100 or {e["id"] for e in entries} != set(expected):
            raise ValueError("manual STEM prompt coverage mismatch")
        totals = {}
        for entry in entries:
            pid = entry["id"]
            row = by_id[pid]
            if entry["source_line"] < 1 or entry["source_line"] > len(rows):
                raise ValueError("manual STEM source line out of range")
            if rows[entry["source_line"] - 1]["id"] != pid:
                raise ValueError("manual STEM source line mismatch")
            if hashlib.sha256(row["answer"].encode()).hexdigest() != entry["response_sha256"]:
                raise ValueError("manual STEM answer hash mismatch")
            if any(
                entry[k] != row[k]
                for k in ("subject", "format", "expected", "finish_reason", "generated_tokens")
            ):
                raise ValueError("manual STEM record metadata mismatch")
            if entry["expected"] != expected[pid].expected:
                raise ValueError("manual STEM expected answer mismatch")
            if row["subject"] != expected[pid].subject or row["format"] != expected[pid].format:
                raise ValueError("manual STEM category differs from canonical prompt")
            if any(type(entry[k]) is not bool for k in ("strict_pass", "core_answer_correct")):
                raise ValueError("manual STEM decision must be boolean")
            if entry["strict_pass"] and not entry["core_answer_correct"]:
                raise ValueError("strict STEM pass cannot have an incorrect core")
            if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
                raise ValueError("manual STEM decision lacks a reason")
            category = f"{row['subject']}_{row['format']}"
            subtotal = totals.setdefault(
                category, {"strict_pass": 0, "core_correct": 0, "total": 0}
            )
            subtotal["strict_pass"] += int(entry["strict_pass"])
            subtotal["core_correct"] += int(entry["core_answer_correct"])
            subtotal["total"] += 1
        totals["overall"] = {
            k: sum(t[k] for t in totals.values()) for k in ("strict_pass", "core_correct", "total")
        }
        if totals != data["totals"]:
            raise ValueError("manual STEM category or overall sum mismatch")
        result[model] = {
            "totals": totals,
            "records": {e["id"]: e for e in entries},
            "source": path,
            "model_sha256": data["model_sha256"],
            "response_sha256": fingerprint,
        }
    return result


def transcript(
    output: Path,
    source: Path,
    artifact: dict,
    stage: str,
    rows: list[dict],
    events: list[dict],
    config: dict,
    source_digest: str | None,
    grade: dict | None = None,
) -> dict:
    by_id = validate_records(rows, artifact, stage, config)
    prompts = judge_prompts() if stage == "judges" else stem_prompts()
    if grade and grade["model_sha256"] != artifact["test_sha256"]:
        raise ValueError("manual grade/model mismatch")
    if grade and (grade["response_sha256"] != source_digest or len(by_id) != len(prompts)):
        raise ValueError("manual grade/source mismatch")
    label = model_label(artifact)
    lines = [
        f"# {label}: {'Gate 1 replay' if stage == 'judges' else '100-prompt STEM test'}",
        "",
        f"Captured: {len(rows)}/{len(prompts)}. Complete captured requests can still contain empty or truncated answers.",
        "",
        f"[Raw response records](<{link(source, output)}>) · [Recorded configuration](<{link(source.parent / 'config.json', output)}>)",
        "",
        "Returned text below is unedited. Separate reasoning is preserved but does not count as a delivered final answer in the Gate 1 rubric.",
        "",
    ]
    failures = [e for e in events if e.get("event") == "model_failure"]
    if failures:
        lines += [
            "## Recorded failure",
            "",
            literal(json.dumps(failures, indent=2, ensure_ascii=False)),
            "",
        ]
    if grade:
        lines += [
            f"Provisional local rubric: {grade['total']}/100. [Criterion-level review](<{link(grade['source'], output)}>). Not an official panel score.",
            "",
        ]
    for prompt in prompts:
        lines += [f"## {prompt.id}", "", "### Prompt", "", literal(prompt.text), ""]
        if stage == "stem":
            lines += [f"Reference answer: {prompt.expected}.", ""]
        row = by_id.get(prompt.id)
        if row is None:
            lines += ["No response captured. Not graded as an incorrect answer.", ""]
            continue
        usage = row.get("usage") or {}
        tokens = row.get("generated_tokens", usage.get("completion_tokens", "unrecorded"))
        lines += [
            f"Finish: `{row.get('finish_reason', 'unrecorded')}`. Output tokens: {tokens}.",
            "",
            "### Returned answer field",
            "",
            literal(row.get("answer", "")),
            "",
        ]
        if row.get("reasoning_content"):
            lines += [
                "### Separately returned reasoning",
                "",
                literal(row["reasoning_content"]),
                "",
            ]
        if grade:
            entry = grade["records"][prompt.id]
            lines += [f"### Provisional assessment: {entry['score']}/10", ""]
            if entry.get("reason"):
                lines += [entry["reason"], ""]
            for c in entry.get("items", entry.get("criteria")):
                points = c["weight"] if c["passed"] else 0
                lines.append(f"- {points}/{c['weight']}: {c['criterion']}.")
            lines.append("")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return {
        "model": artifact["test_artifact"],
        "stage": stage,
        "captured": len(rows),
        "expected": len(prompts),
        "source": str(source),
        "source_sha256": source_digest,
        "model_sha256": artifact["test_sha256"],
        "output": str(output),
        "output_sha256": digest(output),
    }


def build(campaign: Path) -> dict:
    campaign = campaign.resolve()
    _, artifacts = load_artifacts(campaign / "artifacts.csv")
    reviews = manual_judges(campaign)
    index = campaign / "prompt-responses.md"
    lines = [
        "# Prompts and model responses",
        "",
        "This index preserves the matched Mac Metal screen, including completed sets and failed requests. Captured counts below define coverage; missing answers are not zero grades. GCP measurements and replays remain separate.",
        "",
        "STEM: 100 raw-completion prompts per model, with 256 output tokens for multiple choice and 512 for written responses. Gate 1: ten chat prompts per model, with a shared 1,024-token output budget including reasoning. These are local test limits, not confirmed organizer limits.",
        "",
        "The Gate 1 set contains five automated-test prompts and five human-judge prompts supplied with the original feedback. Unreadable currency glyphs were restored to ₦ in two prompts; other wording is unchanged apart from whitespace. Local rubric scores are assistant assessments, not organizer grades.",
        "",
        "| Model | Full STEM responses | Full Gate 1 responses | Provisional Mac Gate 1 rubric |",
        "|---|---:|---:|---:|",
    ]
    manifest = []
    excluded = []
    for artifact in artifacts:
        name = artifact["test_artifact"]
        if Path(name).name != name:
            raise ValueError("artifact filename must not contain a directory")
        if artifact["runtime_gate"] != "pass":
            excluded.append(name)
            continue
        paths = []
        for stage in ("stem", "judges"):
            directory = campaign / "mac-accuracy" / name / stage
            source = directory / "responses.jsonl"
            output = campaign / "transcripts" / "mac" / name / f"{stage}.md"
            source_rows, source_digest = read_snapshot(source)
            config = json.loads((directory / "config.json").read_text())
            entry = transcript(
                output,
                source,
                artifact,
                stage,
                source_rows,
                read_jsonl(directory / "events.jsonl"),
                config,
                source_digest,
                reviews.get(name) if stage == "judges" else None,
            )
            manifest.append(entry)
            paths.append(f"[{entry['captured']}/{entry['expected']}](<{link(output, index)}>)")
        grade = str(reviews[name]["total"]) + "/100" if name in reviews else "incomplete; unranked"
        lines.append(f"| {model_label(artifact)} | {paths[0]} | {paths[1]} | {grade} |")
    lines += [
        "",
        "Empty and truncated answers are retained verbatim. Falcon's failed requests remain visibly missing; no answers are fabricated or substituted. A source hash changing invalidates its attached manual assessment.",
        "",
        "## Separate evidence",
        "",
        "- [Campaign report](report.md)",
        "- [Measurements and separate accuracy assessments](results.csv)",
        "- [Separate GCP and Mac Gate 1 rankings](judges-ranking.csv)",
        "- [Matched Mac STEM ranking](stem-report.md)",
        "- [Gate 1 replay and grading](judges-report.md)",
        "- [GCP scalar prompts, answers and assessments](gcp-judges-responses.md)",
        "- [Original GCP scalar STEM review](manual-stem/)",
        "- [Matched Mac STEM review](manual-stem-mac/)",
        "- [GCP scalar Gate 1 raw responses](raw/judges-responses.jsonl)",
        "",
        "Runtime-excluded artifacts: " + ", ".join(excluded) + ".",
        "",
    ]
    index.write_text("\n".join(lines))
    result = {"files": manifest, "index": str(index), "excluded": excluded}
    (campaign / "transcript-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def scalar_transcript(output: Path, artifact: dict, review: dict) -> dict:
    """Render one source-validated scalar snapshot, without rereading growing inputs."""
    expected = {p.id for p in judge_prompts()}
    rows, assessments = review["raw_records"], review["records"]
    if set(rows) != expected or set(assessments) != expected:
        raise ValueError("scalar transcript requires ten reviewed prompt records")
    if review["model_sha256"] != artifact["test_sha256"]:
        raise ValueError("scalar transcript model/grade mismatch")
    if review["score"] != sum(a["score"] for a in assessments.values()):
        raise ValueError("scalar transcript grade sum mismatch")
    lines = [
        f"# {model_label(artifact)}: GCP scalar Gate 1 replay",
        "",
        f"Local rubric: {review['score']}/100. Finished final answers: {review['finished']}/10. These are assistant assessments, not official panel grades.",
        "",
        "Each prompt is a separate chat request using the embedded template, temperature 0 and a 1,024-token output allowance including reasoning. This is a local test limit, not a confirmed organizer limit. Only delivered final text earns points. Reasoning and truncated outputs remain visible below.",
        "",
        f"[Raw response file](<{link(review['response_source'], output)}>) · [Source-bound criterion ledger](<{link(review['source'], output)}>). The ledger identifies the exact reviewed prefix of the accumulated raw file.",
        "",
    ]
    for prompt in judge_prompts():
        row, assessment = rows[prompt.id], assessments[prompt.id]
        if (
            row["id"] != prompt.id
            or row["model"] != artifact["test_artifact"]
            or row["model_sha256"] != artifact["test_sha256"]
            or row["hardware_context"] != GCP_CONTEXT
            or row["server_sha256"] != GCP_BINARY
            or row["settings"] != GCP_SETTINGS
            or row["text"] != prompt.text
            or hashlib.sha256(row["answer"].encode()).hexdigest() != assessment["answer_sha256"]
            or hashlib.sha256(row["reasoning_content"].encode()).hexdigest()
            != assessment["reasoning_sha256"]
        ):
            raise ValueError("scalar transcript answer/grade identity mismatch")
        lines += [
            f"## {prompt.id}: {prompt.title}",
            "",
            "### Prompt",
            "",
            literal(prompt.text),
            "",
            f"Finish: `{row['finish_reason']}`. Output tokens: {row.get('usage', {}).get('completion_tokens', 'unrecorded')}.",
            "",
            "### Returned answer field",
            "",
            literal(row["answer"]),
            "",
            "### Separately returned reasoning",
            "",
            literal(row["reasoning_content"]),
            "",
            f"### Local assessment: {assessment['score']}/10",
            "",
        ]
        if assessment.get("reason"):
            lines += [assessment["reason"], ""]
        for item in assessment.get("items", assessment.get("criteria")):
            points = item["weight"] if item["passed"] else 0
            note = f" {item['reason']}" if item.get("reason") else ""
            lines.append(f"- {points}/{item['weight']}: {item['criterion']}.{note}")
        lines.append("")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return {
        "model": artifact["test_artifact"],
        "model_sha256": artifact["test_sha256"],
        "review": str(review["source"]),
        "source": str(review["response_source"]),
        "source_prefix_sha256": review["response_sha256"],
        "source_prefix_bytes": review["response_prefix_bytes"],
        "source_prefix_lines": review["response_prefix_lines"],
        "output": str(output),
        "output_sha256": digest(output),
    }


def build_gcp(campaign: Path) -> dict:
    campaign = campaign.resolve()
    _, artifacts = load_artifacts(campaign / "artifacts.csv")
    by_model = {a["test_artifact"]: a for a in artifacts}
    reviews = manual_gcp_judges(campaign)
    captures = load_gcp_captures(campaign)
    captured_models = captures.by_model
    index = campaign / "gcp-judges-responses.md"
    lines = [
        "# GCP scalar Gate 1 responses",
        "",
        f"{len(reviews)} models have complete, source-checked local assessments. This ranking applies to the fixed-budget scalar chat test, not general model ability or the ADTC composite. Failed or unreviewed captures remain unranked.",
        "",
        "The ten prompts come from the supplied Gate 1 feedback: five automated-test and five human-judge prompts, including one repeated question. Two unreadable currency glyphs were restored to ₦. These are local rubric grades, not organizer grades or ADTC composite scores.",
        "",
        "| Rank among reviewed | Model | Local rubric / 100 | Finished finals / 10 | Full prompts and responses |",
        "|---:|---|---:|---:|---|",
    ]
    manifest = []
    for model, review in sorted(reviews.items(), key=lambda pair: (-pair[1]["score"], pair[0])):
        if Path(model).name != model:
            raise ValueError("scalar artifact filename must not contain a directory")
        prefix = captures.responses.prefix[: review["response_prefix_bytes"]]
        if hashlib.sha256(prefix).hexdigest() != review["response_sha256"]:
            raise ValueError("scalar capture and review source snapshots differ")
        if captured_models[model].summary["status"] != "complete_unreviewed":
            raise ValueError("reviewed scalar model lacks a complete captured lifecycle")
        output = campaign / "transcripts/gcp-scalar" / model / "judges.md"
        manifest.append(scalar_transcript(output, by_model[model], review))
        rank = 1 + sum(r["score"] > review["score"] for r in reviews.values())
        lines.append(
            f"| {rank} | {model_label(by_model[model])} | {review['score']} | {review['finished']}/10 | [Read](<{link(output, index)}>) |"
        )
    unreviewed = [
        a for a in artifacts if a["runtime_gate"] == "pass" and a["test_artifact"] not in reviews
    ]
    if unreviewed:
        lines += [
            "",
            "## Other scalar captures",
            "",
            "These sets have no reviewed score or rank. Each page contains all ten prompt positions, any saved answers and recorded failures. Missing responses are not zero scores. Status reflects the saved snapshot, not a live process check.",
            "",
            "| Model | Recorded state | Captured / 10 | Prompts and saved responses |",
            "|---|---|---:|---|",
        ]
    for artifact in unreviewed:
        model = artifact["test_artifact"]
        capture = captured_models[model]
        summary = capture.summary
        output = campaign / "transcripts/gcp-scalar" / model / "judges.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_gcp_capture(capture))
        manifest.append(
            {
                **summary,
                "review": None,
                "score": None,
                "rank": None,
                "output": str(output),
                "output_sha256": digest(output),
            }
        )
        lines.append(
            f"| {model_label(artifact)} | {summary['status'].replace('_', ' ')} | {summary['response_count']}/10 | [Read](<{link(output, index)}>) |"
        )
    lines += [
        "",
        "[Campaign report](report.md) · [Measurements](results.csv) · [Separate GCP and Mac Gate 1 rankings](judges-ranking.csv) · [Separate GCP STEM attempts](gcp-stem-attempts.md) · [Supplementary Mac response archive](prompt-responses.md).",
        "",
    ]
    index.write_text("\n".join(lines))
    result = {"files": manifest, "index": str(index)}
    (campaign / "gcp-transcript-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument(
        "--gcp-scalar", action="store_true", help="Publish reviewed GCP scalar judges snapshots"
    )
    args = parser.parse_args()
    result = build_gcp(args.campaign) if args.gcp_scalar else build(args.campaign)
    print(f"Wrote {len(result['files'])} source-checked transcript files and {result['index']}")


if __name__ == "__main__":
    main()
