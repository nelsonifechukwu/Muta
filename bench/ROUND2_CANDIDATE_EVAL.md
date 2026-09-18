# Round-two candidate evaluation

`bench/round2_candidate_eval.py` replays one frozen prompt set across the upstream
control, incumbent Muta, and every new LoRA candidate. It refuses an existing output
directory and verifies all declared SHA-256 values before loading a model.

## Candidate manifest

Paths may be absolute or relative to the manifest. Replace every digest placeholder
with the content receipt produced for that artifact.

```json
{
  "schema_version": 1,
  "campaign_id": "muta-round2-20260918",
  "candidates": [
    {
      "id": "upstream-qwen",
      "label": "Upstream Qwen2.5-1.5B-Instruct",
      "backend": "hf",
      "model": "/path/to/upstream-qwen25",
      "tokenizer": "/path/to/upstream-qwen25",
      "expected": {
        "model_tree_sha256": "<64 lowercase hexadecimal characters>",
        "tokenizer_tree_sha256": "<64 lowercase hexadecimal characters>"
      }
    },
    {
      "id": "incumbent-muta",
      "label": "Incumbent Muta Q4_K_M",
      "backend": "gguf",
      "model": "/path/to/incumbent.gguf",
      "server": "/path/to/llama-server",
      "expected": {
        "model_sha256": "<64 lowercase hexadecimal characters>",
        "server_sha256": "<64 lowercase hexadecimal characters>"
      }
    },
    {
      "id": "warm-r16-lr1e5",
      "label": "Warm LoRA r16 lr1e-5",
      "backend": "peft",
      "base_model": "/path/to/incumbent-merged-bf16",
      "adapter": "/path/to/warm-r16-lr1e5/adapter",
      "tokenizer": "/path/to/upstream-qwen25",
      "expected": {
        "base_model_tree_sha256": "<64 lowercase hexadecimal characters>",
        "adapter_tree_sha256": "<64 lowercase hexadecimal characters>",
        "tokenizer_tree_sha256": "<64 lowercase hexadecimal characters>"
      }
    }
  ]
}
```

## Run

```bash
python -m bench.round2_candidate_eval \
  --candidates provenance/configs/round2-evaluation.json \
  --suite judges \
  --output provenance/evaluation/judges-20260918T120000Z
```

Omitting `--prompt-id` runs all ten recovered Gate 1 prompts. If IDs are supplied,
at least two unique IDs are required. Greedy decoding, seed 3407, thinking disabled,
and the exact prompt-set digest are recorded for every response.

## Evidence written

| File | Purpose |
|---|---|
| `run.json` | Git, host, package, script, prompt-set, and decoding receipts |
| `candidate-manifest.json` | Byte-exact snapshot of the declared treatment matrix |
| `candidates/*/identity.json` | Expected and observed artifact inventories |
| `candidates/*/raw/*.bin` | Exact HTTP body or exact Transformers token output |
| `candidates/*/responses.jsonl` | Full prompt and response records for one candidate |
| `responses.jsonl` | Flat aggregate accepted by `bench/judges_prompt_report.py` |
| `summary.csv`, `summary.md` | Terse all-candidate comparison |
| `gate1-rubric.csv` | Existing Gate 1 rubric table |
| `artifact-inventory.json` | SHA-256 and byte count for every preceding evidence file |
| `COMPLETED.json` or `FAILED.json` | Terminal receipt |

To render the existing detailed Gate 1 report from the immutable aggregate:

```bash
python -m bench.judges_prompt_report \
  --responses provenance/evaluation/RUN/responses.jsonl \
  --artifacts provenance/evaluation/RUN/artifacts.csv \
  --csv provenance/evaluation/RUN/gate1-rubric-recheck.csv \
  --report provenance/evaluation/RUN/gate1-rubric-report.md
```
