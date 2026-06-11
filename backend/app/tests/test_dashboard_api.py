from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def test_dashboard_matches_mock_contract(client: TestClient) -> None:
    response = client.get("/api/dashboard", params={"userId": "alexey", "scenario": "machine-warning"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["greeting"] == "Добрый день, Алексей"
    assert payload["machine"]["machineState"] == "warning"
    assert payload["alerts"][0]["tone"] == "warning"
    assert payload["recommendedExercises"][0]["name"] == "Тяга сверху"
    assert payload["todayWorkout"]["list"][0]["slug"] == "machine-pulldown"
    assert payload["todayWorkout"]["list"][0]["planned"]["label"] == "План"
    assert payload["todayWorkout"]["list"][0]["previewVideoUrl"] is not None

    plank = next(item for item in payload["todayWorkout"]["list"] if item["slug"] == "forearm-plank")
    assert plank["planned"]["primary"] == "45 сек"
    assert plank["planned"]["secondary"] == "вес тела"


def test_dashboard_uses_current_fatigue_snapshots(client: TestClient) -> None:
    workout_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "today",
            "title": "Грудь и трицепс",
            "status": "completed",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "durationSeconds": 1800,
            "exercises": [
                {
                    "userId": "alexey",
                    "exerciseSlug": "band-bench-press",
                    "exerciseName": "Жим с резинкой",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "completed",
                    "startedAt": (datetime.now(UTC) - timedelta(minutes=25)).isoformat(),
                    "finishedAt": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                    "targetSets": 1,
                    "muscles": [
                        {"muscleId": "chest", "name": "Грудь", "role": "primary"},
                        {"muscleId": "triceps", "name": "Трицепс", "role": "secondary"},
                    ],
                    "sets": [
                        {
                            "setNumber": 1,
                            "plannedValue": 12,
                            "actualValue": 12,
                            "reps": 12,
                            "weightKg": 35,
                            "tempoLabel": "2-0-2",
                            "amplitudePercent": 92,
                            "subjectiveEffort": 8,
                            "discomfortLevel": 0,
                        }
                    ],
                }
            ],
        },
    )

    assert workout_response.status_code == 200

    response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert response.status_code == 200
    payload = response.json()
    assert any(item["name"] == "Грудь" and item["score"] > 0 for item in payload["muscles"])
    assert any(item["name"] == "Трицепс" and item["score"] > 0 for item in payload["muscles"])


def test_dashboard_progress_uses_backend_data(client: TestClient) -> None:
    initial_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert initial_response.status_code == 200
    initial_payload = initial_response.json()
    initial_progress = {item["label"]: item["value"] for item in initial_payload["progress"]}
    assert initial_progress["тренировок за месяц"] == "0"
    assert initial_progress["кг за месяц"] == "-0.9 кг"

    workout_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "today",
            "title": "Спина + бицепс",
            "status": "completed",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=50)).isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "durationSeconds": 3000,
            "exercises": [
                {
                    "userId": "alexey",
                    "exerciseSlug": "machine-pulldown",
                    "exerciseName": "Тяга сверху",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "completed",
                    "startedAt": (datetime.now(UTC) - timedelta(minutes=40)).isoformat(),
                    "finishedAt": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                    "targetSets": 2,
                    "muscles": [
                        {"muscleId": "back", "name": "Спина", "role": "primary"},
                        {"muscleId": "biceps", "name": "Бицепс", "role": "secondary"},
                    ],
                    "sets": [
                        {
                            "setNumber": 1,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 50,
                            "tempoLabel": "2-0-2",
                            "amplitudePercent": 90,
                            "subjectiveEffort": 7,
                            "discomfortLevel": 0,
                        },
                        {
                            "setNumber": 2,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 55,
                            "tempoLabel": "2-0-2",
                            "amplitudePercent": 88,
                            "subjectiveEffort": 8,
                            "discomfortLevel": 0,
                        },
                    ],
                }
            ],
        },
    )

    assert workout_response.status_code == 200

    updated_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert updated_response.status_code == 200
    updated_payload = updated_response.json()
    updated_progress = {item["label"]: item["value"] for item in updated_payload["progress"]}
    assert updated_progress["тренировок за месяц"] == "1"
    assert updated_progress["к объёму за неделю"] == "+100%"


def test_dashboard_today_workout_uses_backend_history_and_plan(client: TestClient) -> None:
    workout_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "today",
            "title": "Спина + бицепс",
            "status": "completed",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=50)).isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "durationSeconds": 3000,
            "exercises": [
                {
                    "userId": "alexey",
                    "exerciseSlug": "machine-pulldown",
                    "exerciseName": "Тяга сверху",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "completed",
                    "startedAt": (datetime.now(UTC) - timedelta(minutes=40)).isoformat(),
                    "finishedAt": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                    "targetSets": 2,
                    "muscles": [
                        {"muscleId": "back", "name": "Спина", "role": "primary"},
                        {"muscleId": "biceps", "name": "Бицепс", "role": "secondary"},
                    ],
                    "sets": [
                        {
                            "setNumber": 1,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 50,
                            "tempoLabel": "2-0-2",
                            "amplitudePercent": 90,
                            "subjectiveEffort": 7,
                            "discomfortLevel": 0,
                        },
                        {
                            "setNumber": 2,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 55,
                            "tempoLabel": "2-0-2",
                            "amplitudePercent": 88,
                            "subjectiveEffort": 8,
                            "discomfortLevel": 0,
                        },
                    ],
                }
            ],
        },
    )

    assert workout_response.status_code == 200

    response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert response.status_code == 200
    payload = response.json()
    pulldown = next(item for item in payload["todayWorkout"]["list"] if item["slug"] == "machine-pulldown")
    assert pulldown["previous"]["primary"] == "55 кг"
    assert pulldown["previous"]["secondary"] == "20 повторов"
    assert pulldown["planned"]["primary"] == "55 кг"
    assert pulldown["planned"]["secondary"] == "20 повторов"


def test_dashboard_uses_saved_today_plan_order(client: TestClient) -> None:
    save_response = client.put(
        "/api/today/plan",
        json={
            "userId": "alexey",
            "slugs": ["barbell-curl", "machine-pulldown", "forearm-plank"],
        },
    )

    assert save_response.status_code == 200

    response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["slug"] for item in payload["todayWorkout"]["list"]] == ["barbell-curl", "machine-pulldown", "forearm-plank"]


def test_dashboard_uses_saved_today_plan_after_delete(client: TestClient) -> None:
    save_response = client.put(
        "/api/today/plan",
        json={
            "userId": "alexey",
            "slugs": ["machine-pulldown", "barbell-curl"],
        },
    )

    assert save_response.status_code == 200

    response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["slug"] for item in payload["todayWorkout"]["list"]] == ["machine-pulldown", "barbell-curl"]


def test_dashboard_builder_workouts_show_today_progress(client: TestClient) -> None:
    dashboard_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert dashboard_response.status_code == 200
    workout = dashboard_response.json()["workouts"][0]

    save_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "builder",
            "title": workout["title"],
            "status": "in_progress",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=15)).isoformat(),
            "finishedAt": None,
            "durationSeconds": 900,
            "exercises": [
                {
                    "userId": "alexey",
                    "exerciseSlug": "machine-pulldown",
                    "exerciseName": "Тяга сверху",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "completed",
                    "startedAt": (datetime.now(UTC) - timedelta(minutes=12)).isoformat(),
                    "finishedAt": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                    "targetSets": 1,
                    "muscles": [
                        {"muscleId": "back", "name": "Спина", "role": "primary"},
                    ],
                    "sets": [
                        {
                            "setNumber": 1,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 45,
                            "tempoLabel": "2-0-2",
                            "subjectiveEffort": 7,
                            "discomfortLevel": 0,
                        }
                    ],
                }
            ],
        },
    )

    assert save_response.status_code == 200

    updated_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert updated_response.status_code == 200
    updated_workout = next(item for item in updated_response.json()["workouts"] if item["id"] == workout["id"])
    assert updated_workout["todayStatus"] == "in_progress"
    assert updated_workout["resumeAvailable"] is True
    assert updated_workout["todayCompletedExercises"] == 1
    assert updated_workout["todayProgressPercent"] > 0
    assert updated_workout["exercises"][0]["status"] == "completed"
    assert updated_workout["exercises"][0]["completedSets"] == 1
    assert updated_workout["exercises"][0]["targetSets"] >= 1


def test_dashboard_day_progress_reset_hides_today_builder_progress(client: TestClient) -> None:
    dashboard_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert dashboard_response.status_code == 200
    workout = dashboard_response.json()["workouts"][0]

    save_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "builder",
            "title": workout["title"],
            "status": "in_progress",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
            "finishedAt": None,
            "durationSeconds": 600,
            "exercises": [],
        },
    )

    assert save_response.status_code == 200

    reset_response = client.post("/api/dashboard/day-progress/reset", json={"userId": "alexey"})

    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "ok"

    updated_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert updated_response.status_code == 200
    updated_workout = next(item for item in updated_response.json()["workouts"] if item["id"] == workout["id"])
    assert updated_workout["todayStatus"] == "idle"
    assert updated_workout["todayProgressPercent"] == 0
    assert updated_workout["resumeAvailable"] is False


def test_dashboard_hides_builder_progress_from_previous_training_day(client: TestClient) -> None:
    dashboard_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert dashboard_response.status_code == 200
    workout = dashboard_response.json()["workouts"][0]

    save_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "builder",
            "title": workout["title"],
            "status": "in_progress",
            "startedAt": (datetime.now(UTC) - timedelta(hours=26)).isoformat(),
            "finishedAt": None,
            "durationSeconds": 600,
            "exercises": [
                {
                    "userId": "alexey",
                    "exerciseSlug": "machine-pulldown",
                    "exerciseName": "Тяга сверху",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "in_progress",
                    "startedAt": (datetime.now(UTC) - timedelta(hours=25, minutes=50)).isoformat(),
                    "finishedAt": None,
                    "targetSets": 4,
                    "muscles": [
                        {"muscleId": "back", "name": "Спина", "role": "primary"},
                    ],
                    "sets": [
                        {
                            "setNumber": 1,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 45,
                            "tempoLabel": "2-0-2",
                            "subjectiveEffort": 7,
                            "discomfortLevel": 0,
                        }
                    ],
                }
            ],
        },
    )

    assert save_response.status_code == 200

    updated_response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert updated_response.status_code == 200
    updated_workout = next(item for item in updated_response.json()["workouts"] if item["id"] == workout["id"])
    assert updated_workout["todayStatus"] == "idle"
    assert updated_workout["todayProgressPercent"] == 0
    assert all(item["completedSets"] == 0 for item in updated_workout["exercises"])
