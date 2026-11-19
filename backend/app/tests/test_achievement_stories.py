from datetime import UTC, datetime, timedelta
from hashlib import sha256

from app.services.achievements.collection import collection
from app.services.achievements.facts import FactBuilder
from app.services.achievements.media import asset_file, collection_voice, manifest_summary
from app.services.achievements.service import detail, evaluate_user, workout_awards
from app.services.runtime_service import RuntimeService
from app.tests.test_achievements import result, workout


def test_story_uses_actual_workouts_and_retells_the_named_movements_after_deletion(db_session):
    monday = datetime(2026, 1, 5, 12, tzinfo=UTC)

    def train(day, *slugs, hour=0):
        row = workout(db_session, 'alexey', monday + timedelta(days=day, hours=hour))
        for slug in slugs:
            result(db_session, row, 'alexey', slug=slug)
        evaluate_user(db_session, 'alexey', source_workout_id=row.id)
        return row

    train(0, 'Присед', 'Тяга', 'Планка')
    train(0, 'Жим', hour=3)
    second = train(4, 'Присед', 'Жим', 'Планка')
    awards = {a['definitionId']: a for a in workout_awards(db_session, 'alexey', second.id)['awards']}
    assert awards['discovery.encore']['valueAtAward'] == 3
    assert awards['discovery.crossroads']['valueAtAward'] == 2
    assert set(awards['discovery.crossroads']['movements']) in ({'Жим', 'Присед'}, {'Жим', 'Планка'})
    assert awards['signature.bookends']['movements'] == ['Присед', 'Планка']
    assert 'calendar.weekend_guest' not in awards
    saturday = train(5, 'Планка')
    sunday = train(6, 'Присед')
    assert detail(db_session, 'alexey', 'calendar.weekend_guest')['currentValue'] == 1
    reward = next(a for a in workout_awards(db_session, 'alexey', saturday.id)['awards'] if a['definitionId'] == 'calendar.weekend_guest')
    assert reward['movements'] == ['Планка']
    RuntimeService().delete_workout_session(db_session, workout_session_id=saturday.id, user_id='alexey')
    moved = next(a for a in workout_awards(db_session, 'alexey', sunday.id)['awards'] if a['definitionId'] == 'calendar.weekend_guest')
    assert moved['grantId'] == reward['grantId'] and moved['movements'] == ['Присед']
    RuntimeService().delete_workout_session(db_session, workout_session_id=second.id, user_id='alexey')
    assert detail(db_session, 'alexey', 'discovery.crossroads')['highestTier'] == 0
    assert detail(db_session, 'alexey', 'signature.bookends')['highestTier'] == 0


def test_same_day_repetitions_and_separate_sessions_do_not_make_a_story(db_session):
    start = datetime(2026, 1, 5, 12, tzinfo=UTC)
    for hour, names in enumerate((['А', 'Б', 'В'], ['А', 'Г', 'В'], ['Г'], ['Б'])):
        row = workout(db_session, 'alexey', start + timedelta(hours=hour))
        for name in names:
            result(db_session, row, 'alexey', slug=name)
    facts = FactBuilder(db_session, 'alexey', collection_only=True).finish()
    assert all(facts.get(key, 0) == 0 for key in ('discovery.encore', 'discovery.crossroads', 'signature.bookends', 'calendar.weekend_guest'))


def test_every_active_tier_has_a_distinct_story_and_the_recording_for_its_current_text():
    active = [line for line in collection().values() if not line.get('archived')]
    clips = collection_voice()
    captions = set()
    for line in collection().values():
        for tier in line['tiers']:
            if not line.get('archived'):
                assert tier['phrase'] not in captions
                captions.add(tier['phrase'])
            script = tier['audioText']
            assert tier['phrase'] in script and script.startswith(tier['title'])
            rev = sha256(f'Microsoft Irina Desktop|ru-awards-v1|{script}'.encode()).hexdigest()[:12]
            assert clips[tier['id']].endswith(f'.{rev}.mp3')
            path = asset_file(tier['id'], 'audio')
            assert path.is_file() and path.stat().st_size > 2500
    assert manifest_summary(active) == dict(lines=len(active), tiers=len(captions), images=len(captions), audio=len(captions))
