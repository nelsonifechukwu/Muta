"""Assemble the per-student system prompt on top of a mode's stable prefix.

The mode prompt (socratic.md / subgoal.md) is the SHARED prefix every session reuses — it
ends with a `--- per-student context (variable — keep last) ---` separator. Everything this
module appends is per-student or per-turn (persona, language, the learning-twin summary, web
grounding, retrieved chunks) and therefore lands *after* that separator, so the cache-reusable
prefix stays intact (ROADMAP 17 Jul / prompt_layout.py §7.3).

Kept as pure string functions (no I/O, no deps) so they're trivially testable and cheap.
"""

from __future__ import annotations

import re

#: persona → a one-line voice directive. The contract's persona vocabulary is about tone;
#: this table turns it into an instruction the model actually receives (it was a dead param).
_PERSONA = {
    "teacher": "Take a warm, patient teacher's voice; encourage effort and never talk down.",
    "friend": "Speak like a friendly classmate studying alongside them — casual and supportive.",
    "professor": "Take a precise, rigorous voice; define terms carefully and be exact.",
    "exam": "Exam-prep mode: be concise, give minimal hints, and push the student to produce "
    "the answer themselves.",
}

#: language tag → human name. Covers the README's target set; unknown tags pass through as-is
#: so an unlisted BCP-47 code still instructs the model to use that language.
_LANGUAGE = {
    "am": "Amharic",
    "ar": "Arabic",
    "de": "German",
    "en": "English",
    "fr": "French",
    "ha": "Hausa",
    "ig": "Igbo",
    "sw": "Swahili",
    "yo": "Yoruba",
    "zu": "Zulu",
}
_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}$")


def persona_language_directive(persona: str, language: str, subject: str | None = None) -> str:
    """A compact per-student voice/language instruction for the trusted system context."""
    parts: list[str] = []
    candidate = (language or "en").strip()
    lang = candidate if candidate.lower() == "auto" or _LANGUAGE_TAG.fullmatch(candidate) else "en"
    if lang.lower() == "auto":
        parts.append(
            "The user's response language preference is AUTO. Respond in the primary natural "
            "language used by the user in their latest message, even when older conversation "
            "history uses another language. If the latest message is too short or ambiguous to "
            "identify a language, continue the most recently established response language; if "
            "none exists, use English. An explicit language request for this specific task "
            "takes precedence."
        )
    else:
        base_lang = lang.split("-", 1)[0].lower()
        name = _LANGUAGE.get(base_lang, lang)
        label = name if name.lower() == lang.lower() else f"{name} ({lang})"
        parts.append(
            f"The user's preferred response language is {label}. Write the entire natural-"
            "language response in that language, even when the latest message or earlier "
            "conversation is in another language. Use another language only when the user "
            "explicitly requests it for this specific task."
        )
    # Language is the highest-priority live preference and stays first in the variable block.
    # This also keeps it inside the protected portion when context fitting must trim the prompt.
    parts.append(_PERSONA.get(persona, _PERSONA["teacher"]))
    parts.append(
        "When identifying or writing the response language, treat source code, variable names, "
        "commands, URLs, and proper nouns as literal content rather than language evidence, and "
        "do not translate them. Translate explanations naturally rather than literally. Use "
        "culturally familiar examples where natural, and always write mathematics in LaTeX "
        "regardless of the language."
    )
    if subject and subject != "math":
        parts.append(f"The student is working on {subject}.")
    return " ".join(parts)


def assemble_system_prompt(
    base_prompt: str,
    *,
    persona: str = "teacher",
    language: str = "en",
    subject: str | None = None,
    twin_summary: str = "",
    web_lines: str = "",
    rag_block: str = "",
) -> str:
    """Compose the full system prompt: the mode's stable prefix, then the per-student block.

    Only non-empty contextual layers are appended. The shared mode prompt remains byte-identical
    at the front, while persona and language stay in the variable suffix."""
    blocks = [base_prompt.rstrip()]
    directive = persona_language_directive(persona, language, subject)
    if directive:
        blocks.append(directive)
    if twin_summary.strip():
        blocks.append("Student context (from their learning record): " + twin_summary.strip())
    if rag_block.strip():
        blocks.append(rag_block.strip())
    if web_lines.strip():
        blocks.append(
            "Web context (retrieved just now — cite [n] when you use it):\n" + web_lines.strip()
        )
    return "\n\n".join(blocks)
