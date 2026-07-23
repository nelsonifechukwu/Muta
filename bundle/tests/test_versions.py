"""`versions.lock` is read by both bash and Python; these tests pin the shared grammar and
the refusal that makes the lock worth having (TDD T1)."""

from __future__ import annotations

import pytest

from bundle.versions import DEFAULT_LOCK, PinMismatch, check, load_lock, main, require


def test_repo_lock_parses_and_pins_the_engine():
    pins = load_lock()
    assert pins["LLAMA_CPP_REF"] == "b10035"
    assert "-DGGML_AVX512=OFF" in pins["LLAMA_BUILD_FLAGS"], "the DQ guard must be in the lock"
    assert "-DGGML_NATIVE=OFF" in pins["LLAMA_BUILD_FLAGS"]


def test_open_gates_are_recorded_as_empty_not_guessed():
    # Unpinned is a fact about the project (D1/D4 are still open); inventing a value here
    # would be a fabricated measurement, which the TDD forbids outright.
    pins = load_lock()
    assert pins["IK_LLAMA_REF"] == ""
    assert pins["CORE_MODEL_REVISION"] == ""


def test_lock_is_shell_sourceable_and_executes_nothing():
    """Both parsers must read the same bytes — that is the entire reason for the format.

    The stderr assertion is not pedantry: an unquoted multi-word value (`FLAGS=-a -b`) is
    parsed by sh as an assignment *followed by a command*, so a careless lock line silently
    runs `-b` — or, worse, runs one of its own build targets. Caught exactly that way.
    """
    import subprocess

    r = subprocess.run(
        ["bash", "-c", f'set -a; . "{DEFAULT_LOCK}"; printf "%s\\n%s" "$LLAMA_CPP_REF" "$LLAMA_BUILD_FLAGS"'],
        capture_output=True,
        text=True,
        check=True,
    )
    assert r.stderr == "", f"sourcing versions.lock produced output: {r.stderr!r}"
    ref, flags = r.stdout.split("\n")
    pins = load_lock()
    assert ref == pins["LLAMA_CPP_REF"]
    assert flags == pins["LLAMA_BUILD_FLAGS"], "shell and Python must agree on every pin"


def test_comments_and_blank_lines_are_ignored(tmp_path):
    lock = tmp_path / "versions.lock"
    lock.write_text("# a comment\n\nFOO=bar  # trailing\nexport BAZ=qux\n")
    assert load_lock(lock) == {"FOO": "bar", "BAZ": "qux"}


def test_require_refuses_an_unpinned_key(tmp_path):
    lock = tmp_path / "versions.lock"
    lock.write_text("EMPTY=\n")
    with pytest.raises(PinMismatch, match="unset"):
        require("EMPTY", lock)


def test_check_accepts_a_longer_commit_for_the_same_pin(tmp_path):
    lock = tmp_path / "versions.lock"
    lock.write_text("SHA=602f828b4\n")
    check("SHA", "602f828b4c1de2fa1e5c2e0a9f", lock)  # rev-parse vs describe length, same tree


def test_check_rejects_a_different_tree(tmp_path):
    lock = tmp_path / "versions.lock"
    lock.write_text("SHA=602f828b4\n")
    with pytest.raises(PinMismatch, match="refusing to build"):
        check("SHA", "deadbeef", lock)


def test_cli_check_exit_codes(tmp_path, capsys):
    lock = tmp_path / "versions.lock"
    lock.write_text("SHA=abc123\n")
    assert main(["check", "SHA", "abc123", "--lock", str(lock)]) == 0
    assert main(["check", "SHA", "zzz", "--lock", str(lock)]) == 1
    assert "refusing to build" in capsys.readouterr().err
