from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

core = importlib.import_module("model-development.finetune.muta_dataset_v2.core")
generators = importlib.import_module("model-development.finetune.muta_dataset_v2.generators")
adapters = importlib.import_module("model-development.finetune.muta_dataset_v2.adapters")
builder = importlib.import_module("model-development.finetune.muta_dataset_v2.build")
sampler = importlib.import_module("model-development.finetune.muta_dataset_v2.sample")
tokenization = importlib.import_module("model-development.finetune.muta_dataset_v2.tokenization")


def test_holdout_index_loads_all_local_evaluations() -> None:
    holdouts = core.HoldoutIndex.from_repository()

    assert holdouts.count >= 100
    assert len(holdouts.digest) == 64
    assert holdouts.compare(
        "A trader buys 24 identical crates for 18 000 naira and sells them at a "
        "25% profit. What is the selling price of one crate? Show your working."
    )[0]


def test_holdout_containment_cannot_be_hidden_by_rendering() -> None:
    stem = "A trolley has mass 5 kg and acceleration 4 metres per second squared."
    holdouts = core.HoldoutIndex([stem])

    blocked, score = holdouts.compare(
        stem + "\nA. 1 N\nB. 9 N\nC. 20 N\nD. 25 N\nChoose the best answer."
    )

    assert blocked
    assert score == 1.0


def test_normalization_preserves_mathematical_meaning() -> None:
    assert core.normalize_text("x = 5") != core.normalize_text("x = -5")
    assert core.normalize_text("1/2") != core.normalize_text("12")
    assert core.normalize_text("3.50") != core.normalize_text("350")


def test_normalization_canonicalizes_equivalent_math_notation() -> None:
    assert core.normalize_text("x²") == core.normalize_text("x^2")
    assert core.normalize_text("½") == core.normalize_text("1/2")
    assert core.normalize_text("√16") == core.normalize_text("sqrt(16)")
    holdouts = core.HoldoutIndex(["Solve x² + ½ = √16."])
    assert holdouts.compare("Solve x^2 + 1/2 = sqrt(16).")[0] is True


def test_normalization_canonicalizes_grouped_numbers_without_erasing_decimals() -> None:
    assert core.normalize_text("₦18,000") == core.normalize_text("₦18000")
    assert core.normalize_text("18 000") == core.normalize_text("18000")
    assert core.normalize_text("1,000.50") == core.normalize_text("1000.50")
    assert core.normalize_text("1\u202f000.50") == core.normalize_text("1000.50")
    assert core.normalize_text("Final answer: 845,640.") == core.normalize_text(
        "Final answer: 845640."
    )
    assert core.normalize_text("Final answer: 1,000.50.") == core.normalize_text(
        "Final answer: 1000.50."
    )
    assert core._contains_token_sequence(
        core.normalize_text("Final answer: 845,640."), core.normalize_text("845,640")
    )
    assert core.normalize_text("18 00") != core.normalize_text("1800")
    assert core.normalize_text("18,00.") != core.normalize_text("1800.")
    assert core.normalize_text("1,000.50") != core.normalize_text("100050")
    assert core.normalize_text("1,000.5x") != core.normalize_text("1000.5x")


@pytest.mark.parametrize("index", range(720))
def test_local_generator_is_schema_valid_and_recomputable(index: int) -> None:
    holdouts = core.HoldoutIndex([])
    record = generators.generate_local_example(
        index, seed=3407, holdouts=holdouts, source_revision="sha256:" + "0" * 64
    )

    assert record is not None
    assert generators.verify_local_record(record)
    assert not core.validate_record(record)
    schema = json.loads(
        (
            core.repository_root() / "model-development/finetune/muta_dataset_v2/schema.json"
        ).read_text()
    )
    Draft202012Validator(schema).validate(record)
    assert record["verification"]["training_eligible"] is True


def test_local_generator_is_deterministic() -> None:
    holdouts = core.HoldoutIndex([])
    first = generators.generate_local_example(
        12_345, seed=3407, holdouts=holdouts, source_revision="sha256:" + "a" * 64
    )
    second = generators.generate_local_example(
        12_345, seed=3407, holdouts=holdouts, source_revision="sha256:" + "a" * 64
    )

    assert first == second


def test_socratic_targets_stop_before_the_answer() -> None:
    index = len(generators.GENERATORS) * 8
    record = generators.generate_local_example(
        index,
        seed=3407,
        holdouts=core.HoldoutIndex([]),
        source_revision="sha256:" + "a" * 64,
    )

    assert record is not None
    assert record["pedagogy"] == "socratic_hint"
    assert "final answer" not in record["completion"].casefold()
    assert "Your turn:" in record["completion"]
    assert not core.validate_record(record)


def test_socratic_scaffolds_are_formula_specific_and_answer_safe() -> None:
    formula_ids = {
        generator(index, 3407).formula_id for index, generator in enumerate(generators.GENERATORS)
    }
    assert set(generators.SOCRATIC_SCAFFOLDS) == formula_ids
    completions = set()
    for index, generator in enumerate(generators.GENERATORS):
        problem = generator(index, 3407)
        _, completion, response_format = generators._render(problem, "socratic_hint")
        completions.add(completion)
        assert response_format == "socratic"
        assert "final answer" not in completion.casefold()
        assert not core._contains_token_sequence(
            core.normalize_text(completion), core.normalize_text(problem.answer)
        )
        assert completion.count("Guiding question:") == 1
        assert completion.count("Hint:") == 1
        assert completion.count("Your turn:") == 1
    assert len(completions) == len(generators.GENERATORS)

    varied = {
        generators._render(
            generators.GENERATORS[index % len(generators.GENERATORS)](index, 3407),
            "socratic_hint",
        )[1]
        for index in range(3000)
    }
    assert len(varied) >= 1000


def test_practice_marking_scheme_is_honest_and_does_not_double_check_prefix() -> None:
    problem = generators._simultaneous(3, 3407)
    prompt, completion, _ = generators._render(problem, "exam_marking_scheme")

    assert "not an official examiner marking scheme" in prompt
    assert "M1 (method):" in completion
    assert "A1 (accuracy working):" in completion
    assert "A2 (reported answer):" in completion
    assert "Check: Check:" not in completion


def test_validator_rejects_forged_identity_provenance_and_answer() -> None:
    record = generators.generate_local_example(
        0,
        seed=3407,
        holdouts=core.HoldoutIndex([]),
        source_revision="sha256:" + "a" * 64,
    )
    assert record is not None

    forged_id = deepcopy(record)
    forged_id["id"] = "muta2_" + "0" * 24
    assert any("record id" in error for error in core.validate_record(forged_id))

    forged_hash = deepcopy(record)
    forged_hash["contamination"]["normalized_prompt_sha256"] = "0" * 64
    assert any("prompt hash" in error for error in core.validate_record(forged_hash))

    forged_task_hash = deepcopy(record)
    forged_task_hash["contamination"]["source_task_sha256"] = "not-a-hash"
    forged_task_hash["id"] = core.record_id_for(forged_task_hash)
    assert any("source-task hash" in error for error in core.validate_record(forged_task_hash))

    forged_revision = deepcopy(record)
    forged_revision["provenance"]["source_revision"] = "garbage"
    forged_revision["id"] = core.record_id_for(forged_revision)
    assert any("source revision" in error for error in core.validate_record(forged_revision))

    forged_split = deepcopy(record)
    forged_split["provenance"]["source_split"] = "test"
    forged_split["id"] = core.record_id_for(forged_split)
    assert any("source split" in error for error in core.validate_record(forged_split))

    forged_cluster = deepcopy(record)
    forged_cluster["provenance"]["semantic_cluster_id"] = "formula:forged"
    forged_cluster["id"] = core.record_id_for(forged_cluster)
    assert any("semantic cluster" in error for error in core.validate_record(forged_cluster))

    forged_status = deepcopy(record)
    forged_status["verification"]["status"] = "human_reviewed"
    assert any("verification status" in error for error in core.validate_record(forged_status))

    forged_eligibility = deepcopy(record)
    forged_eligibility["verification"]["training_eligible"] = False
    assert any(
        "training eligibility" in error for error in core.validate_record(forged_eligibility)
    )

    forged_synthetic = deepcopy(record)
    forged_synthetic["provenance"]["synthetic"] = False
    assert any("synthetic flag" in error for error in core.validate_record(forged_synthetic))

    forged_answer = deepcopy(record)
    old_answer = forged_answer["answer"]
    value = int(old_answer.split("=")[1])
    forged = f"x = {-value if value else 1}"
    forged_answer["answer"] = forged
    forged_answer["completion"] = forged_answer["completion"].replace(old_answer, forged)
    forged_answer["messages"][1]["content"] = forged_answer["completion"]
    forged_answer["verification"]["expected"] = forged
    forged_answer["verification"]["observed"] = forged
    forged_answer["id"] = core.record_id_for(forged_answer)
    assert any("does not recompute" in error for error in core.validate_record(forged_answer))

    forged_explanation = deepcopy(record)
    forged_explanation["completion"] += "\nA fabricated extra step."
    forged_explanation["messages"][1]["content"] = forged_explanation["completion"]
    forged_explanation["id"] = core.record_id_for(forged_explanation)
    assert any("does not recompute" in error for error in core.validate_record(forged_explanation))


def test_validator_rechecks_holdout_instead_of_trusting_flag() -> None:
    holdouts = core.HoldoutIndex(["Solve 3x + 2 = 11."])
    record = generators.generate_local_example(
        2,
        seed=3407,
        holdouts=core.HoldoutIndex([]),
        source_revision="sha256:" + "a" * 64,
    )
    assert record is not None
    record["prompt"] = "Solve 3x + 2 = 11."
    record["messages"][0]["content"] = record["prompt"]
    record["contamination"]["normalized_prompt_sha256"] = core.normalized_sha256(record["prompt"])
    record["contamination"]["max_holdout_5gram_similarity"] = 0.0
    record["id"] = core.record_id_for(record)

    errors = core.validate_record(record, holdouts=holdouts)

    assert any("sealed holdout" in error for error in errors)
    assert any("similarity" in error for error in errors)


def test_token_counter_metadata_is_exact_and_tamper_evident() -> None:
    class FakeTokenizer:
        chat_template = "{{ messages }}"

        @staticmethod
        def apply_chat_template(messages, *, tokenize, add_generation_prompt):
            assert tokenize is True
            assert add_generation_prompt is False
            return list(range(sum(len(message["content"].split()) for message in messages) + 3))

    counter = object.__new__(tokenization.QwenTokenCounter)
    counter.tokenizer_id = tokenization.TOKENIZER_ID
    counter.revision = tokenization.TOKENIZER_REVISION
    counter.max_sequence_tokens = 1024
    counter.tokenizer = FakeTokenizer()
    counter.chat_template_sha256 = "b" * 64
    record = {"id": "test", "messages": [{"role": "user", "content": "two words"}]}

    counter.annotate(record)

    assert record["tokenization"]["sequence_tokens"] == 5
    assert counter.validate(record)
    record["tokenization"]["sequence_tokens"] += 1
    assert not counter.validate(record)


def test_validator_rejects_unpinned_tokenizer_metadata() -> None:
    record = generators.generate_local_example(
        0,
        seed=3407,
        holdouts=core.HoldoutIndex([]),
        source_revision="sha256:" + "a" * 64,
    )
    assert record is not None
    record["tokenization"] = {
        "tokenizer_id": "forged/tokenizer",
        "tokenizer_revision": "0" * 40,
        "chat_template_sha256": "0" * 64,
        "sequence_tokens": 10,
        "max_sequence_tokens": 1024,
        "within_limit": True,
    }

    errors = core.validate_record(record)

    assert any("tokenizer id" in error for error in errors)
    assert any("tokenizer revision" in error for error in errors)
    assert any("chat template hash" in error for error in errors)


def test_cluster_split_never_separates_semantic_near_clones() -> None:
    first = generators.generate_local_example(
        0,
        seed=3407,
        holdouts=core.HoldoutIndex([]),
        source_revision="sha256:" + "a" * 64,
    )
    second = generators.generate_local_example(
        len(generators.GENERATORS) * len(generators.PEDAGOGIES),
        seed=3407,
        holdouts=core.HoldoutIndex([]),
        source_revision="sha256:" + "a" * 64,
    )
    assert first is not None and second is not None
    assert first["provenance"]["semantic_cluster_id"] == second["provenance"]["semantic_cluster_id"]
    assert builder._deterministic_split(first, 0.5) == builder._deterministic_split(second, 0.5)
    assert builder._deterministic_split(first, 0.5) == "train"


@pytest.mark.parametrize("source_id", ["qasc", "gsm8k", "muta_verified_stem_v2"])
def test_singleton_anchor_and_scarce_local_skills_are_not_called_template_ood(
    source_id: str,
) -> None:
    record = {
        "provenance": {
            "source_id": source_id,
            "semantic_cluster_id": "row:one"
            if source_id != "muta_verified_stem_v2"
            else "formula:density",
        }
    }
    assert builder._deterministic_split(record, 0.49) == "train"


def test_misconception_answers_are_not_actual_answers() -> None:
    assert len(generators.GENERATORS) == 30
    assert {generator.__name__ for generator in generators.QUARANTINED_GENERATORS} == {
        "_profit",
        "_average_speed",
        "_ratio",
        "_probability",
        "_interest",
    }
    assert not set(generators.GENERATORS) & set(generators.QUARANTINED_GENERATORS)
    assert len({generator.__name__ for generator in generators.GENERATORS}) == len(
        generators.GENERATORS
    )
    for index in range(1400):
        problem = generators.GENERATORS[index % len(generators.GENERATORS)](index, 3407)
        assert problem.wrong_answer != problem.answer
        assert problem.misconception_type
        assert problem.steps and all(step.strip() for step in problem.steps)
        assert problem.self_check.strip()


def test_sealed_numeric_cores_are_structurally_blocked() -> None:
    pythagoras = generators._pythagoras(0, 3407)
    pythagoras = replace(pythagoras, inputs={**pythagoras.inputs, "first_leg": 8, "second_leg": 6})
    assert generators._matches_sealed_numeric_core(pythagoras)

    ohm = generators._ohm(0, 3407)
    ohm = replace(ohm, inputs={**ohm.inputs, "current": 2, "resistance": 3})
    assert generators._matches_sealed_numeric_core(ohm)

    sequence = generators._sequence(0, 3407)
    sequence = replace(sequence, inputs={**sequence.inputs, "first": 5, "difference": 3})
    assert generators._matches_sealed_numeric_core(sequence)

    linear = generators._linear(0, 3407)
    linear = replace(
        linear,
        inputs={**linear.inputs, "coefficient": 3, "offset": 5, "rhs": 20},
    )
    assert generators._matches_sealed_numeric_core(linear)


def test_misconception_diagnosis_matches_constructed_wrong_attempt() -> None:
    for index in range(2000):
        problem = generators.GENERATORS[index % len(generators.GENERATORS)](index, 3407)
        if problem.formula_id == "linear_equation":
            assert problem.misconception_type == "coefficient_not_divided"
            assert problem.wrong_answer == f"x = {problem.inputs['rhs'] - problem.inputs['offset']}"
        elif problem.formula_id == "force":
            assert problem.misconception_type == "added_instead_of_multiplied"
            assert problem.wrong_answer == (
                f"{problem.inputs['mass'] + problem.inputs['acceleration']} N"
            )
        elif problem.formula_id == "simultaneous_equations":
            values = problem.answer.replace("x = ", "").replace("y = ", "").split(", ")
            assert values[0] != values[1]
            assert problem.misconception_type == "variables_swapped"
            assert problem.wrong_answer == f"x = {values[1]}, y = {values[0]}"


def test_science_generator_ranges_and_requested_precision_are_plausible() -> None:
    seen_subjects = set()
    for index in range(3500):
        problem = generators.GENERATORS[index % len(generators.GENERATORS)](index, 3407)
        seen_subjects.add(problem.subject)
        if problem.formula_id == "moles":
            mass = generators.Fraction(
                problem.inputs["mass_numerator"], problem.inputs["mass_denominator"]
            )
            assert mass <= 2500
        elif problem.formula_id == "concentration":
            concentration = generators.Fraction(
                problem.inputs["moles_numerator"], problem.inputs["moles_denominator"]
            ) / generators.Fraction(problem.inputs["volume_cm3"], 1000)
            assert 0 < concentration <= 5
        elif problem.formula_id == "dilution":
            assert 1 <= problem.inputs["initial_concentration"] <= 5
            assert problem.answer.split()[0].count(".") == 1
            assert len(problem.answer.split()[0].split(".")[1]) == 2
        elif problem.formula_id == "pulse_rate":
            rate = generators.Fraction(problem.inputs["beats"] * 60, problem.inputs["seconds"])
            assert 48 <= rate <= 140
        elif problem.formula_id == "energy_efficiency":
            efficiency = generators.Fraction(
                problem.inputs["useful_energy"] * 100, problem.inputs["input_energy"]
            )
            assert 20 <= efficiency <= 90
        elif problem.formula_id == "magnification":
            assert 1 <= problem.inputs["actual"] <= 250
            assert "measured" in problem.problem or "feature" in problem.problem
    assert seen_subjects == {
        "mathematics",
        "physics",
        "chemistry",
        "biology",
        "integrated_science",
    }


def test_concentration_visible_operands_are_exact_across_full_parameter_grid() -> None:
    for concentration_tenths in range(1, 51):
        concentration = generators.Fraction(concentration_tenths, 10)
        for volume_cm3 in range(50, 2050, 50):
            exact_moles = concentration * volume_cm3 / 1000
            rendered_moles = generators._fraction(exact_moles, 3)
            assert generators.Fraction(rendered_moles) == exact_moles
            visible_answer = generators.Fraction(rendered_moles) / generators.Fraction(
                volume_cm3, 1000
            )
            assert visible_answer == concentration

    for index in range(20_000):
        assert generators._visible_semantics_valid(generators._concentration(index, 3407))


def test_dilution_uses_approximation_only_for_rounded_results() -> None:
    for initial_concentration in range(1, 6):
        for multiplier in (2, 3, 4, 5, 6, 8, 10):
            exact = generators.Fraction(initial_concentration, multiplier)
            reported = generators._fixed(exact, 2)
            expected_relation = "=" if generators.Fraction(reported) == exact else "≈"
            if expected_relation == "=":
                assert generators.Fraction(reported) == exact
            else:
                assert generators.Fraction(reported) != exact

    for index in range(20_000):
        assert generators._visible_semantics_valid(generators._dilution(index, 3407))


def test_visible_semantics_gate_rejects_precision_sensitive_field_mutations() -> None:
    concentration = generators._concentration(17, 3407)
    concentration_mutations = (
        replace(concentration, problem=concentration.problem.replace(" mol", "0 mol", 1)),
        replace(concentration, answer="999 mol/dm³"),
        replace(concentration, steps=("mutated", concentration.steps[1])),
        replace(concentration, self_check="mutated"),
        replace(concentration, wrong_answer="999 mol/dm³"),
    )
    assert generators._visible_semantics_valid(concentration)
    assert not any(generators._visible_semantics_valid(row) for row in concentration_mutations)

    dilution = generators._dilution(17, 3407)
    if " ≈ " in dilution.steps[1]:
        wrong_relation_step = dilution.steps[1].replace(" ≈ ", " = ")
    else:
        wrong_relation_step = dilution.steps[1].replace(
            f" = {dilution.answer}.", f" ≈ {dilution.answer}."
        )
    dilution_mutations = (
        replace(dilution, problem=dilution.problem + " changed"),
        replace(dilution, answer="999 mol/dm³"),
        replace(dilution, steps=("mutated", dilution.steps[1])),
        replace(dilution, steps=(dilution.steps[0], wrong_relation_step)),
        replace(dilution, self_check="mutated"),
        replace(dilution, wrong_answer="999 mol/dm³"),
    )
    assert generators._visible_semantics_valid(dilution)
    assert not any(generators._visible_semantics_valid(row) for row in dilution_mutations)


def test_school_rounding_and_ordinals() -> None:
    assert generators._percent(generators.Fraction(125, 4)) == "31.3%"
    assert generators._ordinal(11) == "11th"
    assert generators._ordinal(22) == "22nd"
    assert generators._ordinal(33) == "33rd"


def test_adapters_remove_hidden_reasoning_and_parse_answers() -> None:
    assert adapters._extract_mcq_answer("Reason. The Best Answer is c.") == "C"
    assert adapters._extract_mcq_answer("Final answer: **D**") == "D"
    assert adapters._clean_reasoning("<think>secret\nwork</think>\nAnswer") == "Answer"
    assert adapters._verify_gsm8k_annotations(
        "Half is <<48/2=24>>24; total is <<48+24=72>>72.\n#### 72", "72"
    )
    assert not adapters._verify_gsm8k_annotations(
        "Half is <<48/2=25>>25; total is <<48+25=73>>73.\n#### 73", "73"
    )


def _templategsm_reasons(answer: str, solution: str) -> tuple[str, ...]:
    return adapters._templategsm_filter_reasons(
        prompt="A static-filter fixture question.",
        answer=answer,
        solution=solution,
        solution_code="result = 1",
    )


def _templategsm_snapshot_fixture(monkeypatch, tmp_path):
    root = tmp_path / "templategsm-snapshot"
    first = root / "data" / "1k" / "0000-0999"
    second = root / "data" / "1k" / "1000-1999"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    readme = root / "README.md"
    readme.write_bytes(b"pinned TemplateGSM fixture\n")
    ids = (0, 2, 1000, 1002)
    # Create in deliberately non-canonical order. Validation must ignore
    # directory iteration order and use the documented lexicographic paths.
    for template_id in reversed(ids):
        directory = first if template_id < 1000 else second
        (directory / f"templategsm-train-problems-{template_id}.jsonl").write_bytes(
            (json.dumps({"template_id": template_id}) + "\n").encode()
        )
    files = [
        *sorted(first.glob("templategsm-train-problems-*.jsonl")),
        *sorted(second.glob("templategsm-train-problems-*.jsonl")),
    ]
    inventory = hashlib.sha256()
    total_bytes = 0
    for path in files:
        size = path.stat().st_size
        total_bytes += size
        relative = path.relative_to(root).as_posix()
        inventory.update(
            f"{relative}\t{size}\t{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode()
        )
    monkeypatch.setattr(adapters, "TEMPLATEGSM_SNAPSHOT_TEMPLATE_IDS", frozenset(ids))
    monkeypatch.setattr(adapters, "TEMPLATEGSM_SNAPSHOT_FILE_COUNT", len(files))
    monkeypatch.setattr(adapters, "TEMPLATEGSM_SNAPSHOT_TOTAL_BYTES", total_bytes)
    monkeypatch.setattr(adapters, "TEMPLATEGSM_SNAPSHOT_INVENTORY_SHA256", inventory.hexdigest())
    monkeypatch.setattr(
        adapters,
        "TEMPLATEGSM_SNAPSHOT_README_SHA256",
        hashlib.sha256(readme.read_bytes()).hexdigest(),
    )
    return root, files


def test_templategsm_snapshot_validates_exact_inventory_and_canonical_order(
    monkeypatch, tmp_path
) -> None:
    root, expected_files = _templategsm_snapshot_fixture(monkeypatch, tmp_path)

    snapshot = adapters.validate_templategsm_snapshot(root)

    assert snapshot.data_files == tuple(path.resolve() for path in expected_files)
    assert snapshot.receipt == {
        "resolved_path": str(root.resolve()),
        "file_count": 4,
        "total_bytes": sum(path.stat().st_size for path in expected_files),
        "inventory_sha256": adapters.TEMPLATEGSM_SNAPSHOT_INVENTORY_SHA256,
        "readme_sha256": adapters.TEMPLATEGSM_SNAPSHOT_README_SHA256,
        "source_revision": adapters.TEMPLATEGSM_SNAPSHOT_REVISION,
        "configuration": adapters.TEMPLATEGSM_CONFIG,
        "inventory_order": (
            "lexicographic relative-path order within data/1k/0000-0999, then data/1k/1000-1999"
        ),
        "row_materialization_network_used": False,
    }


@pytest.mark.parametrize("mutation", ["tamper", "readme", "missing", "extra", "wrong_range"])
def test_templategsm_snapshot_rejects_filesystem_drift(monkeypatch, tmp_path, mutation) -> None:
    root, files = _templategsm_snapshot_fixture(monkeypatch, tmp_path)
    if mutation == "tamper":
        original = files[0].read_bytes()
        files[0].write_bytes(b"X" + original[1:])
        expected = "inventory hash mismatch"
    elif mutation == "readme":
        (root / "README.md").write_text("tampered\n")
        expected = "README hash mismatch"
    elif mutation == "missing":
        files[0].unlink()
        expected = "template ID set mismatch"
    elif mutation == "extra":
        (files[0].parent / "templategsm-train-problems-3.jsonl").write_text("{}\n")
        expected = "template ID set mismatch"
    else:
        misplaced = root / "data" / "1k" / "0000-0999" / files[-1].name
        files[-1].replace(misplaced)
        expected = "outside path range"

    with pytest.raises(ValueError, match=expected):
        adapters.validate_templategsm_snapshot(root)


def test_templategsm_snapshot_rejects_internal_file_symlink(monkeypatch, tmp_path) -> None:
    root, files = _templategsm_snapshot_fixture(monkeypatch, tmp_path)
    link = files[0].parent / "templategsm-train-problems-3.jsonl"
    link.symlink_to(files[0])

    with pytest.raises(ValueError, match="unexpected TemplateGSM snapshot entry"):
        adapters.validate_templategsm_snapshot(root)


def test_templategsm_snapshot_rejects_range_directory_symlink(monkeypatch, tmp_path) -> None:
    root, _ = _templategsm_snapshot_fixture(monkeypatch, tmp_path)
    first = root / "data" / "1k" / "0000-0999"
    backing = tmp_path / "range-backing"
    first.replace(backing)
    first.symlink_to(backing, target_is_directory=True)

    with pytest.raises(FileNotFoundError, match="path range.*symlink"):
        adapters.validate_templategsm_snapshot(root)


def test_templategsm_snapshot_stream_uses_local_json_files_in_receipted_order(
    monkeypatch, tmp_path
) -> None:
    root, expected_files = _templategsm_snapshot_fixture(monkeypatch, tmp_path)
    snapshot = adapters.validate_templategsm_snapshot(root)
    calls = []

    class FakeDataset(list):
        def shuffle(self, **kwargs):
            calls.append(("shuffle", kwargs))
            return self

    def fake_load_dataset(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeDataset()

    monkeypatch.setattr(adapters, "_load_dataset", fake_load_dataset)
    monkeypatch.setattr(
        adapters,
        "_load_templategsm_filter_audit",
        lambda: (frozenset(), "a" * 64),
    )

    assert (
        list(
            adapters.iter_templategsm(
                holdouts=core.HoldoutIndex([]),
                limit=1,
                seed=3407,
                split="train",
                per_template_cap=400,
                snapshot=snapshot,
            )
        )
        == []
    )
    args, kwargs = calls[0]
    assert args == ("json",)
    assert kwargs == {
        "data_files": [str(path.resolve()) for path in expected_files],
        "split": "train",
        "streaming": True,
    }
    assert calls[1] == ("shuffle", {"seed": 3407, "buffer_size": 20_000})


def test_templategsm_filter_rejects_exact_arithmetic_contradiction() -> None:
    reasons = _templategsm_reasons(
        "120",
        "Half of 120 is shown as 50% x 120 = 80. The reported total is 120.",
    )

    assert "arithmetic_contradiction" in reasons


def test_templategsm_filter_rejects_unsupported_target() -> None:
    reasons = _templategsm_reasons(
        "757",
        "The total is 104188 and the count is 122, so 104188 / 122 = 854.",
    )

    assert "target_unsupported" in reasons


def test_templategsm_filter_rejects_float_artifact_and_noncanonical_result() -> None:
    float_reasons = _templategsm_reasons(
        "355",
        "After using 82.83333333333333 units, the exact reported result is 355.",
    )
    result_reasons = _templategsm_reasons(
        "28.000000000000004",
        "The reimbursement is 0.28 * 100 = 28.0.",
    )

    assert "solution_float_artifact" in float_reasons
    assert "result_noncanonical" in result_reasons


def test_templategsm_filter_honours_explicit_approximation_escape() -> None:
    reasons = _templategsm_reasons(
        "0.33",
        "Approximately, 1 / 3 = 0.33, so the reported result is 0.33.",
    )

    assert "arithmetic_contradiction" not in reasons
    assert reasons == ()


def test_templategsm_adapter_checker_matches_archived_reference_on_regression_cases(
    monkeypatch,
) -> None:
    """Keep the runtime copy aligned with the exact checker used for the 2M audit."""

    monkeypatch.setitem(
        sys.modules,
        "datasets",
        SimpleNamespace(load_dataset=lambda *args, **kwargs: None),
    )
    spec = importlib.util.spec_from_file_location(
        "templategsm_static_prefilter_v1_reference",
        adapters.TEMPLATEGSM_REFERENCE_CHECKER_PATH,
    )
    assert spec is not None and spec.loader is not None
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)

    fixtures = (
        ("5", "Use exact arithmetic: 2 + 3 = 5."),
        ("5", "Use exact arithmetic: 2 + 3 = 8. Final answer: 5."),
        ("5", "No supported target is stated here."),
        ("0.33", "Approximately, 1 / 3 = 0.33, so the result is 0.33."),
        ("5", "The floating output was 5.0000000123, so the result is 5."),
        ("1e3", "The result is 1e3."),
    )
    for answer, solution in fixtures:
        row = {
            "problem": "What is the result?",
            "result": answer,
            "solution_wocode": solution,
            "solution_code": "result = 5",
        }
        reference_reasons = reference.row_flags(row, Counter())
        runtime_reasons = adapters._templategsm_filter_reasons(
            prompt=row["problem"],
            answer=adapters._normalise_number(answer),
            solution=adapters._clean_reasoning(solution),
            solution_code=row["solution_code"],
        )
        assert list(runtime_reasons) == reference_reasons


def test_templategsm_filter_audit_is_hash_revision_and_config_bound(tmp_path) -> None:
    assert {
        "templategsm_filter_audit.json",
        "templategsm_full_audit.json",
        "templategsm_static_prefilter_v1.py",
    } <= set(builder.PROVENANCE_FILES)
    identifiers, observed_hash = adapters._load_templategsm_filter_audit()
    assert len(identifiers) == 362
    assert observed_hash == adapters.TEMPLATEGSM_FILTER_AUDIT_SHA256
    audit_payload = json.loads(adapters.TEMPLATEGSM_FILTER_AUDIT_PATH.read_text())
    for artifact in ("full_scan_report", "reference_checker"):
        receipt = audit_payload[artifact]
        artifact_path = core.repository_root() / receipt["path"]
        assert artifact_path.is_file()
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == receipt["sha256"]

    raw = adapters.TEMPLATEGSM_FILTER_AUDIT_PATH.read_bytes()
    tampered = tmp_path / "tampered.json"
    tampered.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        adapters._load_templategsm_filter_audit(tampered)

    for field, value in (
        ("source_revision", "wrong-revision"),
        ("configuration", "templategsm-1000-1k"),
        ("checker_version", "templategsm-static-prefilter-v0"),
    ):
        payload = json.loads(raw)
        payload[field] = value
        changed = tmp_path / f"wrong-{field}.json"
        changed_raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
        changed.write_bytes(changed_raw)
        with pytest.raises(ValueError, match=field):
            adapters._load_templategsm_filter_audit(
                changed,
                expected_sha256=hashlib.sha256(changed_raw).hexdigest(),
            )

    for receipt_name in ("full_scan_report", "reference_checker"):
        payload = json.loads(raw)
        payload[receipt_name]["sha256"] = "0" * 64
        changed = tmp_path / f"wrong-{receipt_name}-receipt.json"
        changed_raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
        changed.write_bytes(changed_raw)
        with pytest.raises(ValueError, match=rf"{receipt_name} SHA-256 mismatch"):
            adapters._load_templategsm_filter_audit(
                changed,
                expected_sha256=hashlib.sha256(changed_raw).hexdigest(),
            )

    tampered_checker = tmp_path / "tampered-checker.py"
    tampered_checker.write_bytes(adapters.TEMPLATEGSM_REFERENCE_CHECKER_PATH.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="reference_checker SHA-256 mismatch"):
        adapters._load_templategsm_filter_audit(reference_checker_path=tampered_checker)

    tampered_full_audit = tmp_path / "tampered-full-audit.json"
    tampered_full_audit.write_bytes(adapters.TEMPLATEGSM_FULL_AUDIT_PATH.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="full_scan_report SHA-256 mismatch"):
        adapters._load_templategsm_filter_audit(full_audit_path=tampered_full_audit)

    changed_full_payload = json.loads(adapters.TEMPLATEGSM_FULL_AUDIT_PATH.read_bytes())
    changed_full_payload["counts"]["accepted_rows"] += 1
    changed_full_raw = (json.dumps(changed_full_payload, sort_keys=True) + "\n").encode()
    changed_full = tmp_path / "self-consistent-but-different-full-audit.json"
    changed_full.write_bytes(changed_full_raw)
    changed_compact_payload = json.loads(raw)
    changed_compact_payload["full_scan_report"]["sha256"] = hashlib.sha256(
        changed_full_raw
    ).hexdigest()
    changed_compact_raw = (json.dumps(changed_compact_payload, sort_keys=True) + "\n").encode()
    changed_compact = tmp_path / "self-consistent-but-different-compact-audit.json"
    changed_compact.write_bytes(changed_compact_raw)
    with pytest.raises(ValueError, match="full audit counts differ"):
        adapters._load_templategsm_filter_audit(
            changed_compact,
            expected_sha256=hashlib.sha256(changed_compact_raw).hexdigest(),
            full_audit_path=changed_full,
        )


def test_templategsm_stream_quarantines_entire_failed_template(monkeypatch) -> None:
    class FakeDataset(list):
        def shuffle(self, **kwargs):
            del kwargs
            return self

    def row(template_id: int, problem_id: int) -> dict[str, object]:
        return {
            "problem": f"What is 2 + 3? Fixture {problem_id}.",
            "solution_code": "result = 2 + 3",
            "result": "5",
            "solution_wocode": "Use exact arithmetic: 2 + 3 = 5.",
            "template_id": template_id,
            "problem_id": problem_id,
        }

    monkeypatch.setattr(
        adapters,
        "_load_dataset",
        lambda *args, **kwargs: FakeDataset([row(25, 0), row(0, 1)]),
    )
    monkeypatch.setattr(
        adapters,
        "_load_templategsm_filter_audit",
        lambda: (frozenset({"25"}), "a" * 64),
    )

    records = list(
        adapters.iter_templategsm(
            holdouts=core.HoldoutIndex([]),
            limit=2,
            seed=3407,
            split="train",
            per_template_cap=400,
        )
    )

    assert len(records) == 1
    assert records[0]["verification"]["template_id"] == "0"
    assert records[0]["verification"]["static_filter"] == {
        "checker_version": adapters.TEMPLATEGSM_CHECKER_VERSION,
        "audit_sha256": "a" * 64,
        "configuration": adapters.TEMPLATEGSM_CONFIG,
        "template_quarantined": False,
        "row_filter_passed": True,
        "solution_code_executed": False,
    }
    assert core.validate_record(records[0], holdouts=core.HoldoutIndex([])) == []


@pytest.mark.parametrize("cap", [0, -1, 401])
def test_templategsm_stream_rejects_caps_outside_audited_range(cap: int) -> None:
    with pytest.raises(ValueError, match="audited maximum 400"):
        next(
            adapters.iter_templategsm(
                holdouts=core.HoldoutIndex([]),
                limit=1,
                seed=3407,
                split="train",
                per_template_cap=cap,
            )
        )


def test_gsm8k_grouped_final_answer_before_period_is_validator_safe(monkeypatch) -> None:
    class FakeDataset(list):
        def shuffle(self, **kwargs):
            del kwargs
            return self

    monkeypatch.setattr(
        adapters,
        "_load_dataset",
        lambda *args, **kwargs: FakeDataset(
            [
                {
                    "question": "What is the computed total?",
                    "answer": "Compute <<845640=845640>>the total.\n#### 845,640",
                }
            ]
        ),
    )

    record = next(
        adapters.iter_gsm8k(holdouts=core.HoldoutIndex([]), limit=1, seed=3407, split="train")
    )

    assert record["answer"] == "845,640"
    assert record["completion"].endswith("Final answer: 845,640.")
    assert core.validate_record(record, holdouts=core.HoldoutIndex([])) == []


def test_deepmind_stream_rejects_rare_upstream_assertion_and_continues(
    monkeypatch, tmp_path
) -> None:
    calls = 0

    def flaky_module():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise AssertionError("upstream entropy sampler rejected this draw")
        return SimpleNamespace(question="What is 2 + 3?", answer="5")

    monkeypatch.setattr(
        adapters,
        "deepmind_modules",
        lambda checkout, *, difficulty: [("arithmetic__add_or_sub", flaky_module)],
    )
    monkeypatch.setattr(
        adapters,
        "_source",
        lambda source_id: {
            "revision": "427f45075f84b8b9774950196ad63867ca20ffb3",
            "license": "Apache-2.0",
        },
    )

    record = next(
        adapters.iter_deepmind_mathematics(
            checkout=tmp_path,
            holdouts=core.HoldoutIndex([]),
            limit=1,
            seed=3407,
            split="train",
        )
    )

    assert calls == 2
    assert record["answer"] == "5"
    assert record["provenance"]["source_split"] == "train-medium"


def test_source_registry_fails_closed_and_recipe_totals_match() -> None:
    package = core.repository_root() / "model-development/finetune/muta_dataset_v2"
    registry = json.loads((package / "source_registry.json").read_text())
    sources = {row["id"]: row for row in registry["sources"]}
    recipe = json.loads((package / "recipe.json").read_text())

    assert sum(recipe["warehouse_allocations"].values()) == 2_500_000
    assert sum(recipe["recommended_sft_allocations"].values()) == 300_000
    assert sources["waec_elearning"]["status"].startswith("prohibited")
    assert sources["cheetahwaec"]["status"].startswith("prohibited")
    assert sources["ai2_arc"]["status"] == "candidate_only"
    for source in sources.values():
        assert source["revision"]
        assert source["license"]
        assert source["license_url"]
        if source["status"].startswith("enabled"):
            assert source["license"] in registry["policy"]["allowed_licenses"]
            assert source["allowed_splits"]
            assert source["allowed_verification_statuses"]
            assert isinstance(source["warehouse_training_eligible"], bool)
            assert source["sft_approval_scope"] == (
                "native" if source["warehouse_training_eligible"] else "row_only"
            )
            assert isinstance(source["synthetic"], bool)


def test_manifest_verification_semantics_are_explicit_and_conservative() -> None:
    semantics = builder.SOURCE_VERIFICATION_SEMANTICS

    assert set(semantics) == {
        "muta_verified_stem_v2",
        "deepmind_mathematics",
        "template_gsm",
        "qasc",
        "gsm8k",
    }
    assert semantics["muta_verified_stem_v2"]["scope"] == (
        "full_record_regeneration_and_answer_recomputation"
    )
    assert semantics["muta_verified_stem_v2"]["independent_answer_rederivation"] is True
    assert semantics["deepmind_mathematics"]["scope"] == (
        "pinned_generator_self_emitted_problem_and_answer"
    )
    assert semantics["template_gsm"]["scope"] == (
        "pinned_static_prefilter_and_whole_template_quarantine"
    )
    assert semantics["qasc"]["scope"] == "publisher_answer_key_and_supporting_facts_only"
    assert semantics["gsm8k"]["scope"] == "calculator_annotation_recomputation_only"
    for source_id in ("deepmind_mathematics", "template_gsm", "qasc", "gsm8k"):
        assert semantics[source_id]["independent_answer_rederivation"] is False
        assert semantics[source_id]["semantic_correctness_assurance"] == (
            "not_independently_certified"
        )


@pytest.mark.parametrize(
    ("warehouse_split", "source_scope", "eligible", "expected"),
    [
        ("train", "native", True, "native_eligible_train"),
        ("train", "row_only", False, "audit_required_train"),
        ("train", "row_only", True, "audit_required_train"),
        ("template_holdout", "native", True, "non_train_holdout"),
        ("review", "native", True, "non_train_holdout"),
    ],
)
def test_training_disposition_is_exhaustive_and_conservative(
    warehouse_split: str, source_scope: str, eligible: bool, expected: str
) -> None:
    record = {
        "split": warehouse_split,
        "provenance": {"source_id": "fixture"},
        "verification": {"training_eligible": eligible},
    }
    registry = {"fixture": {"sft_approval_scope": source_scope}}

    assert builder._training_disposition_key(record, registry) == expected


def test_source_split_eligibility_matrix_keeps_all_three_dimensions() -> None:
    counts = Counter(
        {
            ("alpha", "train", "training_eligible"): 7,
            ("alpha", "template_holdout", "training_eligible"): 2,
            ("beta", "train", "audit_required"): 3,
        }
    )

    assert builder._source_split_eligibility_matrix(counts) == {
        "alpha": {
            "template_holdout": {"training_eligible": 2},
            "train": {"training_eligible": 7},
        },
        "beta": {"train": {"audit_required": 3}},
    }


def test_public_holdout_receipts_are_pinned_split_level_and_prompt_free(monkeypatch) -> None:
    monkeypatch.setattr(
        adapters,
        "_source",
        lambda source_id: {"revision": f"revision-{source_id}"},
    )

    def fake_load_dataset(repo, *args, **kwargs):
        config = args[0] if args else None
        identity = f"{repo}|{config}|{kwargs['split']}"
        return [
            {"question": f"SEALED TEXT A {identity}"},
            {"question": f"SEALED TEXT A {identity}  "},
            {"question": f"SEALED TEXT B {identity}"},
        ]

    monkeypatch.setattr(adapters, "_load_dataset", fake_load_dataset)

    prompts, receipts = adapters.public_evaluation_holdouts()

    assert len(receipts) == 25
    assert len(prompts) == 75
    assert all(receipt["raw_prompt_count"] == 3 for receipt in receipts)
    assert all(receipt["normalized_prompt_count"] == 2 for receipt in receipts)
    assert all(len(receipt["normalized_prompt_set_sha256"]) == 64 for receipt in receipts)
    assert "SEALED TEXT" not in json.dumps(receipts)
    gsm8k = next(receipt for receipt in receipts if receipt["source_id"] == "gsm8k")
    assert gsm8k == {
        "source_id": "gsm8k",
        "repo": "openai/gsm8k",
        "config": "main",
        "split": "test",
        "revision": "revision-gsm8k",
        "prompt_field": "question",
        "raw_prompt_count": 3,
        "normalized_prompt_count": 2,
        "normalized_prompt_set_sha256": core.HoldoutIndex(prompts[:3]).digest,
    }


def test_deepmind_build_requires_startup_hash_seed(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    args = builder.parse_args(
        [
            "--profile",
            "warehouse",
            "--include-public-holdouts",
            "--deepmind-checkout",
            str(tmp_path / "unused-checkout"),
            "--local-rows",
            "0",
            "--deepmind-rows",
            "1",
            "--templategsm-rows",
            "0",
            "--nemotron-rows",
            "0",
            "--anchor-rows",
            "0",
            "--output",
            str(tmp_path / "warehouse"),
        ]
    )

    with pytest.raises(RuntimeError, match="PYTHONHASHSEED=3407"):
        builder.build(args)


def test_oversized_anchor_request_fails_before_output_or_download(tmp_path) -> None:
    output = tmp_path / "oversized-anchors"
    args = builder.parse_args(
        [
            "--profile",
            "warehouse",
            "--include-public-holdouts",
            "--local-rows",
            "0",
            "--deepmind-rows",
            "0",
            "--templategsm-rows",
            "0",
            "--nemotron-rows",
            "0",
            "--anchor-rows",
            str(builder.MAX_BALANCED_ANCHOR_ROWS + 1),
            "--output",
            str(output),
        ]
    )

    with pytest.raises(ValueError, match="exceeds the balanced QASC/GSM8K"):
        builder.build(args)

    assert not output.exists()


def test_templategsm_warehouse_requires_snapshot_before_output_is_touched(tmp_path) -> None:
    output = tmp_path / "missing-templategsm-snapshot"
    args = builder.parse_args(
        [
            "--profile",
            "warehouse",
            "--include-public-holdouts",
            "--local-rows",
            "0",
            "--deepmind-rows",
            "0",
            "--templategsm-rows",
            "1",
            "--nemotron-rows",
            "0",
            "--anchor-rows",
            "0",
            "--output",
            str(output),
        ]
    )

    with pytest.raises(ValueError, match="--templategsm-snapshot is required"):
        builder.build(args)

    assert not output.exists()


def test_templategsm_preflight_does_not_write_existing_empty_output(tmp_path) -> None:
    output = tmp_path / "existing-empty-output"
    output.mkdir()
    args = builder.parse_args(
        [
            "--profile",
            "warehouse",
            "--include-public-holdouts",
            "--local-rows",
            "0",
            "--deepmind-rows",
            "0",
            "--templategsm-rows",
            "1",
            "--nemotron-rows",
            "0",
            "--anchor-rows",
            "0",
            "--output",
            str(output),
        ]
    )

    with pytest.raises(ValueError, match="--templategsm-snapshot is required"):
        builder.build(args)

    assert list(output.iterdir()) == []


def test_build_rejects_programmatic_invalid_profile_before_output(tmp_path) -> None:
    output = tmp_path / "invalid-profile"
    args = builder.parse_args(
        ["--output", str(output), "--local-rows", "1", "--tokenization", "skip"]
    )
    args.profile = "not-a-real-profile"

    with pytest.raises(ValueError, match="unsupported build profile"):
        builder.build(args)

    assert not output.exists()


def test_templategsm_warehouse_authenticates_snapshot_before_output_is_touched(
    monkeypatch, tmp_path
) -> None:
    snapshot_root, files = _templategsm_snapshot_fixture(monkeypatch, tmp_path)
    original = files[0].read_bytes()
    files[0].write_bytes(b"X" + original[1:])
    output = tmp_path / "tampered-templategsm-snapshot"
    args = builder.parse_args(
        [
            "--profile",
            "warehouse",
            "--include-public-holdouts",
            "--local-rows",
            "0",
            "--deepmind-rows",
            "0",
            "--templategsm-rows",
            "1",
            "--templategsm-snapshot",
            str(snapshot_root),
            "--nemotron-rows",
            "0",
            "--anchor-rows",
            "0",
            "--output",
            str(output),
        ]
    )

    with pytest.raises(ValueError, match="inventory hash mismatch"):
        builder.build(args)

    assert not output.exists()


def test_templategsm_warehouse_postflight_rejects_snapshot_changed_during_rows(
    monkeypatch, tmp_path
) -> None:
    snapshot_root, files = _templategsm_snapshot_fixture(monkeypatch, tmp_path)
    output = tmp_path / "snapshot-race"

    class FakeTokenCounter:
        tokenizer_id = "Qwen/Qwen2.5-1.5B-Instruct"
        revision = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
        chat_template_sha256 = "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"

        def __init__(self, *, max_sequence_tokens):
            self.max_sequence_tokens = max_sequence_tokens

        def annotate(self, record):
            record["tokenization"] = {
                "tokenizer_id": self.tokenizer_id,
                "tokenizer_revision": self.revision,
                "chat_template_sha256": self.chat_template_sha256,
                "sequence_tokens": 32,
                "max_sequence_tokens": self.max_sequence_tokens,
                "within_limit": True,
            }

    def mutating_streams(
        args, holdouts, allocations, recipe, local_source_revision, templategsm_snapshot
    ):
        del allocations, recipe, templategsm_snapshot
        original = files[0].read_bytes()
        files[0].write_bytes(b"X" + original[1:])
        files[0].write_bytes(original)
        record = generators.generate_local_example(
            0,
            seed=args.seed,
            holdouts=holdouts,
            source_revision=local_source_revision,
        )
        assert record is not None
        return [("template_gsm", 1, iter((record,)))]

    monkeypatch.setattr(builder, "QwenTokenCounter", FakeTokenCounter)
    monkeypatch.setattr(builder, "public_evaluation_holdouts", lambda: ([], []))
    monkeypatch.setattr(builder, "_source_streams", mutating_streams)
    args = builder.parse_args(
        [
            "--profile",
            "warehouse",
            "--include-public-holdouts",
            "--local-rows",
            "0",
            "--deepmind-rows",
            "0",
            "--templategsm-rows",
            "1",
            "--templategsm-snapshot",
            str(snapshot_root),
            "--nemotron-rows",
            "0",
            "--anchor-rows",
            "0",
            "--output",
            str(output),
        ]
    )

    with pytest.raises(RuntimeError, match="changed during row materialization"):
        builder.build(args)

    assert (output / "FAILED.json").is_file()
    assert not (output / "manifest.json").exists()


def test_templategsm_warehouse_manifest_receipts_local_snapshot(monkeypatch, tmp_path) -> None:
    snapshot_root, expected_files = _templategsm_snapshot_fixture(monkeypatch, tmp_path)
    output = tmp_path / "templategsm-warehouse"
    load_calls = []

    class FakeDataset(list):
        def shuffle(self, **kwargs):
            return self

    def fake_load_dataset(*args, **kwargs):
        load_calls.append((args, kwargs))
        return FakeDataset(
            [
                {
                    "problem": "What is 2 + 3?",
                    "solution_code": "result = 2 + 3",
                    "result": "5",
                    "solution_wocode": "Use exact arithmetic: 2 + 3 = 5.",
                    "template_id": 0,
                    "problem_id": 0,
                }
            ]
        )

    class FakeTokenCounter:
        tokenizer_id = "Qwen/Qwen2.5-1.5B-Instruct"
        revision = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
        chat_template_sha256 = "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"

        def __init__(self, *, max_sequence_tokens):
            self.max_sequence_tokens = max_sequence_tokens

        def annotate(self, record):
            record["tokenization"] = {
                "tokenizer_id": self.tokenizer_id,
                "tokenizer_revision": self.revision,
                "chat_template_sha256": self.chat_template_sha256,
                "sequence_tokens": 32,
                "max_sequence_tokens": self.max_sequence_tokens,
                "within_limit": True,
            }

    monkeypatch.setattr(adapters, "_load_dataset", fake_load_dataset)
    monkeypatch.setattr(builder, "QwenTokenCounter", FakeTokenCounter)
    monkeypatch.setattr(builder, "public_evaluation_holdouts", lambda: ([], []))
    args = builder.parse_args(
        [
            "--profile",
            "warehouse",
            "--include-public-holdouts",
            "--local-rows",
            "0",
            "--deepmind-rows",
            "0",
            "--templategsm-rows",
            "1",
            "--templategsm-snapshot",
            str(snapshot_root),
            "--nemotron-rows",
            "0",
            "--anchor-rows",
            "0",
            "--output",
            str(output),
        ]
    )

    manifest = builder.build(args)

    snapshot_receipt = manifest["inputs"]["templategsm_snapshot"]
    assert snapshot_receipt["resolved_path"] == str(snapshot_root.resolve())
    assert snapshot_receipt["file_count"] == len(expected_files)
    assert snapshot_receipt["inventory_sha256"] == (adapters.TEMPLATEGSM_SNAPSHOT_INVENTORY_SHA256)
    assert snapshot_receipt["readme_sha256"] == adapters.TEMPLATEGSM_SNAPSHOT_README_SHA256
    assert snapshot_receipt["source_revision"] == adapters.TEMPLATEGSM_SNAPSHOT_REVISION
    assert snapshot_receipt["configuration"] == adapters.TEMPLATEGSM_CONFIG
    assert snapshot_receipt["row_materialization_network_used"] is False
    assert load_calls[0] == (
        ("json",),
        {
            "data_files": [str(path.resolve()) for path in expected_files],
            "split": "train",
            "streaming": True,
        },
    )
    source_evidence = manifest["inputs"]["source_evidence_archive"]["files"]
    assert len(source_evidence) == 1
    assert source_evidence[0]["source_id"] == "template_gsm"
    assert source_evidence[0]["sha256"] == adapters.TEMPLATEGSM_SNAPSHOT_README_SHA256
    assert source_evidence[0]["locator"].startswith("local-snapshot:")


def test_anchor_capacity_constants_match_exhaustive_pinned_audit() -> None:
    # Exact emitted capacities under the pinned adapters and sealed holdouts;
    # the warehouse recipe requests 6,500 rows from each source.
    assert builder.QASC_TRAIN_CAPACITY == 8_126
    assert builder.GSM8K_TRAIN_CAPACITY == 6_999
    assert builder.MAX_BALANCED_ANCHOR_ROWS == 13_998


def test_deepmind_checkout_rejects_untracked_shadow_files(monkeypatch, tmp_path) -> None:
    checkout = tmp_path / "deepmind"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=checkout, check=True)
    (checkout / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "LICENSE"], cwd=checkout, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Muta Test",
            "-c",
            "user.email=muta-test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=checkout,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(adapters, "_source", lambda _: {"revision": revision})
    (checkout / "mathematics_dataset").mkdir()
    (checkout / "mathematics_dataset" / "shadow.py").write_text(
        "raise RuntimeError('shadowed')\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="modified or untracked"):
        adapters.validate_deepmind_checkout(checkout)


def test_review_build_is_unique_valid_and_hashed(tmp_path) -> None:
    output = tmp_path / "review"
    args = builder.parse_args(
        [
            "--profile",
            "review",
            "--local-rows",
            "180",
            "--shard-rows",
            "64",
            "--output",
            str(output),
            "--tokenization",
            "skip",
        ]
    )
    manifest = builder.build(args)

    rows = []
    for shard in manifest["shards"]:
        path = output / shard["path"]
        assert core.sha256_file(path) == shard["sha256"]
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    assert manifest["row_count"] == 180 == len(rows)
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({core.normalize_text(row["prompt"]) for row in rows}) == len(rows)
    assert Counter(row["split"] for row in rows) == {"review": 180}
    expected_revision = builder._content_revision(
        manifest["inputs"]["provenance_archive"],
        manifest["inputs"]["holdout_source_archive"],
    )
    assert {row["provenance"]["source_revision"] for row in rows} == {expected_revision}
    assert {row["provenance"]["source_split"] for row in rows} == {"generated"}
    assert manifest["sources"][0]["revision"] == expected_revision
    assert manifest["artifact_role"] == "candidate_warehouse"
    assert manifest["whole_artifact_training_authorized"] is False
    assert manifest["training_disposition_totals"] == {
        "native_eligible_train": 0,
        "audit_required_train": 0,
        "non_train_holdout": 180,
    }
    assert manifest["counts"]["source_warehouse_split_eligibility"] == {
        "muta_verified_stem_v2": {"review": {"training_eligible": 180}}
    }
    assert set(manifest["verification_semantics_by_source"]) == {"muta_verified_stem_v2"}
    assert manifest["counts"]["semantic_cluster_split_overlap_count"] == 0
    assert manifest["inputs"]["muta_license"]["sha256"] == core.sha256_file(
        core.repository_root() / "LICENSE"
    )
    assert manifest["holdouts"]["local_normalized_prompt_sha256_inventory"]
    assert manifest["holdouts"]["public_evaluation_source_receipts"] == []
    assert json.loads((output / "manifest.json").read_text())["row_count"] == 180
    assert not (output / "manifest.json.partial").exists()


def test_build_rejects_config_snapshot_that_differs_from_loaded_bytes(
    monkeypatch, tmp_path
) -> None:
    output = tmp_path / "config-race"

    def mismatched_archive(*, output_dir, root):
        del output_dir, root
        return {
            "files": [
                {
                    "path": "provenance-code/recipe.json",
                    "sha256": "0" * 64,
                }
            ],
            "receipts": {"sha256": "1" * 64},
        }

    monkeypatch.setattr(builder, "_archive_provenance_files", mismatched_archive)
    args = builder.parse_args(
        ["--output", str(output), "--local-rows", "1", "--tokenization", "skip"]
    )

    with pytest.raises(RuntimeError, match="differs from its provenance archive"):
        builder.build(args)

    assert (output / "FAILED.json").is_file()
    assert not (output / "manifest.json").exists()


def test_build_refuses_to_overwrite_materialized_data(tmp_path) -> None:
    output = tmp_path / "review"
    output.mkdir()
    (output / "keep.txt").write_text("user data")
    args = builder.parse_args(
        ["--output", str(output), "--local-rows", "1", "--tokenization", "skip"]
    )

    with pytest.raises(FileExistsError):
        builder.build(args)


def test_failed_build_keeps_partial_marker_and_issues_no_manifest(monkeypatch, tmp_path) -> None:
    output = tmp_path / "failed-review"

    def broken_stream():
        raise RuntimeError("deliberate fixture failure")
        yield  # pragma: no cover

    monkeypatch.setattr(
        builder,
        "_source_streams",
        lambda *args, **kwargs: [("fixture", 1, broken_stream())],
    )
    args = builder.parse_args(
        ["--output", str(output), "--local-rows", "1", "--tokenization", "skip"]
    )

    with pytest.raises(RuntimeError, match="deliberate fixture failure"):
        builder.build(args)

    failure = json.loads((output / "FAILED.json").read_text())
    assert failure["status"] == "failed_or_interrupted"
    assert not (output / "manifest.json").exists()
    assert not list(output.glob("part-*.jsonl"))


def test_review_sample_is_stratified_and_hashed(tmp_path) -> None:
    input_dir = tmp_path / "review"
    build_args = builder.parse_args(
        [
            "--output",
            str(input_dir),
            "--local-rows",
            "1000",
            "--shard-rows",
            "100",
            "--tokenization",
            "skip",
        ]
    )
    builder.build(build_args)
    output = tmp_path / "sample.jsonl"
    manifest_output = tmp_path / "sample-manifest.json"

    manifest = sampler.build_sample(
        input_dir=input_dir,
        output=output,
        manifest_output=manifest_output,
        rows_per_cell=2,
        seed=3407,
    )

    assert manifest["sample_rows"] == 50
    assert manifest["strata"] == ["subject", "pedagogy"]
    assert manifest["stratum_cell_count"] == 25
    assert set(manifest["counts"]["subject"].values()) == {10}
    assert set(manifest["counts"]["subject_pedagogy"].values()) == {2}
    assert manifest["counts"]["source"] == {"muta_verified_stem_v2": 50}
    assert manifest["source_shard_verification"]["verified"] is True
    assert manifest["source_shard_verification"]["shard_count"] == 10
    assert manifest["output"]["sha256"] == core.sha256_file(output)


def test_review_sample_rejects_changed_live_validator(tmp_path) -> None:
    input_dir = tmp_path / "review"
    builder.build(
        builder.parse_args(
            [
                "--output",
                str(input_dir),
                "--local-rows",
                "5",
                "--tokenization",
                "skip",
            ]
        )
    )
    manifest_path = input_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    core_receipt = next(row for row in manifest["inputs"]["code"] if row["path"] == "core.py")
    core_receipt["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="live validator core.py differs"):
        sampler.build_sample(
            input_dir=input_dir,
            output=tmp_path / "sample.jsonl",
            manifest_output=tmp_path / "sample-manifest.json",
            rows_per_cell=1,
            seed=3407,
        )


def _write_sampler_fixture(input_dir, records) -> None:
    input_dir.mkdir()
    midpoint = len(records) // 2
    shards = []
    for shard_index, shard_records in enumerate((records[:midpoint], records[midpoint:])):
        path = input_dir / f"part-{shard_index:05d}.jsonl"
        path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                for record in shard_records
            ),
            encoding="utf-8",
        )
        shards.append(
            {
                "path": path.name,
                "rows": len(shard_records),
                "bytes": path.stat().st_size,
                "sha256": core.sha256_file(path),
            }
        )
    fingerprint = hashlib.sha256(
        "\n".join(shard["sha256"] for shard in shards).encode("ascii")
    ).hexdigest()
    (input_dir / "manifest.json").write_text(
        json.dumps(
            {
                "row_count": len(records),
                "dataset_fingerprint_sha256": fingerprint,
                "shards": shards,
            }
        ),
        encoding="utf-8",
    )


def test_review_sample_can_be_source_balanced_and_is_deterministic(tmp_path) -> None:
    records = []
    for source in ("source_alpha", "source_beta"):
        for subject in ("mathematics", "physics"):
            for ordinal in range(3):
                records.append(
                    {
                        "id": f"{source}-{subject}-{ordinal}",
                        "subject": subject,
                        "topic": "measurement",
                        "difficulty": "standard",
                        "pedagogy": "worked_solution",
                        "provenance": {"source_id": source},
                    }
                )
    input_dir = tmp_path / "warehouse"
    _write_sampler_fixture(input_dir, records)

    first_output = tmp_path / "source-sample-a.jsonl"
    first_manifest_output = tmp_path / "source-sample-a-manifest.json"
    manifest = sampler.build_sample(
        input_dir=input_dir,
        output=first_output,
        manifest_output=first_manifest_output,
        rows_per_cell=1,
        seed=3407,
        strata=("source", "subject"),
        revalidate_rows=False,
    )
    second_output = tmp_path / "source-sample-b.jsonl"
    sampler.build_sample(
        input_dir=input_dir,
        output=second_output,
        manifest_output=tmp_path / "source-sample-b-manifest.json",
        rows_per_cell=1,
        seed=3407,
        strata=("source", "subject"),
        revalidate_rows=False,
    )

    selected = [json.loads(line) for line in first_output.read_text().splitlines()]
    expected_ids = {
        min(
            (
                record
                for record in records
                if record["provenance"]["source_id"] == source and record["subject"] == subject
            ),
            key=lambda record: sampler._rank(3407, record["id"]),
        )["id"]
        for source in ("source_alpha", "source_beta")
        for subject in ("mathematics", "physics")
    }
    assert {record["id"] for record in selected} == expected_ids
    assert first_output.read_bytes() == second_output.read_bytes()
    assert manifest["strata"] == ["source", "subject"]
    assert manifest["stratum_cell_count"] == 4
    assert manifest["counts"]["source"] == {"source_alpha": 2, "source_beta": 2}
    assert set(manifest["counts"]["strata_cells"].values()) == {1}

    filtered_output = tmp_path / "source-sample-filtered.jsonl"
    filtered_manifest = sampler.build_sample(
        input_dir=input_dir,
        output=filtered_output,
        manifest_output=tmp_path / "source-sample-filtered-manifest.json",
        rows_per_cell=1,
        seed=3407,
        strata=("source", "subject"),
        source_filter=("source_beta",),
        revalidate_rows=False,
    )
    assert filtered_manifest["source_filter"] == ["source_beta"]
    assert filtered_manifest["counts"]["source"] == {"source_beta": 2}
    assert {
        json.loads(line)["provenance"]["source_id"]
        for line in filtered_output.read_text().splitlines()
    } == {"source_beta"}

    with pytest.raises(ValueError, match="absent from the dataset"):
        sampler.build_sample(
            input_dir=input_dir,
            output=tmp_path / "missing-source.jsonl",
            manifest_output=tmp_path / "missing-source-manifest.json",
            rows_per_cell=1,
            seed=3407,
            source_filter=("source_gamma",),
            revalidate_rows=False,
        )


def test_review_sample_strata_are_allowlisted_and_unique(tmp_path) -> None:
    args = sampler.parse_args(
        [
            "--input",
            str(tmp_path),
            "--output",
            str(tmp_path / "sample.jsonl"),
            "--manifest-output",
            str(tmp_path / "manifest.json"),
            "--strata",
            "source",
            "semantic_cluster",
        ]
    )
    assert args.strata == ("source", "semantic_cluster")

    with pytest.raises(ValueError, match="unsupported strata"):
        sampler.build_sample(
            input_dir=tmp_path,
            output=tmp_path / "sample.jsonl",
            manifest_output=tmp_path / "manifest.json",
            rows_per_cell=1,
            seed=3407,
            revalidate_rows=False,
            strata=("provenance.source_id",),
        )
    with pytest.raises(ValueError, match="duplicate"):
        sampler.build_sample(
            input_dir=tmp_path,
            output=tmp_path / "sample.jsonl",
            manifest_output=tmp_path / "manifest.json",
            rows_per_cell=1,
            seed=3407,
            revalidate_rows=False,
            strata=("source", "source"),
        )


def test_review_sample_refuses_overwrite_and_detects_shard_tampering(tmp_path) -> None:
    input_dir = tmp_path / "warehouse"
    records = [
        {
            "id": "one",
            "subject": "mathematics",
            "topic": "number",
            "difficulty": "foundation",
            "pedagogy": "worked_solution",
            "provenance": {"source_id": "source_alpha"},
        },
        {
            "id": "two",
            "subject": "physics",
            "topic": "motion",
            "difficulty": "standard",
            "pedagogy": "concise_answer",
            "provenance": {"source_id": "source_beta"},
        },
    ]
    _write_sampler_fixture(input_dir, records)
    output = tmp_path / "sample.jsonl"
    output.write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        sampler.build_sample(
            input_dir=input_dir,
            output=output,
            manifest_output=tmp_path / "sample-manifest.json",
            rows_per_cell=1,
            seed=3407,
            revalidate_rows=False,
        )
    assert output.read_text() == "keep me"

    output.unlink()
    (input_dir / "part-00000.jsonl").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source shard hash mismatch"):
        sampler.build_sample(
            input_dir=input_dir,
            output=output,
            manifest_output=tmp_path / "sample-manifest.json",
            rows_per_cell=1,
            seed=3407,
            revalidate_rows=False,
        )


def test_review_sample_rejects_unlisted_shards_and_bad_aggregate(tmp_path) -> None:
    records = [
        {
            "id": "one",
            "subject": "mathematics",
            "topic": "number",
            "difficulty": "foundation",
            "pedagogy": "worked_solution",
            "provenance": {"source_id": "source_alpha", "semantic_cluster_id": "one"},
        },
        {
            "id": "two",
            "subject": "physics",
            "topic": "motion",
            "difficulty": "standard",
            "pedagogy": "concise_answer",
            "provenance": {"source_id": "source_beta", "semantic_cluster_id": "two"},
        },
    ]
    input_dir = tmp_path / "coverage"
    _write_sampler_fixture(input_dir, records)
    (input_dir / "part-99999.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="coverage mismatch"):
        sampler.build_sample(
            input_dir=input_dir,
            output=tmp_path / "coverage.jsonl",
            manifest_output=tmp_path / "coverage-manifest.json",
            rows_per_cell=1,
            seed=3407,
            revalidate_rows=False,
        )

    (input_dir / "part-99999.jsonl").unlink()
    manifest_path = input_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["dataset_fingerprint_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="aggregate dataset fingerprint"):
        sampler.build_sample(
            input_dir=input_dir,
            output=tmp_path / "aggregate.jsonl",
            manifest_output=tmp_path / "aggregate-manifest.json",
            rows_per_cell=1,
            seed=3407,
            revalidate_rows=False,
        )
