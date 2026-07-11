import sqlite3
from pathlib import Path

from gr_autopilot.actions.core import GoodreadsBackend, Throttle, payload_hash
from gr_autopilot.actions.executor import ActionExecutor
from gr_autopilot.config import Settings
from gr_autopilot.store.repository import start_run


class RecordingBackend:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._fail = fail

    def post_review(self, book_id: int, text: str, rating: int) -> None:
        if self._fail:
            raise RuntimeError("boom")
        self.calls.append(("post_review", (book_id, text, rating)))

    def set_shelf(self, book_id: int, shelf: str) -> None:
        self.calls.append(("set_shelf", (book_id, shelf)))

    def set_rating(self, book_id: int, rating: int) -> None:
        self.calls.append(("set_rating", (book_id, rating)))

    def set_date(self, book_id: int, date_read: str) -> None:
        self.calls.append(("set_date", (book_id, date_read)))

    def ensure_shelf(self, name: str, *, exclusive: bool) -> None:
        self.calls.append(("ensure_shelf", (name, exclusive)))

    def add_to_list(self, list_id: str, book_id: int) -> None:
        self.calls.append(("add_to_list", (list_id, book_id)))


def _executor(
    conn: sqlite3.Connection,
    backend: GoodreadsBackend,
    *,
    dry_run: bool,
    settings: Settings | None = None,
    stop_file: Path | None = None,
) -> ActionExecutor:
    return ActionExecutor(
        conn,
        backend,
        run_id=start_run(conn, "test"),
        settings=settings or Settings(),
        throttle=Throttle(sleeper=lambda _: None),
        dry_run=dry_run,
        stop_file=stop_file or Path("/nonexistent/STOP"),
    )


def test_payload_hash_is_stable_and_distinct() -> None:
    a = payload_hash("post_review", {"text": "x", "rating": 5})
    b = payload_hash("post_review", {"rating": 5, "text": "x"})  # key order independent
    c = payload_hash("post_review", {"text": "y", "rating": 5})
    assert a == b
    assert a != c


def test_dry_run_does_not_call_backend(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    res = _executor(conn, backend, dry_run=True).post_review(11, "great book", 5)
    assert res.status == "dry_run"
    assert backend.calls == []
    n = conn.execute(
        "SELECT COUNT(*) FROM actions_log WHERE status='dry_run'"
    ).fetchone()[0]
    assert n == 1


def test_live_calls_backend_and_logs_done(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    res = _executor(conn, backend, dry_run=False).post_review(11, "great book", 5)
    assert res.status == "done"
    assert backend.calls[0][0] == "post_review"


def test_idempotent_skip_after_done(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    ex = _executor(conn, backend, dry_run=False)
    ex.post_review(11, "great book", 5)
    res2 = ex.post_review(11, "great book", 5)
    assert res2.status == "skipped_idempotent"
    assert len(backend.calls) == 1  # not performed twice


def test_kill_switch_env_blocks_write(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    ex = _executor(conn, backend, dry_run=False, settings=Settings(disable_writes=True))
    res = ex.post_review(11, "great book", 5)
    assert res.status == "failed"
    assert "kill switch" in res.detail
    assert backend.calls == []


def test_kill_switch_stop_file_blocks_write(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    stop = tmp_path / "STOP"
    stop.write_text("stop")
    backend = RecordingBackend()
    res = _executor(conn, backend, dry_run=False, stop_file=stop).post_review(
        11, "x", 5
    )
    assert res.status == "failed"
    assert backend.calls == []


def test_failed_backend_logs_failed(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend(fail=True)
    res = _executor(conn, backend, dry_run=False).post_review(11, "great book", 5)
    assert res.status == "failed"
    assert "boom" in res.detail


def test_set_rating_live_calls_backend(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    res = _executor(conn, backend, dry_run=False).set_rating(11, 5)
    assert res.status == "done"
    assert backend.calls[0] == ("set_rating", (11, 5))


def test_set_rating_dry_run_does_not_write(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    res = _executor(conn, backend, dry_run=True).set_rating(11, 5)
    assert res.status == "dry_run"
    assert backend.calls == []


def test_set_rating_is_idempotent(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    ex = _executor(conn, backend, dry_run=False)
    ex.set_rating(11, 5)
    res2 = ex.set_rating(11, 5)
    assert res2.status == "skipped_idempotent"
    assert len(backend.calls) == 1


def test_set_date_live_calls_backend(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    res = _executor(conn, backend, dry_run=False).set_date(11, "2024/03/01")
    assert res.status == "done"
    assert backend.calls[0] == ("set_date", (11, "2024/03/01"))


def test_set_date_kill_switch_blocks(conn: sqlite3.Connection) -> None:
    backend = RecordingBackend()
    ex = _executor(conn, backend, dry_run=False, settings=Settings(disable_writes=True))
    res = ex.set_date(11, "2024/03/01")
    assert res.status == "failed"
    assert backend.calls == []
