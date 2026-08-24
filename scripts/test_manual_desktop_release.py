from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import gcp_desktop_build as gcp
import manual_desktop_release as release
import manual_desktop_worker as worker
import sync_desktop_model_inputs as model_sync


def test_release_version_accepts_semver_and_rejects_invalid() -> None:
    commit = "a" * 40
    assert release.release_version(commit, "2.4.1-beta.2") == "2.4.1-beta.2"
    try:
        release.release_version(commit, "version two")
    except release.ReleaseError as error:
        assert "not SemVer" in str(error)
    else:
        raise AssertionError("invalid release version was accepted")


def test_archive_names_cover_all_four_targets() -> None:
    assert release.archive_name("1.2.3", "darwin-aarch64").endswith(".tar.gz")
    assert release.archive_name("1.2.3", "darwin-x86_64").endswith(".tar.gz")
    assert release.archive_name("1.2.3", "linux-x86_64").endswith(".tar.gz")
    assert release.archive_name("1.2.3", "windows-x86_64").endswith(".zip")


def test_final_manifest_verifies_every_checksum(tmp_path: Path) -> None:
    for target in release.PLATFORMS:
        archive = tmp_path / release.archive_name("1.2.3", target)
        archive.write_bytes(target.encode())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        Path(f"{archive}.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")

    manifest = release.write_manifest("b" * 40, "1.2.3", tmp_path, dry_run=False)

    body = json.loads(manifest.read_text(encoding="utf-8"))
    assert body["git_commit"] == "b" * 40
    assert {item["platform"] for item in body["files"]} == set(release.PLATFORMS)


def test_model_sync_copies_only_declared_product_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    product = "muta-iq/model/product.gguf"
    projector = "models/mmproj/projector.gguf"
    (source / "runtime").mkdir(parents=True)
    (source / "runtime/model-catalog.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": model_sync.PRODUCT_MODEL_ID,
                        "path": product,
                        "mmproj_path": projector,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for relative in (product, projector, *model_sync.MODEL_FILES):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    for relative in model_sync.MODEL_DIRECTORIES:
        path = source / relative / "asset.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())

    model_sync.sync(source, destination)

    assert (destination / product).read_text(encoding="utf-8") == product
    assert (destination / projector).read_text(encoding="utf-8") == projector
    assert not (destination / "runtime/model-catalog.json").exists()


def test_gateway_worker_uses_external_cargo_cache(tmp_path: Path) -> None:
    environment = worker.target_environment("darwin-x86_64", tmp_path)
    assert worker.bundle_root(environment) == (
        tmp_path / "cargo-target/darwin-x86_64/x86_64-apple-darwin/release/bundle"
    )


def test_linux_worker_caps_compiler_parallelism_on_eight_gb_builder(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("CMAKE_BUILD_PARALLEL_LEVEL", raising=False)
    monkeypatch.delenv("NUMBER_OF_PROCESSORS", raising=False)
    monkeypatch.delenv("MUTA_NATIVE_JOBS", raising=False)
    environment = worker.target_environment("linux-x86_64", tmp_path)
    assert environment["CMAKE_BUILD_PARALLEL_LEVEL"] == "2"
    assert environment["NUMBER_OF_PROCESSORS"] == "2"
    assert environment["MUTA_NATIVE_JOBS"] == "2"


def test_gcp_model_key_changes_with_manifest(tmp_path: Path) -> None:
    for relative in (
        "runtime/model-catalog.json",
        "models/MANIFEST.json",
        "models/pins.lock.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    before = gcp.model_key(tmp_path)
    (tmp_path / "models/MANIFEST.json").write_text("changed", encoding="utf-8")
    assert gcp.model_key(tmp_path) != before


def test_gcp_powershell_commands_survive_ssh_argument_parsing() -> None:
    script = "& 'C:/MutaIncoming/build.ps1' -Version '1.2.3-beta.1'; exit 0"
    command = gcp.powershell_command(script)

    assert command[-2] == "-EncodedCommand"
    assert base64.b64decode(command[-1]).decode("utf-16-le") == script


def test_gcp_prunes_only_old_commit_scratch_data(tmp_path: Path, monkeypatch) -> None:
    current = "a" * 40
    old = "b" * 40
    worktrees = tmp_path / "worktrees/linux-x86_64"
    transfer = tmp_path / "transfer"
    outputs = tmp_path / "outputs"
    for path in (worktrees / current, worktrees / old, outputs / current, outputs / old):
        path.mkdir(parents=True)
    transfer.mkdir(parents=True)
    (transfer / f"source-{current}.tar.gz").write_bytes(b"current")
    (transfer / f"source-{old}.tar.gz").write_bytes(b"old")
    (transfer / "model-inputs-keep.tar.gz").write_bytes(b"model")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(gcp, "run", fake_run)
    gcp.prune_completed_commits(tmp_path, current)

    assert (worktrees / current).is_dir()
    assert not (worktrees / old).exists()
    assert (outputs / current).is_dir()
    assert not (outputs / old).exists()
    assert (transfer / f"source-{current}.tar.gz").is_file()
    assert not (transfer / f"source-{old}.tar.gz").exists()
    assert (transfer / "model-inputs-keep.tar.gz").is_file()
    assert ["git", "worktree", "prune"] in commands


def test_manual_worker_rejects_wrong_host(monkeypatch) -> None:
    monkeypatch.setattr(worker.platform, "system", lambda: "Darwin")
    try:
        worker.verify_host("linux-x86_64")
    except worker.WorkerError as error:
        assert "must build on Linux" in str(error)
    else:
        raise AssertionError("cross-OS desktop build was accepted")


def test_worker_recovers_lock_left_by_dead_process(tmp_path: Path) -> None:
    lock = tmp_path / "locks/linux-x86_64.lock"
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(
        json.dumps({"pid": 999_999_999, "host": worker.platform.node()}),
        encoding="utf-8",
    )

    with worker.platform_lock(tmp_path, "linux-x86_64"):
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        assert owner["pid"] > 0

    assert not lock.exists()
