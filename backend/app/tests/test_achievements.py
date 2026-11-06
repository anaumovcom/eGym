from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementEvidence, AchievementGrant
from app.models.analytics import ExerciseSession, SetResult, WorkoutSession
from app.models.enums import ExerciseSessionStatus, RuntimeExerciseKind, RuntimeFlowSource, WorkoutSessionStatus
from app.services.achievements.content import load_catalog, validate_catalog
from app.services.achievements.facts import training_day
from app.services.achievements.media import manifest_summary
from app.services.achievements.rules import CATALOG_VERSION, RULES
from app.services.achievements.service import catalog, detail, evaluate_user, overview, workout_awards


def workout(db: Session, user_id: str, started: datetime, *, status=WorkoutSessionStatus.completed) -> WorkoutSession:
    row = WorkoutSession(user_id=user_id, source=RuntimeFlowSource.catalog, title="Test", status=status,
                         started_at=started, finished_at=started + timedelta(minutes=30), duration_seconds=1800)
    db.add(row)
    db.flush()
    return row


def result(db: Session, workout_row: WorkoutSession, user_id: str, *, kind=RuntimeExerciseKind.machine,
           actual=10, weight=20.0, slug="press", metrics=None) -> SetResult:
    exercise = ExerciseSession(workout_session_id=workout_row.id, user_id=user_id, exercise_slug=slug,
                               exercise_name=slug, kind=kind, order_index=1, status=ExerciseSessionStatus.completed,
                               started_at=workout_row.started_at, finished_at=workout_row.finished_at,
                               target_sets=1, set_results=[])
    db.add(exercise)
    db.flush()
    row = SetResult(exercise_session_id=exercise.id, set_number=1, planned_value=actual, actual_value=actual,
                    reps=actual if kind not in {RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch} else None,
                    duration_seconds=actual if kind in {RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch} else None,
                    weight_kg=weight, tempo_label="normal", created_at=workout_row.started_at,
                    machine_metrics=metrics or {"setType": "working", "completionStatus": "completed"})
    db.add(row)
    db.flush()
    return row


def test_catalog_has_120_independent_lines_and_360_tiers():
    catalog = load_catalog()
    assert len(catalog["lines"]) == len(RULES)
    assert sum(len(line["tiers"]) for line in catalog["lines"]) == sum(len(rule['thresholds']) for rule in RULES)
    assert len({rule["metric"] for rule in RULES}) > 100
    complete = all(tier["contentOrigin"] == "gpt-6.1-sol" for line in catalog["lines"] for tier in line["tiers"])
    if complete:
        assert validate_catalog(catalog, generated=True) == []


def test_training_day_resets_at_three():
    zone = datetime.now().astimezone().tzinfo
    assert training_day(datetime(2026, 1, 2, 2, 59, tzinfo=zone)).isoformat() == "2026-01-01"
    assert training_day(datetime(2026, 1, 2, 3, 0, tzinfo=zone)).isoformat() == "2026-01-02"


def test_evaluation_is_idempotent_and_scoped_to_workout(db_session: Session):
    user_id = "alexey"
    for day in range(12):
        first = workout(db_session, user_id, datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(days=day))
        for _ in range(2):
            result(db_session, first, user_id, actual=10, weight=20,
                   metrics={'setType': 'working', 'completionStatus': 'completed'})
    db_session.commit()

    evaluation = evaluate_user(db_session, user_id, source_workout_id=first.id)
    assert evaluation["awarded"]
    assert len(db_session.scalars(select(AchievementGrant).where(AchievementGrant.user_id == user_id)).all()) == len(evaluation["awarded"])
    assert evaluate_user(db_session, user_id, source_workout_id=first.id)["awarded"] == []
    awards = workout_awards(db_session, user_id, first.id)
    assert awards is not None and len(awards["awards"]) == len(evaluation["awarded"])
    assert all(award["sourceWorkoutId"] == first.id for award in awards["awards"])
    assert workout_awards(db_session, "elena", first.id) is None


def test_seconds_are_not_reps_and_volume_uses_exact_grams(db_session: Session):
    user_id = "alexey"
    row = workout(db_session, user_id, datetime(2026, 1, 1, 12, tzinfo=UTC))
    result(db_session, row, user_id, kind=RuntimeExerciseKind.timed, actual=45, weight=None)
    db_session.commit()
    evaluate_user(db_session, user_id, source_workout_id=row.id)
    grants = {(grant.definition_id, grant.tier) for grant in db_session.scalars(select(AchievementGrant))}
    assert ("variety.timed_seconds", 1) not in grants
    assert ("practice.reps", 1) not in grants
    assert ("start.first_set", 1) not in grants  # no first-session freebies


def test_simulated_sets_never_award(db_session: Session):
    user_id = "alexey"
    row = workout(db_session, user_id, datetime(2026, 1, 1, 12, tzinfo=UTC))
    result(db_session, row, user_id, metrics={"sourceClass": "simulated", "setType": "working"})
    db_session.commit()
    evaluation = evaluate_user(db_session, user_id, source_workout_id=row.id)
    assert evaluation["awarded"] == []
    assert workout_awards(db_session, user_id, row.id)["awards"] == []


def test_media_summary_has_expected_catalog_size():
    assert manifest_summary()["lines"] == len(RULES)
    assert manifest_summary()["tiers"] == sum(len(rule['thresholds']) for rule in RULES)


def test_summary_and_detail_include_lines_after_120(db_session):
    summary = overview(db_session, 'alexey')
    assert summary['totalLines'] == len(RULES)
    assert summary['totalTiers'] == sum(len(rule['thresholds']) for rule in RULES)
    assert summary['completedLines'] == 0
    assert detail(db_session, 'alexey', RULES[-1]['id']) is None
    assert len(catalog(db_session, 'alexey', limit=len(RULES))['lines']) == len(RULES)


def test_rebalance_preserves_historical_but_revokes_new_invalid_evidence(db_session):
    row = workout(db_session, 'alexey', datetime(2026, 1, 1, 12, tzinfo=UTC))
    result(db_session, row, 'alexey')
    old = AchievementGrant(user_id='alexey', definition_id='start.first_set', tier=1, scope_key='lifetime',
                           status='earned', source_workout_id=row.id, earned_at=row.started_at,
                           awarded_at=row.started_at, evidence_digest='historical')
    new = AchievementGrant(user_id='alexey', definition_id='start.first_workout', tier=1, scope_key='lifetime',
                           status='earned', source_workout_id=row.id, earned_at=row.started_at,
                           awarded_at=row.started_at, evidence_digest='new')
    db_session.add_all([old, new])
    db_session.flush()
    for grant, revision in ((old, 'achievements-rules-1.1.0'), (new, CATALOG_VERSION)):
        db_session.add(AchievementEvidence(grant_id=grant.id, source_type='workout', source_id=str(row.id),
                                          source_revision=revision, metric_value=1, unit='test'))
    db_session.commit()
    evaluate_user(db_session, 'alexey')
    assert old.status == 'earned'
    assert new.status == 'revoked'
