#!/usr/bin/env python3
"""Acceptance checks for the fetched model bundle (TDD T2).

Proves the things a manifest cannot: that the bytes on disk are the bytes we pinned, that
the budget holds, that the engines can actually *load* what we shipped, and that nothing
carries a licence we cannot redistribute.

Checks that need a tool we do not have on this box (llama.cpp binaries, sherpa-onnx) are
reported as SKIP, loudly, and are turned into hard failures by --strict. The build machine
and CI run --strict; a Mac dev loop does not have to.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))

from fetch_models import RESIDENT_CAP_BYTES, human, sha256_file  # noqa: E402
from model_specs import ALLOWED_LICENSES  # noqa: E402

# The GGUF reader and the KV arithmetic already exist for T5 — reuse them rather than
# growing a second parser that can drift from the one runtime/profiles.py sizes slots with.
from runtime.gguf import read_metadata  # noqa: E402
from runtime.kvmath import KVCost  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "models" / "MANIFEST.json"
KV_METADATA_PATH = REPO_ROOT / "bench" / "kv_metadata.json"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
# (name, status, detail, expected). `expected` separates the two very different reasons a
# check can be skipped: a tier B artifact we deliberately did not fetch (expected — must
# not fail --strict) versus a tool this box lacks (not expected — --strict fails on it,
# because the build machine has no excuse for missing llama-cli or sherpa-onnx).
results: list[tuple[str, str, str, bool]] = []


def record(name: str, status: str, detail: str = "", expected: bool = False) -> None:
    results.append((name, status, detail, expected))
    mark = {PASS: "  ok  ", FAIL: " FAIL ", SKIP: " skip "}[status]
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def find_bin(name: str) -> str | None:
    """Same resolution order as runtime/server.py: env override, local build, PATH."""
    env = {"llama-cli": "MUTA_RT_LLAMA_CLI_BIN", "llama-server": "MUTA_RT_LLAMA_SERVER_BIN"}
    import os

    if (v := os.environ.get(env.get(name, ""))) and Path(v).exists():
        return v
    local = REPO_ROOT / "runtime" / "build" / "bin" / name
    if local.exists():
        return str(local)
    return shutil.which(name)


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(
            f"FATAL: {MANIFEST_PATH} not found — run scripts/fetch_models.sh first.",
            file=sys.stderr,
        )
        sys.exit(2)
    return json.loads(MANIFEST_PATH.read_text())


# ======================================================================================
# checks
# ======================================================================================


def check_hashes(manifest: dict) -> None:
    """Every fetched artifact exists on disk and its sha256 still matches."""
    for a in manifest["artifacts"]:
        if not a.get("fetched"):
            record(f"hash/{a['name']}", SKIP, "not fetched (tier B, recorded only)", expected=True)
            continue
        entries = a.get("files") or [
            {"path": a["path"], "sha256": a["sha256"], "bytes": a["bytes"]}
        ]
        bad = []
        for e in entries:
            p = REPO_ROOT / e["path"]
            if not p.exists():
                bad.append(f"{e['path']}: MISSING")
                continue
            actual = sha256_file(p)
            if actual != e["sha256"]:
                bad.append(f"{e['path']}: sha256 {actual[:16]}… != {e['sha256'][:16]}…")
        if bad:
            record(f"hash/{a['name']}", FAIL, "; ".join(bad))
        else:
            record(f"hash/{a['name']}", PASS, f"{len(entries)} file(s), {human(a['bytes'])}")


def check_resident_budget(manifest: dict) -> None:
    total = sum(
        a["bytes"] for a in manifest["artifacts"] if a["tier"] == "resident" and a.get("fetched")
    )
    detail = f"{human(total)} vs cap {human(RESIDENT_CAP_BYTES)}"
    record(
        "budget/resident-tier",
        PASS if total <= RESIDENT_CAP_BYTES else FAIL,
        detail
        + (f" — OVER by {human(total - RESIDENT_CAP_BYTES)}" if total > RESIDENT_CAP_BYTES else ""),
    )


def check_licenses(manifest: dict) -> None:
    bad = [
        f"{a['name']}={a['license']}"
        for a in manifest["artifacts"]
        if a["license"] not in ALLOWED_LICENSES
    ]
    if bad:
        record("license/policy", FAIL, "non-permissive: " + ", ".join(bad))
    else:
        record(
            "license/policy",
            PASS,
            f"{len(manifest['artifacts'])} artifacts, all permissive",
        )
    missing = [
        a["name"]
        for a in manifest["artifacts"]
        if a.get("fetched")
        and not list((REPO_ROOT / "models" / "LICENSES").glob(f"{a['name']}.*.txt"))
    ]
    record(
        "license/texts",
        FAIL if missing else PASS,
        f"missing text for {missing}" if missing else "all fetched artifacts have text",
    )


def artifact(manifest: dict, name: str) -> dict | None:
    for a in manifest["artifacts"]:
        if a["name"] == name:
            return a
    return None


def check_core_loads(manifest: dict) -> None:
    a = artifact(manifest, "core")
    if not a or not a.get("fetched"):
        record("load/core", SKIP, "core not fetched", expected=True)
        return
    cli = find_bin("llama-cli")
    if not cli:
        record("load/core", SKIP, "llama-cli not found (brew install llama.cpp, or make build)")
        return
    # `-st` (single turn) is load-bearing, not decoration. Modern llama-cli defaults to
    # conversation mode for chat models, so the bare invocation in TDD T2 never exits: it
    # sits at an interactive `>` prompt. Passing `-no-cnv` is *worse* — at stdin EOF it
    # spins printing prompts and produced 916 MB of stdout here before being killed, which
    # would OOM a CI runner rather than fail it. `-st` generates and exits cleanly.
    cmd = [
        cli, "-m", str(REPO_ROOT / a["path"]),
        "-p", "2+2=", "-n", "8", "--no-warmup", "-st",
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        record(
            "load/core",
            FAIL,
            "llama-cli timed out after 300s — check it is not sitting at an interactive "
            "prompt (`-st` should prevent that)",
        )
        return
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
        record("load/core", FAIL, f"exit {r.returncode}: {' | '.join(tail)}")
    else:
        record("load/core", PASS, "llama-cli generated 8 tokens without error")


def check_embed_loads(manifest: dict) -> None:
    a = artifact(manifest, "embed")
    if not a or not a.get("fetched"):
        record("load/embed", SKIP, "embed not fetched", expected=True)
        return
    exe = find_bin("llama-embedding")
    path = REPO_ROOT / a["path"]
    try:
        # Expected dimensionality comes from the file itself, not a hardcoded 384.
        expected_dim = read_metadata(path).arch_key("embedding_length")
    except Exception:
        expected_dim = None
    if not exe:
        record(
            "load/embed",
            SKIP,
            f"llama-embedding not found (gguf metadata says dim={expected_dim})",
        )
        return
    cmd = [exe, "-m", str(path), "-p", "test", "--pooling", "cls"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        record("load/embed", FAIL, "llama-embedding timed out")
        return
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
        record("load/embed", FAIL, f"exit {r.returncode}: {' | '.join(tail)}")
        return
    floats = [t for t in r.stdout.split() if _is_float(t)]
    if expected_dim and len(floats) != expected_dim:
        record("load/embed", FAIL, f"got {len(floats)} floats, expected dim {expected_dim}")
    else:
        record("load/embed", PASS, f"returned a {len(floats)}-dim vector (--pooling cls)")


def _is_float(t: str) -> bool:
    # llama-embedding prints "embedding 0: -0.031531  0.023092 …". Requiring a decimal
    # point keeps the "0:" index token out of the dimensionality count.
    if "." not in t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def check_kv_metadata(manifest: dict) -> None:
    """TDD §5.2: the slot table is provisional until it is re-derived from the real file."""
    a = artifact(manifest, "core")
    if not a or not a.get("fetched"):
        record("kv/metadata", SKIP, "core not fetched", expected=True)
        return
    try:
        md = read_metadata(REPO_ROOT / a["path"])
    except Exception as exc:
        record("kv/metadata", FAIL, f"could not read GGUF metadata: {exc}")
        return
    if not (md.n_layer and md.n_kv_head and md.head_dim_k):
        record(
            "kv/metadata",
            FAIL,
            "GGUF is missing block_count / head_count_kv / key_length — the slot table "
            "cannot be derived, and guessing it puts an OOM risk on the target box",
        )
        return

    facts = {
        "_note": (
            "Generated by scripts/verify_models.sh from the shipped GGUF's own metadata. "
            "TDD §5.2's slot table is provisional until it is regenerated from these "
            "values (T5, `make kv-budget`)."
        ),
        "source_file": a["path"],
        "repo": a["repo"],
        "revision": a["revision"],
        "architecture": md.architecture,
        "block_count": md.n_layer,
        "n_attn_layer": md.n_attn_layer,
        "head_count": md.n_head,
        "head_count_kv": md.n_kv_head,
        "key_length": md.head_dim_k,
        "value_length": md.head_dim_v,
        "trained_context": md.trained_context,
        "kv_bytes_per_token": {},
        "kv_mib_per_slot": {},
    }
    for ct in ("f16", "q8_0", "q5_1"):
        cost = KVCost.from_metadata(md, cache_type=ct)
        facts["kv_bytes_per_token"][ct] = round(cost.bytes_per_token, 2)
        facts["kv_mib_per_slot"][ct] = {
            str(ctx): round(cost.mib_for(ctx), 1) for ctx in (2048, 4096, 8192)
        }

    KV_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    KV_METADATA_PATH.write_text(json.dumps(facts, indent=2) + "\n")
    record(
        "kv/metadata",
        PASS,
        f"block_count={md.n_layer} head_count_kv={md.n_kv_head} "
        f"key_length={md.head_dim_k} -> {KV_METADATA_PATH.relative_to(REPO_ROOT)}",
    )


def _sherpa():
    try:
        import sherpa_onnx  # noqa: F401

        return sherpa_onnx
    except ImportError:
        return None


def check_asr(manifest: dict) -> None:
    a = artifact(manifest, "asr")
    if not a or not a.get("fetched"):
        record("smoke/asr", SKIP, "asr not fetched", expected=True)
        return
    sherpa = _sherpa()
    if sherpa is None:
        record("smoke/asr", SKIP, "sherpa_onnx not installed (pip install sherpa-onnx)")
        return
    d = REPO_ROOT / a["path"]
    try:
        import numpy as np

        rec = sherpa.OfflineRecognizer.from_moonshine(
            preprocessor=str(d / "preprocess.onnx"),
            encoder=str(d / "encode.int8.onnx"),
            uncached_decoder=str(d / "uncached_decode.int8.onnx"),
            cached_decoder=str(d / "cached_decode.int8.onnx"),
            tokens=str(d / "tokens.txt"),
        )
        s = rec.create_stream()
        s.accept_waveform(16000, np.zeros(16000, dtype=np.float32))  # 1 s of silence
        rec.decode_stream(s)
        record("smoke/asr", PASS, f"recognizer built; 1s silence -> {s.result.text!r}")
    except Exception as exc:
        record("smoke/asr", FAIL, f"{type(exc).__name__}: {exc}")


def check_vad(manifest: dict) -> None:
    a = artifact(manifest, "vad")
    if not a or not a.get("fetched"):
        record("smoke/vad", SKIP, "vad not fetched", expected=True)
        return
    sherpa = _sherpa()
    if sherpa is None:
        record("smoke/vad", SKIP, "sherpa_onnx not installed")
        return
    try:
        cfg = sherpa.VadModelConfig()
        cfg.silero_vad.model = str(REPO_ROOT / a["path"])
        cfg.sample_rate = 16000
        sherpa.VoiceActivityDetector(cfg, buffer_size_in_seconds=10)
        record("smoke/vad", PASS, "sherpa-onnx accepted silero_vad.onnx")
    except Exception as exc:
        # This is the check that earns the choice of the MIT-licensed VAD mirror.
        record("smoke/vad", FAIL, f"{type(exc).__name__}: {exc}")


def check_tts(manifest: dict) -> None:
    a = artifact(manifest, "tts")
    if not a or not a.get("fetched"):
        record("smoke/tts", SKIP, "tts not fetched", expected=True)
        return
    sherpa = _sherpa()
    if sherpa is None:
        record("smoke/tts", SKIP, "sherpa_onnx not installed")
        return
    d = REPO_ROOT / a["path"]
    onnx = next((p for p in d.glob("*.onnx")), None)
    if onnx is None:
        record("smoke/tts", FAIL, f"no .onnx voice under {d}")
        return
    try:
        cfg = sherpa.OfflineTtsConfig(
            model=sherpa.OfflineTtsModelConfig(
                vits=sherpa.OfflineTtsVitsModelConfig(
                    model=str(onnx),
                    tokens=str(d / "tokens.txt"),
                    data_dir=str(d / "espeak-ng-data"),
                ),
                num_threads=1,
            )
        )
        tts = sherpa.OfflineTts(cfg)
        audio = tts.generate("test", sid=0, speed=1.0)
        n = len(audio.samples)
        if n == 0:
            record("smoke/tts", FAIL, "synthesized 0 samples for 'test'")
        else:
            record(
                "smoke/tts",
                PASS,
                f"synthesized {n} samples @ {audio.sample_rate} Hz "
                f"({n / audio.sample_rate:.2f}s) for 'test'",
            )
    except Exception as exc:
        record("smoke/tts", FAIL, f"{type(exc).__name__}: {exc}")


# ======================================================================================


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="verify_models.sh")
    p.add_argument("--strict", action="store_true", help="treat SKIP (missing tooling) as failure")
    args = p.parse_args(argv)

    manifest = load_manifest()
    print("=" * 86)
    print(f"Muta model verification — manifest generated {manifest['generated_at']}")
    print("=" * 86)

    check_hashes(manifest)
    check_resident_budget(manifest)
    check_licenses(manifest)
    check_kv_metadata(manifest)
    check_core_loads(manifest)
    check_embed_loads(manifest)
    check_asr(manifest)
    check_vad(manifest)
    check_tts(manifest)

    print("\n" + "=" * 86)
    print(f"{'name':<30}{'tier':<12}{'size':>12}  {'license':<14}status")
    print("-" * 86)
    for a in manifest["artifacts"]:
        st = "fetched" if a.get("fetched") else "recorded-only"
        print(f"{a['name']:<30}{a['tier']:<12}{human(a['bytes']):>12}  {a['license']:<14}{st}")
    print("-" * 86)

    n_fail = sum(1 for _, s, _, _ in results if s == FAIL)
    n_pass = sum(1 for _, s, _, _ in results if s == PASS)
    expected_skips = [r for r in results if r[1] == SKIP and r[3]]
    blocked_skips = [r for r in results if r[1] == SKIP and not r[3]]
    print(
        f"checks: {n_pass} passed, {n_fail} failed, "
        f"{len(blocked_skips)} skipped for missing tooling, "
        f"{len(expected_skips)} skipped by design"
    )
    if n_fail:
        print("\nfailures:")
        for name, s, detail, _ in results:
            if s == FAIL:
                print(f"  FAIL {name} — {detail}")
    if blocked_skips:
        print("\nnot verified — tooling absent (--strict fails on these):")
        for name, _, detail, _ in blocked_skips:
            print(f"  skip {name} — {detail}")
    if expected_skips:
        print("\nskipped by design (artifact deliberately not fetched):")
        for name, _, detail, _ in expected_skips:
            print(f"  skip {name} — {detail}")
    print("=" * 86)

    if n_fail:
        return 1
    # --strict fails on missing tooling, never on a tier B artifact we chose not to fetch.
    if args.strict and blocked_skips:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
