import json
import sqlite3

import pytest

from gr_autopilot.catalog.enrich import enrich_genres
from gr_autopilot.catalog.parse import extract_next_data, parse_book_meta
from gr_autopilot.catalog.protocols import BookMeta

# Minimal __NEXT_DATA__ mirroring the verified live structure
# (goodreads.com/book/show/5907: Book.bookGenres[].genre.name, inline).
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
                }
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


def test_enrich_genres_populates_and_is_idempotent(conn: sqlite3.Connection) -> None:
    _seed_books(conn)
    catalog = FakeCatalog(
        {
            1: BookMeta(book_id=1, title="A", genres=("Fantasy", "Fiction")),
            2: BookMeta(book_id=2, title="B", genres=("Mystery",)),
        }
    )
    assert enrich_genres(conn, catalog) == 2
    rows = conn.execute(
        "SELECT genre FROM book_genres WHERE book_id = 1 ORDER BY genre"
    ).fetchall()
    assert [r["genre"] for r in rows] == ["Fantasy", "Fiction"]
    # second run: nothing missing -> no fetches
    catalog.calls.clear()
    assert enrich_genres(conn, catalog) == 0
    assert catalog.calls == []


def test_enrich_skips_books_with_no_genres(conn: sqlite3.Connection) -> None:
    _seed_books(conn)
    catalog = FakeCatalog(
        {1: BookMeta(book_id=1, title="A", genres=())}
    )  # book 2 absent -> None
    assert enrich_genres(conn, catalog) == 0
