"""Report Gate 1 responses with a provisional keyword rubric for adjudication."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from bench.judges_prompt_suite import prompts
from bench.run_stem_prompt_suite import selected_option


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[,_*`$₦£€]", "", value)


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)


def item(label: str, weight: float, passed: bool) -> dict:
    return {"criterion": label, "weight": weight, "passed": bool(passed)}


def two_sigma_items(text: str) -> list[dict]:
    value = normalize(text)
    return [
        item(
            "states direct proportionality R = kP",
            3,
            has_any(
                value,
                (
                    r"r\s*(?:\([^)]*\))?\s*=\s*[kc].{0,8}p\b",
                    r"knowledge acquisition rate.{0,80}directly proportional",
                    r"r\s*(?:∝|proportional to)\s*p",
                ),
            ),
        ),
        item(
            "as personalization tends to zero the rate tends to zero",
            2,
            has_any(
                value,
                (
                    r"(?:p|personalization).{0,60}(?:approach|tend).{0,12}zero.{0,100}(?:r|rate).{0,50}(?:zero|0)",
                    r"(?:p|personalization).{0,15}(?:→|->)\s*0.{0,80}(?:r|rate).{0,15}(?:→|->)\s*0",
                ),
            ),
        ),
        item(
            "as personalization tends to infinity the linear rate is unbounded",
            2,
            has_any(
                value,
                (
                    r"(?:p|personalization).{0,60}(?:infinity|infinite|∞).{0,100}(?:unbounded|infinity|infinite|∞)",
                    r"(?:r|rate).{0,40}(?:grow|increase).{0,40}(?:without bound|unbounded)",
                ),
            ),
        ),
        item(
            "defines the variables and positive proportionality constant",
            2,
            has_any(value, (r"(?:k|constant of proportionality).{0,80}(?:positive|constant)",))
            and "personalization" in value,
        ),
        item(
            "does not invent a square-root-of-two constant or Kahneman attribution",
            1,
            not has_any(value, (r"sqrt\s*\(?2", r"√\s*2", r"kahneman")),
        ),
    ]


def grade(prompt_id: str, response: str) -> dict:
    value = normalize(response)
    original = response.lower()
    if prompt_id in {"automated_01", "human_04"}:
        items = two_sigma_items(response)
    elif prompt_id == "automated_02":
        items = [
            item(
                "gives S(t) = T + (S(0) - T)e^(-kt)",
                4,
                "s(0)" in value
                and "t" in value
                and has_any(value, (r"(?:e\^|exp\s*\().{0,12}[-−]\s*k\s*t",)),
            ),
            item(
                "applies the initial condition",
                1,
                has_any(value, (r"initial condition", r"s\s*\(\s*0\s*\)\s*=", r"s[_ ]?0")),
            ),
            item(
                "states convergence to T for positive k",
                2,
                has_any(value, (r"(?:approach|converge|tend).{0,30}(?:tutor|\bt\b)",))
                and has_any(value, (r"k\s*>\s*0", r"positive\s+k")),
            ),
            item(
                "connects the ceiling or rate to individual learning",
                2,
                has_any(value, (r"(?:ceiling|limit|asymptot|diminish)",))
                and has_any(value, (r"(?:mastery|learning|student)",)),
            ),
            item(
                "relates one-to-one gains to the difficulty of scaling tutoring",
                1,
                has_any(
                    value, (r"(?:one.to.one|personaliz|individual).{0,120}(?:scal|resource|tutor)",)
                ),
            ),
        ]
    elif prompt_id == "automated_03":
        items = [
            item(
                "recognizes that parameter count is underdetermined",
                4,
                has_any(
                    value,
                    (
                        r"(?:cannot|can.t|not possible|insufficient|not enough).{0,50}(?:determine|calculate|infer)",
                        r"underdetermined",
                    ),
                ),
            ),
            item(
                "computes the 200 ms operation budget as 8 × 10^11",
                2,
                has_any(value, (r"8\s*(?:x|×)\s*10\s*\^?\s*11", r"800\s*billion", r"800000000000")),
            ),
            item(
                "requires an output-length assumption",
                1,
                has_any(value, (r"(?:output|response).{0,30}(?:length|characters|tokens)",)),
            ),
            item(
                "requires operations per parameter per generated token",
                2,
                has_any(
                    value,
                    (
                        r"operations?.{0,30}parameter.{0,30}token",
                        r"flops?.{0,30}token",
                    ),
                ),
            ),
            item(
                "does not treat two tokens per character as enough to size the model",
                1,
                has_any(
                    value,
                    (r"(?:2|two) tokens per character.{0,100}(?:not|insufficient|doesn.t)",),
                ),
            ),
        ]
    elif prompt_id == "automated_04":
        items = [
            item("selects option C", 4, selected_option(response) == "C"),
            item("gives ₦3,000", 2, "3000" in value),
            item("shows 6 × 500 = 3,000", 2, "6" in value and "500" in value and "3000" in value),
            item("keeps the requested answer concise", 2, len(response) <= 500),
        ]
    elif prompt_id == "automated_05":
        items = [
            item("selects option B", 4, selected_option(response) == "B"),
            item("identifies photosynthesis", 2, "photosynthesis" in value),
            item(
                "explains conversion of light into stored chemical energy or food",
                2,
                "light" in value and has_any(value, (r"(?:chemical energy|glucose|food)",)),
            ),
            item("keeps the requested explanation concise", 2, len(response) <= 500),
        ]
    elif prompt_id == "human_01":
        items = [
            item("gives 53.3 km/h", 3, has_any(value, (r"53\.3", r"53\s*1/3"))),
            item(
                "computes 1.5 h, 0.75 h, and 2.25 h",
                2,
                all(n in value for n in ("1.5", "0.75", "2.25")),
            ),
            item(
                "uses total distance divided by total time",
                1,
                "total distance" in value and "total time" in value,
            ),
            item(
                "explains why the arithmetic mean fails for equal distances",
                2,
                "equal distance" in value
                or has_any(
                    value,
                    (
                        r"spends?.{0,40}(?:more|different).{0,20}time",
                        r"weighted.{0,20}time",
                        r"harmonic mean",
                    ),
                ),
            ),
            item(
                "includes an intuitive second example",
                1,
                has_any(value, (r"(?:example|imagine|suppose)",)),
            ),
            item(
                "teaches a future recognition rule",
                1,
                has_any(
                    value, (r"next time", r"recognize", r"always.{0,30}total distance", r"remember")
                ),
            ),
        ]
    elif prompt_id == "human_02":
        scientific_error = has_any(
            value,
            (r"chromosomes? (?:are|is).{0,20}cell walls?", r"proteins? contain genes?"),
        )
        items = [
            item(
                "identifies the misconception that the terms are not synonyms",
                1,
                has_any(
                    value,
                    (
                        r"not.{0,25}(?:same|synonym|interchange)",
                        r"different.{0,20}(?:levels|roles|things)",
                    ),
                ),
            ),
            item(
                "describes DNA as genetic information or material",
                1,
                "dna" in value and has_any(value, (r"genetic (?:information|material|code)",)),
            ),
            item(
                "defines a gene as a segment of DNA",
                2,
                has_any(
                    value,
                    (
                        r"gene.{0,30}(?:segment|section|stretch|part).{0,20}dna",
                        r"segment.{0,20}dna.{0,20}gene",
                    ),
                ),
            ),
            item(
                "states that chromosomes package DNA",
                1,
                has_any(value, (r"chromosome.{0,40}(?:contain|package|made of).{0,20}dna",)),
            ),
            item(
                "connects gene expression to proteins",
                2,
                has_any(
                    value,
                    (
                        r"gene.{0,80}(?:instruct|code|express).{0,30}protein",
                        r"proteins?.{0,30}(?:made|produced).{0,50}gene",
                    ),
                ),
            ),
            item(
                "uses a simple analogy without a flagged scientific error",
                1,
                has_any(value, (r"analogy", r"imagine", r"like a")) and not scientific_error,
            ),
            item("asks a check question", 1, "?" in response),
            item(
                "provides a response for an incorrect student answer",
                1,
                has_any(
                    value,
                    (r"if (?:you|the student).{0,30}(?:incorrect|wrong|answer)", r"if.{0,30}says?"),
                ),
            ),
        ]
    elif prompt_id == "human_03":
        english_terms = all(
            term in value
            for term in ("sunlight", "carbon dioxide", "water", "glucose", "oxygen", "chlorophyll")
        )
        yoruba_markers = (
            sum(mark in original for mark in ("ọ", "ṣ", "ẹ", "ì", "à", "ń")) >= 3
            or sum(word in value for word in ("oorun", "eweko", "erogba", "atẹgun", "suga")) >= 3
        )
        items = [
            item("includes all six required scientific terms", 2, english_terms),
            item(
                "correctly states the inputs and outputs",
                2,
                "carbon dioxide" in value
                and "water" in value
                and "glucose" in value
                and "oxygen" in value,
            ),
            item(
                "states that chlorophyll absorbs or captures light",
                1,
                has_any(value, (r"chlorophyll.{0,50}(?:absorb|capture|trap).{0,30}(?:light|sun)",)),
            ),
            item(
                "contains a substantive Yorùbá explanation",
                2,
                yoruba_markers and len(response) >= 300,
            ),
            item(
                "uses a West African everyday example",
                1,
                has_any(value, (r"(?:nigeria|west africa|lagos|farm|maize|cassava|rice|garden)",)),
            ),
            item(
                "ends with English and Yorùbá understanding questions",
                2,
                response.count("?") >= 2 and yoruba_markers,
            ),
        ]
    elif prompt_id == "human_05":
        wrong_anchor = has_any(value, (r"107125", r"33125", r"44\.7\s*%", r"69\.1\s*%"))
        items = [
            item("computes total cost as ₦74,000", 1, "74000" in value),
            item(
                "identifies 15 kg remaining", 1, has_any(value, (r"15\s*kg", r"remaining.{0,15}15"))
            ),
            item("reduces the price to ₦1,955 per kg", 2, "1955" in value),
            item(
                "computes batch revenues ₦57,500 and ₦29,325",
                2,
                "57500" in value and "29325" in value,
            ),
            item("computes total revenue as ₦86,825", 1, "86825" in value),
            item("computes profit as ₦12,825", 1, "12825" in value),
            item("computes percentage profit as 17.3%", 1, "17.3" in value),
            item(
                "checks by a genuinely different method",
                1,
                has_any(
                    value,
                    (r"(?:alternative|different|second) method", r"weighted average", r"check"),
                )
                and not wrong_anchor,
            ),
        ]
    else:
        raise KeyError(prompt_id)

    if not response.strip():
        for entry in items:
            entry["passed"] = False
    total = sum(entry["weight"] for entry in items if entry["passed"])
    return {"score": round(total, 2), "max_score": 10, "items": items}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_names(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["test_artifact"]: row["model"] for row in csv.DictReader(handle)}


def evaluate(rows: list[dict], names: dict[str, str]) -> tuple[list[dict], list[dict]]:
    expected = {prompt.id: prompt.source for prompt in prompts()}
    seen: set[tuple[str, str]] = set()
    hashes: dict[str, str] = {}
    contexts = set()
    details = []
    for row in rows:
        key = (row["model"], row["id"])
        if key in seen:
            raise ValueError(f"duplicate judge response: {key}")
        seen.add(key)
        contexts.add(row.get("hardware_context") or "unspecified")
        if len(contexts) > 1:
            raise ValueError("mixed hardware contexts in judge aggregate; report each separately")
        if row["id"] not in expected or row["source"] != expected[row["id"]]:
            raise ValueError(f"unknown judge prompt or mismatched source: {key}")
        previous_hash = hashes.setdefault(row["model"], row["model_sha256"])
        if previous_hash != row["model_sha256"]:
            raise ValueError(f"different artifacts share a model filename: {row['model']}")
        scored = grade(row["id"], row.get("answer", ""))
        details.append({**row, "model_label": names.get(row["model"], row["model"]), **scored})

    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in details:
        by_model[row["model"]].append(row)
    summary = []
    for model_rows in by_model.values():
        automated = sum(row["score"] for row in model_rows if row["source"] == "automated")
        human = sum(row["score"] for row in model_rows if row["source"] == "human judge")
        summary.append(
            {
                "model": model_rows[0]["model_label"],
                "prompts_completed": len(model_rows),
                "status": "complete" if len(model_rows) == len(expected) else "incomplete",
                "hardware_context": model_rows[0].get("hardware_context") or "unspecified",
                "truncated_responses": sum(
                    row.get("finish_reason") == "length" for row in model_rows
                ),
                "empty_final_responses": sum(
                    not row.get("answer", "").strip() for row in model_rows
                ),
                "automated_prompt_score": automated,
                "human_judge_prompt_score": human,
                "judge_prompt_total": automated + human,
                "model_sha256": model_rows[0]["model_sha256"],
            }
        )
    summary.sort(
        key=lambda row: (row["status"] == "complete", row["judge_prompt_total"]), reverse=True
    )
    for rank, row in enumerate(summary, 1):
        row["rank"] = rank if row["status"] == "complete" else None
    return summary, details


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "rank",
        "model",
        "prompts_completed",
        "status",
        "hardware_context",
        "truncated_responses",
        "empty_final_responses",
        "automated_prompt_score",
        "human_judge_prompt_score",
        "judge_prompt_total",
        "model_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def execution_records(details: list[dict], events: list[dict] | None = None) -> list[dict]:
    """Describe only settings retained in response records or matching start events."""
    records = {}
    generation_keys = {"temperature", "top_p", "seed", "max_tokens"}
    flags = {
        "--ctx-size": "context_size",
        "--threads": "threads",
        "--n-gpu-layers": "gpu_layers",
    }
    for row in details:
        candidates = []
        for event in events or []:
            if event.get("event") != "model_start" or event.get("model") != row["model"]:
                continue
            if any(
                not row.get(field) or event.get(field) != row[field]
                for field in ("model_sha256", "server_sha256")
            ):
                continue
            command = event.get("command", [])
            settings = {}
            for flag, name in flags.items():
                if flag in command and command.index(flag) + 1 < len(command):
                    settings[name] = command[command.index(flag) + 1]
            if "--jinja" in command:
                settings["jinja"] = True
            settings.update(event.get("settings", {}))
            candidates.append(settings)
        unique_candidates = {json.dumps(item, sort_keys=True) for item in candidates}
        settings = json.loads(next(iter(unique_candidates))) if len(unique_candidates) == 1 else {}
        settings.update(row.get("settings", {}))
        server_settings = {
            key: value for key, value in settings.items() if key not in generation_keys
        }
        server_settings.update(row.get("server_settings", {}))
        generation_settings = {
            key: value for key, value in settings.items() if key in generation_keys
        }
        generation_settings.update(row.get("generation_settings", {}))
        context = row.get("hardware_context")
        record = {
            "hardware_context": (
                context if context and context != "unspecified" else "unspecified (legacy record)"
            ),
            "server_sha256": row.get("server_sha256") or "unrecorded",
            "server_version": row.get("server_version") or "unrecorded",
            "server_settings": server_settings,
            "generation_settings": generation_settings,
            "ambiguous_start_events": len(unique_candidates) > 1,
        }
        key = json.dumps(record, sort_keys=True)
        if key not in records:
            records[key] = {**record, "responses": 0}
        records[key]["responses"] += 1
    return list(records.values())


def write_report(
    path: Path, summary: list[dict], details: list[dict], events: list[dict] | None = None
) -> None:
    prompt_by_id = {prompt.id: prompt for prompt in prompts()}
    lines = [
        "# Gate 1 judge-prompt replay",
        "",
        "## Provisional keyword-rubric ranking",
        "",
        "| Rank | Model | Automated prompts | Human-judge prompts | Total | Completed | Status |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in summary:
        lines.append(
            f"| {row['rank'] or '—'} | {row['model']} | {row['automated_prompt_score']:.1f}/50 | "
            f"{row['human_judge_prompt_score']:.1f}/50 | "
            f"**{row['judge_prompt_total']:.1f}/100** | {row['prompts_completed']}/10 | "
            f"{row['status']} |"
        )
    lines.extend(
        [
            "",
            "## Method",
            "",
            (
                "The replay contains ten recovered Gate 1 prompts. The execution details below "
                "come from saved response records and, when supplied, matching server-start "
                "events. Missing legacy metadata is reported as unrecorded; hardware, runtime "
                "version, sampler settings, and template behavior are not inferred from defaults."
            ),
            "",
            (
                "The provisional ranking uses ten keyword rubrics worth ten points each. "
                "Keyword matches can miss equivalent correct answers and accept contradictions, "
                "so these scores require manual adjudication before model selection. They are "
                "not the organisers' unpublished panel score. Incomplete runs are unranked. "
                "Raw responses are retained below for blind review."
            ),
            "",
        ]
    )
    for index, record in enumerate(execution_records(details, events), 1):
        settings = record["server_settings"]
        generation = record["generation_settings"]
        lines.extend(
            [
                f"### Recorded execution {index}",
                "",
                f"Context: `{record['hardware_context']}`. Responses: {record['responses']}.",
                "",
                (
                    f"Server version: `{record['server_version']}`. "
                    f"Server SHA-256: `{record['server_sha256']}`."
                ),
                "",
                "Server settings: "
                + (
                    "; ".join(f"{key}={value}" for key, value in sorted(settings.items()))
                    if settings
                    else "unrecorded"
                )
                + ".",
                "",
                "Generation settings: "
                + (
                    "; ".join(f"{key}={value}" for key, value in sorted(generation.items()))
                    if generation
                    else "unrecorded"
                )
                + ".",
                "",
            ]
        )
        if record["ambiguous_start_events"]:
            lines.extend(["Multiple matching start events disagree on server settings.", ""])
    lines.extend(["## Responses and rubric results", ""])
    detail_by_model: dict[str, list[dict]] = defaultdict(list)
    for row in details:
        detail_by_model[row["model_label"]].append(row)
    for model in [row["model"] for row in summary]:
        lines.extend([f"### {model}", ""])
        for row in sorted(detail_by_model[model], key=lambda entry: entry["id"]):
            prompt = prompt_by_id[row["id"]]
            passed = [entry["criterion"] for entry in row["items"] if entry["passed"]]
            missed = [entry["criterion"] for entry in row["items"] if not entry["passed"]]
            lines.extend(
                [
                    f"<details><summary>{row['id']} · {prompt.title} · {row['score']:.1f}/10</summary>",
                    "",
                    "**Prompt**",
                    "",
                    prompt.text,
                    "",
                    "**Response**",
                    "",
                    "<pre>",
                    html.escape(row.get("answer", "") or "No final response."),
                    "</pre>",
                ]
            )
            if row.get("reasoning_content"):
                lines.extend(
                    [
                        "",
                        "**Server reasoning field**",
                        "",
                        "<pre>",
                        html.escape(row["reasoning_content"]),
                        "</pre>",
                    ]
                )
            lines.extend(
                [
                    "",
                    "**Rubric**",
                    "",
                    f"Passed: {'; '.join(passed) if passed else 'none'}.",
                    "",
                    f"Missed: {'; '.join(missed) if missed else 'none'}.",
                    "",
                    "</details>",
                    "",
                ]
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--events", type=Path, help="Optional server lifecycle records")
    args = parser.parse_args()
    summary, details = evaluate(read_jsonl(args.responses), load_names(args.artifacts))
    write_csv(args.csv, summary)
    write_report(args.report, summary, details, read_jsonl(args.events) if args.events else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
