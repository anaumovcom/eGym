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
    fit_bus_timing,
    fit_config,
    fit_zero,
)
from app.motor.calibration.procedures.direction import direction_test
from app.motor.calibration.procedures.dynamics import fit_friction_up, fit_moving_mass, friction_up, moving_mass
from app.motor.calibration.procedures.heightmap import fit_height_map, height_map, map_heights
from app.motor.calibration.procedures.motion import Balance
from app.motor.calibration.procedures.reference import fit_accuracy, fit_scale, loaded_window, weight_shift
from app.motor.calibration.procedures.relay import fit_relay, relay_test
from app.motor.calibration.procedures.statics import balance_and_friction, fit_balance
from app.motor.calibration.procedures.support import fit_support, support_descent
from app.motor.calibration.runner import (
    CalibrationRunner,
    Frame,
    Procedure,
    ProcedureEnvelope,
    ProcedureError,
    RunResult,
)
from app.motor.calibration.wizard import DIRECTION_ENVELOPE, _measured
from app.motor.drive.protocol import TorqueDrive
from app.motor.parameters import BY_KEY, _measured_payload
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.units import SIDES, Side, n_to_kgf

SessionStatus = Literal["running", "done", "aborted", "failed"]
StageStatus = Literal["pending", "running", "done", "aborted", "failed"]
DEAD_MAN_TIMEOUT_S = 0.6
ON_STOPS_MM = 15.0
RELAY_STEPS_N = (6.0, 12.0)
LOG_POINTS = 600
REFERENCE_KG = (2.0, 60.0)
MAX_S = {"S7": 1500.0}
_RESCALED = ("gravity_map", "coulomb_up_n", "coulomb_down_n", "viscous_n_per_mm_s", "stribeck_extra_n", "moving_mass_kg")
EXTRA_PATHS = {
    "S3": ("left.stribeck_extra_n", "right.stribeck_extra_n"),
    "S7": ("left.coulomb_up_n", "left.coulomb_down_n", "right.coulomb_up_n", "right.coulomb_down_n"),
    "S9": (*(f"{side}.{key}" for side in SIDES for key in _RESCALED), "hold_ultimate_k_n_per_mm"),
}
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
        raise ValueError(code)

    def _top_mm(self) -> float:
        return min(float(self.profile.travel_mm.value), self.safety.soft_max_mm) - 80.0

    def _profile_window(self) -> dict[Side, tuple[float, float]]:
        window = {}
        for side in SIDES:
            profile = self.profile.side(side)
            weight = profile.weight_n(10.0)
            window[side] = (weight - float(profile.coulomb_down_n.value), weight + float(profile.coulomb_up_n.value))
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
            stage.result = {"sides": data["sides"]}
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
                    stribeck_extra_n=_measured(0.0, None, self.id),
                ))
            self._window = {
                side: (estimate.weight_n[side].mean - estimate.coulomb_down_n[side].mean, estimate.weight_n[side].mean + estimate.coulomb_up_n[side].mean) for side in SIDES
            }
            stage.result = estimate.to_dict()
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
            stage.result = {**relay, "relay_n": relay_n}
            return False
        fitter = getattr(self, f"_fit_{stage.code.lower()}", None)
        if fitter is None:
            raise ValueError(stage.code)
        fitter(stage, data)
        if stage.code not in ("B0", "B1"):
            self._bar_up = False  # these procedures land the bar on the stops at the end
        return False

    def _set_side(self, side: Side, **values: Measured) -> None:
        self.profile = self.profile.with_side(side, replace(self.profile.side(side), **values))

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
        report = []
        for side in SIDES:
            item, current = scale[side], sides[side]
            ratio = item["ratio"]
            rescaled = {key: _scaled(getattr(current, key), ratio) for key in _RESCALED}
            self._set_side(side, n_per_raw=_measured(item["n_per_raw"], item["ci95"], self.id), **rescaled)
            report.append(_line(f"{_SIDE_LABEL[side]}: ΔW от груза", f"{shifts[side]['delta_n']:.1f} Н при ожидаемых {shifts[side]['expected_n']:.1f} Н"))
            report.append(_line(f"{_SIDE_LABEL[side]}: масштаб силы", f"{item['old_n_per_raw']:.4f} → {item['n_per_raw']:.4f} Н/ед. (×{ratio:.3f})", abs(ratio - 1) < 0.2))
        mean_ratio = sum(scale[side]["ratio"] for side in SIDES) / len(SIDES)
        self.profile = replace(self.profile, hold_ultimate_k_n_per_mm=_scaled(self.profile.hold_ultimate_k_n_per_mm, mean_ratio))
        stage.result = {"referenceKg": self.options["referenceKg"], "shifts": shifts, "sides": scale, "report": report}

    def _fit_g1(self, stage: Stage, data: dict[str, Any]) -> None:
        shifts = self._shifts(data)
        r = fit_accuracy(shifts, float(self.options["referenceKg"]))
        report = [
            _line(
                f"{_SIDE_LABEL[side]}: груз на стороне",
                f"{item['measured_kg']:.2f} кг при {item['expected_kg']:.2f} кг (ошибка {item['error_kg']:+.2f} кг, {item['error_pct']:+.1f}%)",
                item["ok"],
            )
            for side, item in r["sides"].items()
        ]
        report.append(_line("Допуск", f"±{r['limit_kg']:.2f} кг", r["ok"]))
        stage.result = {"referenceKg": self.options["referenceKg"], **r, "report": report}
        if not r["ok"]:
            raise ProcedureError(f"статическая точность вне допуска ±{r['limit_kg']:.2f} кг")

    def _fit_d2(self, stage: Stage, data: dict[str, Any]) -> None:
        assert self._balance is not None
        r = fit_friction_up(data, self._balance)
        report, sides = [], {}
        for side in SIDES:
            item = r[side]
            self._set_side(side, viscous_n_per_mm_s=_measured(item["viscous_n_per_mm_s"], _finite(item["ci95"]), self.id))
            sides[side] = {key: value for key, value in item.items() if key != "rows"}
            report.append(_line(f"{_SIDE_LABEL[side]}: вязкое трение", f"{item['viscous_n_per_mm_s']:.3f} ± {item['ci95']:.3f} Н·с/мм", item["viscous_raw"] > -item["ci95"]))
            report.append(_line(f"{_SIDE_LABEL[side]}: кинетическое трение (статическое)", f"{item['coulomb_kin_n']:.1f} Н ({self._balance.coulomb_up[side]:.1f} Н)"))
            report.append(_line(f"{_SIDE_LABEL[side]}: невязка / задержка", f"{item['rmse_n']:.1f} Н / {item['lag_frames']} кадр. ({item['rows']} точек)"))
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

    def _finish(self, status: SessionStatus, reason: str | None) -> None:
        self.status = status
        self.reason = reason
        self.finished_at = datetime.now(UTC)
        self._finished_monotonic = time.monotonic()
        _set_profiles(self.drives, self.base)  # the candidate is not active until saved

    # -------------------------------------------------------------- results
    def changes(self) -> list[dict[str, Any]]:
        done = [stage.code for stage in self.stages if stage.status == "done"]
        paths = [path for code in done for path in (*BY_CODE[code].produces, *EXTRA_PATHS.get(code, ()))]
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
            "deadManHeld": self._dead_man_held() if self.running else False,
            "stages": [stage.to_payload() for stage in self.stages],
            "changes": changes,
            "hasChanges": any(item["changed"] for item in changes),
            "savedVersion": self.saved_version,
            "log": self._log_payload(),
        }
