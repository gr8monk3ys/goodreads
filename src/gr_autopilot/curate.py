"""Concrete curation plans over a library. Pure: BookFacts -> actionable per-book plans.

Where `insights` reports aggregates and ranked suggestions, `curate` produces the lists you
act on: which exact books lack a date or rating, and which to-read books to pick up next
based on authors you've already enjoyed. Read-only; nothing here writes to an account.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from gr_autopilot.insights.metrics import BookFact

READ = "read"
TO_READ = "to-read"
_YEAR_RE = re.compile(r"(\d{4})")

# The one shared definition of the featured-shelf membership — launch and dashboard
# must agree on it or the same page contradicts itself.
EXISTENTIAL_AUTHORS = {
    "Fyodor Dostoevsky",
    "Hermann Hesse",
    "Franz Kafka",
    "Aldous Huxley",
    "Viktor E. Frankl",
    "George Orwell",
    "Theodore John Kaczynski",
}


def existential_shelf_members(facts: Sequence[BookFact]) -> list[BookFact]:
    """Read books that belong on the featured existential-classics shelf."""
    return sorted(
        (
            f
            for f in facts
            if f.exclusive_shelf == READ and (f.my_rating == 5 or f.author in EXISTENTIAL_AUTHORS)
        ),
        key=lambda f: -f.my_rating,
    )


def _has_year(value: str | None) -> bool:
    return bool(value and _YEAR_RE.search(value))


def _year(value: str | None) -> int:
    m = _YEAR_RE.search(value or "")
    return int(m.group(1)) if m else 0


@dataclass(frozen=True)
class Hygiene:
    undated_reads: list[BookFact]  # read but no Date Read -> invisible to stats/challenge
    unrated_reads: list[BookFact]  # read but never scored


def hygiene(facts: Sequence[BookFact]) -> Hygiene:
    read = [f for f in facts if f.exclusive_shelf == READ]
    return Hygiene(
        undated_reads=[f for f in read if not _has_year(f.date_read)],
        unrated_reads=[f for f in read if f.my_rating <= 0],
    )


@dataclass(frozen=True)
class Triaged:
    book: BookFact
    score: int
    reason: str


def _author_affinity(
    facts: Sequence[BookFact],
) -> dict[str, tuple[int, int, float | None]]:
    """author -> (score, n_read, avg_rating). Score favors how much you LIKED, then how much.

    score = round(avg * 10) + n_read, where avg defaults to 3.0 for read-but-unrated authors.
    A one-book 5★ author (51) thus outranks three 3★ reads (33): taste over volume.
    """
    count: dict[str, int] = defaultdict(int)
    rating_sum: dict[str, int] = defaultdict(int)
    rating_n: dict[str, int] = defaultdict(int)
    for f in facts:
        if f.exclusive_shelf != READ or not f.author:
            continue
        count[f.author] += 1
        if f.my_rating > 0:
            rating_sum[f.author] += f.my_rating
            rating_n[f.author] += 1

    out: dict[str, tuple[int, int, float | None]] = {}
    for author, n in count.items():
        avg = rating_sum[author] / rating_n[author] if rating_n[author] else None
        score = round((avg if avg is not None else 3.0) * 10) + n
        out[author] = (score, n, avg)
    return out


def tbr_triage(facts: Sequence[BookFact], top: int = 20) -> list[Triaged]:
    """Rank to-read books by affinity for their author (how much you've read & loved them)."""
    affinity = _author_affinity(facts)

    triaged: list[Triaged] = []
    for f in facts:
        if f.exclusive_shelf != TO_READ:
            continue
        score, n, avg = affinity.get(f.author, (0, 0, None))
        if n and avg is not None:
            reason = f"you've read {n} by {f.author} (avg {avg:.1f}★)"
        elif n:
            reason = f"you've read {n} by {f.author}"
        else:
            reason = "author you haven't read yet"
        triaged.append(Triaged(book=f, score=score, reason=reason))

    triaged.sort(key=lambda t: (-t.score, -_year(t.book.date_added), t.book.title))
    return triaged[:top]


def find_duplicates(facts: Sequence[BookFact]) -> list[tuple[str, list[BookFact]]]:
    """Group books whose titles collapse to the same normalized key (likely dup editions)."""
    groups: dict[str, list[BookFact]] = defaultdict(list)
    for f in facts:
        key = re.sub(r"[^a-z0-9]+", "", f.title.lower())
        if key:
            groups[key].append(f)
    out = [(books[0].title, books) for books in groups.values() if len(books) > 1]
    return sorted(out, key=lambda g: g[0])


@dataclass(frozen=True)
class ProposedShelf:
    name: str
    kind: str  # "author" | "era"
    book_count: int
    sample_titles: tuple[str, ...]


def _era_band(year: int) -> str:
    if year < 1900:
        return "classics"
    if year < 2000:
        return "20th-century"
    return "contemporary"


def shelf_plan(facts: Sequence[BookFact], min_books: int = 3) -> list[ProposedShelf]:
    """Propose custom shelves: authors you own/read in bulk, and publication-era buckets."""
    by_author: dict[str, list[BookFact]] = defaultdict(list)
    by_era: dict[str, list[BookFact]] = defaultdict(list)
    for f in facts:
        if f.author:
            by_author[f.author].append(f)
        if f.original_pub_year is not None:
            by_era[_era_band(f.original_pub_year)].append(f)

    shelves: list[ProposedShelf] = []
    for name, books in by_author.items():
        if len(books) >= min_books:
            shelves.append(
                ProposedShelf(name, "author", len(books), tuple(b.title for b in books[:3]))
            )
    for name, books in by_era.items():
        if len(books) >= min_books:
            shelves.append(
                ProposedShelf(name, "era", len(books), tuple(b.title for b in books[:3]))
            )
    shelves.sort(key=lambda s: (-s.book_count, s.name))
    return shelves
