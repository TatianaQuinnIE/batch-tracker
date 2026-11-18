from datetime import date

import pytest

from feedback import service

DAY = date(2026, 10, 11)

VALID = {"batch_code": " ros-2608 ", "rating": 4, "had_reaction": False, "comment": " fine "}


def submit(conn, code, rating, had_reaction, comment=""):
    service.submit_feedback(conn, service.parse_feedback(
        {"batch_code": code, "rating": rating, "had_reaction": had_reaction, "comment": comment}), DAY)


# --- reaction rate and the flagging rule (boundaries) --------------------------

def test_reaction_rate_with_no_reports_is_zero():
    assert service.reaction_rate(0, 0) == 0.0


def test_reaction_rate_divides_reactions_by_reports():
    assert service.reaction_rate(4, 1) == 0.25


def test_not_flagged_below_minimum_reports():
    assert service.is_flagged(2, 2) is False


def test_flagged_at_minimum_reports_with_reactions():
    assert service.is_flagged(3, 1) is True


def test_flagged_above_threshold():
    assert service.is_flagged(10, 2) is True


def test_not_flagged_at_threshold():
    assert service.is_flagged(10, 1) is False


# --- parse_feedback: the input gaps found in the Assignment 1 review -----------

def test_parse_feedback_cleans_values():
    assert service.parse_feedback(VALID) == {
        "batch_code": "ROS-2608", "rating": 4, "had_reaction": False, "comment": "fine"}


def test_parse_feedback_comment_is_optional():
    body = {k: v for k, v in VALID.items() if k != "comment"}
    assert service.parse_feedback(body)["comment"] == ""


@pytest.mark.parametrize("field", ["batch_code", "rating"])
def test_parse_feedback_missing_field_names_it(field):
    body = {k: v for k, v in VALID.items() if k != field}
    with pytest.raises(service.ValidationError, match=f"^{field} is required$"):
        service.parse_feedback(body)


def test_parse_feedback_rejects_whitespace_only_code():
    with pytest.raises(service.ValidationError, match="^batch_code is required$"):
        service.parse_feedback({**VALID, "batch_code": "   "})


@pytest.mark.parametrize("rating", ["five", "4.5", True])
def test_parse_feedback_rejects_non_numeric_rating(rating):
    with pytest.raises(service.ValidationError, match="whole number from 1 to 5"):
        service.parse_feedback({**VALID, "rating": rating})


@pytest.mark.parametrize("rating", [0, 6])
def test_parse_feedback_rejects_rating_out_of_range(rating):
    with pytest.raises(service.ValidationError, match="between 1 and 5"):
        service.parse_feedback({**VALID, "rating": rating})


@pytest.mark.parametrize("rating", [1, 5, "3"])
def test_parse_feedback_accepts_rating_bounds_and_numeric_text(rating):
    assert service.parse_feedback({**VALID, "rating": rating})["rating"] == int(rating)


@pytest.mark.parametrize("had_reaction", [None, "false", "on", 0])
def test_parse_feedback_needs_a_real_boolean_for_reaction(had_reaction):
    # In Assignment 1, bool("false") would have counted as a reaction.
    with pytest.raises(service.ValidationError, match="had_reaction"):
        service.parse_feedback({**VALID, "had_reaction": had_reaction})


def test_parse_feedback_rejects_too_long_comment():
    with pytest.raises(service.ValidationError, match="at most 1000"):
        service.parse_feedback({**VALID, "comment": "x" * 1001})


def test_parse_feedback_rejects_non_object_body():
    with pytest.raises(service.ValidationError, match="JSON object"):
        service.parse_feedback("rating=5")


# --- storage and aggregates (SQL Server) -----------------------------------------

def test_summary_for_batch(conn):
    submit(conn, "lav-01", 5, False, "lovely")
    submit(conn, "LAV-01", 2, True, "itchy")
    assert service.summary_for_batch(conn, " lav-01 ") == {
        "batch_code": "LAV-01",
        "reports": 2,
        "reactions": 1,
        "reaction_rate": 0.5,
        "average_rating": 3.5,   # AVG of an INT column would give 3 in SQL Server
        "flagged": False,
    }


def test_summary_for_unknown_batch_is_none(conn):
    assert service.summary_for_batch(conn, "NOPE") is None


def test_flagged_batches_lists_only_flagged(conn):
    for _ in range(3):
        submit(conn, "BAD", 1, True)
    for _ in range(3):
        submit(conn, "GOOD", 5, False)
    assert [s["batch_code"] for s in service.flagged_batches(conn)] == ["BAD"]
    assert [s["batch_code"] for s in service.all_summaries(conn)] == ["BAD", "GOOD"]
