"""Run the fixed Muta STEM battery through a scalar llama-server, one model at a time."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from bench.stem_prompt_suite import Prompt, prompts


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def request_json(url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def wait_until_ready(base_url: str, process: subprocess.Popen, timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"llama-server exited during load with code {process.returncode}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    raise TimeoutError(f"llama-server did not become ready within {timeout:g} seconds")


def selected_option(text: str) -> str | None:
    """Extract an asserted answer, leaving ambiguous option lists ungraded.

    Explicit answers take precedence over line-leading options. Within that class,
    use textual order rather than the order of the extraction patterns. This only
    extracts the option; it does not validate the accompanying explanation.
    """
    explicit_patterns = (
        (
            r"(?i:final\s+(?:answer|option)|correct\s+(?:answer|option)|answer)"
            r"\s*(?i:is|:)?\s*[*`]*\(?([A-Z]|[b-d]|a(?=\s*[).,:;*!`]|\s*$))\b"
        ),
        r"\\boxed\{\s*([A-Za-z])\s*\}",
    )
    explicit = [match for pattern in explicit_patterns for match in re.finditer(pattern, text)]
    if explicit:
        choice = max(explicit, key=lambda match: match.start()).group(1).upper()
        return choice if choice in "ABCD" else None

    # A single labelled answer (or a bare letter) is accepted. Multiple distinct
    # line-leading options could be a reproduced question, so require adjudication.
    choices = {
        match.group(1).upper()
        for match in re.finditer(
            r"(?m)^\s*[*`]*\(?([A-Da-d])(?:\s*[).,:-]|[*`]*\s*$)", text
        )
    }
    return next(iter(choices)) if len(choices) == 1 else None


def run_prompt(base_url: str, prompt: Prompt) -> dict:
    max_tokens = 256 if prompt.format == "multiple_choice" else 512
    started = time.monotonic()
    response = request_json(
        f"{base_url}/completion",
        {
            "prompt": prompt.text,
            "n_predict": max_tokens,
            "temperature": 0.0,
            "seed": 42,
            "cache_prompt": False,
            "stream": False,
        },
        timeout=900,
    )
    answer = response.get("content", "")
    row = {
        **prompt.as_dict(),
        "answer": answer,
        "finish_reason": response.get("stop_type"),
        "generated_tokens": response.get("tokens_predicted"),
        "wall_s": round(time.monotonic() - started, 3),
    }
    if prompt.format == "multiple_choice":
        choice = selected_option(answer)
        row.update({"selected": choice, "correct": choice == prompt.expected})
    return row


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--models", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument(
        "--hardware-context",
        default="unspecified",
        help="Execution context recorded with every response and lifecycle event.",
    )
    args = parser.parse_args()

    missing = [path for path in [args.server, *args.models] if not path.exists()]
    if missing:
        parser.error(f"missing inputs: {missing}")
    args.logs.mkdir(parents=True, exist_ok=True)
    base_url = f"http://127.0.0.1:{args.port}"
    server_hash = sha256(args.server)

    for model in args.models:
        model_hash = sha256(model)
        log_path = args.logs / f"{model.stem}.log"
        command = [
            str(args.server),
            "--model",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--ctx-size",
            "2048",
            "--threads",
            str(args.threads),
            "--n-gpu-layers",
            str(args.gpu_layers),
            "--cache-ram",
            "256",
        ]
        append_jsonl(
            args.events,
            {
                "event": "model_start",
                "ts": now(),
                "model": model.name,
                "model_sha256": model_hash,
                "server_sha256": server_hash,
                "hardware_context": args.hardware_context,
                "command": command,
            },
        )
        print(f"[STEM] loading {model.name}", flush=True)
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            try:
                wait_until_ready(base_url, process)
                for prompt in prompts():
                    result = run_prompt(base_url, prompt)
                    append_jsonl(
                        args.out,
                        {
                            "ts": now(),
                            "model": model.name,
                            "model_sha256": model_hash,
                            "server_sha256": server_hash,
                            "hardware_context": args.hardware_context,
                            **result,
                        },
                    )
                    status = result.get("correct", "ungraded")
                    print(f"  {prompt.id}: {status}", flush=True)
            except Exception as exc:
                append_jsonl(
                    args.events,
                    {
                        "event": "model_failure",
                        "ts": now(),
                        "model": model.name,
                        "hardware_context": args.hardware_context,
                        "error": repr(exc),
                    },
                )
                raise
            finally:
                stop_server(process)
        append_jsonl(
            args.events,
            {
                "event": "model_stop",
                "ts": now(),
                "model": model.name,
                "hardware_context": args.hardware_context,
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
