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
SEMANTIC_CHANGES_PATH = ROOT / "ui/i18n-semantic-changes.json"
SEMANTIC_OVERRIDES_PATH = ROOT / "ui/locale-semantic-overrides.json"
HOST_CAPACITY_WARNING_OVERRIDES_PATH = ROOT / "ui/locale-host-capacity-warning.json"


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
require('./ui/locales.js');
require('./ui/locale-generated.js');
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
    assert len(actual["key_references"]) > 250
    assert all(row["status"] == "pending-i18n" for row in actual["literal_candidates"])
    assert all(row["reason"].strip() for row in actual["literal_exceptions"])


def test_extractor_catches_a_visible_literal_hidden_behind_a_variable(
    tmp_path: Path,
) -> None:
    extractor = _load_extractor()
    source = tmp_path / "probe.js"
    source.write_text('const message = "Visible error"; node.textContent = message;\n')
    extractor.ROOT = tmp_path
    _, literals = extractor.javascript_inventory(source)
    assert {
        "file": "probe.js",
        "line": 1,
        "kind": "js-ui-variable",
        "text": "Visible error",
    } in literals


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

    for row in inventory["key_references"]:
        if row["kind"] in {"js:featureT", "js:powerText", "js:releaseT"}:
            assert row["key"] in english, row


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


def test_every_changed_english_meaning_has_a_durable_visible_locale_override() -> None:
    runtime = _runtime_catalogs()
    changes = json.loads(SEMANTIC_CHANGES_PATH.read_text())
    overrides = json.loads(SEMANTIC_OVERRIDES_PATH.read_text())
    english = runtime["catalogs"]["en"]
    visible = set(runtime["visible"]) - {"en"}

    assert len(changes) == 9
    assert set(overrides) == visible
    for key, change in changes.items():
        assert english[key] == change["after"]
        assert change["before"] != change["after"]
    for tag, rows in overrides.items():
        assert set(rows) == set(changes), tag
        composer = rows["composer.placeholder"]
        assert "Enter" not in composer and "Ctrl" not in composer, (
            f"{tag}:composer.placeholder retains the retired keyboard instructions"
        )
        assert len(composer) <= 60, f"{tag}:composer.placeholder is not the compact prompt"
        for key, value in rows.items():
            assert runtime["catalogs"][tag][key] == value, f"{tag}:{key} override"
            assert value not in {changes[key]["before"], changes[key]["after"]}, (
                f"{tag}:{key} silent English semantic fallback"
            )

    generator = (ROOT / "scripts/generate_ui_catalogs.py").read_text()
    assert "HAND_RELEASE_OVERRIDE_KEYS = SEMANTIC_CHANGE_KEYS" in generator
    assert "messages.update(SEMANTIC_OVERRIDES.get(tag, {}))" in generator


def test_host_capacity_warning_is_actionable_and_translated_in_every_visible_locale() -> None:
    runtime = _runtime_catalogs()
    overrides = json.loads(HOST_CAPACITY_WARNING_OVERRIDES_PATH.read_text())
    english = runtime["catalogs"]["en"]["host.capacityInsufficient"]
    visible = set(runtime["visible"]) - {"en"}

    assert english == (
        "Muta cannot fit one Host-mode chat in the RAM currently available; "
        "close other applications or install a smaller model"
    )
    assert set(overrides) == visible
    for tag, value in overrides.items():
        assert value.strip() == value and "\n" not in value, tag
        assert value != english, f"{tag}: silent English Host warning fallback"
        assert any(name in value for name in ("Muta", "I-Muta", "ሙታ")), tag
        assert len(value) >= 55, f"{tag}: warning lost actionability"
        assert runtime["catalogs"][tag]["host.capacityInsufficient"] == value

    generator = (ROOT / "scripts/generate_ui_catalogs.py").read_text()
    assert 'HOST_CAPACITY_WARNING_KEY = "host.capacityInsufficient"' in generator
    assert "messages[HOST_CAPACITY_WARNING_KEY] = HOST_CAPACITY_WARNING_OVERRIDES[tag]" in generator


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
