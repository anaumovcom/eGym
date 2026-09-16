import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.dashboard import DashboardBuilderWorkoutSchema


@pytest.fixture(autouse=True)
def isolated_dashboard_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    # Requests use conftest's temporary SQLite DB; do not start local DB/hardware services.
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr("app.main.lifespan", lifespan)


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
    assert updated_workout["lastPerformedAt"] is None
    assert updated_workout["lastStatus"] is None


def test_dashboard_builder_last_execution_empty_history(client: TestClient) -> None:
    response = client.get("/api/dashboard", params={"userId": "alexey"})

    assert response.status_code == 200
    workouts = response.json()["workouts"]
    assert workouts
    assert all(item["lastPerformedAt"] is None and item["lastStatus"] is None for item in workouts)


@pytest.mark.parametrize("status", ["completed", "partial", "aborted"])
@pytest.mark.parametrize("has_finished_at", [True, False])
def test_dashboard_builder_last_execution_previous_day(
    client: TestClient, status: str, has_finished_at: bool,
) -> None:
    response = client.get("/api/dashboard", params={"userId": "alexey"})
    assert response.status_code == 200
    workout = response.json()["workouts"][0]
    started_at = datetime.now(UTC) - timedelta(days=2)
    finished_at = started_at + timedelta(minutes=30) if has_finished_at else None
    expected_at = finished_at or started_at

    # Insert out of chronological order to ensure the latest execution wins, not the last row.
    for user_id, source, title, session_status, started, finished in [
        ("alexey", "builder", workout["title"], status, started_at, finished_at),
        ("alexey", "builder", workout["title"], "completed", started_at - timedelta(days=1), None),
        ("elena", "builder", workout["title"], "completed", started_at + timedelta(hours=1), None),
        ("alexey", "catalog", workout["title"], "completed", started_at + timedelta(hours=2), None),
        ("alexey", "builder", "Other workout", "completed", started_at + timedelta(hours=3), None),
        ("alexey", "builder", workout["title"], "in_progress", started_at + timedelta(hours=4), None),
    ]:
        saved = client.post(
            "/api/runtime/workouts",
            json={
                "userId": user_id,
                "source": source,
                "title": title,
                "status": session_status,
                "startedAt": started.isoformat(),
                "finishedAt": finished.isoformat() if finished else None,
                "exercises": [],
            },
        )
        assert saved.status_code == 200

    # Resetting today's progress must not erase the last execution from earlier days.
    reset = client.post("/api/dashboard/day-progress/reset", json={"userId": "alexey"})
    assert reset.status_code == 200
    updated = client.get("/api/dashboard", params={"userId": "alexey"})
    assert updated.status_code == 200
    result = next(item for item in updated.json()["workouts"] if item["id"] == workout["id"])
    assert result["todayStatus"] == "idle"
    assert result["lastStatus"] == status
    assert datetime.fromisoformat(result["lastPerformedAt"]) == expected_at


def test_dashboard_builder_last_execution_fields_are_optional(client: TestClient) -> None:
    workout = DashboardBuilderWorkoutSchema(id="test", title="Test", exercises=[], duration="0")
    assert workout.last_performed_at is None
    assert workout.last_status is None
    schemas = client.get("/api/openapi.json").json()["components"]["schemas"]
    schema = schemas["DashboardBuilderWorkoutSchema"]
    assert "lastPerformedAt" not in schema["required"]
    assert "lastStatus" not in schema["required"]
    assert schema["properties"]["lastStatus"]["anyOf"] == [
        {"type": "string", "enum": ["completed", "partial", "aborted"]},
        {"type": "null"},
    ]
    artifact = Path(__file__).resolve().parents[2] / "openapi" / "openapi.json"
    exported = json.loads(artifact.read_text(encoding="utf-8"))["components"]["schemas"]
    for name in ("DashboardBuilderWorkoutSchema", "DashboardBuilderWorkoutExerciseSchema"):
        assert exported[name] == schemas[name]
    assert exported["DashboardDataSchema"]["properties"]["workouts"] == schemas["DashboardDataSchema"]["properties"]["workouts"]


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
