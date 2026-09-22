# Twelve-candidate science generation release

Prepare local code and a new immutable release only. Root captures and verifies
the Oracle inventory, independently reviews this materializer/controller, then
stages and executes it. The writer performs no remote mutation or GPU work.

The release contains the four controls C1/C2/C3/C4 and the half/final checkpoint
of each P1/P2/P3/P4. P2/P3 use their terminal Oracle relocation paths. All 12 use
the unchanged reviewed `evaluate_pilots.py` SHA256
`74c1037f298533a37f8637fb37fb358e58555766a054d8289892871a19f189df`,
its three frozen helpers, one 72-row prompt artifact, and one fixed decoding
protocol. Existing training sources, configs, checkpoints and results stay in
place. No ranking or grading runs here.

## Input and reconstruction

Root supplies a hash-bound remote inventory JSON. It contains `schema_version`,
`host` (`python`, `release`, `outputs`, `control`), four `controls`, four `runs`,
and `remote_verification` assertions for run inventories, control completions and
input trees. The actual collector also supplies full `input_trees`, per-pilot
`control_verification`, and its own `collector` reference; these are required and
preserved. P4's controller did not originally seal its directory, so its explicit
qualification/config/trainer references and retrospective directory inventory are
labeled separately from the original sealed controller inventories. Each run
supplies `run_id`, `configuration`, `config_ref`,
`completion_ref`, parsed `completion`, `control_completion_ref`, two
`checkpoint_refs`, `base`, and `tokenizer`. Each checkpoint supplies `step`,
`path`, `tree_sha256`, and a `checkpoint_seal` file reference. Controls use the
reviewed evaluator's candidate schema. Scalar path/hash references are sufficient;
the terminal completion already contains complete checkpoint inventories.

The materializer checks exact P/C lineage, the frozen numeric training treatment,
native source sets, terminal status/steps/tokens, two checkpoint file inventories
and their seals, and distinct outputs. It derives the generation candidates from
those verified records, including P3 by loading its continued checkpoint directly
on its original parent. It rejects missing/duplicate candidates and rehashed
treatment changes. Local prompts are validated as 72 unique id/messages objects;
their bytes are copied into the new bundle, with an explicit remote prompt path.
That path is exactly `<host.release>/prompts.jsonl`, so transferring the new
bundle stages the declared prompt artifact without a separate copy.

## Queue and evidence

`materialize --inventory FILE --inventory-sha256 SHA --prompts LOCAL_JSONL
--remote-prompts ABS_ORACLE_PATH --output NEW_LOCAL_RELEASE` creates exclusively
new local files and seals a manifest. All source/config/input files become
read-only. `launch --manifest <release/manifest.json> --manifest-sha256 SHA`
reconstructs the exact config from the sealed inventory, checks UID/interpreter/
release identity, and verifies original remote config/completion/control refs.

The queue claims an exclusive new control directory and rejects any pre-existing
candidate output. It checks the shared Oracle GPU lock and idle device before
each child. The lock is released before starting the reviewed child, which
acquires that same lock itself for its entire inference. A competing owner causes
failure, never concurrent model execution. The queue runs one child at a time,
with an explicit two-hour bound per child and no retries. On interruption it
terminates only its own child.

After every child, validate the exact config/source/prompt/candidate identities,
all 72 durable responses, nine raw batch artifacts and the terminal inventory.
Recheck all 12 terminal results before sealing queue completion. Any failure
preserves stdout, completed prior candidates and an immutable FAILED receipt,
then stops. Partial results never trigger ranking or grading.

## Verification

CPU tests cover lineage and missing-candidate rejection, token/numeric changes,
checkpoint and seal mismatch, immutable materialization, rehashed config changes,
duplicate launch refusal before a child, serial fail-stop behavior, and terminal
inventory/response completeness. Independent review is required before root
executes the new release.

## Local readiness

The actual captured inventory is
`provenance/science-tutor-20260919/evaluation/pilot-inventory-20260919T1850.json`,
SHA256 `32312e633b610c4d171530bfac597e69fef20d4db93119e01fdfc4565df43956`.
Its 12 candidates reconstruct successfully. The shared admitted prompts are
`evaluation/development72-v1/prompts.jsonl` within the same provenance campaign,
SHA256 `e1369765c215fbc92a55222d5ebedfac83c5f79a9870d83115cc1a4dcb1da089`.
The destination is `release/development12-v1/prompts.jsonl` under the Oracle
science campaign; outputs and queue controls use separate `development12-v1`
directories.

Twenty-three CPU tests pass, including the actual captured inventory, negative
lineage/config/seal mutations, immutable snapshots, exact serial order, fail-stop
behavior, and terminal tree/response/raw-batch checks. Targeted Ruff checks pass.
The controller candidate SHA256 is
`2937b42e235eb5f242ea51f1c2805cd5a70246f1c073c5704f935a33844a590e`.
No production release has been materialized, staged or executed by the writer.
