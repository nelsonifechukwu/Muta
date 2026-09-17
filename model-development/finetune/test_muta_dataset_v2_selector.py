from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

core = importlib.import_module("model-development.finetune.muta_dataset_v2.core")
generators = importlib.import_module("model-development.finetune.muta_dataset_v2.generators")
selector = importlib.import_module("model-development.finetune.muta_dataset_v2.select_sft")
review_pack = importlib.import_module(
    "model-development.finetune.muta_dataset_v2.audit_review_pack"
)


def test_explicit_anchor_source_allocations_are_supported() -> None:
    recipe = {
        "recommended_sft_target_rows": 300_000,
        "recommended_sft_allocations": {
            "muta_verified_stem_v2": 280_000,
            "deepmind_mathematics": 20_000,
        },
    }
    assert selector._expanded_source_quotas(recipe) == {
        "muta_verified_stem_v2": 280_000,
        "deepmind_mathematics": 20_000,
    }


def test_explicit_and_legacy_anchor_allocations_cannot_be_mixed() -> None:
    recipe = {
        "recommended_sft_target_rows": 10,
        "recommended_sft_allocations": {
            "muta_verified_stem_v2": 4,
            "licensed_anchors": 4,
            "gsm8k": 2,
        },
    }
    with pytest.raises(ValueError, match="cannot mix"):
        selector._expanded_source_quotas(recipe)


def test_quality_recipe_enforces_documented_native_replacement_cells() -> None:
    recipe = json.loads((selector.PACKAGE_DIR / "recipe.json").read_text(encoding="utf-8"))
    declared = {
        tuple(label.split(" :: ")): quota
        for label, quota in recipe["recommended_sft_local_cell_quotas"].items()
    }
    availability = {
        ("muta_verified_stem_v2", subject, pedagogy): quota + 1_000
        for (subject, pedagogy), quota in declared.items()
    }
    availability[("deepmind_mathematics", "mathematics", "concise_answer")] = 20_000

    cells, sources, subjects, pedagogies = selector._solve_cell_quotas(
        recipe=recipe,
        availability=availability,
    )

    observed_local = {
        (subject, pedagogy): quota
        for (source, subject, pedagogy), quota in cells.items()
        if source == "muta_verified_stem_v2"
    }
    assert observed_local == declared
    assert sources == {
        "muta_verified_stem_v2": 280_000,
        "deepmind_mathematics": 20_000,
    }
    assert subjects == {
        "mathematics": 150_000,
        "physics": 54_000,
        "chemistry": 42_000,
        "biology": 42_000,
        "integrated_science": 12_000,
    }
    assert pedagogies == {
        "worked_solution": 120_000,
        "exam_marking_scheme": 60_000,
        "misconception_correction": 60_000,
        "socratic_hint": 30_000,
        "concise_answer": 30_000,
    }
    assert len(observed_local) == 25
    assert min(observed_local.values()) > 0
    assert cells[("muta_verified_stem_v2", "mathematics", "worked_solution")] == 61_199
    assert cells[("muta_verified_stem_v2", "mathematics", "concise_answer")] == 2_454
    assert cells[("muta_verified_stem_v2", "integrated_science", "worked_solution")] == 3_070
    assert cells[("muta_verified_stem_v2", "integrated_science", "concise_answer")] == 4_892


def test_selection_recipe_override_is_limited_and_receipted(tmp_path) -> None:
    archived = _mini_recipe()
    selected = json.loads(json.dumps(archived))
    selected["recommended_sft_allocations"] = {
        "muta_verified_stem_v2": 19,
        "deepmind_mathematics": 1,
    }
    selected["recommended_sft_allocation_decision"] = {
        "version": "fixture-quality-override-v1",
        "reason": "Independent review rejected every audit-gated source allocation.",
    }
    selected["training_note"] = "Quality-first fixture allocation."
    archived_path = tmp_path / "archived.json"
    selected_path = tmp_path / "selected.json"
    archived_path.write_text(json.dumps(archived), encoding="utf-8")
    selected_path.write_text(json.dumps(selected), encoding="utf-8")

    loaded, loaded_path, binding = selector._load_selection_recipe(
        archived_recipe_path=archived_path,
        requested_recipe_path=selected_path,
    )

    assert loaded == selected
    assert loaded_path == selected_path.resolve()
    assert binding["mode"] == "post_warehouse_quality_allocation_override"
    assert binding["changed_fields"] == [
        "recommended_sft_allocation_decision",
        "recommended_sft_allocations",
        "training_note",
    ]
    assert binding["warehouse_construction_reinterpreted"] is False
    assert binding["subject_targets_changed"] is False
    assert binding["pedagogy_targets_changed"] is False


def test_selection_recipe_override_rejects_target_or_seed_drift(tmp_path) -> None:
    archived = _mini_recipe()
    archived_path = tmp_path / "archived.json"
    archived_path.write_text(json.dumps(archived), encoding="utf-8")
    for field, value in (("seed", 99), ("recommended_sft_target_rows", 19)):
        selected = json.loads(json.dumps(archived))
        selected[field] = value
        selected["recommended_sft_allocation_decision"] = {
            "version": "invalid-fixture-override-v1",
            "reason": "This must not authorize target drift.",
        }
        selected_path = tmp_path / f"selected-{field}.json"
        selected_path.write_text(json.dumps(selected), encoding="utf-8")

        with pytest.raises(ValueError, match="changes warehouse or target invariants"):
            selector._load_selection_recipe(
                archived_recipe_path=archived_path,
                requested_recipe_path=selected_path,
            )


def _tokenize_fixture(record: dict) -> dict:
    record["tokenization"] = {
        "tokenizer_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "tokenizer_revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
        "chat_template_sha256": (
            "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"
        ),
        "sequence_tokens": 100,
        "max_sequence_tokens": 1024,
        "within_limit": True,
    }
    return record


def _external_record(
    source_id: str,
    ordinal: int,
    *,
    split: str = "train",
    source_task: str | None = None,
) -> dict:
    registry = core.load_source_registry()
    source = registry[source_id]
    prompt = f"Selector fixture {source_id} problem {ordinal}: what is {ordinal + 2} + 3?"
    answer = str(ordinal + 5)
    if source_id == "deepmind_mathematics":
        module = "arithmetic__add_or_sub" if ordinal == 1 else f"fixture_module_{ordinal}"
        source_split = "train-easy"
        source_row_id = f"train-easy:fixture:{ordinal}"
        cluster = f"module:{module}"
        subject = "mathematics"
        pedagogy = "concise_answer"
        status = "programmatic"
        method = f"deepmind_generator:{module}"
        eligible = True
        synthetic = True
    elif source_id == "template_gsm":
        source_split = "train"
        source_row_id = f"train:template:fixture:problem:{ordinal}"
        cluster = "template:fixture"
        subject = "mathematics"
        pedagogy = "worked_solution"
        status = "silver_pending_audit"
        method = "publisher generated-code result"
        eligible = False
        synthetic = True
    elif source_id == "qasc":
        source_split = "train"
        source_row_id = f"train:qasc-fixture-{ordinal}"
        cluster = f"row:{source_row_id}"
        subject = "integrated_science"
        pedagogy = "concise_answer"
        status = "source_verified"
        method = "published answer key"
        eligible = False
        synthetic = False
    elif source_id == "gsm8k":
        source_split = "train"
        source_row_id = f"train:prompt-sha256:{ordinal:064x}"
        cluster = f"row:{source_row_id}"
        subject = "mathematics"
        pedagogy = "worked_solution"
        status = "programmatic"
        method = "restricted-AST verification of every GSM8K calculator annotation"
        eligible = False
        synthetic = False
    else:  # pragma: no cover - fixture misuse
        raise AssertionError(source_id)
    verification = {
        "status": status,
        "method": method,
        "expected": answer,
        "observed": answer,
        "verifier_version": "selector-fixture-v1",
        "training_eligible": eligible,
    }
    if source_id == "template_gsm":
        verification["template_id"] = "fixture"
    record = core.make_record(
        prompt=prompt,
        completion=f"The checkable calculation gives {answer}. Final answer: {answer}.",
        answer=answer,
        subject=subject,
        topic="word_problems" if subject == "mathematics" else "multiple_choice_science",
        difficulty="standard",
        response_format="free_response",
        pedagogy=pedagogy,
        mode="chat",
        split=split,
        source_id=source_id,
        source_revision=source["revision"],
        source_split=source_split,
        source_row_id=source_row_id,
        semantic_cluster_id=cluster,
        license_name=source["license"],
        synthetic=synthetic,
        transform="selector test fixture",
        country="not-applicable",
        curriculum_authority="none",
        curriculum_version="none",
        exam_era="not-applicable",
        alignment="selector test fixture",
        verification=verification,
        holdouts=core.HoldoutIndex([]),
        source_task=source_task or prompt,
    )
    assert record is not None
    _tokenize_fixture(record)
    assert not core.validate_record(record)
    return record


def _local_records() -> list[dict]:
    required = {
        ("mathematics", "worked_solution"): 4,
        ("mathematics", "exam_marking_scheme"): 3,
        ("mathematics", "misconception_correction"): 3,
        ("mathematics", "socratic_hint"): 1,
        ("physics", "worked_solution"): 1,
        ("physics", "exam_marking_scheme"): 1,
        ("chemistry", "worked_solution"): 1,
        ("chemistry", "misconception_correction"): 1,
        ("biology", "socratic_hint"): 1,
    }
    selected: list[dict] = []
    counts: Counter[tuple[str, str]] = Counter()
    task_hashes: set[str] = set()
    for index in range(100_000):
        record = generators.generate_local_example(
            index,
            seed=3407,
            holdouts=core.HoldoutIndex([]),
            split="train",
            source_revision="sha256:" + "a" * 64,
        )
        assert record is not None
        cell = (record["subject"], record["pedagogy"])
        task_hash = record["contamination"]["source_task_sha256"]
        if cell not in required or counts[cell] >= required[cell] or task_hash in task_hashes:
            continue
        _tokenize_fixture(record)
        selected.append(record)
        counts[cell] += 1
        task_hashes.add(task_hash)
        if counts == Counter(required):
            break
    assert counts == Counter(required)
    return selected


def _mini_recipe() -> dict:
    return {
        "schema_version": 1,
        "name": "selector-fixture",
        "seed": 3407,
        "warehouse_target_rows": 24,
        "warehouse_allocations": {},
        "recommended_sft_target_rows": 20,
        "recommended_sft_allocations": {
            "muta_verified_stem_v2": 16,
            "deepmind_mathematics": 1,
            "template_gsm": 1,
            "licensed_anchors": 2,
        },
        "recommended_sft_subject_targets": {
            "mathematics": 0.70,
            "physics": 0.10,
            "chemistry": 0.10,
            "biology": 0.05,
            "integrated_science": 0.05,
        },
        "recommended_sft_pedagogy_targets": {
            "worked_solution": 0.40,
            "exam_marking_scheme": 0.20,
            "misconception_correction": 0.20,
            "socratic_hint": 0.10,
            "concise_answer": 0.10,
        },
        "limits": {
            "max_rows_per_external_template_in_sft": 1,
            "max_rows_per_source_task_in_sft": 1,
            "shard_rows": 7,
        },
    }


def _receipt(path: Path, relative: str, *, archive_path: bool = False) -> dict:
    result = {
        "path": relative,
        "bytes": path.stat().st_size,
        "sha256": core.sha256_file(path),
    }
    if archive_path:
        result["archive_path"] = result.pop("path")
        result["path"] = path.name
    return result


def _counter_documents(records: list[dict]) -> dict:
    formula = Counter()
    for record in records:
        verification = record["verification"]
        if verification.get("formula_id"):
            key = f"formula:{verification['formula_id']}"
        elif verification.get("template_id"):
            key = f"template:{verification['template_id']}"
        else:
            method = verification["method"]
            key = (
                f"formula:{method}"
                if record["provenance"]["source_id"] == "muta_verified_stem_v2"
                else f"method:{method}"
            )
        formula[key] += 1
    counter = lambda values: dict(sorted(Counter(values).items()))
    clusters: dict[str, set[str]] = {}
    for record in records:
        source = record["provenance"]["source_id"]
        clusters.setdefault(source, set()).add(record["provenance"]["semantic_cluster_id"])
    return {
        "source": counter(record["provenance"]["source_id"] for record in records),
        "source_split": counter(
            f"{record['provenance']['source_id']} :: {record['provenance']['source_split']}"
            for record in records
        ),
        "semantic_cluster_count_by_source": {
            source: len(values) for source, values in sorted(clusters.items())
        },
        "semantic_cluster_split_overlap_count": 0,
        "cross_source_task_collision_pairs": {},
        "subject": counter(record["subject"] for record in records),
        "topic": counter(record["topic"] for record in records),
        "difficulty": counter(record["difficulty"] for record in records),
        "pedagogy": counter(record["pedagogy"] for record in records),
        "formula_template_method": dict(sorted(formula.items())),
        "curriculum_alignment": counter(record["curriculum"]["alignment"] for record in records),
        "source_subject_pedagogy": counter(
            f"{record['provenance']['source_id']} :: {record['subject']} :: {record['pedagogy']}"
            for record in records
        ),
        "verification": counter(record["verification"]["status"] for record in records),
        "eligibility": counter(
            "eligible" if record["verification"]["training_eligible"] else "audit_required"
            for record in records
        ),
        "audit_eligibility": counter(
            "training_eligible" if record["verification"]["training_eligible"] else "audit_required"
            for record in records
        ),
        "split": counter(record["split"] for record in records),
    }


def _write_archive(directory: Path, name: str, files: list[dict]) -> dict:
    receipts_path = directory / "receipts.json"
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    receipts_path.write_text(
        json.dumps({"schema_version": 1, "files": files}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "directory": name,
        "files": files,
        "receipts": _receipt(receipts_path, receipts_path.relative_to(directory.parent).as_posix()),
    }


def _write_warehouse(
    tmp_path: Path,
    *,
    cross_split_task: bool = False,
    qasc_shared_task: bool = False,
) -> tuple[Path, list[dict]]:
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir(parents=True)
    records = _local_records()
    template_rows = [_external_record("template_gsm", index) for index in (1, 2)]
    qasc = _external_record("qasc", 1)
    rejected_qasc_fixture = _external_record(
        "qasc", 2, source_task=qasc["prompt"] if qasc_shared_task else None
    )
    gsm = _external_record("gsm8k", 1)
    deep_train = _external_record("deepmind_mathematics", 1)
    deep_train_variant_a = _external_record(
        "deepmind_mathematics", 3, source_task=deep_train["prompt"]
    )
    deep_train_variant_b = _external_record(
        "deepmind_mathematics", 4, source_task=deep_train["prompt"]
    )
    deep_holdout = _external_record(
        "deepmind_mathematics",
        2,
        split="template_holdout",
        source_task=(deep_train["prompt"] if cross_split_task else None),
    )
    records.extend(
        [
            *template_rows,
            qasc,
            rejected_qasc_fixture,
            gsm,
            deep_train,
            deep_train_variant_a,
            deep_train_variant_b,
            deep_holdout,
        ]
    )

    shard = warehouse / "part-00000.jsonl"
    shard.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    shard_receipt = {
        "path": shard.name,
        "rows": len(records),
        "bytes": shard.stat().st_size,
        "sha256": core.sha256_file(shard),
    }
    fingerprint = hashlib.sha256(shard_receipt["sha256"].encode("ascii")).hexdigest()

    provenance = warehouse / "provenance-code"
    provenance.mkdir()
    recipe_path = provenance / "recipe.json"
    recipe_path.write_text(json.dumps(_mini_recipe()), encoding="utf-8")
    schema_path = provenance / "schema.json"
    shutil.copyfile(selector.PACKAGE_DIR / "schema.json", schema_path)
    registry_path = provenance / "source_registry.json"
    shutil.copyfile(selector.PACKAGE_DIR / "source_registry.json", registry_path)
    requirements = provenance / "requirements-build.txt"
    requirements.write_text("fixture\n", encoding="utf-8")
    requirements_lock = provenance / "requirements-build.lock.txt"
    requirements_lock.write_text("fixture-lock\n", encoding="utf-8")
    license_path = provenance / "MUTA-LICENSE"
    license_path.write_text("MIT fixture\n", encoding="utf-8")
    direct = {
        "recipe": _receipt(recipe_path, "provenance-code/recipe.json", archive_path=True),
        "schema": _receipt(schema_path, "provenance-code/schema.json", archive_path=True),
        "source_registry": _receipt(
            registry_path, "provenance-code/source_registry.json", archive_path=True
        ),
        "requirements": _receipt(
            requirements, "provenance-code/requirements-build.txt", archive_path=True
        ),
        "requirements_lock": _receipt(
            requirements_lock,
            "provenance-code/requirements-build.lock.txt",
            archive_path=True,
        ),
        "muta_license": _receipt(license_path, "provenance-code/MUTA-LICENSE", archive_path=True),
    }
    code_receipts = []
    for name in ("core.py", "generators.py", "tokenization.py"):
        archived_code = provenance / name
        shutil.copyfile(selector.PACKAGE_DIR / name, archived_code)
        code_receipts.append(_receipt(archived_code, f"provenance-code/{name}", archive_path=True))
    provenance_files = [
        {
            "path": receipt["archive_path"],
            "bytes": receipt["bytes"],
            "sha256": receipt["sha256"],
        }
        for receipt in direct.values()
    ]
    provenance_files.extend(
        {
            "path": receipt["archive_path"],
            "bytes": receipt["bytes"],
            "sha256": receipt["sha256"],
        }
        for receipt in code_receipts
    )
    provenance_archive = _write_archive(provenance, "provenance-code", provenance_files)
    holdout_archive = _write_archive(warehouse / "provenance-holdouts", "provenance-holdouts", [])
    evidence_directory = warehouse / "provenance-source-evidence"
    qasc_evidence = evidence_directory / "qasc" / "README.md"
    qasc_evidence.parent.mkdir(parents=True)
    qasc_evidence.write_text(
        "QASC fixture dataset card with CC-BY-4.0 licence metadata.\n", encoding="utf-8"
    )
    qasc_evidence_receipt = {
        "source_id": "qasc",
        "revision": core.load_source_registry()["qasc"]["revision"],
        "locator": "fixture:qasc:README.md",
        "path": "provenance-source-evidence/qasc/README.md",
        "bytes": qasc_evidence.stat().st_size,
        "sha256": core.sha256_file(qasc_evidence),
    }
    evidence_archive = _write_archive(
        evidence_directory, "provenance-source-evidence", [qasc_evidence_receipt]
    )
    (evidence_directory / "unreceipted.txt").write_text("must not be copied\n", encoding="utf-8")
    counts = _counter_documents(records)
    source_counts = Counter(record["provenance"]["source_id"] for record in records)
    manifest = {
        "schema_version": 1,
        "dataset_name": "selector-fixture-warehouse",
        "profile": "warehouse",
        "seed": 3407,
        "row_count": len(records),
        "dataset_fingerprint_sha256": fingerprint,
        "requested_counts": dict(source_counts),
        "sources": [
            {"id": source, "rows": count} for source, count in sorted(source_counts.items())
        ],
        "counts": counts,
        "tokenization": {
            "status": "exact",
            "minimum_sequence_tokens": 100,
            "maximum_sequence_tokens": 100,
            "mean_sequence_tokens": 100.0,
            "buckets": {"0001-0128": len(records)},
        },
        "inputs": {
            **direct,
            "code": code_receipts,
            "provenance_archive": provenance_archive,
            "holdout_source_archive": holdout_archive,
            "source_evidence_archive": evidence_archive,
        },
        "shards": [shard_receipt],
    }
    (warehouse / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return warehouse, records


def _approval(
    fingerprint: str,
    *,
    source_id: str,
    content_hash: str,
    rubric_hash: str,
    record_id: str | None = None,
    semantic_cluster_id: str | None = None,
    decision: str = "approved",
) -> dict:
    receipt = {
        "schema_version": 1,
        "warehouse_dataset_fingerprint_sha256": fingerprint,
        "target_type": "record" if record_id else "semantic_cluster",
        "source_id": source_id,
        "record_content_sha256": content_hash,
        "decision": decision,
        "reviewer": "selector-test-reviewer",
        "review_method": "manual worked-solution and provenance review",
        "reviewed_at": "2026-09-15T12:00:00Z",
        "rubric_version": "selector-test-rubric-v1",
        "rubric_sha256": rubric_hash,
    }
    if record_id:
        receipt["record_id"] = record_id
    else:
        receipt["semantic_cluster_id"] = semantic_cluster_id
    receipt["receipt_id"] = selector.approval_receipt_id(receipt)
    return receipt


def _write_approvals(path: Path, warehouse: Path, records: list[dict], rubric: Path) -> list[dict]:
    fingerprint = json.loads((warehouse / "manifest.json").read_text())[
        "dataset_fingerprint_sha256"
    ]
    templates = [
        record for record in records if record["provenance"]["source_id"] == "template_gsm"
    ]
    qasc = next(record for record in records if record["provenance"]["source_id"] == "qasc")
    gsm = next(record for record in records if record["provenance"]["source_id"] == "gsm8k")
    receipts = [
        *[
            _approval(
                fingerprint,
                source_id="template_gsm",
                record_id=record["id"],
                content_hash=selector.record_content_sha256(record),
                rubric_hash=core.sha256_file(rubric),
            )
            for record in templates
        ],
        _approval(
            fingerprint,
            source_id="qasc",
            record_id=qasc["id"],
            content_hash=selector.record_content_sha256(qasc),
            rubric_hash=core.sha256_file(rubric),
        ),
        _approval(
            fingerprint,
            source_id="gsm8k",
            record_id=gsm["id"],
            content_hash=selector.record_content_sha256(gsm),
            rubric_hash=core.sha256_file(rubric),
        ),
    ]
    path.write_text(
        "".join(json.dumps(receipt, separators=(",", ":")) + "\n" for receipt in receipts),
        encoding="utf-8",
    )
    return receipts


def _write_rubric(path: Path) -> Path:
    path.write_text(
        "Muta selector test rubric v1: verify correctness, level, pedagogy, and provenance.\n",
        encoding="utf-8",
    )
    return path


def _read_output_rows(output: Path) -> list[dict]:
    manifest = json.loads((output / "manifest.json").read_text())
    return [
        json.loads(line)
        for shard in manifest["shards"]
        for line in (output / shard["path"]).read_text().splitlines()
    ]


def _read_review_rows(output: Path) -> list[dict]:
    manifest = json.loads((output / "manifest.json").read_text())
    return [
        json.loads(line)
        for line in (output / manifest["review_rows"]["path"]).read_text().splitlines()
    ]


def test_audit_review_pack_is_deterministic_exact_capped_and_unapproved(tmp_path) -> None:
    warehouse, _ = _write_warehouse(tmp_path)
    first = tmp_path / "audit-review-a"
    second = tmp_path / "audit-review-b"

    manifest = review_pack.materialize_audit_review_pack(warehouse=warehouse, output=first)
    second_manifest = review_pack.materialize_audit_review_pack(warehouse=warehouse, output=second)

    rows = _read_review_rows(first)
    expected_sources = {"gsm8k": 1, "qasc": 1, "template_gsm": 1}
    assert len(rows) == manifest["row_count"] == 3
    assert manifest["selection"]["source_quotas"] == expected_sources
    assert manifest["counts"]["source"] == expected_sources
    assert Counter(row["source_id"] for row in rows) == Counter(expected_sources)
    assert {row["record"]["split"] for row in rows} == {"train"}
    assert {row["record"]["verification"]["training_eligible"] for row in rows} == {False}
    assert all("decision" not in row and "approved" not in row for row in rows)
    assert all(
        row["record_content_sha256"] == selector.record_content_sha256(row["record"])
        for row in rows
    )
    assert all(
        row["selection_rank_sha256"] == selector._rank(3407, row["record_id"]) for row in rows
    )
    task_counts = Counter(row["source_task_sha256"] for row in rows)
    template_counts = Counter(
        row["semantic_cluster_id"] for row in rows if row["source_id"] == "template_gsm"
    )
    assert max(task_counts.values()) == 1
    assert max(template_counts.values()) == 1
    caps = manifest["selection"]["caps"]
    assert caps["max_rows_per_source_task"] == 1
    assert caps["template_source"] == "template_gsm"
    assert caps["max_rows_per_external_template"] == 1
    assert caps["observed_approved_plus_batch_max_rows_per_source_task"] == 1
    assert caps["observed_approved_plus_batch_max_rows_per_external_template"] == 1
    assert manifest["review_state"] == {
        "new_decisions_emitted": False,
        "prior_validated_approvals": 0,
        "prior_validated_rejections": 0,
        "authorizes_training": False,
        "required_next_step": (
            "issue separate schema-valid approval or rejection receipts for each exact record "
            "after documented rubric-based review, accurately labeling whether the method was "
            "human or model-assisted"
        ),
    }
    assert manifest["approval_receipt_schema"]["sha256"] == core.sha256_file(
        selector.APPROVAL_SCHEMA_PATH
    )
    batch_key_inputs = manifest["batch"]["key_inputs"]
    assert batch_key_inputs["materializer_sha256"] == (review_pack.IMPORTED_MATERIALIZER_SHA256)
    assert batch_key_inputs["selector_sha256"] == selector.IMPORTED_SELECTOR_SHA256
    assert batch_key_inputs["approval_schema_sha256"] == (selector.IMPORTED_APPROVAL_SCHEMA_SHA256)
    assert (
        manifest["batch"]["key_sha256"]
        == hashlib.sha256(selector._canonical_json_bytes(batch_key_inputs)).hexdigest()
    )
    assert manifest["inputs"]["selector_sha256"] == selector.IMPORTED_SELECTOR_SHA256
    selector_archive = manifest["inputs"]["archived_executable_inputs"]["selector"]
    assert selector_archive["sha256"] == core.sha256_file(selector.PACKAGE_DIR / "select_sft.py")
    assert selector_archive["sha256"] == core.sha256_file(first / selector_archive["path"])
    warehouse_recipe_archive = manifest["inputs"]["warehouse_recipe"]
    selection_recipe_archive = manifest["inputs"]["selection_recipe"]
    assert warehouse_recipe_archive["sha256"] == core.sha256_file(
        first / warehouse_recipe_archive["path"]
    )
    assert selection_recipe_archive["sha256"] == core.sha256_file(
        first / selection_recipe_archive["path"]
    )
    assert warehouse_recipe_archive["path"] != selection_recipe_archive["path"]
    assert manifest["review_rows"]["sha256"] == core.sha256_file(
        first / manifest["review_rows"]["path"]
    )
    assert manifest["row_bindings"] == [
        {
            "source_id": row["source_id"],
            "record_id": row["record_id"],
            "record_content_sha256": row["record_content_sha256"],
        }
        for row in rows
    ]
    assert manifest["review_rows"]["sha256"] == second_manifest["review_rows"]["sha256"]
    assert (first / manifest["review_rows"]["path"]).read_bytes() == (
        second / second_manifest["review_rows"]["path"]
    ).read_bytes()
    assert not first.with_name(first.name + ".partial").exists()


def test_audit_review_pack_refills_from_cumulative_decisions_after_reapplying_caps(
    tmp_path,
) -> None:
    warehouse, records = _write_warehouse(tmp_path, qasc_shared_task=True)
    first = tmp_path / "audit-review-initial"
    first_manifest = review_pack.materialize_audit_review_pack(warehouse=warehouse, output=first)
    first_rows = _read_review_rows(first)
    by_source = {row["source_id"]: row for row in first_rows}
    assert set(by_source) == {"gsm8k", "qasc", "template_gsm"}

    rubric = _write_rubric(tmp_path / "audit-rubric.md")
    fingerprint = first_manifest["source_warehouse"]["dataset_fingerprint_sha256"]
    first_decisions = [
        _approval(
            fingerprint,
            source_id="template_gsm",
            record_id=by_source["template_gsm"]["record_id"],
            content_hash=by_source["template_gsm"]["record_content_sha256"],
            rubric_hash=core.sha256_file(rubric),
            decision="approved",
        ),
        _approval(
            fingerprint,
            source_id="qasc",
            record_id=by_source["qasc"]["record_id"],
            content_hash=by_source["qasc"]["record_content_sha256"],
            rubric_hash=core.sha256_file(rubric),
            decision="rejected",
        ),
    ]
    ledger = tmp_path / "cumulative-decisions-a.jsonl"
    ledger.write_text(
        "".join(json.dumps(receipt, separators=(",", ":")) + "\n" for receipt in first_decisions),
        encoding="utf-8",
    )

    refill = tmp_path / "audit-review-refill-a"
    refill_manifest = review_pack.materialize_audit_review_pack(
        warehouse=warehouse,
        output=refill,
        decision_receipts=[ledger],
        rubric_files=[rubric],
    )
    duplicate_refill = tmp_path / "audit-review-refill-b"
    duplicate_manifest = review_pack.materialize_audit_review_pack(
        warehouse=warehouse,
        output=duplicate_refill,
        decision_receipts=[ledger],
        rubric_files=[rubric],
    )
    refill_rows = _read_review_rows(refill)
    refill_by_source = {row["source_id"]: row for row in refill_rows}

    assert refill_manifest["batch"]["source_quotas"] == {
        "gsm8k": 1,
        "qasc": 1,
        "template_gsm": 0,
    }
    assert refill_manifest["row_count"] == len(refill_rows) == 2
    assert set(refill_by_source) == {"gsm8k", "qasc"}
    assert by_source["template_gsm"]["record_id"] not in {row["record_id"] for row in refill_rows}
    assert by_source["qasc"]["record_id"] not in {row["record_id"] for row in refill_rows}
    assert refill_by_source["gsm8k"]["record_id"] == by_source["gsm8k"]["record_id"]
    assert refill_by_source["qasc"]["source_task_sha256"] == by_source["qasc"]["source_task_sha256"]
    expected_qasc_replacement = next(
        record
        for record in records
        if record["provenance"]["source_id"] == "qasc"
        and record["id"] != by_source["qasc"]["record_id"]
    )
    assert refill_by_source["qasc"]["record_id"] == expected_qasc_replacement["id"]
    assert refill_manifest["decision_ledger"]["approved_by_source"] == {
        "gsm8k": 0,
        "qasc": 0,
        "template_gsm": 1,
    }
    assert refill_manifest["decision_ledger"]["rejected_by_source"] == {
        "gsm8k": 0,
        "qasc": 1,
        "template_gsm": 0,
    }
    assert refill_manifest["decision_ledger"]["omitted_decisions_may_reemit_rows"] is True
    assert refill_manifest["review_rows"]["sha256"] == duplicate_manifest["review_rows"]["sha256"]
    decision_archive = refill_manifest["decision_ledger"]["archive"]
    assert (
        core.sha256_file(refill / decision_archive["canonical_ledger"]["path"])
        == (decision_archive["canonical_ledger"]["sha256"])
    )
    assert all(
        core.sha256_file(refill / receipt["path"]) == receipt["sha256"]
        for receipt in decision_archive["receipt_inputs"]
    )
    assert all(
        core.sha256_file(refill / rubric_receipt["path"]) == rubric_receipt["sha256"]
        for rubric_receipt in decision_archive["rubrics"]
    )

    completed_decisions = [
        *first_decisions,
        *[
            _approval(
                fingerprint,
                source_id=row["source_id"],
                record_id=row["record_id"],
                content_hash=row["record_content_sha256"],
                rubric_hash=core.sha256_file(rubric),
                decision="approved",
            )
            for row in refill_rows
        ],
    ]
    completed_ledger = tmp_path / "cumulative-decisions-complete.jsonl"
    completed_ledger.write_text(
        "".join(
            json.dumps(receipt, separators=(",", ":")) + "\n" for receipt in completed_decisions
        ),
        encoding="utf-8",
    )
    completed = tmp_path / "audit-review-complete"
    completed_manifest = review_pack.materialize_audit_review_pack(
        warehouse=warehouse,
        output=completed,
        decision_receipts=[completed_ledger],
        rubric_files=[rubric],
    )
    assert completed_manifest["row_count"] == 0
    assert completed_manifest["batch"]["source_quotas"] == {
        "gsm8k": 0,
        "qasc": 0,
        "template_gsm": 0,
    }
    assert _read_review_rows(completed) == []


def test_audit_review_pack_archives_both_distinct_recipe_versions(tmp_path) -> None:
    warehouse, _ = _write_warehouse(tmp_path)
    selected_recipe = _mini_recipe()
    selected_recipe["recommended_sft_allocation_decision"] = {
        "version": "fixture-review-pack-override-v1",
        "reason": "Exercise distinct post-warehouse policy provenance.",
    }
    selected_recipe["training_note"] = "Distinct selection policy fixture."
    selected_recipe_path = tmp_path / "selection-recipe.json"
    selected_recipe_path.write_text(json.dumps(selected_recipe), encoding="utf-8")
    output = tmp_path / "audit-review-override"

    manifest = review_pack.materialize_audit_review_pack(
        warehouse=warehouse,
        output=output,
        recipe_path=selected_recipe_path,
    )

    binding = manifest["selection"]["recipe_binding"]
    assert binding["mode"] == "post_warehouse_quality_allocation_override"
    assert binding["warehouse_recipe_sha256"] != binding["selection_recipe_sha256"]
    for key in ("warehouse_recipe", "selection_recipe"):
        receipt = manifest["inputs"][key]
        assert core.sha256_file(output / receipt["path"]) == receipt["sha256"]
    assert manifest["inputs"]["warehouse_recipe"]["sha256"] == binding[
        "warehouse_recipe_sha256"
    ]
    assert manifest["inputs"]["selection_recipe"]["sha256"] == binding[
        "selection_recipe_sha256"
    ]


def test_audit_review_pack_rejects_selector_code_drift_atomically(tmp_path, monkeypatch) -> None:
    warehouse, _ = _write_warehouse(tmp_path)
    tampered_selector = tmp_path / "select_sft.py"
    tampered_selector.write_text("# not the imported selector\n", encoding="utf-8")
    monkeypatch.setattr(review_pack, "SELECTOR_PATH", tampered_selector)
    output = tmp_path / "audit-review"

    with pytest.raises(RuntimeError, match="loaded selector code differs"):
        review_pack.materialize_audit_review_pack(warehouse=warehouse, output=output)

    assert not output.exists()
    assert not output.with_name(output.name + ".partial").exists()


def test_audit_review_pack_rejects_tampered_warehouse_atomically(tmp_path) -> None:
    warehouse, _ = _write_warehouse(tmp_path)
    with (warehouse / "part-00000.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    output = tmp_path / "audit-review"

    with pytest.raises(ValueError, match="byte count mismatch"):
        review_pack.materialize_audit_review_pack(warehouse=warehouse, output=output)

    assert not output.exists()
    assert not output.with_name(output.name + ".partial").exists()


def test_audit_review_pack_refuses_overwrite(tmp_path) -> None:
    warehouse, _ = _write_warehouse(tmp_path)
    output = tmp_path / "audit-review"
    output.mkdir()
    (output / "keep.txt").write_text("do not replace", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        review_pack.materialize_audit_review_pack(warehouse=warehouse, output=output)

    assert (output / "keep.txt").read_text(encoding="utf-8") == "do not replace"


def test_selector_enforces_receipts_quotas_caps_and_is_deterministic(tmp_path) -> None:
    warehouse, records = _write_warehouse(tmp_path)
    rubric = _write_rubric(tmp_path / "rubric.md")
    approvals = tmp_path / "approvals.jsonl"
    receipts = _write_approvals(approvals, warehouse, records, rubric)

    first = tmp_path / "selected-a"
    manifest = selector.select_sft(
        warehouse=warehouse,
        output=first,
        approval_receipts=[approvals],
        rubric_files=[rubric],
    )
    second = tmp_path / "selected-b"
    second_manifest = selector.select_sft(
        warehouse=warehouse,
        output=second,
        approval_receipts=[approvals],
        rubric_files=[rubric],
    )

    rows = _read_output_rows(first)
    assert len(rows) == manifest["row_count"] == 20
    assert {row["split"] for row in rows} == {"train"}
    assert Counter(row["provenance"]["source_id"] for row in rows) == Counter(
        manifest["counts"]["source"]
    )
    assert manifest["counts"]["source"] == manifest["required_margins"]["source"]
    assert manifest["counts"]["subject"] == manifest["required_margins"]["subject"]
    assert manifest["counts"]["pedagogy"] == manifest["required_margins"]["pedagogy"]
    assert all(
        manifest["selection"]["capped_availability"][cell] >= quota
        for cell, quota in manifest["selection"]["cell_quotas"].items()
    )
    assert manifest["selection"]["max_rows_per_source_task_sha256"] == 1
    assert manifest["candidate_exclusions"]["excluded_by_source_task_cap"] >= 1
    assert manifest["selection"]["observed_max_rows_per_external_template"] == 1
    assert Counter(
        row["provenance"]["semantic_cluster_id"]
        for row in rows
        if row["provenance"]["source_id"] == "template_gsm"
    ) == {"template:fixture": 1}
    receipt_usage = manifest["approval_receipts"]["selected_row_usage"]
    assert sum(receipt_usage.values()) == 3
    assert set(receipt_usage) == {receipt["receipt_id"] for receipt in receipts}
    assert manifest["approval_receipts"]["validated_by_decision"] == {
        "approved": 4,
        "rejected": 0,
    }
    assert "not cryptographic signatures" in manifest["approval_receipts"]["trust_model"]
    assert manifest["inputs"]["approval_rubrics"]["count"] == 1
    copied_manifest_path = first / manifest["inputs"]["warehouse_manifest"]["path"]
    copied_warehouse_manifest = json.loads(copied_manifest_path.read_text(encoding="utf-8"))
    copied_bundle = manifest["inputs"]["warehouse_provenance_archives"]
    assert copied_bundle["archive_count"] == 3
    assert copied_bundle["copied_manifest_paths_resolve_from_this_root"] is True
    assert (
        copied_bundle["inventory_sha256"]
        == hashlib.sha256(selector._canonical_json_bytes(copied_bundle["archives"])).hexdigest()
    )
    for archive_key in (
        "provenance_archive",
        "holdout_source_archive",
        "source_evidence_archive",
    ):
        source_archive = copied_warehouse_manifest["inputs"][archive_key]
        copied_archive = copied_bundle["archives"][archive_key]
        assert copied_archive["file_count"] == len(source_archive["files"])
        for receipt in [*copied_archive["files"], copied_archive["receipts"]]:
            copied_path = first / receipt["path"]
            assert copied_path.stat().st_size == receipt["bytes"]
            assert core.sha256_file(copied_path) == receipt["sha256"]
            assert copied_path == copied_manifest_path.parent / receipt["warehouse_relative_path"]
    assert not (first / "selector-provenance/provenance-source-evidence/unreceipted.txt").exists()

    attribution_receipt = manifest["inputs"]["selected_source_attribution"]
    assert attribution_receipt == manifest["source_attribution"]["inventory"]
    attribution_path = first / attribution_receipt["path"]
    assert core.sha256_file(attribution_path) == attribution_receipt["sha256"]
    attribution = json.loads(attribution_path.read_text(encoding="utf-8"))
    assert attribution["blanket_license"] is None
    assert attribution["selected_row_count"] == 20
    assert attribution["source_count"] == 5
    attribution_sources = {source["source_id"]: source for source in attribution["sources"]}
    assert {
        source_id: source["selected_count"] for source_id, source in attribution_sources.items()
    } == manifest["counts"]["source"]
    assert {
        source_id: source["license"] for source_id, source in attribution_sources.items()
    } == manifest["source_attribution"]["license_by_source"]
    for source_id, source in attribution_sources.items():
        assert {
            row["provenance"]["license"]
            for row in rows
            if row["provenance"]["source_id"] == source_id
        } == {source["license"]["name"]}
    assert attribution_sources["qasc"]["license"]["archived_evidence"][0][
        "sha256"
    ] == core.sha256_file(warehouse / "provenance-source-evidence/qasc/README.md")
    assert attribution_sources["muta_verified_stem_v2"]["license"]["archived_evidence"][0][
        "sha256"
    ] == core.sha256_file(warehouse / "provenance-code/MUTA-LICENSE")
    for source in attribution["sources"]:
        assert source["creator"]
        assert source["title"] == source["name"]
        assert source["immutable_revision_config_split_evidence"]["selected_row_revisions"]
        assert source["immutable_revision_config_split_evidence"]["selected_source_splits"]
        assert (
            sum(source["transform_change_notice"]["selected_transform_counts"].values())
            == source["selected_count"]
        )
        assert (
            sum(source["verification_audit_result"]["authorization_counts"].values())
            == source["selected_count"]
        )
    assert manifest["dataset_fingerprint_sha256"] == second_manifest["dataset_fingerprint_sha256"]
    assert [(first / shard["path"]).read_bytes() for shard in manifest["shards"]] == [
        (second / shard["path"]).read_bytes() for shard in second_manifest["shards"]
    ]
    assert not first.with_name(first.name + ".partial").exists()


def test_selector_rejects_selection_recipe_drift_after_parsing(
    tmp_path, monkeypatch
) -> None:
    warehouse, records = _write_warehouse(tmp_path)
    rubric = _write_rubric(tmp_path / "rubric.md")
    approvals = tmp_path / "approvals.jsonl"
    _write_approvals(approvals, warehouse, records, rubric)
    selected_recipe = _mini_recipe()
    selected_recipe["recommended_sft_allocation_decision"] = {
        "version": "fixture-drift-guard-v1",
        "reason": "Exercise the recipe parse-to-archive drift guard.",
    }
    selected_recipe["training_note"] = "Drift-guard fixture."
    selected_recipe_path = tmp_path / "selection-recipe.json"
    selected_recipe_path.write_text(json.dumps(selected_recipe), encoding="utf-8")
    real_loader = selector._load_selection_recipe

    def load_then_drift(**kwargs):
        loaded = real_loader(**kwargs)
        with selected_recipe_path.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        return loaded

    monkeypatch.setattr(selector, "_load_selection_recipe", load_then_drift)
    output = tmp_path / "selected-drifted-recipe"

    with pytest.raises(RuntimeError, match="selector provenance input drifted"):
        selector.select_sft(
            warehouse=warehouse,
            output=output,
            approval_receipts=[approvals],
            rubric_files=[rubric],
            recipe_path=selected_recipe_path,
        )

    assert not output.exists()
    assert output.with_name(output.name + ".partial").is_dir()


def test_selector_rejects_provenance_tamper_and_copy_time_drift(monkeypatch, tmp_path) -> None:
    tampered_warehouse, tampered_records = _write_warehouse(tmp_path / "tampered")
    tampered_rubric = _write_rubric(tmp_path / "tampered-rubric.md")
    tampered_approvals = tmp_path / "tampered-approvals.jsonl"
    _write_approvals(tampered_approvals, tampered_warehouse, tampered_records, tampered_rubric)
    with (tampered_warehouse / "provenance-source-evidence/qasc/README.md").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write("tamper\n")
    with pytest.raises(ValueError, match="receipted warehouse input byte count mismatch"):
        selector.select_sft(
            warehouse=tampered_warehouse,
            output=tmp_path / "tampered-output",
            approval_receipts=[tampered_approvals],
            rubric_files=[tampered_rubric],
        )

    drifting_warehouse, drifting_records = _write_warehouse(tmp_path / "drifting")
    drifting_rubric = _write_rubric(tmp_path / "drifting-rubric.md")
    drifting_approvals = tmp_path / "drifting-approvals.jsonl"
    _write_approvals(drifting_approvals, drifting_warehouse, drifting_records, drifting_rubric)
    drifting_source = (drifting_warehouse / "provenance-source-evidence/qasc/README.md").resolve()
    real_copyfile = shutil.copyfile

    def copy_then_drift(source, destination):
        result = real_copyfile(source, destination)
        if Path(source).resolve() == drifting_source:
            with Path(source).open("a", encoding="utf-8") as handle:
                handle.write("copy-time drift\n")
        return result

    monkeypatch.setattr(selector.shutil, "copyfile", copy_then_drift)
    with pytest.raises(RuntimeError, match="warehouse provenance input drifted while copied"):
        selector.select_sft(
            warehouse=drifting_warehouse,
            output=tmp_path / "drifting-output",
            approval_receipts=[drifting_approvals],
            rubric_files=[drifting_rubric],
        )


def test_selector_fails_closed_without_required_audit_receipts(tmp_path) -> None:
    warehouse, _ = _write_warehouse(tmp_path)
    output = tmp_path / "selected"

    with pytest.raises(RuntimeError, match="external source .* one audited"):
        selector.select_sft(warehouse=warehouse, output=output)

    assert not output.exists()
    assert not output.with_name(output.name + ".partial").exists()


def test_selector_rejects_stale_and_malformed_receipts(tmp_path) -> None:
    warehouse, records = _write_warehouse(tmp_path)
    rubric = _write_rubric(tmp_path / "rubric.md")
    approvals = tmp_path / "approvals.jsonl"
    receipts = _write_approvals(approvals, warehouse, records, rubric)
    receipts[0]["record_content_sha256"] = "0" * 64
    receipts[0]["receipt_id"] = selector.approval_receipt_id(receipts[0])
    approvals.write_text(
        "".join(json.dumps(receipt) + "\n" for receipt in receipts), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="stale content hash"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "stale-output",
            approval_receipts=[approvals],
            rubric_files=[rubric],
        )

    receipts = _write_approvals(approvals, warehouse, records, rubric)
    receipts[0].pop("review_method")
    receipts[0]["receipt_id"] = selector.approval_receipt_id(receipts[0])
    approvals.write_text(
        "".join(json.dumps(receipt) + "\n" for receipt in receipts), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="malformed approval receipt"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "malformed-output",
            approval_receipts=[approvals],
            rubric_files=[rubric],
        )

    receipts = _write_approvals(approvals, warehouse, records, rubric)
    receipts[0]["review_method"] = "   "
    receipts[0]["receipt_id"] = selector.approval_receipt_id(receipts[0])
    approvals.write_text(
        "".join(json.dumps(receipt) + "\n" for receipt in receipts), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="malformed approval receipt"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "blank-review-method-output",
            approval_receipts=[approvals],
            rubric_files=[rubric],
        )


def test_rejected_receipt_is_bound_archived_reported_and_never_selected(tmp_path) -> None:
    warehouse, records = _write_warehouse(tmp_path)
    rubric = _write_rubric(tmp_path / "rubric.md")
    approvals_path = tmp_path / "approvals.jsonl"
    receipts = _write_approvals(approvals_path, warehouse, records, rubric)
    fingerprint = json.loads((warehouse / "manifest.json").read_text())[
        "dataset_fingerprint_sha256"
    ]
    qasc_rows = [record for record in records if record["provenance"]["source_id"] == "qasc"]
    assert len(qasc_rows) == 2
    rejected_row = qasc_rows[1]
    rejected_receipt = _approval(
        fingerprint,
        source_id="qasc",
        record_id=rejected_row["id"],
        content_hash=selector.record_content_sha256(rejected_row),
        rubric_hash=core.sha256_file(rubric),
        decision="rejected",
    )
    stale_rejected_receipt = dict(rejected_receipt)
    stale_rejected_receipt["record_content_sha256"] = "0" * 64
    stale_rejected_receipt["receipt_id"] = selector.approval_receipt_id(stale_rejected_receipt)
    approvals_path.write_text(
        "".join(
            json.dumps(receipt, separators=(",", ":")) + "\n"
            for receipt in [*receipts, stale_rejected_receipt]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="stale content hash"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "stale-rejected-output",
            approval_receipts=[approvals_path],
            rubric_files=[rubric],
        )

    receipts.append(rejected_receipt)
    approvals_path.write_text(
        "".join(json.dumps(receipt, separators=(",", ":")) + "\n" for receipt in receipts),
        encoding="utf-8",
    )

    output = tmp_path / "selected"
    manifest = selector.select_sft(
        warehouse=warehouse,
        output=output,
        approval_receipts=[approvals_path],
        rubric_files=[rubric],
    )

    assert rejected_row["id"] not in {row["id"] for row in _read_output_rows(output)}
    receipt_report = manifest["approval_receipts"]
    assert receipt_report["validated_by_decision"] == {"approved": 4, "rejected": 1}
    assert receipt_report["selected_row_usage_by_decision"]["rejected"] == {
        rejected_receipt["receipt_id"]: 0
    }
    assert receipt_report["selected_row_usage"][rejected_receipt["receipt_id"]] == 0
    assert receipt_report["rejected_receipts_never_authorize_selection"] is True
    archived_receipts = (output / manifest["inputs"]["approval_receipts"]["path"]).read_text(
        encoding="utf-8"
    )
    assert rejected_receipt["receipt_id"] in archived_receipts


def test_selector_requires_rubric_artifact_and_exact_row_authorization(tmp_path) -> None:
    warehouse, records = _write_warehouse(tmp_path)
    rubric = _write_rubric(tmp_path / "rubric.md")
    approvals = tmp_path / "approvals.jsonl"
    receipts = _write_approvals(approvals, warehouse, records, rubric)

    with pytest.raises(ValueError, match="no supplied rubric artifact"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "missing-rubric-output",
            approval_receipts=[approvals],
        )

    fingerprint = json.loads((warehouse / "manifest.json").read_text())[
        "dataset_fingerprint_sha256"
    ]
    templates = [
        record for record in records if record["provenance"]["source_id"] == "template_gsm"
    ]
    cluster_receipt = _approval(
        fingerprint,
        source_id="template_gsm",
        semantic_cluster_id="template:fixture",
        content_hash=selector.semantic_cluster_content_sha256(
            templates, source_id="template_gsm", semantic_cluster_id="template:fixture"
        ),
        rubric_hash=core.sha256_file(rubric),
    )
    cluster_only = [cluster_receipt, *receipts[2:]]
    approvals.write_text(
        "".join(json.dumps(receipt) + "\n" for receipt in cluster_only), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="row-only"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "cluster-output",
            approval_receipts=[approvals],
            rubric_files=[rubric],
        )


def test_selector_rejects_tampered_shard_and_cross_split_source_task(tmp_path) -> None:
    warehouse, records = _write_warehouse(tmp_path / "tamper")
    rubric = _write_rubric(tmp_path / "tamper-rubric.md")
    approvals = tmp_path / "tamper-approvals.jsonl"
    _write_approvals(approvals, warehouse, records, rubric)
    with (warehouse / "part-00000.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(ValueError, match="byte count mismatch"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "tamper-output",
            approval_receipts=[approvals],
            rubric_files=[rubric],
        )

    cross_warehouse, cross_records = _write_warehouse(
        tmp_path / "cross-split", cross_split_task=True
    )
    cross_approvals = tmp_path / "cross-approvals.jsonl"
    cross_rubric = _write_rubric(tmp_path / "cross-rubric.md")
    _write_approvals(cross_approvals, cross_warehouse, cross_records, cross_rubric)
    with pytest.raises(ValueError, match="canonical source task crosses dataset splits"):
        selector.select_sft(
            warehouse=cross_warehouse,
            output=tmp_path / "cross-output",
            approval_receipts=[cross_approvals],
            rubric_files=[cross_rubric],
        )


def test_selector_rejects_warehouse_seed_recipe_drift(tmp_path) -> None:
    warehouse, records = _write_warehouse(tmp_path)
    rubric = _write_rubric(tmp_path / "rubric.md")
    approvals = tmp_path / "approvals.jsonl"
    _write_approvals(approvals, warehouse, records, rubric)
    manifest_path = warehouse / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["seed"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="archived recipe seed"):
        selector.select_sft(
            warehouse=warehouse,
            output=tmp_path / "seed-drift-output",
            approval_receipts=[approvals],
            rubric_files=[rubric],
        )


def test_selector_rejects_live_validator_drift(monkeypatch, tmp_path) -> None:
    warehouse, _ = _write_warehouse(tmp_path)
    manifest = json.loads((warehouse / "manifest.json").read_text())
    real_sha256_file = selector.sha256_file

    def mismatched_live_core(path):
        if Path(path).resolve() == (selector.PACKAGE_DIR / "core.py").resolve():
            return "0" * 64
        return real_sha256_file(path)

    monkeypatch.setattr(selector, "sha256_file", mismatched_live_core)
    with pytest.raises(ValueError, match="live validator core.py differs"):
        selector._assert_live_validators_match_warehouse(manifest)


def test_selector_keeps_output_partial_if_materialization_fails(monkeypatch, tmp_path) -> None:
    warehouse, records = _write_warehouse(tmp_path)
    rubric = _write_rubric(tmp_path / "rubric.md")
    approvals = tmp_path / "approvals.jsonl"
    _write_approvals(approvals, warehouse, records, rubric)
    original_write = selector._AtomicShardWriter.write
    calls = 0

    def fail_on_second(writer, record):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("deliberate materialization failure")
        return original_write(writer, record)

    monkeypatch.setattr(selector._AtomicShardWriter, "write", fail_on_second)
    output = tmp_path / "selected"
    with pytest.raises(RuntimeError, match="deliberate materialization failure"):
        selector.select_sft(
            warehouse=warehouse,
            output=output,
            approval_receipts=[approvals],
            rubric_files=[rubric],
        )

    assert not output.exists()
    partial = output.with_name(output.name + ".partial")
    assert partial.is_dir()
    assert not (partial / "manifest.json").exists()
