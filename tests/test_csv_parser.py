from pathlib import Path

from gr_autopilot.ingest.csv_parser import clean_isbn, norm_review, parse_export

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def test_clean_isbn_strips_formula_wrapper() -> None:
    assert clean_isbn('="160486530X"') == "160486530X"


def test_clean_isbn_empty_wrapper_is_none() -> None:
    assert clean_isbn('=""') is None
    assert clean_isbn("") is None
    assert clean_isbn(None) is None


def test_clean_isbn_plain_value_passes_through() -> None:
    assert clean_isbn("9780441478125") == "9780441478125"


def test_norm_review_converts_br_to_newline_and_strips_tags() -> None:
    raw = "Line one.<br/>Line two.<br />Line three."
    assert norm_review(raw) == "Line one.\nLine two.\nLine three."


def test_norm_review_br_only_is_empty() -> None:
    assert norm_review("<br/>") == ""
    assert norm_review("") == ""
    assert norm_review(None) == ""


def test_norm_review_unescapes_entities() -> None:
    assert norm_review("Tom &amp; Jerry rule") == "Tom & Jerry rule"


def test_parse_export_reads_all_rows() -> None:
    records = parse_export(FIXTURE)
    assert len(records) == 3


def test_parse_export_fields_and_quirks() -> None:
    by_id = {r.book_id: r for r in parse_export(FIXTURE)}
    dune = by_id[11]
    assert dune.title == "Dune"
    assert dune.isbn == "0441478123"  # formula wrapper stripped
    assert dune.my_rating == 5
    assert dune.exclusive_shelf == "read"
    assert dune.review_text == "Loved it.\nA masterpiece."
    assert dune.shelves == ("sci-fi", "favorites")

    skim = by_id[22]
    assert skim.isbn is None  # ="" -> None
    assert skim.review_text == ""  # empty review
    assert skim.exclusive_shelf == "read"
