"""Deletion must roll back achievement state, and re-earning must re-point the award."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.achievement import AchievementGrant
from app.services.achievements.service import evaluate_user, workout_awards
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
    rows = [practice(db_session, day) for day in range(12)]
    db_session.commit()
    evaluate_user(db_session, 'alexey', source_workout_id=rows[0].id)

    grant = _grant(db_session, 'start.first_set', 1)
    assert grant.status == 'earned'
    assert grant.source_workout_id == rows[0].id
    assert workout_awards(db_session, 'alexey', rows[0].id)['awards']

    RuntimeService().delete_workout_session(db_session, workout_session_id=rows[0].id, user_id='alexey')
    db_session.expire_all()

    grant = _grant(db_session, 'start.first_set', 1)
    assert grant.status == 'revoked'
    assert grant.source_workout_id is None
    # The removed workout must not keep any award attached to it.
    assert workout_awards(db_session, 'alexey', rows[0].id) is None

    new_row = practice(db_session, 30)
    db_session.commit()
    evaluate_user(db_session, 'alexey', source_workout_id=new_row.id)

    grant = _grant(db_session, 'start.first_set', 1)
    assert grant.status == 'earned'
    assert grant.source_workout_id == new_row.id
    awards = workout_awards(db_session, 'alexey', new_row.id)
    assert any(award['definitionId'] == 'start.first_set' for award in awards['awards'])
