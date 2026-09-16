"""Replay the exact Gate 1 judge prompts through each GGUF's embedded chat template."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from bench.judges_prompt_suite import JudgePrompt, prompts
from bench.run_stem_prompt_suite import append_jsonl, sha256


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


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


def run_prompt(base_url: str, prompt: JudgePrompt) -> dict:
    started = time.monotonic()
    response = request_json(
        f"{base_url}/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": prompt.text}],
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 3407,
            "max_tokens": 1024,
            "stream": False,
        },
        timeout=1800,
    )
    choice = response.get("choices", [{}])[0]
    message = choice.get("message", {})
    return {
        **prompt.as_dict(),
        "answer": message.get("content", ""),
        "reasoning_content": message.get("reasoning_content", ""),
        "finish_reason": choice.get("finish_reason"),
        "usage": response.get("usage", {}),
        "wall_s": round(time.monotonic() - started, 3),
    }


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
    def terminate(signum: int, _frame: object) -> None:
        # Allow the active model's finally block to stop its server on service shutdown.
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--models", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--threads", type=int, default=2)
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
    settings = {
        "context_size": 4096,
        "threads": args.threads,
        "gpu_layers": args.gpu_layers,
        "cache_ram_mib": 256,
        "embedded_chat_template": True,
        "external_system_prompt": False,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 3407,
        "max_tokens": 1024,
    }

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
            "4096",
            "--threads",
            str(args.threads),
            "--n-gpu-layers",
            str(args.gpu_layers),
            "--cache-ram",
            "256",
            "--jinja",
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
                "settings": settings,
                "command": command,
            },
        )
        print(f"[JUDGES] loading {model.name}", flush=True)
        failed = False
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
                            "settings": settings,
                            **result,
                        },
                    )
                    print(f"  {prompt.id}: {result['finish_reason']}", flush=True)
            except (OSError, RuntimeError, TimeoutError, ValueError, urllib.error.URLError) as exc:
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
                failed = True
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
        if failed:
            print("  -> failed; continuing to the next model", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
