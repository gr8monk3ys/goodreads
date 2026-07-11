from gr_autopilot.curate import find_duplicates, hygiene, shelf_plan, tbr_triage
from gr_autopilot.insights.metrics import BookFact


def bf(book_id: int, **over: object) -> BookFact:
    base: dict[str, object] = {"exclusive_shelf": "read", "author": "A"}
    base.update(over)
    return BookFact(book_id=book_id, **base)  # type: ignore[arg-type]


def test_hygiene_finds_undated_and_unrated_reads() -> None:
    facts = [
        bf(1, my_rating=5, date_read="2024/01/01"),  # clean
        bf(2, my_rating=0, date_read="2024/01/01"),  # unrated
        bf(3, my_rating=4, date_read=None),  # undated
        bf(4, my_rating=0, date_read=None),  # both
        bf(5, exclusive_shelf="to-read"),  # excluded
    ]
    h = hygiene(facts)
    assert [b.book_id for b in h.undated_reads] == [3, 4]
    assert [b.book_id for b in h.unrated_reads] == [2, 4]


def test_tbr_triage_ranks_by_author_affinity() -> None:
    facts = [
        bf(1, exclusive_shelf="read", author="Dostoevsky", my_rating=5),
        bf(2, exclusive_shelf="read", author="Dostoevsky", my_rating=4),
        bf(3, exclusive_shelf="to-read", author="Dostoevsky", title="The Idiot"),
        bf(4, exclusive_shelf="to-read", author="Nobody", title="Random"),
    ]
    triaged = tbr_triage(facts)
    # only to-read books are candidates; the author you've read+loved ranks first
    assert [t.book.book_id for t in triaged] == [3, 4]
    assert "Dostoevsky" in triaged[0].reason
    assert triaged[0].score > triaged[1].score


def test_tbr_triage_prefers_loved_author_over_lukewarm_many() -> None:
    facts = [
        bf(1, exclusive_shelf="read", author="Loved", my_rating=5),
        bf(2, exclusive_shelf="read", author="Meh", my_rating=3),
        bf(3, exclusive_shelf="read", author="Meh", my_rating=3),
        bf(4, exclusive_shelf="read", author="Meh", my_rating=3),
        bf(5, exclusive_shelf="to-read", author="Loved", title="LovedBook"),
        bf(6, exclusive_shelf="to-read", author="Meh", title="MehBook"),
    ]
    triaged = tbr_triage(facts)
    # one 5★ author should beat three 3★ reads — taste, not volume
    assert triaged[0].book.title == "LovedBook"


def test_find_duplicates_groups_by_normalized_title() -> None:
    facts = [
        bf(1, title="Brave New World", author="Aldous Huxley"),
        bf(
            2,
            title="Brave New World",
            author="Aldous Huxley",
            exclusive_shelf="to-read",
        ),
        bf(3, title="1984", author="George Orwell"),
        bf(4, title="The Very Hungry Caterpillar!", author="Eric Carle"),
        bf(5, title="the very hungry caterpillar", author="Eric Carle"),
    ]
    dups = find_duplicates(facts)
    titles = {grp[0] for grp in dups}
    assert "Brave New World" in titles  # two editions collapse
    assert any(len(grp[1]) == 2 for grp in dups if grp[0] == "Brave New World")
    assert "1984" not in titles  # only one copy -> not a duplicate
    # punctuation/case-insensitive match catches the caterpillar pair too
    assert any(len(grp[1]) == 2 for grp in dups if "Caterpillar" in grp[0])


def test_shelf_plan_proposes_author_and_era_shelves() -> None:
    facts = [
        bf(
            1,
            author="Poe",
            original_pub_year=1845,
            title="The Raven",
            exclusive_shelf="to-read",
        ),
        bf(2, author="Poe", original_pub_year=1843, title="The Black Cat"),
        bf(3, author="Poe", original_pub_year=1839, title="Usher"),
        bf(4, author="X", original_pub_year=2015, title="A"),
        bf(5, author="Y", original_pub_year=2018, title="B", exclusive_shelf="to-read"),
        bf(6, author="Z", original_pub_year=2020, title="C"),
    ]
    plan = {s.name: s for s in shelf_plan(facts, min_books=3)}
    assert plan["Poe"].kind == "author"
    assert plan["Poe"].book_count == 3
    assert "The Raven" in plan["Poe"].sample_titles
    assert plan["classics"].book_count == 3  # the three pre-1900 Poe books
    assert plan["contemporary"].book_count == 3  # X, Y, Z (2000+)
    assert "20th-century" not in plan  # nothing in 1900-1999 -> below threshold
