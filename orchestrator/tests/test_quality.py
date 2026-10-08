from __future__ import annotations

import json
from pathlib import Path

from orchestrator.gateway.integrity import IntegrityGuard
from orchestrator.gateway.quality import (
    CombinedReplyGuard,
    ResponseQualityGuard,
    build_response_guard,
    correctly_explains_series_current,
    deduplicate_sentences,
    detect_pathological_repetition,
    expected_response_language,
    has_balanced_photosynthesis_equation,
    looks_like_swahili,
)

FIXTURES = Path(__file__).parent / "fixtures" / "semifinal_judge_prompts.json"
JUDGE_PROMPTS = json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_three_repeated_sentences_are_pathological_but_two_are_not():
    sentence = "Mmea unahitaji mwanga wa jua."
    assert not detect_pathological_repetition(sentence * 2).pathological
    finding = detect_pathological_repetition(sentence * 3)
    assert finding.pathological
    assert finding.count == 3


def test_repeated_four_gram_loop_is_detected_without_sentence_punctuation():
    loop = "mwanga wa jua hutoa nishati " * 12
    finding = detect_pathological_repetition(loop)
    assert finding.pathological
    assert finding.repeated_ngram_ratio >= 0.58


def test_sentence_deduplication_keeps_order_and_unique_content():
    reply = "Check the sign. Check the sign. Try substitution. Check the sign."
    assert deduplicate_sentences(reply) == "Check the sign. Try substitution."


def test_swahili_detection_and_default_language_override_for_exact_judge_prompt():
    prompt = JUDGE_PROMPTS["swahili_photosynthesis"]
    reply = "Usanisinuru ni mchakato wa mmea unaotumia maji na mwanga wa jua."
    assert expected_response_language("en", prompt) == "sw"
    assert expected_response_language("auto", prompt) == "sw"
    assert looks_like_swahili(reply)
    assert not looks_like_swahili("Photosynthesis is how the plant uses light and water.")


def test_balanced_photosynthesis_equation_accepts_unicode_or_ascii_not_unbalanced():
    assert has_balanced_photosynthesis_equation("6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂")
    assert has_balanced_photosynthesis_equation("6CO2 + 6H2O -> C6H12O6 + 6O2")
    assert not has_balanced_photosynthesis_equation("CO2 + H2O -> C6H12O6 + O2")


def test_exact_swahili_judge_prompt_retries_bad_loop_then_uses_safe_fallback():
    guard = build_response_guard(
        IntegrityGuard(),
        language="en",
        message=JUDGE_PROMPTS["swahili_photosynthesis"],
    )
    broken = "Hii kwa nini mmea unahitaji mwanga. " * 4

    first = guard(broken, 0)
    second = guard("Photosynthesis is how a plant makes food.", 1)

    assert guard.requires_buffering
    assert first.retry_instruction
    assert first.retry_params["dry_multiplier"] == 0.8
    assert first.retry_params["repeat_last_n"] == 128
    assert first.retry_params["max_tokens"] == 384
    assert looks_like_swahili(second.text)
    assert has_balanced_photosynthesis_equation(second.text)
    assert not detect_pathological_repetition(second.text).pathological


def test_swahili_language_failure_on_unrelated_subject_never_invents_photosynthesis():
    guard = build_response_guard(
        IntegrityGuard(),
        language="sw",
        message="Nisaidie kuelewa mlinganyo huu wa aljebra.",
    )

    first = guard("Here is the final algebra answer.", 0)
    second = guard("I still cannot answer in Swahili.", 1)

    assert first.retry_instruction
    assert looks_like_swahili(second.text)
    assert second.text.startswith(
        "Bado ninajifunza Kiswahili vizuri — hapa ni maelezo kwa Kiingereza."
    )
    assert "I still cannot answer in Swahili." in second.text
    assert "usanisinuru" not in second.text.casefold()


def test_combined_guard_preserves_integrity_retry_and_quality_parameters():
    class RetryIntegrity(IntegrityGuard):
        def review(self, reply: str, attempt: int):
            from runtime.chat import ReplyGuardResult

            if attempt == 0:
                return ReplyGuardResult(
                    "",
                    retry_instruction="Correct the verified step.",
                    retry_params={"temperature": 0.0},
                )
            return ReplyGuardResult("The checked step is not equivalent.")

    guard = CombinedReplyGuard(RetryIntegrity(), ResponseQualityGuard())
    first = guard("You are correct.", 0)
    second = guard("You are correct.", 1)
    assert "Correct the verified step" in first.retry_instruction
    assert first.retry_params["temperature"] == 0.0
    assert second.text == "The checked step is not equivalent."


def test_series_misconception_is_checked_and_falls_back_to_a_correct_distinct_strategy():
    prompt = JUDGE_PROMPTS["series_adaptation"]
    guard = build_response_guard(
        IntegrityGuard(),
        language="en",
        message=prompt,
        series_strategy="charge-counter thought experiment",
    )

    wrong = "Exactly. The first bulb uses up current, so the second gets less current."
    first = guard(wrong, 0)
    second = guard(wrong, 1)

    assert guard.requires_buffering
    assert "same through both series bulbs" in first.retry_instruction
    assert correctly_explains_series_current(second.text)
    assert "counter" in second.text.casefold()
