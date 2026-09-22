# Final science MC context-dependency correction

## Finding

Independent pre-inference review rejected `final-science-mc-v1`. Eight ScienceQA
rows ask the model to read a thermometer that is not represented in the text.
Their raw `image` and `hint` fields are null, while the source solution refers to
the top of red liquid and a scale that the model-facing prompt does not contain.
The source answer is therefore not derivable from the question and choices.

The exact excluded IDs are:

- `scienceqa:167`
- `scienceqa:3857`
- `scienceqa:4767`
- `scienceqa:7528`
- `scienceqa:10114`
- `scienceqa:12134`
- `scienceqa:15206`
- `scienceqa:20239`

The audit covered all 733 ScienceQA holdout rows using the question, ordered
choices, source solution, and source metadata. Broad deictic/visual screening was
followed by family-level inspection. Other deictic matches were text-closed: for
example, animal-classification rows include the relevant observations in their
ordered choice descriptions, and reaction rows include the reaction passage in
the question.

## Correction

Keep v1 unchanged as rejected evidence. Publish an append-only
`final-science-mc-v2` pack from the same immutable 1,591-row holdout, excluding
the eight reviewed missing-context rows plus the already excluded non-MC
MathDial dialogue. The corrected pack must contain exactly 1,582 prompts:
725 ScienceQA and 857 SciQ rows.

The v2 freezer must fail if any reviewed exclusion no longer has the exact
thermometer-question family, expected skill metadata, temperature choices, or
source-solution evidence. It must retain the same prompt/key isolation,
canonical joins, source bindings, exclusive publication, and manifest-last
failure behavior as v1.

The final capture runner must default to 1,582 prompts, accept only a manifest
whose source-row arithmetic is internally consistent, and continue to validate
the separately bound key receipt without opening the key file during capture.
