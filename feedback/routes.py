from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from db import get_connection
from feedback import service

bp = Blueprint("feedback", __name__, url_prefix="/feedback", template_folder="templates")


def _render_page(conn, error=None, status=200):
    summaries = service.all_summaries(conn)
    return render_template("feedback.html", summaries=summaries, error=error), status


@bp.get("/")
def list_summaries():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        return _render_page(conn)


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
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        try:
            service.submit_feedback(
                conn,
                request.form["batch_code"],
                int(request.form["rating"]),
                "had_reaction" in request.form,
                request.form.get("comment", ""),
                date.today(),
            )
        except KeyError as missing:
            return _render_page(conn, f"missing field {missing}", 400)
        except ValueError as err:
            return _render_page(conn, str(err), 400)
    return redirect(url_for("feedback.list_summaries"))
