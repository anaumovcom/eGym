import ctypes as ct
import platform
import struct
import sys
import threading
import time
from collections import deque
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.settings import AppSetting
from app.motor.drive import can_bus, canopen
from app.motor.drive.canopen import COMMAND, MOTION, STATUS, CanopenDrive, CanopenPair, DriveFaultError
from app.motor.profile import SideProfile
from app.schemas.drive_transport import CanopenSettings, DriveTransportSettings
from app.services import hardware_runtime as runtime_module
from app.services.drive_transport_settings import load_transport
from app.services.hardware_runtime import HardwareRuntime


class VirtualClock:
    now = 10.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class TwoDrives:
    """Two independent CiA 402 nodes. Replies are actual SDO/TPDO wire bytes, including aborts."""

    def __init__(self, config: CanopenSettings, clock=time):
        self.clock = clock
        self.nodes = (config.left_id, config.right_id)
        self.online = set(self.nodes)
        self.drop: set[int] = set()
        self.refuse_enable: set[int] = set()
        self.ignore_torque: set[int] = set()
        self.frames: list[tuple[int, bytes]] = []
        self.queue: deque[tuple[int, bytes]] = deque()
        self.targets = {}
        self.operational = set()
        self.od = {}
        for n in self.nodes:
            od = {(0x6041, 0): 0x40, (0x6502, 0): 0x208, (0x1018, 1): 15, (0x6061, 0): 0,
                  (0x1005, 0): 0x80, (0x6072, 0): 3000, (0x6080, 0): 3000,
                  (0x1016, 0): 1, (0x1016, 1): 0}
            for comm, base, mapping in [(0x1400, 0x200, COMMAND), (0x1800, 0x180, MOTION), (0x1801, 0x280, STATUS)]:
                od[comm, 1], od[comm, 2] = base + n, 1
                od[comm + 0x200, 0] = len(mapping)
                od.update({(comm + 0x200, sub): field for sub, field in enumerate(mapping, 1)})
            self.od[n] = od

    def receive(self, timeout):
        if self.queue:
            return self.queue.popleft()
        if timeout > 0:
            self.clock.sleep(timeout)
        return None

    def close(self):
        self.queue.clear()

    def send(self, identifier, data):
        self.frames.append((identifier, data))
        if identifier == 0:
            command, node = data
            if command == 1:
                self.operational.add(node)
            else:
                self.operational.discard(node)
        elif identifier == 0x80:
            for n in self.nodes:
                if n not in self.targets or n not in self.online or n not in self.operational:
                    continue
                cw, torque = self.targets[n]
                self.od[n][0x6071, 0] = 0 if n in self.ignore_torque else torque & 0xffff
                state = {6: 0x21, 7: 0x23, 15: 0x27}.get(cw, 0x40)
                if n in self.refuse_enable and cw == 15:
                    state = 0x23
                self.od[n][0x6041, 0] = state
                for can_id, payload in ((0x180 + n, struct.pack("<ii", -12000 * n, -30 * n)),
                                        (0x280 + n, struct.pack("<hH", torque, state))):
                    if can_id not in self.drop:
                        self.queue.append((can_id, payload))
        elif identifier - 0x200 in self.online:
            self.targets[identifier - 0x200] = struct.unpack("<Hh", data)
        elif (node := identifier - 0x600) in self.online:
            cs, idx, sub, payload = struct.unpack("<BHBI", data)
            od = self.od[node]
            if cs == 0x40:
                if (idx, sub) in od:
                    cs, payload = 0x43, od[idx, sub]
                else:
                    cs, payload = 0x80, 0x06020000
            else:
                od[idx, sub] = payload
                if idx == 0x6060:
                    od[0x6061, 0] = payload
                if idx == 0x6040 and payload == 0x80:
                    od[0x6041, 0] = 0x40
                cs, payload = 0x60, 0
            self.queue.append((0x580 + node, struct.pack("<BHBI", cs, idx, sub, payload)))


def test_pair_negotiates_profile_and_uses_signed_pdo_feedback():
    config = CanopenSettings(left_id=7, right_id=11)
    bus = TwoDrives(config)
    bus.od[11][0x6502, 0] = 8
    bus.od[7][0x1800, 2] = 255
    pair = CanopenPair(config, lambda _: bus)
    pair.connect({7: 100, 11: -110}, 455, 300)
    assert pair.mode == {7: 4, 11: 4} and bus.od[7][0x1800, 2] == 1
    assert bus.od[11][0x6072, 0] == 455 and bus.od[11][0x1016, 1] == (127 << 16) + 300
    assert bus.targets == {7: (6, 100), 11: (6, -110)}
    pair.switch(pair.nodes, True)
    profile = SideProfile()
    drive = CanopenDrive("right", 11, profile, 455, pair)
    assert drive.servo_state()
    pair.zero[11] -= 500
    assert drive.write_raw(-980) is None
    bus.frames.clear()
    pair.cycle()
    sample = drive.read()
    assert sample.ok and sample.counts == -132000 and sample.speed_mm_s == -176 * profile.sign
    assert sample.position_mm == 500 * profile.mm_per_pulse.value * profile.sign
    assert sample.motor_force_n == -455 * profile.n_per_raw_value * profile.sign
    assert [f for f in bus.frames if f[0] != 0x77F] == [(0x207, struct.pack("<Hh", 15, 100)), (0x20B, struct.pack("<Hh", 15, -455)), (0x80, b"")]
    pair.zero[11], pair.feedback[11][0x6064] = 0x7FFFFFFE, -0x80000000
    assert drive.read().position_mm == 2 * profile.mm_per_pulse.value * profile.sign
    assert all(row["ok"] for row in drive.config_report())
    bus.od[11][0x6080, 0] = 1000
    assert not next(row for row in drive.config_report() if row["register"] == "6080:00")["ok"]


@pytest.mark.parametrize("cycle_ms", [10, 5])
def test_fast_cycles_carry_new_targets_and_measure_complete_exchanges(monkeypatch, cycle_ms):
    clock = VirtualClock()
    monkeypatch.setattr(canopen, "time", clock)
    config = CanopenSettings(cycle_ms=cycle_ms)
    bus = TwoDrives(config, clock)
    for node in bus.nodes:
        bus.od[node][0x1006, 0] = 20000
    pair = CanopenPair(config, lambda _: bus)
    pair.connect({1: 100, 2: -100}, 450, 300)
    assert [bus.od[n][0x1006, 0] for n in pair.nodes] == [cycle_ms * 1000] * 2
    assert bus.targets == {1: (6, 100), 2: (6, -100)}
    assert sum(identifier == 0x80 for identifier, _ in bus.frames) == 4
    axes = [CanopenDrive(side, n, SideProfile(), 450, pair) for side, n in zip(("left", "right"), pair.nodes, strict=True)]
    assert all(drive.control_period_s == cycle_ms / 1000 for drive in axes)
    # A slow status transition must still have 100 ms to complete, including at 200 Hz.
    original_send = bus.send
    enabling_since = None

    def slow_enable(identifier, data):
        nonlocal enabling_since
        if identifier == 0x80 and bus.targets[2][0] == 15:
            if enabling_since is None:
                enabling_since = clock.now
            if clock.now - enabling_since < 0.070:
                bus.refuse_enable.add(2)
            else:
                bus.refuse_enable.discard(2)
        original_send(identifier, data)

    monkeypatch.setattr(bus, "send", slow_enable)
    pair.switch(pair.nodes, True)
    for target in range(205):
        assert axes[0].write_raw(target) is None and axes[1].write_raw(-target) is None
        pair.cycle(spaced=True)
        assert tuple(pair.feedback[n][0x6077] for n in pair.nodes) == (target, -target)
    timing = pair.timing()
    assert timing.intervals == 200 and timing.mean_hz == pytest.approx(1000 / cycle_ms)
    assert timing.p99_ms == pytest.approx(cycle_ms)
    pair.close()
    assert pair.timing() is None


@pytest.mark.parametrize("cycle_ms", [10, 5])
def test_late_second_tpdo_prevents_fast_auto_enable(monkeypatch, cycle_ms):
    clock = VirtualClock()
    monkeypatch.setattr(canopen, "time", clock)
    config = CanopenSettings(cycle_ms=cycle_ms)
    bus = TwoDrives(config, clock)
    receive = bus.receive

    def late_receive(timeout):
        frame = receive(timeout)
        if frame is not None and frame[0] == 0x282:
            clock.sleep(cycle_ms / 1000 * 0.8)
        return frame

    monkeypatch.setattr(bus, "receive", late_receive)
    pair = CanopenPair(config, lambda _: bus)
    with pytest.raises(OSError, match="Нет свежих TPDO.*282"):
        pair.connect({1: 100, 2: -100}, 450, 300)
    assert not pair.ready and pair.timing() is None
    assert bus.targets == {1: (6, 100), 2: (6, -100)}


def test_fast_period_rejected_by_drive_stops_before_start():
    config = CanopenSettings(cycle_ms=5)
    bus = TwoDrives(config)
    bus.od[2][0x1006, 0] = 20000
    def send(identifier, data):
        TwoDrives.send(bus, identifier, data)
        bus.od[2][0x1006, 0] = 20000
    bus.send = send
    pair = CanopenPair(config, lambda _: bus)
    with pytest.raises(OSError, match="1006.*5000"):
        pair.connect({1: 100, 2: -100}, 450, 300)
    assert not bus.operational and not bus.targets


def test_no_enable_for_unknown_mode_or_conflicting_pdo():
    config = CanopenSettings()
    bus = TwoDrives(config)
    pair = CanopenPair(config, lambda _: bus)
    bus.od[2][0x6502, 0] = 1
    with pytest.raises(OSError, match="6061"):
        pair.connect({1: 100, 2: 100}, 300, 300)
    assert not pair.ready and not bus.targets
    bus.od[2][0x6502, 0] = 8
    bus.od[2][0x1800, 1] = 0x181
    with pytest.raises(OSError, match="CAN-ID"):
        pair.connect({1: 100, 2: 100}, 300, 300)
    assert not pair.ready and not bus.targets


def test_requested_torque_mode_is_confirmed_by_both_drives():
    cfg = CanopenSettings(torque_mode="profile_torque")
    bus = TwoDrives(cfg)
    pair = CanopenPair(cfg, lambda _: bus)
    pair.connect({1: 80, 2: -80}, 300, 100)
    assert all(bus.od[node][0x6061, 0] == 4 for node in pair.nodes)
    pair.close()
    cfg = CanopenSettings(torque_mode="cst")
    bus = TwoDrives(cfg)
    bus.od[2][0x6502, 0] = 8
    pair = CanopenPair(cfg, lambda _: bus)
    with pytest.raises(OSError, match=r"CST \(10\).*6061"):
        pair.connect({1: 80, 2: -80}, 300, 100)
    assert not bus.operational and not bus.targets


def test_rollback_on_partial_enable_and_explicit_fault_reset():
    config = CanopenSettings()
    bus = TwoDrives(config)
    pair = CanopenPair(config, lambda _: bus)
    bus.od[2][0x6041, 0] = 8
    with pytest.raises(DriveFaultError):
        pair.connect({1: 110, 2: -110}, 300, 300)
    assert not bus.targets
    pair.connect({1: 110, 2: -110}, 300, 300, reset_fault=True)
    bus.refuse_enable.add(2)
    with pytest.raises(OSError, match="0027|0x27"):
        pair.switch(pair.nodes, True)
    assert bus.targets == {1: (6, 110), 2: (6, -110)}


def test_pair_never_enables_if_second_drive_ignores_signed_preload():
    config = CanopenSettings()
    bus = TwoDrives(config)
    bus.ignore_torque.add(2)
    pair = CanopenPair(config, lambda _: bus)
    pair.connect({1: 110, 2: -110}, 300, 300)
    with pytest.raises(OSError, match="6071"):
        pair.switch(pair.nodes, True)
    assert all(struct.unpack_from("<H", data)[0] != 15 for i, data in bus.frames if i in (0x201, 0x202))


def test_runtime_late_power_manual_off_and_lost_feedback(monkeypatch):
    runtime = HardwareRuntime()
    config = DriveTransportSettings(adapter="canopen")
    bus = TwoDrives(config.canopen)
    monkeypatch.setattr(runtime_module, "CanopenPair", lambda cfg: CanopenPair(cfg, lambda _: bus))
    bus.online.remove(2)
    runtime.change_transport(config, lambda _: None)
    runtime.tick()
    assert runtime.latch == "drive_wait" and not bus.targets
    bus.online.add(2)
    runtime._next_drive_recovery = 0
    runtime.tick()
    assert runtime.latch is None and all(runtime.servo_states().values())
    assert runtime.tick_seconds == 0.020 and runtime.bench is None
    assert {n: t for n, (_, t) in bus.targets.items()} == runtime._support_commands()
    with pytest.raises(PermissionError):
        runtime.change_transport(DriveTransportSettings(adapter="modbus"), lambda _: pytest.fail("saved active switch"))
    runtime.set_service_mode(True)
    runtime.set_servo(False)
    runtime.set_service_mode(False)
    runtime.tick()
    assert not any(runtime.servo_states().values())
    # The right drive's state changed externally since the most recent TPDO.
    bus.od[2][0x6041, 0] = 0x27
    with pytest.raises(PermissionError, match="выключите"):
        runtime.change_transport(DriveTransportSettings(adapter="twin"), lambda _: pytest.fail("saved stale state"))
    bus.od[2][0x6041, 0] = 0x21
    runtime.set_service_mode(True)
    runtime.set_servo(True)
    runtime.set_service_mode(False)
    runtime.canopen.commands = {1: 800, 2: -800}
    bus.drop.add(0x282)
    runtime.workout.mode = "training"
    with pytest.raises(PermissionError, match="упражнения"):
        runtime.change_transport(DriveTransportSettings(adapter="modbus"), lambda _: pytest.fail("saved busy switch"))
    runtime.tick()
    assert runtime.latch == "fault" and not runtime.canopen.ready and not runtime.workout.active
    assert not any(s.ok for s in runtime.samples.values())
    assert {n: t for n, (_, t) in bus.targets.items()} == runtime._support_commands()
    bus.drop.clear()
    runtime._next_drive_recovery = 0
    runtime.tick()
    assert runtime.latch == "fault"


def test_legacy_selection_uses_original_period(db_session):
    db_session.add(AppSetting(key="hardware.drive_transport", value={"adapter": "canopen", "canopen": {"channel": 1}}))
    db_session.commit()
    can = load_transport(db_session).canopen
    assert can.cycle_ms == 20 and can.channel == 1 and can.operation == "control"


def test_fresh_environment_can_starts_in_diagnostics(monkeypatch, db_session):
    monkeypatch.setenv("HARDWARE_ADAPTER", "canopen")
    get_settings.cache_clear()
    assert load_transport(db_session).canopen.operation == "diagnostics"


def test_diagnostics_independent_axes_dictionary_alarms_and_usb_recovery(monkeypatch):
    clock = VirtualClock()
    monkeypatch.setattr(canopen, "time", clock)
    config = CanopenSettings(operation="diagnostics")
    bus = TwoDrives(config, clock)
    bus.online.remove(1)
    bus.od[2].update({(0x6064, 0): 0xfffffefa, (0x6077, 0): 0xff9c, (0x6061, 0): 0xff,
                      (0x1018, 2): 0x12345678, (0x603F, 0): 0x2310, (0x1001, 0): 2, (0x6041, 0): 8})
    def send(identifier, data):
        TwoDrives.send(bus, identifier, data)
        if identifier == 0x602 and data[1:4] == bytes.fromhex("181003"):
            bus.queue[-1] = (0x582, b"\x41" + data[1:4] + bytes.fromhex("04000000"))

    monkeypatch.setattr(bus, "send", send)
    pair = CanopenPair(config, lambda _: bus)

    def poll(count):
        for _ in range(count):
            pair.observe()
            clock.sleep(0.02)
        return pair.monitor.snapshot(clock.now, pair.bus is not None, pair.feedback, pair.replies, pair.sent_targets)

    bus.queue.extend([(0x702, b"\x00"), (0x702, b"\x7f"), (0x82, bytes.fromhex("1023020000000000"))])
    status = poll(55)
    left, right = status.axes
    assert not pair.ready and status.adapter_open and status.sdo_timeouts >= 1 and status.sdo_aborts > 0
    assert left.responding is False and "6041:00" in left.issue
    assert right.responding and right.bootups == 1 and right.heartbeat_state == 127 and right.heartbeat_age_ms > 0
    assert (right.emcy, right.emcy_register) == (0x2310, 2) and right.objects["6041:00"].value == 8
    assert [right.objects[k].value for k in ("6064:00", "6077:00", "6061:00")] == [-262, -100, -1]
    assert right.objects["1018:02"].value == 0x12345678 and right.objects["1018:04"].abort == 0x06020000
    assert "0x41" in right.objects["1018:03"].issue
    assert right.objects["1600:02"].value == COMMAND[1] and right.objects["1016:01"].value == 0
    assert len(status.frames) == 64 and status.frames[-1].seq == status.tx + status.rx
    assert status.tx == len(bus.frames) and status.rx > 0
    bus.online.add(1)
    bus.queue.append((0x82, bytes(8)))  # EMCY reset from the drive
    status = poll(75)
    assert all(a.responding for a in status.axes) and status.axes[1].emcy == 0
    for identifier, data in ((0, b"\x01\x01"), (0x80, b""), (0x77f, b"\x05"), (0x201, bytes(4)),
                             (0x601, bytes.fromhex("2b4060000f000000"))):
        with pytest.raises(OSError, match="диагностика"):
            pair._send(identifier, data)
    with pytest.raises(OSError, match="диагностика"):
        pair.connect({1: 100, 2: 100}, 450, 300, reset_fault=True)
    monkeypatch.setattr(bus, "check_online", lambda: (_ for _ in ()).throw(OSError("USB отключён")), raising=False)
    clock.sleep(2)
    closed = poll(1)
    assert not closed.adapter_open and pair.error == "USB отключён" and closed.axes[1].objects["1018:02"].age_ms > 2000
    monkeypatch.setattr(bus, "check_online", lambda: None)
    clock.sleep(2)
    assert all(a.responding for a in poll(15).axes) and pair.error is None
    assert bus.frames and all(i in (0x601, 0x602) and len(data) == 8 and data[0] == 0x40 for i, data in bus.frames)


def test_readonly_runtime_rejects_control_and_status_does_not_probe(monkeypatch):
    cfg = DriveTransportSettings(adapter="canopen", canopen=CanopenSettings(operation="diagnostics"))
    bus = TwoDrives(cfg.canopen)
    runtime = HardwareRuntime()
    monkeypatch.setattr(runtime_module, "CanopenPair", lambda settings: CanopenPair(settings, lambda _: bus))
    runtime.change_transport(cfg, lambda _: None)
    assert not bus.frames
    for _ in range(16):
        runtime.tick()
    before = list(bus.frames)
    status = runtime.transport_status()
    assert status.diagnostics.adapter_open and all(a.responding for a in status.diagnostics.axes)
    assert runtime.state.machine_label == "Диагностика CANopen" and all(d.connected for d in runtime.state.drives.values())
    assert not status.connected and not runtime.canopen.ready and runtime.motion_block_reason()
    runtime.set_service_mode(True)
    for action in (lambda: runtime.set_servo(True), lambda: runtime.set_servo(False), runtime.reset_fault,
                   runtime.reset_zero, lambda: runtime.start_calibration("B0")):
        with pytest.raises(PermissionError, match="диагностика"):
            action()
    runtime.apply_shutdown_support()
    assert before == bus.frames and all(data[0] == 0x40 and i in (0x601, 0x602) for i, data in before)
    assert not bus.targets
    control = cfg.model_copy(update={"canopen": cfg.canopen.model_copy(update={"operation": "control"})})
    bus.od[1][0x6041, 0] = 0x27  # Another master enabled the drive after the displayed reading.
    with pytest.raises(PermissionError, match="выключите"):
        runtime.change_transport(control, lambda _: pytest.fail("took control of a live axis"))
    assert runtime.canopen.read_only and all(data[0] == 0x40 for _, data in bus.frames)
    bus.od[1][0x6041, 0] = 0x40
    bus.online.remove(2)  # Previously disabled, now awaiting power.
    assert runtime.change_transport(control, lambda _: None).config.canopen.operation == "control"


def test_control_discovery_checks_right_when_left_unpowered():
    cfg = CanopenSettings()
    bus = TwoDrives(cfg)
    bus.online.remove(1)
    pair = CanopenPair(cfg, lambda _: bus)
    with pytest.raises(canopen.SdoTimeoutError, match="ID 1"):
        pair.connect({1: 80, 2: -80}, 300, 100)
    snapshot = pair.monitor.snapshot(time.monotonic(), False, {}, {}, {})
    assert snapshot.axes[1].objects["6041:00"].value == 0x40 and "6041:00" in snapshot.axes[0].issue
    assert not bus.operational and not bus.targets


def test_feedback_latency_uses_last_tpdo_of_each_verified_cycle(monkeypatch):
    clock = VirtualClock()
    monkeypatch.setattr(canopen, "time", clock)
    config = CanopenSettings(cycle_ms=5)
    bus = TwoDrives(config, clock)
    original_receive = bus.receive

    def delayed(timeout):
        frame = original_receive(timeout)
        if frame and 0x180 < frame[0] < 0x300:
            clock.sleep(0.00025)
        return frame

    monkeypatch.setattr(bus, "receive", delayed)
    pair = CanopenPair(config, lambda _: bus)
    pair.connect({1: 80, 2: -80}, 300, 100)
    for _ in range(24):
        pair.cycle(spaced=True)
    assert [pair.monitor.axes[n].tpdo_latency_ms for n in pair.nodes] == pytest.approx([0.5, 1.0])
    assert pair.timing().p99_feedback_ms == pytest.approx(1.0)
    assert pair.timing().p99_ms == pytest.approx(5.0)


def test_diagnostic_bitrates_and_socketcan_kernel_bitrate(monkeypatch):
    with pytest.raises(ValidationError):
        CanopenSettings(operation="control", bitrate=250000)
    with pytest.raises(ValidationError):
        CanopenSettings(operation="diagnostics", driver="usbcanfd", bitrate=50000)
    cfg = CanopenSettings(operation="diagnostics", driver="socketcan", bitrate=50000)
    monkeypatch.setattr(can_bus.socket, "AF_CAN", 29, raising=False)
    link = b'[{"flags":["UP"],"linkinfo":{"info_data":{"state":"ERROR-ACTIVE","bittiming":{"bitrate":250000}}}}]'
    monkeypatch.setattr(can_bus.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=link))
    with pytest.raises(OSError, match="250000.*50000"):
        can_bus.SocketCan(cfg)


@pytest.mark.parametrize("cycle_ms", [10, 5])
def test_worker_schedule_allows_full_rate_and_yields_after_overrun(monkeypatch, cycle_ms):
    config = CanopenSettings(cycle_ms=cycle_ms)
    runtime = HardwareRuntime()
    runtime.change_transport(DriveTransportSettings(adapter="canopen", canopen=config), lambda _: None)
    assert runtime.tick_seconds == runtime.drives["left"].control_period_s == cycle_ms / 1000
    clock = VirtualClock()
    monkeypatch.setattr(runtime_module, "time", clock)
    starts = []

    class Stop:
        def is_set(self):
            return len(starts) >= 5

        def wait(self, delay):
            pytest.fail("Fast CAN must use the high-resolution timer")

    def tick():
        starts.append(clock.now)
        clock.sleep(runtime.tick_seconds * (2 if len(starts) == 3 else 0.5))

    monkeypatch.setattr(runtime, "tick", tick)
    monkeypatch.setattr(runtime, "apply_shutdown_support", lambda: None)
    runtime._control_loop(Stop())
    gaps = [b - a for a, b in pairwise(starts)]
    assert gaps == pytest.approx([runtime.tick_seconds * n for n in (1, 1, 2.25, 1)])
    stop = threading.Event()
    monkeypatch.setattr(clock, "sleep", lambda _: stop.set())
    runtime._control_loop(stop)
    assert len(starts) == 5


def test_selection_api_persists_and_guards_debug(client, session_factory, monkeypatch):
    # The background worker also runs on a commissioning PC with the actual adapters attached.
    def offline_bus(_config):
        raise OSError("Тестовый адаптер отключён")

    monkeypatch.setattr(runtime_module, "CanopenPair", lambda config: CanopenPair(config, offline_bus))
    monkeypatch.setattr(runtime_module.modbus_service, "recover_pair", lambda *args, **kwargs: ["Тестовый порт отключён"])
    original = client.get("/api/hardware/drive-transport").json()["config"]
    payload = DriveTransportSettings(adapter="canopen", canopen=CanopenSettings(channel=1, cycle_ms=5)).model_dump()
    response = client.put("/api/hardware/drive-transport", json=payload)
    assert response.status_code == 200 and response.json()["config"] == payload
    assert client.get("/api/hardware/drive-transport").json()["config"] == payload
    assert client.post("/api/modbus/connect", json={"port": "SIM://"}).status_code == 409
    with session_factory() as session:
        assert load_transport(session).model_dump() == payload
    payload["canopen"]["operation"] = "diagnostics"
    observed = client.put("/api/hardware/drive-transport", json=payload).json()
    assert not observed["connected"] and not observed["diagnostics"]["adapter_open"]
    assert [axis["node"] for axis in observed["diagnostics"]["axes"]] == [1, 2]
    with session_factory() as session:
        assert load_transport(session).canopen.operation == "diagnostics"
    payload["canopen"]["right_id"] = 1
    assert client.put("/api/hardware/drive-transport", json=payload).status_code == 422
    payload["canopen"]["right_id"] = 2
    payload["canopen"]["cycle_ms"] = 1
    assert client.put("/api/hardware/drive-transport", json=payload).status_code == 422
    payload["canopen"]["cycle_ms"] = 5
    payload["adapter"] = "modbus"
    assert client.put("/api/hardware/drive-transport", json=payload).json()["config"] == payload
    assert client.put("/api/hardware/drive-transport", json=original).json()["config"] == original


def test_native_sdk_abi_and_packaged_architectures():
    assert [ct.sizeof(s) for s in (can_bus._Frame, can_bus._Transmit, can_bus._Receive, can_bus._ChannelConfig)] == [16, 20, 24, 32]
    assert ct.sizeof(can_bus._DeviceInfo) == 82 and can_bus._DeviceInfo.model.offset == 32
    root = Path(can_bus.__file__).parent / "usbcanfd"
    for arch, machine in (("x86_64", 62), ("aarch64", 183), ("armhf", 40)):
        binary = (root / arch / "libcontrolcanfd.so").read_bytes()
        assert binary[:4] == b"\x7fELF" and struct.unpack_from("<H", binary, 18)[0] == machine


@pytest.mark.skipif(sys.platform != "linux", reason="The supplied SDK uses Linux ELF binaries")
def test_linux_loads_packaged_sdk_without_opening_usb(monkeypatch):
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64", "aarch64", "arm64"} and not machine.startswith("armv"):
        pytest.skip(f"No packaged USB-CAN-FD-B SDK for {machine}")
    monkeypatch.delenv("CANOPEN_LIBRARY", raising=False)
    library = can_bus._vendor_library()
    assert library.ZCAN_OpenDevice.restype is ct.c_void_p
    assert library.ZCAN_Receive.argtypes[1] == ct.POINTER(can_bus._Receive)


def test_native_sdk_classic_frame_and_cleanup(monkeypatch):
    calls = []
    device, channel = 0x100000014, 0x100001234

    class Sdk:
        def ZCAN_OpenDevice(self, kind, num, reserved):  # noqa: N802
            assert (kind, num, reserved) == (41, 3, 0)
            return device

        def ZCAN_InitCAN(self, handle, number, pointer):  # noqa: N802
            assert (handle, number) == (device, 1)
            init = ct.cast(pointer, ct.POINTER(can_bus._ChannelConfig)).contents
            assert (init.can_type, init.acc_mask, init.filter, init.mode) == (1, 0xffffffff, 1, 0)
            return channel

        def ZCAN_GetDeviceInf(self, handle, pointer):  # noqa: N802
            assert handle == device
            info = ct.cast(pointer, ct.POINTER(can_bus._DeviceInfo)).contents
            info.serial, info.model, info.channels, info.firmware = b"USBCANFD202408094469", b"USB-CAN-FD-B", 2, 0x120
            return 1

        def ZCAN_Transmit(self, handle, pointer, count):  # noqa: N802
            obj = ct.cast(pointer, ct.POINTER(can_bus._Transmit)).contents
            assert (handle, count, obj.frame.identifier, obj.frame.size, obj.transmit_type) == (channel, 1, 0x602, 8, 0)
            assert bytes(obj.frame.data) == bytes.fromhex("4002650000000000")
            return 1

        def ZCAN_Receive(self, handle, pointer, count, wait):  # noqa: N802
            assert (handle, count, wait) == (channel, 1, 0)
            obj = ct.cast(pointer, ct.POINTER(can_bus._Receive)).contents
            obj.frame.identifier, obj.frame.size = 0x702, 1
            obj.frame.data[0] = 5
            return 1

        def __getattr__(self, name):
            def run(*args):
                calls.append((name, *args))
                return 1
            return run

    monkeypatch.setattr(can_bus, "_vendor_library", Sdk)
    bus = can_bus.UsbCanFd(CanopenSettings(device=3, channel=1))
    assert bus.info.serial == "USBCANFD202408094469" and bus.info.channels == 2 and bus.info.firmware == 0x120
    assert [c[0] for c in calls][-3:] == ["ZCAN_ClearFilter", "ZCAN_AckFilter", "ZCAN_StartCAN"]
    bus.send(0x602, bytes.fromhex("4002650000000000"))
    assert bus.receive(0) == (0x702, b"\x05")
    bus.close()
    assert calls[0] == ("ZCAN_SetAbitBaud", device, 1, 500000)
    assert calls[-2:] == [("ZCAN_ResetCAN", channel), ("ZCAN_CloseDevice", device)]
    monkeypatch.setattr(Sdk, "ZCAN_AckFilter", lambda self, h: 0, raising=False)
    cfg = CanopenSettings(device=3, channel=1, operation="diagnostics")
    pair = CanopenPair(cfg, can_bus.UsbCanFd)
    pair.observe()
    assert pair.bus is None and "AckFilter" in pair.error and "ошибка запуска канала" in pair.monitor.stage
    assert pair.monitor.adapter.serial == "USBCANFD202408094469"
    assert calls[-2:] == [("ZCAN_ResetCAN", channel), ("ZCAN_CloseDevice", device)]
