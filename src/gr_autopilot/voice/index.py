from __future__ import annotations

import sqlite3

from gr_autopilot.voice.protocols import Embedder, Exemplar, VectorStore


def build_index(
    conn: sqlite3.Connection, embedder: Embedder, store: VectorStore
) -> int:
    """Embed every non-empty review in the store and upsert it into the vector store.

    Returns the number of reviews indexed.
    """
    rows = conn.execute("""
        SELECT r.book_id AS book_id, r.review_text AS review_text, b.my_rating AS my_rating,
               (SELECT g.genre FROM book_genres g WHERE g.book_id = b.book_id LIMIT 1) AS genre
        FROM reviews r
        JOIN books b ON b.book_id = r.book_id
        WHERE r.is_empty = 0
        """).fetchall()
    if not rows:
        return 0
    texts = [str(r["review_text"]) for r in rows]
    vectors = embedder.embed_documents(texts)
    ids = [str(r["book_id"]) for r in rows]
    metadata: list[dict[str, object]] = [
        {"book_id": r["book_id"], "rating": r["my_rating"], "genre": r["genre"] or ""}
        for r in rows
    ]
    store.upsert(ids, vectors, texts, metadata)
    return len(rows)


def retrieve(
    query_text: str,
    embedder: Embedder,
    store: VectorStore,
    k: int = 5,
    where: dict[str, object] | None = None,
) -> list[Exemplar]:
    """Return the k stylistically nearest past reviews to query_text."""
    return store.query(embedder.embed_query(query_text), k, where)
