"""Pure analytics over the library. No I/O, no SQL, no formatting — just data -> data.

Every function takes a sequence of `BookFact` (a flat projection of one book) and returns a
small frozen result. This is where correctness lives; it is exercised entirely with
hand-built facts, never a database.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

READ = "read"
TO_READ = "to-read"
_PRE_1500 = "pre-1500"
_YEAR_RE = re.compile(r"(\d{4})")


def _year(value: str | None) -> int | None:
    """First 4-digit year in a Goodreads date cell ('2024/05/01', '2024-05'); else None."""
    if not value:
        return None
    m = _YEAR_RE.search(value)
    return int(m.group(1)) if m else None


def _rank(counts: Counter[str]) -> list[tuple[str, int]]:
    """Items ranked by count desc, ties broken alphabetically for determinism."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


@dataclass(frozen=True)
class BookFact:
    """Flat, store-independent projection of a single book for analytics."""

    book_id: int
    title: str = ""
    author: str = ""
    my_rating: int = 0  # 0 == unrated
    avg_rating: float | None = None  # Goodreads crowd average; None if export omits it
    exclusive_shelf: str = READ
    date_read: str | None = None
    date_added: str | None = None
    num_pages: int | None = None
    original_pub_year: int | None = None
    has_review: bool = False
    genres: tuple[str, ...] = ()


def _read(facts: Sequence[BookFact]) -> list[BookFact]:
    return [f for f in facts if f.exclusive_shelf == READ]


def shelf_counts(facts: Sequence[BookFact]) -> dict[str, int]:
    """Count books per exclusive shelf (read / to-read / currently-reading / ...)."""
    counts: dict[str, int] = {}
    for f in facts:
        counts[f.exclusive_shelf] = counts.get(f.exclusive_shelf, 0) + 1
    return counts


@dataclass(frozen=True)
class RatingProfile:
    n_read: int
    n_rated: int
    n_unrated: int
    mean: float | None
    histogram: dict[int, int]  # stars 1..5 -> count
    crowd_delta: float | None  # mean(my_rating - avg_rating); None if no avg data
    harsher: bool | None  # crowd_delta < 0; None if unknown


def rating_profile(facts: Sequence[BookFact]) -> RatingProfile:
    read = _read(facts)
    rated = [f.my_rating for f in read if f.my_rating > 0]
    histogram = {star: 0 for star in range(1, 6)}
    for r in rated:
        if r in histogram:
            histogram[r] += 1
    pairs = [(f.my_rating, f.avg_rating) for f in read if f.my_rating > 0 and f.avg_rating]
    crowd_delta = round(statistics.mean([m - a for m, a in pairs]), 2) if pairs else None
    return RatingProfile(
        n_read=len(read),
        n_rated=len(rated),
        n_unrated=len(read) - len(rated),
        mean=round(statistics.mean(rated), 2) if rated else None,
        histogram=histogram,
        crowd_delta=crowd_delta,
        harsher=(crowd_delta < 0) if crowd_delta is not None else None,
    )


@dataclass(frozen=True)
class ReviewCoverage:
    n_read: int
    n_reviewed: int
    n_unreviewed: int
    n_targets: int  # read + rated + no review (the best draft candidates)


def review_coverage(facts: Sequence[BookFact]) -> ReviewCoverage:
    read = _read(facts)
    reviewed = [f for f in read if f.has_review]
    unreviewed = [f for f in read if not f.has_review]
    targets = [f for f in unreviewed if f.my_rating > 0]
    return ReviewCoverage(
        n_read=len(read),
        n_reviewed=len(reviewed),
        n_unreviewed=len(unreviewed),
        n_targets=len(targets),
    )


@dataclass(frozen=True)
class TbrShape:
    size: int
    adds_by_year: list[tuple[int, int]]
    oldest_add_year: int | None
    recent_year: int | None  # latest calendar year on record (may be a partial year)
    recent_adds: int
    peak_year: int | None  # year you added the most — the honest "velocity" signal
    peak_adds: int
    authors: list[tuple[str, int]]  # most-stacked authors on the TBR, full ranked list


def tbr_shape(facts: Sequence[BookFact]) -> TbrShape:
    tbr = [f for f in facts if f.exclusive_shelf == TO_READ]
    years = Counter(y for f in tbr if (y := _year(f.date_added)) is not None)
    recent_year = max(years) if years else None
    # peak = most-added year; ties resolve to the later year for determinism.
    peak_year = max(years, key=lambda y: (years[y], y)) if years else None
    return TbrShape(
        size=len(tbr),
        adds_by_year=sorted(years.items()),
        oldest_add_year=min(years) if years else None,
        recent_year=recent_year,
        recent_adds=years.get(recent_year, 0) if recent_year is not None else 0,
        peak_year=peak_year,
        peak_adds=years.get(peak_year, 0) if peak_year is not None else 0,
        authors=_rank(Counter(f.author for f in tbr if f.author)),
    )


@dataclass(frozen=True)
class Pace:
    reads_by_year: list[tuple[int, int]]
    n_missing_date: int


def pace(facts: Sequence[BookFact]) -> Pace:
    read = _read(facts)
    years = Counter(y for f in read if (y := _year(f.date_read)) is not None)
    return Pace(
        reads_by_year=sorted(years.items()),
        n_missing_date=sum(1 for f in read if _year(f.date_read) is None),
    )


@dataclass(frozen=True)
class Eras:
    by_band: list[tuple[str, int]]  # chronological: pre-1500 first, then decades ascending
    n_missing: int


def _band(year: int) -> str:
    return _PRE_1500 if year < 1500 else f"{year // 10 * 10}s"


def _band_sort_key(band: str) -> int:
    return -10_000 if band == _PRE_1500 else int(band[:-1])


def eras(facts: Sequence[BookFact]) -> Eras:
    read = _read(facts)
    bands = Counter(_band(f.original_pub_year) for f in read if f.original_pub_year is not None)
    by_band = sorted(bands.items(), key=lambda kv: _band_sort_key(kv[0]))
    return Eras(
        by_band=by_band,
        n_missing=sum(1 for f in read if f.original_pub_year is None),
    )


@dataclass(frozen=True)
class PageStats:
    n_with_pages: int
    total_pages: int
    median_pages: int | None


def page_stats(facts: Sequence[BookFact]) -> PageStats:
    pages = [f.num_pages for f in _read(facts) if f.num_pages]
    return PageStats(
        n_with_pages=len(pages),
        total_pages=sum(pages),
        median_pages=int(statistics.median(pages)) if pages else None,
    )


def author_concentration(facts: Sequence[BookFact]) -> list[tuple[str, int]]:
    """Read-shelf authors ranked by how many of their books you've read."""
    return _rank(Counter(f.author for f in _read(facts) if f.author))


@dataclass(frozen=True)
class GenreStats:
    top: list[tuple[str, int]]
    n_ungenred: int  # read books with no genre data (run `gr enrich` to fill)


def genre_stats(facts: Sequence[BookFact]) -> GenreStats:
    read = _read(facts)
    counts: Counter[str] = Counter()
    for f in read:
        counts.update(f.genres)
    return GenreStats(
        top=_rank(counts),
        n_ungenred=sum(1 for f in read if not f.genres),
    )


@dataclass(frozen=True)
class LibraryMetrics:
    """The full read-only analysis of a library — every sub-metric in one object."""

    total_books: int
    shelf_counts: dict[str, int]
    ratings: RatingProfile
    reviews: ReviewCoverage
    tbr: TbrShape
    pace: Pace
    eras: Eras
    pages: PageStats
    authors: list[tuple[str, int]]
    genres: GenreStats


def compute(facts: Sequence[BookFact]) -> LibraryMetrics:
    """Assemble every metric over the library in one pass-friendly call."""
    return LibraryMetrics(
        total_books=len(facts),
        shelf_counts=shelf_counts(facts),
        ratings=rating_profile(facts),
        reviews=review_coverage(facts),
        tbr=tbr_shape(facts),
        pace=pace(facts),
        eras=eras(facts),
        pages=page_stats(facts),
        authors=author_concentration(facts),
        genres=genre_stats(facts),
    )
