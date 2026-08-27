# Visualization V2 acceptance fixtures

These schema-version-1 fixtures are release QA data, not production routing data. Production
modules must not import them or match their IDs/full prompt strings.

The acceptance corpus is exactly 200 unique cases:

- `stem_supplied.json`: all 50 supplied cross-STEM prompts.
- `math_supplied.json`: all 100 supplied mathematical cases. The attachment contained 100
  intended cases (65 explicit and 35 implicit/unusual), so no synthetic completion was needed.
- `synthetic_held_out.json`: 50 separately designed, progressively harder prompts.

Every supplied prompt is retained in `raw_prompt`. `normalized_prompt` records only an audited
renderable form. The only semantically material repair is `math-046`: the source placed two
Gaussian terms on separate lines without an operator. Its per-case `normalization_decision`
records why the audited equation uses their difference. Stray brackets and multiline source
formatting remain in the raw field, and all other normalization/topology decisions are listed in
the fixture metadata rather than being silently discarded.

Each case declares the expected intent, reusable visualization family, renderer, spec kind,
controls, and executable semantic oracles. `scripts/visualization_v2_gate.py` compiles them through
the production planner, validates the typed spec, runs those oracles, and merges real-browser
render/interaction evidence. The release gate rejects any result below 200/200; waivers are not
supported.
