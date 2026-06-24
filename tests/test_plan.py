from gr_autopilot.actions.plan import PlanItem, is_unfilled, parse_plan


def test_parse_plan_reads_rows_with_optional_header() -> None:
    text = (
        "action,book_id,value\n"
        "ensure_shelf,,existential-classics\n"
        "set_shelf,436982,existential-classics\n"
        "set_rating,28187,4\n"
        "set_date,5129,2024/03/01\n"
    )
    items = parse_plan(text)
    assert items == [
        PlanItem("ensure_shelf", None, "existential-classics"),
        PlanItem("set_shelf", 436982, "existential-classics"),
        PlanItem("set_rating", 28187, "4"),
        PlanItem("set_date", 5129, "2024/03/01"),
    ]


def test_parse_plan_skips_blank_and_comment_lines() -> None:
    text = "set_rating,1,5\n\n# fill these in later\nset_date,2,2024/01/01\n"
    items = parse_plan(text)
    assert [i.action for i in items] == ["set_rating", "set_date"]


def test_is_unfilled_flags_blank_rating_and_date_placeholders() -> None:
    assert is_unfilled(PlanItem("set_rating", 11, ""))  # user hasn't filled the star yet
    assert is_unfilled(PlanItem("set_date", 11, ""))
    assert not is_unfilled(PlanItem("set_rating", 11, "4"))
    assert not is_unfilled(PlanItem("set_shelf", 11, "existential-classics"))
    assert not is_unfilled(PlanItem("ensure_shelf", None, "existential-classics"))


def test_parse_plan_rejects_unknown_action() -> None:
    try:
        parse_plan("follow_user,,someone\n")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown/unsafe action")
