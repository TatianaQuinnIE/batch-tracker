# syntax=docker/dockerfile:1
# Batches service: batch register and expiry status.
FROM python:3.12-slim

ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Unprivileged user: the process never runs as root inside the container.
RUN useradd --create-home --uid 10001 appuser

# Dependencies first so editing the source does not reinstall packages.
# pymssql ships as a wheel with FreeTDS inside, so no apt packages are needed.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Only what the service needs to run: no tests, no .env, no credentials.
COPY app.py db.py migrate.py seed.json ./
COPY batches/ ./batches/
COPY migrations/ ./migrations/

USER appuser

EXPOSE 8000

# Start period covers a database that is still resuming from pause.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=4)" || exit 1

# One worker: migrations run in create_app(), so they must never run twice at once.
# --timeout 120: loading the app may wait up to ~90 s for a paused database.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 'app:create_app()'"]
