"""Offline, identity-masked development review and exact guarded selection."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "provenance/science-tutor-20260919/evaluation/development72-v1"
PROTOCOL = ROOT / "docs/plans/2026-09-19-science-development-adjudication.md"
MANIFEST_SHA = "eac6c3ee88c5ec44a7cb0b9ae986995dc9dbafd9dd82df17deea83b64406865c"
CAMPAIGN_SHA = "9cb17104ddf98ff6f1541d7d9e718f9bbd38642d675aa78a92475b75d804eca1"
ROSTER_SHA = "a5425e7654ec8ca953e553af305ac337ca8dda87218388e5e6516b11c04f34a0"
HELDOUT_SHA = "d0f97685e09c9b481e385b86015d0181660a11e6a64c47201ed046e93222c7f6"
HELPER_SHA = "038abb238eb8044ceb7f4b2f85af4f14965c4cabbf1c636c5fa669894aa33cdd"
GENERATION = {
    "batch_size": 8,
    "max_new_tokens": 1024,
    "context_length": 4096,
    "do_sample": False,
    "seed": 3407,
}
PROTOCOL_SHA = "cc224a0616e76a8aac9e59cf6aeb0cfc634deb9b2a1a0675f8cac88412a17d39"
SOURCE_HASHES = {
    "train.py": "a800ca3bf599b234c4fa61f50a37b0638496269bd811a6656598cf5543291bd0",
    "tokenization.py": "93d251a9b0394cf9033622386ebbb352a3393cbe516f985795c5289f2a85bfd4",
    "calibrate.py": "1dbbfd2072516d39c60ac4ab90be03e8f23b4215f5a1da44aef3ed2745119a57",
    "evaluate_pilots.py": "74c1037f298533a37f8637fb37fb358e58555766a054d8289892871a19f189df",
}


def _module(name, digest):
    path = Path(__file__).with_name(name + ".py")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("review helper source changed: " + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _module("freeze_development72", HELPER_SHA)
heldout = _module("heldout_curriculum", HELDOUT_SHA)
require, sha, canonical, parse, rows, index = (
    helper.require,
    helper.sha,
    helper.canonical,
    helper.parse,
    helper.rows,
    helper.index,
)


def read(path):
    path = Path(path).absolute()
    require(
        path.is_file() and all(not p.is_symlink() for p in (path, *path.parents)),
        "nonregular/symlinked file: " + str(path),
    )
    return path.read_bytes()


def pinned(path, digest):
    raw = read(path)
    require(sha(raw) == digest, "file SHA256 mismatch: " + str(path))
    return raw


def code_identity():
    paths = [Path(__file__), Path(helper.__file__), Path(heldout.__file__), PROTOCOL]
    identities = {str(p.relative_to(ROOT)): sha(read(p)) for p in paths}
    require(
        sha(read(helper.__file__)) == HELPER_SHA
        and sha(read(heldout.__file__)) == HELDOUT_SHA
        and sha(read(PROTOCOL)) == PROTOCOL_SHA,
        "compiler dependency/protocol changed",
    )
    return identities


def separate_output(output, protected):
    output = Path(output).absolute()
    for source in protected:
        source = Path(source).absolute()
        require(
            source != output and source not in output.parents,
            "output must not mutate protected inputs",
        )


def inventory(root, *, omit=()):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "missing/symlinked tree")
    result = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "symlink in sealed tree")
        if path.is_file() and path.relative_to(root).as_posix() not in omit:
            raw = read(path)
            result.append(
                {"path": path.relative_to(root).as_posix(), "sha256": sha(raw), "bytes": len(raw)}
            )
        else:
            require(path.is_dir() or path.is_file(), "special file in sealed tree")
    return result


def tree_sha(files):
    return sha("\n".join(f"{r['sha256']}  {r['path']}" for r in files).encode())


def check_tree(receipt, files, expected_root):
    require(
        receipt
        == {
            "root": expected_root,
            "tree_sha256": tree_sha(files),
            "files": files,
            "file_count": len(files),
            "bytes": sum(r["bytes"] for r in files),
        },
        "tree inventory/seal mismatch",
    )


def validate_roster(roster):
    require(type(roster) is dict and len(roster) == 12, "exact12 roster required")
    slots = []
    for candidate, row in roster.items():
        require(
            type(candidate) is str and candidate and "/" not in candidate and ".." not in candidate,
            "unsafe candidate id",
        )
        require(type(row) is dict and set(row) == {"lineage", "role", "step"}, "roster schema")
        require(
            row["lineage"] in ("P1", "P2", "P3", "P4")
            and type(row["step"]) is int
            and (row["role"], row["step"]) in (("control", 0), ("pilot", 63), ("pilot", 126)),
            "roster role/lineage/step",
        )
        slots.append((row["lineage"], row["step"]))
    require(len(set(slots)) == 12, "duplicate/missing roster slots")
    canonical_roster = {}
    for n in range(1, 5):
        canonical_roster[f"C{n}"] = {"lineage": f"P{n}", "role": "control", "step": 0}
        for suffix, step in (("half", 63), ("end", 126)):
            canonical_roster[f"P{n}-{suffix}"] = {"lineage": f"P{n}", "role": "pilot", "step": step}
    require(roster == canonical_roster, "roster differs from predeclared twelve-candidate mapping")


def validate_lineages(config, roster):
    validate_roster(roster)
    require(set(config["candidates"]) == set(roster), "config/roster candidate mismatch")
    for n in range(1, 5):
        control = config["candidates"][f"C{n}"]
        expected_profile = "deepseek_native" if n == 4 else "qwen_native"
        expected_template = (
            "56a1447ad31926fdc21fb07e56e5642bd9c850c4f52d8c8af7bbe5f079a84f5f"
            if n == 4
            else "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"
        )
        require(
            control["profile"] == expected_profile
            and control["chat_template_sha256"] == expected_template,
            "lineage native profile/template mismatch",
        )
        require(bool(control.get("adapter")) == (n == 3), "unchanged control adapter mismatch")
        for suffix, step in (("half", 63), ("end", 126)):
            candidate = config["candidates"][f"P{n}-{suffix}"]
            require(
                all(
                    candidate[k] == control[k]
                    for k in ("base", "tokenizer", "profile", "chat_template_sha256")
                ),
                "pilot differs from its own control parent/native profile",
            )
            adapter = candidate.get("adapter")
            require(
                type(adapter) is dict
                and adapter.get("parent_base_tree_sha256") == candidate["base"]["tree_sha256"],
                "pilot missing adapter or wrong adapter parent",
            )
            root = Path(adapter["path"])
            require(
                root.name == f"checkpoint-{step}"
                and root.parent.name == "checkpoints"
                and adapter.get("checkpoint_seal", {}).get("path") == str(root / "COMPLETE.json"),
                "half/end checkpoint seal path mismatch",
            )


def frozen_inputs():
    manifest_raw = pinned(FROZEN / "manifest.json", MANIFEST_SHA)
    manifest = parse(manifest_raw)
    require(
        not any((FROZEN / p).exists() for p in ("FAILED.json", "manifest.FAILED.json")),
        "failed frozen development artifact",
    )
    payloads = {p: pinned(FROZEN / p, ref["sha256"]) for p, ref in manifest["artifacts"].items()}
    for path, raw in payloads.items():
        require(len(raw) == manifest["artifacts"][path]["bytes"], "frozen byte count mismatch")
    prompts = rows(payloads["prompts.jsonl"])
    keys, rubrics = (
        index(rows(payloads["mc_keys.jsonl"])),
        index(rows(payloads["tutor_rubrics.jsonl"])),
    )
    require(
        len(prompts) == 72 and len(index(prompts)) == 72 and len(keys) == 64 and len(rubrics) == 8,
        "frozen count mismatch",
    )
    require(
        [r["id"] for r in prompts] == list(keys) + list(rubrics) == manifest["ids"],
        "frozen IDs mismatch",
    )
    for row in prompts:
        require(set(row) == {"id", "messages"}, "frozen prompt schema")
        key = (keys | rubrics)[row["id"]]
        require(
            sha(canonical(row["messages"])) == key["model_messages_sha256"],
            "frozen messages mismatch",
        )
    return prompts, keys, rubrics


def validate_candidate(root, candidate_id, config, config_sha, prompts):
    """Validate copied run evidence, not remote weight bytes or tokenizer re-decoding."""
    root = Path(root)
    require(not (root / "FAILED.json").exists(), "failed candidate cannot be compared")
    seal_raw = read(root / "COMPLETED.json")
    seal = parse(seal_raw)
    files = inventory(root, omit=("COMPLETED.json",))
    expected_files = {"REQUEST.json", "host-before.json", "initialized.json", "responses.jsonl"}
    expected_files.update(f"batches/batch-{i:04d}.json" for i in range(9))
    require({r["path"] for r in files} == expected_files, "candidate inventory incomplete/extra")
    remote_root = str(Path(config["output"]) / candidate_id)
    check_tree(seal["inventory"], files, remote_root)
    expected_ids = [r["id"] for r in prompts]
    require(
        seal["status"] == "complete"
        and seal["candidate_id"] == candidate_id
        and seal["completed_count"] == 72
        and seal["completed_ids"] == expected_ids
        and seal["ranking_performed"] is False,
        "candidate incomplete/wrong identity",
    )
    require(
        seal["config"]["sha256"] == config_sha
        and seal["source_sha256"] == SOURCE_HASHES
        and seal["prompts"] == config["prompts"],
        "terminal config/source/prompt mismatch",
    )
    raw = read(root / "responses.jsonl")
    require(
        seal["responses"]
        == {"path": remote_root + "/responses.jsonl", "sha256": sha(raw), "bytes": len(raw)},
        "responses receipt mismatch",
    )
    response_rows = rows(raw)
    require([r["id"] for r in response_rows] == expected_ids, "responses not exactly72 ordered IDs")
    request = parse(read(root / "REQUEST.json"))
    candidate = config["candidates"][candidate_id]
    require(
        request["config"] == seal["config"]
        and request["candidate"] == candidate
        and request["prompt_ref"] == config["prompts"]
        and request["source_sha256"] == SOURCE_HASHES,
        "request/config mismatch",
    )
    for name in ("base", "tokenizer", "adapter"):
        identity, expected = request["identities"][name], candidate.get(name)
        if expected is None:
            require(identity is None, "unexpected adapter identity")
        else:
            check_tree(identity, identity["files"], expected["path"])
            require(
                identity["tree_sha256"] == expected["tree_sha256"],
                "model/tokenizer/adapter identity mismatch",
            )
    initialized = parse(read(root / "initialized.json"))["model"]
    adapter_present = bool(candidate.get("adapter"))
    require(
        initialized["adapter_loads"] == int(adapter_present)
        and initialized["merged"] is False
        and initialized["operation"]
        == ("exact_adapter_once_on_original_parent" if adapter_present else "bare_parent"),
        "loaded-model operation mismatch",
    )
    if adapter_present:
        adapter_files = {r["path"]: r for r in request["identities"]["adapter"]["files"]}
        require(
            "adapter_model.safetensors" in adapter_files
            and initialized.get("exact_tensor_values_loaded") is True
            and type(initialized.get("source_tensor_count")) is int
            and initialized["source_tensor_count"] > 0
            and initialized.get("source_safetensors_sha256")
            == adapter_files["adapter_model.safetensors"]["sha256"],
            "loaded adapter tensor proof mismatch",
        )
        if "checkpoint_seal" in candidate["adapter"]:
            required = {
                "COMPLETE.json",
                "adapter_model.safetensors",
                "adapter_config.json",
                "training-state.pt",
                "state.json",
            }
            require(
                required <= set(adapter_files)
                and set(adapter_files) <= required | {"README.md"}
                and all(type(r["bytes"]) is int and r["bytes"] > 0 for r in adapter_files.values()),
                "required checkpoint file inventory missing/extra/empty",
            )
            require(
                "COMPLETE.json" in adapter_files
                and adapter_files["COMPLETE.json"]["sha256"]
                == candidate["adapter"]["checkpoint_seal"]["sha256"],
                "checkpoint seal inventory binding mismatch",
            )
    for batch_index in range(9):
        batch = parse(read(root / "batches" / f"batch-{batch_index:04d}.json"))
        offset = batch_index * 8
        require(
            batch["offset"] == offset
            and batch["candidate_id"] == candidate_id
            and batch["config_sha256"] == config_sha,
            "raw batch identity mismatch",
        )
        require(
            all(
                len(batch[k]) == 8
                for k in ("prompts", "padded_prompt_ids", "attention_mask", "returned_sequence_ids")
            ),
            "raw batch count mismatch",
        )
        for n, row in enumerate(response_rows[offset : offset + 8]):
            prompt = prompts[offset + n]
            require(
                {k: row[k] for k in ("id", "messages")} == prompt
                and row["candidate_id"] == candidate_id
                and row["profile"] == candidate["profile"],
                "response prompt/candidate join mismatch",
            )
            require(
                batch["prompts"][n]
                == {k: row[k] for k in ("id", "messages", "rendered_prompt", "prompt_ids")},
                "batch rendered-prompt mismatch",
            )
            require(
                batch["padded_prompt_ids"][n] == row["padded_prompt_ids"]
                and batch["attention_mask"][n] == row["attention_mask"]
                and batch["returned_sequence_ids"][n]
                == row["padded_prompt_ids"] + row["generated_ids"],
                "batch token/response join mismatch",
            )
            padded, mask, generated = (
                row["padded_prompt_ids"],
                row["attention_mask"],
                row["generated_ids"],
            )
            require(
                type(generated) is list
                and 0 < len(generated) <= 1024
                and all(type(t) is int and t >= 0 for t in generated),
                "invalid generated IDs",
            )
            require(
                len(mask) == len(padded)
                and mask == sorted(mask)
                and set(mask) <= {0, 1}
                and [t for t, m in zip(padded, mask, strict=True) if m] == row["prompt_ids"]
                and all(
                    t == row["pad_token_id"] for t, m in zip(padded, mask, strict=True) if not m
                )
                and len(row["prompt_ids"]) + 1024 <= 4096,
                "padding/context mismatch",
            )
            eos = next((i for i, t in enumerate(generated) if t == row["eos_token_id"]), None)
            active = len(generated) if eos is None else eos + 1
            require(
                row["finish_reason"] == ("token_cap" if eos is None else "eos")
                and (eos is not None or active == 1024)
                and row["generated_tokens_through_eos"] == active
                and row["batch_padding_tokens"] == len(generated) - active
                and all(t == row["pad_token_id"] for t in generated[active:]),
                "EOS/cap accounting mismatch",
            )
            require(
                type(row["continuation"]) is str and type(row["raw_continuation"]) is str,
                "response text type",
            )
            require(
                row["rendered_prompt"].endswith("<think>\n")
                == (candidate["profile"] == "deepseek_native"),
                "native reasoning prefix mismatch",
            )
    require(
        inventory(root, omit=("COMPLETED.json",)) == files
        and read(root / "COMPLETED.json") == seal_raw,
        "candidate changed during verification",
    )
    return response_rows, [sha(line) for line in raw.splitlines(keepends=True)], sha(seal_raw)


def _publish(output, artifacts, metadata):
    output = Path(output).absolute()
    require(
        not output.exists() and all(not p.is_symlink() for p in (output, *output.parents)),
        "existing/symlinked output",
    )
    require(
        metadata["code_bindings"] == code_identity(), "compiler source changed before publication"
    )
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, raw in artifacts.items():
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(raw)
        require(
            metadata["code_bindings"] == code_identity(),
            "compiler source changed during publication",
        )
        require(
            all(read(output / name) == raw for name, raw in artifacts.items()),
            "output changed before seal",
        )
        metadata = metadata | {
            "files": inventory(output),
            "compiler_sha256": sha(read(__file__)),
            "heldout_reducer_sha256": HELDOUT_SHA,
        }
        with (output / "SEALED.json").open("xb") as handle:
            handle.write(canonical(metadata) + b"\n")
    except BaseException as exc:
        failure = {"error": str(exc), "automatic_retry": False}
        try:
            if (output / "SEALED.json").exists():
                require(
                    not (output / "SEALED.FAILED.json").exists(), "preserve existing failed seal"
                )
                (output / "SEALED.json").rename(output / "SEALED.FAILED.json")
        except (OSError, ValueError) as preservation_error:
            failure["seal_preservation_error"] = str(preservation_error)
        try:
            with (output / "FAILED.json").open("xb") as handle:
                handle.write(canonical(failure) + b"\n")
        except OSError as marker_error:
            raise RuntimeError(
                f"Publication failed ({exc}); failure marker unavailable: {marker_error}"
            ) from exc
        raise
    return metadata


def jsonl(records):
    return b"".join(canonical(r) + b"\n" for r in records)


def build_packet(
    *,
    config_path,
    config_sha256,
    runs,
    roster_path,
    roster_sha256,
    mask_key_path,
    completion_manifest,
    completion_manifest_sha256,
    output,
):
    pinned(PROTOCOL, PROTOCOL_SHA)
    source_identity = code_identity()
    separate_output(output, (runs, FROZEN))
    require(
        config_sha256 == CAMPAIGN_SHA and roster_sha256 == ROSTER_SHA,
        "campaign/roster is not the exact admitted treatment",
    )
    config_raw, roster_raw, mask_key = (
        pinned(config_path, config_sha256),
        pinned(roster_path, roster_sha256),
        read(mask_key_path),
    )
    config, roster_doc = parse(config_raw), parse(roster_raw)
    require(
        set(roster_doc) == {"schema_version", "config_sha256", "candidates"}
        and roster_doc["schema_version"] == 1
        and roster_doc["config_sha256"] == config_sha256,
        "roster/config binding",
    )
    roster = roster_doc["candidates"]
    validate_lineages(config, roster)
    completion_raw = pinned(completion_manifest, completion_manifest_sha256)
    completion = parse(completion_raw)
    require(
        set(completion) == {"schema_version", "status", "config_sha256", "candidates"}
        and completion["schema_version"] == 1
        and completion["status"] == "all12_complete"
        and completion["config_sha256"] == config_sha256
        and set(completion["candidates"]) == set(roster),
        "external completion manifest incomplete/mismatched",
    )
    require(
        set(config["candidates"]) == set(roster)
        and config["source_sha256"] == SOURCE_HASHES
        and canonical(config["generation"]) == canonical(GENERATION),
        "campaign source/settings/roster mismatch",
    )
    for name, digest in SOURCE_HASHES.items():
        pinned(Path(__file__).with_name(name), digest)
    require(len(mask_key) == 32, "mask key must be exactly32 separately retained bytes")
    prompts, keys, rubrics = frozen_inputs()
    require(
        config["prompts"]["sha256"] == sha(read(FROZEN / "prompts.jsonl")),
        "campaign prompt hash mismatch",
    )
    packets, mapping, seals = [], [], {}
    for candidate_id in config["candidates"]:
        captured = completion["candidates"][candidate_id]
        require(
            set(captured) == {"remote_root", "completed_sha256"}
            and captured["remote_root"] == str(Path(config["output"]) / candidate_id),
            "external completion identity mismatch",
        )
        pinned(Path(runs) / candidate_id / "COMPLETED.json", captured["completed_sha256"])
        values, raw_hashes, seal_sha = validate_candidate(
            Path(runs) / candidate_id, candidate_id, config, config_sha256, prompts
        )
        require(
            seal_sha == captured["completed_sha256"],
            "candidate completion changed after external binding",
        )
        seals[candidate_id] = seal_sha
        for row, raw_sha in zip(values, raw_hashes, strict=True):
            review_id = (
                "d72-"
                + hmac.new(
                    mask_key, canonical([candidate_id, row["id"]]), hashlib.sha256
                ).hexdigest()[:32]
            )
            item = {
                "review_id": review_id,
                "messages": row["messages"],
                "response": row["continuation"],
                "response_sha256": sha(row["continuation"].encode()),
                "finish_reason": row["finish_reason"],
                "reasoning_prefix_already_open": row["rendered_prompt"].endswith("<think>\n"),
            }
            if row["id"] in keys:
                item |= {
                    "kind": "mc",
                    "key": {
                        k: keys[row["id"]][k] for k in ("choices", "answer_index", "answer_text")
                    },
                }
            else:
                item |= {"kind": "tutor", "case": rubrics[row["id"]]}
            packets.append(item)
            mapping.append(
                {
                    "review_id": review_id,
                    "candidate_id": candidate_id,
                    "item_id": row["id"],
                    "raw_row_sha256": raw_sha,
                    "packet_row_sha256": sha(canonical(item)),
                    "response_sha256": item["response_sha256"],
                    "candidate_seal_sha256": seal_sha,
                }
            )
    require(len({r["review_id"] for r in packets}) == 864, "mask collision/count mismatch")
    packets.sort(key=lambda r: r["review_id"])
    mapping.sort(key=lambda r: r["review_id"])
    require(
        read(config_path) == config_raw and read(roster_path) == roster_raw,
        "campaign inputs mutated",
    )
    artifacts = {
        "reviewer/mc.jsonl": jsonl([r for r in packets if r["kind"] == "mc"]),
        "reviewer/tutor.jsonl": jsonl([r for r in packets if r["kind"] == "tutor"]),
        "private-mapping.jsonl": jsonl(mapping),
        "roster.json": roster_raw,
        "config.json": config_raw,
        "completion-manifest.json": completion_raw,
    }
    return _publish(
        output,
        artifacts,
        {
            "status": "all12_complete_identity_masked",
            "rows": 864,
            "config_sha256": config_sha256,
            "roster_sha256": roster_sha256,
            "mask_key_sha256": sha(mask_key),
            "candidate_seals": seals,
            "completion_manifest_sha256": completion_manifest_sha256,
            "code_bindings": source_identity,
            "frozen_manifest_sha256": MANIFEST_SHA,
            "protocol_sha256": sha(read(PROTOCOL)),
            "limits": "Identity-masked agent review; raw style and native reasoning state may reveal model characteristics. "
            "Remote model bytes were verified by the pinned runner; this offline join does not re-decode tokens or rehash remote weights.",
        },
    )


def select_candidates(scores, roster):
    validate_roster(roster)
    require(type(scores) is dict and set(scores) == set(roster), "scores/roster candidate mismatch")
    for row in scores.values():
        required_fields = {"M", "S", "T", "critical_cases", "caps", "mc_correct"}
        optional_fields = {
            "delivered_final_answers",
            "mc_explanatory_falsehoods",
            "mc_format_adherent",
        }
        require(
            type(row) is dict
            and required_fields <= set(row)
            and set(row) <= required_fields | optional_fields,
            "score row schema mismatch",
        )
        for name, high in (("M", 64), ("S", 32), ("T", 32), ("critical_cases", 8), ("caps", 72)):
            require(type(row[name]) is int and 0 <= row[name] <= high, "score count/bound mismatch")
        require(
            type(row["mc_correct"]) is list
            and len(row["mc_correct"]) == 64
            and all(type(v) is bool for v in row["mc_correct"])
            and sum(row["mc_correct"]) == row["M"],
            "MC vector/count mismatch",
        )
        require(
            all(type(row[k]) is int and 0 <= row[k] <= 64 for k in optional_fields if k in row),
            "optional MC report count/bound mismatch",
        )

    def order(candidate):
        row = scores[candidate]
        return (-(row["M"] + row["S"] + row["T"]), -row["M"], -row["S"], roster[candidate]["step"])

    lineages = []
    for lineage in ("P1", "P2", "P3", "P4"):
        members = [c for c in roster if roster[c]["lineage"] == lineage]
        control = next(c for c in members if roster[c]["role"] == "control")
        chosen = min((c for c in members if roster[c]["role"] == "pilot"), key=order)
        pairs = list(zip(scores[control]["mc_correct"], scores[chosen]["mc_correct"], strict=True))
        losses, gains = sum(a and not b for a, b in pairs), sum(b and not a for a, b in pairs)
        critical_delta = scores[chosen]["critical_cases"] - scores[control]["critical_cases"]
        lineages.append(
            {
                "lineage": lineage,
                "candidate_id": chosen,
                "selected_checkpoint": roster[chosen]["step"],
                "control": control,
                "paired_losses": losses,
                "paired_gains": gains,
                "net_mc_change": gains - losses,
                "critical_case_delta": critical_delta,
                "eligible": losses <= 2 and critical_delta <= 0,
            }
        )
    eligible = sorted(
        (r for r in lineages if r["eligible"]),
        key=lambda r: (*order(r["candidate_id"])[:3], r["lineage"]),
    )
    candidates = [
        {
            "candidate_id": c,
            **roster[c],
            **scores[c],
            "index_numerator": scores[c]["M"] + scores[c]["S"] + scores[c]["T"],
            "index_percent": 100 * (scores[c]["M"] + scores[c]["S"] + scores[c]["T"]) / 128,
        }
        for c in roster
    ]
    return {
        "candidates": candidates,
        "lineages": lineages,
        "advance": [r["candidate_id"] for r in eligible[:2]],
    }


def evidence(item, response):
    require(
        type(item["rationale"]) is str and item["rationale"].strip(), "semantic rationale required"
    )
    require(
        type(item["evidence"]) is list
        and all(type(s) is str and s.strip() and s in response for s in item["evidence"]),
        "evidence not an exact response span",
    )


def judge(row, packet):
    common = {"review_id", "reviewer", "packet_row_sha256", "response_sha256"}
    require(
        row["review_id"] == packet["review_id"]
        and type(row["reviewer"]) is str
        and row["reviewer"].strip()
        and row["packet_row_sha256"] == sha(canonical(packet))
        and row["response_sha256"] == sha(packet["response"].encode()),
        "review identity/hash mismatch",
    )
    if packet["kind"] == "mc":
        fields = {
            "chosen_index",
            "ambiguity",
            "explanatory_falsehood",
            "format_adherent",
            "delivered_final_answer",
            "rationale",
            "evidence",
        }
        require(set(row) == common | fields, "MC review schema mismatch")
        require(
            row["chosen_index"] is None
            or (
                type(row["chosen_index"]) is int
                and 0 <= row["chosen_index"] < len(packet["key"]["choices"])
            ),
            "invalid selected choice",
        )
        require(
            all(type(row[k]) is bool for k in fields - {"chosen_index", "rationale", "evidence"}),
            "MC flags must be boolean",
        )
        evidence(row, packet["response"])
        require(
            not row["ambiguity"] or row["chosen_index"] is None,
            "ambiguous answer must not claim one committed choice",
        )
        require(
            not (
                row["chosen_index"] is not None
                or row["ambiguity"]
                or row["explanatory_falsehood"]
                or row["delivered_final_answer"]
                or row["format_adherent"]
            )
            or bool(row["evidence"]),
            "affirmed MC judgment needs evidence",
        )
        require(
            not (packet["reasoning_prefix_already_open"] and "</think>" not in packet["response"])
            or not row["delivered_final_answer"],
            "unclosed reasoning is not delivered final answer",
        )
        return {
            "correct": row["chosen_index"] == packet["key"]["answer_index"]
            and not row["ambiguity"],
            "semantic": {k: row[k] for k in fields - {"rationale", "evidence"}},
        }
    require(set(row) == common | {"assessment"}, "tutor review schema mismatch")
    if packet["response"].strip():
        score = heldout.score_assessment(packet["case"], packet["response"], row["assessment"])
    else:
        assessment = row["assessment"]
        require(
            set(assessment) == {"science", "tutoring", "critical_errors", "additional_errors"},
            "empty assessment schema",
        )
        for axis in ("science", "tutoring", "critical_errors"):
            require(
                set(assessment[axis]) == {r["id"] for r in packet["case"]["rubric"][axis]},
                "empty criterion IDs",
            )
            flag = "present" if axis == "critical_errors" else "met"
            for value in assessment[axis].values():
                heldout._validate_judgment(value, packet["response"], flag)
                require(value[flag] is False, "empty response cannot affirm criteria/errors")
        require(
            assessment["additional_errors"] == [], "empty response cannot affirm additional errors"
        )
        score = {
            "science": 0,
            "tutoring": 0,
            "critical_errors_present": 0,
            "empty_response_zero": True,
        }
    semantic = {
        axis: {
            k: v["present" if axis == "critical_errors" else "met"]
            for k, v in row["assessment"][axis].items()
        }
        for axis in ("science", "tutoring", "critical_errors")
    }
    # Different added-error content requires adjudication even when scores agree.
    semantic["additional_errors"] = row["assessment"]["additional_errors"]
    return {"score": score, "semantic": semantic}


def _review_index(values):
    return index([{"id": r["review_id"], **r} for r in values])


def _strip_index(row):
    return {k: v for k, v in row.items() if k != "id"}


def compile_review(
    *,
    packet,
    packet_sha256,
    primary,
    primary_sha256,
    secondary,
    secondary_sha256,
    adjudication,
    adjudication_sha256,
    output,
):
    pinned(PROTOCOL, PROTOCOL_SHA)
    source_identity = code_identity()
    separate_output(output, (packet, FROZEN))
    packet = Path(packet)
    seal_raw = pinned(packet / "SEALED.json", packet_sha256)
    seal = parse(seal_raw)
    require(
        seal["status"] == "all12_complete_identity_masked"
        and seal["files"] == inventory(packet, omit=("SEALED.json",))
        and seal["frozen_manifest_sha256"] == MANIFEST_SHA
        and seal["protocol_sha256"] == sha(read(PROTOCOL)),
        "packet seal/inventory/protocol mismatch",
    )
    require(
        seal["compiler_sha256"] == sha(read(__file__))
        and seal["heldout_reducer_sha256"] == HELDOUT_SHA
        and seal["code_bindings"] == source_identity,
        "packet compiler/reducer identity mismatch",
    )
    require(
        seal["config_sha256"] == CAMPAIGN_SHA and seal["roster_sha256"] == ROSTER_SHA,
        "packet campaign/roster is not exact admitted treatment",
    )
    completion = parse(
        pinned(packet / "completion-manifest.json", seal["completion_manifest_sha256"])
    )
    require(
        completion["status"] == "all12_complete"
        and completion["config_sha256"] == CAMPAIGN_SHA
        and {k: v["completed_sha256"] for k, v in completion["candidates"].items()}
        == seal["candidate_seals"],
        "packet external completion bindings mismatch",
    )
    values = rows(read(packet / "reviewer/mc.jsonl")) + rows(read(packet / "reviewer/tutor.jsonl"))
    by_id = _review_index(values)
    mapping = _review_index(rows(read(packet / "private-mapping.jsonl")))
    require(len(by_id) == 864 and set(by_id) == set(mapping), "packet/mapping coverage")
    prompts, keys, rubrics = frozen_inputs()
    prompt_map = index(prompts)
    roster_doc = parse(pinned(packet / "roster.json", seal["roster_sha256"]))
    roster = roster_doc["candidates"]
    validate_roster(roster)
    require(roster_doc["config_sha256"] == seal["config_sha256"], "packet roster/config mismatch")
    packet_config = parse(pinned(packet / "config.json", seal["config_sha256"]))
    validate_lineages(packet_config, roster)
    expected_pairs = {(c, r["id"]) for c in roster for r in prompts}
    require(
        {(m["candidate_id"], m["item_id"]) for m in mapping.values()} == expected_pairs,
        "masked mapping joins incomplete",
    )
    for key, indexed in by_id.items():
        item, ref = _strip_index(indexed), mapping[key]
        permitted = {
            "review_id",
            "messages",
            "response",
            "response_sha256",
            "finish_reason",
            "reasoning_prefix_already_open",
            "kind",
        }
        require(
            set(item) == permitted | ({"key"} if item["kind"] == "mc" else {"case"})
            and type(item["reasoning_prefix_already_open"]) is bool
            and item["finish_reason"] in ("eos", "token_cap"),
            "masked reviewer packet schema/leakage",
        )
        require(
            ref["packet_row_sha256"] == sha(canonical(item))
            and ref["response_sha256"] == item["response_sha256"]
            and sha(item["response"].encode()) == item["response_sha256"]
            and item["messages"] == prompt_map[ref["item_id"]]["messages"],
            "masked packet row/hash join",
        )
        require(
            ref["candidate_seal_sha256"] == seal["candidate_seals"][ref["candidate_id"]],
            "mapping candidate seal mismatch",
        )
        if item["kind"] == "mc":
            require(
                item["key"]
                == {k: keys[ref["item_id"]][k] for k in ("choices", "answer_index", "answer_text")},
                "MC key drift",
            )
        else:
            require(
                item["kind"] == "tutor" and item["case"] == rubrics[ref["item_id"]],
                "tutor rubric drift",
            )
    original_raw = {
        "primary.jsonl": pinned(primary, primary_sha256),
        "secondary.jsonl": pinned(secondary, secondary_sha256),
        "adjudication.jsonl": pinned(adjudication, adjudication_sha256),
    }
    a, b = (_review_index(rows(original_raw[p])) for p in ("primary.jsonl", "secondary.jsonl"))
    require(set(a) == set(by_id) and set(b) <= set(by_id), "review coverage mismatch")
    scored_a = {k: judge(_strip_index(r), _strip_index(by_id[k])) for k, r in a.items()}
    audit_ids = set(
        sorted(keys, key=lambda key: sha(("3407:science-mc-audit:" + key).encode()))[:8]
    )
    required_b = {
        k
        for k in by_id
        if by_id[k]["kind"] == "tutor"
        or not scored_a[k]["correct"]
        or a[k]["ambiguity"]
        or mapping[k]["item_id"] in audit_ids
    }
    require(required_b <= set(b), "mandatory independent secondary reviews missing")
    scored_b = {}
    for key, item in b.items():
        require(item["reviewer"] != a[key]["reviewer"], "secondary reviewer must be independent")
        scored_b[key] = judge(_strip_index(item), _strip_index(by_id[key]))
    different = {k for k in b if scored_a[k]["semantic"] != scored_b[k]["semantic"]}
    # Empty adjudication file is valid only when there are zero disagreements.
    resolution_rows = (
        rows(original_raw["adjudication.jsonl"])
        if original_raw["adjudication.jsonl"].strip()
        else []
    )
    resolutions = _review_index(resolution_rows)
    require(set(resolutions) == different, "explicit adjudication coverage mismatch")
    final = {k: _strip_index(r) for k, r in a.items()}
    for key, indexed in resolutions.items():
        resolution = _strip_index(indexed)
        require(
            set(resolution)
            == {
                "review_id",
                "primary_row_sha256",
                "secondary_row_sha256",
                "rationale",
                "evidence",
                "decision",
            },
            "adjudication schema",
        )
        require(
            resolution["primary_row_sha256"] == sha(canonical(_strip_index(a[key])))
            and resolution["secondary_row_sha256"] == sha(canonical(_strip_index(b[key]))),
            "adjudication originals hash mismatch",
        )
        evidence(resolution, by_id[key]["response"])
        require(
            not by_id[key]["response"].strip() or bool(resolution["evidence"]),
            "adjudication needs response evidence",
        )
        require(resolution["decision"]["review_id"] == key, "adjudication decision ID mismatch")
        judge(resolution["decision"], _strip_index(by_id[key]))
        final[key] = resolution["decision"]
    totals = {
        c: {
            "M": 0,
            "S": 0,
            "T": 0,
            "critical_cases": 0,
            "caps": 0,
            "mc_correct": [False] * 64,
            "delivered_final_answers": 0,
            "mc_explanatory_falsehoods": 0,
            "mc_format_adherent": 0,
        }
        for c in roster
    }
    mc_order = {key: n for n, key in enumerate(keys)}
    final_rows = []
    for key in sorted(final):
        item, assessment, ref = _strip_index(by_id[key]), final[key], mapping[key]
        score = judge(assessment, item)
        target = totals[ref["candidate_id"]]
        target["caps"] += item["finish_reason"] == "token_cap"
        if item["kind"] == "mc":
            target["M"] += score["correct"]
            target["mc_correct"][mc_order[ref["item_id"]]] = score["correct"]
            target["delivered_final_answers"] += assessment["delivered_final_answer"]
            target["mc_explanatory_falsehoods"] += assessment["explanatory_falsehood"]
            target["mc_format_adherent"] += assessment["format_adherent"]
        else:
            target["S"] += score["score"]["science"]
            target["T"] += score["score"]["tutoring"]
            target["critical_cases"] += score["score"]["critical_errors_present"] > 0
        final_rows.append(
            {
                "review_id": key,
                "assessment": assessment,
                "score": score,
                "review_passes": 2 if key in b else 1,
                "adjudicated": key in different,
            }
        )
    result = select_candidates(totals, roster) | {
        "audit_mc_item_ids": sorted(audit_ids),
        "primary_rows": 864,
        "secondary_rows": len(b),
        "adjudicated_rows": len(different),
        "single_review_rows": 864 - len(b),
        "mc_denominator": 64,
        "tutor_science_denominator": 32,
        "tutor_teaching_denominator": 32,
        "limit": "Identity-masked agent diagnostic, not a hardware score or universal superiority claim. "
        "Primary-correct MC outside the fixed audit may have only one reviewer.",
    }
    require(
        read(packet / "SEALED.json") == seal_raw
        and inventory(packet, omit=("SEALED.json",)) == seal["files"],
        "packet changed during compile",
    )
    artifacts = original_raw | {
        "final-assessments.jsonl": jsonl(final_rows),
        "scores.json": canonical(result) + b"\n",
    }
    return _publish(
        output,
        artifacts,
        {
            "status": "complete_evidence_backed_development_selection",
            "code_bindings": source_identity,
            "packet_seal_sha256": packet_sha256,
            "protocol_sha256": sha(read(PROTOCOL)),
            "score_rows": 12,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    packet = commands.add_parser("packet")
    for name in (
        "config",
        "config-sha256",
        "runs",
        "roster",
        "roster-sha256",
        "mask-key",
        "completion-manifest",
        "completion-manifest-sha256",
        "output",
    ):
        packet.add_argument("--" + name, required=True)
    compile_cmd = commands.add_parser("compile")
    for name in (
        "packet",
        "packet-sha256",
        "primary",
        "primary-sha256",
        "secondary",
        "secondary-sha256",
        "adjudication",
        "adjudication-sha256",
        "output",
    ):
        compile_cmd.add_argument("--" + name, required=True)
    args = vars(parser.parse_args())
    if args.pop("command") == "packet":
        args["config_path"] = args.pop("config")
        args["roster_path"] = args.pop("roster")
        args["mask_key_path"] = args.pop("mask_key")
        print(json.dumps(build_packet(**args), sort_keys=True))
    else:
        print(json.dumps(compile_review(**args), sort_keys=True))


if __name__ == "__main__":
    main()
