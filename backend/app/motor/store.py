"""Versioned storage of the active motor profile (plan 14 §5.4)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.motor import MachineProfileRecord
from app.models.settings import AppSetting
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, Tunables

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


def save_version(session: Session, bundle: ProfileBundle, *, note: str | None = None, source_run_id: str | None = None) -> int:
    version = int(session.scalar(select(func.max(MachineProfileRecord.version))) or 0) + 1
    for record in session.scalars(select(MachineProfileRecord).where(MachineProfileRecord.active.is_(True))):
        record.active = False
    payload = replace(bundle, machine=replace(bundle.machine, version=version)).to_dict()
    session.add(MachineProfileRecord(version=version, payload=payload, note=note, source_run_id=source_run_id, active=True))
    session.flush()
    return version


def activate(session: Session, version: int) -> None:
    target = session.scalars(select(MachineProfileRecord).where(MachineProfileRecord.version == version)).first()
    if target is None:
        raise LookupError(f"Версия профиля {version} не найдена")
    for record in session.scalars(select(MachineProfileRecord).where(MachineProfileRecord.active.is_(True))):
        record.active = False
    target.active = True
    session.flush()
