"""Calibration catalog and dependency graph (plan 15 §2–3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.motor.profile import MachineProfile

Status = Literal["actual", "missing", "planned"]


@dataclass(frozen=True)
class CalibrationSpec:
    code: str
    group: str
    title: str
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    implemented: bool
    hardware: bool = True  # needs the machine and an operator (dead-man)


CATALOG: tuple[CalibrationSpec, ...] = (
    CalibrationSpec("B0", "B", "Конфигурация привода", (), (), False),
    CalibrationSpec("B1", "B", "Тайминг шины", ("B0",), ("loop_period_s", "jitter_p95_s"), False),
    CalibrationSpec("B5", "B", "Направление мотора и энкодера", ("B0",), ("left.direction_sign", "right.direction_sign"), True),
    CalibrationSpec("B7", "B", "Абсолютный ноль", ("B5",), ("left.zero_counts", "right.zero_counts"), False),
    CalibrationSpec("S3", "S", "Окно невесомости: трогание вверх/вниз, баланс, сухое трение", ("B5",), ("left.gravity_map", "left.coulomb_up_n", "left.coulomb_down_n", "right.gravity_map", "right.coulomb_up_n", "right.coulomb_down_n"), True),
    CalibrationSpec("S7", "S", "Карта по высоте", ("S3", "B7"), ("left.gravity_map", "right.gravity_map"), False),
    CalibrationSpec("S9", "S", "Шкала силы по эталонному грузу", ("S3",), ("left.n_per_raw", "right.n_per_raw"), False),
    CalibrationSpec("D2", "D", "Трение в движении вверх", ("S3",), ("left.viscous_n_per_mm_s", "right.viscous_n_per_mm_s"), False),
    CalibrationSpec("D4", "D", "Приведённая масса", ("D2",), ("left.moving_mass_kg", "right.moving_mass_kg"), False),
    CalibrationSpec("C1", "C", "Запас устойчивости удержания (relay)", ("S3",), ("hold_ultimate_k_n_per_mm", "hold_ultimate_period_s"), True),
    CalibrationSpec("C3", "C", "Опускание поддержкой", ("S3",), ("left.support_raw", "right.support_raw"), False),
    CalibrationSpec("G1", "G", "Статическая точность нагрузки", ("S9", "C1"), (), False),
)
BY_CODE = {spec.code: spec for spec in CATALOG}


def _field(profile: MachineProfile, path: str):  # noqa: ANN202
    target: object = profile
    for part in path.split("."):
        target = getattr(target, part)
    return target


def status(profile: MachineProfile, spec: CalibrationSpec) -> Status:
    if not spec.implemented:
        return "planned"
    if spec.produces and all(_field(profile, path).provenance == "measured" for path in spec.produces):
        return "actual"
    return "missing"


def graph(profile: MachineProfile) -> list[dict[str, object]]:
    return [
        {
            "code": spec.code,
            "group": spec.group,
            "title": spec.title,
            "requires": list(spec.requires),
            "produces": list(spec.produces),
            "implemented": spec.implemented,
            "status": status(profile, spec),
        }
        for spec in CATALOG
    ]
