from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, request

from batches import service
from db import get_connection

bp = Blueprint("batches", __name__, url_prefix="/batches")


@bp.get("/")
def list_all():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        return jsonify(service.list_batches(conn, date.today()))


@bp.get("/expiring-soon")
def list_expiring_soon():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        return jsonify(service.expiring_soon(conn, date.today()))


@bp.post("/")
def create():
    data = request.get_json(silent=True) or request.form
    try:
        with closing(get_connection(current_app.config["DB_PATH"])) as conn:
            service.create_batch(
                conn,
                data["batch_code"],
                data["product"],
                date.fromisoformat(data["produced_on"]),
                date.fromisoformat(data["expires_on"]),
                int(data["quantity"]),
            )
    except KeyError as missing:
        return jsonify(error=f"missing field {missing}"), 400
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(status="created"), 201
