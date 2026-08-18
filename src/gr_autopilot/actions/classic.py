from __future__ import annotations

# Goodreads' classic Rails write endpoints (captured live 2026-08-17 against a
# real session; see docs/superpowers/research/bulk-shelving-runbook.md). Unlike
# the AppSync path these need no JWT, no GID, and no stealth: an authenticated
# session cookie plus the page's CSRF meta token is sufficient. Verified at
# volume — 140 add_to_shelf and 8 user_shelves POSTs, all 200, all confirmed
# by shelf-count reload.
#
# Semantics of add_to_shelf: an exclusive shelf name (to-read/currently-reading/
# read) RE-SHELVES the book; a custom shelf name ADDS a tagging and leaves the
# exclusive shelf alone.
#
# Failure mode worth knowing: under rate limiting Goodreads answers HTTP 202
# with an empty body instead of an error status. Transports must treat any
# non-200 as failure, never as success.

ADD_TO_SHELF_URL = "https://www.goodreads.com/shelf/add_to_shelf"
CREATE_SHELF_URL = "https://www.goodreads.com/user_shelves"


def build_add_to_shelf_form(book_id: int, shelf: str, csrf_token: str) -> dict[str, str]:
    """Form body to add a book to a shelf (numeric legacy book id, not GID)."""
    return {"name": shelf, "book_id": str(int(book_id)), "authenticity_token": csrf_token}


def build_create_shelf_form(name: str, csrf_token: str) -> dict[str, str]:
    """Form body to create a custom (non-exclusive) shelf. Idempotent-safe: 200 either way."""
    return {"user_shelf[name]": name, "authenticity_token": csrf_token}


def build_remove_from_shelf_form(book_id: int, shelf: str, csrf_token: str) -> dict[str, str]:
    """Form body to remove a book from a shelf (same endpoint as add, plus a=remove).

    Captured live 2026-08-18 (4 removals, each confirmed by shelf-count reload).
    CAUTION: removing from the book's EXCLUSIVE shelf (to-read/currently-reading/
    read) deletes the whole review row — the book leaves the library, taking any
    rating/review/date with it. Removing a custom-shelf tagging is harmless.
    """
    return {
        "name": shelf,
        "book_id": str(int(book_id)),
        "a": "remove",
        "authenticity_token": csrf_token,
    }
