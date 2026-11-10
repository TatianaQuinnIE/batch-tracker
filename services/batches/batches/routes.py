from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, request

from batches import service
from db import get_connection

bp = Blueprint("batches", __name__, url_prefix="/batches")


def _connect():
    return closing(get_connection(current_app.config["DB_PATH"]))


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
    if batch is None:
        return jsonify(error=f"batch {batch_code.upper()} not found"), 404
    return jsonify(batch)


@bp.post("")
def create():
    body = request.get_json(silent=True) or {}
    with _connect() as conn:
        try:
            service.create_batch(
                conn,
                body["batch_code"],
                body["product"],
                date.fromisoformat(body["produced_on"]),
                date.fromisoformat(body["expires_on"]),
                int(body["quantity"]),
            )
            batch = service.get_batch(conn, body["batch_code"], date.today())
        except KeyError as missing:
            return jsonify(error=f"missing field {missing}"), 400
        except (TypeError, ValueError) as err:
            return jsonify(error=str(err)), 400
    return jsonify(batch), 201
