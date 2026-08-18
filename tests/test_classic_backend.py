from typing import Any

import pytest

from gr_autopilot.actions.classic import (
    ADD_TO_SHELF_URL,
    CREATE_SHELF_URL,
    build_add_to_shelf_form,
    build_create_shelf_form,
    build_remove_from_shelf_form,
)
from gr_autopilot.actions.classic_backend import ClassicRailsBackend


def test_add_to_shelf_form_is_the_captured_contract() -> None:
    form = build_add_to_shelf_form(book_id=394535, shelf="to-read", csrf_token="tok")  # noqa: S106
    assert form == {"name": "to-read", "book_id": "394535", "authenticity_token": "tok"}
    assert ADD_TO_SHELF_URL == "https://www.goodreads.com/shelf/add_to_shelf"


def test_create_shelf_form_is_the_captured_contract() -> None:
    form = build_create_shelf_form(name="russian-lit", csrf_token="tok")  # noqa: S106
    assert form == {"user_shelf[name]": "russian-lit", "authenticity_token": "tok"}
    assert CREATE_SHELF_URL == "https://www.goodreads.com/user_shelves"


def test_remove_from_shelf_form_is_the_captured_contract() -> None:
    # Same endpoint as add, plus a=remove. Verified live 2026-08-17 (4 removals,
    # each confirmed by shelf-count reload).
    form = build_remove_from_shelf_form(book_id=18788, shelf="to-read", csrf_token="tok")  # noqa: S106
    assert form == {
        "name": "to-read",
        "book_id": "18788",
        "a": "remove",
        "authenticity_token": "tok",
    }


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status
        self.ok = 200 <= status < 300


class _FakePage:
    """Just enough of a Playwright Page: csrf meta + a recording request.post."""

    def __init__(self, status: int = 200) -> None:
        self._status = status
        self.posts: list[dict[str, Any]] = []

    def eval_on_selector(self, selector: str, expr: str) -> str:
        assert selector == 'meta[name="csrf-token"]'
        return "csrf-abc"

    @property
    def request(self) -> "_FakePage":
        return self

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.posts.append({"url": url, **kwargs})
        return _FakeResponse(self._status)


def test_set_shelf_posts_the_form_with_csrf_headers() -> None:
    page = _FakePage()
    ClassicRailsBackend(page).set_shelf(394535, "russian-lit")
    (call,) = page.posts
    assert call["url"] == ADD_TO_SHELF_URL
    assert call["form"] == {
        "name": "russian-lit",
        "book_id": "394535",
        "authenticity_token": "csrf-abc",
    }
    assert call["headers"]["X-CSRF-Token"] == "csrf-abc"
    assert call["headers"]["X-Requested-With"] == "XMLHttpRequest"


def test_set_shelf_raises_on_non_200() -> None:
    # Goodreads throttles with HTTP 202 + empty body; that must not read as success.
    page = _FakePage(status=202)
    with pytest.raises(RuntimeError, match="202"):
        ClassicRailsBackend(page).set_shelf(1, "to-read")


def test_backend_remove_from_shelf_posts_a_remove() -> None:
    page = _FakePage()
    ClassicRailsBackend(page).remove_from_shelf(18788, "to-read")
    (call,) = page.posts
    assert call["url"] == ADD_TO_SHELF_URL
    assert call["form"]["a"] == "remove"
    assert call["form"]["book_id"] == "18788"


def test_ensure_shelf_creates_custom_shelf() -> None:
    page = _FakePage()
    ClassicRailsBackend(page).ensure_shelf("japanese-lit", exclusive=False)
    (call,) = page.posts
    assert call["url"] == CREATE_SHELF_URL
    assert call["form"] == {"user_shelf[name]": "japanese-lit", "authenticity_token": "csrf-abc"}


def test_ensure_shelf_refuses_exclusive() -> None:
    # The captured endpoint only creates ordinary custom shelves.
    page = _FakePage()
    with pytest.raises(ValueError, match="exclusive"):
        ClassicRailsBackend(page).ensure_shelf("read-2026", exclusive=True)
    assert page.posts == []  # refused before any network write


def test_uncaptured_operations_still_raise() -> None:
    backend = ClassicRailsBackend(_FakePage())
    with pytest.raises(NotImplementedError):
        backend.post_review(1, "text", 5)
    with pytest.raises(NotImplementedError):
        backend.set_date(1, "2026/08/17")
    with pytest.raises(NotImplementedError):
        backend.add_to_list("42", 1)
