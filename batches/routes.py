from contextlib import closing
from datetime import date

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from batches import service
from db import get_connection

bp = Blueprint("batches", __name__, url_prefix="/batches", template_folder="templates")


def _render_page(conn, error=None, status=200):
    batches = service.list_batches(conn, date.today())
    return render_template("batches.html", batches=batches, error=error), status


@bp.get("/")
def list_all():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        return _render_page(conn)


@bp.get("/expiring-soon")
def list_expiring_soon():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        return jsonify(service.expiring_soon(conn, date.today()))


@bp.post("/")
def create():
    with closing(get_connection(current_app.config["DB_PATH"])) as conn:
        try:
            service.create_batch(
                conn,
                request.form["batch_code"],
                request.form["product"],
                date.fromisoformat(request.form["produced_on"]),
                date.fromisoformat(request.form["expires_on"]),
                int(request.form["quantity"]),
            )
        except KeyError as missing:
            return _render_page(conn, f"missing field {missing}", 400)
        except ValueError as err:
            return _render_page(conn, str(err), 400)
    return redirect(url_for("batches.list_all"))
