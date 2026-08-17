#!/usr/bin/env python3
"""ADTC profiler dashboard — zero-dependency stdlib server.

Serves the dashboard UI, scans ../model/*.gguf, runs adtc-profiler on demand
(one run at a time, in the `ai` conda env), and persists every run to SQLite.

Usage: python3 app.py [port] [--no-open]     (default port 8765)
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DASH_DIR = Path(__file__).resolve().parent
ROOT = DASH_DIR.parent                      # submission repo root (holds metadata.json)
MODEL_DIR = ROOT / "model"
METADATA = ROOT / "metadata.json"
SUBMISSION = ROOT / "submission.json"
DB_PATH = DASH_DIR / "profiler.db"
RUNS_DIR = DASH_DIR / "runs"                # raw profiler output files (gitignored)

# Scoring constants from the adtc-profiler README / challenge rules.
# S_perf has no fixed reference: the official site scores 100*TPS/TPS_max with
# TPS_max = the fastest submission, so locally the fastest stored run stands in
# for it (see tps_reference()). The profiler README's fixed 15 tok/s is NOT used.
RAM_LIMIT_GB = 7.0
TEMP_LIMIT_C = 85.0
THERMAL_PENALTY_PTS = 10

# ---------------------------------------------------------------------------
# Pure logic (unit-tested in test_app.py)
# ---------------------------------------------------------------------------

_QUANT_RE = re.compile(r"(?:^|[-_.])(I?Q\d+(?:_[A-Za-z0-9]+)*|BF16|F16|F32)(?=[-_.]|$)")
_PARAMS_RE = re.compile(r"(?:^|[-_ .])(\d+(?:\.\d+)?)([MBmb])(?=[-_. ]|$)")


def parse_quant(filename: str) -> str | None:
    """Quantization tag from a GGUF filename, e.g. Q4_K_M, IQ4_XS, F16."""
    m = _QUANT_RE.search(Path(filename).stem)
    return m.group(1) if m else None


def parse_params(filename: str) -> str | None:
    """Parameter-count tag from a GGUF filename, e.g. 135M, 0.8B, 4B."""
    m = _PARAMS_RE.search(Path(filename).stem)
    return f"{m.group(1)}{m.group(2).upper()}" if m else None


def updated_metadata(base: dict, model_file: str) -> dict:
    """Copy of metadata.json contents re-pointed at model_file.

    Only the model block and _runtime.model_path change; quant/params fields
    keep their previous values when the filename doesn't reveal them.
    """
    meta = copy.deepcopy(base)
    model = meta.setdefault("model", {})
    model["name"] = Path(model_file).stem
    quant = parse_quant(model_file)
    if quant:
        model["quantization"] = f"GGUF {quant}"
    params = parse_params(model_file)
    if params:
        model["parameters_estimate"] = params
    meta.setdefault("_runtime", {})["model_path"] = f"model/{model_file}"
    return meta


def model_listing(disk_files: list[str], run_files: list[str]) -> list[tuple[str, bool]]:
    """Model files to display with a present-on-disk flag.

    On-disk models first; models whose .gguf was deleted but that still have
    run history in the DB follow, so profile records outlive the file.
    """
    on_disk = sorted(set(disk_files))
    ghosts = sorted(set(run_files) - set(disk_files))
    return [(f, True) for f in on_disk] + [(f, False) for f in ghosts]


def extract_metrics(report: dict) -> dict:
    """Flatten the metrics the dashboard tracks out of a profiler report."""
    sub = report.get("submission") or {}
    thr = report.get("throughput") or {}
    mem = report.get("memory") or {}
    therm = report.get("cpu_thermal") or {}
    acc_list = report.get("accuracy") or []
    acc = acc_list[0] if acc_list else {}
    return {
        "tps": thr.get("tokens_per_second_generation"),
        "ttft_ms": thr.get("first_token_latency_ms"),
        "peak_rss_mb": mem.get("peak_rss_mb"),
        "arc_score": acc.get("score"),
        "arc_samples": acc.get("samples"),
        "arc_benchmark": acc.get("benchmark"),
        "arc_metric": acc.get("metric"),
        "temp_c": therm.get("core_temp_c_peak"),
        "throttled": therm.get("throttled"),
        "cpu_p99": therm.get("cpu_percent_p99"),
        "african_claim": sub.get("african_alpha_claim"),
        "budget_claim": sub.get("budget_laptop_claim"),
    }


def compute_scores(arc_score, tps, peak_rss_mb, throttled, temp_c, crashed,
                   tps_reference) -> dict:
    """ADTC scoring: S_total = 0.5*S_acc + 0.3*S_perf + 0.2*S_eff - P_thermal.

    S_acc is proxied locally by the arc_easy benchmark score (the judges' panel
    component only exists at audit time). S_perf = min(tps/tps_reference, 1)*100
    where tps_reference is the fastest tok/s among all stored runs (None/0 →
    no S_perf). A crashed/OOM run is disqualified.
    """
    if crashed:
        return {"s_acc": None, "s_perf": None, "s_eff": None,
                "thermal_penalty": 0, "s_total": 0.0, "disqualified": True}
    s_acc = round(arc_score * 100, 2) if arc_score is not None else None
    s_perf = (round(min(tps / tps_reference, 1.0) * 100, 2)
              if tps is not None and tps_reference else None) # tps_reference could be 15 tok/s
    s_eff = (round(max(0.0, (RAM_LIMIT_GB - peak_rss_mb / 1024) / RAM_LIMIT_GB) * 100, 2)
             if peak_rss_mb is not None else None)
    penalty = THERMAL_PENALTY_PTS if (throttled or (temp_c is not None and temp_c > TEMP_LIMIT_C)) else 0
    s_total = None
    if s_acc is not None and s_perf is not None and s_eff is not None:
        s_total = round(max(0.0, 0.5 * s_acc + 0.3 * s_perf + 0.2 * s_eff - penalty), 2)
    return {"s_acc": s_acc, "s_perf": s_perf, "s_eff": s_eff,
            "thermal_penalty": penalty, "s_total": s_total, "disqualified": False}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_file TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                skip_accuracy INTEGER NOT NULL DEFAULT 0,
                exit_code INTEGER,
                error TEXT,
                oom INTEGER NOT NULL DEFAULT 0,
                report_json TEXT,
                log_tail TEXT,
                tps REAL, ttft_ms REAL, peak_rss_mb REAL,
                arc_score REAL, arc_samples INTEGER,
                temp_c REAL, throttled INTEGER, cpu_p99 REAL,
                african_claim INTEGER, budget_claim INTEGER
            )
        """)
        # A daemon-thread death (Ctrl-C mid-profile) skips _run_profile's
        # finally, stranding rows at 'running'; nothing can be running at boot.
        conn.execute(
            "UPDATE runs SET status='failed', finished_at=?,"
            " error='interrupted: server stopped mid-run' WHERE status='running'",
            (now_iso(),))


def tps_reference(conn: sqlite3.Connection) -> tuple[float | None, dict | None]:
    """(fastest tok/s across all stored runs, {id, model_file} of that run).

    Every finished run with a measured tps counts — quick runs and runs of
    since-deleted models included — so the reference is the best speed this
    machine has actually produced. (None, None) when nothing has been measured.
    """
    row = conn.execute(
        "SELECT id, model_file, tps, skip_accuracy FROM runs WHERE tps IS NOT NULL"
        " ORDER BY tps DESC, id ASC LIMIT 1").fetchone()
    if row is None:
        return None, None
    return row["tps"], {"id": row["id"], "model_file": row["model_file"],
                        "quick": bool(row["skip_accuracy"])}


def promote_run(run_id: int) -> tuple[dict | None, str | None]:
    """Promote a stored run's report to submission.json + metadata.json.

    Refuses when the model file is gone: metadata.json must never point at a
    .gguf that no longer exists. Returns (result, None) or (None, error).
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if row is None or not row["report_json"]:
        return None, "run has no report"
    if not (MODEL_DIR / row["model_file"]).is_file():
        return None, f"model file no longer exists: {row['model_file']}"
    report = json.loads(row["report_json"])
    SUBMISSION.write_text(json.dumps(report, indent=2) + "\n")
    meta = json.loads(METADATA.read_text())
    METADATA.write_text(json.dumps(updated_metadata(meta, row["model_file"]), indent=2) + "\n")
    return {"promoted": True, "submission": str(SUBMISSION)}, None


def run_row_public(row: sqlite3.Row, *, tps_reference: float | None,
                   include_report: bool = False) -> dict:
    d = dict(row)
    d["skip_accuracy"] = bool(d["skip_accuracy"])
    d["oom"] = bool(d["oom"])
    for k in ("throttled", "african_claim", "budget_claim"):
        d[k] = None if d[k] is None else bool(d[k])
    d["scores"] = compute_scores(
        arc_score=d["arc_score"], tps=d["tps"], peak_rss_mb=d["peak_rss_mb"],
        throttled=bool(d["throttled"]), temp_c=d["temp_c"],
        crashed=(d["status"] == "failed"), tps_reference=tps_reference,
    ) if d["status"] != "running" else None
    if not include_report:
        d.pop("report_json", None)
        d.pop("log_tail", None)
    return d


# ---------------------------------------------------------------------------
# Profiler runner (one at a time)
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
_OOM_RE = re.compile(r"MemoryError|out of memory|std::bad_alloc|Killed: 9|oom", re.IGNORECASE)

RUN_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
CURRENT: dict | None = None  # {run_id, model_file, started_mono, started_at, skip_accuracy, log, proc}


def find_profiler() -> list[str]:
    for cand in (os.environ.get("ADTC_PROFILER"),
                 str(Path.home() / "miniforge3/envs/ai/bin/adtc-profiler"),
                 shutil.which("adtc-profiler")):
        if cand and Path(cand).exists():
            return [cand]
    return ["conda", "run", "--no-capture-output", "-n", "ai", "adtc-profiler"]


PROFILER_CMD = find_profiler()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def start_profile(model_file: str, skip_accuracy: bool) -> tuple[int | None, str | None]:
    """Returns (run_id, None) or (None, error)."""
    if "/" in model_file or model_file.startswith("."):
        return None, "invalid model filename"
    if not (MODEL_DIR / model_file).is_file():
        return None, f"model not found: {model_file}"
    if not RUN_LOCK.acquire(blocking=False):
        return None, "a profiling run is already in progress"
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO runs (model_file, started_at, status, skip_accuracy) VALUES (?,?,?,?)",
                (model_file, now_iso(), "running", int(skip_accuracy)))
            run_id = cur.lastrowid
        global CURRENT
        with STATE_LOCK:
            CURRENT = {"run_id": run_id, "model_file": model_file,
                       "started_mono": time.monotonic(), "started_at": now_iso(),
                       "skip_accuracy": skip_accuracy,
                       "log": deque(maxlen=500), "proc": None}
        threading.Thread(target=_run_profile, args=(run_id, model_file, skip_accuracy),
                         daemon=True).start()
        return run_id, None
    except Exception as exc:  # insert/thread failure: don't leave the lock held
        RUN_LOCK.release()
        return None, str(exc)


def _append_log(line: str) -> None:
    line = _ANSI_RE.sub("", line).rstrip("\n")
    if "\r" in line:
        line = line.rsplit("\r", 1)[-1]
    if line.strip():
        with STATE_LOCK:
            if CURRENT is not None:
                CURRENT["log"].append(line)


def _run_profile(run_id: int, model_file: str, skip_accuracy: bool) -> None:
    global CURRENT
    error, exit_code, report = None, None, None
    out_path = RUNS_DIR / f"run-{run_id}.json"
    try:
        meta = json.loads(METADATA.read_text())
        METADATA.write_text(json.dumps(updated_metadata(meta, model_file), indent=2) + "\n")
        _append_log(f"metadata.json -> model/{model_file}")

        cmd = PROFILER_CMD + ["run", "--submission", str(ROOT), "--mode", "participant",
                              "--output", str(out_path)]
        if skip_accuracy:
            cmd.append("--skip-accuracy")
        _append_log("$ " + " ".join(cmd))
        env = {**os.environ, "NO_COLOR": "1", "TERM": "dumb"}
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        with STATE_LOCK:
            if CURRENT is not None:
                CURRENT["proc"] = proc
        for line in proc.stdout:
            _append_log(line)
        exit_code = proc.wait()
        if exit_code == 0 and out_path.is_file():
            report = json.loads(out_path.read_text())
        elif exit_code != 0:
            error = f"profiler exited with code {exit_code}"
        else:
            error = "profiler produced no output file"
    except Exception as exc:
        error = str(exc)
    finally:
        with STATE_LOCK:
            log_lines = list(CURRENT["log"]) if CURRENT is not None else []
            CURRENT = None
        log_text = "\n".join(log_lines)
        oom = int(bool(_OOM_RE.search(log_text)) or (exit_code is not None and exit_code < 0))
        cols = {"finished_at": now_iso(), "exit_code": exit_code, "error": error,
                "oom": oom, "log_tail": log_text,
                "status": "ok" if report is not None else "failed"}
        if report is not None:
            cols["report_json"] = json.dumps(report)
            m = extract_metrics(report)
            cols.update(
                tps=m["tps"], ttft_ms=m["ttft_ms"], peak_rss_mb=m["peak_rss_mb"],
                arc_score=m["arc_score"], arc_samples=m["arc_samples"],
                temp_c=m["temp_c"],
                throttled=None if m["throttled"] is None else int(m["throttled"]),
                cpu_p99=m["cpu_p99"],
                african_claim=None if m["african_claim"] is None else int(m["african_claim"]),
                budget_claim=None if m["budget_claim"] is None else int(m["budget_claim"]),
            )
        sets = ", ".join(f"{k}=?" for k in cols)
        with db() as conn:
            conn.execute(f"UPDATE runs SET {sets} WHERE id=?", (*cols.values(), run_id))
        RUN_LOCK.release()


def cancel_current() -> bool:
    with STATE_LOCK:
        proc = CURRENT.get("proc") if CURRENT else None
    if proc is None:
        return False
    proc.terminate()
    return True


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

def state_payload() -> dict:
    models = []
    disk = {p.name: p for p in MODEL_DIR.glob("*.gguf") if p.is_file()}
    with db() as conn:
        conn.execute("BEGIN")  # one snapshot for the reference and the rows
        ref_tps, ref_run = tps_reference(conn)
        run_files = [r["model_file"] for r in
                     conn.execute("SELECT DISTINCT model_file FROM runs").fetchall()]
        for name, present in model_listing(list(disk), run_files):
            rows = conn.execute(
                "SELECT * FROM runs WHERE model_file=? AND status!='running' ORDER BY id DESC",
                (name,)).fetchall()
            runs = [run_row_public(r, tps_reference=ref_tps) for r in rows]
            latest = runs[0] if runs else None
            scored = [r for r in runs if r["scores"] and r["scores"]["s_total"] is not None]
            best = max(scored, key=lambda r: r["scores"]["s_total"], default=None)
            models.append({
                "file": name, "present": present,
                "size_bytes": disk[name].stat().st_size if present else None,
                "quant": parse_quant(name), "params": parse_params(name),
                "runs_count": len(runs), "latest": latest, "best": best,
            })
    with STATE_LOCK:
        current = None
        if CURRENT is not None:
            current = {
                "run_id": CURRENT["run_id"], "model_file": CURRENT["model_file"],
                "started_at": CURRENT["started_at"],
                "elapsed_s": round(time.monotonic() - CURRENT["started_mono"], 1),
                "skip_accuracy": CURRENT["skip_accuracy"],
                "log": list(CURRENT["log"])[-80:],
            }
    try:
        meta = json.loads(METADATA.read_text())
    except Exception:
        meta = {}
    return {
        "models": models,
        "current": current,
        "metadata": {
            "team_id": meta.get("team_id"), "domain": meta.get("domain"),
            "african_alpha_claim": meta.get("african_alpha_claim"),
            "budget_laptop_claim": meta.get("budget_laptop_claim"),
            "current_model_path": (meta.get("_runtime") or {}).get("model_path"),
        },
        "scoring": {"tps_reference": ref_tps, "tps_reference_run": ref_run,
                    "ram_limit_gb": RAM_LIMIT_GB,
                    "temp_limit_c": TEMP_LIMIT_C, "thermal_penalty_pts": THERMAL_PENALTY_PTS},
    }


STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/script.js": ("script.js", "application/javascript; charset=utf-8"),
}

_RUN_ID_RE = re.compile(r"^/api/runs/(\d+)$")
_PROMOTE_RE = re.compile(r"^/api/runs/(\d+)/promote$")


class Handler(BaseHTTPRequestHandler):
    server_version = "adtc-dashboard/1.0"

    def log_message(self, fmt, *args):  # quiet access log
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in STATIC_FILES:
            name, ctype = STATIC_FILES[url.path]
            fp = DASH_DIR / name
            if not fp.is_file():
                return self._json({"error": "missing static file"}, 404)
            body = fp.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if url.path == "/api/state":
            return self._json(state_payload())
        if url.path == "/api/runs":
            model = (parse_qs(url.query).get("model") or [None])[0]
            with db() as conn:
                conn.execute("BEGIN")
                ref_tps, _ = tps_reference(conn)
                if model:
                    rows = conn.execute(
                        "SELECT * FROM runs WHERE model_file=? ORDER BY id DESC", (model,)).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
            return self._json({"runs": [run_row_public(r, tps_reference=ref_tps) for r in rows]})
        m = _RUN_ID_RE.match(url.path)
        if m:
            with db() as conn:
                conn.execute("BEGIN")
                ref_tps, _ = tps_reference(conn)
                row = conn.execute("SELECT * FROM runs WHERE id=?", (int(m.group(1)),)).fetchone()
            if row is None:
                return self._json({"error": "run not found"}, 404)
            d = run_row_public(row, tps_reference=ref_tps, include_report=True)
            if d.get("report_json"):
                d["report"] = json.loads(d.pop("report_json"))
            return self._json(d)
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/api/profile":
            body = self._read_body()
            model = body.get("model") or ""
            run_id, err = start_profile(model, bool(body.get("skip_accuracy")))
            if err:
                code = 409 if "in progress" in err else 400
                return self._json({"error": err}, code)
            return self._json({"run_id": run_id}, 202)
        if url.path == "/api/cancel":
            return self._json({"cancelled": cancel_current()})
        m = _PROMOTE_RE.match(url.path)
        if m:
            result, err = promote_run(int(m.group(1)))
            if err:
                return self._json({"error": err}, 404 if err == "run has no report" else 409)
            return self._json(result)
        self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        m = _RUN_ID_RE.match(urlparse(self.path).path)
        if m:
            with db() as conn:
                cur = conn.execute(
                    "DELETE FROM runs WHERE id=? AND status!='running'", (int(m.group(1)),))
            return self._json({"deleted": cur.rowcount > 0})
        self._json({"error": "not found"}, 404)


def main() -> None:
    args = [a for a in sys.argv[1:]]
    open_browser = "--no-open" not in args
    ports = [int(a) for a in args if a.isdigit()]
    port = ports[0] if ports else 8765
    RUNS_DIR.mkdir(exist_ok=True)
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"adtc dashboard: {url}  (models: {MODEL_DIR}, db: {DB_PATH})")
    print(f"profiler: {' '.join(PROFILER_CMD)}")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
