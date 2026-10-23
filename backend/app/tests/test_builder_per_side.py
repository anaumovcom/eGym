from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settings import AppSetting


@pytest.fixture(autouse=True)
def isolated_builder_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep these API tests on the temporary DB without bootstrap or hardware.
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield

    monkeypatch.setattr("app.main.lifespan", lifespan)


def builder_plan(per_side: bool | None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "item", "slug": "machine-pulldown", "name": "Pull down",
        "muscleGroup": "Back", "sets": "3×10", "load": "50 кг",
        "rest": "60 сек", "loadType": "weighted",
    }
    if per_side is not None:
        item["perSide"] = per_side
    return {
        "userId": "alexey", "programId": "back-biceps", "selectedExerciseId": "item",
        "groups": [{"id": "custom", "kind": "single", "title": "Custom", "items": [item]}],
    }


def builder_editor(per_side: bool | None) -> dict[str, Any]:
    editor: dict[str, Any] = {
        "name": "Pull down", "subtitle": "Back",
        "setParams": {"sets": 3, "reps": 10, "weight": 50, "restSeconds": 60},
        "loadType": "weighted", "loadMode": "Обычный вес", "tempo": "Обычный",
        "note": "Saved per-side editor",
    }
    if per_side is not None:
        editor["perSide"] = per_side
    return editor


def read_builder(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/builder", params={
        "userId": "alexey", "programId": "back-biceps", "selectedExerciseId": "item",
    })
    assert response.status_code == 200
    return response.json()


def stored_plan(db_session: Session) -> AppSetting:
    db_session.expire_all()
    setting = db_session.scalar(select(AppSetting).where(
        AppSetting.user_id == "alexey", AppSetting.key == "training.builder.plan.back-biceps",
    ))
    assert setting is not None
    return setting


@pytest.mark.parametrize("per_side", [None, False, True])
def test_group_flag_survives_sanitizer_storage_and_default_editor(
    client: TestClient, db_session: Session, per_side: bool | None,
) -> None:
    assert client.put("/api/builder/plan", json=builder_plan(per_side)).status_code == 200
    payload = read_builder(client)
    expected = per_side is True
    item = payload["groups"][0]["items"][0]
    assert item["perSide"] is expected
    assert payload["selectedExercise"]["perSide"] is expected
    assert item["sets"] == "3×10"
    assert payload["selectedExercise"]["setParams"]["reps"] == 10
    assert stored_plan(db_session).value["groups"][0]["items"][0]["perSide"] is expected


@pytest.mark.parametrize("per_side", [None, False, True])
def test_editor_flag_updates_every_item_of_the_exercise_and_roundtrips(
    client: TestClient, db_session: Session, per_side: bool | None,
) -> None:
    plan = builder_plan(per_side is not True)
    # The same exercise twice in one workout: both entries share one exercise profile.
    sibling = {**plan["groups"][0]["items"][0], "id": "sibling", "perSide": True}
    plan["groups"][0]["items"].append(sibling)
    plan["selectedExercise"] = builder_editor(per_side)
    assert client.put("/api/builder/plan", json=plan).status_code == 200
    payload = read_builder(client)
    expected = per_side is True
    assert payload["groups"][0]["items"][0]["perSide"] is expected
    assert payload["groups"][0]["items"][1]["perSide"] is expected
    assert payload["selectedExercise"]["perSide"] is expected
    assert payload["selectedExercise"]["note"] == "Saved per-side editor"
    stored = stored_plan(db_session).value
    assert stored["groups"][0]["items"][0]["perSide"] is expected
    assert stored["editors"]["item"]["perSide"] is expected
    # Saving groups alone must retain the exercise settings, including its flag/note.
    plan["groups"] = payload["groups"]
    del plan["selectedExercise"]
    assert client.put("/api/builder/plan", json=plan).status_code == 200
    assert read_builder(client)["selectedExercise"]["note"] == "Saved per-side editor"
    assert read_builder(client)["selectedExercise"]["perSide"] is expected


@pytest.mark.parametrize("old_flag", [False, True])
def test_group_flag_change_updates_exercise_profile(
    client: TestClient, db_session: Session, old_flag: bool,
) -> None:
    plan = builder_plan(old_flag)
    plan["selectedExercise"] = builder_editor(old_flag)
    assert client.put("/api/builder/plan", json=plan).status_code == 200
    del plan["selectedExercise"]
    plan["groups"][0]["items"][0]["perSide"] = not old_flag
    assert client.put("/api/builder/plan", json=plan).status_code == 200
    payload = read_builder(client)
    assert payload["groups"][0]["items"][0]["perSide"] is not old_flag
    assert payload["selectedExercise"]["perSide"] is not old_flag
    # Only the flag changed: the rest of the exercise settings stay.
    assert payload["selectedExercise"]["note"] == "Saved per-side editor"
    assert payload["selectedExercise"]["setParams"] == {"sets": 3, "reps": 10, "weight": 50, "restSeconds": 60}


@pytest.mark.parametrize("old_flag", [False, True])
def test_stored_group_values_never_override_exercise_profile(
    client: TestClient, db_session: Session, old_flag: bool,
) -> None:
    plan = builder_plan(old_flag)
    plan["selectedExercise"] = builder_editor(old_flag)
    assert client.put("/api/builder/plan", json=plan).status_code == 200
    setting = stored_plan(db_session)
    # Emulate an existing JSON snapshot inconsistent with the exercise profile.
    value = setting.value
    setting.value = {
        **value,
        "groups": [{**value["groups"][0], "items": [
            {**value["groups"][0]["items"][0], "perSide": not old_flag, "sets": "5×5", "load": "90 кг"},
        ]}],
    }
    db_session.commit()
    payload = read_builder(client)
    item = payload["groups"][0]["items"][0]
    assert (item["perSide"], item["sets"], item["load"]) == (old_flag, "3×10", "50 кг")
    assert payload["selectedExercise"]["perSide"] is old_flag
    assert payload["selectedExercise"]["note"] == "Saved per-side editor"


def test_legacy_json_without_flag_defaults_to_false(
    client: TestClient, db_session: Session,
) -> None:
    plan = builder_plan(None)
    plan["selectedExercise"] = builder_editor(None)
    assert client.put("/api/builder/plan", json=plan).status_code == 200
    setting = stored_plan(db_session)
    value = setting.value
    item = {key: val for key, val in value["groups"][0]["items"][0].items() if key != "perSide"}
    editor = {key: val for key, val in value["editors"]["item"].items() if key != "perSide"}
    setting.value = {
        **value, "groups": [{**value["groups"][0], "items": [item]}],
        "editors": {"item": editor},
    }
    db_session.commit()
    payload = read_builder(client)
    assert payload["groups"][0]["items"][0]["perSide"] is False
    assert payload["selectedExercise"]["perSide"] is False
    assert payload["selectedExercise"]["note"] == "Saved per-side editor"