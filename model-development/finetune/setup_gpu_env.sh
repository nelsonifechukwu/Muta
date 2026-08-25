#!/usr/bin/env bash
set -euo pipefail

VENV_PATH="${1:-.venv}"
python3 -m venv --system-site-packages "$VENV_PATH"
"$VENV_PATH/bin/python" -m pip install --upgrade pip
"$VENV_PATH/bin/python" -m pip install -r "$(dirname "$0")/requirements-gpu.txt"

# The supplied host has PyTorch 2.7. torchao 0.18 is pulled transitively but requires
# newer torch APIs; BF16 LoRA does not use torchao, so remove it from this isolated venv.
"$VENV_PATH/bin/python" -m pip uninstall -y torchao
"$VENV_PATH/bin/python" - <<'PY'
import torch
from unsloth import FastLanguageModel

assert torch.cuda.is_available(), "CUDA is unavailable"
print(f"ready: {torch.__version__=} gpu={torch.cuda.get_device_name(0)}")
PY
