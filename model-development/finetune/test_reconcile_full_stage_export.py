from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import launch_full_stage_export as launch
import reconcile_full_stage_export as reconcile
import test_preflight_full_stage_export as artifact_tests
from test_launch_full_stage_export import auxiliary_setup, write  # noqa: F401 -- pytest fixture


@pytest.fixture
def state(tmp_path, monkeypatch, auxiliary_setup):  # noqa: F811 -- imported pytest fixture
    args, _, _, rows, _, _ = auxiliary_setup
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    fixture = artifact_tests.Fixture(inputs, monkeypatch)
    gate = artifact_tests.gate
    report = json.loads(json.dumps(gate.preflight(fixture.args)))
    replay = launch.replay_args(gate, report)
    args.attempt = args.output
    args.gpu = 0
    args.receipt = tmp_path / "reconciliation.json"
    args.launcher = HERE / "launch_full_stage_export.py"
    args.expected_launcher_sha256 = launch.sha_file(args.launcher)
    args.attempt_authority = tmp_path / "authority.json"
    args.runtime_admission = tmp_path / "current-runtime.json"
    runtime = {
        "commands": {"git": {"path": "/usr/bin/git"}},
        "kind": "muta_full_export_runtime_admission",
        "candidate_id": replay.candidate_id,
    }
    report_sha = write(args.output / "artifact-preflight.json", report)
    runtime["preflight_sha256"] = report_sha
    args.expected_runtime_admission_sha256 = write(args.runtime_admission, runtime)
    original_runtime = tmp_path / "original-runtime.json"
    write(original_runtime, runtime)
    original_launcher = tmp_path / "original-launcher.py"
    original_launcher.write_text("# synthetic frozen v1, never executed\n")
    monkeypatch.setattr(reconcile, "V1_SHA", launch.sha_file(original_launcher))
    monkeypatch.setattr(launch, "gpu_lock_path", lambda gpu: tmp_path / "gpu.lock")
    payload = {
        "lock_fd": 3,
        "invocations": str(args.output / "child-invocations.jsonl"),
        "helper": str(replay.exporter.with_name("campaign_io.py")),
        "helper_sha256": gate.HELPER_SHA,
        "exporter_sha256": gate.EXPORTER_SHA,
        "argv": [
            *report["exporter_arguments"],
            "--output",
            str(args.output),
            "--model-name",
            launch.MODELS[replay.candidate_id],
        ],
    }
    old = {
        "launcher": launch.file_receipt(original_launcher),
        "preflight_source_sha256": launch.PREFLIGHT_SHA,
        "preflight_sha256": report_sha,
        "runtime": {"admission_sha256": launch.sha_file(original_runtime)},
        "candidate_id": replay.candidate_id,
        "selection": report["selection"],
        "controller_pid": 122,
        "gpu_lock": str(launch.gpu_lock_path(0)),
        "cwd": str(args.output),
        "environment": launch.environment_for(args, runtime),
        "bootstrap_sha256": hashlib.sha256(launch.BOOTSTRAP.encode()).hexdigest(),
        "argv": [str(args.python), "-E", "-s", "-B", "-c", launch.BOOTSTRAP, json.dumps(payload)],
    }
    write(args.output / "launch.json", old)
    write(args.output / "started.json", {"child_pid": 123})
    write(args.output / "exit.json", {"child_pid": 123, "returncode": 0})
    failed = {
        "error_type": "LaunchError",
        "error_code": "child_invocation_bound",
        "state": "descendant_liveness_unassessed",
        "automatic_retry": False,
        "child_pid_preserved": None,
        "returncode": 0,
        "known_descendant_pids": sorted(r["child_pid"] for r in rows),
    }
    write(args.output / "FAILED.json", failed)
    write(args.output / "quantization-manifest.json", {"synthetic": "not exported"})
    for name in ("merge-and-quantize.log", "stdout.log", "stderr.log"):
        (args.output / name).write_text("")
    monkeypatch.setattr(reconcile, "load_launcher", lambda *a: launch)
    monkeypatch.setattr(launch, "load_gate", lambda *_a: gate)
    monkeypatch.setattr(launch, "verify_runtime", lambda *a: {"synthetic": "no runtime executed"})
    monkeypatch.setattr(launch, "check_idle", lambda *a: {"synthetic": "no GPU queried"})
    monkeypatch.setattr(launch, "auxiliary_profile", lambda *a: {"synthetic": True})
    monkeypatch.setattr(launch, "verify_result", lambda *a: {"child_invocations": rows})
    monkeypatch.setattr(
        reconcile, "require_absent", lambda launch, pids: {"synthetic_pids": sorted(pids)}
    )

    def freeze():
        authority = {
            "schema_version": 1,
            "kind": "muta_failed_export_reconciliation_authority",
            "attempt": str(args.output),
            "files": {
                name: reconcile.evidence_receipt(launch, args.output / name)
                for name in reconcile.FILES
            },
            "original_runtime_admission": reconcile.evidence_receipt(launch, original_runtime),
        }
        args.expected_attempt_authority_sha256 = write(args.attempt_authority, authority)
        return authority

    freeze()
    return args, fixture, freeze, rows


def test_reconcile_preserves_every_original_byte(state, monkeypatch):
    args, _, _, _ = state
    before = {p.name: p.read_bytes() for p in args.output.iterdir()}
    monkeypatch.setattr(
        launch.subprocess, "Popen", lambda *a, **kw: pytest.fail("must never spawn")
    )
    receipt = reconcile.reconcile(args)
    assert receipt["status"] == "export_artifacts_verified_after_controller_verifier_defect"
    assert receipt["original_attempt_modified"] is False
    assert receipt["inference_tested"] is False and receipt["reexported"] is False
    assert before == {p.name: p.read_bytes() for p in args.output.iterdir()}
    assert args.receipt.exists() and not (args.output / "COMPLETED.json").exists()
    with pytest.raises(launch.LaunchError, match="external_receipt"):
        reconcile.reconcile(args)


@pytest.mark.parametrize(
    "mutation",
    [
        "authority",
        "original_bytes",
        "failure",
        "returncode",
        "pid",
        "descendants",
        "bootstrap",
        "payload",
        "environment",
        "original_source",
        "receipt_inside",
        "receipt_symlink",
        "completed",
        "lock",
        "busy",
        "runtime",
        "preflight",
        "result",
        "live_process",
        "post_drift",
    ],
)
def test_reconcile_refuses_unsafe_attempt(state, tmp_path, monkeypatch, mutation):
    args, fixture, freeze, rows = state
    held = None
    if mutation == "authority":
        args.expected_attempt_authority_sha256 = "0" * 64
    elif mutation == "original_bytes":
        (args.output / "stdout.log").write_text("changed")
    elif mutation in {"failure", "descendants"}:
        data = launch.read_json(args.output / "FAILED.json")
        data["error_code" if mutation == "failure" else "known_descendant_pids"] = "other"
        write(args.output / "FAILED.json", data)
        freeze()
    elif mutation in {"returncode", "pid"}:
        write(
            args.output / "exit.json",
            {
                "child_pid": 999 if mutation == "pid" else 123,
                "returncode": 1 if mutation == "returncode" else 0,
            },
        )
        freeze()
    elif mutation in {"bootstrap", "payload", "environment", "original_source"}:
        data = launch.read_json(args.output / "launch.json")
        if mutation == "bootstrap":
            data["argv"][5] += "\n# other"
        elif mutation == "payload":
            payload = json.loads(data["argv"][6])
            payload["lock_fd"] = True
            data["argv"][6] = json.dumps(payload)
        elif mutation == "environment":
            data["environment"]["PRIVATE_TOKEN"] = "must not leak"
        else:
            Path(data["launcher"]["path"]).write_text("changed")
        write(args.output / "launch.json", data)
        freeze()
    elif mutation == "receipt_inside":
        args.receipt = args.output / "reconciled.json"
    elif mutation == "receipt_symlink":
        link = tmp_path / "linked"
        link.symlink_to(args.output, target_is_directory=True)
        args.receipt = link / "reconciled.json"
    elif mutation == "completed":
        write(args.output / "COMPLETED.json", {})
    elif mutation == "lock":
        held = launch.acquire_gpu_lock(0)
    elif mutation == "preflight":
        (fixture.run / "adapter/tokenizer.json").write_text("changed")
    elif mutation == "post_drift":

        def result(*a):
            (args.output / "stdout.log").write_text("changed after verification")
            return {"child_invocations": rows}

        monkeypatch.setattr(launch, "verify_result", result)
    else:
        name = {
            "busy": "check_idle",
            "runtime": "verify_runtime",
            "result": "verify_result",
            "live_process": "require_absent",
        }[mutation]
        target = reconcile if mutation == "live_process" else launch
        monkeypatch.setattr(
            target, name, lambda *a: (_ for _ in ()).throw(launch.LaunchError("synthetic_failure"))
        )
    try:
        with pytest.raises(
            (launch.LaunchError, BlockingIOError, artifact_tests.gate.PreflightError)
        ):
            reconcile.reconcile(args)
    finally:
        if held is not None:
            os.close(held)
    assert not args.receipt.exists()


def test_absence_probe_fails_closed(monkeypatch):
    monkeypatch.setattr(os, "kill", lambda *a: None)
    with pytest.raises(launch.LaunchError, match="process_present"):
        reconcile.require_absent(launch, {123})

    def absent(*a):
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", absent)
    assert reconcile.require_absent(launch, {123})["recorded_pids_absent"] == [123]


def test_loader_external_hash():
    path = HERE / "launch_full_stage_export.py"
    assert (
        reconcile.load_launcher(path, launch.sha_file(path)).PREFLIGHT_SHA == launch.PREFLIGHT_SHA
    )
    with pytest.raises(ValueError, match="source_changed"):
        reconcile.load_launcher(path, "0" * 64)


@pytest.mark.parametrize(
    "error", [launch.LaunchError("safe_failure_code"), OSError("PRIVATE_TEXT")]
)
def test_cli_error_diagnostics_are_safe(monkeypatch, capsys, error):
    monkeypatch.setattr(
        reconcile, "parser", lambda: type("Parser", (), {"parse_args": lambda *a: None})()
    )
    monkeypatch.setattr(reconcile, "reconcile", lambda *a: (_ for _ in ()).throw(error))
    assert reconcile.main([]) == 2
    text = capsys.readouterr().err
    assert "PRIVATE_TEXT" not in text
    assert ("safe_failure_code" if isinstance(error, launch.LaunchError) else "OSError") in text
