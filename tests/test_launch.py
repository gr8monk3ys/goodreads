from gr_autopilot.insights.metrics import BookFact
from gr_autopilot.launch import (
    build_launch_plan,
    ranked_review_targets,
    render_markdown,
)


def _read(
    book_id: int,
    title: str,
    author: str,
    rating: int,
    *,
    avg: float = 4.0,
    reviewed: bool = False,
) -> BookFact:
    return BookFact(
        book_id=book_id,
        title=title,
        author=author,
        my_rating=rating,
        avg_rating=avg,
        exclusive_shelf="read",
        date_read="2024/01/01",
        has_review=reviewed,
        review_text="x" if reviewed else "",
    )


def test_ranked_targets_lead_with_drafted_then_passion() -> None:
    facts = [
        _read(1, "Faint Praise", "A", 3),  # 3★, no draft
        _read(2, "Beloved Classic", "B", 5),  # 5★, no draft
        _read(3, "My Favorite", "C", 5),  # 5★, draft ready
        _read(4, "Already Done", "D", 5, reviewed=True),  # already reviewed -> excluded
    ]
    ranked = ranked_review_targets(facts, drafted_ids={3})
    titles = [f.title for f in ranked]
    assert "Already Done" not in titles  # reviewed books are not targets
    assert titles[0] == "My Favorite"  # a ready draft leads
    assert titles.index("Beloved Classic") < titles.index("Faint Praise")  # passion before faint


def test_plan_has_today_and_this_week_phases() -> None:
    facts = [_read(i, f"Book {i}", "A", 5) for i in range(1, 5)]
    plan = build_launch_plan(facts, drafted_ids=set(), bio="hi", reviews_per_week=3)
    keys = {p.key for p in plan.phases}
    assert {"today", "this_week", "ongoing"} <= keys


def test_this_week_features_the_top_targets() -> None:
    facts = [
        _read(1, "Top", "A", 5, avg=4.5),
        _read(2, "Mid", "B", 4, avg=4.0),
        _read(3, "Low", "C", 3, avg=3.0),
        _read(4, "Extra", "D", 3, avg=3.0),
    ]
    plan = build_launch_plan(facts, drafted_ids=set(), bio="", reviews_per_week=2)
    week = plan.phase("this_week")
    joined = " ".join(s.text for s in week.steps)
    assert "Top" in joined and "Mid" in joined  # top 2 by leverage surface this week
    assert "Low" not in joined  # the rest are deferred to the cadence


def test_weeks_to_finish_uses_cadence_ceiling() -> None:
    facts = [_read(i, f"Book {i}", "A", 5) for i in range(1, 8)]  # 7 unreviewed reads
    plan = build_launch_plan(facts, drafted_ids=set(), bio="", reviews_per_week=3)
    assert plan.n_review_targets == 7
    assert plan.weeks_to_finish == 3  # ceil(7 / 3)


def test_empty_library_is_safe() -> None:
    plan = build_launch_plan([], drafted_ids=set(), bio="", reviews_per_week=3)
    assert plan.n_review_targets == 0
    assert plan.weeks_to_finish == 0
    assert plan.phases  # still renders the static phases


def test_render_markdown_includes_phase_titles() -> None:
    facts = [_read(1, "Solo", "A", 5)]
    md = render_markdown(build_launch_plan(facts, drafted_ids=set(), bio="b", reviews_per_week=3))
    assert "# " in md  # has a heading
    assert "This week" in md
