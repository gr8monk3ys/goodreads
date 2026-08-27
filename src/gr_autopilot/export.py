"""`goodreads.json` — the library as one versioned file other tools can read.

Pure projection of the local store (`data/autopilot.db`); nothing here touches the
account. The `review` field is a tri-state shared with the letterboxd export:
`"own"` for text the user wrote (CSV export), `"ai"` for text the pipeline posted,
`None` when the account holds no review text.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import TypedDict

SCHEMA = "goodreads/1"
FILENAME = "goodreads.json"

# Goodreads' three built-in status shelves. They arrive in the CSV `Bookshelves`
# column alongside custom shelves, so the store's `shelves` table lists them too;
# the export keeps them out of `shelves` (that list is the additive taxonomy only).
EXCLUSIVE_SHELVES = frozenset({"read", "currently-reading", "to-read"})


class ExportBook(TypedDict):
    book_id: int
    title: str
    author: str
    isbn13: str | None
    shelf: str
    shelves: list[str]
    rating: int | None
    date_read: str | None
    review: str | None


class Coverage(TypedDict):
    read: int
    rated: int
    reviewed: int
    queued: int


class ExportDoc(TypedDict):
    schema: str
    generated_at: str
    books: list[ExportBook]
    coverage: Coverage


def review_state(source: str | None, is_empty: int | None) -> str | None:
    """Tri-state review marker: own text, AI-posted text, or nothing on the account."""
    if is_empty is None or int(is_empty) == 1:
        return None
    return "own" if (source or "csv") == "csv" else "ai"


def _taxonomy_shelves(conn: sqlite3.Connection) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for row in conn.execute(
        """
        SELECT bs.book_id, s.name FROM book_shelves bs
        JOIN shelves s ON s.shelf_id = bs.shelf_id
        ORDER BY bs.book_id, s.name
        """
    ):
        name = str(row["name"])
        if name not in EXCLUSIVE_SHELVES:
            out.setdefault(int(row["book_id"]), []).append(name)
    return out


def build_export(conn: sqlite3.Connection, generated_at: str) -> ExportDoc:
    """Every book plus coverage counts. `rating` is null (not 0) when unrated."""
    shelves = _taxonomy_shelves(conn)
    books: list[ExportBook] = []
    read = rated = reviewed = queued = 0
    for row in conn.execute(
        """
        SELECT b.book_id, b.title, b.author, b.isbn13, b.exclusive_shelf, b.my_rating,
               b.date_read, r.source, r.is_empty
        FROM books b LEFT JOIN reviews r ON r.book_id = b.book_id
        ORDER BY b.book_id
        """
    ):
        book_id = int(row["book_id"])
        rating = int(row["my_rating"] or 0) or None
        review = review_state(row["source"], row["is_empty"])
        shelf = row["exclusive_shelf"] or ""
        if shelf == "read":
            read += 1
            rated += rating is not None
            reviewed += review is not None
            queued += rating is None or review is None
        books.append(
            ExportBook(
                book_id=book_id,
                title=row["title"] or "",
                author=row["author"] or "",
                isbn13=row["isbn13"] or None,
                shelf=shelf,
                shelves=shelves.get(book_id, []),
                rating=rating,
                date_read=row["date_read"] or None,
                review=review,
            )
        )
    return ExportDoc(
        schema=SCHEMA,
        generated_at=generated_at,
        books=books,
        coverage=Coverage(read=read, rated=rated, reviewed=reviewed, queued=queued),
    )


def write_export(doc: ExportDoc, path: Path) -> Path:
    """Atomic write: readers never observe a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
