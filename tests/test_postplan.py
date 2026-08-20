from gr_autopilot.drafts.format import DraftMeta
from gr_autopilot.postplan import paced_schedule

GUARD = "<!-- Edit the review above in your own words. -->"


def _draft(book_id: int, words: int, status: str = "draft", rating: int = 4):
    meta = DraftMeta(
        book_id=book_id, title=f"Book {book_id}", author="A", my_rating=rating, status=status
    )
    return meta, ("word " * words).strip() + "\n\n" + GUARD


def test_gap_covers_typing_time_at_the_given_wpm() -> None:
    # 300 words at 100 wpm is 3 minutes of typing before any editing time is added.
    [slot] = paced_schedule([_draft(1, 300)], wpm=100)
    assert slot.words == 300  # the guard comment must not count as review words
    assert slot.gap_minutes >= 3.0


def test_longer_drafts_get_more_editing_time_per_word_typed() -> None:
    slots = {s.book_id: s for s in paced_schedule([_draft(1, 40), _draft(2, 400)], wpm=100)}
    short_edit = slots[1].gap_minutes - 40 / 100
    long_edit = slots[2].gap_minutes - 400 / 100
    assert long_edit > short_edit  # heavier pieces get fussed over longer


def test_posted_drafts_are_excluded() -> None:
    slots = paced_schedule([_draft(1, 100), _draft(2, 100, status="posted")], wpm=100)
    assert [s.book_id for s in slots] == [1]


def test_schedule_is_deterministic() -> None:
    drafts = [_draft(i, 50 + i * 10) for i in range(1, 8)]
    first = [(s.book_id, s.gap_minutes, s.offset_minutes) for s in paced_schedule(drafts)]
    second = [(s.book_id, s.gap_minutes, s.offset_minutes) for s in paced_schedule(drafts)]
    assert first == second  # no wall-clock or RNG: a resumed run reproduces the same plan


def test_sittings_break_after_the_configured_run_length() -> None:
    drafts = [_draft(i, 100) for i in range(1, 6)]
    slots = paced_schedule(drafts, per_sitting=(2, 2), break_range=(30.0, 30.0))
    assert [s.sitting for s in slots] == [1, 1, 2, 2, 3]
    assert slots[1].break_after_minutes == 30.0  # break closes a full sitting
    assert slots[0].break_after_minutes == 0.0  # ...but never mid-sitting
    assert slots[-1].break_after_minutes == 0.0  # ...nor after the final post


def test_offsets_accumulate_gaps_and_breaks() -> None:
    drafts = [_draft(i, 100) for i in range(1, 4)]
    slots = paced_schedule(drafts, per_sitting=(2, 2), break_range=(30.0, 30.0))
    assert slots[0].offset_minutes == 0.0
    assert slots[1].offset_minutes == slots[0].gap_minutes
    # third post waits for the second's gap plus the 30-minute break between sittings
    assert slots[2].offset_minutes == slots[1].offset_minutes + slots[1].gap_minutes + 30.0
