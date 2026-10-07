from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
    SetResultCreateSchema,
    SetResultSaveSchema,
    WorkoutSessionCreateSchema,
)
from app.services.coach.lifecycle import RuntimeObservationBuffer
from app.services.runtime_service import RuntimeService


def exercise_payload(status="in_progress"):
    return ExerciseSessionCreateSchema(
        user_id="alexey", exercise_slug="machine-pulldown", exercise_name="Тест",
        kind="machine", status=status, started_at=datetime.now(UTC), target_sets=1,
    )


def create_exercise(service, session):
    return service.save_exercise_session(session, exercise_payload()).exercise_session.id


def set_payload(exercise_id):
    return SetResultSaveSchema(
        exercise_session_id=exercise_id, set_number=1, planned_value=10, actual_value=8,
        reps=8, weight_kg=20, tempo_label="unknown", machine_metrics={"completionStatus": "partial"},
    )


def test_capabilities_are_off_and_never_paid(client: TestClient, monkeypatch):
    monkeypatch.delenv("COACH_ENABLED", raising=False)
    get_settings.cache_clear()
    response = client.get("/api/coach/capabilities")
    assert response.status_code == 200
    assert response.json() == {
        "schemaVersion": 1, "enabled": False, "implementation": "control-plane",
        "paidDispatch": False, "lifecycleObservation": False, "replay": "test-only",
    }
    monkeypatch.setenv("COACH_ENABLED", "true")
    get_settings.cache_clear()
    assert client.get("/api/coach/capabilities").json()["paidDispatch"] is False
    assert Settings(_env_file=None).coach_enabled is True
    assert client.post("/api/coach/replay", json={}).status_code == 404
    assert client.post("/api/coach/credentials", json={}).status_code == 405


def test_after_commit_notices_have_captured_ids_and_real_outcome(db_session: Session):
    buffer = RuntimeObservationBuffer(lambda: True)
    service = RuntimeService(coach_observer=buffer)
    exercise_id = create_exercise(service, db_session)
    assert not buffer.notices
    response = service.save_set_result(db_session, set_payload(exercise_id))
    notice = buffer.notices[-1]
    assert notice.kind == "set_persisted" and notice.set_id == response.set_id
    assert notice.exercise_session_id == exercise_id and notice.user_id == "alexey"
    assert notice.actual_value == 8 and notice.outcome == "partial"
    service.save_exercise_session(db_session, exercise_payload("partial").model_copy(update={"exercise_session_id": exercise_id}))
    assert buffer.notices[-1].kind == "exercise_finalized"
    summary = service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Тест", status="partial",
        started_at=datetime.now(UTC), exercise_session_ids=[exercise_id],
    ))
    assert buffer.notices[-1].kind == "workout_finalized"
    assert buffer.notices[-1].workout_session_id == summary.workout_session_id


def test_failed_commit_and_nested_uncommitted_exercise_emit_nothing(db_session: Session, monkeypatch):
    buffer = RuntimeObservationBuffer(lambda: True)
    service = RuntimeService(coach_observer=buffer)
    exercise_id = create_exercise(service, db_session)

    def failed_commit():
        raise RuntimeError("Synthetic commit failure")

    monkeypatch.setattr(db_session, "commit", failed_commit)
    with pytest.raises(RuntimeError):
        service.save_set_result(db_session, set_payload(exercise_id))
    assert not buffer.notices
    db_session.rollback()
    service.save_exercise_session(db_session, exercise_payload("completed"), commit=False)
    assert not buffer.notices
    db_session.rollback()
    with pytest.raises(RuntimeError):
        service.save_workout_session(db_session, WorkoutSessionCreateSchema(
            user_id="alexey", source="catalog", title="Тест", status="completed",
            started_at=datetime.now(UTC), exercises=[exercise_payload("completed")],
        ))
    assert not buffer.notices
    db_session.rollback()


def test_disabled_or_failing_observer_cannot_fail_training_save(db_session: Session):
    buffer = RuntimeObservationBuffer(lambda: False)
    service = RuntimeService(coach_observer=buffer)
    exercise_id = create_exercise(service, db_session)
    assert service.save_set_result(db_session, set_payload(exercise_id)).set_id > 0
    assert not buffer.notices

    def broken_enabled():
        raise RuntimeError("Observer failed")

    buffer.enabled = broken_enabled
    assert service.save_set_result(db_session, set_payload(exercise_id)).set_id > 0
    assert buffer.failures == 1


def test_nested_set_and_summaries_are_observed_only_after_parent_commit(db_session: Session, monkeypatch):
    buffer = RuntimeObservationBuffer(lambda: True)
    service = RuntimeService(coach_observer=buffer)
    original_commit = db_session.commit
    during_commit = []

    def commit():
        during_commit.append(tuple(buffer.notices))
        original_commit()

    monkeypatch.setattr(db_session, "commit", commit)
    payload = exercise_payload("partial").model_copy(update={"sets": [SetResultCreateSchema(
        set_number=1, planned_value=10, actual_value=8, reps=8, tempo_label="unknown",
        machine_metrics={"completionStatus": "partial"},
    )]})
    service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Тест", status="partial",
        started_at=datetime.now(UTC), exercises=[payload],
    ))
    assert during_commit == [()]
    assert [notice.kind for notice in buffer.notices] == ["set_persisted", "exercise_finalized", "workout_finalized"]
    assert len({notice.workout_session_id for notice in buffer.notices}) == 1


def test_bounded_observation_does_not_dispatch_network():
    buffer = RuntimeObservationBuffer(lambda: True, capacity=2)
    for i in range(3):
        buffer.record(kind="set_persisted", user_id="fixture-user", set_id=i + 1, set_ordinal=1, exercise_session_id=1)
    assert len(buffer.notices) == 2 and buffer.notices[0].set_id == 2
    buffer.clear()
    assert not buffer.notices
    with pytest.raises(ValueError):
        RuntimeObservationBuffer(lambda: True, capacity=0)