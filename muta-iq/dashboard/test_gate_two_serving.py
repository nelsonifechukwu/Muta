"""HTTP coverage for the published Gate 2 evidence archive."""

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

import app
import build_gate_two_evidence


def test_every_advertised_download_is_served():
    with TemporaryDirectory() as tmp:
        evidence = build_gate_two_evidence.build(Path(tmp) / "gate-2")
        saved = app.GATE_TWO_EVIDENCE_DIR
        app.GATE_TWO_EVIDENCE_DIR = evidence
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            manifest = json.loads((evidence / "index.json").read_text())
            base = f"http://127.0.0.1:{server.server_port}/evidence/gate-2/"
            for item in manifest["downloads"]:
                with urlopen(base + item["path"], timeout=5) as response:
                    assert response.status == 200, item["path"]
                    assert int(response.headers["Content-Length"]) > 0
            with urlopen(base + "raw/manual-stem/", timeout=5) as response:
                assert response.status == 200
                assert b"evidence files" in response.read()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            app.GATE_TWO_EVIDENCE_DIR = saved
