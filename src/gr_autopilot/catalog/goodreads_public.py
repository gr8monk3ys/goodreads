from __future__ import annotations

import http.client
import urllib.request

from gr_autopilot.catalog.parse import extract_next_data, parse_book_meta
from gr_autopilot.catalog.protocols import BookMeta

# Read-only public catalog. No login, no cookies, public data only — the
# goodreads-mcp technique (github.com/shreeyachand/goodreads-mcp): fetch the
# public book page and read its embedded __NEXT_DATA__ JSON. Live HTTP, so this
# adapter is integration-only (omitted from unit coverage); the parser it calls
# IS unit-tested against the verified structure.

_BASE = "https://www.goodreads.com/book/show/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class GoodreadsPublicCatalog:
    """Fetches public book metadata (genres) from goodreads.com without authentication."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def get_meta(self, book_id: int) -> BookMeta | None:
        url = f"{_BASE}{int(book_id)}"
        request = urllib.request.Request(url, headers={"User-Agent": _UA})
        # One retry: a truncated chunked body (http.client.IncompleteRead) is
        # usually transient. It is an HTTPException, NOT an OSError, so it used
        # to escape this method and kill the whole `gr enrich` run (launchd
        # exit 1 on 2026-09-22) instead of skipping one book.
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as resp:  # nosec B310 - fixed https host
                    html = resp.read().decode("utf-8", "replace")
                return parse_book_meta(extract_next_data(html))
            except http.client.HTTPException:
                if attempt == 0:
                    continue
                return None
            except (ValueError, OSError):
                return None
        return None
