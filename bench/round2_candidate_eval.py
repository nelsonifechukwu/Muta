#!/usr/bin/env python3
"""Provenance-complete, deterministic evaluation of Muta round-two candidates.

The candidate manifest supports three backends:

* ``hf``: an unmodified local Hugging Face model directory (the upstream control),
* ``peft``: a local base model plus a LoRA adapter directory (new candidates), and
* ``gguf``: an exact GGUF plus an exact llama-server binary (the incumbent control).

Every candidate receives the same frozen prompt objects in the same order.  The
output directory must not already exist; a partial run is evidence, not something
this program silently resumes or appends to.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 compatibility
    from typing_extensions import Self

from bench.judges_prompt_report import evaluate as evaluate_judge_rows
from bench.judges_prompt_report import grade as grade_judge_prompt
from bench.judges_prompt_report import write_csv as write_judge_csv
from bench.judges_prompt_suite import prompts as judge_prompts
from bench.run_stem_prompt_suite import selected_option
from bench.stem_prompt_suite import prompts as stem_prompts

SCHEMA_VERSION = 1
SEED = 3407
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class EvaluationInputError(ValueError):
    """Raised before inference when frozen evaluation inputs are invalid."""


@dataclass(frozen=True)
class EvalPrompt:
    id: str
    suite: str
    title: str
    source: str
    subject: str
    format: str
    text: str
    expected: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    reasoning_content: str
    finish_reason: str
    generated_tokens: int
    raw_bytes: bytes
    raw_media_type: str
    backend_details: dict[str, Any]


class Backend(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def generate(self, prompt: EvalPrompt, *, max_new_tokens: int) -> GenerationResult: ...


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def write_json_exclusive(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_bytes_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def tree_identity(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_dir():
        raise EvaluationInputError(f"artifact directory does not exist: {path}")
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise EvaluationInputError(f"artifact identity refuses symlink: {child}")
        if child.is_file():
            files.append(
                {
                    "path": child.relative_to(path).as_posix(),
                    "bytes": child.stat().st_size,
                    "sha256": sha256_file(child),
                }
            )
    if not files:
        raise EvaluationInputError(f"artifact directory is empty: {path}")
    tree_sha = sha256_bytes(
        "\n".join(f"{row['sha256']}  {row['path']}" for row in files).encode("utf-8")
    )
    return {
        "path": str(path),
        "file_count": len(files),
        "bytes": sum(row["bytes"] for row in files),
        "tree_sha256": tree_sha,
        "files": files,
    }


def file_identity(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise EvaluationInputError(f"artifact file does not exist: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def output_inventory(root: Path) -> dict[str, Any]:
    """Inventory the finished evidence files before the inventory and terminal receipt exist."""
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "file_count": len(files),
        "bytes": sum(row["bytes"] for row in files),
        "files": files,
    }


def prompt_suite(name: str) -> list[EvalPrompt]:
    if name == "judges":
        return [
            EvalPrompt(
                id=row.id,
                suite="judges",
                title=row.title,
                source=row.source,
                subject="mixed",
                format="written",
                text=row.text,
                expected="rubric",
            )
            for row in judge_prompts()
        ]
    if name == "stem":
        return [
            EvalPrompt(
                id=row.id,
                suite="stem",
                title=row.id,
                source="Muta fixed STEM battery",
                subject=row.subject,
                format=row.format,
                text=row.text,
                expected=row.expected,
            )
            for row in stem_prompts()
        ]
    raise EvaluationInputError(f"unknown prompt suite: {name}")


def select_prompts(name: str, requested: list[str] | None) -> list[EvalPrompt]:
    available = prompt_suite(name)
    if requested:
        if len(requested) != len(set(requested)):
            raise EvaluationInputError("duplicate --prompt-id values")
        by_id = {row.id: row for row in available}
        unknown = sorted(set(requested) - set(by_id))
        if unknown:
            raise EvaluationInputError(f"unknown prompt IDs: {unknown}")
        selected = [by_id[prompt_id] for prompt_id in requested]
    else:
        selected = available
    if len(selected) < 2:
        raise EvaluationInputError("at least two identical prompts per candidate are required")
    return selected


def _resolve_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise EvaluationInputError(f"candidate has no {label}")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_candidate_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(f"cannot read candidate manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise EvaluationInputError("candidate manifest root is not an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise EvaluationInputError(f"candidate manifest schema must be {SCHEMA_VERSION}")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise EvaluationInputError("candidate manifest has no candidates")
    ids: set[str] = set()
    resolved = []
    for raw in candidates:
        if not isinstance(raw, dict):
            raise EvaluationInputError("candidate entry is not an object")
        candidate = dict(raw)
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not SAFE_ID.fullmatch(candidate_id):
            raise EvaluationInputError(f"unsafe candidate id: {candidate_id!r}")
        if candidate_id in ids:
            raise EvaluationInputError(f"duplicate candidate id: {candidate_id}")
        ids.add(candidate_id)
        backend = candidate.get("backend")
        if backend not in {"hf", "peft", "gguf"}:
            raise EvaluationInputError(f"unsupported backend for {candidate_id}: {backend!r}")
        fields = {
            "hf": ("model", "tokenizer"),
            "peft": ("base_model", "adapter", "tokenizer"),
            "gguf": ("model", "server"),
        }[backend]
        for field in fields:
            candidate[field] = str(_resolve_path(path.parent, candidate.get(field), field))
        expected = candidate.get("expected")
        if not isinstance(expected, dict):
            raise EvaluationInputError(f"candidate {candidate_id} has no expected hashes")
        resolved.append(candidate)
    return {
        **payload,
        "manifest_path": str(path),
        "manifest_sha256": sha256_file(path),
        "candidates": resolved,
    }


def verify_candidate(
    candidate: dict[str, Any], cache: dict[tuple[str, str], dict[str, Any]]
) -> dict[str, Any]:
    backend = candidate["backend"]
    expected = candidate["expected"]
    observed: dict[str, Any] = {}
    requirements = {
        "hf": (
            ("model", "tree", "model_tree_sha256"),
            ("tokenizer", "tree", "tokenizer_tree_sha256"),
        ),
        "peft": (
            ("base_model", "tree", "base_model_tree_sha256"),
            ("adapter", "tree", "adapter_tree_sha256"),
            ("tokenizer", "tree", "tokenizer_tree_sha256"),
        ),
        "gguf": (
            ("model", "file", "model_sha256"),
            ("server", "file", "server_sha256"),
        ),
    }[backend]
    for field, kind, hash_key in requirements:
        expected_hash = expected.get(hash_key)
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise EvaluationInputError(
                f"candidate {candidate['id']} has invalid expected.{hash_key}"
            )
        path = Path(candidate[field])
        cache_key = (kind, str(path))
        if cache_key not in cache:
            cache[cache_key] = tree_identity(path) if kind == "tree" else file_identity(path)
        identity = cache[cache_key]
        actual_hash = identity["tree_sha256"] if kind == "tree" else identity["sha256"]
        if actual_hash != expected_hash:
            raise EvaluationInputError(
                f"candidate {candidate['id']} {field} hash mismatch: "
                f"{actual_hash} != {expected_hash}"
            )
        observed[field] = identity
    if backend == "peft":
        adapter_files = {row["path"]: row["sha256"] for row in observed["adapter"].get("files", [])}
        required_adapter_files = {"adapter_model.safetensors", "adapter_config.json"}
        if not required_adapter_files.issubset(adapter_files):
            raise EvaluationInputError(
                f"candidate {candidate['id']} adapter lacks weights or adapter_config.json"
            )
    return {
        "candidate_id": candidate["id"],
        "backend": backend,
        "expected": expected,
        "observed": observed,
        "metadata": candidate.get("metadata", {}),
    }


def candidate_content_sha256(identity: dict[str, Any]) -> str:
    """Identify model weights without host paths, labels, tokenizer, or serving binary."""
    observed = identity["observed"]
    if identity["backend"] == "gguf":
        return observed["model"]["sha256"]
    if identity["backend"] == "hf":
        return observed["model"]["tree_sha256"]
    return sha256_bytes(
        canonical_bytes(
            {
                "backend": "peft",
                "base_model_tree_sha256": observed["base_model"]["tree_sha256"],
                "adapter_model_sha256": next(
                    row["sha256"]
                    for row in observed["adapter"]["files"]
                    if row["path"] == "adapter_model.safetensors"
                ),
                "adapter_config_sha256": next(
                    row["sha256"]
                    for row in observed["adapter"]["files"]
                    if row["path"] == "adapter_config.json"
                ),
            }
        )
    )


def candidate_identity_kind(backend: str) -> str:
    return {
        "gguf": "gguf_file_sha256",
        "hf": "huggingface_model_tree_sha256",
        "peft": "sha256_of_base_tree_adapter_weights_and_config",
    }[backend]


def validate_generation_result(result: Any) -> GenerationResult:
    if not isinstance(result, GenerationResult):
        raise TypeError("backend did not return GenerationResult")
    for field in ("answer", "reasoning_content", "finish_reason", "raw_media_type"):
        if not isinstance(getattr(result, field), str):
            raise TypeError(f"generation {field} is not text")
    if (
        isinstance(result.generated_tokens, bool)
        or not isinstance(result.generated_tokens, int)
        or result.generated_tokens < 0
    ):
        raise TypeError("generation token count is not a non-negative integer")
    if not isinstance(result.raw_bytes, bytes) or not result.raw_bytes:
        raise TypeError("generation raw output is not non-empty bytes")
    if not isinstance(result.backend_details, dict):
        raise TypeError("generation backend details are not an object")
    return result


def request_bytes(url: str, payload: dict[str, Any] | None, timeout: float) -> bytes:
    data = canonical_bytes(payload) if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class GGUFBackend:
    def __init__(
        self,
        candidate: dict[str, Any],
        candidate_dir: Path,
        *,
        port: int,
        gpu_layers: int,
        threads: int,
        context_size: int,
    ) -> None:
        self.candidate = candidate
        self.candidate_dir = candidate_dir
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.command = [
            candidate["server"],
            "--model",
            candidate["model"],
            "--alias",
            candidate["id"],
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ctx-size",
            str(context_size),
            "--threads",
            str(threads),
            "--n-gpu-layers",
            str(gpu_layers),
            "--parallel",
            "1",
            "--cache-ram",
            "256",
            "--jinja",
        ]

    def __enter__(self) -> Self:
        log_path = self.candidate_dir / "backend.log"
        self.log_handle = log_path.open("xb")
        try:
            self.process = subprocess.Popen(
                self.command,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f"llama-server exited with status {self.process.returncode}")
                try:
                    payload = json.loads(request_bytes(f"{self.base_url}/health", None, 2))
                    if payload.get("status") in {"ok", "no slot available"}:
                        return self
                except (OSError, TimeoutError, json.JSONDecodeError):
                    pass
                time.sleep(1)
            raise TimeoutError("llama-server did not become ready within 300 seconds")
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        if self.log_handle is not None:
            self.log_handle.close()

    def generate(self, prompt: EvalPrompt, *, max_new_tokens: int) -> GenerationResult:
        request = {
            "model": self.candidate["id"],
            "messages": [{"role": "user", "content": prompt.text}],
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": SEED,
            "max_tokens": max_new_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        raw = request_bytes(f"{self.base_url}/v1/chat/completions", request, 1800)
        response = json.loads(raw)
        choice = response["choices"][0]
        message = choice["message"]
        usage = response.get("usage") or {}
        return GenerationResult(
            answer=message.get("content", ""),
            reasoning_content=message.get("reasoning_content", ""),
            finish_reason=choice.get("finish_reason") or "unknown",
            generated_tokens=int(usage.get("completion_tokens") or 0),
            raw_bytes=raw,
            raw_media_type="application/json; source=llama-server-http-body",
            backend_details={"request": request, "command": self.command},
        )


class HuggingFaceBackend:
    def __init__(self, candidate: dict[str, Any], *, context_size: int) -> None:
        self.candidate = candidate
        self.context_size = context_size
        self.model: Any = None
        self.tokenizer: Any = None
        self.torch: Any = None

    def __enter__(self) -> Self:
        try:
            return self._load()
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def _load(self) -> Self:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        torch.manual_seed(SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(SEED)
            torch.cuda.reset_peak_memory_stats()
        torch.use_deterministic_algorithms(True)
        if hasattr(torch.backends, "cuda"):
            torch.backends.cuda.matmul.allow_tf32 = False
        if hasattr(torch.backends, "cudnn"):
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True

        tokenizer_path = self.candidate["tokenizer"]
        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_path,
            local_files_only=True,
            fix_mistral_regex=True,
        )
        model_path = (
            self.candidate["model"]
            if self.candidate["backend"] == "hf"
            else self.candidate["base_model"]
        )
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            local_files_only=True,
            torch_dtype=dtype,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        if self.candidate["backend"] == "peft":
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(
                self.model,
                self.candidate["adapter"],
                local_files_only=True,
                is_trainable=False,
            )
        self.model.eval()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.model = None
        self.tokenizer = None
        if self.torch is not None and self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()

    def generate(self, prompt: EvalPrompt, *, max_new_tokens: int) -> GenerationResult:
        torch = self.torch
        messages = [{"role": "user", "content": prompt.text}]
        rendered = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        encoded = self.tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
        device = self.model.get_input_embeddings().weight.device
        encoded = {key: value.to(device) for key, value in encoded.items()}
        input_length = int(encoded["input_ids"].shape[-1])
        if input_length + max_new_tokens > self.context_size:
            raise RuntimeError(
                f"prompt {prompt.id} needs {input_length + max_new_tokens} tokens, "
                f"above context {self.context_size}"
            )
        started = time.monotonic()
        with torch.inference_mode():
            output = self.model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                num_beams=1,
                use_cache=True,
                pad_token_id=(
                    self.tokenizer.pad_token_id
                    if self.tokenizer.pad_token_id is not None
                    else self.tokenizer.eos_token_id
                ),
                eos_token_id=self.tokenizer.eos_token_id,
            )
        token_ids = output[0, input_length:].detach().cpu().tolist()
        answer = self.tokenizer.decode(token_ids, skip_special_tokens=True)
        finish_reason = "length" if len(token_ids) >= max_new_tokens else "stop"
        raw_payload = {
            "prompt_rendered": rendered,
            "prompt_token_ids": encoded["input_ids"][0].detach().cpu().tolist(),
            "generated_token_ids": token_ids,
            "decoded_continuation": answer,
        }
        return GenerationResult(
            answer=answer,
            reasoning_content="",
            finish_reason=finish_reason,
            generated_tokens=len(token_ids),
            raw_bytes=canonical_bytes(raw_payload),
            raw_media_type="application/json; source=transformers-token-output",
            backend_details={
                "generation": {
                    "max_new_tokens": max_new_tokens,
                    "do_sample": False,
                    "num_beams": 1,
                    "seed": SEED,
                },
                "runtime": {
                    "device": str(device),
                    "model_dtype": str(self.model.get_input_embeddings().weight.dtype),
                    "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                },
                "generation_wall_s": round(time.monotonic() - started, 6),
            },
        )


def make_backend(
    candidate: dict[str, Any],
    candidate_dir: Path,
    *,
    port: int,
    gpu_layers: int,
    threads: int,
    context_size: int,
) -> Backend:
    if candidate["backend"] == "gguf":
        return GGUFBackend(
            candidate,
            candidate_dir,
            port=port,
            gpu_layers=gpu_layers,
            threads=threads,
            context_size=context_size,
        )
    return HuggingFaceBackend(candidate, context_size=context_size)


def _runtime_receipt() -> dict[str, Any]:
    packages = {}
    for name in ("torch", "transformers", "peft", "accelerate", "safetensors"):
        with contextlib.suppress(importlib.metadata.PackageNotFoundError):
            packages[name] = importlib.metadata.version(name)
    try:
        repo = Path(__file__).resolve().parents[1]
        git_commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        git_status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        git = {
            "available": True,
            "commit": git_commit,
            "dirty": bool(git_status),
            "status": git_status,
        }
    except (OSError, subprocess.CalledProcessError):
        git = {"available": False}
    accelerator: dict[str, Any] = {"available": False}
    try:
        import torch

        accelerator = {
            "available": torch.cuda.is_available(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "devices": (
                [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())]
                if torch.cuda.is_available()
                else []
            ),
        }
    except ImportError:
        pass
    return {
        "created_at": now(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version,
        "packages": packages,
        "accelerator": accelerator,
        "git": git,
        "script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "slurm": {
            key: os.environ[key]
            for key in ("SLURM_JOB_ID", "SLURM_JOB_NAME", "SLURM_NODELIST")
            if key in os.environ
        },
    }


def response_row(
    candidate: dict[str, Any],
    candidate_identity_sha256: str,
    prompt: EvalPrompt,
    prompt_set_sha256: str,
    result: GenerationResult,
    *,
    server_sha256: str | None,
    ordinal: int,
    raw_relative_path: str,
    wall_s: float,
) -> dict[str, Any]:
    row = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate["id"],
        "candidate_backend": candidate["backend"],
        # These flat aliases intentionally make judge-suite JSONL directly consumable by
        # bench/judges_prompt_report.py without rewriting the saved model output.
        "model": candidate["id"],
        "model_sha256": candidate_identity_sha256,
        "model_identity_kind": candidate_identity_kind(candidate["backend"]),
        "id": prompt.id,
        "source": prompt.source,
        "title": prompt.title,
        "text": prompt.text,
        "ordinal": ordinal,
        "prompt_set_sha256": prompt_set_sha256,
        "prompt_sha256": sha256_bytes(prompt.text.encode("utf-8")),
        "prompt": prompt.as_dict(),
        "answer": result.answer,
        "reasoning_content": result.reasoning_content,
        "finish_reason": result.finish_reason,
        "generated_tokens": result.generated_tokens,
        "wall_s": round(wall_s, 6),
        "raw_output": {
            "path": raw_relative_path,
            "bytes": len(result.raw_bytes),
            "sha256": sha256_bytes(result.raw_bytes),
            "media_type": result.raw_media_type,
        },
        "backend_details": result.backend_details,
        "hardware_context": socket.gethostname(),
        "generation_settings": {
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": SEED,
            "max_tokens": result.backend_details.get("generation", {}).get("max_new_tokens")
            or result.backend_details.get("request", {}).get("max_tokens"),
            "deterministic_decoding": "greedy",
            "enable_thinking": False,
        },
    }
    if server_sha256 is not None:
        row["server_sha256"] = server_sha256
    return row


def summarize_candidate(
    candidate: dict[str, Any],
    prompts: list[EvalPrompt],
    rows: list[dict[str, Any]],
    error: str | None,
    responses_sha256: str,
) -> dict[str, Any]:
    expected_ids = [prompt.id for prompt in prompts]
    captured_ids = [row["prompt"]["id"] for row in rows]
    complete = captured_ids == expected_ids and len(rows) >= 2 and error is None
    judge_score = ""
    judge_max = ""
    stem_mc_correct = ""
    stem_mc_total = ""
    if prompts[0].suite == "judges":
        judge_score = sum(
            grade_judge_prompt(row["prompt"]["id"], row["answer"])["score"] for row in rows
        )
        judge_max = 10 * len(prompts)
    else:
        multiple_choice = [row for row in rows if row["prompt"]["format"] == "multiple_choice"]
        stem_mc_correct = sum(
            selected_option(row["answer"]) == row["prompt"]["expected"] for row in multiple_choice
        )
        stem_mc_total = len([prompt for prompt in prompts if prompt.format == "multiple_choice"])
    return {
        "candidate_id": candidate["id"],
        "backend": candidate["backend"],
        "status": "complete" if complete else "failed" if error else "incomplete",
        "prompts": len(rows),
        "expected_prompts": len(prompts),
        "nonempty": sum(bool(row["answer"].strip()) for row in rows),
        "truncated": sum(row["finish_reason"] == "length" for row in rows),
        "judge_score": judge_score,
        "judge_max": judge_max,
        "stem_mc_correct": stem_mc_correct,
        "stem_mc_total": stem_mc_total,
        "mean_generated_tokens": (
            round(sum(row["generated_tokens"] for row in rows) / len(rows), 2) if rows else ""
        ),
        "mean_wall_s": round(sum(row["wall_s"] for row in rows) / len(rows), 3) if rows else "",
        "responses_sha256": responses_sha256,
        "error": error or "",
    }


SUMMARY_FIELDS = (
    "rank",
    "candidate_id",
    "backend",
    "status",
    "prompts",
    "expected_prompts",
    "nonempty",
    "truncated",
    "judge_score",
    "judge_max",
    "stem_mc_correct",
    "stem_mc_total",
    "mean_generated_tokens",
    "mean_wall_s",
    "responses_sha256",
    "error",
)


def rank_summaries(rows: list[dict[str, Any]], suite: str) -> list[dict[str, Any]]:
    score_key = "judge_score" if suite == "judges" else "stem_mc_correct"
    ranked = sorted(
        rows,
        key=lambda row: (
            row["status"] == "complete",
            float(row[score_key] or -1),
            -int(row["truncated"]),
            row["candidate_id"],
        ),
        reverse=True,
    )
    rank = 0
    for row in ranked:
        if row["status"] == "complete":
            rank += 1
            row["rank"] = rank
        else:
            row["rank"] = ""
    return ranked


def write_summary(output: Path, rows: list[dict[str, Any]], suite: str) -> None:
    csv_path = output / "summary.csv"
    with csv_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    if suite == "judges":
        score_header = "Judge score"

        def score(row: dict[str, Any]) -> str:
            return f"{row['judge_score']}/{row['judge_max']}"

    else:
        score_header = "STEM MC"

        def score(row: dict[str, Any]) -> str:
            return f"{row['stem_mc_correct']}/{row['stem_mc_total']}"

    lines = [
        "# Muta candidate evaluation",
        "",
        f"| Rank | Candidate | Backend | Status | Prompts | {score_header} | Empty | Truncated |",
        "|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['rank'] or '—'} | {row['candidate_id']} | {row['backend']} | "
            f"{row['status']} | {row['prompts']}/{row['expected_prompts']} | {score(row)} | "
            f"{int(row['prompts']) - int(row['nonempty'])} | {row['truncated']} |"
        )
    lines.extend(
        [
            "",
            (
                "Scores are screening aids. Judge keyword-rubric scores require manual "
                "adjudication; written STEM responses are retained ungraded."
            ),
            (
                "HF/PEFT candidates run in BF16 while the incumbent control is its exact "
                "quantized GGUF; wall time is diagnostic, not an apples-to-apples "
                "performance comparison."
            ),
            "",
        ]
    )
    with (output / "summary.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_campaign(
    manifest_path: Path,
    output: Path,
    *,
    suite: str,
    prompt_ids: list[str] | None,
    max_new_tokens: int,
    port: int,
    gpu_layers: int,
    threads: int,
    context_size: int,
    backend_factory: Any = make_backend,
) -> list[dict[str, Any]]:
    manifest = load_candidate_manifest(manifest_path)
    prompts = select_prompts(suite, prompt_ids)
    prompt_payload = [prompt.as_dict() for prompt in prompts]
    prompt_set_sha = sha256_bytes(canonical_bytes(prompt_payload))
    identities = {}
    identity_cache: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in manifest["candidates"]:
        identities[candidate["id"]] = verify_candidate(candidate, identity_cache)
    content_owners: dict[str, str] = {}
    for candidate in manifest["candidates"]:
        digest = candidate_content_sha256(identities[candidate["id"]])
        if digest in content_owners:
            raise EvaluationInputError(
                "duplicate candidate model identity: "
                f"{content_owners[digest]} and {candidate['id']}"
            )
        content_owners[digest] = candidate["id"]

    output = output.resolve()
    # Receipt the repository before creating the evaluation tree.  Capturing
    # status afterward would mark an in-repository evidence output as its own
    # uncommitted change and make every otherwise clean run unpromotable.
    runtime_receipt = _runtime_receipt()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    manifest_snapshot = output / "candidate-manifest.json"
    write_bytes_exclusive(manifest_snapshot, Path(manifest["manifest_path"]).read_bytes())
    write_json_exclusive(output / "prompts.json", prompt_payload)
    write_json_exclusive(
        output / "run.json",
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": manifest.get("campaign_id", "unspecified"),
            "candidate_manifest": {
                "path": manifest["manifest_path"],
                "sha256": manifest["manifest_sha256"],
                "snapshot": manifest_snapshot.name,
            },
            "prompt_suite": suite,
            "prompt_count": len(prompts),
            "prompt_set_sha256": prompt_set_sha,
            "settings": {
                "seed": SEED,
                "deterministic_decoding": "greedy",
                "max_new_tokens": max_new_tokens,
                "context_size": context_size,
                "gguf_gpu_layers": gpu_layers,
                "gguf_threads": threads,
                "gguf_port": port,
                "enable_thinking": False,
            },
            "runtime": runtime_receipt,
        },
    )

    summaries = []
    all_responses: list[dict[str, Any]] = []
    for candidate_index, candidate in enumerate(manifest["candidates"]):
        candidate_dir = output / "candidates" / candidate["id"]
        candidate_dir.mkdir(parents=True)
        identity = identities[candidate["id"]]
        candidate_identity_sha = candidate_content_sha256(identity)
        write_json_exclusive(
            candidate_dir / "identity.json",
            {
                **identity,
                "candidate_identity_sha256": candidate_identity_sha,
                "candidate_identity_kind": candidate_identity_kind(candidate["backend"]),
            },
        )
        rows: list[dict[str, Any]] = []
        error = None
        responses_path = candidate_dir / "responses.jsonl"
        with responses_path.open("x", encoding="utf-8") as responses:
            try:
                backend = backend_factory(
                    candidate,
                    candidate_dir,
                    port=port + candidate_index,
                    gpu_layers=gpu_layers,
                    threads=threads,
                    context_size=context_size,
                )
                with backend:
                    for ordinal, prompt in enumerate(prompts, 1):
                        started = time.monotonic()
                        result = validate_generation_result(
                            backend.generate(prompt, max_new_tokens=max_new_tokens)
                        )
                        wall_s = time.monotonic() - started
                        raw_path = candidate_dir / "raw" / f"{ordinal:03d}-{prompt.id}.bin"
                        write_bytes_exclusive(raw_path, result.raw_bytes)
                        row = response_row(
                            candidate,
                            candidate_identity_sha,
                            prompt,
                            prompt_set_sha,
                            result,
                            server_sha256=(
                                identity["observed"]["server"]["sha256"]
                                if candidate["backend"] == "gguf"
                                else None
                            ),
                            ordinal=ordinal,
                            raw_relative_path=raw_path.relative_to(candidate_dir).as_posix(),
                            wall_s=wall_s,
                        )
                        responses.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                        responses.flush()
                        os.fsync(responses.fileno())
                        rows.append(row)
                        all_responses.append(row)
            except Exception as exc:  # noqa: BLE001 - retain all candidate failure evidence
                error = f"{type(exc).__name__}: {exc}"
                write_json_exclusive(
                    candidate_dir / "error.json",
                    {"ts": now(), "error": error, "traceback": traceback.format_exc()},
                )
        responses_sha = sha256_file(responses_path)
        summary = summarize_candidate(
            candidate,
            prompts,
            rows,
            error,
            responses_sha,
        )
        write_json_exclusive(candidate_dir / "result.json", summary)
        summaries.append(summary)

    summaries = rank_summaries(summaries, suite)
    write_summary(output, summaries, suite)
    aggregate_path = output / "responses.jsonl"
    with aggregate_path.open("x", encoding="utf-8") as aggregate:
        for row in all_responses:
            aggregate.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    if suite == "judges":
        artifact_path = output / "artifacts.csv"
        with artifact_path.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=("test_artifact", "model"))
            writer.writeheader()
            for candidate in manifest["candidates"]:
                writer.writerow(
                    {
                        "test_artifact": candidate["id"],
                        "model": candidate.get("label", candidate["id"]),
                    }
                )
        judge_summary, _ = evaluate_judge_rows(
            all_responses,
            {
                candidate["id"]: candidate.get("label", candidate["id"])
                for candidate in manifest["candidates"]
            },
        )
        write_judge_csv(output / "gate1-rubric.csv", judge_summary)
    write_json_exclusive(output / "artifact-inventory.json", output_inventory(output))
    terminal = (
        "COMPLETED.json" if all(row["status"] == "complete" for row in summaries) else "FAILED.json"
    )
    write_json_exclusive(
        output / terminal,
        {
            "ts": now(),
            "status": terminal.removesuffix(".json").lower(),
            "summary_csv_sha256": sha256_file(output / "summary.csv"),
            "summary_markdown_sha256": sha256_file(output / "summary.md"),
            "aggregate_responses_sha256": sha256_file(output / "responses.jsonl"),
            "artifact_inventory_sha256": sha256_file(output / "artifact-inventory.json"),
        },
    )
    return summaries


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=("judges", "stem"), default="judges")
    parser.add_argument("--prompt-id", action="append")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--port", type=int, default=18180)
    parser.add_argument("--gpu-layers", type=int, default=99)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--context-size", type=int, default=4096)
    args = parser.parse_args(argv)
    if args.max_new_tokens < 1:
        parser.error("--max-new-tokens must be positive")
    if args.context_size < args.max_new_tokens:
        parser.error("--context-size must be at least --max-new-tokens")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summaries = run_campaign(
            args.candidates,
            args.output,
            suite=args.suite,
            prompt_ids=args.prompt_id,
            max_new_tokens=args.max_new_tokens,
            port=args.port,
            gpu_layers=args.gpu_layers,
            threads=args.threads,
            context_size=args.context_size,
        )
    except (EvaluationInputError, FileExistsError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0 if all(row["status"] == "complete" for row in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
