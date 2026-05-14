from fastapi.testclient import TestClient


def test_exercise_catalog_and_details_use_real_backend(client: TestClient) -> None:
    catalog_response = client.get("/api/exercises", params={"userId": "alexey", "search": "pulldown"})

    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert catalog_payload["total"] >= 1
    assert any(item["slug"] == "machine-pulldown" for item in catalog_payload["items"])

    details_response = client.get("/api/exercises/machine-pulldown", params={"userId": "alexey"})
    assert details_response.status_code == 200
    details_payload = details_response.json()
    assert details_payload["slug"] == "machine-pulldown"
    assert details_payload["loadSettings"]["weight"] >= 0
    assert details_payload["compatibility"]["title"]


def test_stage2_real_api_routes_return_frontend_shapes(client: TestClient) -> None:
    quick_start = client.get("/api/quick-start", params={"userId": "alexey", "selected": "machine-pulldown"})
    today = client.get("/api/today", params={"userId": "alexey", "scenario": "planned", "selected": "machine-pulldown"})
    programs = client.get("/api/programs", params={"selected": "back-biceps"})
    calendar = client.get("/api/calendar", params={"mode": "week", "selectedDayId": "2026-05-14"})
    builder = client.get("/api/builder", params={"selectedExerciseId": "group-pullups-1"})

    assert quick_start.status_code == 200
    assert quick_start.json()["selectedExercise"]["exercise"]["slug"] == "machine-pulldown"

    assert today.status_code == 200
    assert today.json()["selectedExerciseId"] == "machine-pulldown"
    assert len(today.json()["exerciseRows"]) >= 3

    assert programs.status_code == 200
    assert programs.json()["selectedProgram"]["id"] == "back-biceps"

    assert calendar.status_code == 200
    calendar_payload = calendar.json()
    assert calendar_payload["mode"] == "week"
    assert calendar_payload["selectedDayId"] == "2026-05-14"
    assert len(calendar_payload["days"]) >= 5

    assert builder.status_code == 200
    assert builder.json()["selectedExerciseId"] == "group-pullups-1"
