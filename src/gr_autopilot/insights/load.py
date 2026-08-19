"""Adapter: project the SQLite store into pure `BookFact`s for the metrics layer.

This is the only place in insights/ that knows about the database. metrics/suggestions/report
all operate on `BookFact`s, so they stay testable without any I/O.
"""

from __future__ import annotations

import sqlite3

from gr_autopilot.insights.metrics import BookFact
from gr_autopilot.store.repository import book_rows, genres_by_book, shelves_by_book


def load_facts(conn: sqlite3.Connection) -> list[BookFact]:
    genres = genres_by_book(conn)
    shelves = shelves_by_book(conn)
    facts: list[BookFact] = []
    for row in book_rows(conn):
        book_id = int(row["book_id"])
        facts.append(
            BookFact(
                book_id=book_id,
                title=row["title"] or "",
                author=row["author"] or "",
                my_rating=int(row["my_rating"] or 0),
                avg_rating=row["avg_rating"],
                exclusive_shelf=row["exclusive_shelf"] or "",
                date_read=row["date_read"],
                date_added=row["date_added"],
                num_pages=row["num_pages"],
                original_pub_year=row["original_pub_year"],
                has_review=bool(row["has_review"]),
                review_text=row["review_text"] or "",
                genres=genres.get(book_id, ()),
                shelves=shelves.get(book_id, ()),
            )
        )
    return facts
