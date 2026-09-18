from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exporter = _load("merge_and_quantize")


def test_export_commands_pin_converter_and_q4_k_m(tmp_path):
    llama = tmp_path / "llama.cpp"
    (llama / "build/bin").mkdir(parents=True)
    (llama / "convert_hf_to_gguf.py").write_text("# converter")
    (llama / "build/bin/llama-quantize").write_text("binary")
    commands = exporter.export_commands(
        llama_cpp=llama,
        merged=tmp_path / "merged",
        f16_gguf=tmp_path / "f16.gguf",
        final_gguf=tmp_path / "final.gguf",
    )
    assert commands[0][-2:] == ["--outtype", "f16"]
    assert commands[1][-1] == "Q4_K_M"
