"""Embedding clients (TDD §4.8, §6.7).

Production embeddings come from a dedicated `llama-server --embeddings --pooling cls` on
:8083 — a separate process so a RAG lookup never queues behind a 1200-token tutoring answer
on the core server.

Every embedder reports an `identity`, and the index records it. Building an index with one
model and querying it with another produces plausible nonsense: no error, no crash, just
worse retrieval that looks like the model being dim. The identity check turns that into a
refusal (`index.py`).
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

import httpx


class Embedder(Protocol):
    identity: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def normalize(vector: Sequence[float]) -> list[float]:
    """Unit-length, so inner product IS cosine similarity — which is why the index can be a
    flat IP index and nothing downstream has to remember to normalise again."""
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else list(vector)


@dataclass
class ServerEmbedder:
    """bge-small over llama-server's OpenAI-compatible embeddings endpoint."""

    base_url: str = "http://127.0.0.1:8083"
    model: str = "bge-small-en-v1.5-q8_0"
    api_key: str | None = None
    timeout: float = 30.0
    dimensions: int = 384

    @property
    def identity(self) -> str:
        return f"server:{self.model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/v1/embeddings",
            json={"model": self.model, "input": list(texts)},
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = sorted(payload["data"], key=lambda d: d.get("index", 0))
        return [normalize(row["embedding"]) for row in rows]

    def healthy(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/health", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False


_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass
class HashingEmbedder:
    """Hashed bag-of-words. **Development and tests only.**

    It exists so the index, the store and the retrieval path can be built and tested without
    a running engine — not as a production fallback. Silently degrading real retrieval to
    keyword hashing would be worse than failing: the tutor would still answer, just with the
    wrong sources, and nobody would see it happen. The identity string makes the substitution
    visible in the index metadata.
    """

    #: 1024, not 256: with signed hashing, collisions between two of a chunk's ~15 content
    #: words are common enough at 256 dims to reorder top-3 results, which makes a plumbing
    #: test look like a retrieval bug.
    dimensions: int = 1024

    @property
    def identity(self) -> str:
        return f"hashing:{self.dimensions}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            tokens = _TOKEN.findall(text.lower())
            for token in tokens:
                digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            vectors.append(normalize(vector))
        return vectors
