import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gr_autopilot import cli
from gr_autopilot.actions.core import GoodreadsBackend, NullBackend, Throttle, probe_post_review
from gr_autopilot.actions.graphql_backend import GoodreadsGraphQLBackend
from gr_autopilot.drafts.format import DraftMeta
from gr_autopilot.drafts.studio import write_draft
from gr_autopilot.postreviews import BLOCKED_MESSAGE, select_postable
from gr_autopilot.store.db import connect, init_db
from gr_autopilot.store.repository import record_action, start_run

runner = CliRunner()


def _book(
    conn: sqlite3.Connection,
    book_id: int,
    *,
    shelf: str = "read",
    rating: int = 4,
    review: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO books (book_id, title, author, my_rating, exclusive_shelf)"
        " VALUES (?, ?, ?, ?, ?)",
        (book_id, f"T{book_id}", f"A{book_id}", rating, shelf),
    )
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (?, ?)", (book_id, review))
    conn.commit()


def _draft(drafts: Path, book_id: int, status: str = "approved", body: str = "nice") -> None:
    meta = DraftMeta(book_id=book_id, title=f"T{book_id}", author="A", my_rating=4, status=status)
    write_draft(drafts, meta, body)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sqlite3.Connection:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "data" / "x.db"))
    monkeypatch.setenv("GR_DRAFTS_DIR", str(tmp_path / "drafts"))
    (tmp_path / "data").mkdir()
    conn = connect(tmp_path / "data" / "x.db")
    init_db(conn)
    return conn


def test_select_postable_applies_every_exclusion(db: sqlite3.Connection, tmp_path: Path) -> None:
    drafts = tmp_path / "drafts"
    _book(db, 1)  # approved draft, rated, empty account review -> postable
    _draft(drafts, 1)
    _book(db, 2, review="my own words")  # invariant 2: own review, never touched
    _draft(drafts, 2)
    _book(db, 3, rating=0)  # invariant 3: unrated, never posted
    _draft(drafts, 3)
    _book(db, 4)  # still a draft, not approved
    _draft(drafts, 4, status="draft")
    _book(db, 5)  # no draft file at all
    _book(db, 6, shelf="currently-reading")
    _draft(drafts, 6)
    _book(db, 7)  # already posted this exact text (idempotency)
    _draft(drafts, 7, body="posted already")
    _book(db, 8)
    _draft(drafts, 8)
    from gr_autopilot.actions.core import payload_hash

    h = payload_hash("post_review", {"text": "posted already", "rating": 4})
    record_action(db, start_run(db, "live"), 7, "post_review", h, "done", dry_run=False)

    got = select_postable(db, drafts, per_run=5)
    assert [(p.book_id, p.text, p.rating) for p in got] == [(1, "nice", 4), (8, "nice", 4)]
    assert [p.book_id for p in select_postable(db, drafts, per_run=1)] == [1]


def test_probe_detects_uncaptured_review_flow() -> None:
    assert probe_post_review(NullBackend()) is True
    assert probe_post_review(GoodreadsGraphQLBackend(page=None)) is False


def test_dry_run_prints_table_and_writes_nothing(
    db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _book(db, 1)
    _draft(tmp_path / "drafts", 1)
    launched: list[str] = []
    monkeypatch.setattr(cli, "_probe_backend", lambda: launched.append("probe"))
    result = runner.invoke(cli.app, ["post-reviews"])
    assert result.exit_code == 0, result.output
    assert "T1" in result.output and "DRY RUN" in result.output
    assert launched == []
    assert db.execute("SELECT COUNT(*) FROM actions_log").fetchone()[0] == 0


def test_apply_is_blocked_before_any_browser_launch(
    db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _book(db, 1)
    _draft(tmp_path / "drafts", 1)

    def boom() -> Iterator[GoodreadsBackend]:
        raise AssertionError("browser must not launch when the flow is uncaptured")

    monkeypatch.setattr(cli, "_review_backend", contextmanager(boom))
    result = runner.invoke(cli.app, ["post-reviews", "--apply"])
    assert result.exit_code == 3, result.output
    assert BLOCKED_MESSAGE in result.output
    assert "write-flows-capture-runbook.md step 2" in BLOCKED_MESSAGE
    assert db.execute("SELECT COUNT(*) FROM actions_log").fetchone()[0] == 0


def test_apply_reports_blocked_even_with_nothing_to_post(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = runner.invoke(cli.app, ["post-reviews", "--apply"])
    assert result.exit_code == 3, result.output
    assert BLOCKED_MESSAGE in result.output


def test_apply_kill_switch_exits_zero_without_probing(
    db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _book(db, 1)
    _draft(tmp_path / "drafts", 1)
    (tmp_path / "data" / "STOP").write_text("stop")

    def boom() -> GoodreadsBackend:
        raise AssertionError("must not probe with the kill switch on")

    monkeypatch.setattr(cli, "_probe_backend", boom)
    result = runner.invoke(cli.app, ["post-reviews", "--apply"])
    assert result.exit_code == 0, result.output
    assert "kill switch on" in result.output


def test_apply_dispatches_through_executor_when_capable(
    db: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts = tmp_path / "drafts"
    for i in (1, 2, 3):
        _book(db, i)
        _draft(drafts, i)
    posted: list[tuple[int, str, int]] = []

    class Recording(NullBackend):
        def post_review(self, book_id: int, text: str, rating: int) -> None:
            posted.append((book_id, text, rating))

    @contextmanager
    def fake_backend() -> Iterator[GoodreadsBackend]:
        yield Recording()

    monkeypatch.setattr(cli, "_probe_backend", lambda: NullBackend())
    monkeypatch.setattr(cli, "_review_backend", fake_backend)
    monkeypatch.setattr(cli, "_live_throttle", lambda: Throttle(sleeper=lambda _: None))
    result = runner.invoke(cli.app, ["post-reviews", "--apply", "--per-run", "2"])
    assert result.exit_code == 0, result.output
    assert posted == [(1, "nice", 4), (2, "nice", 4)]
    assert "2 done" in result.output
    rows = db.execute(
        "SELECT book_id FROM actions_log WHERE action_type='post_review' AND status='done'"
    ).fetchall()
    assert [r[0] for r in rows] == [1, 2]
    # second run: the two are idempotent, only book 3 remains
    posted.clear()
    result = runner.invoke(cli.app, ["post-reviews", "--apply", "--per-run", "5"])
    assert result.exit_code == 0, result.output
    assert posted == [(3, "nice", 4)]
