"""Connectivity: a cached is-the-internet-there verdict (design P2, 2026-08-08).

The probe runs on a timer thread started by the lifespan — never per request. Online
features (cloud boost, web grounding, update hints) key off `online()`, and `/v1/ready`
reports it so the UI can show a quiet status dot. Offline is a state, not an error, which
is why the verdict is a top-level `online` field and never a readiness check.
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
        self.forced_offline = os.environ.get("MUTA_OFFLINE", "0").lower() in {
            "1", "true", "yes", "on"
        }
        self._online: bool | None = False if self.forced_offline else None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def online(self) -> bool | None:
        """Latest verdict; None until the first probe has run."""
        return self._online

    def probe_once(self) -> bool:
        if self.forced_offline:
            self._online = False
            return False
        try:
            # Any HTTP status proves routing (captive portals 302, rate limits 403 — the
            # packets still made it out); only transport failure means offline.
            httpx.head(self.url, timeout=3.0, follow_redirects=True)
            self._online = True
        except httpx.HTTPError:
            self._online = False
        return self._online

    def start(self) -> None:
        if self.forced_offline:
            self._online = False
            return
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
