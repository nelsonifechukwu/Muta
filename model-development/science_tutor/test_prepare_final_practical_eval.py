"""Static tests for the append-only final practical-2,000 preparation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).with_name("prepare_final_practical_eval.py")
SPEC = importlib.util.spec_from_file_location("prepare_final_practical_eval", MODULE)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

ROOT = Path(__file__).resolve().parents[2]
OLD_CONFIG = ROOT / "provenance/evaluation/practical-winner-2000-20260919/full-config.json"
OLD_TRANSPORT = (
    ROOT / "provenance/evaluation/practical-winner-2000-20260919/transport-acceptance.json"
)
ROSTER = (
    ROOT
    / "provenance/science-tutor-20260919/evaluation/final-five-candidate-manifest.json"
)


def test_real_inputs_support_narrow_transport_inheritance(tmp_path: Path):
    output = tmp_path / "noncanonical-release"
    prepared = gate.prepare(OLD_CONFIG, OLD_TRANSPORT, ROSTER, output)
    assert prepared["status"] == "prepared_not_launched"
    assert prepared["expected_responses"] == 10000

    config = json.loads((output / "config.json").read_text())
    transport = json.loads(
        (output / "inherited-transport-acceptance.json").read_text()
    )
    assert config["candidates"]["sha256"] == gate.NEW_ROSTER_SHA256
    assert config["transport_gate"]["sha256"] == gate.file_sha256(
        output / "inherited-transport-acceptance.json"
    )
    assert transport["new_inference_performed"] is False
    assert transport["duplicate_integrity_passed"] is False
    assert transport["parent_candidates_sha256"] != transport["candidates_sha256"]
    assert transport["candidate_expected"] == json.loads(ROSTER.read_text())["candidates"][0][
        "expected"
    ]
    assert "candidates[:1]" in transport["inheritance_scope"]
    assert "verifies all five" in transport["inheritance_scope"]
    launcher = (output / "stage-and-launch.sh").read_text()
    assert f"local_dir={output.resolve()}" in launcher
    assert f"mkdir -m 700 '{gate.REMOTE_CONFIG_DIR}'" in launcher
    assert f"rmdir '{gate.REMOTE_CONFIG_DIR}.staging'" in launcher
    assert "find '/lambda/nfs/awf-tmp" in launcher


def test_inheritance_rejects_changed_first_candidate():
    old_config = gate.load_json(OLD_CONFIG, gate.OLD_CONFIG_SHA256)
    old_transport = gate.load_json(OLD_TRANSPORT, gate.OLD_TRANSPORT_SHA256)
    roster = gate.load_json(ROSTER, gate.NEW_ROSTER_SHA256)
    roster["candidates"][0]["expected"]["model_sha256"] = "0" * 64
    with pytest.raises(gate.PreparationError, match="smoke candidate changed"):
        gate.inherited_transport(old_config, old_transport, roster)


def test_inheritance_rejects_changed_settings():
    old_config = gate.load_json(OLD_CONFIG, gate.OLD_CONFIG_SHA256)
    old_transport = gate.load_json(OLD_TRANSPORT, gate.OLD_TRANSPORT_SHA256)
    roster = gate.load_json(ROSTER, gate.NEW_ROSTER_SHA256)
    old_config["settings"]["slots"] = 4
    with pytest.raises(gate.PreparationError, match="settings changed"):
        gate.inherited_transport(old_config, old_transport, roster)


def test_preparation_is_append_only(tmp_path: Path):
    output = tmp_path / "release"
    gate.prepare(OLD_CONFIG, OLD_TRANSPORT, ROSTER, output)
    with pytest.raises(FileExistsError):
        gate.prepare(OLD_CONFIG, OLD_TRANSPORT, ROSTER, output)


def test_failed_preparation_leaves_failure_receipt(tmp_path: Path):
    bad_config = tmp_path / "bad-config.json"
    bad_config.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "failed-release"
    with pytest.raises(gate.PreparationError, match="hash mismatch"):
        gate.prepare(bad_config, OLD_TRANSPORT, ROSTER, output)
    failure = json.loads((output / "PREPARATION_FAILED.json").read_text())
    assert failure["status"] == "failed"
    assert failure["inference_launched"] is False
