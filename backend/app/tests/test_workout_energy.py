from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.profile import UserProfile
from app.schemas.runtime import ExerciseSessionCreateSchema, SetResultCreateSchema, WorkoutSessionCreateSchema
from app.services.runtime_service import RuntimeService


@pytest.mark.parametrize(("weight", "seconds", "actual", "kind", "status", "expected", "hint"), [
    (80, 3600, 10, "machine", "completed", "≈ 2 ккал", "30 с работы · оценка: 3 с/повтор"),
    (40, 3600, 10, "machine", "completed", "≈ 1 ккал", "30 с работы"),
    (80, 1800, 5, "machine", "partial", "≈ 1 ккал", "15 с работы"),
    (80, 59, 10, "machine", "completed", "≈ 2 ккал", "30 с работы"),
    (80, 86400, 10, "machine", "completed", "≈ 2 ккал", "30 с работы"),
    (80, 3600, 30, "timed", "completed", "≈ 2 ккал", "30 с работы · по времени подходов"),
    (80, 3600, 30, "stretch", "completed", "≈ 2 ккал", "30 с работы"),
    (80, 3600, 10, "bodyweight", "completed", "≈ 2 ккал", "30 с работы"),
    (None, 3600, 10, "machine", "completed", "—", "укажите вес тела"),
    ("missing", 3600, 10, "machine", "completed", "—", "укажите вес тела"),
    (0, 3600, 10, "machine", "completed", "—", "укажите вес тела"),
    (-80, 3600, 10, "machine", "completed", "—", "укажите вес тела"),
    (80, 0, 10, "machine", "completed", "≈ 2 ккал", "30 с работы"),
    (80, -60, 10, "machine", "completed", "≈ 2 ккал", "30 с работы"),
    (80, 3600, 0, "machine", "completed", "0 ккал", "нет выполненных подходов"),
    (80, 3600, 0, "machine", "skipped", "0 ккал", "нет выполненных подходов"),
    (80, 3600, 10, "machine", "skipped", "0 ккал", "нет выполненных подходов"),
])
def test_workout_energy(db_session: Session, weight, seconds, actual, kind, status, expected, hint) -> None:
    profile = db_session.get(UserProfile, "alexey")
    assert profile is not None
    if weight == "missing":
        db_session.delete(profile)
    else:
        profile.weight_kg = weight
    db_session.commit()
    service = RuntimeService()
    exercise = service.save_exercise_session(db_session, ExerciseSessionCreateSchema(
        user_id="alexey", exercise_slug="energy-test", exercise_name="Energy test", kind=kind,
        status=status, started_at=datetime.now(UTC), target_sets=1,
        sets=[SetResultCreateSchema(
            set_number=1, planned_value=10, actual_value=actual,
            reps=None if kind == "timed" else actual,
            weight_kg=20 if kind == "machine" else None, tempo_label="stable",
            machine_metrics={"completionStatus": "skipped" if status == "skipped" else "completed"},
        )],
    )).exercise_session
    summary = service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Energy test", status="partial" if status == "skipped" else status,
        started_at=datetime.now(UTC), duration_seconds=seconds, exercise_session_ids=[exercise.id],
    ))
    metric = next(item for item in summary.metrics if item.label == "энергия")
    assert metric.value == expected
    assert hint in metric.hint
    assert summary.metrics.index(metric) < 4  # Visible in the main summary cards.
    db_session.expire_all()
    reloaded = service.build_workout_summary(db_session, summary.workout_session_id)
    assert next(item for item in reloaded.metrics if item.label == "энергия") == metric


def test_empty_workout_without_profile_does_not_invent_calories(db_session: Session) -> None:
    summary = RuntimeService().save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="guest", source="catalog", title="Empty", status="aborted",
        started_at=datetime.now(UTC), duration_seconds=3600,
    ))
    assert next(item for item in summary.metrics if item.label == "энергия").value == "0 ккал"


@pytest.mark.parametrize(("kind", "duration", "reps", "expected_seconds", "estimated"), [
    ("machine", 120, 10, 120, False),
    ("machine", 0, 10, 30, True),
    ("machine", -30, 10, 30, True),
    ("machine", None, None, 30, True),
    ("machine", None, 0, 0, False),
    ("timed", 120, None, 10, False),  # Performed seconds beat a stale duration/target.
    ("stretch", 120, 10, 10, False),
])
def test_energy_uses_performed_duration_or_rep_fallback(
    db_session: Session, kind, duration, reps, expected_seconds, estimated,
) -> None:
    profile = db_session.get(UserProfile, "alexey")
    assert profile is not None
    profile.weight_kg = 80
    db_session.commit()
    summary = RuntimeService().save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Active work", status="partial",
        started_at=datetime.now(UTC), duration_seconds=86400,
        exercises=[ExerciseSessionCreateSchema(
            user_id="alexey", exercise_slug="active-test", exercise_name="Active", kind=kind,
            status="partial", started_at=datetime.now(UTC), target_sets=10,
            sets=[SetResultCreateSchema(
                set_number=1, planned_value=100, actual_value=10, reps=reps,
                duration_seconds=duration, rest_duration_seconds=3600, tempo_label="stable",
                machine_metrics={"completionStatus": "partial"},
            )],
        )],
    ))
    metric = next(item for item in summary.metrics if item.label == "энергия")
    assert metric.value == (f"≈ {round(3.5 * expected_seconds / 60)} ккал" if expected_seconds else "0 ккал")
    assert ("3 с/повтор" in metric.hint) is estimated


def test_energy_sums_sides_and_mixed_sets_once_ignoring_skipped_and_zero(db_session: Session) -> None:
    profile = db_session.get(UserProfile, "alexey")
    assert profile is not None
    profile.weight_kg = 80
    db_session.commit()
    sets = [
        SetResultCreateSchema(
            set_number=number, planned_value=100, actual_value=actual, reps=actual,
            duration_seconds=duration, rest_duration_seconds=3600, tempo_label="stable",
            machine_metrics={"side": side, "roundNumber": (number + 1) // 2, "completionStatus": status},
        )
        for number, side, actual, duration, status in [
            (1, "left", 10, 60, "completed"),
            (2, "right", 10, None, "partial"),
            (3, "left", 10, 3600, "skipped"),
            (4, "right", 0, 3600, "completed"),
        ]
    ]
    summary = RuntimeService().save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Sides", status="partial",
        started_at=datetime.now(UTC), duration_seconds=86400,
        exercises=[ExerciseSessionCreateSchema(
            user_id="alexey", exercise_slug="side-energy", exercise_name="Sides", kind="machine",
            status="partial", started_at=datetime.now(UTC), target_sets=4, per_side=True, sets=sets,
        ), ExerciseSessionCreateSchema(
            user_id="alexey", exercise_slug="timed-energy", exercise_name="Timed", kind="timed",
            status="completed", started_at=datetime.now(UTC), target_sets=1,
            sets=[SetResultCreateSchema(set_number=1, planned_value=60, actual_value=30, tempo_label="stable")],
        )],
    ))
    metric = next(item for item in summary.metrics if item.label == "энергия")
    assert metric.value == "≈ 7 ккал"  # 60 + 10*3 + 30 = 120 active seconds.
    assert metric.hint == "2 мин 0 с работы · оценка: 3 с/повтор"