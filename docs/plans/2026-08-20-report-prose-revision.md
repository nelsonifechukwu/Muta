# Report prose revision

Date: 2026-08-20

Status: Complete

## Reference

The writing reference is the current and historical `docs/index.html` from the KronOpt project.
The relevant revisions replace informal framing with explicit technical statements, remove
subjective and emotive wording, define terms before interpreting figures, and distinguish
measurements, estimates, and limitations in the sentence that reports each result.

## Scope

- Rewrite all visible prose in `muta-iq/dashboard/index.html`.
- Rewrite dynamic report copy in `muta-iq/dashboard/script.js`, including the experiment ledger,
  FAQ, chart labels, campaign notes, empty states, and status text.
- Preserve measurements, formulas, artifact names, hashes, citations, IDs, controls, and data
  bindings.
- Keep the report structure and figures unless a heading or caption depends on informal framing.

## Style constraints

- Use direct declarative sentences.
- Name the measurement method, hardware context, and evidence tier where they affect a claim.
- Use measured quantities instead of qualitative intensifiers.
- Use technical terms only in their literal established sense.
- Remove metaphors, analogies, rhetorical questions, narrative transitions, praise, emotive
  language, marketing language, summaries, and concluding sign-offs.
- Do not describe a technical result as teaching, surviving, rewarding, collapsing a field,
  crossing a boundary, or exposing a hidden truth.

## Verification

- Search the rendered text and source for prohibited constructions and known informal phrases.
- Run the dashboard test suite, JavaScript syntax check, Python compile check, and repository
  whitespace checks.
- Inspect the report at desktop and phone widths in the browser and confirm a clean console.
- Commit the prose revision as one grouped change, push it, and synchronize the GCP checkout.
