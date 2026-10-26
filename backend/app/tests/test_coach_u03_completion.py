"""U03 offline local-first contract, lifecycle, queue and audible/attempt budgets."""

import asyncio
import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.coach import CoachEvent
from app.schemas.coach_control import CoachPreferences
from app.services.coach import ledger
from app.services.coach.completion import LocalCompletion, additional_package, duplicate_local
from app.services.coach.director import Director
from app.services.coach.identity import WorkState
from app.services.coach.luna import FakeTextAuthor
from app.tests.test_coach_e10_live import HYBRID, echo, event, make_coach, seed, settle


@pytest.fixture(autouse=True)
def enabled(use_test_emulator, monkeypatch):
    monkeypatch.setenv('COACH_ENABLED', 'true')
    get_settings.cache_clear()


def local(cue='set-end', idea='set_closed'):
    return {'cueIds': [cue], 'acknowledged': [idea]}


def count_script(text='Выполнено десять повторов.'):
    def script(body):
        output = echo(text)(body)
        data = json.loads(body['input'][0]['content'])
        output['usedFactIds'] = data['lockedFactIds'] or ['saved-set']
        return output
    return script


@pytest.mark.parametrize('value', [
    {'cueIds': ['invented'], 'acknowledged': ['set_closed']},
    {'cueIds': ['set-end'], 'acknowledged': ['unknown']},
    {'cueIds': ['set-end'], 'acknowledged': ['set_partial']},
    {'cueIds': ['set-end'] * 4, 'acknowledged': ['set_closed'] * 4},
    {'cueIds': ['set-end'] * 2, 'acknowledged': ['set_closed'] * 2},
    {'cueIds': [], 'acknowledged': []},
    {**local(), 'text': 'arbitrary instructions'},
    {'cueIds': [True], 'acknowledged': ['set_closed']},
])
def test_fixed_bounded_local_contract(value):
    with pytest.raises(ValidationError):
        LocalCompletion.model_validate(value)


@pytest.mark.parametrize('cue,idea,text', [
    ('set-end', 'set_closed', 'Подход завершён. Выполнено десять повторов.'),
    ('set-partial', 'set_partial', 'План подхода выполнен частично.'),
    ('exercise-done', 'exercise_full', 'Все подходы выполнены.'),
    ('exercise-partial', 'exercise_partial', 'Упражнение выполнено частично.'),
    ('exercise-skipped', 'exercise_skipped', 'Упражнение пропущено.'),
    ('workout-done', 'workout_closed', 'Тренировка завершена.'),
    ('workout-partial', 'workout_partial', 'Тренировка завершена частично.'),
    ('last-set-next', 'last_set_remaining', 'Остался последний подход.'),
    ('set-end', 'set_closed', 'Закрыли подход.'),
    ('exercise-done', 'exercise_full', 'Упражнение сделано.'),
    ('workout-done', 'workout_closed', 'Закончили тренировку.'),
])
def test_duplicate_clause_is_forbidden_even_with_new_count(cue, idea, text):
    acknowledged = LocalCompletion.model_validate(local(cue, idea))
    assert duplicate_local(text, acknowledged)
    assert not duplicate_local('Выполнено десять повторов.', acknowledged)


def test_opportunity_fsm_is_idempotent_and_terminal():
    for terminal in ('completed', 'interrupted', 'expired', 'rejected'):
        state = WorkState()
        assert not state.transition('completed')
        assert state.transition('preparing')
        assert not state.transition('preparing')
        if terminal in {'completed', 'interrupted'}:
            assert state.transition('ready')
            assert state.transition('started')
        assert state.transition(terminal)
        for next_state in ('pending', 'preparing', 'ready', 'started', 'completed', 'interrupted', 'expired', 'rejected'):
            assert not state.transition(next_state)


async def test_set_closed_allows_new_saved_count_without_local_outcome(session_factory):
    with session_factory() as db:
        _, _, sid = seed(db, actual=10, planned=10, status='completed')
    fake = FakeTextAuthor(count_script())
    coach, sink, run = make_coach(session_factory, fake_text=fake)
    message = event('set_persisted', run, set_ordinal=1, phase='rest', refs={'backendSetId': sid},
                    context={'localCompletion': local(), 'restMs': 90_000})
    await coach.handle(message)
    await settle(coach)
    assert sink.of('speech_start')[0]['text'] == 'Выполнено десять повторов.'
    data = json.loads(fake.calls[0]['input'][0]['content'])
    assert data['localCompletion'] == ['set_closed']
    assert 'outcome' not in {f['id'] for f in data['allowedFacts']}
    assert 'saved-set' in {f['id'] for f in data['allowedFacts']}
    assert coach.stats.opportunities == {'pending': 1, 'preparing': 1, 'ready': 1}
    await coach.close()


@pytest.mark.parametrize('text,used_count', [
    ('Подход завершён. Выполнено десять повторов.', True),
    ('Поехали, спокойно и собранно.', False),
    ('Поехали, спокойно и собранно.', True),
])
async def test_no_duplicate_or_generic_followup_reaches_voice(session_factory, text, used_count):
    with session_factory() as db:
        _, _, sid = seed(db, actual=10, planned=10, status='completed')
    fake = FakeTextAuthor(count_script(text) if used_count else echo(text))
    coach, sink, run = make_coach(session_factory, fake_text=fake)
    await coach.handle(event('set_persisted', run, set_ordinal=1, phase='rest', refs={'backendSetId': sid},
                             context={'localCompletion': local(), 'restMs': 90_000}))
    await settle(coach)
    assert not sink.of('speech_start') and not sink.bytes
    assert sink.of('decision')[-1]['reason'] == 'no_useful_content'
    assert coach.stats.opportunities['rejected'] == 1
    assert len(fake.calls) == 1


async def test_partial_honesty_survives_local_full_and_matching_partial_is_not_repeated(session_factory):
    with session_factory() as db:
        _, _, sid = seed(db, actual=8, planned=10, status='partial')
    for acknowledgment, expected in [(local(), 'План подхода выполнен частично. Выполнено восемь повторов.'),
                                     (local('set-partial', 'set_partial'), 'Выполнено восемь повторов.')]:
        fake = FakeTextAuthor(count_script('Выполнено восемь повторов.'))
        coach, sink, run = make_coach(session_factory, fake_text=fake)
        message = event('set_persisted', run, set_ordinal=1, phase='rest', refs={'backendSetId': sid},
                        context={'localCompletion': acknowledgment, 'restMs': 90_000})
        await coach.handle(message)
        await settle(coach)
        assert sink.of('speech_start')[0]['text'] == expected
        await coach.close()


async def test_comparison_locked_count_is_new_and_preserved(session_factory):
    with session_factory() as db:
        seed(db, days_ago=7, actual=8, planned=8, status='completed')
        _, _, sid = seed(db, actual=10, planned=10, status='completed')
    fake = FakeTextAuthor(echo('Хороший шаг вперёд.'))
    coach, sink, run = make_coach(session_factory, CoachPreferences(**HYBRID, history_consent=True), fake_text=fake)
    await coach.handle(event('set_persisted', run, set_ordinal=1, phase='rest', refs={'backendSetId': sid},
                             context={'localCompletion': local(), 'restMs': 90_000}))
    await settle(coach)
    data = json.loads(fake.calls[0]['input'][0]['content'])
    assert data['lockedFactIds'] == ['comparison', 'saved-set']
    assert sink.of('speech_start')[0]['text'].startswith(data['lockedFactClause'])
    await coach.close()


async def test_wrong_completion_scope_is_rejected_before_author(session_factory):
    fake = FakeTextAuthor(echo())
    coach, sink, run = make_coach(session_factory, fake_text=fake)
    await coach.handle(event('workout_started', run, context={'localCompletion': local()}))
    assert sink.of('event_rejected')[-1]['reason'] == 'invalid_local_completion'
    assert not fake.calls


async def test_summary_without_new_facts_is_silent_before_author(session_factory):
    with session_factory() as db:
        _, eid, _ = seed(db, actual=8, planned=10, status='partial')
    fake = FakeTextAuthor(echo())
    prefs = CoachPreferences(**HYBRID, say_numbers=False, say_weight=False, say_exercise_name=False)
    coach, sink, run = make_coach(session_factory, prefs, fake_text=fake)
    await coach.handle(event('exercise_finalized', run, phase='exercise-summary', refs={'backendExerciseId': eid},
                             context={'localCompletion': local('exercise-partial', 'exercise_partial')}))
    assert not fake.calls and not sink.of('speech_start')
    assert sink.of('decision')[-1]['reason'] == 'no_useful_content'
    assert coach.stats.opportunities == {'pending': 1, 'rejected': 1}
    assert not coach.director.slot_counts


@pytest.mark.parametrize('kind,cue,idea,ref,used,text', [
    ('exercise_finalized', 'exercise-partial', 'exercise_partial', 'backendExerciseId', 'best-set',
     'Лучший подход — восемь повторов.'),
    ('workout_finalized', 'workout-partial', 'workout_partial', 'backendWorkoutId', 'total-reps',
     'Всего восемь повторов.'),
])
async def test_partial_summary_adds_numbers_not_the_already_local_outcome(
        session_factory, kind, cue, idea, ref, used, text):
    with session_factory() as db:
        wid, eid, _ = seed(db, actual=8, planned=10, status='partial')
    def script(body):
        output = echo(text)(body)
        output['usedFactIds'] = [used]
        return output
    fake = FakeTextAuthor(script)
    coach, sink, run = make_coach(session_factory, fake_text=fake)
    await coach.handle(event(kind, run, phase='exercise-summary' if kind == 'exercise_finalized' else 'workout-summary',
                             refs={ref: eid if kind == 'exercise_finalized' else wid},
                             context={'localCompletion': local(cue, idea)}))
    await settle(coach)
    assert sink.of('speech_start')[0]['text'] == text
    data = json.loads(fake.calls[0]['input'][0]['content'])
    assert 'outcome' not in {f['id'] for f in data['allowedFacts']}
    await coach.close()


async def test_actual_duration_updates_do_not_add_starts_or_attempts(session_factory):
    coach, sink, run = make_coach(session_factory)
    await coach.handle(event('workout_started', run))
    await settle(coach)
    gid = sink.of('speech_start')[0]['generationId']
    await coach.handle({'type': 'playback_completed', 'generationId': gid, 'durationMs': 9000})
    assert not coach.memory.completed
    await coach.handle({'type': 'playback_started', 'generationId': gid})
    attempts = dict(coach.director.slot_counts)
    await coach.handle({'type': 'playback_started', 'generationId': gid, 'durationMs': 9000})
    assert coach.director.audible[0][1] == 9000
    assert coach.memory.started[gid].duration_ms == 9000
    assert len(coach.director.audible) == 1 and len(coach.memory.started) == 1
    await coach.handle({'type': 'playback_completed', 'generationId': gid, 'durationMs': 8000})
    await coach.handle({'type': 'playback_failed', 'generationId': gid})
    assert coach.memory.started[gid].duration_ms == 8000
    assert gid in coach.memory.completed and gid not in coach.memory.interrupted
    assert coach.stats.opportunities['started'] == coach.stats.opportunities['completed'] == 1
    assert coach.director.slot_counts == attempts


def test_same_timestamp_overlaps_update_only_the_matching_utterance():
    director = Director()
    director.note_audible(1000, 2500, content=True, utterance_id='a')
    director.note_audible(1000, 2500, content=True, utterance_id='b')
    director.update_audible('a', 9000)
    assert director.audible == [(1000, 9000), (1000, 2500)]


async def test_priority_queue_preserves_burst_until_source_expiry(session_factory):
    with session_factory() as db:
        wid, eid, sid = seed(db, actual=10, planned=10, status='completed')
    coach, sink, run = make_coach(session_factory)
    clock = [1000.0]
    coach.monotonic_ms = lambda: clock[0]
    # Occupy only the paid pipeline; queue planning still uses authoritative saved rows.
    blocker = asyncio.Event()
    coach.task = asyncio.create_task(blocker.wait())
    messages = []
    for _ in range(8):
        message = event('set_persisted', run, set_ordinal=1, phase='rest', refs={'backendSetId': sid})
        messages.append(message)
        await coach.handle(message)
    assert len(coach.queue) == 8
    assert not sink.of('decision')
    await coach.handle(event('exercise_finalized', run, phase='exercise-summary', refs={'backendExerciseId': eid}))
    await coach.handle(event('workout_finalized', run, phase='workout-summary', refs={'backendWorkoutId': wid}))
    assert len(coach.queue) == 10
    assert [op.event.kind for op in coach.queue[:2]] == ['workout_finalized', 'exercise_finalized']
    assert not sink.of('decision')
    clock[0] += 30_000
    await coach.handle({'type': 'ping'})
    assert not coach.queue
    assert [m['reason'] for m in sink.of('decision')].count('expired') == 10
    await coach.handle(messages[0])
    assert sink.of('event_rejected')[-1]['reason'] == 'duplicate'
    assert not coach.author.adapter.calls
    await coach.close()


async def test_outcome_only_filtered_package_has_no_additional_fact(session_factory):
    with session_factory() as db:
        _, _, sid = seed(db, actual=10, planned=10, status='completed')
        coach, _, run = make_coach(session_factory)
        message = event('set_persisted', run, set_ordinal=1, phase='rest')
        op = coach.plan(db, CoachEvent.model_validate(message['event']), {'backendSetId': sid}, {})
        outcome = next(f for f in op.package.facts if f.id == 'outcome')
        package = replace(op.package, facts=(outcome,))
        assert additional_package(package, LocalCompletion.model_validate(local())).facts == ()


@pytest.mark.parametrize('failure', ['timeout', 'validation', 'silence', 'budget', 'busy'])
async def test_failures_are_terminal_and_attempt_density_never_retries_forever(session_factory, failure):
    with session_factory() as db:
        _, _, sid = seed(db, actual=10, planned=10, status='completed')
    script = count_script()
    if failure == 'validation':
        def script(body):
            return {'unvalidated': 'not speech'}
    elif failure == 'silence':
        def script(body):
            output = echo()(body)
            output.update(action='silence', text='', usedFactIds=[], silenceReason='no_useful_content')
            return output
    fake = FakeTextAuthor(script, delay_s=.1 if failure == 'timeout' else 0)
    coach, sink, run = make_coach(session_factory, fake_text=fake)
    if failure == 'timeout':
        coach.author.timeout_s = .01
    if failure == 'budget':
        with session_factory() as db:
            ledger.get_run(db, run).cap_micros = 0
            db.commit()
    if failure == 'busy':
        # Ordinary work and completions both wait, then respect explicit safety.
        blocker = asyncio.Event()
        coach.task = asyncio.create_task(blocker.wait())
        await coach.handle(event('exercise_ready', run))
        assert not sink.of('decision') and len(coach.queue) == 1
    message = event('set_persisted', run, set_ordinal=1, phase='rest', refs={'backendSetId': sid},
                    context={'localCompletion': local(), 'restMs': 90_000})
    await coach.handle(message)
    if failure == 'busy':
        assert len(coach.queue) == 2
        await coach.cancel('safety')
    else:
        await settle(coach)
    assert not sink.of('speech_start') and not sink.bytes
    reasons = [m['reason'] for m in sink.of('decision')]
    expected = {'timeout': 'provider_timeout', 'validation': 'validation_failed',
                'silence': 'no_useful_content', 'budget': 'budget', 'busy': 'safety'}[failure]
    assert any(reason and reason.startswith(expected) for reason in reasons)
    for _ in range(3):
        await coach.handle(message)
    # A fresh event ID cannot bypass the same set's consumed attempt/density slot.
    await coach.handle({**message, 'event': {**message['event'], 'id': 'same-result-new-event'}})
    if failure != 'busy':
        await settle(coach)
        assert len(fake.calls) == (0 if failure == 'budget' else 1)
        # V0.3: an exhausted ledger (tier 4) is refused before the Director, so no density slot is consumed.
        assert sum(coach.director.slot_counts.values()) == (0 if failure == 'budget' else 1)
    assert coach.stats.opportunities['rejected'] >= 1
    await coach.close()