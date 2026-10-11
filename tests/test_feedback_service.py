from datetime import date

import pytest

from feedback import service

DAY = date(2026, 10, 11)


def test_reaction_rate_with_no_reports_is_zero():
    assert service.reaction_rate(0, 0) == 0.0


def test_reaction_rate_divides_reactions_by_reports():
    assert service.reaction_rate(4, 1) == 0.25


def test_not_flagged_below_minimum_reports():
    assert service.is_flagged(2, 2) is False


def test_flagged_above_threshold():
    assert service.is_flagged(10, 2) is True


def test_not_flagged_at_threshold():
    assert service.is_flagged(10, 1) is False


def test_submit_feedback_rejects_bad_rating(conn):
    with pytest.raises(ValueError):
        service.submit_feedback(conn, "A", 6, False, "", DAY)


def test_submit_feedback_rejects_empty_code(conn):
    with pytest.raises(ValueError):
        service.submit_feedback(conn, "   ", 3, False, "", DAY)


def test_summary_for_batch(conn):
    service.submit_feedback(conn, "lav-01", 5, False, "lovely", DAY)
    service.submit_feedback(conn, "LAV-01", 2, True, "itchy", DAY)
    summary = service.summary_for_batch(conn, "lav-01")
    assert summary["reports"] == 2
    assert summary["reactions"] == 1
    assert summary["reaction_rate"] == 0.5
    assert summary["average_rating"] == 3.5
    assert summary["flagged"] is False


def test_summary_for_unknown_batch_is_none(conn):
    assert service.summary_for_batch(conn, "NOPE") is None


def test_flagged_batches_lists_only_flagged(conn):
    for _ in range(3):
        service.submit_feedback(conn, "BAD", 1, True, "", DAY)
    for _ in range(3):
        service.submit_feedback(conn, "GOOD", 5, False, "", DAY)
    flagged = service.flagged_batches(conn)
    assert [s["batch_code"] for s in flagged] == ["BAD"]
    assert len(service.all_summaries(conn)) == 2
