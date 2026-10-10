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
