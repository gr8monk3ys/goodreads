from gr_autopilot.insights.metrics import BookFact
from gr_autopilot.presence import best_reviews, signature


def bf(book_id: int, **over: object) -> BookFact:
    base: dict[str, object] = {"exclusive_shelf": "read", "author": "A", "title": f"B{book_id}"}
    base.update(over)
    return BookFact(book_id=book_id, **base)  # type: ignore[arg-type]


def test_signature_surfaces_five_stars_authors_eras_genres() -> None:
    facts = [
        bf(1, my_rating=5, title="Notes", author="Dostoevsky",
           original_pub_year=1864, genres=("Classics", "Philosophy")),
        bf(2, my_rating=5, title="Siddhartha", author="Hesse", original_pub_year=1922),
        bf(3, my_rating=4, title="The Trial", author="Kafka", original_pub_year=1925),
    ]
    sig = signature(facts)
    assert sig.five_star_titles == ("Notes", "Siddhartha")  # sorted, only 5★ reads
    assert ("Dostoevsky", 1) in sig.top_authors
    assert sig.top_eras[0] == ("1920s", 2)  # eras ranked by how much you read them
    assert ("Classics", 1) in sig.top_genres


def test_signature_authors_ranked_by_taste_not_volume() -> None:
    facts = [
        bf(1, my_rating=5, author="Beloved", title="b1"),
        bf(2, my_rating=2, author="Prolific", title="p1"),
        bf(3, my_rating=2, author="Prolific", title="p2"),
        bf(4, my_rating=2, author="Prolific", title="p3"),
    ]
    sig = signature(facts)
    # one adored author defines you more than three you barely tolerated
    assert sig.top_authors[0][0] == "Beloved"


def test_best_reviews_ranks_longest_substantive_first() -> None:
    facts = [
        bf(1, has_review=True, my_rating=4, title="Long", review_text=" ".join(["w"] * 50)),
        bf(2, has_review=True, my_rating=5, title="Short", review_text="short one here"),
        bf(3, has_review=False, title="NoReview"),
    ]
    best = best_reviews(facts, top=5)
    assert best[0].title == "Long"
    assert best[0].word_count == 50
    assert all(b.title != "NoReview" for b in best)  # only books with a real review
