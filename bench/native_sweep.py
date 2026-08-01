"""Engine-only native sweep — benchmark llama-server flag-sets without gateway, db or docker.

`bench/profile.py` measures the product path (gateway + engine, needs Postgres up).
This harness answers a different question: *which engine flags are fastest/smallest on
this host*, by driving the pinned `runtime/build/bin/llama-server` directly over
/v1/chat/completions (the same endpoint the gateway uses). Per named flag-set it records:

  - decode tok/s   engine `timings.predicted_per_second`, warm; `decode_tps_max` is the
                   max over the 4 throughput probes AND the 2 reuse-probe generations
                   (probe spread = scheduler noise)
  - prefill tok/s  ~900-token prompt, `timings.prompt_per_second`
  - peak/steady tree RSS (psutil, 25 ms sampling) AND `phys_footprint` via
                   /usr/bin/footprint — on macOS sampled RSS swings with file-backed
                   page eviction; footprint is the honest "what it costs" figure
  - multi-turn prefix reuse (turn-2 `prompt_n` vs full history)
  - full suite only: greedy accuracy probes, >1024-token window probe, a 3-conversation
                   RAM stressor before the footprint reading

Results append to bench/.artifacts/native-sweep.jsonl; engine logs land next to it.
The 2026-08-01 sweep this tool was built for is written up in RESULTS.md (that artifact
was recorded with the session iteration of this script; ad-hoc flag-sets — the AB-*
interleaved rounds, B0-longctx-verify — go through `run_config()` directly).

    python -m bench.native_sweep B0-baseline WINNER
    python -m bench.native_sweep --list
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "runtime" / "build" / "bin" / "llama-server"
MODEL = ROOT / "models" / "core" / "Qwen3.5-4B-Q4_K_M.gguf"
DRAFT = ROOT / "models" / "draft" / "Qwen3.5-0.8B-Q4_K_M.gguf"
PORT = 8089  # off the 8080/8000 defaults so a running stack never collides
BASE = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(__file__).resolve().parent / ".artifacts"
OUT = ARTIFACTS / "native-sweep.jsonl"
LOGDIR = ARTIFACTS / "native-logs"

# Mirrors runtime/server.py build_command() with the PRE-2026-08-01 RuntimeConfig
# defaults (engine-default threads, split KV, 4 checkpoints), speculation stripped —
# the fixed reference point sweeps are measured against.
BASE_FLAGS = [
    "--model", str(MODEL), "--alias", "qwen3.5-4b",
    "--host", "127.0.0.1", "--port", str(PORT),
    "--ctx-size", "2048", "--n-gpu-layers", "0", "--jinja",
    "--parallel", "2", "--ctx-checkpoints", "4", "--cache-ram", "256",
    "-b", "512", "-ub", "128", "--cache-type-k", "q8_0",
    "--reasoning-budget", "512",
]

ACCURACY = [
    ("Compute 17 times 23. Give only the number.", ["391"]),
    ("A rectangle has sides 7 cm and 12 cm. What is its area in square centimeters? Give only the number.", ["84"]),
    ("What is the derivative of x^3 + 2x with respect to x? Answer in one short line.", ["3x^2 + 2", "3x² + 2", "3x^2+2", "3x²+2"]),
    ("Convert 2.5 hours to minutes. Give only the number.", ["150"]),
]

THROUGHPUT_PROMPTS = [
    "A train travels 120 km in 1.5 hours. A student thinks the speed is 90 km/h. As a tutor, help them see their mistake step by step without giving the final answer immediately.",
    "Explain to a 12-year-old why dividing by zero is undefined, using a sharing-cookies example.",
]

_FACTS = [
    "The speed of light in vacuum is 299792458 metres per second and is the same for all observers.",
    "Water boils at 100 degrees Celsius at one standard atmosphere of pressure at sea level.",
    "The gravitational acceleration near Earth's surface is approximately 9.81 metres per second squared.",
    "Photosynthesis converts carbon dioxide and water into glucose and oxygen using light energy.",
    "The Pythagorean theorem states that the square of the hypotenuse equals the sum of the squares of the other two sides.",
    "Newton's second law states that force equals mass times acceleration in an inertial frame.",
    "The area of a circle is pi times the radius squared, and its circumference is two pi times the radius.",
    "Sound travels at about 343 metres per second in dry air at 20 degrees Celsius.",
    "An acid donates protons while a base accepts protons according to the Bronsted-Lowry definition.",
    "The mitochondrion is the organelle responsible for producing ATP through cellular respiration.",
    "Ohm's law relates voltage, current and resistance as V equals I times R in linear circuits.",
    "The Earth completes one orbit around the Sun in approximately 365.25 days.",
]


def _notes_prompt(repeats: int) -> str:
    return (
        "Here are the notes from today's science class:\n"
        + "\n".join(f"{i + 1}. {f}" for i, f in enumerate(_FACTS * repeats))
        + "\nSummarize the three most important ideas in one sentence each."
    )


PREFILL_PROMPT = _notes_prompt(3)  # ~900 tokens: fits a 1024-token split slot
LONGCTX_PROMPT = _notes_prompt(5)  # ~1500 tokens: needs the unified 2048 window

MULTITURN_T1 = "I need help with fractions. What is 1/2 + 1/3? Explain step by step."
MULTITURN_T2 = "Thanks! Now what is 1/2 + 1/4?"


class RssSampler:
    """Peak/steady RSS of the engine's process tree, sampled on a daemon thread."""

    def __init__(self, pid: int, interval: float = 0.025) -> None:
        self.proc = psutil.Process(pid)
        self.interval = interval
        self.peak = 0
        self.last = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _tree_rss(self) -> int:
        total = 0
        try:
            for p in [self.proc, *self.proc.children(recursive=True)]:
                try:
                    total += p.memory_info().rss
                except psutil.Error:
                    pass
        except psutil.Error:
            pass
        return total

    def _run(self) -> None:
        while not self._stop.is_set():
            rss = self._tree_rss()
            if rss:
                self.last = rss
                self.peak = max(self.peak, rss)
            time.sleep(self.interval)

    def start(self) -> "RssSampler":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


def phys_footprint_mib(pid: int) -> float | None:
    """macOS phys_footprint — anonymous + compressed, immune to mmap-eviction noise."""
    try:
        out = subprocess.run(
            ["/usr/bin/footprint", str(pid)], capture_output=True, text=True, timeout=15
        ).stdout
        m = re.search(r"phys_footprint:\s+([\d.]+)\s*(KB|MB|GB)", out)
        if m:
            return float(m.group(1)) * {"KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}[m.group(2)]
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def chat(messages, max_tokens=384, temperature=None, timeout=300.0):
    body = {"messages": messages, "max_tokens": max_tokens, "stream": False}
    if temperature is not None:
        body["temperature"] = temperature
        body["top_k"] = 1
    r = httpx.post(f"{BASE}/v1/chat/completions", json=body, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    return (j["choices"][0]["message"].get("content") or ""), j.get("timings", {})


def wait_health(proc, deadline=180.0):
    t0 = time.time()
    while time.time() - t0 < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"engine exited rc={proc.returncode}")
        try:
            if httpx.get(f"{BASE}/health", timeout=1.0).status_code == 200:
                return time.time() - t0
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise TimeoutError("engine not healthy in time")


def run_config(name: str, extra: list[str], *, suite: str = "speed") -> dict:
    """Launch, probe, sample, tear down; append one JSON line to OUT."""
    try:  # a stale server on PORT would silently absorb the probes of every config
        httpx.get(f"{BASE}/health", timeout=1.0)
        raise RuntimeError(f"something is already serving on {BASE} — stop it first")
    except httpx.HTTPError:
        pass
    LOGDIR.mkdir(parents=True, exist_ok=True)
    flags = [*BASE_FLAGS, *extra]  # llama-server arg parsing is last-wins
    log_path = LOGDIR / f"{name}.log"
    print(f"\n=== {name} ===\n  flags: {' '.join(extra) or '(baseline)'}", flush=True)
    with open(log_path, "w") as lf:
        proc = subprocess.Popen([str(BIN), *flags], stdout=lf, stderr=subprocess.STDOUT)
    result: dict = {"name": name, "extra_flags": extra, "suite": suite}
    sampler = None
    try:
        result["load_s"] = round(wait_health(proc), 1)
        sampler = RssSampler(proc.pid).start()
        time.sleep(0.5)
        result["rss_after_load_mib"] = round(sampler.last / 2**20)

        chat([{"role": "user", "content": "Say OK."}], max_tokens=8, temperature=0.0)  # warmup

        decode = []
        for p in [THROUGHPUT_PROMPTS[0]] * 3 + [THROUGHPUT_PROMPTS[1]]:
            _, t = chat([{"role": "user", "content": p}], max_tokens=320, temperature=0.0)
            decode.append(t.get("predicted_per_second", 0.0))
            if t.get("draft_n"):
                result.setdefault("draft", []).append(
                    {"draft_n": t["draft_n"], "accepted": t.get("draft_n_accepted")})
        result["decode_tps"] = [round(x, 2) for x in decode]

        _, t = chat([{"role": "user", "content": PREFILL_PROMPT}], max_tokens=32, temperature=0.0)
        result["prefill_n"] = t.get("prompt_n")
        result["prefill_tps"] = round(t.get("prompt_per_second", 0.0), 1)

        a1, t1 = chat([{"role": "user", "content": MULTITURN_T1}], max_tokens=384, temperature=0.0)
        _, t2 = chat(
            [{"role": "user", "content": MULTITURN_T1},
             {"role": "assistant", "content": a1},
             {"role": "user", "content": MULTITURN_T2}],
            max_tokens=384, temperature=0.0)
        result["reuse"] = {"t1_prompt_n": t1.get("prompt_n"), "t2_prompt_n": t2.get("prompt_n")}
        result["decode_tps_max"] = round(
            max([*decode, t1.get("predicted_per_second", 0), t2.get("predicted_per_second", 0)]), 2)

        if suite == "full":
            try:
                _, tl = chat([{"role": "user", "content": LONGCTX_PROMPT}], max_tokens=32, temperature=0.0)
                result["longctx"] = {"ok": True, "prompt_n": tl.get("prompt_n")}
            except httpx.HTTPStatusError as e:
                result["longctx"] = {"ok": False, "status": e.response.status_code}
            acc = []
            for q, expects in ACCURACY:
                content, _ = chat([{"role": "user", "content": q}], max_tokens=600, temperature=0.0)
                acc.append({"q": q[:40], "ok": any(e in content for e in expects),
                            "tail": content.strip()[-60:]})
            result["accuracy"] = acc
            result["accuracy_pass"] = sum(1 for a in acc if a["ok"])
            for i in range(3):  # RAM stressor: populate checkpoints + prompt cache
                s1, _ = chat([{"role": "user", "content": f"Conversation {i}: {THROUGHPUT_PROMPTS[0]}"}],
                             max_tokens=256, temperature=0.0)
                chat([{"role": "user", "content": f"Conversation {i}: {THROUGHPUT_PROMPTS[0]}"},
                      {"role": "assistant", "content": s1},
                      {"role": "user", "content": "Can you rephrase that more simply?"}],
                     max_tokens=256, temperature=0.0)
        result["footprint_mib"] = phys_footprint_mib(proc.pid)
        time.sleep(0.3)
        result["rss_peak_mib"] = round(sampler.peak / 2**20)
        result["rss_steady_mib"] = round(sampler.last / 2**20)
        result["ok"] = True
    except Exception as e:  # noqa: BLE001 — a failed config is a data point, not a crash
        result["ok"] = False
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if sampler:
            sampler.stop()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(result) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("extra_flags", "accuracy")},
                     indent=2), flush=True)
    return result


_T6 = ["--threads", "6", "--threads-batch", "6"]  # M2 Pro P-core count; see RESULTS.md

#: name -> (extra flags appended after BASE_FLAGS, suite). The 2026-08-01 sweep set.
CONFIGS: dict[str, tuple[list[str], str]] = {
    "B0-baseline": ([], "full"),
    "T4": (["--threads", "4", "--threads-batch", "4"], "speed"),
    "T6": (_T6, "speed"),
    "T8": (["--threads", "8", "--threads-batch", "8"], "speed"),
    "T10": (["--threads", "10", "--threads-batch", "10"], "speed"),
    "PRIO2": (["--prio", "2", "--prio-batch", "2"], "speed"),  # pathological — kept reproducible
    "T6B8": (_T6[:2] + ["--threads-batch", "8"], "speed"),
    "T6B10": (_T6[:2] + ["--threads-batch", "10"], "speed"),
    "T6-FAon": (_T6 + ["-fa", "on"], "speed"),
    "T6-FAoff": (_T6 + ["-fa", "off"], "speed"),
    "T6-UB256": (_T6 + ["-ub", "256"], "speed"),
    "T6-UB512": (_T6 + ["-ub", "512"], "speed"),
    "T6-NP1": (_T6 + ["--parallel", "1"], "speed"),
    "T6-KVU": (_T6 + ["--kv-unified"], "speed"),
    "T6-CKPT2": (_T6 + ["--ctx-checkpoints", "2"], "full"),
    "T6-CKPT1": (_T6 + ["--ctx-checkpoints", "1"], "full"),
    "T6-CRAM64": (_T6 + ["--cache-ram", "64"], "full"),
    "T6-CTVq8": (_T6 + ["-fa", "on", "--cache-type-v", "q8_0"], "full"),
    "T6-NOMMAP": (_T6 + ["--no-mmap"], "speed"),
    "T6-MLOCK": (_T6 + ["--mlock"], "speed"),
    "T6-SPECn3": (_T6 + ["--spec-type", "draft-simple", "--spec-draft-model", str(DRAFT),
                  "--spec-draft-n-max", "3", "--spec-draft-n-min", "1",
                  "--spec-draft-p-min", "0.90", "--spec-draft-threads", "2"], "speed"),
    "T6-SPECn8": (_T6 + ["--spec-type", "draft-simple", "--spec-draft-model", str(DRAFT),
                  "--spec-draft-n-max", "8", "--spec-draft-n-min", "1",
                  "--spec-draft-p-min", "0.75"], "speed"),
    "T6-NGRAM": (_T6 + ["--spec-type", "ngram-simple", "--spec-ngram-simple-size-n", "4",
                 "--spec-ngram-simple-size-m", "12"], "speed"),
    # What RuntimeConfig ships since 2026-08-01: P-core threads + unified KV + 2 checkpoints.
    "WINNER": (_T6 + ["--kv-unified", "--ctx-checkpoints", "2"], "full"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="native-sweep", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("configs", nargs="*", help="config names (default: all)")
    parser.add_argument("--list", action="store_true", help="list known configs")
    args = parser.parse_args(argv)
    if args.list:
        for n, (extra, suite) in CONFIGS.items():
            print(f"{n:12s} [{suite:5s}] {' '.join(extra)}")
        return 0
    unknown = [n for n in args.configs if n not in CONFIGS]
    if unknown:
        parser.error(f"unknown configs {unknown}; known: {list(CONFIGS)}")
    for n in args.configs or list(CONFIGS):
        extra, suite = CONFIGS[n]
        run_config(n, extra, suite=suite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
