# Africa-54 interface-language baseline

## Requirement

Muta's language catalog must represent the main written languages of all 54 fully recognised
African sovereign states before optional non-baseline languages are prioritised. Coverage must
be provable from country-to-language data, not inferred from the number of entries in a flat
selector.

The candidate rule is: nationally official or working written languages with a country-wide
function, plus languages at 20% or more in pinned CLDR territory data, plus specifically sourced
country-wide lingua francas. It does not mean every constitutionally listed, regional, or minority
language. The checked-in matrix remains draft until every country-language edge has a recorded
basis/source and regional review.

## Data policy

- Use the 54 fully recognised African sovereign states identified by ISO alpha-2 codes and the
  UN M49 Africa grouping. The African Union has 55 members because it also includes the Sahrawi
  Arab Democratic Republic; that distinction must remain explicit in documentation.
- Give every country one or more main-language tags. Include nationally important indigenous
  lingua francas even when a European language is the sole nationwide official language.
- Identify languages with BCP 47 / ISO language tags and display autonyms rather than flags.
- Keep sign-language accessibility on the product accessibility roadmap; a written interface
  pack must not falsely claim to provide sign-language localization.
- Keep interface-translation readiness separate from response-language mapping. Every mapped tag
  is selectable as a response preference; only complete UI catalogs localize the browser chrome.
- Keep country coverage and review status in project documentation rather than adding planning
  information to the learner-facing Settings panel.
- Record community-review status independently. Machine-generated or unreviewed copy must never
  be labelled complete.

## Implementation

1. Add a standalone `ui/africa-languages.js` registry containing the 54-country matrix and the
   deduplicated baseline language definitions.
2. Build the African section of the Settings selector from every mapped tag, before the existing
   "Other languages" group, and keep every option enabled as a response preference.
3. Keep the country matrix in documentation for coverage auditing and community review; do not
   reproduce the planning matrix in the learner-facing Settings panel.
4. Add tests that fail if there are not exactly 54 unique countries, a country has no main
   language, a mapped language is absent from the registry, an autonym is missing, or an
   additional language appears ahead of the Africa-54 baseline.

## Sources and review

- Country scope: United Nations Statistics Division M49 Africa grouping.
- Language metadata starting point: Unicode CLDR territory-language information, which is aimed
  at literate populations able to use a language with computers and records official status.
- Continental cross-check: African Union member-state list and its explicit count of 55.
- The checked-in country matrix remains a product policy artifact. It requires named regional or
  native-speaker review because official status and practical lingua-franca use are not the same.

## Completion boundary

This change maps every baseline language into a visible, test-gated response-language choice.
That makes the preference available to the trusted generation instruction, but does not by itself
prove model response quality or complete UI localization in every language. Translation and
community review proceed country by country until selecting each baseline language also translates
the whole interface.
