from struct import pack

import pytest

from app.services.scale_protocol import MeasurementGate, decode_service_data


def packet(raw=14000, unit=2, flags=0x22, impedance=510, year=2026):
    return pack("<BBHBBBBBHH", unit, flags, year, 10, 18, 12, 30, 15, impedance, raw)


@pytest.mark.parametrize(("raw", "unit", "flags", "expected"), [
    (14000, 2, 0x22, 70), (15432, 3, 0x22, 69.998), (14000, 2, 0x62, 70),
])
def test_units(raw, unit, flags, expected):
    result = decode_service_data(packet(raw, unit, flags))
    assert result.weight_kg == pytest.approx(expected, abs=0.001)
    assert result.stable
    assert result.impedance_ohm == 510
    assert result.clock == "2026-10-18T12:30:15"


@pytest.mark.parametrize("data", [b"", bytes(12), bytes(14), packet(unit=4), packet(raw=0), packet(raw=65535)])
def test_invalid_packets(data):
    assert decode_service_data(data) is None


def test_flags_and_unsynchronized_clock():
    result = decode_service_data(packet(flags=0, year=0))
    assert not result.stable and not result.removed
    assert result.impedance_ohm is None and result.clock is None
    assert decode_service_data(packet(flags=0xA2, raw=0)).removed
    assert decode_service_data(packet(impedance=65535)).impedance_ohm is None


def test_one_result_per_occupancy():
    gate = MeasurementGate()
    unstable = decode_service_data(packet(flags=0))
    stable = decode_service_data(packet())
    removed = decode_service_data(packet(flags=0xA2))
    assert not gate.accept(unstable, 0)
    assert gate.accept(stable, 1)
    for now in range(2, 1000):
        assert not gate.accept(stable, now)
    assert not gate.accept(removed, 1001)
    assert gate.accept(stable, 1002)


def test_missed_unload_and_impedance_packets():
    gate = MeasurementGate()
    stable = decode_service_data(packet())
    assert gate.accept(stable, 0)
    assert not gate.accept(decode_service_data(packet(flags=0x20, impedance=0)), 1)
    assert not gate.accept(decode_service_data(packet(flags=0)), 2)
    assert not gate.accept(stable, 3)
    assert gate.accept(stable, 130)