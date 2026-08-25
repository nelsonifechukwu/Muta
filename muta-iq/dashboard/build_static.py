#!/usr/bin/env python3
"""Render the Muta IQ report as a self-contained static site.

The report in this directory normally polls ``app.py`` for ``/api/state``. This build
pre-renders that payload once, so the same ``index.html``/``style.css``/``script.js`` can be
published from a plain file host — GitHub Pages in particular — with no server behind it.

Output layout (every URL inside is relative, so the site works from any prefix, including a
project page such as ``https://<owner>.github.io/<repo>/``):

    index.html        the report, stamped ``<html data-snapshot="api/state.json">`` so that
                      script.js switches to its read-only published-snapshot mode
    style.css, script.js
    api/state.json    the /api/state payload plus ``runs_by_model`` (every stored run with its
                      raw profiler report) so History and Raw report keep working offline
    .nojekyll         keeps GitHub Pages from running Jekyll over the tree
    .muta-iq-site     marker; the builder only ever clears a directory it created itself

The evidence inputs are the tracked JSON summaries ``app.py`` already reads from
``bench/measurements/`` and the tracked ``profiler.db``; the build fails if any lane is
missing rather than publishing a page of "unavailable" placeholders. The ``model/`` directory
is not needed. E-mail addresses inside embedded profiler reports are redacted because the
output is meant to be public.

Usage: python3 build_static.py [--out DIR]        (default: <repository>/site, gitignored)
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import app  # the stdlib-only dashboard server, imported for its evidence loaders

DASH_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = app.REPO_ROOT / "site"
SNAPSHOT_PATH = "api/state.json"
HTML_TAG = '<html lang="en">'
STAMPED_TAG = f'<html lang="en" data-snapshot="{SNAPSHOT_PATH}">'
MARKER = ".muta-iq-site"
STATIC_ASSETS = ("style.css", "script.js")
EVIDENCE_LANES = (
    "campaign",
    "campaign_parity",
    "campaign_alternative",
    "campaign_avx2_score",
    "overnight",
    "model_extension",
)


def redact_emails(value):
    """Return a copy of ``value`` with every ``email`` field blanked."""
    if isinstance(value, dict):
        return {k: (None if k == "email" else redact_emails(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_emails(v) for v in value]
    return value


def runs_by_model() -> dict[str, list[dict]]:
    """Every finished stored run, newest first, grouped by model file, report embedded."""
    with app.db() as conn:
        conn.execute("BEGIN")
        ref_tps, _ = app.tps_reference(conn)
        rows = conn.execute(
            "SELECT * FROM runs WHERE status!='running' ORDER BY id DESC"
        ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        run = app.run_row_public(row, tps_reference=ref_tps, include_report=True)
        report_json = run.pop("report_json", None)
        run["report"] = redact_emails(json.loads(report_json)) if report_json else None
        grouped.setdefault(run["model_file"], []).append(run)
    return grouped


def snapshot_payload() -> dict:
    """The /api/state payload as a publishable snapshot."""
    if not app.DB_PATH.is_file():
        app.init_db()
    payload = app.state_payload()
    missing = [lane for lane in EVIDENCE_LANES if payload.get(lane) is None]
    if missing:
        raise SystemExit(
            "build_static: evidence input missing or unreadable for: " + ", ".join(missing)
        )
    payload["current"] = None  # nothing can be profiling in a published copy
    payload["runs_by_model"] = runs_by_model()
    payload["snapshot"] = {
        "path": SNAPSHOT_PATH,
        "generator": "muta-iq/dashboard/build_static.py",
    }
    return payload


def prepare_out(out: Path) -> None:
    if out.is_file():
        raise SystemExit(f"build_static: {out} is a file, not a directory")
    if out.is_dir():
        if any(out.iterdir()) and not (out / MARKER).is_file():
            raise SystemExit(
                f"build_static: refusing to clear {out}: it is not empty and was not created "
                f"by this builder (no {MARKER} marker)"
            )
        shutil.rmtree(out)
    out.mkdir(parents=True)


def build(out: Path = DEFAULT_OUT) -> Path:
    html = (DASH_DIR / "index.html").read_text()
    if html.count(HTML_TAG) != 1:
        raise SystemExit(f"build_static: expected exactly one {HTML_TAG!r} in index.html")
    payload = snapshot_payload()  # fail before touching the output directory
    prepare_out(out)
    (out / "index.html").write_text(html.replace(HTML_TAG, STAMPED_TAG, 1))
    for name in STATIC_ASSETS:
        shutil.copy2(DASH_DIR / name, out / name)
    (out / "api").mkdir()
    (out / SNAPSHOT_PATH).write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    (out / ".nojekyll").write_text("")
    (out / MARKER).write_text("Generated by muta-iq/dashboard/build_static.py; safe to delete.\n")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"output directory (default: {DEFAULT_OUT})"
    )
    args = parser.parse_args(argv)
    out = build(args.out.resolve())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"Muta IQ static report: {out} ({size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
