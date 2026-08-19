import sqlite3
from pathlib import Path

from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.insights.load import load_facts
from gr_autopilot.store.repository import set_book_genres, upsert_books

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def test_load_facts_projects_books_reviews_and_genres(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    set_book_genres(conn, 11, ["Science Fiction", "Classics"])

    facts = {f.book_id: f for f in load_facts(conn)}
    assert len(facts) == 3

    dune = facts[11]
    assert dune.title == "Dune"
    assert dune.num_pages == 412
    assert dune.original_pub_year == 1965
    assert dune.my_rating == 5
    assert dune.exclusive_shelf == "read"
    assert dune.has_review is True  # Dune has a non-empty review
    assert dune.review_text == "Loved it.\nA masterpiece."
    assert set(dune.genres) == {"Science Fiction", "Classics"}
    assert set(dune.shelves) == {"sci-fi", "favorites"}  # custom shelves reach analytics

    skim = facts[22]
    assert skim.has_review is False  # empty review -> not a review
    assert skim.review_text == ""
    assert skim.genres == ()
