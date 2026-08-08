# P4 — Web-augmented tutoring (opt-in): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the student opts in, the box is online, and `MUTA_SEARCH_URL` is configured, the gateway grounds the answer with top-k web snippets and returns the sources; otherwise the request is byte-identical to today.

**Architecture:** No agentic tool-calling on a 4B model — RAG-style: a `websearch.fetch_snippets()` helper (SearXNG-compatible JSON API, ~2 s budget, every failure → `[]`), injected as a system-prompt suffix in the `/v1/chat/stream` handler; `ChatRequest` gains additive `use_web: bool = False`; the SSE `done` event carries `sources`; the UI gets a composer toggle and renders the source list.

## Global Constraints

- Grounding is additive and fail-silent: offline, unconfigured, toggle off, or a slow/failed search → the exact request the tutor already serves. Never delay the first token by more than the ~2 s search budget.
- `/v1` additive-only; regenerate `contracts/openapi.yaml`; commit it.
- Sources shown to the student whenever grounding influenced the answer.

---

### Task 1: `websearch.fetch_snippets`

**Files:** Create `orchestrator/gateway/websearch.py`; test `orchestrator/tests/test_websearch.py`.

**Interfaces:** `Source` dataclass `(title: str, url: str, snippet: str)`; `fetch_snippets(query: str, *, base_url: str, k: int = 3, timeout: float = 2.0) -> list[Source]` — GET `{base_url}/search?q=…&format=json`, map `results[:k]` (`title`, `url`, `content`); ANY exception or non-JSON → `[]`.

- [x] RED: tests — happy path maps k results; transport error → []; malformed JSON → []; k truncates.
- [x] GREEN: implement; ruff.
- [x] Commit `gateway: websearch snippets — SearXNG-shaped, fail-silent`.

### Task 2: grounding in `/v1/chat/stream` + contract

**Files:** Modify `contracts/models.py` (`ChatRequest.use_web: bool = False`), `orchestrator/gateway/routes.py` (chat_stream handler: build the suffix, pass sources into the done event), regenerate `contracts/openapi.yaml`; test in `orchestrator/tests/test_web_grounding.py`.

**Interfaces:** grounding block appended to the system prompt:
`"\n\nWeb context (retrieved just now — cite [n] when you use it):\n[1] {title} — {snippet}\n…"`; done event gains `"sources": [{"title","url"}, …]` (empty list when ungrounded).

- [x] RED: wired-fixture tests — `use_web=true` + env + online-true → fake engine's captured `system_prompt` contains `[1]` and the snippet, done contains sources; toggle off / env unset / offline → prompt untouched, `"sources": []`.
- [x] GREEN: implement (env `MUTA_SEARCH_URL`; `get_connectivity().online() is True` gate; `fetch_snippets` in a threadpool). `make contract`.
- [x] Commit `gateway: opt-in web grounding on chat/stream — sources ride the done event`.

### Task 3: UI toggle + sources

**Files:** `ui/index.html` (a 🌐 toggle button in the composer, `aria-pressed`), `ui/app.js` (send `use_web` when active + render sources under the finalized reply), `ui/styles.css`.

- [x] Implement; `node --check`; UI asset tests green.
- [x] Commit `ui: web-grounding toggle and source list`.

### Task 4: close P4

- [x] Full suite + ruff; RESULTS.md entry (grounded vs ungrounded prompt evidence from tests; note no live SearXNG endpoint was available if that is the case); check off plan; commit `results: web grounding landed; P4 closed`.
