"""Math-to-speech tests (TDD T9: 60-expression speech goldens).

Each golden is what a student *hears*. The suite is parametrised per case so a regression
names the expression that started reading wrong, which is the only useful form of this
failure — "59/60" tells you nothing you can fix.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.audio.mathspeech import (
    number_to_words,
    speak,
    split_sentences,
    to_speech,
    verbalize,
)

GOLDENS = Path(__file__).resolve().parent.parent / "audio" / "goldens" / "speech_goldens.json"
CASES = json.loads(GOLDENS.read_text())["cases"]


def test_golden_set_is_the_promised_size():
    assert len(CASES) == 60, "T9 promises 60 expressions"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["input"])
def test_golden(case):
    assert speak(case["input"]) == case["speech"], case["note"]


# --- the rules behind the goldens ---------------------------------------------------------


def test_the_tdd_example():
    """§7.7's own illustration: 'x squared plus three x over two'."""
    assert speak(r"$x^2 + \frac{3x}{2}$") == "x squared plus three x over two"


@pytest.mark.parametrize(
    "value,words",
    [
        ("0", "zero"),
        ("7", "seven"),
        ("13", "thirteen"),
        ("42", "forty two"),
        ("100", "one hundred"),
        ("250", "two hundred and fifty"),
        ("1000", "one thousand"),
        ("2026", "two thousand and twenty six"),
        ("3.5", "three point five"),
        ("-7", "minus seven"),
        ("123456", "123456"),  # beyond the range: leave it to the voice rather than guess
    ],
)
def test_number_to_words(value, words):
    assert number_to_words(value) == words


def test_units_are_spoken_never_spelled():
    """'twelve see em' is the single most common complaint about maths TTS, and WAEC answers
    are full of units."""
    assert speak("12 cm") == "twelve centimetres"
    assert speak("500 mg") == "five hundred milligrams"


def test_unary_and_binary_minus_are_different_words():
    assert speak("-7") == "negative seven"
    assert speak("a - b") == "a minus b"


def test_prose_survives_verbalisation():
    spoken = speak(r"First, factorise. The area is $\pi r^2$ square units.")
    assert spoken.startswith("First, factorise.")
    assert "pi r squared" in spoken


def test_bare_latex_without_delimiters_is_still_verbalised():
    """Models emit undelimited LaTeX constantly; a voice reading 'backslash frac' is a worse
    failure than over-verbalising an English sentence."""
    assert "over" in speak(r"\frac{3}{7}")


def test_empty_input_is_empty_output():
    assert speak("") == "" and speak("   ") == ""
    assert to_speech("") == []


def test_sentences_are_split_for_pipelined_synthesis():
    """Sentence-level streaming is why first audio arrives ~1 s in instead of after the whole
    answer is generated (§6.6)."""
    parts = split_sentences("Factorise first. Then solve. Why does that work?")
    assert len(parts) == 3 and parts[-1].endswith("?")


def test_abbreviation_inside_a_sentence_does_not_split_it():
    assert len(split_sentences("The value 3.5 kg is given.")) == 1


def test_to_speech_tags_language_for_voice_routing():
    spoken = to_speech(r"Solve $x = 2$. Then check.", language="ha")
    assert [s.language for s in spoken] == ["ha", "ha"]
    assert spoken[0].text == "Solve x equals two."


def test_verbalize_leaves_no_latex_control_sequences_behind():
    """Whatever the model emits, the voice must not read a backslash."""
    for expression in (r"\frac{\sqrt{2}}{2}", r"\sum_{i=1}^{n} i", r"\lim_{x \to 0} \frac{\sin x}{x}"):
        assert "\\" not in verbalize(expression), expression
