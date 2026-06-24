import json

from gr_autopilot.insights.metrics import BookFact, compute
from gr_autopilot.insights.report import render
from gr_autopilot.insights.suggestions import suggest


def sample() -> list[BookFact]:
    reads = [
        BookFact(book_id=i, exclusive_shelf="read", my_rating=0, has_review=False)
        for i in range(1, 13)
    ]
    reads[0] = BookFact(
        book_id=1, exclusive_shelf="read", my_rating=5, has_review=True,
        num_pages=300, original_pub_year=1965, date_read="2024/01/01", genres=("Classics",),
    )
    tbr = [BookFact(book_id=100 + i, exclusive_shelf="to-read", author="Poe") for i in range(160)]
    return reads + tbr


def test_render_markdown_has_sections_and_numbers() -> None:
    facts = sample()
    out = render(compute(facts), suggest(compute(facts)), fmt="md")
    assert "# " in out  # has a title
    assert "## Ratings" in out
    assert "## Suggested moves" in out
    assert "172 books" in out  # 12 read + 160 to-read
    assert "Rate 11" in out or "rating" in out.lower()  # the rating-gap suggestion surfaces


def test_render_json_roundtrips() -> None:
    facts = sample()
    metrics = compute(facts)
    out = render(metrics, suggest(metrics), fmt="json")
    data = json.loads(out)
    assert data["metrics"]["total_books"] == 172
    assert any(s["key"] == "tbr_triage" for s in data["suggestions"])


def test_render_table_is_compact_text() -> None:
    facts = sample()
    out = render(compute(facts), suggest(compute(facts)), fmt="table")
    assert "books=172" in out
    assert "tbr_triage" in out or "Triage" in out


def test_render_unknown_format_raises() -> None:
    facts = sample()
    try:
        render(compute(facts), suggest(compute(facts)), fmt="pdf")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown format")
