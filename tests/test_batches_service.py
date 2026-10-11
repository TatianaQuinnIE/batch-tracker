import json
from datetime import date

import pytest

from batches import service

TODAY = date(2026, 10, 11)


def test_expiry_status_expired():
    assert service.expiry_status(date(2026, 10, 10), TODAY) == "expired"


def test_expiry_status_expiring_soon_on_boundary():
    assert service.expiry_status(date(2026, 11, 10), TODAY) == "expiring_soon"


def test_expiry_status_ok_after_boundary():
    assert service.expiry_status(date(2026, 11, 11), TODAY) == "ok"


def test_create_batch_normalises_code(conn):
    service.create_batch(conn, " lav-01 ", "Soap", date(2026, 1, 1), date(2027, 1, 1), 10)
    batches = service.list_batches(conn, TODAY)
    assert batches[0]["batch_code"] == "LAV-01"
    assert batches[0]["status"] == "ok"


def test_create_batch_rejects_expiry_before_production(conn):
    with pytest.raises(ValueError):
        service.create_batch(conn, "A", "Soap", date(2026, 5, 1), date(2026, 4, 1), 10)


def test_create_batch_rejects_negative_quantity(conn):
    with pytest.raises(ValueError):
        service.create_batch(conn, "A", "Soap", date(2026, 1, 1), date(2027, 1, 1), -1)


def test_create_batch_rejects_duplicate_code(conn):
    service.create_batch(conn, "A", "Soap", date(2026, 1, 1), date(2027, 1, 1), 1)
    with pytest.raises(ValueError):
        service.create_batch(conn, "a", "Soap", date(2026, 1, 1), date(2027, 1, 1), 1)


def test_expiring_soon_only_returns_soon_batches(conn):
    service.create_batch(conn, "OLD", "Soap", date(2026, 1, 1), date(2026, 10, 1), 1)
    service.create_batch(conn, "SOON", "Soap", date(2026, 1, 1), date(2026, 10, 20), 1)
    service.create_batch(conn, "LATER", "Soap", date(2026, 1, 1), date(2027, 6, 1), 1)
    codes = [b["batch_code"] for b in service.expiring_soon(conn, TODAY)]
    assert codes == ["SOON"]


def test_seed_if_empty_loads_once(conn, tmp_path):
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps([
        {"batch_code": "S1", "product": "Soap", "produced_on": "2026-01-01",
         "expires_on": "2027-01-01", "quantity": 5},
    ]))
    assert service.seed_if_empty(conn, seed_file) == 1
    assert service.seed_if_empty(conn, seed_file) == 0
    assert len(service.list_batches(conn, TODAY)) == 1
