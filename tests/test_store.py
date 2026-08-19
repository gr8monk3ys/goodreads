import sqlite3
from dataclasses import replace
from pathlib import Path

from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.store.db import init_db
from gr_autopilot.store.repository import (
    set_book_avg_rating,
    targets,
    upsert_books,
    voice_samples,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"

# The pre-migration books schema (10 columns, no num_pages/original_pub_year).
_LEGACY_BOOKS = """
CREATE TABLE books (
    book_id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT, isbn TEXT,
    isbn13 TEXT, my_rating INTEGER DEFAULT 0, avg_rating REAL,
    exclusive_shelf TEXT, date_read TEXT, date_added TEXT
)
"""


def test_init_db_creates_tables(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"books", "reviews", "shelves", "book_shelves"} <= names


def test_is_empty_generated_column(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO books (book_id, title) VALUES (1, 'X')")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (1, '')")
    conn.execute("INSERT INTO books (book_id, title) VALUES (2, 'Y')")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (2, 'real')")
    empty = conn.execute("SELECT book_id FROM reviews WHERE is_empty = 1").fetchall()
    assert [r["book_id"] for r in empty] == [1]


def test_upsert_is_idempotent(conn: sqlite3.Connection) -> None:
    records = parse_export(FIXTURE)
    upsert_books(conn, records)
    upsert_books(conn, records)  # second time must not duplicate
    assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 3
    # 'sci-fi','favorites','fantasy','to-read' = 4 distinct shelves
    assert conn.execute("SELECT COUNT(*) FROM shelves").fetchone()[0] == 4


def test_upsert_persists_pages_and_pub_year(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    row = conn.execute(
        "SELECT num_pages, original_pub_year FROM books WHERE book_id = 11"
    ).fetchone()
    assert row["num_pages"] == 412
    assert row["original_pub_year"] == 1965


def test_reingest_without_avg_rating_preserves_enriched_value(
    conn: sqlite3.Connection,
) -> None:
    # 2026 exports dropped the Average Rating column, so re-ingested records
    # carry avg_rating=None. That must not wipe values set by `gr enrich`.
    records = parse_export(FIXTURE)
    upsert_books(conn, records)
    set_book_avg_rating(conn, 11, 4.44)
    stripped = [replace(r, avg_rating=None) for r in records]
    upsert_books(conn, stripped)
    row = conn.execute("SELECT avg_rating FROM books WHERE book_id = 11").fetchone()
    assert row["avg_rating"] == 4.44


def test_reingest_with_avg_rating_still_updates_it(conn: sqlite3.Connection) -> None:
    records = parse_export(FIXTURE)
    upsert_books(conn, records)
    set_book_avg_rating(conn, 11, 1.11)
    upsert_books(conn, records)  # fixture carries 4.25 for book 11
    row = conn.execute("SELECT avg_rating FROM books WHERE book_id = 11").fetchone()
    assert row["avg_rating"] == 4.25


def test_init_db_migrates_legacy_books_table() -> None:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_LEGACY_BOOKS)  # simulate a DB created before the new columns
    init_db(c)  # must add the two columns idempotently, no error
    init_db(c)  # second run proves idempotency
    cols = {r["name"] for r in c.execute("PRAGMA table_info(books)")}
    assert {"num_pages", "original_pub_year"} <= cols
    c.close()


def test_upsert_updates_review_text(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    row = conn.execute("SELECT review_text FROM reviews WHERE book_id = 11").fetchone()
    assert row["review_text"] == "Loved it.\nA masterpiece."


def test_targets_rated_reads_only(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    rows = targets(conn, require_rating=True)
    # only book 22: read + empty review + rating > 0
    assert [r["book_id"] for r in rows] == [22]


def test_targets_include_unrated_when_disabled(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    rows = targets(conn, require_rating=False)
    # book 22 is the only read+empty-review row in the fixture
    assert [r["book_id"] for r in rows] == [22]


def test_voice_samples_returns_only_nonempty_reviews(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    samples = voice_samples(conn)
    # only Dune (book 11) carries a written review in the fixture
    assert samples == ["Loved it.\nA masterpiece."]
