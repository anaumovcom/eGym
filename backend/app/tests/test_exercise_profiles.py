"""One exercise = one set of load settings across every workout in "Мои тренировки" and the runtime."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, SetResult
from app.models.enums import ExerciseSessionStatus, RuntimeExerciseKind
from app.models.settings import AppSetting
from app.models.training import UserExerciseState

SLUG = "barbell-curl"
SETTINGS = "/api/runtime/exercises/settings"


@pytest.fixture(autouse=True)
def isolated_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr("app.main.lifespan", lifespan)


def item(item_id: str, slug: str = SLUG, **changes: Any) -> dict[str, Any]:
    return {"id": item_id, "slug": slug, "name": "Сгибание рук", "muscleGroup": "Бицепс",
            "sets": "3×12", "rest": "75 сек", "load": "20 кг", "loadType": "weighted", **changes}


def editor(**changes: Any) -> dict[str, Any]:
    return {"name": "Сгибание рук", "subtitle": "Бицепс",
            "setParams": {"sets": 4, "reps": 8, "weight": 32, "restSeconds": 120},
            "loadType": "weighted", "loadMode": "Обычный вес", "tempo": "Обычный",
            "strengthModeId": "strength", "perSide": True, "note": "Локти прижаты", **changes}


def save_plan(client: TestClient, program_id: str, items: list[dict[str, Any]], **payload: Any) -> None:
    response = client.put("/api/builder/plan", json={
        "userId": "alexey", "programId": program_id,
        "groups": [{"id": f"{program_id}-group", "kind": "single", "title": "Блок", "items": items}],
        **payload,
    })
    assert response.status_code == 200, response.text


def builder(client: TestClient, program_id: str, selected: str | None = None) -> dict[str, Any]:
    params = {"userId": "alexey", "programId": program_id}
    if selected:
        params["selectedExerciseId"] = selected
    response = client.get("/api/builder", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def builder_item(client: TestClient, program_id: str, item_id: str) -> dict[str, Any]:
    return next(entry for group in builder(client, program_id)["groups"] for entry in group["items"] if entry["id"] == item_id)


def runtime_settings(client: TestClient, slug: str = SLUG) -> dict[str, Any]:
    response = client.get(SETTINGS, params={"userId": "alexey", "exerciseSlug": slug})
    assert response.status_code == 200
    return response.json()


def two_programs(client: TestClient) -> None:
    save_plan(client, "back-biceps", [item("a-curl")])
    save_plan(client, "fullbody-base", [item("b-curl"), item("b-plank", "forearm-plank",
              name="Планка", sets="3×45 сек", load="вес тела", loadType="timed", rest="45 сек")])


def test_editing_exercise_in_one_workout_changes_it_in_every_workout(client: TestClient) -> None:
    two_programs(client)
    save_plan(client, "back-biceps", [item("a-curl")], selectedExerciseId="a-curl", selectedExercise=editor())

    for program_id, item_id in (("back-biceps", "a-curl"), ("fullbody-base", "b-curl")):
        entry = builder_item(client, program_id, item_id)
        assert (entry["sets"], entry["load"], entry["rest"]) == ("4×8", "32 кг", "120 сек")
        assert (entry["strengthModeId"], entry["perSide"]) == ("strength", True)
        selected = builder(client, program_id, item_id)["selectedExercise"]
        assert selected["setParams"] == {"sets": 4, "reps": 8, "weight": 32, "restSeconds": 120}
        assert selected["note"] == "Локти прижаты"
    # Other exercises of the second workout keep their own settings.
    assert builder_item(client, "fullbody-base", "b-plank")["sets"] == "3×45 сек"
    # Quick start / catalog read the same profile.
    assert runtime_settings(client) == {"weight": 32, "sets": 4, "reps": 8, "restSeconds": 120, "mode": "Обычный вес",
                                        "tempo": "Обычный", "trainingMode": "strength", "trainingDayType": None}
    details = client.get(f"/api/exercises/{SLUG}", params={"userId": "alexey"}).json()["loadSettings"]
    assert (details["weight"], details["sets"], details["reps"], details["trainingMode"], details["perSide"]) == (32, 4, 8, "strength", True)


def test_adding_configured_exercise_to_another_workout_configures_it_everywhere(client: TestClient) -> None:
    two_programs(client)
    # The picker's "Подходы и нагрузка" step sends explicit values for the added exercise.
    save_plan(client, "mobility-recovery", [item("c-curl", sets="5×5", load="40 кг", rest="180 сек")])
    for program_id, item_id in (("back-biceps", "a-curl"), ("fullbody-base", "b-curl"), ("mobility-recovery", "c-curl")):
        entry = builder_item(client, program_id, item_id)
        assert (entry["sets"], entry["load"], entry["rest"]) == ("5×5", "40 кг", "180 сек")


def test_same_exercise_twice_in_one_workout_is_identical(client: TestClient) -> None:
    save_plan(client, "back-biceps", [item("first"), item("second", sets="2×20", load="10 кг")],
              selectedExerciseId="first", selectedExercise=editor(perSide=False))
    first, second = builder(client, "back-biceps")["groups"][0]["items"]
    assert {key: first[key] for key in ("sets", "load", "rest", "strengthPlan")} == {
        key: second[key] for key in ("sets", "load", "rest", "strengthPlan")}


def test_runtime_weight_change_reaches_every_workout(client: TestClient) -> None:
    two_programs(client)
    current = runtime_settings(client)
    assert client.put(SETTINGS, json={"userId": "alexey", "exerciseSlug": SLUG, **{**current, "weight": 27.5}}).status_code == 200
    assert builder_item(client, "back-biceps", "a-curl")["load"] == "27.5 кг"
    assert builder_item(client, "fullbody-base", "b-curl")["load"] == "27.5 кг"
    selected = builder(client, "fullbody-base", "b-curl")["selectedExercise"]
    assert selected["setParams"]["weight"] == 27.5
    # The working sets use the exact weight; only scaled sets are rounded.
    assert [entry["recommendedWeightLabel"] for entry in selected["strengthPlan"]] == ["14 кг", "27.5 кг", "27.5 кг"]


@pytest.mark.parametrize("direction,expected", [("increase", "22.5 кг"), ("decrease", "17.5 кг")])
def test_load_adjustment_changes_the_workouts(client: TestClient, direction: str, expected: str) -> None:
    two_programs(client)
    response = client.post("/api/runtime/exercises/load-adjustment", json={
        "userId": "alexey", "exerciseSlug": SLUG, "kind": "machine", "direction": direction,
        "currentWeightKg": 20, "currentReps": 12, "currentSets": 3, "restSeconds": 75,
    })
    assert response.status_code == 200, response.text
    assert builder_item(client, "back-biceps", "a-curl")["load"] == expected
    assert builder_item(client, "fullbody-base", "b-curl")["load"] == expected


def test_timed_load_adjustment_changes_duration_in_workouts(client: TestClient) -> None:
    two_programs(client)
    response = client.post("/api/runtime/exercises/load-adjustment", json={
        "userId": "alexey", "exerciseSlug": "forearm-plank", "kind": "timed", "direction": "increase",
        "currentWeightKg": 0, "currentReps": 45, "currentSets": 3, "restSeconds": 45,
    })
    assert response.status_code == 200, response.text
    assert builder_item(client, "fullbody-base", "b-plank")["sets"] == "3×50 сек"
    assert builder(client, "fullbody-base", "b-plank")["selectedExercise"]["setParams"]["durationSeconds"] == 50


def test_performed_working_weight_is_saved_to_the_workouts(client: TestClient) -> None:
    two_programs(client)
    now = datetime.now(UTC).isoformat()
    response = client.post("/api/runtime/exercises", json={
        "userId": "alexey", "exerciseSlug": SLUG, "exerciseName": "Curl", "kind": "machine", "status": "completed",
        "targetSets": 3, "startedAt": now, "trainingMode": "basic",
        "sets": [
            {"setNumber": 1, "plannedValue": 12, "actualValue": 12, "reps": 12, "weightKg": 12.5, "tempoLabel": "Обычный",
             "setType": "warmup", "restDurationSeconds": 60, "machineMetrics": {"workingWeightKg": 25}},
            # A pyramid/light set performs a share of the working weight: the working weight is remembered.
            {"setNumber": 2, "plannedValue": 12, "actualValue": 12, "reps": 12, "weightKg": 20, "tempoLabel": "Обычный",
             "restDurationSeconds": 60, "machineMetrics": {"workingWeightKg": 25}},
        ],
    })
    assert response.status_code == 200, response.text
    assert builder_item(client, "back-biceps", "a-curl")["load"] == "25 кг"
    entry = builder_item(client, "fullbody-base", "b-curl")
    # Reps, sets and rest still come from the settings, not from the plan that was performed.
    assert (entry["load"], entry["sets"], entry["rest"]) == ("25 кг", "3×12", "75 сек")


def test_resent_editor_does_not_undo_a_newer_runtime_change(client: TestClient) -> None:
    save_plan(client, "back-biceps", [item("a-curl")], selectedExerciseId="a-curl", selectedExercise=editor())
    current = runtime_settings(client)
    assert client.put(SETTINGS, json={"userId": "alexey", "exerciseSlug": SLUG, **{**current, "weight": 35}}).status_code == 200
    # A builder tab opened before the workout autosaves its unchanged editor (e.g. a group title edit).
    save_plan(client, "back-biceps", [item("a-curl", sets="4×8", load="32 кг", rest="180 сек", strengthModeId="strength", perSide=True)],
              selectedExerciseId="a-curl", selectedExercise=editor())
    assert builder_item(client, "back-biceps", "a-curl")["load"] == "35 кг"
    assert runtime_settings(client)["weight"] == 35


def test_load_mode_modifiers_round_trip_without_drift(client: TestClient) -> None:
    save_plan(client, "back-biceps", [item("a-curl")], selectedExerciseId="a-curl",
              selectedExercise=editor(loadMode="Лёгкий режим", strengthModeId="basic", setParams={"sets": 3, "reps": 10, "weight": 50, "restSeconds": 60}))
    effective = runtime_settings(client)
    assert (effective["weight"], effective["reps"], effective["restSeconds"]) == (40, 8, 75)
    for _ in range(3):
        assert client.put(SETTINGS, json={"userId": "alexey", "exerciseSlug": SLUG, **effective}).status_code == 200
    selected = builder(client, "back-biceps", "a-curl")["selectedExercise"]
    assert selected["setParams"] == {"sets": 3, "reps": 10, "weight": 50, "restSeconds": 60}
    # A runtime change is the performed (effective) value: the builder control is re-derived from it.
    assert client.put(SETTINGS, json={"userId": "alexey", "exerciseSlug": SLUG, **{**effective, "weight": 44}}).status_code == 200
    selected = builder(client, "back-biceps", "a-curl")["selectedExercise"]
    assert (selected["setParams"]["weight"], selected["effectiveSetParams"]["weight"]) == (55, 44)


def legacy_plans(db_session: Session) -> None:
    """Data written before exercise profiles: two workouts disagree about the same exercise."""
    for program_id, sets, load in (("back-biceps", "3×12", "20 кг"), ("fullbody-base", "5×5", "40 кг")):
        db_session.merge(AppSetting(user_id="alexey", key=f"training.builder.plan.{program_id}", value={
            "groups": [{"id": "g", "kind": "single", "title": "Блок", "items": [item(f"{program_id}-curl", sets=sets, load=load)]}],
        }))
    for row in db_session.scalars(select(UserExerciseState).where(UserExerciseState.user_id == "alexey")):
        row.calibration_payload = {key: val for key, val in (row.calibration_payload or {}).items() if key != "profile"}
    db_session.commit()


def performed(db_session: Session, started_at: datetime, *sets: tuple[str, float]) -> None:
    exercise = ExerciseSession(user_id="alexey", exercise_slug=SLUG, exercise_name="Curl", kind=RuntimeExerciseKind.machine,
                               status=ExerciseSessionStatus.completed, started_at=started_at, target_sets=len(sets))
    db_session.add(exercise)
    db_session.flush()
    for number, (set_type, weight) in enumerate(sets, start=1):
        db_session.add(SetResult(exercise_session_id=exercise.id, set_number=number, planned_value=12, actual_value=12, reps=12,
                                 weight_kg=weight, tempo_label="Обычный", machine_metrics={"setType": set_type}))
    db_session.commit()


def test_legacy_workouts_migrate_first_workout_wins_and_last_performed_weight_is_kept(
    client: TestClient, db_session: Session,
) -> None:
    legacy_plans(db_session)
    performed(db_session, datetime(2026, 10, 1, tzinfo=UTC), ("working", 30))
    # The latest workout: warm-up and a bar-only set do not replace the working weight.
    performed(db_session, datetime(2026, 10, 9, tzinfo=UTC), ("warmup", 12.5), ("working", 22.5), ("working", 0))
    state = db_session.scalar(select(UserExerciseState).where(
        UserExerciseState.user_id == "alexey", UserExerciseState.exercise_slug == SLUG))
    if state is not None:
        # Saved on a setup screen without being performed: not a performed weight.
        state.calibration_payload = {**(state.calibration_payload or {}), "lastSettings": {"weight": 1, "sets": 2, "reps": 30, "restSeconds": 10}}
        db_session.commit()

    # Opening any workout migrates all of them: the first workout in "Мои тренировки" defines the settings.
    for program_id in ("fullbody-base", "back-biceps"):
        entry = builder_item(client, program_id, f"{program_id}-curl")
        assert (entry["sets"], entry["load"], entry["rest"]) == ("3×12", "22.5 кг", "75 сек")
    db_session.expire_all()
    stored = db_session.scalar(select(UserExerciseState).where(
        UserExerciseState.user_id == "alexey", UserExerciseState.exercise_slug == SLUG))
    assert stored.calibration_payload["profile"]["weight"] == 22.5


def test_first_runtime_write_after_upgrade_edits_the_workout_settings(client: TestClient, db_session: Session) -> None:
    legacy_plans(db_session)
    # Quick start saves a new weight before any workout was opened: only the weight changes.
    assert client.put(SETTINGS, json={"userId": "alexey", "exerciseSlug": SLUG, "weight": 27.5, "sets": 3,
                                      "reps": 12, "restSeconds": 75}).status_code == 200
    for program_id in ("back-biceps", "fullbody-base"):
        entry = builder_item(client, program_id, f"{program_id}-curl")
        assert (entry["sets"], entry["load"], entry["rest"]) == ("3×12", "27.5 кг", "75 сек")
