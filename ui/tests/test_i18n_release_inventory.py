from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "ui/i18n-source-inventory.json"
GATE_PATH = ROOT / "ui/i18n-release-gate.json"
EQUIVALENTS_PATH = ROOT / "ui/i18n-english-equivalents.json"


def _load_extractor():
    path = ROOT / "scripts/extract_ui_i18n.py"
    spec = importlib.util.spec_from_file_location("extract_ui_i18n", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_catalogs() -> dict:
    script = r"""
globalThis.MutaAfricaLanguages=require('./ui/africa-languages.js');
globalThis.MutaInterfaceLocales=require('./ui/locale-manifest.js');
globalThis.MutaI18n=require('./ui/i18n.js');
globalThis.window=globalThis;
require('./ui/locale-fr.js');
require('./ui/locale-generated.js');
require('./ui/locales.js');
process.stdout.write(JSON.stringify({
  catalogs: MutaI18n.catalogs,
  visible: MutaI18n.supportedDefinitions().map((locale) => locale.tag),
}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _placeholders(value: str) -> list[str]:
    return sorted(re.findall(r"\{[a-zA-Z][\w]*\}", value))


def test_checked_in_source_inventory_is_complete_and_deterministic() -> None:
    expected = json.loads(INVENTORY_PATH.read_text())
    actual = _load_extractor().build_inventory()
    assert actual == expected, (
        "UI localization inventory drifted. Route new visible copy through canonical i18n, or "
        "run `python scripts/extract_ui_i18n.py --write` and review every new literal candidate."
    )
    assert actual["catalog"]["english_key_count"] == len(actual["catalog"]["english_keys"])
    assert len(actual["key_references"]) > actual["catalog"]["english_key_count"]
    assert all(row["status"] == "pending-i18n" for row in actual["literal_candidates"])


def test_every_canonical_html_and_javascript_key_exists() -> None:
    inventory = json.loads(INVENTORY_PATH.read_text())
    english = set(inventory["catalog"]["english_keys"])
    canonical_references = [
        row
        for row in inventory["key_references"]
        if row["kind"].startswith("html:") or row["kind"] == "js:t"
    ]
    assert canonical_references
    missing = [row for row in canonical_references if row["key"] not in english]
    assert missing == []

    resource_definitions = {
        row["key"]
        for row in inventory["key_references"]
        if row["kind"] == "js-copy-definition:RESOURCE_RAG_COPY"
    }
    power_definitions = {
        row["key"]
        for row in inventory["key_references"]
        if row["kind"] == "js-copy-definition:POWER_COPY"
    }
    assert resource_definitions
    assert power_definitions
    for row in inventory["key_references"]:
        if row["kind"] == "js:featureT":
            assert row["key"] in resource_definitions, row
        elif row["kind"] == "js:powerText":
            assert row["key"] in power_definitions, row


def test_dependency_gate_prevents_premature_release_localization() -> None:
    gate = json.loads(GATE_PATH.read_text())
    inventory = json.loads(INVENTORY_PATH.read_text())
    dependencies = gate["dependencies"]
    complete = all(re.fullmatch(r"[0-9a-f]{40}", value or "") for value in dependencies.values())
    if complete:
        assert gate["phase"] == "release"
        assert inventory["phase"] == "release"
        assert inventory["literal_candidates"] == []
    else:
        assert gate["phase"] == "awaiting-dependencies"
        assert inventory["phase"] == "awaiting-dependencies"
        assert set(dependencies) == {"ui", "host_mode", "power"}
        assert any(value is None for value in dependencies.values())
        pending_text = {row["text"] for row in inventory["literal_candidates"]}
        assert "Use your device setting, or keep Muta in light or dark mode." in pending_text
        assert "Checking host power…" in pending_text
        assert "Could not read Host mode settings." in pending_text
        assert "Muta could not save that privacy setting. Please try again." in pending_text
        assert "settings.limits" in inventory["catalog"]["english_keys"]


def test_visible_catalogs_have_exact_keys_and_placeholders() -> None:
    runtime = _runtime_catalogs()
    english = runtime["catalogs"]["en"]
    required = set(english)
    for tag in runtime["visible"]:
        catalog = runtime["catalogs"][tag]
        assert set(catalog) == required, f"{tag} key parity"
        for key, source in english.items():
            assert isinstance(catalog[key], str) and catalog[key].strip(), f"{tag}:{key} empty"
            assert _placeholders(catalog[key]) == _placeholders(source), (
                f"{tag}:{key} placeholder drift"
            )


def test_visible_locales_have_no_unreviewed_exact_english_fallbacks() -> None:
    runtime = _runtime_catalogs()
    english = runtime["catalogs"]["en"]
    allowed = json.loads(EQUIVALENTS_PATH.read_text())
    actual: dict[str, dict[str, str]] = {}
    for tag in runtime["visible"]:
        if tag == "en":
            continue
        catalog = runtime["catalogs"][tag]
        identical = {
            key: allowed.get(tag, {}).get(key, "")
            for key, value in catalog.items()
            if value == english[key]
        }
        if identical:
            actual[tag] = identical
    assert actual == allowed
    assert all(reason.strip() for entries in allowed.values() for reason in entries.values())


def test_release_phase_enforces_exact_copy_and_removed_helpers() -> None:
    gate = json.loads(GATE_PATH.read_text())
    if gate["phase"] != "release":
        return
    runtime = _runtime_catalogs()
    english_values = set(runtime["catalogs"]["en"].values())
    assert "Muta can make mistakes. Check important info." in english_values
    assert "Auto mode detects your language and replies in it." in english_values
    assert "Help us improve Muta by sharing your analytics." in english_values
    assert "settings.limits" not in runtime["catalogs"]["en"]
    html = (ROOT / "ui/index.html").read_text()
    assert "Use your device setting, or keep Muta in light or dark mode." not in html
