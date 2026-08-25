"""Safeguards for the published-snapshot build of the report (what the pages workflow ships)."""

import json
from pathlib import Path

import build_static
import pytest

DASHBOARD = Path(__file__).resolve().parent


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return build_static.build(tmp_path_factory.mktemp("pages") / "site")


def test_site_is_self_contained_and_relative(site):
    for name in ("index.html", "style.css", "script.js", "api/state.json", ".nojekyll"):
        assert (site / name).is_file(), name
    assert (site / build_static.MARKER).is_file()
    html = (site / "index.html").read_text()
    assert html.count('<html lang="en" data-snapshot="api/state.json">') == 1
    assert (site / "style.css").read_bytes() == (DASHBOARD / "style.css").read_bytes()
    assert (site / "script.js").read_bytes() == (DASHBOARD / "script.js").read_bytes()
    # Everything the page loads must stay relative so a /<repo>/ project-page prefix works.
    assert 'href="/' not in html
    assert 'src="/' not in html


def test_snapshot_carries_every_evidence_lane(site):
    state = json.loads((site / "api/state.json").read_text())
    for lane in build_static.EVIDENCE_LANES:
        assert state[lane] is not None, lane
    assert state["current"] is None
    assert state["snapshot"]["path"] == "api/state.json"
    assert state["models"], "stored model runs should be listed"
    assert {model["file"] for model in state["models"]} == set(state["runs_by_model"])


def test_snapshot_embeds_reports_without_emails(site):
    text = (site / "api/state.json").read_text()
    state = json.loads(text)
    runs = [run for runs in state["runs_by_model"].values() for run in runs]
    assert any(run["report"] for run in runs)
    for run in runs:
        assert "report_json" not in run
        assert run["status"] != "running"
    for key, value in walk(state["runs_by_model"]):
        if key == "email":
            assert value is None
    submitter = json.loads((DASHBOARD.parent / "metadata.json").read_text())["submitter"]
    assert submitter["email"] not in text


def test_build_refuses_to_clear_a_foreign_directory(tmp_path):
    out = tmp_path / "keep"
    out.mkdir()
    (out / "precious.txt").write_text("not ours")
    with pytest.raises(SystemExit):
        build_static.build(out)
    assert (out / "precious.txt").read_text() == "not ours"


def test_build_replaces_its_own_previous_output(tmp_path):
    out = tmp_path / "site"
    build_static.build(out)
    (out / "stale.txt").write_text("from an earlier build")
    build_static.build(out)
    assert not (out / "stale.txt").exists()
    assert (out / "index.html").is_file()


def test_script_and_page_support_the_published_snapshot():
    html = (DASHBOARD / "index.html").read_text()
    script = (DASHBOARD / "script.js").read_text()

    assert 'id="static-notice" hidden' in html
    assert "document.documentElement.dataset.snapshot" in script
    assert 'fetch(STATIC ? SNAPSHOT_URL : "/api/state")' in script
    assert "if (STATIC) return;" in script  # a static file is fetched once, never polled
    assert "runs_by_model" in script  # History and Raw report read the embedded runs
    for guard in (
        '["profile", "cancel", "promote", "delete"].includes(action)',
        "Promotion needs the local dashboard server",
        "Deleting a record needs the local dashboard server",
        "Profiling needs the local dashboard server",
    ):
        assert guard in script
