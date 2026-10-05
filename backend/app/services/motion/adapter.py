"""Drive adapter contract shared by the physics emulator and the real Modbus driver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Side = Literal["left", "right"]
SIDES: tuple[Side, Side] = ("left", "right")

DriveMode = Literal["disabled", "brake", "torque", "velocity", "position"]


@dataclass
class SideCommand:
    """What the controller asks one drive to do for the next control tick."""

    mode: DriveMode = "brake"
    force_kg: float = 0.0  # torque mode: upward force in kg-equivalent
    target_velocity_mm_s: float = 0.0  # velocity mode
    target_position_mm: float | None = None  # position mode
    force_limit_kg: float = 200.0  # clamp for velocity/position modes
    feedforward_kg: float = 0.0  # added in velocity/position modes (gravity etc.)
    weight_comp_kg: float = 0.0  # share of the commanded force that only carries the bar weight (per side)


@dataclass
class DriveCommand:
    left: SideCommand = field(default_factory=SideCommand)
    right: SideCommand = field(default_factory=SideCommand)
    heartbeat: bool = True

    def side(self, side: Side) -> SideCommand:
        return self.left if side == "left" else self.right


@dataclass
class SideTelemetry:
    side: Side
    connected: bool = True
    enabled: bool = True
    brake_engaged: bool = False
    homed: bool = True
    position_mm: float = 0.0
    velocity_mm_s: float = 0.0
    force_kg: float = 0.0  # applied upward force (kg-equivalent), from current or load cell
    current_a: float = 0.0
    temperature_c: float = 30.0
    torque_limit_percent: int = 100
    error_code: str | None = None
    error_message: str | None = None
    limit_switch_low: bool = False
    limit_switch_high: bool = False
    firmware_version: str = "emu-1.0"
    latency_ms: float = 0.0


@dataclass
class AdapterTelemetry:
    timestamp: float
    left: SideTelemetry
    right: SideTelemetry
    power_ok: bool = True
    heartbeat_ok: bool = True
    physical_estop: bool = False

    def side(self, side: Side) -> SideTelemetry:
        return self.left if side == "left" else self.right

    @property
    def bar_position_mm(self) -> float:
        return (self.left.position_mm + self.right.position_mm) / 2

    @property
    def bar_velocity_mm_s(self) -> float:
        return (self.left.velocity_mm_s + self.right.velocity_mm_s) / 2

    @property
    def sync_delta_mm(self) -> float:
        return self.left.position_mm - self.right.position_mm

    @property
    def total_force_kg(self) -> float:
        return self.left.force_kg + self.right.force_kg


@dataclass
class SelfTestResult:
    id: str
    label: str
    passed: bool
    detail: str
    severity: Literal["critical", "warning", "info"] = "critical"


class DriveAdapter(Protocol):
    """Abstraction over two synchronised ball-screw drives.

    Implementations: ``PhysicsEmulatorAdapter`` (development, tests) and
    ``ModbusDriveAdapter`` (real hardware; time-critical loops are expected to
    live in the drive controller, the adapter only sets targets/limits).
    """

    name: str

    def step(self, command: DriveCommand, dt: float) -> AdapterTelemetry: ...

    def read(self) -> AdapterTelemetry: ...

    def emergency_stop(self) -> None: ...

    def release_emergency_stop(self) -> None: ...

    def set_brake(self, engaged: bool) -> None: ...

    def home(self) -> None: ...

    def self_test(self) -> list[SelfTestResult]: ...

    def reset_errors(self) -> None: ...
