from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, request

from db import get_connection
from feedback import service

bp = Blueprint("feedback", __name__, url_prefix="/feedback")


def _connect():
    return closing(get_connection(current_app.config["DB_PATH"]))


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
        return jsonify(error="no feedback for this batch"), 404
    return jsonify(summary)


@bp.post("")
def submit():
    body = request.get_json(silent=True) or {}
    with _connect() as conn:
        try:
            service.submit_feedback(
                conn,
                body["batch_code"],
                int(body["rating"]),
                bool(body.get("had_reaction", False)),
                body.get("comment", ""),
                date.today(),
            )
            summary = service.summary_for_batch(conn, body["batch_code"])
        except KeyError as missing:
            return jsonify(error=f"missing field {missing}"), 400
        except (TypeError, ValueError) as err:
            return jsonify(error=str(err)), 400
    return jsonify(summary), 201
