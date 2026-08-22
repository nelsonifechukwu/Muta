# Chat resource RAG vertical slice

**Status:** implemented and locally verified; approved for GitHub/GCP integration on
22 August 2026.

## Outcome

A learner can upload a PDF in Settings, watch it move through an asynchronous preparation
state, enable RAG in chat, mention one or more owned resources with `@`, and receive a
resource-grounded answer with durable citations that reopen the source at the exact physical
PDF page. Preparing or failed resources never block use of other ready resources.

This slice deliberately builds resource RAG separately from the existing staged syllabus
index. The chat toggle is authoritative: when it is off, user-resource retrieval does no work.

## Locked product behaviour

1. Settings → Files accepts PDFs and shows `Preparing`, `Ready`, or `Failed` per resource.
   Failed files can be retried and any file can be deleted.
2. Upload returns immediately after durable storage. A bounded in-process worker extracts each
   physical page, creates page-bounded overlapping chunks, embeds them, and atomically marks
   the resource ready only after all chunks are committed.
3. The `@` menu is available only while RAG is enabled. It shows all owned PDFs with status;
   ready files are selectable, while preparing/failed rows explain why they cannot be used.
4. A selected mention is represented by an opaque resource ID in request state. Display names
   are never used for authorization or retrieval scoping.
5. RAG on with explicit mentions searches exactly those resources. RAG on without a mention
   asks the learner to select a file rather than silently searching unrelated private files.
6. The backend revalidates ownership and readiness before reserving an inference slot or
   writing the user turn. A preparing resource produces a friendly resource-specific response;
   ready resources remain independently usable.
7. Retrieval context is strict evidence: chunks are numbered by the server and the model is
   told to say when the selected source does not contain the answer. Citation links are built
   from server-owned records, never from model-provided URLs.
8. Citations are persisted against the exact assistant message and survive history reload.
   Each citation includes resource ID, title, physical PDF page, chunk index, and a short
   excerpt. Clicking opens an authenticated inline PDF at `#page=N` in a new tab.
9. Queued, retried, regenerated, and interrupted turns retain their original RAG toggle and
   resource scope rather than reading later global UI state.

## Architecture

### Durable data

Add mirrored PostgreSQL and SQLite migrations for:

- `learning_resources`: owner, safe display name, MIME, PDF bytes, state, page count,
  embedding identity, failure detail, timestamps;
- `resource_chunks`: resource ID, physical page, ordinal, text, normalized embedding;
- `message_sources`: exact assistant message ID plus immutable citation metadata.

All list/read/status/content/delete/search operations constrain `owner_id` in SQL. Resource
deletion cascades through chunks and citation joins. Student-data deletion includes resources.

For this local-first slice PDF bytes live in the existing application database, like current
attachments. A later hosted deployment can replace that column with object-storage keys
without changing the public API.

### Preparation and retrieval

`orchestrator/retrieval/resources.py` owns the worker and retrieval abstraction:

- page extraction via `pypdf` (no network dependency);
- whitespace/paragraph normalization and page-bounded chunks of about 1,500 characters with
  a small overlap;
- a deterministic local hashing embedder for a fully working zero-model test baseline, with
  its identity stored per index;
- cosine retrieval restricted in the database to the authenticated owner and selected IDs;
- bounded top-k results, page deduplication, and server-assigned citation numbers.

The embedder is injectable so the product upgrade is a swap to the already-designed local
embedding server (for example BGE-small), not a schema/API rewrite. The hashing baseline must
be labelled in code and docs as the vertical-slice retrieval engine, not the final semantic
quality target.

On process startup, unfinished `processing` rows are requeued. Chunk replacement and the
transition to `ready` happen in one store transaction. Failures are terminal and visible until
retry.

### API

Add authenticated `/v1/resources` routes for upload, list, retry, delete, and inline PDF
content. Upload is bounded, validates the PDF signature/MIME, and uses generated IDs.

Extend chat requests with `use_rag` and `resource_ids`. The browser generation route performs
resource preflight before generation reservation. The blocking `/v1/chat` path receives the
same retrieval semantics so the public contract does not have two meanings.

Add structured resource citations to chat responses, SSE completion events, and message
history. Direct content links accept the existing private query-token mechanism because new
tabs cannot attach an Authorization header; URLs are constructed only at click time and are
never persisted.

### UI

- RAG toggle beside the current grounding controls;
- selected-resource chips and an accessible keyboard-operated `@` listbox;
- Settings → Files upload/status/retry/delete controls;
- structured source cards below answers with page and excerpt;
- direct page navigation in a new tab (the current CSP/frame policy intentionally rules out an
  embedded PDF viewer for this first slice).

The slice uses a small feature-local English catalog with the same interpolation rules as the
main translator. This avoids regenerating or overwriting the localization work already in
progress; moving these keys into every completed locale is follow-up localization work.

## Verification

Automated coverage completed for this slice includes:

- PDF extraction preserves physical page numbers and produces page-bounded chunks;
- owner A cannot read, download, or retrieve owner B's resources;
- explicit resource scoping and no-hit behaviour;
- a selected preparing resource rejects before inference reservation/transcript mutation;
- citations attach to the exact assistant message and survive history replay;
- concurrent writers cannot steal a streamed turn's citations;
- deletion during a streamed reply cannot fail cleanup or leak an inference admission;
- service shutdown waits for running preparation, preventing duplicate work after reload;
- retry cannot strand a failed resource in `processing` during worker cleanup;
- SQLite citation replay and learner-resource erasure through the store test surface. The
  PostgreSQL implementation mirrors the same schema and methods and is linted here; legacy
  migration upgrades and a live-PostgreSQL integration run still need explicit integration
  coverage before hosted deployment.

Manual browser and real-file coverage includes upload limits/signature handling through the
live route, `Preparing` → `Ready`, toggle and keyboard `@` selection, stable selected-resource
chips, direct page navigation, and a clean browser console. The queue/regenerate scope is
retained structurally in each queued job and in the original generation item; additional UI
automation for those paths remains useful regression hardening.

The untracked `resource.pdf` is manual smoke-test input only and will not be committed. Its
content is Grade 7 General Science, so the positive retrieval smoke uses a topic actually in
the book (for example kinetic energy). The requested `tan x` example is a negative grounding
test: Muta should say that the selected source does not contain that explanation rather than
invent a citation.

## Deferred after inspection

- per-owner file/count quotas plus killable PDF parsing with time, page, text, chunk, and RSS
  limits before exposing uploads to untrusted multi-user traffic;
- semantic-quality bakeoff and switch to the supervised local BGE embedding service;
- OCR for scanned/image-only books;
- resumable uploads and object storage for hosted deployments;
- printed page-label detection in addition to physical PDF page;
- short-lived signed preview URLs and HTTP range delivery;
- cross-resource synthesis, highlights, notes, and automatic concept cards.
