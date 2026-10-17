from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
from app.models.analytics import ExerciseSession
from app.models.training import ExerciseHistoryRecord, UserExerciseState
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
    SetResultCreateSchema,
    SetResultSaveSchema,
    WorkoutSessionCreateSchema,
)
from app.services.runtime_service import RuntimeService


def side_result(number: int, side: str, *, actual: int = 10, status: str = "completed", round_number: int = 1, set_type: str = "work") -> SetResultCreateSchema:
    return SetResultCreateSchema(
        set_number=number, planned_value=10, actual_value=actual, reps=actual,
        weight_kg=20, tempo_label="stable", set_type=set_type,
        machine_metrics={"side": side, "roundNumber": round_number, "completionStatus": status},
    )


def payload(sets: list[SetResultCreateSchema], *, target_sets: int = 2, status: str = "completed") -> ExerciseSessionCreateSchema:
    return ExerciseSessionCreateSchema(
        user_id="alexey", exercise_slug="per-side-test", exercise_name="Per side",
        kind="machine", status=status, started_at=datetime.now(UTC), finished_at=datetime.now(UTC),
        target_sets=target_sets, sets=sets,
    )


def test_metadata_roundtrips_incremental_save_summary_and_state(db_session: Session) -> None:
    service = RuntimeService()
    exercise_id = service.save_exercise_session(db_session, payload([], status="in_progress")).exercise_session.id
    for result in [side_result(1, "left"), side_result(2, "right")]:
        service.save_set_result(db_session, SetResultSaveSchema(exercise_session_id=exercise_id, **result.model_dump()))
    service.save_exercise_session(db_session, payload([]).model_copy(update={"exercise_session_id": exercise_id}))
    db_session.expire_all()
    exercise = db_session.get(ExerciseSession, exercise_id)
    assert exercise is not None
    assert exercise.target_sets == 2  # Persistence keeps the physical target.
    assert [(item.machine_metrics["side"], item.machine_metrics["roundNumber"]) for item in exercise.set_results] == [("left", 1), ("right", 1)]
    summary = service.get_exercise_summary(db_session, exercise_id)
    wire = summary.model_dump(by_alias=True)
    assert [(item["setNumber"], item["side"], item["roundNumber"]) for item in wire["setResults"]] == [(1, "left", 1), (2, "right", 1)]
    assert summary.totals.sets_completed == "1 из 1 пар · 2 из 2 сторон"
    assert summary.totals.reps_or_time == "20 повторов"
    assert summary.totals.volume == "400 кг"
    assert "1 из 1 пар" in summary.subtitle
    assert "левая" in (summary.totals.best_set or "")
    state = db_session.scalar(select(UserExerciseState).where(UserExerciseState.exercise_slug == "per-side-test"))
    assert state is not None
    assert state.working_sets == 1
    assert state.working_reps == 10  # A target for one set, not the sum of both sides.
    assert state.calibration_payload["lastResult"]["sets"] == 1
    assert state.calibration_payload["lastResult"]["repsPerSet"] == 10
    assert state.calibration_payload["lastResult"]["volumeKg"] == 400
    history = db_session.scalar(select(ExerciseHistoryRecord).where(ExerciseHistoryRecord.exercise_slug == "per-side-test"))
    assert history is not None and history.sets == 1 and history.reps == 20
    workout = service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Test", status="completed", started_at=datetime.now(UTC),
        exercise_session_ids=[exercise_id],
    ))
    assert workout.exercises[0].current_sets == 1
    assert workout.exercises[0].current_reps == 10
    assert workout.exercises[0].current_load == "20 кг × 1×10"
    assert "1 из 1 пар" in workout.exercises[0].result
    assert next(item for item in workout.metrics if item.label == "подходов / сторон").value == "2 / 2"


@pytest.mark.parametrize("right", [None, "skipped", "zero"])
def test_incomplete_pair_is_not_completed_or_recommended_twice(db_session: Session, right: str | None) -> None:
    sets = [side_result(1, "left")]
    if right is not None:
        sets.append(side_result(2, "right", actual=0, status="skipped" if right == "skipped" else "completed"))
    service = RuntimeService()
    saved = service.save_exercise_session(db_session, payload(sets, status="partial"))
    assert saved.summary.totals.sets_completed == "0 из 1 пар · 1 из 2 сторон"
    assert saved.summary.totals.reps_or_time == "10 повторов"
    assert saved.summary.totals.volume == "200 кг"
    assert "увеличить вес" not in saved.summary.recommendation
    db_session.expire_all()
    state = db_session.scalar(select(UserExerciseState).where(UserExerciseState.exercise_slug == "per-side-test"))
    assert state is not None and state.working_sets == 1  # Keep the planned round on partial completion.
    assert state.calibration_payload["lastResult"]["sets"] == 0
    assert state.calibration_payload["lastResult"]["repsPerSet"] == 10
    workout = service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Partial", status="partial", started_at=datetime.now(UTC),
        exercise_session_ids=[saved.exercise_session.id],
    ))
    assert workout.exercises[0].current_sets == 0
    assert "0 из 1 пар" in workout.exercises[0].result
    assert next(item for item in workout.metrics if item.label == "подходов / сторон").value == "1 / 2"


def test_pairing_uses_round_and_side_not_just_number_of_rows(db_session: Session) -> None:
    service = RuntimeService()
    saved = service.save_exercise_session(db_session, payload([
        side_result(1, "left", round_number=1), side_result(3, "left", round_number=2),
    ], target_sets=4, status="partial"))
    assert saved.summary.totals.sets_completed == "0 из 2 пар · 2 из 4 сторон"


@pytest.mark.parametrize("status", ["skipped", "completed"])
@pytest.mark.parametrize("sets", [[], [side_result(1, "left", actual=0, status="skipped"), side_result(2, "right", actual=0, status="skipped")]])
def test_empty_and_skipped_do_not_crash_or_overwrite_state(db_session: Session, sets: list[SetResultCreateSchema], status: str) -> None:
    state = UserExerciseState(user_id="alexey", exercise_slug="per-side-test", working_sets=3, working_reps=30, calibration_payload={"keep": True})
    db_session.add(state)
    db_session.commit()
    saved = RuntimeService().save_exercise_session(db_session, payload(sets, status=status, target_sets=0))
    assert saved.summary.totals.reps_or_time == "0 повторов"
    db_session.refresh(state)
    assert state.working_sets == 3 and state.calibration_payload == {"keep": True}


def test_warmup_pairs_are_not_working_sets(db_session: Session) -> None:
    sets = [side_result(1, "left", set_type="warmup"), side_result(2, "right", set_type="warmup"),
            side_result(3, "left", round_number=2), side_result(4, "right", round_number=2)]
    saved = RuntimeService().save_exercise_session(db_session, payload(sets, target_sets=4))
    assert saved.summary.totals.sets_completed == "2 из 2 пар · 4 из 4 сторон"
    state = db_session.scalar(select(UserExerciseState).where(UserExerciseState.exercise_slug == "per-side-test"))
    assert state is not None and state.working_sets == 1
    assert state.calibration_payload["lastResult"]["repsPerSet"] == 10


@pytest.mark.parametrize("metrics", [{}, {"side": "invalid", "roundNumber": "bad"}])
def test_legacy_results_keep_physical_counts_and_labels(db_session: Session, metrics: dict[str, object]) -> None:
    sets = [side_result(1, "left"), side_result(2, "right")]
    for item in sets:
        item.machine_metrics = metrics
    service = RuntimeService()
    saved = service.save_exercise_session(db_session, payload(sets))
    assert saved.summary.totals.sets_completed == "2 из 2"
    assert saved.summary.subtitle == "Per side · 2 подхода выполнено"
    assert saved.summary.plan_vs_fact[0].label == "Подходы"
    assert all(item.side is None for item in saved.summary.set_results)
    state = db_session.scalar(select(UserExerciseState).where(UserExerciseState.exercise_slug == "per-side-test"))
    assert state is not None and state.working_sets == 2


def test_timed_sides_and_missing_round_metadata(db_session: Session) -> None:
    sets = [side_result(1, "left", actual=30), side_result(2, "right", actual=30)]
    for item in sets:
        item.reps = None
        item.weight_kg = None
        item.duration_seconds = 30
        item.machine_metrics.pop("roundNumber")
    saved = RuntimeService().save_exercise_session(db_session, payload(sets).model_copy(update={"kind": "timed"}))
    assert saved.summary.totals.sets_completed == "1 из 1 пар · 2 из 2 сторон"
    assert saved.summary.totals.reps_or_time == "60 сек"
    assert saved.summary.totals.volume == "60 сек"
    state = db_session.scalar(select(UserExerciseState).where(UserExerciseState.exercise_slug == "per-side-test"))
    assert state is not None and state.working_sets == 1
    assert state.calibration_payload["lastResult"]["repsPerSet"] == 30


def test_opposite_sides_from_different_rounds_are_not_a_pair(db_session: Session) -> None:
    saved = RuntimeService().save_exercise_session(db_session, payload([
        side_result(1, "left", round_number=1), side_result(4, "right", round_number=2),
    ], target_sets=4, status="partial"))
    assert saved.summary.totals.sets_completed == "0 из 2 пар · 2 из 4 сторон"


@pytest.mark.parametrize("sets", [[], [side_result(1, "left", status="skipped"), side_result(2, "right", actual=0)]])
def test_persisted_mode_keeps_skipped_pair_and_full_plan(db_session: Session, sets: list[SetResultCreateSchema]) -> None:
    service = RuntimeService()
    request = payload(sets, status="skipped" if not sets else "partial").model_dump(by_alias=True)
    request.update(perSide=True, plannedTotal=20)
    saved = service.save_exercise_session(db_session, ExerciseSessionCreateSchema.model_validate(request))
    exercise_id = saved.exercise_session.id
    db_session.expire_all()
    exercise = db_session.get(ExerciseSession, exercise_id)
    assert exercise is not None
    assert exercise.per_side is True and exercise.planned_total == 20
    assert exercise.muscle_targets == []
    summary = service.get_exercise_summary(db_session, exercise_id)
    assert summary.totals.sets_completed == "0 из 1 пар · 0 из 2 сторон"
    assert summary.totals.reps_or_time == "0 повторов"
    assert summary.plan_vs_fact[0].label == "Стороны"
    assert summary.plan_vs_fact[1].plan == "20"
    workout = service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Skipped", status="partial", started_at=datetime.now(UTC),
        exercise_session_ids=[exercise_id],
    ))
    assert next(item for item in workout.metrics if item.label == "подходов / сторон").value == "0 / 2"


def test_left_only_keeps_intended_total_across_incremental_finalization(db_session: Session) -> None:
    service = RuntimeService()
    request = payload([], status="in_progress").model_dump(by_alias=True)
    request.update(perSide=True, plannedTotal=20)
    saved = service.save_exercise_session(db_session, ExerciseSessionCreateSchema.model_validate(request))
    exercise_id = saved.exercise_session.id
    result = side_result(1, "left")
    service.save_set_result(db_session, SetResultSaveSchema(exercise_session_id=exercise_id, **result.model_dump()))
    # An older caller omitting metadata must not erase the persisted plan.
    service.save_exercise_session(db_session, payload([], status="partial").model_copy(update={"exercise_session_id": exercise_id}))
    db_session.expire_all()
    summary = service.get_exercise_summary(db_session, exercise_id)
    assert summary.totals.sets_completed == "0 из 1 пар · 1 из 2 сторон"
    assert summary.plan_vs_fact[1].model_dump() == {"label": "Повторы", "plan": "20", "fact": "10", "delta": "-10"}


@pytest.mark.parametrize("per_side", [False, True])
def test_timed_seconds_do_not_count_as_workout_reps(db_session: Session, per_side: bool) -> None:
    sets = [side_result(1, "left", actual=45), side_result(2, "right", actual=45)]
    for item in sets:
        item.reps = None
        item.weight_kg = None
        item.duration_seconds = 45
        item.planned_value = 45
        if not per_side:
            item.machine_metrics = {}
    service = RuntimeService()
    request = payload(sets).model_dump(by_alias=True)
    request.update(kind="timed", perSide=per_side, plannedTotal=90)
    saved = service.save_exercise_session(db_session, ExerciseSessionCreateSchema.model_validate(request))
    assert saved.summary.totals.reps_or_time == "90 сек"
    workout = service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Timed", status="completed", started_at=datetime.now(UTC),
        exercise_session_ids=[saved.exercise_session.id],
    ))
    assert next(item for item in workout.metrics if item.label == "повторов").value == "0"


def test_per_side_migration_preserves_legacy_rows_and_is_reversible(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'per-side.db'}")
    command.upgrade(config, "20261016_0010")
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO exercise_sessions
                (user_id, exercise_slug, exercise_name, kind, order_index, status,
                 started_at, target_sets, muscle_targets, created_at, updated_at)
                VALUES ('alexey', 'legacy', 'Legacy', 'machine', 1, 'skipped',
                        CURRENT_TIMESTAMP, 2, '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
        command.upgrade(config, "20261016_0011")
        columns = {column["name"]: column for column in inspect(engine).get_columns("exercise_sessions")}
        assert columns["per_side"]["nullable"] is False
        assert columns["planned_total"]["nullable"] is True
        with engine.begin() as connection:
            assert connection.execute(text("SELECT per_side, planned_total, target_sets FROM exercise_sessions")).one() == (0, None, 2)
            connection.execute(text("UPDATE exercise_sessions SET per_side = 1, planned_total = 20"))
        command.downgrade(config, "20261016_0010")
        assert not {"per_side", "planned_total"} & {column["name"] for column in inspect(engine).get_columns("exercise_sessions")}
        with engine.connect() as connection:
            assert connection.execute(text("SELECT exercise_slug, target_sets, muscle_targets FROM exercise_sessions")).one() == ("legacy", 2, "[]")
        command.upgrade(config, "20261016_0011")
    finally:
        engine.dispose()