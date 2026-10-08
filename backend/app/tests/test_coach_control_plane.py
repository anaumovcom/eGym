import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachCredential, CoachJob, CoachLedgerRun, CoachPreference
from app.schemas.coach_control import (
    CoachPreferences,
    PartialUsage,
    PreferencesSave,
    Pricing,
    ReportedUsage,
    UsageBounds,
)
from app.schemas.runtime import WorkoutSessionCreateSchema
from app.services.coach import ledger, security
from app.services.coach.jobs import TestJobRunner
from app.services.coach.preferences import load_preferences, save_preferences
from app.services.runtime_service import RuntimeService
from app.tests.test_coach_lifecycle import create_exercise, set_payload

ORIGIN = {"Origin": "http://localhost:5173"}
PRICE = Pricing(version="synthetic-1", model="fake-text", input_rate=100_000, cached_rate=10_000,
                output_rate=500_000, verified=True, enforceable_bounds=True)
BOUNDS = UsageBounds(input_tokens=1000, output_tokens=1000)


def usage(**kwargs):
    return ReportedUsage(input_tokens=100, output_tokens=100, audio_input_tokens=0, audio_output_tokens=0, **kwargs)


@pytest.fixture
def secured(monkeypatch, tmp_path):
    master = tmp_path / "master.key"
    master.write_bytes(Fernet.generate_key())
    master.chmod(0o600)
    operator = tmp_path / "operator.hash"
    operator.write_text(security.password_hash("synthetic-operator-password"))
    operator.chmod(0o600)
    monkeypatch.setenv("COACH_MASTER_KEY_FILE", str(master))
    monkeypatch.setenv("COACH_OPERATOR_HASH_FILE", str(operator))
    get_settings.cache_clear()
    security._login_limits.clear()
    yield master, operator
    get_settings.cache_clear()


def auth(client):
    client.base_url = "http://localhost"
    response = client.post("/api/coach/operator/session", json={"password": "synthetic-operator-password"}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
    return response


def make_run(db, cap="2.00"):
    row, token = ledger.create_run(db, "alexey", "test", cap)
    run_id = row.id
    db.rollback()
    generation = ledger.lease(db, run_id, "tab-a", 0)["generation"]
    return run_id, generation, token


def test_preferences_persist_cas_isolate_and_legacy_off(db_session):
    saved = save_preferences(db_session, "alexey", PreferencesSave(expected_revision=0, settings=CoachPreferences(enabled=True, consent_version=1)))
    assert saved.revision == 1 and load_preferences(db_session, "alexey").enabled
    assert not load_preferences(db_session, "elena").enabled
    with pytest.raises(HTTPException, match="revision_conflict"):
        save_preferences(db_session, "alexey", PreferencesSave(expected_revision=0, settings=CoachPreferences()))
    row = db_session.get(CoachPreference, "alexey")
    row.value = {"schemaVersion": 0, "enabled": True, "mode": "hybrid"}
    db_session.commit()
    migrated = load_preferences(db_session, "alexey")
    assert not migrated.enabled and migrated.network_consent_version is None and migrated.revision == 1


@pytest.mark.parametrize("fields", [{"enabled": True}, {"enabled": True, "consent_version": 1, "mode": "hybrid"}, {"budget_usd": "2.01"}, {"budget_usd": "0"}, {"consent_version": 99, "enabled": True}])
def test_preferences_reject_missing_consent_and_bad_caps(fields):
    with pytest.raises(ValueError):
        CoachPreferences(**fields)


def test_settings_endpoint_and_conflict(client):
    client.base_url = "http://localhost"
    path = "/api/coach/users/alexey/settings"
    current = client.get(path).json()
    assert not current["enabled"]
    saved = client.put(path, json={"expectedRevision": 0, "settings": current}, headers=ORIGIN)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert saved.headers["etag"] == '"1"'
    assert client.put(path, json={"expectedRevision": 0, "settings": current}, headers=ORIGIN).status_code == 409
    assert client.get("/api/coach/users/unknown/settings").status_code == 404


def test_vault_requires_operator_encrypted_and_delete_no_fallback(client, session_factory, secured, monkeypatch):
    client.base_url = "http://localhost"
    assert client.put("/api/coach/credentials", json={"key": "synthetic-secret-key", "expectedVersion": 0}, headers=ORIGIN).status_code == 401
    auth(client)
    saved = client.put("/api/coach/credentials", json={"key": "synthetic-secret-key", "expectedVersion": 0}, headers=ORIGIN)
    assert saved.status_code == 200 and saved.json()["configured"]
    assert "synthetic-secret" not in saved.text
    with session_factory() as db:
        row = db.get(CoachCredential, 1)
        assert "synthetic-secret" not in row.ciphertext
        assert security.read_credential(db) == ("synthetic-secret-key", 1)
    async def check(key):
        assert key == "synthetic-secret-key"
        return "auth_ok_models_not_verified"
    monkeypatch.setattr(security, "metadata_check", check)
    assert client.post("/api/coach/credentials/check", headers=ORIGIN).json()["lastCheckStatus"] == "auth_ok_models_not_verified"
    assert client.put("/api/coach/credentials", json={"key": "other-secret", "expectedVersion": 0}, headers=ORIGIN).status_code == 409
    deleted = client.request("DELETE", "/api/coach/credentials", json={"expectedVersion": 1}, headers=ORIGIN)
    assert not deleted.json()["configured"] and deleted.json()["credentialVersion"] == 2
    assert client.post("/api/coach/credentials/check", headers=ORIGIN).status_code == 409
    assert client.delete("/api/coach/operator/session", headers=ORIGIN).status_code == 200
    assert client.get("/api/coach/credentials").status_code == 401


@pytest.mark.parametrize("case", ["missing", "permissive", "symlink", "repository"])
def test_vault_fails_closed(secured, monkeypatch, case):
    master, _ = secured
    if case == "missing":
        master.unlink()
    if case == "permissive":
        master.chmod(0o644)
    if case == "symlink":
        link = master.parent / "link"
        link.symlink_to(master)
        monkeypatch.setenv("COACH_MASTER_KEY_FILE", str(link))
    if case == "repository":
        monkeypatch.setenv("COACH_MASTER_KEY_FILE", os.path.abspath("pyproject.toml"))
    get_settings.cache_clear()
    with pytest.raises(HTTPException, match="secure_storage_unavailable"):
        security.cipher()


def test_secret_validation_never_echoes_input_and_body_bound(client, secured):
    auth(client)
    secret = "sentinel-SECRET"
    response = client.put("/api/coach/credentials", json={"key": secret, "expectedVersion": secret}, headers=ORIGIN)
    assert response.status_code == 422 and secret not in response.text and "input" not in response.text
    response = client.put("/api/coach/credentials", content="x" * 17000, headers=ORIGIN)
    assert response.status_code == 413


@pytest.mark.parametrize("origin", [None, "http://evil.invalid", "null"])
def test_cross_origin_rejected(client, secured, origin):
    client.base_url = "http://localhost"
    headers = {"Origin": origin} if origin else {}
    assert client.post("/api/coach/operator/session", json={"password": "synthetic-operator-password"}, headers=headers).status_code == 403


def test_lan_http_rejected_and_login_rate_limit(client, secured):
    client.base_url = "http://192.0.2.2"
    assert client.post("/api/coach/operator/session", json={"password": "synthetic-operator-password"}, headers=ORIGIN).status_code == 403
    client.base_url = "http://localhost"
    for _ in range(5):
        assert client.post("/api/coach/operator/session", json={"password": "wrong"}, headers=ORIGIN).status_code == 401
    assert client.post("/api/coach/operator/session", json={"password": "wrong"}, headers=ORIGIN).status_code == 429


def test_reserve_dispatch_settle_dedup_reconciliation(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        attempt = ledger.reserve(db, run_id, "tab-a", generation, "event-1", "text", PRICE, BOUNDS)
        ledger.dispatch(db, attempt, "tab-a", test_only=True)
        ledger.settle(db, attempt, "response-1", usage(cached_input_tokens=50, reasoning_tokens=20), terminal=True)
        ledger.settle(db, attempt, "response-1", usage(), terminal=True)
        first = ledger.snapshot(db, run_id)
        assert first["requests"] == 1 and first["pendingMicros"] == 0
        expected = ledger.cost(PRICE, usage(cached_input_tokens=50, reasoning_tokens=20))
        assert first["settledMicros"] == expected
        db.rollback()
        ledger.settle(db, attempt, "aggregate-1", usage(cached_input_tokens=50, reasoning_tokens=20), terminal=True, basis="aggregate")
        assert ledger.snapshot(db, run_id)["settledMicros"] == expected
        db.rollback()
        with pytest.raises(HTTPException, match="duplicate_attempt"):
            ledger.reserve(db, run_id, "tab-a", generation, "event-1", "text", PRICE, BOUNDS)


def test_daily_usage_counts_only_sent_requests_since_midnight(client, session_factory):
    import time

    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        settled = ledger.reserve(db, run_id, "tab-a", generation, "event-1", "text", PRICE, BOUNDS)
        ledger.dispatch(db, settled, "tab-a", test_only=True)
        ledger.settle(db, settled, "response-1", usage(), terminal=True)
        pending = ledger.reserve(db, run_id, "tab-a", generation, "event-2", "voice", PRICE, BOUNDS)
        ledger.dispatch(db, pending, "tab-a", test_only=True)
        ledger.mark_unsettled(db, pending)
        never_sent = ledger.reserve(db, run_id, "tab-a", generation, "event-3", "text", PRICE, BOUNDS)
        ledger.cancel_reserved(db, never_sent)
        old = ledger.reserve(db, run_id, "tab-a", generation, "event-4", "text", PRICE, BOUNDS)
        ledger.dispatch(db, old, "tab-a", test_only=True)
        ledger.settle(db, old, "response-4", usage(), terminal=True)
        db.get(CoachAttempt, old).sent_at = time.time() - 86_400
        db.commit()
        value = ledger.daily_usage(db, time.time() - 3600)
    one = ledger.cost(PRICE, usage())
    reserve = ledger.cost(PRICE, ReportedUsage(**BOUNDS.model_dump(exclude={"schema_version"})))
    assert value["requests"] == 2
    assert value["settledMicros"] == one and value["pendingMicros"] == reserve and value["totalMicros"] == one + reserve
    client.base_url = "http://localhost"
    response = client.get("/api/coach/usage/today", params={"since": time.time() - 3600})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["requests"] == 2
    assert client.get("/api/coach/usage/today").json()["requests"] >= 2
    for since in (time.time() - 3 * 86_400, time.time() + 3600, "nan"):
        assert client.get("/api/coach/usage/today", params={"since": since}).status_code == 422


def test_cancel_sent_unknown_usage_remains_reserved_after_restart(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        attempt = ledger.reserve(db, run_id, "tab-a", generation, "event", "voice", PRICE, BOUNDS)
        ledger.dispatch(db, attempt, "tab-a", test_only=True)
        ledger.cancel_run(db, run_id)
    with session_factory() as db:
        value = ledger.snapshot(db, run_id)
        assert value["requests"] == 1 and value["pendingMicros"] > 0
        assert value["attempts"][0]["usage"] is None and value["attempts"][0]["costMicros"] is None
        db.rollback()
        ledger.settle(db, attempt, "missing", None, terminal=True, complete=False)
        assert ledger.snapshot(db, run_id)["pendingMicros"] > 0


def test_owner_lease_stale_cancel_and_settings_generation(db_session):
    run_id, generation, _ = make_run(db_session)
    with pytest.raises(HTTPException, match="owner_mismatch"):
        ledger.lease(db_session, run_id, "tab-b", generation)
    attempt = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    save_preferences(db_session, "alexey", PreferencesSave(expected_revision=0, settings=CoachPreferences()))
    with pytest.raises(HTTPException, match="stale_attempt"):
        ledger.dispatch(db_session, attempt, "tab-a", test_only=True)
    ledger.cancel_run(db_session, run_id)
    assert ledger.snapshot(db_session, run_id)["pendingMicros"] == 0


def test_production_dispatch_and_unverified_price_fail_closed(db_session):
    run_id, generation, _ = make_run(db_session)
    with pytest.raises(HTTPException, match="strict_cap_unprovable"):
        ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE.model_copy(update={"verified": False}), BOUNDS)
    attempt = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    with pytest.raises(HTTPException, match="paid_adapter_unavailable"):
        ledger.dispatch(db_session, attempt, "tab-a")


def test_budget_retry_lower_cap_and_singleflight(db_session):
    run_id, generation, _ = make_run(db_session, "0.000700")
    attempt = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    with pytest.raises(HTTPException, match="pipeline_busy"):
        ledger.reserve(db_session, run_id, "tab-a", generation, "event-2", "text", PRICE, BOUNDS)
    ledger.dispatch(db_session, attempt, "tab-a", test_only=True)
    ledger.mark_unsettled(db_session, attempt)
    with pytest.raises(HTTPException, match="budget"):
        ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS, retry=1)
    ledger.change_cap(db_session, run_id, "0.000001")
    assert ledger.snapshot(db_session, run_id)["availableMicros"] == 0
    db_session.rollback()
    with pytest.raises(HTTPException, match="operator_confirmation_required"):
        ledger.change_cap(db_session, run_id, "0.001")


def test_independent_connections_reserve_at_most_once(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
    def worker():
        with session_factory() as db:
            try:
                ledger.reserve(db, run_id, "tab-a", generation, "same-event", "text", PRICE, BOUNDS)
                return True
            except HTTPException:
                return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(lambda _: worker(), range(2))) == 1


def test_operator_quota_and_overflow_block(db_session, monkeypatch):
    run_id, generation, _ = make_run(db_session)
    monkeypatch.setenv("COACH_OPERATOR_DAILY_USD", "0.000001")
    get_settings.cache_clear()
    with pytest.raises(HTTPException, match="operator_budget"):
        ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    monkeypatch.setenv("COACH_OPERATOR_DAILY_USD", "10")
    get_settings.cache_clear()
    attempt = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    ledger.dispatch(db_session, attempt, "tab-a", test_only=True)
    huge = ReportedUsage(input_tokens=10000, output_tokens=10000, audio_input_tokens=0, audio_output_tokens=0)
    ledger.settle(db_session, attempt, "overflow", huge, terminal=True)
    assert ledger.snapshot(db_session, run_id)["state"] == "blocked"


def test_recovery_does_not_refund_sent_and_reacquires_owner(db_session):
    run_id, generation, _ = make_run(db_session)
    attempt = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    ledger.dispatch(db_session, attempt, "tab-a", test_only=True)
    row = db_session.get(CoachLedgerRun, run_id)
    row.lease_until = 0
    db_session.commit()
    ledger.recover(db_session, run_id)
    value = ledger.snapshot(db_session, run_id)
    assert value["requests"] == 1 and value["pendingMicros"] > 0
    db_session.rollback()
    assert ledger.lease(db_session, run_id, "tab-b", value["generation"])["generation"] > generation


def test_run_api_token_and_no_credentials_or_inference(client, secured):
    auth(client)
    response = client.post("/api/coach/runs", json={"userId": "alexey", "ledger": "test"}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    run = response.json()
    assert client.get(f'/api/coach/runs/{run["runId"]}/usage').status_code == 404
    headers = {**ORIGIN, "X-Coach-Run-Token": run["runToken"]}
    saved = client.get(f'/api/coach/runs/{run["runId"]}/usage', headers=headers)
    assert saved.status_code == 200 and "runToken" not in saved.json()
    assert client.post(f'/api/coach/runs/{run["runId"]}/lease', headers=headers, json={"ownerId": "a", "expectedGeneration": 0}).status_code == 200
    assert client.post("/api/coach/generate", headers=headers).status_code == 404


@pytest.mark.asyncio
async def test_job_idempotency_complete_resume_no_repeat(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        job_id = ledger.submit_job(db, run_id, "job-key", "a" * 64, ["one", "two"])
        assert ledger.submit_job(db, run_id, "job-key", "a" * 64, ["one", "two"]) == job_id
        ledger.job_state(db, job_id, "queued")
    class Fake:
        test_only = True
        calls = 0
        async def generate(self, item, bounds):
            self.calls += 1
            return usage()
    provider = Fake()
    runner = TestJobRunner(session_factory)
    await runner.run(job_id, "tab-a", generation, provider, PRICE, BOUNDS)
    await runner.run(job_id, "tab-a", generation, provider, PRICE, BOUNDS)
    assert provider.calls == 2
    with session_factory() as db:
        assert db.get(CoachJob, job_id).state == "completed"
        assert db.scalar(select(func.count()).select_from(CoachAttempt)) == 2


@pytest.mark.asyncio
async def test_job_timeout_preserves_unsettled_and_prevents_blind_regeneration(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        job_id = ledger.submit_job(db, run_id, "key", "b" * 64, ["one"])
        ledger.job_state(db, job_id, "queued")
    class Stalled:
        test_only = True
        calls = 0
        async def generate(self, item, bounds):
            self.calls += 1
            await asyncio.Event().wait()
    provider = Stalled()
    runner = TestJobRunner(session_factory, timeout=0.01)
    with pytest.raises(TimeoutError):
        await runner.run(job_id, "tab-a", generation, provider, PRICE, BOUNDS)
    with session_factory() as db:
        assert ledger.snapshot(db, run_id)["pendingMicros"] > 0
        db.rollback()
        ledger.job_state(db, job_id, "queued")
    with pytest.raises(HTTPException, match="duplicate_attempt"):
        await runner.run(job_id, "tab-a", generation, provider, PRICE, BOUNDS)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_cancel_job_releases_transaction_before_await(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        job_id = ledger.submit_job(db, run_id, "key", "c" * 64, ["one"])
        ledger.job_state(db, job_id, "queued")
    started = asyncio.Event()
    class Stalled:
        test_only = True
        async def generate(self, item, bounds):
            started.set()
            await asyncio.Event().wait()
    runner = TestJobRunner(session_factory)
    task = asyncio.create_task(runner.run(job_id, "tab-a", generation, Stalled(), PRICE, BOUNDS))
    await started.wait()
    await asyncio.wait_for(runner.cancel(job_id), 1)
    assert task.cancelled() and not runner.tasks
    with session_factory() as db:
        assert ledger.snapshot(db, run_id)["pendingMicros"] > 0


def test_binding_workout_and_receipt_alias_preserve_ledger(db_session):
    service = RuntimeService()
    summary = service.save_workout_session(db_session, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Synthetic", started_at=datetime.now(UTC), status="in_progress"))
    exercise_id = create_exercise(service, db_session)
    saved = service.save_set_result(db_session, set_payload(exercise_id))
    row, _ = ledger.create_run(db_session, "alexey", "workout", "2.00")
    run_id = row.id
    db_session.rollback()
    ledger.bind_workout(db_session, run_id, summary.workout_session_id)
    assert ledger.snapshot(db_session, run_id)["workoutSessionId"] == summary.workout_session_id
    db_session.rollback()
    from app.models.coach import CoachReceipt
    db_session.add(CoachReceipt(id="synthetic-receipt", run_id=run_id, canonical=security.digest("set-1")))
    db_session.commit()
    ledger.alias_receipt(db_session, run_id, "set-1", saved.set_id)
    ledger.alias_receipt(db_session, run_id, "set-1", saved.set_id)
    assert db_session.get(CoachReceipt, "synthetic-receipt").backend_set_id == saved.set_id


def test_credential_rotation_invalidates_reserved_attempt(client, session_factory, secured):
    auth(client)
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        attempt = ledger.reserve(db, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    response = client.put("/api/coach/credentials", json={"key": "synthetic-new-key", "expectedVersion": 0}, headers=ORIGIN)
    assert response.status_code == 200
    with session_factory() as db:
        with pytest.raises(HTTPException, match="stale_attempt"):
            ledger.dispatch(db, attempt, "tab-a", test_only=True)


def test_jobs_api_no_dispatch_and_idempotency(client, secured):
    auth(client)
    run = client.post("/api/coach/runs", json={"userId": "alexey", "ledger": "test"}, headers=ORIGIN).json()
    headers = {**ORIGIN, "X-Coach-Run-Token": run["runToken"]}
    path = f'/api/coach/runs/{run["runId"]}/jobs'
    body = {"idempotencyKey": "plan-1", "fingerprint": "a" * 64, "items": ["clip-1"]}
    job = client.post(path, json=body, headers=headers)
    assert job.status_code == 200 and job.json()["dispatchAvailable"] is False
    assert client.post(path, json=body, headers=headers).json() == job.json()
    status = client.get(f'{path}/{job.json()["jobId"]}', headers=headers)
    assert status.json()["state"] == "paused"
    assert client.post(f'{path}/{job.json()["jobId"]}/action', json={"action": "resume"}, headers=headers).status_code == 200
    assert client.get(f'{path}/{job.json()["jobId"]}', headers=headers).json()["state"] == "queued"


def test_migration_roundtrip_only_temporary_db(tmp_path):
    from sqlalchemy import create_engine, inspect

    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert "coach_attempts" in inspect(engine).get_table_names()
    command.downgrade(config, "20260928_0006")
    assert "coach_attempts" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "coach_preferences" in inspect(engine).get_table_names()
    engine.dispose()


def test_partial_usage_keeps_unknown_and_enriches_same_response_after_restart(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        attempt = ledger.reserve(db, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
        ledger.dispatch(db, attempt, "tab-a", test_only=True)
        ledger.settle(db, attempt, "response", PartialUsage(input_tokens=100), terminal=False, complete=False)
        data = ledger.snapshot(db, run_id)
        assert data["attempts"][0]["usage"]["output_tokens"] is None
        assert data["attempts"][0]["completeness"] == "partial"
        assert data["pendingMicros"] > 0
    with session_factory() as db:
        ledger.settle(db, attempt, "response", usage(), terminal=True)
        data = ledger.snapshot(db, run_id)
        assert data["requests"] == 1 and data["pendingMicros"] == 0
        assert data["attempts"][0]["completeness"] == "complete"


def test_spoofed_forwarded_transport_rejected(client, secured):
    client.base_url = "http://localhost"
    assert client.post("/api/coach/operator/session", json={"password": "synthetic-operator-password"},
                       headers={**ORIGIN, "X-Forwarded-Proto": "https"}).status_code == 403


@pytest.mark.asyncio
async def test_job_circuit_survives_runner_restart(session_factory):
    with session_factory() as db:
        run_id, generation, _ = make_run(db)
        job_id = ledger.submit_job(db, run_id, "key", "d" * 64, ["one"])
        job = db.get(CoachJob, job_id)
        job.failures = 3
        job.state = "queued"
        db.commit()
    class Fake:
        test_only = True
        async def generate(self, item, bounds):
            raise AssertionError("Circuit must not call provider")
    runner = TestJobRunner(session_factory)
    with pytest.raises(HTTPException, match="provider_circuit"):
        await runner.run(job_id, "tab-a", generation, Fake(), PRICE, BOUNDS)


def test_retry_at_most_once_and_model_switch_never_resets_usage(db_session):
    run_id, generation, _ = make_run(db_session)
    first = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    ledger.dispatch(db_session, first, "tab-a", test_only=True)
    ledger.mark_unsettled(db_session, first)
    second = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE.model_copy(update={"model": "fake-second"}), BOUNDS, retry=1)
    ledger.dispatch(db_session, second, "tab-a", test_only=True)
    ledger.settle(db_session, second, "response", usage(), terminal=True)
    data = ledger.snapshot(db_session, run_id)
    assert data["requests"] == 2 and data["pendingMicros"] > 0 and data["settledMicros"] > 0
    assert {a["model"] for a in data["attempts"]} == {"fake-text", "fake-second"}
    db_session.rollback()
    with pytest.raises(HTTPException, match="invalid_attempt"):
        ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS, retry=2)


def test_terminal_ack_enriches_existing_complete_usage_without_double_charge(db_session):
    run_id, generation, _ = make_run(db_session)
    attempt = ledger.reserve(db_session, run_id, "tab-a", generation, "event", "text", PRICE, BOUNDS)
    ledger.dispatch(db_session, attempt, "tab-a", test_only=True)
    ledger.settle(db_session, attempt, "response", usage(), terminal=False)
    assert ledger.snapshot(db_session, run_id)["pendingMicros"] > 0
    db_session.rollback()
    ledger.settle(db_session, attempt, "response", usage(), terminal=True)
    value = ledger.snapshot(db_session, run_id)
    assert value["pendingMicros"] == 0 and value["settledMicros"] == ledger.cost(PRICE, usage())