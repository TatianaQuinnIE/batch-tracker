"""Forward-only migration runner.

Every file in migrations/ named NNN_description.sql is applied once, in file-name
order, and recorded in schema_migrations. A file may hold several batches separated
by a line containing only GO (needed when a later statement uses a column that an
earlier ALTER TABLE in the same file adds). Applied files must never be edited:
corrections go in a new file.
"""
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

MIGRATION_NAME = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")
GO_LINE = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)

CREATE_TRACKING_TABLE = """
IF OBJECT_ID('dbo.schema_migrations', 'U') IS NULL
    CREATE TABLE dbo.schema_migrations (
        version NVARCHAR(255) NOT NULL PRIMARY KEY,
        applied_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    )
"""


def migration_files(migrations_dir):
    files = sorted(p for p in Path(migrations_dir).iterdir() if p.suffix == ".sql")
    for path in files:
        if not MIGRATION_NAME.match(path.name):
            raise ValueError(f"migration file name {path.name!r} must look like 001_init.sql")
    return files


def split_batches(sql):
    return [batch.strip() for batch in GO_LINE.split(sql) if batch.strip()]


def apply_migrations(conn, migrations_dir):
    """Apply pending migrations; return the names of the ones applied now."""
    cursor = conn.cursor()
    cursor.execute(CREATE_TRACKING_TABLE)
    conn.commit()
    cursor.execute("SELECT version FROM dbo.schema_migrations")
    applied = {row["version"] for row in cursor.fetchall()}

    newly_applied = []
    for path in migration_files(migrations_dir):
        if path.name in applied:
            continue
        log.info("applying migration %s", path.name)
        try:
            for batch in split_batches(path.read_text(encoding="utf-8")):
                cursor.execute(batch)
            cursor.execute("INSERT INTO dbo.schema_migrations (version) VALUES (%s)", (path.name,))
            # The schema change and its record are committed together, or not at all.
            conn.commit()
        except Exception:
            conn.rollback()
            log.error("migration %s failed and was rolled back", path.name)
            raise
        log.info("applied migration %s", path.name)
        newly_applied.append(path.name)

    if not newly_applied:
        log.info("migrations up to date (%d already applied)", len(applied))
    return newly_applied
