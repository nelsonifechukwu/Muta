import hashlib
import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import run_mac_accuracy_queue as queue


def artifact(data=b"verified GGUF", name="candidate.gguf"):
    digest = hashlib.sha256(data).hexdigest()
    return {
        "test_artifact": name,
        "test_bytes": len(data),
        "test_sha256": digest,
        "source_bytes": len(data),
        "source_sha256": digest,
        "source_repository": "org/model",
        "source_revision": "a" * 40,
        "source_artifact": "weights/candidate.gguf",
        "runtime_gate": "pass",
    }


def test_download_is_pinned_resumable_and_promoted_only_after_verification(tmp_path, monkeypatch):
    data = b"verified GGUF"
    row = artifact(data)
    partial = tmp_path / "candidate.gguf.part"
    partial.write_bytes(data[:3])
    commands = []

    def download(command, **kwargs):
        commands.append(command)
        assert kwargs["check"]
        assert partial.read_bytes() == data[:3]
        assert not (tmp_path / "candidate.gguf").exists()
        partial.write_bytes(data)

    monkeypatch.setattr(subprocess, "run", download)
    result = queue.acquire_artifact(row, tmp_path, [])
    assert result.read_bytes() == data
    assert not partial.exists()
    assert commands[0][commands[0].index("--continue-at") + 1] == "-"
    assert commands[0][-1] == f"https://huggingface.co/org/model/resolve/{'a' * 40}/weights/candidate.gguf"


def test_corrupt_download_stays_partial_and_never_becomes_a_model(tmp_path, monkeypatch):
    row = artifact()

    def download(command, **kwargs):
        Path(command[command.index("--output") + 1]).write_bytes(b"wrong content")

    monkeypatch.setattr(subprocess, "run", download)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        queue.acquire_artifact(row, tmp_path, [])
    assert (tmp_path / "candidate.gguf.part").read_bytes() == b"wrong content"
    assert not (tmp_path / "candidate.gguf").exists()


def test_complete_partial_promotes_without_redownloading(tmp_path, monkeypatch):
    row = artifact()
    (tmp_path / "candidate.gguf.part").write_bytes(b"verified GGUF")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("unexpected network"))
    assert queue.acquire_artifact(row, tmp_path, []).name == "candidate.gguf"


def test_reuse_hardlinks_only_an_exact_artifact(tmp_path, monkeypatch):
    source = tmp_path / "control.gguf"
    source.write_bytes(b"verified GGUF")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("unexpected network"))
    linked = queue.acquire_artifact(artifact(), tmp_path / "models", [source])
    assert linked.stat().st_ino == source.stat().st_ino


def test_converted_artifact_needs_exact_transfer_never_downloads_source(tmp_path, monkeypatch):
    row = artifact()
    row["source_sha256"] = "f" * 64
    row["source_bytes"] = 300
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("unexpected network"))
    with pytest.raises(ValueError, match="needs_exact_transfer"):
        queue.acquire_artifact(row, tmp_path, [])
    assert not list(tmp_path.iterdir())


def test_existing_wrong_artifact_is_preserved(tmp_path, monkeypatch):
    target = tmp_path / "candidate.gguf"
    target.write_bytes(b"not a model")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("unexpected network"))
    with pytest.raises(ValueError, match="size mismatch"):
        queue.acquire_artifact(artifact(), tmp_path, [])
    assert target.read_bytes() == b"not a model"


def response_stage(tmp_path):
    config = {
        "stage": "judges", "model": "candidate.gguf", "model_sha256": "modelhash",
        "server_sha256": "serverhash", "hardware_context": queue.HARDWARE,
    }
    rows = [{**config, **prompt.as_dict(), "answer": "response"} for prompt in queue.judges_prompts()]
    output = tmp_path / "responses.jsonl"
    output.write_text("".join(json.dumps(row) + "\n" for row in rows))
    (tmp_path / "events.jsonl").write_text('{"event":"model_stop"}\n')
    return config, rows, output


def test_complete_requires_each_exact_prompt_and_execution_identity(tmp_path):
    config, rows, output = response_stage(tmp_path)
    assert queue.completed_stage(tmp_path, config)
    rows[-1]["text"] = "not the original prompt"
    output.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert not queue.completed_stage(tmp_path, config)


def test_duplicate_missing_and_wrong_context_do_not_complete(tmp_path):
    config, rows, output = response_stage(tmp_path)
    for invalid_rows in (rows[:-1], rows + rows[:1], rows[:-1] + rows[:1]):
        output.write_text("".join(json.dumps(row) + "\n" for row in invalid_rows))
        assert not queue.completed_stage(tmp_path, config)
    rows[0]["hardware_context"] = "gcp_scalar"
    output.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert not queue.completed_stage(tmp_path, config)


def test_runner_failure_is_not_completed_even_with_all_answers(tmp_path):
    config, _, _ = response_stage(tmp_path)
    (tmp_path / "events.jsonl").write_text(
        '{"event":"model_failure"}\n{"event":"model_stop"}\n'
    )
    assert not queue.completed_stage(tmp_path, config)


def test_partial_stage_is_preserved_without_invoking_runner(tmp_path, monkeypatch):
    row = artifact()
    args = SimpleNamespace(output=tmp_path, server=tmp_path / "server", port=18083)
    model = tmp_path / "models" / row["test_artifact"]
    directory = tmp_path / model.name / "judges"
    directory.mkdir(parents=True)
    config = queue.stage_config("judges", row, args.server, "serverhash", args.port)
    (directory / "config.json").write_text(json.dumps(config))
    output = directory / "responses.jsonl"
    output.write_text('{"id":"automated_01"}\n')
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("unexpected runner"))
    status = queue.run_stage("judges", row, model, args, "serverhash")
    assert status.startswith("skipped_partial")
    assert output.read_text() == '{"id":"automated_01"}\n'


def test_real_manifest_priority_and_no_quantization_substitution():
    manifest = queue.REPO / "bench/measurements/campaign-20260913-balanced-models/artifacts.csv"
    rows = queue.load_artifacts(manifest)
    assert [row["test_artifact"] for row in rows[:4]] == list(queue.PRIORITY)
    pure = next(row for row in rows if row["test_artifact"] == "MiniCPM5-1B-Q4_0.gguf")
    assert pure["source_sha256"] != pure["test_sha256"]
    assert len([row for row in rows if row["runtime_gate"] == "pass"]) == 13


def test_unsafe_source_path_rejected():
    row = artifact()
    row["source_artifact"] = "../model.gguf"
    with pytest.raises(ValueError, match="unsafe"):
        queue.source_url(row)


def test_archive_build_requires_hash_and_declared_source_revision():
    with pytest.raises(ValueError, match="provide both"):
        queue.server_provenance("b0-unknown", "a" * 64, None, None)
    with pytest.raises(ValueError, match="provide both"):
        queue.server_provenance("b0-unknown", "a" * 64, "a" * 64, None)
    record = queue.server_provenance("b0-unknown", "a" * 64, "a" * 64, queue.SOURCE_REVISION)
    assert record["identity_method"] == "verified_binary_hash_with_operator_supplied_source_revision"
    assert record["version_output"] == "b0-unknown"


def test_mismatched_binary_or_source_is_rejected():
    with pytest.raises(ValueError, match="SHA-256"):
        queue.server_provenance("b0-unknown", "a" * 64, "b" * 64, queue.SOURCE_REVISION)
    with pytest.raises(ValueError, match="source revision"):
        queue.server_provenance("60bccc3", "a" * 64, None, "b" * 40)


def test_port_probe_rejects_a_live_listener():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen()
        with pytest.raises(OSError, match="already listening"):
            queue.assert_port_available(server.getsockname()[1])


def test_port_probe_allows_reuse_after_server_connection_closes():
    with socket.socket() as server, socket.socket() as client:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen()
        client.connect(("127.0.0.1", port))
        accepted, _ = server.accept()
        accepted.close()  # Server side initiates close and leaves TIME_WAIT.
        assert client.recv(1) == b""
    queue.assert_port_available(port)


def test_config_only_stage_can_start_without_rewriting_config(tmp_path, monkeypatch):
    row = artifact()
    args = SimpleNamespace(output=tmp_path, server=tmp_path / "server", port=18083)
    model = tmp_path / "models" / row["test_artifact"]
    directory = tmp_path / model.name / "stem"
    directory.mkdir(parents=True)
    config = queue.stage_config("stem", row, args.server, "serverhash", args.port)
    original_config = json.dumps(config)
    (directory / "config.json").write_text(original_config)
    monkeypatch.setattr(queue, "assert_port_available", lambda port: None)
    commands = []

    class FakeRunner:
        def __init__(self, command, **kwargs):
            commands.append(command)

        def wait(self):
            return 1

    monkeypatch.setattr(subprocess, "Popen", FakeRunner)
    status = queue.run_stage("stem", row, model, args, "serverhash")
    assert status.startswith("failed_or_incomplete")
    assert len(commands) == 1
    assert "bench.run_stem_prompt_suite" in commands[0]
    assert (directory / "config.json").read_text() == original_config
    assert config["settings"]["cache_ram_mib"] == 256


def test_port_failure_does_not_create_a_new_stage(tmp_path, monkeypatch):
    row = artifact()
    args = SimpleNamespace(output=tmp_path, server=tmp_path / "server", port=18083)
    model = tmp_path / "models" / row["test_artifact"]

    def occupied(port):
        raise OSError("port occupied")

    monkeypatch.setattr(queue, "assert_port_available", occupied)
    with pytest.raises(OSError, match="occupied"):
        queue.run_stage("stem", row, model, args, "serverhash")
    assert not (tmp_path / model.name / "stem").exists()
