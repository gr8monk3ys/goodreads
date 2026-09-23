import http.client
import urllib.request
from typing import Any

import pytest

from gr_autopilot.catalog.goodreads_public import GoodreadsPublicCatalog


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_incomplete_read_is_retried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake_urlopen(request: Any, timeout: float) -> _Resp:
        calls.append(request)
        if len(calls) == 1:
            raise http.client.IncompleteRead(b"partial")
        return _Resp(b"<html>no next data</html>")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    # The second attempt succeeds at the HTTP level; the page has no
    # __NEXT_DATA__, so the parser's ValueError maps to None -- not a crash.
    assert GoodreadsPublicCatalog().get_meta(1) is None
    assert len(calls) == 2


def test_repeated_incomplete_read_skips_the_book_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> _Resp:
        raise http.client.IncompleteRead(b"")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert GoodreadsPublicCatalog().get_meta(1) is None
