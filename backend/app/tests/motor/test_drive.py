from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.motor.drive.lichuan import LichuanTorqueDrive
from app.motor.drive.registers import FORBIDDEN_WRITES, ForbiddenRegisterWriteError, assert_writable
from app.motor.profile import MachineProfile, Measured, SideProfile
from app.motor.units import force_to_raw, passport_mm_per_pulse, passport_n_per_raw, raw_to_force, rpm_to_mm_s
from app.tests.motor.fakes import FakeModbusService


def test_passport_constants() -> None:
    assert passport_n_per_raw() == pytest.approx(0.7069, rel=1e-3)
    assert passport_n_per_raw(efficiency=1.0) == pytest.approx(0.7854, rel=1e-3)
    assert passport_mm_per_pulse() == pytest.approx(0.00024414, rel=1e-4)
    assert rpm_to_mm_s(1) == pytest.approx(0.5333, rel=1e-3)


@given(st.floats(-2000, 2000), st.sampled_from([1, -1]), st.floats(0.3, 1.2))
def test_force_raw_roundtrip_within_one_count(force: float, sign: int, k: float) -> None:
    raw = force_to_raw(force, k, sign)
    assert abs(raw_to_force(raw, k, sign) - force) <= k / 2 + 1e-9


def test_profile_json_roundtrip_and_weight_map() -> None:
    side = SideProfile(gravity_map=Measured([(0.0, 60.0), (1000.0, 80.0)], 1.0, "measured", "run-1"))
    profile = MachineProfile(version=3, left=side)
    restored = MachineProfile.from_dict(profile.to_dict())
    assert restored.left.gravity_map.provenance == "measured"
    assert restored.left.weight_n(500) == pytest.approx(70.0)
    assert restored.left.weight_n(-100) == pytest.approx(60.0)
    assert restored.left.weight_n(5000) == pytest.approx(80.0)
    assert restored.right.n_per_raw.provenance == "derived"


@pytest.mark.parametrize("address", sorted(FORBIDDEN_WRITES))
def test_forbidden_registers(address: int) -> None:
    with pytest.raises(ForbiddenRegisterWriteError):
        assert_writable(address)


@given(st.integers(0, 0x3FF))
def test_only_whitelisted_registers_are_writable(address: int) -> None:
    try:
        assert_writable(address)
    except ForbiddenRegisterWriteError:
        return
    assert address in {0x12C, 0x05E, 0x056, 0x1A4}


@pytest.mark.parametrize("sign", [1, -1])
def test_support_respects_direction(sign: int) -> None:
    service = FakeModbusService()
    drive = LichuanTorqueDrive("left", 1, SideProfile(direction_sign=Measured(sign)), 1000, service)
    assert drive.support() is None
    assert service.writes == [(1, 100 * sign)]


@given(st.floats(-1e5, 1e5))
def test_raw_is_always_clamped(force: float) -> None:
    service = FakeModbusService()
    drive = LichuanTorqueDrive("right", 2, SideProfile(), 700, service)
    drive.write_force(force)
    assert -700 <= service.writes[-1][1] <= 700


def test_drive_read_maps_registers_to_newtons_and_mm() -> None:
    service = FakeModbusService(speed_rpm={1: -30})
    sample = LichuanTorqueDrive("left", 1, SideProfile(direction_sign=Measured(-1)), 1000, service).read()
    assert sample.ok
    assert sample.speed_mm_s == pytest.approx(16.0)
    assert sample.motor_force_n == pytest.approx(-100 * passport_n_per_raw())
