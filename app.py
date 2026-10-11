import os
from contextlib import closing

from flask import Flask, render_template

from batches import service as batches_service
from batches.routes import bp as batches_bp
from db import get_connection
from feedback import service as feedback_service
from feedback.routes import bp as feedback_bp

DATA_DIR = os.environ.get("DATA_DIR", "./data")
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed.json")


def create_app(data_dir=DATA_DIR):
    os.makedirs(data_dir, exist_ok=True)
    app = Flask(__name__)
    app.config["DB_PATH"] = os.path.join(data_dir, "tracker.db")

    with closing(get_connection(app.config["DB_PATH"])) as conn:
        batches_service.init_schema(conn)
        batches_service.seed_if_empty(conn, SEED_PATH)
        feedback_service.init_schema(conn)

    app.register_blueprint(batches_bp)
    app.register_blueprint(feedback_bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    create_app().run(host="0.0.0.0", port=port)
