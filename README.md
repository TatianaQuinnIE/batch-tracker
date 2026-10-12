# Batch Tracker

A small web app for a natural cosmetics workshop. Staff register each production **batch** (product, batch code, dates, units) and see what is expired or expiring within 30 days. Customers use the batch code printed on their label to report **feedback**, including whether they had a skin reaction. A batch is flagged when it has at least 3 reports and more than 10% of them mention a reaction.

The app is one Flask process with one SQLite file. It has two feature domains that only share the `batch_code` text, so they can be split into separate services in Assignment 2.

## Feature domains

| Domain | Package | Owns | Main logic |
|---|---|---|---|
| Batches | `batches/` | `batches` table | create batch with validation, expiry status (`expired` / `expiring_soon` / `ok`), seed loading |
| Feedback | `feedback/` | `feedback` table | submit report, reaction rate per batch, flagging rule |

`feedback/` never imports from `batches/` and never queries the `batches` table. `app.py` is the only place that knows about both: it creates the schema for each domain and registers both Blueprints. That is where the split would happen.

## Project structure

```
app.py               entry point: create_app(), reads PORT and DATA_DIR
db.py                opens the SQLite connection
seed.json            starter batches, loaded only when the table is empty
batches/             service.py (logic), routes.py (Blueprint), templates/
feedback/            service.py (logic), routes.py (Blueprint), templates/
templates/           base.html, index.html (shared layout)
tests/               unit tests (services) and route tests
Dockerfile           course template with the four TODOs filled in
ADR.md               architecture decision records
AI_USAGE.md          AI usage log
```

## Configuration

Everything is configured with environment variables. None are required.

| Variable | Default | What it does |
|---|---|---|
| `PORT` | `8000` | Port the server listens on (always on `0.0.0.0`) |
| `DATA_DIR` | `./data` (the Dockerfile sets `/data`) | Folder for the SQLite file; created on first start |
| `REACTION_ALERT_RATE` | `0.10` | Reaction rate above which a batch is flagged (with 3+ reports) |

**SQLite path:** `$DATA_DIR/tracker.db`. The schema is created on first start with `CREATE TABLE IF NOT EXISTS`, and `seed.json` is loaded only when the `batches` table is empty, so restarting never duplicates or deletes data.

## Run it on your machine

Requires Python 3.12 or newer.

```bash
git clone https://github.com/TatianaQuinnIE/batch-tracker.git
cd batch-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000. To use another port or data folder: `PORT=9000 DATA_DIR=/tmp/bt python app.py`.

## Run it with Docker

```bash
docker build -t batch-tracker .
docker run -p 8000:8000 -v batch-tracker-data:/data batch-tracker
```

Open http://localhost:8000. The named volume keeps the database when the container is removed. Another port: `docker run -e PORT=9000 -p 9000:9000 -v batch-tracker-data:/data batch-tracker`.

## Pages and endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/` | Home page |
| GET / POST | `/batches/` | Batch list and "register a batch" form |
| GET | `/batches/expiring-soon` | JSON list of batches expiring within 30 days |
| GET / POST | `/feedback/` | Customer feedback form and the workshop view |
| GET | `/feedback/flagged` | JSON list of flagged batches |
| GET | `/feedback/<batch_code>` | JSON summary for one batch (404 if no feedback) |

## Tests and coverage

```bash
pytest --cov=batches --cov=feedback --cov-report=term-missing
```

Result on 2026-10-12: **31 passed, 100% coverage** of the `batches` and `feedback` packages.

```
Name                   Stmts   Miss  Cover   Missing
----------------------------------------------------
batches/__init__.py        0      0   100%
batches/routes.py         27      0   100%
batches/service.py        44      0   100%
feedback/__init__.py       0      0   100%
feedback/routes.py        34      0   100%
feedback/service.py       40      0   100%
----------------------------------------------------
TOTAL                    145      0   100%
```

See ADR-4 in `ADR.md` for what the tests focus on and what they leave out.

## Container contract check (§7)

Output of the course checker `container/run.sh` against this repository on 2026-10-12:

```
=== SDD Assignment 1 contract check ===
Repository: /Users/tatianaquinn/Desktop/batch-tracker

==> Repository shape
  PASS  one Dockerfile, one manifest (requirements.txt)

==> Build from a clean context, no build args
  PASS  image built
  PASS  image size 50 MB

==> Start on PORT=8000 and reach it from the host
  PASS  HTTP 200 from http://localhost:8000/

==> SQLite file under DATA_DIR
  PASS  found in /data: tracker.db 

==> Data persists, and a second boot does not re-seed
  PASS  volume at /data persists
  PASS  row counts unchanged across restart: batches=4 feedback=0 

==> PORT override is honoured (not hardcoded)
  PASS  HTTP 200 from http://localhost:9123/

=== ALL CHECKS PASSED ===
Paste this output into your README as the §7 evidence.
```
