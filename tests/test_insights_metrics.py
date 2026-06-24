from gr_autopilot.insights.metrics import (
    BookFact,
    author_concentration,
    compute,
    eras,
    genre_stats,
    pace,
    page_stats,
    rating_profile,
    review_coverage,
    shelf_counts,
    tbr_shape,
)


def bf(book_id: int, **over: object) -> BookFact:
    """Terse BookFact factory; defaults to a read, unrated, unreviewed book."""
    base: dict[str, object] = {
        "title": f"B{book_id}",
        "author": "A",
        "my_rating": 0,
        "avg_rating": None,
        "exclusive_shelf": "read",
        "date_read": None,
        "date_added": None,
        "num_pages": None,
        "original_pub_year": None,
        "has_review": False,
        "genres": (),
    }
    base.update(over)
    return BookFact(book_id=book_id, **base)  # type: ignore[arg-type]


def test_shelf_counts_buckets_by_exclusive_shelf() -> None:
    facts = [
        bf(1, exclusive_shelf="read"),
        bf(2, exclusive_shelf="read"),
        bf(3, exclusive_shelf="to-read"),
        bf(4, exclusive_shelf="currently-reading"),
    ]
    assert shelf_counts(facts) == {"read": 2, "to-read": 1, "currently-reading": 1}


def test_rating_profile_over_read_shelf() -> None:
    facts = [
        bf(1, my_rating=5, avg_rating=4.0, has_review=True),
        bf(2, my_rating=2, avg_rating=4.0),
        bf(3, my_rating=0),  # read but unrated
        bf(4, my_rating=4, avg_rating=3.0, exclusive_shelf="to-read"),  # excluded
    ]
    p = rating_profile(facts)
    assert p.n_read == 3
    assert p.n_rated == 2
    assert p.n_unrated == 1
    assert p.mean == 3.5
    assert p.histogram == {1: 0, 2: 1, 3: 0, 4: 0, 5: 1}
    # crowd delta: (5-4.0)=+1, (2-4.0)=-2 -> mean -0.5 -> harsher
    assert p.crowd_delta == -0.5
    assert p.harsher is True


def test_rating_profile_without_avg_rating_column() -> None:
    # the user's real export omits Average Rating: crowd comparison must degrade, not crash
    facts = [bf(1, my_rating=5), bf(2, my_rating=3)]
    p = rating_profile(facts)
    assert p.mean == 4.0
    assert p.crowd_delta is None
    assert p.harsher is None


def test_rating_profile_empty_library() -> None:
    p = rating_profile([])
    assert p.n_read == 0
    assert p.mean is None
    assert p.histogram == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}


def test_review_coverage_counts_targets() -> None:
    facts = [
        bf(1, my_rating=5, has_review=True),  # reviewed
        bf(2, my_rating=4, has_review=False),  # target: read+rated+no review
        bf(3, my_rating=0, has_review=False),  # read, unrated, no review -> not a target
        bf(4, exclusive_shelf="to-read"),  # excluded
    ]
    c = review_coverage(facts)
    assert c.n_read == 3
    assert c.n_reviewed == 1
    assert c.n_unreviewed == 2
    assert c.n_targets == 1


def test_tbr_shape_size_velocity_and_authors() -> None:
    facts = [
        bf(1, exclusive_shelf="to-read", date_added="2024/01/01", author="Poe"),
        bf(2, exclusive_shelf="to-read", date_added="2025/02/01", author="Poe"),
        bf(3, exclusive_shelf="to-read", date_added="2025/03/01", author="Wilde"),
        bf(4, exclusive_shelf="to-read", date_added="2026/01/01", author="X"),  # partial year
        bf(5, exclusive_shelf="read"),  # excluded
    ]
    t = tbr_shape(facts)
    assert t.size == 4
    assert t.adds_by_year == [(2024, 1), (2025, 2), (2026, 1)]
    assert t.oldest_add_year == 2024
    assert t.recent_year == 2026  # latest year on record
    assert t.recent_adds == 1
    assert t.peak_year == 2025  # year you added the most — the real signal
    assert t.peak_adds == 2
    assert t.authors == [("Poe", 2), ("Wilde", 1), ("X", 1)]


def test_pace_reads_by_year_and_missing_dates() -> None:
    facts = [
        bf(1, date_read="2024/05/01"),
        bf(2, date_read="2025/01/01"),
        bf(3, date_read="2025/06/01"),
        bf(4, date_read=None),  # read but undated
        bf(5, exclusive_shelf="to-read", date_read="2025/01/01"),  # excluded
    ]
    p = pace(facts)
    assert p.reads_by_year == [(2024, 1), (2025, 2)]
    assert p.n_missing_date == 1


def test_eras_buckets_decades_and_folds_pre_1500() -> None:
    facts = [
        bf(1, original_pub_year=1965),
        bf(2, original_pub_year=2001),
        bf(3, original_pub_year=2008),
        bf(4, original_pub_year=-350),  # Plato -> pre-1500 band, must not crash
        bf(5, original_pub_year=None),
    ]
    e = eras(facts)
    assert e.by_band == [("pre-1500", 1), ("1960s", 1), ("2000s", 2)]
    assert e.n_missing == 1


def test_page_stats_totals_and_median() -> None:
    facts = [
        bf(1, num_pages=100),
        bf(2, num_pages=200),
        bf(3, num_pages=300),
        bf(4, num_pages=None),
    ]
    s = page_stats(facts)
    assert s.n_with_pages == 3
    assert s.total_pages == 600
    assert s.median_pages == 200


def test_author_concentration_ranks_by_count_then_name() -> None:
    facts = [bf(1, author="A"), bf(2, author="A"), bf(3, author="B"), bf(4, author="C")]
    assert author_concentration(facts) == [("A", 2), ("B", 1), ("C", 1)]


def test_genre_stats_counts_read_genres_and_ungenred() -> None:
    facts = [
        bf(1, genres=("Fiction", "Classics")),
        bf(2, genres=("Fiction",)),
        bf(3, genres=()),  # read but ungenred
    ]
    g = genre_stats(facts)
    assert g.top == [("Fiction", 2), ("Classics", 1)]
    assert g.n_ungenred == 1


def test_compute_assembles_all_metrics() -> None:
    facts = [
        bf(1, my_rating=5, avg_rating=4.0, has_review=True, num_pages=300,
           original_pub_year=1965, date_read="2024/01/01", author="Poe"),
        bf(2, my_rating=4, has_review=False, date_read="2025/02/01", author="Poe"),
        bf(3, exclusive_shelf="to-read", date_added="2025/03/01", author="Wilde"),
    ]
    m = compute(facts)
    assert m.total_books == 3
    assert m.shelf_counts == {"read": 2, "to-read": 1}
    assert m.ratings.n_read == 2
    assert m.reviews.n_targets == 1  # book 2: read, rated, no review
    assert m.tbr.size == 1
    assert m.pace.reads_by_year == [(2024, 1), (2025, 1)]
    assert m.eras.by_band == [("1960s", 1)]
    assert m.pages.total_pages == 300
    assert m.authors == [("Poe", 2)]
    assert m.genres.n_ungenred == 2
