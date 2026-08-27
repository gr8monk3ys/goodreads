import sqlite3
from datetime import date

import pytest

from gr_autopilot.curate import shelf_suggestions
from gr_autopilot.insights.metrics import BookFact
from gr_autopilot.queue import (
    QueueEntry,
    build_queue,
    plan_rows,
    render_html,
    render_plan,
)


def _book(
    conn: sqlite3.Connection,
    book_id: int,
    *,
    shelf: str = "read",
    rating: int = 0,
    date_read: str | None = None,
    date_added: str | None = None,
    review: str | None = None,
    source: str = "csv",
) -> None:
    conn.execute(
        "INSERT INTO books (book_id, title, author, my_rating, exclusive_shelf, date_read,"
        " date_added) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (book_id, f"T{book_id}", f"A{book_id}", rating, shelf, date_read, date_added),
    )
    conn.execute(
        "INSERT INTO reviews (book_id, review_text, source) VALUES (?, ?, ?)",
        (book_id, review, source),
    )


TODAY = date(2026, 8, 27)


@pytest.fixture
def library(conn: sqlite3.Connection) -> sqlite3.Connection:
    _book(conn, 1, rating=5, date_read="2024/03/01", review="mine")  # done: never queued
    _book(conn, 2, rating=0, date_read="2024/02/01", review="mine")  # own review, unrated
    _book(conn, 3, rating=0, date_read="2024/05/01")  # needs both
    _book(conn, 4, rating=4, date_read="2024/04/01")  # needs review
    _book(conn, 5, rating=4, date_read=None, review="ai", source="claude")  # ai review, done
    _book(conn, 6, rating=3, date_read=None)  # undated read, needs review, sorts last
    _book(conn, 7, shelf="currently-reading", date_added="2024/01/01")  # stale
    _book(conn, 8, shelf="currently-reading", date_added="2026/08/20")  # fresh: excluded
    _book(conn, 9, shelf="to-read", date_added="2020/01/01")  # never queued
    conn.commit()
    return conn


def test_queue_orders_read_books_by_date_read_then_stale(library: sqlite3.Connection) -> None:
    q = build_queue(library, today=TODAY)
    assert [(e.book_id, sorted(e.needs)) for e in q] == [
        (3, ["rating", "review"]),
        (4, ["review"]),
        (2, ["rating"]),
        (6, ["review"]),
        (7, ["stale"]),
    ]


def test_rated_and_reviewed_book_never_appears(library: sqlite3.Connection) -> None:
    ids = {e.book_id for e in build_queue(library, today=TODAY)}
    assert 1 not in ids  # own review + rating
    assert 5 not in ids  # ai review + rating


def test_own_review_is_never_review_needed(library: sqlite3.Connection) -> None:
    """Invariant 2: a human review is never a target, whatever else the book lacks."""
    by_id = {e.book_id: e for e in build_queue(library, today=TODAY)}
    assert by_id[2].needs == frozenset({"rating"})


def test_unrated_books_are_never_review_targets_for_posting(library: sqlite3.Connection) -> None:
    """Invariant 3: needs=review on an unrated book only means 'after the user rates it'."""
    by_id = {e.book_id: e for e in build_queue(library, today=TODAY)}
    assert by_id[3].rating is None


def test_stale_days_is_configurable(library: sqlite3.Connection) -> None:
    ids = {e.book_id for e in build_queue(library, today=TODAY, stale_days=10_000)}
    assert 7 not in ids


def _entry(book_id: int, needs: set[str], rating: int | None = None) -> QueueEntry:
    return QueueEntry(
        book_id=book_id,
        title=f"T{book_id}",
        author="A",
        shelf="read",
        rating=rating,
        date_read=None,
        needs=frozenset(needs),
    )


def test_plan_rows_leave_ratings_blank_and_add_taxonomy_shelves() -> None:
    entries = [_entry(3, {"rating", "review"}), _entry(4, {"review"}, 4)]
    rows = plan_rows(entries, [(4, "classics"), (3, "classics"), (99, "classics")])
    assert rows == [
        ["set_rating", "3", "", "T3 — A"],
        ["set_shelf", "3", "classics", "T3 — A"],
        ["set_shelf", "4", "classics", "T4 — A"],
    ]


@pytest.mark.parametrize("shelf", ["read", "to-read", "currently-reading"])
def test_plan_never_emits_exclusive_shelf(shelf: str) -> None:
    rows = plan_rows([_entry(4, {"review"}, 4)], [(4, shelf), (4, "classics")])
    assert rows == [["set_shelf", "4", "classics", "T4 — A"]]


def test_plan_never_invents_a_rating() -> None:
    rows = plan_rows([_entry(3, {"rating"}), _entry(6, {"rating", "review"})], [])
    assert all(r[2] == "" for r in rows if r[0] == "set_rating")


def test_render_plan_round_trips_through_gr_apply_parser() -> None:
    from gr_autopilot.actions.plan import is_unfilled, parse_plan

    rows = [["set_rating", "3", "", "T3 — A"], ["set_shelf", "4", "classics", "T4 — A"]]
    text, line_numbers = render_plan(rows)
    items = parse_plan(text)
    assert [(i.action, i.book_id, i.value) for i in items] == [
        ("set_rating", 3, ""),
        ("set_shelf", 4, "classics"),
    ]
    assert is_unfilled(items[0])
    # line numbers are 1-based and point at the row a person would edit
    lines = text.splitlines()
    assert lines[line_numbers[3] - 1].startswith("set_rating,3,")
    assert lines[line_numbers[4] - 1].startswith("set_shelf,4,")


def test_render_html_links_rating_rows_to_plan_lines() -> None:
    entries = [_entry(3, {"rating", "review"}), _entry(4, {"review"}, 4)]
    html = render_html(entries, {3: 9})
    assert "<!doctype html>" in html.lower()
    assert "T3" in html and "T4" in html
    assert "write-plan.csv:9" in html
    assert "★★★★" in html or "4★" in html


def test_shelf_suggestions_only_existing_taxonomy_shelves_not_yet_on_book() -> None:
    facts = [
        BookFact(1, exclusive_shelf="read", original_pub_year=1850, shelves=("classics",)),
        BookFact(2, exclusive_shelf="read", original_pub_year=1850),
        BookFact(3, exclusive_shelf="read", original_pub_year=1950),
        BookFact(4, exclusive_shelf="read", author="Franz Kafka", original_pub_year=1915),
        BookFact(5, exclusive_shelf="to-read", original_pub_year=1850),
    ]
    existing = {"classics", "existential-classics", "read", "to-read"}
    got = shelf_suggestions(facts, existing)
    assert got == [(2, "classics"), (4, "existential-classics")]
