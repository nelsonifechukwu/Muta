"""Safeguards for the published-snapshot build of the report (what the pages workflow ships)."""

import json
import re
from pathlib import Path

import build_gate_two_evidence
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
    assert (site / "brand" / "muta-wordmark-on-light.svg").read_bytes() == (
        DASHBOARD / "brand" / "muta-wordmark-on-light.svg"
    ).read_bytes()
    assert (site / "brand" / "InstrumentSans-Regular.ttf").is_file()
    assert (site / "evidence" / "gate-2" / "index.json").is_file()
    # Everything the page loads must stay relative so a /<repo>/ project-page prefix works.
    assert 'href="/' not in html
    assert 'src="/' not in html


def test_gate_two_evidence_bundle_preserves_coverage_and_failures(site):
    root = site / "evidence" / "gate-2"
    manifest = json.loads((root / "index.json").read_text())
    datasets = {dataset["id"]: dataset for dataset in manifest["datasets"]}

    assert len(manifest["models"]) == 13
    assert manifest["excluded_artifacts"] == [
        {
            "model": "Spark-X2.5 1.7B",
            "artifact": "Spark-X2.5-1.7B-Q4_K_M.gguf",
            "reason": "fail: spark architecture unsupported by b10175",
        }
    ]
    assert sum(model["captured"] for model in datasets["mac-stem"]["models"]) == 1200
    assert sum(model["captured"] for model in datasets["gcp-judges"]["models"]) == 125
    assert sum(model["captured"] for model in datasets["mac-judges"]["models"]) == 123
    assert sum(model["captured"] for model in datasets["gcp-stem-original"]["models"]) == 935
    assert sum(model["captured"] for model in datasets["gcp-stem-restart"]["models"]) == 28
    assert sum(model["captured"] for model in datasets["gcp-stem-vector"]["models"]) == 200

    mac_judge_records = []
    for model in datasets["mac-judges"]["models"]:
        payload = json.loads((root / model["path"]).read_text())
        mac_judge_records.extend(payload["records"])
    assert sum("review" in record for record in mac_judge_records) == 120
    assert sum("review" not in record for record in mac_judge_records) == 3

    vector_models = {model["label"]: model for model in datasets["gcp-stem-vector"]["models"]}
    assert vector_models["Falcon-H1-Tiny-R 0.6B Q4_K_M"]["attempt"] == {
        "status": "failed",
        "label": "Failed; no response",
        "reason": "The retained attempt inventory records a runtime failure before any response was captured.",
    }
    assert vector_models["OpenReasoning Nemotron 1.5B Q4_K_M"]["attempt"] == {
        "status": "not_reached",
        "label": "Not reached",
        "reason": "The retained attempt inventory records that this model was not reached.",
    }

    gcp_judges = {model["label"]: model for model in datasets["gcp-judges"]["models"]}
    assert gcp_judges["Falcon-H1-Tiny-R 0.6B Q4_K_M"]["captured"] == 5
    assert gcp_judges["OpenReasoning Nemotron 1.5B Q4_K_M"]["captured"] == 10
    arc_control = next(
        model
        for model in datasets["arc-easy-500"]["models"]
        if model["label"].startswith("Muta Tutor")
    )
    assert arc_control["aggregate"]["accuracy_percent"] == 77.8
    assert arc_control["aggregate"]["availability"] == "aggregate_only"


def test_gate_two_download_manifest_contains_only_reachable_files(site):
    root = site / "evidence" / "gate-2"
    manifest = json.loads((root / "index.json").read_text())
    paths = [item["path"] for item in manifest["downloads"]]

    assert len(paths) == len(set(paths))
    assert "raw/artifacts.csv" in paths
    assert "raw/raw/stem-responses-gcp-remainder.jsonl" in paths
    assert "raw/raw/stem-responses-vector-remainder.jsonl" in paths
    assert any(path.startswith("raw/mac-accuracy/") for path in paths)
    assert any(path.startswith("raw/manual-judges-gcp/") for path in paths)
    assert all((root / path).is_file() for path in paths)
    assert all(not path.endswith("/") for path in paths)

    for path in root.glob("raw/**/*.json*"):
        text = path.read_text(encoding="utf-8")
        assert "/home/elijahnelson/" not in text
        assert "/Users/elijahnelson/" not in text
        assert "/private/tmp/" not in text
        assert '"/tmp/' not in text

    markdown_link = re.compile(r"\[[^\]]+\]\(<?([^)\n>]+)>?\)")
    for document in root.glob("raw/**/*.md"):
        for target in markdown_link.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            destination = (document.parent / target.split("#", 1)[0]).resolve()
            assert destination.is_file() or (
                destination.is_dir() and (destination / "index.html").is_file()
            ), f"broken published evidence link: {document} -> {target}"


def test_gate_two_evidence_builder_refuses_foreign_output(tmp_path):
    out = tmp_path / "keep"
    out.mkdir()
    (out / "precious.txt").write_text("keep")
    with pytest.raises(SystemExit):
        build_gate_two_evidence.build(out)
    assert (out / "precious.txt").read_text() == "keep"


def test_snapshot_carries_every_evidence_lane(site):
    state = json.loads((site / "api/state.json").read_text())
    for lane in build_static.EVIDENCE_LANES:
        assert state[lane] is not None, lane
    assert state["current"] is None
    assert state["snapshot"]["path"] == "api/state.json"
    assert state["models"], "stored model runs should be listed"
    assert state["runs_by_model"], "finished stored runs should be listed"
    assert set(state["runs_by_model"]) <= {model["file"] for model in state["models"]}


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
