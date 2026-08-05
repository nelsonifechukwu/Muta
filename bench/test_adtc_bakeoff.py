"""Unit tests for the D1 bake-off harness — pure logic only, no subprocesses."""

from __future__ import annotations

import json

import pytest

from bench import adtc_bakeoff


def test_parse_tasks_default_battery():
    tasks = adtc_bakeoff.parse_tasks(adtc_bakeoff.DEFAULT_TASKS)
    assert ("arc_easy", 100) in tasks
    assert ("gsm8k", 40) in tasks
    assert len(tasks) == 4


def test_parse_tasks_defaults_limit_to_50():
    assert adtc_bakeoff.parse_tasks("arc_easy") == [("arc_easy", 50)]


def test_parse_tasks_tolerates_spaces_and_empties():
    assert adtc_bakeoff.parse_tasks(" arc_easy:10 , ,sciq:5 ") == [
        ("arc_easy", 10),
        ("sciq", 5),
    ]


def test_parse_tasks_rejects_non_numeric_limit():
    with pytest.raises(ValueError):
        adtc_bakeoff.parse_tasks("arc_easy:lots")


def test_append_writes_one_json_line(tmp_path):
    out = tmp_path / "rows.jsonl"
    adtc_bakeoff._append(out, {"b": 2, "a": 1})
    adtc_bakeoff._append(out, {"c": 3})
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    # sort_keys so rows diff cleanly in review
    assert lines[0] == json.dumps({"a": 1, "b": 2}, sort_keys=True)


def test_missing_model_is_an_argument_error(tmp_path):
    with pytest.raises(SystemExit):
        adtc_bakeoff.main(
            ["--models", str(tmp_path / "nope.gguf"), "--out", str(tmp_path / "o.jsonl")]
        )


def test_bench_spec_requires_name_equals_path(tmp_path):
    model = tmp_path / "m.gguf"
    model.write_bytes(b"GGUF")
    with pytest.raises(SystemExit):
        adtc_bakeoff.main(
            [
                "--models",
                str(model),
                "--bench",
                "just-a-name-no-path",
                "--out",
                str(tmp_path / "o.jsonl"),
            ]
        )
