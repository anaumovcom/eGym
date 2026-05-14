from fastapi.testclient import TestClient


def test_list_users_returns_frontend_shape(client: TestClient) -> None:
    response = client.get("/api/users")

    assert response.status_code == 200
    payload = response.json()
    assert [user["id"] for user in payload["users"]] == ["alexey", "elena"]
    assert payload["users"][0]["readinessPercent"] == 78


def test_select_user_updates_current_user(client: TestClient) -> None:
    select_response = client.post("/api/users/select", json={"userId": "elena"})
    current_response = client.get("/api/users/current")

    assert select_response.status_code == 200
    assert select_response.json()["currentUser"]["id"] == "elena"
    assert current_response.status_code == 200
    assert current_response.json()["id"] == "elena"
