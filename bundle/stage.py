"""Staging: USB bundle → local disk, hashed on both sides (TDD §10.3, C-4, S10).

    python -m bundle.stage --src /media/usb/tutor --dst /opt/tutor

Why a copy at all: models are never served from the flash drive. `mmap` of a 2.5 GiB GGUF
from USB turns every first-touch page fault into a USB round trip, which destroys decode
latency — the one number the demo is judged on live. So: verify at the source, copy, verify
again at the destination (cheap flash rots), then warm the page cache.

The two verifications are not redundant. The first catches a bad drive before a four-minute
copy; the second catches corruption introduced *by* the copy.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bundle.layout import INSTALL_ROOT, MANIFEST_NAME, PRIVATE_DIRS
from bundle.manifest import IntegrityError, Manifest, verify_or_raise

#: TDD A-3 — assume ≥ 30 GB free for staging. We only require bundle size + 20% headroom,
#: because the assumption is about the box, and the check should be about the copy.
HEADROOM = 1.20

Progress = Callable[[str], None]


@dataclass
class StageReport:
    src: Path
    dst: Path
    artifacts: int
    bytes_copied: int
    seconds: float
    warmed: bool = False
    steps: list[str] = field(default_factory=list)

    @property
    def mib_per_s(self) -> float:
        return (self.bytes_copied / 2**20) / self.seconds if self.seconds > 0 else 0.0

    def __str__(self) -> str:
        return (
            f"staged {self.artifacts} artifacts ({self.bytes_copied / 2**30:.2f} GiB) "
            f"{self.src} → {self.dst} in {self.seconds:.1f}s ({self.mib_per_s:.0f} MiB/s)"
            + ("; page cache warmed" if self.warmed else "")
        )


def free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def stage(
    src: Path,
    dst: Path = INSTALL_ROOT,
    *,
    warm: bool = True,
    progress: Progress | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> StageReport:
    """Verify → copy → re-verify → warm. Raises `IntegrityError` naming the file on any
    mismatch, and never leaves a half-verified tree marked as usable."""
    say = progress or (lambda _msg: None)
    steps: list[str] = []

    say(f"verifying source bundle at {src}")
    manifest = verify_or_raise(src)
    steps.append("verify:source")

    need = int(manifest.total_bytes * HEADROOM)
    have = free_bytes(dst)
    if have < need:
        raise RuntimeError(
            f"not enough free space at {dst}: need {need / 2**30:.1f} GiB "
            f"(bundle {manifest.total_bytes / 2**30:.1f} GiB + 20% headroom), have {have / 2**30:.1f} GiB"
        )

    started = clock()
    say(f"copying {manifest.total_bytes / 2**30:.2f} GiB → {dst}")
    _copy_tree(src, dst, manifest, say)
    steps.append("copy")

    say("re-verifying staged bundle (flash bitrot check)")
    try:
        verify_or_raise(dst)
    except IntegrityError as e:
        # The copy is the suspect, not the source — say so, because the operator's next move
        # differs (re-copy vs. replace the drive).
        raise IntegrityError(
            dst, e.mismatches
        ) from RuntimeError("corruption introduced during staging; retry the copy or replace the drive")
    steps.append("verify:destination")
    elapsed = clock() - started

    for rel in PRIVATE_DIRS:
        d = dst / rel
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o700)

    report = StageReport(
        src=src,
        dst=dst,
        artifacts=len(manifest.artifacts),
        bytes_copied=manifest.total_bytes,
        seconds=elapsed,
        steps=steps,
    )
    if warm:
        report.warmed = warm_page_cache(dst / "models" / "core", say=say)
        if report.warmed:
            steps.append("warm")
    return report


def _copy_tree(src: Path, dst: Path, manifest: Manifest, say: Progress) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    # Manifest artifacts first (the big, integrity-critical files), then the rest of the
    # bundle (gateway code, units, scripts) which the manifest deliberately does not hash.
    for a in manifest.artifacts:
        target = dst / a.path
        target.parent.mkdir(parents=True, exist_ok=True)
        say(f"  {a.path} ({a.size / 2**20:.0f} MiB)")
        shutil.copy2(src / a.path, target)
    for extra in ("gw", "units", MANIFEST_NAME, "versions.lock", "install.sh", "selftest.sh"):
        s = src / extra
        if not s.exists():
            continue
        d = dst / extra
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)


def warm_page_cache(path: Path, *, say: Progress | None = None) -> bool:
    """`vmtouch -t` the core weights so the first token is not a cold-read (TDD S10).

    Returns False when vmtouch is absent — warming is an optimisation, never a gate. The
    fallback is a plain read, which populates the page cache just as well, only slower.
    """
    say = say or (lambda _m: None)
    if not path.exists():
        return False
    vmtouch = shutil.which("vmtouch")
    if vmtouch:
        say(f"warming page cache: vmtouch -t {path}")
        return subprocess.run([vmtouch, "-t", str(path)], capture_output=True).returncode == 0
    say(f"warming page cache: reading {path} (vmtouch not installed)")
    ok = False
    for f in sorted(Path(path).rglob("*.gguf")):
        with open(f, "rb") as fh:
            while fh.read(1 << 24):  # 16 MiB strides
                pass
        ok = True
    return ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", required=True, help="bundle root on the flash drive")
    p.add_argument("--dst", default=str(INSTALL_ROOT), help="local install root")
    p.add_argument("--no-warm", action="store_true", help="skip page-cache warming")
    args = p.parse_args(argv)

    try:
        report = stage(Path(args.src), Path(args.dst), warm=not args.no_warm, progress=print)
    except (IntegrityError, RuntimeError) as e:
        print(f"\nSTAGING REFUSED\n{e}", file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
