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
                               avg_rating, exclusive_shelf, date_read, date_added,
                               num_pages, original_pub_year)
            VALUES (:book_id, :title, :author, :isbn, :isbn13, :my_rating,
                    :avg_rating, :exclusive_shelf, :date_read, :date_added,
                    :num_pages, :original_pub_year)
            ON CONFLICT(book_id) DO UPDATE SET
                title=excluded.title, author=excluded.author, isbn=excluded.isbn,
                isbn13=excluded.isbn13, my_rating=excluded.my_rating,
                avg_rating=excluded.avg_rating, exclusive_shelf=excluded.exclusive_shelf,
                date_read=excluded.date_read, date_added=excluded.date_added,
                num_pages=excluded.num_pages, original_pub_year=excluded.original_pub_year
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
                "num_pages": r.num_pages,
                "original_pub_year": r.original_pub_year,
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
    cur = conn.execute(
        "INSERT INTO runs (started_at, mode) VALUES (datetime('now'), ?)", (mode,)
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def finish_run(
    conn: sqlite3.Connection, run_id: int, planned: int, done: int, failed: int
) -> None:
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


def books_without_genres(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("""
        SELECT b.book_id FROM books b
        WHERE NOT EXISTS (SELECT 1 FROM book_genres g WHERE g.book_id = b.book_id)
        ORDER BY b.book_id
        """).fetchall()
    return [int(r["book_id"]) for r in rows]


def set_book_genres(
    conn: sqlite3.Connection, book_id: int, genres: Sequence[str]
) -> None:
    for genre in genres:
        conn.execute(
            "INSERT OR IGNORE INTO book_genres (book_id, genre) VALUES (?, ?)",
            (book_id, genre),
        )
    conn.commit()


def voice_samples(conn: sqlite3.Connection) -> list[str]:
    """The user's existing written reviews — style exemplars for voice-matched drafting."""
    rows = conn.execute(
        "SELECT review_text FROM reviews WHERE is_empty = 0 ORDER BY book_id"
    ).fetchall()
    return [str(r["review_text"]) for r in rows]


def book_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every book with a has_review flag (non-empty review), for read-only analytics."""
    return conn.execute("""
        SELECT b.book_id, b.title, b.author, b.my_rating, b.avg_rating, b.exclusive_shelf,
               b.date_read, b.date_added, b.num_pages, b.original_pub_year,
               CASE WHEN r.is_empty = 0 THEN 1 ELSE 0 END AS has_review,
               COALESCE(r.review_text, '') AS review_text
        FROM books b
        LEFT JOIN reviews r ON r.book_id = b.book_id
        """).fetchall()


def genres_by_book(conn: sqlite3.Connection) -> dict[int, tuple[str, ...]]:
    """book_id -> its genres, for analytics joins."""
    out: dict[int, list[str]] = {}
    for row in conn.execute(
        "SELECT book_id, genre FROM book_genres ORDER BY book_id, genre"
    ):
        out.setdefault(int(row["book_id"]), []).append(str(row["genre"]))
    return {bid: tuple(gs) for bid, gs in out.items()}
