# WAEC public study corpus ingestion

## Goal

Build a reproducible, source-attributed JSONL study corpus from the user-supplied public
WAEC e-Learning and Cheetah WAEC pages for General Mathematics, Physics, Chemistry, and
Biology. Preserve questions, published expected answers/solutions, examiner observations,
marks, diagrams, and source URLs without silently claiming that visually incomplete records
are usable.

## Source and access constraints

- WAEC e-Learning publishes question pages and expected answers through ordinary public HTML.
  Its pages state that copyright is reserved. Fetch slowly, identify the client, keep the copy
  local for the user's study, retain attribution, and provide a metadata-only mode.
- Cheetah WAEC publishes explicit download links for paired mathematics problem/solution PDFs
  for 2019-2025. Its terms allow learning/revision and prohibit scraping or mass downloading
  that harms the site. Download only the linked PDF set, with a delay and no parallel requests.
- Never bypass authentication, CAPTCHAs, paywalls, anti-bot controls, or access errors.
- A source failure is recorded in a manifest; it is not retried aggressively.

## Outputs

- `corpus/waec/schema.json`: JSON Schema for normalized question records.
- `corpus/waec/questions.jsonl`: one normalized question record per line.
- `corpus/waec/manifest.json`: run provenance, counts, failures, and coverage.
- `corpus/waec/assets/`: downloaded question/answer images needed to interpret records.
- `corpus/waec/raw/cheetah/`: the publisher-provided PDF downloads.
- `corpus/waec/README.md`: usage, limitations, licensing notes, and regeneration commands.

Generated records must carry source URLs, source type, subject, year, paper/session when known,
question number, question text, options, published answer, worked solution, examiner observation,
marking scheme, local asset paths, extraction warnings, and a content completeness status.

## Implementation

1. Add a conservative collector in `corpus/waec_collect.py` using the standard library plus
   BeautifulSoup if available. It must support source/subject/year limits for testability,
   caching, a configurable delay, resumability, and metadata-only discovery.
2. Discover WAEC paper pages from each subject home page, then question pages from each paper
   page. Parse the central question content while excluding global navigation/footer material.
3. Download question-page images with stable hashed names and retain their original URLs.
4. Discover Cheetah's explicit PDF links from its past-paper page, download them sequentially,
   and extract text with `pypdf`. Pair problem and solution documents by year. Flag records whose
   equations/diagrams are incomplete; do not overwrite a cleaner WAEC record with a degraded PDF
   extraction.
5. Normalize/deduplicate by source URL and stable record ID. Validate every output row against
   the schema before atomically replacing the generated files.
6. Add fixture-based tests for discovery, parsing, image references, deduplication, validation,
   and failure accounting. Network access remains an explicit integration mode.

## Verification

- Run unit tests and lint on the collector/tests.
- Run a small live crawl first and inspect records/assets.
- Render representative Cheetah PDF pages with Poppler and inspect them against extracted text.
- Run the full respectful crawl only after the sample succeeds.
- Report exact counts by subject/year/source, incomplete records, image-bearing records, failed
  URLs, and any content that could not be downloaded.

## Answering policy

Prefer publisher-provided expected answers and worked solutions. Do not label model-generated
text as official. If an item has no published answer, retain it with `answer_status: missing` for
later solving rather than inventing an unverified answer in a bulk run. Any future generated
solution must use a separate field with model/tool provenance and verification status.
