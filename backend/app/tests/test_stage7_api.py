from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.api.routes.analytics import media_service
from app.models.analytics import ExerciseSession, MuscleFatigueEvent, MuscleFatigueSnapshot
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


def test_fatigue_grows_after_each_set_and_across_exercises(client: TestClient, db_session) -> None:
    started_at = datetime.now(UTC) - timedelta(minutes=20)
    workout_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "today",
            "title": "Грудь и трицепс",
            "status": "in_progress",
            "startedAt": started_at.isoformat(),
            "durationSeconds": 0,
            "exercises": [],
        },
    )
    assert workout_response.status_code == 200
    workout_session_id = workout_response.json()["workoutSessionId"]

    exercise_response = client.post(
        "/api/runtime/exercises",
        json={
            "userId": "alexey",
            "workoutSessionId": workout_session_id,
            "exerciseSlug": "band-bench-press",
            "exerciseName": "Жим с резинкой",
            "kind": "machine",
            "orderIndex": 1,
            "status": "in_progress",
            "startedAt": started_at.isoformat(),
            "targetSets": 2,
            "muscles": [
                {"muscleId": "chest", "name": "Грудь", "role": "primary"},
                {"muscleId": "triceps", "name": "Трицепс", "role": "secondary"},
            ],
            "sets": [],
        },
    )
    assert exercise_response.status_code == 200
    exercise_session_id = exercise_response.json()["exerciseSessionId"]

    first_set = client.post(
        "/api/runtime/sets",
        json={
            "exerciseSessionId": exercise_session_id,
            "setNumber": 1,
            "plannedValue": 12,
            "actualValue": 12,
            "setType": "work",
            "reps": 12,
            "weightKg": 35,
            "tempoLabel": "хорошо",
            "subjectiveEffort": 7,
            "discomfortLevel": 0,
        },
    )
    assert first_set.status_code == 200
    assert {item["muscleId"] for item in first_set.json()["fatigue"]} == {"chest", "triceps"}
    db_session.expire_all()
    chest_after_first = db_session.scalars(
        select(MuscleFatigueSnapshot).where(MuscleFatigueSnapshot.user_id == "alexey", MuscleFatigueSnapshot.muscle_id == "chest")
    ).first()
    assert chest_after_first is not None
    first_score = chest_after_first.fatigue_score

    second_set = client.post(
        "/api/runtime/sets",
        json={
            "exerciseSessionId": exercise_session_id,
            "setNumber": 2,
            "plannedValue": 10,
            "actualValue": 10,
            "setType": "failure",
            "reps": 10,
            "weightKg": 37.5,
            "tempoLabel": "хорошо",
            "subjectiveEffort": 9,
            "discomfortLevel": 1,
        },
    )
    assert second_set.status_code == 200
    db_session.expire_all()
    chest_after_second = db_session.scalars(
        select(MuscleFatigueSnapshot).where(MuscleFatigueSnapshot.user_id == "alexey", MuscleFatigueSnapshot.muscle_id == "chest")
    ).first()
    assert chest_after_second is not None
    assert chest_after_second.fatigue_score > first_score
    second_score = chest_after_second.fatigue_score

    finalize_response = client.post(
        "/api/runtime/exercises",
        json={
            "exerciseSessionId": exercise_session_id,
            "userId": "alexey",
            "workoutSessionId": workout_session_id,
            "exerciseSlug": "band-bench-press",
            "exerciseName": "Жим с резинкой",
            "kind": "machine",
            "orderIndex": 1,
            "status": "completed",
            "startedAt": started_at.isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "targetSets": 2,
            "muscles": [
                {"muscleId": "chest", "name": "Грудь", "role": "primary"},
                {"muscleId": "triceps", "name": "Трицепс", "role": "secondary"},
            ],
            "sets": [],
        },
    )
    assert finalize_response.status_code == 200
    db_session.expire_all()
    chest_events_after_finalize = db_session.scalars(
        select(MuscleFatigueEvent).where(MuscleFatigueEvent.exercise_session_id == exercise_session_id, MuscleFatigueEvent.muscle_id == "chest")
    ).all()
    assert len(chest_events_after_finalize) == 2

    second_exercise_response = client.post(
        "/api/runtime/exercises",
        json={
            "userId": "alexey",
            "workoutSessionId": workout_session_id,
            "exerciseSlug": "band-chest-fly",
            "exerciseName": "Сведение рук с резинкой",
            "kind": "machine",
            "orderIndex": 2,
            "status": "in_progress",
            "startedAt": datetime.now(UTC).isoformat(),
            "targetSets": 1,
            "muscles": [{"muscleId": "chest", "name": "Грудь", "role": "primary"}],
            "sets": [],
        },
    )
    assert second_exercise_response.status_code == 200
    second_exercise_session_id = second_exercise_response.json()["exerciseSessionId"]
    third_set = client.post(
        "/api/runtime/sets",
        json={
            "exerciseSessionId": second_exercise_session_id,
            "setNumber": 1,
            "plannedValue": 15,
            "actualValue": 15,
            "setType": "work",
            "reps": 15,
            "weightKg": 20,
            "tempoLabel": "хорошо",
            "subjectiveEffort": 7,
            "discomfortLevel": 0,
        },
    )
    assert third_set.status_code == 200
    db_session.expire_all()
    all_chest_events = db_session.scalars(
        select(MuscleFatigueEvent).where(MuscleFatigueEvent.workout_session_id == workout_session_id, MuscleFatigueEvent.muscle_id == "chest")
    ).all()
    chest_after_third = db_session.scalars(
        select(MuscleFatigueSnapshot).where(MuscleFatigueSnapshot.user_id == "alexey", MuscleFatigueSnapshot.muscle_id == "chest")
    ).first()
    assert len(all_chest_events) == 3
    assert chest_after_third is not None
    assert chest_after_third.fatigue_score > second_score


def test_save_workout_links_existing_exercise_session(client: TestClient, db_session) -> None:
    exercise_response = client.post(
        "/api/runtime/exercises",
        json={
            "userId": "alexey",
            "exerciseSlug": "band-bench-press",
            "exerciseName": "Жим с резинкой",
            "kind": "machine",
            "orderIndex": 1,
            "status": "partial",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=12)).isoformat(),
            "finishedAt": (datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
            "targetSets": 2,
            "muscles": [{"muscleId": "chest", "name": "Грудь", "role": "primary"}],
            "sets": [
                {
                    "setNumber": 1,
                    "plannedValue": 12,
                    "actualValue": 8,
                    "reps": 8,
                    "weightKg": 35,
                    "tempoLabel": "частично",
                    "subjectiveEffort": 8,
                    "discomfortLevel": 0,
                    "machineMetrics": {"completionStatus": "partial"},
                }
            ],
        },
    )
    assert exercise_response.status_code == 200
    exercise_session_id = exercise_response.json()["exerciseSessionId"]

    workout_response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": "alexey",
            "source": "today",
            "title": "Грудь и трицепс",
            "status": "partial",
            "startedAt": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "durationSeconds": 1200,
            "exerciseSessionIds": [exercise_session_id],
            "exercises": [],
        },
    )

    assert workout_response.status_code == 200
    workout_id = workout_response.json()["workoutSessionId"]
    db_session.expire_all()
    linked_session = db_session.get(ExerciseSession, exercise_session_id)
    assert linked_session.workout_session_id == workout_id
    saved_sessions = list(db_session.scalars(select(ExerciseSession).where(ExerciseSession.exercise_slug == "band-bench-press")))
    assert len(saved_sessions) == 1


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


def test_fatigue_reset_zeroes_current_snapshots(client: TestClient, db_session) -> None:
    db_session.add(
        MuscleFatigueSnapshot(
            user_id="alexey",
            muscle_id="chest",
            fatigue_score=42.0,
            recovery_half_life_hours=24.0,
            calculated_at=datetime.now(UTC),
            last_load_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    before_response = client.get("/api/fatigue", params={"userId": "alexey", "mode": "current"})

    assert before_response.status_code == 200
    before_payload = before_response.json()
    assert any(item["score"] > 0 for item in before_payload["muscles"])

    reset_response = client.post("/api/fatigue/reset", json={"userId": "alexey"})

    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "ok"

    after_response = client.get("/api/fatigue", params={"userId": "alexey", "mode": "current"})

    assert after_response.status_code == 200
    after_payload = after_response.json()
    assert after_payload["muscles"]
    assert all(item["score"] == 0 for item in after_payload["muscles"])


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