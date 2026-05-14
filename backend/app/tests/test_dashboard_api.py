from fastapi.testclient import TestClient


def test_dashboard_matches_mock_contract(client: TestClient) -> None:
    response = client.get("/api/dashboard", params={"userId": "alexey", "scenario": "machine-warning"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["greeting"] == "Добрый день, Алексей"
    assert payload["machine"]["machineState"] == "warning"
    assert payload["alerts"][0]["tone"] == "warning"
    assert payload["recommendedExercises"][0]["name"] == "Тяга сверху"
