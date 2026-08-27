import json
import sqlite3
from pathlib import Path

import pytest

from gr_autopilot.config import Settings
from gr_autopilot.export import SCHEMA, build_export, write_export


def _book(
    conn: sqlite3.Connection,
    book_id: int,
    *,
    shelf: str = "read",
    rating: int = 0,
    date_read: str | None = None,
    review: str | None = None,
    source: str = "csv",
    shelves: tuple[str, ...] = (),
) -> None:
    conn.execute(
        "INSERT INTO books (book_id, title, author, isbn13, my_rating, exclusive_shelf, date_read)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (book_id, f"T{book_id}", f"A{book_id}", f"978{book_id}", rating, shelf, date_read),
    )
    conn.execute(
        "INSERT INTO reviews (book_id, review_text, source) VALUES (?, ?, ?)",
        (book_id, review, source),
    )
    for name in (shelf, *shelves):
        conn.execute("INSERT OR IGNORE INTO shelves (name) VALUES (?)", (name,))
        sid = conn.execute("SELECT shelf_id FROM shelves WHERE name = ?", (name,)).fetchone()[0]
        conn.execute("INSERT INTO book_shelves (book_id, shelf_id) VALUES (?, ?)", (book_id, sid))


@pytest.fixture
def library(conn: sqlite3.Connection) -> sqlite3.Connection:
    _book(conn, 1, rating=5, date_read="2024/03/01", review="mine", shelves=("classics",))
    _book(conn, 2, rating=4, date_read="2024/02/01", review="ai text", source="claude")
    _book(conn, 3, rating=0, date_read="2024/01/01", review="")
    _book(conn, 4, rating=3, date_read=None)  # no review row text -> None
    _book(conn, 5, shelf="to-read", shelves=("classics",))
    _book(conn, 6, shelf="currently-reading")
    conn.commit()
    return conn


def test_export_shape_and_review_tristate(library: sqlite3.Connection) -> None:
    doc = build_export(library, generated_at="2026-08-27T00:00:00Z")
    assert doc["schema"] == SCHEMA == "goodreads/1"
    assert doc["generated_at"] == "2026-08-27T00:00:00Z"
    books = {b["book_id"]: b for b in doc["books"]}
    assert len(books) == 6
    assert books[1]["review"] == "own"
    assert books[2]["review"] == "ai"
    assert books[3]["review"] is None
    assert books[4]["review"] is None
    assert dict(books[1]) == {
        "book_id": 1,
        "title": "T1",
        "author": "A1",
        "isbn13": "9781",
        "shelf": "read",
        "shelves": ["classics"],
        "rating": 5,
        "date_read": "2024/03/01",
        "review": "own",
    }
    assert books[3]["rating"] is None  # unrated is null, never 0
    # exclusive shelves never leak into the taxonomy list
    assert books[5]["shelves"] == ["classics"]
    assert books[6]["shelves"] == []


def test_export_coverage_counts(library: sqlite3.Connection) -> None:
    doc = build_export(library, generated_at="x")
    # read=4; rated read=3 (1,2,4); reviewed read=2 (own + ai); queued = read books
    # still needing a rating or a review = {3 (unrated+unreviewed), 4 (unreviewed)}
    assert doc["coverage"] == {"read": 4, "rated": 3, "reviewed": 2, "queued": 2}


def test_export_books_are_deterministically_ordered(library: sqlite3.Connection) -> None:
    doc = build_export(library, generated_at="x")
    ids = [b["book_id"] for b in doc["books"]]
    assert ids == sorted(ids)


def test_write_export_is_atomic_and_round_trips(
    library: sqlite3.Connection, tmp_path: Path
) -> None:
    doc = build_export(library, generated_at="x")
    out = tmp_path / "nested" / "goodreads.json"
    written = write_export(doc, out)
    assert written == out
    assert json.loads(out.read_text(encoding="utf-8")) == doc
    assert not list(out.parent.glob("*.tmp"))  # no temp file left behind


def test_books_dir_setting_honours_BOOKS_DIR(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: N802
    monkeypatch.delenv("BOOKS_DIR", raising=False)
    assert Settings().books_dir == Path.home() / ".books"
    monkeypatch.setenv("BOOKS_DIR", "/tmp/elsewhere")  # noqa: S108
    assert Settings().books_dir == Path("/tmp/elsewhere")  # noqa: S108
