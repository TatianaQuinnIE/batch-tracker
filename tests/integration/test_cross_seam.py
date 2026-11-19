"""Integration test across the seam, against the real compose stack (ADR-9).

Run from the repository root with the stack up:
    docker compose up -d --build
    pip install pytest==8.3.4
    pytest tests/integration

It drives both real services over HTTP: a batch is created in batches, a report is
sent to feedback, and feedback must show the batch's product (fetched from batches
over HTTP). Then the batches container is stopped, and feedback must keep serving its
own data with a notice, quickly, instead of failing or hanging. Batches is started
again at the end.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import pytest

BATCHES_URL = os.environ.get("BATCHES_URL", "http://localhost:8001")
FEEDBACK_URL = os.environ.get("FEEDBACK_URL", "http://localhost:8002")
STARTUP_WAIT_S = 240


def call(method, url, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as err:
        return err.code, json.load(err)


def wait_until_healthy(url):
    deadline = time.monotonic() + STARTUP_WAIT_S
    while time.monotonic() < deadline:
        try:
            if call("GET", f"{url}/health")[0] == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(3)
    pytest.fail(f"{url}/health did not return 200 within {STARTUP_WAIT_S} s")


def compose(*args):
    subprocess.run(["docker", "compose", *args], check=True, capture_output=True)


@pytest.fixture(scope="module")
def batch_code():
    wait_until_healthy(BATCHES_URL)
    wait_until_healthy(FEEDBACK_URL)
    code = f"IT-{uuid.uuid4().hex[:8].upper()}"   # unique, so the test can run on a used stack
    status, _ = call("POST", f"{BATCHES_URL}/batches", {
        "batch_code": code, "product": "Integration test balm",
        "produced_on": "2026-11-01", "expires_on": "2027-11-01", "quantity": 5})
    assert status == 201
    return code


def test_feedback_shows_product_fetched_from_batches(batch_code):
    status, body = call("POST", f"{FEEDBACK_URL}/feedback",
                        {"batch_code": batch_code, "rating": 3, "had_reaction": True})
    assert status == 201
    assert body["batch"]["product"] == "Integration test balm"

    status, body = call("GET", f"{FEEDBACK_URL}/feedback/{batch_code}")
    assert status == 200
    assert body["batches_service"] == "ok"
    assert body["batch"] == {"product": "Integration test balm", "expires_on": "2027-11-01", "status": "ok"}


def test_feedback_degrades_when_batches_is_stopped(batch_code):
    compose("stop", "batches")
    try:
        started = time.monotonic()
        status, body = call("GET", f"{FEEDBACK_URL}/feedback/{batch_code}")
        elapsed = time.monotonic() - started
        assert status == 200
        assert body["batches_service"] == "unavailable"
        assert body["batch"] is None
        assert body["notice"]
        assert body["reports"] >= 1, "feedback still serves its own data"
        assert elapsed < 5, "BATCHES_TIMEOUT_S must bound the wait"

        status, body = call("POST", f"{FEEDBACK_URL}/feedback",
                            {"batch_code": batch_code, "rating": 4, "had_reaction": False})
        assert status == 201, "reports are still accepted with batches down"

        assert call("GET", f"{FEEDBACK_URL}/health")[0] == 200, "health is about feedback only"
    finally:
        compose("start", "batches")
        wait_until_healthy(BATCHES_URL)
