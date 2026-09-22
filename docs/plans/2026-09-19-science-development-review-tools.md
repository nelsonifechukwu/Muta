# Offline development review tooling implementation

Implement one compact offline module, `development_review.py`, with packet and
compile commands. It never invokes an inference library, starts a process, or
loads model weights. The pre-generation adjudication protocol and four-parent
selection amendment govern all scoring; this implementation adds no selection
criterion. Independent code review precedes use on real model outputs.

The packet command requires a hash-bound generation config and explicit
twelve-candidate lineage/role/step roster. It accepts only twelve complete
72-response invocations with exact ordered input joins, source/config/model
identity receipts, all nine raw batch joins, and complete terminal inventories.
The exact admitted campaign and roster hashes are pinned in the implementation.
A separately hash-bound, root-captured all-twelve completion manifest must bind
each remote candidate directory and its `COMPLETED.json` hash. Local self-seals
alone are insufficient: otherwise text could be changed and re-sealed without
matching the preserved token batches. This is a capture/admission gate, not a
claim that the offline tool re-decodes tokens or rehashes remote model weights.
It rechecks the frozen 64 MC keys/eight tutor rubrics. Deterministic HMAC review
IDs use a separately supplied secret key; the reviewer packet excludes candidate
identity, profile, paths, checkpoint and training metrics. A separate mapping
preserves exact raw-line/response/config/seal identities. Styling may still reveal
model characteristics, as the protocol discloses.

The compiler preserves original primary, secondary and adjudication ledger bytes.
Every primary row is required. Secondary coverage is the union of all tutors,
all primary incorrect/ambiguous MC, and the same eight pre-ranked audit MC items
across all candidates. Each differing categorical/criterion judgment requires
an explicit evidence-backed adjudication; rationale-only differences remain in
the original ledgers. MC semantic choice, ambiguity, explanatory falsehood,
format and delivered-final-answer status remain separate. Correctness derives
only from the frozen choice key after semantic judgment. Nonempty tutor outputs
use the exact heldout-v2 reducer. Empty outputs require explicit all-false
assessment, receive zero/zero, and remain in every denominator.

Publication uses new output directories only, hash-bound seals, no overwrite or
automatic retries, and preserved failure markers. Compile checks joins again;
it does not trust a mutable packet manifest by existence alone. Selection uses
exact integer totals, predeclared tie-breaks and gross paired-loss/critical-case
guards, with no rescue checkpoint and at most two advancing lineages. Synthetic
fixtures cover partial/corrupt seals, mapping leakage, caps, mandatory secondary
coverage, explicit adjudication, guards and exact ties. No real outputs are read
or packets materialized during implementation.
