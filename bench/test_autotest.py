"""Tests for the autonomous orchestrator.

A stub `adtc-profiler` stands in for the real one, so these run with no venv, no model, and no
network. What is tested is the wiring and the exit codes — the parts that decide whether a bad
run is loud or silent.
"""

from __future__ import annotations

import json
import platform
import stat

import pytest

from bench import autotest

GOOD = {
    "throughput": {"tokens_per_second_generation": 14.0, "first_token_latency_ms": 300.0},
    "memory": {"peak_rss_mb": 1024.0, "steady_state_rss_mb": 900.0, "peak_vms_mb": 4000.0},
    "cpu_thermal": {"cpu_percent_p99": 70.0, "core_temp_c_peak": None, "throttled": False},
    "model_info": {"params_match": True},
}


def _stub_profiler(tmp_path, payload: dict, exit_code: int = 0):
    """A fake adtc-profiler that writes `payload` to the path after --output."""
    script = tmp_path / "adtc-profiler"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv\n"
        "out = args[args.index('--output') + 1] if '--output' in args else None\n"
        f"payload = {payload!r}\n"
        f"code = {exit_code}\n"
        "if out and code == 0:\n"
        "    open(out, 'w').write(json.dumps(payload))\n"
        "if code:\n"
        "    sys.stderr.write('stub failure\\n')\n"
        "sys.exit(code)\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_run_official_returns_the_parsed_report(tmp_path):
    binary = _stub_profiler(tmp_path, GOOD)
    out = tmp_path / "submission.json"
    data = autotest.run_official(binary, tmp_path, out, extra_path=None)
    assert data["throughput"]["tokens_per_second_generation"] == 14.0
    assert json.loads(out.read_text()) == GOOD


def test_run_official_raises_on_a_failing_profiler(tmp_path):
    binary = _stub_profiler(tmp_path, GOOD, exit_code=3)
    with pytest.raises(autotest.AutotestError) as exc:
        autotest.run_official(binary, tmp_path, tmp_path / "o.json", extra_path=None)
    assert "stub failure" in str(exc.value)


def test_run_official_prepends_llama_bench_to_path(tmp_path):
    """The profiler finds llama-bench via shutil.which only; ours is in runtime/build/bin."""
    binary = tmp_path / "adtc-profiler"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "out = sys.argv[sys.argv.index('--output') + 1]\n"
        "open(out, 'w').write(json.dumps({'seen_path': os.environ['PATH']}))\n"
    )
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    extra = tmp_path / "bin"
    extra.mkdir()
    data = autotest.run_official(binary, tmp_path, tmp_path / "o.json", extra_path=extra)
    assert data["seen_path"].startswith(str(extra))  # prepended, not appended


def test_provenance_marks_a_dev_host():
    p = autotest.capture_provenance()
    assert p.system == platform.system()
    if p.system == "Darwin" or p.machine in {"arm64", "aarch64"}:
        assert p.label == "dev_host_provisional"
    else:
        assert p.label == "target_candidate"


def test_log_row_carries_provenance_and_both_paths():
    row = autotest.log_row(
        {
            "profiler": {"tps": 14.0, "peak_rss_gb": 1.0, "s_total": 61.2},
            "product": {"tps": 11.0, "peak_rss_gb": 2.4, "s_total": 55.0},
        },
        autotest.Provenance(
            system="Darwin",
            machine="arm64",
            git_sha="abc123-dirty",
            label="dev_host_provisional",
        ),
    )
    assert "dev_host_provisional" in row
    assert "abc123-dirty" in row
    assert "14.0" in row and "11.0" in row
    assert row.startswith("|") and row.endswith("|")


def test_log_row_shows_dq_rather_than_a_number_for_a_disqualified_run():
    row = autotest.log_row(
        {"product": {"tps": 0.0, "peak_rss_gb": 0.0, "s_total": None}},
        autotest.Provenance(system="Linux", machine="x86_64", git_sha="a", label="target_candidate"),
    )
    assert "DQ" in row


def test_fraud_check_failure_exits_three(tmp_path, monkeypatch):
    binary = _stub_profiler(tmp_path, dict(GOOD, model_info={"params_match": False}))
    monkeypatch.setattr(autotest, "_prepare", lambda args: (binary, tmp_path, tmp_path))
    monkeypatch.setattr(autotest, "ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(autotest, "RUNS_JSONL", tmp_path / "runs.jsonl")
    assert autotest.main(["--skip-product", "--no-log"]) == 3


def test_profiler_failure_exits_two(tmp_path, monkeypatch):
    binary = _stub_profiler(tmp_path, GOOD, exit_code=3)
    monkeypatch.setattr(autotest, "_prepare", lambda args: (binary, tmp_path, tmp_path))
    monkeypatch.setattr(autotest, "ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(autotest, "RUNS_JSONL", tmp_path / "runs.jsonl")
    assert autotest.main(["--skip-product", "--no-log"]) == 2


def test_missing_llama_bench_exits_two(tmp_path, monkeypatch):
    binary = _stub_profiler(tmp_path, GOOD)
    monkeypatch.setattr(autotest, "_prepare", lambda args: (binary, tmp_path, None))
    assert autotest.main(["--skip-product", "--no-log"]) == 2


def test_clean_run_exits_zero_and_records(tmp_path, monkeypatch):
    binary = _stub_profiler(tmp_path, GOOD)
    runs = tmp_path / "runs.jsonl"
    monkeypatch.setattr(autotest, "_prepare", lambda args: (binary, tmp_path, tmp_path))
    monkeypatch.setattr(autotest, "ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(autotest, "RUNS_JSONL", runs)
    assert autotest.main(["--skip-product", "--no-log"]) == 0

    record = json.loads(runs.read_text().strip())
    assert record["scored"]["profiler"]["tps"] == 14.0
    # Provenance and the tps_max caveat must travel with every number.
    assert record["provenance"]["git_sha"]
    assert record["tps_max_provenance"] == "provisional_reference"
