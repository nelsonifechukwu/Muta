"""Math → spoken English (TDD §7.7).

    >>> speak(r"Solve $x^2 + \\frac{3x}{2} = 0$")
    'Solve x squared plus three x over two equals zero'

Rules, in the order they have to run:

1. fractions (recursive, innermost first) — `\\frac{3x}{2}` → "three x over two"
2. roots, powers, functions — the notational forms
3. symbols and operators — greek letters, relations, arithmetic
4. numbers — "3" → "three", because a TTS voice reading "3.5" as "three point five" beats
   the voice's own guess, and because *we* can then unit-test what the student hears
5. units — "cm" → "centimetres", never "see em"

Pure Python, no model, no network: it is a golden-tested lookup pipeline (60 expressions,
T9 acceptance), which is exactly what it should be — nobody should need a GPU to find out
why a fraction was read wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- numbers -----------------------------------------------------------------------------

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_to_words(value: str) -> str:
    """Integers to 9999 and simple decimals. Anything larger stays as digits — a voice
    reading "12345" is fine; a wrong myriad is not."""
    text = value.strip()
    negative = text.startswith("-")
    text = text.lstrip("-")
    if "." in text:
        whole, _, frac = text.partition(".")
        spoken_frac = " ".join(_ONES[int(d)] for d in frac if d.isdigit())
        spoken = f"{_int_to_words(whole)} point {spoken_frac}".strip()
    else:
        spoken = _int_to_words(text)
    return f"minus {spoken}" if negative else spoken


def _int_to_words(digits: str) -> str:
    if not digits.isdigit():
        return digits
    n = int(digits)
    if n >= 10_000:
        return digits
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        out = f"{_ONES[hundreds]} hundred"
        return out + (f" and {_int_to_words(str(rest))}" if rest else "")
    thousands, rest = divmod(n, 1000)
    out = f"{_int_to_words(str(thousands))} thousand"
    if not rest:
        return out
    joiner = " and " if rest < 100 else " "
    return out + joiner + _int_to_words(str(rest))


# --- vocabulary ---------------------------------------------------------------------------

#: Common fractions get their idiomatic name; everything else is "a over b". "one over two"
#: is not wrong, but no teacher says it.
_NAMED_FRACTIONS = {
    ("1", "2"): "one half",
    ("1", "3"): "one third",
    ("2", "3"): "two thirds",
    ("1", "4"): "one quarter",
    ("3", "4"): "three quarters",
    ("1", "5"): "one fifth",
}

_GREEK = {
    "π": "pi", "θ": "theta", "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "Δ": "delta", "λ": "lambda", "μ": "mu", "σ": "sigma", "Σ": "sum of", "φ": "phi",
    "ω": "omega", "ρ": "rho", "τ": "tau", "ε": "epsilon", "∞": "infinity",
}

_LATEX_WORDS = [
    (r"\\times", " times "),
    (r"\\cdot", " times "),
    (r"\\div", " divided by "),
    (r"\\pm", " plus or minus "),
    (r"\\leq|\\le\b|≤", " is less than or equal to "),
    (r"\\geq|\\ge\b|≥", " is greater than or equal to "),
    (r"\\neq|≠", " is not equal to "),
    (r"\\approx|≈", " is approximately "),
    (r"\\infty", " infinity "),
    (r"\\pi\b", " pi "),
    (r"\\theta\b", " theta "),
    (r"\\alpha\b", " alpha "),
    (r"\\beta\b", " beta "),
    (r"\\lambda\b", " lambda "),
    (r"\\Delta\b|\\delta\b", " delta "),
    (r"\\int", " the integral of "),
    (r"\\sum", " the sum of "),
    (r"\\prod", " the product of "),
    (r"\\lim", " the limit of "),
    (r"\\therefore", " therefore "),
    (r"\\%|%", " percent "),
    (r"\\degree|°", " degrees "),
    (r"\\left|\\right|\\!|\\,|\\;|\\quad|\\qquad", " "),
]

_FUNCTIONS = {
    "sin": "sine of", "cos": "cosine of", "tan": "tangent of",
    "sec": "secant of", "csc": "cosecant of", "cot": "cotangent of",
    "sinh": "hyperbolic sine of", "cosh": "hyperbolic cosine of", "tanh": "hyperbolic tangent of",
    "log": "log of", "ln": "the natural log of", "exp": "e to the power of",
    "arcsin": "inverse sine of", "arccos": "inverse cosine of", "arctan": "inverse tangent of",
}

#: Spoken, never spelled. "cm" read as letters is the single most common complaint about
#: maths TTS, and WAEC answers are full of units.
_UNITS = {
    "cm": "centimetres", "mm": "millimetres", "km": "kilometres", "m": "metres",
    "kg": "kilograms", "mg": "milligrams", "g": "grams",
    "ms": "milliseconds", "s": "seconds", "min": "minutes", "hr": "hours", "h": "hours",
    "N": "newtons", "J": "joules", "W": "watts", "V": "volts", "A": "amperes", "K": "kelvin",
    "mol": "moles", "L": "litres", "ml": "millilitres",
}

_OPERATORS = [
    (r"\+", " plus "),
    (r"(?<=[\w\)\]}])\s*-\s*(?=[\w\(\[{\\])", " minus "),  # binary minus only
    (r"(?<![\w\)\]])-(?=\d|[a-zA-Z(])", " negative "),  # unary minus
    (r"\*", " times "),
    (r"/", " over "),
    (r"=", " equals "),
    (r"<", " is less than "),
    (r">", " is greater than "),
]

_MATH_SEGMENT = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]", re.DOTALL)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\\$])")


# --- the pipeline ---------------------------------------------------------------------------


def _expand_fractions(text: str) -> str:
    # One level of nesting inside each brace group: the quadratic formula puts a \sqrt{}
    # inside the numerator, and a flat `[^{}]*` leaves the whole formula unspoken as "frac".
    _group = r"((?:[^{}]|\{[^{}]*\})*)"
    pattern = re.compile(r"\\[dt]?frac\s*\{" + _group + r"\}\s*\{" + _group + r"\}")
    for _ in range(8):
        def repl(match: re.Match) -> str:
            num, den = match.group(1).strip(), match.group(2).strip()
            named = _NAMED_FRACTIONS.get((num, den))
            return f" {named} " if named else f" {num} over {den} "

        new = pattern.sub(repl, text)
        if new == text:
            return text
        text = new
    return text


def _expand_roots(text: str) -> str:
    # "2\sqrt{2}" is "two TIMES the square root of two". The coefficient is detected on the
    # raw LaTeX — juxtaposition with no space is what makes it a coefficient. Doing it after
    # expansion instead would also fire on "\pm \sqrt{...}", producing "plus or minus times".
    text = re.sub(r"(?<=[\w\)])(?=\\sqrt|√)", " times ", text)
    text = re.sub(r"\\sqrt\s*\[\s*3\s*\]\s*\{([^{}]*)\}", r" the cube root of \1 ", text)
    text = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r" the square root of \1 ", text)
    return re.sub(r"√\s*\(?([\w.]+)\)?", r" the square root of \1 ", text)


def _expand_powers(text: str) -> str:
    def named(exponent: str) -> str:
        exponent = exponent.strip()
        if exponent == "2":
            return " squared "
        if exponent == "3":
            return " cubed "
        if exponent.startswith("-"):
            return f" to the power of minus {exponent[1:]} "
        return f" to the power of {exponent} "

    text = re.sub(r"\^\s*\{([^{}]*)\}", lambda m: named(m.group(1)), text)
    text = re.sub(r"\^\s*(-?[\w.]+)", lambda m: named(m.group(1)), text)
    text = text.replace("²", " squared ").replace("³", " cubed ")
    return text


def _expand_functions(text: str) -> str:
    for name in sorted(_FUNCTIONS, key=len, reverse=True):
        spoken = _FUNCTIONS[name]
        text = re.sub(rf"\\?\b{name}\s*\(([^()]*)\)", rf" {spoken} \1 ", text)
        text = re.sub(rf"\\?\b{name}\b(?!\s*\()", f" {spoken.removesuffix(' of')} ", text)
    # log base handling reads better than "log underscore two"
    text = re.sub(r"log of\s*_\s*\{?([\w.]+)\}?\s*", r"log base \1 of ", text)
    text = re.sub(r"log\s*_\s*\{?([\w.]+)\}?\s*", r"log base \1 of ", text)
    return text


def _expand_units(text: str) -> str:
    def repl(match: re.Match) -> str:
        value, unit = match.group(1), match.group(2)
        spoken = _UNITS.get(unit) or _UNITS.get(unit.lower())
        return f"{value} {spoken}" if spoken else match.group(0)

    pattern = r"(\d+(?:\.\d+)?)\s*(" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")\b"
    return re.sub(pattern, repl, text)


def _expand_numbers(text: str) -> str:
    return re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", lambda m: number_to_words(m.group(1)), text)


def verbalize(expression: str) -> str:
    """Turn one mathematical expression into words. Prose is left alone."""
    out = expression
    out = _expand_fractions(out)
    out = _expand_roots(out)
    out = _expand_powers(out)
    out = _expand_functions(out)
    for pattern, replacement in _LATEX_WORDS:
        out = re.sub(pattern, replacement, out)
    for symbol, word in _GREEK.items():
        out = out.replace(symbol, f" {word} ")
    for pattern, replacement in _OPERATORS:
        out = re.sub(pattern, replacement, out)
    out = _expand_units(out)
    # Implicit multiplication is written without a space and has to be spoken with one:
    # "3x" is "three x", not "three-ex". Runs after units so "12cm" is already "12 cm".
    out = re.sub(r"(?<=\d)(?=[a-zA-Zπθ])", " ", out)
    out = _expand_numbers(out)
    out = re.sub(r"[{}\\]", " ", out)
    # Function application: "f(x)" is "f of x". Only single letters, so "sin(x)" (already
    # handled) and "2(x+1)" (a product) are untouched.
    out = re.sub(r"\b([a-zA-Z])\s*\(([^()]*)\)", r"\1 of \2", out)
    out = out.replace(")(", " times ")  # (x+2)(x-3)
    out = out.replace("(", " ").replace(")", " ")
    out = re.sub(r"\s+", " ", out).strip()
    return re.sub(r"\s+([,.;:?!])", r"\1", out)


def speak(text: str) -> str:
    """Normalise a whole reply: verbalize the math segments, keep the prose.

    Delimited math (`$…$`, `\\(…\\)`) is verbalized in place. Text with no delimiters at all
    is verbalized wholesale — models frequently emit bare LaTeX, and a voice reading
    "backslash frac" is a worse failure than over-verbalising an English sentence.
    """
    if not text or not text.strip():
        return ""
    if _MATH_SEGMENT.search(text):
        spoken = re.sub(
            _MATH_SEGMENT,
            lambda m: " " + verbalize(next(g for g in m.groups() if g is not None)) + " ",
            text,
        )
        spoken = re.sub(r"\s+", " ", spoken).strip()
        return re.sub(r"\s+([,.;:?!])", r"\1", spoken)
    return verbalize(text)


# --- sentence pipeline for streaming TTS (§6.6) ------------------------------------------


@dataclass(frozen=True)
class SpokenSentence:
    text: str
    language: str

    def __str__(self) -> str:
        return self.text


def split_sentences(text: str) -> list[str]:
    """Sentence boundaries for pipelined synthesis.

    The gateway synthesises sentence by sentence so the first audio starts ~1 s after the
    first sentence completes instead of after the whole answer — on a CPU box that is the
    difference between a conversation and a wait.
    """
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text.strip()) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def to_speech(text: str, *, language: str = "en") -> list[SpokenSentence]:
    """Full §7.7 pipeline: normalise math, split, tag language for voice routing."""
    return [SpokenSentence(speak(part), language) for part in split_sentences(text) if speak(part)]
