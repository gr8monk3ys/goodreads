from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ActionResult:
    action_type: str
    book_id: int | None
    status: str  # dry_run | done | failed | skipped_idempotent
    detail: str = ""


def payload_hash(action_type: str, payload: dict[str, object]) -> str:
    """Stable hash of an action + its payload — the idempotency key."""
    blob = json.dumps({"action_type": action_type, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Throttle:
    """Human-like randomized delay between actions. Sleeper/rng are injectable for tests."""

    def __init__(
        self,
        min_seconds: float = 8.0,
        max_seconds: float = 25.0,
        sleeper: Callable[[float], None] | None = None,
        rng: Callable[[float, float], float] | None = None,
    ) -> None:
        self._min = min_seconds
        self._max = max_seconds
        self._sleeper = sleeper or time.sleep
        self._rng = rng or random.uniform  # noqa: S311  # nosec - jitter, not security

    def wait(self) -> None:
        self._sleeper(self._rng(self._min, self._max))


class GoodreadsBackend(Protocol):
    """Low-level write operations against Goodreads. Implementations actually touch the site."""

    def post_review(self, book_id: int, text: str, rating: int) -> None: ...

    def set_shelf(self, book_id: int, shelf: str) -> None: ...

    def ensure_shelf(self, name: str, *, exclusive: bool) -> None: ...

    def add_to_list(self, list_id: str, book_id: int) -> None: ...


class NullBackend:
    """No-op backend (no network writes) — the default for dry runs."""

    def post_review(self, book_id: int, text: str, rating: int) -> None:
        return None

    def set_shelf(self, book_id: int, shelf: str) -> None:
        return None

    def ensure_shelf(self, name: str, *, exclusive: bool) -> None:
        return None

    def add_to_list(self, list_id: str, book_id: int) -> None:
        return None
