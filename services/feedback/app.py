import logging
import os
import time
from contextlib import closing
from pathlib import Path

import pymssql
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

import db
from feedback import service
from feedback.routes import bp
from migrate import apply_migrations

HERE = Path(__file__).resolve().parent
MIGRATIONS_DIR = HERE / "migrations"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("feedback")


def create_app(database_url=None, connect_delays=db.STARTUP_RETRY_DELAYS_S):
    app = Flask(__name__)
    app.config["DATABASE_URL"] = database_url or os.environ.get("DATABASE_URL", "")
    app.config["ALLOWED_ORIGIN"] = os.environ.get("ALLOWED_ORIGIN", "http://localhost:8080")
    app.config["VERSION"] = os.environ.get("GIT_SHA", "dev")
    # Not called yet: the cross-seam call to the batches service comes in a later commit.
    app.config["BATCHES_URL"] = os.environ.get("BATCHES_URL", "http://localhost:8001")
    app.config["BATCHES_TIMEOUT_S"] = float(os.environ.get("BATCHES_TIMEOUT_S", "2"))

    # Startup: wait for the database (it may be resuming from pause), then apply
    # pending migrations. Feedback has no seed data. Max one replica and one gunicorn worker,
    # so this never runs twice at the same time.
    with closing(db.connect_with_retry(app.config["DATABASE_URL"], connect_delays)) as conn:
        apply_migrations(conn, MIGRATIONS_DIR)

    app.register_blueprint(bp)

    @app.before_request
    def start_timer():
        g.started = time.perf_counter()

    @app.after_request
    def cors_and_log(response):
        # Only the UI's origin may call this API from a browser.
        response.headers["Access-Control-Allow-Origin"] = app.config["ALLOWED_ORIGIN"]
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"
        duration_ms = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
        log.info("%s %s %s %.1fms", request.method, request.path, response.status_code, duration_ms)
        return response

    @app.errorhandler(service.ValidationError)
    def bad_input(err):
        return jsonify(error=str(err)), 400

    @app.errorhandler(pymssql.OperationalError)
    def database_unavailable(err):
        log.warning("database unavailable: %s", str(err).splitlines()[0])
        return jsonify(error="the database is not available right now, try again in a minute"), 503

    @app.errorhandler(HTTPException)
    def http_error(err):
        return jsonify(error=err.description), err.code

    @app.errorhandler(Exception)
    def unexpected(err):
        log.exception("unhandled error on %s %s", request.method, request.path)
        return jsonify(error="internal error"), 500

    @app.get("/health")
    def health():
        # 200 only if this service can both read and write its own database.
        try:
            with closing(db.connect(app.config["DATABASE_URL"], login_timeout=5)) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE dbo.health_check SET checked_at = SYSUTCDATETIME() WHERE id = 1")
                cursor.execute("SELECT COUNT(*) AS n FROM dbo.feedback")
                cursor.fetchone()
                conn.commit()
        except Exception as err:
            log.warning("health check failed: %s", str(err).splitlines()[0])
            return jsonify(status="error", db="unreachable", version=app.config["VERSION"]), 503
        return jsonify(status="ok", db="ok", version=app.config["VERSION"])

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
