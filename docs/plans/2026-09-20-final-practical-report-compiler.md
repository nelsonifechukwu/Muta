# Final practical report compiler

## Purpose

Compile the running `science-tutor-final-practical-2000-v2` output without
changing the run, launching inference, or joining the obsolete historical
five-model comparison. The output is a structured-numeric practical component;
it is not by itself the final tutoring-quality or target-CPU decision.

## Implementation

1. Add a separate append-only compiler. Pin and verify the exact final config,
   final roster, inherited transport receipt, practical battery, existing
   independent launch-review/static-GO receipts, existing validation helper,
   and the three grading/statistics sources frozen in the runner config.
2. Require a complete 10,000-response terminal seal. Recompute the full file
   inventory, pre/post model identities, raw-response hashes and projections,
   request joins, individual/JSONL joins, and queue disposition before grading.
3. Grade every response with the frozen `practical_common.grade`, retain the
   per-response grading ledger and per-item paired-score ledger, and replay the
   frozen conditional cluster bootstrap and fresh-practical thresholds. Do not
   import or synthesize known-suite guards for candidates absent from that old
   roster; expose that guard as intentionally unevaluated here.
4. Require the SHA256 of remote `COMPLETED.json` captured independently before
   transfer, preventing a coherent local rewrite from self-resealing the run.
   Emit a completion seal only after all source/input identities are rechecked.
   Preserve the single-realization, non-bitwise transport, family-overlap,
   approximate-bootstrap, semantic-review, and target-CPU limitations.
5. Stage the complete report in a private sibling directory, verify it, and
   publish with an OS-level atomic no-replace rename. Exercise the new path with
   synthetic complete runs plus fixed-input, coherent-reseal, and publication
   failure attacks, then request an adversarial review before declaring it ready.

## Commands

Static input preflight (safe while inference is running):

```sh
.venv/bin/python -m bench.winner_battery.final_practical_report --preflight-only
```

Before copying the complete remote output, capture its terminal seal through
the independent control channel. Compile only after that unchanged output is in
the stated local `run` directory, substituting the captured lowercase digest:

```sh
.venv/bin/python -m bench.winner_battery.final_practical_report \
  --run-root provenance/science-tutor-20260919/evaluation/final-practical-2000-v2/run \
  --output provenance/science-tutor-20260919/results/final-practical-2000-v2-score \
  --completed-sha256 '<INDEPENDENTLY_CAPTURED_REMOTE_COMPLETED_SHA256>'
```

## Review outcome

Adversarial re-review: **GO**. The reviewer reproduced and then verified the
closure of coherent-reseal, arbitrary-input production stamping, missing launch
review binding, incomplete transport disclosure, and partial-publication
attacks. Compiler SHA256:
`f4f82f4d39f4d5c657a78a9a9e0761615ba42b9d40edef4c582ed216fedf26d2`.
Focused-test SHA256:
`e5cb2a31088b50d3c4e477d136aacac859791a6fd096f2de8d6d550985b1ffe7`.
All 1,725 `bench/winner_battery` tests pass; the 12 focused tests, targeted Ruff,
and format checks pass. Operationally, never replace the independently captured
remote terminal digest with one computed from the copied local run.
