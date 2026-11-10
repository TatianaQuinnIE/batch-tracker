import logging
import os
import time
from contextlib import closing

from flask import Flask, g, jsonify, request

from batches import service
from batches.routes import bp
from db import get_connection

DATA_DIR = os.environ.get("DATA_DIR", "./data")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:8080")
VERSION = os.environ.get("GIT_SHA", "dev")
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("batches")


def create_app(data_dir=DATA_DIR):
    os.makedirs(data_dir, exist_ok=True)
    app = Flask(__name__)
    app.config["DB_PATH"] = os.path.join(data_dir, "batches.db")

    with closing(get_connection(app.config["DB_PATH"])) as conn:
        service.init_schema(conn)
        service.seed_if_empty(conn, SEED_PATH)

    app.register_blueprint(bp)

    @app.before_request
    def start_timer():
        g.started = time.perf_counter()

    @app.after_request
    def cors_and_log(response):
        response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        duration_ms = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
        log.info("%s %s %s %.1fms", request.method, request.path, response.status_code, duration_ms)
        return response

    @app.get("/health")
    def health():
        try:
            with closing(get_connection(app.config["DB_PATH"])) as conn:
                conn.execute("SELECT COUNT(*) FROM batches").fetchone()
        except Exception:
            return jsonify(status="error", db="unreachable", version=VERSION), 503
        return jsonify(status="ok", db="ok", version=VERSION)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    create_app().run(host="0.0.0.0", port=port)
