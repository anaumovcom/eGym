from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.api.routes.runtime import runtime_service
from app.models.analytics import ExerciseSession, MuscleFatigueEvent, MuscleFatigueSnapshot, SetResult
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
    ExerciseSessionsResetRequestSchema,
    MuscleTargetSchema,
    SetResultCreateSchema,
)
from app.services.coach.lifecycle import RuntimeObservationBuffer
from app.services.runtime_service import RuntimeService


@pytest.fixture()
def reset_exercises(db_session):
    service = RuntimeService(coach_observer=RuntimeObservationBuffer(lambda: False))
    exercises = []
    for index in range(3):
        original = ExerciseSessionCreateSchema(
            user_id="alexey", exercise_slug=f"atomic-reset-{index}", exercise_name=f"Exercise {index}",
            kind="machine", order_index=index + 1, status="completed", started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC), target_sets=2,
            muscles=[MuscleTargetSchema(muscle_id="chest", name="Chest", role="primary")],
            sets=[SetResultCreateSchema(
                set_number=1, planned_value=10, actual_value=10, reps=10, weight_kg=30, tempo_label="stable",
            )],
        )
        saved = service.save_exercise_session(db_session, original)
        exercises.append(original.model_copy(update={
            "exercise_session_id": saved.exercise_session.id, "reset_sets": True, "status": "in_progress",
            "sets": [], "finished_at": None, "exercise_name": f"Reset {index}",
        }))
    ids = [item.exercise_session_id for item in exercises]
    assert len(db_session.scalars(select(SetResult).where(SetResult.exercise_session_id.in_(ids))).all()) == 3
    assert len(db_session.scalars(select(MuscleFatigueEvent).where(
        MuscleFatigueEvent.exercise_session_id.in_(ids),
    )).all()) == 3
    return exercises


def database_state(session):
    session.expire_all()
    return {
        model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)).mappings())
        for model in (ExerciseSession, SetResult, MuscleFatigueEvent, MuscleFatigueSnapshot)
    }


def wire(exercises):
    return {"exercises": [item.model_dump(mode="json", by_alias=True) for item in exercises]}


@pytest.mark.parametrize("count", [1, 2])
def test_reset_endpoint_clears_sets_and_fatigue_without_notices(
    client, db_session, reset_exercises, monkeypatch, count,
):
    observer = Mock()
    monkeypatch.setattr(runtime_service, "coach_observer", observer)
    before = database_state(db_session)
    response = client.post("/api/runtime/exercises/reset", json=wire(reset_exercises[:count]))
    assert response.status_code == 200
    assert response.json() == {"missingExerciseSessionIds": []}
    db_session.expire_all()
    for index, payload in enumerate(reset_exercises):
        exercise = db_session.get(ExerciseSession, payload.exercise_session_id)
        events = db_session.scalars(select(MuscleFatigueEvent).where(
            MuscleFatigueEvent.exercise_session_id == exercise.id,
        )).all()
        if index < count:
            assert exercise.status.value == "in_progress"
            assert exercise.exercise_name == f"Reset {index}"
            assert exercise.finished_at is None
            assert exercise.set_results == []
            assert events == []
        else:
            assert exercise.status.value == "completed"
            assert exercise.exercise_name == f"Exercise {index}"
            assert len(exercise.set_results) == len(events) == 1
    after = database_state(db_session)
    before_chest = next(row for row in before["muscle_fatigue_snapshots"]
                        if row["user_id"] == "alexey" and row["muscle_id"] == "chest")
    after_chest = next(row for row in after["muscle_fatigue_snapshots"] if row["id"] == before_chest["id"])
    assert 0 < after_chest["fatigue_score"] < before_chest["fatigue_score"]
    observer.record.assert_not_called()


def test_reset_service_commits_once(db_session, reset_exercises, monkeypatch):
    service = RuntimeService(coach_observer=RuntimeObservationBuffer(lambda: True))
    commit = Mock(wraps=db_session.commit)
    save = Mock(wraps=service.save_exercise_session)
    monkeypatch.setattr(db_session, "commit", commit)
    monkeypatch.setattr(service, "save_exercise_session", save)
    result = service.reset_exercise_sessions(
        db_session, ExerciseSessionsResetRequestSchema(exercises=reset_exercises[:2]),
    )
    assert result.missing_exercise_session_ids == []
    commit.assert_called_once_with()
    assert save.call_count == 2
    assert all(call.kwargs == {"commit": False} for call in save.call_args_list)
    assert not service.coach_observer.notices


@pytest.mark.parametrize("error,expected_status", [(ValueError, 409), (LookupError, 404)])
def test_second_reset_failure_rolls_back_first_and_second(
    client, db_session, reset_exercises, monkeypatch, error, expected_status,
):
    before = database_state(db_session)
    save = runtime_service.save_exercise_session
    calls = []

    def fail_second(session, payload, *, commit=True):
        calls.append(payload.exercise_session_id)
        result = save(session, payload, commit=commit)
        assert result.exercise_session.set_results == []
        if len(calls) == 2:
            raise error("Second reset failed")
        return result

    monkeypatch.setattr(runtime_service, "save_exercise_session", fail_second)
    response = client.post("/api/runtime/exercises/reset", json=wire(reset_exercises[:2]))
    assert response.status_code == expected_status
    assert response.json() == {"detail": "Second reset failed"}
    assert calls == [item.exercise_session_id for item in reset_exercises[:2]]
    assert database_state(db_session) == before


@pytest.mark.parametrize("failure", ["second_save", "commit"])
def test_unexpected_failure_rolls_back_and_propagates(db_session, reset_exercises, monkeypatch, failure):
    service = RuntimeService(coach_observer=RuntimeObservationBuffer(lambda: True))
    before = database_state(db_session)
    commit = db_session.commit
    rollback = Mock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    if failure == "commit":
        monkeypatch.setattr(db_session, "commit", Mock(side_effect=RuntimeError("Storage failed")))
    else:
        save = service.save_exercise_session

        def fail_second(session, payload, *, commit=True):
            if payload.exercise_session_id == reset_exercises[1].exercise_session_id:
                raise RuntimeError("Storage failed")
            return save(session, payload, commit=commit)

        monkeypatch.setattr(service, "save_exercise_session", fail_second)
    with pytest.raises(RuntimeError, match="Storage failed"):
        service.reset_exercise_sessions(
            db_session, ExerciseSessionsResetRequestSchema(exercises=reset_exercises[:2]),
        )
    rollback.assert_called_once_with()
    assert database_state(db_session) == before
    assert not service.coach_observer.notices
    # The rolled-back session remains usable.
    commit()


def test_ownership_is_checked_for_all_records_before_any_save(client, db_session, reset_exercises, monkeypatch):
    second = db_session.get(ExerciseSession, reset_exercises[1].exercise_session_id)
    second.user_id = "elena"
    db_session.commit()
    before = database_state(db_session)
    save = Mock(wraps=runtime_service.save_exercise_session)
    monkeypatch.setattr(runtime_service, "save_exercise_session", save)
    response = client.post("/api/runtime/exercises/reset", json=wire(reset_exercises[:2]))
    assert response.status_code == 404
    save.assert_not_called()
    assert database_state(db_session) == before


@pytest.mark.parametrize("missing_positions", [(0,), (1,), (0, 1)])
def test_missing_records_are_reported_without_creation(client, db_session, reset_exercises, missing_positions):
    exercises = list(reset_exercises[:2])
    missing_ids = []
    for index in missing_positions:
        missing_id = 999_000 + index
        missing_ids.append(missing_id)
        exercises[index] = exercises[index].model_copy(update={"exercise_session_id": missing_id})
    before_count = len(database_state(db_session)["exercise_sessions"])
    response = client.post("/api/runtime/exercises/reset", json=wire(exercises))
    assert response.status_code == 200
    assert response.json() == {"missingExerciseSessionIds": missing_ids}
    assert len(database_state(db_session)["exercise_sessions"]) == before_count
    for index in range(2):
        row = db_session.get(ExerciseSession, reset_exercises[index].exercise_session_id)
        assert len(row.set_results) == (1 if index in missing_positions else 0)


@pytest.mark.parametrize("invalid", [
    "empty", "too_many", "no_id", "null_id", "no_reset", "false_reset", "status", "sets", "users", "duplicate",
])
def test_invalid_reset_payload_is_rejected_before_writes(client, db_session, reset_exercises, monkeypatch, invalid):
    body = wire(reset_exercises[:2])
    first = body["exercises"][0]
    if invalid == "empty":
        body["exercises"] = []
    elif invalid == "too_many":
        body = wire(reset_exercises)
    elif invalid == "no_id":
        del first["exerciseSessionId"]
    elif invalid == "null_id":
        first["exerciseSessionId"] = None
    elif invalid == "no_reset":
        del first["resetSets"]
    elif invalid == "false_reset":
        first["resetSets"] = False
    elif invalid == "status":
        first["status"] = "completed"
    elif invalid == "sets":
        first["sets"] = [{"setNumber": 1, "plannedValue": 10, "actualValue": 10, "tempoLabel": "stable"}]
    elif invalid == "users":
        body["exercises"][1]["userId"] = "elena"
    elif invalid == "duplicate":
        body["exercises"][1]["exerciseSessionId"] = first["exerciseSessionId"]
    before = database_state(db_session)
    reset = Mock(wraps=runtime_service.reset_exercise_sessions)
    monkeypatch.setattr(runtime_service, "reset_exercise_sessions", reset)
    response = client.post("/api/runtime/exercises/reset", json=body)
    assert response.status_code == 422
    reset.assert_not_called()
    assert database_state(db_session) == before