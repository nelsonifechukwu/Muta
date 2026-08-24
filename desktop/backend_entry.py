"""Frozen Muta gateway entrypoint used by the desktop sidecar.

Argument parsing and environment setup intentionally happen before importing any product module:
several process-wide singletons resolve their database/resource paths at import time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import MutableMapping
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="muta-gateway")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--serve", action="store_true", help="serve the packaged Muta application")
    mode.add_argument("--tool-worker", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--healthcheck", action="store_true", help="probe a running gateway")
    mode.add_argument("--print-config", action="store_true", help="print resolved desktop paths")
    parser.add_argument("--resource-root", type=Path)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--llama-server", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--engine-port", type=int, default=0)
    parser.add_argument("--parent-pid", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser


def _default_resource_root() -> Path:
    configured = os.environ.get("MUTA_RESOURCE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return (Path(sys.executable).resolve().parent / "resources").resolve()
    return Path(__file__).resolve().parents[1]


def _default_data_root() -> Path:
    configured = os.environ.get("MUTA_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "Muta"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Muta"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".local" / "share") / "muta"


def _safe_child(root: Path, relative: str, *, label: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"{label} path escapes its bundle: {relative}")
    return candidate


def _load_product_manifest(root: Path) -> dict:
    path = root / "desktop-product.json"
    if not path.is_file():
        raise FileNotFoundError(f"packaged product manifest is missing: {path}")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("schema") != 1:
        raise ValueError("unsupported desktop-product.json schema")
    return body


def _verify_file(path: Path, expected_size: int, expected_sha256: str, *, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"packaged {label} is missing: {path}")
    if path.stat().st_size != expected_size:
        raise ValueError(f"packaged {label} has the wrong byte size: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise ValueError(f"packaged {label} failed SHA-256 verification: {path}")


def _discover_model(model_root: Path, manifest: dict) -> tuple[Path, Path | None]:
    selected = manifest.get("active_model") or {}
    relative = selected.get("path")
    if not relative:
        raise ValueError("desktop-product.json does not select an active offline model")
    model = _safe_child(model_root, str(relative), label="model")
    _verify_file(
        model,
        int(selected.get("size_bytes", -1)),
        str(selected.get("sha256", "")),
        label="model",
    )
    projector = selected.get("mmproj_path")
    if not projector:
        return model, None
    mmproj = _safe_child(model_root, str(projector), label="model projector")
    _verify_file(
        mmproj,
        int(selected.get("mmproj_size_bytes", -1)),
        str(selected.get("mmproj_sha256", "")),
        label="model projector",
    )
    return model, mmproj


def _sqlite_dsn(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def configure(
    args: argparse.Namespace, environment: MutableMapping[str, str] | None = None
) -> dict[str, str]:
    environment = os.environ if environment is None else environment
    resource = (args.resource_root or _default_resource_root()).expanduser().resolve()
    models = (args.model_root or resource).expanduser().resolve()
    data = (args.data_root or _default_data_root()).expanduser().resolve()
    cache = (args.cache_root or data / "cache").expanduser().resolve()
    for directory in (data, cache, data / "logs", data / "kv-slots", data / "twins"):
        directory.mkdir(parents=True, exist_ok=True)

    manifest = _load_product_manifest(resource)
    model, mmproj = _discover_model(models, manifest)
    executable = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    llama = (args.llama_server or resource / "bin" / executable).expanduser().resolve()
    if not llama.is_file():
        raise FileNotFoundError(f"packaged llama-server is missing: {llama}")
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    ffmpeg = resource / "bin" / ffmpeg_name

    port = args.port or int(environment.get("MUTA_DESKTOP_PORT", "18000"))
    engine_port = args.engine_port or int(environment.get("MUTA_DESKTOP_ENGINE_PORT", "18080"))
    values = {
        "MUTA_RESOURCE_ROOT": str(resource),
        "MUTA_MODEL_ROOT": str(models),
        "MUTA_DATA_ROOT": str(data),
        "MUTA_CACHE_ROOT": str(cache),
        # Compatibility for modules that still use the historical read-only root.
        "TUTOR_ROOT": str(resource),
        "MUTA_OFFLINE": "1",
        "MUTA_DESKTOP": "1",
        # The packaged operator owns the local llama process and may switch between models
        # that passed ModelManager's catalog/path/RAM checks. Shared members never see this UI.
        "MUTA_ALLOW_MODEL_SWITCH": "1",
        "MUTA_DEPLOY_MODE": "mounted",
        "MUTA_RT_AUTOSTART": "1",
        "MUTA_RT_AUTO_DOWNLOAD": "0",
        "MUTA_RT_MODEL_SOURCE": "local",
        "MUTA_RT_MODEL_DIR": str(model.parent),
        "MUTA_RT_MODEL_FILE": model.name,
        "MUTA_MODEL_CATALOG_PATH": str(resource / "runtime" / "model-catalog.json"),
        "MUTA_RT_DB_URL": _sqlite_dsn(data / "muta.sqlite3"),
        "MUTA_RT_LLAMA_SERVER_BIN": str(llama),
        "TUTOR_LLAMA_SERVER_BIN": str(llama),
        "MUTA_RT_SERVER_HOST": "127.0.0.1",
        "MUTA_RT_SERVER_PORT": str(engine_port),
        "MUTA_LLAMA_SERVER_URL": f"http://127.0.0.1:{engine_port}",
        "MUTA_OPERATOR_ID_FILE": str(data / "operator-student-id"),
        "MUTA_DESKTOP_HOST": args.host,
        "MUTA_DESKTOP_PORT": str(port),
        "MUTA_VERSION": str(manifest.get("version") or "0.0.0+desktop"),
        "MUTA_GIT_SHA": str(manifest.get("git_sha") or "unknown"),
    }
    if ffmpeg.is_file():
        values["MUTA_FFMPEG_BIN"] = str(ffmpeg)
    draft_dir = models / "models" / "draft"
    drafts = sorted(draft_dir.glob("*.gguf")) if draft_dir.is_dir() else []
    # Never inherit developer-only engine or fleet settings into a signed application.
    for key in (
        "MUTA_RT_EXTRA_SERVER_ARGS",
        "MUTA_RT_MMPROJ_PATH",
        "MUTA_RT_DRAFT_MODEL",
        "MUTA_FLEET_URL",
        "MUTA_FLEET_INGEST_KEY",
        "MUTA_FLEET_SYNC_INTERVAL_S",
        "MUTA_FLEET_TIMEOUT_S",
        "MUTA_FLEET_ACTIVE_WINDOW_S",
        "MUTA_CLOUD_URL",
        "MUTA_CLOUD_MODEL",
        "MUTA_CLOUD_API_KEY",
        "MUTA_SEARCH_URL",
        "MUTA_RT_HF_REPO",
        "MUTA_RT_HF_FILENAME",
    ):
        environment.pop(key, None)
    heartbeat = manifest.get("heartbeat") or {}
    if heartbeat.get("url") and heartbeat.get("ingest_key"):
        values["MUTA_FLEET_URL"] = str(heartbeat["url"])
        values["MUTA_FLEET_INGEST_KEY"] = str(heartbeat["ingest_key"])
    if mmproj is not None:
        values["MUTA_RT_MMPROJ_PATH"] = str(mmproj)
    if len(drafts) == 1:
        values["MUTA_RT_DRAFT_MODEL"] = str(drafts[0])
    for key, value in values.items():
        # The desktop launcher is the authority for local paths/offline guarantees. Inheriting
        # a developer's `.env` here could silently point a signed app at Postgres or HF.
        environment[key] = value
    return values


def _healthcheck(host: str, port: int, timeout: float) -> int:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/v1/ready", timeout=timeout) as response:
            body = json.loads(response.read())
    except (OSError, ValueError, urllib.error.URLError):
        return 1
    return 0 if response.status == 200 and body.get("ready") is True else 1


def _watch_parent(expected_pid: int) -> None:
    """Terminate gracefully if the native shell dies instead of sending a close event."""
    while True:
        time.sleep(1.0)
        if os.getppid() != expected_pid:
            os.kill(os.getpid(), signal.SIGTERM)
            return
        try:
            os.kill(expected_pid, 0)
        except OSError:
            os.kill(os.getpid(), signal.SIGTERM)
            return


def _use_parent_watchdog(expected_pid: int, platform_name: str | None = None) -> bool:
    platform_name = os.name if platform_name is None else platform_name
    return expected_pid > 0 and platform_name != "nt"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.tool_worker:
        from orchestrator.tools._worker import main as worker_main

        return worker_main()
    if args.healthcheck:
        port = args.port or int(os.environ.get("MUTA_DESKTOP_PORT", "18000"))
        return _healthcheck(args.host, port, args.timeout)

    values = configure(args)
    if args.print_config:
        redacted = dict(values)
        for key in ("MUTA_FLEET_INGEST_KEY", "MUTA_CLOUD_API_KEY"):
            if key in redacted:
                redacted[key] = "<redacted>"
        print(json.dumps(redacted, indent=2, sort_keys=True))
        return 0

    # RuntimeConfig supports a source-checkout .env for developers. A staged resource root is
    # signed and intentionally contains no .env, making it a safe desktop working directory.
    os.chdir(values["MUTA_RESOURCE_ROOT"])
    # On Windows the native shell already owns the gateway through a
    # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE job. Python's os.kill(pid, 0) is not a
    # POSIX-style liveness probe there: it can fail with ERROR_INVALID_HANDLE
    # for a healthy GUI parent and make every gateway attempt self-terminate.
    if _use_parent_watchdog(args.parent_pid):
        threading.Thread(
            target=_watch_parent,
            args=(args.parent_pid,),
            name="muta-parent-watchdog",
            daemon=True,
        ).start()

    import uvicorn

    from orchestrator.main import app

    uvicorn.run(
        app,
        host=values["MUTA_DESKTOP_HOST"],
        port=int(values["MUTA_DESKTOP_PORT"]),
        access_log=False,
        log_level=os.environ.get("MUTA_LOG_LEVEL", "info").lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
