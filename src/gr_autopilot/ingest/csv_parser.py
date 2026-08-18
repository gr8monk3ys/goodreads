from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path

_ISBN_RE = re.compile(r'^="?(.*?)"?$')  # matches the ="..." spreadsheet-formula wrapper
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def clean_isbn(raw: str | None) -> str | None:
    """Strip Goodreads' ="..." spreadsheet-formula ISBN wrapper; '' -> None."""
    s = (raw or "").strip()
    m = _ISBN_RE.match(s)
    value = (m.group(1) if m else s).strip()
    return value or None


def norm_review(raw: str | None) -> str:
    """Normalize a 'My Review' HTML cell to plain text. <br/> -> newline; tags stripped."""
    text = _BR_RE.sub("\n", raw or "")
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def coerce_int(raw: str | None) -> int | None:
    """Tolerant int from a Goodreads cell. '', None, or non-numeric -> None; floats truncate."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


@dataclass(frozen=True)
class BookRecord:
    book_id: int
    title: str
    author: str
    isbn: str | None
    isbn13: str | None
    my_rating: int
    avg_rating: float | None
    exclusive_shelf: str
    date_read: str | None
    date_added: str | None
    review_html: str
    review_text: str
    has_spoiler: bool
    shelves: tuple[str, ...]
    num_pages: int | None
    original_pub_year: int | None


def _row_to_record(row: dict[str, str]) -> BookRecord:
    review_html = row.get("My Review") or ""
    shelves = tuple(s.strip() for s in (row.get("Bookshelves") or "").split(",") if s.strip())
    avg = row.get("Average Rating") or ""
    return BookRecord(
        book_id=int(row["Book Id"]),
        title=(row.get("Title") or "").strip(),
        author=(row.get("Author") or "").strip(),
        isbn=clean_isbn(row.get("ISBN")),
        isbn13=clean_isbn(row.get("ISBN13")),
        # Not int(): the 2026 export emits nonzero ratings as "4.0".
        my_rating=coerce_int(row.get("My Rating")) or 0,
        avg_rating=float(avg) if avg else None,
        exclusive_shelf=(row.get("Exclusive Shelf") or "").strip(),
        date_read=((row.get("Date Read") or "").strip() or None),
        date_added=((row.get("Date Added") or "").strip() or None),
        review_html=review_html,
        review_text=norm_review(review_html),
        has_spoiler=(row.get("Spoiler") or "").strip().lower() == "true",
        shelves=shelves,
        num_pages=coerce_int(row.get("Number of Pages")),
        original_pub_year=(
            coerce_int(row.get("Original Publication Year"))
            or coerce_int(row.get("Year Published"))
        ),
    )


def parse_export(path: Path) -> list[BookRecord]:
    """Parse a goodreads_library_export.csv into BookRecords (header-name access)."""
    with open(path, encoding="utf-8", newline="") as f:
        return [_row_to_record(row) for row in csv.DictReader(f)]
