"""Web snippets for grounding (design P4, 2026-08-08) — SearXNG-shaped, fail-silent.

No agentic tool-calling on a 4B model: the gateway fetches top-k snippets up front and
injects them as context. Grounding is a bonus, never a blocker — every failure mode
(offline, slow endpoint, malformed body) is an empty list, and the answer proceeds
exactly as it would have without the web.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger("muta.gateway.websearch")


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    snippet: str


def fetch_snippets(
    query: str, *, base_url: str, k: int = 3, timeout: float = 2.0
) -> list[Source]:
    """GET `{base_url}/search?q=…&format=json` (SearXNG shape) → up to k Sources."""
    try:
        r = httpx.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json"},
            timeout=timeout,
        )
        results = r.json().get("results") or []
    except Exception:  # noqa: BLE001 — any failure is "no grounding", never an error
        log.debug("web search failed — answering ungrounded", exc_info=True)
        return []
    out: list[Source] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title, url, content = item.get("title"), item.get("url"), item.get("content")
        if not (title and url and content):
            continue
        out.append(Source(title=str(title), url=str(url), snippet=str(content)))
        if len(out) >= k:
            break
    return out
