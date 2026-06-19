from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from gr_autopilot.ingest.csv_parser import BookRecord


def upsert_books(conn: sqlite3.Connection, records: Sequence[BookRecord]) -> int:
    """Insert or update books, their reviews, and shelf memberships. Idempotent."""
    for r in records:
        conn.execute(
            """
            INSERT INTO books (book_id, title, author, isbn, isbn13, my_rating,
                               avg_rating, exclusive_shelf, date_read, date_added)
            VALUES (:book_id, :title, :author, :isbn, :isbn13, :my_rating,
                    :avg_rating, :exclusive_shelf, :date_read, :date_added)
            ON CONFLICT(book_id) DO UPDATE SET
                title=excluded.title, author=excluded.author, isbn=excluded.isbn,
                isbn13=excluded.isbn13, my_rating=excluded.my_rating,
                avg_rating=excluded.avg_rating, exclusive_shelf=excluded.exclusive_shelf,
                date_read=excluded.date_read, date_added=excluded.date_added
            """,
            {
                "book_id": r.book_id,
                "title": r.title,
                "author": r.author,
                "isbn": r.isbn,
                "isbn13": r.isbn13,
                "my_rating": r.my_rating,
                "avg_rating": r.avg_rating,
                "exclusive_shelf": r.exclusive_shelf,
                "date_read": r.date_read,
                "date_added": r.date_added,
            },
        )
        conn.execute(
            """
            INSERT INTO reviews (book_id, review_html, review_text, has_spoiler, source)
            VALUES (:book_id, :review_html, :review_text, :has_spoiler, 'csv')
            ON CONFLICT(book_id) DO UPDATE SET
                review_html=excluded.review_html, review_text=excluded.review_text,
                has_spoiler=excluded.has_spoiler
            """,
            {
                "book_id": r.book_id,
                "review_html": r.review_html,
                "review_text": r.review_text,
                "has_spoiler": int(r.has_spoiler),
            },
        )
        for shelf in r.shelves:
            conn.execute("INSERT OR IGNORE INTO shelves (name) VALUES (?)", (shelf,))
            shelf_id = conn.execute(
                "SELECT shelf_id FROM shelves WHERE name = ?", (shelf,)
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO book_shelves (book_id, shelf_id) VALUES (?, ?)",
                (r.book_id, shelf_id),
            )
    conn.commit()
    return len(records)


def targets(conn: sqlite3.Connection, require_rating: bool = True) -> list[sqlite3.Row]:
    """Read-but-unreviewed books. require_rating restricts to my_rating > 0 (sign-off default)."""
    query = """
        SELECT b.book_id, b.title, b.author, b.my_rating, b.date_read
        FROM books b
        JOIN reviews r ON r.book_id = b.book_id
        WHERE b.exclusive_shelf = 'read' AND r.is_empty = 1
    """
    if require_rating:
        query += " AND b.my_rating > 0"
    query += " ORDER BY b.date_read DESC"
    return conn.execute(query).fetchall()


def start_run(conn: sqlite3.Connection, mode: str) -> int:
    cur = conn.execute("INSERT INTO runs (started_at, mode) VALUES (datetime('now'), ?)", (mode,))
    conn.commit()
    return int(cur.lastrowid or 0)


def finish_run(conn: sqlite3.Connection, run_id: int, planned: int, done: int, failed: int) -> None:
    conn.execute(
        """
        UPDATE runs SET finished_at = datetime('now'),
            actions_planned = ?, actions_done = ?, actions_failed = ?
        WHERE run_id = ?
        """,
        (planned, done, failed, run_id),
    )
    conn.commit()


def record_action(
    conn: sqlite3.Connection,
    run_id: int,
    book_id: int | None,
    action_type: str,
    payload_hash: str,
    status: str,
    *,
    dry_run: bool,
    detail: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO actions_log
            (run_id, book_id, action_type, payload_hash, status, dry_run, created_at, detail)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)
        """,
        (run_id, book_id, action_type, payload_hash, status, int(dry_run), detail),
    )
    conn.commit()


def already_done(
    conn: sqlite3.Connection, book_id: int | None, action_type: str, payload_hash: str
) -> bool:
    """True if this exact action already completed successfully (idempotency guard)."""
    row = conn.execute(
        """
        SELECT 1 FROM actions_log
        WHERE book_id IS ? AND action_type = ? AND payload_hash = ? AND status = 'done'
        LIMIT 1
        """,
        (book_id, action_type, payload_hash),
    ).fetchone()
    return row is not None
