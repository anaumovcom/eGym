"""Torque Mode reference pipeline for the Lichuan A6 drives (pure logic, no I/O).

The only runtime reference sent to a drive is PA_12C (signed, 0.1 % of rated
torque).  The pipeline per side is::

    weightCompensationTorque + exerciseTorque
        -> requestedTorque
        -> ramp (max step per control cycle)
        -> software position limits / overspeed safety
        -> synchronisation correction (position / velocity holds only)
        -> torqueDirection (screw.*DirectionInverted)
        -> clamp to +-maxCommandRaw
        -> PA_12C

Logical torque is positive when the side pulls the bar *up*.  The motion
controller already builds torque-mode commands in kg-equivalent force that
contain the bar weight (``weight_comp_kg``) and the exercise load, so
``exerciseTorque = requested - weightCompensation``.  Below the exercise
lower bound the controller removes the load, which leaves only the weight
compensation ("levitation").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.motion.adapter import SIDES, DriveCommand, Side, SideCommand

if TYPE_CHECKING:  # pragma: no cover
    from app.services.motion.parameters import MotionParameters


@dataclass(frozen=True)
class TorqueSettings:
    per_kg_raw: float = 20.0
    weight_comp_raw: float = 0.0  # 0 -> derive from kg and per_kg_raw
    nominal_weight_kg_per_side: float = 13.0  # bar weight share the calibrated value belongs to
    max_command_raw: int = 400
    speed_limit_rpm: int = 50
    ramp_step_raw: int = 25
    speed_warn_rpm: float = 300.0
    speed_alarm_rpm: float = 400.0
    sync_gain_raw_per_mm: float = 4.0
    sync_max_raw: float = 30.0
    hold_gain_factor: float = 0.25
    position_kp_kg_per_mm: float = 2.0
    position_kd_kg_s_per_mm: float = 0.08
    velocity_kv_kg_s_per_mm: float = 0.15
    soft_min_mm: float = 50.0
    soft_max_mm: float = 1800.0
    left_inverted: bool = False
    right_inverted: bool = False

    @classmethod
    def from_parameters(cls, params: MotionParameters) -> TorqueSettings:
        bar_mass = float(params.get("compensation.barMassKg")) + float(params.get("compensation.movingPartsMassKg"))
        return cls(
            per_kg_raw=float(params.get("torque.perKgRaw")),
            weight_comp_raw=float(params.get("torque.weightCompensationRaw")),
            nominal_weight_kg_per_side=bar_mass / 2,
            max_command_raw=int(params.get("torque.maxCommandRaw")),
            speed_limit_rpm=int(params.get("torque.speedLimitRpm")),
            ramp_step_raw=int(params.get("torque.rampStepRaw")),
            speed_warn_rpm=float(params.get("torque.speedWarnRpm")),
            speed_alarm_rpm=float(params.get("torque.speedAlarmRpm")),
            sync_gain_raw_per_mm=float(params.get("torque.syncGainRawPerMm")),
            sync_max_raw=float(params.get("torque.syncMaxRaw")),
            hold_gain_factor=float(params.get("torque.holdGainFactor")),
            position_kp_kg_per_mm=float(params.get("regulator.positionKp")),
            position_kd_kg_s_per_mm=float(params.get("regulator.positionKd")),
            velocity_kv_kg_s_per_mm=float(params.get("regulator.velocityKv")),
            soft_min_mm=float(params.get("limits.softMinMm")),
            soft_max_mm=float(params.get("limits.softMaxMm")),
            left_inverted=bool(params.get("screw.leftDirectionInverted")),
            right_inverted=bool(params.get("screw.rightDirectionInverted")),
        )


@dataclass
class SideInput:
    position_mm: float = 0.0
    velocity_mm_s: float = 0.0  # signed, positive = up
    speed_rpm: float = 0.0  # absolute motor speed from PA_1C1
    limits_known: bool = True  # software position limits only apply once the zero is established


@dataclass
class SideTorque:
    weight_compensation_raw: float = 0.0
    exercise_raw: float = 0.0
    requested_raw: float = 0.0
    ramped_raw: float = 0.0
    logical_raw: float = 0.0  # after limits / safety / sync, positive = up
    command_raw: int = 0  # value for PA_12C after direction and clamp
    speed_scale: float = 1.0


@dataclass
class TorqueOutput:
    sides: dict[Side, SideTorque] = field(default_factory=lambda: {"left": SideTorque(), "right": SideTorque()})
    warning: str | None = None
    alarm: str | None = None

    def command(self, side: Side) -> int:
        return self.sides[side].command_raw


class TorqueController:
    """Stateful (ramp, alarm latch) conversion of controller commands to PA_12C values."""

    def __init__(self, settings: TorqueSettings | None = None) -> None:
        self.settings = settings or TorqueSettings()
        self._ramped: dict[Side, float] = {"left": 0.0, "right": 0.0}
        self.alarm: str | None = None

    def reset(self) -> None:
        self._ramped = {"left": 0.0, "right": 0.0}
        self.alarm = None

    def stop(self) -> None:
        """PA_12C goes to zero immediately, ramp restarts from zero."""

        self._ramped = {"left": 0.0, "right": 0.0}

    # ------------------------------------------------------------------
    def compute(self, command: DriveCommand, inputs: dict[Side, SideInput], dt: float) -> TorqueOutput:
        del dt
        settings = self.settings
        output = TorqueOutput()
        sync = self._sync_correction(command, inputs)

        for side in SIDES:
            cmd = command.side(side)
            data = inputs[side]
            detail = output.sides[side]
            weight = self._weight_raw(cmd)
            requested = self._requested_raw(cmd, data, weight)
            detail.weight_compensation_raw = weight
            detail.requested_raw = requested
            detail.exercise_raw = requested - weight

            if self.alarm is not None or cmd.mode in {"brake", "disabled"}:
                # nothing to carry the bar: the reference is zero, ramp restarts from zero
                self._ramped[side] = 0.0
                detail.ramped_raw = 0.0
                continue

            detail.ramped_raw = self._ramp(side, requested)
            logical = detail.ramped_raw

            # overspeed: warn reduces the exercise torque working along the movement, alarm cuts PA_12C
            scale = self._speed_scale(data.speed_rpm)
            if data.speed_rpm >= settings.speed_alarm_rpm:
                self.alarm = f"overspeed_{side}_{data.speed_rpm:.0f}rpm"
                output.alarm = self.alarm
                self._ramped[side] = 0.0
                detail.ramped_raw = 0.0
                continue
            if scale < 1.0:
                exercise = logical - weight
                if exercise * data.velocity_mm_s > 0:
                    logical = weight + exercise * scale
                detail.speed_scale = scale
                output.warning = output.warning or f"overspeed_{side}_{data.speed_rpm:.0f}rpm"

            logical = self._apply_position_limits(logical, weight, data)
            logical += sync[side]
            detail.logical_raw = logical
            inverted = settings.left_inverted if side == "left" else settings.right_inverted
            signed = -logical if inverted else logical
            detail.command_raw = int(round(max(-settings.max_command_raw, min(settings.max_command_raw, signed))))

        if self.alarm is not None:
            output.alarm = self.alarm
            for side in SIDES:
                output.sides[side].command_raw = 0
                output.sides[side].logical_raw = 0.0
        return output

    # ------------------------------------------------------------------
    def _weight_raw(self, cmd: SideCommand) -> float:
        settings = self.settings
        if cmd.weight_comp_kg <= 0:
            return 0.0
        if settings.weight_comp_raw > 0 and settings.nominal_weight_kg_per_side > 0:
            return settings.weight_comp_raw * cmd.weight_comp_kg / settings.nominal_weight_kg_per_side
        return cmd.weight_comp_kg * settings.per_kg_raw

    def _requested_raw(self, cmd: SideCommand, data: SideInput, weight: float) -> float:
        settings = self.settings
        per_kg = settings.per_kg_raw
        if cmd.mode == "torque":
            # controller force = gravity share + exercise; the gravity share is replaced by the calibrated weight torque
            return weight + (cmd.force_kg - cmd.weight_comp_kg) * per_kg
        if cmd.mode == "velocity":
            regulator_kg = settings.velocity_kv_kg_s_per_mm * (cmd.target_velocity_mm_s - data.velocity_mm_s)
        elif cmd.mode == "position":
            target = cmd.target_position_mm if cmd.target_position_mm is not None else data.position_mm
            regulator_kg = settings.hold_gain_factor * (
                settings.position_kp_kg_per_mm * (target - data.position_mm) - settings.position_kd_kg_s_per_mm * data.velocity_mm_s
            )
        else:
            return 0.0
        feedforward = weight if abs(cmd.feedforward_kg - cmd.weight_comp_kg) < 1e-6 else cmd.feedforward_kg * per_kg
        limit_raw = abs(cmd.force_limit_kg) * per_kg
        return max(-limit_raw, min(limit_raw, feedforward + regulator_kg * per_kg))

    def _ramp(self, side: Side, requested: float) -> float:
        step = float(max(1, self.settings.ramp_step_raw))
        current = self._ramped[side]
        value = max(current - step, min(current + step, requested))
        self._ramped[side] = value
        return value

    def _speed_scale(self, speed_rpm: float) -> float:
        warn, alarm = self.settings.speed_warn_rpm, self.settings.speed_alarm_rpm
        if speed_rpm <= warn:
            return 1.0
        if alarm <= warn:
            return 0.0
        return max(0.0, 1.0 - (speed_rpm - warn) / (alarm - warn))

    def _apply_position_limits(self, logical: float, weight: float, data: SideInput) -> float:
        if not data.limits_known:
            return logical
        settings = self.settings
        if data.position_mm <= settings.soft_min_mm:
            return max(logical, weight)  # never push further down
        if data.position_mm >= settings.soft_max_mm:
            return min(logical, weight)  # never push further up
        return logical

    def _sync_correction(self, command: DriveCommand, inputs: dict[Side, SideInput]) -> dict[Side, float]:
        """Only holds / automatic moves are corrected here; torque-mode commands already carry the controller's own sync term."""

        zero: dict[Side, float] = {"left": 0.0, "right": 0.0}
        if command.left.mode not in {"position", "velocity"} or command.right.mode not in {"position", "velocity"}:
            return zero
        settings = self.settings
        delta = inputs["left"].position_mm - inputs["right"].position_mm  # > 0: left is higher
        correction = max(-settings.sync_max_raw, min(settings.sync_max_raw, settings.sync_gain_raw_per_mm * delta))
        return {"left": -correction / 2, "right": correction / 2}
