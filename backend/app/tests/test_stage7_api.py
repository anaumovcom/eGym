from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes.analytics import media_service
from app.services.fatigue_service import FatigueService


def test_save_workout_and_read_progress_and_fatigue(client: TestClient) -> None:
    response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "today",
            "title": "Грудь и трицепс",
            "subtitle": "Силовой блок",
            "status": "completed",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=50)).isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "durationSeconds": 3000,
            "feeling": "hard",
            "discomfort": "none",
            "exercises": [
                {
                    "userId": "alexey",
                    "exerciseSlug": "band-bench-press",
                    "exerciseName": "Жим с резинкой",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "completed",
                    "startedAt": (datetime.now(UTC) - timedelta(minutes=40)).isoformat(),
                    "finishedAt": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
                    "targetSets": 2,
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
                            "subjectiveEffort": 7,
                            "discomfortLevel": 0,
                        },
                        {
                            "setNumber": 2,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 37.5,
                            "tempoLabel": "2-0-2",
                            "amplitudePercent": 89,
                            "subjectiveEffort": 8,
                            "discomfortLevel": 1,
                        },
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["outcome"] == "completed"
    assert "минут" in summary["metrics"][0]["value"]

    progress_response = client.get("/api/progress", params={"userId": "alexey", "period": "30d"})
    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["summaryCards"]
    assert progress_payload["selectedExercise"]["history"]

    fatigue_response = client.get("/api/fatigue", params={"userId": "alexey", "mode": "current"})
    assert fatigue_response.status_code == 200
    fatigue_payload = fatigue_response.json()
    assert fatigue_payload["muscles"]
    assert any(item["id"] == "chest" and item["score"] > 0 for item in fatigue_payload["muscles"])


def test_legacy_back_fatigue_is_split_into_detail_muscles(client: TestClient, db_session) -> None:
    workout_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "today",
            "title": "Спина",
            "status": "completed",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "durationSeconds": 1800,
            "exercises": [
                {
                    "userId": "alexey",
                    "exerciseSlug": "machine-seated-cable-row",
                    "exerciseName": "Тяга к поясу",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "completed",
                    "startedAt": (datetime.now(UTC) - timedelta(minutes=25)).isoformat(),
                    "finishedAt": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                    "targetSets": 1,
                    "muscles": [
                        {"muscleId": "back", "name": "Спина", "role": "primary"}
                    ],
                    "sets": [
                        {
                            "setNumber": 1,
                            "plannedValue": 10,
                            "actualValue": 10,
                            "reps": 10,
                            "weightKg": 45,
                            "tempoLabel": "2-0-2",
                            "amplitudePercent": 90,
                            "subjectiveEffort": 7,
                            "discomfortLevel": 0,
                        }
                    ],
                }
            ],
        },
    )

    assert workout_response.status_code == 200

    fatigue_response = client.get("/api/fatigue", params={"userId": "alexey", "mode": "current"})
    assert fatigue_response.status_code == 200
    fatigue_payload = fatigue_response.json()

    assert any(item["id"] == "lats" and item["score"] > 0 for item in fatigue_payload["muscles"])
    assert any(item["id"] == "traps-middle" and item["score"] > 0 for item in fatigue_payload["muscles"])
    assert all(item["id"] != "back" for item in fatigue_payload["muscles"])


def test_photo_progress_upload_list_and_delete(client: TestClient, tmp_path: Path) -> None:
    media_service.media_root = tmp_path
    image = Image.new("RGB", (120, 180), color=(240, 240, 240))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    upload_response = client.post(
        "/api/photo-progress",
        data={"userId": "alexey", "mode": "manual", "view": "front"},
        files={"file": ("progress.png", buffer.getvalue(), "image/png")},
    )
    assert upload_response.status_code == 200
    photo_id = upload_response.json()["id"]

    list_response = client.get("/api/photo-progress", params={"userId": "alexey"})
    assert list_response.status_code == 200
    assert any(photo["id"] == photo_id for photo in list_response.json()["photos"])

    delete_response = client.delete(f"/api/photo-progress/{photo_id}", params={"confirm": True})
    assert delete_response.status_code == 204


def test_fatigue_decay_uses_elapsed_time() -> None:
    service = FatigueService()
    decayed = service.decay_score(144.0, elapsed_hours=24.0, recovery_half_life_hours=24.0)

    assert round(decayed, 2) == 72.0