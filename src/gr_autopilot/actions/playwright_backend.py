from __future__ import annotations

from typing import Any

# Real Goodreads write backend driving the authenticated Playwright page.
#
# SELECTORS AND ENDPOINTS ARE PROVISIONAL. There is no Goodreads API, and the
# exact 2026 DOM selectors / request contracts cannot be known without an
# authenticated session. Capture them live (see
# docs/superpowers/research/write-flows-capture-runbook.md) and fill in the
# methods below BEFORE using this backend for real writes. Until then each
# method raises, so only NullBackend (dry-run) is usable.


class PlaywrightBackend:
    """Drives writes through a logged-in Playwright page. Pending live selector capture."""

    def __init__(self, page: Any) -> None:  # playwright Page
        self._page = page

    def _csrf_token(self) -> str:
        # CSRF token lives in <meta name="csrf-token"> and must be re-read per page load.
        return str(self._page.eval_on_selector('meta[name="csrf-token"]', "el => el.content"))

    def post_review(self, book_id: int, text: str, rating: int) -> None:
        raise NotImplementedError("post_review: capture the review-editor flow first")

    def set_shelf(self, book_id: int, shelf: str) -> None:
        raise NotImplementedError("set_shelf: confirm /shelf/add_to_shelf.json 2026 contract first")

    def ensure_shelf(self, name: str, *, exclusive: bool) -> None:
        raise NotImplementedError("ensure_shelf: capture the create-shelf control first")

    def add_to_list(self, list_id: str, book_id: int) -> None:
        raise NotImplementedError("add_to_list: capture the Listopia add flow first")
