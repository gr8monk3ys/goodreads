from gr_autopilot.dashboard import build_dashboard_html
from gr_autopilot.insights.metrics import BookFact


def bf(book_id: int, **over: object) -> BookFact:
    base: dict[str, object] = {
        "exclusive_shelf": "read",
        "author": "A",
        "title": f"B{book_id}",
    }
    base.update(over)
    return BookFact(book_id=book_id, **base)  # type: ignore[arg-type]


def test_dashboard_is_self_contained_html_with_action_sections() -> None:
    facts = [
        bf(1, my_rating=5, title="Siddhartha", author="Hermann Hesse", has_review=True),
        bf(2, my_rating=0, title="Tom & Jerry", author="X"),  # unrated + needs escaping
        bf(3, my_rating=4, title="The Trial", author="Franz Kafka", has_review=False),
    ]
    out = build_dashboard_html(
        facts,
        draft_counts={"draft": 2},
        proposed_ratings={2: 3},
        bio="I read to argue.",
    )
    assert out.startswith("<!doctype html>") and out.rstrip().endswith("</html>")
    assert "existential-classics" in out  # shelf section
    assert "Siddhartha" in out  # 5-star canon in the subtitle
    assert "Rate 1 books" in out  # one unrated read
    assert 'type="checkbox"' in out  # it's an interactive checklist
    assert "localStorage" in out  # ticks persist
    assert "Tom &amp; Jerry" in out  # html-escaped, not raw &
    assert "I read to argue." in out  # bio embedded


def test_dashboard_opens_with_a_start_here_launch_sequence() -> None:
    facts = [
        bf(1, my_rating=5, title="Siddhartha", author="Hermann Hesse", avg_rating=4.5),
        bf(2, my_rating=4, title="The Trial", author="Franz Kafka", avg_rating=4.0),
        bf(3, my_rating=3, title="A Lesser Read", author="Z", avg_rating=3.0),
    ]
    out = build_dashboard_html(facts, draft_counts={}, drafted_ids={1})
    assert "Start here" in out  # the sequence leads the page
    # the launch card appears before the flat numbered sections
    assert out.index("Start here") < out.index("Rate ")
    assert "This week" in out  # the campaign's cadence framing
    assert out.index("Siddhartha") < out.index("A Lesser Read")  # leverage order, not file order


def test_dashboard_escapes_markup_in_titles_everywhere() -> None:
    # a hostile title must never reach the page raw — not in the canon line, launch card,
    # or any section (regression guard for the canon-subtitle injection hole).
    facts = [bf(1, my_rating=5, title="<script>x</script>", author="A", has_review=False)]
    out = build_dashboard_html(facts, draft_counts={}, drafted_ids=set())
    assert "<script>x</script>" not in out
    assert "&lt;script&gt;x&lt;/script&gt;" in out


def test_dashboard_renders_reading_visualizations() -> None:
    facts = [
        bf(
            1,
            my_rating=5,
            date_read="2023/01/01",
            original_pub_year=1866,
            genres=("classics", "fiction"),
        ),
        bf(
            2,
            my_rating=4,
            date_read="2023/05/01",
            original_pub_year=1932,
            genres=("dystopia",),
        ),
        bf(
            3,
            my_rating=4,
            date_read="2024/02/01",
            original_pub_year=1951,
            genres=("classics",),
        ),
    ]
    out = build_dashboard_html(facts, draft_counts={}, drafted_ids=set())
    assert "reading in numbers" in out.lower()  # the visualization section exists
    assert 'class="meter"' in out  # CSS bar charts, not just text
    assert "2023" in out and "2024" in out  # reads-by-year chart is data-driven


def test_checkbox_ids_are_keyed_by_book_id_not_position() -> None:
    """Ticks persist in localStorage by checkbox id; positional ids (rate0, rev1) re-attach
    to different books when the list shrinks or reorders between regenerations."""
    facts = [
        bf(7, my_rating=0, title="Seven", author="A"),  # unrated + undated + unreviewed
        bf(9, my_rating=0, title="Nine", author="B"),
        bf(3, my_rating=5, title="Three", author="C", has_review=False),  # shelf member
    ]
    out = build_dashboard_html(facts, draft_counts={}, drafted_ids={7})
    assert 'id="rate7"' in out and 'id="rate9"' in out
    assert 'id="rev7"' in out and 'id="rev3"' in out
    assert 'id="shelf3"' in out
    assert 'id="date7"' in out
    assert 'id="L-this_week-b7"' in out  # launch-card steps too


def test_dashboard_honors_reviews_per_week() -> None:
    facts = [bf(i, my_rating=5, title=f"B{i}", has_review=False) for i in range(1, 9)]
    out = build_dashboard_html(facts, draft_counts={}, drafted_ids=set(), reviews_per_week=5)
    assert "~5/week" in out


def test_dashboard_makes_no_network_requests() -> None:
    """The board is documented as self-contained: opening a personal file must not
    ping any remote host, and offline opens must not block on a font fetch."""
    out = build_dashboard_html([bf(1, my_rating=5)], draft_counts={}, drafted_ids=set())
    assert "fonts.googleapis.com" not in out
    assert "@import" not in out


def test_review_section_lists_targets_in_ranked_order() -> None:
    """Section 2 is what the launch card's cadence defers to — it must show the ranked
    order (drafted first, then passion), not raw fact order."""
    facts = [
        bf(1, my_rating=3, title="Faint Praise", author="A", has_review=False),
        bf(2, my_rating=5, title="Beloved Classic", author="B", has_review=False),
    ]
    out = build_dashboard_html(facts, draft_counts={}, drafted_ids=set())
    section = out.split("2 · Post")[1].split("3 · Create")[0]
    assert section.index("Beloved Classic") < section.index("Faint Praise")


def test_dashboard_ports_site_design_system() -> None:
    out = build_dashboard_html([bf(1, my_rating=5)], draft_counts={}, drafted_ids=set())
    assert "Fraunces" in out  # the site's display serif
    assert "IBM Plex Mono" in out  # the site's mono "wall-label" font
    assert "#2c5530" in out or "152" in out  # the forest-green primary
    assert "prefers-color-scheme: dark" in out  # dark mode, like the site
