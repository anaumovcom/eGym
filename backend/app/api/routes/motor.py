"""Motor control v2 API: profile versions, calibration runs and parameters (plan 14 §8, plan 15 §6)."""

from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models.motor import CalibrationRun, MachineProfileRecord
from app.motor import store
from app.motor.calibration.graph import CATALOG, graph
from app.motor.calibration.session import CalibrationSession
from app.motor.parameters import apply_changes, describe
from app.services.hardware_runtime import hardware_runtime

router = APIRouter(prefix="/motor")


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _require_service_mode() -> None:
    if not hardware_runtime.state.service_mode:
        raise _conflict("Доступно только в сервисном режиме")


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


VERIFICATION_CODES = tuple(spec.code for spec in CATALOG if spec.implemented and not spec.produces)


def _verified(session: Session) -> dict[str, str]:
    """code → finish time of the latest run, if it passed (checks without parameters: B0, G1)."""

    verified: dict[str, str] = {}
    for code in VERIFICATION_CODES:
        row = session.scalars(
            select(CalibrationRun).where(CalibrationRun.procedure == code).order_by(CalibrationRun.started_at.desc()).limit(1)
        ).first()
        if row is not None and row.status in {"done", "saved"} and row.finished_at is not None:
            verified[code] = row.finished_at.isoformat()
    return verified


@router.get("/calibrations")
def list_calibrations(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    _persist_finished(session)
    return graph(store.load_active(session).machine, _verified(session))


# ------------------------------------------------------------------ calibration runs
class CalibrationStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: Literal["WIZARD", "B0", "B1", "B5", "B7", "S3", "S7", "S9", "D2", "D4", "C1", "C3", "G1"]
    reference_kg: float | None = Field(None, alias="referenceKg", ge=2, le=60)


def _persist_run(session: Session, run: CalibrationSession, run_status: str) -> None:
    row = session.get(CalibrationRun, run.id)
    if row is None:
        row = CalibrationRun(id=run.id, procedure=run.code, started_at=run.started_at, status=run_status)
        session.add(row)
    row.status = run_status
    row.finished_at = run.finished_at
    row.estimate = {stage.code: stage.result for stage in run.stages if stage.result}
    row.metrics = {
        "title": run.title,
        "reason": run.reason,
        "savedVersion": run.saved_version,
        "stages": [{"code": stage.code, "status": stage.status, "reason": stage.reason} for stage in run.stages],
        "changes": run.changes() if run.status == "done" else [],
    }
    run.persisted_status = run_status


def _persist_finished(session: Session) -> None:
    run = hardware_runtime.calibration
    if run is not None and not run.running and run.persisted_status is None:
        _persist_run(session, run, run.status)
        session.commit()


@router.get("/calibration/session")
def calibration_session(code: str = Query("WIZARD", max_length=16)) -> dict[str, Any]:
    return hardware_runtime.calibration_payload(code)


@router.post("/calibration/start")
def start_calibration(payload: CalibrationStartRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    _persist_finished(session)
    try:
        hardware_runtime.start_calibration(payload.code, {"referenceKg": payload.reference_kg})
    except PermissionError as error:
        raise _conflict(str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return hardware_runtime.calibration_payload(payload.code)


@router.post("/calibration/keepalive")
def calibration_keepalive() -> dict[str, bool]:
    """Dead-man: the UI posts this while the operator holds the button; silence > 0.6 s aborts to support."""

    return {"running": hardware_runtime.calibration_keepalive()}


@router.post("/calibration/abort")
def abort_calibration(session: Session = Depends(get_session)) -> dict[str, Any]:
    hardware_runtime.abort_calibration()
    _persist_finished(session)
    run = hardware_runtime.calibration
    return {"session": run.to_payload() if run is not None else None}


@router.post("/calibration/accept")
def accept_calibration(session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_service_mode()
    run = hardware_runtime.calibration
    if run is None or run.status != "done":
        raise _conflict("Нет завершённой калибровки для сохранения")
    if run.saved_version is not None:
        raise _conflict(f"Результат уже сохранён (версия {run.saved_version})")
    if not any(item["changed"] for item in run.changes()):
        raise _conflict("Новых значений нет")
    bundle = store.load_active(session)
    version = store.save_version(session, replace(bundle, machine=run.profile), note=f"Калибровка {run.code}", source_run_id=run.id)
    run.saved_version = version
    _persist_run(session, run, "saved")
    session.commit()
    try:
        hardware_runtime.apply_profile(replace(run.profile, version=version))
    except PermissionError as error:
        raise _conflict(f"Профиль v{version} сохранён, но не применён: {error}") from error
    return {"version": version, "session": run.to_payload()}


@router.post("/calibration/discard")
def discard_calibration(session: Session = Depends(get_session)) -> dict[str, bool]:
    run = hardware_runtime.calibration
    if run is not None and not run.running and run.saved_version is None:
        changed = run.status == "done" and any(item["changed"] for item in run.changes())
        _persist_run(session, run, "discarded" if changed else run.status)
        session.commit()
    try:
        hardware_runtime.discard_calibration()
    except PermissionError as error:
        raise _conflict(str(error)) from error
    return {"ok": True}


@router.get("/calibration/runs")
def calibration_runs(session: Session = Depends(get_session), limit: int = Query(30, ge=1, le=200)) -> list[dict[str, Any]]:
    rows = session.scalars(select(CalibrationRun).order_by(CalibrationRun.started_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "code": row.procedure,
            "title": (row.metrics or {}).get("title"),
            "status": row.status,
            "startedAt": row.started_at.isoformat(),
            "finishedAt": row.finished_at.isoformat() if row.finished_at else None,
            "reason": (row.metrics or {}).get("reason"),
            "savedVersion": (row.metrics or {}).get("savedVersion"),
            "changes": (row.metrics or {}).get("changes", []),
        }
        for row in rows
    ]


# ------------------------------------------------------------------ parameters
class ParameterChange(BaseModel):
    scope: Literal["side", "machine", "tunables", "envelope"]
    key: str = Field(max_length=64)
    side: Literal["left", "right"] | None = None
    value: float | int | bool


class ParametersUpdate(BaseModel):
    changes: list[ParameterChange] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=200)


@router.get("/parameters")
def get_parameters(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {**describe(store.load_active(session)), "runtimeVersion": hardware_runtime.profile.version}


@router.put("/parameters")
def update_parameters(payload: ParametersUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_service_mode()
    if hardware_runtime.calibration is not None and hardware_runtime.calibration.running:
        raise _conflict("Идёт калибровка — параметры нельзя менять")
    bundle = store.load_active(session)
    try:
        updated = apply_changes(bundle, [change.model_dump() for change in payload.changes])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    version = store.save_version(session, updated, note=payload.note or "Ручная настройка параметров")
    session.commit()
    try:
        hardware_runtime.apply_profile(replace(updated.machine, version=version), updated.envelope)
    except PermissionError as error:
        raise _conflict(f"Профиль v{version} сохранён, но не применён: {error}") from error
    saved = store.load_active(session)
    return {**describe(saved), "runtimeVersion": hardware_runtime.profile.version}
