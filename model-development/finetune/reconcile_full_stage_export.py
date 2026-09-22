"""Read-only replay of one v1 child_invocation_bound failure; never re-export.

Writes only one new external receipt. A successful reconciliation does not erase
the original controller failure or establish historical hermeticity/inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
import types
from pathlib import Path

V1_SHA = "16f10222dab4be4facc7e04e6f6a6215d6d0d17d312887a4308445a85df9abb0"
FILES = {
    "launch.json",
    "started.json",
    "exit.json",
    "FAILED.json",
    "child-invocations.jsonl",
    "artifact-preflight.json",
    "quantization-manifest.json",
    "merge-and-quantize.log",
    "stdout.log",
    "stderr.log",
}


def load_launcher(path, expected):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("launcher_symlink")
    with path.open("rb") as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("launcher_source_changed")
    module = types.ModuleType("_reconciliation_launcher")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 -- externally pinned source
    return module


def evidence_receipt(launch, path):
    path = Path(os.path.abspath(path))
    launch.require(not any(p.is_symlink() for p in (path, *path.parents)), "evidence_symlink")
    info = path.stat()
    launch.require(stat.S_ISREG(info.st_mode) and info.st_size <= 64 * 1024**2, "evidence_bound")
    return {"path": str(path), "bytes": info.st_size, "sha256": launch.sha_file(path)}


def verify_originals(launch, args, authority):
    launch.require(
        set(authority)
        == {"schema_version", "kind", "attempt", "files", "original_runtime_admission"}
        and authority["schema_version"] == 1
        and authority["kind"] == "muta_failed_export_reconciliation_authority"
        and authority["attempt"] == str(args.output)
        and set(authority["files"]) == FILES,
        "attempt_authority",
    )
    for name, receipt in authority["files"].items():
        launch.require(
            evidence_receipt(launch, args.output / name) == receipt, "original_evidence_changed"
        )
    original = authority["original_runtime_admission"]
    launch.require(
        evidence_receipt(launch, original["path"]) == original, "original_admission_changed"
    )
    launch.require(
        not (args.output / "COMPLETED.json").exists()
        and not (args.output / "COMPLETED.json").is_symlink(),
        "already_completed",
    )


def require_absent(launch, pids):
    for pid in pids:
        launch.require(type(pid) is int and pid > 0, "original_pid")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
        launch.require(False, "original_process_present_or_unassessable")
    return {
        "checked_unix": time.time(),
        "recorded_pids_absent": sorted(pids),
        "transitive_process_history": "not_assessed",
    }


def reconcile(args):
    launch = load_launcher(args.launcher, args.expected_launcher_sha256)
    verifier_identity = launch.file_receipt(Path(__file__))
    args.output = Path(os.path.abspath(args.attempt))
    authority = launch.read_json(args.attempt_authority, args.expected_attempt_authority_sha256)
    verify_originals(launch, args, authority)
    old = launch.read_json(args.output / "launch.json")
    started = launch.read_json(args.output / "started.json")
    exited = launch.read_json(args.output / "exit.json")
    failed = launch.read_json(args.output / "FAILED.json")
    report = launch.read_json(args.output / "artifact-preflight.json")
    original_runtime = launch.read_json(authority["original_runtime_admission"]["path"])
    args.expected_preflight_sha256 = authority["files"]["artifact-preflight.json"]["sha256"]
    launch.require(
        failed.get("error_type") == "LaunchError"
        and failed.get("error_code") == "child_invocation_bound"
        and failed.get("state") == "descendant_liveness_unassessed"
        and failed.get("automatic_retry") is False
        and failed.get("child_pid_preserved") is None
        and type(failed.get("returncode")) is int
        and failed["returncode"] == 0
        and type(exited.get("returncode")) is int
        and exited["returncode"] == 0
        and type(started.get("child_pid")) is int
        and started["child_pid"] > 0
        and exited.get("child_pid") == started["child_pid"],
        "unsupported_original_failure",
    )
    launch.require(
        old["launcher"]["sha256"] == V1_SHA
        and launch.file_receipt(old["launcher"]["path"]) == old["launcher"]
        and old["preflight_source_sha256"] == launch.PREFLIGHT_SHA
        and old["preflight_sha256"] == args.expected_preflight_sha256
        and old["runtime"]["admission_sha256"] == authority["original_runtime_admission"]["sha256"]
        and old["candidate_id"] == report["candidate_id"]
        and old["selection"] == report["selection"]
        and original_runtime["kind"] == "muta_full_export_runtime_admission"
        and original_runtime["candidate_id"] == report["candidate_id"]
        and original_runtime["preflight_sha256"] == args.expected_preflight_sha256
        and old["gpu_lock"] == str(launch.gpu_lock_path(args.gpu)),
        "original_launch_binding",
    )
    gate = launch.load_gate(report)
    replay = launch.replay_args(gate, report)
    admission = launch.read_json(args.runtime_admission, args.expected_runtime_admission_sha256)
    environment = launch.environment_for(args, admission)
    command = old["argv"]
    launch.require(
        isinstance(command, list)
        and len(command) == 7
        and command[:5] == [str(args.python), "-E", "-s", "-B", "-c"]
        and command[5] == launch.BOOTSTRAP
        and old["bootstrap_sha256"] == hashlib.sha256(launch.BOOTSTRAP.encode()).hexdigest()
        and old["environment"] == environment
        and old["cwd"] == str(args.output),
        "original_bootstrap_binding",
    )
    payload = launch.json_object(command[6])
    launch.require(
        type(payload.get("lock_fd")) is int
        and 3 <= payload["lock_fd"] <= 1048576
        and payload
        == {
            "lock_fd": payload["lock_fd"],
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
        },
        "original_payload_binding",
    )
    receipt_path = Path(os.path.abspath(args.receipt))
    launch.require(
        receipt_path.parent.is_dir()
        and not any(p.is_symlink() for p in (receipt_path, *receipt_path.parents))
        and not receipt_path.exists()
        and not receipt_path.is_relative_to(args.output)
        and not receipt_path.is_relative_to(replay.run_dir)
        and not any(receipt_path.is_relative_to(Path(r["path"]).parent) for r in report["inputs"]),
        "external_receipt_path",
    )
    descriptor = launch.acquire_gpu_lock(args.gpu)
    try:
        runtime = launch.verify_runtime(args, gate, replay, admission, environment)
        launch.require(
            launch.auxiliary_profile(args, admission, environment) is not None,
            "auxiliary_profile_required",
        )
        idle = launch.check_idle(args, admission, environment)
        launch.require(
            json.loads(json.dumps(gate.preflight(replay))) == report, "artifact_preflight_changed"
        )
        result = launch.verify_result(args, gate, replay, report)
        invocations = result["child_invocations"]
        launch.require(len(invocations) == 5, "unsupported_original_invocation_count")
        children = sorted(row["child_pid"] for row in invocations)
        launch.require(
            failed.get("known_descendant_pids") == children, "original_descendant_binding"
        )
        processes = require_absent(launch, {old["controller_pid"], started["child_pid"], *children})
        launch.verify_runtime(args, gate, replay, admission, environment)
        launch.auxiliary_profile(args, admission, environment)
        idle = launch.check_idle(args, admission, environment)
        verify_originals(launch, args, authority)
        launch.require(
            launch.read_json(args.attempt_authority, args.expected_attempt_authority_sha256)
            == authority,
            "authority_changed",
        )
        launch.require(
            launch.read_json(args.runtime_admission, args.expected_runtime_admission_sha256)
            == admission,
            "admission_changed",
        )
        launch.require(
            launch.sha_file(args.launcher) == args.expected_launcher_sha256
            and launch.file_receipt(Path(__file__)) == verifier_identity,
            "verifier_source_changed",
        )
        receipt = {
            "schema_version": 1,
            "status": "export_artifacts_verified_after_controller_verifier_defect",
            "candidate_id": replay.candidate_id,
            "attempt_authority_sha256": args.expected_attempt_authority_sha256,
            "original_failure": authority["files"]["FAILED.json"],
            "original_runtime_admission": authority["original_runtime_admission"],
            "verifier": verifier_identity,
            "launcher": launch.file_receipt(args.launcher),
            "runtime_now": runtime,
            "gpu_idle_now": idle,
            "recorded_processes_now": processes,
            "result": result,
            "inference_tested": False,
            "reexported": False,
            "original_attempt_modified": False,
            "historical_limitations": [
                "Auxiliary file hashes measured after export do not authenticate their historical bytes.",
                "Runtime coverage is enumerated and non-hermetic; transitive child execution/history is not proven.",
                "Original FAILED.json remains authoritative for the v1 controller outcome; no retroactive COMPLETED.json.",
            ],
        }
        launch.write_json(receipt_path, receipt)
        return receipt
    finally:
        os.close(descriptor)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in (
        "launcher",
        "attempt",
        "attempt-authority",
        "runtime-admission",
        "auxiliary-profile",
        "python",
        "receipt",
    ):
        result.add_argument("--" + name, type=Path, required=True)
    for name in (
        "expected-launcher-sha256",
        "expected-attempt-authority-sha256",
        "expected-runtime-admission-sha256",
        "expected-auxiliary-profile-sha256",
    ):
        result.add_argument("--" + name, required=True)
    result.add_argument("--gpu", type=int, default=0)
    return result


def main(argv=None):
    try:
        receipt = reconcile(parser().parse_args(argv))
        print(json.dumps({"status": receipt["status"], "inference_tested": False}))
        return 0
    except Exception as error:  # noqa: BLE001 -- no arbitrary exception text in CLI
        code = type(error).__name__
        if code in {"LaunchError", "PreflightError"} and re.fullmatch(
            r"[a-z0-9_]{1,128}", str(error)
        ):
            code = str(error)
        print("Reconciliation failed: " + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
