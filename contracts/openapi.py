"""Generate `contracts/openapi.yaml` from the assembled app's public `/v1` surface.

    python -m contracts.openapi      # or: make contract

The Pydantic models + gateway routes are the source of truth; the YAML is a derived
artifact clients bind to. Regenerate whenever the contract changes; commit the result.
"""

from __future__ import annotations

from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent / "openapi.yaml"


def generate() -> Path:
    # Lazy import so importing the `contracts` package never pulls in the app (no cycle).
    from orchestrator.main import app

    schema = app.openapi()
    OUT.write_text(yaml.safe_dump(schema, sort_keys=False, width=100, allow_unicode=True))
    return OUT


if __name__ == "__main__":
    path = generate()
    print(f"wrote {path}")
