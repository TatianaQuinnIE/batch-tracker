"""Connections to this service's own SQL Server database.

The connection string comes from DATABASE_URL in the form
mssql://user:password@host:1433/database (special characters URL-encoded).
"""
import logging
import time
from urllib.parse import unquote, urlparse

import pymssql

log = logging.getLogger(__name__)

# Waits between connection attempts at startup, about 90 s in total. An Azure SQL
# serverless database that auto-paused takes up to a minute to resume, and while it
# resumes every connection fails (error 40613 or a login timeout).
STARTUP_RETRY_DELAYS_S = (2, 4, 8, 16, 30, 30)


def parse_database_url(url):
    if not url:
        raise ValueError("DATABASE_URL is not set")
    parts = urlparse(url)
    if parts.scheme != "mssql" or not parts.hostname or not parts.path.strip("/"):
        raise ValueError("DATABASE_URL must look like mssql://user:password@host:1433/database")
    return {
        "server": parts.hostname,
        "port": parts.port or 1433,
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "database": parts.path.strip("/"),
    }


def connect(url, login_timeout=10):
    """One connection; rows come back as dicts. Autocommit is off, so call commit()."""
    return pymssql.connect(
        **parse_database_url(url),
        as_dict=True,
        login_timeout=login_timeout,
        timeout=15,
        tds_version="7.4",
    )


def connect_with_retry(url, delays=STARTUP_RETRY_DELAYS_S, sleep=time.sleep):
    """Used at startup only, when the database may still be resuming from pause."""
    for attempt, delay in enumerate((*delays, None), start=1):
        try:
            return connect(url)
        except pymssql.OperationalError as err:
            if delay is None:
                raise
            log.warning("database not reachable (attempt %d): %s; retrying in %ss",
                        attempt, str(err).splitlines()[0], delay)
            sleep(delay)
