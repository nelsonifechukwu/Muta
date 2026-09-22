# Four science pilot loss panels

Read only the four verified local metric logs and the pinned terminal inventory
`evaluation/pilot-inventory-20260919T1850.json` (SHA256
`32312e633b610c4d171530bfac597e69fef20d4db93119e01fdfc4565df43956`).
Resolve each exact local metric filename from its remote completion reference;
verify SHA256 and byte length, including local trainer completion identity.

Extract raw loss points with the existing all-training-loss gallery's `extract`
and `stats` helpers and render with its `plot_panel` helper. Do not run its main
function or touch the old gallery. Require 126 training points at exactly steps
1 through 126 and two scheduled development points at steps 63 and 126. Check
full token accounting against each completion, including 8,002 distinct training
rows and the disclosed 62-row repeated tail. P4 uses its own native token budget.

Write a new standalone 2×2 PNG and SVG, exact numeric projection JSON, source
identity receipt and output checksums under
`provenance/science-tutor-20260919/results/pilot-loss-curves-v1`. No HTML, copied
logs, prompts, model weights, GPU access or model-output processing. Preserve
raw points without smoothing, inserted step zero or a selected-checkpoint line.
Use independent y scales and label that P4's native token losses do not support
cross-model ranking; every x-axis represents only this new 126-step stage.

Run numeric self-tests and exact readback of all written numbers. Recheck input
and helper hashes after generation. Root reviews the rendered figure before
completion. The output directory must be new; existing artifacts are preserved.

Generated five files: `four-science-pilots.png`, `four-science-pilots.svg`,
`loss-points.json`, `sources.json`, and `GENERATED.json`. Fifteen extraction/
validation self-test cases pass; all 504 training values and eight development
values exactly match their original source records after JSON readback. The four
output artifact checksums and all 12 local input file identities were rechecked.
The writer visually inspected the figure and found no clipping or overlapping
labels; root visual review remains the final task gate.

Generator SHA256:
`0f09c983527e51cc36b7a0aa144aa6fa71c378770a9191358d49045c22ddf72a`.
