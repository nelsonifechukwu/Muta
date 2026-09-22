"""Collect metadata-only runtime evidence; never grant export admission.

Uses the exact reviewed launcher's stdlib probe. No model/GPU/export/SSH call.
The output kind is deliberately rejected by the launcher until external review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import time
import types
from pathlib import Path

LAUNCHER_SHA = "16f10222dab4be4facc7e04e6f6a6215d6d0d17d312887a4308445a85df9abb0"
DRAFT_KIND = "muta_full_export_runtime_evidence_draft"
MAX_ENTRIES = 10000


class EvidenceError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise EvidenceError(code)


def load_launcher(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), "launcher_symlink")
    with path.open("rb") as handle:
        raw = handle.read(1024 * 1024 + 1)
    require(
        len(raw) <= 1024 * 1024 and hashlib.sha256(raw).hexdigest() == LAUNCHER_SHA,
        "launcher_source_changed",
    )
    module = types.ModuleType("_runtime_evidence_launcher")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 -- exact reviewed SHA
    return module


def python_sources(root):
    """Bounded scandir, including tracked/untracked sources, without following links."""
    require(root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)), "source_root")
    result, visited = [], 0
    pending = [(root, 0)]
    while pending:
        directory, depth = pending.pop()
        require(depth <= 12, "source_depth_bound")
        with os.scandir(directory) as entries:
            for entry in entries:
                visited += 1
                require(visited <= MAX_ENTRIES, "source_count_bound")
                require(not entry.is_symlink(), "source_symlink")
                if entry.is_dir(follow_symlinks=False):
                    pending.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".py"):
                    require(
                        0 <= entry.stat(follow_symlinks=False).st_size <= 8 * 1024 * 1024,
                        "source_size_bound",
                    )
                    result.append(Path(entry.path))
    require(result, "empty_source_set")
    return sorted(result)


def parse_ldd(text):
    require(len(text) <= 1024 * 1024, "ldd_size_bound")
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"linux-vdso\.so\.\d+ \(0x[0-9a-fA-F]+\)", line):
            continue
        match = re.fullmatch(r"(?:\S+ => )?(/\S+) \(0x[0-9a-fA-F]+\)", line)
        require(match is not None, "unsupported_or_unresolved_ldd")
        logical = Path(match[1])
        resolved = logical.resolve(strict=True)
        require(resolved.is_file(), "native_library_missing")
        result[str(logical)] = {"path": str(logical), "resolved_path": str(resolved)}
        require(len(result) <= 128, "native_library_count_bound")
    require(result, "empty_ldd")
    return [result[key] for key in sorted(result)]


def collect(args):
    require(type(args.gpu) is int and args.gpu >= 0, "gpu_identifier")
    require(
        type(args.expires_in_seconds) is int and 1 <= args.expires_in_seconds <= 86400,
        "expiry_bound",
    )
    args.output = Path(os.path.abspath(args.output))
    args.planned_output = Path(os.path.abspath(args.planned_output))
    require(not args.output.exists() and not args.output.is_symlink(), "output_exists")
    require(
        not args.planned_output.exists() and not args.planned_output.is_symlink(),
        "planned_output_exists",
    )
    require(args.output.parent.is_dir() and args.planned_output.parent.is_dir(), "missing_parent")
    require(
        not any(
            p.is_symlink()
            for p in (
                args.output.parent,
                *args.output.parent.parents,
                args.planned_output.parent,
                *args.planned_output.parent.parents,
            )
        ),
        "output_parent_symlink",
    )
    launch = load_launcher(args.launcher)
    report = launch.read_json(args.preflight_receipt, args.expected_preflight_sha256)
    gate = launch.load_gate()
    replay = launch.replay_args(gate, report)
    source_roots = [replay.llama_cpp / "conversion", replay.llama_cpp / "gguf-py"]
    forbidden = [
        replay.run_dir,
        replay.base,
        replay.training_code,
        replay.llama_cpp,
        replay.exporter.parent,
        Path(args.launcher).parent,
    ]
    require(
        not any(root == args.output or root in args.output.parents for root in forbidden),
        "output_inside_verified_input",
    )
    require(args.python.is_absolute(), "python_absolute_path_required")
    resolved_python = args.python.resolve(strict=True)
    interpreter = launch.file_receipt(resolved_python)
    commands = {
        "git": launch.file_receipt(args.git),
        "nvidia_smi": launch.file_receipt(args.nvidia_smi),
    }
    ldd_receipt = launch.file_receipt(args.ldd)
    runtime_args = argparse.Namespace(
        output=args.planned_output,
        python=args.python,
        gpu=args.gpu,
        expected_preflight_sha256=args.expected_preflight_sha256,
    )
    environment = launch.environment_for(runtime_args, {"commands": commands})
    observed_commands = []

    def probe(argv):
        observed_commands.append(argv)
        return launch.command_output(argv, environment, cwd=args.planned_output.parent)

    def git_state():
        commit = probe(
            [commands["git"]["path"], "-C", str(replay.llama_cpp), "rev-parse", "HEAD"]
        ).strip()
        status = probe(
            [
                commands["git"]["path"],
                "-C",
                str(replay.llama_cpp),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ]
        )
        require(commit == gate.LLAMA_COMMIT and status == "", "unclean_or_wrong_llama_checkout")
        return {"root": str(replay.llama_cpp), "git_commit": commit, "status_porcelain": status}

    llama = git_state()
    converter = replay.llama_cpp / "convert_hf_to_gguf.py"
    quantizer = replay.llama_cpp / "build/bin/llama-quantize"
    initial_converter, initial_quantizer = (
        launch.file_receipt(converter),
        launch.file_receipt(quantizer),
    )
    require(
        initial_converter["sha256"] == gate.CONVERTER_SHA
        and initial_quantizer["sha256"] == gate.QUANTIZER_SHA,
        "toolchain_source_changed",
    )
    probe_argv = [
        str(args.python),
        "-E",
        "-s",
        "-B",
        "-c",
        launch.PROBE,
        str(replay.exporter.parent),
        str(replay.llama_cpp),
    ]
    python_probe = json.loads(probe(probe_argv))
    require(
        set(python_probe["packages"]) == set(launch.PACKAGES)
        and set(python_probe["origins"]) == {*launch.MODULES, "gguf"},
        "probe_schema",
    )
    libraries = parse_ldd(probe([ldd_receipt["path"], str(quantizer)]))
    source_sets = {str(root): python_sources(root) for root in source_roots}
    paths = {converter, quantizer, resolved_python, Path(ldd_receipt["path"])}
    paths.update(Path(value["path"]) for value in commands.values())
    paths.update(Path(value) for value in python_probe["origins"].values())
    paths.update(Path(row["resolved_path"]) for row in libraries)
    for source_set in source_sets.values():
        paths.update(source_set)
    require(len(paths) <= MAX_ENTRIES, "dependency_count_bound")
    # The frozen launcher rejects zero-byte dependency files. Preserve their
    # exact evidence separately instead of pretending they were never present.
    empty_sources = [
        {"path": str(path), "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
        for source_set in source_sets.values()
        for path in source_set
        if path.stat().st_size == 0
    ]
    empty_paths = {row["path"] for row in empty_sources}
    dependencies = [
        launch.file_receipt(path) for path in sorted(paths) if str(path) not in empty_paths
    ]
    require(
        set(python_probe["origins"].values()) <= {row["path"] for row in dependencies},
        "empty_or_missing_module_origin",
    )
    # Recheck all measured identities and discovery sets; no self-declared clean flag.
    require(git_state() == llama and json.loads(probe(probe_argv)) == python_probe, "probe_changed")
    require(
        parse_ldd(probe([ldd_receipt["path"], str(quantizer)])) == libraries,
        "native_resolution_changed",
    )
    require(
        all(python_sources(Path(root)) == prior for root, prior in source_sets.items()),
        "source_set_changed",
    )
    require(
        all(launch.file_receipt(row["path"]) == row for row in dependencies), "dependency_changed"
    )
    require(
        all(
            launch.file_receipt(row["path"]) == row
            for row in [
                interpreter,
                ldd_receipt,
                *commands.values(),
                initial_converter,
                initial_quantizer,
            ]
        ),
        "initial_identity_changed",
    )
    require(
        all(
            Path(row["path"]).is_file()
            and not Path(row["path"]).is_symlink()
            and Path(row["path"]).stat().st_size == 0
            for row in empty_sources
        ),
        "empty_source_changed",
    )
    require(
        str(args.python.resolve(strict=True)) == str(resolved_python), "python_resolution_changed"
    )
    require(
        launch.read_json(args.preflight_receipt, args.expected_preflight_sha256) == report,
        "preflight_changed",
    )
    require(launch.file_receipt(args.launcher)["sha256"] == LAUNCHER_SHA, "launcher_changed")
    return {
        "schema_version": 1,
        "kind": DRAFT_KIND,
        "review_required": True,
        "runtime_admission_granted": False,
        "mode": "gpu",
        "candidate_id": replay.candidate_id,
        "preflight_sha256": args.expected_preflight_sha256,
        "host": platform.node(),
        "uid": os.getuid(),
        "gpu": args.gpu,
        "expires_unix": time.time() + args.expires_in_seconds,
        "python": {
            "path": str(args.python),
            "resolved_path": str(resolved_python),
            "bytes": interpreter["bytes"],
            "sha256": interpreter["sha256"],
        },
        "commands": commands,
        "dependency_files": dependencies,
        "quantizer_native_libraries": libraries,
        "llama_cpp": llama,
        "python_probe": python_probe,
        "python_probe_source_sha256": hashlib.sha256(launch.PROBE.encode()).hexdigest(),
        "coverage": {
            "kind": "enumerated_files_and_live_import_probe_not_hermetic",
            "all_transitive_dependencies_hashed": False,
            "python_source_counts": {root: len(files) for root, files in source_sets.items()},
            "empty_python_sources": empty_sources,
            "limitations": [
                "Not all installed Python/stdlib/CUDA bytes are hashed.",
                "ldd does not enumerate every runtime dlopen dependency.",
                "No GPU idle/resource admission, export or inference was performed.",
                "Frozen launcher cannot hash zero-byte dependencies; empty source evidence requires explicit review and is not rehashed by its dependency loop.",
            ],
        },
        "collection": {
            "collector": launch.file_receipt(Path(__file__)),
            "launcher_sha256": LAUNCHER_SHA,
            "collected_unix": time.time(),
            "planned_output": str(args.planned_output),
            "environment": environment,
            "probe_argv": observed_commands,
            "ldd_command": ldd_receipt,
            "model_loaded": False,
            "gpu_queried": False,
        },
    }


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in (
        "launcher",
        "preflight-receipt",
        "python",
        "git",
        "nvidia-smi",
        "ldd",
        "planned-output",
        "output",
    ):
        result.add_argument("--" + name, required=True, type=Path)
    result.add_argument("--expected-preflight-sha256", required=True)
    result.add_argument("--gpu", type=int, default=0)
    result.add_argument("--expires-in-seconds", type=int, default=7200)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = collect(args)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(
            json.dumps(
                {"kind": DRAFT_KIND, "review_required": True, "runtime_admission_granted": False}
            )
        )
        return 0
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- no private exception text in CLI
        code = (
            str(error) if isinstance(error, EvidenceError) else "invalid_or_changed_runtime_input"
        )
        print("Evidence collection failed: " + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
