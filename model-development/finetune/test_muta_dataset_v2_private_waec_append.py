from __future__ import annotations

import copy
import hashlib
import importlib
import json
from collections import Counter
from pathlib import Path

import pytest

adapter = importlib.import_module(
    "model-development.finetune.muta_dataset_v2.private_waec_append"
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "corpus" / "waec" / "questions.jsonl"
ATTESTATION_PATH = ROOT / "corpus" / "waec" / "private-training-attestation.json"
CHEETAH_ATTESTATION_PATH = (
    ROOT / "corpus" / "waec" / "private-training-cheetah-attestation.json"
)
REVIEW_PATHS = [
    ROOT / "corpus" / "waec" / "private-training-review-ledger.jsonl",
    ROOT
    / "model-development"
    / "finetune"
    / "muta_dataset_v2"
    / "WAEC_COMPLETE_PUBLISHED_APPROVED_IDS.jsonl",
]


def _require_private_inputs(*paths: Path) -> None:
    missing = [path for path in paths if not path.is_file()]
    if missing:
        pytest.skip("private WAEC review fixtures are intentionally absent")


class DeterministicTokenCounter:
    tokenizer_id = "Qwen/Qwen2.5-1.5B-Instruct"
    revision = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
    chat_template_sha256 = (
        "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"
    )
    max_sequence_tokens = 1024

    def count(self, messages: list[dict[str, str]]) -> int:
        del messages
        return 100

    def annotate(self, record: dict) -> None:
        record["tokenization"] = {
            "tokenizer_id": self.tokenizer_id,
            "tokenizer_revision": self.revision,
            "chat_template_sha256": self.chat_template_sha256,
            "sequence_tokens": 100,
            "max_sequence_tokens": self.max_sequence_tokens,
            "within_limit": True,
        }

    def validate(self, record: dict) -> bool:
        return record.get("tokenization") == {
            "tokenizer_id": self.tokenizer_id,
            "tokenizer_revision": self.revision,
            "chat_template_sha256": self.chat_template_sha256,
            "sequence_tokens": 100,
            "max_sequence_tokens": self.max_sequence_tokens,
            "within_limit": True,
        }


@pytest.fixture(scope="module")
def live_inputs() -> dict:
    _require_private_inputs(CORPUS_PATH, ATTESTATION_PATH, *REVIEW_PATHS)
    corpus_rows, corpus_sha256 = adapter._load_jsonl(CORPUS_PATH)
    review_rows, review_sha256, review_sources = adapter._load_review_ledgers(REVIEW_PATHS)
    attestation, _raw, attestation_sha256 = adapter._load_json(ATTESTATION_PATH)
    return {
        "corpus_rows": corpus_rows,
        "corpus_sha256": corpus_sha256,
        "review_rows": review_rows,
        "review_sha256": review_sha256,
        "review_sources": review_sources,
        "attestation": attestation,
        "attestation_sha256": attestation_sha256,
    }


def _build(inputs: dict, **overrides: object) -> list[dict]:
    values = {
        "corpus_rows": inputs["corpus_rows"],
        "corpus_sha256": inputs["corpus_sha256"],
        "review_rows": inputs["review_rows"],
        "review_sha256": inputs["review_sha256"],
        "review_sources": inputs["review_sources"],
        "attestation": inputs["attestation"],
        "attestation_sha256": inputs["attestation_sha256"],
        "token_counter": DeterministicTokenCounter(),
        "holdouts": adapter.HoldoutIndex([]),
    }
    values.update(overrides)
    return adapter.build_approved_records(**values)


@pytest.fixture(scope="module")
def approved_records(live_inputs: dict) -> list[dict]:
    return _build(live_inputs)


def test_live_review_bundle_builds_exactly_47_rows(
    approved_records: list[dict],
) -> None:
    assert len(approved_records) == 47
    assert len({row["id"] for row in approved_records}) == 47
    assert len({adapter.normalize_text(row["prompt"]) for row in approved_records}) == 47
    assert Counter(row["subject"] for row in approved_records) == {
        "physics": 30,
        "mathematics": 8,
        "chemistry": 6,
        "biology": 3,
    }
    assert all(row["split"] == "train" for row in approved_records)


def test_attestation_rejects_a_changed_review_ledger_bundle(
    tmp_path: Path,
    live_inputs: dict,
) -> None:
    changed = tmp_path / "changed-ledger.jsonl"
    changed.write_bytes(REVIEW_PATHS[0].read_bytes() + b"\n")
    review_rows, review_sha256, review_sources = adapter._load_review_ledgers(
        [changed, REVIEW_PATHS[1]]
    )

    with pytest.raises(adapter.AppendRefused, match="different review bundle"):
        _build(
            live_inputs,
            review_rows=review_rows,
            review_sha256=review_sha256,
            review_sources=review_sources,
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("source_corpus_sha256", "not bound to the corpus snapshot"),
        ("source_record_sha256", "not bound to the exact source row"),
    ],
)
def test_review_must_bind_the_exact_corpus_and_source_row(
    live_inputs: dict,
    field: str,
    message: str,
) -> None:
    reviews = copy.deepcopy(live_inputs["review_rows"])
    approved = next(
        row for row in reviews if adapter._review_decision(row) in adapter.APPROVED_DECISIONS
    )
    approved[field] = "0" * 64

    with pytest.raises(adapter.AppendRefused, match=message):
        _build(live_inputs, review_rows=reviews)


def test_incomplete_source_requires_an_explicitly_reviewed_clean_prompt(
    live_inputs: dict,
) -> None:
    sources = {row["record_id"]: row for row in live_inputs["corpus_rows"]}
    reviews = copy.deepcopy(live_inputs["review_rows"])
    approved = next(
        row
        for row in reviews
        if adapter._review_decision(row) in adapter.APPROVED_DECISIONS
        and sources[row["record_id"]]["content_status"] == "incomplete"
    )
    approved.pop("clean_prompt", None)

    with pytest.raises(adapter.AppendRefused, match="lacks an explicitly reviewed clean prompt"):
        _build(live_inputs, review_rows=reviews)


def test_correction_flag_must_match_the_review_decision(live_inputs: dict) -> None:
    reviews = copy.deepcopy(live_inputs["review_rows"])
    corrected = next(row for row in reviews if row.get("correction_applied") is True)
    corrected["decision"] = "approve_verified"

    with pytest.raises(adapter.AppendRefused, match="decision/correction flag mismatch"):
        _build(live_inputs, review_rows=reviews)


def test_prompt_correction_does_not_reclassify_a_matching_answer() -> None:
    source = {
        "record_id": "row-1",
        "subject": "mathematics",
        "year": 2025,
        "question_text": "Find the missing side.",
        "correct_answer": "A",
        "worked_solution": "The publisher obtains 6 cm.",
        "options": [
            {"label": "A", "text": "6 cm"},
            {"label": "B", "text": "5 cm"},
            {"label": "C", "text": "8 cm"},
            {"label": "D", "text": "9 cm"},
        ],
        "assets": [],
    }
    entry = {
        "record_id": "row-1",
        "decision": "approve_corrected_verified",
        "canonical_answer": "A. 6 cm",
        "worked_solution": "Similarity gives the missing side as 6 cm.",
        "verification_method": "rendered-PDF review and independent recomputation",
        "evidence_summary": "A typographical relation in the prompt was repaired.",
        "source_answer_origin": "publisher_worked_solution_in_record",
        "correction_applied": True,
        "prompt_correction_applied": True,
        "answer_correction_applied": False,
        "correction_origin": "publisher_question_typographical_error",
        "clean_prompt": (
            "Find the missing side. Options: A. 6 cm; B. 5 cm; C. 8 cm; D. 9 cm."
        ),
    }

    compiled = adapter._compile_review_entry(entry, source)

    assert compiled is not None
    assert compiled["answer_origin"] == "publisher_answer_independently_verified"
    assert compiled["source_answer_match"] is True
    assert compiled["prompt_correction_applied"] is True
    assert compiled["answer_correction_applied"] is False

    missing_origin = copy.deepcopy(entry)
    missing_origin.pop("correction_origin")
    with pytest.raises(adapter.AppendRefused, match="correction lacks an explicit origin"):
        adapter._compile_review_entry(missing_origin, source)


def test_non_exact_overlap_requires_a_bound_adjudication(live_inputs: dict) -> None:
    attestation = copy.deepcopy(live_inputs["attestation"])
    attestation["overlap_adjudications"] = []

    with pytest.raises(adapter.AppendRefused, match="overlapping reviews disagree on answer"):
        _build(live_inputs, attestation=attestation)


def test_private_training_eligibility_does_not_rewrite_publisher_rights(
    approved_records: list[dict],
) -> None:
    assert all(
        row["verification"]["status"] == "model_assisted_reviewed"
        and row["verification"]["reviewer_type"] == "model_assisted"
        and row["verification"]["training_eligible"] is True
        and row["verification"]["publisher_permission_asserted"] is False
        and row["verification"]["publisher_license_unchanged"] is True
        for row in approved_records
    )
    assert {
        row["provenance"]["license"] for row in approved_records
    } == {"Copyright West African Examinations Council. All rights reserved."}
    inherited_blocks = [
        row
        for row in approved_records
        if row["verification"]["audit_history"].get("rights_status")
        == "blocked_pending_written_permission"
    ]
    assert len(inherited_blocks) == 26
    assert all(
        row["verification"]["audit_history"]["training_eligible"] is False
        and row["verification"]["training_eligibility_basis"]
        == "project_owner_private_training_adjudication"
        for row in inherited_blocks
    )


def test_cheetah_text_only_review_requires_bound_pdf_evidence() -> None:
    source = {
        "assets": [],
        "source": {
            "source_type": "cheetah_pdf",
            "local_question_file": "raw/cheetah/2019-questions.pdf",
            "local_answer_file": "raw/cheetah/2019-answers.pdf",
        },
    }
    entry = {
        "clean_prompt": "A complete text-only problem.",
        "all_required_assets_resolved": True,
        "visual_dependency_status": "reviewed_text_only_self_contained",
        "pdf_question_file": "raw/cheetah/2019-questions.pdf",
        "pdf_answer_file": "raw/cheetah/2019-answers.pdf",
    }

    adapter._validate_cheetah_text_only_review(entry, source, record_id="row-1")

    changed = copy.deepcopy(entry)
    changed["pdf_answer_file"] = "raw/cheetah/2020-answers.pdf"
    with pytest.raises(adapter.AppendRefused, match="answer evidence does not match"):
        adapter._validate_cheetah_text_only_review(changed, source, record_id="row-1")


def test_clean_prompt_may_recover_multipart_text_retained_as_options() -> None:
    source = {
        "question_text": "",
        "options": [
            {"label": "A", "text": "Find the original amount."},
            {"label": "B", "text": "Find the percentage profit."},
        ],
    }
    evidence = adapter._source_prompt_evidence(source)

    assert "A. Find the original amount." in evidence
    assert "B. Find the percentage profit." in evidence
    assert adapter._token_containment(
        "Find the original amount. Find the percentage profit.", evidence
    ) == 1.0


def test_exclusion_receipt_does_not_require_an_answer_payload() -> None:
    source = {"record_id": "row-1"}
    entry = {
        "record_id": "row-1",
        "decision": "exclude_visual_dependency",
        "evidence_summary": "The prompt depends on an omitted diagram.",
    }

    assert adapter._compile_review_entry(entry, source) is None


def test_pdf_text_only_review_rejects_visual_and_extraction_artifacts() -> None:
    assert adapter._UNRESOLVED_VISUAL_DEPENDENCY.search(
        "Use the diagram below to find x."
    )
    assert adapter._PDF_EXTRACTION_ARTIFACT.search("Math input error")
    assert adapter._PDF_EXTRACTION_ARTIFACT.search("Solve \\frac{x}{2} = 3")


def test_mcq_answer_may_appear_only_as_one_of_four_bound_options() -> None:
    source = {
        "correct_answer": "D",
        "options": [
            {"label": "A", "text": "19 m"},
            {"label": "B", "text": "23 m"},
            {"label": "C", "text": "24 m"},
            {"label": "D", "text": "26 m"},
        ],
    }
    prompt = (
        "Find the length.\nA. 19 m\nB. 23 m\nC. 24 m\nD. 26 m"
    )

    assert adapter._validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt,
        canonical_answer="D. 26 m",
        corrected=False,
    )
    assert not adapter._validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt.replace("C. 24 m\n", ""),
        canonical_answer="D. 26 m",
        corrected=False,
    )
    assert adapter._clean_source_prompt(
        prompt,
        canonical_answer="D. 26 m",
        allow_answer_option_in_prompt=True,
    ).endswith("D. 26 m")


def test_legacy_inline_mcq_options_are_bound_before_leakage_exception() -> None:
    source = {
        "question_text": (
            "Find y. Possible answers: A. 8; B. 7; C. 6; D. 5"
        ),
        "correct_answer": "C",
        "options": [],
    }
    prompt = "Find y.\nA. 8\nB. 7\nC. 6\nD. 5"

    assert adapter._validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt,
        canonical_answer="C. 6",
        corrected=True,
    )


def test_legacy_log_base_option_normalizes_to_reviewed_unicode_form() -> None:
    source = {
        "question_text": (
            "Simplify. Possible answers: A. log1090; B. log1019; "
            "C. log109; D. log106"
        ),
        "correct_answer": "A",
        "options": [],
    }
    prompt = (
        "Simplify. Options: A. log₁₀90; B. log₁₀19; "
        "C. log₁₀9; D. log₁₀6."
    )

    assert adapter._validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt,
        canonical_answer="A. log₁₀90.",
        corrected=False,
    )


def test_reviewed_pdf_transcription_can_recover_blank_source_options() -> None:
    source = {
        "question_text": "Find , expressing the answer in base 2.",
        "correct_answer": "C",
        "options": [{"label": "A", "text": "B."}, {"label": "C", "text": "D."}],
    }
    prompt = (
        "Find 11000₂ − 101₂, expressing the answer in base 2.\n"
        "A. 10001₂\nB. 10010₂\nC. 10011₂\nD. 10100₂"
    )

    assert not adapter._validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt,
        canonical_answer="C. 10011₂",
        corrected=False,
    )
    assert adapter._validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt,
        canonical_answer="C. 10011₂",
        corrected=False,
        reviewed_pdf_transcription=True,
    )
    assert not adapter._validated_mcq_prompt_answer(
        source,
        clean_prompt=prompt,
        canonical_answer="D. 10100₂",
        corrected=False,
        reviewed_pdf_transcription=True,
    )

    currency_source = {
        "question_text": "Share ₦ in the ratio .",
        "correct_answer": "C",
        "options": [
            {"label": "A", "text": "₦"},
            {"label": "B", "text": "₦"},
            {"label": "C", "text": "₦"},
            {"label": "D", "text": "₦"},
        ],
    }
    currency_prompt = (
        "Share ₦12.00 in the ratio 1:2:3. Options: "
        "A. ₦2.00; B. ₦4.00; C. ₦6.00; D. ₦8.00."
    )
    assert adapter._validated_mcq_prompt_answer(
        currency_source,
        clean_prompt=currency_prompt,
        canonical_answer="C. ₦6.00.",
        corrected=False,
        reviewed_pdf_transcription=True,
    )


def test_answer_pdf_origin_requires_bound_source_evidence() -> None:
    source = {
        "correct_answer": "B",
        "source": {"local_answer_file": "raw/cheetah/2025-answers.pdf"},
    }

    adapter._validate_source_answer_origin(
        source,
        source_origin="publisher_worked_solution_in_answer_pdf",
        record_id="row-1",
    )

    changed = copy.deepcopy(source)
    changed["source"].pop("local_answer_file")
    with pytest.raises(adapter.AppendRefused, match="answer PDF is absent"):
        adapter._validate_source_answer_origin(
            changed,
            source_origin="publisher_worked_solution_in_answer_pdf",
            record_id="row-1",
        )


def test_cheetah_attestation_binds_raw_pdf_bytes() -> None:
    _require_private_inputs(CHEETAH_ATTESTATION_PATH)
    attestation = json.loads(CHEETAH_ATTESTATION_PATH.read_text(encoding="utf-8"))
    source_pdfs = [ROOT / binding["path"] for binding in attestation["source_pdf_bindings"]]
    _require_private_inputs(*source_pdfs)
    adapter._validate_attested_source_pdfs(attestation)

    changed = copy.deepcopy(attestation)
    changed["source_pdf_bindings"][0]["sha256"] = "0" * 64
    with pytest.raises(adapter.AppendRefused, match="source PDF hash changed"):
        adapter._validate_attested_source_pdfs(changed)


def _base_shard_receipt() -> dict:
    return {
        "path": "part-00000.jsonl",
        "rows": 1,
        "bytes": 100,
        "sha256": "a" * 64,
    }


def _warehouse_manifest() -> dict:
    shard = _base_shard_receipt()
    one = {"base": 1}
    return {
        "profile": "warehouse",
        "dataset_name": "fixture-warehouse",
        "row_count": 1,
        "dataset_fingerprint_sha256": adapter._dataset_fingerprint([shard]),
        "requested_counts": dict(one),
        "sources": [{"id": "base", "rows": 1}],
        "verification_semantics_by_source": {},
        "training_disposition_totals": {"native_eligible_train": 1},
        "counts": {
            "source": dict(one),
            "source_split": dict(one),
            "source_warehouse_split_eligibility": {
                "base": {"train": {"training_eligible": 1}}
            },
            "semantic_cluster_count_by_source": dict(one),
            "subject": dict(one),
            "topic": dict(one),
            "difficulty": dict(one),
            "pedagogy": dict(one),
            "formula_template_method": dict(one),
            "curriculum_alignment": dict(one),
            "source_subject_pedagogy": dict(one),
            "verification": dict(one),
            "eligibility": {"eligible": 1},
            "audit_eligibility": {"training_eligible": 1},
            "split": {"train": 1},
        },
        "tokenization": {
            "minimum_sequence_tokens": 100,
            "maximum_sequence_tokens": 100,
            "mean_sequence_tokens": 100.0,
            "buckets": {"0001-0128": 1},
        },
        "shards": [shard],
        "training_warning": "fixture",
    }


def _sft_manifest() -> dict:
    shard = _base_shard_receipt()
    return {
        "dataset_name": "muta-stem-sft-v2-selected",
        "row_count": 1,
        "dataset_fingerprint_sha256": adapter._dataset_fingerprint([shard]),
        "counts": {
            "source": {"base": 1},
            "subject": {"base": 1},
            "pedagogy": {"base": 1},
            "authorization": {"native_training_eligible": 1},
        },
        "required_margins": {
            "source": {"base": 1},
            "subject": {"base": 1},
            "pedagogy": {"base": 1},
        },
        "source_attribution": {
            "selected_count_by_source": {"base": 1},
            "license_by_source": {},
        },
        "shards": [shard],
    }


def _append_metadata() -> dict:
    return {
        "append_id": "fixture-append",
        "publisher_licences_by_source": {
            "waec_elearning": {
                "name": "Copyright West African Examinations Council. All rights reserved.",
                "url": "https://www.waeconline.org.ng/e-learning/",
                "unchanged_by_user_attestation": True,
            }
        },
        "authorization": {
            "private_training_attestation": {
                "attestation_id": "fixture-attestation"
            }
        },
        "distribution_warning": "fixture private-use warning",
    }


def test_manifest_updates_have_exact_counts_fingerprints_and_inverse_patches(
    approved_records: list[dict],
) -> None:
    new_shard = {
        "path": "part-00001-private-waec.jsonl",
        "rows": len(approved_records),
        "bytes": 12345,
        "sha256": "b" * 64,
    }
    fixtures = [
        ("warehouse", _warehouse_manifest(), adapter._update_warehouse_manifest),
        ("sft", _sft_manifest(), adapter._update_sft_manifest),
    ]
    for kind, before, updater in fixtures:
        before_bytes = adapter.manifest_bytes(before)
        updated, reverse = updater(
            before,
            records=approved_records,
            shard=new_shard,
            append_metadata=_append_metadata(),
        )
        assert updated["row_count"] == 48
        assert updated["dataset_fingerprint_sha256"] == adapter._dataset_fingerprint(
            updated["shards"]
        )
        assert updated["shards"][0] == before["shards"][0]
        if kind == "warehouse":
            assert updated["counts"]["eligibility"]["eligible"] == 48
            assert updated["counts"]["verification"]["model_assisted_reviewed"] == 47
            assert updated["training_disposition_totals"][
                "private_exact_row_eligible"
            ] == 47
        else:
            assert updated["counts"]["authorization"]["private_exact_row_review"] == 47
            assert sum(updated["required_margins"]["source"].values()) == 48
        restored = adapter._apply_reverse_patch(updated, reverse)
        assert adapter.manifest_bytes(restored) == before_bytes


def _write_target(path: Path, manifest: dict) -> None:
    path.mkdir()
    base_row = {
        "id": "fixture_base_record",
        "prompt": "Unrelated fixture prompt.",
        "contamination": {
            "normalized_prompt_sha256": adapter.normalized_sha256(
                "Unrelated fixture prompt."
            ),
            "source_task_sha256": "c" * 64,
        },
    }
    shard_bytes = (json.dumps(base_row, separators=(",", ":")) + "\n").encode()
    (path / "part-00000.jsonl").write_bytes(shard_bytes)
    receipt = manifest["shards"][0]
    receipt["bytes"] = len(shard_bytes)
    receipt["sha256"] = hashlib.sha256(shard_bytes).hexdigest()
    manifest["dataset_fingerprint_sha256"] = adapter._dataset_fingerprint(
        manifest["shards"]
    )
    (path / "manifest.json").write_bytes(adapter.manifest_bytes(manifest))


def _file_snapshot(path: Path) -> dict[str, bytes]:
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_dry_planning_writes_nothing(tmp_path: Path) -> None:
    _require_private_inputs(CORPUS_PATH, ATTESTATION_PATH, *REVIEW_PATHS)
    warehouse = tmp_path / "warehouse"
    sft = tmp_path / "sft"
    _write_target(warehouse, _warehouse_manifest())
    _write_target(sft, _sft_manifest())
    before = {
        "warehouse": _file_snapshot(warehouse),
        "sft": _file_snapshot(sft),
    }

    _append_id, records, plans, summary = adapter.plan_append(
        corpus_path=CORPUS_PATH,
        review_paths=REVIEW_PATHS,
        attestation_path=ATTESTATION_PATH,
        warehouse_path=warehouse,
        sft_path=sft,
        token_counter=DeterministicTokenCounter(),
        holdouts=adapter.HoldoutIndex([]),
    )

    assert len(records) == 47
    assert len(plans) == 2
    assert summary["status"] == "ready"
    assert not any(plan.shard_path.exists() or plan.receipt_path.exists() for plan in plans)
    assert before == {
        "warehouse": _file_snapshot(warehouse),
        "sft": _file_snapshot(sft),
    }
