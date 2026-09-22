#!/usr/bin/env python3
"""Freeze explicitly selected round-two pilots into three full-run configs."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Any

from campaign_io import inventory_tree, sha256_file
from compile_round2_pilots import PilotResultError, validate_pilot_config

CANONICAL_CLEAN_SELECTION = "clean-r16-lr1e5"
CANONICAL_WARM_SELECTION = "warm-r16-lr5e6"
CANONICAL_GGUF_SUFFIX = "-q4km"
CANONICAL_GGUF_PREFIX = "pilot-"
CANONICAL_CONFIG_GIT_PATH = "provenance/configs/full-runs.json"
CANONICAL_PILOT_CONFIG_SHA256 = "35eb48a88b7958f856eb757b1ef05f8022fd238d9465ec770b0d2ff54d14ad23"
CANONICAL_PILOT_RESULTS_SHA256 = "511333117563e3fc3e74808dcfdde2389574af7b38e2b688a639bface6257929"
CANONICAL_PILOT_COMPILER_RECEIPT_SHA256 = (
    "8df2683fffad15607d79cb1a15b83fd792980eaceb1d9788abd3007cfeb54951"
)
CANONICAL_DATA = {
    "artifact_rows": 300_350,
    "rights_clean_rows": 300_000,
    "fingerprint_sha256": "037edf28cccff62d90c23e2d6caf56b9998dea6928080f98af2a513f9f92910e",
    "manifest_sha256": "93b7dbcbad72350e099d8951effcbc9a253693dc364b25ffc165102a6e844f4e",
}
CANONICAL_VALIDATION = {
    "rows": 5_000,
    "fingerprint_sha256": "c056e1744fe148f847354527aa7c7caf6b1fc24fec509f9834d700345e68cc8b",
    "manifest_sha256": "2bbde7545eef5ddd531705e6e71ebc09321e3c7bfbb371ec89ed471696dda301",
}
CANONICAL_TOKENIZER = {
    "lineage_receipt_sha256": "e92c17e795759007127c8a52783f29e7f2a8a0d438c3fc9fc1e5fa4af5dfe9e6",
    "files": {
        "tokenizer.json": {
            "bytes": 7_031_645,
            "sha256": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
        },
        "tokenizer_config.json": {
            "bytes": 7_305,
            "sha256": "5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583",
        },
    },
}
LORA_TARGET_MODULES = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)
CANONICAL_FULL_SHARED = {
    "training_method": "BF16 LoRA",
    "max_length": 512,
    "epochs": 1.0,
    "batch_size": 64,
    "gradient_accumulation": 1,
    "global_batch": 64,
    "warmup_ratio": 0.03,
    "weight_decay": 0.0,
    "seed": 3407,
    "logging_steps": 47,
    "checkpoint_schedule": "quarter_half_end",
    "completion_only_loss": True,
}
CANONICAL_COMPARISON_SHA256 = {
    "terminal_sha256": "361957972d7e0a508d562c4fb73847b66bae030296a571b4e1d6ba9afa54c483",
    "comparison_json_sha256": "f652519fea5773bdacb3595d52b8ffdee5a531f32a14e2eb2978444e9441f5a2",
    "comparison_csv_sha256": "89b08dcbc31ee20bf706e2e3cbc689a60cbf06272e29e235908241d21bffe7d2",
    "compiler_sha256": "fb29d71fe8d8e4cfcc9b3985440d363fd2b5f905dd57b3b15cdbd5b2752d3e3e",
    "frozen_roster_sha256": "8925c569ab66c86643d49c294909bc2b89d26d6b6375d6aa2f3691956e4eac4c",
}
CANONICAL_COMPARISON_INPUT_SHA256 = {
    "math_review": "06d7f2ac4cc3fbe71a421eefef6aebc4300d2af9e6ab4cc46b84bd1f3f08fc7f",
    "science_review": "2e9ebf479a1642f4e242ddcc21646851401c828793deaa437d22a0bbf21aa953",
    "mc_review": "7e3db8fce83cbd667cb88b0b5be5e011953bacce1754fed69435a7b12851a3c9",
    "judges_review": "dce56e8ed3a114550fb4045ed95e867b963d338c7601058501ddcdbdb75ad455",
    "stem": "6f6a435b6adab0b649abd3fa24830a5b3065e1b6cc2faedde8036f81e27da0f0",
    "judges": "41dfe7e940be8fe076dff362fe07c718eb5a1644e1b3752920cbdb96ca7515a6",
}
CANONICAL_EXPORT_TOOLCHAIN = {
    "merge_script_sha256": "ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be",
    "llama_cpp_git_commit": "60bccc3763395e01b039aa1ddeacc8cc0ea69f70",
    "converter_sha256": "8f1bed9466221e57e434caa7ee720abe1569deb6bc2fe5a65da950ea66c8e737",
    "quantizer_sha256": "fd6dcbb13f2c69c29b7038436fa514721cacedec6839748f776cb3fde12beca1",
}
CANONICAL_TRAINING_SOURCE_SHA256 = {
    "full_launcher_sha256": "27052215314f0d148f914367bc0177185616ee46e16c61a9c8ade1e2e81ce3ba",
    "trainer_sha256": "b39bdd3b64f0b787e614ac3c92ce8ac4f1bdc8d6cb5068172be4dca9b590f1d4",
    "campaign_io_sha256": "ded88829f91109eb6664d3cf177cde7a8c9665cab731204213ab33047b8fe121",
    "train_lora_sha256": "bfca938da9413ef61a12d4c46ee853d74ebf0c7af69749411e000f8c88e06637",
}
HARDENED_RESUME_VERIFICATION_SHA256 = (
    "4700e82e564dca0787904353c2f34580bdcf17983ace8b9636ce2f39db4ba28c"
)
HARDENED_RESUME_SHA256SUMS_SHA256 = (
    "54ab41d504fd266f5fd85791fbbf4725a484bf5222bbc84d0927516b1c8e68d0"
)
HARDENED_LINEAGE = {
    "clean": {
        "receipt_sha256": "e92c17e795759007127c8a52783f29e7f2a8a0d438c3fc9fc1e5fa4af5dfe9e6",
        "base_tree_sha256": "ae1baefcdac4c037b545696abffc1bd07824c109572163664333b5a5c0dda892",
        "training_manifest_sha256": "2f3e78d33f0f38869a1906d9ff1856146080fe79a7d1d7115d4864fa3dbb55b0",
        "resolved_config_sha256": "a6cab34c9d32147aa9e7b455fc242a4d1862590d283f3ed5c882074c61295bc4",
    },
    "warm": {
        "receipt_sha256": "27c21acb1425511f0cb013283a522afe69409aa25c91412946b040b89fc43354",
        "base_tree_sha256": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
        "training_manifest_sha256": "1a2bcb0b96db0672afc45b8e205f80468424058314eab8cec9b2c9533d37cfec",
        "resolved_config_sha256": "52e16c1802fff7d8e354ccc995ca6a9c62922619542466807fffa008be3b3b6e",
    },
}
CANONICAL_RUNTIME_INPUT_AUTHORITY = {
    "lineages": {
        lineage: {
            "lineage_receipt_sha256": authority["receipt_sha256"],
            "base_tree_sha256": authority["base_tree_sha256"],
        }
        for lineage, authority in HARDENED_LINEAGE.items()
    },
    "tokenizer": {
        "lineage_receipt_sha256": HARDENED_LINEAGE["clean"]["receipt_sha256"],
        "base_tree_sha256": HARDENED_LINEAGE["clean"]["base_tree_sha256"],
        "files": CANONICAL_TOKENIZER["files"],
    },
    "dataset": {
        "manifest_sha256": CANONICAL_DATA["manifest_sha256"],
        "fingerprint_sha256": CANONICAL_DATA["fingerprint_sha256"],
        "rows": CANONICAL_DATA["artifact_rows"],
    },
    "validation": {
        "manifest_sha256": CANONICAL_VALIDATION["manifest_sha256"],
        "fingerprint_sha256": CANONICAL_VALIDATION["fingerprint_sha256"],
        "rows": CANONICAL_VALIDATION["rows"],
    },
}
CANONICAL_PILOT_AUTHORITY = {
    "clean-r16-lr1e5": {
        "lineage": "clean",
        "rank": 16,
        "learning_rate": 1e-5,
        "best_dev_loss": 0.5932567119598389,
        "adapter_sha256": "c0b6d775e65abf3571bdb4407c1031c25756e2b73d1e81c7f3d0237049b22ad7",
        "training_manifest_sha256": "1bfa84d438c5e16ab9e5b7fdaeab617620ea7e8d7e95758f89821c92c3a9bc6b",
        "training_base_tree_sha256": "ae1baefcdac4c037b545696abffc1bd07824c109572163664333b5a5c0dda892",
        "quantization_manifest_sha256": "cfe9a05e4cb071283fc7a933926144f730310ea2a1f6a63f1de6c7b048982c77",
        "gguf_sha256": "c2d4c0ef8b27a6d0965bc20f7596c071ad595d146fb0e33d957108b93cc82280",
    },
    "clean-r32-lr1e5": {
        "lineage": "clean",
        "rank": 32,
        "learning_rate": 1e-5,
        "best_dev_loss": 0.3468289077281952,
        "adapter_sha256": "216be319ce7bd83728e692646d131c843f43f8e2372f95b534ba4d2126cd232f",
        "training_manifest_sha256": "67b9e47b5cdb8370e755e0d3d949b6306c900c6054727012cede60218b8bcd50",
        "training_base_tree_sha256": "ae1baefcdac4c037b545696abffc1bd07824c109572163664333b5a5c0dda892",
        "quantization_manifest_sha256": "83426e0c0595b9d63443b9347f1f4ad6990f207e247deb2b518c8fa0d6a2df0d",
        "gguf_sha256": "ce82fdf54bc46e737f92f90e6788b9d6f777eb3e94185d624d042763cdb533fb",
    },
    "warm-r8-lr5e6": {
        "lineage": "warm",
        "rank": 8,
        "learning_rate": 5e-6,
        "best_dev_loss": 1.151685357093811,
        "adapter_sha256": "8b91481fcf971f20e35141cdd53ae85b9b37cf13298fb3c5321ec91c5c8a18d8",
        "training_manifest_sha256": "d5f1be618c10899fdb4cda9e5c6c7c03e1830a2ff6983a5bb02f7411656d8536",
        "training_base_tree_sha256": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
        "quantization_manifest_sha256": "69967385299be020efbcda42137abf047aef6dfcd43500001329e60620637fff",
        "gguf_sha256": "10043c11e03496ca8dc1358779776e3143c64e127d28b6dfa46f9c6bb689049f",
    },
    "warm-r16-lr5e6": {
        "lineage": "warm",
        "rank": 16,
        "learning_rate": 5e-6,
        "best_dev_loss": 0.9617626667022705,
        "adapter_sha256": "4ec07d3668e9a772573c7f6553319760af00fb28cc1c8743a3c8fe5ce97a0aff",
        "training_manifest_sha256": "6ec33e9cbcba01c86d775977a35bf6f791f46ee110d167db1fb46c8815a3cb6c",
        "training_base_tree_sha256": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
        "quantization_manifest_sha256": "67077e17743327aacbade27f4c497b6fd214bcf22aa07c99a45e21b5e34edc69",
        "gguf_sha256": "ebb09067e78692168d4ee328498faebb2b662966c24c8f23d944b48a905ac62c",
    },
    "warm-r16-lr1e5": {
        "lineage": "warm",
        "rank": 16,
        "learning_rate": 1e-5,
        "best_dev_loss": 0.5780092477798462,
        "adapter_sha256": "eedae2da530769a2d2b261bcec6ac11006210c3b068f0ce592e0ad02e781d311",
        "training_manifest_sha256": "bf08259c64979360bce2e0f3f71c3508ce43e822eb5b4aea365e6ebefb02c098",
        "training_base_tree_sha256": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
        "quantization_manifest_sha256": "eba856d0139ecb58fe524da038a98feaaaa3c07459be8e11e804b8bbb9496295",
        "gguf_sha256": "262e95bc09ebd87d106d29a08d1b8ddff02708295411f73741d07cab25f6cc5e",
    },
    "warm-r16-lr2e5": {
        "lineage": "warm",
        "rank": 16,
        "learning_rate": 2e-5,
        "best_dev_loss": 0.2170596420764923,
        "adapter_sha256": "5f7fc5691fa3a95d7a730f3e601927aa338c958fa404bf122e7dcfe39bda81a7",
        "training_manifest_sha256": "2be2ae18ed644d61e83e8b4b7120d3af38c8d703662ee44235629e0b01a92a97",
        "training_base_tree_sha256": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
        "quantization_manifest_sha256": "309ce25491f0fe16d111b73c62d89f6f76afb21ada5c7f1ea44ec6d52b695f8b",
        "gguf_sha256": "94ccf1cf68c0637b3ffa3994a013f94828125a0540244e48bc61677b684860f4",
    },
    "warm-r32-lr5e6": {
        "lineage": "warm",
        "rank": 32,
        "learning_rate": 5e-6,
        "best_dev_loss": 0.6859107613563538,
        "adapter_sha256": "8745067225ab5d9152e38f3f31cb111e522ac1b59b0051017621744a8ad16982",
        "training_manifest_sha256": "13989fc96f226cdd99b7595a78ac48238b4972acace63be6e8fb5c12ea4316cc",
        "training_base_tree_sha256": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
        "quantization_manifest_sha256": "f8d58a499da64db8ebc1c900cdf3fadb53116b19466fb676fc366dc0290ef5cb",
        "gguf_sha256": "187d6bbb4d74df1428b25611b35898bb929f4c4257d893b5e7379455806ead2a",
    },
    "warm-r32-lr1e5": {
        "lineage": "warm",
        "rank": 32,
        "learning_rate": 1e-5,
        "best_dev_loss": 0.33982783555984497,
        "adapter_sha256": "fcf0c91fa5cd97ab7515c1a29e640eab7a93db4d63bb3750d2d6cadfa6121b6b",
        "training_manifest_sha256": "dbe76a802a6fe2401a2055e2727a963400ec224e681d8cd0c4c5bf91f404a4c1",
        "training_base_tree_sha256": "02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8",
        "quantization_manifest_sha256": "4c7ace52fc9d7b06694f8018383597d17c4a70d5c112c74422d9f83541d698c1",
        "gguf_sha256": "c472ce88ccf74d1973a46f5d3d0204244fcf31926e160da6c218bd641312a2d8",
    },
}


def milestone_steps(total_steps: int) -> list[int]:
    """Return exact quarter, half, and final optimizer-step milestones."""
    if total_steps < 1:
        raise PilotResultError("total steps must be positive")
    return sorted({math.ceil(total_steps / 4), math.ceil(total_steps / 2), total_steps})


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PilotResultError(f"JSON root is not an object: {path}")
    return value


def _selected_result(
    results: dict[str, Any], *, candidate_id: str, expected_lineage: str
) -> dict[str, Any]:
    matches = [row for row in results.get("rows", []) if row.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        raise PilotResultError(f"selected pilot is missing or ambiguous: {candidate_id}")
    row = matches[0]
    if row.get("status") != "complete":
        raise PilotResultError(f"selected pilot is not complete: {candidate_id}")
    if row.get("lineage") != expected_lineage:
        raise PilotResultError(
            f"selected {expected_lineage} pilot has {row.get('lineage')!r} lineage"
        )
    for field in ("best_dev_loss", "train_loss", "adapter_sha256"):
        if row.get(field) in (None, ""):
            raise PilotResultError(f"selected pilot lacks {field}: {candidate_id}")
    return row


def _verify_file(path: Path, receipt: dict[str, Any]) -> None:
    if not path.is_file():
        raise PilotResultError(f"evaluation artifact is missing: {path}")
    if path.stat().st_size != receipt.get("bytes") or sha256_file(path) != receipt.get("sha256"):
        raise PilotResultError(f"evaluation artifact receipt mismatch: {path}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PilotResultError(
                        f"evaluation response {line_number} is not an object: {path}"
                    )
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"cannot read evaluation responses: {path}") from exc
    return rows


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _finite_nonnegative_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PilotResultError(f"{label} must be a finite numeric value")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise PilotResultError(f"{label} must be a finite non-negative value")
    return number


_SAFETENSORS_DTYPE_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
    "U16": 2,
    "I16": 2,
    "F16": 2,
    "BF16": 2,
    "U32": 4,
    "I32": 4,
    "F32": 4,
    "U64": 8,
    "I64": 8,
    "F64": 8,
}


def _qwen25_rank16_lora_shapes() -> dict[str, list[int]]:
    shapes: dict[str, list[int]] = {}
    projections = {
        "q_proj": ("self_attn", 1_536),
        "k_proj": ("self_attn", 256),
        "v_proj": ("self_attn", 256),
        "o_proj": ("self_attn", 1_536),
        "gate_proj": ("mlp", 8_960),
        "up_proj": ("mlp", 8_960),
        "down_proj": ("mlp", 1_536),
    }
    for layer in range(28):
        prefix = f"base_model.model.model.layers.{layer}"
        for projection, (component, output_width) in projections.items():
            input_width = 8_960 if projection == "down_proj" else 1_536
            tensor_prefix = f"{prefix}.{component}.{projection}"
            shapes[f"{tensor_prefix}.lora_A.weight"] = [16, input_width]
            shapes[f"{tensor_prefix}.lora_B.weight"] = [output_width, 16]
    return shapes


QWEN25_RANK16_LORA_SHAPES = _qwen25_rank16_lora_shapes()
QWEN25_RANK16_LORA_ELEMENTS = sum(math.prod(shape) for shape in QWEN25_RANK16_LORA_SHAPES.values())


def _verify_safetensors(path: Path, *, require_qwen25_rank16_lora: bool = False) -> dict[str, Any]:
    """Parse the safe, JSON-header portion and prove the payload layout is coherent."""
    if not path.is_file() or path.is_symlink():
        raise PilotResultError(f"safetensors artifact is missing or a symlink: {path}")
    size = path.stat().st_size
    if size < 11:
        raise PilotResultError(f"safetensors artifact is too small: {path}")
    try:
        with path.open("rb") as handle:
            prefix = handle.read(8)
            if len(prefix) != 8:
                raise PilotResultError(f"safetensors header is truncated: {path}")
            (header_bytes,) = struct.unpack("<Q", prefix)
            if header_bytes < 2 or header_bytes > size - 8:
                raise PilotResultError(f"safetensors header length is invalid: {path}")
            raw_header = handle.read(header_bytes)
        header = json.loads(raw_header.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, struct.error) as exc:
        raise PilotResultError(f"cannot parse safetensors header: {path}") from exc
    if not isinstance(header, dict):
        raise PilotResultError(f"safetensors header is not an object: {path}")
    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items()
    ):
        raise PilotResultError(f"safetensors metadata is invalid: {path}")
    tensors = [(name, value) for name, value in header.items() if name != "__metadata__"]
    if not tensors:
        raise PilotResultError(f"safetensors artifact has no tensors: {path}")
    if require_qwen25_rank16_lora:
        observed_shapes = {
            name: tensor.get("shape") if isinstance(tensor, dict) else None
            for name, tensor in tensors
        }
        observed_dtypes = {
            tensor.get("dtype") for _name, tensor in tensors if isinstance(tensor, dict)
        }
        if (
            observed_shapes != QWEN25_RANK16_LORA_SHAPES
            or len(observed_dtypes) != 1
            or not observed_dtypes.issubset({"F32", "BF16"})
        ):
            raise PilotResultError(
                f"safetensors is not the exact Qwen2.5-1.5B rank-16 LoRA signature: {path}"
            )
    payload_bytes = size - 8 - header_bytes
    ranges: list[tuple[int, int]] = []
    for name, tensor in tensors:
        if not isinstance(name, str) or not name or not isinstance(tensor, dict):
            raise PilotResultError(f"safetensors tensor entry is invalid: {path}")
        dtype = tensor.get("dtype")
        shape = tensor.get("shape")
        offsets = tensor.get("data_offsets")
        if (
            dtype not in _SAFETENSORS_DTYPE_BYTES
            or not isinstance(shape, list)
            or any(
                isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1
                for dimension in shape
            )
            or not isinstance(offsets, list)
            or len(offsets) != 2
            or any(isinstance(offset, bool) or not isinstance(offset, int) for offset in offsets)
        ):
            raise PilotResultError(f"safetensors tensor metadata is invalid: {path}")
        start, end = offsets
        elements = math.prod(shape)
        if start < 0 or end < start or end > payload_bytes:
            raise PilotResultError(f"safetensors tensor offsets are invalid: {path}")
        if end - start != elements * _SAFETENSORS_DTYPE_BYTES[dtype]:
            raise PilotResultError(f"safetensors tensor byte count is invalid: {path}")
        ranges.append((start, end))
    expected_start = 0
    for start, end in sorted(ranges):
        if start != expected_start:
            raise PilotResultError(f"safetensors payload is sparse or overlapping: {path}")
        expected_start = end
    if expected_start != payload_bytes:
        raise PilotResultError(f"safetensors payload has unclaimed bytes: {path}")
    return {
        "bytes": size,
        "sha256": sha256_file(path),
        "header_bytes": header_bytes,
        "tensor_count": len(tensors),
        "dtype": next(iter({tensor["dtype"] for _name, tensor in tensors})),
        "element_count": sum(math.prod(tensor["shape"]) for _name, tensor in tensors),
    }


def _verify_adapter_config(path: Path) -> dict[str, Any]:
    config = _read_object(path)
    expected_targets = set(LORA_TARGET_MODULES)
    target_modules = config.get("target_modules")
    if (
        config.get("peft_type") != "LORA"
        or config.get("task_type") != "CAUSAL_LM"
        or isinstance(config.get("r"), bool)
        or not isinstance(config.get("r"), int)
        or config["r"] != 16
        or isinstance(config.get("lora_alpha"), bool)
        or not isinstance(config.get("lora_alpha"), int)
        or config["lora_alpha"] != 16
        or not isinstance(target_modules, list)
        or any(not isinstance(module, str) for module in target_modules)
        or len(target_modules) != len(expected_targets)
        or set(target_modules) != expected_targets
    ):
        raise PilotResultError(f"adapter config is not a complete causal-LM LoRA config: {path}")
    # PEFT stores this set as a JSON list whose order may vary after process
    # restart. Normalize only the validated set for semantic comparisons; keep
    # original files untouched so byte hashes and inventories remain exact.
    return {**config, "target_modules": sorted(target_modules)}


def _verify_tokenizer_receipt(receipt: Any) -> None:
    if (
        not isinstance(receipt, dict)
        or receipt.get("lineage_receipt_sha256") != (CANONICAL_TOKENIZER["lineage_receipt_sha256"])
    ):
        raise PilotResultError("promotion smoke tokenizer lineage changed")
    files = receipt.get("files")
    if not isinstance(files, dict) or set(files) != set(CANONICAL_TOKENIZER["files"]):
        raise PilotResultError("promotion smoke tokenizer file set changed")
    for name, authority in CANONICAL_TOKENIZER["files"].items():
        observed = files[name]
        if (
            not isinstance(observed, dict)
            or observed.get("bytes") != authority["bytes"]
            or observed.get("sha256") != authority["sha256"]
            or not isinstance(observed.get("path"), str)
            or not observed["path"]
        ):
            raise PilotResultError(f"promotion smoke tokenizer receipt changed: {name}")


def _verify_loss_curve_files(*, png_path: Path, svg_path: Path) -> dict[str, Any]:
    try:
        png = png_path.read_bytes()
        svg = svg_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PilotResultError("cannot read promotion smoke loss curves") from exc
    if len(png) < 45 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PilotResultError("promotion smoke loss-curve PNG is invalid")
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(png):
        if offset + 12 > len(png):
            raise PilotResultError("promotion smoke loss-curve PNG is truncated")
        chunk_bytes = int.from_bytes(png[offset : offset + 4], "big")
        chunk_type = png[offset + 4 : offset + 8]
        end = offset + 12 + chunk_bytes
        if end > len(png):
            raise PilotResultError("promotion smoke loss-curve PNG chunk is truncated")
        chunk_data = png[offset + 8 : offset + 8 + chunk_bytes]
        expected_crc = int.from_bytes(png[offset + 8 + chunk_bytes : end], "big")
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            raise PilotResultError("promotion smoke loss-curve PNG has an invalid CRC")
        chunks.append((chunk_type, chunk_data))
        offset = end
        if chunk_type == b"IEND":
            break
    png_width = int.from_bytes(chunks[0][1][:4], "big") if chunks else 0
    png_height = int.from_bytes(chunks[0][1][4:8], "big") if chunks else 0
    if (
        offset != len(png)
        or not chunks
        or chunks[0][0] != b"IHDR"
        or len(chunks[0][1]) != 13
        or (png_width, png_height) != (1_440, 900)
        or chunks[0][1][8:10] != b"\x08\x06"
        or not any(chunk_type == b"IDAT" for chunk_type, _data in chunks)
        or chunks[-1] != (b"IEND", b"")
    ):
        raise PilotResultError("promotion smoke loss-curve PNG structure is invalid")
    try:
        svg_root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise PilotResultError("promotion smoke loss-curve SVG is invalid") from exc
    elements = list(svg_root.iter())
    element_names = [element.tag.rsplit("}", 1)[-1] for element in elements]
    element_ids = {
        element.attrib["id"] for element in elements if isinstance(element.attrib.get("id"), str)
    }
    line_ids = {identifier for identifier in element_ids if identifier.startswith("line2d_")}
    if (
        len(svg.encode("utf-8")) < 10_000
        or not svg_root.tag.endswith("svg")
        or svg_root.attrib.get("width") != "576pt"
        or svg_root.attrib.get("height") != "360pt"
        or svg_root.attrib.get("viewBox") != "0 0 576 360"
        or element_names.count("path") < 20
        or element_names.count("g") < 50
        or element_names.count("use") < 20
        or len(line_ids) < 20
        or not {"axes_1", "legend_1"}.issubset(element_ids)
    ):
        raise PilotResultError("promotion smoke loss-curve SVG is invalid")
    return {
        "png_width": png_width,
        "png_height": png_height,
        "svg_bytes": len(svg.encode("utf-8")),
        "svg_path_count": element_names.count("path"),
        "svg_line_id_count": len(line_ids),
        "svg_axes_id": "axes_1",
        "svg_legend_id": "legend_1",
    }


def _svg_series_paths(svg_bytes: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as exc:
        raise PilotResultError("cannot parse loss-curve SVG series") from exc
    series: dict[str, str] = {}
    for element in root.iter():
        if not element.tag.endswith("path") or "clip-path" not in element.attrib:
            continue
        style = element.attrib.get("style", "")
        for label, color in (("train", "#1f77b4"), ("validation", "#ff7f0e")):
            if f"stroke: {color}" in style and isinstance(element.attrib.get("d"), str):
                if label in series:
                    raise PilotResultError(f"loss-curve SVG has duplicate {label} data paths")
                series[label] = element.attrib["d"]
    if set(series) != {"train", "validation"}:
        raise PilotResultError("loss-curve SVG lacks the two plotted data series")
    return series


def _verify_loss_curve_rendering(
    *,
    png_path: Path,
    svg_path: Path,
    train_rows: list[dict[str, Any]],
    evaluation_rows: list[dict[str, Any]],
    expected_matplotlib_version: str,
    portable: bool = False,
) -> dict[str, str]:
    """Re-render the frozen plotting code and compare decoded pixels and SVG series geometry."""
    if portable:
        from round2_promotion_v3 import verify_portable_loss_series

        return verify_portable_loss_series(
            png_path, svg_path, train_rows, evaluation_rows, expected_matplotlib_version
        )
    try:
        import matplotlib

        if matplotlib.__version__ != expected_matplotlib_version:
            raise PilotResultError(
                "promotion verifier Matplotlib differs from the smoke environment"
            )
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from PIL import Image
    except (ImportError, RuntimeError) as exc:
        raise PilotResultError("cannot load the frozen loss-curve renderer") from exc

    train = [(row["step"], row["loss"]) for row in train_rows]
    evaluation = [(row["step"], row["eval_loss"]) for row in evaluation_rows]
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.plot(*zip(*train, strict=True), label="train", linewidth=1.5)
    axis.plot(*zip(*evaluation, strict=True), label="validation", marker="o")
    axis.set(xlabel="optimizer step", ylabel="loss", title="Muta fine-tuning loss")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    expected_png = io.BytesIO()
    expected_svg = io.BytesIO()
    figure.savefig(expected_png, format="png", dpi=180)
    figure.savefig(expected_svg, format="svg")
    plt.close(figure)
    expected_png.seek(0)
    try:
        with Image.open(png_path) as observed_image, Image.open(expected_png) as expected_image:
            observed_image.load()
            expected_image.load()
            if (
                observed_image.mode != expected_image.mode
                or observed_image.size != expected_image.size
                or observed_image.tobytes() != expected_image.tobytes()
            ):
                raise PilotResultError(
                    "promotion smoke loss-curve pixels do not render the recorded metrics"
                )
            pixel_bytes = observed_image.tobytes()
    except OSError as exc:
        raise PilotResultError("cannot decode promotion smoke loss-curve PNG") from exc
    observed_series = _svg_series_paths(svg_path.read_bytes())
    expected_series = _svg_series_paths(expected_svg.getvalue())
    if observed_series != expected_series:
        raise PilotResultError(
            "promotion smoke SVG series geometry does not render the recorded metrics"
        )
    return {
        "png_pixel_sha256": hashlib.sha256(pixel_bytes).hexdigest(),
        "svg_series_sha256": hashlib.sha256(
            json.dumps(observed_series, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _verify_canonical_pilot_authority(
    *,
    pilot_config_path: Path,
    pilot_results_path: Path,
    compiler_receipt_path: Path,
    pilot_config: dict[str, Any],
    pilot_results: dict[str, Any],
) -> None:
    """Join mutable working paths to the campaign's retained immutable receipts."""
    expected_files = {
        pilot_config_path: CANONICAL_PILOT_CONFIG_SHA256,
        pilot_results_path: CANONICAL_PILOT_RESULTS_SHA256,
        compiler_receipt_path: CANONICAL_PILOT_COMPILER_RECEIPT_SHA256,
    }
    for path, expected_sha in expected_files.items():
        if sha256_file(path) != expected_sha:
            raise PilotResultError(f"canonical pilot authority changed: {path.name}")
    if pilot_config.get("dataset") != {
        "rows": CANONICAL_DATA["artifact_rows"],
        "fingerprint_sha256": CANONICAL_DATA["fingerprint_sha256"],
        "pilot_rows": 20_000,
        "private_policy": "include",
    } or pilot_config.get("validation") != {
        "rows": CANONICAL_VALIDATION["rows"],
        "fingerprint_sha256": CANONICAL_VALIDATION["fingerprint_sha256"],
    }:
        raise PilotResultError("canonical pilot dataset/validation authority changed")
    configured = {candidate.get("id"): candidate for candidate in pilot_config["candidates"]}
    results = {row.get("candidate_id"): row for row in pilot_results.get("rows", [])}
    if set(configured) != set(CANONICAL_PILOT_AUTHORITY) or set(results) != set(
        CANONICAL_PILOT_AUTHORITY
    ):
        raise PilotResultError("canonical pilot authority roster changed")
    for pilot_id, authority in CANONICAL_PILOT_AUTHORITY.items():
        treatment = configured[pilot_id]
        result = results[pilot_id]
        for field in ("lineage", "rank", "learning_rate"):
            if treatment.get(field) != authority[field] or result.get(field) != authority[field]:
                raise PilotResultError(f"canonical pilot treatment changed: {pilot_id}/{field}")
        for result_field, authority_field in (
            ("best_dev_loss", "best_dev_loss"),
            ("adapter_sha256", "adapter_sha256"),
            ("training_manifest_sha256", "training_manifest_sha256"),
            ("training_base_tree_sha256", "training_base_tree_sha256"),
        ):
            if result.get(result_field) != authority[authority_field]:
                raise PilotResultError(
                    f"canonical pilot compiled result changed: {pilot_id}/{result_field}"
                )


def _load_comparison_compiler():
    """Load the retained comparison compiler without invoking its CLI."""
    repo = Path(__file__).resolve().parents[2]
    compiler_path = repo / "bench" / "round2_comparison_report.py"
    module_name = "_muta_round2_comparison_report_for_promotion"
    spec = importlib.util.spec_from_file_location(module_name, compiler_path)
    if spec is None or spec.loader is None:
        raise PilotResultError("cannot load the canonical comparison compiler")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    added_repo = str(repo) not in sys.path
    if added_repo:
        sys.path.insert(0, str(repo))
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PilotResultError("cannot import the canonical comparison compiler") from exc
    finally:
        if added_repo:
            sys.path.remove(str(repo))
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
    return module, compiler_path


def _comparison_input_path(payload: dict[str, Any], name: str) -> Path:
    receipt = payload.get("inputs", {}).get(name)
    if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
        raise PilotResultError(f"canonical comparison lacks input receipt: {name}")
    path = Path(receipt["path"]).resolve()
    if not path.exists() and "provenance" in path.parts:
        # A copied, immutable evidence tree may live on a different host. Only
        # relocate the known repository-relative suffix; still require exact bytes.
        suffix = Path(*path.parts[path.parts.index("provenance") :])
        path = Path(__file__).resolve().parents[2] / suffix
    if not path.is_file() or path.is_symlink() or sha256_file(path) != receipt.get("sha256"):
        raise PilotResultError(f"canonical comparison input changed: {name}")
    return path


def verify_canonical_gguf_semantic_evidence(
    comparison_dir: Path,
    *,
    pilot_config: dict[str, Any],
) -> dict[str, Any]:
    """Re-run the retained compiler's validators against its immutable outputs."""
    root = comparison_dir.resolve()
    if not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
        raise PilotResultError("canonical comparison directory is missing or contains a symlink")
    terminal_path = root / "COMPLETED.json"
    json_path = root / "comparison.json"
    csv_path = root / "comparison.csv"
    terminal = _read_object(terminal_path)
    terminal_files = terminal.get("files")
    if (
        terminal.get("status") != "complete"
        or not isinstance(terminal_files, dict)
        or set(terminal_files) != {"comparison.csv", "comparison.json"}
    ):
        raise PilotResultError("canonical comparison terminal receipt is invalid")
    for path in (json_path, csv_path):
        if terminal_files.get(path.name) != sha256_file(path):
            raise PilotResultError(f"canonical comparison terminal hash mismatch: {path.name}")

    payload = _read_object(json_path)
    compiler, compiler_path = _load_comparison_compiler()
    compiler_sha = sha256_file(compiler_path)
    if payload.get("compiler_sha256") != compiler_sha:
        raise PilotResultError("canonical comparison compiler binding changed")
    if payload.get("comparison_csv_sha256") != sha256_file(csv_path):
        raise PilotResultError("canonical comparison CSV binding changed")
    if payload.get("review_type") != "agent_semantic_review_not_official_grading":
        raise PilotResultError("canonical comparison review type changed")
    observed_comparison_authority = {
        "terminal_sha256": sha256_file(terminal_path),
        "comparison_json_sha256": sha256_file(json_path),
        "comparison_csv_sha256": sha256_file(csv_path),
        "compiler_sha256": compiler_sha,
        "frozen_roster_sha256": sha256_file(Path(compiler.FROZEN_ROSTER)),
    }
    if observed_comparison_authority != CANONICAL_COMPARISON_SHA256:
        raise PilotResultError("canonical comparison no longer matches retained authority")

    repo = Path(__file__).resolve().parents[2]
    expected_sources = compiler.REVIEW_SOURCE_SHA256
    retained_sources = payload.get("review_sources")
    if not isinstance(retained_sources, dict) or set(retained_sources) != set(expected_sources):
        raise PilotResultError("canonical comparison review-source set changed")
    for relative, expected_sha in expected_sources.items():
        path = repo / relative
        receipt = retained_sources[relative]
        if (
            not path.is_file()
            or path.is_symlink()
            or sha256_file(path) != expected_sha
            or receipt
            != {
                "bytes": path.stat().st_size,
                "sha256": expected_sha,
            }
        ):
            raise PilotResultError(f"canonical comparison review source changed: {relative}")

    expected_input_names = {
        "math_review",
        "science_review",
        "mc_review",
        "judges_review",
        "stem",
        "judges",
    }
    retained_inputs = payload.get("inputs")
    if not isinstance(retained_inputs, dict) or set(retained_inputs) != expected_input_names:
        raise PilotResultError("canonical comparison input set changed")
    input_paths = {
        name: _comparison_input_path(payload, name) for name in sorted(expected_input_names)
    }
    if {
        name: payload["inputs"][name]["sha256"] for name in sorted(expected_input_names)
    } != CANONICAL_COMPARISON_INPUT_SHA256:
        raise PilotResultError("canonical comparison input hashes changed")
    if input_paths["stem"].name != "COMPLETED.json" or input_paths["judges"].name != (
        "COMPLETED.json"
    ):
        raise PilotResultError("canonical comparison run receipt path changed")

    try:
        stem_run, stem = compiler.sealed_run(input_paths["stem"].parent, "stem")
        judges_run, judges = compiler.sealed_run(input_paths["judges"].parent, "judges")
        comparable = lambda run: {
            key: value for key, value in run["settings"].items() if key != "gguf_port"
        }
        compiler.require(
            comparable(stem_run) == comparable(judges_run),
            "suite decoding settings differ",
        )
        compiler.require(
            {candidate: row["model_sha256"] for (candidate, _), row in stem.items()}
            == {candidate: row["model_sha256"] for (candidate, _), row in judges.items()},
            "suite models differ",
        )
        compiler.require(
            {row["server_sha256"] for row in stem.values()}
            == {row["server_sha256"] for row in judges.values()},
            "suite servers differ",
        )
        written_fields = ("core_correct", "instruction_complete")
        math_review = compiler.ledger(
            input_paths["math_review"],
            stem,
            {f"M{number:02}" for number in range(26, 51)},
            written_fields,
        )
        science_review = compiler.ledger(
            input_paths["science_review"],
            stem,
            {f"S{number:02}" for number in range(26, 51)},
            written_fields,
        )
        mc_review = compiler.ledger(
            input_paths["mc_review"],
            stem,
            {f"{subject}{number:02}" for subject in "MS" for number in range(1, 26)},
            (
                "parser_correct",
                "semantic_choice_correct",
                "explanation_correct",
                "format_compliant",
                "contradictory",
            ),
        )
        judges_review = compiler.ledger(
            input_paths["judges_review"],
            judges,
            {prompt.id for prompt in compiler.prompt_suite("judges")},
            (),
        )
        recomputed_rows = compiler.aggregate(
            stem,
            judges,
            math_review | science_review,
            mc_review,
            judges_review,
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PilotResultError(f"canonical comparison revalidation failed: {exc}") from exc
    if payload.get("rows") != recomputed_rows:
        raise PilotResultError("canonical comparison rows do not match recomputation")

    expected_pilot_ids = {candidate["id"] for candidate in pilot_config["candidates"]}
    candidate_id_map = {
        pilot_id: f"{CANONICAL_GGUF_PREFIX}{pilot_id}{CANONICAL_GGUF_SUFFIX}"
        for pilot_id in expected_pilot_ids
    }
    expected_comparison_ids = {"incumbent-muta", *candidate_id_map.values()}
    comparison_ids = [row.get("candidate_id") for row in recomputed_rows]
    if len(comparison_ids) != len(set(comparison_ids)) or set(comparison_ids) != (
        expected_comparison_ids
    ):
        raise PilotResultError("canonical comparison does not contain the exact pilot roster")
    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            csv_rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise PilotResultError("cannot read canonical comparison CSV") from exc
    expected_csv_rows = [
        {key: "" if value is None else str(value) for key, value in row.items()}
        for row in recomputed_rows
    ]
    if csv_rows != expected_csv_rows:
        raise PilotResultError("canonical comparison CSV differs from recomputed rows")

    frozen_roster_path = Path(compiler.FROZEN_ROSTER).resolve()
    frozen_roster = _read_object(frozen_roster_path)
    frozen_roster_candidates = {
        candidate["id"]: candidate for candidate in frozen_roster.get("candidates", [])
    }
    if set(frozen_roster_candidates) != expected_comparison_ids:
        raise PilotResultError("canonical frozen roster candidate set changed")
    quantization_manifests = {
        pilot_id: frozen_roster_candidates[comparison_id]
        .get("metadata", {})
        .get("quantization_manifest_sha256")
        for pilot_id, comparison_id in candidate_id_map.items()
    }
    if not all(_is_sha256(value) for value in quantization_manifests.values()):
        raise PilotResultError("canonical frozen roster lacks quantization-manifest hashes")

    model_sha256_by_id = {
        candidate: next(
            row["model_sha256"] for (current, _), row in stem.items() if current == candidate
        )
        for candidate in expected_comparison_ids
    }
    rows_by_id = {row["candidate_id"]: row for row in recomputed_rows}
    return {
        "path": str(root),
        "terminal_sha256": sha256_file(terminal_path),
        "comparison_json_sha256": sha256_file(json_path),
        "comparison_csv_sha256": sha256_file(csv_path),
        "compiler_path": str(compiler_path.resolve()),
        "compiler_sha256": compiler_sha,
        "frozen_roster_path": str(frozen_roster_path),
        "frozen_roster_sha256": sha256_file(frozen_roster_path),
        "inputs": retained_inputs,
        "review_sources": retained_sources,
        "evaluated_pilot_ids": sorted(expected_pilot_ids),
        "evaluated_control_ids": ["incumbent-muta"],
        "candidate_id_map": dict(sorted(candidate_id_map.items())),
        "model_sha256_by_id": dict(sorted(model_sha256_by_id.items())),
        "quantization_manifest_sha256_by_pilot_id": dict(sorted(quantization_manifests.items())),
        "rows_by_pilot_id": {
            pilot_id: rows_by_id[comparison_id]
            for pilot_id, comparison_id in sorted(candidate_id_map.items())
        },
    }


def verify_export_manifests(
    export_root: Path,
    *,
    pilot_config: dict[str, Any],
    pilot_results: dict[str, Any],
    comparison_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Bind every evaluated GGUF through its adapter and parent training tree."""
    root = export_root.resolve()
    if not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
        raise PilotResultError("GGUF export root is missing or contains a symlink")
    configured_ids = {candidate["id"] for candidate in pilot_config["candidates"]}
    results_by_id = {row.get("candidate_id"): row for row in pilot_results.get("rows", [])}
    if set(results_by_id) != configured_ids or len(results_by_id) != len(
        pilot_results.get("rows", [])
    ):
        raise PilotResultError("pilot results cannot be indexed for export verification")
    id_map = comparison_receipt.get("candidate_id_map", {})
    model_hashes = comparison_receipt.get("model_sha256_by_id", {})
    expected_manifest_hashes = comparison_receipt.get(
        "quantization_manifest_sha256_by_pilot_id", {}
    )
    if set(id_map) != configured_ids or set(expected_manifest_hashes) != configured_ids:
        raise PilotResultError("comparison/export pilot roster differs")
    if configured_ids != set(CANONICAL_PILOT_AUTHORITY):
        raise PilotResultError("export verification is not using the canonical pilot roster")

    receipts: dict[str, dict[str, Any]] = {}
    script_hashes: set[str] = set()
    llama_commits: set[str] = set()
    converter_hashes: set[str] = set()
    quantizer_hashes: set[str] = set()
    final_gguf_hashes: set[str] = set()
    for pilot_id in sorted(configured_ids):
        manifest_path = root / f"pilot-{pilot_id}" / "quantization-manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise PilotResultError(f"missing quantization manifest: {pilot_id}")
        manifest = _read_object(manifest_path)
        result = results_by_id[pilot_id]
        adapter = manifest.get("inputs", {}).get("adapter")
        base = manifest.get("inputs", {}).get("base")
        training_manifest = manifest.get("inputs", {}).get("training_manifest")
        final_gguf = manifest.get("final_gguf")
        comparison_id = id_map[pilot_id]
        authority = CANONICAL_PILOT_AUTHORITY[pilot_id]
        if manifest.get("schema_version") != 1 or manifest.get("quantization") != "Q4_K_M":
            raise PilotResultError(f"invalid quantization manifest header: {pilot_id}")
        if not all(
            isinstance(value, dict) for value in (adapter, base, training_manifest, final_gguf)
        ):
            raise PilotResultError(f"incomplete quantization manifest inputs: {pilot_id}")
        if adapter.get("tree_sha256") != result.get("adapter_sha256"):
            raise PilotResultError(f"export adapter does not match pilot result: {pilot_id}")
        if base.get("tree_sha256") != result.get("training_base_tree_sha256"):
            raise PilotResultError(f"export base does not match pilot result: {pilot_id}")
        if training_manifest.get("sha256") != result.get("training_manifest_sha256"):
            raise PilotResultError(
                f"export training manifest does not match pilot result: {pilot_id}"
            )
        if (
            adapter.get("tree_sha256") != authority["adapter_sha256"]
            or base.get("tree_sha256") != authority["training_base_tree_sha256"]
            or training_manifest.get("sha256") != authority["training_manifest_sha256"]
            or expected_manifest_hashes[pilot_id] != authority["quantization_manifest_sha256"]
            or model_hashes.get(comparison_id) != authority["gguf_sha256"]
        ):
            raise PilotResultError(f"export differs from retained pilot authority: {pilot_id}")
        if (
            final_gguf.get("sha256") != model_hashes.get(comparison_id)
            or not isinstance(final_gguf.get("bytes"), int)
            or final_gguf["bytes"] < 1
        ):
            raise PilotResultError(f"export GGUF does not match evaluated model: {pilot_id}")
        for section_name, section in (
            ("adapter", adapter),
            ("base", base),
        ):
            if (
                not isinstance(section.get("bytes"), int)
                or section["bytes"] < 1
                or not isinstance(section.get("file_count"), int)
                or section["file_count"] < 1
            ):
                raise PilotResultError(f"invalid export {section_name} receipt: {pilot_id}")
        if not _is_sha256(manifest.get("script", {}).get("sha256")) or not re.fullmatch(
            r"[0-9a-f]{40}", str(manifest.get("llama_cpp", {}).get("git_commit", ""))
        ):
            raise PilotResultError(f"export toolchain receipt is incomplete: {pilot_id}")
        script_sha = manifest["script"]["sha256"]
        llama_commit = manifest["llama_cpp"]["git_commit"]
        converter_sha = manifest.get("llama_cpp", {}).get("converter", {}).get("sha256")
        quantizer_sha = manifest.get("llama_cpp", {}).get("quantizer", {}).get("sha256")
        if not _is_sha256(converter_sha) or not _is_sha256(quantizer_sha):
            raise PilotResultError(f"export converter/quantizer receipt is invalid: {pilot_id}")
        manifest_sha = sha256_file(manifest_path)
        if manifest_sha != expected_manifest_hashes[pilot_id]:
            raise PilotResultError(f"export manifest differs from frozen roster: {pilot_id}")
        script_hashes.add(script_sha)
        llama_commits.add(llama_commit)
        converter_hashes.add(converter_sha)
        quantizer_hashes.add(quantizer_sha)
        final_gguf_hashes.add(final_gguf["sha256"])
        receipts[pilot_id] = {
            "path": str(manifest_path.resolve()),
            "bytes": manifest_path.stat().st_size,
            "sha256": manifest_sha,
            "comparison_candidate_id": comparison_id,
            "adapter_tree_sha256": adapter["tree_sha256"],
            "base_tree_sha256": base["tree_sha256"],
            "training_manifest_sha256": training_manifest["sha256"],
            "gguf_bytes": final_gguf["bytes"],
            "gguf_sha256": final_gguf["sha256"],
            "quantization": "Q4_K_M",
            "merge_script_sha256": script_sha,
            "llama_cpp_git_commit": llama_commit,
            "converter_sha256": converter_sha,
            "quantizer_sha256": quantizer_sha,
        }
    if any(
        len(values) != 1
        for values in (script_hashes, llama_commits, converter_hashes, quantizer_hashes)
    ):
        raise PilotResultError("evaluated exports do not share one exact export toolchain")
    observed_toolchain = {
        "merge_script_sha256": next(iter(script_hashes)),
        "llama_cpp_git_commit": next(iter(llama_commits)),
        "converter_sha256": next(iter(converter_hashes)),
        "quantizer_sha256": next(iter(quantizer_hashes)),
    }
    if observed_toolchain != CANONICAL_EXPORT_TOOLCHAIN:
        raise PilotResultError("evaluated export toolchain differs from retained authority")
    if len(final_gguf_hashes) != len(configured_ids):
        raise PilotResultError("evaluated exports do not have unique GGUF identities")
    return {
        "root": str(root),
        "count": len(receipts),
        "toolchain": observed_toolchain,
        "pilots": receipts,
    }


def verify_hardened_resume_evidence(
    verification_path: Path,
    *,
    pilot_config: dict[str, Any],
) -> dict[str, Any]:
    """Validate the retained real interruption/resume proof and its file receipts."""
    if verification_path.is_symlink():
        raise PilotResultError("hardened resume verification cannot be a symlink")
    path = verification_path.resolve()
    if sha256_file(path) != HARDENED_RESUME_VERIFICATION_SHA256:
        raise PilotResultError("hardened resume verification differs from retained authority")
    verification = _read_object(path)
    script_dir = Path(__file__).resolve().parent
    script_hashes = {
        "train_lora_round2.py": sha256_file(script_dir / "train_lora_round2.py"),
        "campaign_io.py": sha256_file(script_dir / "campaign_io.py"),
        "train_lora.py": sha256_file(script_dir / "train_lora.py"),
    }
    expected_script_hashes = {
        "train_lora_round2.py": CANONICAL_TRAINING_SOURCE_SHA256["trainer_sha256"],
        "campaign_io.py": CANONICAL_TRAINING_SOURCE_SHA256["campaign_io_sha256"],
        "train_lora.py": CANONICAL_TRAINING_SOURCE_SHA256["train_lora_sha256"],
    }
    if script_hashes != expected_script_hashes:
        raise PilotResultError("hardened resume training source authority changed")
    trainer_sha = script_hashes["train_lora_round2.py"]
    if verification.get("schema_version") != 1 or verification.get("result") != "pass":
        raise PilotResultError("hardened resume verification is not a schema-v1 pass")
    repository = verification.get("repository", {})
    if (
        repository.get("train_lora_round2_sha256") != trainer_sha
        or repository.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40}", str(repository.get("commit", "")))
    ):
        raise PilotResultError("hardened resume evidence used a different or dirty trainer")
    inputs = verification.get("inputs", {})
    expected_inputs = {
        "clean_lineage_sha256": HARDENED_LINEAGE["clean"]["receipt_sha256"],
        "dev_fingerprint": CANONICAL_VALIDATION["fingerprint_sha256"],
        "dev_manifest_sha256": CANONICAL_VALIDATION["manifest_sha256"],
        "private_policy": "exclude",
        "train_fingerprint": CANONICAL_DATA["fingerprint_sha256"],
        "train_manifest_sha256": CANONICAL_DATA["manifest_sha256"],
        "warm_lineage_sha256": HARDENED_LINEAGE["warm"]["receipt_sha256"],
    }
    if inputs != expected_inputs or (
        pilot_config["dataset"]["fingerprint_sha256"] != CANONICAL_DATA["fingerprint_sha256"]
        or pilot_config["validation"]["fingerprint_sha256"]
        != CANONICAL_VALIDATION["fingerprint_sha256"]
    ):
        raise PilotResultError("hardened resume input fingerprints do not match the campaign")
    bounds = verification.get("bounds", {})
    expected_schedule = [3, 6, 9, 12]
    if (
        bounds.get("planned_steps_per_treatment") != 12
        or bounds.get("max_length") != pilot_config["shared"]["max_length"]
    ):
        raise PilotResultError("hardened resume bounds changed")
    clean = verification.get("clean", {})
    interruption = verification.get("warm_interruption", {})
    resumed = verification.get("warm_resume", {})
    for label, section in (("clean", clean), ("warm resume", resumed)):
        schedule = section.get("schedule", {})
        if (
            schedule.get("requested_steps") != expected_schedule
            or schedule.get("observed_eval_steps") != expected_schedule
            or schedule.get("surviving_checkpoint_steps") != [6, 9, 12]
            or not _is_sha256(section.get("completion_manifest_sha256"))
        ):
            raise PilotResultError(f"hardened {label} schedule/manifest changed")
    resume = resumed.get("resume", {})
    if (
        interruption.get("exit_status") != 143
        or interruption.get("completed_marker") is not False
        or 6 not in interruption.get("complete_checkpoint_steps", [])
        or resume.get("requested") is not True
        or resume.get("retry_from_scratch") is not False
        or resume.get("checkpoint_step") != 6
    ):
        raise PilotResultError("hardened interruption/resume semantics changed")
    gpu = verification.get("gpu", {})
    if gpu.get("released_before_receipt") is not True or gpu.get("compute_processes_at_receipt"):
        raise PilotResultError("hardened resume receipt did not release the GPU")

    if path.parent.name != "receipts":
        raise PilotResultError("hardened resume verification must remain in its receipt tree")
    evidence_root = path.parent.parent
    if any(candidate.is_symlink() for candidate in evidence_root.rglob("*")):
        raise PilotResultError("hardened resume evidence contains a symlink")
    sums_path = evidence_root / "SHA256SUMS"
    if sha256_file(sums_path) != HARDENED_RESUME_SHA256SUMS_SHA256:
        raise PilotResultError("hardened resume SHA256SUMS changed")
    checksum_receipts: dict[str, str] = {}
    try:
        checksum_lines = sums_path.read_text(encoding="ascii").splitlines()
    except OSError as exc:
        raise PilotResultError("cannot read hardened resume SHA256SUMS") from exc
    for line in checksum_lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not _is_sha256(parts[0]):
            raise PilotResultError("hardened resume SHA256SUMS has an invalid line")
        relative_text = parts[1].removeprefix("./")
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts or relative_text in checksum_receipts:
            raise PilotResultError("hardened resume SHA256SUMS has an unsafe path")
        checksum_receipts[relative_text] = parts[0]
    actual_files = {
        candidate.relative_to(evidence_root).as_posix()
        for candidate in evidence_root.rglob("*")
        if candidate.is_file()
    }
    if actual_files != set(checksum_receipts) | {"SHA256SUMS"}:
        raise PilotResultError("hardened resume SHA256SUMS does not cover the exact tree")
    for relative, expected_sha in checksum_receipts.items():
        if sha256_file(evidence_root / relative) != expected_sha:
            raise PilotResultError(f"hardened resume checksum mismatch: {relative}")
    sidecar_parts = (path.with_suffix(path.suffix + ".sha256")).read_text(encoding="ascii").split()
    if sidecar_parts != [HARDENED_RESUME_VERIFICATION_SHA256, path.name]:
        raise PilotResultError("hardened resume verification sidecar changed")
    listed: set[str] = set()
    for receipt in verification.get("receipt_files", []):
        if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
            raise PilotResultError("hardened resume file receipt is invalid")
        relative = Path(receipt["path"])
        unresolved_target = evidence_root / relative
        target = unresolved_target.resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or unresolved_target.is_symlink()
            or evidence_root not in target.parents
            or relative.as_posix() in listed
        ):
            raise PilotResultError("hardened resume file receipt has an unsafe path")
        listed.add(relative.as_posix())
        _verify_file(target, receipt)
    if len(listed) != len(verification.get("receipt_files", [])) or not listed:
        raise PilotResultError("hardened resume file receipt set is empty or duplicated")
    completion_receipts: dict[str, dict[str, Any]] = {}
    for lineage, directory in (
        ("clean", evidence_root / "clean-complete"),
        ("warm", evidence_root / "warm-interrupted-resume"),
    ):
        authority = HARDENED_LINEAGE[lineage]
        manifest_path = directory / "training-manifest.json"
        resolved_path = directory / "resolved-config.json"
        completed_path = directory / "COMPLETED.json"
        if (
            sha256_file(manifest_path) != authority["training_manifest_sha256"]
            or sha256_file(resolved_path) != authority["resolved_config_sha256"]
        ):
            raise PilotResultError(f"hardened {lineage} completion authority changed")
        manifest = _read_object(manifest_path)
        resolved = _read_object(resolved_path)
        completed = _read_object(completed_path)
        if (
            completed.get("training_manifest_sha256") != sha256_file(manifest_path)
            or manifest.get("lineage") != lineage
            or manifest.get("base_lineage", {}).get("receipt_sha256") != authority["receipt_sha256"]
            or manifest.get("base_lineage", {}).get("observed", {}).get("tree_sha256")
            != authority["base_tree_sha256"]
            or resolved.get("lineage") != lineage
            or resolved.get("lineage_receipt_sha256") != authority["receipt_sha256"]
            or manifest.get("scripts") != script_hashes
            or resolved.get("script_sha256") != trainer_sha
            or manifest.get("dataset", {}).get("manifest_sha256")
            != CANONICAL_DATA["manifest_sha256"]
            or manifest.get("validation", {}).get("manifest_sha256")
            != CANONICAL_VALIDATION["manifest_sha256"]
            or manifest.get("trainer_global_step") != 12
        ):
            raise PilotResultError(f"hardened {lineage} completion is not joined to authority")
        completion_receipts[lineage] = {
            "training_manifest_sha256": sha256_file(manifest_path),
            "resolved_config_sha256": sha256_file(resolved_path),
            "base_tree_sha256": authority["base_tree_sha256"],
        }
    warm_manifest = _read_object(
        evidence_root / "warm-interrupted-resume" / "training-manifest.json"
    )
    if warm_manifest.get("resume") != resumed.get("resume"):
        raise PilotResultError("hardened warm resume manifest differs from verification")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "trainer_sha256": trainer_sha,
        "train_fingerprint_sha256": inputs["train_fingerprint"],
        "validation_fingerprint_sha256": inputs["dev_fingerprint"],
        "train_manifest_sha256": inputs["train_manifest_sha256"],
        "validation_manifest_sha256": inputs["dev_manifest_sha256"],
        "clean_lineage_sha256": inputs["clean_lineage_sha256"],
        "warm_lineage_sha256": inputs["warm_lineage_sha256"],
        "script_sha256": script_hashes,
        "completion_receipts": completion_receipts,
        "sha256sums_sha256": sha256_file(sums_path),
        "planned_steps": 12,
        "interrupted_after_loss_records": bounds.get("interrupted_loss_records"),
        "resume_checkpoint_step": 6,
        "completed_step": 12,
        "evidence_file_count": len(listed),
    }


def verify_promotion_smoke_run(
    smoke_dir: Path,
    *,
    pilot_config: dict[str, Any],
    current_source: bool = False,
    resumed_step: int | None = None,
) -> dict[str, Any]:
    """Validate a real 20-100-step smoke, not merely self-asserted step fields."""
    root = smoke_dir.resolve()
    if not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
        raise PilotResultError("promotion smoke directory is missing or contains a symlink")
    if (root / "FAILED.json").exists() or (root / "RUNNING.json").exists():
        raise PilotResultError("promotion smoke has a conflicting live/failed marker")
    terminal_path = root / "COMPLETED.json"
    manifest_path = root / "training-manifest.json"
    resolved_path = root / "resolved-config.json"
    terminal = _read_object(terminal_path)
    manifest = _read_object(manifest_path)
    resolved = _read_object(resolved_path)
    script_dir = Path(__file__).resolve().parent
    script_hashes = {
        "train_lora_round2.py": sha256_file(script_dir / "train_lora_round2.py"),
        "campaign_io.py": sha256_file(script_dir / "campaign_io.py"),
        "train_lora.py": sha256_file(script_dir / "train_lora.py"),
    }
    expected_script_hashes = {
        "train_lora_round2.py": CANONICAL_TRAINING_SOURCE_SHA256["trainer_sha256"],
        "campaign_io.py": CANONICAL_TRAINING_SOURCE_SHA256["campaign_io_sha256"],
        "train_lora.py": CANONICAL_TRAINING_SOURCE_SHA256["train_lora_sha256"],
    }
    if not current_source and script_hashes != expected_script_hashes:
        raise PilotResultError("promotion smoke training source authority changed")
    trainer_sha = script_hashes["train_lora_round2.py"]
    if terminal.get("training_manifest_sha256") != sha256_file(manifest_path):
        raise PilotResultError("promotion smoke terminal does not bind its training manifest")
    if terminal.get("run_name") != manifest.get("run_name"):
        raise PilotResultError("promotion smoke terminal run name changed")
    steps = manifest.get("planned_steps")
    if (
        manifest.get("schema_version") != 2
        or isinstance(steps, bool)
        or not isinstance(steps, int)
        or not 20 <= steps <= 100
        or manifest.get("max_steps") != steps
        or manifest.get("trainer_global_step") != steps
    ):
        raise PilotResultError("promotion smoke must complete 20-100 planned optimizer steps")
    if (
        manifest.get("scripts") != script_hashes
        or resolved.get("script_sha256") != trainer_sha
        or resolved.get("campaign_io_sha256") != script_hashes["campaign_io.py"]
    ):
        raise PilotResultError("promotion smoke used different training source")
    git = manifest.get("git", {})
    if not current_source and (
        git.get("available") is not True
        or git.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40}", str(git.get("commit", "")))
    ):
        raise PilotResultError("promotion smoke was not run from clean Git")
    dataset = manifest.get("dataset", {})
    validation = manifest.get("validation", {})
    if (
        dataset.get("dataset_fingerprint_sha256") != CANONICAL_DATA["fingerprint_sha256"]
        or dataset.get("manifest_sha256") != CANONICAL_DATA["manifest_sha256"]
        or dataset.get("row_count") != CANONICAL_DATA["artifact_rows"]
        or validation.get("dataset_fingerprint_sha256")
        != CANONICAL_VALIDATION["fingerprint_sha256"]
        or validation.get("manifest_sha256") != CANONICAL_VALIDATION["manifest_sha256"]
        or validation.get("row_count") != CANONICAL_VALIDATION["rows"]
        or pilot_config["dataset"]["fingerprint_sha256"] != CANONICAL_DATA["fingerprint_sha256"]
        or pilot_config["validation"]["fingerprint_sha256"]
        != CANONICAL_VALIDATION["fingerprint_sha256"]
        or resolved.get("dataset", {}).get("dataset_fingerprint_sha256")
        != dataset.get("dataset_fingerprint_sha256")
        or resolved.get("validation", {}).get("dataset_fingerprint_sha256")
        != validation.get("dataset_fingerprint_sha256")
        or resolved.get("dataset", {}).get("manifest_sha256") != dataset.get("manifest_sha256")
        or resolved.get("validation", {}).get("manifest_sha256")
        != validation.get("manifest_sha256")
    ):
        raise PilotResultError("promotion smoke input authority changed")
    schedule = manifest.get("schedule", {})
    requested = milestone_steps(steps)
    surviving = schedule.get("surviving_checkpoint_steps")
    if (
        schedule.get("kind") != "milestones"
        or schedule.get("requested_steps") != requested
        or schedule.get("observed_eval_steps") != requested
        or schedule.get("session_save_callback_steps")
        != [step for step in requested if resumed_step is None or step > resumed_step]
        or surviving != requested
        or resolved.get("max_steps") != steps
        or resolved.get("expected_planned_steps") != steps
        or resolved.get("milestone_steps") != requested
    ):
        raise PilotResultError("promotion smoke milestone evidence is incomplete")
    if (
        manifest.get("completion_only_loss") is not True
        or manifest.get("training_method") != "lora_bf16"
        or manifest.get("max_length") != pilot_config["shared"]["max_length"]
        or manifest.get("seed") != pilot_config["shared"]["seed"]
        or manifest.get("global_batch_per_gpu") != 64
        or not isinstance(manifest.get("pilot_rows"), int)
        or manifest["pilot_rows"] < 1
        or not isinstance(manifest.get("validation_rows"), int)
        or manifest["validation_rows"] < 1
        or resolved.get("pilot_rows") != manifest.get("pilot_rows")
        or resolved.get("expected_train_rows") != manifest.get("pilot_rows")
        or resolved.get("validation_rows") != manifest.get("validation_rows")
        or resolved.get("expected_validation_rows") != manifest.get("validation_rows")
        or resolved.get("batch_size", 0) * resolved.get("gradient_accumulation", 0) != 64
        or manifest.get("logging_steps") != 1
        or resolved.get("logging_steps") != 1
        or manifest.get("rank") != 16
        or manifest.get("lora_alpha") != 16
        or manifest.get("target_modules") != list(LORA_TARGET_MODULES)
        or manifest.get("epochs") != 1.0
        or manifest.get("batch_size") != 64
        or manifest.get("eval_batch_size") != 64
        or manifest.get("gradient_accumulation") != 1
        or manifest.get("warmup_ratio") != 0.03
        or manifest.get("weight_decay") != 0.0
        or manifest.get("private_policy") not in {"include", "exclude"}
        or resolved.get("rank") != manifest.get("rank")
        or resolved.get("lora_alpha") != manifest.get("lora_alpha")
        or resolved.get("epochs") != manifest.get("epochs")
        or resolved.get("batch_size") != manifest.get("batch_size")
        or resolved.get("eval_batch_size") != manifest.get("eval_batch_size")
        or resolved.get("gradient_accumulation") != manifest.get("gradient_accumulation")
        or resolved.get("warmup_ratio") != manifest.get("warmup_ratio")
        or resolved.get("weight_decay") != manifest.get("weight_decay")
        or resolved.get("seed") != manifest.get("seed")
        or resolved.get("max_length") != manifest.get("max_length")
        or resolved.get("private_policy") != manifest.get("private_policy")
        or manifest.get("campaign_config") is not None
        or resolved.get("campaign_config") is not None
    ):
        raise PilotResultError("promotion smoke treatment differs from the campaign")
    _verify_tokenizer_receipt(manifest.get("tokenizer"))
    if resolved.get("tokenizer") != manifest.get("tokenizer"):
        raise PilotResultError("promotion smoke resolved tokenizer receipt changed")
    tokenization = manifest.get("tokenization")
    if not isinstance(tokenization, dict) or set(tokenization) != {"train", "validation"}:
        raise PilotResultError("promotion smoke tokenization receipt is incomplete")
    for split, expected_rows in (
        ("train", manifest["pilot_rows"]),
        ("validation", manifest["validation_rows"]),
    ):
        receipt = tokenization[split]
        if (
            not isinstance(receipt, dict)
            or receipt.get("rows") != expected_rows
            or isinstance(receipt.get("assistant_tokens"), bool)
            or not isinstance(receipt.get("assistant_tokens"), int)
            or receipt["assistant_tokens"] < expected_rows
            or isinstance(receipt.get("sequence_tokens"), bool)
            or not isinstance(receipt.get("sequence_tokens"), int)
            or receipt["sequence_tokens"] < receipt["assistant_tokens"]
            or isinstance(receipt.get("max_sequence_tokens"), bool)
            or not isinstance(receipt.get("max_sequence_tokens"), int)
            or not 1 <= receipt["max_sequence_tokens"] <= manifest["max_length"]
        ):
            raise PilotResultError(f"promotion smoke {split} tokenization receipt is invalid")
    if not _is_sha256(manifest.get("train_ordered_id_sha256")) or not _is_sha256(
        manifest.get("validation_ordered_id_sha256")
    ):
        raise PilotResultError("promotion smoke ordered-row receipts are invalid")
    lineage = resolved.get("lineage")
    lineage_receipt_sha = resolved.get("lineage_receipt_sha256")
    base_lineage = manifest.get("base_lineage", {})
    if lineage not in HARDENED_LINEAGE:
        raise PilotResultError("promotion smoke lineage is invalid")
    lineage_authority = HARDENED_LINEAGE[lineage]
    expected_learning_rate = 1e-5 if lineage == "clean" else 5e-6
    if (
        lineage_receipt_sha != lineage_authority["receipt_sha256"]
        or base_lineage.get("receipt_sha256") != lineage_receipt_sha
        or base_lineage.get("observed", {}).get("tree_sha256")
        != lineage_authority["base_tree_sha256"]
        or manifest.get("lineage") != lineage
        or manifest.get("learning_rate") != expected_learning_rate
        or resolved.get("learning_rate") != expected_learning_rate
    ):
        raise PilotResultError("promotion smoke lineage receipt is incomplete")
    resolved_receipt = root / "resolved-config.json.sha256"
    try:
        resolved_parts = resolved_receipt.read_text(encoding="ascii").strip().split()
    except OSError as exc:
        raise PilotResultError("promotion smoke lacks a resolved-config receipt") from exc
    if resolved_parts != [sha256_file(resolved_path), resolved_path.name]:
        raise PilotResultError("promotion smoke resolved-config receipt mismatch")
    resume = manifest.get("resume")
    if (
        not isinstance(resume, dict)
        or resume.get("requested") is not (resumed_step is not None)
        or resume.get("retry_from_scratch") is not False
        or resume.get("checkpoint_step") != resumed_step
        or not _is_sha256(resume.get("treatment_signature_sha256"))
        or resume.get("initial_resolved_config_sha256") != sha256_file(resolved_path)
        or resolved.get("resume_from_checkpoint") is not None
        or resolved.get("resume_checkpoint_step") is not None
    ):
        raise PilotResultError("promotion smoke must be a fresh, non-resumed trainer run")
    elapsed = manifest.get("elapsed_seconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(float(elapsed))
        or float(elapsed) <= 0
    ):
        raise PilotResultError("promotion smoke elapsed-time evidence is invalid")
    gpu_memory = manifest.get("gpu_memory")
    if not isinstance(gpu_memory, dict) or set(gpu_memory) != {
        "before_training",
        "training",
        "final_evaluation",
    }:
        raise PilotResultError("promotion smoke GPU-memory evidence is incomplete")
    for phase, receipt in gpu_memory.items():
        if (
            not isinstance(receipt, dict)
            or not isinstance(receipt.get("device_name"), str)
            or "A100" not in receipt["device_name"]
            or any(
                isinstance(receipt.get(field), bool)
                or not isinstance(receipt.get(field), int)
                or receipt[field] < 0
                for field in (
                    "current_allocated_bytes",
                    "current_reserved_bytes",
                    "peak_allocated_bytes",
                    "peak_reserved_bytes",
                    "device_total_bytes",
                )
            )
            or receipt["device_total_bytes"] < 1
        ):
            raise PilotResultError(f"promotion smoke {phase} GPU receipt is invalid")
    environment = manifest.get("environment")
    packages = environment.get("packages") if isinstance(environment, dict) else None
    if (
        not isinstance(environment, dict)
        or not isinstance(environment.get("hostname"), str)
        or not environment["hostname"]
        or not isinstance(environment.get("platform"), str)
        or not environment["platform"]
        or not isinstance(environment.get("python"), str)
        or not environment["python"]
        or not isinstance(environment.get("torch"), str)
        or not environment["torch"]
        or not isinstance(environment.get("cuda"), str)
        or not environment["cuda"]
        or not isinstance(environment.get("gpu"), str)
        or "A100" not in environment["gpu"]
        or not isinstance(packages, dict)
        or any(
            not isinstance(packages.get(package), str) or not packages[package]
            for package in (
                "torch",
                "transformers",
                "peft",
                "safetensors",
                "unsloth",
                "matplotlib",
            )
        )
    ):
        raise PilotResultError("promotion smoke environment evidence is incomplete")

    metric_receipts = manifest.get("metrics", {})
    expected_metrics = {
        "metrics.csv",
        "metrics.jsonl",
        "loss-curve.png",
        "loss-curve.svg",
    }
    if not isinstance(metric_receipts, dict) or set(metric_receipts) != expected_metrics:
        raise PilotResultError("promotion smoke metric receipt set is incomplete")
    for name in sorted(expected_metrics):
        receipt = metric_receipts[name]
        if not isinstance(receipt, dict):
            raise PilotResultError(f"promotion smoke lacks {name} receipt")
        _verify_file(root / name, receipt)
    loss_curve_receipt = _verify_loss_curve_files(
        png_path=root / "loss-curve.png",
        svg_path=root / "loss-curve.svg",
    )
    metrics_rows = _read_jsonl(root / "metrics.jsonl")
    if not metrics_rows:
        raise PilotResultError("promotion smoke metrics are empty")
    train_rows: list[dict[str, Any]] = []
    evaluation_rows: list[dict[str, Any]] = []
    train_summaries = [
        row for row in metrics_rows if row.get("step") == steps and "train_loss" in row
    ]
    for row_number, row in enumerate(metrics_rows, 1):
        step = row.get("step")
        if isinstance(step, bool) or not isinstance(step, int) or not 1 <= step <= steps:
            raise PilotResultError(f"promotion smoke metric row {row_number} has invalid step")
        loss_fields = [field for field in ("loss", "eval_loss", "train_loss") if field in row]
        if len(loss_fields) != 1:
            raise PilotResultError(
                f"promotion smoke metric row {row_number} must contain exactly one loss field"
            )
        field = loss_fields[0]
        _finite_nonnegative_number(
            row[field],
            label=f"promotion smoke metric row {row_number} {field}",
        )
        if field == "loss":
            train_rows.append(row)
        elif field == "eval_loss":
            evaluation_rows.append(row)
    train_steps = [row["step"] for row in train_rows]
    if train_steps != list(range(1, steps + 1)) or len(train_summaries) != 1:
        raise PilotResultError("promotion smoke metrics do not prove every optimizer step")
    evals_by_step: dict[int, list[dict[str, Any]]] = {}
    for row in evaluation_rows:
        evals_by_step.setdefault(row["step"], []).append(row)
    expected_eval_counts = {step: 1 for step in requested}
    expected_eval_counts[steps] += 1  # explicit post-training evaluation of the best model
    if {step: len(rows) for step, rows in evals_by_step.items()} != expected_eval_counts:
        raise PilotResultError("promotion smoke evaluation metric steps/multiplicity changed")
    scheduled_evaluations = {step: evals_by_step[step][0] for step in requested}
    scheduled_eval_losses = {
        step: _finite_nonnegative_number(
            row["eval_loss"], label=f"promotion smoke scheduled eval loss at step {step}"
        )
        for step, row in scheduled_evaluations.items()
    }
    expected_best_metric = min(scheduled_eval_losses.values())
    expected_best_steps = {
        step for step, value in scheduled_eval_losses.items() if value == expected_best_metric
    }
    post_eval = evals_by_step[steps][-1]
    train_summary = train_summaries[0]
    if (
        metrics_rows[-2:] != [train_summary, post_eval]
        or _finite_nonnegative_number(
            post_eval["eval_loss"], label="promotion smoke post-training eval loss"
        )
        != expected_best_metric
    ):
        raise PilotResultError("promotion smoke post-training best-model evaluation changed")
    manifest_train_loss = _finite_nonnegative_number(
        manifest.get("train_metrics", {}).get("train_loss"),
        label="promotion smoke manifest train loss",
    )
    manifest_eval_loss = _finite_nonnegative_number(
        manifest.get("validation_metrics", {}).get("eval_loss"),
        label="promotion smoke manifest validation loss",
    )
    if (
        manifest_train_loss
        != _finite_nonnegative_number(
            train_summary["train_loss"], label="promotion smoke train summary loss"
        )
        or manifest_eval_loss != expected_best_metric
    ):
        raise PilotResultError("promotion smoke summary losses disagree with metric history")
    metric_fields = sorted({field for row in metrics_rows for field in row})
    rendered_csv = io.StringIO(newline="")
    writer = csv.DictWriter(rendered_csv, fieldnames=metric_fields)
    writer.writeheader()
    writer.writerows(metrics_rows)
    try:
        with (root / "metrics.csv").open(newline="", encoding="utf-8") as handle:
            observed_csv = handle.read()
    except OSError as exc:
        raise PilotResultError("cannot read promotion smoke metrics CSV") from exc
    if observed_csv != rendered_csv.getvalue():
        raise PilotResultError("promotion smoke CSV does not exactly project its JSONL metrics")
    loss_curve_receipt["data_sha256"] = hashlib.sha256(
        json.dumps(
            {
                "train": [[row["step"], row["loss"]] for row in train_rows],
                "validation": [[row["step"], row["eval_loss"]] for row in evaluation_rows],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    loss_curve_receipt.update(
        _verify_loss_curve_rendering(
            png_path=root / "loss-curve.png",
            svg_path=root / "loss-curve.svg",
            train_rows=train_rows,
            evaluation_rows=evaluation_rows,
            expected_matplotlib_version=packages["matplotlib"],
            portable=current_source,
        )
    )

    trainer_state_path = root / "checkpoints" / "trainer_state.json"
    trainer_state = _read_object(trainer_state_path)
    trainer_best_metric = _finite_nonnegative_number(
        trainer_state.get("best_metric"), label="promotion smoke trainer-state best metric"
    )
    if (
        trainer_state.get("global_step") != steps
        or trainer_state.get("max_steps") != steps
        or trainer_state.get("log_history") != metrics_rows
        or Path(str(trainer_state.get("best_model_checkpoint", ""))).name
        not in {f"checkpoint-{step}" for step in expected_best_steps}
        or trainer_best_metric != expected_best_metric
    ):
        raise PilotResultError("promotion smoke final trainer state is incomplete")
    adapter_dir = root / "adapter"
    final_adapter_weights = _verify_safetensors(
        adapter_dir / "adapter_model.safetensors", require_qwen25_rank16_lora=True
    )
    final_adapter_config = _verify_adapter_config(adapter_dir / "adapter_config.json")
    checkpoint_state_hashes: dict[str, str] = {}
    checkpoint_weight_receipts: dict[str, dict[str, Any]] = {}
    checkpoint_inventories: dict[str, dict[str, Any]] = {}
    required_checkpoint_files = {
        "adapter_model.safetensors",
        "adapter_config.json",
        "trainer_state.json",
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pth",
        "training_args.bin",
    }
    for checkpoint_step in surviving:
        checkpoint = root / "checkpoints" / f"checkpoint-{checkpoint_step}"
        for name in required_checkpoint_files:
            artifact = checkpoint / name
            if not artifact.is_file() or artifact.is_symlink() or artifact.stat().st_size < 1:
                raise PilotResultError(
                    f"promotion smoke checkpoint lacks trainer artifact {name}: {checkpoint_step}"
                )
        state_path = checkpoint / "trainer_state.json"
        state = _read_object(state_path)
        checkpoint_history = state.get("log_history")
        checkpoint_eval = scheduled_evaluations[checkpoint_step]
        checkpoint_best_metric = min(
            value for step, value in scheduled_eval_losses.items() if step <= checkpoint_step
        )
        checkpoint_best_steps = {
            step
            for step, value in scheduled_eval_losses.items()
            if step <= checkpoint_step and value == checkpoint_best_metric
        }
        if (
            state.get("global_step") != checkpoint_step
            or state.get("max_steps") != steps
            or not isinstance(checkpoint_history, list)
            or not checkpoint_history
            or checkpoint_history != metrics_rows[: len(checkpoint_history)]
            or checkpoint_history[-1] != checkpoint_eval
            or Path(str(state.get("best_model_checkpoint", ""))).name
            not in {f"checkpoint-{step}" for step in checkpoint_best_steps}
            or _finite_nonnegative_number(
                state.get("best_metric"),
                label=f"promotion smoke checkpoint-{checkpoint_step} best metric",
            )
            != checkpoint_best_metric
        ):
            raise PilotResultError(f"promotion smoke checkpoint is incomplete: {checkpoint_step}")
        checkpoint_weights = _verify_safetensors(
            checkpoint / "adapter_model.safetensors", require_qwen25_rank16_lora=True
        )
        if _verify_adapter_config(checkpoint / "adapter_config.json") != final_adapter_config:
            raise PilotResultError(
                f"promotion smoke checkpoint adapter config changed: {checkpoint_step}"
            )
        checkpoint_state_hashes[str(checkpoint_step)] = sha256_file(state_path)
        checkpoint_weight_receipts[str(checkpoint_step)] = checkpoint_weights
        checkpoint_inventories[str(checkpoint_step)] = inventory_tree(checkpoint)
    adapter_inventory = inventory_tree(adapter_dir)
    if manifest.get("adapter") != adapter_inventory:
        raise PilotResultError("promotion smoke adapter inventory changed")
    selection = manifest.get("adapter_selection", {})
    best_step = selection.get("best_checkpoint_step")
    best_checkpoint = root / "checkpoints" / f"checkpoint-{best_step}"
    selected_metric = _finite_nonnegative_number(
        selection.get("best_metric"), label="promotion smoke selected best metric"
    )
    if (
        selection.get("policy") != "minimum_eval_loss"
        or selection.get("best_metric_name") != "eval_loss"
        or best_step not in expected_best_steps
        or selected_metric != expected_best_metric
        or selection.get("best_checkpoint_relative_path") != f"checkpoints/checkpoint-{best_step}"
        or selection.get("best_checkpoint_adapter_model_sha256")
        != sha256_file(best_checkpoint / "adapter_model.safetensors")
        or selection.get("final_adapter_model_sha256")
        != sha256_file(adapter_dir / "adapter_model.safetensors")
        or selection.get("best_checkpoint_adapter_config_sha256")
        != sha256_file(best_checkpoint / "adapter_config.json")
        or selection.get("final_adapter_config_sha256")
        != sha256_file(adapter_dir / "adapter_config.json")
        or selection.get("best_checkpoint_adapter_model_sha256")
        != selection.get("final_adapter_model_sha256")
        or selection.get("best_checkpoint_adapter_config_sha256")
        != selection.get("final_adapter_config_sha256")
    ):
        raise PilotResultError("promotion smoke adapter is not the selected checkpoint")
    stdout_path = root / "stdout.log"
    if not stdout_path.is_file() or stdout_path.is_symlink() or stdout_path.stat().st_size < 256:
        raise PilotResultError("promotion smoke has no retained execution log")
    tree = inventory_tree(root)
    return {
        "path": str(root),
        "completed_sha256": sha256_file(terminal_path),
        "training_manifest_sha256": sha256_file(manifest_path),
        "resolved_config_sha256": sha256_file(resolved_path),
        "metrics_csv_sha256": sha256_file(root / "metrics.csv"),
        "metrics_jsonl_sha256": sha256_file(root / "metrics.jsonl"),
        "loss_curve": loss_curve_receipt,
        "trainer_state_sha256": sha256_file(trainer_state_path),
        "checkpoint_trainer_state_sha256": checkpoint_state_hashes,
        "checkpoint_adapter_safetensors": checkpoint_weight_receipts,
        "checkpoint_inventories": checkpoint_inventories,
        "adapter_safetensors": final_adapter_weights,
        "adapter_tree_sha256": adapter_inventory["tree_sha256"],
        "stdout_sha256": sha256_file(stdout_path),
        "tree_sha256": tree["tree_sha256"],
        "tree_bytes": tree["bytes"],
        "tree_file_count": tree["file_count"],
        "trainer_sha256": trainer_sha,
        "script_sha256": script_hashes,
        "train_fingerprint_sha256": dataset["dataset_fingerprint_sha256"],
        "validation_fingerprint_sha256": validation["dataset_fingerprint_sha256"],
        "train_manifest_sha256": dataset["manifest_sha256"],
        "validation_manifest_sha256": validation["manifest_sha256"],
        "lineage": lineage,
        "lineage_receipt_sha256": lineage_receipt_sha,
        "lineage_base_tree_sha256": lineage_authority["base_tree_sha256"],
        "planned_steps": steps,
        "completed_step": manifest["trainer_global_step"],
        "milestone_steps": requested,
        "metric_row_count": len(metrics_rows),
        "optimizer_loss_row_count": len(train_rows),
        "evaluation_loss_row_count": len(evaluation_rows),
        "best_checkpoint_step": best_step,
        "best_eval_loss": expected_best_metric,
        **({"resume_checkpoint_step": resumed_step} if current_source else {}),
    }


def verify_pilot_evaluation(
    evaluation_dir: Path,
    *,
    pilot_config: dict[str, Any],
    pilot_results: dict[str, Any],
) -> dict[str, Any]:
    """Bind a complete matched-prompt replay to every compiled pilot adapter."""
    root = evaluation_dir.resolve()
    terminal_path = root / "COMPLETED.json"
    if not root.is_dir() or not terminal_path.is_file() or (root / "FAILED.json").exists():
        raise PilotResultError("pilot evaluation is not terminally complete")
    terminal = _read_object(terminal_path)
    if terminal.get("status") != "completed":
        raise PilotResultError("evaluation terminal receipt is not completed")
    inventory_path = root / "artifact-inventory.json"
    if terminal.get("artifact_inventory_sha256") != sha256_file(inventory_path):
        raise PilotResultError("evaluation terminal does not bind its artifact inventory")
    inventory = _read_object(inventory_path)
    if inventory.get("schema_version") != 1:
        raise PilotResultError("evaluation inventory schema is not supported")
    inventory_files = inventory.get("files")
    if not isinstance(inventory_files, list):
        raise PilotResultError("evaluation inventory has no file list")
    listed: set[str] = set()
    listed_bytes = 0
    for receipt in inventory_files:
        if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
            raise PilotResultError("evaluation inventory has an invalid entry")
        relative = Path(receipt["path"])
        unresolved_target = root / relative
        target = unresolved_target.resolve()
        if relative.is_absolute() or root not in target.parents or unresolved_target.is_symlink():
            raise PilotResultError("evaluation inventory path escapes its root")
        _verify_file(target, receipt)
        listed.add(relative.as_posix())
        listed_bytes += target.stat().st_size
    if (
        len(listed) != len(inventory_files)
        or inventory.get("file_count") != len(inventory_files)
        or inventory.get("bytes") != listed_bytes
    ):
        raise PilotResultError("evaluation inventory counts are inconsistent")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"artifact-inventory.json", "COMPLETED.json"}
    }
    if listed != actual:
        raise PilotResultError("evaluation inventory does not exactly cover the evidence tree")
    for name, terminal_field in (
        ("summary.csv", "summary_csv_sha256"),
        ("summary.md", "summary_markdown_sha256"),
        ("responses.jsonl", "aggregate_responses_sha256"),
    ):
        if terminal.get(terminal_field) != sha256_file(root / name):
            raise PilotResultError(f"evaluation terminal does not bind {name}")

    run = _read_object(root / "run.json")
    if (
        run.get("schema_version") != 1
        or run.get("prompt_suite") != "judges"
        or run.get("prompt_count", 0) < 2
        or not isinstance(run.get("prompt_set_sha256"), str)
    ):
        raise PilotResultError("evaluation does not contain at least two frozen judges prompts")
    runtime = run.get("runtime")
    runtime_git = runtime.get("git") if isinstance(runtime, dict) else None
    runtime_script = runtime.get("script") if isinstance(runtime, dict) else None
    expected_evaluator_sha = sha256_file(
        Path(__file__).resolve().parents[2] / "bench" / "round2_candidate_eval.py"
    )
    if (
        not isinstance(runtime_git, dict)
        or runtime_git.get("available") is not True
        or runtime_git.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40,64}", str(runtime_git.get("commit", "")))
        or not isinstance(runtime_script, dict)
        or not re.fullmatch(r"[0-9a-f]{64}", str(runtime_script.get("sha256", "")))
        or runtime_script.get("sha256") != expected_evaluator_sha
    ):
        raise PilotResultError(
            "evaluation runtime is not bound to clean Git and this exact evaluator"
        )
    prompts_path = root / "prompts.json"
    try:
        prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotResultError("cannot read evaluation prompts") from exc
    if not isinstance(prompts, list) or len(prompts) != run["prompt_count"]:
        raise PilotResultError("evaluation prompt artifact has the wrong row count")
    prompt_set_sha256 = hashlib.sha256(
        json.dumps(
            prompts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if prompt_set_sha256 != run["prompt_set_sha256"]:
        raise PilotResultError("evaluation prompt artifact does not match its frozen digest")
    snapshot_path = root / "candidate-manifest.json"
    if run.get("candidate_manifest", {}).get("sha256") != sha256_file(snapshot_path):
        raise PilotResultError("evaluation run does not bind its candidate manifest snapshot")
    snapshot = _read_object(snapshot_path)
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list):
        raise PilotResultError("evaluation candidate snapshot is invalid")
    evaluated_ids = [row.get("id") for row in candidates if isinstance(row, dict)]
    if (
        len(evaluated_ids) != len(candidates)
        or any(
            not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier)
            for identifier in evaluated_ids
        )
        or len(evaluated_ids) != len(set(evaluated_ids))
    ):
        raise PilotResultError("evaluation candidate IDs are invalid or duplicated")
    pilot_ids = {candidate["id"] for candidate in pilot_config["candidates"]}
    if not pilot_ids.issubset(evaluated_ids):
        raise PilotResultError("evaluation omits a configured fine-tuned pilot")
    snapshot_by_id = {candidate["id"]: candidate for candidate in candidates}
    result_by_id = {row.get("candidate_id"): row for row in pilot_results.get("rows", [])}
    control_ids = set(evaluated_ids) - pilot_ids
    controls_by_backend: dict[str, list[str]] = {}
    for identifier in control_ids:
        controls_by_backend.setdefault(snapshot_by_id[identifier].get("backend"), []).append(
            identifier
        )
    if set(controls_by_backend) != {"hf", "gguf"} or any(
        len(identifiers) != 1 for identifiers in controls_by_backend.values()
    ):
        raise PilotResultError(
            "evaluation must contain exactly one upstream HF and one incumbent GGUF control"
        )
    clean_base_hashes = {
        result_by_id.get(candidate["id"], {}).get("training_base_tree_sha256")
        for candidate in pilot_config["candidates"]
        if candidate["lineage"] == "clean"
    }
    incumbent_gguf_hashes = {
        result_by_id.get(candidate["id"], {}).get("incumbent_gguf_sha256")
        for candidate in pilot_config["candidates"]
        if candidate["lineage"] == "warm"
    }
    if (
        len(clean_base_hashes) != 1
        or not re.fullmatch(r"[0-9a-f]{64}", str(next(iter(clean_base_hashes), "")))
        or len(incumbent_gguf_hashes) != 1
        or not re.fullmatch(r"[0-9a-f]{64}", str(next(iter(incumbent_gguf_hashes), "")))
    ):
        raise PilotResultError("pilot results do not bind unique upstream/incumbent controls")
    expected_upstream_base_sha = next(iter(clean_base_hashes))
    expected_incumbent_gguf_sha = next(iter(incumbent_gguf_hashes))
    prompt_sequence: list[tuple[int, str, str]] | None = None
    detailed_responses: list[dict[str, Any]] = []
    for candidate_id in evaluated_ids:
        candidate_dir = root / "candidates" / candidate_id
        identity = _read_object(candidate_dir / "identity.json")
        result = _read_object(candidate_dir / "result.json")
        snapshot_candidate = snapshot_by_id[candidate_id]
        if (
            identity.get("candidate_id") != candidate_id
            or identity.get("backend") != snapshot_candidate.get("backend")
            or result.get("candidate_id") != candidate_id
            or result.get("backend") != identity.get("backend")
        ):
            raise PilotResultError(f"evaluation identity/result mismatch: {candidate_id}")
        if candidate_id in pilot_ids:
            pilot_result = result_by_id.get(candidate_id, {})
            if identity.get("backend") != "peft":
                raise PilotResultError(f"pilot evaluation backend is not PEFT: {candidate_id}")
            adapter_sha = identity.get("observed", {}).get("adapter", {}).get("tree_sha256")
            if adapter_sha != pilot_result.get("adapter_sha256"):
                raise PilotResultError(f"evaluated adapter does not match pilot: {candidate_id}")
            base_sha = identity.get("observed", {}).get("base_model", {}).get("tree_sha256")
            if base_sha != pilot_result.get("training_base_tree_sha256"):
                raise PilotResultError(
                    f"evaluated adapter uses the wrong training base: {candidate_id}"
                )
        elif identity.get("backend") == "hf":
            control_sha = identity.get("observed", {}).get("model", {}).get("tree_sha256")
            if control_sha != expected_upstream_base_sha:
                raise PilotResultError("HF control is not the pilots' upstream training base")
        elif identity.get("backend") == "gguf":
            control_sha = identity.get("observed", {}).get("model", {}).get("sha256")
            if control_sha != expected_incumbent_gguf_sha:
                raise PilotResultError("GGUF control is not the bound incumbent Muta model")
        if (
            result.get("status") != "complete"
            or result.get("prompts") != run["prompt_count"]
            or result.get("expected_prompts") != run["prompt_count"]
        ):
            raise PilotResultError(f"matched-prompt evaluation is incomplete: {candidate_id}")
        responses_path = candidate_dir / "responses.jsonl"
        if result.get("responses_sha256") != sha256_file(responses_path):
            raise PilotResultError(f"evaluation result does not bind responses: {candidate_id}")
        rows = _read_jsonl(responses_path)
        detailed_responses.extend(rows)
        identity_sha = identity.get("candidate_identity_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", str(identity_sha or "")):
            raise PilotResultError(f"evaluation has no model identity: {candidate_id}")
        sequence = [
            (int(row.get("ordinal", 0)), str(row.get("id", "")), str(row.get("prompt_sha256", "")))
            for row in rows
        ]
        expected_sequence = [
            (
                ordinal,
                str(prompt.get("id", "")),
                hashlib.sha256(str(prompt.get("text", "")).encode("utf-8")).hexdigest(),
            )
            for ordinal, prompt in enumerate(prompts, 1)
            if isinstance(prompt, dict)
        ]
        if (
            len(rows) != run["prompt_count"]
            or len(expected_sequence) != run["prompt_count"]
            or any(row.get("candidate_id") != candidate_id for row in rows)
            or any(row.get("prompt_set_sha256") != run["prompt_set_sha256"] for row in rows)
            or any(row.get("candidate_backend") != identity.get("backend") for row in rows)
            or any(row.get("model") != candidate_id for row in rows)
            or any(row.get("model_sha256") != identity_sha for row in rows)
            or any(
                row.get("prompt") != prompt or row.get("text") != prompt.get("text")
                for row, prompt in zip(rows, prompts, strict=True)
            )
            or sequence != expected_sequence
        ):
            raise PilotResultError(f"responses violate the frozen prompt set: {candidate_id}")
        if identity.get("backend") == "gguf":
            server_sha = identity.get("observed", {}).get("server", {}).get("sha256")
            if not re.fullmatch(r"[0-9a-f]{64}", str(server_sha or "")) or any(
                row.get("server_sha256") != server_sha for row in rows
            ):
                raise PilotResultError(f"responses do not bind the GGUF server: {candidate_id}")
        raw_paths: set[str] = set()
        for row in rows:
            raw_receipt = row.get("raw_output")
            if not isinstance(raw_receipt, dict) or not isinstance(raw_receipt.get("path"), str):
                raise PilotResultError(f"response has no raw-output receipt: {candidate_id}")
            relative = Path(raw_receipt["path"])
            raw_path = (candidate_dir / relative).resolve()
            if (
                relative.is_absolute()
                or not relative.parts
                or relative.parts[0] != "raw"
                or candidate_dir.resolve() not in raw_path.parents
                or relative.as_posix() in raw_paths
            ):
                raise PilotResultError(f"raw-output path escapes candidate: {candidate_id}")
            raw_paths.add(relative.as_posix())
            _verify_file(raw_path, raw_receipt)
        if prompt_sequence is None:
            prompt_sequence = sequence
        elif sequence != prompt_sequence:
            raise PilotResultError("candidates and controls did not receive identical prompts")

    if _read_jsonl(root / "responses.jsonl") != detailed_responses:
        raise PilotResultError("aggregate responses do not exactly match candidate evidence")

    # Ensure the summary table agrees that each pilot completed; the detailed
    # evidence above remains the source of truth for artifact and prompt identity.
    try:
        with (root / "summary.csv").open(newline="", encoding="utf-8") as handle:
            summary_rows = list(csv.DictReader(handle))
    except (OSError, KeyError) as exc:
        raise PilotResultError("cannot read evaluation summary") from exc
    summary_ids = [row.get("candidate_id") for row in summary_rows]
    if len(summary_ids) != len(set(summary_ids)) or set(summary_ids) != set(evaluated_ids):
        raise PilotResultError("evaluation summary candidate set is not exact")
    summary = {row["candidate_id"]: row for row in summary_rows}
    if any(summary.get(identifier, {}).get("status") != "complete" for identifier in evaluated_ids):
        raise PilotResultError("evaluation summary marks a candidate/control incomplete")
    tree = inventory_tree(root)
    return {
        "path": str(root),
        "tree_sha256": tree["tree_sha256"],
        "bytes": tree["bytes"],
        "file_count": tree["file_count"],
        "terminal_sha256": sha256_file(terminal_path),
        "artifact_inventory_sha256": sha256_file(inventory_path),
        "prompt_suite": run["prompt_suite"],
        "prompt_count": run["prompt_count"],
        "prompt_set_sha256": run["prompt_set_sha256"],
        "evaluated_pilot_ids": sorted(pilot_ids),
        "evaluated_control_ids": sorted(set(evaluated_ids) - pilot_ids),
        "upstream_hf_control_sha256": expected_upstream_base_sha,
        "incumbent_gguf_control_sha256": expected_incumbent_gguf_sha,
    }


def _candidate(
    *,
    identifier: str,
    source: dict[str, Any],
    private_policy: str,
    planned_rows: int,
    global_batch: int,
    selection_note: str,
) -> dict[str, Any]:
    steps = math.ceil(planned_rows / global_batch)
    return {
        "id": identifier,
        "source_pilot_id": source["candidate_id"],
        "source_pilot_training_manifest_sha256": source["training_manifest_sha256"],
        "source_pilot_adapter_sha256": source["adapter_sha256"],
        "source_pilot_best_dev_loss": source["best_dev_loss"],
        "selection_note": selection_note,
        "lineage": source["lineage"],
        "rank": source["rank"],
        "learning_rate": source["learning_rate"],
        "private_policy": private_policy,
        "planned_rows": planned_rows,
        "planned_steps": steps,
        "milestone_steps": milestone_steps(steps),
    }


def _validate_canonical_config_evidence(
    config: dict[str, Any],
    source_pilots: dict[str, Any],
    *,
    current_gates: bool = False,
) -> tuple[dict[str, Any], set[str]]:
    if config.get("selection_protocol") != "canonical_matched_gguf_semantic_addendum_v1":
        raise PilotResultError("schema-v2 promotion has the wrong selection protocol")
    if "matched_prompt_evaluation" in source_pilots:
        raise PilotResultError("schema-v2 promotion cannot contain legacy PEFT evidence")
    if config.get("runtime_input_authority") != CANONICAL_RUNTIME_INPUT_AUTHORITY:
        raise PilotResultError("schema-v2 runtime input authority changed")
    if (
        source_pilots.get("config_sha256") != CANONICAL_PILOT_CONFIG_SHA256
        or source_pilots.get("results_sha256") != CANONICAL_PILOT_RESULTS_SHA256
        or source_pilots.get("compiler_receipt_sha256") != CANONICAL_PILOT_COMPILER_RECEIPT_SHA256
    ):
        raise PilotResultError("schema-v2 pilot authority hashes changed")
    comparison = source_pilots.get("canonical_gguf_semantic_evaluation")
    exports = source_pilots.get("export_manifests")
    if not isinstance(comparison, dict) or not isinstance(exports, dict):
        raise PilotResultError("schema-v2 promotion lacks canonical GGUF/export evidence")
    for field in (
        "terminal_sha256",
        "comparison_json_sha256",
        "comparison_csv_sha256",
        "compiler_sha256",
        "frozen_roster_sha256",
    ):
        if not _is_sha256(comparison.get(field)):
            raise PilotResultError(f"canonical comparison has invalid {field}")
    if any(
        comparison.get(field) != expected for field, expected in CANONICAL_COMPARISON_SHA256.items()
    ):
        raise PilotResultError("canonical comparison receipt differs from retained authority")
    compiler_path = Path(__file__).resolve().parents[2] / "bench/round2_comparison_report.py"
    if comparison["compiler_sha256"] != sha256_file(compiler_path):
        raise PilotResultError("canonical comparison compiler is not the retained compiler")
    comparison_compiler, _compiler_path = _load_comparison_compiler()
    if comparison["frozen_roster_sha256"] != comparison_compiler.FROZEN_ROSTER_SHA:
        raise PilotResultError("canonical comparison frozen-roster binding changed")
    expected_pilot_ids = {
        CANONICAL_CLEAN_SELECTION,
        "clean-r32-lr1e5",
        "warm-r8-lr5e6",
        CANONICAL_WARM_SELECTION,
        "warm-r16-lr1e5",
        "warm-r16-lr2e5",
        "warm-r32-lr5e6",
        "warm-r32-lr1e5",
    }
    if set(comparison.get("evaluated_pilot_ids", [])) != expected_pilot_ids or comparison.get(
        "evaluated_control_ids"
    ) != ["incumbent-muta"]:
        raise PilotResultError("canonical comparison roster is not the frozen eight plus incumbent")
    expected_id_map = {
        pilot_id: f"{CANONICAL_GGUF_PREFIX}{pilot_id}{CANONICAL_GGUF_SUFFIX}"
        for pilot_id in expected_pilot_ids
    }
    if comparison.get("candidate_id_map") != dict(sorted(expected_id_map.items())):
        raise PilotResultError("canonical comparison pilot/GGUF mapping changed")
    model_hashes = comparison.get("model_sha256_by_id")
    quantization_manifest_hashes = comparison.get("quantization_manifest_sha256_by_pilot_id")
    rows_by_pilot = comparison.get("rows_by_pilot_id")
    if (
        not isinstance(model_hashes, dict)
        or set(model_hashes) != {"incumbent-muta", *expected_id_map.values()}
        or not all(_is_sha256(value) for value in model_hashes.values())
        or len(set(model_hashes.values())) != 9
        or not isinstance(quantization_manifest_hashes, dict)
        or set(quantization_manifest_hashes) != expected_pilot_ids
        or not all(_is_sha256(value) for value in quantization_manifest_hashes.values())
        or not isinstance(rows_by_pilot, dict)
        or set(rows_by_pilot) != expected_pilot_ids
    ):
        raise PilotResultError("canonical comparison model/row binding is incomplete")
    selected_scores = {
        CANONICAL_CLEAN_SELECTION: (31, 42, 39, 28, 20, 34),
        CANONICAL_WARM_SELECTION: (30, 37, 35, 33, 23, 56),
    }
    for pilot_id, expected_scores in selected_scores.items():
        row = rows_by_pilot[pilot_id]
        observed_scores = tuple(
            row.get(field)
            for field in (
                "strict_mc_50",
                "semantic_mc_50",
                "mc_explanation_50",
                "written_core_50",
                "written_complete_50",
                "judges_96",
            )
        )
        if row.get("candidate_id") != expected_id_map[pilot_id] or observed_scores != (
            expected_scores
        ):
            raise PilotResultError(f"frozen selection evidence changed: {pilot_id}")
    inputs = comparison.get("inputs")
    if (
        not isinstance(inputs, dict)
        or set(inputs)
        != {
            "math_review",
            "science_review",
            "mc_review",
            "judges_review",
            "stem",
            "judges",
        }
        or any(
            not isinstance(receipt, dict) or not _is_sha256(receipt.get("sha256"))
            for receipt in inputs.values()
        )
    ):
        raise PilotResultError("canonical comparison input receipts are incomplete")
    if {
        name: receipt["sha256"] for name, receipt in sorted(inputs.items())
    } != CANONICAL_COMPARISON_INPUT_SHA256:
        raise PilotResultError("canonical comparison input authority changed")
    expected_sources = comparison_compiler.REVIEW_SOURCE_SHA256
    review_sources = comparison.get("review_sources")
    if not isinstance(review_sources, dict) or set(review_sources) != set(expected_sources):
        raise PilotResultError("canonical comparison review-source receipts are incomplete")
    for relative, expected_sha in expected_sources.items():
        receipt = review_sources[relative]
        if (
            not isinstance(receipt, dict)
            or receipt.get("sha256") != expected_sha
            or not isinstance(receipt.get("bytes"), int)
        ):
            raise PilotResultError(f"canonical review-source binding changed: {relative}")

    pilot_exports = exports.get("pilots")
    toolchain = exports.get("toolchain")
    if (
        exports.get("count") != 8
        or not isinstance(pilot_exports, dict)
        or set(pilot_exports) != expected_pilot_ids
    ):
        raise PilotResultError("full promotion must bind exactly eight GGUF export manifests")
    if not isinstance(toolchain, dict) or set(toolchain) != {
        "merge_script_sha256",
        "llama_cpp_git_commit",
        "converter_sha256",
        "quantizer_sha256",
    }:
        raise PilotResultError("full promotion lacks one exact export toolchain")
    if (
        not _is_sha256(toolchain["merge_script_sha256"])
        or not re.fullmatch(r"[0-9a-f]{40}", str(toolchain["llama_cpp_git_commit"]))
        or not _is_sha256(toolchain["converter_sha256"])
        or not _is_sha256(toolchain["quantizer_sha256"])
    ):
        raise PilotResultError("full promotion export toolchain receipt is invalid")
    if toolchain != CANONICAL_EXPORT_TOOLCHAIN:
        raise PilotResultError("full promotion export toolchain authority changed")
    for pilot_id, receipt in pilot_exports.items():
        if not isinstance(receipt, dict):
            raise PilotResultError(f"GGUF export receipt is not an object: {pilot_id}")
        comparison_id = expected_id_map[pilot_id]
        authority = CANONICAL_PILOT_AUTHORITY[pilot_id]
        if (
            receipt.get("comparison_candidate_id") != comparison_id
            or receipt.get("quantization") != "Q4_K_M"
            or receipt.get("gguf_sha256") != model_hashes[comparison_id]
            or receipt.get("sha256") != quantization_manifest_hashes[pilot_id]
            or not isinstance(receipt.get("gguf_bytes"), int)
            or receipt["gguf_bytes"] < 1
        ):
            raise PilotResultError(f"GGUF export receipt changed: {pilot_id}")
        if (
            receipt.get("sha256") != authority["quantization_manifest_sha256"]
            or receipt.get("adapter_tree_sha256") != authority["adapter_sha256"]
            or receipt.get("base_tree_sha256") != authority["training_base_tree_sha256"]
            or receipt.get("training_manifest_sha256") != authority["training_manifest_sha256"]
            or receipt.get("gguf_sha256") != authority["gguf_sha256"]
        ):
            raise PilotResultError(f"GGUF export/pilot authority changed: {pilot_id}")
        for field in (
            "sha256",
            "adapter_tree_sha256",
            "base_tree_sha256",
            "training_manifest_sha256",
        ):
            if not _is_sha256(receipt.get(field)):
                raise PilotResultError(f"GGUF export has invalid {field}: {pilot_id}")
        for receipt_field, toolchain_field in (
            ("merge_script_sha256", "merge_script_sha256"),
            ("llama_cpp_git_commit", "llama_cpp_git_commit"),
            ("converter_sha256", "converter_sha256"),
            ("quantizer_sha256", "quantizer_sha256"),
        ):
            if receipt.get(receipt_field) != toolchain[toolchain_field]:
                raise PilotResultError(f"GGUF export toolchain changed: {pilot_id}")

    if current_gates:
        return comparison, expected_pilot_ids
    gates = config.get("training_gates")
    if not isinstance(gates, dict) or set(gates) != {
        "hardened_interruption_resume",
        "promotion_smoke",
    }:
        raise PilotResultError("schema-v2 promotion lacks exact training gates")
    resume = gates["hardened_interruption_resume"]
    smoke = gates["promotion_smoke"]
    if not isinstance(resume, dict) or not isinstance(smoke, dict):
        raise PilotResultError("training-gate receipts must be objects")
    if (
        resume.get("planned_steps") != 12
        or resume.get("resume_checkpoint_step") != 6
        or resume.get("completed_step") != 12
        or not isinstance(smoke.get("planned_steps"), int)
        or not 20 <= smoke["planned_steps"] <= 100
        or smoke.get("completed_step") != smoke["planned_steps"]
        or smoke.get("milestone_steps") != milestone_steps(smoke["planned_steps"])
    ):
        raise PilotResultError("training-gate step evidence is invalid")
    if (
        resume.get("sha256") != HARDENED_RESUME_VERIFICATION_SHA256
        or resume.get("sha256sums_sha256") != HARDENED_RESUME_SHA256SUMS_SHA256
        or resume.get("clean_lineage_sha256") != HARDENED_LINEAGE["clean"]["receipt_sha256"]
        or resume.get("warm_lineage_sha256") != HARDENED_LINEAGE["warm"]["receipt_sha256"]
        or resume.get("evidence_file_count") != 25
        or resume.get("completion_receipts")
        != {
            lineage: {
                "training_manifest_sha256": authority["training_manifest_sha256"],
                "resolved_config_sha256": authority["resolved_config_sha256"],
                "base_tree_sha256": authority["base_tree_sha256"],
            }
            for lineage, authority in HARDENED_LINEAGE.items()
        }
    ):
        raise PilotResultError("hardened resume retained authority changed")
    for section_name, section in (("resume", resume), ("smoke", smoke)):
        for field in (
            "trainer_sha256",
            "train_fingerprint_sha256",
            "validation_fingerprint_sha256",
            "train_manifest_sha256",
            "validation_manifest_sha256",
        ):
            if not _is_sha256(section.get(field)):
                raise PilotResultError(f"{section_name} gate has invalid {field}")
    for field in ("sha256", "clean_lineage_sha256", "warm_lineage_sha256"):
        if not _is_sha256(resume.get(field)):
            raise PilotResultError(f"resume gate has invalid {field}")
    for field in (
        "completed_sha256",
        "training_manifest_sha256",
        "resolved_config_sha256",
        "metrics_csv_sha256",
        "metrics_jsonl_sha256",
        "lineage_receipt_sha256",
        "trainer_state_sha256",
        "adapter_tree_sha256",
        "stdout_sha256",
        "tree_sha256",
    ):
        if not _is_sha256(smoke.get(field)):
            raise PilotResultError(f"smoke gate has invalid {field}")
    if smoke.get("lineage") not in {"clean", "warm"} or smoke["lineage_receipt_sha256"] not in {
        resume["clean_lineage_sha256"],
        resume["warm_lineage_sha256"],
    }:
        raise PilotResultError("smoke gate lineage is not bound to hardened evidence")
    if (
        smoke.get("lineage_base_tree_sha256")
        != HARDENED_LINEAGE[smoke["lineage"]]["base_tree_sha256"]
        or not isinstance(smoke.get("tree_bytes"), int)
        or smoke["tree_bytes"] < 1
        or not isinstance(smoke.get("tree_file_count"), int)
        or smoke["tree_file_count"] < 1
        or not isinstance(smoke.get("checkpoint_trainer_state_sha256"), dict)
        or set(smoke["checkpoint_trainer_state_sha256"])
        != {str(step) for step in smoke["milestone_steps"]}
        or not all(_is_sha256(value) for value in smoke["checkpoint_trainer_state_sha256"].values())
    ):
        raise PilotResultError("smoke gate artifact evidence is incomplete")
    adapter_safetensors = smoke.get("adapter_safetensors")
    checkpoint_safetensors = smoke.get("checkpoint_adapter_safetensors")
    checkpoint_inventories = smoke.get("checkpoint_inventories")
    loss_curve = smoke.get("loss_curve")

    def valid_adapter_receipt(receipt: Any) -> bool:
        return (
            isinstance(receipt, dict)
            and _is_sha256(receipt.get("sha256"))
            and isinstance(receipt.get("bytes"), int)
            and receipt["bytes"] >= QWEN25_RANK16_LORA_ELEMENTS * 2
            and isinstance(receipt.get("header_bytes"), int)
            and receipt["header_bytes"] >= 2
            and receipt.get("tensor_count") == len(QWEN25_RANK16_LORA_SHAPES)
            and receipt.get("dtype") in {"F32", "BF16"}
            and receipt.get("element_count") == QWEN25_RANK16_LORA_ELEMENTS
        )

    if (
        not valid_adapter_receipt(adapter_safetensors)
        or not isinstance(checkpoint_safetensors, dict)
        or set(checkpoint_safetensors) != {str(step) for step in smoke["milestone_steps"]}
        or not all(valid_adapter_receipt(receipt) for receipt in checkpoint_safetensors.values())
        or not isinstance(checkpoint_inventories, dict)
        or set(checkpoint_inventories) != {str(step) for step in smoke["milestone_steps"]}
        or any(
            not isinstance(receipt, dict)
            or not _is_sha256(receipt.get("tree_sha256"))
            or not isinstance(receipt.get("bytes"), int)
            or receipt["bytes"] < 1
            or not isinstance(receipt.get("file_count"), int)
            or receipt["file_count"] < 7
            for receipt in checkpoint_inventories.values()
        )
        or not isinstance(loss_curve, dict)
        or loss_curve.get("png_width") != 1_440
        or loss_curve.get("png_height") != 900
        or not isinstance(loss_curve.get("svg_bytes"), int)
        or loss_curve["svg_bytes"] < 10_000
        or not isinstance(loss_curve.get("svg_path_count"), int)
        or loss_curve["svg_path_count"] < 20
        or not isinstance(loss_curve.get("svg_line_id_count"), int)
        or loss_curve["svg_line_id_count"] < 20
        or loss_curve.get("svg_axes_id") != "axes_1"
        or loss_curve.get("svg_legend_id") != "legend_1"
        or not _is_sha256(loss_curve.get("data_sha256"))
        or not _is_sha256(loss_curve.get("png_pixel_sha256"))
        or not _is_sha256(loss_curve.get("svg_series_sha256"))
        or smoke.get("optimizer_loss_row_count") != smoke["planned_steps"]
        or smoke.get("evaluation_loss_row_count") != len(smoke["milestone_steps"]) + 1
        or smoke.get("metric_row_count")
        != smoke["optimizer_loss_row_count"] + smoke["evaluation_loss_row_count"] + 1
        or smoke.get("best_checkpoint_step") not in smoke["milestone_steps"]
    ):
        raise PilotResultError("smoke gate semantic training evidence is incomplete")
    _finite_nonnegative_number(
        smoke.get("best_eval_loss"), label="smoke gate selected validation loss"
    )
    for field in (
        "trainer_sha256",
        "train_fingerprint_sha256",
        "validation_fingerprint_sha256",
        "train_manifest_sha256",
        "validation_manifest_sha256",
    ):
        if resume[field] != smoke[field]:
            raise PilotResultError(f"training gates disagree on {field}")
    expected_gate_scripts = {
        "train_lora_round2.py": CANONICAL_TRAINING_SOURCE_SHA256["trainer_sha256"],
        "campaign_io.py": CANONICAL_TRAINING_SOURCE_SHA256["campaign_io_sha256"],
        "train_lora.py": CANONICAL_TRAINING_SOURCE_SHA256["train_lora_sha256"],
    }
    if (
        resume.get("script_sha256") != expected_gate_scripts
        or smoke.get("script_sha256") != expected_gate_scripts
    ):
        raise PilotResultError("training gates disagree on helper source hashes")
    source_code = config.get("source_code")
    source_paths = {
        "promotion_builder_sha256": Path(__file__).resolve(),
        "full_launcher_sha256": Path(__file__).resolve().parent / "launch_round2_full.py",
        "trainer_sha256": Path(__file__).resolve().parent / "train_lora_round2.py",
        "campaign_io_sha256": Path(__file__).resolve().parent / "campaign_io.py",
        "train_lora_sha256": Path(__file__).resolve().parent / "train_lora.py",
    }
    if not isinstance(source_code, dict) or set(source_code) != set(source_paths):
        raise PilotResultError("schema-v2 promotion lacks executable source bindings")
    for field, path in source_paths.items():
        if source_code.get(field) != sha256_file(path):
            raise PilotResultError(f"schema-v2 executable source changed: {field}")
        if (
            field != "promotion_builder_sha256"
            and source_code[field] != (CANONICAL_TRAINING_SOURCE_SHA256[field])
        ):
            raise PilotResultError(f"schema-v2 retained source authority changed: {field}")
    if source_code["trainer_sha256"] != resume["trainer_sha256"]:
        raise PilotResultError("schema-v2 trainer and training gates disagree")
    return comparison, expected_pilot_ids


def _verify_v2_committed_authority(config: dict[str, Any]) -> None:
    """Require the launch-time object to equal the config committed in Git."""
    authority = config.get("frozen_authority")
    expected = {
        "git_path": CANONICAL_CONFIG_GIT_PATH,
        "mode": "committed_git_blob_exact",
    }
    if authority != expected:
        raise PilotResultError("schema-v2 config lacks its committed-Git authority")
    repo = Path(__file__).resolve().parents[2]
    try:
        process = subprocess.run(
            ["git", "show", f"HEAD:{CANONICAL_CONFIG_GIT_PATH}"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise PilotResultError("cannot read schema-v2 committed-Git authority") from exc
    if process.returncode != 0:
        raise PilotResultError("schema-v2 canonical config is not committed at HEAD")
    try:
        committed = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise PilotResultError("schema-v2 committed config is invalid JSON") from exc
    if committed != config:
        raise PilotResultError("schema-v2 config differs from the committed authority")


def validate_promotion_config(
    config: dict[str, Any], *, enforce_authority: bool = True
) -> list[dict[str, Any]]:
    schema_version = config.get("schema_version")
    if schema_version == 3:
        from round2_promotion_v3 import validate_config

        return validate_config(config, enforce_authority=enforce_authority)
    if schema_version not in {1, 2} or config.get("frozen_before_full_runs") is not True:
        raise PilotResultError("full-run config is not a frozen supported config")
    shared = config.get("shared")
    if not isinstance(shared, dict):
        raise PilotResultError("full-run config has no shared settings")
    try:
        batch_size = shared["batch_size"]
        gradient_accumulation = shared["gradient_accumulation"]
        global_batch = shared["global_batch"]
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (batch_size, gradient_accumulation, global_batch)
        ):
            raise ValueError
        derived_global_batch = batch_size * gradient_accumulation
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotResultError("invalid full-run batch settings") from exc
    if global_batch != 64 or derived_global_batch != 64:
        raise PilotResultError("full-run global batch must equal 64")
    for field in ("max_length", "seed", "logging_steps"):
        if (
            isinstance(shared.get(field), bool)
            or not isinstance(shared.get(field), int)
            or shared[field] < 1
        ):
            raise PilotResultError(f"invalid full-run shared field: {field}")
    for field in ("epochs", "warmup_ratio", "weight_decay"):
        if isinstance(shared.get(field), bool):
            raise PilotResultError(f"invalid full-run shared field: {field}")
        try:
            value = float(shared[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise PilotResultError(f"invalid full-run shared field: {field}") from exc
        if not math.isfinite(value) or value < 0 or (field != "weight_decay" and value == 0):
            raise PilotResultError(f"invalid full-run shared field: {field}")
    if float(shared["epochs"]) != 1.0:
        raise PilotResultError("full-run protocol requires exactly one epoch")
    if (
        shared.get("training_method") != "BF16 LoRA"
        or shared.get("completion_only_loss") is not True
    ):
        raise PilotResultError("full-run training method must be completion-only BF16 LoRA")
    dataset = config.get("dataset")
    validation = config.get("validation")
    if not isinstance(dataset, dict) or not isinstance(validation, dict):
        raise PilotResultError("full-run config has no dataset/validation binding")
    for label, section, row_field in (
        ("dataset", dataset, "artifact_rows"),
        ("validation", validation, "rows"),
    ):
        if not isinstance(section.get(row_field), int) or section[row_field] < 1:
            raise PilotResultError(f"invalid full-run {label} rows")
        if not re.fullmatch(r"[0-9a-f]{64}", str(section.get("fingerprint_sha256", ""))):
            raise PilotResultError(f"invalid full-run {label} fingerprint")
        if schema_version == 2 and not _is_sha256(section.get("manifest_sha256")):
            raise PilotResultError(f"invalid full-run {label} manifest binding")
    if shared.get("checkpoint_schedule") != "quarter_half_end":
        raise PilotResultError("full-run checkpoint schedule is not quarter/half/end")
    source_pilots = config.get("source_pilots")
    if not isinstance(source_pilots, dict):
        raise PilotResultError("full-run config has no source-pilot binding")
    for field in (
        "config_sha256",
        "results_sha256",
        "compiler_receipt_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(source_pilots.get(field, ""))):
            raise PilotResultError(f"full-run config has invalid source pilot {field}")
    if schema_version == 1:
        if (
            "canonical_gguf_semantic_evaluation" in source_pilots
            or "export_manifests" in source_pilots
            or config.get("training_gates")
            or "selection_protocol" in config
            or "source_code" in config
        ):
            raise PilotResultError("schema-v1 promotion cannot contain canonical GGUF evidence")
        evaluation = source_pilots.get("matched_prompt_evaluation")
        if (
            not isinstance(evaluation, dict)
            or evaluation.get("prompt_suite") != "judges"
            or not isinstance(evaluation.get("prompt_count"), int)
            or evaluation["prompt_count"] < 2
            or not re.fullmatch(r"[0-9a-f]{64}", str(evaluation.get("prompt_set_sha256", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(evaluation.get("tree_sha256", "")))
        ):
            raise PilotResultError("full-run config has no matched-prompt evaluation binding")
        if (
            not isinstance(evaluation.get("evaluated_pilot_ids"), list)
            or not isinstance(evaluation.get("evaluated_control_ids"), list)
            or len(evaluation["evaluated_control_ids"]) != 2
        ):
            raise PilotResultError("matched-prompt evaluation candidate binding is incomplete")
        for field in (
            "terminal_sha256",
            "artifact_inventory_sha256",
            "upstream_hf_control_sha256",
            "incumbent_gguf_control_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(evaluation.get(field, ""))):
                raise PilotResultError(f"matched-prompt evaluation has invalid {field}")
        evaluated_pilot_ids = set(evaluation["evaluated_pilot_ids"])
        canonical_evidence = None
        expected_export_ids: set[str] = set()
    else:
        canonical_evidence, expected_export_ids = _validate_canonical_config_evidence(
            config, source_pilots
        )
        evaluated_pilot_ids = set(canonical_evidence["evaluated_pilot_ids"])
        if json.dumps(shared, sort_keys=True, separators=(",", ":")) != json.dumps(
            CANONICAL_FULL_SHARED, sort_keys=True, separators=(",", ":")
        ):
            raise PilotResultError("schema-v2 shared treatment differs from frozen authority")
        if dataset != CANONICAL_DATA or validation != CANONICAL_VALIDATION:
            raise PilotResultError("schema-v2 dataset/validation differs from retained authority")

    candidates = config.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise PilotResultError("full-run config must contain exactly three candidates")
    expected = {
        "full-best-clean-private-enriched": ("clean", "include"),
        "full-best-warm-private-enriched": ("warm", "include"),
        "full-best-warm-rights-clean": ("warm", "exclude"),
    }
    if {candidate.get("id") for candidate in candidates} != set(expected):
        raise PilotResultError("full-run candidate treatment set is not exact")
    by_id = {candidate["id"]: candidate for candidate in candidates}
    for identifier, (lineage, policy) in expected.items():
        candidate = by_id[identifier]
        if candidate.get("lineage") != lineage or candidate.get("private_policy") != policy:
            raise PilotResultError(f"invalid treatment for {identifier}")
        source_id = candidate.get("source_pilot_id")
        if not isinstance(source_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", source_id):
            raise PilotResultError(f"invalid source pilot ID for {identifier}")
        if (
            not isinstance(candidate.get("selection_note"), str)
            or not candidate["selection_note"].strip()
        ):
            raise PilotResultError(f"missing selection note for {identifier}")
        if (
            not isinstance(candidate.get("rank"), int)
            or isinstance(candidate.get("rank"), bool)
            or candidate["rank"] < 1
        ):
            raise PilotResultError(f"invalid rank for {identifier}")
        try:
            learning_rate = float(candidate["learning_rate"])
            best_loss = float(candidate["source_pilot_best_dev_loss"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PilotResultError(f"invalid selected pilot metric for {identifier}") from exc
        if (
            learning_rate <= 0
            or not math.isfinite(learning_rate)
            or best_loss < 0
            or not math.isfinite(best_loss)
        ):
            raise PilotResultError(f"invalid selected pilot metric for {identifier}")
        for field in (
            "source_pilot_training_manifest_sha256",
            "source_pilot_adapter_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get(field, ""))):
                raise PilotResultError(f"invalid {field} for {identifier}")
        rows = candidate.get("planned_rows")
        steps = candidate.get("planned_steps")
        if not isinstance(rows, int) or rows < 1:
            raise PilotResultError(f"invalid planned rows for {identifier}")
        if steps != math.ceil(rows / global_batch):
            raise PilotResultError(f"invalid planned steps for {identifier}")
        if candidate.get("milestone_steps") != milestone_steps(steps):
            raise PilotResultError(f"invalid milestone schedule for {identifier}")
    artifact_rows = dataset["artifact_rows"]
    rights_clean_rows = dataset.get("rights_clean_rows")
    if (
        not isinstance(rights_clean_rows, int)
        or isinstance(rights_clean_rows, bool)
        or not 0 < rights_clean_rows < artifact_rows
    ):
        raise PilotResultError("invalid rights-clean dataset row count")
    if (
        by_id["full-best-clean-private-enriched"]["planned_rows"] != artifact_rows
        or by_id["full-best-warm-private-enriched"]["planned_rows"] != artifact_rows
        or by_id["full-best-warm-rights-clean"]["planned_rows"] != rights_clean_rows
    ):
        raise PilotResultError("candidate row counts do not match their private-data policies")
    clean_source_id = by_id["full-best-clean-private-enriched"]["source_pilot_id"]
    warm_source_id = by_id["full-best-warm-private-enriched"]["source_pilot_id"]
    if clean_source_id == warm_source_id:
        raise PilotResultError("clean and warm promotions cannot share one source pilot")
    selected_pilot_ids = {clean_source_id, warm_source_id}
    if (
        source_pilots.get("best_clean_id") != clean_source_id
        or source_pilots.get("best_warm_id") != warm_source_id
    ):
        raise PilotResultError("selected pilots do not match the source-pilot binding")
    if not selected_pilot_ids.issubset(evaluated_pilot_ids):
        raise PilotResultError("selected pilots are absent from matched-prompt evaluation")
    if schema_version == 2:
        if selected_pilot_ids != {CANONICAL_CLEAN_SELECTION, CANONICAL_WARM_SELECTION}:
            raise PilotResultError("schema-v2 selections differ from the frozen addendum")
        if expected_export_ids != evaluated_pilot_ids:
            raise PilotResultError("schema-v2 export/comparison pilot rosters differ")
        exports = source_pilots["export_manifests"]["pilots"]
        selected_by_pilot = {
            clean_source_id: by_id["full-best-clean-private-enriched"],
            warm_source_id: by_id["full-best-warm-private-enriched"],
        }
        for pilot_id, candidate in selected_by_pilot.items():
            export = exports[pilot_id]
            authority = CANONICAL_PILOT_AUTHORITY[pilot_id]
            if (
                candidate["source_pilot_adapter_sha256"] != export["adapter_tree_sha256"]
                or candidate["source_pilot_training_manifest_sha256"]
                != export["training_manifest_sha256"]
                or candidate["lineage"] != authority["lineage"]
                or candidate["rank"] != authority["rank"]
                or candidate["learning_rate"] != authority["learning_rate"]
                or candidate["source_pilot_best_dev_loss"] != authority["best_dev_loss"]
                or candidate["source_pilot_adapter_sha256"] != authority["adapter_sha256"]
                or candidate["source_pilot_training_manifest_sha256"]
                != authority["training_manifest_sha256"]
            ):
                raise PilotResultError(f"selected treatment/export binding changed: {pilot_id}")
        gates = config["training_gates"]
        smoke = gates["promotion_smoke"]
        if (
            dataset.get("manifest_sha256") != smoke["train_manifest_sha256"]
            or validation.get("manifest_sha256") != smoke["validation_manifest_sha256"]
            or dataset["fingerprint_sha256"] != smoke["train_fingerprint_sha256"]
            or validation["fingerprint_sha256"] != smoke["validation_fingerprint_sha256"]
        ):
            raise PilotResultError("schema-v2 dataset/validation training-gate binding changed")
    warm = by_id["full-best-warm-private-enriched"]
    rights_clean = by_id["full-best-warm-rights-clean"]
    for field in (
        "source_pilot_id",
        "source_pilot_training_manifest_sha256",
        "source_pilot_adapter_sha256",
        "source_pilot_best_dev_loss",
        "lineage",
        "rank",
        "learning_rate",
    ):
        if warm.get(field) != rights_clean.get(field):
            raise PilotResultError(f"rights-clean ablation changes warm field: {field}")
    if schema_version == 2:
        expected_authority = {
            "git_path": CANONICAL_CONFIG_GIT_PATH,
            "mode": "committed_git_blob_exact",
        }
        if config.get("frozen_authority") != expected_authority:
            raise PilotResultError("schema-v2 config lacks its committed-Git authority")
        if enforce_authority:
            _verify_v2_committed_authority(config)
    return candidates


def build_promotion_config(
    *,
    pilot_config_path: Path,
    pilot_results_path: Path,
    pilot_evaluation_dir: Path,
    best_clean_id: str,
    best_warm_id: str,
    rights_clean_rows: int,
    clean_selection_note: str,
    warm_selection_note: str,
    batch_size: int = 64,
    gradient_accumulation: int = 1,
) -> dict[str, Any]:
    pilot_config_path = pilot_config_path.resolve()
    pilot_results_path = pilot_results_path.resolve()
    pilot_config = _read_object(pilot_config_path)
    validate_pilot_config(pilot_config)
    results = _read_object(pilot_results_path)
    if results.get("schema_version") != 1:
        raise PilotResultError("pilot result schema_version must be 1")
    if results.get("campaign_id") != pilot_config.get("campaign_id"):
        raise PilotResultError("pilot result campaign does not match pilot config")
    if results.get("source", {}).get("pilot_config_sha256") != sha256_file(pilot_config_path):
        raise PilotResultError("pilot results do not bind the supplied pilot config")
    compiler_receipt_path = pilot_results_path.parent / "compiler-receipt.json"
    compiler_receipt = _read_object(compiler_receipt_path)
    result_receipt = compiler_receipt.get("artifacts", {}).get(pilot_results_path.name, {})
    if result_receipt.get("bytes") != pilot_results_path.stat().st_size or result_receipt.get(
        "sha256"
    ) != sha256_file(pilot_results_path):
        raise PilotResultError("compiler receipt does not bind the supplied pilot results")
    compiler_script = Path(__file__).resolve().parent / "compile_round2_pilots.py"
    compiler_git = compiler_receipt.get("git")
    if (
        compiler_receipt.get("compiler", {}).get("sha256") != sha256_file(compiler_script)
        or not isinstance(compiler_git, dict)
        or compiler_git.get("available") is not True
        or compiler_git.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40,64}", str(compiler_git.get("commit", "")))
    ):
        raise PilotResultError("pilot results were not produced by this clean exact compiler")
    config_ids = {candidate["id"] for candidate in pilot_config["candidates"]}
    result_ids = [row.get("candidate_id") for row in results.get("rows", [])]
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != config_ids:
        raise PilotResultError("pilot results do not contain the exact configured candidate set")
    if any(row.get("status") != "complete" for row in results["rows"]):
        raise PilotResultError("every configured pilot must complete before promotion")
    evaluation_receipt = verify_pilot_evaluation(
        pilot_evaluation_dir,
        pilot_config=pilot_config,
        pilot_results=results,
    )
    if not clean_selection_note.strip() or not warm_selection_note.strip():
        raise PilotResultError("both selections require a non-empty provenance note")
    if batch_size < 1 or gradient_accumulation < 1:
        raise PilotResultError("batch settings must be positive")
    global_batch = batch_size * gradient_accumulation
    if global_batch != 64:
        raise PilotResultError("full-run global batch must equal 64")

    full_rows = pilot_config["dataset"].get("rows")
    if not isinstance(full_rows, int) or full_rows < 1:
        raise PilotResultError("pilot config has no full dataset row count")
    if not 0 < rights_clean_rows < full_rows:
        raise PilotResultError("rights-clean rows must be positive and below full rows")
    clean = _selected_result(results, candidate_id=best_clean_id, expected_lineage="clean")
    warm = _selected_result(results, candidate_id=best_warm_id, expected_lineage="warm")
    configured = {candidate["id"]: candidate for candidate in pilot_config["candidates"]}
    for selected in (clean, warm):
        treatment = configured[selected["candidate_id"]]
        for field in ("lineage", "rank", "learning_rate"):
            if selected.get(field) != treatment.get(field):
                raise PilotResultError(
                    f"selected pilot result changes frozen treatment field: {field}"
                )

    shared_pilot = pilot_config["shared"]
    candidates = [
        _candidate(
            identifier="full-best-clean-private-enriched",
            source=clean,
            private_policy="include",
            planned_rows=full_rows,
            global_batch=global_batch,
            selection_note=clean_selection_note.strip(),
        ),
        _candidate(
            identifier="full-best-warm-private-enriched",
            source=warm,
            private_policy="include",
            planned_rows=full_rows,
            global_batch=global_batch,
            selection_note=warm_selection_note.strip(),
        ),
        _candidate(
            identifier="full-best-warm-rights-clean",
            source=warm,
            private_policy="exclude",
            planned_rows=rights_clean_rows,
            global_batch=global_batch,
            selection_note=(
                "Rights-clean ablation of selected warm pilot; identical hyperparameters with "
                "private sources excluded."
            ),
        ),
    ]
    promotion = {
        "schema_version": 1,
        "campaign_id": f"{pilot_config['campaign_id']}-full",
        "frozen_before_full_runs": True,
        "source_pilots": {
            "config_path": str(pilot_config_path),
            "config_sha256": sha256_file(pilot_config_path),
            "results_path": str(pilot_results_path),
            "results_sha256": sha256_file(pilot_results_path),
            "compiler_receipt_path": str(compiler_receipt_path.resolve()),
            "compiler_receipt_sha256": sha256_file(compiler_receipt_path),
            "best_clean_id": best_clean_id,
            "best_warm_id": best_warm_id,
            "pilot_result_warnings": results.get("warnings", []),
            "pilot_environment_groups": results.get("environment_groups", {}),
            "matched_prompt_evaluation": evaluation_receipt,
        },
        "dataset": {
            "artifact_rows": full_rows,
            "fingerprint_sha256": pilot_config["dataset"]["fingerprint_sha256"],
            "rights_clean_rows": rights_clean_rows,
        },
        "validation": pilot_config["validation"],
        "shared": {
            "training_method": shared_pilot["training_method"],
            "max_length": shared_pilot["max_length"],
            "epochs": 1.0,
            "batch_size": batch_size,
            "gradient_accumulation": gradient_accumulation,
            "global_batch": global_batch,
            "warmup_ratio": shared_pilot["warmup_ratio"],
            "weight_decay": shared_pilot["weight_decay"],
            "seed": shared_pilot["seed"],
            "logging_steps": max(10, math.ceil(full_rows / global_batch / 100)),
            "checkpoint_schedule": "quarter_half_end",
            "completion_only_loss": True,
        },
        "candidates": candidates,
    }
    validate_promotion_config(promotion)
    return promotion


def _load_verified_pilot_inputs(
    pilot_config_path: Path,
    pilot_results_path: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any], Path]:
    """Load the immutable pilot table and retain the legacy compiler checks."""
    pilot_config_path = pilot_config_path.resolve()
    pilot_results_path = pilot_results_path.resolve()
    pilot_config = _read_object(pilot_config_path)
    validate_pilot_config(pilot_config)
    results = _read_object(pilot_results_path)
    if results.get("schema_version") != 1:
        raise PilotResultError("pilot result schema_version must be 1")
    if results.get("campaign_id") != pilot_config.get("campaign_id"):
        raise PilotResultError("pilot result campaign does not match pilot config")
    if results.get("source", {}).get("pilot_config_sha256") != sha256_file(pilot_config_path):
        raise PilotResultError("pilot results do not bind the supplied pilot config")
    compiler_receipt_path = pilot_results_path.parent / "compiler-receipt.json"
    compiler_receipt = _read_object(compiler_receipt_path)
    result_receipt = compiler_receipt.get("artifacts", {}).get(pilot_results_path.name, {})
    if result_receipt.get("bytes") != pilot_results_path.stat().st_size or result_receipt.get(
        "sha256"
    ) != sha256_file(pilot_results_path):
        raise PilotResultError("compiler receipt does not bind the supplied pilot results")
    compiler_script = Path(__file__).resolve().parent / "compile_round2_pilots.py"
    compiler_git = compiler_receipt.get("git")
    if (
        compiler_receipt.get("compiler", {}).get("sha256") != sha256_file(compiler_script)
        or not isinstance(compiler_git, dict)
        or compiler_git.get("available") is not True
        or compiler_git.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40,64}", str(compiler_git.get("commit", "")))
    ):
        raise PilotResultError("pilot results were not produced by this clean exact compiler")
    config_ids = {candidate["id"] for candidate in pilot_config["candidates"]}
    result_ids = [row.get("candidate_id") for row in results.get("rows", [])]
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != config_ids:
        raise PilotResultError("pilot results do not contain the exact configured candidate set")
    if any(row.get("status") != "complete" for row in results["rows"]):
        raise PilotResultError("every configured pilot must complete before promotion")
    return (
        pilot_config_path,
        pilot_results_path,
        pilot_config,
        results,
        compiler_receipt_path,
    )


def _canonical_treatments(
    *,
    pilot_config: dict[str, Any],
    results: dict[str, Any],
    best_clean_id: str,
    best_warm_id: str,
    rights_clean_rows: int,
    clean_selection_note: str,
    warm_selection_note: str,
    batch_size: int,
    gradient_accumulation: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not clean_selection_note.strip() or not warm_selection_note.strip():
        raise PilotResultError("both selections require a non-empty provenance note")
    if batch_size != 64 or gradient_accumulation != 1:
        raise PilotResultError("canonical full runs require the frozen 64 x 1 batch split")
    global_batch = batch_size * gradient_accumulation
    full_rows = pilot_config["dataset"].get("rows")
    if not isinstance(full_rows, int) or full_rows < 1:
        raise PilotResultError("pilot config has no full dataset row count")
    if not 0 < rights_clean_rows < full_rows:
        raise PilotResultError("rights-clean rows must be positive and below full rows")
    clean = _selected_result(results, candidate_id=best_clean_id, expected_lineage="clean")
    warm = _selected_result(results, candidate_id=best_warm_id, expected_lineage="warm")
    configured = {candidate["id"]: candidate for candidate in pilot_config["candidates"]}
    for selected in (clean, warm):
        treatment = configured[selected["candidate_id"]]
        for field in ("lineage", "rank", "learning_rate"):
            if selected.get(field) != treatment.get(field):
                raise PilotResultError(
                    f"selected pilot result changes frozen treatment field: {field}"
                )
    candidates = [
        _candidate(
            identifier="full-best-clean-private-enriched",
            source=clean,
            private_policy="include",
            planned_rows=full_rows,
            global_batch=global_batch,
            selection_note=clean_selection_note.strip(),
        ),
        _candidate(
            identifier="full-best-warm-private-enriched",
            source=warm,
            private_policy="include",
            planned_rows=full_rows,
            global_batch=global_batch,
            selection_note=warm_selection_note.strip(),
        ),
        _candidate(
            identifier="full-best-warm-rights-clean",
            source=warm,
            private_policy="exclude",
            planned_rows=rights_clean_rows,
            global_batch=global_batch,
            selection_note=(
                "Rights-clean ablation of selected warm pilot; identical hyperparameters with "
                "private sources excluded."
            ),
        ),
    ]
    shared = dict(CANONICAL_FULL_SHARED)
    return candidates, shared


def build_canonical_gguf_promotion_config(
    *,
    pilot_config_path: Path,
    pilot_results_path: Path,
    canonical_comparison_dir: Path,
    export_root: Path,
    hardened_resume_verification: Path,
    promotion_smoke_dir: Path,
    best_clean_id: str,
    best_warm_id: str,
    rights_clean_rows: int,
    clean_selection_note: str,
    warm_selection_note: str,
    batch_size: int = 64,
    gradient_accumulation: int = 1,
) -> dict[str, Any]:
    """Freeze the addendum's treatments from the canonical matched-GGUF evidence."""
    if best_clean_id != CANONICAL_CLEAN_SELECTION or best_warm_id != CANONICAL_WARM_SELECTION:
        raise PilotResultError(
            "canonical promotion selections differ from the frozen full-data addendum"
        )
    (
        pilot_config_path,
        pilot_results_path,
        pilot_config,
        results,
        compiler_receipt_path,
    ) = _load_verified_pilot_inputs(pilot_config_path, pilot_results_path)
    _verify_canonical_pilot_authority(
        pilot_config_path=pilot_config_path,
        pilot_results_path=pilot_results_path,
        compiler_receipt_path=compiler_receipt_path,
        pilot_config=pilot_config,
        pilot_results=results,
    )
    comparison = verify_canonical_gguf_semantic_evidence(
        canonical_comparison_dir,
        pilot_config=pilot_config,
    )
    exports = verify_export_manifests(
        export_root,
        pilot_config=pilot_config,
        pilot_results=results,
        comparison_receipt=comparison,
    )
    hardened_resume = verify_hardened_resume_evidence(
        hardened_resume_verification,
        pilot_config=pilot_config,
    )
    promotion_smoke = verify_promotion_smoke_run(
        promotion_smoke_dir,
        pilot_config=pilot_config,
    )
    for field in (
        "trainer_sha256",
        "train_fingerprint_sha256",
        "validation_fingerprint_sha256",
        "train_manifest_sha256",
        "validation_manifest_sha256",
    ):
        if hardened_resume.get(field) != promotion_smoke.get(field):
            raise PilotResultError(
                f"smoke/resume evidence does not share exact trainer/input field: {field}"
            )
    if promotion_smoke["lineage_receipt_sha256"] not in {
        hardened_resume["clean_lineage_sha256"],
        hardened_resume["warm_lineage_sha256"],
    }:
        raise PilotResultError("promotion smoke lineage was not exercised by resume hardening")
    candidates, shared = _canonical_treatments(
        pilot_config=pilot_config,
        results=results,
        best_clean_id=best_clean_id,
        best_warm_id=best_warm_id,
        rights_clean_rows=rights_clean_rows,
        clean_selection_note=clean_selection_note,
        warm_selection_note=warm_selection_note,
        batch_size=batch_size,
        gradient_accumulation=gradient_accumulation,
    )
    full_rows = pilot_config["dataset"]["rows"]
    promotion = {
        "schema_version": 2,
        "campaign_id": f"{pilot_config['campaign_id']}-full",
        "frozen_before_full_runs": True,
        "selection_protocol": "canonical_matched_gguf_semantic_addendum_v1",
        "frozen_authority": {
            "git_path": CANONICAL_CONFIG_GIT_PATH,
            "mode": "committed_git_blob_exact",
        },
        "source_pilots": {
            "config_path": str(pilot_config_path),
            "config_sha256": sha256_file(pilot_config_path),
            "results_path": str(pilot_results_path),
            "results_sha256": sha256_file(pilot_results_path),
            "compiler_receipt_path": str(compiler_receipt_path.resolve()),
            "compiler_receipt_sha256": sha256_file(compiler_receipt_path),
            "best_clean_id": best_clean_id,
            "best_warm_id": best_warm_id,
            "pilot_result_warnings": results.get("warnings", []),
            "pilot_environment_groups": results.get("environment_groups", {}),
            "canonical_gguf_semantic_evaluation": comparison,
            "export_manifests": exports,
        },
        "training_gates": {
            "hardened_interruption_resume": hardened_resume,
            "promotion_smoke": promotion_smoke,
        },
        "source_code": {
            "promotion_builder_sha256": sha256_file(Path(__file__).resolve()),
            "full_launcher_sha256": sha256_file(
                Path(__file__).resolve().parent / "launch_round2_full.py"
            ),
            "trainer_sha256": sha256_file(Path(__file__).resolve().parent / "train_lora_round2.py"),
            "campaign_io_sha256": sha256_file(Path(__file__).resolve().parent / "campaign_io.py"),
            "train_lora_sha256": sha256_file(Path(__file__).resolve().parent / "train_lora.py"),
        },
        "runtime_input_authority": copy.deepcopy(CANONICAL_RUNTIME_INPUT_AUTHORITY),
        "dataset": {
            "artifact_rows": full_rows,
            "fingerprint_sha256": pilot_config["dataset"]["fingerprint_sha256"],
            "manifest_sha256": promotion_smoke["train_manifest_sha256"],
            "rights_clean_rows": rights_clean_rows,
        },
        "validation": {
            **pilot_config["validation"],
            "manifest_sha256": promotion_smoke["validation_manifest_sha256"],
        },
        "shared": shared,
        "candidates": candidates,
    }
    validate_promotion_config(promotion, enforce_authority=False)
    return promotion


def write_frozen_config(output: Path, config: dict[str, Any]) -> dict[str, Any]:
    validate_promotion_config(config, enforce_authority=False)
    output = output.resolve()
    expected_v2_output = Path(__file__).resolve().parents[2] / CANONICAL_CONFIG_GIT_PATH
    if config.get("schema_version") == 2 and output != expected_v2_output:
        raise PilotResultError(
            f"schema-v2 canonical config must be written to {expected_v2_output}"
        )
    receipt_path = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or receipt_path.exists():
        raise FileExistsError(f"promotion config or receipt already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, output)
    digest = sha256_file(output)
    with receipt_path.open("x", encoding="ascii") as handle:
        handle.write(f"{digest}  {output.name}\n")
    return {"path": str(output), "bytes": output.stat().st_size, "sha256": digest}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-config", type=Path, required=True)
    parser.add_argument("--pilot-results", type=Path, required=True)
    evidence = parser.add_mutually_exclusive_group(required=True)
    evidence.add_argument("--pilot-evaluation-dir", type=Path)
    evidence.add_argument("--canonical-comparison-dir", type=Path)
    parser.add_argument("--export-root", type=Path)
    parser.add_argument("--hardened-resume-verification", type=Path)
    parser.add_argument("--promotion-smoke-dir", type=Path)
    parser.add_argument("--current-smoke-dir", type=Path)
    parser.add_argument("--current-resume-dir", type=Path)
    parser.add_argument("--interruption-receipt", type=Path)
    parser.add_argument("--best-clean-id", required=True)
    parser.add_argument("--best-warm-id", required=True)
    parser.add_argument("--rights-clean-rows", type=int)
    parser.add_argument("--clean-selection-note", required=True)
    parser.add_argument("--warm-selection-note", required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--gradient-accumulation", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    current_fields = (args.current_smoke_dir, args.current_resume_dir, args.interruption_receipt)
    if any(value is not None for value in current_fields):
        if (
            any(value is None for value in current_fields)
            or args.canonical_comparison_dir is None
            or args.export_root is None
            or args.hardened_resume_verification is not None
            or args.promotion_smoke_dir is not None
            or args.rights_clean_rows is not None
        ):
            parser.error(
                "v3 requires all current gate arguments plus canonical comparison/export; no legacy gates or exclusion rows"
            )
        return args
    if args.rights_clean_rows is None:
        parser.error("legacy v1/v2 requires --rights-clean-rows")
    canonical_fields = (
        args.export_root,
        args.hardened_resume_verification,
        args.promotion_smoke_dir,
    )
    if args.canonical_comparison_dir is not None and any(
        value is None for value in canonical_fields
    ):
        parser.error(
            "canonical GGUF evidence requires --export-root, "
            "--hardened-resume-verification, and --promotion-smoke-dir"
        )
    if args.pilot_evaluation_dir is not None and any(
        value is not None for value in canonical_fields
    ):
        parser.error("legacy PEFT evidence cannot be mixed with canonical GGUF gate arguments")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    common = {
        "pilot_config_path": args.pilot_config,
        "pilot_results_path": args.pilot_results,
        "best_clean_id": args.best_clean_id,
        "best_warm_id": args.best_warm_id,
        "rights_clean_rows": args.rights_clean_rows,
        "clean_selection_note": args.clean_selection_note,
        "warm_selection_note": args.warm_selection_note,
        "batch_size": args.batch_size,
        "gradient_accumulation": args.gradient_accumulation,
    }
    if args.current_smoke_dir is not None:
        from round2_promotion_v3 import build_config

        common.pop("rights_clean_rows")
        config = build_config(
            canonical_comparison_dir=args.canonical_comparison_dir,
            export_root=args.export_root,
            current_smoke_dir=args.current_smoke_dir,
            current_resume_dir=args.current_resume_dir,
            interruption_receipt=args.interruption_receipt,
            **common,
        )
    elif args.canonical_comparison_dir is not None:
        config = build_canonical_gguf_promotion_config(
            canonical_comparison_dir=args.canonical_comparison_dir,
            export_root=args.export_root,
            hardened_resume_verification=args.hardened_resume_verification,
            promotion_smoke_dir=args.promotion_smoke_dir,
            **common,
        )
    else:
        config = build_promotion_config(
            pilot_evaluation_dir=args.pilot_evaluation_dir,
            **common,
        )
    print(json.dumps(write_frozen_config(args.output, config), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
