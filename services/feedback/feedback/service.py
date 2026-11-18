"""Customer feedback: validation, storage, reaction rate and flagging. No Flask in here."""
import os

REACTION_ALERT_RATE = float(os.environ.get("REACTION_ALERT_RATE", "0.10"))
MIN_REPORTS_FOR_ALERT = 3
BATCH_CODE_MAX = 40
COMMENT_MAX = 1000


class ValidationError(ValueError):
    """Input the user can fix. The message is safe to show as it is."""


def parse_feedback(body):
    """Turn a JSON body into clean values, or raise ValidationError."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")

    batch_code = str(body.get("batch_code") or "").strip().upper()
    if not batch_code:
        raise ValidationError("batch_code is required")
    if len(batch_code) > BATCH_CODE_MAX:
        raise ValidationError(f"batch_code must be at most {BATCH_CODE_MAX} characters")

    rating = body.get("rating")
    if rating is None or str(rating).strip() == "":
        raise ValidationError("rating is required")
    if isinstance(rating, bool):
        raise ValidationError("rating must be a whole number from 1 to 5")
    try:
        rating = int(str(rating).strip())
    except ValueError:
        raise ValidationError("rating must be a whole number from 1 to 5") from None
    if rating < 1 or rating > 5:
        raise ValidationError("rating must be between 1 and 5")

    # Must be a real JSON boolean: in Assignment 1, bool("false") counted as a reaction.
    had_reaction = body.get("had_reaction")
    if not isinstance(had_reaction, bool):
        raise ValidationError("had_reaction is required and must be true or false")

    comment = body.get("comment") or ""
    if not isinstance(comment, str):
        raise ValidationError("comment must be text")
    comment = comment.strip()
    if len(comment) > COMMENT_MAX:
        raise ValidationError(f"comment must be at most {COMMENT_MAX} characters")

    return {"batch_code": batch_code, "rating": rating,
            "had_reaction": had_reaction, "comment": comment}


def reaction_rate(reports, reactions):
    if reports == 0:
        return 0.0
    return reactions / reports


def is_flagged(reports, reactions):
    if reports < MIN_REPORTS_FOR_ALERT:
        return False
    return reaction_rate(reports, reactions) > REACTION_ALERT_RATE


def submit_feedback(conn, feedback, submitted_on):
    """Insert a report already checked by parse_feedback."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO dbo.feedback (batch_code, rating, had_reaction, comment, submitted_on) "
        "VALUES (%s, %s, %s, %s, %s)",
        (feedback["batch_code"], feedback["rating"], feedback["had_reaction"],
         feedback["comment"], submitted_on),
    )
    conn.commit()


def _summary(row):
    reports = row["reports"]
    reactions = row["reactions"]
    return {
        "batch_code": row["batch_code"],
        "reports": reports,
        "reactions": reactions,
        "reaction_rate": round(reaction_rate(reports, reactions), 2),
        "average_rating": round(row["average_rating"], 1),
        "flagged": is_flagged(reports, reactions),
    }


# SQL Server cannot SUM a BIT column, and AVG of an INT column is an INT
# (AVG of 5 and 2 would be 3), so both are cast first.
SUMMARY_QUERY = (
    "SELECT batch_code, COUNT(*) AS reports, "
    "SUM(CAST(had_reaction AS INT)) AS reactions, "
    "AVG(CAST(rating AS FLOAT)) AS average_rating FROM dbo.feedback"
)


def summary_for_batch(conn, batch_code):
    cursor = conn.cursor()
    cursor.execute(
        SUMMARY_QUERY + " WHERE batch_code = %s GROUP BY batch_code",
        (batch_code.strip().upper(),),
    )
    row = cursor.fetchone()
    return None if row is None else _summary(row)


def all_summaries(conn):
    cursor = conn.cursor()
    cursor.execute(SUMMARY_QUERY + " GROUP BY batch_code ORDER BY batch_code")
    return [_summary(row) for row in cursor.fetchall()]


def flagged_batches(conn):
    return [s for s in all_summaries(conn) if s["flagged"]]
