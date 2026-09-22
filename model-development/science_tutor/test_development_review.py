"""Synthetic transport/ledger tests only; never read actual model outputs."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "development_review", Path(__file__).with_name("development_review.py")
)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def write(path, value, *, jsonl=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(review.jsonl(value) if jsonl else review.canonical(value) + b"\n")
    return review.sha(path.read_bytes())


def receipt(path, raw):
    return {"path": str(path), "sha256": review.sha(raw), "bytes": len(raw)}


def tree(files, root):
    return {
        "root": root,
        "files": files,
        "file_count": len(files),
        "bytes": sum(r["bytes"] for r in files),
        "tree_sha256": review.tree_sha(files),
    }


def reseal_run(path):
    seal = review.parse((path / "COMPLETED.json").read_bytes())
    seal["inventory"] = tree(
        review.inventory(path, omit=("COMPLETED.json",)), seal["inventory"]["root"]
    )
    seal["responses"] = receipt(seal["responses"]["path"], (path / "responses.jsonl").read_bytes())
    write(path / "COMPLETED.json", seal)


@pytest.fixture(scope="module")
def campaign(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic-development-campaign").resolve()
    prompts, keys, rubrics = review.frozen_inputs()
    roster, candidates = {}, {}
    model_files = [{"path": "weights.bin", "sha256": "a" * 64, "bytes": 1}]
    adapter_files_by_id = {}
    for lineage in range(1, 5):
        for name, role, step in (
            (f"C{lineage}", "control", 0),
            (f"P{lineage}-half", "pilot", 63),
            (f"P{lineage}-end", "pilot", 126),
        ):
            roster[name] = {"lineage": f"P{lineage}", "role": role, "step": step}
            candidates[name] = {
                "base": {
                    "path": f"/synthetic/model-{lineage}",
                    "tree_sha256": review.tree_sha(model_files),
                },
                "tokenizer": {
                    "path": "/synthetic/tokenizer",
                    "tree_sha256": review.tree_sha(model_files),
                },
                "profile": "deepseek_native" if lineage == 4 else "qwen_native",
                "chat_template_sha256": (
                    "56a1447ad31926fdc21fb07e56e5642bd9c850c4f52d8c8af7bbe5f079a84f5f"
                    if lineage == 4
                    else "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"
                ),
            }
            if role == "pilot" or name == "C3":
                adapter_files = [
                    {"path": "adapter_model.safetensors", "sha256": "c" * 64, "bytes": 16}
                ]
                adapter_path = (
                    f"/synthetic/{lineage}/checkpoints/checkpoint-{step}"
                    if role == "pilot"
                    else "/synthetic/control-adapter"
                )
                adapter = {
                    "path": adapter_path,
                    "parent_base_tree_sha256": review.tree_sha(model_files),
                }
                if role == "pilot":
                    adapter_files.insert(
                        0, {"path": "COMPLETE.json", "sha256": "d" * 64, "bytes": 100}
                    )
                    adapter_files.extend(
                        {"path": file, "sha256": "e" * 64, "bytes": 10}
                        for file in ("adapter_config.json", "state.json", "training-state.pt")
                    )
                    adapter_files.sort(key=lambda row: row["path"])
                    adapter["checkpoint_seal"] = {
                        "path": adapter_path + "/COMPLETE.json",
                        "sha256": "d" * 64,
                    }
                adapter["tree_sha256"] = review.tree_sha(adapter_files)
                candidates[name]["adapter"] = adapter
                adapter_files_by_id[name] = adapter_files
    config = {
        "schema_version": 1,
        "output": "/synthetic/oracle-development",
        "gpu_lock": "/synthetic/shared.lock",
        "prompts": receipt(
            "/synthetic/prompts.jsonl", (review.FROZEN / "prompts.jsonl").read_bytes()
        ),
        "source_sha256": review.SOURCE_HASHES,
        "generation": review.GENERATION,
        "candidates": candidates,
    }
    config_sha = write(root / "config.json", config)
    roster_sha = write(
        root / "roster.json",
        {"schema_version": 1, "config_sha256": config_sha, "candidates": roster},
    )
    (root / "mask.key").write_bytes(bytes(range(32)))
    config_ref = receipt("/synthetic/config.json", (root / "config.json").read_bytes())
    for candidate_id, candidate in candidates.items():
        path = root / "runs" / candidate_id
        remote_root = config["output"] + "/" + candidate_id
        request = {
            "config": config_ref,
            "candidate": candidate,
            "identities": {
                "base": tree(model_files, candidate["base"]["path"]),
                "tokenizer": tree(model_files, candidate["tokenizer"]["path"]),
                "adapter": (
                    tree(adapter_files_by_id[candidate_id], candidate["adapter"]["path"])
                    if candidate.get("adapter")
                    else None
                ),
            },
            "prompt_ref": config["prompts"],
            "source_sha256": review.SOURCE_HASHES,
        }
        write(path / "REQUEST.json", request)
        write(path / "host-before.json", {"synthetic": True})
        initialized = {"operation": "bare_parent", "adapter_loads": 0, "merged": False}
        if candidate.get("adapter"):
            initialized |= {
                "operation": "exact_adapter_once_on_original_parent",
                "adapter_loads": 1,
                "exact_tensor_values_loaded": True,
                "source_safetensors_sha256": "c" * 64,
                "source_tensor_count": 196,
            }
        write(path / "initialized.json", {"model": initialized})
        deepseek = candidate["profile"] == "deepseek_native"
        response_rows = []
        for prompt in prompts:
            response_rows.append(
                {
                    **prompt,
                    "candidate_id": candidate_id,
                    "profile": candidate["profile"],
                    "rendered_prompt": "Synthetic native prompt"
                    + ("<think>\n" if deepseek else ""),
                    "prompt_ids": [10, 11],
                    "padded_prompt_ids": [10, 11],
                    "attention_mask": [1, 1],
                    "generated_ids": [22, 42 if deepseek else 2],
                    "continuation": ("</think>" if deepseek else "") + "Synthetic answer.<eos>",
                    "raw_continuation": ("</think>" if deepseek else "") + "Synthetic answer.<eos>",
                    "finish_reason": "eos",
                    "generated_tokens_through_eos": 2,
                    "batch_padding_tokens": 0,
                    "eos_token_id": 42 if deepseek else 2,
                    "pad_token_id": 43 if deepseek else 0,
                    "batch_seconds": 1.0,
                }
            )
        for number in range(9):
            subset = response_rows[number * 8 : number * 8 + 8]
            write(
                path / "batches" / f"batch-{number:04d}.json",
                {
                    "offset": number * 8,
                    "candidate_id": candidate_id,
                    "config_sha256": config_sha,
                    "prompts": [
                        {k: r[k] for k in ("id", "messages", "rendered_prompt", "prompt_ids")}
                        for r in subset
                    ],
                    "padded_prompt_ids": [r["padded_prompt_ids"] for r in subset],
                    "attention_mask": [r["attention_mask"] for r in subset],
                    "returned_sequence_ids": [
                        r["padded_prompt_ids"] + r["generated_ids"] for r in subset
                    ],
                },
            )
        write(path / "responses.jsonl", response_rows, jsonl=True)
        seal = {
            "status": "complete",
            "candidate_id": candidate_id,
            "config": config_ref,
            "source_sha256": review.SOURCE_HASHES,
            "prompts": config["prompts"],
            "completed_ids": [r["id"] for r in prompts],
            "completed_count": 72,
            "ranking_performed": False,
            "responses": receipt(
                remote_root + "/responses.jsonl", (path / "responses.jsonl").read_bytes()
            ),
            "inventory": tree(review.inventory(path), remote_root),
        }
        write(path / "COMPLETED.json", seal)
    completion_sha = write(
        root / "completion-manifest.json",
        {
            "schema_version": 1,
            "status": "all12_complete",
            "config_sha256": config_sha,
            "candidates": {
                name: {
                    "remote_root": config["output"] + "/" + name,
                    "completed_sha256": review.sha(
                        (root / "runs" / name / "COMPLETED.json").read_bytes()
                    ),
                }
                for name in candidates
            },
        },
    )
    monkey = pytest.MonkeyPatch()
    monkey.setattr(review, "CAMPAIGN_SHA", config_sha)
    monkey.setattr(review, "ROSTER_SHA", roster_sha)
    yield {
        "root": root,
        "config": config,
        "config_sha": config_sha,
        "roster_sha": roster_sha,
        "prompts": prompts,
        "keys": keys,
        "rubrics": rubrics,
        "roster": roster,
        "completion_sha": completion_sha,
    }
    monkey.undo()


@pytest.fixture(scope="module")
def packet(campaign):
    root = campaign["root"]
    output = root / "packet"
    review.build_packet(
        config_path=root / "config.json",
        config_sha256=campaign["config_sha"],
        runs=root / "runs",
        roster_path=root / "roster.json",
        roster_sha256=campaign["roster_sha"],
        mask_key_path=root / "mask.key",
        completion_manifest=root / "completion-manifest.json",
        completion_manifest_sha256=campaign["completion_sha"],
        output=output,
    )
    return output


def packet_values(packet):
    return review.rows((packet / "reviewer/mc.jsonl").read_bytes()) + review.rows(
        (packet / "reviewer/tutor.jsonl").read_bytes()
    )


def blank_assessment(item, met=False, error=False):
    evidence = ["Synthetic answer."] if met or error else []
    return {
        axis: {
            c["id"]: {
                "present" if axis == "critical_errors" else "met": error
                if axis == "critical_errors"
                else met,
                "evidence": evidence,
                "rationale": "Synthetic explicit judgment.",
            }
            for c in item["case"]["rubric"][axis]
        }
        for axis in ("science", "tutoring", "critical_errors")
    } | {"additional_errors": []}


def primary_rows(packet):
    result = []
    for item in packet_values(packet):
        row = {
            "review_id": item["review_id"],
            "reviewer": "synthetic-reviewer-A",
            "packet_row_sha256": review.sha(review.canonical(item)),
            "response_sha256": item["response_sha256"],
        }
        if item["kind"] == "mc":
            row |= {
                "chosen_index": item["key"]["answer_index"],
                "ambiguity": False,
                "explanatory_falsehood": False,
                "format_adherent": True,
                "delivered_final_answer": True,
                "rationale": "Synthetic choice assessment.",
                "evidence": ["Synthetic answer."],
            }
        else:
            row["assessment"] = blank_assessment(item)
        result.append(row)
    return result


def compile_fixture(packet, tmp_path, *, edit_a=None, edit_b=None, resolutions=None):
    a = primary_rows(packet)
    if edit_a:
        edit_a(a)
    b = copy.deepcopy(a)
    for row in b:
        row["reviewer"] = "synthetic-reviewer-B"
    if edit_b:
        edit_b(b)
    paths = {}
    for name, values in (("primary", a), ("secondary", b), ("adjudication", resolutions or [])):
        paths[name] = tmp_path / (name + ".jsonl")
        write(paths[name], values, jsonl=True)
    return review.compile_review(
        packet=packet,
        packet_sha256=review.sha((packet / "SEALED.json").read_bytes()),
        primary=paths["primary"],
        primary_sha256=review.sha(paths["primary"].read_bytes()),
        secondary=paths["secondary"],
        secondary_sha256=review.sha(paths["secondary"].read_bytes()),
        adjudication=paths["adjudication"],
        adjudication_sha256=review.sha(paths["adjudication"].read_bytes()),
        output=tmp_path / "compiled",
    )


def test_all12_complete_packet_masks_only_identity_not_answers(packet, campaign):
    items = packet_values(packet)
    assert len(items) == len({r["review_id"] for r in items}) == 864
    assert sum(r["kind"] == "mc" for r in items) == 768
    assert sum(r["kind"] == "tutor" for r in items) == 96
    forbidden = {"candidate_id", "profile", "model", "checkpoint", "step", "loss", "raw_row_sha256"}
    for item in items:
        assert not (set(item) & forbidden)
        assert item["response"].endswith("Synthetic answer.<eos>")
        assert item["review_id"].startswith("d72-")
    assert (packet / "private-mapping.jsonl").exists()
    assert not (packet / "reviewer/private-mapping.jsonl").exists()
    assert all(r["response_sha256"] == review.sha(r["response"].encode()) for r in items)


def test_compile_exact_denominators_ties_and_preserved_ledgers(packet, tmp_path):
    compile_fixture(packet, tmp_path)
    scores = review.parse((tmp_path / "compiled/scores.json").read_bytes())
    assert len(scores["candidates"]) == 12 and scores["advance"] == ["P1-half", "P2-half"]
    assert all(
        (r["M"], r["S"], r["T"], r["index_percent"]) == (64, 0, 0, 50) for r in scores["candidates"]
    )
    assert scores["secondary_rows"] == 864 and scores["adjudicated_rows"] == 0
    for name in ("primary", "secondary", "adjudication"):
        assert (tmp_path / f"{name}.jsonl").read_bytes() == (
            tmp_path / f"compiled/{name}.jsonl"
        ).read_bytes()


@pytest.mark.parametrize(
    "change,error",
    [
        (lambda r: r.pop(), "review coverage"),
        (lambda r: r.__setitem__(1, copy.deepcopy(r[0])), "duplicate row id"),
        (lambda r: r[0].__setitem__("response_sha256", "0" * 64), "identity/hash mismatch"),
        (lambda r: r[0].__setitem__("packet_row_sha256", "0" * 64), "identity/hash mismatch"),
        (
            lambda r: r[0].__setitem__("evidence", ["not present in response"]),
            "exact response span",
        ),
    ],
)
def test_primary_coverage_hashes_and_evidence(packet, tmp_path, change, error):
    with pytest.raises(ValueError, match=error):
        compile_fixture(packet, tmp_path, edit_a=change)


def test_all_tutors_require_secondary(packet, tmp_path):
    tutor_ids = {r["review_id"] for r in packet_values(packet) if r["kind"] == "tutor"}
    with pytest.raises(ValueError, match="mandatory independent secondary"):
        compile_fixture(
            packet,
            tmp_path,
            edit_b=lambda b: b.__setitem__(
                slice(None), [r for r in b if r["review_id"] not in tutor_ids]
            ),
        )


def test_primary_correct_fixed_audit_still_requires_secondary(packet, tmp_path):
    mapping = {
        r["review_id"]: r for r in review.rows((packet / "private-mapping.jsonl").read_bytes())
    }
    keys = review.frozen_inputs()[1]
    fixed = sorted(keys, key=lambda k: review.sha(("3407:science-mc-audit:" + k).encode()))[:8]
    remove = next(k for k, r in mapping.items() if r["item_id"] == fixed[0])
    with pytest.raises(ValueError, match="mandatory independent secondary"):
        compile_fixture(
            packet,
            tmp_path,
            edit_b=lambda b: b.__setitem__(slice(None), [r for r in b if r["review_id"] != remove]),
        )


def test_incorrect_outside_fixed_audit_requires_secondary(packet, tmp_path):
    mapping = {
        r["review_id"]: r for r in review.rows((packet / "private-mapping.jsonl").read_bytes())
    }
    keys = review.frozen_inputs()[1]
    fixed = sorted(keys, key=lambda k: review.sha(("3407:science-mc-audit:" + k).encode()))[:8]
    bad = next(k for k, r in mapping.items() if r["item_id"] in keys and r["item_id"] not in fixed)

    def edit(a):
        next(r for r in a if r["review_id"] == bad)["chosen_index"] = None

    with pytest.raises(ValueError, match="mandatory independent secondary"):
        compile_fixture(
            packet,
            tmp_path,
            edit_a=edit,
            edit_b=lambda b: b.__setitem__(slice(None), [r for r in b if r["review_id"] != bad]),
        )


def test_same_reviewer_is_not_independent(packet, tmp_path):
    with pytest.raises(ValueError, match="reviewer must be independent"):
        compile_fixture(
            packet, tmp_path, edit_b=lambda b: b[0].__setitem__("reviewer", "synthetic-reviewer-A")
        )


def test_equal_score_different_flag_requires_explicit_resolution(packet, tmp_path):
    with pytest.raises(ValueError, match="adjudication coverage mismatch"):
        compile_fixture(
            packet, tmp_path, edit_b=lambda b: b[0].__setitem__("format_adherent", False)
        )


def test_explicit_resolution_preserves_all_originals(packet, tmp_path):
    a = primary_rows(packet)[0]
    b = copy.deepcopy(a) | {"reviewer": "synthetic-reviewer-B", "format_adherent": False}
    decision = copy.deepcopy(b) | {"reviewer": "synthetic-adjudicator"}
    resolution = {
        "review_id": a["review_id"],
        "primary_row_sha256": review.sha(review.canonical(a)),
        "secondary_row_sha256": review.sha(review.canonical(b)),
        "decision": decision,
        "rationale": "Synthetic adjudication of categorical difference.",
        "evidence": ["Synthetic answer."],
    }
    compile_fixture(
        packet,
        tmp_path,
        edit_b=lambda values: values[0].__setitem__("format_adherent", False),
        resolutions=[resolution],
    )
    scores = review.parse((tmp_path / "compiled/scores.json").read_bytes())
    assert scores["adjudicated_rows"] == 1


def test_critical_cap_does_not_reduce_teaching_or_denominator(packet):
    item = next(r for r in packet_values(packet) if r["kind"] == "tutor")
    base = next(r for r in primary_rows(packet) if r["review_id"] == item["review_id"])
    base["assessment"] = blank_assessment(item, met=True, error=True)
    result = review.judge(base, item)["score"]
    assert result["science"] == 1 and result["science_before_critical_cap"] == 4
    assert result["tutoring"] == 4 and result["critical_errors_present"] == 2


def test_empty_tutor_zero_retained_without_fabricating_evidence(packet):
    item = copy.deepcopy(next(r for r in packet_values(packet) if r["kind"] == "tutor"))
    base = copy.deepcopy(
        next(r for r in primary_rows(packet) if r["review_id"] == item["review_id"])
    )
    item["response"] = ""
    item["response_sha256"] = review.sha(b"")
    base["response_sha256"] = review.sha(b"")
    base["packet_row_sha256"] = review.sha(review.canonical(item))
    assert review.judge(base, item)["score"] == {
        "science": 0,
        "tutoring": 0,
        "critical_errors_present": 0,
        "empty_response_zero": True,
    }
    base["assessment"]["science"]["S1"]["met"] = True
    with pytest.raises(ValueError):
        review.judge(base, item)


def test_unclosed_reasoning_can_be_correct_but_not_delivered(packet):
    item = copy.deepcopy(packet_values(packet)[0])
    base = copy.deepcopy(primary_rows(packet)[0])
    item["reasoning_prefix_already_open"] = True
    item["finish_reason"] = "token_cap"
    base["packet_row_sha256"] = review.sha(review.canonical(item))
    base["delivered_final_answer"] = False
    assert review.judge(base, item)["correct"] is True
    base["delivered_final_answer"] = True
    with pytest.raises(ValueError, match="unclosed reasoning"):
        review.judge(base, item)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda seal: seal.__setitem__("completed_count", 71), "candidate incomplete"),
        (lambda seal: seal["config"].__setitem__("sha256", "0" * 64), "terminal config/source"),
        (lambda seal: seal["responses"].__setitem__("sha256", "0" * 64), "responses receipt"),
    ],
)
def test_candidate_terminal_bindings(campaign, tmp_path, mutation, error):
    # Copy only one synthetic candidate (not model weights or real outputs).
    import shutil

    path = tmp_path / "candidate"
    shutil.copytree(campaign["root"] / "runs/C1", path)
    seal = review.parse((path / "COMPLETED.json").read_bytes())
    mutation(seal)
    write(path / "COMPLETED.json", seal)
    with pytest.raises(ValueError, match=error):
        review.validate_candidate(
            path, "C1", campaign["config"], campaign["config_sha"], campaign["prompts"]
        )


def test_partial_raw_batch_even_resealed_is_rejected(campaign, tmp_path):
    import shutil

    path = tmp_path / "candidate"
    shutil.copytree(campaign["root"] / "runs/C1", path)
    batch = review.parse((path / "batches/batch-0000.json").read_bytes())
    batch["returned_sequence_ids"].pop()
    write(path / "batches/batch-0000.json", batch)
    reseal_run(path)
    with pytest.raises(ValueError, match="raw batch count"):
        review.validate_candidate(
            path, "C1", campaign["config"], campaign["config_sha"], campaign["prompts"]
        )


def test_failed_run_not_admitted_even_with_complete(campaign, tmp_path):
    import shutil

    path = tmp_path / "candidate"
    shutil.copytree(campaign["root"] / "runs/C1", path)
    write(path / "FAILED.json", {"status": "failed"})
    with pytest.raises(ValueError, match="failed candidate"):
        review.validate_candidate(
            path, "C1", campaign["config"], campaign["config_sha"], campaign["prompts"]
        )


def test_rehashed_wrong_prompt_response_join_rejected(campaign, tmp_path):
    import shutil

    path = tmp_path / "candidate"
    shutil.copytree(campaign["root"] / "runs/C1", path)
    data = review.rows((path / "responses.jsonl").read_bytes())
    data[0]["messages"][0]["content"] = "Synthetic changed prompt"
    write(path / "responses.jsonl", data, jsonl=True)
    reseal_run(path)
    with pytest.raises(ValueError, match="prompt/candidate join"):
        review.validate_candidate(
            path, "C1", campaign["config"], campaign["config_sha"], campaign["prompts"]
        )


def test_output_reuse_refused(packet, tmp_path):
    compile_fixture(packet, tmp_path)
    with pytest.raises(ValueError, match="existing/symlinked output"):
        compile_fixture(packet, tmp_path)


def packet_call(campaign, output, **overrides):
    root = campaign["root"]
    arguments = {
        "config_path": root / "config.json",
        "config_sha256": campaign["config_sha"],
        "runs": root / "runs",
        "roster_path": root / "roster.json",
        "roster_sha256": campaign["roster_sha"],
        "mask_key_path": root / "mask.key",
        "completion_manifest": root / "completion-manifest.json",
        "completion_manifest_sha256": campaign["completion_sha"],
        "output": output,
    }
    return review.build_packet(**(arguments | overrides))


def test_external_completion_binding_rejects_resealed_fake_text(campaign, tmp_path):
    import shutil

    copied = tmp_path / "runs"
    shutil.copytree(campaign["root"] / "runs", copied)
    data = review.rows((copied / "C1/responses.jsonl").read_bytes())
    data[0]["continuation"] = data[0]["raw_continuation"] = "Invented after execution"
    write(copied / "C1/responses.jsonl", data, jsonl=True)
    reseal_run(copied / "C1")
    with pytest.raises(ValueError, match="file SHA256 mismatch"):
        packet_call(campaign, tmp_path / "packet", runs=copied)
    assert not (tmp_path / "packet").exists()


def test_all_twelve_required_before_any_packet_write(campaign, tmp_path, monkeypatch):
    original = review.validate_candidate
    seen = []
    last_candidate = next(
        reversed(review.parse((campaign["root"] / "config.json").read_bytes())["candidates"])
    )

    def validate(root, candidate, *args):
        seen.append(candidate)
        if candidate == last_candidate:
            raise ValueError("synthetic twelfth run not complete")
        return original(root, candidate, *args)

    monkeypatch.setattr(review, "validate_candidate", validate)
    with pytest.raises(ValueError, match="twelfth run not complete"):
        packet_call(campaign, tmp_path / "packet")
    assert len(seen) == 12 and not (tmp_path / "packet").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("exact_tensor_values_loaded", False),
        ("source_safetensors_sha256", "0" * 64),
        ("source_tensor_count", 0),
        ("source_tensor_count", True),
    ],
)
def test_loaded_adapter_proof_required(campaign, tmp_path, field, value):
    import shutil

    path = tmp_path / "candidate"
    shutil.copytree(campaign["root"] / "runs/P1-half", path)
    initialized = review.parse((path / "initialized.json").read_bytes())
    initialized["model"][field] = value
    write(path / "initialized.json", initialized)
    reseal_run(path)
    with pytest.raises(ValueError, match="loaded adapter tensor proof"):
        review.validate_candidate(
            path, "P1-half", campaign["config"], campaign["config_sha"], campaign["prompts"]
        )


@pytest.mark.parametrize("kind", ["parent", "checkpoint", "profile", "no_adapter"])
def test_wrong_pilot_lineage_description_rejected(campaign, kind):
    config = copy.deepcopy(campaign["config"])
    pilot = config["candidates"]["P1-half"]
    if kind == "parent":
        pilot["base"] = config["candidates"]["C2"]["base"]
    elif kind == "checkpoint":
        pilot["adapter"] = config["candidates"]["P1-end"]["adapter"]
    elif kind == "profile":
        pilot["profile"] = "deepseek_native"
    else:
        pilot.pop("adapter")
    with pytest.raises(ValueError):
        review.validate_lineages(config, campaign["roster"])


def test_whole_parent_relabel_cannot_replace_admitted_config(campaign, tmp_path):
    config = copy.deepcopy(campaign["config"])
    for first, second in (("C1", "C2"), ("P1-half", "P2-half"), ("P1-end", "P2-end")):
        config["candidates"][first], config["candidates"][second] = (
            config["candidates"][second],
            config["candidates"][first],
        )
    modified = tmp_path / "changed-config.json"
    digest = write(modified, config)
    with pytest.raises(ValueError, match="not the exact admitted treatment"):
        packet_call(campaign, tmp_path / "packet", config_path=modified, config_sha256=digest)


def test_whitespace_is_not_valid_mc_evidence(packet):
    item = packet_values(packet)[0]
    assessment = primary_rows(packet)[0]
    assessment["evidence"] = [" "]
    with pytest.raises(ValueError, match="exact response span"):
        review.judge(assessment, item)


def test_affirmative_format_requires_response_evidence(packet):
    item = packet_values(packet)[0]
    assessment = primary_rows(packet)[0] | {
        "chosen_index": None,
        "delivered_final_answer": False,
        "evidence": [],
    }
    with pytest.raises(ValueError, match="affirmed MC judgment needs evidence"):
        review.judge(assessment, item)


def modify_packet(packet, destination, change):
    import shutil

    shutil.copytree(packet, destination)
    change(destination)
    seal = review.parse((destination / "SEALED.json").read_bytes())
    seal["files"] = review.inventory(destination, omit=("SEALED.json",))
    write(destination / "SEALED.json", seal)
    return destination


def test_packet_mapping_seal_join_refused(packet, tmp_path):
    def mutate(path):
        mapping = review.rows((path / "private-mapping.jsonl").read_bytes())
        mapping[0]["candidate_seal_sha256"] = "0" * 64
        write(path / "private-mapping.jsonl", mapping, jsonl=True)

    bad = modify_packet(packet, tmp_path / "bad", mutate)
    with pytest.raises(ValueError, match="mapping candidate seal mismatch"):
        compile_fixture(bad, tmp_path / "ledgers")


def test_key_change_cannot_be_hidden_by_resealing_packet(packet, tmp_path):
    def mutate(path):
        data = review.rows((path / "reviewer/mc.jsonl").read_bytes())
        data[0]["key"]["answer_text"] = "Unreviewed replacement"
        write(path / "reviewer/mc.jsonl", data, jsonl=True)
        mapping = review.rows((path / "private-mapping.jsonl").read_bytes())
        next(r for r in mapping if r["review_id"] == data[0]["review_id"])["packet_row_sha256"] = (
            review.sha(review.canonical(data[0]))
        )
        write(path / "private-mapping.jsonl", mapping, jsonl=True)

    bad = modify_packet(packet, tmp_path / "bad", mutate)
    with pytest.raises(ValueError, match="MC key drift"):
        compile_fixture(bad, tmp_path / "ledgers")


def test_identity_metadata_in_reviewer_packet_refused(packet, tmp_path):
    def mutate(path):
        data = review.rows((path / "reviewer/mc.jsonl").read_bytes())
        data[0]["candidate_id"] = "C1"
        write(path / "reviewer/mc.jsonl", data, jsonl=True)

    bad = modify_packet(packet, tmp_path / "bad", mutate)
    with pytest.raises(ValueError, match="packet schema/leakage"):
        compile_fixture(bad, tmp_path / "ledgers")


def test_output_cannot_mutate_sealed_packet(packet, tmp_path):
    a = tmp_path / "a.jsonl"
    digest = write(a, primary_rows(packet), jsonl=True)
    with pytest.raises(ValueError, match="must not mutate protected inputs"):
        review.compile_review(
            packet=packet,
            packet_sha256=review.sha((packet / "SEALED.json").read_bytes()),
            primary=a,
            primary_sha256=digest,
            secondary=a,
            secondary_sha256=digest,
            adjudication=a,
            adjudication_sha256=digest,
            output=packet / "new-child",
        )
