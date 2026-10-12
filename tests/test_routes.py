import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path))
    return app.test_client()


NEW_BATCH = {
    "batch_code": "new-01",
    "product": "Rose soap",
    "produced_on": "2026-10-01",
    "expires_on": "2027-10-01",
    "quantity": "20",
}


def test_pages_load(client):
    assert client.get("/").status_code == 200
    assert client.get("/batches/").status_code == 200
    assert client.get("/feedback/").status_code == 200


def test_seed_batches_are_listed(client):
    page = client.get("/batches/").data
    assert b"LAV-2607" in page


def test_create_batch_redirects_with_confirmation(client):
    response = client.post("/batches/", data=NEW_BATCH)
    assert response.status_code == 302
    assert response.location == "/batches/?saved=NEW-01"
    assert b"Batch NEW-01 added" in client.get(response.location).data


def test_create_batch_with_bad_dates_shows_error_and_keeps_input(client):
    bad = dict(NEW_BATCH, expires_on="2026-01-01")
    response = client.post("/batches/", data=bad)
    assert response.status_code == 400
    assert b"expiry date must be after production date" in response.data
    assert b'value="Rose soap"' in response.data


def test_create_batch_with_missing_field_is_rejected(client):
    response = client.post("/batches/", data={"batch_code": "X"})
    assert response.status_code == 400
    assert b"missing field" in response.data


def test_expiring_soon_returns_json(client):
    response = client.get("/batches/expiring-soon")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_submit_feedback_redirects_with_thanks(client):
    response = client.post("/feedback/", data={"batch_code": "ros-2608", "rating": "4", "had_reaction": ""})
    assert response.location == "/feedback/?sent=ROS-2608"
    assert b"ROS-2608 was recorded" in client.get(response.location).data


def test_no_reaction_answer_is_not_counted_as_reaction(client):
    client.post("/feedback/", data={"batch_code": "ALO-2609", "rating": "5", "had_reaction": ""})
    summary = client.get("/feedback/ALO-2609").get_json()
    assert summary["reports"] == 1
    assert summary["reactions"] == 0


def test_three_reactions_flag_the_batch(client):
    for _ in range(3):
        client.post("/feedback/", data={"batch_code": "ROS-2608", "rating": "2", "had_reaction": "on"})
    flagged = client.get("/feedback/flagged").get_json()
    assert [s["batch_code"] for s in flagged] == ["ROS-2608"]


def test_summary_for_unknown_batch_is_404(client):
    assert client.get("/feedback/NOPE").status_code == 404


def test_invalid_rating_shows_error(client):
    response = client.post("/feedback/", data={"batch_code": "ROS-2608", "rating": "9"})
    assert response.status_code == 400
    assert b"rating must be between 1 and 5" in response.data


def test_feedback_missing_field_is_rejected(client):
    response = client.post("/feedback/", data={"rating": "3"})
    assert response.status_code == 400
    assert b"missing field" in response.data
