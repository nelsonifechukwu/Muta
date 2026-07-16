"""Runtime — the inference layer (Lane A).

Owns model provisioning (local folder, or Hugging Face download), the llama.cpp
`llama-server` process, a thin HTTP client to it, and multi-turn conversation state with
SQLite persistence. Downstream, the gateway's `/v1/chat` drives `ChatEngine`.

The architecture keeps `inference` (llama-server) a separate process with an HTTP API
(ROADMAP A.2); this package is how the rest of the system provisions, launches, and talks
to it. Model resolution always yields a *local* GGUF path — HF is only a dev convenience,
because the deployment target is offline (ROADMAP A.1).

Re-exports are lazy (PEP 562) so running a submodule as a script — `python -m runtime.server`
— does not trigger a re-import of that submodule via this package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "ChatEngine",
    "ChatResult",
    "ConversationStore",
    "InferenceClient",
    "LlamaServer",
    "RuntimeConfig",
    "resolve_model",
]

_LAZY = {
    "ChatEngine": "runtime.chat",
    "ChatResult": "runtime.chat",
    "InferenceClient": "runtime.client",
    "RuntimeConfig": "runtime.config",
    "ConversationStore": "runtime.memory",
    "resolve_model": "runtime.models",
    "LlamaServer": "runtime.server",
}


def __getattr__(name: str):
    if name in _LAZY:
        import importlib

        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(f"module 'runtime' has no attribute {name!r}")


if TYPE_CHECKING:
    from runtime.chat import ChatEngine, ChatResult
    from runtime.client import InferenceClient
    from runtime.config import RuntimeConfig
    from runtime.memory import ConversationStore
    from runtime.models import resolve_model
    from runtime.server import LlamaServer
