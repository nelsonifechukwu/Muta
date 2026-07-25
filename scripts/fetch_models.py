#!/usr/bin/env python3
"""Fetch, pin, verify and manifest every model artifact the offline tutor ships (TDD T2).

Build-machine only. This is the one step in the system allowed to touch the network
(TDD §2 C-4, §11.2); nothing it writes needs network access at run time.

Contract:
  * resolve   — confirm repo + exact filename exist on the Hub before downloading anything
  * pin       — record the commit SHA, so a re-run fetches byte-identical files
  * verify    — sha256 after download AND again after the copy into models/
  * license   — capture SPDX id + license text; refuse anything non-permissive
  * report    — on-disk size per artifact vs the TDD planning value, flagged at +/-20%

Run `scripts/fetch_models.sh --help` for the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model_specs import (  # noqa: E402
    ALLOWED_LICENSES,
    ARTIFACTS,
    QUANT_VARIANTS,
    UNRESOLVED,
    Artifact,
    GiB,
    MiB,
)

# Set before huggingface_hub is imported anywhere (it reads these at import time).
# A multi-GiB fetch over a flaky link can leave a half-open socket that never delivers
# another byte and never errors — observed in practice on the core model. A bounded read
# timeout turns "hangs forever unattended" into "fails and can be resumed", and resume is
# free: hf_hub_download continues from the .incomplete blob and the hash check still runs.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")

REPO_ROOT = Path(__file__).resolve().parent.parent
PINS_PATH = REPO_ROOT / "models" / "pins.lock.json"
MANIFEST_PATH = REPO_ROOT / "models" / "MANIFEST.json"
LICENSES_DIR = REPO_ROOT / "models" / "LICENSES"

# The resident tier must fit this budget (T2 acceptance check).
RESIDENT_CAP_BYTES = int(3.3 * GiB)
SIZE_TOLERANCE = 0.20


# ======================================================================================
# small helpers
# ======================================================================================


def human(n: int) -> str:
    if n >= GiB:
        return f"{n / GiB:.2f} GiB"
    if n >= MiB:
        return f"{n / MiB:.1f} MiB"
    return f"{n} B"


def sha256_file(path: Path, _buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_buf):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Stop(Exception):
    """Unrecoverable: resolution failed or policy was violated. Never downgraded."""


def log(msg: str = "") -> None:
    print(msg, flush=True)


# ======================================================================================
# Hub access
# ======================================================================================


def make_api(use_token: bool):
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:  # pragma: no cover
        raise Stop(
            "huggingface_hub is not installed. `pip install huggingface_hub` on the build "
            "machine (this dependency is build-time only and never ships)."
        ) from exc
    # Default to anonymous: every pinned repo is public, and a stale cached OAuth token
    # makes the Hub return 401 on calls that would otherwise succeed. Opt in with
    # --use-token if you need gated access.
    return HfApi(token=None if use_token else False)


@dataclass
class Resolution:
    repo: str
    revision: str
    files: list[str]
    hub_license: str | None
    sizes: dict[str, int]  # filename -> bytes, as reported by the Hub

    @property
    def total_bytes(self) -> int:
        return sum(self.sizes.get(f, 0) for f in self.files)


def resolve(api, art: Artifact, locked_rev: str | None) -> Resolution:
    """Confirm the pin still points at something real, and fix it to a commit SHA."""
    from huggingface_hub.utils import RepositoryNotFoundError, RevisionNotFoundError

    try:
        info = api.model_info(art.repo, revision=locked_rev, files_metadata=True)
    except (RepositoryNotFoundError, RevisionNotFoundError) as exc:
        at = f"@{locked_rev}" if locked_rev else ""
        raise Stop(
            f"[{art.name}] cannot resolve {art.repo}{at}: {exc}\n" + candidate_report(api, art)
        ) from exc

    revision = locked_rev or info.sha
    repo_files = [s.rfilename for s in (info.siblings or [])]

    if art.file:
        if art.file not in repo_files:
            raise Stop(
                f"[{art.name}] {art.repo}@{revision[:12]} does not contain "
                f"{art.file!r}.\n" + candidate_report(api, art)
            )
        wanted = [art.file]
    else:
        wanted = [
            f
            for f in repo_files
            if any(fnmatch(f, p) for p in art.patterns)
            and not any(fnmatch(f, p) for p in art.ignore)
        ]
        if not wanted:
            raise Stop(
                f"[{art.name}] {art.repo}@{revision[:12]} matched none of "
                f"{art.patterns}.\n" + candidate_report(api, art)
            )

    hub_license = (info.cardData or {}).get("license") if info.cardData else None
    sizes = {s.rfilename: (s.size or 0) for s in (info.siblings or [])}
    return Resolution(art.repo, revision, sorted(wanted), hub_license, sizes)


def candidate_report(api, art: Artifact) -> str:
    """Hard rule 1: on failure, print what we DID find — never substitute silently."""
    if not art.search:
        return "    (no search terms recorded for this artifact)"
    lines = [
        f"    Candidates for {art.search!r} (download counts + last modified) — pick one",
        "    deliberately and update scripts/model_specs.py; do NOT let the script guess:",
    ]
    try:
        found = list(api.list_models(search=art.search, sort="downloads", limit=15))
    except Exception as exc:  # network/API trouble is itself worth reporting
        return f"    (candidate search failed: {exc})"
    if not found:
        lines.append("      <no candidates matched>")
    for m in found:
        mod = getattr(m, "lastModified", None)
        mod = mod.date().isoformat() if hasattr(mod, "date") else str(mod)
        lines.append(f"      {m.id:64s} dl={m.downloads or 0:<10} mod={mod}")
    if art.rejected:
        lines.append("    Previously rejected, with reasons:")
        lines += [f"      - {r}" for r in art.rejected]
    return "\n".join(lines)


# ======================================================================================
# licenses
# ======================================================================================


def capture_license(api, art: Artifact, revision: str, dry_run: bool) -> tuple[str, str]:
    """Return (spdx, url) and write the license text into models/LICENSES/."""
    spdx = art.license.spdx
    url = art.license.locator()

    if spdx not in ALLOWED_LICENSES:
        raise Stop(
            f"[{art.name}] license {spdx!r} is not on the permissive allow-list "
            f"{sorted(ALLOWED_LICENSES)}. This bundle is redistributed to third parties "
            f"(TDD §13), so a non-permissive artifact is a ship blocker, not a warning.\n"
            f"    source: {url}\n"
            f"    note:   {art.license.note}"
        )
    if dry_run:
        return spdx, url

    LICENSES_DIR.mkdir(parents=True, exist_ok=True)
    out = LICENSES_DIR / f"{art.name}.{spdx}.txt"
    header = (
        f"# artifact : {art.name}\n"
        f"# repo     : {art.repo}@{revision}\n"
        f"# spdx     : {spdx}\n"
        f"# source   : {url}\n"
        f"# note     : {art.license.note}\n"
        f"{'-' * 78}\n"
    )
    body = _license_text(api, art)
    out.write_text(header + body, encoding="utf-8")
    return spdx, url


def _license_text(api, art: Artifact) -> str:
    from huggingface_hub import hf_hub_download

    if art.license.repo and art.license.path:
        try:
            p = hf_hub_download(repo_id=art.license.repo, filename=art.license.path, token=False)
            return Path(p).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log(f"    ! license file fetch failed ({exc}); falling back to canonical text")
    target = art.license.url or ""
    from model_specs import SPDX_TEXT_URL

    target = target or SPDX_TEXT_URL.get(art.license.spdx, "")
    if not target:
        return f"<no license text available for {art.license.spdx}>\n"
    try:
        with urllib.request.urlopen(target, timeout=30) as r:  # noqa: S310
            return r.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"<could not retrieve license text from {target}: {exc}>\n"


# ======================================================================================
# download + double verification
# ======================================================================================


CHUNK_BYTES = 16 * MiB
CHUNK_RETRIES = 6
RANGED_THRESHOLD = 64 * MiB  # above this, don't trust a single long-lived GET


def download_ranged(repo: str, filename: str, revision: str, target: Path, size: int) -> None:
    """Download a large file in bounded HTTP range requests, resuming into a .part file.

    `hf_hub_download` streams one long-lived GET. On a slow or lossy link that connection
    can die mid-body without raising: the socket stays open, no more bytes arrive, and the
    build hangs indefinitely (observed at ~256 MiB on the 2.5 GiB core model — twice, at
    byte-identical offsets, while ranged requests to the same URL kept working).

    Bounded chunks make every request short enough to either finish or fail fast, and the
    .part file means a failure costs one chunk rather than the whole download. The pinned
    revision is in the URL, so this is still fetching exactly what the manifest records —
    and the caller hashes the result either way, so a truncated chunk cannot go unnoticed.
    """
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
    part = target.with_suffix(target.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > size:  # a stale .part from a different revision
        part.unlink()
        have = 0

    while have < size:
        end = min(have + CHUNK_BYTES, size) - 1
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-{end}"})
        for attempt in range(1, CHUNK_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                    data = resp.read()
                break
            except Exception as exc:
                if attempt == CHUNK_RETRIES:
                    raise Stop(
                        f"{filename}: range {have}-{end} failed after {CHUNK_RETRIES} "
                        f"attempts: {exc}. Re-run to resume from {human(have)}."
                    ) from exc
                log(f"      retry {attempt}/{CHUNK_RETRIES} at {human(have)} ({exc})")
        if not data:
            raise Stop(f"{filename}: server returned an empty range at offset {have}")
        with part.open("ab") as fh:
            fh.write(data)
        have = part.stat().st_size
        pct = 100 * have / size
        log(f"      {human(have)} / {human(size)}  ({pct:.1f}%)")

    part.replace(target)


@dataclass
class FetchedFile:
    name: str  # filename within the source repo (the pin key)
    relpath: str  # path relative to repo root
    bytes: int
    sha256: str


def fetch_files(art: Artifact, res: Resolution, locked: dict, force: bool) -> list[FetchedFile]:
    """Download each file, hashing it in the cache and again at its destination."""
    from huggingface_hub import hf_hub_download

    dest_dir = REPO_ROOT / art.dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    locked_files = (locked or {}).get("files", {})
    out: list[FetchedFile] = []

    # Directory artifacts are many small files (Piper and Kokoro each carry ~355 espeak-ng
    # dictionaries). Fetched one at a time the cost is per-request latency, not bandwidth —
    # measured at roughly 20 s/file here, i.e. ~2 hours for 17 MiB. snapshot_download pulls
    # them concurrently in one pass; the per-file hash/copy/re-hash below is unchanged, so
    # this buys speed without weakening the double verification.
    snapshot: Path | None = None
    if art.is_dir and len(res.files) > 8:
        from huggingface_hub import snapshot_download

        log(f"    v {len(res.files)} files via snapshot_download (concurrent)")
        snapshot = Path(
            snapshot_download(
                repo_id=res.repo,
                revision=res.revision,
                allow_patterns=list(art.patterns) or None,
                ignore_patterns=list(art.ignore) or None,
                max_workers=8,
                token=False,
            )
        )

    for name in res.files:
        # Directory artifacts keep their internal structure (espeak-ng-data/... etc).
        target = dest_dir / name if art.is_dir else dest_dir / Path(name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        rel = str(target.relative_to(REPO_ROOT))
        expected = locked_files.get(name, {}).get("sha256")

        # Idempotency: a present file whose hash matches the lock is not re-downloaded.
        if not force and expected and target.exists():
            actual = sha256_file(target)
            if actual == expected:
                log(f"    = {rel}  ({human(target.stat().st_size)}, hash ok, skipped)")
                out.append(FetchedFile(name, rel, target.stat().st_size, actual))
                continue
            log(f"    ! {rel} present but hash differs — refetching")

        # Large files go through the ranged downloader (see download_ranged); small ones
        # use hf_hub_download, which dedupes them in the shared HF cache. Either way the
        # bytes land in a staging location first, so the double verification below is
        # identical for both paths.
        size_hint = res.sizes.get(name, 0)
        if snapshot is not None:
            cached = snapshot / name
            if not cached.exists():
                raise Stop(f"[{art.name}] {name} missing from snapshot at {snapshot}")
        elif size_hint >= RANGED_THRESHOLD:
            staging = REPO_ROOT / "models" / ".staging" / res.repo.replace("/", "_")
            staging.mkdir(parents=True, exist_ok=True)
            cached = staging / name.replace("/", "_")
            log(f"    v {rel}  ({human(size_hint)}, ranged)")
            download_ranged(res.repo, name, res.revision, cached, size_hint)
        else:
            cached = Path(
                hf_hub_download(repo_id=res.repo, filename=name, revision=res.revision, token=False)
            )

        # Verification #1 — the bytes as downloaded.
        sha_src = sha256_file(cached)
        if expected and sha_src != expected:
            raise Stop(
                f"[{art.name}] {name}: downloaded content does not match the pinned hash.\n"
                f"    expected {expected}\n    got      {sha_src}\n"
                f"    repo {res.repo}@{res.revision} — the pin moved or the file was "
                f"rewritten upstream. Re-run with --repin only after confirming why."
            )

        shutil.copyfile(cached, target)

        # Verification #2 — the bytes after the copy. Cheap flash bitrots (TDD §10.2).
        sha_dst = sha256_file(target)
        if sha_dst != sha_src:
            raise Stop(
                f"[{art.name}] {rel}: sha256 changed across the copy.\n"
                f"    source {sha_src}\n    dest   {sha_dst}\n"
                f"    The copy is corrupt — this is exactly the failure the double check "
                f"exists to catch. Do not ship this file."
            )

        size = target.stat().st_size
        # Only now that both hashes agree is it safe to drop the staged copy. Doing this
        # earlier would trade a 2.5 GiB disk spike for an unrecoverable download.
        if cached.is_relative_to(REPO_ROOT / "models" / ".staging"):
            cached.unlink(missing_ok=True)
        log(f"    + {rel}  ({human(size)})  sha256={sha_dst[:16]}…")
        out.append(FetchedFile(name, rel, size, sha_dst))

    return out


# ======================================================================================
# orchestration
# ======================================================================================


def select(args) -> list[Artifact]:
    enabled_flags = {
        "--with-multilingual-asr": args.with_multilingual_asr,
        "--with-kokoro": args.with_kokoro,
        "--with-draft": args.with_draft,
        "--quant-variants": args.quant_variants,
    }
    pool = list(ARTIFACTS) + list(QUANT_VARIANTS)
    if args.only:
        names = set(args.only)
        unknown = names - {a.name for a in pool}
        if unknown:
            raise Stop(
                f"--only: unknown artifact(s) {sorted(unknown)}. "
                f"Known: {sorted(a.name for a in pool)}"
            )
        pool = [a for a in pool if a.name in names]

    out = []
    for a in pool:
        # Quant variants are never implicit — they only appear via their flag.
        if a in QUANT_VARIANTS and not enabled_flags["--quant-variants"]:
            continue
        out.append(a)
    return out


def will_fetch(art: Artifact, args) -> bool:
    """Gated artifacts need their flag. `--only draft` alone is NOT consent to download it."""
    if art.flag is None:
        return True
    return bool(
        {
            "--with-multilingual-asr": args.with_multilingual_asr,
            "--with-kokoro": args.with_kokoro,
            "--with-draft": args.with_draft,
            "--quant-variants": args.quant_variants,
        }[art.flag]
    )


def load_pins() -> dict:
    if PINS_PATH.exists():
        return json.loads(PINS_PATH.read_text())
    return {"resolved_at": None, "artifacts": {}}


def size_verdict(art: Artifact, actual: int) -> tuple[str, str]:
    """Compare on-disk size to the TDD planning value. Wrong quant == wrong size."""
    plan = art.planning_bytes
    if plan <= 0:
        return "ok", ""
    delta = (actual - plan) / plan
    if art.size_mode == "max":
        if actual > plan:
            return "FLAG", f"exceeds the {human(plan)} ceiling by {delta:+.0%}"
        return "ok", f"under the {human(plan)} ceiling"
    if abs(delta) > SIZE_TOLERANCE:
        return "FLAG", f"{delta:+.0%} vs planning {human(plan)} — check the quant"
    return "ok", f"{delta:+.0%} vs planning {human(plan)}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="fetch_models.sh",
        description="Fetch, pin and manifest every model artifact (TDD T2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--only", action="append", metavar="NAME", help="fetch a single artifact")
    p.add_argument("--dry-run", action="store_true", help="print the resolution plan only")
    p.add_argument("--with-multilingual-asr", action="store_true")
    p.add_argument("--with-kokoro", action="store_true")
    p.add_argument("--with-draft", action="store_true")
    p.add_argument(
        "--quant-variants", action="store_true", help="fetch the D1 bake-off candidate set"
    )
    p.add_argument(
        "--mmproj-precision",
        choices=["f16"],
        help="acknowledge that no Q8_0 vision projector exists and accept F16 (see T2 note)",
    )
    p.add_argument("--repin", action="store_true", help="re-resolve pins to current HEAD")
    p.add_argument("--force", action="store_true", help="redownload even if hashes match")
    p.add_argument("--use-token", action="store_true", help="use the local HF token")
    args = p.parse_args(argv)

    api = make_api(args.use_token)
    pins = load_pins()
    if args.repin:
        pins["artifacts"] = {}

    selected = select(args)

    log("=" * 86)
    log("Muta model fetch — TDD T2 (build machine only; nothing here runs on the target)")
    log("=" * 86)

    rows: list[dict] = []
    manifest_entries: list[dict] = []
    flagged: list[str] = []

    for art in selected:
        fetch = will_fetch(art, args)

        # ---- the mmproj gate (hard rule 1) -------------------------------------------
        if art.name == "mmproj" and fetch and not args.mmproj_precision:
            raise Stop(
                "[mmproj] REFUSING TO GUESS.\n    "
                + UNRESOLVED["mmproj-q8_0"].replace(". ", ".\n    ")
                + "\n\n"
                + candidate_report(api, art)
            )

        log(f"\n>> {art.name}  [{art.tier}]  {art.role}")
        res = resolve(api, art, (pins["artifacts"].get(art.name) or {}).get("revision"))
        log(f"    repo {res.repo}@{res.revision[:12]}  files={len(res.files)}")
        if res.hub_license:
            log(f"    hub license tag: {res.hub_license}")
        for c in art.caveats:
            log(f"    ! {c}")

        spdx, lic_url = capture_license(api, art, res.revision, args.dry_run or not fetch)

        if not fetch:
            log(f"    (skipped — needs {art.flag}; recorded in manifest as fetched:false)")
        if args.dry_run:
            log("    (dry run — nothing downloaded)")

        files: list[FetchedFile] = []
        if fetch and not args.dry_run:
            files = fetch_files(art, res, pins["artifacts"].get(art.name, {}), args.force)

        # In a dry run the Hub's reported sizes stand in for on-disk sizes, so the plan is
        # auditable — including a budget bust — before spending gigabytes of download.
        total = sum(f.bytes for f in files) if files else res.total_bytes
        measured = bool(files)
        if total:
            verdict, note = size_verdict(art, total)
            label = "size" if measured else "size (expected)"
            log(f"    {label} {human(total)}  [{verdict}] {note}")
            if verdict == "FLAG":
                flagged.append(f"{art.name}: {note}")

        pins["artifacts"][art.name] = {
            "repo": res.repo,
            "revision": res.revision,
            # Keyed by the source-repo filename, not by position: a zip() here would
            # silently attach the wrong hash to the wrong file if order ever diverged.
            "files": {f.name: {"sha256": f.sha256, "bytes": f.bytes} for f in files}
            if files
            else (pins["artifacts"].get(art.name, {}) or {}).get("files", {}),
        }

        entry = {
            "name": art.name,
            "role": art.role,
            "repo": res.repo,
            "revision": res.revision,
            "tier": art.tier,
            "license": spdx,
            "license_url": lic_url,
            "fetched": bool(files),
        }
        if art.file:
            entry["file"] = art.file
            entry["path"] = files[0].relpath if files else f"{art.dest}/{Path(art.file).name}"
            entry["bytes"] = files[0].bytes if files else 0
            entry["sha256"] = files[0].sha256 if files else ""
        else:
            entry["file"] = f"{len(res.files)} files"
            entry["path"] = art.dest
            entry["bytes"] = sum(f.bytes for f in files)
            entry["sha256"] = _dir_digest(files)
            entry["files"] = [
                {"path": f.relpath, "bytes": f.bytes, "sha256": f.sha256} for f in files
            ]
        # `bytes` means "bytes on disk", so it is 0 for anything we did not fetch — for
        # single files and directories alike. What a tier B artifact *would* cost belongs
        # in its own field; conflating the two made an unfetched directory look resident.
        if not files:
            entry["expected_bytes"] = res.total_bytes
        if art.caveats:
            entry["caveats"] = list(art.caveats)
        manifest_entries.append(entry)
        rows.append(
            {
                "name": art.name,
                "tier": art.tier,
                "bytes": total,
                # Only artifacts we would actually put on disk count toward the budget.
                "counts_to_budget": measured or (args.dry_run and fetch),
                "license": spdx,
                "status": "fetched" if files else ("dry-run" if args.dry_run else "skipped"),
            }
        )

    if not args.dry_run:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if MANIFEST_PATH.exists():
            try:
                existing = json.loads(MANIFEST_PATH.read_text()).get("artifacts", [])
            except (json.JSONDecodeError, KeyError) as exc:
                log(f"  ! existing manifest unreadable ({exc}); rewriting from scratch")
        MANIFEST_PATH.write_text(
            json.dumps(
                {
                    "generated_at": now_iso(),
                    "artifacts": merge_manifest(existing, manifest_entries),
                },
                indent=2,
            )
            + "\n"
        )
        pins["resolved_at"] = now_iso()
        PINS_PATH.write_text(json.dumps(pins, indent=2, sort_keys=True) + "\n")
        log(f"\nwrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")
        log(f"wrote {PINS_PATH.relative_to(REPO_ROOT)}")
        log(f"wrote {LICENSES_DIR.relative_to(REPO_ROOT)}/")

    summary(rows, flagged)
    return 1 if flagged else 0


def _dir_digest(files: list[FetchedFile]) -> str:
    """Stable digest over a directory artifact: sha256 of 'name sha' lines, sorted."""
    if not files:
        return ""
    joined = "\n".join(f"{f.relpath} {f.sha256}" for f in sorted(files, key=lambda x: x.relpath))
    return hashlib.sha256(joined.encode()).hexdigest()


def merge_manifest(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Merge, never replace: `--only tts` must not erase the record of everything else.

    Entries are keyed by name and this run's entries win. Output is in canonical spec
    order so the committed file diffs cleanly between runs.
    """
    merged: dict[str, dict] = {e["name"]: e for e in existing}
    for e in fresh:
        merged[e["name"]] = e
    order = [a.name for a in ARTIFACTS + QUANT_VARIANTS]
    return sorted(
        merged.values(),
        key=lambda e: order.index(e["name"]) if e["name"] in order else len(order),
    )


def summary(rows: list[dict], flagged: list[str]) -> None:
    log("\n" + "=" * 86)
    log(f"{'name':<28}{'tier':<12}{'size':>12}  {'license':<14}status")
    log("-" * 86)
    resident = 0
    for r in rows:
        if r["tier"] == "resident" and r.get("counts_to_budget"):
            resident += r["bytes"]
        log(
            f"{r['name']:<28}{r['tier']:<12}{human(r['bytes']):>12}  "
            f"{r['license']:<14}{r['status']}"
        )
    log("-" * 86)
    total = sum(r["bytes"] for r in rows)
    log(f"{'TOTAL':<28}{'':<12}{human(total):>12}")
    log(f"{'resident tier':<28}{'':<12}{human(resident):>12}  cap {human(RESIDENT_CAP_BYTES)}")
    if resident > RESIDENT_CAP_BYTES:
        log(f"  !! resident tier is OVER the 3.3 GiB cap by {human(resident - RESIDENT_CAP_BYTES)}")
    if flagged:
        log("\nsize flags (>20% off planning — usually the wrong quant):")
        for f in flagged:
            log(f"  ! {f}")
    log("=" * 86)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        sys.exit(3)
    except KeyboardInterrupt:
        sys.exit(130)
