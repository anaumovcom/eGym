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


def test_update_profile_persists_user_profile_and_primary_goal(client: TestClient) -> None:
    response = client.put(
        "/api/users/alexey/profile",
        json={
            "name": "Алексей П.",
            "birthDate": "1991-06-12",
            "heightCm": 183,
            "weightKg": 83.4,
            "notes": "Без боли",
            "goalLabel": "Жим 100 кг",
            "goalType": "strength",
            "targetValue": 100,
            "targetUnit": "кг",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Алексей П."
    assert payload["profile"] == {
        "birthDate": "1991-06-12",
        "heightCm": 183,
        "weightKg": 83.4,
        "photoUrl": None,
        "notes": "Без боли",
    }
    primary = next(goal for goal in payload["goals"] if goal["isPrimary"])
    assert primary["label"] == "Жим 100 кг"
    assert primary["goalType"] == "strength"
    assert primary["targetValue"] == 100

    current = client.get("/api/users/current")
    assert current.status_code == 200
    assert current.json()["profile"]["weightKg"] == 83.4


def test_update_profile_validates_ranges_and_missing_user(client: TestClient) -> None:
    invalid = client.put(
        "/api/users/alexey/profile",
        json={"name": "А", "heightCm": 20, "goalLabel": "Активность"},
    )
    missing = client.put(
        "/api/users/missing/profile",
        json={"name": "Нет", "heightCm": 180, "goalLabel": "Активность"},
    )

    assert invalid.status_code == 422
    assert missing.status_code == 404
