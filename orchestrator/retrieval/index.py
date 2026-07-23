"""RAG index: chunk store + flat inner-product search (TDD §6.7, T11).

    python -m orchestrator.retrieval.index build  --corpus corpus/chunks.jsonl --out index/
    python -m orchestrator.retrieval.index search --index index/ --query "quadratic formula"

Flat, not IVF: the syllabus corpus is thousands of chunks, not millions, and at that size a
flat index is both faster and exactly correct while IVF adds a training step, a nprobe knob
and a recall cliff nobody will have time to debug in August. Vectors are unit-normalised at
embed time, so inner product is cosine similarity.

FAISS when it is installed, NumPy otherwise — a matmul against a few thousand 384-dim
vectors is sub-millisecond, so the fallback is a real implementation rather than a stub. Both
mmap the vectors read-only: the gateway's cap is 600 MiB and the index counts against it.

The invariant worth stating: **an index records the embedder that built it and refuses a
query from a different one.** A mismatch produces no error, just quietly wrong retrieval.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from orchestrator.gateway.prompt_layout import RetrievedChunk
from orchestrator.retrieval.embedder import Embedder, HashingEmbedder, ServerEmbedder

VECTORS_FILE = "vectors.npy"
META_FILE = "index.json"
CHUNKS_DB = "chunks.sqlite"


class IndexMismatch(RuntimeError):
    """The query embedder is not the one that built the index."""


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    chunk_id: int
    text: str
    subject: str = "math"
    source: str = ""

    @property
    def key(self) -> str:
        return f"{self.doc_id}:{self.chunk_id}"


class ChunkStore:
    """SQLite-backed chunk text. The vectors find the chunk; this returns what it says."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS chunks (
                   row_id   INTEGER PRIMARY KEY,
                   doc_id   TEXT NOT NULL,
                   chunk_id INTEGER NOT NULL,
                   text     TEXT NOT NULL,
                   subject  TEXT NOT NULL DEFAULT 'math',
                   source   TEXT NOT NULL DEFAULT '',
                   UNIQUE (doc_id, chunk_id))"""
        )
        self.db.commit()

    def add_all(self, chunks: Iterable[Chunk]) -> int:
        rows = [(i, c.doc_id, c.chunk_id, c.text, c.subject, c.source) for i, c in enumerate(chunks)]
        self.db.executemany(
            "INSERT OR REPLACE INTO chunks (row_id, doc_id, chunk_id, text, subject, source)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.db.commit()
        return len(rows)

    def get(self, row_id: int) -> Chunk | None:
        row = self.db.execute("SELECT * FROM chunks WHERE row_id = ?", (row_id,)).fetchone()
        if row is None:
            return None
        return Chunk(row["doc_id"], row["chunk_id"], row["text"], row["subject"], row["source"])

    def __len__(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def close(self) -> None:
        self.db.close()


class FlatIndex:
    """Inner-product search over unit vectors, FAISS-backed when available."""

    def __init__(self, vectors, *, embedder_identity: str, dimensions: int) -> None:
        self.vectors = vectors  # numpy array (n, d), float32
        self.embedder_identity = embedder_identity
        self.dimensions = dimensions
        self._faiss = None
        self._maybe_build_faiss()

    def _maybe_build_faiss(self) -> None:
        try:
            import faiss
        except ImportError:
            return
        index = faiss.IndexFlatIP(self.dimensions)
        index.add(self.vectors)
        self._faiss = index

    @property
    def backend(self) -> str:
        return "faiss" if self._faiss is not None else "numpy"

    def __len__(self) -> int:
        return int(self.vectors.shape[0])

    def search(self, query_vectors, k: int) -> list[list[tuple[int, float]]]:
        import numpy as np

        queries = np.asarray(query_vectors, dtype="float32")
        if queries.ndim == 1:
            queries = queries.reshape(1, -1)
        k = min(k, len(self))
        if k == 0:
            return [[] for _ in queries]
        if self._faiss is not None:
            scores, ids = self._faiss.search(queries, k)
        else:
            scores_all = queries @ self.vectors.T
            ids = np.argsort(-scores_all, axis=1)[:, :k]
            scores = np.take_along_axis(scores_all, ids, axis=1)
        return [
            [(int(i), float(s)) for i, s in zip(row_ids, row_scores)]
            for row_ids, row_scores in zip(ids, scores)
        ]

    # --- persistence ------------------------------------------------------------------
    def save(self, directory: Path | str) -> Path:
        import numpy as np

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / VECTORS_FILE, self.vectors)
        (directory / META_FILE).write_text(
            json.dumps(
                {
                    "embedder": self.embedder_identity,
                    "dimensions": self.dimensions,
                    "count": len(self),
                },
                indent=2,
            )
            + "\n"
        )
        return directory

    @classmethod
    def load(cls, directory: Path | str) -> "FlatIndex":
        import numpy as np

        directory = Path(directory)
        meta = json.loads((directory / META_FILE).read_text())
        # mmap_mode: the vectors are read-only and count against the gateway's 600 MiB cap;
        # there is no reason for them to be anonymous heap.
        vectors = np.load(directory / VECTORS_FILE, mmap_mode="r")
        return cls(
            np.ascontiguousarray(vectors, dtype="float32"),
            embedder_identity=meta["embedder"],
            dimensions=int(meta["dimensions"]),
        )


def build_index(chunks: Sequence[Chunk], embedder: Embedder, out_dir: Path | str, *, batch: int = 64):
    """Embed every chunk and write `index/` + `chunks.sqlite` (build-time, never at runtime)."""
    import numpy as np

    out_dir = Path(out_dir)
    store = ChunkStore(out_dir / CHUNKS_DB)
    store.add_all(chunks)

    vectors: list[list[float]] = []
    for start in range(0, len(chunks), batch):
        vectors.extend(embedder.embed([c.text for c in chunks[start : start + batch]]))

    array = np.asarray(vectors, dtype="float32") if vectors else np.zeros((0, embedder.dimensions), "float32")
    index = FlatIndex(array, embedder_identity=embedder.identity, dimensions=embedder.dimensions)
    index.save(out_dir)
    store.close()
    return index


@dataclass
class Retriever:
    """Query-time side: embed the question, take top-k, return citable chunks."""

    index: FlatIndex
    store: ChunkStore
    embedder: Embedder

    def __post_init__(self) -> None:
        if self.index.embedder_identity != self.embedder.identity:
            raise IndexMismatch(
                f"index was built with {self.index.embedder_identity!r} but the query "
                f"embedder is {self.embedder.identity!r} — retrieval would silently return "
                "plausible nonsense, so it is refused instead"
            )

    @classmethod
    def open(cls, directory: Path | str, embedder: Embedder) -> "Retriever":
        directory = Path(directory)
        return cls(FlatIndex.load(directory), ChunkStore(directory / CHUNKS_DB), embedder)

    def search(self, query: str, k: int = 5, *, min_score: float = 0.0) -> list[RetrievedChunk]:
        if not query.strip() or len(self.index) == 0:
            return []
        (hits,) = self.index.search(self.embedder.embed([query]), k)
        out: list[RetrievedChunk] = []
        for row_id, score in hits:
            if score < min_score:
                continue
            chunk = self.store.get(row_id)
            if chunk is not None:
                out.append(RetrievedChunk(chunk.doc_id, chunk.chunk_id, chunk.text, score))
        return out


def load_chunks(path: Path | str) -> list[Chunk]:
    """Read `chunks.jsonl` — one JSON object per line, the corpus lane's output."""
    chunks: list[Chunk] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        chunks.append(
            Chunk(
                doc_id=str(raw["doc_id"]),
                chunk_id=int(raw.get("chunk_id", len(chunks))),
                text=str(raw["text"]),
                subject=str(raw.get("subject", "math")),
                source=str(raw.get("source", "")),
            )
        )
    return chunks


def _embedder(name: str) -> Embedder:
    return HashingEmbedder() if name == "hashing" else ServerEmbedder()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="embed a corpus into an index (build machine only)")
    b.add_argument("--corpus", required=True, help="chunks.jsonl")
    b.add_argument("--out", required=True)
    b.add_argument("--embedder", default="server", choices=["server", "hashing"])

    s = sub.add_parser("search", help="query an index")
    s.add_argument("--index", required=True)
    s.add_argument("--query", required=True)
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--embedder", default="server", choices=["server", "hashing"])

    args = p.parse_args(argv)
    embedder = _embedder(args.embedder)

    if args.cmd == "build":
        chunks = load_chunks(args.corpus)
        index = build_index(chunks, embedder, args.out)
        print(f"indexed {len(index)} chunks ({index.backend}) with {embedder.identity} → {args.out}")
        return 0

    try:
        retriever = Retriever.open(args.index, embedder)
    except IndexMismatch as e:
        print(str(e), file=sys.stderr)
        return 1
    for hit in retriever.search(args.query, args.k):
        print(f"{hit.score:.3f} {hit.cite} {hit.text[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
