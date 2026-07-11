"""Profile-presence pack. Pure: BookFacts -> the material you put on your public profile.

Surfaces your reading "signature" (5★ canon, signature authors/eras/genres) and ranks your
existing written reviews so the strongest can be featured. Read-only; the bio prose itself
is drafted in-loop and handed to you to edit — nothing is published automatically.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gr_autopilot.curate import _author_affinity
from gr_autopilot.insights.metrics import (
    BookFact,
    eras,
    genre_stats,
)

READ = "read"


def _signature_authors(facts: Sequence[BookFact]) -> list[tuple[str, int]]:
    """Read authors ranked by affinity (taste, then volume), displayed as (author, count)."""
    affinity = _author_affinity(facts)  # author -> (score, n_read, avg)
    ranked = sorted(affinity.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return [(author, stats[1]) for author, stats in ranked]


@dataclass(frozen=True)
class Signature:
    five_star_titles: tuple[str, ...]
    top_authors: list[tuple[str, int]]
    top_eras: list[tuple[str, int]]  # ranked by how much you've read them
    top_genres: list[tuple[str, int]]


def signature(facts: Sequence[BookFact]) -> Signature:
    read = [f for f in facts if f.exclusive_shelf == READ]
    five = tuple(sorted(f.title for f in read if f.my_rating == 5))
    eras_by_count = sorted(eras(facts).by_band, key=lambda kv: (-kv[1], kv[0]))
    return Signature(
        five_star_titles=five,
        top_authors=_signature_authors(facts),
        top_eras=eras_by_count,
        top_genres=genre_stats(facts).top,
    )


@dataclass(frozen=True)
class FeaturedReview:
    title: str
    author: str
    my_rating: int
    word_count: int
    snippet: str


def _snippet(text: str, limit: int = 140) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def best_reviews(facts: Sequence[BookFact], top: int = 5) -> list[FeaturedReview]:
    """Your existing written reviews, ranked longest/most-substantive first, to feature."""
    reviewed = [
        f for f in facts if f.exclusive_shelf == READ and f.has_review and f.review_text
    ]
    reviewed.sort(key=lambda f: (-len(f.review_text.split()), -f.my_rating, f.title))
    return [
        FeaturedReview(
            title=f.title,
            author=f.author,
            my_rating=f.my_rating,
            word_count=len(f.review_text.split()),
            snippet=_snippet(f.review_text),
        )
        for f in reviewed[:top]
    ]
