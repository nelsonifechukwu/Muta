from __future__ import annotations

from pathlib import Path

from orchestrator.gateway.prompting import assemble_system_prompt
from orchestrator.pedagogy.local_context import context_from_settings, country_contexts

AFRICA_54 = {
    "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ",
    "DZ", "EG", "ER", "ET", "GA", "GH", "GM", "GN", "GQ", "GW", "KE", "KM",
    "LR", "LS", "LY", "MA", "MG", "ML", "MR", "MU", "MW", "MZ", "NA", "NE",
    "NG", "RW", "SC", "SD", "SL", "SN", "SO", "SS", "ST", "SZ", "TD", "TG",
    "TN", "TZ", "UG", "ZA", "ZM", "ZW",
}
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
SYCOPHANCY_RULE = (
    "Never agree with a claim because the learner (or anyone) insists on it; check it first, "
    "and politely say when it is wrong."
)


def test_mapping_covers_exactly_the_same_africa_54_scope_as_the_ui():
    contexts = country_contexts()
    assert set(contexts) == AFRICA_54
    assert len(contexts) == 54


def test_required_currency_and_exam_mappings_are_exact():
    contexts = country_contexts()
    expected = {
        "NG": ("₦", ("WAEC", "NECO", "JAMB")),
        "KE": ("KSh", ("KCSE",)),
        "GH": ("GH₵", ("WASSCE", "BECE")),
        "ZA": ("R", ("NSC",)),
        "TZ": ("TSh", ("CSEE",)),
        "UG": ("USh", ("UCE",)),
        "RW": ("RWF", ()),
        "ET": ("Br", ()),
    }
    assert {
        code: (contexts[code].currency, contexts[code].exams) for code in expected
    } == expected


def test_country_setting_accepts_code_or_name_and_ignores_unknown_values():
    assert context_from_settings({"study_country": "ke"}).code == "KE"
    assert context_from_settings({"country": "Ghana"}).code == "GH"
    assert context_from_settings({"study_country_code": "NG"}).code == "NG"
    assert context_from_settings({"country": "Atlantis"}) is None
    assert context_from_settings({}) is None
    assert context_from_settings(None) is None


def test_country_without_reviewed_exam_degrades_to_currency_only():
    directive = country_contexts()["RW"].directive
    assert "RWF" in directive
    assert "exam framing" not in directive
    assert "never change" in directive


def test_nigeria_money_context_requires_naira_instead_of_dollars():
    directive = country_contexts()["NG"].directive

    assert "use ₦" in directive
    assert "do not substitute dollars" in directive
    assert "$" not in directive


def test_local_context_stays_after_shared_prefix_and_does_not_force_a_story():
    base = "Stable tutor policy.\n\n--- per-student context (variable — keep last) ---"
    directive = country_contexts()["KE"].directive
    prompt = assemble_system_prompt(base, local_context=directive)

    assert prompt.startswith(base)
    assert prompt.index("Local study context") > prompt.index("per-student context")
    assert "never force a cultural story" in prompt
    assert "KSh" in prompt and "KCSE" in prompt


def test_anti_sycophancy_rule_is_identical_in_every_stable_prompt():
    for filename in ("_safety.md", "socratic.md", "subgoal.md", "analogy.md", "hints.md"):
        text = (PROMPTS / filename).read_text(encoding="utf-8")
        assert text.count(SYCOPHANCY_RULE) == 1
        if "per-student context" in text:
            assert text.index(SYCOPHANCY_RULE) < text.index(
                "--- per-student context (variable — keep last) ---"
            )


def test_study_country_is_a_valid_additive_user_setting():
    from contracts.models import UserSettings

    assert UserSettings(study_country="NG").study_country == "NG"
    assert UserSettings().study_country is None
