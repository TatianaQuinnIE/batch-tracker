import sqlite3
from datetime import date

EXPIRING_SOON_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_code TEXT NOT NULL UNIQUE,
    product TEXT NOT NULL,
    produced_on TEXT NOT NULL,
    expires_on TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
)
"""


def init_schema(conn):
    conn.execute(SCHEMA)
    conn.commit()


def expiry_status(expires_on, today):
    days_left = (expires_on - today).days
    if days_left < 0:
        return "expired"
    if days_left <= EXPIRING_SOON_DAYS:
        return "expiring_soon"
    return "ok"


def create_batch(conn, batch_code, product, produced_on, expires_on, quantity):
    if expires_on <= produced_on:
        raise ValueError("expiry date must be after production date")
    if quantity < 0:
        raise ValueError("quantity cannot be negative")
    try:
        conn.execute(
            "INSERT INTO batches (batch_code, product, produced_on, expires_on, quantity) "
            "VALUES (?, ?, ?, ?, ?)",
            (batch_code.strip().upper(), product.strip(),
             produced_on.isoformat(), expires_on.isoformat(), quantity),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"batch code {batch_code} already exists")


def list_batches(conn, today):
    rows = conn.execute("SELECT * FROM batches ORDER BY expires_on").fetchall()
    batches = []
    for row in rows:
        batch = dict(row)
        batch["status"] = expiry_status(date.fromisoformat(row["expires_on"]), today)
        batches.append(batch)
    return batches


def expiring_soon(conn, today):
    return [b for b in list_batches(conn, today) if b["status"] == "expiring_soon"]
