"""Which approved review drafts may be posted. Pure selection; the CLI does the writing.

Scoped by the invariants: only rated read books (a rating is never invented), only
where the account holds no review text (a human review is never edited or replaced),
only drafts the user flipped to `status: approved`, and never the same text twice
(`actions_log` idempotency). Both live backends still raise NotImplementedError for
reviews; until the flow is captured `gr post-reviews --apply` reports BLOCKED_MESSAGE.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from gr_autopilot.actions.core import payload_hash
from gr_autopilot.drafts.format import parse_draft, review_text
from gr_autopilot.store.repository import already_done

BLOCKED_MESSAGE = (
    "blocked: capture the review flow "
    "(docs/superpowers/research/write-flows-capture-runbook.md step 2)"
)


@dataclass(frozen=True)
class Postable:
    book_id: int
    title: str
    text: str
    rating: int


def _approved_drafts(drafts_dir: Path) -> dict[int, str]:
    if not drafts_dir.is_dir():
        return {}
    out: dict[int, str] = {}
    for path in sorted(drafts_dir.glob("*.md")):
        meta, body = parse_draft(path.read_text(encoding="utf-8"))
        text = review_text(body)
        if meta.status == "approved" and text:
            out[meta.book_id] = text
    return out


def select_postable(conn: sqlite3.Connection, drafts_dir: Path, per_run: int) -> list[Postable]:
    """Rated read books with an approved draft, an empty account review, not yet posted."""
    drafts = _approved_drafts(drafts_dir)
    out: list[Postable] = []
    for row in conn.execute(
        """
        SELECT b.book_id, b.title, b.my_rating FROM books b
        LEFT JOIN reviews r ON r.book_id = b.book_id
        WHERE b.exclusive_shelf = 'read' AND b.my_rating > 0
          AND COALESCE(r.is_empty, 1) = 1
        ORDER BY b.date_read DESC, b.book_id
        """
    ):
        book_id = int(row["book_id"])
        text = drafts.get(book_id)
        if text is None:
            continue
        rating = int(row["my_rating"])
        h = payload_hash("post_review", {"text": text, "rating": rating})
        if already_done(conn, book_id, "post_review", h):
            continue
        out.append(Postable(book_id, str(row["title"] or ""), text, rating))
        if len(out) >= per_run:
            break
    return out
