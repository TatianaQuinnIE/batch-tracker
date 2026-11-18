import json
from datetime import date

import pytest

from batches import service

TODAY = date(2026, 10, 11)

VALID = {
    "batch_code": " lav-01 ",
    "product": " Lavender soap ",
    "produced_on": "2026-01-01",
    "expires_on": "2027-01-01",
    "quantity": "10",
}


def make(conn, code, expires_on, produced_on="2026-01-01"):
    service.create_batch(conn, service.parse_new_batch(
        {**VALID, "batch_code": code, "produced_on": produced_on, "expires_on": expires_on}))


# --- expiry status: the 30-day boundary --------------------------------------

def test_expiry_status_expired():
    assert service.expiry_status(date(2026, 10, 10), TODAY) == "expired"


def test_expiry_status_today_is_expiring_soon_not_expired():
    assert service.expiry_status(TODAY, TODAY) == "expiring_soon"


def test_expiry_status_expiring_soon_on_boundary():
    assert service.expiry_status(date(2026, 11, 10), TODAY) == "expiring_soon"


def test_expiry_status_ok_after_boundary():
    assert service.expiry_status(date(2026, 11, 11), TODAY) == "ok"


# --- parse_new_batch: the input gaps found in the Assignment 1 review ----------

def test_parse_new_batch_cleans_values():
    batch = service.parse_new_batch(VALID)
    assert batch == {
        "batch_code": "LAV-01",
        "product": "Lavender soap",
        "produced_on": date(2026, 1, 1),
        "expires_on": date(2027, 1, 1),
        "quantity": 10,
    }


@pytest.mark.parametrize("field", ["batch_code", "product", "produced_on", "expires_on", "quantity"])
def test_parse_new_batch_missing_field_names_it(field):
    body = {k: v for k, v in VALID.items() if k != field}
    with pytest.raises(service.ValidationError, match=f"^{field} is required$"):
        service.parse_new_batch(body)


@pytest.mark.parametrize("field", ["batch_code", "product"])
def test_parse_new_batch_rejects_whitespace_only_text(field):
    with pytest.raises(service.ValidationError, match=f"^{field} is required$"):
        service.parse_new_batch({**VALID, field: "   "})


@pytest.mark.parametrize("quantity", ["ten", "2.5", True, [3]])
def test_parse_new_batch_rejects_non_numeric_quantity(quantity):
    with pytest.raises(service.ValidationError, match="^quantity must be a whole number$"):
        service.parse_new_batch({**VALID, "quantity": quantity})


def test_parse_new_batch_rejects_negative_quantity():
    with pytest.raises(service.ValidationError, match="cannot be negative"):
        service.parse_new_batch({**VALID, "quantity": -1})


def test_parse_new_batch_accepts_zero_quantity():
    assert service.parse_new_batch({**VALID, "quantity": 0})["quantity"] == 0


def test_parse_new_batch_rejects_bad_date_format():
    with pytest.raises(service.ValidationError, match="YYYY-MM-DD"):
        service.parse_new_batch({**VALID, "expires_on": "01/02/2027"})


@pytest.mark.parametrize("expires_on", ["2025-12-31", "2026-01-01"])
def test_parse_new_batch_rejects_expiry_not_after_production(expires_on):
    with pytest.raises(service.ValidationError, match="must be after produced_on"):
        service.parse_new_batch({**VALID, "expires_on": expires_on})


def test_parse_new_batch_rejects_code_with_spaces_or_symbols():
    with pytest.raises(service.ValidationError, match="letters, digits and hyphens"):
        service.parse_new_batch({**VALID, "batch_code": "LAV 01!"})


def test_parse_new_batch_rejects_too_long_product():
    with pytest.raises(service.ValidationError, match="at most 120"):
        service.parse_new_batch({**VALID, "product": "x" * 121})


def test_parse_new_batch_rejects_non_object_body():
    with pytest.raises(service.ValidationError, match="JSON object"):
        service.parse_new_batch(["not", "an", "object"])


# --- storage (SQL Server) ----------------------------------------------------

def test_create_and_get_batch_round_trip(conn):
    service.create_batch(conn, service.parse_new_batch(VALID))
    batch = service.get_batch(conn, " lav-01 ", TODAY)
    assert batch == {
        "batch_code": "LAV-01",
        "product": "Lavender soap",
        "produced_on": "2026-01-01",
        "expires_on": "2027-01-01",
        "quantity": 10,
        "status": "ok",
    }


def test_create_batch_rejects_duplicate_code_case_insensitively(conn):
    make(conn, "A-1", "2027-01-01")
    with pytest.raises(service.ValidationError, match="A-1 already exists"):
        make(conn, "a-1", "2027-01-01")
    assert len(service.list_batches(conn, TODAY)) == 1


def test_get_batch_unknown_code_is_none(conn):
    assert service.get_batch(conn, "NOPE", TODAY) is None


def test_list_batches_sorted_by_expiry(conn):
    make(conn, "LATER", "2027-06-01")
    make(conn, "SOON", "2026-10-20")
    assert [b["batch_code"] for b in service.list_batches(conn, TODAY)] == ["SOON", "LATER"]


def test_expiring_soon_only_returns_soon_batches(conn):
    make(conn, "OLD", "2026-10-01")
    make(conn, "SOON", "2026-10-20")
    make(conn, "LATER", "2027-06-01")
    assert [b["batch_code"] for b in service.expiring_soon(conn, TODAY)] == ["SOON"]


def test_seed_if_empty_loads_once(conn, tmp_path):
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps([
        {"batch_code": "S1", "product": "Soap", "produced_on": "2026-01-01",
         "expires_on": "2027-01-01", "quantity": 5},
    ]))
    assert service.seed_if_empty(conn, seed_file) == 1
    assert service.seed_if_empty(conn, seed_file) == 0
    assert len(service.list_batches(conn, TODAY)) == 1
