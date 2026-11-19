REPORT = {"batch_code": "ros-2608", "rating": 4, "had_reaction": False}


def test_health_reports_ok_with_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "dev"}


def test_health_is_503_when_database_is_unreachable(client):
    client.application.config["DATABASE_URL"] = "mssql://nobody:wrong@127.0.0.1:1/none"
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "error"


def test_submit_feedback_returns_201_with_summary(client):
    response = client.post("/feedback", json=REPORT)
    assert response.status_code == 201
    assert response.get_json()["batch_code"] == "ROS-2608"
    assert response.get_json()["reports"] == 1


def test_no_reaction_is_not_counted_as_reaction(client):
    client.post("/feedback", json={**REPORT, "had_reaction": False})
    assert client.get("/feedback/ROS-2608").get_json()["reactions"] == 0


def test_three_reactions_flag_the_batch(client):
    for _ in range(3):
        client.post("/feedback", json={**REPORT, "rating": 2, "had_reaction": True})
    flagged = client.get("/feedback/flagged").get_json()["summaries"]
    assert [s["batch_code"] for s in flagged] == ["ROS-2608"]


def test_summary_for_unknown_batch_is_404(client):
    response = client.get("/feedback/nope")
    assert response.status_code == 404
    assert response.get_json() == {"error": "no feedback for batch NOPE"}


def test_out_of_range_rating_is_400_and_nothing_written(client):
    response = client.post("/feedback", json={**REPORT, "rating": 9})
    assert response.status_code == 400
    assert response.get_json() == {"error": "rating must be between 1 and 5"}
    assert client.get("/feedback").get_json()["summaries"] == []


def test_non_numeric_rating_gives_a_readable_400(client):
    response = client.post("/feedback", json={**REPORT, "rating": "great"})
    assert response.status_code == 400
    assert response.get_json() == {"error": "rating must be a whole number from 1 to 5"}


def test_missing_field_names_the_field(client):
    response = client.post("/feedback", json={"rating": 3, "had_reaction": False})
    assert response.status_code == 400
    assert response.get_json() == {"error": "batch_code is required"}


def test_list_summaries_starts_empty(client):
    assert client.get("/feedback").get_json() == {
        "summaries": [], "batches_service": "ok", "notice": None}


def test_cors_header_allows_only_the_ui_origin(client):
    response = client.get("/feedback")
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8080"
