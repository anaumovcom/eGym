from dataclasses import replace
from hashlib import sha256

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

pytestmark = pytest.mark.usefixtures('isolated_coach_lifespan')


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


@pytest.fixture
def synthetic_speaker(client, paid_pack):
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
    return voice, closed


def test_prepare_generates_and_downloads_without_repaying(client, synthetic_speaker, pack_env, session_factory):  # noqa: F811
    voice, closed = synthetic_speaker
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


def test_interrupted_preparation_does_not_leave_settings_polling(client, synthetic_speaker, pack_env, monkeypatch):  # noqa: F811
    async def lost_generation(*args, **kwargs):
        return None

    monkeypatch.setattr(packs.PackJobRunner, 'run', lost_generation)
    result = client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN).json()
    status = client.get(f'/api/coach/runs/{result["runId"]}/jobs/{result["jobId"]}', headers={'X-Coach-Run-Token': result['runToken']})
    assert status.json()['state'] == 'paused' and not synthetic_speaker[0].calls


def test_prepare_validates_keys_switches_budget_and_busy(client, paid_pack, pack_env, monkeypatch):  # noqa: F811
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(capUsd='3.00'), headers=ORIGIN).status_code == 422
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(capUsd='0'), headers=ORIGIN).status_code == 422
    pack_generation.active_slots.add(packs.storage_slot('fish-streamer'))
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN).json()['detail'] == 'pack_generation_busy'
    pack_generation.active_slots.clear()
    monkeypatch.setenv('COACH_PAID_VOICE_ENABLED', 'false')
    get_settings.cache_clear()
    assert client.post('/api/coach/packs/fish-streamer/prepare', json=body(), headers=ORIGIN).json()['detail'] == 'pack_generation_disabled'


def test_full_catalogue_plan_get_only(client, pack_env):  # noqa: F811
    client.base_url = 'http://localhost'
    plan = client.get('/api/coach/packs/ash/plan').json()
    assert plan['groups']['count'] == {'total': 100, 'generated': 0, 'published': 0, 'playable': 0}
    assert plan['required'] == {'total': 61, 'generated': 0}
    assert plan['optional'] == {'total': 70, 'generated': 0}
    assert plan['groups']['technique']['total'] == 2
    assert plan['groups']['guidance']['total'] == 3
    rows = {row['clipId']: row for row in plan['clips']}
    for clip, phases in [('tip-machine-prepare', ['setup', 'rest']), ('tip-machine-no-jerks', ['active'])]:
        assert rows[clip]['tip']['exerciseSlugs'] == ['machine-pulldown']
        assert rows[clip]['tip']['phases'] == phases and rows[clip]['tip']['loadModes'] == ['constant']
        assert rows[clip]['required'] and rows[clip]['text'] == packs.CATALOG[clip].text
    assert not pack_env.root.exists()


def test_bundled_voice_is_downloadable_without_credentials_or_generation(client, pack_env, monkeypatch):  # noqa: F811
    client.base_url = 'http://localhost'
    monkeypatch.setattr(packs.starter_voice, 'synthesize', lambda *args: pytest.fail('GET cannot synthesize audio'))
    base = '/api/coach/packs/ru-base'
    manifest = client.get(base + '/manifest').json()
    assert manifest['missingClips'] == 0 and manifest['clips'].keys() == packs.CATALOG.keys()
    for key, entry in manifest['clips'].items():
        assert entry['text'] == packs.CATALOG[key].text
        assert entry['fingerprint'] == packs.fingerprint(packs.CATALOG[key], manifest['voice'], manifest['model'])
        response = client.get(f"{base}/{manifest['packVersion']}/clips/{key}")
        assert response.status_code == 200 and sha256(response.content).hexdigest() == entry['sha256']
    assert not pack_env.root.exists()


def test_free_single_recording_and_review_are_version_scoped(client, secured, pack_env):  # noqa: F811
    base = '/api/coach/packs/ru-base'
    manifest = client.get(base + '/manifest').json()
    key = 'pain-stop'
    old = manifest['packVersion']
    original = client.get(f'{base}/{old}/clips/{key}').content
    params = {'expectedPackVersion': old, 'pace': 'slow', 'confirmLocal': True}
    assert client.post(f'{base}/clips/{key}/record', json=params, headers=ORIGIN).status_code != 200
    auth(client)
    assert client.post(base + '/prepare', json=body(), headers=ORIGIN).json()['detail'] == 'local_pack_only'
    result = client.post(f'{base}/clips/{key}/record', json=params, headers=ORIGIN)
    assert result.status_code == 200, result.text
    new = result.json()['packVersion']
    updated = client.get(base + '/manifest').json()['clips']
    assert new != old and not updated[key]['approved']
    assert all(updated[i] == manifest['clips'][i] for i in updated if i != key)
    assert client.get(f'{base}/{old}/clips/{key}').content == original != client.get(f'{base}/{new}/clips/{key}').content
    assert client.post(f'{base}/clips/{key}/record', json=params, headers=ORIGIN).status_code == 409
    review = f'{base}/clips/{key}/approve'
    assert client.post(review, json={'expectedPackVersion': old, 'listened': True}, headers=ORIGIN).status_code == 409
    assert client.post(review, json={'expectedPackVersion': new, 'listened': False}, headers=ORIGIN).status_code == 422
    assert client.post(review, json={'expectedPackVersion': new, 'listened': True}, headers=ORIGIN).status_code == 200
    assert client.get(base + '/manifest').json()['clips'][key] == {**updated[key], 'approved': True}


def test_downloaded_pack_replacements_are_atomic(client, synthetic_speaker, pack_env, monkeypatch):  # noqa: F811
    voice, _ = synthetic_speaker
    ids = ['count-1', 'count-31', 'tip-machine-prepare', 'set-start', 'safety-stop']
    monkeypatch.setattr(packs, 'CATALOG', {key: packs.CATALOG[key] for key in ids})
    base = '/api/coach/packs/fish-streamer'
    alias = f'/api/coach/packs/fish-{packs.provider_voice("fish-streamer")}'

    def post(url, **fields):
        return client.post(url, json=body(**fields), headers=ORIGIN)

    def status(response):
        assert response.status_code == 200, response.text
        job = response.json()
        return client.get(f'/api/coach/runs/{job["runId"]}/jobs/{job["jobId"]}',
                          headers={'X-Coach-Run-Token': job['runToken']}).json()

    def version():
        return client.get(base + '/manifest').json()['packVersion']

    def audio(ver, clip):
        response = client.get(f'{base}/{ver}/clips/{clip}')
        assert response.status_code == 200
        return response.content

    assert post(base + '/regenerate', expectedPackVersion='1' * 16).status_code == 404
    assert status(post(base + '/prepare', includeOptional=True))['total'] == len(ids)
    old = version()
    previous = client.get(base + '/manifest').json()['clips']
    original = audio(old, 'count-1')
    voice.calls.clear()
    assert post(base + '/clips/unknown/regenerate', expectedPackVersion=old).status_code == 404
    assert post(base + '/regenerate', expectedPackVersion='1' * 16).status_code == 409
    assert post(base + '/regenerate', expectedPackVersion=old, confirmPaid=False).status_code == 422
    assert not voice.calls

    voice.amplitude = 0.1
    result = status(post(alias + '/clips/count-1/regenerate', expectedPackVersion=old))
    assert result['state'] == 'completed' and result['total'] == result['completed'] == 1
    assert voice.calls == [packs.CATALOG['count-1'].text]
    new = version()
    assert new != old and audio(new, 'count-1') != original and audio(old, 'count-1') == original
    entries = client.get(base + '/manifest').json()['clips']
    assert entries['tip-machine-prepare']['tip']['version'] == '1'
    assert all(entries[i] == previous[i] for i in ids if i != 'count-1')
    plan = client.get(base + '/plan').json()
    assert plan['groups']['count'] == {'total': 2, 'generated': 2, 'published': 2, 'playable': 2}
    assert post(base + '/prepare').json() == {'state': 'completed'} and version() == new
    assert post(base + '/regenerate', expectedPackVersion=old).status_code == 409

    voice.fail_on = {packs.CATALOG['set-start'].text}
    result = status(post(base + '/regenerate', expectedPackVersion=new))
    assert result['state'] == 'paused' and 0 < result['completed'] < len(ids)
    assert version() == new and client.get(base + '/manifest').json()['clips'] == entries
    voice.fail_on.clear()
    voice.calls.clear()
    assert status(post(base + '/regenerate', expectedPackVersion=new))['state'] == 'completed'
    assert len(voice.calls) == len(ids) and version() not in {old, new}
    assert audio(old, 'count-1') == original
    assert client.get(base + '/manifest').json()['clips']['safety-stop']['approved'] is False


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