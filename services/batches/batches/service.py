"""Batch register: validation, storage and expiry status. No Flask in here."""
import json
import re
from datetime import date

import pymssql

EXPIRING_SOON_DAYS = 30
BATCH_CODE_MAX = 40
PRODUCT_MAX = 120
RECALL_REASON_MAX = 200
BATCH_CODE_FORMAT = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")

NEW_BATCH_COLUMNS = "batch_code, product, produced_on, expires_on, quantity"
COLUMNS = NEW_BATCH_COLUMNS + ", recalled_on, recall_reason"
# The only fields PATCH may change. batch_code is the key feedback stores (ADR-6), so it
# never changes; produced_on is a fact about the past.
EDITABLE = ("product", "expires_on", "quantity")


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


def normalise_code(batch_code):
    return batch_code.strip().upper()


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
        "recalled_on": row["recalled_on"].isoformat() if row["recalled_on"] else None,
        "recall_reason": row["recall_reason"],
    }


def create_batch(conn, batch):
    """Insert a batch already checked by parse_new_batch."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"INSERT INTO dbo.batches ({NEW_BATCH_COLUMNS}) VALUES (%s, %s, %s, %s, %s)",
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
        (normalise_code(batch_code),),
    )
    row = cursor.fetchone()
    return None if row is None else _to_json(row, today)


def expiring_soon(conn, today):
    """Batches still on sale that expire within 30 days; a recalled batch is already off the shelf."""
    return [b for b in list_batches(conn, today)
            if b["status"] == "expiring_soon" and b["recalled_on"] is None]


def parse_recall(body):
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    return _text(body, "reason", RECALL_REASON_MAX)


def recall_batch(conn, batch_code, reason, today):
    """Mark a batch as recalled today. Returns the batch, or None if there is no such batch."""
    batch = get_batch(conn, batch_code, today)
    if batch is None:
        return None
    if batch["recalled_on"] is not None:
        raise ValidationError(f"batch {batch['batch_code']} was already recalled on {batch['recalled_on']}")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE dbo.batches SET recalled_on = %s, recall_reason = %s WHERE batch_code = %s",
        (today, reason, batch["batch_code"]),
    )
    conn.commit()
    return get_batch(conn, batch_code, today)


def parse_changes(body):
    """Validate a PATCH body: one or more of EDITABLE, each checked like a new batch."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    unknown = sorted(set(body) - set(EDITABLE))
    if unknown:
        raise ValidationError(
            f"only product, expires_on and quantity can be changed, not {', '.join(unknown)}")
    if not body:
        raise ValidationError("send at least one of product, expires_on, quantity")
    changes = {}
    if "product" in body:
        changes["product"] = _text(body, "product", PRODUCT_MAX)
    if "expires_on" in body:
        changes["expires_on"] = _date(body, "expires_on")
    if "quantity" in body:
        changes["quantity"] = _whole_number(body, "quantity")
        if changes["quantity"] < 0:
            raise ValidationError("quantity cannot be negative")
    return changes


def update_batch(conn, batch_code, changes, today):
    """Apply changes from parse_changes. Returns the batch, or None if there is no such batch."""
    batch = get_batch(conn, batch_code, today)
    if batch is None:
        return None
    if "expires_on" in changes and changes["expires_on"] <= date.fromisoformat(batch["produced_on"]):
        raise ValidationError("expires_on must be after produced_on")
    # Column names come from EDITABLE (via parse_changes), never from the request.
    assignments = ", ".join(f"{column} = %s" for column in changes)
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE dbo.batches SET {assignments} WHERE batch_code = %s",
        (*changes.values(), batch["batch_code"]),
    )
    conn.commit()
    return get_batch(conn, batch_code, today)


def delete_batch(conn, batch_code):
    """For a batch registered by mistake. Returns False if there was no such batch."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dbo.batches WHERE batch_code = %s", (normalise_code(batch_code),))
    deleted = cursor.rowcount
    conn.commit()
    return deleted == 1


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
