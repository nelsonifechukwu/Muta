"""Gateway dependencies: the shared ChatEngine and the mode → system-prompt loader.

`get_engine` is a FastAPI dependency (so tests can override it with a fake) that builds one
process-wide ChatEngine over the runtime. Construction touches no network — only the first
real `/chat` call reaches llama-server — so importing the app stays cheap and offline.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from runtime.chat import ChatEngine
from runtime.client import InferenceClient
from runtime.config import RuntimeConfig
from runtime.memory import ConversationStore

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@lru_cache(maxsize=8)
def load_prompt(mode: str) -> str:
    """Read a persona/system prompt for the mode, stripping the authoring comment header."""
    path = _PROMPTS_DIR / f"{mode}.md"
    if not path.exists():
        path = _PROMPTS_DIR / "socratic.md"
    return _COMMENT.sub("", path.read_text()).strip()


@lru_cache(maxsize=1)
def get_engine() -> ChatEngine:
    cfg = RuntimeConfig()
    client = InferenceClient(
        cfg.base_url, model=cfg.model_alias, enable_thinking=cfg.enable_thinking
    )
    store = ConversationStore(cfg.db_path)
    return ChatEngine(client, store, max_history_messages=cfg.max_history_messages)
