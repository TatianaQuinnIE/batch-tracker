from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, request

import db
from batches import service

bp = Blueprint("batches", __name__, url_prefix="/batches")


def _connect():
    return closing(db.connect(current_app.config["DATABASE_URL"]))


@bp.get("")
def list_all():
    with _connect() as conn:
        return jsonify(service.list_batches(conn, date.today()))


@bp.get("/expiring-soon")
def list_expiring_soon():
    with _connect() as conn:
        return jsonify(service.expiring_soon(conn, date.today()))


@bp.get("/<batch_code>")
def get_one(batch_code):
    with _connect() as conn:
        batch = service.get_batch(conn, batch_code, date.today())
    return _not_found(batch_code) if batch is None else jsonify(batch)


@bp.post("")
def create():
    # All parsing and validation lives in service.parse_new_batch; a ValidationError
    # becomes a 400 in app.py, so no raw Python exception text reaches the user.
    batch = service.parse_new_batch(request.get_json(silent=True))
    with _connect() as conn:
        service.create_batch(conn, batch)
        created = service.get_batch(conn, batch["batch_code"], date.today())
    return jsonify(created), 201


def _not_found(batch_code):
    return jsonify(error=f"batch {service.normalise_code(batch_code)} not found"), 404


@bp.post("/<batch_code>/recall")
def recall(batch_code):
    reason = service.parse_recall(request.get_json(silent=True))
    with _connect() as conn:
        batch = service.recall_batch(conn, batch_code, reason, date.today())
    return _not_found(batch_code) if batch is None else jsonify(batch)

