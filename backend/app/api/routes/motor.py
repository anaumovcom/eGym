"""Motor control v2 API: profile versions and the calibration catalog (plan 14 §8, plan 15 §6)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models.motor import MachineProfileRecord
from app.motor import store
from app.motor.calibration.graph import graph
from app.services.hardware_runtime import hardware_runtime

router = APIRouter(prefix="/motor")


@router.get("/profile")
def get_profile(session: Session = Depends(get_session)) -> dict[str, object]:
    bundle = store.load_active(session)
    return {**bundle.to_dict(), "runtimeVersion": hardware_runtime.profile.version}


@router.get("/profile/versions")
def list_versions(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(MachineProfileRecord).order_by(MachineProfileRecord.version.desc())).all()
    return [
        {"version": row.version, "active": row.active, "note": row.note, "sourceRunId": row.source_run_id, "createdAt": row.created_at.isoformat() if row.created_at else None}
        for row in rows
    ]


@router.post("/profile/{version}/activate")
def activate_version(version: int, session: Session = Depends(get_session)) -> dict[str, object]:
    if not hardware_runtime.state.service_mode:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Смена профиля доступна только в сервисном режиме")
    try:
        store.activate(session, version)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    session.commit()
    return {"version": version, "active": True, "appliedAfterRestart": True}


@router.get("/calibrations")
def list_calibrations(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    return graph(store.load_active(session).machine)
