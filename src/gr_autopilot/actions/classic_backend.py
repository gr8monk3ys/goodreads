from __future__ import annotations

from typing import Any

from gr_autopilot.actions.classic import (
    ADD_TO_SHELF_URL,
    CREATE_SHELF_URL,
    build_add_to_shelf_form,
    build_create_shelf_form,
)

# Live write backend over the classic Rails endpoints (contracts in classic.py).
# Needs an authenticated Playwright page on any goodreads.com URL — the CSRF
# token is read from the page's <meta>, and page.request shares its cookies.
# Only shelf ops are captured; the rest raise until their contracts are.


class ClassicRailsBackend:
    """Shelf writes via form POSTs with the page session's cookies + CSRF token."""

    def __init__(self, page: Any) -> None:  # an authenticated playwright Page
        self._page = page

    def _csrf_token(self) -> str:
        # Lives in <meta name="csrf-token">; re-read per call so a page reload
        # mid-run can't leave us posting a stale token.
        return str(self._page.eval_on_selector('meta[name="csrf-token"]', "el => el.content"))

    def _post_form(self, url: str, form: dict[str, str], csrf_token: str) -> None:
        resp = self._page.request.post(
            url,
            form=form,
            headers={"X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": csrf_token},
        )
        # Rate limiting answers 202 + empty body, which is `ok` by HTTP's lights
        # but means the write was dropped — only a real 200 counts.
        if resp.status != 200:
            raise RuntimeError(f"classic POST {url} -> {resp.status} (200 required)")

    def set_shelf(self, book_id: int, shelf: str) -> None:
        token = self._csrf_token()
        self._post_form(ADD_TO_SHELF_URL, build_add_to_shelf_form(book_id, shelf, token), token)

    def ensure_shelf(self, name: str, *, exclusive: bool) -> None:
        if exclusive:
            raise ValueError("user_shelves only creates custom shelves, not exclusive ones")
        token = self._csrf_token()
        self._post_form(CREATE_SHELF_URL, build_create_shelf_form(name, token), token)

    def set_rating(self, book_id: int, rating: int) -> None:
        raise NotImplementedError("rating: use GoodreadsGraphQLBackend (RateBook is captured)")

    def set_date(self, book_id: int, date_read: str) -> None:
        raise NotImplementedError("date-read: classic editor contract not yet captured")

    def post_review(self, book_id: int, text: str, rating: int) -> None:
        raise NotImplementedError("review: classic editor contract not yet captured")

    def add_to_list(self, list_id: str, book_id: int) -> None:
        raise NotImplementedError("listopia: add flow not yet captured")
