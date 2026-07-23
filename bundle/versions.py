"""`versions.lock` — the pins every build must reproduce (TDD T1, §11.1).

The file is deliberately `KEY=value` so both `source versions.lock` (shell, in `build.sh`)
and this module read the same bytes. No TOML, no YAML: a second parser is a second way for
the build and the lock to disagree.

    python -m bundle.versions show
    python -m bundle.versions check LLAMA_CPP_REF "$(git -C /src describe --tags)"
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

DEFAULT_LOCK = Path(__file__).resolve().parent.parent / "deploy" / "versions.lock"


class PinMismatch(RuntimeError):
    """A build tried to compile a tree that is not the pinned one."""


def load_lock(path: Path | str | None = None) -> dict[str, str]:
    path = Path(path) if path else DEFAULT_LOCK
    pins: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        pins[key] = " ".join(shlex.split(value.strip())) if value.strip() else ""
    return pins


def require(key: str, path: Path | str | None = None) -> str:
    pins = load_lock(path)
    value = pins.get(key, "")
    if not value:
        raise PinMismatch(f"{key} is unset in {path or DEFAULT_LOCK} — pin it before building (TDD T1)")
    return value


def check(key: str, actual: str, path: Path | str | None = None) -> None:
    """Raise unless `actual` matches the pin. Accepts a commit that *starts with* the pinned
    short SHA, since `git describe` and `rev-parse` disagree on length, not on identity."""
    expected = require(key, path)
    a, e = actual.strip(), expected.strip()
    if a == e or a.startswith(e) or e.startswith(a):
        return
    raise PinMismatch(f"{key}: tree is at {a!r} but versions.lock pins {e!r} — refusing to build")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="print all pins")
    s.add_argument("--lock", default=None)
    c = sub.add_parser("check", help="fail unless the pin matches")
    c.add_argument("key")
    c.add_argument("actual")
    c.add_argument("--lock", default=None)
    args = p.parse_args(argv)

    if args.cmd == "show":
        for k, v in load_lock(args.lock).items():
            print(f"{k}={v}")
        return 0
    try:
        check(args.key, args.actual, args.lock)
    except PinMismatch as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"{args.key} ok ({args.actual})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
