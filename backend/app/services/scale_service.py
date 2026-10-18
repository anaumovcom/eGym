"""Optional, bounded BLE observer. No motor/coach/runtime imports or commands."""

import asyncio
import logging
import sys
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy.orm import Session

from app.repositories.scale_repository import ScaleRepository
from app.schemas.scale import ScaleActivity, ScaleDevice, ScaleSettings, ScaleStatus
from app.services.scale_protocol import SERVICE_UUID, MeasurementGate, decode_service_data

logger = logging.getLogger(__name__)


class ScaleService:
    def __init__(self, sessions: Callable[[], Session], scanner_factory=None, retry_seconds: float = 10,
                 activity_blocker: Callable[[], str | None] | None = None) -> None:
        self.sessions = sessions
        self.repository = ScaleRepository()
        self.status = ScaleStatus()
        self.scanner_factory = scanner_factory
        self.retry_seconds = retry_seconds
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers: set[asyncio.Queue] = set()
        self._tasks: list[asyncio.Task] = []
        self._devices: dict[str, tuple[ScaleDevice, float]] = {}
        self._gate = MeasurementGate()
        self._measuring_until = 0.0
        self._generation = 0
        self._activity: dict[str, tuple[int, str, float]] = {}
        self._hardware_pause: str | None = None
        self._activity_blocker = activity_blocker

    async def _db(self, operation):
        def run():
            with self.sessions() as db:
                return operation(db)
        return await asyncio.to_thread(run)

    async def start(self) -> None:
        try:
            settings = await self._db(self.repository.settings)
            self.status = ScaleStatus(**settings.model_dump())
            self.status.last_measurement = await self._db(self.repository.latest)
        except Exception:
            logger.exception("Scale settings unavailable; machine startup continues")
            self.status.error = "Не удалось загрузить настройки весов"
        if self._activity_blocker:
            try:
                self._hardware_pause = await asyncio.to_thread(self._activity_blocker)
            except Exception:
                self._hardware_pause = "Ожидание состояния тренажёра"
            self._refresh_pause()
        self._tasks = [asyncio.create_task(self._run()), asyncio.create_task(self._consume()), asyncio.create_task(self._monitor_activity())]

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.status.scanning = False

    async def configure(self, settings: ScaleSettings) -> ScaleStatus:
        async with self._lock:
            await self._db(lambda db: self.repository.configure(db, settings))
            self._generation += 1
            self._gate = MeasurementGate()
            self._measuring_until = 0
            for field, value in settings.model_dump().items():
                setattr(self.status, field, value)
            self.status.last_measurement = await self._db(self.repository.latest)
            self.status.error = None
            self._wake.set()
            self._publish()
            return self.snapshot()

    async def start_scanning(self) -> ScaleStatus:
        return await self.configure(ScaleSettings(
            enabled=True, device_id=self.status.device_id,
        ))

    async def stop_scanning(self) -> ScaleStatus:
        return await self.configure(ScaleSettings(
            enabled=False, device_id=self.status.device_id,
        ))

    def update_activity(self, activity: ScaleActivity) -> ScaleStatus:
        previous = self._activity.get(activity.client_id)
        if previous is None or activity.sequence > previous[0]:
            self._activity.pop(activity.client_id, None)
            self._activity[activity.client_id] = (activity.sequence, activity.phase, monotonic())
            while len(self._activity) > 64:
                self._activity.pop(next(iter(self._activity)))
            self._refresh_pause()
        return self.snapshot()

    def _refresh_pause(self) -> None:
        now = monotonic()
        busy = next((phase for _, phase, seen in self._activity.values() if now - seen < 20 and phase != "idle"), None)
        reason = self._hardware_pause or ({"setup": "Настройка упражнения", "exercise": "Выполняется упражнение", "rest": "Отдых между подходами"}.get(busy))
        paused = reason is not None
        if paused != self.status.paused:
            self._generation += 1  # Drop queued pre-transition packets.
            self._measuring_until = 0
            self._wake.set()  # Stop/start the actual scanner, not just the UI.
        if reason != self.status.pause_reason:
            self.status.paused = paused
            self.status.pause_reason = reason
            self._publish()

    async def _monitor_activity(self) -> None:
        while True:
            try:
                if self._activity_blocker:
                    self._hardware_pause = await asyncio.to_thread(self._activity_blocker)
                self._refresh_pause()
            except Exception:
                logger.exception("Cannot read scale activity; pausing optional BLE observer")
                self._hardware_pause = "Ожидание состояния тренажёра"
                self._refresh_pause()
            await asyncio.sleep(0.25)

    async def delete_measurement(self, measurement_id: int, user_id: str) -> None:
        async with self._lock:
            await self._db(lambda db: self.repository.delete_measurement(db, measurement_id, user_id))
            self.status.last_measurement = await self._db(self.repository.latest)
            self._publish()

    def snapshot(self) -> ScaleStatus:
        now = monotonic()
        self.status.devices = [entry for entry, seen in self._devices.values() if now - seen < 90]
        self.status.measuring = self.status.enabled and not self.status.paused and self.status.scanning and now < self._measuring_until
        return self.status.model_copy(deep=True)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _publish(self) -> None:
        for queue in self._subscribers:
            if not queue.full():
                queue.put_nowait(True)

    def on_advertisement(self, device, advertisement) -> None:
        """Bleak invokes this on its asyncio loop; no DB work or task-per-packet."""
        if not self.status.enabled or self.status.paused:
            return
        payload = next((value for key, value in advertisement.service_data.items() if key.lower() == SERVICE_UUID), None)
        if payload is None:
            return
        packet = decode_service_data(payload)
        if packet is None:
            return
        device_id = device.address.upper()
        now = monotonic()
        self._devices.pop(device_id, None)
        self._devices[device_id] = (ScaleDevice(
            device_id=device_id, name=advertisement.local_name or device.name or "Xiaomi Mi Scale 2",
            rssi=advertisement.rssi, last_seen=datetime.now(UTC),
        ), now)
        while len(self._devices) > 32:
            self._devices.pop(next(iter(self._devices)))
        if device_id != self.status.device_id:
            self._publish()
            return
        self.status.last_seen = datetime.now(UTC)
        self._measuring_until = now + 8 if not packet.stable and not packet.removed else 0
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait((self._generation, device_id, packet, now, datetime.now(UTC)))
        self._publish()

    async def _consume(self) -> None:
        while True:
            generation, device_id, packet, seen, received_at = await self._queue.get()
            try:
                async with self._lock:
                    if generation != self._generation or not self.status.enabled or self.status.paused:
                        continue
                    accepted = self._gate.accept(packet, seen)
                    last = self.status.last_measurement
                    if accepted:
                        measurement = await self._db(lambda db, device_id=device_id, packet=packet, received_at=received_at: self.repository.save_current_measurement(
                            db, device_id, packet, received_at,
                        ))
                        if measurement:
                            self.status.last_measurement = measurement
                            self.status.error = None
                    elif (last and packet.stable and not packet.removed and packet.impedance_ohm
                          and last.device_id == device_id and last.impedance_ohm is None
                          and abs(last.weight_kg - packet.weight_kg) < 0.1
                          and 0 <= (received_at - last.timestamp).total_seconds() < 30):
                        await self._db(lambda db, last=last, packet=packet: self.repository.enrich_impedance(db, last.id, packet.impedance_ohm))
                        last.impedance_ohm = packet.impedance_ohm
                    self._publish()
            except ValueError as error:
                self.status.error = str(error)
                self._gate = MeasurementGate()
                self._publish()
            except Exception:
                logger.exception("Scale measurement rejected; machine operation unaffected")
                self.status.error = "Не удалось сохранить измерение весов"
                self._gate = MeasurementGate()  # Retry a transient DB failure on the next advertisement.
                self._publish()

    def _scanner(self, mode: str):
        if self.scanner_factory:
            return self.scanner_factory(self.on_advertisement, mode)
        from bleak import BleakScanner

        if mode == "passive":
            # AD type 0x16: UUID is at offset zero, little endian. BlueZ passive
            # scanning requires AdvertisementMonitor patterns, NOT service_uuids.
            return BleakScanner(self.on_advertisement, scanning_mode="passive",
                                bluez={"or_patterns": [(0, 0x16, b"\x1b\x18")]})
        return BleakScanner(self.on_advertisement, service_uuids=[SERVICE_UUID])

    async def _wait(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)

    async def _run(self) -> None:
        while True:
            self._wake.clear()
            if not self.status.enabled or self.status.paused:
                self.status.scanning = False
                self._publish()
                await self._wake.wait()
                continue
            scanner = None
            try:
                mode = "passive" if sys.platform.startswith("linux") else "active"
                self.status.warning = None
                scanner = self._scanner(mode)
                try:
                    await asyncio.wait_for(scanner.start(), timeout=10)
                except Exception as error:
                    # Older BlueZ/controllers lack AdvertisementMonitor support.
                    # Fallback still reads advertisements, never pairs/connects.
                    unsupported = isinstance(error, NotImplementedError) or any(
                        text in str(error).lower() for text in ("notsupported", "not supported", "advertisementmonitor", "passive")
                    )
                    if mode != "passive" or not unsupported:
                        raise
                    with suppress(Exception):
                        await asyncio.wait_for(scanner.stop(), timeout=3)
                    mode = "active"
                    scanner = self._scanner(mode)
                    await asyncio.wait_for(scanner.start(), timeout=10)
                    self.status.warning = "Пассивный режим недоступен: используются BLE advertising-пакеты в активном поиске"
                self.status.bluetooth_available = True
                self.status.scanning = True
                self.status.scanning_mode = mode
                self.status.error = None
                self._publish()
                # Refresh BlueZ registration periodically: detect a powered-off
                # adapter even when no advertisements (including unload) arrive.
                await self._wait(15)
            except Exception as error:
                self.status.bluetooth_available = False
                self.status.scanning = False
                self.status.error = f"Bluetooth недоступен или ошибка BLE ({type(error).__name__}). Повторный поиск автоматически."
                self._publish()
                await self._wait(self.retry_seconds)
            finally:
                if scanner is not None:
                    with suppress(Exception):
                        await asyncio.wait_for(scanner.stop(), timeout=3)
                self.status.scanning = False
                self._publish()