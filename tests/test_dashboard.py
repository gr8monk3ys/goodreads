from gr_autopilot.dashboard import build_dashboard_html
from gr_autopilot.insights.metrics import BookFact


def bf(book_id: int, **over: object) -> BookFact:
    base: dict[str, object] = {"exclusive_shelf": "read", "author": "A", "title": f"B{book_id}"}
    base.update(over)
    return BookFact(book_id=book_id, **base)  # type: ignore[arg-type]


def test_dashboard_is_self_contained_html_with_action_sections() -> None:
    facts = [
        bf(1, my_rating=5, title="Siddhartha", author="Hermann Hesse", has_review=True),
        bf(2, my_rating=0, title="Tom & Jerry", author="X"),  # unrated + needs escaping
        bf(3, my_rating=4, title="The Trial", author="Franz Kafka", has_review=False),
    ]
    out = build_dashboard_html(
        facts, draft_counts={"draft": 2}, proposed_ratings={2: 3}, bio="I read to argue."
    )
    assert out.startswith("<!doctype html>") and out.rstrip().endswith("</html>")
    assert "existential-classics" in out  # shelf section
    assert "Siddhartha" in out  # 5-star canon in the subtitle
    assert "Rate 1 books" in out  # one unrated read
    assert 'type="checkbox"' in out  # it's an interactive checklist
    assert "localStorage" in out  # ticks persist
    assert "Tom &amp; Jerry" in out  # html-escaped, not raw &
    assert "I read to argue." in out  # bio embedded
