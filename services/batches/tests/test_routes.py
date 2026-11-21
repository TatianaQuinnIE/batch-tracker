NEW_BATCH = {
    "batch_code": "new-01",
    "product": "Rose soap",
    "produced_on": "2026-10-01",
    "expires_on": "2027-10-01",
    "quantity": 20,
}


def test_health_reports_ok_with_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "dev"}


def test_health_is_503_when_database_is_unreachable(client):
    client.application.config["DATABASE_URL"] = "mssql://nobody:wrong@127.0.0.1:1/none"
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "error"


def test_seed_batches_are_listed(client):
    codes = [b["batch_code"] for b in client.get("/batches").get_json()]
    assert set(codes) == {"LAV-2607", "ROS-2608", "CAL-2603", "ALO-2609"}


def test_create_batch_returns_201_with_normalised_code(client):
    response = client.post("/batches", json=NEW_BATCH)
    assert response.status_code == 201
    assert response.get_json()["batch_code"] == "NEW-01"
    assert client.get("/batches/new-01").status_code == 200


def test_duplicate_batch_is_400_and_not_written_twice(client):
    client.post("/batches", json=NEW_BATCH)
    response = client.post("/batches", json=NEW_BATCH)
    assert response.status_code == 400
    assert response.get_json() == {"error": "batch code NEW-01 already exists"}


def test_blank_code_and_product_are_400_and_nothing_written(client):
    before = len(client.get("/batches").get_json())
    response = client.post("/batches", json={**NEW_BATCH, "batch_code": "  ", "product": ""})
    assert response.status_code == 400
    assert response.get_json() == {"error": "batch_code is required"}
    assert len(client.get("/batches").get_json()) == before


def test_non_numeric_quantity_gives_a_readable_400(client):
    response = client.post("/batches", json={**NEW_BATCH, "quantity": "lots"})
    assert response.status_code == 400
    assert response.get_json() == {"error": "quantity must be a whole number"}


def test_missing_field_names_the_field(client):
    response = client.post("/batches", json={"batch_code": "X-1"})
    assert response.status_code == 400
    assert response.get_json() == {"error": "product is required"}


def test_body_that_is_not_json_is_400(client):
    response = client.post("/batches", data="batch_code=X", content_type="text/plain")
    assert response.status_code == 400


def test_unknown_batch_is_404(client):
    response = client.get("/batches/nope")
    assert response.status_code == 404
    assert response.get_json() == {"error": "batch NOPE not found"}


def test_unknown_path_is_json_404(client):
    response = client.get("/nothing-here")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_expiring_soon_returns_json_list(client):
    response = client.get("/batches/expiring-soon")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_cors_header_allows_only_the_ui_origin(client):
    response = client.get("/batches")
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8080"


def test_preflight_for_json_post_is_allowed(client):
    response = client.options("/batches", headers={
        "Origin": "http://localhost:8080",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert response.status_code == 200
    assert "POST" in response.headers["Access-Control-Allow-Methods"]


# --- recall --------------------------------------------------------------------

def test_recall_returns_the_recalled_batch(client):
    response = client.post("/batches/lav-2607/recall", json={"reason": "Mould found in one jar"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["batch_code"] == "LAV-2607"
    assert body["recall_reason"] == "Mould found in one jar"
    assert body["recalled_on"] is not None


def test_recall_without_reason_is_400(client):
    response = client.post("/batches/LAV-2607/recall", json={})
    assert response.status_code == 400
    assert response.get_json() == {"error": "reason is required"}


def test_recall_twice_is_400(client):
    client.post("/batches/LAV-2607/recall", json={"reason": "first"})
    response = client.post("/batches/LAV-2607/recall", json={"reason": "second"})
    assert response.status_code == 400
    assert "already recalled" in response.get_json()["error"]


def test_recall_unknown_batch_is_404(client):
    response = client.post("/batches/nope/recall", json={"reason": "x"})
    assert response.status_code == 404
    assert response.get_json() == {"error": "batch NOPE not found"}

