"""Run a small deterministic chat battery against exact GGUF artifacts.

This is a qualitative acceptance gate, not an accuracy benchmark.  It starts one
llama-server at a time, records exact binary/model identities, and retains the
complete responses for human review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROMPTS = (
    {
        "id": "crate_profit",
        "text": (
            "A trader buys 24 identical crates for 18,000 naira and sells them at a "
            "25% profit. What is the selling price of one crate? Show your working."
        ),
    },
    {
        "id": "fraction_misconception",
        "text": "I think 1/2 + 1/3 = 2/5. Where did I go wrong?",
    },
    {
        "id": "thermal_energy",
        "text": (
            "A 2.0 kg sample of water warms from 20 C to 30 C. Using a specific heat "
            "capacity of 4200 J/(kg C), calculate the energy transferred and check the units."
        ),
    },
    {
        "id": "sqrt2_proof",
        "text": (
            "Give a concise proof by contradiction that sqrt(2) is irrational, written for "
            "a secondary-school student."
        ),
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_json(url: str, payload: dict | None = None, timeout: float = 10) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def wait_ready(base_url: str, process: subprocess.Popen, timeout_s: float = 90) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"llama-server exited with status {process.returncode}")
        try:
            request_json(f"{base_url}/health", timeout=2)
            return
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError):
            time.sleep(0.5)
    raise TimeoutError("llama-server did not become ready")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def run_model(
    binary: Path,
    model_id: str,
    model: Path,
    system_prompt: str | None,
    port: int,
    thinking: str,
) -> dict:
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.NamedTemporaryFile(prefix="muta-live-prompt-", suffix=".log") as log:
        command = [
            str(binary),
            "--model", str(model),
            "--alias", model_id,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--ctx-size", "2048",
            "--n-gpu-layers", "0",
            "--threads", "2",
            "--parallel", "1",
            "--jinja",
        ]
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            wait_ready(base_url, process)
            responses = []
            for prompt in PROMPTS:
                messages = []
                if system_prompt is not None:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt["text"]})
                started = time.monotonic()
                payload = {
                    "model": model_id,
                    "messages": messages,
                    "temperature": 0,
                    "seed": 42,
                    "max_tokens": 256,
                    "stream": False,
                }
                if thinking != "auto":
                    payload["chat_template_kwargs"] = {
                        "enable_thinking": thinking == "on"
                    }
                reply = request_json(
                    f"{base_url}/v1/chat/completions",
                    payload,
                    timeout=180,
                )
                choice = reply["choices"][0]
                responses.append(
                    {
                        "prompt_id": prompt["id"],
                        "prompt": prompt["text"],
                        "response": choice["message"].get("content", ""),
                        "reasoning": choice["message"].get("reasoning_content", ""),
                        "finish_reason": choice.get("finish_reason"),
                        "elapsed_s": round(time.monotonic() - started, 3),
                        "usage": reply.get("usage"),
                    }
                )
            return {
                "model_id": model_id,
                "model_path": str(model),
                "model_sha256": sha256(model),
                "model_bytes": model.stat().st_size,
                "system_prompt_supplied": system_prompt is not None,
                "responses": responses,
            }
        except Exception as exc:
            log.seek(0)
            tail = log.read().decode(errors="replace")[-4000:]
            raise RuntimeError(f"{model_id}: {exc}\nserver log tail:\n{tail}") from exc
        finally:
            stop(process)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--model", action="append", required=True, metavar="ID=PATH",
        help="repeat for each exact GGUF artifact",
    )
    parser.add_argument("--system", type=Path)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--thinking", choices=("auto", "off", "on"), default="off")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"binary not found: {binary}")
    system_prompt = args.system.read_text().strip() if args.system else None
    models = []
    for item in args.model:
        model_id, separator, raw_path = item.partition("=")
        if not separator or not model_id or not raw_path:
            raise SystemExit(f"invalid --model value: {item}")
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise SystemExit(f"model not found: {path}")
        models.append((model_id, path))

    report = {
        "schema_version": 1,
        "kind": "qualitative_live_prompt_acceptance",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "binary": str(binary),
        "binary_sha256": sha256(binary),
        "settings": {
            "threads": 2,
            "ctx_size": 2048,
            "temperature": 0,
            "seed": 42,
            "max_tokens": 256,
            "thinking": args.thinking,
        },
        "models": [
            run_model(binary, model_id, path, system_prompt, args.port, args.thinking)
            for model_id, path in models
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
