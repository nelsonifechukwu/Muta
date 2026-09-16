#!/usr/bin/env python3
"""Generate answers to the ADTC Round-1 judge prompts from one model.

Runs llama-server from the ADTC reference profiler image (llama.cpp b10175,
scalar CPU build) so the inference runtime matches the audit environment,
then asks each prompt once with greedy decoding (temperature 0, seed 42).
Everything the model emits is kept in `response` (--reasoning-format none),
so any thinking trace is graded exactly as the judges would have seen it.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

W = os.path.expanduser("~/adtc-semis")
IMAGE = "adtc-profiler:latest"
PORT = 8080
MAX_TOKENS = 1536

m = sys.argv[1]
nothink = "--no-think" in sys.argv[2:]
suffix = "-nothink" if nothink else ""
meta = json.load(open(f"{W}/subs/{m}/metadata.json"))
model_rel = meta["_runtime"]["model_path"]
name = f"llm-{m}{suffix}"

subprocess.run(["sudo", "docker", "rm", "-f", name], capture_output=True)
server_args = [
    "-m", "/submission/" + model_rel,
    "--host", "0.0.0.0", "--port", str(PORT),
    "-c", "4096", "-ngl", "0",
    "--jinja", "--reasoning-format", "none",
]
cmd = [
    "sudo", "docker", "run", "-d", "--name", name, "--memory=7.5g",
    "-p", f"127.0.0.1:{PORT}:{PORT}",
    "-v", f"{W}/subs/{m}:/submission:ro",
    "--entrypoint", "llama-server", IMAGE,
] + server_args
subprocess.run(cmd, check=True)

for _ in range(150):
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5)
        if r.status == 200:
            break
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        pass
    time.sleep(2)
else:
    subprocess.run(["sudo", "docker", "logs", name])
    subprocess.run(["sudo", "docker", "rm", "-f", name], capture_output=True)
    raise SystemExit("llama-server never became healthy")

prompts = json.load(open(f"{W}/prompts/prompts.json"))
settings = {"max_tokens": MAX_TOKENS, "temperature": 0, "seed": 42, "stream": False}
if nothink:
    # Qwen3.5 chat template switch; the Round-1 human-judge answers were thinking-free.
    settings["chat_template_kwargs"] = {"enable_thinking": False}
out_path = f"{W}/artifacts/responses-{m}{suffix}.json"
out = []
for p in prompts:
    body = dict(settings, messages=[{"role": "user", "content": p["prompt"]}])
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    resp = json.load(urllib.request.urlopen(req, timeout=7200))
    wall = time.time() - t0
    ch = resp["choices"][0]
    rec = {
        "id": p["id"],
        "source": p["source"],
        "prompt": p["prompt"],
        "response": ch["message"].get("content"),
        "reasoning_content": ch["message"].get("reasoning_content"),
        "finish_reason": ch.get("finish_reason"),
        "usage": resp.get("usage"),
        "timings": resp.get("timings"),
        "wall_s": round(wall, 1),
    }
    out.append(rec)
    print(p["id"], ch.get("finish_reason"), resp.get("usage"), f"{wall:.0f}s", flush=True)
    json.dump(
        {
            "model": m,
            "condition": "thinking_off" if nothink else "template_default",
            "model_file": model_rel,
            "image": IMAGE,
            "server_args": server_args,
            "sampling": settings,
            "responses": out,
        },
        open(out_path, "w"),
        indent=2,
        ensure_ascii=False,
    )

with open(f"{W}/logs/llama-server-{m}{suffix}.log", "w") as f:
    subprocess.run(["sudo", "docker", "logs", name], stdout=f, stderr=subprocess.STDOUT)
subprocess.run(["sudo", "docker", "rm", "-f", name], capture_output=True)
print("GEN_DONE")
