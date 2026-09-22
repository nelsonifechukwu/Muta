# Five-model known-suite comparison compiler

## Implementation plan

Add an explicit `--roster full-five` mode to the existing semantic-review
compiler. Keep the default `pilot-nine` mode, its pinned roster, old validation
semantics, and every scoring/aggregation rule unchanged. This change touches
only the post-inference compiler and its tests; it neither edits the frozen
inference snapshot nor launches inference.

The new mode pins
`provenance/evaluation/full-five-gguf-20260919/candidate-manifest.json` at SHA256
`10ac72b6ce3b2ffcb29612814be9933e377544d8d55161e6fa746545786a7475`.
Require the complete manifest bytes (including candidate order, paths, labels,
metadata, and hashes) to equal that pinned authority: the evaluator copies the
original manifest bytes into its sealed tree. A user-supplied roster or digest
override is intentionally unavailable.

Retain the existing sealed inventory, evaluator/settings, model/server,
prompt/request/raw-response, GPU-offload, duplicate-prompt and semantic-ledger
joins. The same frozen review authorities and denominators apply: 50 MC,
50 written STEM, judges /96 and deduplicated /86 per model. No new composite
score, automatic prose grader, independent-battery claim or target-CPU score
is introduced. The report records the chosen roster authority and states the
known-suite scope explicitly.

Test both modes with sealed fixtures; verify cross-mode rejection, exact
five-roster identity/order rejection even after resealing, preserved raw and
ledger failure gates, a full 550-response aggregation, and CLI/report provenance.
Root performs independent adversarial review before this code is used on the
actual campaign outputs.

## Implementation and local verification

Implemented `--roster {pilot-nine,full-five}` in
`bench/round2_comparison_report.py`. `sealed_run(..., roster="full-five")`
selects the same compiled-in authority for read-only validation. Omission still
selects the historical nine-candidate mode. The full-five branch additionally
requires byte-exact snapshot identity, preventing silent roster reordering,
path substitutions, metadata changes or alternate manifest serialization.

The compiler writes the selected roster path/digest/mode and known-suite scope
into the new report, while retaining all old score columns and /50, /96, /86
denominators. No old report, rubric or inference source was changed.

Validation: 37 focused tests passed, including both explicit full-five and
implicit default-pilot end-to-end synthetic compiles; 550/990 full-suite joins;
stale-ledger refusal before output creation; cross-mode and source-drift
refusal; exact five-roster order/path/metadata/formatting rejection; and the
pre-existing raw/command/cache/ledger invariants exercised in both modes.
`ruff check` passed for the compiler and its tests. These synthetic fixtures
are not model results. Independent root review remains required before use.

Example (paths must name the actual sealed full runs and completed ledgers):

```bash
.venv/bin/python -m bench.round2_comparison_report --roster full-five \
  --stem /path/to/sealed/stem --judges /path/to/sealed/judges \
  --math-review /path/to/math-review.jsonl \
  --science-review /path/to/science-review.jsonl \
  --mc-review /path/to/mc-review.jsonl \
  --judges-review /path/to/judges-review.jsonl \
  --out /path/to/new-comparison-directory
```

## Independent review before actual compilation

Root inspected the implementation and independently reproduced 37 passing tests.
A separate reviewer also reproduced all 37 tests, validated the actual sealed
five-model judges run, confirmed that the same tree is rejected in pilot-nine
mode, and recomputed every historical nine-model aggregate from its sealed raw
outputs and existing ledgers. Every historical aggregate exactly matched its
stored result. No scoring change or cross-mode bypass was found. The reviewed
compiler SHA256 is
`33eedb53921de70cc2b3a4109fe52b507512fe3f4b029cacaeb311f6d39cbf3c`;
test SHA256 is
`bb243fadf9d816714a6453eebe6b18baeba1bbb6f370aadf50d9da7d42738347`.
This approves the compiler, not unreviewed model answers or an overall winner.
