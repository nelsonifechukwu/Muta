"""MANIFEST.json — every shipped binary and model with size, sha256 and license (TDD §10.2).

    python -m bundle.manifest build  --root dist
    python -m bundle.manifest verify --root /opt/tutor

Verification is the gate `stage.sh` runs *twice* (before and after the copy). A failure
prints the offending path and exits non-zero — "any mismatch → refuse to start, name the
file". Hashing streams in 1 MiB blocks: a 2.5 GiB GGUF must not be read into a 7 GiB budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from bundle.layout import MANIFEST_NAME, MANIFEST_ROOTS, resolve_root

_BLOCK = 1 << 20  # 1 MiB
MANIFEST_VERSION = 1

#: Licenses we are allowed to redistribute (TDD §13). `build` refuses anything else, so an
#: incompatible artifact is caught at packaging time rather than by a judge.
ALLOWED_LICENSES = frozenset({"Apache-2.0", "MIT", "BSD-3-Clause", "CC-BY-4.0", "unlicensed-local"})


def sha256_file(path: Path, *, block: int = _BLOCK) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(block):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Artifact:
    path: str  # bundle-relative, POSIX separators
    size: int
    sha256: str
    license: str = "unlicensed-local"
    source: str = ""  # provenance: HF repo@revision, upstream tag, ...

    @classmethod
    def scan(cls, root: Path, rel: str, *, license: str = "unlicensed-local", source: str = ""):
        f = root / rel
        return cls(
            path=rel, size=f.stat().st_size, sha256=sha256_file(f), license=license, source=source
        )


@dataclass(frozen=True)
class Mismatch:
    path: str
    reason: str  # "missing" | "size" | "sha256"
    expected: str
    actual: str

    def __str__(self) -> str:  # what the operator reads when staging refuses
        return f"{self.path}: {self.reason} mismatch (expected {self.expected}, got {self.actual})"


@dataclass(frozen=True)
class Manifest:
    artifacts: tuple[Artifact, ...]
    version: int = MANIFEST_VERSION

    # --- io ---------------------------------------------------------------------------
    def to_json(self) -> str:
        payload = {
            "version": self.version,
            "artifacts": [asdict(a) for a in sorted(self.artifacts, key=lambda a: a.path)],
        }
        return json.dumps(payload, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        raw = json.loads(text)
        return cls(
            version=int(raw.get("version", MANIFEST_VERSION)),
            artifacts=tuple(Artifact(**a) for a in raw["artifacts"]),
        )

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        return cls.from_json(path.read_text())

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())
        return path

    # --- build / verify ---------------------------------------------------------------
    @classmethod
    def build(
        cls,
        root: Path,
        *,
        roots: tuple[str, ...] = MANIFEST_ROOTS,
        licenses: dict[str, str] | None = None,
        sources: dict[str, str] | None = None,
    ) -> "Manifest":
        """Hash everything under `roots`. `licenses`/`sources` key on the relative path or,
        as a fallback, on its first path component (so `models/core/*` can be labelled once)."""
        licenses = licenses or {}
        sources = sources or {}
        artifacts: list[Artifact] = []
        for top in roots:
            base = root / top
            if not base.is_dir():
                continue
            for f in sorted(base.rglob("*")):
                if not f.is_file() or f.name == "MANIFEST.json" or f.name.startswith("."):
                    continue
                rel = f.relative_to(root).as_posix()
                lic = _lookup(licenses, rel, default="unlicensed-local")
                if lic not in ALLOWED_LICENSES:
                    raise ValueError(
                        f"{rel}: license {lic!r} is not redistributable "
                        f"(allowed: {sorted(ALLOWED_LICENSES)}) — TDD §13"
                    )
                artifacts.append(
                    Artifact.scan(root, rel, license=lic, source=_lookup(sources, rel, default=""))
                )
        # Sorted, so a manifest equals a manifest regardless of scan order and `git diff` on
        # MANIFEST.json is reviewable.
        return cls(artifacts=tuple(sorted(artifacts, key=lambda a: a.path)))

    def verify(self, root: Path, *, deep: bool = True) -> list[Mismatch]:
        """Check every artifact against the tree at `root`.

        `deep=False` checks only presence and size — the cheap pre-flight. The real gate is
        `deep=True` (sha256), which is what staging runs on both sides of the copy.
        """
        bad: list[Mismatch] = []
        for a in self.artifacts:
            f = root / a.path
            if not f.is_file():
                bad.append(Mismatch(a.path, "missing", a.sha256, "-"))
                continue
            size = f.stat().st_size
            if size != a.size:
                bad.append(Mismatch(a.path, "size", str(a.size), str(size)))
                continue  # a wrong size is already conclusive; don't pay for the hash
            if deep:
                digest = sha256_file(f)
                if digest != a.sha256:
                    bad.append(Mismatch(a.path, "sha256", a.sha256, digest))
        return bad

    @property
    def total_bytes(self) -> int:
        return sum(a.size for a in self.artifacts)


def _lookup(table: dict[str, str], rel: str, *, default: str) -> str:
    if rel in table:
        return table[rel]
    parts = Path(rel).parts
    for i in range(len(parts) - 1, 0, -1):  # models/core/x.gguf -> models/core -> models
        prefix = "/".join(parts[:i])
        if prefix in table:
            return table[prefix]
    return default


class IntegrityError(RuntimeError):
    """Raised when verification fails. `str()` names every offending file."""

    def __init__(self, root: Path, mismatches: list[Mismatch]) -> None:
        self.root = root
        self.mismatches = mismatches
        detail = "\n".join(f"  - {m}" for m in mismatches)
        super().__init__(f"integrity check failed under {root}:\n{detail}")


def verify_or_raise(root: Path, manifest_path: Path | None = None, *, deep: bool = True) -> Manifest:
    manifest_path = manifest_path or (root / MANIFEST_NAME)
    if not manifest_path.is_file():
        raise IntegrityError(root, [Mismatch(str(manifest_path), "missing", "MANIFEST.json", "-")])
    manifest = Manifest.load(manifest_path)
    bad = manifest.verify(root, deep=deep)
    if bad:
        raise IntegrityError(root, bad)
    return manifest


# --- CLI ----------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="hash the bundle tree into MANIFEST.json")
    b.add_argument("--root", default=None, help="bundle root (default: /opt/tutor if present, else dist)")
    b.add_argument("--out", default=None, help="manifest path (default: <root>/models/MANIFEST.json)")
    b.add_argument("--licenses", default=None, help="JSON map: bundle path (or prefix) -> SPDX id")

    v = sub.add_parser("verify", help="check the tree against MANIFEST.json")
    v.add_argument("--root", default=None)
    v.add_argument("--manifest", default=None)
    v.add_argument("--shallow", action="store_true", help="presence+size only (pre-flight)")

    args = p.parse_args(argv)
    root = resolve_root(args.root)

    if args.cmd == "build":
        licenses = json.loads(Path(args.licenses).read_text()) if args.licenses else {}
        manifest = Manifest.build(root, licenses=licenses)
        out = Path(args.out) if args.out else root / MANIFEST_NAME
        manifest.write(out)
        print(f"wrote {out} — {len(manifest.artifacts)} artifacts, {manifest.total_bytes / 2**30:.2f} GiB")
        return 0

    try:
        manifest = verify_or_raise(
            root, Path(args.manifest) if args.manifest else None, deep=not args.shallow
        )
    except IntegrityError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"ok — {len(manifest.artifacts)} artifacts verified under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
