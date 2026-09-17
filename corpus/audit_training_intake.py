#!/usr/bin/env python3
"""Audit a local exam corpus before it can influence a Muta training build.

The output is deliberately content-free: it contains hashes, source metadata,
high-level taxonomy labels, quality gates, and aggregate counts, but never
copies question, answer, explanation, marking-scheme, or examiner-report text.
The source corpus remains a separate, access-controlled study snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_VERSION = 1
AUDITOR_VERSION = "muta-corpus-intake-v1"
TOPIC_RULE_VERSION = "west-african-secondary-stem-broad-v1"

SOURCE_TYPE_TO_REGISTRY_ID = {
    "waec_html": "waec_elearning",
    "cheetah_pdf": "cheetahwaec",
}

EXPRESSIVE_SOURCE_KEYS = frozenset(
    {
        "question_text",
        "options",
        "correct_answer",
        "worked_solution",
        "marking_scheme",
        "examiner_observation",
        "generated_solution",
    }
)

# These are broad curriculum concepts, not source-derived phrases. Matching may
# inspect the private corpus, but only labels and aggregate counts are emitted.
TOPIC_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "mathematics": (
        ("number_and_numeration", (r"\bfraction", r"\bdecimal", r"\bbase\s+\d+", r"\bprime\b", r"\bhcf\b", r"\blcm\b", r"\bsur[dr]\b")),
        ("algebra", (r"\bequation", r"\binequal", r"\bfactoris", r"\bexpand", r"\bquadratic", r"\bsimultaneous", r"\bpolynomial", r"\bexpression")),
        ("indices_logarithms_and_surds", (r"\blog(?:arithm)?\b", r"\bindex|indices\b", r"\bsurd", r"\bexponent")),
        ("sets_and_logic", (r"\bset\b", r"\bvenn\b", r"\bunion\b", r"\bintersection\b", r"\bsubset")),
        ("ratio_rate_and_variation", (r"\bratio\b", r"\bproportion", r"\bvar(?:y|ies|iation)\b", r"\brate\b", r"\bspeed\b")),
        ("sequences_and_series", (r"\bsequence", r"\bseries\b", r"\bprogression", r"\bnth\s+term", r"\bcommon\s+(?:difference|ratio)")),
        ("financial_arithmetic", (r"\binterest\b", r"\bprofit\b", r"\bloss\b", r"\bdiscount\b", r"\bcommission\b", r"\btax\b", r"\bdepreciat", r"\bpercentage")),
        ("coordinate_geometry_and_graphs", (r"\bcoordinate", r"\bgradient\b", r"\bslope\b", r"\bgraph\b", r"\bmidpoint\b", r"\bordinate\b", r"\babscissa\b")),
        ("plane_geometry", (r"\btriangle", r"\bcircle", r"\bangle", r"\bpolygon", r"\bchord\b", r"\btangent\b", r"\bparallel\b", r"\btheorem\b")),
        ("mensuration", (r"\barea\b", r"\bvolume\b", r"\bperimeter\b", r"\bsurface\s+area", r"\bcircumference", r"\bcone\b", r"\bcylinder", r"\bprism\b", r"\bsphere\b")),
        ("trigonometry_and_bearings", (r"\bsin\b", r"\bcos\b", r"\btan\b", r"\btrigonom", r"\bbearing", r"\belevation", r"\bdepression")),
        ("statistics", (r"\bmean\b", r"\bmedian\b", r"\bmode\b", r"\bfrequency", r"\bhistogram", r"\bstandard\s+deviation", r"\bvariance\b")),
        ("probability", (r"\bprobability", r"\brandom\b", r"\bsample\s+space", r"\boutcome")),
        ("vectors_and_transformations", (r"\bvector", r"\bmatrix|matrices\b", r"\btransformation", r"\btranslation", r"\brotation", r"\breflection", r"\benlargement")),
    ),
    "physics": (
        ("measurement_and_experimental_skills", (r"\bmeasure", r"\breading", r"\bparallax", r"\bprecision", r"\baccuracy", r"\buncertaint", r"\bplot\b", r"\bgradient", r"\bapparatus")),
        ("mechanics", (r"\bforce\b", r"\bmotion\b", r"\bvelocity", r"\bacceleration", r"\bmomentum", r"\bfriction", r"\bprojectile", r"\bnewton", r"\btorque|moment\b")),
        ("work_energy_and_power", (r"\bwork\b", r"\benergy\b", r"\bpower\b", r"\befficien", r"\bkinetic", r"\bpotential")),
        ("properties_of_matter_and_fluids", (r"\bdensity", r"\bpressure", r"\belastic", r"\bviscos", r"\bsurface\s+tension", r"\bcapillar", r"\bupthrust", r"\bbuoy")),
        ("thermal_physics", (r"\bheat\b", r"\btemperature", r"\bthermal", r"\bspecific\s+heat", r"\blatent", r"\bexpansion")),
        ("waves_and_sound", (r"\bwave", r"\bfrequency", r"\bwavelength", r"\bsound\b", r"\bresonance", r"\boscillat", r"\bvibration")),
        ("light_and_optics", (r"\blight\b", r"\blens\b", r"\bmirror\b", r"\brefraction", r"\breflection", r"\bfocal", r"\bimage\b", r"\bprism\b")),
        ("electricity_and_circuits", (r"\bcurrent\b", r"\bvoltage", r"\bpotential\s+difference", r"\bresistance", r"\bresistor", r"\bcircuit", r"\bohm", r"\bcapacit")),
        ("magnetism_and_electromagnetism", (r"\bmagnet", r"\bmagnetic", r"\binduction", r"\btransformer", r"\bsolenoid", r"\belectromagnet")),
        ("atomic_and_nuclear_physics", (r"\batom", r"\bnuclear", r"\bradioactiv", r"\bhalf[- ]life", r"\bisotope", r"\bphotoelectric", r"\bx[- ]ray")),
        ("electronics", (r"\bdiode", r"\btransistor", r"\bsemiconductor", r"\brectif", r"\blogic\s+gate")),
    ),
    "chemistry": (
        ("measurement_and_experimental_skills", (r"\btitrat", r"\bapparatus", r"\bexperiment", r"\bobservation", r"\bfiltrat", r"\bprecipitate", r"\btest\b")),
        ("atomic_structure_and_periodicity", (r"\batom", r"\belectron", r"\bproton", r"\bneutron", r"\bperiodic", r"\bgroup\b", r"\bperiod\b", r"\bisotope")),
        ("bonding_and_structure", (r"\bbond", r"\bionic", r"\bcovalent", r"\bmetallic", r"\bintermolecular", r"\bcrystal|lattice\b")),
        ("mole_concept_and_stoichiometry", (r"\bmole\b", r"\bmolar", r"\bstoichiometr", r"\bempirical\s+formula", r"\bmolecular\s+formula", r"\bavogadro")),
        ("states_gases_and_solutions", (r"\bgas\b", r"\bpressure", r"\bvolume", r"\bsolution", r"\bsolub", r"\bconcentration", r"\bdilut")),
        ("acids_bases_and_salts", (r"\bacid", r"\bbase\b", r"\balkali", r"\bsalt\b", r"\bph\b", r"\bneutral", r"\bindicator", r"\blitmus")),
        ("redox_and_electrochemistry", (r"\boxid", r"\breduc", r"\bredox", r"\belectrolys", r"\belectrode", r"\banode", r"\bcathode", r"\belectrochemical")),
        ("energetics_kinetics_and_equilibrium", (r"\benthalpy", r"\bheat\s+of", r"\brate\s+of\s+reaction", r"\bcatalyst", r"\bequilibrium", r"\ble\s*chatelier", r"\bactivation\s+energy")),
        ("organic_chemistry", (r"\bhydrocarbon", r"\balkane", r"\balkene", r"\balkyne", r"\balcohol", r"\bester", r"\bpolymer", r"\borganic")),
        ("metals_and_extraction", (r"\bmetal\b", r"\balloy", r"\bore\b", r"\bextraction", r"\bblast\s+furnace", r"\bcorrosion")),
        ("qualitative_analysis", (r"\bidentify", r"\bflame\s+test", r"\bcolour", r"\bprecipitate", r"\bconfirmatory\s+test", r"\bion\b")),
        ("environmental_and_industrial_chemistry", (r"\bpollut", r"\bwater\s+treatment", r"\bindustr", r"\bfertilizer", r"\bsoap", r"\bdetergent", r"\bair\b")),
    ),
    "biology": (
        ("measurement_and_practical_skills", (r"\bspecimen", r"\bobserve", r"\bapparatus", r"\bexperiment", r"\bdiagram", r"\blabel", r"\bmagnif")),
        ("cell_biology", (r"\bcell\b", r"\bcellular", r"\bmembrane", r"\bcytoplasm", r"\bnucleus", r"\bmitosis", r"\bmeiosis")),
        ("nutrition_and_digestion", (r"\bfood\b", r"\bnutrition", r"\bdigest", r"\benzyme", r"\bvitamin", r"\bphotosynthesis")),
        ("transport_respiration_and_excretion", (r"\bblood\b", r"\bheart\b", r"\bcirculat", r"\brespirat", r"\bexcret", r"\bkidney", r"\bstomata", r"\btranspir")),
        ("coordination_and_homeostasis", (r"\bnervous", r"\bbrain\b", r"\bhormone", r"\bhomeostas", r"\bresponse", r"\bsense\s+organ", r"\btemperature\s+regulation")),
        ("reproduction_growth_and_development", (r"\breproduc", r"\bfertiliz", r"\bpollination", r"\bgerminat", r"\bgrowth\b", r"\bmenstrual", r"\bplacenta")),
        ("genetics_and_evolution", (r"\bgene\b", r"\bgenetic", r"\binherit", r"\bchromosome", r"\ballele", r"\bvariation", r"\bevolution", r"\bmutation")),
        ("ecology", (r"\becolog", r"\bhabitat", r"\bpopulation", r"\bcommunity", r"\bfood\s+(?:chain|web)", r"\becosystem", r"\bsoil\b", r"\bconservation")),
        ("classification_and_diversity", (r"\bclassif", r"\btaxonom", r"\bkingdom", r"\bphylum", r"\bspecies", r"\borganism", r"\bvertebrate", r"\binvertebrate")),
        ("plant_structure_and_physiology", (r"\bleaf|leaves\b", r"\broot\b", r"\bstem\b", r"\bxylem", r"\bphloem", r"\bplant\b", r"\btropism")),
        ("disease_and_immunity", (r"\bdisease", r"\bpathogen", r"\bbacteria", r"\bvirus", r"\bparasite", r"\bimmun", r"\bvaccin")),
    ),
}

SKILL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("calculation", (r"\bcalculate", r"\bcompute", r"\bevaluate", r"\bsolve", r"\bfind\b", r"\bdetermine")),
    ("explanation", (r"\bexplain", r"\bwhy\b", r"\bgive\s+(?:a\s+)?reason", r"\baccount\s+for")),
    ("definition_or_recall", (r"\bdefine", r"\bstate\b", r"\bname\b", r"\blist\b", r"\bmention")),
    ("comparison_or_classification", (r"\bcompare", r"\bdistinguish", r"\bdifference", r"\bclassif", r"\bgroup\b")),
    ("graph_or_data_interpretation", (r"\bgraph\b", r"\btable\b", r"\bplot\b", r"\bgradient", r"\bchart\b")),
    ("experimental_reasoning", (r"\bexperiment", r"\bapparatus", r"\bprocedure", r"\bprecaution", r"\bobservation", r"\bmeasure")),
    ("visual_reasoning", (r"\bdiagram", r"\bfigure", r"\bshown\b", r"\bsketch", r"\bdraw\b", r"\blabel")),
    ("proof_or_derivation", (r"\bprove", r"\bshow\s+that", r"\bderive")),
)

ERROR_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "omission_or_non_attempt",
        (r"\bdid not attempt", r"\bnot attempted", r"\bomitt", r"\bleft (?:it )?blank"),
    ),
    (
        "diagram_or_labelling",
        (r"\bdiagram", r"\blabel", r"\bdrawing", r"\bsketch"),
    ),
    (
        "explanation_or_reasoning",
        (r"\bexplain", r"\breason", r"\bdescription", r"\baccount for"),
    ),
    (
        "calculation_or_substitution",
        (r"\bcalculat", r"\bsubstitut", r"\bformula", r"\barithmetic"),
    ),
    (
        "notation_or_nomenclature",
        (r"\bnotation", r"\bnomenclature", r"\bspell", r"\bsymbol", r"\bformula"),
    ),
    (
        "definition_or_concept",
        (r"\bdefin", r"\bconcept", r"\bmeaning", r"\bterminology"),
    ),
    ("graphing", (r"\bgraph", r"\baxis|axes\b", r"\bplot", r"\bscale")),
    (
        "practical_procedure",
        (r"\bprocedure", r"\bapparatus", r"\bprecaution", r"\bexperiment"),
    ),
    (
        "units_or_precision",
        (r"\bunit", r"\bdecimal place", r"\bsignificant figure", r"\bprecision"),
    ),
    (
        "test_result_inference",
        (r"\btest result", r"\binference", r"\bobservation", r"\bconclusion"),
    ),
)

EXISTING_TOPIC_TO_BROAD: dict[str, str] = {
    "commercial_arithmetic": "financial_arithmetic",
    "rates_and_average_speed": "ratio_rate_and_variation",
    "linear_equations": "algebra",
    "ratio_and_proportion": "ratio_rate_and_variation",
    "simple_interest": "financial_arithmetic",
    "simultaneous_equations": "algebra",
    "sequences": "sequences_and_series",
    "probability": "probability",
    "arithmetic_mean": "statistics",
    "area_of_triangle": "mensuration",
    "pythagoras_theorem": "plane_geometry",
    "percentage_change": "financial_arithmetic",
    "newtons_second_law": "mechanics",
    "density": "properties_of_matter_and_fluids",
    "ohms_law": "electricity_and_circuits",
    "waves": "waves_and_sound",
    "kinetic_energy": "work_energy_and_power",
    "electrical_power": "electricity_and_circuits",
    "pressure": "properties_of_matter_and_fluids",
    "work_done": "work_energy_and_power",
    "amount_of_substance": "mole_concept_and_stoichiometry",
    "solution_concentration": "states_gases_and_solutions",
    "dilution": "states_gases_and_solutions",
    "molar_gas_volume": "mole_concept_and_stoichiometry",
    "stoichiometry": "mole_concept_and_stoichiometry",
    "percentage_composition": "mole_concept_and_stoichiometry",
    "acid_base_neutralization": "acids_bases_and_salts",
    "microscopy": "measurement_and_practical_skills",
    "ecological_sampling": "ecology",
    "mendelian_inheritance": "genetics_and_evolution",
    "seed_germination": "reproduction_growth_and_development",
    "pulse_rate": "transport_respiration_and_excretion",
    "energy_efficiency": "work_energy_and_power",
    "water_storage_volume": "mensuration",
    "temperature_conversion": "thermal_physics",
}


def map_existing_topic_to_broad(topic: str) -> str:
    mapped = EXISTING_TOPIC_TO_BROAD.get(topic)
    if mapped is not None:
        return mapped
    if topic.startswith("algebra_sequence_"):
        return "sequences_and_series"
    if topic.startswith(("algebra_", "polynomials_")):
        return "algebra"
    if topic.startswith(("arithmetic_", "numbers_", "comparison_", "measurement_")):
        return "number_and_numeration"
    if topic.startswith("probability_"):
        return "probability"
    if topic.startswith("calculus_"):
        return "calculus"
    return f"unmapped::{topic}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.translate(str.maketrans({"−": "-", "–": "-", "—": "-", "×": "*", "÷": "/"}))
    return " ".join(re.findall(r"[a-z]+|\d+(?:\.\d+)?|<=|>=|!=|[+\-*/=<>%^]", text))


def normalized_sha256(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def classify_labels(record: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    text = "\n".join(
        str(record.get(field) or "")
        for field in ("question_text", "worked_solution", "marking_scheme")
    ).casefold()
    text = re.sub(r"\[asset:[^\]]+\]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    subject = str(record.get("subject") or "")
    topics = [
        label
        for label, patterns in TOPIC_RULES.get(subject, ())
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    ]
    skills = [
        label
        for label, patterns in SKILL_RULES
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    ]
    return sorted(topics or ["unclassified"]), sorted(skills or ["unclassified"])


def classify_error_categories(record: Mapping[str, Any]) -> list[str]:
    text = str(record.get("examiner_observation") or "").casefold()
    labels = [
        label
        for label, patterns in ERROR_RULES
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    ]
    return sorted(labels or ["unclassified"])


def _source_text_hash(record: Mapping[str, Any]) -> str:
    fields = (
        "question_text",
        "options",
        "correct_answer",
        "worked_solution",
        "marking_scheme",
        "examiner_observation",
        "generated_solution",
    )
    return canonical_json_sha256({field: record.get(field) for field in fields})


def _answer_material_present(record: Mapping[str, Any]) -> bool:
    if str(record.get("correct_answer") or "").strip():
        return True
    if str(record.get("worked_solution") or "").strip():
        return True
    return any(asset.get("role") == "answer" for asset in record.get("assets", []))


def make_row_decision(record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    source_type = str(source.get("source_type") or "")
    source_id = SOURCE_TYPE_TO_REGISTRY_ID.get(source_type, "unregistered")
    topics, skills = classify_labels(record)
    error_categories = classify_error_categories(record)
    answer_status = str(record.get("answer_status") or "missing")
    content_status = str(record.get("content_status") or "incomplete")
    assets = record.get("assets") or []

    reasons = ["source_not_licensed_for_training", "answer_not_independently_verified"]
    if answer_status == "missing" or not _answer_material_present(record):
        reasons.append("answer_missing")
        assurance = "missing"
    elif answer_status == "generated_unverified":
        reasons.append("generated_answer_unverified")
        assurance = "generated_unverified"
    else:
        assurance = "publisher_only"
    if content_status == "incomplete":
        reasons.append("content_incomplete")
    if content_status == "needs_visual_review":
        reasons.append("visual_review_required")
    if assets:
        reasons.append("asset_rights_not_cleared")

    decision = {
        "record_id": str(record.get("record_id") or ""),
        "source_id": source_id,
        "source_type": source_type,
        "source_record_sha256": canonical_json_sha256(record),
        "source_text_bundle_sha256": _source_text_hash(record),
        "normalized_question_sha256": normalized_sha256(str(record.get("question_text") or "")),
        "subject": record.get("subject"),
        "year": record.get("year"),
        "paper": record.get("paper"),
        "question_format": record.get("question_format"),
        "content_status": content_status,
        "answer_status": answer_status,
        "answer_material_present": _answer_material_present(record),
        "answer_assurance": assurance,
        "answer_independently_verified": False,
        "correction_status": "not_attempted_rights_quarantine",
        "asset_count": len(assets),
        "has_unresolved_asset": any(not asset.get("local_path") for asset in assets),
        "extraction_warning_codes": sorted(set(record.get("extraction_warnings") or [])),
        "taxonomy": {
            "rule_version": TOPIC_RULE_VERSION,
            "topics": topics,
            "skills": skills,
            "error_categories": error_categories,
        },
        "training_decision": "blocked",
        "evaluation_decision": "conditional_private_review_only",
        "shipped_rag_decision": "blocked",
        "exclusion_reasons": sorted(set(reasons)),
    }
    if EXPRESSIVE_SOURCE_KEYS & decision.keys():
        raise AssertionError("row decision leaked an expressive source field")
    return decision


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for row in rows:
            line = canonical_json_bytes(row) + b"\n"
            handle.write(line)
            digest.update(line)
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    return count, digest.hexdigest()


def iter_inventory(root: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        yield {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }


def _counter_dict(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): value for key, value in sorted(counter.items(), key=lambda item: str(item[0]))}


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[bytes]]:
    rows: list[dict[str, Any]] = []
    raw_lines: list[bytes] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows.append(value)
            raw_lines.append(raw.rstrip(b"\r\n"))
    return rows, raw_lines


def _validate_rows(rows: list[dict[str, Any]], schema: dict[str, Any]) -> list[dict[str, Any]]:
    validator = Draft202012Validator(schema)
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        for error in validator.iter_errors(row):
            errors.append(
                {
                    "row_index": index,
                    "record_id": row.get("record_id"),
                    "path": "/".join(str(part) for part in error.absolute_path),
                    "validator": error.validator,
                    "error_code": f"{error.validator}_validation_failure",
                }
            )
    return errors


def _asset_audit(rows: list[dict[str, Any]], corpus_dir: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    unique_hashes: set[str] = set()
    for row in rows:
        assets = row.get("assets") or []
        if assets:
            counts["records_with_assets"] += 1
        for asset in assets:
            counts["asset_references"] += 1
            if asset.get("role") == "question":
                counts["question_asset_references"] += 1
            if asset.get("role") == "answer":
                counts["answer_asset_references"] += 1
            local_path = asset.get("local_path")
            expected_sha = asset.get("sha256")
            if not local_path:
                counts["unresolved_references"] += 1
                continue
            path = corpus_dir / str(local_path)
            if not path.is_file():
                counts["missing_local_files"] += 1
                continue
            counts["resolved_local_files"] += 1
            observed_sha = sha256_file(path)
            unique_hashes.add(observed_sha)
            if not expected_sha:
                counts["resolved_without_recorded_sha256"] += 1
            elif observed_sha != expected_sha:
                counts["sha256_mismatches"] += 1
    result = dict(counts)
    for key in (
        "records_with_assets",
        "asset_references",
        "question_asset_references",
        "answer_asset_references",
        "unresolved_references",
        "missing_local_files",
        "resolved_local_files",
        "resolved_without_recorded_sha256",
        "sha256_mismatches",
    ):
        result.setdefault(key, 0)
    result["unique_resolved_asset_payloads"] = len(unique_hashes)
    result["rights_clearance"] = "not_documented"
    return result


def _pdf_audit(corpus_dir: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    physical: list[dict[str, Any]] = []
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pages_with_text = 0
    total_pages = 0
    diagnostic_error_markers = 0
    for path in sorted(corpus_dir.rglob("*.pdf")):
        digest = sha256_file(path)
        reader = PdfReader(path)
        page_count = len(reader.pages)
        nonempty_text_pages = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                nonempty_text_pages += 1
            diagnostic_error_markers += text.casefold().count("math input error")
        row = {
            "path": path.relative_to(corpus_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest,
            "pages": page_count,
            "pages_with_nonempty_text_layer": nonempty_text_pages,
        }
        physical.append(row)
        by_hash[digest].append(row)
        total_pages += page_count
        pages_with_text += nonempty_text_pages

    unique_documents = [group[0] for _, group in sorted(by_hash.items())]
    duplicate_groups = [
        {
            "sha256": digest,
            "paths": sorted(row["path"] for row in group),
            "copies": len(group),
        }
        for digest, group in sorted(by_hash.items())
        if len(group) > 1
    ]
    return {
        "physical_pdf_files": len(physical),
        "unique_pdf_payloads": len(unique_documents),
        "physical_bytes": sum(row["bytes"] for row in physical),
        "unique_bytes": sum(row["bytes"] for row in unique_documents),
        "physical_pages": total_pages,
        "unique_pages": sum(row["pages"] for row in unique_documents),
        "physical_pages_with_nonempty_text_layer": pages_with_text,
        "unique_pages_with_nonempty_text_layer": sum(
            row["pages_with_nonempty_text_layer"] for row in unique_documents
        ),
        "diagnostic_math_input_error_markers_across_physical_copies": diagnostic_error_markers,
        "files": physical,
        "duplicate_groups": duplicate_groups,
        "visual_audit_required": True,
    }


def _source_decisions(
    rows: list[dict[str, Any]], registry_document: dict[str, Any]
) -> list[dict[str, Any]]:
    registry = {row["id"]: row for row in registry_document["sources"]}
    source_counts = Counter(
        SOURCE_TYPE_TO_REGISTRY_ID.get(row["source"]["source_type"], "unregistered")
        for row in rows
    )
    decisions: list[dict[str, Any]] = []
    for source_id, count in sorted(source_counts.items()):
        source = registry.get(source_id)
        if source is None:
            decisions.append(
                {
                    "source_id": source_id,
                    "rows": count,
                    "registry_status": "missing",
                    "training": "blocked",
                    "evaluation": "blocked",
                    "shipped_rag": "blocked",
                    "reason": "source_missing_from_registry",
                }
            )
            continue
        decisions.append(
            {
                "source_id": source_id,
                "name": source.get("name"),
                "rows": count,
                "revision": source.get("revision"),
                "license": source.get("license"),
                "license_url": source.get("license_url"),
                "registry_status": source.get("status"),
                "allowed_splits": source.get("allowed_splits", []),
                "training": "blocked",
                "evaluation": "conditional_private_review_only",
                "shipped_rag": "blocked",
                "permission_route": source.get("permission_route"),
                "reason": "no_explicit_model_training_and_artifact_distribution_grant",
            }
        )
    return decisions


def _quality_summary(rows: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    exact_questions = [str(row.get("question_text") or "") for row in rows]
    normalized_questions = [normalize_text(value) for value in exact_questions]
    nonempty_exact = [value for value in exact_questions if value.strip()]
    nonempty_normalized = [value for value in normalized_questions if value]
    warning_counts = Counter(
        warning for row in rows for warning in row.get("extraction_warnings", [])
    )
    topic_counts: Counter[str] = Counter()
    skill_counts: Counter[str] = Counter()
    error_category_counts: Counter[str] = Counter()
    topic_by_subject: dict[str, Counter[str]] = defaultdict(Counter)
    for decision in decisions:
        subject = str(decision["subject"])
        for topic in decision["taxonomy"]["topics"]:
            topic_counts[topic] += 1
            topic_by_subject[subject][topic] += 1
        for skill in decision["taxonomy"]["skills"]:
            skill_counts[skill] += 1
        for category in decision["taxonomy"]["error_categories"]:
            error_category_counts[category] += 1

    return {
        "rows": len(rows),
        "subjects": _counter_dict(Counter(row.get("subject") for row in rows)),
        "years": _counter_dict(Counter(row.get("year") for row in rows)),
        "source_types": _counter_dict(
            Counter(row.get("source", {}).get("source_type") for row in rows)
        ),
        "content_status": _counter_dict(Counter(row.get("content_status") for row in rows)),
        "answer_status": _counter_dict(Counter(row.get("answer_status") for row in rows)),
        "answer_assurance": _counter_dict(
            Counter(decision["answer_assurance"] for decision in decisions)
        ),
        "question_format": _counter_dict(
            Counter(row.get("question_format") for row in rows)
        ),
        "papers": _counter_dict(Counter(row.get("paper") for row in rows)),
        "records_with_nonempty_question": len(nonempty_exact),
        "records_with_answer_material": sum(_answer_material_present(row) for row in rows),
        "records_with_independently_verified_answer": 0,
        "records_with_generated_solution": sum(
            row.get("generated_solution") is not None for row in rows
        ),
        "records_with_extraction_warnings": sum(
            bool(row.get("extraction_warnings")) for row in rows
        ),
        "extraction_warning_codes": _counter_dict(warning_counts),
        "exact_question_duplicate_excess": len(nonempty_exact) - len(set(nonempty_exact)),
        "normalized_question_duplicate_excess": len(nonempty_normalized)
        - len(set(nonempty_normalized)),
        "topic_rule_version": TOPIC_RULE_VERSION,
        "heuristic_topic_counts": _counter_dict(topic_counts),
        "heuristic_topic_counts_by_subject": {
            subject: _counter_dict(counter) for subject, counter in sorted(topic_by_subject.items())
        },
        "heuristic_skill_counts": _counter_dict(skill_counts),
        "heuristic_examiner_error_category_counts": _counter_dict(error_category_counts),
        "taxonomy_caveat": (
            "Rule-based, multi-label coverage signal only; labels are not authoritative "
            "syllabus annotations and do not authorize source-text use."
        ),
    }


def _manifest_consistency(
    source_manifest: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    actual_by_source = Counter(row["source"]["source_type"] for row in rows)
    declared_coverage = source_manifest.get("coverage", {}).get("by_source", {})
    source_manifest_keys = {
        "waec_html": "waec",
        "cheetah_pdf": "cheetah",
    }
    declared_source_records = {
        source_type: source_manifest.get("sources", {}).get(manifest_key, {}).get("records")
        for source_type, manifest_key in source_manifest_keys.items()
    }
    mismatches: list[dict[str, Any]] = []
    for source_type, actual in sorted(actual_by_source.items()):
        coverage_value = declared_coverage.get(source_type)
        source_value = declared_source_records.get(source_type)
        if coverage_value != actual:
            mismatches.append(
                {
                    "field": f"coverage.by_source.{source_type}",
                    "declared": coverage_value,
                    "actual": actual,
                }
            )
        if source_value != actual:
            mismatches.append(
                {
                    "field": f"sources.{source_manifest_keys[source_type]}.records",
                    "declared": source_value,
                    "actual": actual,
                }
            )
    return {
        "actual_total_rows": len(rows),
        "declared_coverage_total_rows": source_manifest.get("coverage", {}).get(
            "total_records"
        ),
        "mismatches": mismatches,
        "consistent": not mismatches,
    }


def _directory_inventory(root: Path) -> tuple[list[dict[str, Any]], str]:
    rows = list(iter_inventory(root))
    digest = hashlib.sha256()
    for row in rows:
        digest.update(canonical_json_bytes(row) + b"\n")
    return rows, digest.hexdigest()


def _audit_sft(sft_dir: Path) -> dict[str, Any]:
    manifest_path = sft_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_counts: Counter[str] = Counter()
    subject_counts: Counter[str] = Counter()
    pedagogy_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()
    broad_counts: Counter[str] = Counter()
    rows_scanned = 0
    shard_failures: list[dict[str, Any]] = []
    for shard in manifest.get("shards", []):
        path = sft_dir / shard["path"]
        observed_sha = sha256_file(path)
        if observed_sha != shard["sha256"]:
            shard_failures.append(
                {
                    "path": shard["path"],
                    "expected_sha256": shard["sha256"],
                    "observed_sha256": observed_sha,
                }
            )
        shard_rows = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                shard_rows += 1
                rows_scanned += 1
                source_counts[str(row.get("provenance", {}).get("source_id"))] += 1
                subject_counts[str(row.get("subject"))] += 1
                pedagogy_counts[str(row.get("pedagogy"))] += 1
                topic = str(row.get("topic"))
                topic_counts[topic] += 1
                broad_counts[map_existing_topic_to_broad(topic)] += 1
        if shard_rows != shard["rows"]:
            shard_failures.append(
                {
                    "path": shard["path"],
                    "expected_rows": shard["rows"],
                    "observed_rows": shard_rows,
                }
            )

    inventory, inventory_fingerprint = _directory_inventory(sft_dir)
    return {
        "path": sft_dir.as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
        "dataset_fingerprint_sha256": manifest.get("dataset_fingerprint_sha256"),
        "declared_rows": manifest.get("row_count"),
        "rows_scanned": rows_scanned,
        "all_declared_shards_valid": not shard_failures,
        "shard_failures": shard_failures,
        "counts": {
            "source": _counter_dict(source_counts),
            "subject": _counter_dict(subject_counts),
            "pedagogy": _counter_dict(pedagogy_counts),
            "topic": _counter_dict(topic_counts),
            "broad_topic": _counter_dict(broad_counts),
        },
        "directory_file_count": len(inventory),
        "directory_inventory_fingerprint_sha256": inventory_fingerprint,
    }


def _coverage_comparison(
    quality: dict[str, Any], sft_audit: dict[str, Any]
) -> dict[str, Any]:
    source_topics = quality["heuristic_topic_counts"]
    sft_topics = sft_audit["counts"]["broad_topic"]
    gaps = [
        {"topic": topic, "source_rows_with_label": count, "current_sft_rows": 0}
        for topic, count in source_topics.items()
        if topic != "unclassified" and sft_topics.get(topic, 0) == 0
    ]
    gaps.sort(key=lambda row: (-row["source_rows_with_label"], row["topic"]))
    return {
        "current_sft": sft_audit,
        "corpus_subject_counts": quality["subjects"],
        "corpus_question_format_counts": quality["question_format"],
        "corpus_heuristic_topic_counts": source_topics,
        "coverage_labels_absent_from_current_native_topic_map": gaps,
        "frequency_warning": (
            "The corpus is an uneven availability snapshot, not a statistically valid target "
            "distribution. Its frequencies must not directly set SFT quotas."
        ),
        "decision": {
            "source_rows_merged_into_sft": 0,
            "replace_current_300k": False,
            "retain_current_300k_unchanged": True,
            "reason": (
                "No new source row passes both rights and independent-answer-verification gates. "
                "The high-level gap labels should inform separately authored, verified generators "
                "and a future versioned candidate, not a direct source-row merge."
            ),
        },
    }


def _artifact_report(
    *,
    quality: dict[str, Any],
    source_decisions: list[dict[str, Any]],
    schema_error_count: int,
    assets: dict[str, Any],
    pdfs: dict[str, Any],
    consistency: dict[str, Any],
    comparison: dict[str, Any],
) -> str:
    source_lines = "\n".join(
        f"- `{item['source_id']}`: {item['rows']:,} rows; training {item['training']}; "
        f"shipped RAG {item['shipped_rag']}."
        for item in source_decisions
    )
    gaps = comparison["coverage_labels_absent_from_current_native_topic_map"][:12]
    gap_lines = "\n".join(
        f"- `{row['topic']}`: {row['source_rows_with_label']:,} source rows carry the label."
        for row in gaps
    ) or "- None detected by the broad rule map."
    mismatches = consistency["mismatches"]
    mismatch_lines = "\n".join(
        f"- `{row['field']}` declares {row['declared']!r}; observed {row['actual']!r}."
        for row in mismatches
    ) or "- No manifest count mismatch detected."
    return f"""# Muta corpus intake audit

## Decision

No row from the newly added exam corpus is admitted to SFT or a shipped RAG
index. The existing 300K v1 artifact remains the approved training candidate
and was not modified. The corpus contributes only content-free, high-level
coverage signals for future independently authored generators.

## Intake summary

- Rows: {quality['rows']:,}
- Schema errors: {schema_error_count:,}
- Complete rows: {quality['content_status'].get('complete', 0):,}
- Rows needing visual review: {quality['content_status'].get('needs_visual_review', 0):,}
- Incomplete rows: {quality['content_status'].get('incomplete', 0):,}
- Rows with publisher-labelled answers: {quality['answer_status'].get('published', 0):,}
- Rows with independently verified answers: {quality['records_with_independently_verified_answer']:,}
- Rows with extraction warnings: {quality['records_with_extraction_warnings']:,}
- Rows with assets: {assets['records_with_assets']:,}
- Unresolved asset references: {assets['unresolved_references']:,}
- Physical PDFs: {pdfs['physical_pdf_files']:,}; unique payloads: {pdfs['unique_pdf_payloads']:,}

## Source decisions

{source_lines}

Public availability and free download access are not model-training licences.
Every publisher answer remains `publisher_only` until independently reproduced;
missing, ambiguous, or unverified answers are never admitted.

## Manifest consistency

{mismatch_lines}

## Coverage signals absent from the current generator map

These labels are heuristic and multi-label. They identify areas for original
generator design; they do not authorize copying or paraphrasing source items.

{gap_lines}

## Artifact contents

- `row-decisions.jsonl`: hashes, metadata, taxonomy labels, and admission gates;
  no question or answer text.
- `file-inventory.jsonl`: path, size, and SHA-256 for each source-corpus file.
- `quality-summary.json`: aggregate completeness, warning, duplicate, and
  taxonomy statistics.
- `source-decisions.json`: source-by-source rights decisions.
- `asset-audit.json` and `pdf-audit.json`: extraction dependency evidence.
- `sft-comparison.json`: verified current-300K counts and the retain/replace
  decision.
- `provenance/`: exact policy, schema, source manifest, and auditor snapshots.
"""


def build_audit(
    *,
    corpus_dir: Path,
    source_registry_path: Path,
    sft_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    corpus_dir = corpus_dir.resolve()
    source_registry_path = source_registry_path.resolve()
    sft_dir = sft_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite immutable audit artifact: {output_dir}")

    questions_jsonl = corpus_dir / "questions.jsonl"
    questions_json = corpus_dir / "questions.json"
    schema_path = corpus_dir / "schema.json"
    source_manifest_path = corpus_dir / "manifest.json"
    required = (
        questions_jsonl,
        questions_json,
        schema_path,
        source_manifest_path,
        source_registry_path,
        sft_dir / "manifest.json",
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    rows, _ = _load_jsonl(questions_jsonl)
    json_rows = json.loads(questions_json.read_text(encoding="utf-8"))
    if canonical_json_sha256(rows) != canonical_json_sha256(json_rows):
        raise ValueError("questions.json and questions.jsonl do not contain the same records")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    registry_document = json.loads(source_registry_path.read_text(encoding="utf-8"))
    schema_errors = _validate_rows(rows, schema)

    decisions = [make_row_decision(row) for row in rows]
    quality = _quality_summary(rows, decisions)
    assets = _asset_audit(rows, corpus_dir)
    pdfs = _pdf_audit(corpus_dir)
    consistency = _manifest_consistency(source_manifest, rows)
    source_decisions = _source_decisions(rows, registry_document)
    sft_audit = _audit_sft(sft_dir)
    comparison = _coverage_comparison(quality, sft_audit)
    inventory = list(iter_inventory(corpus_dir))

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.partial-", dir=output_dir.parent))
    try:
        row_count, row_decisions_sha = _write_jsonl(temporary / "row-decisions.jsonl", decisions)
        inventory_count, inventory_sha = _write_jsonl(
            temporary / "file-inventory.jsonl", inventory
        )
        _write_json(temporary / "schema-errors.json", {"errors": schema_errors})
        _write_json(temporary / "quality-summary.json", quality)
        _write_json(temporary / "source-decisions.json", {"sources": source_decisions})
        _write_json(temporary / "asset-audit.json", assets)
        _write_json(temporary / "pdf-audit.json", pdfs)
        _write_json(temporary / "source-manifest-consistency.json", consistency)
        _write_json(temporary / "sft-comparison.json", comparison)
        (temporary / "REPORT.md").write_text(
            _artifact_report(
                quality=quality,
                source_decisions=source_decisions,
                schema_error_count=len(schema_errors),
                assets=assets,
                pdfs=pdfs,
                consistency=consistency,
                comparison=comparison,
            ),
            encoding="utf-8",
        )

        provenance = temporary / "provenance"
        provenance.mkdir()
        provenance_sources = {
            "auditor-audit_training_intake.py": Path(__file__).resolve(),
            "policy-source_registry.json": source_registry_path,
            "corpus-schema.json": schema_path,
            "corpus-manifest.json": source_manifest_path,
        }
        provenance_receipts: list[dict[str, Any]] = []
        for name, source_path in sorted(provenance_sources.items()):
            destination = provenance / name
            shutil.copyfile(source_path, destination)
            provenance_receipts.append(
                {
                    "path": destination.relative_to(temporary).as_posix(),
                    "source_path": source_path.as_posix(),
                    "sha256": sha256_file(destination),
                }
            )

        output_receipts = []
        for path in sorted(
            candidate for candidate in temporary.rglob("*") if candidate.is_file()
        ):
            output_receipts.append(
                {
                    "path": path.relative_to(temporary).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        artifact_fingerprint = hashlib.sha256(
            b"".join(canonical_json_bytes(row) + b"\n" for row in output_receipts)
        ).hexdigest()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "artifact_name": "muta-corpus-training-intake-audit",
            "auditor_version": AUDITOR_VERSION,
            "artifact_fingerprint_sha256": artifact_fingerprint,
            "inputs": {
                "corpus_dir": corpus_dir.as_posix(),
                "questions_jsonl_sha256": sha256_file(questions_jsonl),
                "questions_json_sha256": sha256_file(questions_json),
                "corpus_schema_sha256": sha256_file(schema_path),
                "corpus_manifest_sha256": sha256_file(source_manifest_path),
                "source_registry_sha256": sha256_file(source_registry_path),
                "sft_manifest_sha256": sft_audit["manifest_sha256"],
                "sft_dataset_fingerprint_sha256": sft_audit[
                    "dataset_fingerprint_sha256"
                ],
            },
            "counts": {
                "source_rows": len(rows),
                "row_decisions": row_count,
                "schema_errors": len(schema_errors),
                "training_admissions": 0,
                "source_files_inventoried": inventory_count,
            },
            "content_boundary": {
                "contains_question_text": False,
                "contains_answer_text": False,
                "contains_solution_or_marking_scheme_text": False,
                "contains_source_media": False,
                "allowed_payload": "hashes_metadata_quality_flags_and_high_level_taxonomy_only",
            },
            "answer_gate": {
                "publisher_answer_is_independent_verification": False,
                "independently_verified_source_answers": 0,
                "unanswered_or_unverified_rows_admitted": 0,
            },
            "decision": comparison["decision"],
            "ledger_hashes": {
                "row_decisions_sha256": row_decisions_sha,
                "file_inventory_sha256": inventory_sha,
            },
            "provenance_files": provenance_receipts,
            "artifact_files_excluding_manifest": output_receipts,
        }
        _write_json(temporary / "manifest.json", manifest)
        os.replace(temporary, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--sft-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_audit(
        corpus_dir=args.corpus_dir,
        source_registry_path=args.source_registry,
        sft_dir=args.sft_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
