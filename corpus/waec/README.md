# WAEC study corpus

This directory is generated from the two public study sources supplied by the user:

- <https://www.waeconline.org.ng/e-learning/> - official question pages, examiner comments,
  and expected answers for General Mathematics, Physics, Chemistry, and Biology.
- <https://cheetahwaec.com/past-papers> - explicit Mathematics PDF downloads for 2019-2025.

The files are for local study and research. WAEC pages state that all rights are reserved;
Cheetah WAEC's terms reserve its original explanations and prohibit harmful scraping or mass
downloads. Do not republish the downloaded source material. Every record retains its source URL
and publisher notice.

## Files

- `questions.json` - the normalized JSON array requested by the user.
- `questions.jsonl` - the same records, one per line, for streaming/RAG tooling.
- `manifest.json` - source coverage, failures, warnings, and run provenance.
- `schema.json` - the validation contract.
- `assets/` - diagrams/equations that are separate images on WAEC pages.
- `raw/` - cached source HTML and publisher-provided PDFs.

An answer with `answer_status: "published"` came from the named publisher. The collector does
not pass off generated text as an official marking scheme. Records with missing published
answers stay in the corpus with `answer_status: "missing"` and can be solved later through a
separate, provenance-bearing step.

Some WAEC answers consist only of publisher-supplied images. In those records,
`worked_solution` points at one or more local `[asset: ...]` files and
`extraction_warnings` contains `published_answer_is_visual_asset`. Review the image rather than
expecting a lossy OCR transcription.

`content_status: "needs_visual_review"` means that the question or answer depends on one or
more assets. `"incomplete"` means a required question/answer component could not be recovered.

## Regenerate

From the repository root:

```sh
uv run python corpus/waec_collect.py --output-dir corpus/waec
```

The collector is deliberately sequential and delayed. It caches successful responses, resumes
from them, merges newly collected records into an existing output by stable record ID, and never
bypasses access controls. Pass `--replace` only when an intentional clean rebuild is needed. Use
`--offline` to rebuild normalized output entirely from the cache. Use a scratch output directory
for a small live check:

```sh
uv run python corpus/waec_collect.py \
  --sources waec \
  --subjects biology \
  --years 2023 \
  --max-questions 2 \
  --output-dir tmp/waec-sample
```

Tests are offline and fixture based:

```sh
uv run pytest corpus/tests/test_waec_collect.py
```
