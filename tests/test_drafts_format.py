from gr_autopilot.drafts.format import DraftMeta, parse_draft, render_draft, slug


def test_render_then_parse_roundtrips_meta() -> None:
    meta = DraftMeta(
        book_id=11, title="Dune: Part One", author="Frank Herbert", my_rating=5
    )
    text = render_draft(meta, "A masterpiece of world-building.")
    parsed_meta, body = parse_draft(text)
    assert parsed_meta == meta  # colon in title survives the round-trip
    assert "A masterpiece of world-building." in body


def test_render_includes_status_and_never_post_guard() -> None:
    meta = DraftMeta(book_id=1, title="X", author="Y", my_rating=4)
    text = render_draft(meta, "body")
    assert "status: draft" in text
    # an explicit, human-facing reminder that nothing is posted automatically
    assert "approved" in text.lower()
    assert "post" in text.lower()


def test_parse_reads_status_after_user_edits_it() -> None:
    meta = DraftMeta(book_id=1, title="X", author="Y", my_rating=4)
    text = render_draft(meta, "original").replace("status: draft", "status: approved")
    parsed_meta, _ = parse_draft(text)
    assert parsed_meta.status == "approved"


def test_slug_handles_punctuation_and_spaces() -> None:
    assert slug("The Brothers Karamazov") == "the-brothers-karamazov"
    assert slug("Notes from the Underground!") == "notes-from-the-underground"
    assert slug("  Multiple   Spaces  ") == "multiple-spaces"
