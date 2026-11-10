def test_health_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["db"] == "ok"


def test_submit_feedback_returns_201_with_summary(client):
    response = client.post("/feedback", json={"batch_code": "ros-2608", "rating": 4})
    assert response.status_code == 201
    assert response.get_json()["batch_code"] == "ROS-2608"
    assert response.get_json()["reports"] == 1


def test_no_reaction_is_not_counted_as_reaction(client):
    client.post("/feedback", json={"batch_code": "ALO-2609", "rating": 5, "had_reaction": False})
    assert client.get("/feedback/ALO-2609").get_json()["reactions"] == 0


def test_three_reactions_flag_the_batch(client):
    for _ in range(3):
        client.post("/feedback", json={"batch_code": "ROS-2608", "rating": 2, "had_reaction": True})
    flagged = client.get("/feedback/flagged").get_json()
    assert [s["batch_code"] for s in flagged] == ["ROS-2608"]


def test_summary_for_unknown_batch_is_404(client):
    assert client.get("/feedback/NOPE").status_code == 404


def test_invalid_rating_is_400(client):
    response = client.post("/feedback", json={"batch_code": "ROS-2608", "rating": 9})
    assert response.status_code == 400


def test_missing_field_is_400(client):
    response = client.post("/feedback", json={"rating": 3})
    assert response.status_code == 400
    assert "missing field" in response.get_json()["error"]


def test_list_summaries_returns_json_list(client):
    assert client.get("/feedback").get_json() == []
