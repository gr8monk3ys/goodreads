import sqlite3
from pathlib import Path

from gr_autopilot.actions.core import NullBackend, Throttle
from gr_autopilot.config import Settings
from gr_autopilot.generate.prompt import TargetBook
from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.orchestrator.run import review_unreviewed
from gr_autopilot.store.repository import upsert_books

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def _gen(book: TargetBook) -> str:
    return f"My review of {book.title}."


def _throttle() -> Throttle:
    return Throttle(sleeper=lambda _: None)


def test_review_unreviewed_dry_run(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    summary = review_unreviewed(
        conn,
        generate_text=_gen,
        backend=NullBackend(),
        settings=Settings(),
        dry_run=True,
        throttle=_throttle(),
    )
    assert summary.planned == 1  # only book 22 (rated read, empty review)
    assert summary.done == 0
    assert summary.dry_run is True
    n = conn.execute("SELECT COUNT(*) FROM actions_log WHERE status='dry_run'").fetchone()[0]
    assert n == 1


def test_review_unreviewed_live_with_null_backend(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    summary = review_unreviewed(
        conn,
        generate_text=_gen,
        backend=NullBackend(),
        settings=Settings(),
        dry_run=False,
        throttle=_throttle(),
    )
    assert summary.planned == 1
    assert summary.done == 1
    assert summary.failed == 0


def test_limit_caps_actions(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    summary = review_unreviewed(
        conn,
        generate_text=_gen,
        backend=NullBackend(),
        settings=Settings(),
        dry_run=True,
        throttle=_throttle(),
        limit=0,
    )
    assert summary.planned == 0
