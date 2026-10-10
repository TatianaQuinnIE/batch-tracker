import os

from flask import Flask

DATA_DIR = os.environ.get("DATA_DIR", "./data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")


def create_app():
    os.makedirs(DATA_DIR, exist_ok=True)
    app = Flask(__name__)

    @app.get("/")
    def index():
        return "Batch tracker is running"

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    create_app().run(host="0.0.0.0", port=port)
