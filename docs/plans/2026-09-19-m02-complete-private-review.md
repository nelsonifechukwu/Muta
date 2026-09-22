# Complete retained private-text review for M02

Pre-execution plan, 19 September 2026. This extends the earlier 16-prompt/key
inspection to **all 350 stored prompts, completions and answer fields** in the
two exact private warehouse shards. The earlier completion reasoning and 334
unread prompts were an explicit gap. This is reasoning-graph inspection, not
answer certification, rewriting training rows or admitting a new benchmark.

Both actual shard hashes/bytes/counts and the warehouse manifest were rechecked
before planning. The combined prompt/completion/answer text is 135,698 characters:
34,117 in 47 WAEC rows; 101,581 in 303 Cheetah rows. This is a small, finite
in-place review, not another 2.5M-row scan or corpus download.

## Read-only extraction and partition

Use a narrow reviewed slicer bound to only these two input identities:

| Role | Warehouse shard | Rows / bytes | SHA256 |
|---|---|---|---|
| waec | `part-00100-private-waec-e1720e95858d.jsonl` | 47 / 296,036 | `c165a0e0f7ede07b9e2843aef5ac714c88b45dbdfd73f99d733d3b35b115bb4e` |
| cheetah | `part-00101-private-waec-363447d90421.jsonl` | 303 / 1,716,873 | `9514e87da6237cd0f2dd9b6f73d19d7ba447ea83ecfb333cf45e8778f22648c6` |

All paths are within `data/muta-stem-v2-warehouse-20260916-v7/`. The slicer must
reject changed bytes/counts, bad selectors/ranges, duplicate JSON keys or missing
string fields before any text is emitted. Limit a call to 25 rows and 32,000
characters of serialized output, with no source truncation or silent omission.
Read only the requested prompt/completion/answer projection plus compact IDs,
physical lines and raw-line hashes into transient tool output. No question text
is saved to a new file, report or corpus. Verify the slicer independently first.

Partitions: root reviews WAEC lines 1–47; three independent agents review
Cheetah lines 1–101, 102–202 and 203–303. Each reader consumes every row in its
range in small complete slices. Earlier 16 rows may be revisited because their
completion text was not covered previously. No model response is regraded.

## Classification and evidence

Apply the existing M02 essential graph, not keyword presence: free parameter
in coefficients or RHS → changing consistency/solution cardinality, including
implicit exceptional-parameter targets. Fixed nonsingular solves, fixed slope
recovery or ordinary algebra are not automatically the same graph; a numeric
key does not exclude a genuine rank-boundary question. Mark absent visuals,
missing data, truncated/malformed content or ambiguous graphs as **unresolved**.
Do not reconstruct missing figures from an answer or call their source clear.

Each partition writes only a compact JSON review ledger under
`provenance/evaluation/winner-battery/private-m02-review/`: every line, row ID,
raw-line hash, an abstract task-graph label and scoped decision (`no_m02_graph_in_retained_text`,
`possible_m02_graph`, or `unresolved_context`). Include field coverage, actual
input identity and reviewer attribution. No quoted private wording, numbers
from exam statements, copied explanations or source credentials belong in it.
The classification concerns M02 overlap, not stored-answer correctness.

Root reconciles exact 350-line coverage and identities and independently reads
every positive/ambiguous item plus a fixed 1-in-20 sample of agent negatives.
Another agent cross-reviews root's flagged items and fixed-sample negatives.
Preserve disagreements explicitly. A retained-text review cannot reconstruct
missing originals, infer publisher grants or clear other source families.

No fresh question, rubric, model run, confidence claim, model promotion or
benchmark admission is authorized by this source-role review. The independent
battery remains at zero admitted items until all its separate gates pass.
