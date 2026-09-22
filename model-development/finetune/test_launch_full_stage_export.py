from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import launch_full_stage_export as launch
import test_preflight_full_stage_export as artifact_tests


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")
    return launch.sha_file(path)


@pytest.fixture
def setup(tmp_path, monkeypatch, request):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    fixture = artifact_tests.Fixture(
        inputs, monkeypatch, getattr(request, "param", next(iter(launch.MODELS)))
    )
    gate = artifact_tests.gate
    report = gate.preflight(fixture.args)
    report_path = tmp_path / "preflight.json"
    report_sha = write(report_path, report)
    admission_path = tmp_path / "runtime.json"
    admission = {"commands": {"git": {"path": "/usr/bin/git"}}}
    admission_sha = write(admission_path, admission)
    args = argparse.Namespace(
        preflight_receipt=report_path,
        expected_preflight_sha256=report_sha,
        runtime_admission=admission_path,
        expected_runtime_admission_sha256=admission_sha,
        python=Path(sys.executable),
        output=tmp_path / "export",
        mode="gpu",
        gpu=0,
        max_seconds=60,
    )
    monkeypatch.setattr(launch, "load_gate", lambda *_a: gate)
    monkeypatch.setattr(launch, "gpu_lock_path", lambda gpu: tmp_path / f"gpu-{gpu}.lock")
    monkeypatch.setattr(launch, "verify_runtime", lambda *_a: {"verified": "synthetic"})
    monkeypatch.setattr(launch, "check_idle", lambda *_a: {"compute_processes": []})
    monkeypatch.setattr(
        launch, "verify_result", lambda *_a: {"final_gguf": "synthetic_not_exported"}
    )
    return args, fixture, gate, report


def fake_process(monkeypatch, args, *, code=0, timeout=False, interrupt=False):
    calls = []

    class Process:
        pid = 43210
        returncode = None

        def __init__(self, command, **kwargs):
            self.command = command
            calls.append((command, kwargs))
            assert kwargs["pass_fds"] and kwargs["start_new_session"] is True
            os.fstat(kwargs["pass_fds"][0])
            (args.output / "child-invocations.jsonl").write_text('{"test":"no export"}\n')

        def wait(self, timeout):
            if interrupt:
                raise InterruptedError("synthetic interruption")
            if timeout_flag:
                raise subprocess.TimeoutExpired(self.command, timeout)
            self.returncode = code
            return code

        def poll(self):
            return self.returncode

    timeout_flag = timeout
    monkeypatch.setattr(launch.subprocess, "Popen", Process)
    return calls


@pytest.mark.parametrize("setup", list(launch.MODELS), indirect=True)
def test_fresh_success_and_exact_sanitized_child(setup, monkeypatch):
    args, _, _, report = setup
    monkeypatch.setenv("HF_TOKEN", "PRIVATE_TOKEN")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("LD_PRELOAD", "/untrusted/lib.so")
    calls = fake_process(monkeypatch, args)
    result = launch.run_export(args)
    assert result["state"] == "complete" and result["inference_tested"] is False
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:5] == [str(args.python), "-E", "-s", "-B", "-c"]
    payload = json.loads(argv[-1])
    assert payload["argv"][:13] == report["exporter_arguments"]
    assert payload["argv"][-1] == launch.MODELS[report["candidate_id"]]
    assert "PRIVATE_TOKEN" not in json.dumps(kwargs["env"])
    assert not ({"HF_TOKEN", "PYTHONPATH", "LD_PRELOAD"} & set(kwargs["env"]))
    assert kwargs["env"]["HF_HUB_OFFLINE"] == kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert kwargs["cwd"] == args.output
    assert all(
        (args.output / name).exists()
        for name in ("launch.json", "started.json", "exit.json", "COMPLETED.json")
    )


@pytest.mark.parametrize(
    "failure", ["cpu", "output", "receipt", "runtime", "lock", "busy", "changed"]
)
def test_prelaunch_failures_never_spawn(setup, monkeypatch, failure):
    args, fixture, _, _ = setup
    calls = fake_process(monkeypatch, args)
    held = None
    if failure == "cpu":
        args.mode = "cpu"
    elif failure == "output":
        args.output.mkdir()
        (args.output / "sentinel").write_text("preserve")
    elif failure == "receipt":
        args.expected_preflight_sha256 = "0" * 64
    elif failure == "runtime":
        args.expected_runtime_admission_sha256 = "0" * 64
    elif failure == "lock":
        held = launch.acquire_gpu_lock(0)
    elif failure == "busy":
        monkeypatch.setattr(
            launch, "check_idle", lambda *_a: (_ for _ in ()).throw(launch.LaunchError("busy"))
        )
    else:
        (fixture.run / "adapter/tokenizer.json").write_text("changed")
    try:
        with pytest.raises(
            (launch.LaunchError, BlockingIOError, artifact_tests.gate.PreflightError)
        ):
            launch.run_export(args)
    finally:
        if held is not None:
            os.close(held)
    assert not calls
    if failure == "output":
        assert (args.output / "sentinel").read_text() == "preserve"


@pytest.mark.parametrize("failure", ["exit", "timeout", "interrupt", "result", "post_input"])
def test_postlaunch_failure_preserves_without_retry(setup, monkeypatch, failure):
    args, fixture, gate, _ = setup
    calls = fake_process(
        monkeypatch,
        args,
        code=7 if failure == "exit" else 0,
        timeout=failure == "timeout",
        interrupt=failure == "interrupt",
    )
    if failure == "result":
        monkeypatch.setattr(
            launch,
            "verify_result",
            lambda *_a: (_ for _ in ()).throw(launch.LaunchError("partial")),
        )
    if failure == "post_input":
        original = gate.preflight
        count = 0

        def changing(args):
            nonlocal count
            count += 1
            if count > 1:
                (fixture.run / "adapter/tokenizer.json").write_text("changed")
            return original(args)

        monkeypatch.setattr(gate, "preflight", changing)
    with pytest.raises(
        (launch.LaunchError, subprocess.TimeoutExpired, InterruptedError, gate.PreflightError)
    ):
        launch.run_export(args)
    assert len(calls) == 1
    failed = json.loads((args.output / "FAILED.json").read_text())
    assert failed["automatic_retry"] is False
    assert failed["error_code"] in {
        "export_child_failed",
        "controller_timeout",
        "controller_interrupted",
        "partial",
        "file_hash_mismatch",
        "adapter_inventory",
    }
    assert failed["descendant_liveness"] == "unassessed"
    assert failed["child_pid_preserved"] == (43210 if failure in {"timeout", "interrupt"} else None)
    assert not (args.output / "COMPLETED.json").exists()


def test_replay_does_not_accept_competing_adapter_path(setup):
    _, _, gate, report = setup
    report["exporter_arguments"][8] = "/another/adapter"
    with pytest.raises(launch.LaunchError, match="adapter_path_binding"):
        launch.replay_args(gate, report)


def test_preflight_loader_checks_exact_reviewed_source():
    gate = launch.load_gate()
    assert launch.sha_file(gate.__file__) == launch.PREFLIGHT_SHA


def test_new_v2_directory_uses_bound_original_v1_gate(tmp_path, monkeypatch):
    original = HERE / "preflight_full_stage_export.py"
    v1 = tmp_path / "frozen-v1/preflight_full_stage_export.py"
    v1.parent.mkdir()
    v1.write_bytes(original.read_bytes())
    v2 = tmp_path / "new-v2/launch_full_stage_export.py"
    v2.parent.mkdir()
    v2.with_name("preflight_full_stage_export.py").write_text(
        "raise AssertionError('wrong sibling')\n"
    )
    monkeypatch.setattr(launch, "__file__", str(v2))
    report = {"inputs": [launch.file_receipt(v1)]}
    loaded = launch.load_gate(report)
    assert loaded.__file__ == str(v1)
    assert launch.sha_file(loaded.__file__) == launch.PREFLIGHT_SHA
    with pytest.raises(launch.LaunchError, match="source_changed"):
        launch.load_gate()
    report["inputs"].append(report["inputs"][0])
    with pytest.raises(launch.LaunchError, match="ambiguous_preflight"):
        launch.load_gate(report)


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "missing_manifest",
        "wrong_parent",
        "wrong_tool",
        "wrong_command",
        "wrong_gguf",
        "wrong_header",
        "wrong_merged",
        "retained_f16",
        "wrong_child",
        "auxiliary_five",
    ],
)
def test_real_post_export_verifier_tiny_artifacts(tmp_path, monkeypatch, mutation, auxiliary_setup):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    fixture = artifact_tests.Fixture(inputs, monkeypatch)
    gate = artifact_tests.gate
    report = json.loads(json.dumps(gate.preflight(fixture.args)))
    replay = launch.replay_args(gate, report)
    output = tmp_path / "output"
    output.mkdir()
    args = SimpleNamespace(output=output, python=Path(sys.executable))
    name = launch.MODELS[replay.candidate_id]
    merged = output / "merged-bf16"
    merged.mkdir()
    (merged / "model.safetensors").write_bytes(b"synthetic merged not loaded")
    final = output / f"{name}-Q4_K_M.gguf"
    final.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"synthetic not loaded")
    f16 = output / f"{name}-F16.gguf"
    log = output / "merge-and-quantize.log"
    log.write_text("synthetic not exported")
    commands = [
        [
            str(args.python),
            str(replay.llama_cpp / "convert_hf_to_gguf.py"),
            str(merged),
            "--outfile",
            str(f16),
            "--outtype",
            "f16",
        ],
        [str(replay.llama_cpp / "build/bin/llama-quantize"), str(f16), str(final), "Q4_K_M"],
    ]
    manifest = {
        "schema_version": 1,
        "model_name": name,
        "quantization": "Q4_K_M",
        "inputs": {
            "base": copy.deepcopy(report["base"]),
            "adapter": copy.deepcopy(report["adapter"]),
            "training_manifest": launch.file_receipt(replay.run_dir / "training-manifest.json"),
            "base_lineage": launch.file_receipt(replay.base_lineage),
        },
        "script": launch.file_receipt(replay.exporter),
        "llama_cpp": {
            "root": str(replay.llama_cpp),
            "git_commit": gate.LLAMA_COMMIT,
            "converter": launch.file_receipt(replay.llama_cpp / "convert_hf_to_gguf.py"),
            "quantizer": launch.file_receipt(replay.llama_cpp / "build/bin/llama-quantize"),
        },
        "commands": commands,
        "final_gguf": launch.file_receipt(final),
        "f16_gguf": {"path": str(f16), "retained": False},
        "merged": gate.Inputs().tree(merged),
        "log": launch.file_receipt(log),
    }
    write(output / "started.json", {"child_pid": 123})
    invocations = [
        {"argv": cmd, "parent_pid": 123, "child_pid": 124 + i, "lock_fd": 9}
        for i, cmd in enumerate(
            [["git", "-C", str(replay.llama_cpp), "rev-parse", "HEAD"], *commands]
        )
    ]
    if mutation == "wrong_parent":
        manifest["inputs"]["base"]["tree_sha256"] = "0" * 64
    elif mutation == "wrong_tool":
        manifest["llama_cpp"]["converter"]["sha256"] = "0" * 64
    elif mutation == "wrong_command":
        commands[1][-1] = "Q8_0"
    elif mutation == "wrong_gguf":
        final.write_bytes(b"changed")
    elif mutation == "wrong_header":
        final.write_bytes(b"WRONG HEADER but matching receipt")
        manifest["final_gguf"] = launch.file_receipt(final)
    elif mutation == "wrong_merged":
        (merged / "model.safetensors").write_bytes(b"changed")
    elif mutation == "retained_f16":
        f16.write_bytes(b"retained unexpectedly")
    elif mutation == "wrong_child":
        invocations[1]["parent_pid"] = 321
    elif mutation == "auxiliary_five":
        aux_args, _, _, aux_rows, _, _ = auxiliary_setup
        args.auxiliary_profile = aux_args.auxiliary_profile
        args.expected_auxiliary_profile_sha256 = aux_args.expected_auxiliary_profile_sha256
        invocations = [invocations[0], *aux_rows[1:3], *invocations[1:]]
        for index, row in enumerate(invocations):
            row["child_pid"] = 124 + index
            row["lock_fd"] = 3
    (output / "child-invocations.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in invocations)
    )
    if mutation != "missing_manifest":
        write(output / "quantization-manifest.json", manifest)
    if mutation and mutation != "auxiliary_five":
        with pytest.raises((launch.LaunchError, gate.PreflightError)):
            launch.verify_result(args, gate, replay, report)
    else:
        result = launch.verify_result(args, gate, replay, report)
        assert result["final_gguf"] == launch.file_receipt(final)
        assert "not_loaded" in result["verification"]


@pytest.mark.parametrize("text", ["123, python\n", "[Not Supported]\n"])
def test_idle_rejects_any_compute_output(monkeypatch, tmp_path, text):
    monkeypatch.setattr(launch, "command_output", lambda *_a, **_k: text)
    args = SimpleNamespace(gpu=0, output=tmp_path / "new")
    with pytest.raises(launch.LaunchError, match="gpu_busy"):
        launch.check_idle(args, {"commands": {"nvidia_smi": {"path": "/observed/nvidia-smi"}}}, {})


def test_bounded_duplicate_json_and_symlink_refused(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('{"x":1,"x":2}')
    with pytest.raises(launch.LaunchError, match="duplicate"):
        launch.read_json(path)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(launch.LaunchError, match="symlink"):
        launch.read_json(link)


def test_safe_failure_codes_exclude_untrusted_exception_text():
    assert launch.safe_error_code(launch.LaunchError("gpu_busy_preserved")) == "gpu_busy_preserved"
    assert "PRIVATE" not in launch.safe_error_code(OSError("PRIVATE prompt"))


@pytest.fixture
def auxiliary_setup(tmp_path):
    root = tmp_path / "aux"
    worker = root / "torch/_inductor/compile_worker/__main__.py"
    paths = [
        worker,
        worker.with_name("subproc_pool.py"),
        worker.parent.parent / "async_compile.py",
        root / "numpy/testing/_private/utils.py",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic source; never imported\n")
    lscpu = root / "bin/lscpu"
    lscpu.parent.mkdir()
    lscpu.write_text("synthetic executable; never executed")
    lscpu.chmod(0o700)
    profile = {
        "schema_version": 1,
        "kind": "muta_full_export_auxiliary_process_profile",
        "host": platform.node(),
        "uid": os.getuid(),
        "python_path": sys.executable,
        "worker_count": 30,
        "lscpu": launch.file_receipt(lscpu),
        "worker_main": launch.file_receipt(worker),
        "sources": [launch.file_receipt(path) for path in paths],
    }
    profile_path = root / "profile.json"
    sha = write(profile_path, profile)
    output = tmp_path / "attempt"
    output.mkdir()
    args = SimpleNamespace(
        python=Path(sys.executable),
        output=output,
        auxiliary_profile=profile_path,
        expected_auxiliary_profile_sha256=sha,
    )
    expected = [["git", "-C", "/llama", "rev-parse", "HEAD"], ["converter"], ["quantizer"]]
    worker_argv = [
        sys.executable,
        str(worker),
        "--pickler=torch._inductor.compile_worker.subproc_pool.SubprocPickler",
        "--kind=fork",
        "--workers=30",
        "--parent=123",
        "--read-fd=25",
        "--write-fd=28",
    ]
    rows = [
        {"argv": argv, "parent_pid": 123, "child_pid": 124 + i, "lock_fd": 3}
        for i, argv in enumerate([expected[0], "lscpu", worker_argv, *expected[1:]])
    ]
    (output / "child-invocations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    admission = {
        "python_probe": {
            "origins": {
                "torch": str(root / "torch/__init__.py"),
                "numpy": str(root / "numpy/__init__.py"),
            }
        }
    }
    environment = {"PATH": str(lscpu.parent)}
    return args, profile, expected, rows, admission, environment


def test_auxiliary_profile_and_exact_five_calls(auxiliary_setup):
    args, profile, expected, rows, admission, environment = auxiliary_setup
    assert launch.auxiliary_profile(args, admission, environment) == profile
    assert launch.verify_child_invocations(args, expected, {"child_pid": 123}, 3) == rows


def test_profile_also_allows_exact_original_three(auxiliary_setup):
    args, _, expected, rows, _, _ = auxiliary_setup
    rows = [rows[0], *rows[3:]]
    (args.output / "child-invocations.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    assert launch.verify_child_invocations(args, expected, {"child_pid": 123}, 3) == rows


@pytest.mark.parametrize(
    "mutation",
    [
        "sixth",
        "four",
        "reorder",
        "lscpu_list",
        "lscpu_shell",
        "worker_script",
        "worker_flag",
        "worker_count",
        "worker_parent",
        "worker_fd_same",
        "worker_fd_lock",
        "worker_fd_large",
        "worker_fd_negative",
        "worker_fd_bool",
        "pid_duplicate",
        "pid_parent",
        "pid_bool",
        "parent",
        "lock",
        "lock_bool",
        "extra_field",
        "duplicate_json",
        "no_profile",
        "wrong_fd",
    ],
)
def test_auxiliary_invocation_mutations_fail(auxiliary_setup, mutation):
    args, _, expected, rows, _, _ = auxiliary_setup
    if mutation == "sixth":
        rows.append(copy.deepcopy(rows[0]))
    elif mutation == "four":
        rows.pop(1)
    elif mutation == "reorder":
        rows[1], rows[2] = rows[2], rows[1]
    elif mutation == "lscpu_list":
        rows[1]["argv"] = ["lscpu"]
    elif mutation == "lscpu_shell":
        rows[1]["argv"] = "lscpu; anything"
    elif mutation == "worker_script":
        rows[2]["argv"][1] += ".other"
    elif mutation == "worker_flag":
        rows[2]["argv"][3] = "--kind=spawn"
    elif mutation == "worker_count":
        rows[2]["argv"][4] = "--workers=31"
    elif mutation == "worker_parent":
        rows[2]["argv"][5] = "--parent=999"
    elif mutation == "worker_fd_same":
        rows[2]["argv"][7] = "--write-fd=25"
    elif mutation == "worker_fd_lock":
        rows[2]["argv"][6] = "--read-fd=3"
    elif mutation == "worker_fd_large":
        rows[2]["argv"][6] = "--read-fd=1048577"
    elif mutation == "worker_fd_negative":
        rows[2]["argv"][6] = "--read-fd=-1"
    elif mutation == "worker_fd_bool":
        rows[2]["argv"][6] = True
    elif mutation == "pid_duplicate":
        rows[2]["child_pid"] = rows[1]["child_pid"]
    elif mutation == "pid_parent":
        rows[2]["child_pid"] = 123
    elif mutation == "pid_bool":
        rows[2]["child_pid"] = True
    elif mutation == "parent":
        rows[1]["parent_pid"] = 999
    elif mutation == "lock":
        rows[1]["lock_fd"] = 4
    elif mutation == "lock_bool":
        rows[1]["lock_fd"] = True
    elif mutation == "extra_field":
        rows[1]["shell"] = False
    elif mutation == "no_profile":
        args.auxiliary_profile = args.expected_auxiliary_profile_sha256 = None
    raw = "".join(json.dumps(row) + "\n" for row in rows)
    if mutation == "duplicate_json":
        raw = raw.replace('"parent_pid": 123', '"parent_pid": 123, "parent_pid": 123', 1)
    (args.output / "child-invocations.jsonl").write_text(raw)
    with pytest.raises(launch.LaunchError):
        launch.verify_child_invocations(
            args, expected, {"child_pid": 123}, 4 if mutation == "wrong_fd" else 3
        )


@pytest.mark.parametrize("mutation", ["hash", "file", "pair", "numpy", "origin", "path"])
def test_auxiliary_profile_identity_failures(auxiliary_setup, mutation):
    args, profile, _, _, admission, environment = auxiliary_setup
    if mutation == "hash":
        args.expected_auxiliary_profile_sha256 = "0" * 64
    elif mutation == "file":
        Path(profile["worker_main"]["path"]).write_text("changed")
    elif mutation == "pair":
        args.expected_auxiliary_profile_sha256 = None
    elif mutation == "numpy":
        admission["python_probe"]["origins"]["numpy"] = "/wrong/numpy/__init__.py"
    elif mutation == "origin":
        admission["python_probe"]["origins"]["torch"] = "/wrong/torch/__init__.py"
    else:
        environment["PATH"] = "/missing"
    with pytest.raises(launch.LaunchError):
        launch.auxiliary_profile(args, admission, environment)
    assert "PRIVATE" not in launch.safe_error_code(launch.LaunchError("PRIVATE prompt"))


def test_oversized_receipt_rejected_before_json(tmp_path, monkeypatch):
    path = tmp_path / "huge.json"
    path.write_bytes(b" " * 65)
    monkeypatch.setattr(launch, "MAX_JSON", 64)
    with pytest.raises(launch.LaunchError, match="receipt_size_bound"):
        launch.read_json(path)


def runtime_fixture(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir()

    def receipt(name):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic dependency " + name)
        return launch.file_receipt(path)

    python, git, nvidia = (receipt(n) for n in ("python", "git", "nvidia-smi"))
    deps = [
        receipt(n) for n in ("llama/convert_hf_to_gguf.py", "llama/conversion/module.py", "lib.so")
    ]
    origins = {m: receipt("packages/" + m + "/__init__.py") for m in (*launch.MODULES, "gguf")}
    deps.extend(origins.values())
    probe = {
        "packages": {p: {"version": "1", "root": str(root / "packages")} for p in launch.PACKAGES},
        "origins": {k: v["path"] for k, v in origins.items()},
        "version": "synthetic",
        "paths": [],
    }
    args = SimpleNamespace(
        python=Path(python["path"]),
        expected_preflight_sha256="a" * 64,
        expected_runtime_admission_sha256="b" * 64,
        gpu=0,
        output=tmp_path / "output",
    )
    replay = SimpleNamespace(
        candidate_id=next(iter(launch.MODELS)),
        llama_cpp=root / "llama",
        exporter=root / "exporter.py",
    )
    gate = SimpleNamespace(LLAMA_COMMIT="c" * 40)
    admission = {
        "schema_version": 1,
        "kind": "muta_full_export_runtime_admission",
        "mode": "gpu",
        "candidate_id": replay.candidate_id,
        "preflight_sha256": args.expected_preflight_sha256,
        "host": platform.node(),
        "uid": os.getuid(),
        "gpu": 0,
        "expires_unix": time.time() + 3600,
        "python": {**python, "resolved_path": python["path"]},
        "commands": {"git": git, "nvidia_smi": nvidia},
        "dependency_files": deps,
        "quantizer_native_libraries": [{"path": deps[2]["path"], "resolved_path": deps[2]["path"]}],
        "llama_cpp": {
            "root": str(replay.llama_cpp),
            "git_commit": gate.LLAMA_COMMIT,
            "status_porcelain": "",
        },
        "python_probe": probe,
        "python_probe_source_sha256": hashlib.sha256(launch.PROBE.encode()).hexdigest(),
        "coverage": {
            "kind": "enumerated_files_and_live_import_probe_not_hermetic",
            "all_transitive_dependencies_hashed": False,
        },
    }

    def command(argv, *_a, **_k):
        if "rev-parse" in argv:
            return gate.LLAMA_COMMIT + "\n"
        if "status" in argv:
            return ""
        return json.dumps(probe)

    monkeypatch.setattr(launch, "command_output", command)
    return args, gate, replay, admission


def test_runtime_measured_receipt_passes(tmp_path, monkeypatch):
    args, gate, replay, admission = runtime_fixture(tmp_path, monkeypatch)
    result = launch.verify_runtime(args, gate, replay, admission, {})
    assert result["coverage"]["all_transitive_dependencies_hashed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "expiry",
        "host",
        "uid",
        "python",
        "dependency",
        "origin",
        "native",
        "dirty",
        "probe",
        "coverage",
    ],
)
def test_runtime_drift_fails_closed(tmp_path, monkeypatch, mutation):
    args, gate, replay, admission = runtime_fixture(tmp_path, monkeypatch)
    if mutation == "expiry":
        admission["expires_unix"] = 0
    elif mutation == "host":
        admission["host"] = "another-host"
    elif mutation == "uid":
        admission["uid"] = -1
    elif mutation == "python":
        admission["python"]["sha256"] = "0" * 64
    elif mutation == "dependency":
        Path(admission["dependency_files"][0]["path"]).write_text("changed")
    elif mutation == "origin":
        admission["dependency_files"] = admission["dependency_files"][:-1]
    elif mutation == "native":
        admission["quantizer_native_libraries"][0]["resolved_path"] = "/missing"
    elif mutation == "dirty":
        monkeypatch.setattr(
            launch,
            "command_output",
            lambda argv, *_a, **_k: gate.LLAMA_COMMIT if "rev-parse" in argv else " M tracked.py\n",
        )
    elif mutation == "probe":
        original = copy.deepcopy(admission["python_probe"])
        admission["python_probe"] = {"changed": True}
        monkeypatch.setattr(
            launch,
            "command_output",
            lambda argv, *_a, **_k: (
                gate.LLAMA_COMMIT
                if "rev-parse" in argv
                else ("" if "status" in argv else json.dumps(original))
            ),
        )
    else:
        admission["coverage"]["all_transitive_dependencies_hashed"] = True
    with pytest.raises(launch.LaunchError):
        launch.verify_runtime(args, gate, replay, admission, {})


def test_grandchild_retains_lock_after_controller_and_exporter_disappear(tmp_path, monkeypatch):
    """Own short Python fixture only: no GPU, model, converter or real export."""
    monkeypatch.setattr(launch, "gpu_lock_path", lambda _gpu: tmp_path / "gpu.lock")
    lock = launch.acquire_gpu_lock(0)
    helper = tmp_path / "helper.py"
    helper.write_text("# Synthetic helper, intentionally empty.\n")
    exporter = tmp_path / "exporter.py"
    marker, stop = tmp_path / "grandchild.pid", tmp_path / "stop"
    child_code = f"import os,time,pathlib; p=pathlib.Path({str(marker)!r}); p.write_text(str(os.getpid())); s=pathlib.Path({str(stop)!r});\nwhile not s.exists(): time.sleep(0.01)"
    exporter.write_text(
        f"import subprocess,sys,time\nsubprocess.Popen([sys.executable, '-c', {child_code!r}])\ntime.sleep(30)\n"
    )
    payload = {
        "lock_fd": lock,
        "invocations": str(tmp_path / "invocations.jsonl"),
        "helper": str(helper),
        "helper_sha256": launch.sha_file(helper),
        "argv": [str(exporter)],
        "exporter_sha256": launch.sha_file(exporter),
    }
    process = subprocess.Popen(
        [sys.executable, "-E", "-s", "-B", "-c", launch.BOOTSTRAP, json.dumps(payload)],
        pass_fds=(lock,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    os.close(lock)  # Simulates controller death; exporter is sole remaining owner.
    child_pid = None
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.01)
        assert marker.exists()
        child_pid = int(marker.read_text())
        invocations = [
            json.loads(row) for row in (tmp_path / "invocations.jsonl").read_text().splitlines()
        ]
        assert invocations[0]["child_pid"] == child_pid
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        os.kill(child_pid, 0)
        assert (
            launch.known_descendants(tmp_path) == []
        )  # Different filename is intentionally not inferred.
        (tmp_path / "child-invocations.jsonl").write_text(
            (tmp_path / "invocations.jsonl").read_text()
        )
        assert launch.known_descendants(tmp_path) == [child_pid]
        with pytest.raises(BlockingIOError):
            launch.acquire_gpu_lock(0)
    finally:
        stop.write_text("stop owned fixture")
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        deadline = time.monotonic() + 5
        acquired = None
        while time.monotonic() < deadline:
            try:
                acquired = launch.acquire_gpu_lock(0)
                break
            except BlockingIOError:
                time.sleep(0.01)
        assert acquired is not None
        os.close(acquired)
        if process.stderr is not None:
            process.stderr.close()
