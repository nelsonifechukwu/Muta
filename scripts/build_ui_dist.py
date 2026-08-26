#!/usr/bin/env python3
"""Build the fully offline browser UI from checked-in sources and pinned vendor assets."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import ssl
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

import certifi

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
OUTPUT = UI / "dist"
TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())

UI_FILES = (
    "VISUALIZATION-LICENSES.txt",
    "access-bootstrap.js",
    "africa-languages.js",
    "app.js",
    "audio.js",
    "citations.js",
    "i18n.js",
    "image-upload.js",
    "index.html",
    "locale-bootstrap.js",
    "locale-fr.js",
    "locale-generated.js",
    "locale-manifest.js",
    "locales.js",
    "math.js",
    "parallel-policy.js",
    "popover-position.js",
    "product-analytics.js",
    "release-english.js",
    "release-lifecycle.js",
    "resource-mentions.js",
    "startup.js",
    "styles.css",
    "syntax.js",
    "theme.js",
    "visualizations.js",
    "viz-frame.css",
    "viz-frame.html",
    "viz-frame.js",
    "viz-theme.js",
    "worklet.js",
)

DOWNLOADS = {
    "katex.tar.gz": (
        "https://github.com/KaTeX/KaTeX/releases/download/v0.16.11/katex.tar.gz",
        "b968d389d7b9455e191605e4984c52faf3123213271880b02abc45e6ad4bbf43",
    ),
    "marked.min.js": (
        "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js",
        "15fabce5b65898b32b03f5ed25e9f891a729ad4c0d6d877110a7744aa847a894",
    ),
    "purify.min.js": (
        "https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js",
        "c0845096a7c4a6741f362ac506c94c1c7d27dc603bcc1bf64a587f76f2dbe3a1",
    ),
}

VIZ_HASHES = {
    "anime.v3.2.2.min.js": "b5ce1be3c3f530f192e0f2571d1942846096d66119cbada34bfdc912c4873f35",
    "d3.v7.9.0.min.js": "f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539",
    "gsap.v3.13.0.min.js": "96c01b81f44a3290e2b4532f55e2c9534b2adc43273a19f3756b2cb41f0fd0b6",
    "motion.v11.11.13.js": "1137223e57ddbf0e60be9e08340e529e6e2ae4967650b39212fe97f4e57285ea",
    "three.r160.min.js": "170c6789f43217c96b3170f4b42fafe135de7f7cd48497a4218f9757ee1d49fa",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected: str) -> None:
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Muta-Packager/1"})
            with (
                urllib.request.urlopen(request, timeout=60, context=TLS_CONTEXT) as response,
                destination.open("wb") as stream,
            ):
                shutil.copyfileobj(response, stream)
            if sha256(destination) != expected:
                raise RuntimeError(f"downloaded asset has the wrong SHA-256: {url}")
            return
        except (OSError, RuntimeError):
            destination.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def extract_katex(archive: Path, vendor: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                raise RuntimeError(f"unsafe KaTeX archive member: {member.name}")
        bundle.extractall(vendor, members=members)
    if not (vendor / "katex" / "katex.min.js").is_file():
        raise RuntimeError("pinned KaTeX archive is incomplete")


def build() -> None:
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir(parents=True)
    for name in UI_FILES:
        source = UI / name
        if not source.is_file():
            raise RuntimeError(f"required UI source is missing: {source}")
        shutil.copy2(source, OUTPUT / name)

    vendor = OUTPUT / "vendor"
    viz_source = UI / "vendor" / "viz"
    shutil.copytree(viz_source, vendor / "viz")
    for name, expected in VIZ_HASHES.items():
        if sha256(vendor / "viz" / name) != expected:
            raise RuntimeError(f"checked-in visualization asset has the wrong SHA-256: {name}")

    with tempfile.TemporaryDirectory(prefix="muta-ui-") as temp_name:
        temp = Path(temp_name)
        for name, (url, expected) in DOWNLOADS.items():
            download(url, temp / name, expected)
        extract_katex(temp / "katex.tar.gz", vendor)
        shutil.copy2(temp / "marked.min.js", vendor / "marked.min.js")
        shutil.copy2(temp / "purify.min.js", vendor / "purify.min.js")


def verify() -> None:
    if not OUTPUT.is_dir():
        raise RuntimeError(f"offline UI output is missing: {OUTPUT}")
    for name in UI_FILES:
        source = UI / name
        output = OUTPUT / name
        if not output.is_file() or sha256(output) != sha256(source):
            raise RuntimeError(f"offline UI cache is stale or corrupt: {name}")

    vendor = OUTPUT / "vendor"
    for name, expected in VIZ_HASHES.items():
        candidate = vendor / "viz" / name
        if not candidate.is_file() or sha256(candidate) != expected:
            raise RuntimeError(f"offline UI visualization cache is corrupt: {name}")
    for name in ("marked.min.js", "purify.min.js"):
        candidate = vendor / name
        expected = DOWNLOADS[name][1]
        if not candidate.is_file() or sha256(candidate) != expected:
            raise RuntimeError(f"offline UI vendor cache is corrupt: {name}")
    if not (vendor / "katex" / "katex.min.js").is_file():
        raise RuntimeError("offline UI KaTeX cache is incomplete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        verify()
    else:
        build()
        verify()
    print(OUTPUT)
