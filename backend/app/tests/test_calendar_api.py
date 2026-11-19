from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, MuscleFatigueEvent, MuscleFatigueSnapshot, SetResult, WorkoutSession
from app.models.training import ExerciseHistoryRecord, UserExerciseState


@pytest.fixture(autouse=True)
def isolated_calendar_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    # Requests use conftest's temporary SQLite DB; do not start local DB/hardware services.
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr("app.main.lifespan", lifespan)


def _save_workout(client: TestClient, *, title: str, status: str, started_at: datetime, minutes: int, user_id: str = "alexey", sets: int = 2) -> int:
    response = client.post(
        "/api/runtime/workouts",
        json={
            "userId": user_id,
            "source": "builder",
            "title": title,
            "status": status,
            "startedAt": started_at.isoformat(),
            "finishedAt": (started_at + timedelta(minutes=minutes)).isoformat(),
            "durationSeconds": minutes * 60,
            "exercises": [
                {
                    "userId": user_id,
                    "exerciseSlug": "machine-pulldown",
                    "exerciseName": "Тяга сверху",
                    "kind": "machine",
                    "orderIndex": 1,
                    "status": "completed",
                    "startedAt": started_at.isoformat(),
                    "finishedAt": (started_at + timedelta(minutes=minutes - 1)).isoformat(),
                    "targetSets": sets,
                    "muscles": [{"muscleId": "back", "name": "Спина", "role": "primary"}],
                    "sets": [
                        {"setNumber": number, "plannedValue": 10, "actualValue": 10, "reps": 10, "weightKg": 50, "tempoLabel": "2-0-2", "amplitudePercent": 90, "subjectiveEffort": 7, "discomfortLevel": 0}
                        for number in range(1, sets + 1)
                    ],
                },
                {
                    "userId": user_id,
                    "exerciseSlug": "forearm-plank",
                    "exerciseName": "Планка",
                    "kind": "timed",
                    "orderIndex": 2,
                    "status": "skipped",
                    "startedAt": started_at.isoformat(),
                    "finishedAt": started_at.isoformat(),
                    "targetSets": 1,
                    "muscles": [],
                    "sets": [],
                },
            ],
        },
    )
    assert response.status_code == 200
    return int(response.json()["workoutSessionId"])


def test_calendar_returns_full_month_grid_without_planning(client: TestClient) -> None:
    response = client.get("/api/calendar", params={"userId": "alexey", "month": "2026-02"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["month"] == "2026-02"
    assert payload["title"] == "Февраль 2026"
    assert payload["weekdays"] == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    assert len(payload["days"]) == 42
    assert payload["days"][0]["id"] == "2026-01-26"
    in_month = [day for day in payload["days"] if day["inMonth"]]
    assert len(in_month) == 28
    assert in_month[0]["id"] == "2026-02-01"
    assert all(day["workouts"] == [] for day in payload["days"])
    assert payload["workoutCount"] == 0
    for legacy_key in ("legend", "quickActions", "selectedDay", "summary", "muscleBalance", "mode"):
        assert legacy_key not in payload


def test_calendar_lists_saved_workouts_by_day_for_the_user(client: TestClient) -> None:
    morning = datetime(2026, 3, 10, 7, 30, tzinfo=UTC)
    evening = datetime(2026, 3, 10, 17, 0, tzinfo=UTC)
    first_id = _save_workout(client, title="Спина и бицепс", status="completed", started_at=morning, minutes=45)
    second_id = _save_workout(client, title="Ноги", status="partial", started_at=evening, minutes=20, sets=1)
    _save_workout(client, title="Чужая тренировка", status="completed", started_at=morning, minutes=30, user_id="elena")
    in_progress = client.post(
        "/api/runtime/workouts",
        json={"userId": "alexey", "source": "builder", "title": "Не завершена", "status": "in_progress", "startedAt": datetime(2026, 3, 12, 10, 0, tzinfo=UTC).isoformat(), "finishedAt": None, "durationSeconds": 0, "exercises": []},
    )
    assert in_progress.status_code == 200

    response = client.get("/api/calendar", params={"userId": "alexey", "month": "2026-03"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["workoutCount"] == 2
    day = next(item for item in payload["days"] if item["id"] == "2026-03-10")
    assert [workout["id"] for workout in day["workouts"]] == [first_id, second_id]
    first, second = day["workouts"]
    assert first["title"] == "Спина и бицепс"
    assert first["status"] == "completed"
    assert first["duration"] == "45 мин"
    assert first["exerciseCount"] == 2
    assert first["setCount"] == 2
    assert first["volume"] == "1 000 кг"
    assert first["exercises"][0]["result"] == "2 подх. · 20 повт. · до 50 кг"
    assert first["exercises"][1] == {"name": "Планка", "status": "skipped", "setCount": 0, "result": "пропущено"}
    assert second["status"] == "partial"
    assert all(not item["workouts"] for item in payload["days"] if item["id"] not in {"2026-03-10"})
    assert "Чужая тренировка" not in response.text
    assert "Не завершена" not in response.text


def test_calendar_defaults_to_current_month_and_marks_today(client: TestClient) -> None:
    response = client.get("/api/calendar", params={"userId": "alexey"})

    assert response.status_code == 200
    payload = response.json()
    today = datetime.now().astimezone().date()
    assert payload["month"] == today.strftime("%Y-%m")
    assert payload["today"] == today.isoformat()
    marked = [day for day in payload["days"] if day["isToday"]]
    assert [day["id"] for day in marked] == [today.isoformat()]
    assert marked[0]["inMonth"] is True


def test_calendar_rejects_invalid_month(client: TestClient) -> None:
    assert client.get("/api/calendar", params={"userId": "alexey", "month": "2026-13"}).status_code == 422
    assert client.get("/api/calendar", params={"userId": "alexey", "month": "05-2026"}).status_code == 422


def _history_count(session: Session, slug: str) -> int:
    return session.scalar(select(func.count()).select_from(ExerciseHistoryRecord).where(ExerciseHistoryRecord.user_id == "alexey", ExerciseHistoryRecord.exercise_slug == slug)) or 0


def _fatigue_total(session: Session) -> float:
    session.expire_all()
    return sum(item.fatigue_score for item in session.scalars(select(MuscleFatigueSnapshot).where(MuscleFatigueSnapshot.user_id == "alexey")))


def test_deleting_workout_removes_it_from_calendar_history_and_fatigue(client: TestClient, db_session: Session) -> None:
    history_before = _history_count(db_session, "machine-pulldown")
    fatigue_before = _fatigue_total(db_session)
    started = datetime(2026, 3, 10, 7, 30, tzinfo=UTC)
    deleted_id = _save_workout(client, title="Спина и бицепс", status="completed", started_at=started, minutes=45)
    kept_id = _save_workout(client, title="Ноги", status="partial", started_at=started + timedelta(hours=9), minutes=20, sets=1)
    exercise_ids = list(db_session.scalars(select(ExerciseSession.id).where(ExerciseSession.workout_session_id == deleted_id)))
    assert _history_count(db_session, "machine-pulldown") == history_before + 2
    fatigue_with_both = _fatigue_total(db_session)
    assert fatigue_with_both > fatigue_before

    assert client.delete(f"/api/runtime/workouts/{deleted_id}", params={"userId": "elena"}).status_code == 404
    response = client.delete(f"/api/runtime/workouts/{deleted_id}", params={"userId": "alexey"})
    assert response.status_code == 204

    day = next(item for item in client.get("/api/calendar", params={"userId": "alexey", "month": "2026-03"}).json()["days"] if item["id"] == "2026-03-10")
    assert [workout["id"] for workout in day["workouts"]] == [kept_id]
    db_session.expire_all()
    assert db_session.get(WorkoutSession, deleted_id) is None
    assert not list(db_session.scalars(select(ExerciseSession).where(ExerciseSession.id.in_(exercise_ids))))
    assert not list(db_session.scalars(select(SetResult).where(SetResult.exercise_session_id.in_(exercise_ids))))
    assert not list(db_session.scalars(select(MuscleFatigueEvent).where(MuscleFatigueEvent.exercise_session_id.in_(exercise_ids))))
    assert _history_count(db_session, "machine-pulldown") == history_before + 1
    fatigue_after = _fatigue_total(db_session)
    assert fatigue_before < fatigue_after < fatigue_with_both
    state = db_session.scalars(select(UserExerciseState).where(UserExerciseState.user_id == "alexey", UserExerciseState.exercise_slug == "machine-pulldown")).one()
    assert state.calibration_payload["lastResult"]["exerciseSessionId"] not in exercise_ids

    assert client.delete(f"/api/runtime/workouts/{deleted_id}", params={"userId": "alexey"}).status_code == 404


def test_deleting_in_progress_workout_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/runtime/workouts",
        json={"userId": "alexey", "source": "builder", "title": "Идёт", "status": "in_progress", "startedAt": datetime(2026, 3, 12, 10, 0, tzinfo=UTC).isoformat(), "finishedAt": None, "durationSeconds": 0, "exercises": []},
    )
    workout_id = response.json()["workoutSessionId"]
    assert client.delete(f"/api/runtime/workouts/{workout_id}", params={"userId": "alexey"}).status_code == 409


def test_calendar_deletion_recalculates_tiers_and_the_workouts_that_earned_them(client: TestClient) -> None:
    owner = {"userId": "elena"}
    start = datetime(2026, 3, 1, 10, tzinfo=UTC)
    first, second, third, fourth = (
        _save_workout(client, title="Дневник", user_id=owner["userId"], status="completed",
                      started_at=start + timedelta(days=day), minutes=20) for day in range(4))
    key = "start.first_workout"

    def tiers_in(workout_id):
        response = client.get(f"/api/runtime/workouts/{workout_id}/awards", params=owner)
        assert response.status_code == 200
        return {a["tier"]["tier"]: a for a in response.json()["awards"] if a["definitionId"] == key}

    initial = tiers_in(first)[1]
    third_award = tiers_in(third)[2]
    other_owner = {"userId": "alexey"}
    other_id = _save_workout(client, title="Другой профиль", user_id=other_owner["userId"], status="completed",
                             started_at=start, minutes=20)
    other_awards = client.get(f"/api/runtime/workouts/{other_id}/awards", params=other_owner).json()
    media_url = third_award["tier"]["imageUrl"]
    image = client.get(media_url)
    assert image.status_code == 200 and "no-cache" in image.headers["cache-control"]
    cached = {"If-None-Match": image.headers["etag"]}
    for number in (1, 2):
        assert client.post(f"/api/achievements/{key}/receipts/detail", params={**owner, "tier": number}).status_code == 200

    assert client.delete(f"/api/runtime/workouts/{first}", params=owner).status_code == 204
    assert client.get(f"/api/runtime/workouts/{first}/awards", params=owner).status_code == 404
    moved = tiers_in(second)[1]
    assert (moved["grantId"], moved["sourceWorkoutId"], moved["isNew"]) == (initial["grantId"], second, False)
    assert datetime.fromisoformat(moved["earnedAt"]) == start + timedelta(days=1, minutes=20)
    assert not tiers_in(third)
    assert tiers_in(fourth)[2]["grantId"] == third_award["grantId"]
    assert tiers_in(fourth)[2]["isNew"] is False
    assert client.get(media_url, headers=cached).status_code == 304

    assert client.delete(f"/api/runtime/workouts/{second}", params=owner).status_code == 204
    line = client.get(f"/api/achievements/{key}", params=owner).json()
    assert (line["currentValue"], line["highestTier"], line["nextTierId"]) == (2, 1, f"{key}:t2")
    assert not line["tiers"][1]["earned"] and line["tiers"][1]["imageUrl"] is None
    assert not tiers_in(fourth)
    assert client.get(media_url, headers=cached).status_code == 404

    replacement = _save_workout(client, title="Ещё одна", user_id=owner["userId"], status="completed",
                                started_at=start + timedelta(days=5), minutes=20)
    again = tiers_in(replacement)[2]
    assert again["grantId"] == third_award["grantId"] and again["isNew"]
    assert client.get(again["tier"]["imageUrl"]).status_code == 200
    for workout_id in (third, fourth, replacement):
        assert client.delete(f"/api/runtime/workouts/{workout_id}", params=owner).status_code == 204
    summary = client.get("/api/achievements/overview", params=owner).json()
    assert (summary["earnedTiers"], summary["newTiers"], summary["activeDays"], summary["recent"]) == (0, 0, 0, [])
    assert client.get(f"/api/runtime/workouts/{other_id}/awards", params=other_owner).json() == other_awards


def test_calendar_removal_and_achievement_correction_commit_together(client: TestClient, monkeypatch) -> None:
    owner = {"userId": "elena"}
    workout_id = _save_workout(client, title="Вместе", user_id=owner["userId"], status="completed",
                               started_at=datetime(2026, 3, 1, 10, tzinfo=UTC), minutes=20)

    def interrupted(*args, **kwargs):
        raise RuntimeError("interrupted recalculation")

    with monkeypatch.context() as patch:
        patch.setattr("app.services.achievements.service.evaluate_user", interrupted)
        with pytest.raises(RuntimeError, match="interrupted recalculation"):
            client.delete(f"/api/runtime/workouts/{workout_id}", params=owner)

    assert client.get("/api/calendar", params={**owner, "month": "2026-03"}).json()["workoutCount"] == 1
    assert client.get(f"/api/runtime/workouts/{workout_id}/awards", params=owner).json()["awards"]
    assert client.delete(f"/api/runtime/workouts/{workout_id}", params=owner).status_code == 204
    assert client.get("/api/achievements/overview", params=owner).json()["earnedTiers"] == 0
    # A new save can reuse both the SQLite workout ID and the old finish timestamp.
    new_id = _save_workout(client, title="Заново", user_id=owner["userId"], status="completed",
                           started_at=datetime(2026, 3, 1, 10, tzinfo=UTC), minutes=20)
    new_awards = client.get(f"/api/runtime/workouts/{new_id}/awards", params=owner).json()["awards"]
    assert new_awards and all(award["sourceWorkoutId"] == new_id and award["isNew"] for award in new_awards)
