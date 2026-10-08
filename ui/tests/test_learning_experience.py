from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui"


def test_learning_style_picker_is_accessible_persistent_and_sent_to_chat() -> None:
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    css = (UI / "styles.css").read_text()

    assert 'id="teaching-style"' in html
    assert 'role="group"' in html
    assert html.count('data-mode="') == 4
    for mode in ("socratic", "subgoal", "analogy", "hints"):
        assert f'data-mode="{mode}"' in html
    assert 'aria-pressed="true"' in html
    assert 'id="style-pill"' in html
    assert "body: JSON.stringify({ preferred_style: mode })" in js
    assert "`/v1/conversations/${targetConversationId}/style`" in js
    assert "mode: teachingMode" in js
    assert "persona: teachingPersona" in js
    assert "personaForConversation" in js
    assert "styleSaveQueue" in js
    assert "persistedConversationStyleVersions" in js
    assert "MutaTeachingStylePolicy.canApplyServerStyle" in js
    assert "MutaTeachingStylePolicy.assignedConversationStyle" in js
    assert "function reconcileAssignedConversationStyle" in js
    repair_body = js.split("function repairConversationStyle", 1)[1].split(
        "function reconcileAssignedConversationStyle", 1
    )[0]
    assert 'fetch(`/v1/conversations/${conversationId}/style`' in repair_body
    assert 'fetch("/v1/settings"' not in repair_body
    assert "localStorage.setItem" not in repair_body
    assert "nextRepairVersion" in repair_body
    assert "updatePendingStyleMarker(targetConversationId, currentViewId, mode)" in js
    assert "requested_mode: teachingMode" in js
    assert "reconcileAssignedConversationStyle(" in js
    assert js.count("const pendingMarker = pendingStyleMarker(clientRequestId);") == 1
    assert "TEACHING_STYLE_KEYS[settings.preferred_style]" in js
    assert "@media (max-width: 420px)" in css
    assert "min-width: 0; min-height: 44px" in css
    assert ".style-pill { display: block;" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".teaching-style-options button { transition: none; }" in css


def test_study_country_setting_uses_africa_registry_and_private_settings_api() -> None:
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()

    assert 'id="setting-study-country"' in html
    assert 'data-i18n="settings.studyCountry"' in html
    assert "window.MutaAfricaLanguages.countries" in js
    assert 'body: JSON.stringify({ study_country: code || null })' in js
    assert 'studyCountrySelect.value = settings.study_country || ""' in js


def test_offline_stem_unit_library_has_verified_units_visualizations_and_citations() -> None:
    schema = json.loads((UI / "units/schema.json").read_text())
    packs = [
        json.loads(path.read_text())
        for path in sorted((UI / "units").glob("*.json"))
        if path.name != "schema.json"
    ]
    assert {pack["topic"] for pack in packs} == {
        "linear_equations", "forces_motion", "chemical_equations", "photosynthesis",
    }
    assert len(packs) == 4
    assert schema["properties"]["checkpoint"]["properties"]["questions"]["minItems"] == 5
    section_schema = schema["properties"]["sections"]["items"]
    question_schema = schema["properties"]["checkpoint"]["properties"]["questions"]["items"]
    citation_schema = schema["properties"]["citations"]["items"]
    for pack in packs:
        assert len(pack["checkpoint"]["questions"]) == 5
        assert all("expected" not in question for question in pack["checkpoint"]["questions"])
        assert any("visualization" in section for section in pack["sections"])
        assert len(pack["citations"]) >= 2
        assert all(citation["url"].startswith("https://openstax.org/") for citation in pack["citations"])
        assert set(schema["required"]) <= set(pack) <= set(schema["properties"])
        assert all(set(section_schema["required"]) <= set(row) <= set(section_schema["properties"]) for row in pack["sections"])
        assert all(set(question_schema["required"]) <= set(row) <= set(question_schema["properties"]) for row in pack["checkpoint"]["questions"])
        assert all(set(citation_schema["required"]) <= set(row) <= set(citation_schema["properties"]) for row in pack["citations"])

    script = """
const viz=require('./ui/visualizations.js');
const fs=require('fs');
for (const file of fs.readdirSync('./ui/units').filter((name)=>name.endsWith('.json') && name !== 'schema.json')) {
  const pack=require('./ui/units/'+file);
  for (const section of pack.sections) {
    if (section.visualization && !viz.validateSpec(section.visualization).ok) process.exit(1);
  }
}
"""
    subprocess.run(["node", "-e", script], cwd=ROOT, check=True)


def test_unit_ui_uses_offline_import_server_verifier_mastery_and_reduced_motion() -> None:
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    css = (UI / "styles.css").read_text()
    build = (ROOT / "scripts/build_ui_dist.py").read_text()

    assert 'id="unit-modal"' in html and 'aria-modal="true"' in html
    assert 'id="file-unit" accept="application/json,.json,.muta"' in html
    assert "new FileReader()" in js and "reader.readAsText(file)" in js
    assert 'fetch("/v1/units/checkpoint"' in js
    assert 'body.progress_saved === false' in js
    assert 't("unit.progressNotSaved")' in js
    assert "body.mastery?.[pack.topic]" in js
    assert "window.MutaViz.renderAll" in js
    assert 'input.setAttribute("aria-describedby"' in js
    assert 'result.setAttribute("role", "status")' in js
    assert "void showUnitLibrary();" in js
    assert "MAX_UNIT_FILE_BYTES" in js and "file.size > MAX_UNIT_FILE_BYTES" in js
    assert "pack.sections.length > 20" in js
    assert "hasOnlyUnitKeys" in js
    assert "Number.isInteger(pack.estimated_minutes)" in js
    assert "const canVerify = trusted && BUILT_IN_UNIT_IDS.has(pack.id)" in js
    assert js.count('subject: "') == 4
    assert 'id="unit-library"' in html and 'id="unit-back"' in html
    assert "input.disabled = !canVerify" in js
    assert 'if (!canVerify) form.addEventListener("submit"' in js
    assert 'if (canVerify) form.addEventListener("submit"' in js
    assert 'UI_DIRECTORIES = ("brand", "units", "courses")' in build
    assert "@media (max-width: 540px)" in css
    assert ".unit-panel { max-height: 100dvh; min-height: 100dvh;" in css
    assert ".unit-mastery-track span { transition: none; }" in css
    assert 'aria-labelledby="unit-mastery-label"' in html
    assert ".unit-visualization .muta-visualization { min-width: 42rem; }" in css
    assert "env(safe-area-inset-top)" in css


def test_portable_learning_platform_ships_five_valid_source_backed_courses() -> None:
    html = (UI / "index.html").read_text()
    platform = (UI / "learning-platform.js").read_text()
    platform_css = (UI / "learning-platform.css").read_text()
    i18n = (UI / "i18n.js").read_text()
    builder = (ROOT / "scripts/build_ui_dist.py").read_text()
    courses = sorted((UI / "courses").glob("*.muta"))

    assert len(courses) == 5
    assert 'id="learning-center"' in html
    assert 'data-learning-tab="studio"' in html
    assert 'data-learning-tab="practice"' in html
    assert 'data-learning-tab="games"' in html
    assert 'data-learning-tab="playground"' in html
    assert 'data-learning-tab="tracker"' in html
    assert 'data-learning-tab="correctness"' in html
    assert 'id="file-course"' in html and ".muta" in html
    assert '"learning-platform.css"' in builder
    assert '"learning-platform.js"' in builder
    assert '"course-schema-v2.json"' in builder
    assert 'UI_DIRECTORIES = ("brand", "units", "courses")' in builder
    assert "MAX_FILE_BYTES = 2 * 1024 * 1024" in platform
    assert "noExecutableMarkup" in platform
    assert "indexedDB" in platform
    assert "course_export" in platform and "course_import" in platform
    assert "Evidence of learning—not screen-time theatre" in i18n
    assert "Mastery changes only" in i18n
    assert 'root.focus({ preventScroll: true })' in platform
    assert '$("#learning-center .learning-shell")?.scrollTo' in platform
    assert 'global.requestAnimationFrame?.(reset)' in platform
    assert 'document.addEventListener?.("muta:localechange"' in platform
    assert "@media (max-width: 520px)" in platform_css
    assert "@media (prefers-reduced-motion: reduce)" in platform_css

    parsed = [json.loads(path.read_text()) for path in courses]
    assert {course["subject"] for course in parsed} == {
        "Artificial Intelligence", "Mathematics", "Physical Science", "Life Science", "History",
    }
    for course in parsed:
        assert course["version"] == 2 and course["kind"] == "course"
        assert len(course["activities"]) >= 3
        assert course["games"] and course["playgrounds"]
        assert course["sources"]
        assert all(source["url"].startswith("https://") for source in course["sources"])

    script = r"""
const fs=require('fs'); const path=require('path');
global.document={querySelector:()=>null,querySelectorAll:()=>[],visibilityState:'visible'};
global.localStorage={getItem:()=>null,setItem:()=>{}};
global.addEventListener=()=>{}; global.setInterval=()=>0; global.setTimeout=()=>0;
global.MutaViz=require('./ui/visualizations.js'); require('./ui/learning-platform.js');
for (const name of fs.readdirSync('./ui/courses').filter((name)=>name.endsWith('.muta'))) {
  const course=JSON.parse(fs.readFileSync(path.join('./ui/courses',name),'utf8'));
  if (!global.MutaLearning.validateCourse(course)) process.exit(1);
}
"""
    subprocess.run(["node", "-e", script], cwd=ROOT, check=True)


def test_first_run_tour_is_once_only_replayable_and_uses_real_targets() -> None:
    html = (UI / "index.html").read_text()
    platform = (UI / "learning-platform.js").read_text()

    assert 'id="muta-tour"' in html
    assert 'id="replay-tour"' in html
    assert "muta-first-tour-v1" in platform
    assert '{ selector: "#teaching-style"' in platform
    assert '{ selector: "#unit-open"' in platform
    assert '{ selector: "#composer"' in platform
    assert 'localStorage.setItem(TOUR_KEY, result)' in platform
    assert 'startTour({ replay: true })' in platform


def test_packaged_unit_directory_prefers_the_staged_browser_bundle(tmp_path: Path) -> None:
    from orchestrator.pedagogy.units import resolve_units_dir

    packaged = tmp_path / "ui" / "dist" / "units"
    packaged.mkdir(parents=True)
    legacy = tmp_path / "ui" / "units"
    legacy.mkdir(parents=True)

    assert resolve_units_dir(tmp_path) == packaged
