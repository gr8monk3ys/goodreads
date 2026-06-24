"""Parse a write-plan CSV into typed items. The allow-list is a safety boundary.

Only ratings, dates, and shelf operations are permitted. Review posting and any social
action (follow/like/comment) are deliberately NOT applyable here — reviews stay human-edited
and posted by hand, and social actions are never automated. An unknown action is a hard error.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

# Deliberately excludes post_review (human-in-the-loop) and any follow/like/comment action.
ALLOWED_ACTIONS = frozenset({"ensure_shelf", "set_shelf", "set_rating", "set_date"})

_HEADER = ("action", "book_id", "value")


_NEEDS_VALUE = frozenset({"set_rating", "set_date"})


@dataclass(frozen=True)
class PlanItem:
    action: str
    book_id: int | None  # None for shelf-level actions (ensure_shelf)
    value: str


def is_unfilled(item: PlanItem) -> bool:
    """True for a rating/date row the user hasn't filled in yet — skip, don't apply."""
    return item.action in _NEEDS_VALUE and not item.value.strip()


def parse_plan(text: str) -> list[PlanItem]:
    items: list[PlanItem] = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
            continue
        cells = [c.strip() for c in row]
        if tuple(cells[:3]) == _HEADER:
            continue
        action = cells[0]
        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"action {action!r} is not allowed by gr apply "
                f"(permitted: {', '.join(sorted(ALLOWED_ACTIONS))}; reviews/social are manual)"
            )
        book_id = int(cells[1]) if len(cells) > 1 and cells[1] else None
        value = cells[2] if len(cells) > 2 else ""
        items.append(PlanItem(action=action, book_id=book_id, value=value))
    return items
