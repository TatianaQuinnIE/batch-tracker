NEW_BATCH = {
    "batch_code": "new-01",
    "product": "Rose soap",
    "produced_on": "2026-10-01",
    "expires_on": "2027-10-01",
    "quantity": 20,
}


def test_health_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert response.get_json()["db"] == "ok"


def test_seed_batches_are_listed(client):
    codes = [b["batch_code"] for b in client.get("/batches").get_json()]
    assert "LAV-2607" in codes


def test_create_batch_returns_201_with_normalised_code(client):
    response = client.post("/batches", json=NEW_BATCH)
    assert response.status_code == 201
    assert response.get_json()["batch_code"] == "NEW-01"
    assert client.get("/batches/new-01").status_code == 200


def test_create_batch_with_bad_dates_is_400(client):
    response = client.post("/batches", json={**NEW_BATCH, "expires_on": "2026-01-01"})
    assert response.status_code == 400
    assert "expiry date" in response.get_json()["error"]


def test_create_batch_with_missing_field_is_400(client):
    response = client.post("/batches", json={"batch_code": "X"})
    assert response.status_code == 400
    assert "missing field" in response.get_json()["error"]


def test_unknown_batch_is_404(client):
    assert client.get("/batches/NOPE").status_code == 404


def test_expiring_soon_returns_json_list(client):
    response = client.get("/batches/expiring-soon")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_cors_header_allows_ui_origin(client):
    response = client.get("/batches")
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8080"
