"""Serial Mac Metal accuracy screen; never produces laptop performance measurements.

Prints a plan unless --execute is supplied. Downloads are pinned and resumable;
response stages resume only when complete. Partial stages are preserved and skipped.
Use a new --output directory to repeat an interrupted stage without overwriting it.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from bench.judges_prompt_suite import prompts as judges_prompts
from bench.run_stem_prompt_suite import append_jsonl, sha256
from bench.stem_prompt_suite import prompts as stem_prompts

REPO = Path(__file__).resolve().parents[1]
HARDWARE = "apple_m4_pro_24gib_macos_metal_b10175"
SOURCE_REVISION = "60bccc3763395e01b039aa1ddeacc8cc0ea69f70"
PRIORITY = (
    "Falcon-H1R-0.6B-Q4_K_M.gguf",
    "nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf",
    "VibeThinker-1.5B-q4_k_m.gguf",
    "Qwen3.5-2B-Q4_K_M.gguf",
)
SUITES = {"judges": judges_prompts, "stem": stem_prompts}


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_artifacts(manifest: Path, only: list[str] | None = None) -> list[dict]:
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    seen = set()
    for row in rows:
        name = row["test_artifact"]
        if Path(name).name != name or name in {"", ".", ".."} or name in seen:
            raise ValueError(f"unsafe or duplicate test_artifact: {name!r}")
        seen.add(name)
        for key in ("source_sha256", "test_sha256"):
            if not re.fullmatch(r"[a-f0-9]{64}", row[key]):
                raise ValueError(f"invalid {key}: {name}")
        if not re.fullmatch(r"[a-f0-9]{40,64}", row["source_revision"]):
            raise ValueError(f"unpinned source_revision: {name}")
        for key in ("source_bytes", "test_bytes"):
            row[key] = int(row[key])
            if row[key] <= 0:
                raise ValueError(f"invalid {key}: {name}")
    if only and set(only) - seen:
        raise ValueError(f"unknown requested artifacts: {sorted(set(only) - seen)}")
    selected = [row for row in rows if not only or row["test_artifact"] in only]
    order = {name: index for index, name in enumerate(PRIORITY)}
    return sorted(selected, key=lambda row: order.get(row["test_artifact"], len(PRIORITY)))


def source_url(row: dict) -> str:
    repo = row["source_repository"]
    artifact = row["source_artifact"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"invalid Hugging Face repository: {repo!r}")
    if artifact.startswith("/") or any(
        part in {".", "..", ""} for part in artifact.split("/")
    ):
        raise ValueError(f"unsafe source artifact: {artifact!r}")
    return (
        f"https://huggingface.co/{repo}/resolve/{row['source_revision']}/"
        f"{quote(str(PurePosixPath(artifact)), safe='/')}"
    )


def verify_artifact(path: Path, row: dict) -> None:
    if path.stat().st_size != row["test_bytes"]:
        raise ValueError(f"size mismatch; preserved {path}")
    if sha256(path) != row["test_sha256"]:
        raise ValueError(f"SHA-256 mismatch; preserved {path}")


def acquire_artifact(row: dict, directory: Path, reuse: list[Path]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / row["test_artifact"]
    if destination.exists():
        verify_artifact(destination, row)
        return destination
    for existing in reuse:
        if (
            existing.is_file()
            and existing.stat().st_size == row["test_bytes"]
            and sha256(existing) == row["test_sha256"]
        ):
            # Never silently copy a multi-GB file if hard-linking is unavailable.
            os.link(existing.resolve(), destination)
            verify_artifact(destination, row)
            return destination
    if (
        row["source_sha256"] != row["test_sha256"]
        or row["source_bytes"] != row["test_bytes"]
    ):
        raise ValueError("needs_exact_transfer: locally converted artifact; no upstream substitute")
    partial = destination.with_name(destination.name + ".part")
    if not partial.exists() or partial.stat().st_size != row["test_bytes"]:
        subprocess.run(
            [
                "curl", "--fail", "--location", "--show-error", "--retry", "3",
                "--retry-delay", "2", "--connect-timeout", "20", "--continue-at", "-",
                "--speed-time", "60", "--speed-limit", "1024",
                "--output", str(partial), source_url(row),
            ],
            check=True,
        )
    verify_artifact(partial, row)
    # Destination was absent, and the queue lock prevents another queue promoting it.
    partial.rename(destination)
    return destination


def stage_config(
    stage: str, row: dict, server: Path, server_hash: str, port: int,
    provenance: dict | None = None,
) -> dict:
    prompt_rows = [prompt.as_dict() for prompt in SUITES[stage]()]
    runner = REPO / "bench" / f"run_{stage}_prompt_suite.py"
    settings = {
        "threads": 2,
        "gpu_layers": 99,
        "cache_ram_mib": 256,
        "context_size": 4096 if stage == "judges" else 2048,
        "temperature": 0.0,
        "seed": 3407 if stage == "judges" else 42,
        "max_tokens": 1024 if stage == "judges" else {"multiple_choice": 256, "written": 512},
        "embedded_chat_template": stage == "judges",
        "external_system_prompt": False,
    }
    if stage == "judges":
        settings["top_p"] = 1.0
    else:
        settings["cache_prompt"] = False
    return {
        "stage": stage,
        "model": row["test_artifact"],
        "model_sha256": row["test_sha256"],
        "model_bytes": row["test_bytes"],
        "source": row,
        "server": str(server),
        "server_sha256": server_hash,
        "server_provenance": provenance,
        "runner_sha256": sha256(runner),
        "prompts_sha256": hashlib.sha256(
            json.dumps(prompt_rows, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "hardware_context": HARDWARE,
        "settings": settings,
        "port": port,
    }


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def completed_stage(directory: Path, config: dict) -> bool:
    """Require all exact prompts once, correct identities, and a clean server stop."""
    output, events = directory / "responses.jsonl", directory / "events.jsonl"
    if not output.exists() or not events.exists():
        return False
    rows = read_jsonl(output)
    expected = {prompt.id: prompt.as_dict() for prompt in SUITES[config["stage"]]()}
    if len(rows) != len(expected) or {row.get("id") for row in rows} != set(expected):
        return False
    for row in rows:
        if any(row.get(key) != config[key] for key in (
            "model", "model_sha256", "server_sha256", "hardware_context"
        )):
            return False
        if any(row.get(key) != value for key, value in expected[row["id"]].items()):
            return False
    lifecycle = read_jsonl(events)
    if any(event.get("event") == "model_failure" for event in lifecycle):
        return False
    return bool(lifecycle and lifecycle[-1].get("event") == "model_stop")


def assert_port_available(port: int) -> None:
    """Reject a listener without mistaking a closed server's TIME_WAIT for one."""
    with socket.socket() as connection:
        connection.settimeout(0.5)
        if connection.connect_ex(("127.0.0.1", port)) == 0:
            raise OSError(errno.EADDRINUSE, f"a server is already listening on port {port}")
    with socket.socket() as probe:
        # llama-server also uses SO_REUSEADDR. A plain bind spuriously rejects the
        # recently stopped server's TIME_WAIT sockets between serial stages.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))


def run_stage(stage: str, row: dict, model: Path, args, server_hash: str) -> str:
    directory = args.output / model.name / stage
    config = stage_config(
        stage, row, args.server, server_hash, args.port,
        getattr(args, "server_provenance", None),
    )
    config_path = directory / "config.json"
    if directory.exists():
        if not config_path.exists() or json.loads(config_path.read_text()) != config:
            return "skipped_config_mismatch: preserved prior stage; use a new output directory"
        if completed_stage(directory, config):
            return "complete_existing"
        if {path.name for path in directory.iterdir()} != {"config.json"}:
            return "skipped_partial: preserved raw responses; use a new output directory to restart"
        # A matching config alone means no runner was ever started. It is safe to
        # launch without appending to or changing any response data.
    assert_port_available(args.port)
    if not directory.exists():
        directory.mkdir(parents=True)
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    command = [
        sys.executable, "-m", f"bench.run_{stage}_prompt_suite",
        "--server", str(args.server), "--models", str(model),
        "--out", str(directory / "responses.jsonl"),
        "--events", str(directory / "events.jsonl"),
        "--logs", str(directory / "server-logs"),
        "--port", str(args.port), "--threads", "2", "--gpu-layers", "99",
        "--hardware-context", HARDWARE,
    ]
    with (directory / "runner.log").open("x", encoding="utf-8") as log:
        log.write(json.dumps({"ts": timestamp(), "command": command}) + "\n")
        log.flush()
        process = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
        try:
            returncode = process.wait()
        except BaseException:
            if process.poll() is None:
                # The runner's finally block shuts down its own llama-server.
                process.send_signal(signal.SIGINT)
                process.wait(timeout=45)
            raise
    if returncode != 0 or not completed_stage(directory, config):
        return f"failed_or_incomplete: runner_exit={returncode}; preserved {directory}"
    (directory / "complete.json").write_text(
        json.dumps({"ts": timestamp(), "responses": len(SUITES[stage]())}) + "\n"
    )
    return "complete_new"


def server_provenance(
    version: str, server_hash: str, expected_hash: str | None, source_revision: str | None
) -> dict:
    if expected_hash is not None and expected_hash != server_hash:
        raise ValueError("server SHA-256 does not match --expected-server-sha256")
    if source_revision is not None and source_revision != SOURCE_REVISION:
        raise ValueError("source revision differs from the pinned b10175 revision")
    if "60bccc3" in version:
        method = "server_version_reports_revision"
    elif expected_hash is not None and source_revision == SOURCE_REVISION:
        method = "verified_binary_hash_with_operator_supplied_source_revision"
    else:
        raise ValueError(
            "server version lacks b10175 revision; provide both --expected-server-sha256 "
            "and --source-revision for a source-archive build"
        )
    return {"identity_method": method, "source_revision": SOURCE_REVISION, "version_output": version}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--models-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", nargs="+", help="Exact test_artifact filenames from the manifest")
    parser.add_argument("--stages", nargs="+", choices=tuple(SUITES), default=["judges", "stem"])
    parser.add_argument("--reuse", action="append", type=Path, default=[], help="Verified hard-link input")
    parser.add_argument("--port", type=int, default=18083)
    parser.add_argument("--expected-server-sha256", help="Required for an unversioned archive build")
    parser.add_argument("--source-revision", help="Declared source revision for an archive build")
    parser.add_argument("--execute", action="store_true", help="Download and run; otherwise print plan")
    args = parser.parse_args()
    args.output, args.models_dir, args.server = (
        path.resolve() for path in (args.output, args.models_dir, args.server)
    )
    rows = load_artifacts(args.manifest, args.only)
    for row in rows:
        print(f"{row['test_artifact']}: {row['runtime_gate']}; stages={','.join(args.stages)}")
    if not args.execute:
        print("Plan only. Add --execute to download and run on this Mac; GCP is untouched.")
        return 0
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("this queue is labelled for an Apple Silicon Mac, not this host")
    if "Apple M4 Pro" not in subprocess.check_output(
        ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
    ) or int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) != 24 * 1024**3:
        parser.error("hardware differs from the fixed Apple M4 Pro / 24 GiB treatment label")
    version = subprocess.run([str(args.server), "--version"], capture_output=True, text=True, check=True)
    server_hash = sha256(args.server)
    try:
        args.server_provenance = server_provenance(
            version.stdout + version.stderr, server_hash,
            args.expected_server_sha256, args.source_revision,
        )
    except ValueError as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    args.models_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    counts = {"complete_new": 0, "complete_existing": 0, "stage_failed_or_skipped": 0,
              "artifact_unavailable": 0, "runtime_excluded": 0}
    # Also lock the artifact directory: output roots may differ but share downloads.
    with (args.output / ".queue.lock").open("a") as output_lock, (
        args.models_dir / ".queue.lock"
    ).open("a") as model_lock:
        for lock in (output_lock, model_lock):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        append_jsonl(args.output / "queue-events.jsonl", {
            "ts": timestamp(), "event": "queue_start", "server_sha256": server_hash,
            "server_version": version.stdout + version.stderr,
            "server_provenance": args.server_provenance,
            "hardware_context": HARDWARE, "host": platform.platform(),
            "manifest_sha256": sha256(args.manifest),
            "compatible_models": sum(row["runtime_gate"] == "pass" for row in rows),
            "stages": list(dict.fromkeys(args.stages)),
        })
        for row in rows:
            name = row["test_artifact"]
            if row["runtime_gate"] != "pass":
                counts["runtime_excluded"] += 1
                status = f"skipped_runtime_gate: {row['runtime_gate']}"
                append_jsonl(args.output / "queue-events.jsonl", {
                    "ts": timestamp(), "model": name, "status": status,
                })
                print(f"{name}: {status}", flush=True)
                continue
            try:
                model = acquire_artifact(row, args.models_dir, args.reuse)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                failed = True
                counts["artifact_unavailable"] += 1
                append_jsonl(args.output / "queue-events.jsonl", {
                    "ts": timestamp(), "model": name, "status": "artifact_unavailable",
                    "error": str(exc),
                })
                print(f"{name}: artifact_unavailable: {exc}", flush=True)
                continue
            for stage in dict.fromkeys(args.stages):
                print(f"{name}: starting {stage}", flush=True)
                append_jsonl(args.output / "queue-events.jsonl", {
                    "ts": timestamp(), "event": "stage_start", "model": name, "stage": stage,
                })
                try:
                    status = run_stage(stage, row, model, args, server_hash)
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    status = f"stage_error: {exc}"
                failed |= not status.startswith("complete_")
                counts[status if status in {"complete_new", "complete_existing"}
                       else "stage_failed_or_skipped"] += 1
                append_jsonl(args.output / "queue-events.jsonl", {
                    "ts": timestamp(), "model": name, "stage": stage, "status": status,
                })
                print(f"{name}: {stage}: {status}", flush=True)
        append_jsonl(args.output / "queue-events.jsonl", {
            "ts": timestamp(), "event": "queue_finish", "had_failures": failed, "counts": counts,
        })
    return 1 if failed else 0


if __name__ == "__main__":
    def interrupt_on_term(signum, frame):
        raise KeyboardInterrupt("queue terminated; preserving partial stages")

    signal.signal(signal.SIGTERM, interrupt_on_term)
    raise SystemExit(main())
