# Expanded architecture screen

This directory retains the raw evidence used by the report's eight-model
extension.

- `screen-accuracy.jsonl`: ARC-Easy-50 results from the participant profiler's
  LM adapter.
- `screen-throughput.jsonl`: matched scalar and vector `llama-bench` rows for
  p512/tg128, two physical cores, and five internal samples per lane.
- `qwen25-15b-arc-easy-500.jsonl`: the promoted Qwen2.5 1.5B ARC-Easy-500
  validation row.
- `summary.json`: fail-closed aggregation consumed by the web report.

The larger accuracy run produced 71.8% `acc_norm` with a Wilson 95% interval of
67.70–75.57%. Accuracy is measured once on the exact GGUF and combined with the
separately measured throughput and RSS from each CPU configuration. Under the
fixed-15 formula, this gives 63.8176 for the scalar configuration and 80.7697
for the vector configuration.

Regenerate the summary from the retained evidence:

```bash
python -m bench.model_extension_summary \
  --accuracy bench/measurements/model-extension/screen-accuracy.jsonl \
  --throughput bench/measurements/model-extension/screen-throughput.jsonl \
  --validation bench/measurements/model-extension/qwen25-15b-arc-easy-500.jsonl \
  --out bench/measurements/model-extension/summary.json
```

The GCP proxy exposes two physical cores and four logical CPUs. It does not
expose package temperature, so these results do not establish thermal parity
with the physical competition laptop.
