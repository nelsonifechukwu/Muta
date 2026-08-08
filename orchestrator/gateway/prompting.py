"""Assemble the per-student system prompt on top of a mode's stable prefix.

The mode prompt (socratic.md / subgoal.md) is the SHARED prefix every session reuses — it
ends with a `--- per-student context (variable — keep last) ---` separator. Everything this
module appends is per-student or per-turn (persona, language, the learning-twin summary, web
grounding, retrieved chunks) and therefore lands *after* that separator, so the cache-reusable
prefix stays intact (ROADMAP 17 Jul / prompt_layout.py §7.3).

Kept as pure string functions (no I/O, no deps) so they're trivially testable and cheap.
"""

from __future__ import annotations

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
    "en": "English", "fr": "French", "ar": "Arabic", "sw": "Swahili", "ha": "Hausa",
    "yo": "Yoruba", "ig": "Igbo", "am": "Amharic", "zu": "Zulu",
}


def persona_language_directive(persona: str, language: str, subject: str | None = None) -> str:
    """A compact per-student voice/language line. English gets no language clause (the model's
    default) so an English session's prefix stays as short as possible."""
    parts = [_PERSONA.get(persona, _PERSONA["teacher"])]
    lang = (language or "en").strip()
    if lang and lang != "en":
        name = _LANGUAGE.get(lang, lang)
        parts.append(
            f"Respond in {name}. Use culturally familiar examples where natural, and always "
            "write mathematics in LaTeX regardless of the language."
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

    Only non-empty layers are appended, so an English teacher-persona turn with no twin, web,
    or RAG context is byte-identical to the bare mode prompt (maximising cache reuse)."""
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
