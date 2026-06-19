import sqlite3
from pathlib import Path

from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.store.repository import targets, upsert_books

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


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
