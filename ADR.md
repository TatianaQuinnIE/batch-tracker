# Architecture Decision Records

## 1. Backend language and framework: Python + Flask with plain sqlite3
Date: 2026-10-10
Status: Superseded by [7]
Context: The workshop (2 staff, roughly a few hundred customer feedback submissions a month) needs a small web app with HTML forms and server-rendered pages, backed by SQLite, running as one process in one container. I am most comfortable in Python and must be able to explain every line.
Decision: Python 3 with Flask 3.1, the standard-library sqlite3 module and Jinja templates (bundled with Flask). Each feature domain becomes a Flask Blueprint.
Alternatives considered: Django, rejected because its ORM, admin and migration system are far more than two small tables need and would hide the schema I have to defend in ADR-3. FastAPI, rejected because it is API-first: server-rendered forms would need extra packages plus a separate ASGI server (uvicorn), adding dependencies without a real need.
Consequences: Very few dependencies and nothing hidden, but I write the SQL and the schema creation myself. Blueprints give each domain its own module, which is where the service split in Assignment 2 will happen.

## 2. Two independent feature domains joined only by batch_code
Date: 2026-10-10
Status: Decided
Context: In Assignment 2 the app will be split into separate services, so the batch register and customer feedback must not depend on each other's code or tables.
Decision: Two packages, batches/ and feedback/, each owning its own table, schema setup, business logic (service.py) and Flask Blueprint (routes.py). The only thing that crosses the seam is the batch_code string printed on the product label; feedback never imports from batches or queries the batches table.
Alternatives considered: One shared models module with a foreign key from feedback to batches. Rejected because it makes joins easy now but ties the two domains together: splitting later would mean untangling shared code and a foreign key that cannot exist across two separate databases.
Consequences: Feedback cannot check through a database join that a batch code exists; after the split that check becomes an HTTP call to the batches service. In exchange, each package can be moved into its own service with its own SQLite file without rewriting it.

## 3. Feedback references batches by batch_code text, with no foreign key
Date: 2026-10-11
Status: Superseded by [7]
Context: Customers only know the code printed on the label, and in Assignment 2 the two tables will live in different services with separate databases.
Decision: One SQLite file (DATA_DIR/tracker.db) with two tables owned by different domains: batches (batch_code UNIQUE) and feedback (batch_code TEXT, indexed, no foreign key). Codes are stored upper-case and dates as ISO text (YYYY-MM-DD).
Alternatives considered: feedback.batch_id INTEGER REFERENCES batches(id). Rejected because customers do not know internal ids, and a foreign key cannot cross two databases once the services are split.
Consequences: The database does not stop feedback for a code that does not exist (it could arrive before the batch is registered); an index on feedback.batch_code keeps the per-batch GROUP BY fast. Splitting later means moving one table, not untangling a relationship.

## 4. Test the service logic directly, then the routes through Flask's test client
Date: 2026-10-12
Status: Decided
Context: The brief asks for at least 70% coverage on the core logic of both domains. The bugs that would actually hurt the workshop are at the boundaries: a batch exactly 30 days from expiry, a batch at exactly 10% reactions, fewer than 3 reports, seed data loading twice, and the "No, all good" answer being counted as a reaction.
Decision: Unit tests call batches/service.py and feedback/service.py directly against an in-memory SQLite database (the conn fixture) with a fixed date, so boundary cases are exact. Route tests then use Flask's test client with a temporary DATA_DIR to check redirects, validation errors, kept form values and the JSON endpoints. Coverage is measured on the batches and feedback packages (command in README).
Alternatives considered: Only end-to-end route tests, rejected because boundary values are harder to hit precisely and a failure does not point to the function that broke. Browser tests (Selenium/Playwright), rejected because they add heavy dependencies and are slow for an app with no JavaScript.
Consequences: Service logic is fully covered and the tests can move with each service in Assignment 2 unchanged. Left thinner on purpose: templates are only checked for key text, not layout, so a visual regression would not fail the suite; container behaviour is checked by run.sh instead of pytest.

## 5. No login for workshop staff in this version
Date: 2026-10-12
Status: Decided
Context: Customers must be able to report a reaction without creating an account, but the "Workshop view" and the Batches page are meant for the two workshop staff. The app runs locally for one workshop in Assignment 1.
Decision: I deliberately did not build authentication. Every page is open to anyone who can reach the app.
Alternatives considered: Flask-Login with a staff account, rejected for now because it adds a dependency, password hashing, a SECRET_KEY setting and session tests, roughly doubling the scope for a feature nobody needs while the app runs on a laptop. Hiding the staff pages behind a secret URL, rejected because it is security by obscurity.
Consequences: Batch and reaction data is visible to anyone on the network, so this must be fixed before any public deployment. The Assignment 2 split makes it easier: the batches service can sit behind staff-only access while the feedback form stays public.

## 7. Data and migrations: one SQL Server database per service, numbered SQL files and my own runner
Date: 2026-11-18
Status: Decided
Context: Assignment 2 replaces the single SQLite file of ADR-3 with one SQL Server database per service (Azure SQL serverless on Azure, one SQL Server container locally). Assignment 1 created its schema with CREATE TABLE IF NOT EXISTS on every boot, which cannot change a table that already holds data. I need versioned, forward-only migrations that run on startup, exactly once each, in a way I can explain line by line.
Decision: Each service has a migrations/ folder of numbered files (001_init.sql, then 002_..., never edited once applied) and a ~60-line runner, migrate.py. On startup, create_app() connects with retries (db.connect_with_retry), creates dbo.schema_migrations if missing, applies every file whose name is not in that table in file-name order, and inserts the file name in the same transaction as the schema change, so a migration is either fully applied and recorded or not at all. A line with only GO splits a file into batches, as in sqlcmd. The data moved with its table: 001_init.sql ports each Assignment 1 table to T-SQL (INT IDENTITY, NVARCHAR with a length, DATE instead of ISO text), and the batches seed.json is still loaded only into an empty table. The Assignment 1 SQLite data was only the seed rows plus test reports, so nothing was exported from it. The driver is pymssql, which ships as a wheel with FreeTDS inside, so the images need no system ODBC packages. Each service connects with its own login (batches_app, feedback_app) that has a user only in its own database, with db_ddladmin (to run its migrations), db_datareader and db_datawriter, not db_owner.
Alternatives considered: Alembic, rejected because it needs SQLAlchemy as well (two dependencies and an ORM layer I do not use, since all my SQL is hand-written) and its autogenerated migrations would be code I did not write. Keeping CREATE TABLE IF NOT EXISTS plus ad-hoc ALTER statements in Python, rejected because nothing would record what has already run, so a second boot could not know whether to apply a change. pyodbc with the Microsoft ODBC driver, rejected because it needs apt repositories and a larger image.
Consequences: What is lost at the seam: feedback.batch_code can no longer even be in the same database as batches.batch_code, so referential integrity is not enforced by SQL Server. It is compensated in code (the feedback service asks the batches service over HTTP, ADR-6) and deliberately not enforced on write, as in ADR-3: a customer can report on a code before staff register the batch. Migrations at startup are only safe because every Container App runs at most one replica with one gunicorn worker; at more replicas two containers could race on the same migration, and I would move migrations to a pipeline step or take an sp_getapplock lock first. Recovery plan for a bad migration in production, since there are no down-migrations: (1) a migration that fails is rolled back by its transaction and is not recorded, so the container fails to start, the old revision keeps serving and the post-deploy health check fails the run; I fix it in a new commit. (2) A migration that succeeds but is wrong is never edited: I write the next numbered migration that corrects it and deploy it through the pipeline. (3) If data was damaged, Azure SQL point-in-time restore (7 days of automatic backups by default) restores the database to a new name from just before the deploy, and I copy the affected rows back or point DATABASE_URL at it.
