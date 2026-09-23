import http.client

from gr_autopilot.catalog import goodreads_public
from gr_autopilot.catalog.goodreads_public import GoodreadsPublicCatalog


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_incomplete_read_is_retried_once(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise http.client.IncompleteRead(b"partial")
        return _Resp(b"<html>no next data</html>")

    monkeypatch.setattr(goodreads_public.urllib.request, "urlopen", fake_urlopen)
    # The second attempt succeeds at the HTTP level; the page has no
    # __NEXT_DATA__, so the parser's ValueError maps to None -- not a crash.
    assert GoodreadsPublicCatalog().get_meta(1) is None
    assert len(calls) == 2


def test_repeated_incomplete_read_skips_the_book_instead_of_raising(monkeypatch):
    def fake_urlopen(request, timeout):
        raise http.client.IncompleteRead(b"")

    monkeypatch.setattr(goodreads_public.urllib.request, "urlopen", fake_urlopen)
    assert GoodreadsPublicCatalog().get_meta(1) is None
