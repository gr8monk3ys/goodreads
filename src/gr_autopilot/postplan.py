"""Pace a batch of finished drafts into a posting schedule that reads as human.

Goodreads records when a review was posted, not how long it took to write, so the only
observable a schedule can shape is the *gap between consecutive posts*. Each gap is the
time the user would plausibly have spent producing that specific review: typing it at
their own words-per-minute, plus an editing pass that runs longer for heavier pieces.
Posts are then grouped into sittings with a break between, because a few dozen reviews
landing back-to-back is itself a tell.

Deterministic by construction — variance comes from hashing the book id, never from a
clock or RNG — so an interrupted run replans identically and resumes where it stopped.
Pure: no I/O, no posting. Read-only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from gr_autopilot.drafts.format import DraftMeta, review_text

POSTED = "posted"


@dataclass(frozen=True)
class PostSlot:
    book_id: int
    title: str
    my_rating: int
    words: int
    # Compose+edit time to wait BEFORE posting this review.
    gap_minutes: float
    sitting: int
    # Cumulative minutes from the start of the run, breaks included.
    offset_minutes: float
    # Time away from the desk after this post; nonzero only when it closes a sitting.
    break_after_minutes: float = 0.0


def _digest(key: str) -> str:
    """Stable hash used only to spread values deterministically — not for security."""
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()


def _spread(book_id: int, low: float, high: float, salt: str) -> float:
    """A stable value in [low, high) derived from the book id — variance without an RNG."""
    return low + int(_digest(f"{salt}{book_id}")[:8], 16) % 1000 / 1000.0 * (high - low)


def review_words(body: str) -> int:
    """Word count of the review itself, with the editing guard comment stripped out."""
    return len(review_text(body).split())


def paced_schedule(
    drafts: Sequence[tuple[DraftMeta, str]],
    *,
    wpm: int = 100,
    edit_range: tuple[float, float] = (2.0, 5.0),
    per_sitting: tuple[int, int] = (6, 9),
    break_range: tuple[float, float] = (22.0, 48.0),
) -> list[PostSlot]:
    """Order and pace unposted drafts into a run of sittings.

    `edit_range` is the editing time for the shortest and longest draft in the batch;
    everything between is interpolated on length, so a 60-word note on a picture book is
    not treated like a 160-word argument about Bulgakov.
    """
    pending = [(m, b) for m, b in drafts if m.status != POSTED]
    if not pending:
        return []

    # A run ordered by rating or length is its own pattern; wander instead.
    pending.sort(key=lambda mb: _digest(f"ord{mb[0].book_id}"))

    counts = [review_words(b) for _, b in pending]
    lightest, heaviest = min(counts), max(counts)
    span = heaviest - lightest
    edit_low, edit_high = edit_range
    run_low, run_high = per_sitting

    slots: list[PostSlot] = []
    offset = 0.0
    sitting = 1
    posted_this_sitting = 0

    for (meta, _), words in zip(pending, counts, strict=True):
        heaviness = (words - lightest) / span if span else 0.0
        edit = edit_low + heaviness * (edit_high - edit_low)
        edit += _spread(meta.book_id, -0.6, 0.9, "edit")
        gap = round(words / wpm + max(edit, edit_low * 0.8), 1)

        posted_this_sitting += 1
        # +1 because _spread never reaches its upper bound: this makes run_high inclusive.
        run_length = run_low + int(_spread(meta.book_id, 0, run_high - run_low + 1, "run"))
        closes_sitting = posted_this_sitting >= run_length and len(slots) + 1 < len(pending)
        pause = round(_spread(meta.book_id, *break_range, "brk"), 1) if closes_sitting else 0.0

        slots.append(
            PostSlot(
                book_id=meta.book_id,
                title=meta.title,
                my_rating=meta.my_rating,
                words=words,
                gap_minutes=gap,
                sitting=sitting,
                offset_minutes=round(offset, 1),
                break_after_minutes=pause,
            )
        )

        offset += gap + pause
        if closes_sitting:
            sitting += 1
            posted_this_sitting = 0

    return slots
