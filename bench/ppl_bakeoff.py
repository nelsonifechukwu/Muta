"""Append-only, provenance-complete llama-perplexity screen for one model family."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
import time
from pathlib import Path

PPL_RE = re.compile(r"Final estimate:\s*PPL\s*=\s*([0-9.]+)\s*\+/-\s*([0-9.]+)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ppl(output: str) -> tuple[float, float]:
    match = PPL_RE.search(output)
    if not match:
        raise ValueError("llama-perplexity output has no final estimate")
    return float(match.group(1)), float(match.group(2))


def append_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--chunks", type=int, default=12)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--hardware-context", default="dev_host_provisional")
    args = parser.parse_args(argv)

    missing = [path for path in [*args.models, args.binary, args.corpus] if not path.is_file()]
    if missing:
        parser.error(f"missing inputs: {missing}")

    binary_sha = sha256(args.binary)
    corpus_sha = sha256(args.corpus)
    model_hashes = {model: sha256(model) for model in args.models}
    failed = False
    for round_number in range(1, args.rounds + 1):
        for model in args.models:
            command = [
                str(args.binary),
                "-m",
                str(model),
                "-f",
                str(args.corpus),
                "-c",
                "512",
                "-b",
                "512",
                "--chunks",
                str(args.chunks),
                "-t",
                str(args.threads),
                "-ngl",
                "0",
            ]
            print(f"[ppl] round {round_number} {model.name}", flush=True)
            started = time.monotonic()
            proc = subprocess.run(command, capture_output=True, text=True, check=False)
            combined = proc.stdout + "\n" + proc.stderr
            row = {
                "schema_version": 1,
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "hardware_context": args.hardware_context,
                "host": platform.platform(),
                "round": round_number,
                "model": model.name,
                "model_path": str(model.resolve()),
                "model_bytes": model.stat().st_size,
                "model_sha256": model_hashes[model],
                "binary_path": str(args.binary.resolve()),
                "binary_sha256": binary_sha,
                "corpus_path": str(args.corpus.resolve()),
                "corpus_sha256": corpus_sha,
                "chunks": args.chunks,
                "threads": args.threads,
                "command": command,
                "rc": proc.returncode,
                "wall_s": round(time.monotonic() - started, 1),
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-4000:],
            }
            try:
                ppl, uncertainty = parse_ppl(combined)
            except ValueError as exc:
                row.update({"ok": False, "error": str(exc)})
            else:
                row.update({"ok": proc.returncode == 0, "ppl": ppl, "ppl_uncertainty": uncertainty})
            failed = failed or not row["ok"]
            append_row(args.out, row)
            print(f"  -> {row.get('ppl')} +/- {row.get('ppl_uncertainty')}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
