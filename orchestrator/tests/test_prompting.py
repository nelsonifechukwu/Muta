"""Per-student prompt assembly: persona/language become real, cache prefix stays intact."""

from __future__ import annotations

from orchestrator.gateway.prompting import assemble_system_prompt, persona_language_directive

BASE = "You are Muta.\n\n--- per-student context (variable — keep last) ---"


def test_english_teacher_turn_includes_the_explicit_preference():
    out = assemble_system_prompt(BASE, persona="teacher", language="en")
    assert out.startswith(BASE.rstrip())
    assert "teacher's voice" in out
    assert "preferred response language is English (en)" in out


def test_non_english_language_is_instructed():
    out = assemble_system_prompt(BASE, persona="friend", language="yo")
    assert "preferred response language is Yoruba (yo)" in out
    assert "unless the user explicitly requests another language" in out
    assert "classmate" in out
    assert "LaTeX" in out


def test_auto_follows_the_latest_message_not_older_history():
    out = assemble_system_prompt(BASE, persona="friend", language="auto")
    assert "response language preference is AUTO" in out
    assert "primary natural language" in out
    assert "latest message" in out
    assert "older conversation history uses another language" in out
    assert "too short or ambiguous" in out


def test_language_directive_protects_literal_content_and_requests_natural_explanations():
    out = persona_language_directive("teacher", "de")
    assert "German (de)" in out
    for protected in ("source code", "variable names", "commands", "URLs", "proper nouns"):
        assert protected in out
    assert "naturally rather than literally" in out


def test_unknown_language_tag_passes_through():
    assert "preferred response language is zz" in persona_language_directive("teacher", "zz")


def test_exam_persona_is_minimal_hints():
    assert "minimal hints" in persona_language_directive("exam", "en")


def test_layers_only_appear_when_present():
    plain = assemble_system_prompt(BASE, persona="teacher", language="en")
    withctx = assemble_system_prompt(
        BASE,
        persona="teacher",
        language="en",
        twin_summary="Working on: quadratics.",
        web_lines="[1] Foo — bar.",
        rag_block="<<<reference-material>>>\n[a:1] text\n<<<end-reference-material>>>",
    )
    assert "learning record" in withctx and "learning record" not in plain
    assert "Web context" in withctx
    assert "reference-material" in withctx
    # The shared prefix (the base mode prompt) is unchanged at the front either way.
    assert withctx.startswith(BASE.rstrip())


def test_subject_focus_added_for_non_math():
    assert "physics" in persona_language_directive("teacher", "en", subject="physics")
    assert "working on" not in persona_language_directive("teacher", "en", subject="math")
