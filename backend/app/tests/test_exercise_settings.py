from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_session
from app.main import create_app
from app.models.training import ExerciseHistoryRecord, UserExerciseState
from app.models.user import User
from app.services.runtime_service import RuntimeService
from app.services.training_service import TrainingService

PATH = "/api/runtime/exercises/settings"
SLUG = "barbell-curl"


@pytest.fixture(autouse=True)
def isolated_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr("app.main.lifespan", lifespan)


@pytest.fixture(autouse=True)
def no_builder_workouts(db_session: Session) -> None:
    # These tests cover exercises outside "Мои тренировки"; workout exercises take their settings
    # from the workout profiles instead (see test_exercise_profiles.py).
    for program in TrainingService()._programs(db_session, "alexey"):
        TrainingService().delete_program(db_session, program_id=program.id, user_id="alexey")


def settings(**changes: object) -> dict:
    return {"userId": "alexey", "exerciseSlug": SLUG, "weight": 37, "sets": 5,
            "reps": 17, "restSeconds": 135, **changes}


def read(client: TestClient, slug: str = SLUG, user: str = "alexey") -> dict | None:
    response = client.get(PATH, params={"userId": user, "exerciseSlug": slug})
    assert response.status_code == 200
    return response.json()


def result(number: int = 1, **changes: object) -> dict:
    return {"setNumber": number, "plannedValue": 12, "actualValue": 7,
            "reps": 7, "weightKg": 40, "tempoLabel": "Обычный", **changes}


def exercise(**changes: object) -> dict:
    return {"userId": "alexey", "exerciseSlug": SLUG, "exerciseName": "Curl",
            "kind": "machine", "status": "completed", "targetSets": 4,
            "startedAt": datetime.now(UTC).isoformat(), "sets": [result()], **changes}


def save_exercise(client: TestClient, **changes: object) -> int:
    response = client.post("/api/runtime/exercises", json=exercise(**changes))
    assert response.status_code == 200, response.text
    return response.json()["exerciseSessionId"]


def state(db: Session, slug: str = SLUG) -> UserExerciseState:
    row = db.scalar(select(UserExerciseState).where(
        UserExerciseState.user_id == "alexey", UserExerciseState.exercise_slug == slug))
    if row is None:
        row = UserExerciseState(user_id="alexey", exercise_slug=slug)
        db.add(row)
    return row


def test_api_roundtrip_restart_isolation_and_catalog(
    client: TestClient, db_session: Session, session_factory: sessionmaker[Session],
) -> None:
    other_user = db_session.scalar(select(User.id).where(User.id != "alexey"))
    assert other_user is not None
    assert read(client, "alphabet") is None
    assert client.put(PATH, json=settings(weight=0, restSeconds=0, mode="Custom", tempo="Slow",
                                         trainingMode="strength", trainingDayType="light")).status_code == 200
    expected = {"weight": 0, "sets": 5, "reps": 17, "restSeconds": 0, "mode": "Custom",
                "tempo": "Slow", "trainingMode": "strength", "trainingDayType": "light"}
    assert read(client) == expected
    assert read(client, "alphabet") is None
    assert read(client, SLUG, other_user) != expected
    # New app, service and SQLAlchemy sessions over the same database: no process-local cache.
    app = create_app()

    def sessions() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as restarted:
        assert read(restarted) == expected
        details = restarted.get(f"/api/exercises/{SLUG}", params={"userId": "alexey"}).json()["loadSettings"]
        assert {key: details[key] for key in ("weight", "sets", "reps", "restSeconds", "mode", "tempo")} == {
            key: expected[key] for key in ("weight", "sets", "reps", "restSeconds", "mode", "tempo")}
        assert RuntimeService().get_exercise_settings(db_session, "alexey", SLUG).reps == 17
    row = state(db_session)
    assert (row.working_weight, row.working_sets, row.working_reps, row.rest_seconds) == (0, 5, 17, 0)


@pytest.mark.parametrize("field,value", [
    ("weight", -1), ("weight", 2001), ("weight", "NaN"), ("weight", "Infinity"),
    ("sets", 0), ("sets", 101), ("reps", 0), ("reps", 86401),
    ("restSeconds", -1), ("restSeconds", 86401),
])
def test_settings_validation(client: TestClient, field: str, value: object) -> None:
    assert client.put(PATH, json=settings(**{field: value})).status_code == 422


@pytest.mark.parametrize("changes", [{"userId": "missing"}, {"exerciseSlug": "missing"}])
def test_settings_unknown_identity(client: TestClient, changes: dict) -> None:
    assert client.put(PATH, json=settings(**changes)).status_code == 404
    assert client.get(PATH, params={"userId": "alexey", "exerciseSlug": SLUG, **changes}).status_code == 404


def test_settings_preserve_other_metadata_and_create_no_history(client: TestClient, db_session: Session) -> None:
    row = state(db_session)
    row.calibration_payload = {"calibration": "keep", "lastResult": {"repsPerSet": 2}}
    db_session.commit()
    before = db_session.scalar(select(func.count()).select_from(ExerciseHistoryRecord))
    assert client.put(PATH, json=settings()).status_code == 200
    db_session.refresh(row)
    assert row.calibration_payload["calibration"] == "keep"
    assert row.calibration_payload["lastResult"] == {"repsPerSet": 2}
    assert db_session.scalar(select(func.count()).select_from(ExerciseHistoryRecord)) == before


def test_multiset_partial_targets_and_latest_zero_weight(client: TestClient, db_session: Session) -> None:
    save_exercise(client, status="partial", sets=[result(1, weightKg=80), result(2, weightKg=0)])
    remembered = read(client)
    assert (remembered["weight"], remembered["sets"], remembered["reps"]) == (0, 4, 12)
    db_session.expire_all()
    row = state(db_session)
    assert row.working_reps == 12
    assert row.calibration_payload["lastResult"]["totalReps"] == 14


@pytest.mark.parametrize("kind,slug", [("timed", "forearm-plank"), ("stretch", "abdominals-stretch-variation-one")])
def test_timed_targets_not_actual_or_total(client: TestClient, kind: str, slug: str) -> None:
    save_exercise(client, kind=kind, exerciseSlug=slug, sets=[
        result(1, reps=None, plannedValue=90, actualValue=20, durationSeconds=20, weightKg=0),
        result(2, reps=None, plannedValue=75, actualValue=10, durationSeconds=10, weightKg=0),
    ])
    assert read(client, slug)["reps"] == 75
    assert read(client, slug)["sets"] == 4


def test_legacy_reps_per_set_and_zero(client: TestClient, db_session: Session) -> None:
    row = state(db_session)
    row.working_weight, row.working_reps, row.working_sets, row.rest_seconds = 90, 36, 3, 0
    row.calibration_payload = {"lastResult": {"repsPerSet": 12, "sets": 3, "weightKg": 0}}
    db_session.commit()
    assert read(client)["reps"] == 12
    assert read(client)["weight"] == 0
    loaded = client.get(f"/api/exercises/{SLUG}", params={"userId": "alexey"}).json()["loadSettings"]
    assert (loaded["reps"], loaded["weight"], loaded["restSeconds"]) == (12, 0, 0)


@pytest.mark.parametrize("kind", ["timed", "stretch"])
def test_legacy_timed_uses_last_planned_target(client: TestClient, db_session: Session, kind: str) -> None:
    exercise_id = save_exercise(client, kind=kind, sets=[result(reps=None, plannedValue=90, actualValue=15)])
    row = state(db_session)
    db_session.refresh(row)
    row.calibration_payload = {"lastResult": {"exerciseSessionId": exercise_id, "repsPerSet": 15,
                                               "sets": 4, "weightKg": 0}}
    db_session.commit()
    assert read(client)["reps"] == 90


@pytest.mark.parametrize("weight", [0, 20])
def test_adjustment_uses_current_not_saved_weight(client: TestClient, weight: int) -> None:
    assert client.put(PATH, json=settings(weight=90)).status_code == 200
    response = client.post("/api/runtime/exercises/load-adjustment", json={
        "userId": "alexey", "exerciseSlug": SLUG, "kind": "machine", "direction": "increase",
        "currentWeightKg": weight, "currentReps": 11, "currentSets": 4, "restSeconds": 0,
    })
    assert response.status_code == 200
    assert response.json()["weightKg"] == weight + 2.5
    saved = read(client)
    assert (saved["weight"], saved["reps"], saved["sets"], saved["restSeconds"]) == (weight + 2.5, 11, 4, 0)


@pytest.mark.parametrize("kind", ["timed", "stretch"])
def test_adjustment_seconds_and_settings_survive(client: TestClient, kind: str) -> None:
    assert client.put(PATH, json=settings(weight=0, reps=80)).status_code == 200
    response = client.post("/api/runtime/exercises/load-adjustment", json={
        "userId": "alexey", "exerciseSlug": SLUG, "kind": kind, "direction": "increase",
        "currentWeightKg": 0,
    })
    assert response.status_code == 200
    assert response.json()["loadLabel"] == "85 сек"
    assert read(client)["reps"] == 85


def test_explicit_snapshot_stale_finalization_and_warmup(client: TestClient) -> None:
    old_start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    old_id = save_exercise(client, startedAt=old_start, status="in_progress", sets=[])
    assert client.put(PATH, json=settings(weight=21)).status_code == 200
    expected = read(client)
    save_exercise(client, exerciseSessionId=old_id, startedAt=old_start, sets=[result(weightKg=99)])
    assert read(client) == expected
    save_exercise(client, sets=[result(setType="warmup", weightKg=100, restDurationSeconds=10)])
    assert read(client) == expected
    # Fresh working performance changes only the weight: plan rest is derived from the settings.
    save_exercise(client, sets=[result(weightKg=0, restDurationSeconds=0)])
    assert read(client) == {**expected, "weight": 0}


def test_midexercise_weight_no_history_and_final_replay(client: TestClient, db_session: Session) -> None:
    exercise_id = save_exercise(client, status="in_progress", sets=[])
    assert client.put(PATH, json=settings(weight=50)).status_code == 200
    before = db_session.scalar(select(func.count()).select_from(ExerciseHistoryRecord))
    for set_type, weight, expected in [("warmup", 70, 50), ("working", 30, 30), ("working", 0, 0)]:
        response = client.post("/api/runtime/sets", json={
            "exerciseSessionId": exercise_id, **result(weightKg=weight, setType=set_type),
        })
        assert response.status_code == 200, response.text
        assert read(client)["weight"] == expected
        assert read(client)["reps"] == 17
    assert db_session.scalar(select(func.count()).select_from(ExerciseHistoryRecord)) == before
    # Saving new setup after the set protects it from a stale finalization/replayed set list.
    assert client.put(PATH, json=settings(weight=25)).status_code == 200
    save_exercise(client, exerciseSessionId=exercise_id,
                  startedAt=(datetime.now(UTC) - timedelta(hours=1)).isoformat(), sets=[result(weightKg=90)])
    assert read(client)["weight"] == 25


def test_sided_partial_remembers_logical_target_sets(client: TestClient) -> None:
    save_exercise(client, perSide=True, targetSets=8, status="partial", sets=[
        result(1, machineMetrics={"side": "left", "roundNumber": 1}),
        result(2, machineMetrics={"side": "right", "roundNumber": 1}),
    ])
    assert read(client)["sets"] == 4


def test_warmup_only_does_not_replace_legacy_settings(client: TestClient, db_session: Session) -> None:
    row = state(db_session)
    row.working_weight, row.working_sets, row.working_reps = 25, 3, 36
    row.calibration_payload = {"lastResult": {"sets": 3, "repsPerSet": 12, "weightKg": 25}}
    db_session.commit()
    expected = read(client)
    save_exercise(client, sets=[result(setType="warmup", weightKg=100)])
    assert read(client) == expected


def test_skipped_set_cannot_replace_last_performed_weight(client: TestClient) -> None:
    save_exercise(client, sets=[result(1, weightKg=20),
                               result(2, weightKg=80, machineMetrics={"completionStatus": "skipped"}),
                               result(3, weightKg=90, actualValue=0, reps=0)])
    assert read(client)["weight"] == 20


def test_adjustment_preserves_saved_modes_and_stale_session_cannot_undo_it(client: TestClient) -> None:
    old_start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    old_id = save_exercise(client, startedAt=old_start, status="in_progress", sets=[])
    assert client.put(PATH, json=settings(trainingMode="strength", trainingDayType="heavy", tempo="Slow")).status_code == 200
    response = client.post("/api/runtime/exercises/load-adjustment", json={
        "userId": "alexey", "exerciseSlug": SLUG, "kind": "machine", "direction": "increase",
        "currentWeightKg": 20,
    })
    assert response.status_code == 200
    expected = read(client)
    assert expected["trainingMode"] == "strength"
    assert expected["trainingDayType"] == "heavy"
    assert expected["tempo"] == "Slow"
    save_exercise(client, exerciseSessionId=old_id, startedAt=old_start, sets=[result(weightKg=99)])
    assert read(client) == expected