"""Scoped achievements use only offline saved-workout fixtures, never paid content."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementGrant
from app.models.analytics import ExerciseSession, SetResult, WorkoutSession
from app.models.enums import ExerciseSessionStatus, RuntimeExerciseKind, RuntimeFlowSource, WorkoutSessionStatus
from app.services.achievements import service
from app.services.achievements.facts import FactBuilder, training_day
from app.services.achievements.rules import EXTENSION_RULES, RULES
from app.services.achievements.training_scope import (
    CANONICAL_GROUP_IDS,
    CURATED_PRIMARY,
    SAVED_PROGRAM_EXERCISES,
    TrainingScopeCounter,
    canonical_primary_targets,
    exercise_metric,
    muscle_metric,
)
from app.services.muscle_catalog import CANONICAL_MUSCLE_DEFINITIONS

SLUG = "smith-machine-bench-press"
METRIC = exercise_metric(SLUG)
START = datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize('slug,targets', list(CURATED_PRIMARY.items()))
def test_reviewed_primary_map_works_without_legacy_roles(db_session, slug, targets):
    _, exercise = saved(db_session, slug=slug, targets=[])
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2)
    result = values(db_session)
    assert all(result[muscle_metric(muscle)] == 1 for muscle in targets)


def test_unmapped_muscles_are_explicitly_insufficient_not_implied(db_session):
    for muscle in ('abdominals', 'forearms', 'obliques', 'rear-shoulders'):
        assert service._data_state(db_session, 'alexey', 'requires_primary', muscle_metric(muscle)) == 'insufficient_data'
    assert service._data_state(db_session, 'alexey', 'requires_primary', muscle_metric('chest')) == 'available'


def saved(db: Session, *, day=0, owner="alexey", slug=SLUG, kind="machine",
          status="completed", targets=None, per_side=False, at=None):
    started = (at or START + timedelta(days=day)).astimezone(UTC)
    workout = WorkoutSession(user_id=owner, source=RuntimeFlowSource.builder, title="Offline fixture",
                             status=WorkoutSessionStatus(status), started_at=started,
                             finished_at=started + timedelta(minutes=10) if status != "in_progress" else None,
                             duration_seconds=600)
    db.add(workout)
    db.flush()
    exercise = ExerciseSession(workout_session_id=workout.id, user_id=owner, exercise_slug=slug,
                               exercise_name=slug, kind=RuntimeExerciseKind(kind),
                               status=ExerciseSessionStatus.partial, started_at=started,
                               finished_at=workout.finished_at, target_sets=3, per_side=per_side,
                               muscle_targets=targets if targets is not None else [
                                   {"muscle_id": "chest", "role": "primary"},
                                   {"muscle_id": "triceps", "role": "secondary"}])
    db.add(exercise)
    db.flush()
    return workout, exercise


def add_set(db: Session, exercise: ExerciseSession, ordinal=1, *, actual=10, planned=None,
            data=None, at=None, duration=None, reps=None):
    timed = exercise.kind in {RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch}
    row = SetResult(exercise_session_id=exercise.id, set_number=ordinal,
                    planned_value=actual if planned is None else planned, actual_value=actual,
                    reps=(None if timed else actual) if reps is None else reps,
                    duration_seconds=(actual if timed else None) if duration is None else duration,
                    tempo_label="normal", created_at=(at or exercise.started_at).astimezone(UTC),
                    machine_metrics={"completionStatus": "completed", "setType": "work", **(data or {})})
    db.add(row)
    db.flush()
    return row


def values(db):
    db.flush()
    return FactBuilder(db, "alexey").finish()


def test_extension_inventory_and_nontrivial_thresholds():
    assert len(SAVED_PROGRAM_EXERCISES) == len(set(SAVED_PROGRAM_EXERCISES)) == 17
    assert len(CANONICAL_GROUP_IDS) == 15
    assert set(CANONICAL_GROUP_IDS) == set(CANONICAL_MUSCLE_DEFINITIONS)
    assert len(EXTENSION_RULES) == 32
    assert all(rule["thresholds"] == [12, 30, 75, 150] for rule in EXTENSION_RULES)
    assert RULES[-32:] == EXTENSION_RULES
    assert len({rule["id"] for rule in RULES}) == len(RULES)


def test_one_set_is_not_a_practice_day_and_partial_workout_keeps_full_sets(db_session):
    _, exercise = saved(db_session, status="partial")
    add_set(db_session, exercise)
    assert values(db_session)[METRIC] == 0
    add_set(db_session, exercise, 2)
    result = values(db_session)
    assert result[METRIC] == result[muscle_metric("chest")] == 1
    assert result[muscle_metric("triceps")] == 0


@pytest.mark.parametrize("data,actual,planned", [
    ({"completionStatus": "partial"}, 10, 10),
    ({"completionStatus": "skipped"}, 10, 10),
    ({"completionStatus": None}, 10, 10),
    ({"setType": "warmup"}, 10, 10),
    ({"setType": None}, 10, 10),
    ({"sourceClass": "simulated"}, 10, 10),
    ({"sourceClass": "test"}, 10, 10),
    ({"sourceClass": "emulator"}, 10, 10),
    ({"simulation": True}, 10, 10),
    ({"isTest": True}, 10, 10),
    ({"isSimulated": True}, 10, 10),
    ({"hardwareAdapter": "emulator"}, 10, 10),
    ({}, 0, 10), ({}, 9, 10), ({}, 10, 0),
])
def test_incomplete_warmup_unknown_and_simulation_do_not_qualify(db_session, data, actual, planned):
    _, exercise = saved(db_session)
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2, actual=actual, planned=planned, data=data)
    assert values(db_session)[METRIC] == 0


@pytest.mark.parametrize("status", ["in_progress", "aborted"])
def test_unfinished_and_aborted_workouts_are_excluded(db_session, status):
    _, exercise = saved(db_session, status=status)
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2)
    assert values(db_session)[METRIC] == 0


def test_missing_finalization_timestamp_is_excluded(db_session):
    workout, exercise = saved(db_session)
    workout.finished_at = None
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2)
    assert values(db_session)[METRIC] == 0


def test_unilateral_requires_two_complete_rounds_and_never_joins_exercise_sessions(db_session):
    _, exercise = saved(db_session, per_side=True)
    add_set(db_session, exercise, 1, data={"side": "left", "roundNumber": 1})
    add_set(db_session, exercise, 2, data={"side": "right", "roundNumber": 1})
    add_set(db_session, exercise, 3, data={"side": "left", "roundNumber": 2})
    assert values(db_session)[METRIC] == 0
    _, other = saved(db_session, per_side=True)
    add_set(db_session, other, data={"side": "right", "roundNumber": 2})
    assert values(db_session)[METRIC] == 0
    add_set(db_session, exercise, 4, data={"side": "right", "roundNumber": 2})
    assert values(db_session)[METRIC] == 1


@pytest.mark.parametrize("bad", [{}, {"side": "left"}, {"side": "right", "roundNumber": True}])
def test_unilateral_missing_side_or_round_metadata_is_not_guessed(db_session, bad):
    _, exercise = saved(db_session, per_side=True)
    for ordinal in range(1, 5):
        add_set(db_session, exercise, ordinal, data=bad)
    assert values(db_session)[METRIC] == 0


def test_duplicate_ordinal_and_duplicate_side_do_not_inflate_credit(db_session):
    _, exercise = saved(db_session)
    add_set(db_session, exercise)
    add_set(db_session, exercise)
    assert values(db_session)[METRIC] == 0
    _, sided = saved(db_session, per_side=True)
    for ordinal, side in enumerate(["left", "right", "left", "right"], 1):
        add_set(db_session, sided, ordinal, data={"side": side, "roundNumber": 1})
    # One bilateral set plus one complete unilateral round is two working units.
    assert values(db_session)[METRIC] == 1


def test_timed_cardio_has_practice_but_no_strength_credit(db_session):
    slug = "butt-kick"
    _, exercise = saved(db_session, slug=slug, kind="timed")
    add_set(db_session, exercise, actual=59)
    assert values(db_session)[exercise_metric(slug)] == 0
    add_set(db_session, exercise, 2, actual=1)
    result = values(db_session)
    assert result[exercise_metric(slug)] == 1
    assert result[muscle_metric("chest")] == 0


def test_timed_unilateral_counts_minimum_side_duration_not_sum(db_session):
    _, exercise = saved(db_session, kind="timed", per_side=True)
    add_set(db_session, exercise, 1, actual=60, data={"side": "left", "roundNumber": 1})
    add_set(db_session, exercise, 2, actual=30, data={"side": "right", "roundNumber": 1})
    assert values(db_session)[METRIC] == 0
    for ordinal, side in [(3, "left"), (4, "right")]:
        add_set(db_session, exercise, ordinal, actual=30, data={"side": side, "roundNumber": 2})
    assert values(db_session)[METRIC] == 1


def test_bodyweight_counts_without_weight_and_stretch_never_counts_strength(db_session):
    _, exercise = saved(db_session, kind="bodyweight")
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2)
    assert values(db_session)[METRIC] == 1
    _, stretch = saved(db_session, day=1, kind="stretch")
    add_set(db_session, stretch, actual=60)
    result = values(db_session)
    assert result[METRIC] == 2  # A saved positive stretch duration can count exercise practice.
    assert result[muscle_metric("chest")] == 1
    _, misclassified = saved(db_session, day=2, slug="abdominals-stretch-variation-one")
    add_set(db_session, misclassified, duration=60, actual=60)
    add_set(db_session, misclassified, 2, duration=60, actual=60)
    assert values(db_session)[muscle_metric("chest")] == 1


def test_canonical_roles_only_no_names_aliases_or_arbitrary_order(db_session):
    targets = [{"muscle_id": "triceps", "role": "stabilizer"},
               {"muscle_id": "Грудь", "role": "primary"},
               {"muscle_id": "back", "role": "primary"},
               {"muscle_id": "chest"}, {"muscle_id": "lats", "role": "primary"}]
    assert canonical_primary_targets(targets) == {"lats"}
    _, exercise = saved(db_session, targets=targets)
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2)
    result = values(db_session)
    assert result[muscle_metric("lats")] == 1
    assert result[muscle_metric("chest")] == result[muscle_metric("triceps")] == 0
    assert result[METRIC] == 1


def test_inventory_does_not_expand_from_unrelated_catalog_exercises(db_session):
    _, exercise = saved(db_session, slug="not-in-saved-programs")
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2)
    result = values(db_session)
    assert exercise_metric(exercise.exercise_slug) not in result
    assert result[muscle_metric("chest")] == 1


@pytest.mark.parametrize("group", CANONICAL_GROUP_IDS)
def test_each_canonical_group_uses_its_own_primary_fact(db_session, group):
    _, exercise = saved(db_session, targets=[{"muscle_id": group, "role": "primary"}])
    add_set(db_session, exercise)
    add_set(db_session, exercise, 2)
    result = values(db_session)
    assert result[muscle_metric(group)] == 1
    assert all(result[muscle_metric(other)] == 0 for other in CANONICAL_GROUP_IDS if other != group)


def test_day_boundary_uses_actual_saved_set_time_and_daily_dedup(db_session):
    zone = datetime.now().astimezone().tzinfo
    before = datetime(2026, 1, 2, 2, 59, tzinfo=zone)
    after = datetime(2026, 1, 2, 3, 0, tzinfo=zone)
    _, exercise = saved(db_session, at=before)
    add_set(db_session, exercise, at=before)
    add_set(db_session, exercise, 2, at=after)
    assert values(db_session)[METRIC] == 0
    add_set(db_session, exercise, 3, at=before)
    add_set(db_session, exercise, 4, at=after)
    assert values(db_session)[METRIC] == 2
    _, other = saved(db_session, at=after)
    add_set(db_session, other)
    add_set(db_session, other, 2)
    assert values(db_session)[METRIC] == 2


def test_counter_and_owner_isolation_are_idempotent(db_session):
    workout, exercise = saved(db_session)
    rows = [add_set(db_session, exercise), add_set(db_session, exercise, 2)]
    counter = TrainingScopeCounter("alexey")
    counter.add_exercise(workout, exercise, rows, training_day)
    counter.add_exercise(workout, exercise, rows, training_day)
    assert counter.values()[METRIC] == 1
    stranger = TrainingScopeCounter("elena")
    stranger.add_exercise(workout, exercise, rows, training_day)
    assert stranger.values()[METRIC] == 0
    exercise.user_id = "elena"  # Corrupt cross-owner linkage is not evidence.
    assert values(db_session)[METRIC] == 0


def test_twelve_days_award_once_without_touching_generated_catalog(db_session, monkeypatch):
    # Parent owns catalog reconciliation. Exercise the real evaluator without catalog writes.
    monkeypatch.setattr(service, "sync_definitions", lambda session: None)
    last = None
    for day in range(12):
        last, exercise = saved(db_session, day=day)
        add_set(db_session, exercise)
        add_set(db_session, exercise, 2)
        if day == 0:
            assert values(db_session)[METRIC] == 1
            assert all(values(db_session)[METRIC] < threshold for threshold in EXTENSION_RULES[0]["thresholds"])
    db_session.commit()
    assert last is not None
    assert values(db_session)[METRIC] == 12
    service.evaluate_user(db_session, "alexey", source_workout_id=last.id)
    def extension():
        return list(db_session.scalars(select(AchievementGrant).where(
            AchievementGrant.definition_id.in_([r["id"] for r in EXTENSION_RULES]))))
    grants = extension()
    assert {(g.definition_id, g.tier) for g in grants} == {("exercise." + SLUG, 1), ("muscle.chest", 1)}
    ids = {grant.id for grant in grants}
    service.evaluate_user(db_session, "alexey", source_workout_id=last.id)
    assert {grant.id for grant in extension()} == ids
    assert all(grant.status == "earned" for grant in extension())
    assert FactBuilder(db_session, "elena").finish()[METRIC] == 0