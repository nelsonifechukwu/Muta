# Final source-heldout science MC freeze and evaluation

## Scope

Materialize every multiple-choice row already present in the immutable 1,591-row
science-tutor holdout.  The single multi-turn MathDial row is not an MC item and
is excluded explicitly; no MC sampling, ranking or post-response filtering is
allowed.  This work does not run inference and does not modify any existing
sealed artifact.

## Frozen artifacts

`model-development/science_tutor/freeze_final_science_holdout.py` publishes a
new, exclusive directory containing:

- `prompts.jsonl`: model-facing prompt objects only.  Each prompt is rebuilt
  deterministically from the source question and ordered choices, ends with a
  request for one option letter, and contains no assistant target, answer index,
  answer key, solution, lecture, rubric or correctness marker.
- `keys.jsonl`: the separate source-key ledger.  It binds each key to the exact
  source row and model-facing messages.  The keys remain source-keyed, not
  independently certified.
- `manifest.json`: source hashes, executable-source hashes, row counts, fixed
  ordering, output hashes, exclusions, leakage checks and limitations.  It is
  written last and is invalid if a failure marker exists.

Rows are ordered by the fixed source order `scienceqa`, then `sciq`, and then by
the exact row ID.  The freezer refuses source/schema/hash drift, duplicates,
invalid keys, symlinks, overwrite/resume and changed inputs during publication.

## Hash-bound capture and scoring

`bench/science_holdout_eval.py` has separate `capture` and `score` commands.
Capture never opens the key ledger.  It requires reviewed hashes for itself and
its GGUF runtime dependency, the exact prompt manifest hash and an exact
five-GGUF candidate-manifest hash.  It verifies all model/server bytes before
launch, uses the fixed final-role roster, runs candidates sequentially with
eight server slots, preserves every raw HTTP response, and seals an ordered
response ledger.

The fixed answer-only generation treatment is greedy decoding, seed 3407,
temperature 0, top-p 1, thinking disabled, prompt caching disabled, 4,096 tokens
per slot and at most 16 generated tokens.  The short cap is valid only because
the frozen prompt asks for one option letter.

Scoring is a separate post-capture action.  It requires the exact terminal
capture-receipt hash and exact key-ledger hash, revalidates every raw response,
and reports source-keyed correctness, strict bare-letter format adherence,
unparsed outputs, truncations and source/subject breakdowns.  Parsing is
conservative: bare or explicitly labelled letters and exact choice text are
accepted; conflicting or explanatory outputs are left unscored rather than
guessed.

## Verification and launch boundary

CPU tests cover deterministic freezing, answer-field isolation, source drift,
hash mismatch, exact-five roster admission, raw-output preservation,
conservative parsing and tamper rejection.  An independent reviewer must review
the exact builder/runner bytes and resulting artifact hashes before any model
inference is launched.
