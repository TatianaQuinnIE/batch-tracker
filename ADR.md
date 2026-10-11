# Architecture Decision Records

## 1. Backend language and framework: Python + Flask with plain sqlite3
Date: 2026-10-10
Status: Decided
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
Status: Decided
Context: Customers only know the code printed on the label, and in Assignment 2 the two tables will live in different services with separate databases.
Decision: One SQLite file (DATA_DIR/tracker.db) with two tables owned by different domains: batches (batch_code UNIQUE) and feedback (batch_code TEXT, indexed, no foreign key). Codes are stored upper-case and dates as ISO text (YYYY-MM-DD).
Alternatives considered: feedback.batch_id INTEGER REFERENCES batches(id). Rejected because customers do not know internal ids, and a foreign key cannot cross two databases once the services are split.
Consequences: The database does not stop feedback for a code that does not exist (it could arrive before the batch is registered); an index on feedback.batch_code keeps the per-batch GROUP BY fast. Splitting later means moving one table, not untangling a relationship.
