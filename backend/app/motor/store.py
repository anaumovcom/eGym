"""Versioned storage of the active motor profile (plan 14 §5.4)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.motor import MachineProfileRecord
from app.models.settings import AppSetting
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, Tunables
from app.motor.units import SIDES

LEGACY_PARAMETERS_KEY = "hardware.tuning.parameters"


@dataclass(frozen=True)
class ProfileBundle:
    machine: MachineProfile = field(default_factory=MachineProfile)
    tunables: Tunables = field(default_factory=Tunables)
    envelope: SafetyEnvelope = field(default_factory=SafetyEnvelope)

    def to_dict(self) -> dict[str, object]:
        return {"machine": self.machine.to_dict(), "tunables": self.tunables.to_dict(), "envelope": self.envelope.to_dict()}

    @staticmethod
    def from_dict(data: dict[str, object]) -> ProfileBundle:
        return ProfileBundle(
            MachineProfile.from_dict(data.get("machine", {})),  # type: ignore[arg-type]
            Tunables.from_dict(data.get("tunables", {})),  # type: ignore[arg-type]
            SafetyEnvelope.from_dict(data.get("envelope", {})),  # type: ignore[arg-type]
        )


def _legacy_directions(session: Session) -> MachineProfile:
    """Before the first v2 calibration keep the v1 screw inversion flags: support must push up."""

    profile = MachineProfile()
    setting = session.scalars(select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key == LEGACY_PARAMETERS_KEY)).first()
    values = setting.value if setting is not None and isinstance(setting.value, dict) else {}
    for side in ("left", "right"):
        if values.get(f"screw.{side}DirectionInverted"):
            profile = profile.with_side(side, replace(profile.side(side), direction_sign=Measured(-1, None, "manual")))
    return profile


def load_active(session: Session) -> ProfileBundle:
    record = session.scalars(select(MachineProfileRecord).where(MachineProfileRecord.active.is_(True)).order_by(MachineProfileRecord.version.desc())).first()
    if record is None:
        return ProfileBundle(machine=_legacy_directions(session))
    bundle = ProfileBundle.from_dict(record.payload)
    return replace(bundle, machine=replace(bundle.machine, version=record.version))


def save_version(
    session: Session, bundle: ProfileBundle, *, note: str | None = None, source_run_id: str | None = None, extra: dict[str, object] | None = None,
) -> int:
    version = int(session.scalar(select(func.max(MachineProfileRecord.version))) or 0) + 1
    for record in session.scalars(select(MachineProfileRecord).where(MachineProfileRecord.active.is_(True))):
        record.active = False
    payload = {**replace(bundle, machine=replace(bundle.machine, version=version)).to_dict(), **(extra or {})}
    session.add(MachineProfileRecord(version=version, payload=payload, note=note, source_run_id=source_run_id, active=True))
    session.flush()
    return version


ResetScope = Literal["calibrations", "parameters", "all"]
# commissioning, not calibration: motor direction (support must push up), the encoder zero, the screw pitch
RESET_KEEPS_SIDE = ("direction_sign", "zero_counts", "mm_per_pulse")
RESET_NOTES: dict[str, str] = {
    "calibrations": "Сброс калибровок",
    "parameters": "Сброс параметров",
    "all": "Сброс калибровок и параметров",
}
RESET_AT_KEY = "calibrationsResetAt"


def reset_bundle(bundle: ProfileBundle, scope: ResetScope) -> ProfileBundle:
    """Calibrations → MachineProfile defaults (keeping ``RESET_KEEPS_SIDE``); parameters → Tunables/SafetyEnvelope defaults."""

    machine, tunables, envelope = bundle.machine, bundle.tunables, bundle.envelope
    if scope in ("calibrations", "all"):
        fresh = MachineProfile()
        for side in SIDES:
            kept = {key: getattr(machine.side(side), key) for key in RESET_KEEPS_SIDE}
            fresh = fresh.with_side(side, replace(fresh.side(side), **kept))
        machine = replace(fresh, version=machine.version)
    if scope in ("parameters", "all"):
        tunables, envelope = Tunables(), SafetyEnvelope()
    return ProfileBundle(machine, tunables, envelope)


def reset(session: Session, scope: ResetScope) -> int:
    """A new active version with the defaults; earlier versions stay (activate one to undo)."""

    extra = {RESET_AT_KEY: datetime.now(UTC).isoformat()} if scope != "parameters" else None
    return save_version(session, reset_bundle(load_active(session), scope), note=RESET_NOTES[scope], extra=extra)


def calibrations_reset_at(session: Session) -> datetime | None:
    """Time of the latest calibration reset: checks (B0, G1, Q1) finished before it no longer count."""

    for record in session.scalars(select(MachineProfileRecord).order_by(MachineProfileRecord.version.desc())):
        value = (record.payload or {}).get(RESET_AT_KEY)
        if isinstance(value, str):
            return datetime.fromisoformat(value)
    return None


def activate(session: Session, version: int) -> None:
    target = session.scalars(select(MachineProfileRecord).where(MachineProfileRecord.version == version)).first()
    if target is None:
        raise LookupError(f"Версия профиля {version} не найдена")
    for record in session.scalars(select(MachineProfileRecord).where(MachineProfileRecord.active.is_(True))):
        record.active = False
    target.active = True
    session.flush()
