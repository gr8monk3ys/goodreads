from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Exemplar:
    """A retrieved past review used to condition generation."""

    id: str
    text: str
    score: float
    metadata: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Embedder(Protocol):
    """Embeds text to vectors. Implementations may apply a query-only instruction."""

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class VectorStore(Protocol):
    """Stores document vectors and answers nearest-neighbour queries."""

    def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadata: list[dict[str, object]],
    ) -> None: ...

    def query(
        self, vector: list[float], k: int, where: dict[str, object] | None = None
    ) -> list[Exemplar]: ...

    def count(self) -> int: ...
