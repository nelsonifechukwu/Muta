# Depth pruning (Block Influence / angular distance)

Stages: (A) `calibration.py` → `block_influence.py` ranks layers on CPU;
(B) `prune_gguf_layers.py` + `screen_metadata.py` + `run_screen.sh` measure unhealed prunes on
the reference audit image; (C) `prune_hf_layers.py` + `run_heal_sweep.sh` + `export_gguf.sh`
heal on a GPU and export; `accuracy_battery.py` + `score_candidates.py` decide.
Plan and constraints: `docs/plans/2026-09-16-depth-pruning-qwen25-1.5b.md`.
Pure helpers are tested by `test_prune_helpers.py` (no GPU, no network).
