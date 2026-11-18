from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, request

import db
from feedback import service

bp = Blueprint("feedback", __name__, url_prefix="/feedback")


def _connect():
    return closing(db.connect(current_app.config["DATABASE_URL"]))


@bp.get("")
def list_summaries():
    with _connect() as conn:
        return jsonify(service.all_summaries(conn))


@bp.get("/flagged")
def list_flagged():
    with _connect() as conn:
        return jsonify(service.flagged_batches(conn))


@bp.get("/<batch_code>")
def batch_summary(batch_code):
    with _connect() as conn:
        summary = service.summary_for_batch(conn, batch_code)
    if summary is None:
        return jsonify(error=f"no feedback for batch {batch_code.strip().upper()}"), 404
    return jsonify(summary)


@bp.post("")
def submit():
    # All parsing and validation lives in service.parse_feedback; a ValidationError
    # becomes a 400 in app.py, so no raw Python exception text reaches the user.
    feedback = service.parse_feedback(request.get_json(silent=True))
    with _connect() as conn:
        service.submit_feedback(conn, feedback, date.today())
        summary = service.summary_for_batch(conn, feedback["batch_code"])
    return jsonify(summary), 201
