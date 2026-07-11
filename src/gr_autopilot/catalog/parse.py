from __future__ import annotations

import json
import re

from gr_autopilot.catalog.protocols import BookMeta

# Goodreads book pages embed a Next.js __NEXT_DATA__ JSON blob whose Apollo cache
# holds the Book entry. Genres live INLINE under Book.bookGenres[].genre.name
# (verified live against goodreads.com/book/show/5907 -> Fantasy/Classics/Fiction).
# Technique credited to github.com/shreeyachand/goodreads-mcp.
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)


def extract_next_data(html: str) -> dict[str, object]:
    match = _NEXT_DATA_RE.search(html)
    if match is None:
        raise ValueError("no __NEXT_DATA__ script found in page")
    parsed: dict[str, object] = json.loads(match.group(1))
    return parsed


def _apollo_state(next_data: dict[str, object]) -> dict[str, object]:
    props = next_data.get("props", {})
    page_props = props.get("pageProps", {}) if isinstance(props, dict) else {}
    state = page_props.get("apolloState", {}) if isinstance(page_props, dict) else {}
    return state if isinstance(state, dict) else {}


def parse_book_meta(next_data: dict[str, object]) -> BookMeta:
    """Extract book_id (legacyId), title, and genres from a parsed __NEXT_DATA__ blob."""
    apollo = _apollo_state(next_data)
    book = next(
        (
            v
            for v in apollo.values()
            if isinstance(v, dict) and v.get("__typename") == "Book"
        ),
        None,
    )
    if book is None:
        raise ValueError("no Book entry in apolloState")

    genres: list[str] = []
    for entry in book.get("bookGenres", []) or []:
        if not isinstance(entry, dict):
            continue
        genre = entry.get("genre")
        if isinstance(genre, dict) and isinstance(genre.get("name"), str):
            genres.append(genre["name"])

    legacy_id = book.get("legacyId")
    return BookMeta(
        book_id=(
            int(legacy_id)
            if isinstance(legacy_id, int | str) and str(legacy_id).isdigit()
            else 0
        ),
        title=str(book.get("title") or ""),
        genres=tuple(genres),
    )
