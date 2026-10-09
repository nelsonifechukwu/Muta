# Learner resources (RAG): PDFs, Markdown and text

How Muta grounds an answer in a file the learner uploaded, and why each piece is shaped the way
it is. Code: `orchestrator/retrieval/documents.py` (parsing and chunking),
`orchestrator/retrieval/resources.py` (preparation, search, evidence),
`orchestrator/retrieval/embed_server.py` (bge sidecar), `orchestrator/gateway/routes.py`
(`_resource_candidates`, `_grounded_system_prompt`, `_persist_resource_reply`).

## Lifecycle

1. **Upload** (`POST /v1/resources`). The stored type comes from the bytes and the name
   (`classify_upload`), never from the declared type alone: `%PDF-` is a PDF; otherwise only an
   explicit `.md`/`.markdown`/`.txt` name (or a `text/markdown`/`text/plain` type) is accepted
   as text and must decode as strict UTF-8 without NUL bytes. Text files are capped at 4 MB
   (they are re-parsed whole for the reader); PDFs at 32 MB.
2. **Preparation** happens in the background right after upload (status `processing` →
   `ready`, usually under 2 s): extract → clean → chunk → embed → store. The learner can keep
   chatting; a file can be selected with `@` once it is ready.
3. **Retrieval** runs per turn over only the selected files, owner-scoped in the store query.
4. **Evidence** is sized to the lane, rendered as numbered `[R#]` blocks, and the answer's
   markers are canonicalized and persisted with the exact assistant row.

## Locators: pages and sections

Every chunk carries a locator a learner can follow. A PDF chunk has its **physical page**.
A Markdown/text chunk has a **section ordinal** (stored in the same `page` field, so
de-duplication, citations and storage keep one shape) plus a `section` heading path such as
`Unit 1: Forces › Newton's laws`. `section` is `null` for PDFs, a path for a headed section,
and `""` for an untitled passage. Citations render as "PDF · page 12", "§ Unit 1 › Forces" or
"passage 3"; text sources open the in-app reader (`GET /v1/resources/{id}/sections`, split
exactly as indexed) scrolled to the cited section.

## Chunking

- **PDF**: pages are cleaned, then windowed at **900 characters with 150 overlap**, never
  crossing a page. 900 characters is ~200–250 tokens: one idea per evidence block, and six or
  seven blocks fit a 4,096-token lane beside the tutor prompt. (The previous 1,500/220 windows
  fit only four.)
- **Markdown**: ATX (`#`) and one-line setext headings open sections whose path is the heading
  stack; fenced code is opaque (a `# comment` is not a heading); YAML front matter is dropped.
  Each section is packed into ≤900-character chunks at paragraph boundaries, and each chunk's
  retrieval text starts with `§ <heading path>` so both scorers see where a paragraph lives.
  The prefix is stripped from learner-facing excerpts.
- **Plain text** (and Markdown before the first heading) becomes numbered passages of about
  900 characters, split at paragraph boundaries.

`CHUNKER_VERSION` (`chunks-v2`) is part of every resource's stored index identity
(`<embedder>+<chunker>`). Changing chunk boundaries bumps it, and the next start re-indexes
old resources in the background **while they stay usable** (lexical scoring covers the gap).

## PDF cleaning

- **Running headers/footers.** A line within the top/bottom two lines of at least 40% of text
  pages (minimum three pages; digits ignored, so "Page 3" and "Page 4" match) is removed, plus
  one more line for the page number that commonly sits just inside a running header. On the
  68-page reference PDF this removed "Prompt Engineering" / "February 2025" / the page number
  from every page. Without it, every chunk shared the title words and matched any query that
  mentioned them.
- **Contents pages** (mostly `Title ...... 12` lines, or a "Contents" heading with entries) are
  detected at search time and their score multiplied by 0.6: a contents page names every topic,
  so it matches almost every query. It is still *preferred* for overview questions.

## Embeddings and scoring

- **bge-small-en-v1.5 (q8_0)** ships in the model pack (`models/embed/`). The gateway runs it
  as a managed sidecar `llama-server --embeddings --pooling cls -c 1024 -np 2 -b 512 -ub 512`
  on a free loopback port, spawned on first use and reaped after 300 s idle on the vision
  reaper's tick (`EmbeddingManager`). CLS pooling is mandatory for BGE; 1024/2 gives each slot
  bge's full 512-token window. Measured: 132 MiB RSS, 0.3 s start from the page cache (6.9 s
  from a cold disk). Inputs are capped at 1,200 characters; a passage the server still
  rejects (dense LaTeX, non-Latin scripts) is retried alone at 600/300/160 characters instead
  of demoting the whole file. A failed start is not retried for 300 s, so questions fall back
  to lexical scoring at once instead of each waiting out a start attempt.
- **Score** = cosine + 0.35 × lexical overlap; contents pages × 0.6. Semantic hits more than
  **0.20** below the best one are dropped (measured: a correct page trailed the best hit by at
  most 0.161; off-topic questions top out at 0.47–0.57 versus ≥0.68 for answerable ones).
  There is **no absolute floor**: bge-small is English-only and would under-score a learner's
  French or Swahili notes. The prompt rules make the model say when the evidence does not
  answer the question.
- **Degradation, not errors.** If bge cannot start, preparation falls back to the hashing
  index (identity `hashing:384+chunks-v2`) and queries score lexically; nothing fails. A
  resource indexed by another embedder is searched lexically and re-indexed in the background
  at the next start, on its own single worker so it never queues ahead of a new upload. A
  re-index never trades a bge index for hashing (no bge model installed, or bge failing
  mid-re-index: the old index is kept). Preflight no longer rejects identity mismatches.
- **Mixed indexes and several files.** bge and lexical scores live on different scales, so
  the 0.20 window applies only among bge-scored passages, and every selected file contributes
  its best passage first. (Review finding: a hashing-indexed file's exact match was hidden.)
- **Diversity.** One hit per PDF page (overlapping windows are near-duplicates); text chunks
  are not windowed, so each is its own candidate.

### Measured (2026-10-09, native, Apple M4 Pro)

18 labelled questions over the 68-page "Prompt Engineering" whitepaper (expected pages read
off the document), bundled binary, `k = 6`:

| index | chunks | top-1 | top-3 | top-6 | prepare | query |
|---|---|---|---|---|---|---|
| hashing, 1,500/220, no cleaning (before) | 87 | 9/18 | 15/18 | 17/18 | 0.5 s | 6 ms |
| bge-small, 900/150 + cleaning (after) | 130 | 12/18 | 17/18 | 18/18 | 1.0 s | 21 ms |

(bge with the old windows scored 13/17/18 at top-1/3/6; the smaller windows are kept because
more of them fit the evidence room, and top-6 is what reaches the prompt.)

## Overview questions

"Summarise this", "what is this document about", "main points", "outline" and similar
(`wants_overview`) bypass similarity search, which answers them badly: the question shares no
terms with the content. Each selected file contributes, in priority order, its introduction
(the first chunk in the first third that opens with or contains an Introduction/Overview/
Abstract heading), its conclusion (a Summary/Conclusion heading in the last 40%, plus the chunk
after it), up to two contents chunks, then section openings spread evenly (bisection order, so
any budget-trimmed prefix still spans the document). Title pages, endnotes, references and
acknowledgements are skipped. Evidence fitting keeps the highest priorities and then presents
the survivors in reading order. On the reference PDF this selects Introduction (p. 6), Summary
(pp. 66–67), Contents (pp. 3–4) and pages 7, 26, 46 — before, it chose the title page,
acknowledgements and endnotes.

## The evidence budget (why answers used to stop at 64 tokens)

The desktop app ran two 2,048-token lanes. The tutor prompt alone is ~900 tokens (measured
with the bundled tokenizer, 4.8 bytes/token), five 1,500-character passages were ~2,000 more,
and the fitter's only answer reserve was 64 tokens. Every grounded answer was therefore capped
at 64 tokens, and the automatic continuation discarded its buffered text on each cap, so the
retries re-sent byte-identical prompts until they gave up (message 684 in the reported
conversation).

Now:

- Every chat turn carries a private `_muta_min_reply_tokens = 512` hint. `_fit_request` keeps
  that room free on every (re)fit, bounded to half the lane and to the turn's own `max_tokens`.
  Clients strip all `_muta_*` keys before a request leaves the process.
- `_grounded_system_prompt` measures the real envelope (system prompt with the evidence rules,
  the learner turn with its trusted instruction, image tokens, any resumed answer, plus a
  64-token margin) with the engine's own tokenizer, converts the room to characters at 3.6
  chars/token, renders, **re-measures**, and shrinks by the ratio it actually observed until
  the prompt fits (dense LaTeX/CJK, or the fitter's byte fallback, would otherwise overflow
  and be clipped mid-passage). `fit_evidence` keeps whole passages in rank order and trims
  the last at a sentence boundary. Citations are exactly the passages shown to the model.
- In a lane too small for even one passage, a grounded turn may give up answer room down to
  256 tokens. If one still does not fit, the model is told that relevant passages exist but
  do not fit this device's chat memory — never "no relevant passage".
- Ordinary (ungrounded) turns reserve an eighth of the lane: 256 tokens on a 2,048-token
  classroom lane, 512 from 4,096 up, so small lanes keep their history.
- The desktop launcher now runs **two 4,096-token lanes** (`MUTA_RT_N_CTX=8192`), leaving
  ~2,000 tokens for six or seven passages. Measured cost on the bundled 1.5B model with both
  lanes full: +107 MiB peak engine RSS (RESULTS.md 2026-10-09).
- Retrieval needs lanes of at least 4,096 tokens to be useful. Classroom profiles with
  2,048-token lanes still work, with about one trimmed passage per answer.

## Inline citations

The prompt asks for an inline `[R#]` after every supported sentence, and the UI renders each as
a small numbered marker with a Sources list (or margin rail) underneath. The bundled 1.5B model
usually answers correctly from the evidence but writes no marker, so after generation
`orchestrator/gateway/citation_attribution.py` numbers the claims itself:

- Each sentence or list item without a marker (headings, questions, code, maths and links are
  skipped or protected) is compared with every passage **shown** to the model, numbered as the
  model saw them.
- With bge: a passage supports a claim when cosine ≥ 0.70 **and** at least 30% of the claim's
  content words occur in it; the best-scoring passage wins. Without bge: ≥ 60% content-word
  coverage. Otherwise the claim stays unmarked — an invented citation is worse than none.
- Calibrated on the learner's real answers over the 68-page PDF: the step-back answer cited
  p. 25 for both claims; the two summaries got 2 and 10 citations; four off-topic answers
  (photosynthesis, catalysts) scored against the same passages got **0** citations.
- The model's own markers are kept; attribution only fills gaps. The finalized text reaches the
  browser through the existing `replace` event, so numbers appear when the answer completes.

## Sources consulted

Even after attribution, some grounded replies end with no marker (no sentence was clearly
supported by one passage — e.g. a very loose paraphrase). Such a reply used to carry no sources
at all, so the learner could not see which pages it came from. Now, when a grounded reply's final
text has **no** marker,
the three strongest passages the model was shown are kept with it and the UI lists them under
"Sources consulted", without numbers: nothing in the reply says which sentence came from which
passage, so none are invented. A reply with any marker keeps exactly the passages it cites.

## Interrupted answers

- **Recovery keeps progress.** After a length or transient stop, the continuation streams
  through a short echo gate (it holds back the first ~240 characters until a line ends, at most
  640, so an echo of the private continuation directive can be stripped) and then streams
  normally. Text produced before a stop reaches the writer and the store immediately, so the
  next continuation starts after it. A capped retry that produced nothing new gets one sampled
  second chance; a second identical stall ends the turn with the partial answer saved.
- **Sources survive failure.** When a grounded answer stops early, its cited passages are
  canonicalized and attached to the saved partial row (and sent in the terminal error event),
  so the partial stays auditable after a refresh.
- **Continue reply extends the same answer.** `ChatRequest.continue_reply` resumes the
  conversation's final failed/stopped/streaming assistant row in place: no learner message is
  added, the stored question drives retrieval, web grounding, visuals and the integrity guard,
  and the model gets the partial as a trusted assistant prefill (with the conversation's
  earlier turns; the partial does not consume the replay budget). The stream opens with a
  `replace` event carrying the stored answer, so live viewers and replays after a refresh show
  one bubble. Continuation is refused (409) under a buffered integrity guard (such turns never
  persist a partial) and for structured output.
- **Numbering survives continuation.** The partial's citations are pinned first and keep their
  stored identity (resource, page, chunk) even when the prompt has no room to show them, so
  `[R1]..[Rk]` stay valid. A pin's prompt text is the current chunk containing that passage
  (a re-index renumbers chunks) or the stored excerpt. If a cited file was deleted, the
  stored markers can no longer be mapped, so they are removed rather than re-pointed. Every
  save rewrites the row's citations in final marker order (`replace_message_sources`), because
  reload resolves `[R#]` against stored order.
- **Reading order is citation order.** Overview passages are chosen by priority but displayed
  in document order. The persisted citation list follows that displayed order, not the ranking
  order, so an `[R2]` in the prompt, answer and reloaded Sources list always means one passage.
- **Deleting a cited file fails closed.** Both database backends atomically remove inline
  `[R#]` markers and clear the full source list of each affected answer before deleting the
  file. A middle citation disappearing must never compact the list and re-point an old marker
  at a different document. The answer prose remains for the learner, without a misleading
  citation; a later continuation can ground new text against the remaining files.
- **The engine echoes the prefill.** The pinned llama-server returns an assistant prefill
  verbatim before continuing it (a 1.9 kB partial came back whole). `_ResumeDeduplicator`
  strips that echo as well as a short restated boundary; without it every recovered answer
  contained its first half twice and tripped the loop guard. A continuation that only echoes
  or repeats counts as no progress (retried, then left failed with Continue still offered).

## Rejected alternatives

- **A larger single lane only for RAG turns.** With `--kv-unified`, an idle second lane's share
  can be borrowed, but a second job can start mid-answer and overcommit the shared KV. The
  per-lane guarantee stays; the lanes got bigger instead.
- **A slimmer tutor prompt for RAG turns.** It would buy ~600 tokens but drop the mode-aware
  pedagogy that document questions need as much as any other.
- **Rendering Markdown from `/content`.** That route serves `text/plain` + `nosniff` so a
  browser can never execute a file. The reader renders sections through the same sanitizing
  Markdown pipeline as replies.
- **Absolute similarity floor.** See *Embeddings and scoring*.
