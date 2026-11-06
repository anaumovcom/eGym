"""Core difficulty and accounting regressions, entirely offline on fixture databases."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.achievement import AchievementEvidence, AchievementGrant
from app.models.enums import RuntimeFlowSource, WorkoutSessionStatus
from app.services.achievements import content, service
from app.services.achievements.facts import FactBuilder
from app.services.achievements.generation import BudgetLedger
from app.services.achievements.rules import RULES
from app.tests import test_achievements as fixtures

START = datetime(2026, 1, 1, 12, tzinfo=UTC)


def practice(db, day, *, note=False):
    row = fixtures.workout(db, 'alexey', START + timedelta(days=day))
    if note:
        row.notes = 'Private note; never provider input'
    for _ in range(2):
        fixtures.result(db, row, 'alexey')
    return row


@pytest.mark.parametrize('status', [WorkoutSessionStatus.in_progress, WorkoutSessionStatus.completed])
def test_unfinalized_work_never_inflates_core_counts(db_session, status):
    row = fixtures.workout(db_session, 'alexey', START, status=status)
    row.finished_at = None
    fixtures.result(db_session, row, 'alexey', actual=500)
    facts = FactBuilder(db_session, 'alexey').finish()
    assert facts['qualified_sets'] == facts['qualified_reps'] == facts['volume_grams'] == 0


@pytest.mark.parametrize('metadata', [
    {'sourceClass': 'synthetic'}, {'sourceClass': 'emulator'}, {'simulation': True},
    {'isTest': True}, {'isSimulated': True}, {'hardwareAdapter': 'emulator'},
    {'completionStatus': 'unknown'},
])
def test_core_excludes_all_simulation_and_unknown_completion_markers(db_session, metadata):
    row = fixtures.workout(db_session, 'alexey', START)
    fixtures.result(db_session, row, 'alexey', actual=500,
                    metrics={'setType': 'working', 'completionStatus': 'completed', **metadata})
    assert FactBuilder(db_session, 'alexey').finish()['qualified_sets'] == 0


def test_repeated_sets_on_third_day_are_not_familiar_history(db_session):
    for day in range(3):
        practice(db_session, day)
    assert FactBuilder(db_session, 'alexey').finish()['familiar_days'] == 0
    practice(db_session, 3)
    assert FactBuilder(db_session, 'alexey').finish()['familiar_days'] == 1


def test_notes_and_practice_must_share_real_qualifying_days(db_session):
    for day in range(12):
        row = fixtures.workout(db_session, 'alexey', START + timedelta(days=day))
        row.notes = 'A note with only one set'
        fixtures.result(db_session, row, 'alexey')
    for day in range(12, 24):
        practice(db_session, day)
    facts = FactBuilder(db_session, 'alexey').finish()
    assert facts['note_days'] == facts['practice_evidence_days'] == 12
    assert facts['evidence:note_days'] == 0
    service.evaluate_user(db_session, 'alexey')
    assert not db_session.scalar(select(AchievementGrant).where(AchievementGrant.definition_id == 'reflection.note'))


def test_builder_session_is_not_a_completed_saved_program(db_session):
    row = practice(db_session, 0)
    row.source = RuntimeFlowSource.builder
    db_session.flush()
    assert FactBuilder(db_session, 'alexey').finish()['completed_programs'] == 0


def test_progress_exposes_both_gates_instead_of_false_99_percent(db_session):
    practice(db_session, 0)
    service.evaluate_user(db_session, 'alexey')
    line = next(row for row in service.catalog(db_session, 'alexey', limit=200)['lines']
                if row['id'] == 'start.first_set')
    assert line['currentValue'] == 2
    assert line['evidenceDays'] == 1
    assert line['tiers'][0]['minimumEvidenceDays'] == 12
    assert line['progressPercent'] == 8.3
    assert not any(tier['earned'] for tier in line['tiers'])


def test_twelve_days_award_opening_but_not_middle_tier(db_session):
    for day in range(12):
        practice(db_session, day)
    service.evaluate_user(db_session, 'alexey')
    line = service.detail(db_session, 'alexey', 'start.first_set')
    assert [tier['earned'] for tier in line['tiers']] == [True, False, False]


def test_bounded_return_window_has_achievable_scoped_evidence(db_session):
    rules = {rule['id']: rule for rule in RULES}
    rule = rules['rhythm.after_return']
    assert rule['minimumEvidenceDays'] == [12, 20, 30]
    assert rule['evidenceMetric'] == 'evidence:post_return_days'
    for day in range(12):
        practice(db_session, day)
    practice(db_session, 30)
    facts = FactBuilder(db_session, 'alexey').finish()
    assert facts['practice_evidence_days'] == 13
    assert facts[rule['evidenceMetric']] == 0


def test_previous_gated_version_is_not_accidentally_grandfathered(db_session):
    row = practice(db_session, 0)
    grant = AchievementGrant(user_id='alexey', definition_id='start.first_set', tier=1,
        scope_key='lifetime', status='earned', source_workout_id=row.id,
        earned_at=row.started_at, awarded_at=row.started_at, evidence_digest='fixture')
    db_session.add(grant)
    db_session.flush()
    db_session.add(AchievementEvidence(grant_id=grant.id, source_type='workout', source_id=str(row.id),
        source_revision='achievements-rules-1.2.0', metric_value=2, unit='set'))
    db_session.commit()
    service.evaluate_user(db_session, 'alexey')
    assert grant.status == 'revoked'


def test_rule_profiles_are_not_a_blanket_multiday_delay():
    core = RULES[:120]
    assert len({tuple(rule['minimumEvidenceDays']) for rule in core}) >= 8
    assert all(rule['minimumEvidenceDays'][0] >= 12 for rule in core)
    assert all(rule['evidenceMetric'].startswith('evidence:') for rule in core)


def test_all_paid_editorial_is_preserved_verbatim_during_reconciliation():
    before = content.load_catalog()
    after = content.reconcile_catalog(before)
    old = {tier['id']: tier for line in before['lines'] for tier in line['tiers']
           if tier['contentOrigin'] == 'gpt-6.1-sol'}
    new = {tier['id']: tier for line in after['lines'] for tier in line['tiers']}
    fields = ('title', 'phrase', 'imagePrompt', 'fishMarkup', 'audioText', 'contentOrigin', 'editorialStyle')
    assert len(old) >= 375
    for key, tier in old.items():
        assert {field: new[key].get(field) for field in fields} == {field: tier.get(field) for field in fields}


def test_budget_reload_retains_unknown_liabilities_and_historical_holds(tmp_path):
    path = tmp_path / 'ledger.json'
    ledger = BudgetLedger(path, openai_cap_usd=1)
    ledger.reserve('historical-hold', 'openai', 'legacy', 'unknown', 800_000)
    ledger.sent('historical-hold')
    ledger.unsettled('historical-hold')
    ledger = BudgetLedger(path, openai_cap_usd=1)
    assert ledger.committed('openai') == 800_000
    with pytest.raises(RuntimeError, match='budget_exhausted'):
        ledger.reserve('new', 'openai', 'text', 'gpt-6.1-sol', 200_001)
    with pytest.raises(RuntimeError, match='outcome_unknown'):
        ledger.reserve('historical-hold', 'openai', 'text', 'gpt-6.1-sol', 1)