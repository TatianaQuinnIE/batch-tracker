from contextlib import closing

import pymssql
import pytest

import db
from migrate import apply_migrations, migration_files, split_batches


def test_split_batches_on_go_lines_only():
    sql = "ALTER TABLE t ADD c INT;\nGO\nUPDATE t SET c = 1; -- GOOD\n  go  \n"
    assert split_batches(sql) == ["ALTER TABLE t ADD c INT;", "UPDATE t SET c = 1; -- GOOD"]


def test_migration_files_are_sorted_by_number(tmp_path):
    for name in ["010_c.sql", "002_b.sql", "001_a.sql"]:
        (tmp_path / name).write_text("SELECT 1")
    assert [p.name for p in migration_files(tmp_path)] == ["001_a.sql", "002_b.sql", "010_c.sql"]


def test_badly_named_migration_is_refused(tmp_path):
    (tmp_path / "add_column.sql").write_text("SELECT 1")
    with pytest.raises(ValueError, match="001_init.sql"):
        migration_files(tmp_path)


def test_second_run_applies_nothing(conn):
    from app import MIGRATIONS_DIR

    assert apply_migrations(conn, MIGRATIONS_DIR) == []


def test_new_migration_runs_once_and_keeps_existing_rows(database_url, tmp_path):
    """A migration that adds a column to a table with data, like the real 00N files."""
    (tmp_path / "001_create.sql").write_text(
        "CREATE TABLE dbo.migration_probe (id INT PRIMARY KEY, name NVARCHAR(20) NOT NULL);"
        "INSERT INTO dbo.migration_probe VALUES (1, N'kept');")
    (tmp_path / "002_add_column.sql").write_text(
        "ALTER TABLE dbo.migration_probe ADD size INT NULL;\nGO\n"
        "UPDATE dbo.migration_probe SET size = LEN(name);")
    cleanup = ("DROP TABLE IF EXISTS dbo.migration_probe; DELETE FROM dbo.schema_migrations "
               "WHERE version IN ('001_create.sql', '002_add_column.sql')")
    with closing(db.connect(database_url)) as conn:
        cursor = conn.cursor()
        cursor.execute(cleanup)
        conn.commit()
        try:
            assert apply_migrations(conn, tmp_path) == ["001_create.sql", "002_add_column.sql"]
            assert apply_migrations(conn, tmp_path) == []
            cursor.execute("SELECT id, name, size FROM dbo.migration_probe")
            assert cursor.fetchall() == [{"id": 1, "name": "kept", "size": 4}]
        finally:
            cursor.execute(cleanup)
            conn.commit()


def test_failed_migration_is_rolled_back_and_not_recorded(database_url, tmp_path):
    (tmp_path / "001_broken.sql").write_text(
        "CREATE TABLE dbo.broken_probe (id INT);\nGO\nSELECT * FROM dbo.table_that_does_not_exist;")
    with closing(db.connect(database_url)) as conn:
        with pytest.raises(pymssql.Error, match="table_that_does_not_exist"):
            apply_migrations(conn, tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT OBJECT_ID('dbo.broken_probe') AS t")
        assert cursor.fetchone()["t"] is None
        cursor.execute("SELECT COUNT(*) AS n FROM dbo.schema_migrations WHERE version = '001_broken.sql'")
        assert cursor.fetchone()["n"] == 0


def test_database_url_must_be_mssql():
    with pytest.raises(ValueError, match="mssql://"):
        db.parse_database_url("sqlite:///tracker.db")


def test_database_url_decodes_special_characters_in_password():
    parts = db.parse_database_url("mssql://app:p%40ss%2Fw0rd@server.example:1444/batches")
    assert parts == {"server": "server.example", "port": 1444, "user": "app",
                     "password": "p@ss/w0rd", "database": "batches"}


def test_connect_with_retry_retries_then_gives_up():
    waits = []
    with pytest.raises(pymssql.OperationalError):
        db.connect_with_retry("mssql://nobody:wrong@127.0.0.1:1/none", delays=(1, 2), sleep=waits.append)
    assert waits == [1, 2]
