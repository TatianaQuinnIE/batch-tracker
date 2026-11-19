"""The cross-seam flow: feedback summaries joined with batch details from the batches
service over HTTP, and what happens when that service is slow, broken or stopped.

The batches service is the stub in stub_batches.py (ADR-9); the compose test in
tests/integration/ runs the same flow against the real batches container.
"""
import time

import pytest

from feedback import batches_client

REPORT = {"batch_code": "ros-2608", "rating": 2, "had_reaction": True}


# --- the happy path ------------------------------------------------------------

def test_summary_includes_product_and_expiry_from_batches(client, batches_stub):
    client.post("/feedback", json=REPORT)
    body = client.get("/feedback/ROS-2608").get_json()
    assert body["batch"] == {"product": "Rosehip face oil", "expires_on": "2026-11-05", "status": "expired"}
    assert body["batches_service"] == "ok"
    assert body["notice"] is None
    assert "/batches/ROS-2608" in batches_stub.requests


def test_submit_answers_with_the_batch_details(client):
    response = client.post("/feedback", json=REPORT)
    assert response.status_code == 201
    assert response.get_json()["batch"]["product"] == "Rosehip face oil"


def test_list_makes_one_call_for_all_summaries(client, batches_stub):
    for code in ("ros-2608", "lav-2607", "lav-2607"):
        client.post("/feedback", json={**REPORT, "batch_code": code})
    batches_stub.requests.clear()
    body = client.get("/feedback").get_json()
    assert batches_stub.requests == ["/batches"]          # not one call per batch
    assert [s["batch"]["product"] for s in body["summaries"]] == ["Lavender soap bar", "Rosehip face oil"]


def test_unknown_batch_code_is_saved_with_no_batch_details(client):
    # Not enforced on write (ADR-7): a report can arrive before staff register the batch.
    response = client.post("/feedback", json={**REPORT, "batch_code": "NEW-0001"})
    assert response.status_code == 201
    body = response.get_json()
    assert body["batch"] is None
    assert body["batches_service"] == "ok"


def test_flagged_list_carries_the_product(client):
    for _ in range(3):
        client.post("/feedback", json=REPORT)
    flagged = client.get("/feedback/flagged").get_json()["summaries"]
    assert flagged[0]["batch"]["product"] == "Rosehip face oil"


# --- partial failure: batches slow, broken or stopped ---------------------------

@pytest.mark.parametrize("mode", ["slow", "error", "html"])
def test_feedback_degrades_when_batches_misbehaves(client, batches_stub, mode):
    client.post("/feedback", json=REPORT)
    batches_stub.mode = mode
    started = time.perf_counter()
    response = client.get("/feedback")
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    body = response.get_json()
    assert body["batches_service"] == "unavailable"
    assert "unavailable" in body["notice"]
    assert body["summaries"][0]["reports"] == 1          # own data is still served
    assert body["summaries"][0]["batch"] is None
    assert elapsed < 2, "the timeout must stop a slow batches service from hanging the request"


def test_submit_still_saves_when_batches_is_stopped(client, batches_stub):
    batches_stub.stop()
    response = client.post("/feedback", json=REPORT)
    assert response.status_code == 201
    assert response.get_json()["batches_service"] == "unavailable"
    assert client.get("/feedback/ROS-2608").get_json()["reports"] == 1


def test_health_ignores_the_batches_service(client, batches_stub):
    batches_stub.stop()
    assert client.get("/health").status_code == 200


# --- the client on its own --------------------------------------------------------

def test_client_returns_none_for_404(batches_stub):
    assert batches_client.get_batch(batches_stub.url, "nope", 1) is None


def test_client_quotes_the_code_in_the_path(batches_stub):
    batches_client.get_batch(batches_stub.url, "a/b c", 1)
    assert batches_stub.requests == ["/batches/A%2FB%20C"]


def test_client_times_out(batches_stub):
    batches_stub.mode = "slow"
    with pytest.raises(batches_client.BatchesUnavailable):
        batches_client.list_batches(batches_stub.url, 0.2)


def test_client_raises_when_nothing_listens():
    with pytest.raises(batches_client.BatchesUnavailable):
        batches_client.get_batch("http://127.0.0.1:1", "LAV-2607", 1)


def test_batch_details_of_none_is_none():
    assert batches_client.batch_details(None) is None
