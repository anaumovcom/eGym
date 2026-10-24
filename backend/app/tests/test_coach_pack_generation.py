from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.api.routes.coach import get_pack_provider
from app.core.config import get_settings
from app.models.coach import CoachJob, CoachLedgerRun
from app.services.coach import pack_generation, packs
from app.services.coach.packs import FakePackVoice
from app.services.coach.schema import ensure_job_failure_counter
from app.services.coach.voice import voice_pricing
from app.tests.test_coach_control_plane import ORIGIN, auth, secured  # noqa: F401
from app.tests.test_coach_e09_packs import pack_env  # noqa: F401


@pytest.fixture
def paid_pack(client, secured, monkeypatch):  # noqa: F811
    auth(client)
    for provider in ('openai', 'fish'):
        response = client.put(f'/api/coach/credentials?provider={provider}',
                              json={'key': f'synthetic-{provider}-key', 'expectedVersion': 0}, headers=ORIGIN)
        assert response.status_code == 200
    monkeypatch.setenv('COACH_ENABLED', 'true')
    monkeypatch.setenv('COACH_PAID_VOICE_ENABLED', 'true')
    monkeypatch.setenv('COACH_VOICE_PRICING_VERIFIED', 'true')
    get_settings.cache_clear()
    yield
    client.app.dependency_overrides.pop(get_pack_provider, None)
    pack_generation.active_slots.clear()
    get_settings.cache_clear()


def body(**kwargs):
    return {'userId': 'alexey', 'capUsd': '2.00', 'confirmPaid': True, **kwargs}


def test_old_job_schema_repair_is_additive_and_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE coach_jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL)'))
        connection.execute(text("INSERT INTO coach_jobs (id, state) VALUES ('existing-job', 'paused')"))
        ensure_job_failure_counter(connection)
        ensure_job_failure_counter(connection)
        assert connection.execute(text('SELECT id, state, failures FROM coach_jobs')).one() == ('existing-job', 'paused', 0)


def test_prepare_rejects_outdated_schema_before_provider_dispatch(client, paid_pack, pack_env, session_factory):  # noqa: F811
    with session_factory().get_bind().begin() as connection:
        connection.execute(text('ALTER TABLE coach_jobs DROP COLUMN failures'))
    calls = []
    client.app.dependency_overrides[get_pack_provider] = lambda: lambda *args: calls.append(True)
    response = client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN)
    assert response.status_code == 503
    assert response.json()['detail'] == 'coach_schema_outdated'
    assert calls == []


def test_prepare_requires_operator_and_confirmation(client, pack_env):  # noqa: F811
    client.base_url = 'http://localhost'
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN).status_code in {401, 403, 503}
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(confirmPaid=False), headers=ORIGIN).status_code == 422


def test_prepare_generates_and_downloads_without_repaying(client, paid_pack, pack_env, session_factory):  # noqa: F811
    class SyntheticPaidVoice(FakePackVoice):
        name = 'fish'
        test_only = False

        async def synthesize(self, *args, **kwargs):
            audio = await super().synthesize(*args, **kwargs)
            return replace(audio, usage={**audio.usage, 'audioOutputTokens': 0})

    voice = SyntheticPaidVoice()
    closed = []

    async def close():
        closed.append(True)

    client.app.dependency_overrides[get_pack_provider] = lambda: lambda sessions, slot: pack_generation.PackProvider(voice, voice_pricing('fish'), close)
    response = client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['state'] == 'queued' and closed == [True]
    headers = {'X-Coach-Run-Token': result['runToken']}
    status = client.get(f"/api/coach/runs/{result['runId']}/jobs/{result['jobId']}", headers=headers)
    assert status.json()['state'] == 'completed'
    assert status.json()['completed'] == status.json()['total']
    assert len(voice.calls) == sum(spec.required for spec in packs.CATALOG.values())
    manifest = client.get('/api/coach/packs/fish-streamer/manifest')
    assert manifest.status_code == 200
    assert manifest.json()['voice'] == packs.provider_voice('fish-streamer')
    assert pack_env.manifest('ash') is None
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN).json() == {'state': 'completed'}
    assert closed == [True]
    with session_factory() as db:
        assert db.get(CoachLedgerRun, result['runId']).state == 'closed'


def test_prepare_validates_keys_switches_budget_and_busy(client, paid_pack, pack_env, monkeypatch):  # noqa: F811
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(capUsd='3.00'), headers=ORIGIN).status_code == 422
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(capUsd='0'), headers=ORIGIN).status_code == 422
    pack_generation.active_slots.add('fish-streamer')
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN).json()['detail'] == 'pack_generation_busy'
    pack_generation.active_slots.clear()
    monkeypatch.setenv('COACH_PAID_VOICE_ENABLED', 'false')
    get_settings.cache_clear()
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN).json()['detail'] == 'pack_generation_disabled'


def test_prepare_failure_closes_provider_and_preserves_partial_work(client, paid_pack, pack_env, session_factory):  # noqa: F811
    closed = []

    async def close():
        closed.append(True)

    class FailingVoice(FakePackVoice):
        name = 'fish'
        test_only = False

        async def synthesize(self, *args, **kwargs):
            raise HTTPException(503, 'synthetic provider secret must not escape')

    client.app.dependency_overrides[get_pack_provider] = lambda: lambda sessions, slot: pack_generation.PackProvider(FailingVoice(), voice_pricing('fish'), close)
    response = client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN)
    assert response.status_code == 200 and 'secret' not in response.text
    result = response.json()
    with session_factory() as db:
        assert db.get(CoachJob, result['jobId']).state == 'paused'
        assert db.get(CoachLedgerRun, result['runId']).state == 'closed'
    assert closed == [True] and not pack_generation.active_slots
    assert pack_env.manifest('fish-streamer') is None