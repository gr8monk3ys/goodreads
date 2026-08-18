from __future__ import annotations

import sqlite3

from gr_autopilot.catalog.protocols import Catalog
from gr_autopilot.store.repository import (
    books_missing_enrichment,
    set_book_avg_rating,
    set_book_genres,
)


def enrich_missing(
    conn: sqlite3.Connection,
    catalog: Catalog,
    limit: int | None = None,
    max_consecutive_misses: int = 5,
) -> int:
    """Fetch each book missing genres or avg_rating once; store whatever the page has.

    Returns books that gained at least one field. Idempotent: a fully enriched
    book leaves the worklist; one whose page lacks a field is retried next run.
    The worklist leads with read books so a --limit pass repairs review-leverage
    ranking first (the 2026 CSV export dropped Average Rating entirely).

    An unbroken run of failed fetches is the rate-limit signature (observed live:
    ~180 futile calls into a dead throttle), so after max_consecutive_misses the
    run aborts — the worklist keeps the remainder for the next invocation.
    """
    ids = books_missing_enrichment(conn)
    if limit is not None:
        ids = ids[:limit]
    enriched = 0
    misses = 0
    for book_id in ids:
        meta = catalog.get_meta(book_id)
        if meta is None:
            misses += 1
            if misses >= max_consecutive_misses:
                break
            continue
        misses = 0
        applied = False
        if meta.genres:
            set_book_genres(conn, book_id, meta.genres)
            applied = True
        if meta.avg_rating is not None:
            set_book_avg_rating(conn, book_id, meta.avg_rating)
            applied = True
        if applied:
            enriched += 1
    return enriched
