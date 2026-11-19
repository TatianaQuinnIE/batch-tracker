"""Tests run against a real SQL Server, never against Azure SQL.

TEST_DATABASE_URL points at the server's master database with a login allowed to
create databases, e.g. mssql://sa:LocalOnly-Sa-2026@localhost:1433/master
(docker compose up -d db locally; a throwaway SQL Server container in CI).
A fresh feedback_test database is created once per test run and migrated with the
real migration files, so the tests also check that the migrations apply.
"""
import os
from contextlib import closing
from pathlib import Path

import pymssql
import pytest
from stub_batches import StubBatches

import db
from migrate import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
TEST_DB = "feedback_test"


@pytest.fixture(scope="session")
def database_url():
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_URL is not set (see README: Running the tests)")
    with closing(pymssql.connect(**db.parse_database_url(admin_url), autocommit=True)) as admin:
        cursor = admin.cursor()
        cursor.execute(f"IF DB_ID('{TEST_DB}') IS NOT NULL "
                       f"BEGIN ALTER DATABASE {TEST_DB} SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
                       f"DROP DATABASE {TEST_DB}; END")
        cursor.execute(f"CREATE DATABASE {TEST_DB}")
    url = admin_url.rsplit("/", 1)[0] + "/" + TEST_DB
    with closing(db.connect(url)) as conn:
        apply_migrations(conn, MIGRATIONS_DIR)
    return url


@pytest.fixture
def conn(database_url):
    """A connection to an empty feedback table."""
    with closing(db.connect(database_url)) as connection:
        connection.cursor().execute("DELETE FROM dbo.feedback")
        connection.commit()
        yield connection


@pytest.fixture
def batches_stub():
    """A stub batches service on a random local port (see stub_batches.py)."""
    stub = StubBatches().start()
    yield stub
    stub.stop()


@pytest.fixture
def client(conn, database_url, batches_stub):
    """The Flask app on an empty feedback table, calling the stub batches service."""
    from app import create_app

    app = create_app(database_url, connect_delays=())
    app.config["BATCHES_URL"] = batches_stub.url
    app.config["BATCHES_TIMEOUT_S"] = 0.5
    return app.test_client()
