import json
import sqlite3

import pytest

from gr_autopilot.catalog.enrich import enrich_missing
from gr_autopilot.catalog.parse import extract_next_data, parse_book_meta
from gr_autopilot.catalog.protocols import BookMeta

# Minimal __NEXT_DATA__ mirroring the verified live structure
# (goodreads.com/book/show/5907: Book.bookGenres[].genre.name inline, and
# Work.stats.averageRating — both re-verified live 2026-08-18).
_NEXT_DATA: dict[str, object] = {
    "props": {
        "pageProps": {
            "apolloState": {
                "Book:kca://book/x": {
                    "__typename": "Book",
                    "legacyId": 5907,
                    "title": "The Hobbit",
                    "bookGenres": [
                        {
                            "__typename": "BookGenre",
                            "genre": {"__typename": "Genre", "name": "Fantasy"},
                        },
                        {
                            "__typename": "BookGenre",
                            "genre": {"__typename": "Genre", "name": "Classics"},
                        },
                    ],
                },
                "Work:kca://work/y": {
                    "__typename": "Work",
                    "stats": {
                        "__typename": "BookOrWorkStats",
                        "averageRating": 4.3,
                        "ratingsCount": 4609640,
                    },
                },
            }
        }
    }
}


def _html(next_data: dict[str, object]) -> str:
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(next_data)
        + "</script></body></html>"
    )


def test_extract_next_data_roundtrip() -> None:
    parsed = extract_next_data(_html(_NEXT_DATA))
    assert "props" in parsed


def test_extract_next_data_missing_raises() -> None:
    with pytest.raises(ValueError, match="no __NEXT_DATA__"):
        extract_next_data("<html>no script here</html>")


def test_parse_book_meta_genres() -> None:
    meta = parse_book_meta(_NEXT_DATA)
    assert meta.book_id == 5907
    assert meta.title == "The Hobbit"
    assert meta.genres == ("Fantasy", "Classics")


def test_parse_book_meta_avg_rating_from_work_stats() -> None:
    assert parse_book_meta(_NEXT_DATA).avg_rating == 4.3


def test_parse_book_meta_missing_work_degrades_to_none_avg() -> None:
    # A page without a Work entry still parses; avg is just unknown.
    no_work = json.loads(json.dumps(_NEXT_DATA))
    del no_work["props"]["pageProps"]["apolloState"]["Work:kca://work/y"]
    meta = parse_book_meta(no_work)
    assert meta.genres == ("Fantasy", "Classics")
    assert meta.avg_rating is None


def test_parse_book_meta_no_book_raises() -> None:
    empty: dict[str, object] = {"props": {"pageProps": {"apolloState": {}}}}
    with pytest.raises(ValueError, match="no Book entry"):
        parse_book_meta(empty)


class FakeCatalog:
    def __init__(self, mapping: dict[int, BookMeta]) -> None:
        self._mapping = mapping
        self.calls: list[int] = []

    def get_meta(self, book_id: int) -> BookMeta | None:
        self.calls.append(book_id)
        return self._mapping.get(book_id)


def _seed_books(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO books (book_id, title) VALUES (1, 'A')")
    conn.execute("INSERT INTO books (book_id, title) VALUES (2, 'B')")
    conn.commit()


def test_enrich_populates_both_fields_and_is_idempotent(conn: sqlite3.Connection) -> None:
    _seed_books(conn)
    catalog = FakeCatalog(
        {
            1: BookMeta(book_id=1, title="A", genres=("Fantasy", "Fiction"), avg_rating=4.3),
            2: BookMeta(book_id=2, title="B", genres=("Mystery",), avg_rating=3.9),
        }
    )
    assert enrich_missing(conn, catalog) == 2
    rows = conn.execute("SELECT genre FROM book_genres WHERE book_id = 1 ORDER BY genre").fetchall()
    assert [r["genre"] for r in rows] == ["Fantasy", "Fiction"]
    avg = conn.execute("SELECT avg_rating FROM books WHERE book_id = 1").fetchone()
    assert avg["avg_rating"] == 4.3
    # second run: nothing missing -> no fetches
    catalog.calls.clear()
    assert enrich_missing(conn, catalog) == 0
    assert catalog.calls == []


def test_enrich_backfills_avg_without_touching_existing_genres(conn: sqlite3.Connection) -> None:
    # The 2026 CSV export dropped Average Rating, so a fully genre-enriched
    # library still needs the avg pass; each book is fetched exactly once.
    _seed_books(conn)
    conn.execute("INSERT INTO book_genres (book_id, genre) VALUES (1, 'Fantasy')")
    conn.execute("INSERT INTO book_genres (book_id, genre) VALUES (2, 'Mystery')")
    conn.commit()
    catalog = FakeCatalog(
        {
            1: BookMeta(book_id=1, title="A", avg_rating=4.1),
            2: BookMeta(book_id=2, title="B", avg_rating=3.5),
        }
    )
    assert enrich_missing(conn, catalog) == 2
    assert sorted(catalog.calls) == [1, 2]
    avgs = conn.execute("SELECT book_id, avg_rating FROM books ORDER BY book_id").fetchall()
    assert [(r["book_id"], r["avg_rating"]) for r in avgs] == [(1, 4.1), (2, 3.5)]


def test_enrich_worklist_puts_read_books_first(conn: sqlite3.Connection) -> None:
    # With --limit, review-leverage ranking benefits first: read books lead.
    conn.execute("INSERT INTO books (book_id, title, exclusive_shelf) VALUES (1, 'A', 'to-read')")
    conn.execute("INSERT INTO books (book_id, title, exclusive_shelf) VALUES (2, 'B', 'read')")
    conn.commit()
    catalog = FakeCatalog({2: BookMeta(book_id=2, title="B", avg_rating=4.0)})
    assert enrich_missing(conn, catalog, limit=1) == 1
    assert catalog.calls == [2]  # the read book, despite the higher id


def test_enrich_skips_books_with_nothing_to_apply(conn: sqlite3.Connection) -> None:
    _seed_books(conn)
    catalog = FakeCatalog({1: BookMeta(book_id=1, title="A", genres=())})  # book 2 absent -> None
    assert enrich_missing(conn, catalog) == 0
