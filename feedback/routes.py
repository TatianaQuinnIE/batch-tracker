from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, request

from db import get_connection
from feedback import service

bp = Blueprint("feedback", __name__, url_prefix="/feedback")


@bp.get("/")
def list_summaries():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        return jsonify(service.all_summaries(conn))


@bp.get("/flagged")
def list_flagged():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        return jsonify(service.flagged_batches(conn))


@bp.get("/<batch_code>")
def batch_summary(batch_code):
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        summary = service.summary_for_batch(conn, batch_code)
    if summary is None:
        return jsonify(error="no feedback for this batch"), 404
    return jsonify(summary)


@bp.post("/")
def submit():
    data = request.get_json(silent=True) or request.form
    try:
        with closing(get_connection(current_app.config["DB_PATH"])) as conn:
            service.submit_feedback(
                conn,
                data["batch_code"],
                int(data["rating"]),
                str(data.get("had_reaction", "")).lower() in ("1", "true", "yes", "on"),
                data.get("comment", ""),
                date.today(),
            )
    except KeyError as missing:
        return jsonify(error=f"missing field {missing}"), 400
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(status="created"), 201
