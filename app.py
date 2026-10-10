import os
from contextlib import closing

from flask import Flask

from batches import service as batches_service
from batches.routes import bp as batches_bp
from db import get_connection

DATA_DIR = os.environ.get("DATA_DIR", "./data")


def create_app(data_dir=DATA_DIR):
    os.makedirs(data_dir, exist_ok=True)
    app = Flask(__name__)
    app.config["DB_PATH"] = os.path.join(data_dir, "tracker.db")

    with closing(get_connection(app.config["DB_PATH"])) as conn:
        batches_service.init_schema(conn)

    app.register_blueprint(batches_bp)

    @app.get("/")
    def index():
        return "Batch tracker is running"

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    create_app().run(host="0.0.0.0", port=port)
