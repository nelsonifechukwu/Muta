from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FROZEN_LAUNCHER = (
    HERE.parents[1]
    / "provenance/hosts/oracle/full-export-v1-20260918T2203/launch_full_stage_export.py"
)
sys.path.insert(0, str(HERE))
import collect_full_export_runtime_evidence as collector
import launch_full_stage_export as launch
import test_launch_full_stage_export as launch_tests


@pytest.fixture
def setup(tmp_path, monkeypatch):
    runtime_args, gate, replay, admission = launch_tests.runtime_fixture(tmp_path, monkeypatch)
    gguf = replay.llama_cpp / "gguf-py/gguf"
    gguf.mkdir(parents=True)
    (gguf / "writer.py").write_text("# synthetic gguf source\n")
    (gguf / "empty.py").touch()
    replay.run_dir = tmp_path / "training"
    replay.base = tmp_path / "base"
    replay.training_code = tmp_path / "training-code"
    quantizer = replay.llama_cpp / "build/bin/llama-quantize"
    quantizer.parent.mkdir(parents=True)
    quantizer.write_text("synthetic binary, never executed")
    gate.CONVERTER_SHA = launch.sha_file(replay.llama_cpp / "convert_hf_to_gguf.py")
    gate.QUANTIZER_SHA = launch.sha_file(quantizer)
    ldd = tmp_path / "ldd"
    ldd.write_text("synthetic command, never executed")
    report = {"status": "artifact_preflight_passed", "candidate_id": replay.candidate_id}
    report_path = tmp_path / "preflight.json"
    report_path.write_text(json.dumps(report))
    args = argparse.Namespace(
        launcher=FROZEN_LAUNCHER,
        preflight_receipt=report_path,
        expected_preflight_sha256=launch.sha_file(report_path),
        python=runtime_args.python,
        git=Path(admission["commands"]["git"]["path"]),
        nvidia_smi=Path(admission["commands"]["nvidia_smi"]["path"]),
        ldd=ldd,
        planned_output=tmp_path / "future-export",
        output=tmp_path / "draft.json",
        gpu=0,
        expires_in_seconds=7200,
    )
    monkeypatch.setattr(collector, "load_launcher", lambda _p: launch)
    monkeypatch.setattr(launch, "load_gate", lambda: gate)
    monkeypatch.setattr(launch, "replay_args", lambda *_a: replay)
    calls = []
    library = admission["quantizer_native_libraries"][0]["path"]

    def command(argv, environment, **_kw):
        calls.append(argv)
        assert argv[0] in {str(args.git), str(args.python), str(args.ldd)}
        assert "HF_TOKEN" not in environment and "PYTHONPATH" not in environment
        assert environment["HF_HUB_OFFLINE"] == environment["TRANSFORMERS_OFFLINE"] == "1"
        if "rev-parse" in argv:
            return gate.LLAMA_COMMIT + "\n"
        if "status" in argv:
            return ""
        if argv[0] == str(args.ldd):
            return f"linux-vdso.so.1 (0x123)\nlibtest.so => {library} (0x456)\n"
        return json.dumps(admission["python_probe"])

    monkeypatch.setattr(launch, "command_output", command)
    return args, gate, replay, admission, calls


def test_draft_is_measured_but_cannot_grant_admission(setup, monkeypatch):
    args, gate, replay, _admission, calls = setup
    monkeypatch.setenv("HF_TOKEN", "PRIVATE_SECRET")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    result = collector.collect(args)
    assert result["kind"] == collector.DRAFT_KIND
    assert result["review_required"] is True and result["runtime_admission_granted"] is False
    assert result["collection"]["model_loaded"] is False
    assert result["collection"]["gpu_queried"] is False
    assert "PRIVATE_SECRET" not in json.dumps(result)
    assert not args.planned_output.exists()
    assert all(argv[0] != str(args.nvidia_smi) for argv in calls)
    names = {Path(r["path"]).name for r in result["dependency_files"]}
    assert {"writer.py", "module.py", "convert_hf_to_gguf.py", "llama-quantize"} <= names
    assert result["coverage"]["empty_python_sources"][0]["bytes"] == 0
    probe_args = argparse.Namespace(
        python=args.python,
        gpu=0,
        output=args.planned_output,
        expected_preflight_sha256=args.expected_preflight_sha256,
        expected_runtime_admission_sha256="a" * 64,
    )
    with pytest.raises(launch.LaunchError, match="runtime_admission_identity"):
        launch.verify_runtime(probe_args, gate, replay, result, {})
    # Schema-compatibility test only; no approval file or real admission is made.
    reviewed_shape = copy.deepcopy(result)
    reviewed_shape["kind"] = "muta_full_export_runtime_admission"
    launch.verify_runtime(
        probe_args, gate, replay, reviewed_shape, result["collection"]["environment"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "expiry",
        "hash",
        "converter",
        "dirty",
        "source_symlink",
        "probe_changed",
        "dependency_changed",
        "output",
    ],
)
def test_collector_failures_do_not_write_or_launch(setup, monkeypatch, mutation):
    args, gate, replay, _admission, calls = setup
    if mutation == "expiry":
        args.expires_in_seconds = 86401
    elif mutation == "hash":
        args.expected_preflight_sha256 = "0" * 64
    elif mutation == "converter":
        gate.CONVERTER_SHA = "0" * 64
    elif mutation == "dirty":
        original = launch.command_output
        monkeypatch.setattr(
            launch,
            "command_output",
            lambda argv, *a, **k: (
                "?? untracked.py\n" if "status" in argv else original(argv, *a, **k)
            ),
        )
    elif mutation == "source_symlink":
        (replay.llama_cpp / "conversion/link.py").symlink_to(
            replay.llama_cpp / "convert_hf_to_gguf.py"
        )
    elif mutation in {"probe_changed", "dependency_changed"}:
        original = launch.command_output
        count = 0

        def changed(argv, *a, **k):
            nonlocal count
            result = original(argv, *a, **k)
            if argv[0] == str(args.python):
                count += 1
                if count == 2:
                    if mutation == "probe_changed":
                        return '{"changed": true}'
                    (replay.llama_cpp / "gguf-py/gguf/writer.py").write_text(
                        "changed after inventory"
                    )
            return result

        monkeypatch.setattr(launch, "command_output", changed)
    else:
        args.output.write_text("preserve")
    with pytest.raises((collector.EvidenceError, launch.LaunchError)):
        collector.collect(args)
    assert not args.planned_output.exists()
    assert all(argv[0] != str(args.nvidia_smi) for argv in calls)
    if mutation == "output":
        assert args.output.read_text() == "preserve"
    else:
        assert not args.output.exists()


@pytest.mark.parametrize("identity", ["python", "git", "ldd", "converter", "quantizer"])
def test_initial_identity_changed_before_dependency_snapshot_rejected(setup, monkeypatch, identity):
    args, _gate, replay, _admission, _calls = setup
    target = {
        "python": args.python,
        "git": args.git,
        "ldd": args.ldd,
        "converter": replay.llama_cpp / "convert_hf_to_gguf.py",
        "quantizer": replay.llama_cpp / "build/bin/llama-quantize",
    }[identity]
    original = launch.command_output
    changed = False

    def command(argv, *a, **k):
        nonlocal changed
        result = original(argv, *a, **k)
        if argv[0] == str(args.python) and not changed:
            changed = True
            target.write_text("changed between initial identity and dependency inventory")
        return result

    monkeypatch.setattr(launch, "command_output", command)
    with pytest.raises(collector.EvidenceError, match="initial_identity_changed"):
        collector.collect(args)
    assert not args.output.exists()


@pytest.mark.parametrize(
    "text", ["libx => not found\n", "not a dynamic executable\n", "", "PRIVATE unexpected prose\n"]
)
def test_malformed_or_unresolved_ldd_rejected(text):
    with pytest.raises(collector.EvidenceError):
        collector.parse_ldd(text)


def test_ldd_resolves_logical_symlink_and_loader(tmp_path):
    native = tmp_path / "native.so"
    native.write_text("synthetic")
    alias = tmp_path / "lib.so"
    alias.symlink_to(native)
    rows = collector.parse_ldd(f"lib.so => {alias} (0x123)\n{native} (0x456)\n")
    assert {row["resolved_path"] for row in rows} == {str(native)}
    assert {row["path"] for row in rows} == {str(alias), str(native)}


def test_source_count_and_depth_bounds(tmp_path, monkeypatch):
    root = tmp_path / "sources"
    root.mkdir()
    (root / "one.py").write_text("x")
    (root / "two.py").write_text("x")
    monkeypatch.setattr(collector, "MAX_ENTRIES", 1)
    with pytest.raises(collector.EvidenceError, match="source_count_bound"):
        collector.python_sources(root)
    monkeypatch.setattr(collector, "MAX_ENTRIES", 10000)
    deep = root
    for _ in range(14):
        deep = deep / "nested"
        deep.mkdir()
    with pytest.raises(collector.EvidenceError, match="source_depth_bound"):
        collector.python_sources(root)


def test_exact_launcher_loader():
    loaded = collector.load_launcher(FROZEN_LAUNCHER)
    assert loaded.PREFLIGHT_SHA == launch.PREFLIGHT_SHA


def test_cli_no_overwrite_and_draft_only(setup, capsys):
    args, *_ = setup
    argv = [
        part
        for key, value in vars(args).items()
        for part in ("--" + key.replace("_", "-"), str(value))
    ]
    assert collector.main(argv) == 0
    result = json.loads(args.output.read_text())
    assert result["kind"] == collector.DRAFT_KIND
    assert json.loads(capsys.readouterr().out)["runtime_admission_granted"] is False
    prior = args.output.read_bytes()
    assert collector.main(argv) == 2
    assert args.output.read_bytes() == prior
    assert "output_exists" in capsys.readouterr().err
