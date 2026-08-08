# P2 — Offline-resilient boot + online provisioning: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The stack always boots offline when everything it needs is already local; when online it provisions/updates; connectivity is visible to the UI.

**Architecture:** `run.sh` gains a ~3 s network probe whose verdict (`online`/`offline`) branches the build/pull logic and shows in `./run.sh plan`; the db image is digest-pinned so neighbor projects can't clobber platform resolution; the gateway gets a background connectivity probe surfaced through `/v1/ready` and telemetry; the UI renders a quiet status dot.

**Tech Stack:** bash + curl, httpx thread probe, FastAPI additive contract, vanilla JS.

## Global Constraints

- Offline is never an error: no student-facing failure may mention the network; boot warnings are one line each.
- `/v1` contract changes are additive-only; regenerate `contracts/openapi.yaml` via `make contract`, never hand-edit; commit the result.
- The probe never sits on a request path; `/v1/ready` reads a cached verdict.
- Every task ends green: pytest on touched files + `ruff check .`; RESULTS.md entry closes the phase.

---

### Task 1: gateway connectivity probe + `/v1/ready.checks.online` + telemetry field

**Files:**
- Create: `orchestrator/gateway/connectivity.py`
- Modify: `orchestrator/gateway/routes.py` (the `/ready` handler), `orchestrator/telemetry.py` (snapshot payload), `contracts/models.py` only if `/v1/ready`'s response is modeled there (check first — if the handler returns a plain dict, no contract change is needed)
- Test: `orchestrator/tests/test_connectivity.py` (new)

**Interfaces:**
- Produces: `ConnectivityProbe` dataclass with `online() -> bool | None` (None = never probed yet), `probe_once() -> bool`, and a module-level `get_connectivity()` singleton (lru_cache, matching `deps.py` conventions). Env: `MUTA_NET_PROBE_URL` (default `https://huggingface.co`), `MUTA_NET_PROBE_INTERVAL_S` (default `60`).

- [x] **Step 1: Write the failing tests**

```python
"""Connectivity probe — cached verdict, never on a request path."""

from __future__ import annotations

import httpx

from orchestrator.gateway.connectivity import ConnectivityProbe


def test_probe_reports_online_when_head_succeeds(monkeypatch):
    monkeypatch.setattr(
        httpx, "head",
        lambda url, timeout, follow_redirects: httpx.Response(200, request=httpx.Request("HEAD", url)),
    )
    probe = ConnectivityProbe()
    assert probe.probe_once() is True
    assert probe.online() is True


def test_probe_reports_offline_on_transport_error(monkeypatch):
    def boom(url, timeout, follow_redirects):
        raise httpx.ConnectError("down", request=httpx.Request("HEAD", url))

    monkeypatch.setattr(httpx, "head", boom)
    probe = ConnectivityProbe()
    assert probe.probe_once() is False
    assert probe.online() is False


def test_online_is_none_before_the_first_probe():
    assert ConnectivityProbe().online() is None


def test_any_http_status_counts_as_online(monkeypatch):
    # A captive portal or a 403 from the probe URL still proves the network routes.
    monkeypatch.setattr(
        httpx, "head",
        lambda url, timeout, follow_redirects: httpx.Response(403, request=httpx.Request("HEAD", url)),
    )
    assert ConnectivityProbe().probe_once() is True
```

- [x] **Step 2: Verify RED** — `.venv/bin/python -m pytest orchestrator/tests/test_connectivity.py -q` — expected: ModuleNotFoundError.

- [x] **Step 3: Implement `connectivity.py`**

```python
"""Connectivity: a cached is-the-internet-there verdict (design P2, 2026-08-08).

The probe runs on a timer thread started by the lifespan (never per request): online
features (cloud boost, web grounding, update hints) key off `online()`, and `/v1/ready`
reports it so the UI can show a quiet status dot. Offline is a state, not an error.
"""

from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache

import httpx

log = logging.getLogger("muta.gateway.connectivity")


class ConnectivityProbe:
    def __init__(self) -> None:
        self.url = os.environ.get("MUTA_NET_PROBE_URL", "https://huggingface.co")
        self.interval_s = float(os.environ.get("MUTA_NET_PROBE_INTERVAL_S", "60"))
        self._online: bool | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def online(self) -> bool | None:
        return self._online

    def probe_once(self) -> bool:
        try:
            # Any HTTP status proves routing; only transport failure means offline.
            httpx.head(self.url, timeout=3.0, follow_redirects=True)
            self._online = True
        except httpx.HTTPError:
            self._online = False
        return self._online

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                was = self._online
                now = self.probe_once()
                if was is not None and was != now:
                    log.info("connectivity: %s", "online" if now else "offline")
                self._stop.wait(self.interval_s)

        self._thread = threading.Thread(target=loop, name="net-probe", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


@lru_cache(maxsize=1)
def get_connectivity() -> ConnectivityProbe:
    return ConnectivityProbe()
```

- [x] **Step 4: Verify GREEN** on the new tests.

- [x] **Step 5: Wire it** — in the lifespan (`orchestrator/main.py`), `get_connectivity().start()` next to the other background tasks and `.stop()` on shutdown; in the `/v1/ready` handler add `"online": get_connectivity().online()` to `checks` (verify the response is a plain dict first; if it is a contract model, add the additive field and run `make contract`); in `orchestrator/telemetry.py` add the same value to the snapshot dict. Add a wiring test in `test_connectivity.py`:

```python
def test_ready_reports_the_connectivity_verdict(monkeypatch):
    from fastapi.testclient import TestClient

    from orchestrator.gateway.connectivity import get_connectivity
    from orchestrator.main import app

    get_connectivity()._online = True  # the probe thread is not running under tests
    body = TestClient(app).get("/v1/ready").json()
    assert body["checks"]["online"] is True
    get_connectivity()._online = None
```

- [x] **Step 6: UI dot** — `ui/app.js`: the telemetry poll already renders fields; add an `online` reading mapped to a small dot + title ("online"/"offline"; absent/None → hidden), styled in `ui/styles.css` (`.net-dot { … }`, green/gray). Keep it to ~10 lines total.

- [x] **Step 7: Full green + commit** — pytest touched files, `ruff check .`, `git add … && git commit -m "gateway: connectivity probe — /v1/ready.checks.online, telemetry field, UI dot"`

---

### Task 2: run.sh network probe + offline-resilient image logic

**Files:**
- Modify: `run.sh` (a `probe_net` function next to `detect_gpu`; `print_plan` gains `net=`; the "1. Images" block branches on the verdict)
- Test: `runtime/tests/test_run_sh_plan.py` (extend)

**Interfaces:**
- Produces: `probe_net` echoes `online` or `offline` (curl HEAD, 3 s budget, `MUTA_NET_PROBE_URL` honored); `./run.sh plan` prints a fourth line `net=online|offline`.

- [x] **Step 1: Failing tests** (append; the curl shim decides the verdict):

```python
def _shim_curl(tmp_path, exit_code: int) -> None:
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    curl = shim / "curl"
    curl.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)


def test_plan_reports_online_when_curl_succeeds(tmp_path):
    _shim_curl(tmp_path, 0)
    out = run_plan(tmp_path, "Darwin", "arm64")
    assert "net=online" in out


def test_plan_reports_offline_when_curl_fails(tmp_path):
    _shim_curl(tmp_path, 6)  # curl: could not resolve host
    out = run_plan(tmp_path, "Darwin", "arm64")
    assert "net=offline" in out
```

- [x] **Step 2: Verify RED** (no `net=` line yet).

- [x] **Step 3: Implement** — next to `detect_gpu`:

```bash
# Connectivity, decided once per invocation (~3 s worst case). Any HTTP response
# counts as online; only transport failure (DNS, TLS, unreachable) means offline.
probe_net() {
    if curl -fsSI --max-time 3 "${MUTA_NET_PROBE_URL:-https://huggingface.co}" \
        >/dev/null 2>&1; then
        echo online
    else
        echo offline
    fi
}
```

`print_plan` gains `echo "net=$(probe_net)"`. In the images block, compute `NET=$(probe_net)` once, then:

```bash
    if [ "$NET" = offline ]; then
        if docker image inspect muta-backend:latest muta-frontend:latest >/dev/null 2>&1; then
            warn "offline — using the existing local images (no build, no pull)"
        else
            die "offline and no local images exist — connect once and rerun ./run.sh"
        fi
    elif ! docker compose build; then
        …existing fallback unchanged…
    fi
```

and gate `docker compose up` pulls: when offline pass `--pull never` so a missing-but-tagged image fails fast with our message, not a registry traceback. Model provisioning: when offline and a required model file is missing, `die` listing the exact paths and the fetch command to run when back online (the `required_models` loop already knows the paths — add the NET guard to its missing-files branch).

- [x] **Step 4: Verify GREEN** — the two new tests + all existing plan tests; real smoke `./run.sh plan` prints `net=online` (network is up).

- [x] **Step 5: Commit** — `git commit -m "run.sh: network probe; offline boots use local images instead of dying on the registry"`

---

### Task 3: digest-pin the db image

**Files:**
- Modify: `docker-compose.yml` (`db.image`)

- [x] **Step 1: Resolve the digest** — `docker buildx imagetools inspect postgres:16-alpine` → take the top-level manifest-list `Digest:` (starts `sha256:`).

- [x] **Step 2: Pin it** —

```yaml
    # Digest-pinned (manifest list): another project's arm64 pull of the bare tag
    # clobbered platform resolution on 2026-08-07 and took the whole boot down.
    # The digest resolves per-platform and no neighbor can move it.
    image: postgres:16-alpine@sha256:<digest>
```

- [x] **Step 3: Verify** — `docker compose -f docker-compose.yml config | grep image:` shows the pinned ref; `docker compose up -d --wait db` still becomes healthy (pulls the amd64 blob by digest — the tag is untouched for neighbors).

- [x] **Step 4: Commit** — `git commit -m "compose: digest-pin postgres so neighbor pulls cannot clobber platform resolution"`

---

### Task 4: `./run.sh update`

**Files:**
- Modify: `run.sh` (usage + arg loop + an `update_stack` function)

- [x] **Step 1: Implement** —

```bash
update_stack() {
    [ "$(probe_net)" = online ] || die "update needs the network — try again when online"
    info "pulling code"
    git pull --ff-only || die "git pull failed — resolve manually and rerun"
    info "refreshing models (hash-verified files are skipped)"
    docker compose run --rm --no-deps backend \
        python3.10 scripts/fetch_models.py --with-draft --mmproj-precision f16 \
        || warn "model refresh failed — the stack still runs on the current files"
    info "rebuilding images"
    docker compose build || die "image rebuild failed"
    info "restarting"
    docker compose up -d --wait
    bold "updated — http://localhost:3000"
}
```

Arg loop: `update) MODE=update ;;` and after the plan gate: `[ "$MODE" = update ] && { update_stack; exit 0; }` written as a proper `if` (set -e). Usage line: `update — pull code, refresh models, rebuild, restart (online only)`.

- [x] **Step 2: Verify** — `bash -n run.sh` (syntax); `./run.sh plan` still clean; do NOT run a live update (it would git-pull the working repo mid-session).

- [x] **Step 3: Commit** — `git commit -m "run.sh: update subcommand — pull, refresh models, rebuild, restart (online only)"`

---

### Task 5: close P2

- [x] **Step 1: Full suite + lint green** (compose db up).
- [x] **Step 2: RESULTS.md** — a same-day subsection: what changed, the offline-boot behavior matrix (offline+images / offline+missing / online), digest value recorded, and the live verification evidence.
- [x] **Step 3: Check off this plan, commit** — `git commit -m "results: offline-resilient boot verified; P2 closed"`
