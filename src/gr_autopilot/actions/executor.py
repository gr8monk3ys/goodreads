from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from gr_autopilot.actions.core import (
    ActionResult,
    GoodreadsBackend,
    Throttle,
    payload_hash,
)
from gr_autopilot.config import Settings
from gr_autopilot.store.repository import already_done, record_action


class ActionExecutor:
    """Wraps a backend with the kill switch, idempotency guard, throttle, and audit log.

    Every write goes through `_guarded`: check kill switch -> check idempotency ->
    throttle -> (dry-run? log only : perform) -> record to actions_log.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        backend: GoodreadsBackend,
        *,
        run_id: int,
        settings: Settings,
        throttle: Throttle,
        dry_run: bool,
        stop_file: Path | None = None,
    ) -> None:
        self._conn = conn
        self._backend = backend
        self._run_id = run_id
        self._settings = settings
        self._throttle = throttle
        self._dry_run = dry_run
        self._stop_file = stop_file if stop_file is not None else Path("data/STOP")

    def _kill_switch_engaged(self) -> bool:
        return self._settings.disable_writes or self._stop_file.exists()

    def _guarded(
        self,
        action_type: str,
        book_id: int | None,
        payload: dict[str, object],
        op: Callable[[GoodreadsBackend], None],
    ) -> ActionResult:
        h = payload_hash(action_type, payload)
        if self._kill_switch_engaged():
            record_action(
                self._conn,
                self._run_id,
                book_id,
                action_type,
                h,
                "failed",
                dry_run=self._dry_run,
                detail="kill switch engaged",
            )
            return ActionResult(action_type, book_id, "failed", "kill switch engaged")
        if already_done(self._conn, book_id, action_type, h):
            record_action(
                self._conn,
                self._run_id,
                book_id,
                action_type,
                h,
                "skipped_idempotent",
                dry_run=self._dry_run,
            )
            return ActionResult(action_type, book_id, "skipped_idempotent")
        self._throttle.wait()
        if self._dry_run:
            record_action(
                self._conn, self._run_id, book_id, action_type, h, "dry_run", dry_run=True
            )
            return ActionResult(action_type, book_id, "dry_run")
        try:
            op(self._backend)
        except Exception as exc:  # noqa: BLE001 - record any backend failure, continue the run
            record_action(
                self._conn,
                self._run_id,
                book_id,
                action_type,
                h,
                "failed",
                dry_run=False,
                detail=str(exc),
            )
            return ActionResult(action_type, book_id, "failed", str(exc))
        record_action(self._conn, self._run_id, book_id, action_type, h, "done", dry_run=False)
        return ActionResult(action_type, book_id, "done")

    def post_review(self, book_id: int, text: str, rating: int) -> ActionResult:
        return self._guarded(
            "post_review",
            book_id,
            {"text": text, "rating": rating},
            lambda b: b.post_review(book_id, text, rating),
        )

    def set_shelf(self, book_id: int, shelf: str) -> ActionResult:
        return self._guarded(
            "set_shelf", book_id, {"shelf": shelf}, lambda b: b.set_shelf(book_id, shelf)
        )

    def want_to_read(self, book_id: int) -> ActionResult:
        return self.set_shelf(book_id, "to-read")

    def ensure_shelf(self, name: str, *, exclusive: bool = False) -> ActionResult:
        return self._guarded(
            "ensure_shelf",
            None,
            {"name": name, "exclusive": exclusive},
            lambda b: b.ensure_shelf(name, exclusive=exclusive),
        )

    def add_to_list(self, list_id: str, book_id: int) -> ActionResult:
        return self._guarded(
            "add_to_list",
            book_id,
            {"list_id": list_id},
            lambda b: b.add_to_list(list_id, book_id),
        )
