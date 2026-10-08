# Muta v4 adaptive tutoring harness

Date: 2026-10-06

Status: implementation plan and integration contract

## Outcome

Muta v4 must make the tutor visibly adaptive without allowing learner text or model output
to override correctness. The product remains offline-first and CPU-bound. Deterministic code
owns policy, verification, persistence, and safe fallbacks; the language model owns the
natural-language explanation inside those boundaries.

This change does not alter the GGUF, chat template, release version, or competition submission
repository. The first delivery is a locally tested macOS package for review.

## Architectural rules

1. **The server is authoritative.** A locked course resolves tutoring style and answer
   withholding on the server. Browser-supplied `mode` is only a preference when no lock applies.
2. **Learner text is data.** Override attempts are detected without rewriting the message. A
   trusted turn directive tells the model to retain the resolved policy.
3. **Check before agreement.** Student equations are parsed and compared as solution sets in the
   existing sandboxed SymPy worker. The first non-equivalent step becomes structured metadata and
   trusted prompt context.
4. **Unsafe output never streams.** Turns that require answer withholding or that contain checked
   student work are buffered until post-generation guarantees pass. At most one repair generation
   is attempted; a deterministic safe response is the terminal fallback.
5. **Adaptation is explicit and inspectable.** The learning twin stores preferences, error tags,
   and strategy history. Stuck detection selects a representation not already used and emits a
   small UI status chip.
6. **Offline collaboration stays host-local.** Courses and the class board reuse Muta Share's
   SQLite state, principals, session cookies, operator boundary, and CSRF enforcement.
7. **The stable prompt prefix stays stable.** Mode invariants live in the mode files. Student,
   course, locale, checker, and strategy data stay in the variable suffix so KV reuse is retained.
8. **Every new API is additive.** `contracts/models.py` remains the source of truth and
   `contracts/openapi.yaml` is regenerated rather than edited.

## Request pipeline

For every chat turn:

1. authenticate and resolve learner identity;
2. resolve course, effective style, withholding, and teacher note;
3. load the learner twin and capture an explicit preference;
4. detect an instruction-override attempt and record it;
5. extract and verify student work, recording the first error class;
6. detect stuck state and choose a new representation when needed;
7. assemble trusted per-turn context after the shared prompt prefix;
8. generate, buffering any integrity-sensitive turn;
9. reject affirmation of checked-wrong work, disclosed withheld answers, leaked internal
   continuation instructions, or degenerate repetition;
10. retry once with a repair directive, then use a deterministic safe fallback if necessary;
11. persist reply plus structured tutoring metadata and expose it as accessible UI chips.

The model never decides whether its own output passed these gates.

## Persistent data

### Learning twin v2

Backward-compatible additive fields:

- `preferences`: resolved learning style and optional country;
- `strategy_history`: per-conversation representations already used;
- `recent_claims`: bounded normalized claims/error classes for stuck detection;
- existing `mastery`, `error_counts`, `pace`, and `summaries` remain readable.

Unknown or missing fields continue to degrade to defaults. Writes remain atomic.

### Share state

Add tables managed by the existing Share SQLite migration path:

- courses, with name, style, locked flag, withholding flag, and a 400-character teacher note;
- board posts and replies, host scope implicit in the local database;
- teacher verification and deletion metadata.

Host writes require the existing operator check and CSRF token. Members can read/post only while
their Share session is valid. The course lock is re-read during chat handling rather than copied
from the browser.

### Interactive STEM units

The versioned offline JSON format now powers a compact four-subject shelf: mathematics, physics,
chemistry, and biology. Every authored unit uses the existing Markdown/KaTeX renderer and bounded
visualization specifications, has a verifier-backed five-question checkpoint, records mastery by
topic, and cites open educational sources. Imported third-party JSON stays preview-only unless the
backend owns its answer authority. No copyrighted textbook content is bundled.

## UI behavior

- Four concise styles: Guide me, Show me how, Everyday examples, Hints only.
- A compact book symbol replaces the oversized sidebar wordmark; the full identity remains on
  startup and brand surfaces.
- Each style names its teaching method and explains the learner experience in plain language.
- The picker is keyboard accessible, touch targets are at least 44 × 44 px, selection is not
  conveyed by colour alone, and chips wrap without horizontal overflow at 375 px.
- A locked course shows “Set by your teacher” and cannot be overridden locally.
- Checker, strategy-switch, verification fallback, course, and unit-progress states use the
  existing Muta palette and typography; no new global colour system is introduced.
- Light, dark, reduced-motion, mobile portrait/landscape, and Muta Share surfaces must match.

## Work partition

- **Integrity/adaptation:** policy detectors, checker, output gates, twin v2, context mapping,
  continuation scrubber, repetition guard, focused tests.
- **Courses/class board:** Share persistence, host/member APIs, authorization, course enforcement,
  board UI and trust-boundary tests.
- **Learning UI/unit/report:** shared contract, style picker, chips, unit, Muta IQ consistency,
  responsive/accessibility tests.
- **Integration (this branch):** conflict resolution, demo seed/runbook, judge regression suite,
  full test matrix, real-model scenarios, desktop staging, signed macOS package verification.

## Acceptance gates

1. Judge prompts never affirm checked-wrong work; the distribution error is named.
2. Hints-only output never contains the protected final answer.
3. “Still confused” changes representation and never exposes internal runtime text.
4. Kiswahili output is coherent or falls back honestly without looping.
5. A locked course ignores a forged client mode.
6. Board data cannot cross an unauthenticated or revoked Share boundary.
7. Existing chat, Stop/recovery, photo, voice, PDF citation, Eco, visualization, language, and
   Share flows remain green.
8. Contract, Python, Node/UI, lint, desktop, and package-inspection suites pass.
9. D1–D8 are exercised three times against the final model where hardware/runtime permits, with
   failures and latency documented rather than hidden.
10. Both macOS architectures are rebuilt from one immutable source tree and staged for user
    review only. No push, release replacement, Drive update, or other-OS build occurs yet.
11. Review packages contain exactly one tutor GGUF: Muta Tutor Qwen2.5 1.5B. Speech and retrieval
    resources remain because they are feature dependencies; optional tutor models are user-added.

## Performance constraints

- Detectors and parsers are bounded and deterministic; no new resident model is introduced.
- SymPy work uses the existing sandbox/time limits.
- Integrity buffering applies only to sensitive turns; ordinary streaming stays unchanged.
- Twin and Share records are bounded so prompt size and disk growth do not become unbounded.
- Any measured latency/RSS change is recorded in `RESULTS.md` with hardware context.
