"""No-network regressions for paid checkpoints and additive catalogs."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from app.services.achievements import content
from app.services.achievements.generation import BudgetLedger, durable_bytes, durable_json
from app.services.achievements.rules import RULES
from scripts import generate_achievement_media as media_generator


def test_replace_sharing_violation_retries_locally(tmp_path, monkeypatch):
    import os

    original = os.replace
    calls = []

    def replace(source, target):
        calls.append(str(source))
        if len(calls) < 3:
            raise PermissionError('synthetic sharing violation')
        original(source, target)

    monkeypatch.setattr(os, 'replace', replace)
    path = tmp_path / 'ledger.json'
    durable_json(path, {'saved': True})
    assert json.loads(path.read_text()) == {'saved': True}
    assert len(calls) == 3
    assert not list(tmp_path.glob('*.tmp'))


def test_reconcile_preserves_editorial_but_not_stale_rules():
    before = content.empty_catalog()
    before['lines'] = before['lines'][:120]
    tier = before['lines'][0]['tiers'][0]
    tier.update(title='Paid title', contentOrigin='gpt-6.1-sol', phrase='Paid phrase')
    saved = deepcopy(tier)
    before['lines'][0]['description'] = 'obsolete condition'
    tier['threshold'] = -1
    after = content.reconcile_catalog(before)
    assert len(after['lines']) == len(RULES)
    assert after['lines'][0]['description'] == RULES[0]['description']
    restored = after['lines'][0]['tiers'][0]
    assert restored['threshold'] == RULES[0]['thresholds'][0]
    assert all(restored[key] == saved[key] for key in ('title', 'phrase', 'contentOrigin'))
    assert before['lines'][0]['description'] == 'obsolete condition'


def test_every_rule_requires_real_multiday_evidence():
    assert all(rule['minimumEvidenceDays'][0] >= 12 for rule in RULES)
    assert all(len(rule['minimumEvidenceDays']) == len(rule['thresholds']) for rule in RULES)


def test_audio_bytes_and_receipt_survive_settlement_failure(tmp_path, monkeypatch):
    ledger = BudgetLedger(tmp_path / 'ledger.json')
    monkeypatch.setattr(media_generator, 'AUDIO_ROOT', tmp_path / 'audio')
    monkeypatch.setattr(media_generator, 'valid_audio', lambda path: path.is_file())
    monkeypatch.setattr(media_generator, 'finalize_streaming_wav', lambda data: data)
    check = type('Check', (), {'duration_ms': 1000, 'rms_dbfs': -12, 'peak_dbfs': -1, 'sample_rate': 24000})()
    monkeypatch.setattr(media_generator, 'verify_wav', lambda data: check)
    published = []
    monkeypatch.setattr(media_generator, 'save_asset', lambda *args, **kwargs: published.append(args))
    monkeypatch.setattr(media_generator, 'load_manifest', lambda: {'assets': {}})
    real_settle = ledger.settle
    monkeypatch.setattr(ledger, 'settle', lambda *a, **kw: (_ for _ in ()).throw(PermissionError('checkpoint fail')))
    calls = []

    def dispatch(request):
        calls.append(request)
        return httpx.Response(200, content=b'synthetic audio', headers={'x-request-id': 'receipt-1'})

    tier = {'id': 'practice.workouts:t1', 'fishMarkup': '[warm] Test phrase'}

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(dispatch)) as client:
            with pytest.raises(PermissionError):
                await media_generator.generate_audio(client, ledger, tier, 'test', 'voice')
            assert (tmp_path / 'audio/practice-workouts-t1.wav').read_bytes() == b'synthetic audio'
            receipt = json.loads((tmp_path / 'audio/receipts/practice-workouts-t1.json').read_text())
            assert receipt['requestId'] == 'receipt-1'
            monkeypatch.setattr(ledger, 'settle', real_settle)
            await media_generator.generate_audio(client, ledger, tier, 'test', 'voice')

    asyncio.run(run())
    assert len(calls) == 1
    assert ledger.attempts()[0]['status'] == 'settled'
    assert published


def test_unique_temp_does_not_consume_old_crash_file(tmp_path):
    stale = tmp_path / 'ledger.tmp'
    stale.write_bytes(b'old crash evidence')
    durable_bytes(tmp_path / 'ledger.json', b'new')
    assert stale.read_bytes() == b'old crash evidence'


def test_permanent_sharing_violation_keeps_fsynced_recovery_bytes(tmp_path, monkeypatch):
    import os

    def blocked(*args):
        raise PermissionError('synthetic permanent lock')

    monkeypatch.setattr(os, 'replace', blocked)
    with pytest.raises(PermissionError):
        durable_bytes(tmp_path / 'paid-response.json', b'paid response must survive')
    leftovers = list(tmp_path.glob('paid-response.json.*.tmp'))
    assert len(leftovers) == 1
    assert leftovers[0].read_bytes() == b'paid response must survive'


def test_audio_manifest_requires_checksum_and_not_just_a_filename(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setattr(media_generator, 'AUDIO_ROOT', tmp_path)
    monkeypatch.setattr(media_generator, 'valid_audio', lambda path: path.is_file())
    path = tmp_path / 'paid.wav'
    path.write_bytes(b'paid audio')
    asset = {'audio': {'file': path.name}, 'audioMetadata': {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
    assert media_generator.current_audio(asset)
    path.write_bytes(b'corrupted')
    assert not media_generator.current_audio(asset)
    assert not media_generator.current_audio({'audio': {'file': path.name}})
    assert not media_generator.current_audio({'audio': {'file': '../paid.wav'}})


def test_unknown_text_outcomes_block_line_ids_across_content_version_changes(tmp_path):
    from scripts.generate_achievement_content import restore_batches

    ledger = BudgetLedger(tmp_path / 'ledger.json')
    pairs = [('start.first_set', 'start.first_workout'),
             ('repertoire.exploration', 'repertoire.familiar_days')]
    for pair in pairs:
        key = 'text:older-content-version:v2:' + ':'.join(pair)
        ledger.reserve(key, 'openai', 'text', 'gpt-6.1-sol', 500_000)
        ledger.sent(key)
    blocked = restore_batches(content.empty_catalog(), ledger)
    assert blocked == {line_id for pair in pairs for line_id in pair}
    assert ledger.committed('openai') == 1_000_000
    assert all(row['status'] == 'sent' for row in ledger.attempts())


def test_audit_cannot_claim_completion_when_catalog_validation_fails(tmp_path, monkeypatch):
    from scripts import audit_achievement_generation as auditor

    ledger = BudgetLedger(tmp_path / 'achievement_generation' / 'ledger.json')
    monkeypatch.setattr(auditor, 'BudgetLedger', lambda: ledger)
    monkeypatch.setattr(auditor, 'IMAGE_ROOT', tmp_path / 'media' / 'achievements' / 'v2' / 'images')
    monkeypatch.setattr(auditor, 'load_catalog', lambda: {'lines': []})
    monkeypatch.setattr(auditor, 'load_manifest', lambda: {'assets': {}})
    monkeypatch.setattr(auditor, 'validate_catalog', lambda *args, **kwargs: ['invalid deterministic rule'])
    report = auditor.audit()
    assert report['missingImages'] == report['missingAudio'] == report['missingText'] == []
    assert report['complete'] is False


def test_settled_legacy_response_recovers_missing_line_without_repurchase(tmp_path):
    from scripts.generate_achievement_content import restore_batches

    catalog = content.empty_catalog()
    generated = deepcopy(catalog['lines'][0])
    for tier in generated['tiers']:
        phrase = f"Ты сохранил новую главу своей практики: {tier['id']}."
        tier.update(title=f"Глава {tier['tier']}", phrase=phrase, audioText=phrase,
                    fishMarkup=f"[warm] {phrase}", imagePrompt='Unique scene ' + 'x' * 130)
    response = {'id': 'resp-settled', 'model': 'gpt-6.1-sol', 'usage': {}, 'output': [
        {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'lines': [generated]})}]},
    ]}
    response_path = tmp_path / 'achievement_generation' / 'responses' / 'paid.json'
    response_path.parent.mkdir(parents=True)
    response_path.write_text(json.dumps(response), encoding='utf-8')
    ledger = BudgetLedger(tmp_path / 'achievement_generation' / 'ledger.json')
    ledger.reserve('text:old:v2:start.first_set', 'openai', 'text', 'gpt-6.1-sol', 1000)
    ledger.sent('text:old:v2:start.first_set')
    ledger.settle('text:old:v2:start.first_set', 1000, request_id='resp-settled')
    unresolved = 'text:achievements-content-1.1.0:v2:start.first_set:start.first_workout'
    ledger.reserve(unresolved, 'openai', 'text', 'gpt-6.1-sol', 2000)
    ledger.sent(unresolved)
    committed = ledger.committed('openai')

    blocked = restore_batches(catalog, ledger)

    assert blocked == {'start.first_workout'}
    assert all(tier['contentOrigin'] == 'gpt-6.1-sol' for tier in catalog['lines'][0]['tiers'])
    assert ledger.find(unresolved)['status'] == 'sent'
    assert ledger.committed('openai') == committed


def test_audio_speed_uses_separate_attempt_and_complete_prosody(tmp_path, monkeypatch):
    ledger = BudgetLedger(tmp_path / 'ledger.json')
    monkeypatch.setattr(media_generator, 'AUDIO_ROOT', tmp_path / 'audio')
    monkeypatch.setattr(media_generator, 'valid_audio', lambda path: path.is_file())
    monkeypatch.setattr(media_generator, 'finalize_streaming_wav', lambda data: data)
    check = type('Check', (), {'duration_ms': 17_876, 'rms_dbfs': -12, 'peak_dbfs': -1, 'sample_rate': 24000})()
    monkeypatch.setattr(media_generator, 'verify_wav', lambda data: check)
    monkeypatch.setattr(media_generator, 'save_asset', lambda *args, **kwargs: None)
    monkeypatch.setattr(media_generator, 'load_manifest', lambda: {'assets': {}})
    requests = []

    def dispatch(request):
        requests.append(request)
        return httpx.Response(200, content=b'complete speech')

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(dispatch)) as client:
            await media_generator.generate_audio(
                client, ledger, {'id': 'muscle.front-shoulders:t4', 'fishMarkup': '[warm] Full phrase'},
                'test', 'voice', 'speed-1.15', 1.15,
            )

    asyncio.run(run())
    assert len(requests) == 1
    assert json.loads(requests[0].content)['prosody']['speed'] == 1.15
    assert ledger.attempts()[0]['key'].endswith(':speed-1.15')
    receipt = json.loads((tmp_path / 'audio/receipts/muscle-front-shoulders-t4.speed-1.15.json').read_text())
    assert receipt['speed'] == 1.15