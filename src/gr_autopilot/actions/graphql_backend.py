from __future__ import annotations

import json
from typing import Any

from gr_autopilot.actions.graphql import APPSYNC_URL, build_shelve_request, parse_gid, parse_jwt
from gr_autopilot.catalog.parse import extract_next_data

# Live write backend over Goodreads' AppSync GraphQL API. Requires a STEALTHED,
# authenticated Playwright page (plain headless is 403'd by AWS WAF — confirmed).
# Integration-only (omitted from unit coverage); the request-building + parsing it
# relies on are unit-tested in actions/graphql.py. Only shelf ops are implemented
# (verified contract); review/rating/list raise NotImplementedError pending capture.

_BOOK_URL = "https://www.goodreads.com/book/show/"


class GoodreadsGraphQLBackend:
    """Performs writes by scraping a fresh JWT+GID from the book page, then POSTing GraphQL."""

    def __init__(self, page: Any) -> None:  # a stealthed, storage_state-authenticated Page
        self._page = page

    def _jwt_and_gid(self, book_id: int) -> tuple[str, str]:
        self._page.goto(f"{_BOOK_URL}{int(book_id)}", wait_until="domcontentloaded")
        self._page.wait_for_timeout(3500)
        next_data = extract_next_data(self._page.content())
        jwt, gid = parse_jwt(next_data), parse_gid(next_data)
        if not jwt or not gid:
            raise RuntimeError(
                f"book {book_id}: missing jwt={bool(jwt)} gid={bool(gid)} (WAF/login?)"
            )
        return jwt, gid

    def _post(self, jwt: str, payload: dict[str, object]) -> dict[str, Any]:
        resp = self._page.request.post(
            APPSYNC_URL,
            headers={"authorization": jwt, "content-type": "application/json"},
            data=json.dumps(payload),
        )
        if not resp.ok:
            raise RuntimeError(f"AppSync POST {resp.status}")
        body: dict[str, Any] = resp.json()
        if body.get("errors"):
            raise RuntimeError(f"AppSync errors: {body['errors']}")
        return body

    def set_shelf(self, book_id: int, shelf: str) -> None:
        jwt, gid = self._jwt_and_gid(book_id)
        self._post(jwt, build_shelve_request(gid, shelf))

    def post_review(self, book_id: int, text: str, rating: int) -> None:
        raise NotImplementedError("review mutation not yet captured")

    def ensure_shelf(self, name: str, *, exclusive: bool) -> None:
        raise NotImplementedError("create-shelf mutation not yet captured")

    def add_to_list(self, list_id: str, book_id: int) -> None:
        raise NotImplementedError("listopia add mutation not yet captured")
