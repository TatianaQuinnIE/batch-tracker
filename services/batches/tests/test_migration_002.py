"""Migration 002 applied to a database that already has data, as it was on Azure.

A separate database is migrated with 001 only, given rows (seed and a staff-added
batch), then upgraded with the real migrations folder. The rows must come through
unchanged and read as not recalled, and the upgrade must be recorded once.
"""
import os
import shutil
from contextlib import closing
from datetime import date

import pymssql
import pytest

import db
from batches import service
from migrate import apply_migrations

UPGRADE_DB = "batches_upgrade_test"


@pytest.fixture
def database_at_001(tmp_path):
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("TEST_DATABASE_URL is not set (see README: Running the tests)")
    drop = (f"IF DB_ID('{UPGRADE_DB}') IS NOT NULL BEGIN ALTER DATABASE {UPGRADE_DB} "
            f"SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE {UPGRADE_DB}; END")
    with closing(pymssql.connect(**db.parse_database_url(admin_url), autocommit=True)) as admin:
        admin.cursor().execute(drop)
        admin.cursor().execute(f"CREATE DATABASE {UPGRADE_DB}")
    from app import MIGRATIONS_DIR

    only_001 = tmp_path / "migrations"
    only_001.mkdir()
    shutil.copy(MIGRATIONS_DIR / "001_init.sql", only_001)
    url = admin_url.rsplit("/", 1)[0] + "/" + UPGRADE_DB
    with closing(db.connect(url)) as conn:
        assert apply_migrations(conn, only_001) == ["001_init.sql"]
    yield url, MIGRATIONS_DIR
    with closing(pymssql.connect(**db.parse_database_url(admin_url), autocommit=True)) as admin:
        admin.cursor().execute(drop)


def test_002_keeps_existing_rows_and_reads_them_as_not_recalled(database_at_001):
    url, migrations_dir = database_at_001
    with closing(db.connect(url)) as conn:
        cursor = conn.cursor()
        # Rows written by the 001 code, which names only its own five columns.
        cursor.execute(
            "INSERT INTO dbo.batches (batch_code, product, produced_on, expires_on, quantity) "
            "VALUES ('LAV-2607', N'Lavender soap bar', '2026-07-01', '2027-07-01', 120), "
            "('ROS-2608', N'Rosehip face oil', '2026-08-15', '2026-11-05', 45)")
        conn.commit()
        cursor.execute("SELECT id, batch_code, product, produced_on, expires_on, quantity "
                       "FROM dbo.batches ORDER BY id")
        before = cursor.fetchall()

        assert apply_migrations(conn, migrations_dir) == ["002_batch_recall.sql"]
        assert apply_migrations(conn, migrations_dir) == []

        cursor.execute("SELECT id, batch_code, product, produced_on, expires_on, quantity "
                       "FROM dbo.batches ORDER BY id")
        assert cursor.fetchall() == before
        batches = service.list_batches(conn, date(2026, 11, 21))
        assert [(b["recalled_on"], b["recall_reason"]) for b in batches] == [(None, None)] * 2
        cursor.execute("SELECT version FROM dbo.schema_migrations ORDER BY version")
        assert [r["version"] for r in cursor.fetchall()] == ["001_init.sql", "002_batch_recall.sql"]


def test_code_from_before_002_still_works_after_it(database_at_001):
    """Expand only: the previous revision keeps serving while the new one rolls out."""
    url, migrations_dir = database_at_001
    with closing(db.connect(url)) as conn:
        apply_migrations(conn, migrations_dir)
        cursor = conn.cursor()
        old_columns = "batch_code, product, produced_on, expires_on, quantity"
        cursor.execute(f"INSERT INTO dbo.batches ({old_columns}) "
                       "VALUES ('OLD-1', N'Old code soap', '2026-01-01', '2027-01-01', 3)")
        conn.commit()
        cursor.execute(f"SELECT {old_columns} FROM dbo.batches WHERE batch_code = 'OLD-1'")
        assert cursor.fetchone()["quantity"] == 3
