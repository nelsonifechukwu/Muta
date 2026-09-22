"""Guard one fresh full-stage export; CPU admission and automatic retries unsupported.

Requires externally pinned artifact and measured-runtime receipts. This is not
a hermetic environment validator or a GGUF correctness/inference test.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time
import types
from pathlib import Path

PREFLIGHT_SHA = "79e2cd8b226aac23b64aa398a98a439096579ddd97bb38f1387e7805f1086e57"
MAX_JSON = 32 * 1024 * 1024
MODELS = {
    "full-best-clean-private-enriched": "Muta-Round2-Full-clean-r16-lr1e5-300350-bestdev",
    "full-best-warm-private-enriched": "Muta-Round2-Full-warm-fresh-r16-lr5e6-300350-bestdev",
    "full-best-warm-pilot-continuation": "Muta-Round2-Full-warm-pilot-cont-r16-lr5e6-300350-bestdev",
}
PACKAGES = (
    "torch",
    "peft",
    "transformers",
    "accelerate",
    "numpy",
    "safetensors",
    "huggingface-hub",
    "sentencepiece",
    "tokenizers",
)
MODULES = (
    "torch",
    "peft",
    "transformers",
    "accelerate",
    "numpy",
    "safetensors",
    "huggingface_hub",
    "sentencepiece",
    "tokenizers",
)

# No ML import. Simulate the exporter's script-directory search path; inspect the
# converter's gguf origin separately. Root uses this same literal for admission.
PROBE = r"""
import importlib.metadata as m, importlib.util as u, json, os, sys
exporter, llama = sys.argv[1:]
sys.path = [exporter] + [p for p in sys.path if p and p != os.getcwd()]
packages = ("torch", "peft", "transformers", "accelerate", "numpy", "safetensors", "huggingface-hub", "sentencepiece", "tokenizers")
modules = ("torch", "peft", "transformers", "accelerate", "numpy", "safetensors", "huggingface_hub", "sentencepiece", "tokenizers")
result = {"version": sys.version, "executable": sys.executable, "paths": sys.path,
          "packages": {p: {"version": m.version(p), "root": str(m.distribution(p).locate_file(""))} for p in packages},
          "origins": {p: u.find_spec(p).origin for p in modules}}
sys.path = [llama, os.path.join(llama, "gguf-py")] + sys.path[1:]
result["converter_paths"] = sys.path
result["origins"]["gguf"] = u.find_spec("gguf").origin
print(json.dumps(result, sort_keys=True))
"""

# The unchanged exporter otherwise closes the inherited lock FD when it starts
# converter/quantizer processes. Propagate it to every direct subprocess, record
# actual argv, and execute only the already hash-checked source bytes.
BOOTSTRAP = r"""
import hashlib, json, os, subprocess, sys, types
payload = json.loads(sys.argv[1])
fd = payload["lock_fd"]
os.fstat(fd)
os.set_inheritable(fd, True)
original = subprocess.Popen
class LockedPopen(original):
    def __init__(self, args, *pos, **kw):
        if kw.get("shell") or kw.get("close_fds") is False:
            raise RuntimeError("unsupported child process policy")
        kw["pass_fds"] = tuple(sorted(set(kw.get("pass_fds", ())) | {fd}))
        super().__init__(args, *pos, **kw)
        with open(payload["invocations"], "a", encoding="utf-8") as log:
            log.write(json.dumps({"argv": args, "parent_pid": os.getpid(), "child_pid": self.pid, "lock_fd": fd}) + "\n")
subprocess.Popen = LockedPopen
def source(path, expected):
    with open(path, "rb") as h:
        raw = h.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("child source changed")
    return raw
helper = types.ModuleType("campaign_io")
helper.__file__ = payload["helper"]
sys.modules["campaign_io"] = helper
exec(compile(source(payload["helper"], payload["helper_sha256"]), helper.__file__, "exec"), helper.__dict__)
exporter = payload["argv"][0]
sys.path = [os.path.dirname(exporter)] + [p for p in sys.path if p and p != os.getcwd()]
sys.argv = payload["argv"]
namespace = {"__name__": "__main__", "__file__": exporter, "__package__": None}
exec(compile(source(exporter, payload["exporter_sha256"]), exporter, "exec"), namespace)
"""


class LaunchError(ValueError):
    pass


def safe_error_code(error):
    if type(error).__name__ in {"LaunchError", "PreflightError"}:
        code = str(error)
        if re.fullmatch(r"[a-z0-9_]{1,128}", code):
            return code
    if isinstance(error, subprocess.TimeoutExpired):
        return "controller_timeout"
    if isinstance(error, (InterruptedError, KeyboardInterrupt)):
        return "controller_interrupted"
    return "invalid_or_failed_input_or_process"


def known_descendants(output):
    """Evidence only: a recorded PID is not a claim that it is still alive."""
    path = output / "child-invocations.jsonl"
    if not path.is_file() or path.is_symlink():
        return []
    result = []
    try:
        with path.open("rb") as handle:
            for _ in range(32):
                line = handle.readline(1024 * 1024 + 1)
                if not line or len(line) > 1024 * 1024:
                    break
                row = json.loads(line)
                pid = row.get("child_pid")
                if type(pid) is int and pid > 0:
                    result.append(pid)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return sorted(set(result))


def require(condition, code):
    if not condition:
        raise LaunchError(code)


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def path_file(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink_path")
    require(path.is_file() and 0 < path.stat().st_size <= 8 * 1024**3, "regular_file_required")
    return path


def file_receipt(path):
    path = path_file(path)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha_file(path)}


def read_json(path, expected=None):
    path = path_file(path)
    with path.open("rb") as handle:
        raw = handle.read(MAX_JSON + 1)
    require(len(raw) <= MAX_JSON, "receipt_size_bound")
    if expected is not None:
        require(
            re.fullmatch(r"[0-9a-f]{64}", expected) is not None
            and hashlib.sha256(raw).hexdigest() == expected,
            "receipt_hash_mismatch",
        )

    return json_object(raw)


def json_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    value = json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(LaunchError("nonfinite_json")),
    )
    require(isinstance(value, dict), "object_required")
    return value


def auxiliary_profile(args, admission=None, environment=None):
    path = getattr(args, "auxiliary_profile", None)
    expected = getattr(args, "expected_auxiliary_profile_sha256", None)
    require(bool(path) == bool(expected), "auxiliary_profile_pair")
    if path is None:
        return None
    profile = read_json(path, expected)
    require(
        set(profile)
        == {
            "schema_version",
            "kind",
            "host",
            "uid",
            "python_path",
            "worker_count",
            "lscpu",
            "worker_main",
            "sources",
        }
        and profile["schema_version"] == 1
        and profile["kind"] == "muta_full_export_auxiliary_process_profile"
        and profile["host"] == platform.node()
        and type(profile["uid"]) is int
        and profile["uid"] == os.getuid()
        and profile["python_path"] == str(args.python)
        and type(profile["worker_count"]) is int
        and 1 <= profile["worker_count"] <= 256,
        "auxiliary_profile_identity",
    )
    sources = profile["sources"]
    require(isinstance(sources, list) and 4 <= len(sources) <= 16, "auxiliary_source_bound")
    seen = set()
    for receipt in [profile["lscpu"], profile["worker_main"], *sources]:
        require(file_receipt(receipt["path"]) == receipt, "auxiliary_source_changed")
    for receipt in sources:
        require(receipt["path"] not in seen, "auxiliary_duplicate_source")
        seen.add(receipt["path"])
    worker = Path(profile["worker_main"]["path"])
    require(
        worker.name == "__main__.py"
        and worker.parent.name == "compile_worker"
        and worker.parent.parent.name == "_inductor"
        and {
            str(worker),
            str(worker.with_name("subproc_pool.py")),
            str(worker.parent.parent / "async_compile.py"),
        }
        <= seen,
        "auxiliary_worker_sources",
    )
    if admission is not None:
        origin = Path(admission["python_probe"]["origins"]["torch"])
        numpy_origin = Path(admission["python_probe"]["origins"]["numpy"])
        require(
            worker == origin.parent / "_inductor/compile_worker/__main__.py"
            and str(numpy_origin.parent / "testing/_private/utils.py") in seen
            and shutil.which("lscpu", path=environment["PATH"]) == profile["lscpu"]["path"],
            "auxiliary_resolution",
        )
    return profile


def verify_child_invocations(args, expected_commands, started, lock_fd=None):
    profile = auxiliary_profile(args)
    invocations = []
    with path_file(args.output / "child-invocations.jsonl").open("rb") as handle:
        while line := handle.readline(1024 * 1024 + 1):
            require(len(line) <= 1024 * 1024 and len(invocations) < 5, "child_invocation_bound")
            invocations.append(json_object(line))
    require(len(invocations) in ({3, 5} if profile else {3}), "actual_child_invocations")
    pids = set()
    observed_fd = invocations[0].get("lock_fd")
    require(type(observed_fd) is int and 3 <= observed_fd <= 1048576, "child_lock_fd")
    require(lock_fd is None or observed_fd == lock_fd, "child_lock_fd")
    for row in invocations:
        require(
            set(row) == {"argv", "parent_pid", "child_pid", "lock_fd"}
            and type(row["parent_pid"]) is int
            and row["parent_pid"] == started["child_pid"]
            and type(row["child_pid"]) is int
            and row["child_pid"] > 0
            and row["child_pid"] != row["parent_pid"]
            and row["child_pid"] not in pids
            and type(row["lock_fd"]) is int
            and row["lock_fd"] == observed_fd,
            "actual_child_invocations",
        )
        pids.add(row["child_pid"])
    actual = [row["argv"] for row in invocations]
    if len(actual) == 5:
        require(actual[1] == "lscpu", "auxiliary_lscpu_argv")
        worker = actual[2]
        require(isinstance(worker, list) and len(worker) == 8, "auxiliary_worker_argv")
        require(
            worker[:6]
            == [
                str(args.python),
                profile["worker_main"]["path"],
                "--pickler=torch._inductor.compile_worker.subproc_pool.SubprocPickler",
                "--kind=fork",
                f"--workers={profile['worker_count']}",
                f"--parent={started['child_pid']}",
            ],
            "auxiliary_worker_argv",
        )
        pipes = []
        for value, prefix in zip(worker[6:], ("--read-fd=", "--write-fd="), strict=True):
            require(
                isinstance(value, str)
                and re.fullmatch(re.escape(prefix) + r"[1-9][0-9]{0,6}", value),
                "auxiliary_worker_fd",
            )
            pipe = int(value[len(prefix) :])
            require(
                3 <= pipe <= 1048576 and pipe != observed_fd and pipe not in pipes,
                "auxiliary_worker_fd",
            )
            pipes.append(pipe)
        actual = [actual[0], *actual[3:]]
    require(actual == expected_commands, "actual_child_invocations")
    return invocations


def write_json(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.write("\n")


def load_gate(report=None):
    path = Path(__file__).with_name("preflight_full_stage_export.py")
    if report is not None:
        rows = report.get("inputs")
        require(isinstance(rows, list) and 1 <= len(rows) <= 512, "input_count_bound")
        matches = [r for r in rows if isinstance(r, dict) and r.get("sha256") == PREFLIGHT_SHA]
        require(len(matches) == 1, "ambiguous_preflight_authority")
        path = Path(matches[0]["path"])
        require(
            path.is_absolute()
            and path.name == "preflight_full_stage_export.py"
            and file_receipt(path) == matches[0],
            "preflight_input_identity",
        )
    path = path_file(path)
    with path.open("rb") as handle:
        raw = handle.read(1024 * 1024 + 1)
    require(
        len(raw) <= 1024 * 1024 and hashlib.sha256(raw).hexdigest() == PREFLIGHT_SHA,
        "preflight_source_changed",
    )
    module = types.ModuleType("_full_export_gate")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 -- exact reviewed SHA
    return module


def replay_args(gate, report):
    require(
        report.get("status") == "artifact_preflight_passed"
        and report.get("scope") == "frozen_v3_fresh_stage_selected_adapter_only"
        and report.get("runtime_admission") == "not_assessed"
        and report.get("candidate_id") in MODELS,
        "unsupported_artifact_receipt",
    )
    rows = report["inputs"]
    require(isinstance(rows, list) and 1 <= len(rows) <= 512, "input_count_bound")

    def by_sha(sha, name=None):
        matches = [
            Path(r["path"])
            for r in rows
            if r["sha256"] == sha and (name is None or Path(r["path"]).name == name)
        ]
        require(len(matches) == 1, "ambiguous_input_authority")
        return matches[0]

    full_config = by_sha(gate.CONFIG_SHA)
    config = read_json(full_config, gate.CONFIG_SHA)
    argv = report["exporter_arguments"]
    names = (
        "--base",
        "--base-lineage",
        "--tokenizer",
        "--adapter",
        "--training-manifest",
        "--llama-cpp",
    )
    require(len(argv) == 13 and argv[1::2] == list(names), "exporter_arguments")
    values = dict(zip(names, argv[2::2], strict=True))
    run = Path(report["run_directory"])
    require(
        all(
            Path(p).is_absolute() and str(Path(os.path.abspath(p))) == p
            for p in [argv[0], *values.values(), str(run)]
        ),
        "absolute_input_paths_required",
    )
    require(
        values["--adapter"] == values["--tokenizer"] == str(run / "adapter")
        and values["--training-manifest"] == str(run / "training-manifest.json"),
        "adapter_path_binding",
    )
    require(by_sha(PREFLIGHT_SHA) == Path(gate.__file__), "preflight_path_changed")
    authority = config["runtime_input_authority"]
    return argparse.Namespace(
        full_config=full_config,
        expected_full_config_sha256=gate.CONFIG_SHA,
        candidate_id=report["candidate_id"],
        run_dir=run,
        training_code=by_sha(
            config["source_code"]["trainer_sha256"], "train_lora_round2.py"
        ).parent,
        base=Path(values["--base"]),
        base_lineage=Path(values["--base-lineage"]),
        dataset_manifest=by_sha(authority["dataset"]["manifest_sha256"]),
        validation_manifest=by_sha(authority["validation"]["manifest_sha256"]),
        exporter=Path(argv[0]),
        expected_exporter_sha256=gate.EXPORTER_SHA,
        llama_cpp=Path(values["--llama-cpp"]),
        reference_export_manifest=by_sha(gate.REFERENCE_SHA),
        expected_reference_export_manifest_sha256=gate.REFERENCE_SHA,
    )


def gpu_lock_path(gpu):
    return Path("/tmp") / f"muta-round2-full-uid-{os.getuid()}-gpu-{gpu}.lock"


def acquire_gpu_lock(gpu):
    descriptor = os.open(gpu_lock_path(gpu), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        require(info.st_uid == os.getuid() and stat.S_ISREG(info.st_mode), "unsafe_gpu_lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def command_output(command, environment, *, cwd, limit=MAX_JSON):
    # Short fixed probes only. Disk-backed output gives a strict read bound and
    # avoids buffering an arbitrary dependency command response in memory.
    import tempfile

    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        result = subprocess.run(
            command, stdout=output, stderr=errors, env=environment, cwd=cwd, timeout=30, check=False
        )
        output.seek(0)
        errors.seek(0)
        raw, error = output.read(limit + 1), errors.read(limit + 1)
    require(result.returncode == 0 and len(raw) <= limit and len(error) <= limit, "probe_failed")
    return raw.decode("utf-8")


def environment_for(args, admission):
    git_dir = str(Path(admission["commands"]["git"]["path"]).parent)
    return {
        "PATH": git_dir + ":/usr/bin:/bin",
        "HOME": str(args.output / "isolated-home"),
        "HF_HOME": str(args.output / "isolated-home/hf"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "CUDA_VISIBLE_DEVICES": str(args.gpu),
        "LC_ALL": "C.UTF-8",
    }


def verify_runtime(args, gate, replay, admission, environment):
    require(
        admission.get("schema_version") == 1
        and admission.get("kind") == "muta_full_export_runtime_admission"
        and admission.get("mode") == "gpu"
        and admission.get("candidate_id") == replay.candidate_id
        and admission.get("preflight_sha256") == args.expected_preflight_sha256
        and admission.get("host") == platform.node()
        and admission.get("uid") == os.getuid()
        and admission.get("gpu") == args.gpu,
        "runtime_admission_identity",
    )
    expiry = admission.get("expires_unix")
    require(
        type(expiry) in (float, int) and time.time() < expiry <= time.time() + 86400,
        "runtime_admission_expired",
    )
    python = admission["python"]
    require(
        str(args.python) == python["path"]
        and args.python.is_absolute()
        and str(args.python.resolve(strict=True)) == python["resolved_path"],
        "python_identity",
    )
    require(
        file_receipt(python["resolved_path"])
        == {"path": python["resolved_path"], "bytes": python["bytes"], "sha256": python["sha256"]},
        "python_identity",
    )
    require(set(admission["commands"]) == {"git", "nvidia_smi"}, "command_set")
    for receipt in admission["commands"].values():
        require(file_receipt(receipt["path"]) == receipt, "command_identity")
    dependencies = admission["dependency_files"]
    require(isinstance(dependencies, list) and 1 <= len(dependencies) <= 10000, "dependency_bound")
    seen = set()
    for receipt in dependencies:
        require(
            receipt["path"] not in seen and file_receipt(receipt["path"]) == receipt,
            "dependency_identity",
        )
        seen.add(receipt["path"])
    coverage = admission["coverage"]
    require(
        coverage.get("kind") == "enumerated_files_and_live_import_probe_not_hermetic"
        and coverage.get("all_transitive_dependencies_hashed") is False,
        "unsupported_coverage_claim",
    )
    native = admission["quantizer_native_libraries"]
    require(isinstance(native, list) and 1 <= len(native) <= 128, "native_dependency_coverage")
    for library in native:
        require(
            set(library) == {"path", "resolved_path"}
            and Path(library["path"]).is_absolute()
            and str(Path(library["path"]).resolve(strict=True)) == library["resolved_path"]
            and library["resolved_path"] in seen,
            "native_dependency_coverage",
        )
    # Exact approved list comes from independently reviewed ldd evidence. This
    # verifies those files; it does not pretend to rediscover every dlopen edge.
    require(
        admission["llama_cpp"]
        == {"root": str(replay.llama_cpp), "git_commit": gate.LLAMA_COMMIT, "status_porcelain": ""},
        "llama_admission",
    )
    git = admission["commands"]["git"]["path"]
    commit = command_output(
        [git, "-C", str(replay.llama_cpp), "rev-parse", "HEAD"], environment, cwd=args.output.parent
    ).strip()
    clean = command_output(
        [git, "-C", str(replay.llama_cpp), "status", "--porcelain=v1", "--untracked-files=all"],
        environment,
        cwd=args.output.parent,
    )
    require(commit == gate.LLAMA_COMMIT and clean == "", "llama_checkout_changed")
    raw = command_output(
        [
            str(args.python),
            "-E",
            "-s",
            "-B",
            "-c",
            PROBE,
            str(replay.exporter.parent),
            str(replay.llama_cpp),
        ],
        environment,
        cwd=args.output.parent,
    )
    probe = json.loads(raw)
    require(
        admission.get("python_probe_source_sha256") == hashlib.sha256(PROBE.encode()).hexdigest(),
        "python_probe_source",
    )
    require(probe == admission["python_probe"], "python_probe_changed")
    require(
        set(probe["packages"]) == set(PACKAGES)
        and set(probe["origins"]) == {*MODULES, "gguf"}
        and set(probe["origins"].values()) <= seen,
        "import_origin_coverage",
    )
    require(
        str(replay.llama_cpp / "convert_hf_to_gguf.py") in seen, "converter_dependency_coverage"
    )
    require(
        any(Path(p).is_relative_to(replay.llama_cpp / "conversion") for p in seen),
        "converter_dependency_coverage",
    )
    return {
        "admission_sha256": args.expected_runtime_admission_sha256,
        "dependency_count": len(seen),
        "coverage": coverage,
        "python_probe": probe,
    }


def check_idle(args, admission, environment):
    text = command_output(
        [
            admission["commands"]["nvidia_smi"]["path"],
            f"--id={args.gpu}",
            "--query-compute-apps=pid,process_name",
            "--format=csv,noheader,nounits",
        ],
        environment,
        cwd=args.output.parent,
        limit=1024 * 1024,
    )
    require(not text.strip(), "gpu_busy_preserved")
    return {"gpu": args.gpu, "checked_unix": time.time(), "compute_processes": []}


def claim_output(args, report):
    output = Path(os.path.abspath(args.output))
    parent = output.parent
    require(
        parent.is_dir() and not any(p.is_symlink() for p in (parent, *parent.parents)),
        "unsafe_output_parent",
    )
    forbidden = [Path(row["path"]).parent for row in report["inputs"]]
    forbidden.extend([Path(report["run_directory"])])
    require(
        not any(p == output or p in output.parents for p in forbidden), "output_inside_input_tree"
    )
    output.mkdir(mode=0o700, exist_ok=False)
    (output / "isolated-home").mkdir(mode=0o700)
    return output


def verify_result(args, gate, replay, report):
    manifest_path = args.output / "quantization-manifest.json"
    result = read_json(manifest_path)
    model_name = MODELS[replay.candidate_id]
    final = args.output / f"{model_name}-Q4_K_M.gguf"
    f16 = args.output / f"{model_name}-F16.gguf"
    merged = args.output / "merged-bf16"
    require(
        result.get("schema_version") == 1
        and result.get("model_name") == model_name
        and result.get("quantization") == "Q4_K_M",
        "export_manifest_identity",
    )
    require(
        gate.stripped_tree(result["inputs"]["base"]) == report["base"]
        and gate.stripped_tree(result["inputs"]["adapter"]) == report["adapter"],
        "export_input_binding",
    )
    for key, path in (
        ("training_manifest", replay.run_dir / "training-manifest.json"),
        ("base_lineage", replay.base_lineage),
    ):
        require(result["inputs"][key] == file_receipt(path), "export_input_binding")
    require(result["script"] == file_receipt(replay.exporter), "export_source_binding")
    require(
        result["llama_cpp"]
        == {
            "root": str(replay.llama_cpp),
            "git_commit": gate.LLAMA_COMMIT,
            "converter": file_receipt(replay.llama_cpp / "convert_hf_to_gguf.py"),
            "quantizer": file_receipt(replay.llama_cpp / "build/bin/llama-quantize"),
        },
        "export_tool_binding",
    )
    expected_commands = [
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
    require(result["commands"] == expected_commands, "export_commands")
    started = read_json(args.output / "started.json")
    expected_invocations = [
        ["git", "-C", str(replay.llama_cpp), "rev-parse", "HEAD"],
        *expected_commands,
    ]
    launch_path = args.output / "launch.json"
    lock_fd = None
    if launch_path.exists():
        command = read_json(launch_path)["argv"]
        lock_fd = json_object(command[-1])["lock_fd"]
    invocations = verify_child_invocations(args, expected_invocations, started, lock_fd)
    require(result["final_gguf"] == file_receipt(final), "gguf_hash")
    with final.open("rb") as handle:
        header = handle.read(24)
    require(
        len(header) == 24
        and header[:4] == b"GGUF"
        and struct.unpack("<I", header[4:8])[0] == 3
        and all(n > 0 for n in struct.unpack("<QQ", header[8:])),
        "gguf_header",
    )
    require(
        result["f16_gguf"]["path"] == str(f16)
        and result["f16_gguf"]["retained"] is False
        and not f16.exists()
        and not f16.is_symlink(),
        "unexpected_f16_retention",
    )
    inputs = gate.Inputs()
    require(
        gate.stripped_tree(inputs.tree(merged)) == gate.stripped_tree(result["merged"]),
        "merged_tree",
    )
    require(
        result["merged"]["root"] == str(merged)
        and result["log"] == file_receipt(args.output / "merge-and-quantize.log"),
        "export_log",
    )
    inputs.finish()
    return {
        "quantization_manifest": file_receipt(manifest_path),
        "final_gguf": file_receipt(final),
        "merged": gate.stripped_tree(result["merged"]),
        "child_invocations": invocations,
        "auxiliary_profile": file_receipt(args.auxiliary_profile)
        if getattr(args, "auxiliary_profile", None)
        else None,
        "verification": "hashes_and_basic_GGUF_header_not_loaded_or_semantically_validated",
    }


def run_export(args):
    require(args.mode == "gpu", "unsupported_cpu")
    require(
        type(args.gpu) is int and args.gpu >= 0 and 1 <= args.max_seconds <= 86400, "invalid_limits"
    )
    args.output = Path(os.path.abspath(args.output))
    require(not args.output.exists() and not args.output.is_symlink(), "output_exists_preserved")
    report = read_json(args.preflight_receipt, args.expected_preflight_sha256)
    gate = load_gate(report)
    admission = read_json(args.runtime_admission, args.expected_runtime_admission_sha256)
    replay = replay_args(gate, report)
    environment = environment_for(args, admission)
    descriptor, process, claimed = None, None, False
    old_handlers = {}

    def interrupted(number, _frame):
        raise InterruptedError(f"signal_{number}")

    try:
        descriptor = acquire_gpu_lock(args.gpu)
        runtime = verify_runtime(args, gate, replay, admission, environment)
        auxiliary_profile(args, admission, environment)
        check_idle(args, admission, environment)
        require(
            json.loads(json.dumps(gate.preflight(replay))) == report, "artifact_preflight_changed"
        )
        require(
            read_json(args.preflight_receipt, args.expected_preflight_sha256) == report
            and read_json(args.runtime_admission, args.expected_runtime_admission_sha256)
            == admission,
            "admission_changed",
        )
        args.output = claim_output(args, report)
        claimed = True
        write_json(args.output / "artifact-preflight.json", report)
        exporter_argv = [
            *report["exporter_arguments"],
            "--output",
            str(args.output),
            "--model-name",
            MODELS[replay.candidate_id],
        ]
        payload = {
            "lock_fd": descriptor,
            "invocations": str(args.output / "child-invocations.jsonl"),
            "helper": str(replay.exporter.with_name("campaign_io.py")),
            "helper_sha256": gate.HELPER_SHA,
            "exporter_sha256": gate.EXPORTER_SHA,
            "argv": exporter_argv,
        }
        command = [
            str(args.python),
            "-E",
            "-s",
            "-B",
            "-c",
            BOOTSTRAP,
            json.dumps(payload, sort_keys=True),
        ]
        runtime = verify_runtime(args, gate, replay, admission, environment)
        auxiliary_profile(args, admission, environment)
        idle = check_idle(args, admission, environment)
        write_json(
            args.output / "launch.json",
            {
                "schema_version": 1,
                "candidate_id": replay.candidate_id,
                "started_unix": time.time(),
                "controller_pid": os.getpid(),
                "argv": command,
                "environment": environment,
                "cwd": str(args.output),
                "runtime": runtime,
                "gpu_idle": idle,
                "gpu_lock": str(gpu_lock_path(args.gpu)),
                "launcher": file_receipt(Path(__file__)),
                "preflight_source_sha256": PREFLIGHT_SHA,
                "preflight_sha256": args.expected_preflight_sha256,
                "bootstrap_sha256": hashlib.sha256(BOOTSTRAP.encode()).hexdigest(),
                "selection": report["selection"],
                "auxiliary_profile": file_receipt(args.auxiliary_profile)
                if getattr(args, "auxiliary_profile", None)
                else None,
            },
        )
        for number in (signal.SIGTERM, signal.SIGINT):
            old_handlers[number] = signal.signal(number, interrupted)
        with (
            (args.output / "stdout.log").open("xb") as stdout,
            (args.output / "stderr.log").open("xb") as stderr,
        ):
            process = subprocess.Popen(
                command,
                stdout=stdout,
                stderr=stderr,
                env=environment,
                cwd=args.output,
                start_new_session=True,
                pass_fds=(descriptor,),
            )
            write_json(
                args.output / "started.json",
                {"child_pid": process.pid, "started_unix": time.time()},
            )
            returncode = process.wait(timeout=args.max_seconds)
        write_json(
            args.output / "exit.json",
            {"child_pid": process.pid, "returncode": returncode, "exited_unix": time.time()},
        )
        require(returncode == 0, "export_child_failed")
        require(
            json.loads(json.dumps(gate.preflight(replay))) == report, "post_export_input_changed"
        )
        verify_runtime(args, gate, replay, admission, environment)
        auxiliary_profile(args, admission, environment)
        result = verify_result(args, gate, replay, report)
        result.update(
            state="complete",
            candidate_id=replay.candidate_id,
            child_pid=process.pid,
            automatic_retry=False,
            inference_tested=False,
            selection=report["selection"],
        )
        result["launch_evidence"] = {
            name: file_receipt(args.output / name)
            for name in ("launch.json", "started.json", "exit.json", "artifact-preflight.json")
        }
        result["runtime_admission_sha256"] = args.expected_runtime_admission_sha256
        result["expected_preflight_sha256"] = args.expected_preflight_sha256
        # Empty stderr/stdout are legitimate; hash directly without nonempty-file gate.
        result["logs"] = {
            name: {
                "bytes": (args.output / name).stat().st_size,
                "sha256": sha_file(args.output / name),
            }
            for name in ("stdout.log", "stderr.log", "child-invocations.jsonl")
        }
        write_json(args.output / "COMPLETED.json", result)
        return result
    except BaseException as error:
        if claimed:
            live = process is not None and process.poll() is None
            write_json(
                args.output / "FAILED.json",
                {
                    "state": "controller_stopped_child_preserved"
                    if live
                    else ("descendant_liveness_unassessed" if process is not None else "failed"),
                    "error_type": type(error).__name__,
                    "error_code": safe_error_code(error),
                    "automatic_retry": False,
                    "child_pid_preserved": process.pid if live else None,
                    "known_descendant_pids": known_descendants(args.output),
                    "descendant_liveness": "unassessed"
                    if process is not None
                    else "no_child_started",
                    "returncode": None if process is None else process.poll(),
                    "failed_unix": time.time(),
                },
            )
        raise
    finally:
        for number, handler in old_handlers.items():
            signal.signal(number, handler)
        if descriptor is not None:
            os.close(descriptor)  # Never LOCK_UN: a preserved descendant retains exclusivity.


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("preflight-receipt", "runtime-admission", "python", "output"):
        result.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-preflight-sha256", "expected-runtime-admission-sha256"):
        result.add_argument("--" + name, required=True)
    result.add_argument("--mode", choices=("gpu", "cpu"), default="gpu")
    result.add_argument("--gpu", type=int, default=0)
    result.add_argument("--max-seconds", type=int, default=7200)
    result.add_argument("--auxiliary-profile", type=Path)
    result.add_argument("--expected-auxiliary-profile-sha256")
    return result


def main(argv=None):
    try:
        result = run_export(parser().parse_args(argv))
        print(
            json.dumps(
                {
                    "state": result["state"],
                    "candidate_id": result["candidate_id"],
                    "inference_tested": False,
                }
            )
        )
        return 0
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- generic CLI diagnostics, preserve details in receipts
        print("Export controller stopped: " + safe_error_code(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
