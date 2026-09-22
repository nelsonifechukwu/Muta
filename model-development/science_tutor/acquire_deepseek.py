"""Acquire the user-requested public DeepSeek parent once, at an exact revision.

No model execution, credentials, cache duplication, retries or overwrites.
Verify small files by HF Git blob identity and weights by published LFS SHA256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

REPOSITORY = "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
REVISION = "ad9f0ae0864d7fbcd1cd905e3c6c5b069cc8b562"
FILES = {
    "LICENSE": (1064, "git", "d42fae903e9fa07f3e8edb0db00a8d905ba49560"),
    "README.md": (15994, "git", "1ae2b2ccda9cb58fb4179e30c1798b6e75980618"),
    "config.json": (679, "git", "68c044b63c894bc0c3d334a44bed2856d6d6815d"),
    "generation_config.json": (181, "git", "052ab54633116a634da950ab483233c4ace0aa82"),
    "model.safetensors": (
        3554214621,
        "sha256",
        "58858233513d76b8703e72eed6ce16807b523328188e13329257fb9594462945",
    ),
    "tokenizer.json": (7031660, "git", "a34650995da6939a945c330eadb0687147ac3ef8"),
    "tokenizer_config.json": (3071, "git", "9967ff32d94b21c94dc7e2b3bcbea295a46cde50"),
}


def save(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def acquire(output, receipt):
    if not output.is_absolute() or not receipt.is_absolute():
        raise ValueError("absolute paths required")
    if output.exists() or receipt.exists() or output.is_symlink() or receipt.is_symlink():
        raise FileExistsError("acquisition target/receipt already exists")
    output.mkdir(parents=True, exist_ok=False)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "revision": REVISION,
        "started_unix": time.time(),
        "files": [],
        "automatic_retry": False,
    }
    try:
        for name, (size, kind, expected) in FILES.items():
            url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
            sha = hashlib.sha256()
            git = hashlib.sha1(f"blob {size}\0".encode())
            count = 0
            # A partial file is preserved if network/content verification fails.
            with (
                urllib.request.urlopen(url, timeout=60) as response,
                (output / name).open("xb") as target,
            ):
                for chunk in iter(lambda: response.read(8 * 1024 * 1024), b""):
                    target.write(chunk)
                    sha.update(chunk)
                    git.update(chunk)
                    count += len(chunk)
            identity = sha.hexdigest() if kind == "sha256" else git.hexdigest()
            if count != size or identity != expected:
                raise ValueError(f"pinned content verification failed: {name}")
            manifest["files"].append(
                {
                    "path": name,
                    "url": url,
                    "bytes": count,
                    "sha256": sha.hexdigest(),
                    "publisher_identity_kind": kind,
                    "publisher_identity": expected,
                }
            )
            print(json.dumps({"verified": name, "bytes": count}), flush=True)
        manifest["tree_sha256"] = hashlib.sha256(
            "\n".join(
                f"{row['sha256']}  {row['path']}"
                for row in sorted(manifest["files"], key=lambda r: r["path"])
            ).encode()
        ).hexdigest()
        manifest.update(
            status="complete",
            ended_unix=time.time(),
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        )
        save(receipt, manifest)
        return manifest
    except BaseException as error:
        manifest.update(
            status="failed",
            error_type=type(error).__name__,
            error=str(error),
            ended_unix=time.time(),
        )
        save(receipt, manifest)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.output, args.receipt)))
