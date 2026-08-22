#!/usr/bin/env python3
"""Extract and verify the pinned Linux x86-64 llama.cpp tools from the backend image.

Docker is used only as the reproducible build/export boundary.  The resulting binaries are
run directly by the native Linux gateway and benchmark workflows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = "muta-backend:latest"
DEFAULT_FRONTEND_IMAGE = "muta-frontend:latest"
DEFAULT_OUTPUT = ROOT / "runtime" / "build"
DEFAULT_UI_OUTPUT = ROOT / "ui" / "dist"
EXPECTED_TAG = "b10035"
EXPECTED_COMMIT = "602f828"
BINARIES = ("llama-server", "llama-bench")
UI_SOURCE_EXTENSIONS = frozenset({".css", ".html", ".js"})
UI_VENDOR_REQUIRED = (
    "VISUALIZATION-LICENSES.txt",
    "vendor/marked.min.js",
    "vendor/purify.min.js",
    "vendor/katex/katex.min.js",
    "vendor/katex/katex.min.css",
    "vendor/viz/d3.v7.9.0.min.js",
    "vendor/viz/three.r160.min.js",
    "vendor/viz/gsap.v3.13.0.min.js",
    "vendor/viz/anime.v3.2.2.min.js",
    "vendor/viz/motion.v11.11.13.js",
)
FORBIDDEN_AVX512 = re.compile(rb"\s(vpxord|vpternlogd|kmovw|vpbroadcastmw2d)\s")


class ExportError(RuntimeError):
    pass


def _discover_ui_source_files(source_path: Path) -> tuple[str, ...]:
    """Return every authored top-level browser asset, excluding metadata and test files.

    Native startup overlays this inventory into the exported frontend. Discovering it from the
    checkout prevents a new script from being referenced by ``index.html`` but omitted from the
    deployed bundle because somebody forgot to extend a second hard-coded list.
    """
    candidates = [
        item
        for item in source_path.iterdir()
        if not item.name.startswith(".")
        and item.suffix.lower() in UI_SOURCE_EXTENSIONS
        and not item.name.lower().endswith((".spec.js", ".test.js"))
    ]
    symlinks = sorted(item.name for item in candidates if item.is_symlink())
    if symlinks:
        raise ExportError("native UI source assets cannot be symlinks: " + ", ".join(symlinks))
    return tuple(sorted(item.name for item in candidates if item.is_file()))


UI_SOURCE_FILES = _discover_ui_source_files(ROOT / "ui")
UI_REQUIRED = (*UI_SOURCE_FILES, *UI_VENDOR_REQUIRED)


class _IndexAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect bundle assets without mistaking ordinary navigation for files.

        Every ``src`` is an asset. Only ``<link href>`` is: anchor ``href`` values such as
        ``/`` and ``/chat/`` are same-origin product routes and must remain valid in the
        portable gateway.
        """
        tag = tag.lower()
        self.references.extend(
            value
            for name, value in attrs
            if value is not None
            and (name.lower() == "src" or (tag == "link" and name.lower() == "href"))
        )


def _safe_child_path(root: Path, relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ExportError(f"{label} must be a non-empty relative path")
    if "\\" in relative:
        raise ExportError(f"{label} contains a non-portable path separator: {relative}")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ExportError(f"{label} must be relative: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ExportError(f"{label} escapes its allowed root: {relative}") from exc
    return resolved


def _manifest_ui_path(ui: object) -> Path:
    if not isinstance(ui, dict):
        raise ExportError("native manifest UI metadata must be an object")
    return _safe_child_path(ROOT, ui.get("path", "ui/dist"), label="native manifest UI path")


def _run(args: list[str], *, text: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=text)
    except FileNotFoundError as exc:
        raise ExportError(f"required command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if isinstance(exc.stderr, str) else ""
        raise ExportError(f"command failed ({' '.join(args)}): {stderr}") from exc


def _version(path: Path) -> str:
    # llama-server supports --version; llama-bench does not. A zero-work invocation against
    # /dev/null exits nonzero after printing its build identity, which is all we need here.
    args = [str(path), "--version"]
    if path.name == "llama-bench":
        args = [str(path), "-m", "/dev/null", "-p", "0", "-n", "0"]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise ExportError(f"cannot read {path.name} build identity: {exc}") from exc
    output = (result.stdout + result.stderr).strip()
    line = next((item.strip() for item in output.splitlines() if EXPECTED_COMMIT in item), "")
    if not line:
        raise ExportError(
            f"{path.name} is not the pinned {EXPECTED_TAG}/{EXPECTED_COMMIT}: {output[:300]}"
        )
    return line


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str | None:
    try:
        return _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    except ExportError:
        return None


def _image_info(image: str) -> dict:
    raw = _run(["docker", "image", "inspect", image]).stdout
    info = json.loads(raw)[0]
    env = {}
    for item in info.get("Config", {}).get("Env", []):
        key, _, value = item.partition("=")
        env[key] = value
    return {
        "reference": image,
        "id": info.get("Id"),
        "repo_digests": info.get("RepoDigests") or [],
        "platform": f"{info.get('Os')}/{info.get('Architecture')}",
        "muta_git_sha": env.get("MUTA_GIT_SHA"),
    }


def _copy_from_image(image: str, source_path: str, destination: Path) -> None:
    container = _run(["docker", "create", image]).stdout.strip()
    try:
        source = f"{container}:{source_path.rstrip('/')}/."
        _run(["docker", "cp", source, str(destination)])
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container], capture_output=True, text=True, check=False
        )


def _verify_binary(path: Path) -> dict:
    if not path.is_file():
        raise ExportError(f"image did not contain {path.name}")
    path.chmod(path.stat().st_mode | 0o111)
    file_description = _run(["file", "-b", str(path)]).stdout.strip()
    if "ELF 64-bit LSB" not in file_description or "x86-64" not in file_description:
        raise ExportError(f"{path.name} is not a Linux x86-64 ELF: {file_description}")

    version = _version(path)

    disassembly = _run(["objdump", "-d", str(path)], text=False).stdout
    match = FORBIDDEN_AVX512.search(disassembly)
    if match:
        raise ExportError(
            f"forbidden AVX-512 instruction {match.group(1).decode()} found in {path.name}"
        )
    dependencies = _run(["ldd", str(path)]).stdout.strip()
    if "not found" in dependencies:
        raise ExportError(f"unresolved shared-library dependency for {path.name}: {dependencies}")
    return {
        # Staged paths live under /tmp and are replaced with the installed repo-relative
        # path by export(); keeping this valid here also makes verification independently
        # testable.
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "file": file_description,
        "version": version,
        "expected_tag": EXPECTED_TAG,
        "expected_commit": EXPECTED_COMMIT,
        "avx512_signature_scan": "pass",
        "ldd": dependencies.splitlines(),
        "dependency_closure": "resolved-on-export-host",
    }


def _verify_ui(path: Path) -> dict:
    missing = [relative for relative in UI_REQUIRED if not (path / relative).is_file()]
    if missing:
        raise ExportError(f"frontend image is missing native UI assets: {', '.join(missing)}")
    index = (path / "index.html").read_text()
    parser = _IndexAssetParser()
    parser.feed(index)
    absolute_assets = []
    remote_assets = []
    missing_references = []
    for reference in parser.references:
        parsed = urlsplit(reference.strip())
        if parsed.scheme == "data" and not parsed.netloc:
            continue
        if parsed.scheme or parsed.netloc:
            remote_assets.append(reference)
            continue
        relative = unquote(parsed.path)
        if not relative:
            continue
        if relative.startswith("/"):
            absolute_assets.append(relative.lstrip("/"))
            continue
        asset = _safe_child_path(path, relative, label="native UI index asset")
        if not asset.is_file():
            missing_references.append(relative)
    if remote_assets:
        raise ExportError(
            "native UI contains remote asset URLs: " + ", ".join(sorted(remote_assets))
        )
    if absolute_assets:
        raise ExportError(
            "native UI contains root-absolute asset URLs: " + ", ".join(sorted(absolute_assets))
        )
    if missing_references:
        raise ExportError(
            "native UI index references missing assets: "
            + ", ".join(sorted(set(missing_references)))
        )
    files = {}
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = file_path.relative_to(path).as_posix()
        files[relative] = {"bytes": file_path.stat().st_size, "sha256": _sha256(file_path)}
    return {"required_assets": list(UI_REQUIRED), "files": files}


def _install_ui(stage: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(f".{destination.name}.pending")
    backup = destination.with_name(f".{destination.name}.previous")
    shutil.rmtree(pending, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(stage, pending)
    if destination.exists():
        os.replace(destination, backup)
    os.replace(pending, destination)
    shutil.rmtree(backup, ignore_errors=True)


def export(image: str, frontend_image: str, output: Path, ui_output: Path) -> Path:
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ExportError("native Linux export must run on a Linux x86-64 host")
    if shutil.which("docker") is None:
        raise ExportError("docker is required for the one-time image extraction")

    image_info = _image_info(image)
    if image_info["platform"] != "linux/amd64":
        raise ExportError(f"image platform is {image_info['platform']}, expected linux/amd64")
    if not image_info.get("muta_git_sha") or image_info["muta_git_sha"] == "unknown":
        raise ExportError("backend image has unknown source identity; rebuild through run.sh/make")
    frontend_info = _image_info(frontend_image)
    if frontend_info["platform"] != "linux/amd64":
        raise ExportError(
            f"frontend image platform is {frontend_info['platform']}, expected linux/amd64"
        )

    output = output.resolve()
    bin_dir = output / "bin"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="muta-native-export-") as temp:
        stage = Path(temp)
        _copy_from_image(image, "/app/runtime/build/bin", stage)
        verified = {name: _verify_binary(stage / name) for name in BINARIES}
        bin_dir.mkdir(parents=True, exist_ok=True)
        for name in BINARIES:
            os.replace(stage / name, bin_dir / name)
            verified[name]["path"] = str((bin_dir / name).relative_to(ROOT))

    with tempfile.TemporaryDirectory(prefix="muta-native-ui-") as temp:
        ui_stage = Path(temp)
        _copy_from_image(frontend_image, "/usr/share/nginx/html/chat", ui_stage)
        ui_verified = _verify_ui(ui_stage)
        _install_ui(ui_stage, ui_output)

    manifest = {
        "schema": 2,
        "kind": "muta-native-linux-engine",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": {"system": platform.system(), "machine": platform.machine()},
        "source_image": image_info,
        "frontend_image": frontend_info,
        "checkout_git_sha": _git_sha(),
        "binaries": verified,
        "ui": {
            "path": str(ui_output.resolve().relative_to(ROOT)),
            **ui_verified,
        },
        "verification": {
            "linux_x86_64_elf": True,
            "llama_cpp_pin": f"{EXPECTED_TAG}/{EXPECTED_COMMIT}",
            "avx512_signature_scan": "pass",
        },
    }
    manifest_path = output / "native-linux-manifest.json"
    pending = manifest_path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(manifest, indent=2) + "\n")
    os.replace(pending, manifest_path)
    return manifest_path


def verify_manifest(output: Path, *, allow_source_overlay: bool = False) -> Path:
    """Re-check installed binary hashes and the recorded pin without invoking Docker.

    ``allow_source_overlay`` is only for the preflight inside :func:`sync_source_ui`: authored
    files are about to be atomically replaced there, so an older export may legitimately lack
    a newly introduced source file. Binaries and pinned vendor assets remain hash-checked.
    The finished overlay always goes through the strict default verification.
    """
    manifest_path = output.resolve() / "native-linux-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"missing or invalid native manifest: {manifest_path}") from exc
    verification = manifest.get("verification", {})
    if manifest.get("schema") != 2:
        raise ExportError("native manifest predates the complete engine + UI export")
    if verification.get("llama_cpp_pin") != f"{EXPECTED_TAG}/{EXPECTED_COMMIT}":
        raise ExportError("native manifest does not carry the expected llama.cpp pin")
    for name in BINARIES:
        binary = output.resolve() / "bin" / name
        expected = manifest.get("binaries", {}).get(name, {}).get("sha256")
        if not binary.is_file() or not expected:
            raise ExportError(f"native artifact is incomplete: {name}")
        actual = _sha256(binary)
        if actual != expected:
            raise ExportError(f"native artifact hash mismatch for {name}: {actual} != {expected}")
    ui = manifest.get("ui", {})
    ui_path = _manifest_ui_path(ui)
    files = ui.get("files")
    if not isinstance(files, dict) or not files:
        raise ExportError("native manifest has no UI file metadata")
    overlay_files = set(UI_SOURCE_FILES) if allow_source_overlay else set()
    required_metadata = set(UI_REQUIRED) - overlay_files
    missing_metadata = sorted(required_metadata - set(files))
    if missing_metadata:
        raise ExportError(
            "native manifest is missing UI hash metadata: " + ", ".join(missing_metadata)
        )
    for relative, metadata in files.items():
        if allow_source_overlay and relative in UI_SOURCE_FILES:
            continue
        asset = _safe_child_path(ui_path, relative, label="native manifest UI asset")
        expected = metadata.get("sha256") if isinstance(metadata, dict) else None
        if not isinstance(expected, str) or not asset.is_file() or _sha256(asset) != expected:
            raise ExportError(f"native UI artifact hash mismatch for {relative}")
    if any(
        not _safe_child_path(ui_path, item, label="required native UI asset").is_file()
        for item in required_metadata
    ):
        raise ExportError("native UI artifact is incomplete")
    return manifest_path


def sync_source_ui(output: Path) -> Path:
    """Overlay the current checkout's authored UI onto a verified native export.

    The frontend image supplies pinned vendor assets, while the repository remains the source
    of truth for the HTML, CSS, and JavaScript. Native starts call this after a pull so an old
    exported frontend cannot silently serve an old client against a new gateway.
    """
    manifest_path = verify_manifest(output, allow_source_overlay=True)
    manifest = json.loads(manifest_path.read_text())
    ui = manifest["ui"]
    ui_path = _manifest_ui_path(ui)
    source_path = ROOT / "ui"
    for relative in UI_SOURCE_FILES:
        source = source_path / relative
        if not source.is_file():
            raise ExportError(f"native UI source is missing: {relative}")
        destination = ui_path / relative
        pending = destination.with_name(f".{destination.name}.pending")
        # Give the installed asset a fresh mtime. Starlette's conditional response handling
        # considers Last-Modified as well as ETag; preserving an older checkout timestamp can
        # otherwise make a browser retain the pre-pull script even when its bytes changed.
        shutil.copyfile(source, pending)
        os.replace(pending, destination)

    verified = _verify_ui(ui_path)
    manifest["ui"] = {
        "path": ui.get("path", "ui/dist"),
        **verified,
        "source_overlay": {
            "checkout_git_sha": _git_sha(),
            "files": list(UI_SOURCE_FILES),
        },
    }
    pending_manifest = manifest_path.with_suffix(".json.tmp")
    pending_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    os.replace(pending_manifest, manifest_path)
    return verify_manifest(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--frontend-image", default=DEFAULT_FRONTEND_IMAGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ui-output", type=Path, default=DEFAULT_UI_OUTPUT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify-only", action="store_true", help="verify the installed artifact without Docker"
    )
    mode.add_argument(
        "--sync-ui",
        action="store_true",
        help="verify the export, then overlay current repository UI assets",
    )
    args = parser.parse_args(argv)
    try:
        if args.verify_only:
            manifest = verify_manifest(args.output)
        elif args.sync_ui:
            manifest = sync_source_ui(args.output)
        else:
            manifest = export(args.image, args.frontend_image, args.output, args.ui_output)
    except ExportError as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"verified native Linux engine: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
