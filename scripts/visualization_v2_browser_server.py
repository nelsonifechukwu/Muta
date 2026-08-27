#!/usr/bin/env python3
"""Serve the real-browser V2 gate and receive its machine-readable result.

The receiver binds to loopback, accepts one bounded JSON document at ``/__results``, and
writes only to the explicitly supplied output path. It exists so the checked-in acceptance
report can be reproduced without copying a large DOM text node by hand.
"""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_RESULT_BYTES = 8 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18084)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matrix-output", type=Path)
    parser.add_argument("--lru-output", type=Path)
    parser.add_argument("--directory", type=Path, default=Path.cwd())
    args = parser.parse_args()
    output = args.output.resolve()
    matrix_output = (
        args.matrix_output.resolve()
        if args.matrix_output
        else output.with_name(f"{output.stem}-matrix{output.suffix}")
    )
    lru_output = (
        args.lru_output.resolve()
        if args.lru_output
        else output.with_name(f"{output.stem}-lru{output.suffix}")
    )
    directory = args.directory.resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *handler_args: object, **handler_kwargs: object) -> None:
            super().__init__(*handler_args, directory=str(directory), **handler_kwargs)

        def do_POST(self) -> None:
            if self.path not in {"/__results", "/__matrix", "/__lru"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 1 <= length <= MAX_RESULT_BYTES:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(HTTPStatus.BAD_REQUEST, "result must be JSON")
                return
            if self.path == "/__lru":
                valid = (
                    isinstance(payload, dict)
                    and payload.get("total") == 6
                    and payload.get("initial_active") == 4
                    and payload.get("initial_suspended") == 2
                    and payload.get("restored_with_cap_preserved") is True
                    and payload.get("passed") is True
                )
                expected_error = "LRU result must prove total=6, active=4, suspended=2, and restore"
                destination = lru_output
            else:
                expected_count = 200 if self.path == "/__results" else 5
                valid = (
                    isinstance(payload, dict)
                    and payload.get("count") == expected_count
                    and len(payload.get("cases", [])) == expected_count
                )
                expected_error = f"result must contain {expected_count} cases"
                destination = output if self.path == "/__results" else matrix_output
            if not valid:
                self.send_error(HTTPStatus.BAD_REQUEST, expected_error)
                return
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
            temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            temporary.replace(destination)
            body = b'{"stored":true}'
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(
        f"Visualization V2 browser gate: http://127.0.0.1:{args.port}/ui/tests/visualization-v2-browser-gate.html?report=1"
    )
    print(f"Result output: {output}")
    print(f"Matrix output: {matrix_output}")
    print(f"LRU output: {lru_output}")
    server.serve_forever()


if __name__ == "__main__":
    main()
