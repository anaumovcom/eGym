"""A calibration session stepped by the hardware runtime tick (plan 15 §2.0, §6).

The runtime owns the bus: every tick it reads both drives and hands the frame
to ``CalibrationSession.step``, which advances the current procedure and
writes its command. Stages run one after another (the wizard: B5 → S3 → C1);
each stage updates the *candidate* profile, which is applied to the drives
only for the duration of the session. The candidate becomes active only when
the operator saves it.
"""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal

from app.motor.calibration.graph import BY_CODE, RUNNABLE, WIZARD
from app.motor.calibration.procedures.bus import (
    absolute_zero,
    bus_timing,
    config_check,
    control_delay,
    fit_bus_timing,
    fit_config,
    fit_delay,
    fit_zero,
)
from app.motor.calibration.procedures.common import Build, Context, Fit, Operator, Outcome
from app.motor.calibration.procedures.coupling import fit_coupling, side_coupling
from app.motor.calibration.procedures.daily import daily_check, fit_daily
from app.motor.calibration.procedures.direction import direction_test
from app.motor.calibration.procedures.drive_response import SPECS as DRIVE_SPECS
from app.motor.calibration.procedures.dynamics import fit_friction_up, fit_moving_mass, friction_up, moving_mass
from app.motor.calibration.procedures.friction_map import SPECS as FRICTION_SPECS
from app.motor.calibration.procedures.heightmap import fit_height_map, height_map, map_heights
from app.motor.calibration.procedures.holding import SPECS as HOLDING_SPECS
from app.motor.calibration.procedures.loaded import SPECS as LOADED_SPECS
from app.motor.calibration.procedures.motion import Balance
from app.motor.calibration.procedures.moves import (
    braking_test,
    fit_braking,
    fit_liftoff,
    fit_motion_check,
    fit_travel_feed,
    liftoff_test,
    motion_check,
    travel_feed,
)
from app.motor.calibration.procedures.positioning import SPECS as POSITIONING_SPECS
from app.motor.calibration.procedures.reference import fit_accuracy, fit_scale, loaded_window, weight_shift
from app.motor.calibration.procedures.relay import fit_relay, relay_test
from app.motor.calibration.procedures.statics import balance_and_friction, fit_balance
from app.motor.calibration.procedures.support import fit_support, support_descent
from app.motor.calibration.procedures.travel import fit_travel, travel_range
from app.motor.calibration.runner import (
    CalibrationRunner,
    Frame,
    Procedure,
    ProcedureEnvelope,
    ProcedureError,
    Prompt,
    RunResult,
)
from app.motor.calibration.wizard import DIRECTION_ENVELOPE, _measured
from app.motor.drive.protocol import TorqueDrive
from app.motor.parameters import BY_KEY, _measured_payload
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.units import SIDES, Side, n_to_kgf

SessionStatus = Literal["running", "done", "aborted", "failed"]
StageStatus = Literal["pending", "running", "done", "aborted", "failed"]
DEAD_MAN_TIMEOUT_S = 1.5  # heartbeat from the calibration screen (sent automatically while it is open)
ON_STOPS_MM = 15.0
RELAY_STEPS_N = (6.0, 12.0)
LOG_POINTS = 600
REFERENCE_KG = (2.0, 60.0)
MAX_S = {"S7": 1500.0, "L1": 1500.0, "L2": 1500.0, "H2": 900.0, "W2": 900.0, "B6": 900.0, "S8": 900.0}
TRAVEL_ENVELOPE_MM = 2000.0  # B8 rises to the real upper stop: beyond the software limit, below the screw length
_RESCALED = (
    "gravity_map", "coulomb_up_n", "coulomb_down_n", "viscous_n_per_mm_s", "stribeck_extra_n", "moving_mass_kg",
    "liftoff_extra_n", "travel_extra_up_n", "travel_extra_down_n", "travel_table_up", "travel_table_down",
    "dwell_extra_n", "screw_ripple_n",
)
_RESCALED_MACHINE = ("hold_ultimate_k_n_per_mm", "side_coupling_n_per_mm", "hold_k_n_per_mm", "hold_c_n_per_mm_s", "sync_k_n_per_mm", "tight_spots")
EXTENDED: dict[str, tuple[Build, Fit]] = {**DRIVE_SPECS, **FRICTION_SPECS, **POSITIONING_SPECS, **HOLDING_SPECS, **LOADED_SPECS}
EXTRA_PATHS = {
    "S3": ("left.stribeck_extra_n", "right.stribeck_extra_n"),
    "S7": ("left.coulomb_up_n", "left.coulomb_down_n", "right.coulomb_up_n", "right.coulomb_down_n", "left.stribeck_extra_n", "right.stribeck_extra_n"),
    "D2": ("left.coulomb_up_n", "left.coulomb_down_n", "right.coulomb_up_n", "right.coulomb_down_n", "left.stribeck_v_mm_s", "right.stribeck_v_mm_s"),
    "S9": (*(f"{side}.{key}" for side in SIDES for key in _RESCALED), *_RESCALED_MACHINE),
}
STRIBECK_MIN_N = 2.0  # a smaller static − kinetic difference is noise: no split
_SIDE_LABEL = {"left": "Л", "right": "П"}


def _line(label: str, value: str, ok: bool | None = None) -> dict[str, Any]:
    return {"label": label, "value": value, "ok": ok}


def _scaled(item: Measured, ratio: float) -> Measured:
    if item.value is None:
        return item
    if isinstance(item.value, list):
        value: Any = [(float(x), float(w) * ratio) for x, w in item.value]
    else:
        value = float(item.value) * ratio
    ci95 = item.ci95 * ratio if item.ci95 is not None and math.isfinite(item.ci95) else item.ci95
    return replace(item, value=value, ci95=ci95)


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


@dataclass
class Stage:
    code: str
    title: str
    status: StageStatus = "pending"
    progress: float = 0.0
    note: str = ""
    reason: str | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {"code": self.code, "title": self.title, "status": self.status, "progress": round(self.progress, 3), "note": self.note, "reason": self.reason, "result": self.result}


def _set_profiles(drives: dict[Side, TorqueDrive], profile: MachineProfile) -> None:
    for side in SIDES:
        drive = drives[side]
        if hasattr(drive, "profile"):
            drive.profile = profile.side(side)  # type: ignore[attr-defined]


def _path_value(profile: MachineProfile, path: str):  # noqa: ANN202
    target: object = profile
    for part in path.split("."):
        target = getattr(target, part)
    return target


class CalibrationSession:
    def __init__(
        self,
        code: str,
        drives: dict[Side, TorqueDrive],
        profile: MachineProfile,
        *,
        options: Mapping[str, Any] | None = None,
        safety: SafetyEnvelope | None = None,
        dead_man_timeout_s: float = DEAD_MAN_TIMEOUT_S,
    ) -> None:
        if code not in RUNNABLE:
            raise ValueError(f"Калибровка {code} не запускается из интерфейса")
        self.options = {key: value for key, value in (options or {}).items() if value is not None}
        if any("referenceKg" in BY_CODE[stage].inputs for stage in RUNNABLE[code]):
            reference = self.options.get("referenceKg")
            if not isinstance(reference, int | float) or not REFERENCE_KG[0] <= reference <= REFERENCE_KG[1]:
                raise ValueError(f"Укажите массу эталонного груза на грифе: {REFERENCE_KG[0]:.0f}–{REFERENCE_KG[1]:.0f} кг")
        self.safety = safety or SafetyEnvelope()
        self.id = f"{code}-{uuid.uuid4().hex[:8]}"
        self.code = code
        self.title = WIZARD.title if code == "WIZARD" else BY_CODE[code].title
        self.drives = drives
        self.base = profile
        self.profile = profile  # candidate
        self.status: SessionStatus = "running"
        self.reason: str | None = None
        self.started_at = datetime.now(UTC)
        self.finished_at: datetime | None = None
        self.stages = [Stage(stage, BY_CODE[stage].title) for stage in RUNNABLE[code]]
        self.saved_version: int | None = None
        self.persisted_status: str | None = None
        self.log: list[tuple[float, float, float, float, float, float, float]] = []
        self.dead_man_timeout_s = dead_man_timeout_s
        self.keepalive_at = time.monotonic()
        self.runner = CalibrationRunner(drives, None, dead_man=self._dead_man_held)
        self._index = 0
        self._relay_attempt = 0
        self._window: dict[Side, tuple[float, float]] | None = None
        self._balance: Balance | None = None
        self.operator = Operator()
        self._context: Context | None = None
        self._bar_up = False  # the bar is held above the stops by the previous stage
        self._started_monotonic = time.monotonic()
        self._finished_monotonic: float | None = None

    # ------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return self.status == "running"

    @property
    def current_stage(self) -> Stage:
        return self.stages[min(self._index, len(self.stages) - 1)]

    def keepalive(self) -> None:
        self.keepalive_at = time.monotonic()

    @property
    def prompt(self) -> Prompt | None:
        return self.operator.prompt if self.running else None

    def reply(self, value: float | None) -> None:
        """The operator's answer to the current prompt; ``ValueError`` with a readable message if it does not fit."""

        prompt = self.prompt
        if prompt is None:
            raise ValueError("Калибровка ничего не спрашивает")
        if prompt.kind == "input":
            if value is None or not math.isfinite(value):
                raise ValueError(f"Введите число: {prompt.label or 'значение'}")
            if (prompt.min is not None and value < prompt.min) or (prompt.max is not None and value > prompt.max):
                raise ValueError(f"{prompt.label or 'Значение'}: допустимо {prompt.min:g}…{prompt.max:g} {prompt.unit or ''}".rstrip())
        self.operator.answer(value)

    def _dead_man_held(self) -> bool:
        return time.monotonic() - self.keepalive_at <= self.dead_man_timeout_s

    def begin(self) -> None:
        self._start_stage()

    def step(self, frame: Frame) -> bool:
        """One tick; ``True`` once the session has finished (the host then writes support)."""

        if not self.running:
            return True
        stage = self.stages[self._index]
        result = self.runner.feed(frame)
        if self.runner.result.log:
            self.log.append(self.runner.result.log[-1])
        stage.note = self.runner.note
        stage.progress = self.runner.progress
        if result is not None:
            self._stage_finished(result)
        return not self.running

    def cancel(self, reason: str, *, support: bool = True) -> None:
        if not self.running:
            return
        self.runner.cancel(reason, support=support)
        stage = self.stages[self._index]
        stage.status, stage.reason = "aborted", reason
        self._finish("aborted", reason)

    # --------------------------------------------------------------- stages
    def _build(self, code: str) -> tuple[Procedure, ProcedureEnvelope | None]:
        if code == "B5":
            return direction_test({side: self.profile.side(side).sign for side in SIDES}), DIRECTION_ENVELOPE
        if code == "S3":
            return balance_and_friction({side: 0.0 for side in SIDES}), None
        if code == "C1":
            window = self._window or self._profile_window()
            relay_n = RELAY_STEPS_N[self._relay_attempt]
            return relay_test(window, relay_n=relay_n, lift_mm=None if self._bar_up else 10.0), None
        if code == "B0":
            return config_check(self.drives), None
        if code == "B1":
            return bus_timing(), None
        self._balance = Balance.from_profile(self.profile)
        if code in EXTENDED:
            self._context = Context(self.profile, self._balance, self.safety, self.options, self.operator, self.drives)
            return EXTENDED[code][0](self._context)
        if code == "B7":
            return absolute_zero(self._balance), None
        if code == "S7":
            heights = map_heights(30.0, self._top_mm())
            return height_map(self._balance, heights), ProcedureEnvelope(max_x_mm=heights[-1] + 60.0)
        if code in ("S9", "G1"):
            start = {side: self._balance.edge(side, 0.0, -1) for side in SIDES}
            return loaded_window(start), ProcedureEnvelope(max_x_mm=80.0)
        if code == "D2":
            top = min(400.0, self._top_mm())
            return friction_up(self._balance, top_mm=top), ProcedureEnvelope(max_x_mm=top + 60.0)
        if code == "D4":
            return moving_mass(self._balance), ProcedureEnvelope(max_x_mm=150.0)
        if code == "C3":
            npr = {side: self.profile.side(side).n_per_raw_value for side in SIDES}
            signs = {side: self.profile.side(side).sign for side in SIDES}
            return support_descent(self._balance, npr, signs), ProcedureEnvelope(max_x_mm=200.0)
        if code == "B3":
            return control_delay(self._balance), ProcedureEnvelope(max_x_mm=120.0)
        if code == "X2":
            return side_coupling(self._balance), ProcedureEnvelope(max_x_mm=120.0)
        if code == "B8":
            return travel_range(self._balance, expected_mm=float(self.profile.travel_mm.value)), ProcedureEnvelope(max_x_mm=TRAVEL_ENVELOPE_MM)
        if code == "Q1":
            start = {side: self._balance.edge(side, 0.0, -1) for side in SIDES}
            return daily_check(self.drives, start), ProcedureEnvelope(max_x_mm=80.0)
        if code == "M1":
            return liftoff_test(self._balance), ProcedureEnvelope(max_x_mm=80.0)
        if code == "M2":
            return travel_feed(self._balance), ProcedureEnvelope(max_x_mm=220.0)
        if code == "M3":
            return braking_test(self._balance), ProcedureEnvelope(max_x_mm=240.0)
        if code == "M4":
            return motion_check(self._balance), ProcedureEnvelope(max_x_mm=200.0)
        raise ValueError(code)

    def _top_mm(self) -> float:
        return min(float(self.profile.travel_mm.value) - 20.0, self.safety.soft_max_mm) - 80.0

    def _profile_window(self) -> dict[Side, tuple[float, float]]:
        window = {}
        for side in SIDES:
            profile = self.profile.side(side)
            weight = profile.weight_n(10.0)
            extra = float(profile.stribeck_extra_n.value or 0.0)
            window[side] = (weight - float(profile.coulomb_down_n.value) - extra, weight + float(profile.coulomb_up_n.value) + extra)
        return window

    def _start_stage(self) -> None:
        stage = self.stages[self._index]
        stage.status = "running"
        stage.progress = 0.0
        procedure, envelope = self._build(stage.code)
        result = self.runner.begin(procedure, max_s=MAX_S.get(stage.code, 600.0), envelope=envelope)
        stage.note = self.runner.note
        if result is not None:
            self._stage_finished(result)

    def _stage_finished(self, result: RunResult) -> None:
        stage = self.stages[self._index]
        if result.status != "done":
            stage.status, stage.reason = result.status, result.reason
            self._finish(result.status, f"{stage.code}: {result.reason}")
            return
        try:
            retry = self._fit(stage, result.data)
        except ProcedureError as error:
            stage.status, stage.reason = "failed", str(error)
            self.runner.cancel(str(error))  # support
            self._finish("failed", f"{stage.code}: {error}")
            return
        if retry:
            self._start_stage()
            return
        stage.status, stage.progress = "done", 1.0
        self._index += 1
        if self._index >= len(self.stages):
            self._finish("done", None)
            return
        _set_profiles(self.drives, self.profile)
        self._start_stage()

    def _fit(self, stage: Stage, data: dict[str, Any]) -> bool:
        """Update the candidate from a finished stage; ``True`` to rerun the stage (C1 with a stronger relay)."""

        if stage.code == "B5":
            for side in SIDES:
                sign = data["sides"][side]["direction_sign"]
                self.profile = self.profile.with_side(side, replace(self.profile.side(side), direction_sign=_measured(sign, None, self.id)))
            stage.result = {"sides": data["sides"], "report": [
                _line(f"{_SIDE_LABEL[side]}: поднимает момент", f"{'+' if item['direction_sign'] > 0 else '−'} (отрыв при {abs(item['lift_raw'])} ед.)", True)
                for side, item in data["sides"].items()
            ]}
            self._bar_up = False
            return False
        if stage.code == "S3":
            estimate = fit_balance(data)
            for side in SIDES:
                current = self.profile.side(side)
                self.profile = self.profile.with_side(side, replace(
                    current,
                    gravity_map=_measured([(estimate.height_mm, estimate.weight_n[side].mean)], estimate.weight_n[side].ci95, self.id),
                    coulomb_up_n=_measured(estimate.coulomb_up_n[side].mean, estimate.coulomb_up_n[side].ci95, self.id),
                    coulomb_down_n=_measured(estimate.coulomb_down_n[side].mean, estimate.coulomb_down_n[side].ci95, self.id),
                    stribeck_extra_n=replace(current.stribeck_extra_n, value=0.0),  # breakaway again: D2 splits it
                ))
            self._window = {
                side: (estimate.weight_n[side].mean - estimate.coulomb_down_n[side].mean, estimate.weight_n[side].mean + estimate.coulomb_up_n[side].mean) for side in SIDES
            }
            stage.result = estimate.to_dict() | {"report": [
                line
                for side in SIDES
                for line in (
                    _line(
                        f"{_SIDE_LABEL[side]}: вес (баланс)",
                        f"{estimate.weight_n[side].mean:.1f} ± {_finite(estimate.weight_n[side].ci95) or 0:.1f} Н ({n_to_kgf(estimate.weight_n[side].mean):.1f} кгс)",
                        estimate.weight_n[side].rel_spread < 0.05,
                    ),
                    _line(f"{_SIDE_LABEL[side]}: трение вверх / вниз", f"{estimate.coulomb_up_n[side].mean:.1f} / {estimate.coulomb_down_n[side].mean:.1f} Н"),
                )
            ] + [_line("Высота замера", f"{estimate.height_mm:.1f} мм")]}
            self._bar_up = True
            return False
        if stage.code == "C1":
            relay_n = RELAY_STEPS_N[self._relay_attempt]
            self._bar_up = True
            try:
                relay = fit_relay(data)
            except ProcedureError as error:
                self._relay_attempt += 1
                if self._relay_attempt < len(RELAY_STEPS_N):
                    stage.note = f"{error}: повтор с реле ±{RELAY_STEPS_N[self._relay_attempt]:.0f} Н"
                    return True
                raise
            self.profile = replace(
                self.profile,
                hold_ultimate_k_n_per_mm=_measured(relay["k_u_n_per_mm"], None, self.id),
                hold_ultimate_period_s=_measured(relay["period_s"], None, self.id),
            )
            stage.result = {**relay, "relay_n": relay_n, "report": [
                _line("Предельная жёсткость Kᵤ", f"{relay['k_u_n_per_mm']:.2f} Н/мм"),
                _line("Период / амплитуда цикла", f"{relay['period_s']:.2f} с / {relay['amplitude_mm']:.2f} мм"),
                _line("Реле", f"±{relay_n:.0f} Н"),
            ]}
            return False
        fitter = getattr(self, f"_fit_{stage.code.lower()}", None)
        if fitter is None and stage.code in EXTENDED:
            self._fit_extended(stage, EXTENDED[stage.code][1](data, self._context))
            self._bar_up = False
            return False
        if fitter is None:
            raise ValueError(stage.code)
        fitter(stage, data)
        if stage.code not in ("B0", "B1"):
            self._bar_up = False  # these procedures land the bar on the stops at the end
        return False

    def _set_side(self, side: Side, **values: Measured) -> None:
        self.profile = self.profile.with_side(side, replace(self.profile.side(side), **values))

    def _fit_extended(self, stage: Stage, outcome: Outcome) -> None:
        stage.result = {**outcome.data, "report": outcome.report}
        if outcome.error:
            raise ProcedureError(outcome.error)
        for side, values in outcome.sides.items():
            self._set_side(side, **{key: _measured(value, ci, self.id) for key, (value, ci) in values.items()})
        if outcome.machine:
            self.profile = replace(self.profile, **{key: _measured(value, ci, self.id) for key, (value, ci) in outcome.machine.items()})

    def _fit_b0(self, stage: Stage, data: dict[str, Any]) -> None:
        result = fit_config(data)
        report = [
            _line(f"{_SIDE_LABEL[side]}: {item['label']}", "—" if item["value"] is None else str(item["value"]) + (f" ({item['detail']})" if item.get("detail") else ""), item["ok"])
            for side in SIDES for item in result["sides"][side]
        ]
        stage.result = {"ok": result["ok"], "mismatches": result["mismatches"], "report": report}
        if not result["ok"]:
            raise ProcedureError("расхождения в настройках привода: " + "; ".join(result["mismatches"]))

    def _fit_b1(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_bus_timing(data)
        self.profile = replace(
            self.profile,
            loop_period_s=_measured(r["loop_period_s"], None, self.id),
            jitter_p95_s=_measured(r["jitter_p95_s"], None, self.id),
        )

        def ms(value: float) -> str:
            return f"{value * 1000:.1f} мс"

        stage.result = {**r, "report": [
            _line("Период цикла (среднее)", ms(r["loop_period_s"])),
            _line("Медиана / p95 / p99", f"{ms(r['p50_s'])} / {ms(r['p95_s'])} / {ms(r['p99_s'])}", r["ok"]),
            _line("Максимальный цикл", ms(r["max_s"])),
            _line("Джиттер p95", ms(r["jitter_p95_s"])),
            _line("Среднее чтение шины", ms(r["read_mean_s"])),
            _line("Опоздавшие циклы (> 2× медианы)", f"{r['late_frames']} из {r['cycles']}", r["late_frames"] == 0),
            _line("Шум положения в покое (СКО)", f"{r['noise_mm'] * 1000:.1f} мкм (критерий < 50)", r["noise_ok"]),
            _line("Шум скорости в покое (СКО)", f"{r['noise_mm_s']:.2f} мм/с (порог трогания 1,5)", r["noise_mm_s"] < 0.5),
        ]}

    def _fit_b7(self, stage: Stage, data: dict[str, Any]) -> None:
        sides = {side: self.profile.side(side) for side in SIDES}
        r = fit_zero(data, {side: float(sides[side].mm_per_pulse.value) for side in SIDES}, {side: sides[side].zero_counts.value for side in SIDES})
        report = []
        for side in SIDES:
            item = r[side]
            self._set_side(side, zero_counts=_measured(int(item["zero_counts"]), None, self.id))
            report.append(_line(f"{_SIDE_LABEL[side]}: ноль энкодера", f"{item['zero_counts']} имп."))
            report.append(_line(f"{_SIDE_LABEL[side]}: положение на упорах по текущему нулю", f"{item['offset_mm']:+.2f} мм", abs(item["offset_mm"]) < 2.0))
            if item["drift_mm"] is not None:
                report.append(_line(f"{_SIDE_LABEL[side]}: сдвиг относительно сохранённого нуля", f"{item['drift_mm']:+.2f} мм", abs(item["drift_mm"]) < 1.0))
        stage.result = {"sides": r, "report": report}

    def _fit_s7(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_height_map(data)
        report = []
        for side in SIDES:
            item = r[side]
            up, down = item["coulomb_up"], item["coulomb_down"]
            self._set_side(
                side,
                gravity_map=_measured([(float(x), float(w)) for x, w in item["map"]], _finite(item["ci95"]), self.id),
                coulomb_up_n=_measured(up.mean, _finite(up.ci95), self.id),
                coulomb_down_n=_measured(down.mean, _finite(down.ci95), self.id),
                stribeck_extra_n=replace(self.profile.side(side).stribeck_extra_n, value=0.0),  # breakaway again: D2 splits it
            )
            weights = [w for _, w in item["map"]]
            report.append(_line(f"{_SIDE_LABEL[side]}: вес по высоте", f"{min(weights):.1f}…{max(weights):.1f} Н ({n_to_kgf(min(weights)):.1f}…{n_to_kgf(max(weights)):.1f} кгс)"))
            report.append(_line(f"{_SIDE_LABEL[side]}: наклон W(x)", f"{item['slope_n_per_m']:+.1f} Н/м"))
            report.append(_line(f"{_SIDE_LABEL[side]}: отклонение от прямой", f"{item['max_deviation_n']:.1f} Н"))
            report.append(_line(f"{_SIDE_LABEL[side]}: трение вверх / вниз", f"{up.mean:.1f} / {down.mean:.1f} Н"))
        stage.result = {
            "heights_mm": r["heights_mm"],
            "sides": {side: {"map": r[side]["map"], "slope_n_per_m": r[side]["slope_n_per_m"], "max_deviation_n": r[side]["max_deviation_n"]} for side in SIDES},
            "report": report,
        }

    def _shifts(self, data: dict[str, Any]) -> dict[Side, dict[str, float]]:
        return weight_shift(data, lambda side, x: self.profile.side(side).weight_n(x), float(self.options["referenceKg"]))

    def _fit_s9(self, stage: Stage, data: dict[str, Any]) -> None:
        shifts = self._shifts(data)
        sides = {side: self.profile.side(side) for side in SIDES}
        scale = fit_scale(shifts, {side: sides[side].n_per_raw_value for side in SIDES}, {side: sides[side].n_per_raw.ci95 for side in SIDES})
        ratio = scale["ratio"]
        report = [
            _line("Сдвиг баланса от груза", f"{scale['delta_n']:.1f} ± {scale['delta_ci95']:.1f} Н при ожидаемых {scale['expected_n']:.1f} Н"),
            _line("Поправка масштаба", f"×{ratio:.3f}", abs(ratio - 1) < 0.2),
        ]
        for side in SIDES:
            item, current = scale["sides"][side], sides[side]
            rescaled = {key: _scaled(getattr(current, key), ratio) for key in _RESCALED}
            self._set_side(side, n_per_raw=_measured(item["n_per_raw"], item["ci95"], self.id), **rescaled)
            side_ratio = f" (по стороне ×{item['side_ratio']:.2f})" if item["side_ratio"] else ""
            report.append(_line(f"{_SIDE_LABEL[side]}: масштаб силы", f"{item['old_n_per_raw']:.4f} → {item['n_per_raw']:.4f} Н/ед.{side_ratio}"))
        self.profile = replace(self.profile, **{key: _scaled(getattr(self.profile, key), ratio) for key in _RESCALED_MACHINE})
        stage.result = {"referenceKg": self.options["referenceKg"], "shifts": shifts, **scale, "report": report}

    def _fit_g1(self, stage: Stage, data: dict[str, Any]) -> None:
        shifts = self._shifts(data)
        r = fit_accuracy(shifts, float(self.options["referenceKg"]))
        report = [
            _line(
                "Измеренная масса груза",
                f"{r['measured_kg']:.2f} ± {r['ci95_kg']:.2f} кг при {r['expected_kg']:.2f} кг (ошибка {r['error_kg']:+.2f} кг, {r['error_pct']:+.1f} %)",
                r["ok"],
            ),
            _line("Допуск", f"±{r['limit_kg']:.2f} кг"),
            *(
                _line(f"{_SIDE_LABEL[side]}: приходится на сторону (справочно)", f"{item['measured_kg']:.2f} кг из {item['expected_kg']:.2f}")
                for side, item in r["sides"].items()
            ),
        ]
        stage.result = {"referenceKg": self.options["referenceKg"], **r, "report": report}
        if not r["ok"]:
            raise ProcedureError(f"статическая точность вне допуска ±{r['limit_kg']:.2f} кг")

    def _fit_d2(self, stage: Stage, data: dict[str, Any]) -> None:
        """Viscous friction; the static window splits into kinetic Coulomb + stiction extra (edges unchanged)."""

        assert self._balance is not None
        r = fit_friction_up(data, self._balance)
        report, sides = [], {}
        for side in SIDES:
            item, current = r[side], self.profile.side(side)
            static_up, static_down = self._balance.coulomb_up[side], self._balance.coulomb_down[side]
            extra = min(max(static_up - item["coulomb_kin_n"], 0.0), static_down)
            if extra < max(STRIBECK_MIN_N, item["coulomb_kin_ci95"] if math.isfinite(item["coulomb_kin_ci95"]) else 0.0):
                extra = 0.0
            values: dict[str, Measured] = {
                "viscous_n_per_mm_s": _measured(item["viscous_n_per_mm_s"], _finite(item["ci95"]), self.id),
                "stribeck_extra_n": _measured(extra, None, self.id),
                # the window edges stay those measured by S3/S7: keep their provenance and time
                "coulomb_up_n": replace(current.coulomb_up_n, value=static_up - extra),
                "coulomb_down_n": replace(current.coulomb_down_n, value=static_down - extra),
            }
            if extra > 0 and item["stribeck_v_mm_s"]:
                values["stribeck_v_mm_s"] = _measured(float(item["stribeck_v_mm_s"]), None, self.id)
            self._set_side(side, **values)
            sides[side] = {key: value for key, value in item.items() if key != "rows"} | {"stribeck_extra_n": extra}
            report.append(_line(f"{_SIDE_LABEL[side]}: вязкое трение", f"{item['viscous_n_per_mm_s']:.3f} ± {item['ci95']:.3f} Н·с/мм", item["viscous_raw"] > -item["ci95"]))
            report.append(_line(f"{_SIDE_LABEL[side]}: трение движения / трогания", f"{static_up - extra:.1f} / {static_up:.1f} Н"))
            stribeck = f"{extra:.1f} Н" + (f", vₛ ≈ {item['stribeck_v_mm_s']:.0f} мм/с" if extra > 0 and item["stribeck_v_mm_s"] else "")
            report.append(_line(f"{_SIDE_LABEL[side]}: добавка трогания (Штрибек)", stribeck if extra > 0 else "нет (трогание ≈ движение)"))
            points = ", ".join(f"{v:.0f} мм/с → {y:+.1f} Н" for v, y in item["points"])
            report.append(_line(f"{_SIDE_LABEL[side]}: сила сверх окна по скоростям", f"{points} (невязка {item['rmse_n']:.1f} Н)"))
        stage.result = {"sides": sides, "report": report}

    def _fit_d4(self, stage: Stage, data: dict[str, Any]) -> None:
        assert self._balance is not None
        viscous = {side: float(self.profile.side(side).viscous_n_per_mm_s.value) for side in SIDES}
        r = fit_moving_mass(data, self._balance, viscous)
        report, sides = [], {}
        for side in SIDES:
            item = r[side]
            if not 5.0 <= item["mass_kg"] <= 400.0:
                raise ProcedureError(f"{side}: оценка подвижной массы {item['mass_kg']:.0f} кг вне правдоподобного диапазона")
            self._set_side(side, moving_mass_kg=_measured(item["mass_kg"], _finite(item["ci95"]), self.id))
            sides[side] = {key: value for key, value in item.items() if key != "rows"}
            report.append(_line(f"{_SIDE_LABEL[side]}: подвижная масса", f"{item['mass_kg']:.1f} ± {item['ci95']:.1f} кг", item["ci95"] < 0.3 * item["mass_kg"]))
            report.append(_line(f"{_SIDE_LABEL[side]}: невязка / задержка", f"{item['rmse_n']:.1f} Н / {item['lag_frames']} кадр. ({item['rows']} точек)"))
        stage.result = {"sides": sides, "report": report}

    def _fit_c3(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_support(data)
        for side in SIDES:
            self._set_side(side, support_raw=_measured(int(r["support_raw"][side]), None, self.id))
        raw = r["support_raw"]
        report = [
            _line("Ток поддержки Л / П", f"{raw['left']} / {raw['right']} ед."),
            _line("Скорость опускания", f"{r['speed_mm_s']:.1f} мм/с (цель 15 ± 5)", r["in_band"]),
            _line("Попыток", str(len(r["trials"]))),
        ]
        stage.result = {**r, "report": report}

    def _fit_b3(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_delay(data)
        self.profile = replace(self.profile, loop_delay_s=_measured(r["delay_s"], _finite(r["ci95"]), self.id))
        frames = f" ≈ {r['frames']:.1f} периода" if r["frames"] else ""
        stage.result = {**r, "report": [
            _line("Задержка команда → движение", f"{r['delay_s'] * 1000:.0f} мс{frames}"),
            _line("Минимум / максимум", f"{r['min_s'] * 1000:.0f} / {r['max_s'] * 1000:.0f} мс", r["ok"]),
            _line("Период кадра во время замера", f"{r['period_s'] * 1000:.0f} мс"),
            _line("Ступеней", str(r["steps"])),
        ]}

    def _fit_b8(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_travel(data)
        self.profile = replace(self.profile, travel_mm=_measured(round(r["travel_mm"], 1), None, self.id))
        soft_ok = self.safety.soft_max_mm <= r["travel_mm"] - 20.0
        stage.result = {**r, "report": [
            _line("Рабочий ход", f"{r['travel_mm']:.0f} мм"),
            _line("Верхний упор Л / П", f"{r['top']['left']:.1f} / {r['top']['right']:.1f} мм", abs(r["skew_mm"]) < 3.0),
            _line(
                "Верхний программный предел",
                f"{self.safety.soft_max_mm:.0f} мм" + ("" if soft_ok else f" — выше хода − 20 мм: уменьшите до {r['travel_mm'] - 20:.0f} мм в «Параметрах»"),
                soft_ok,
            ),
        ]}

    def _fit_x2(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_coupling(data)
        self.profile = replace(self.profile, side_coupling_n_per_mm=_measured(round(r["k_n_per_mm"], 1), r["ci95"], self.id))
        bound = "не менее " if r["lower_bound"] else ""
        report = [_line("Жёсткость связи сторон", f"{bound}{r['k_n_per_mm']:.0f} Н/мм")]
        for side, item in r["sides"].items():
            fit = f", R² {item['r2']:.2f}" if item["r2"] is not None else ", перекос ниже разрешения"
            report.append(_line(f"{_SIDE_LABEL[side]} тянется: перекос до {item['skew_max_mm']:.2f} мм", f"{item['k_n_per_mm']:.0f} Н/мм{fit} ({item['reason']})"))
        report.append(_line("Рекомендуемое «Выравнивание сторон»", f"не более {0.2 * r['k_n_per_mm']:.1f} Н/мм (20 % жёсткости)"))
        stage.result = {**r, "report": report}

    # ---------------------------------------------------------- motion (M)
    def _fit_m1(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_liftoff(data)
        report = []
        for side in SIDES:
            item = r["sides"][side]
            ci = item["ci95"]
            self._set_side(side, liftoff_extra_n=_measured(round(item["extra_n"], 1), _finite(ci) if ci is not None else None, self.id))
            values = " / ".join(f"{v:+.0f}" for v in item["values"])
            friction = self._balance.coulomb_up[side] if self._balance else 0.0
            share = f" ({100 * item['extra_n'] / friction:.0f} % трения)" if friction else ""
            report.append(_line(f"{_SIDE_LABEL[side]}: добавка для отрыва от упоров", f"{item['extra_n']:.1f} Н{share}", item["extra_n"] < 1.5 * friction if friction else None))
            report.append(_line(f"{_SIDE_LABEL[side]}: по повторам (первый — после стоянки)", f"{values} Н"))
        stage.result = {**r, "report": report}

    def _fit_m2(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_travel_feed(data)
        target = r["speed_mm_s"]
        report = []
        for key, label, path in (("up", "вверх", "travel_extra_up_n"), ("down", "вниз", "travel_extra_down_n")):
            item = r[key]
            for side in SIDES:
                value = item["sides"][side]
                self._set_side(side, **{path: _measured(round(value["extra_n"], 1), _finite(value["ci95"]), self.id)})
            extras = " / ".join(f"{item['sides'][side]['extra_n']:+.1f}" for side in SIDES)
            report.append(_line(f"Сила сверх окна {label} (Л / П)", f"{extras} Н"))
            rms = item["speed_rms_err"]
            report.append(_line(
                f"Скорость {label}: средняя / ошибка (СКО)",
                f"{item['speed_mean']:.1f} мм/с / {rms:.1f} мм/с (цель {target:.0f})" if rms is not None else f"{item['speed_mean']:.1f} мм/с",
                rms is None or rms < 0.4 * target,
            ))
        stage.result = {**r, "report": report}

    def _fit_m3(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_braking(data)
        self.profile = replace(
            self.profile,
            brake_lag_s=_measured(round(r["lag_s"], 3), None, self.id),
            brake_decel_up_mm_s2=_measured(round(r["decel_up_mm_s2"], 1) if r["decel_up_mm_s2"] else None, None, self.id),
            brake_decel_down_mm_s2=_measured(round(r["decel_down_mm_s2"], 1) if r["decel_down_mm_s2"] else None, None, self.id),
        )

        def decel(value: float | None) -> str:
            return f"{value:.0f} мм/с²" if value else "мгновенно (путь только от задержки)"

        report = [
            _line("Задержка торможения", f"{r['lag_s'] * 1000:.0f} мс"),
            _line("Замедление вверх / вниз", f"{decel(r['decel_up_mm_s2'])} / {decel(r['decel_down_mm_s2'])}"),
        ]
        for run in r["runs"]:
            report.append(_line(
                f"{'↑' if run['direction'] > 0 else '↓'} {run['v_mm_s']:.0f} мм/с",
                f"путь {run['distance_mm']:.1f} мм за {run['time_s']:.2f} с",
                run["distance_mm"] < 30.0,
            ))
        stage.result = {**r, "report": report}

    def _fit_m4(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_motion_check(data)
        report = [
            _line(
                f"→ {move['target_mm']:.0f} мм",
                f"стоп {move['stop_mm']:.1f} мм ({move['error_mm']:+.1f}), перелёт {move['overshoot_mm']:.1f}, перекос {move['skew_mm']:.1f} мм, {move['time_s']:.1f} с",
                abs(move["error_mm"]) <= 5.0 and move["skew_mm"] <= 5.0,
            )
            for move in r["moves"]
        ]
        report.append(_line("Наибольшая ошибка остановки", f"{r['max_error_mm']:.1f} мм (допуск 5)", r["ok_stop"]))
        report.append(_line("Наибольший перекос сторон", f"{r['max_skew_mm']:.1f} мм (допуск 5)", r["ok_skew"]))
        stage.result = {**r, "report": report}
        if not r["ok"]:
            raise ProcedureError(f"перемещение вне допуска: ошибка {r['max_error_mm']:.1f} мм, перекос {r['max_skew_mm']:.1f} мм — повторите M2/M3")

    def _fit_q1(self, stage: Stage, data: dict[str, Any]) -> None:
        r = fit_daily(data, self.profile)
        d = r["deviation"]

        def pct(value: float) -> str:
            return f"{100 * value:+.1f} %"

        report = [
            _line("Настройки приводов", "в порядке" if r["config"]["ok"] else "; ".join(r["config"]["mismatches"]), r["config"]["ok"]),
            _line("Положение на упорах Л / П", f"{r['rest_mm']['left']:.1f} / {r['rest_mm']['right']:.1f} мм", r["zero_ok"]),
            _line("Вес грифа (сумма сторон)", f"{r['weight_n']:.1f} Н против {r['weight_profile_n']:.1f} Н ({pct(d['weight'])})", abs(d["weight"]) <= 0.07),
            _line("Трение вверх", f"{r['up_n']:.1f} Н против {r['up_profile_n']:.1f} Н ({pct(d['up'])})", abs(d["up"]) <= 0.25),
            _line("Трение вниз", f"{r['down_n']:.1f} Н против {r['down_profile_n']:.1f} Н ({pct(d['down'])})", abs(d["down"]) <= 0.25),
        ]
        if r["warnings"] and r["ok"]:
            report.append(_line("Рекомендация", "повторите S3 (и S7, D2): " + "; ".join(r["warnings"]), False))
        stage.result = {key: value for key, value in r.items() if key != "config"} | {"report": report}
        if not r["ok"]:
            raise ProcedureError("ежедневная проверка не пройдена: " + "; ".join(r["failures"]))

    def _finish(self, status: SessionStatus, reason: str | None) -> None:
        self.status = status
        self.reason = reason
        self.finished_at = datetime.now(UTC)
        self._finished_monotonic = time.monotonic()
        _set_profiles(self.drives, self.base)  # the candidate is not active until saved

    # -------------------------------------------------------------- results
    def changes(self) -> list[dict[str, Any]]:
        done = [stage.code for stage in self.stages if stage.status == "done"]
        paths = list(dict.fromkeys(path for code in done for path in (*BY_CODE[code].produces, *EXTRA_PATHS.get(code, ()))))
        items = []
        for path in paths:
            parts = path.split(".")
            side, key = (parts[0], parts[1]) if len(parts) == 2 else (None, parts[0])
            spec = BY_KEY[("side" if side else "machine", key)]
            old, new = _path_value(self.base, path), _path_value(self.profile, path)
            items.append({
                "scope": spec.scope, "key": key, "side": side, "label": spec.label, "unit": spec.unit, "kind": spec.kind,
                "old": _measured_payload(old, spec.kind), "new": _measured_payload(new, spec.kind),
                "changed": old.value != new.value or old.provenance != new.provenance,
            })
        return items

    def _log_payload(self) -> dict[str, list[float]]:
        log = self.log
        stride = max(1, math.ceil(len(log) / LOG_POINTS))
        rows = log[::stride]
        if log and rows[-1] is not log[-1]:
            rows.append(log[-1])
        t0 = log[0][0] if log else 0.0
        names = ("t", "xL", "xR", "vL", "vR", "fL", "fR")
        return {name: [round(row[i] - (t0 if i == 0 else 0.0), 3 if i == 0 else 2) for row in rows] for i, name in enumerate(names)}

    def to_payload(self) -> dict[str, Any]:
        end = self._finished_monotonic or time.monotonic()
        done = sum(1 for stage in self.stages if stage.status == "done")
        current = self.current_stage
        progress = 1.0 if self.status == "done" else (done + (current.progress if current.status == "running" else 0.0)) / len(self.stages)
        changes = self.changes() if self.status == "done" else []
        return {
            "id": self.id,
            "code": self.code,
            "title": self.title,
            "status": self.status,
            "reason": self.reason,
            "startedAt": self.started_at.isoformat(),
            "finishedAt": self.finished_at.isoformat() if self.finished_at else None,
            "elapsedS": round(end - self._started_monotonic, 1),
            "progress": round(progress, 3),
            "currentStage": current.code if self.running else None,
            "note": current.note if self.running else "",
            "prompt": self.prompt.to_dict() if self.prompt else None,
            "deadManHeld": self._dead_man_held() if self.running else False,
            "stages": [stage.to_payload() for stage in self.stages],
            "changes": changes,
            "hasChanges": any(item["changed"] for item in changes),
            "savedVersion": self.saved_version,
            "log": self._log_payload(),
        }
