from __future__ import annotations

import sqlite3

from gr_autopilot.catalog.protocols import Catalog
from gr_autopilot.store.repository import books_without_genres, set_book_genres


def enrich_genres(
    conn: sqlite3.Connection, catalog: Catalog, limit: int | None = None
) -> int:
    """Fetch genres for books that have none yet and store them. Returns books enriched.

    Idempotent: only books missing genres are fetched, and inserts ignore duplicates.
    """
    ids = books_without_genres(conn)
    if limit is not None:
        ids = ids[:limit]
    enriched = 0
    for book_id in ids:
        meta = catalog.get_meta(book_id)
        if meta is None or not meta.genres:
            continue
        set_book_genres(conn, book_id, meta.genres)
        enriched += 1
    return enriched
