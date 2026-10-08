# Local context and anti-sycophancy design

Country context is an example-selection hint, not evidence. The backend reads an existing raw
country setting when present and appends a small reviewed record after the shared prompt prefix.
No country value changes mathematical verification, scientific truth, safety policy, mastery, or
the response language.

The mapping covers the same 54-country scope as `ui/africa-languages.js`. Currency is included for
ordinary money examples. Exam names are included only where the repository has a reviewed label;
an empty exam list deliberately produces no exam claim. Missing, unknown, or malformed settings
produce no local-context block and never fail a turn.

Localisation must not become stereotyping. The prompt asks for local context only when it clarifies
the lesson and explicitly forbids changing a factual judgment. It does not infer ethnicity,
language, ability, income, urban/rural background, or interests from a country. Examples should use
ordinary neutral settings and avoid clichés.

The anti-sycophancy sentence is part of the stable safety prefix in `_safety.md`, `socratic.md`, and
`subgoal.md`. The deterministic learner-work checker remains the stronger control for parseable
mathematics; the prompt rule covers qualitative science and claims the checker cannot parse.
