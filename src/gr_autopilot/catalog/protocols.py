from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class BookMeta:
    book_id: int
    title: str
    genres: tuple[str, ...] = field(default_factory=tuple)


class Catalog(Protocol):
    """Read-only public book metadata source (no auth). Returns None if not found."""

    def get_meta(self, book_id: int) -> BookMeta | None: ...
