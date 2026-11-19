"""Deletion must roll back achievement state, and re-earning must re-point the award."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.achievement import AchievementEvidence, AchievementGrant, AchievementProgress
from app.services.achievements.facts import FactBuilder
from app.services.achievements.service import detail, evaluate_user, overview, workout_awards
from app.services.runtime_service import RuntimeService
from app.tests import test_achievements as fixtures

START = datetime(2026, 1, 1, 12, tzinfo=UTC)


def practice(db, day, *, n_sets=2):
    row = fixtures.workout(db, 'alexey', START + timedelta(days=day))
    for _ in range(n_sets):
        fixtures.result(db, row, 'alexey', actual=10, weight=20,
                        metrics={'setType': 'working', 'completionStatus': 'completed'})
    db.flush()
    return row


def _grant(db, definition_id, tier):
    return db.scalar(select(AchievementGrant).where(
        AchievementGrant.user_id == 'alexey', AchievementGrant.definition_id == definition_id,
        AchievementGrant.tier == tier))


def test_deleting_source_workout_rolls_back_and_re_earn_points_at_new_workout(db_session):
    rows = [practice(db_session, day) for day in range(5)]
    db_session.commit()
    evaluate_user(db_session, 'alexey', source_workout_id=rows[-1].id)

    grant = _grant(db_session, 'rhythm.active_days', 1)
    assert grant.status == 'earned'
    assert grant.source_workout_id == rows[-1].id
    assert workout_awards(db_session, 'alexey', rows[-1].id)['awards']

    RuntimeService().delete_workout_session(db_session, workout_session_id=rows[-1].id, user_id='alexey')
    db_session.expire_all()

    grant = _grant(db_session, 'rhythm.active_days', 1)
    assert grant.status == 'revoked'
    assert grant.source_workout_id is None
    # This profile first received its backlog at the last finish. Redistribute the surviving
    # first- and third-workout awards to the actual milestones in the corrected history.
    assert _grant(db_session, 'start.first_workout', 1).source_workout_id == rows[0].id
    assert _grant(db_session, 'start.first_workout', 2).source_workout_id == rows[2].id
    # The removed workout must not keep any award attached to it.
    assert workout_awards(db_session, 'alexey', rows[-1].id) is None

    new_row = practice(db_session, 30)
    db_session.commit()
    evaluate_user(db_session, 'alexey', source_workout_id=new_row.id)

    grant = _grant(db_session, 'rhythm.active_days', 1)
    assert grant.status == 'earned'
    assert grant.source_workout_id == new_row.id
    awards = workout_awards(db_session, 'alexey', new_row.id)
    assert any(award['definitionId'] == 'rhythm.active_days' for award in awards['awards'])


def test_deleting_a_day_can_create_a_gap_but_only_a_finish_can_award_it(db_session):
    for day in (0, 8, 16):
        row = practice(db_session, day)
        evaluate_user(db_session, 'alexey', source_workout_id=row.id)
        if day == 8:
            middle_id = row.id
    db_session.commit()
    key = 'return.homecoming'
    assert _grant(db_session, key, 1) is None
    RuntimeService().delete_workout_session(db_session, workout_session_id=middle_id, user_id='alexey')
    line = detail(db_session, 'alexey', key)
    assert line['currentValue'] == 1 and line['highestTier'] == 0
    assert _grant(db_session, key, 1) is None
    later = practice(db_session, 17)
    evaluate_user(db_session, 'alexey', source_workout_id=later.id)
    assert _grant(db_session, key, 1).source_workout_id == later.id


def _legacy_first_set(db_session, original, total_sets):
    key = 'start.first_set'
    grant = AchievementGrant(user_id='alexey', definition_id=key, tier=1, scope_key='lifetime', status='earned',
                             source_workout_id=original.id, earned_at=original.finished_at, awarded_at=original.finished_at,
                             evidence_digest='old')
    progress = AchievementProgress(user_id='alexey', definition_id=key, scope_key='lifetime', current_value=total_sets, highest_tier=1)
    db_session.add_all([grant, progress])
    db_session.flush()
    db_session.add(AchievementEvidence(grant_id=grant.id, source_type='workout', source_id=str(original.id),
                                       source_revision='achievements-rules-1.3.0', metric_value=24, unit='подходов'))
    db_session.commit()
    return grant, progress


def test_archive_rolls_back_using_its_original_evidence_day_requirement(db_session):
    rows = [practice(db_session, day) for day in range(13)]
    grant, progress = _legacy_first_set(db_session, rows[-2], 26)
    db_session.delete(progress)  # Some imports contain the award without its display progress.
    db_session.flush()

    runtime = RuntimeService()
    runtime.delete_workout_session(db_session, workout_session_id=rows[0].id, user_id='alexey')
    assert grant.status == 'earned' and grant.source_workout_id == rows[-1].id
    progress = db_session.scalars(select(AchievementProgress).where(
        AchievementProgress.user_id == 'alexey', AchievementProgress.definition_id == grant.definition_id)).one()
    assert progress.current_value == 24 and progress.highest_tier == 1
    evidence = db_session.scalars(select(AchievementEvidence).where(AchievementEvidence.grant_id == grant.id)).one()
    assert (evidence.source_id, evidence.source_revision) == (str(rows[-1].id), 'achievements-rules-1.3.0')

    runtime.delete_workout_session(db_session, workout_session_id=rows[-1].id, user_id='alexey')
    assert grant.status == 'revoked' and progress.highest_tier == 0
    assert progress.current_value == 22
    assert detail(db_session, 'alexey', grant.definition_id) is None
    assert overview(db_session, 'alexey')['archivedTiers'] == 0


def test_archive_requires_a_surviving_finish_that_can_confirm_all_its_conditions(db_session):
    for day in range(11):
        practice(db_session, day)
    legacy = practice(db_session, 11, n_sets=0)
    stretch = fixtures.result(db_session, legacy, 'alexey', slug='abdominals-stretch-variation-one', actual=60)
    # This older machine entry records stretch practice in seconds, with no completed repetitions.
    stretch.duration_seconds, stretch.reps = 60, 0
    original = practice(db_session, 12)
    grant, progress = _legacy_first_set(db_session, original, 24)

    RuntimeService().delete_workout_session(db_session, workout_session_id=original.id, user_id='alexey')
    history = FactBuilder(db_session, 'alexey')
    assert history.finish()['practice_evidence_days'] == 12
    assert not next(w for w in history.workouts if w.row.id == legacy.id).qualified
    assert grant.status == 'revoked' and grant.source_workout_id is None
    assert progress.highest_tier == 0 and progress.current_value == 22
