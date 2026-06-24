from gr_autopilot.insights.metrics import BookFact, compute
from gr_autopilot.insights.suggestions import IMPACT_RANK, suggest


def read_books(n: int, **over: object) -> list[BookFact]:
    return [BookFact(book_id=i, exclusive_shelf="read", **over) for i in range(1, n + 1)]  # type: ignore[arg-type]


def by_key(metrics_facts: list[BookFact]) -> dict[str, object]:
    return {s.key: s for s in suggest(compute(metrics_facts))}


def test_rating_gap_is_high_impact_when_many_unrated() -> None:
    s = by_key(read_books(12, my_rating=0))
    assert "rating_gap" in s
    assert s["rating_gap"].impact == "high"  # type: ignore[attr-defined]
    assert s["rating_gap"].goal == "stats"  # type: ignore[attr-defined]


def test_review_gap_surfaces_and_is_presence_goal() -> None:
    s = by_key(read_books(12, my_rating=4, has_review=False))
    assert s["review_gap"].impact == "high"  # type: ignore[attr-defined]
    assert s["review_gap"].goal == "presence"  # type: ignore[attr-defined]


def test_tbr_triage_fires_high_on_large_pile() -> None:
    facts = [BookFact(book_id=i, exclusive_shelf="to-read") for i in range(1, 161)]
    s = by_key(facts)
    assert s["tbr_triage"].impact == "high"  # type: ignore[attr-defined]
    assert s["tbr_triage"].goal == "curation"  # type: ignore[attr-defined]


def test_author_shelves_lists_stacked_authors() -> None:
    facts = [BookFact(book_id=i, exclusive_shelf="to-read", author="Poe") for i in range(1, 5)]
    s = by_key(facts)
    assert "author_shelves" in s
    assert "Poe" in s["author_shelves"].items[0]  # type: ignore[attr-defined]


def test_date_hygiene_fires_when_reads_lack_dates() -> None:
    s = by_key(read_books(11, my_rating=5, has_review=True, date_read=None))
    assert s["date_hygiene"].impact == "medium"  # type: ignore[attr-defined]


def test_suggestions_ranked_high_to_low() -> None:
    facts = read_books(12, my_rating=0) + [
        BookFact(book_id=900 + i, exclusive_shelf="to-read") for i in range(160)
    ]
    ranks = [IMPACT_RANK[s.impact] for s in suggest(compute(facts))]
    assert ranks == sorted(ranks)  # never a lower-impact item before a higher one


def test_empty_library_yields_no_suggestions() -> None:
    assert suggest(compute([])) == []
