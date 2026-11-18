"""Batch register: validation, storage and expiry status. No Flask in here."""
import json
import re
from datetime import date

import pymssql

EXPIRING_SOON_DAYS = 30
BATCH_CODE_MAX = 40
PRODUCT_MAX = 120
BATCH_CODE_FORMAT = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")

COLUMNS = "batch_code, product, produced_on, expires_on, quantity"


class ValidationError(ValueError):
    """Input the user can fix. The message is safe to show as it is."""


def _text(body, field, max_length):
    value = body.get(field)
    if value is None or not str(value).strip():
        raise ValidationError(f"{field} is required")
    value = str(value).strip()
    if len(value) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters")
    return value


def _date(body, field):
    value = _text(body, field, 10)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} must be a date in YYYY-MM-DD format") from None


def _whole_number(body, field):
    value = body.get(field)
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{field} is required")
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a whole number")
    try:
        return int(str(value).strip())
    except ValueError:
        raise ValidationError(f"{field} must be a whole number") from None


def parse_new_batch(body):
    """Turn a JSON body (or a seed.json entry) into clean values, or raise ValidationError."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    batch_code = _text(body, "batch_code", BATCH_CODE_MAX).upper()
    if not BATCH_CODE_FORMAT.match(batch_code):
        raise ValidationError("batch_code may only contain letters, digits and hyphens")
    batch = {
        "batch_code": batch_code,
        "product": _text(body, "product", PRODUCT_MAX),
        "produced_on": _date(body, "produced_on"),
        "expires_on": _date(body, "expires_on"),
        "quantity": _whole_number(body, "quantity"),
    }
    if batch["expires_on"] <= batch["produced_on"]:
        raise ValidationError("expires_on must be after produced_on")
    if batch["quantity"] < 0:
        raise ValidationError("quantity cannot be negative")
    return batch


def expiry_status(expires_on, today):
    days_left = (expires_on - today).days
    if days_left < 0:
        return "expired"
    if days_left <= EXPIRING_SOON_DAYS:
        return "expiring_soon"
    return "ok"


def _to_json(row, today):
    return {
        "batch_code": row["batch_code"],
        "product": row["product"],
        "produced_on": row["produced_on"].isoformat(),
        "expires_on": row["expires_on"].isoformat(),
        "quantity": row["quantity"],
        "status": expiry_status(row["expires_on"], today),
    }


def create_batch(conn, batch):
    """Insert a batch already checked by parse_new_batch."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"INSERT INTO dbo.batches ({COLUMNS}) VALUES (%s, %s, %s, %s, %s)",
            (batch["batch_code"], batch["product"], batch["produced_on"],
             batch["expires_on"], batch["quantity"]),
        )
        conn.commit()
    except pymssql.IntegrityError:
        conn.rollback()
        raise ValidationError(f"batch code {batch['batch_code']} already exists") from None


def list_batches(conn, today):
    cursor = conn.cursor()
    cursor.execute(f"SELECT {COLUMNS} FROM dbo.batches ORDER BY expires_on, batch_code")
    return [_to_json(row, today) for row in cursor.fetchall()]


def get_batch(conn, batch_code, today):
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {COLUMNS} FROM dbo.batches WHERE batch_code = %s",
        (batch_code.strip().upper(),),
    )
    row = cursor.fetchone()
    return None if row is None else _to_json(row, today)


def expiring_soon(conn, today):
    return [b for b in list_batches(conn, today) if b["status"] == "expiring_soon"]


def seed_if_empty(conn, seed_path):
    """Load seed.json only into an empty table, so a restart never duplicates rows."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS n FROM dbo.batches")
    if cursor.fetchone()["n"] > 0:
        return 0
    with open(seed_path, encoding="utf-8") as seed_file:
        seed_batches = json.load(seed_file)
    for entry in seed_batches:
        create_batch(conn, parse_new_batch(entry))
    return len(seed_batches)
