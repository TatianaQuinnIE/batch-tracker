# syntax=docker/dockerfile:1
# Batches service: batch register and expiry status.
FROM python:3.12-slim

ENV PORT=8000 \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Unprivileged user; /data is where the SQLite file lives until the SQL Server move.
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /data \
 && chown appuser:appuser /data

# Dependencies first so editing the source does not reinstall packages.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Only what the service needs to run: no tests, no .env, no local database.
COPY app.py db.py seed.json ./
COPY batches/ ./batches/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=2)" || exit 1

# One worker so schema setup on startup never runs twice at the same time.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 'app:create_app()'"]
