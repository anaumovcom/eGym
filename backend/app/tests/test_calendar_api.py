from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


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
    assert first["duration"] == "45 минут"
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
