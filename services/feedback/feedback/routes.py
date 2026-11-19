from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, request

import db
from feedback import batches_client, service

bp = Blueprint("feedback", __name__, url_prefix="/feedback")

UNAVAILABLE_NOTICE = ("Batch details are unavailable right now (the batches service did not answer). "
                      "Feedback is shown without product names or expiry dates.")


def _connect():
    return closing(db.connect(current_app.config["DATABASE_URL"]))


def _batches_url():
    return current_app.config["BATCHES_URL"]


def _timeout_s():
    return current_app.config["BATCHES_TIMEOUT_S"]


def _degraded(err):
    current_app.logger.warning("batches service unavailable, degrading: %s", err)
    return {"batches_service": "unavailable", "notice": UNAVAILABLE_NOTICE}


def _with_batch_list(summaries):
    """Cross-seam flow for lists: one GET /batches, then join in code by batch_code.

    If batches does not answer within BATCHES_TIMEOUT_S, the summaries from this
    service's own database are still returned, with batch = null and a notice.
    """
    try:
        by_code = batches_client.list_batches(_batches_url(), _timeout_s())
    except batches_client.BatchesUnavailable as err:
        return {"summaries": [{**s, "batch": None} for s in summaries], **_degraded(err)}
    return {
        "summaries": [{**s, "batch": batches_client.batch_details(by_code.get(s["batch_code"]))}
                      for s in summaries],
        "batches_service": "ok",
        "notice": None,
    }


def _with_one_batch(summary):
    """Cross-seam flow for one summary: GET /batches/{code}."""
    try:
        batch = batches_client.get_batch(_batches_url(), summary["batch_code"], _timeout_s())
    except batches_client.BatchesUnavailable as err:
        return {**summary, "batch": None, **_degraded(err)}
    return {**summary, "batch": batches_client.batch_details(batch),
            "batches_service": "ok", "notice": None}


@bp.get("")
def list_summaries():
    with _connect() as conn:
        summaries = service.all_summaries(conn)
    return jsonify(_with_batch_list(summaries))


@bp.get("/flagged")
def list_flagged():
    with _connect() as conn:
        flagged = service.flagged_batches(conn)
    return jsonify(_with_batch_list(flagged))


@bp.get("/<batch_code>")
def batch_summary(batch_code):
    with _connect() as conn:
        summary = service.summary_for_batch(conn, batch_code)
    if summary is None:
        return jsonify(error=f"no feedback for batch {batch_code.strip().upper()}"), 404
    return jsonify(_with_one_batch(summary))


@bp.post("")
def submit():
    # All parsing and validation lives in service.parse_feedback; a ValidationError
    # becomes a 400 in app.py, so no raw Python exception text reaches the user.
    # The batch code is not checked against batches before saving (ADR-6, ADR-7): a
    # report must never be lost because the batches service is asleep or down.
    feedback = service.parse_feedback(request.get_json(silent=True))
    with _connect() as conn:
        service.submit_feedback(conn, feedback, date.today())
        summary = service.summary_for_batch(conn, feedback["batch_code"])
    return jsonify(_with_one_batch(summary)), 201
