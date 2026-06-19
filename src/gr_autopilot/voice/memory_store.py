from __future__ import annotations

import math

from gr_autopilot.voice.protocols import Exemplar


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Returns 0.0 if either vector is all-zero."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Pure-Python brute-force vector store — correct and fast for small personal corpora.

    Doubles as the default zero-dependency store and the unit-test fixture; the
    Chroma-backed store is a drop-in alternative behind the same protocol.
    """

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []
        self._documents: list[str] = []
        self._metadata: list[dict[str, object]] = []

    def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadata: list[dict[str, object]],
    ) -> None:
        for id_, vec, doc, md in zip(ids, vectors, documents, metadata, strict=True):
            if id_ in self._ids:
                i = self._ids.index(id_)
                self._vectors[i], self._documents[i], self._metadata[i] = vec, doc, md
            else:
                self._ids.append(id_)
                self._vectors.append(vec)
                self._documents.append(doc)
                self._metadata.append(md)

    def query(
        self, vector: list[float], k: int, where: dict[str, object] | None = None
    ) -> list[Exemplar]:
        scored: list[Exemplar] = []
        for id_, vec, doc, md in zip(
            self._ids, self._vectors, self._documents, self._metadata, strict=True
        ):
            if where and not all(md.get(key) == val for key, val in where.items()):
                continue
            scored.append(Exemplar(id=id_, text=doc, score=cosine(vector, vec), metadata=md))
        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:k]

    def count(self) -> int:
        return len(self._ids)
