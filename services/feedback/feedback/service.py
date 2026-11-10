import os

REACTION_ALERT_RATE = float(os.environ.get("REACTION_ALERT_RATE", "0.10"))
MIN_REPORTS_FOR_ALERT = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_code TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    had_reaction INTEGER NOT NULL CHECK (had_reaction IN (0, 1)),
    comment TEXT NOT NULL DEFAULT '',
    submitted_on TEXT NOT NULL
)
"""

INDEX = "CREATE INDEX IF NOT EXISTS idx_feedback_batch_code ON feedback (batch_code)"


def init_schema(conn):
    conn.execute(SCHEMA)
    conn.execute(INDEX)
    conn.commit()


def reaction_rate(reports, reactions):
    if reports == 0:
        return 0.0
    return reactions / reports


def is_flagged(reports, reactions):
    if reports < MIN_REPORTS_FOR_ALERT:
        return False
    return reaction_rate(reports, reactions) > REACTION_ALERT_RATE


def submit_feedback(conn, batch_code, rating, had_reaction, comment, submitted_on):
    batch_code = batch_code.strip().upper()
    if not batch_code:
        raise ValueError("batch code is required")
    if rating < 1 or rating > 5:
        raise ValueError("rating must be between 1 and 5")
    conn.execute(
        "INSERT INTO feedback (batch_code, rating, had_reaction, comment, submitted_on) "
        "VALUES (?, ?, ?, ?, ?)",
        (batch_code, rating, 1 if had_reaction else 0, comment.strip(), submitted_on.isoformat()),
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


SUMMARY_QUERY = (
    "SELECT batch_code, COUNT(*) AS reports, SUM(had_reaction) AS reactions, "
    "AVG(rating) AS average_rating FROM feedback"
)


def summary_for_batch(conn, batch_code):
    row = conn.execute(
        SUMMARY_QUERY + " WHERE batch_code = ? GROUP BY batch_code",
        (batch_code.strip().upper(),),
    ).fetchone()
    if row is None:
        return None
    return _summary(row)


def all_summaries(conn):
    rows = conn.execute(SUMMARY_QUERY + " GROUP BY batch_code ORDER BY batch_code").fetchall()
    return [_summary(row) for row in rows]


def flagged_batches(conn):
    return [s for s in all_summaries(conn) if s["flagged"]]
