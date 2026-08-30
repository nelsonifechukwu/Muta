# Bearings/navigation holdout — immutable first run

Checkpoint: `b5e726ba184d49b57a4f025ada16b43881c9b2da`

Result: **0/15 semantically correct**; 9 compiled and 9 rendered.

A rendered generic frame is not a pass. Every case was graded for bearing mathematics and visible navigation semantics.

| Case | Compiled | Rendered | Family | Result | Failures |
|---:|:---:|:---:|---|:---:|---|
| 1 | yes | yes | concept_process | FAIL | wrong semantic family: concept_process; no visible north reference line or label; no visible bearing value or bearing explanation |
| 2 | yes | yes | concept_process | FAIL | wrong semantic family: concept_process; no visible north reference line or label; no visible bearing value or bearing explanation |
| 3 | yes | yes | concept_process | FAIL | wrong semantic family: concept_process; no visible north reference line or label; no visible bearing value or bearing explanation |
| 4 | no | no | — | FAIL | production compiler returned no visualization; wrong semantic family: none; no real-browser visualization rendered; no visible north reference line or label; no visible route/bearing direction arrow; no visible bearing value or bearing explanation |
| 5 | yes | yes | concept_process | FAIL | wrong semantic family: concept_process; no visible north reference line or label; no visible bearing value or bearing explanation |
| 6 | yes | yes | concept_process | FAIL | wrong semantic family: concept_process; no visible north reference line or label; no visible bearing value or bearing explanation |
| 7 | no | no | — | FAIL | production compiler returned no visualization; wrong semantic family: none; no real-browser visualization rendered; no visible north reference line or label; no visible route/bearing direction arrow; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 8 | no | no | — | FAIL | production compiler returned no visualization; wrong semantic family: none; no real-browser visualization rendered; no visible north reference line or label; no visible route/bearing direction arrow; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 9 | no | no | — | FAIL | production compiler returned no visualization; wrong semantic family: none; no real-browser visualization rendered; no visible north reference line or label; no visible route/bearing direction arrow; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 10 | yes | yes | basic_geometry | FAIL | wrong semantic family: basic_geometry; no visible north reference line or label; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 11 | yes | yes | concept_process | FAIL | wrong semantic family: concept_process; no visible north reference line or label; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 12 | yes | yes | basic_geometry | FAIL | wrong semantic family: basic_geometry; no visible north reference line or label; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 13 | no | no | — | FAIL | production compiler returned no visualization; wrong semantic family: none; no real-browser visualization rendered; no visible north reference line or label; no visible route/bearing direction arrow; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 14 | no | no | — | FAIL | production compiler returned no visualization; wrong semantic family: none; no real-browser visualization rendered; no visible north reference line or label; no visible route/bearing direction arrow; no visible bearing value or bearing explanation; no visible distance units or computed distance |
| 15 | yes | yes | concept_process | FAIL | wrong semantic family: concept_process; no visible north reference line or label; no visible bearing value or bearing explanation; no visible distance units or computed distance |
