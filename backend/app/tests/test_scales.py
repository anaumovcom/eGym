import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models.profile import BodyMeasurement, UserProfile
from app.models.scale import ScaleReading
from app.models.user import User
from app.repositories.scale_repository import ScaleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.scale import ScaleActivity, ScaleSettings
from app.services.scale_protocol import SERVICE_UUID, decode_service_data
from app.services.scale_service import ScaleService
from app.tests.test_scale_protocol import packet

DEVICE = "AA:BB:CC:DD:EE:FF"


def advertise(service, data, device_id=DEVICE):
    service.on_advertisement(
        SimpleNamespace(address=device_id, name="MIBCS"),
        SimpleNamespace(service_data={SERVICE_UUID: data}, local_name="MIBCS", rssi=-51),
    )


async def drain(service):
    # Synchronization via the same lock used by consumption, not wall-clock sleeps.
    for _ in range(100):
        await asyncio.sleep(0)
        async with service._lock:
            if service._queue.empty():
                return
    raise AssertionError("Measurement queue did not drain")


def test_repository_persists_history_and_profile(session_factory):
    repo = ScaleRepository()
    now = datetime.now(UTC)
    with session_factory() as db:
        first = repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet()), now)
        assert first.weight_kg == 70
        assert db.get(UserProfile, "alexey").weight_kg == 70
        assert repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet()), now + timedelta(days=1)) is None
        assert repo.save_measurement(db, "elena", DEVICE, decode_service_data(packet(year=0)), now + timedelta(seconds=20)) is None
        repo.configure(db, ScaleSettings(enabled=True, device_id=DEVICE))
    with session_factory() as db:
        assert repo.latest(db, "alexey").id == first.id
        assert repo.history(db, "alexey", 7)[0].weight_kg == 70
        assert repo.history(db, "elena", 7) == []
        assert repo.settings(db).device_id == DEVICE
        assert repo.settings(db).enabled


def test_history_period_and_validation(session_factory):
    repo = ScaleRepository()
    with session_factory() as db:
        result = repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet()), datetime.now(UTC) - timedelta(days=20))
        assert repo.history(db, "alexey", 7) == []
        assert repo.history(db, "alexey", 30)[0].id == result.id
        assert repo.latest(db, "alexey").id == result.id
        assert repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet(flags=0)), datetime.now(UTC)) is None
        repo.configure(db, ScaleSettings(enabled=True, device_id=DEVICE))
        assert repo.settings(db).device_id == DEVICE


@pytest.mark.asyncio
async def test_replay_one_occupancy_and_late_impedance(session_factory):
    service = ScaleService(session_factory)
    # Consumer only: no Bluetooth or machine runtime needed.
    service.status.enabled = True
    service.status.device_id = DEVICE
    with session_factory() as db:
        UserRepository().set_current_user(db, "alexey")
        db.commit()
    consumer = asyncio.create_task(service._consume())
    try:
        records = json.loads((Path(__file__).parent / "fixtures/scale_advertisements.json").read_text())
        for record in records:
            advertise(service, bytes.fromhex(record["serviceDataHex"]))
            await drain(service)
        with session_factory() as db:
            assert db.scalar(select(func.count()).select_from(ScaleReading)) == 1
            latest = service.repository.latest(db, "alexey")
            assert latest.weight_kg == 70
            assert latest.impedance_ohm == 510
        assert service.status.last_measurement.impedance_ohm == 510
        assert not service.snapshot().measuring
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)


@pytest.mark.asyncio
async def test_wrong_device_and_disabled_and_restart(session_factory):
    service = ScaleService(session_factory)
    await service.configure(ScaleSettings(enabled=True, device_id=DEVICE))
    advertise(service, packet(), "11:22:33:44:55:66")
    assert service._queue.empty()
    assert len(service.snapshot().devices) == 1
    advertise(service, packet())
    await service.configure(ScaleSettings(enabled=False, device_id=DEVICE))
    consumer = asyncio.create_task(service._consume())
    try:
        await drain(service)
        with session_factory() as db:
            assert db.scalar(select(func.count()).select_from(ScaleReading)) == 0
        advertise(service, packet())
        assert service._queue.empty()
        restarted = ScaleService(session_factory)
        await restarted.start()
        assert restarted.status.device_id == DEVICE
        assert not restarted.status.enabled
        await restarted.close()
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)


@pytest.mark.asyncio
async def test_bluetooth_power_off_and_recovery(session_factory):
    attempted = asyncio.Queue()
    release = asyncio.Event()
    attempts = 0

    class Scanner:
        async def start(self):
            nonlocal attempts
            attempts += 1
            attempted.put_nowait(attempts)
            if attempts == 2:
                raise RuntimeError("org.bluez.Error.NotReady")
            if attempts == 3:
                await release.wait()

        async def stop(self):
            pass

    service = ScaleService(session_factory, scanner_factory=lambda callback, mode: Scanner(), retry_seconds=0)
    service.status.enabled = True
    task = asyncio.create_task(service._run())
    try:
        await asyncio.wait_for(attempted.get(), 2)
        # Trigger a health refresh as if the 15-second registration elapsed.
        for _ in range(100):
            await asyncio.sleep(0)
            if service.status.scanning:
                break
        assert service.status.scanning and service.status.bluetooth_available
        service._wake.set()
        assert await asyncio.wait_for(attempted.get(), 2) == 2
        assert await asyncio.wait_for(attempted.get(), 2) == 3
        assert not service.status.scanning
        assert not service.status.bluetooth_available
        assert service.status.error
        release.set()
        for _ in range(100):
            await asyncio.sleep(0)
            if service.status.scanning:
                break
        assert service.status.scanning and service.status.bluetooth_available
        assert service.status.error is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_passive_unsupported_fallback_and_bounded_queue(session_factory):
    modes = []

    class Scanner:
        def __init__(self, mode):
            self.mode = mode

        async def start(self):
            modes.append(self.mode)
            if self.mode == "passive":
                raise NotImplementedError("passive")

        async def stop(self):
            pass

    service = ScaleService(session_factory, scanner_factory=lambda callback, mode: Scanner(mode))
    service.status.enabled = True
    service.status.device_id = DEVICE
    task = asyncio.create_task(service._run())
    try:
        for _ in range(100):
            await asyncio.sleep(0)
            if service.status.scanning:
                break
        assert service.status.scanning_mode == "active"
        assert service.status.warning
        assert modes == ["passive", "active"]
        for _ in range(200):
            advertise(service, packet())
        assert service._queue.qsize() == 64
        queue = service.subscribe()
        for _ in range(100):
            service._publish()
        assert queue.qsize() == 1
        service.unsubscribe(queue)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_api_settings_history_and_websocket(client):
    assert client.get("/api/scales/status").json()["enabled"] is True
    assert client.put("/api/scales/settings", json={"enabled": False, "deviceId": DEVICE, "userId": "alexey"}).status_code == 400
    response = client.put("/api/scales/settings", json={"enabled": False, "userId": "alexey"})
    assert response.status_code == 200
    assert "userId" not in response.json()
    assert client.get("/api/scales/measurements?userId=alexey&days=7").json() == {"measurements": []}
    assert client.get("/api/scales/measurements/latest?userId=alexey").json() is None
    assert client.get("/api/scales/measurements?userId=alexey&days=0").status_code == 422
    with client.websocket_connect("/api/scales/realtime") as socket:
        state = socket.receive_json()
        assert state["scanning"] is False
        assert "userId" not in state


def test_atomic_history_update(session_factory):
    repo = ScaleRepository()
    with session_factory() as db:
        before = db.scalar(select(func.count()).select_from(BodyMeasurement))
        for _ in range(100):
            repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet()), datetime.now(UTC))
        assert db.scalar(select(func.count()).select_from(BodyMeasurement)) == before + 1
        assert db.scalar(select(func.count()).select_from(ScaleReading)) == 1


def test_shared_scales_follow_current_user(session_factory):
    repo = ScaleRepository()
    users = UserRepository()
    with session_factory() as db:
        users.set_current_user(db, "alexey")
        db.commit()
        first = repo.save_current_measurement(db, DEVICE, decode_service_data(packet()), datetime.now(UTC))
        users.set_current_user(db, "elena")
        db.commit()
        second = repo.save_current_measurement(db, DEVICE, decode_service_data(packet(raw=12000)), datetime.now(UTC))
        assert first.user_id == "alexey"
        assert second.user_id == "elena"
        db.query(User).update({User.is_current: False})
        db.commit()
        with pytest.raises(ValueError, match="активного"):
            repo.save_current_measurement(db, DEVICE, decode_service_data(packet()), datetime.now(UTC))


def test_delete_restores_profile_and_blocks_replayed_deleted_packet(session_factory):
    repo = ScaleRepository()
    with session_factory() as db:
        first = repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet(raw=13000)), datetime.now(UTC))
        second = repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet()), datetime.now(UTC))
        with pytest.raises(LookupError):
            repo.delete_measurement(db, second.id, "elena")
        repo.delete_measurement(db, second.id, "alexey")
        assert db.get(BodyMeasurement, second.id) is None
        assert db.get(ScaleReading, second.id) is None
        assert db.get(UserProfile, "alexey").weight_kg == 65
        assert repo.latest(db, "alexey").id == first.id
        assert repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet()), datetime.now(UTC)) is None
        assert repo.save_measurement(db, "alexey", DEVICE, decode_service_data(packet(year=0)), datetime.now(UTC)) is None


def test_delete_api_confirmation_scope_and_status(client):
    service = client.app.state.scale_service
    with service.sessions() as db:
        measurement = service.repository.save_measurement(db, "alexey", DEVICE, decode_service_data(packet()), datetime.now(UTC))
    path = f"/api/scales/measurements/{measurement.id}"
    assert client.delete(path + "?userId=alexey").status_code == 400
    assert client.delete(path + "?userId=elena&confirm=true").status_code == 404
    assert client.delete(path + "?userId=alexey&confirm=true").status_code == 204
    assert client.get("/api/scales/measurements/latest?userId=alexey").json() is None


@pytest.mark.asyncio
async def test_auto_pause_stops_scanner_and_resumes_without_changing_settings(session_factory):
    started = asyncio.Queue()
    stopped = asyncio.Queue()

    class Scanner:
        async def start(self):
            started.put_nowait(True)

        async def stop(self):
            stopped.put_nowait(True)

    service = ScaleService(session_factory, scanner_factory=lambda callback, mode: Scanner())
    task = asyncio.create_task(service._run())
    try:
        await asyncio.wait_for(started.get(), 2)
        service.update_activity(ScaleActivity(client_id="screen", sequence=1, phase="setup"))
        await asyncio.wait_for(stopped.get(), 2)
        for _ in range(20):
            await asyncio.sleep(0)
        assert service.status.enabled and service.status.paused
        assert not service.status.scanning
        service.status.device_id = DEVICE
        advertise(service, packet())
        assert service._queue.empty()
        # An older response must not release a newer exercise lease.
        service.update_activity(ScaleActivity(client_id="screen", sequence=0, phase="idle"))
        assert service.status.paused
        service.update_activity(ScaleActivity(client_id="screen", sequence=2, phase="exercise"))
        assert service.status.pause_reason == "Выполняется упражнение"
        service.update_activity(ScaleActivity(client_id="screen", sequence=3, phase="idle"))
        await asyncio.wait_for(started.get(), 2)
        assert not service.status.paused and service.status.enabled
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_activity_lease_multiple_clients_and_hardware_guard(session_factory, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.services.scale_service.monotonic", lambda: now[0])
    service = ScaleService(session_factory)
    service.update_activity(ScaleActivity(client_id="one", sequence=1, phase="setup"))
    service.update_activity(ScaleActivity(client_id="two", sequence=1, phase="idle"))
    assert service.status.paused
    now[0] += 21
    service._refresh_pause()
    assert not service.status.paused
    service._hardware_pause = "Калибровка тренажёра"
    service._refresh_pause()
    assert service.status.paused
    service._hardware_pause = None
    service._refresh_pause()
    assert not service.status.paused


def test_activity_api_does_not_persist_disable(client):
    state = client.put("/api/scales/activity", json={"clientId": "test", "sequence": 1, "phase": "setup"}).json()
    assert state["enabled"] and state["paused"]
    assert "Настройка" in state["pauseReason"]
    state = client.put("/api/scales/activity", json={"clientId": "test", "sequence": 2, "phase": "idle"}).json()
    assert state["enabled"] and not state["paused"]


def test_weight_only_readings_do_not_zero_body_circumferences():
    from app.services.progress_service import ProgressService

    rows = [
        BodyMeasurement(weight_kg=80, waist_cm=88, chest_cm=108, hips_cm=98, measured_at=datetime.now(UTC)),
        BodyMeasurement(weight_kg=79, measured_at=datetime.now(UTC)),
        BodyMeasurement(waist_cm=87, measured_at=datetime.now(UTC)),
    ]
    progress = ProgressService()
    result = progress._body_measurement_rows(rows)
    assert result[0].current == "87.0 см"
    assert result[0].delta == "-1.0 см"
    assert result[1].current == "108.0 см"
    assert progress._body_cards(rows)[0].value == "79.0 кг"
    assert len(progress._body_weight_series(rows)) == 2