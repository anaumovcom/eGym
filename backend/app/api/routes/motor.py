"""Motor control v2 API: profile versions, calibration runs and parameters (plan 14 §8, plan 15 §6)."""

import threading
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, defer

from app.api.dependencies import get_session
from app.models.motor import CalibrationRun, MachineProfileRecord, MotorSetObservation
from app.motor import store
from app.motor.calibration.fault_rehearsal import fault_rehearsal
from app.motor.calibration.graph import (
    AUTO_STAGES,
    BY_CODE,
    CATALOG,
    MOTION_CHECKS,
    RUNNABLE,
    WIZARD_STAGES,
    CheckResult,
    graph,
    motion_check_settings,
)
from app.motor.calibration.graph import status as calibration_status
from app.motor.calibration.measurement_plots import PLOT_ROOT, PlotStage, plot_result
from app.motor.calibration.session import CalibrationSession
from app.motor.calibration.speed_study import speed_study
from app.motor.parameters import apply_changes, describe
from app.services.exercise_library import get_imported_exercise
from app.services.hardware_runtime import hardware_runtime

router = APIRouter(prefix="/motor")

# Coordinate profile writes with calibration starts, acceptance and archival. SQL runs outside
# the separate motor lock so it cannot block a control tick or the emergency stop.
_calibration_route_lock = threading.RLock()


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _require_service_mode() -> None:
    if not hardware_runtime.state.service_mode:
        raise _conflict("Доступно только в сервисном режиме")


@router.get("/profile")
def get_profile(session: Session = Depends(get_session)) -> dict[str, object]:
    bundle = store.load_active(session)
    return {**bundle.to_dict(), "runtimeVersion": hardware_runtime.profile.version}


def _observation_summary(row: MotorSetObservation) -> dict[str, Any]:
    exercise = get_imported_exercise(row.exercise_slug) if row.exercise_slug else None
    return {"id": row.id, "startedAt": _utc(row.started_at).isoformat(), "source": row.source,
            "profileVersion": row.profile_version, "exerciseSlug": row.exercise_slug, "exerciseName": exercise.name_ru if exercise else None,
            "status": row.status, **row.summary}


@router.get("/exercise-observations")
def exercise_observations(source: Literal["modbus", "canopen", "twin"] | None = None, limit: int = Query(30, ge=1, le=100),
                          offset: int = Query(0, ge=0), session: Session = Depends(get_session)) -> dict[str, Any]:
    query = select(MotorSetObservation).options(defer(MotorSetObservation.trace))
    if source:
        query = query.where(MotorSetObservation.source == source)
    rows = session.scalars(query.order_by(MotorSetObservation.started_at.desc(), MotorSetObservation.id.desc())
                           .offset(offset).limit(limit + 1)).all()
    return {"items": [_observation_summary(row) for row in rows[:limit]], "hasMore": len(rows) > limit}


@router.get("/exercise-observations/{record_id}")
def exercise_observation(record_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.get(MotorSetObservation, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Запись подхода не найдена")
    return {**_observation_summary(row), "schemaVersion": 1, "trace": row.trace,
            "traceUnits": {"t": "s since set start", "xL": "mm", "xR": "mm", "vL": "mm/s", "vR": "mm/s",
                           "fL": "N (drive feedback)", "fR": "N (drive feedback)", "rawL": "PA_12C", "rawR": "PA_12C",
                           "loadKg": "kg (applied setpoint)", "targetKg": "kg (requested)", "segment": "continuous working interval"}}


@router.get("/profile/versions")
def list_versions(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(MachineProfileRecord).order_by(MachineProfileRecord.version.desc())).all()
    return [
        {"version": row.version, "active": row.active, "note": row.note, "sourceRunId": row.source_run_id, "createdAt": row.created_at.isoformat() if row.created_at else None}
        for row in rows
    ]


@router.post("/profile/{version}/activate")
def activate_version(version: int, session: Session = Depends(get_session)) -> dict[str, object]:
    with _calibration_route_lock:
        if not hardware_runtime.state.service_mode:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Смена профиля доступна только в сервисном режиме")
        try:
            store.activate(session, version)
        except LookupError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        session.commit()
    return {"version": version, "active": True, "appliedAfterRestart": True}


VERIFICATION_CODES = tuple(spec.code for spec in CATALOG if spec.implemented and not spec.produces)
CHECK_FAULTS = ("skew", "telemetry", "drive", "fault", "overspeed", "machine_speed", "position", "move_speed")


def _utc(stamp: datetime) -> datetime:
    return stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _checks(session: Session, codes: tuple[str, ...] = VERIFICATION_CODES) -> dict[str, CheckResult]:
    """code → latest finished run of the checks without parameters (B0, G1, Q1): passed or failed."""

    checks: dict[str, CheckResult] = {}
    since = store.calibrations_reset_at(session)
    for code in codes:
        source = CalibrationRun.procedure == code
        if code in MOTION_CHECKS:
            source = and_(source, CalibrationRun.metrics["adapter"].as_string() == hardware_runtime.transport.adapter)
        for series, stages in {"WIZARD": WIZARD_STAGES, **AUTO_STAGES}.items():
            if code in stages:
                stage = CalibrationRun.metrics["stages"][stages.index(code)]
                stage_status = stage["status"].as_string()
                source = or_(source, and_(CalibrationRun.procedure == series, or_(
                    CalibrationRun.status == "saved", and_(CalibrationRun.status == "failed", stage_status == "failed"),
                    and_(CalibrationRun.status == "aborted", stage["faultCode"].as_string().in_(CHECK_FAULTS)),
                )))
        row = session.execute(
            select(CalibrationRun.finished_at, CalibrationRun.status, CalibrationRun.metrics["checkSettings"])
            .where(source, or_(CalibrationRun.status.in_(("done", "saved", "failed")),
                               and_(CalibrationRun.status == "aborted", CalibrationRun.metrics["faultCode"].as_string().in_(CHECK_FAULTS))),
                   CalibrationRun.finished_at.is_not(None))
            .order_by(CalibrationRun.finished_at.desc())
            .limit(1)
        ).first()
        if row is not None and row.finished_at is not None:
            finished = _utc(row.finished_at)
            if since is not None and finished <= since:
                continue
            checks[code] = CheckResult(finished.isoformat(), row.status in ("done", "saved"), settings=row[2])
    return checks


def _reviewed_checks(checks: dict[str, CheckResult], bundle: store.ProfileBundle) -> dict[str, CheckResult]:
    result = checks.copy()
    for code in MOTION_CHECKS:
        check = checks.get(code)
        if check and check.ok and check.settings != motion_check_settings(code, bundle.machine, bundle.envelope, bundle.tunables):
            reason = ("Изменилась методика проверки или настройки движения и защиты. Повторите замер." if check.settings else
                      "Предыдущая запись выполнена до проверки каждого конца грифа. Повторите замер.")
            result[code] = replace(check, review_reason=reason)
    return result


@router.get("/calibrations")
def list_calibrations(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    _persist_finished(session)
    bundle = store.load_active(session)
    return graph(bundle.machine, _reviewed_checks(_checks(session), bundle))


# ------------------------------------------------------------------ calibration runs
class CalibrationStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    code: str = Field(min_length=2, max_length=16)
    reference_kg: float | None = Field(None, alias="referenceKg", ge=2, le=60)
    working_zone: Literal["middle"] | None = Field(None, alias="workingZone")

    @field_validator("code")
    @classmethod
    def _runnable(cls, value: str) -> str:
        if value not in RUNNABLE:
            raise ValueError(f"неизвестная калибровка {value}")
        return value


def _persist_run(session: Session, run: CalibrationSession, run_status: str, saved_version: int | None = None, travel_limit_report: dict | None = None) -> None:
    """Build or update the ``CalibrationRun`` row. No commit and no in-memory marking here: the caller
    commits first, and only then marks ``run`` as persisted/saved (a failed commit must not mark it)."""

    row = session.get(CalibrationRun, run.id)
    if row is None:
        row = CalibrationRun(id=run.id, procedure=run.code, started_at=run.started_at, status=run_status)
        session.add(row)
    row.status = run_status
    row.finished_at = run.finished_at
    row.estimate = {stage.code: stage.result for stage in run.stages if stage.result}
    if travel_limit_report is not None:
        row.estimate = {"B8": travel_limit_report}
    row.metrics = {
        "title": run.title,
        "reason": run.reason,
        "faultCode": run.current_stage.fault_code,
        "checkSettings": motion_check_settings(run.code, run.base, run.safety, run.tunables) if run.code in MOTION_CHECKS else None,
        "savedVersion": run.saved_version if saved_version is None else saved_version,
        "stages": [{k: v for k, v in stage.to_payload().items() if k != "result"} for stage in run.stages],
        "stageLogs": {s.code: run.log_payload(s, 240) for s in run.stages if s.status != "pending"} if len(run.stages) > 1 else {},
        "log": run.log_payload(),
        "workingZone": run.working_zone,
        "baseVersion": run.base.version,
        "adapter": run.adapter or hardware_runtime.transport.adapter,
        "changes": run.changes() if run.status == "done" else [],
    }


def _persist_finished(session: Session) -> None:
    """Persist the finished (not running, not yet persisted) session; SQL runs outside the motor lock."""

    with _calibration_route_lock:
        with hardware_runtime._lock:
            run = hardware_runtime.calibration
            if run is None or run.running or run.persisted_status is not None:
                return
            run_status = run.status
        _persist_run(session, run, run_status)
        session.commit()
        with hardware_runtime._lock:
            if hardware_runtime.calibration is run and run.persisted_status is None:
                run.persisted_status = run_status


def _hand_check_ready(session: Session) -> dict[str, Any]:
    profile = hardware_runtime.profile
    checks = _checks(session, ("G2",))
    pending = [f"{BY_CODE[code].title} ({code})" for code in ("F11", "G2") if calibration_status(profile, BY_CODE[code], checks) != "actual"]
    return {"id": "feelCheck", "label": "Захват грифа и отклик под нагрузкой проверены с текущими настройками", "ok": not pending,
            "detail": "Перед повторениями с грифом выполните: " + ", ".join(pending) if pending else None}


@router.get("/calibration/session")
def calibration_session(
    code: str = Query("WIZARD", max_length=16),
    working_zone: Literal["middle"] | None = Query(None, alias="workingZone"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    state = hardware_runtime.calibration_payload(code, working_zone)
    if code == "G3" and state["session"] is None:
        state["preconditions"].append(_hand_check_ready(session))
    return state


@router.post("/calibration/start")
def start_calibration(payload: CalibrationStartRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    with _calibration_route_lock:
        _persist_finished(session)
        if payload.code == "G3" and not (hand_check := _hand_check_ready(session))["ok"]:
            raise _conflict(hand_check["detail"])
        try:
            started = hardware_runtime.start_calibration(payload.code, {
                "referenceKg": payload.reference_kg,
                "workingZone": payload.working_zone,
            })
        except PermissionError as error:
            raise _conflict(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return hardware_runtime.calibration_payload(payload.code, payload.working_zone, run=started)


class CalibrationSessionCommand(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str | None = Field(None, alias="sessionId", min_length=1, max_length=64)


class CalibrationKeepalive(CalibrationSessionCommand):
    interval_ms: float | None = Field(None, alias="intervalMs", ge=0, le=3_600_000)


@router.post("/calibration/keepalive")
async def calibration_keepalive(payload: CalibrationKeepalive | None = None) -> dict[str, bool]:
    """Heartbeat of the calibration screen: silence > 1.5 s (screen closed, hidden, network lost) aborts to support.

    Served on the event loop without the runtime lock: a slow control tick (RS-485 retries) must not
    delay the heartbeat and turn into a false «no link with the screen».
    """

    return {"running": hardware_runtime.calibration_keepalive(
        payload.interval_ms if payload else None,
        payload.session_id if payload else None,
    )}


class CalibrationReply(CalibrationSessionCommand):
    value: float | None = None
    prompt_text: str | None = Field(None, alias="promptText", max_length=4000)


@router.post("/calibration/reply")
def calibration_reply(payload: CalibrationReply) -> dict[str, Any]:
    """Operator's answer to a prompt: «Готово» (no value) or a measured number."""

    try:
        with hardware_runtime._lock:
            run = hardware_runtime.calibration
            if payload.session_id is not None and (run is None or run.id != payload.session_id):
                raise PermissionError("Ответ относится к другой сессии калибровки")
            hardware_runtime.calibration_reply(payload.value, payload.session_id, payload.prompt_text)
            return {"session": run.to_payload() if run is not None else None}
    except PermissionError as error:
        raise _conflict(str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.post("/calibration/abort")
def abort_calibration(payload: CalibrationSessionCommand | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    session_id = payload.session_id if payload else None
    # Interrupt immediately under the motor lock: no SQL and no wait for a completion marker.
    with hardware_runtime._lock:
        run = hardware_runtime.calibration
        if session_id is not None and (run is None or run.id != session_id):
            return {"session": run.to_payload() if run is not None else None}
        hardware_runtime.abort_calibration(session_id=session_id)
    # History is written only after the motor lock is released.
    _persist_finished(session)
    return {"session": run.to_payload() if run is not None else None}


class CalibrationAccept(CalibrationSessionCommand):
    fit_travel_limit: bool = Field(False, alias="fitTravelLimit")


@router.post("/calibration/accept")
def accept_calibration(payload: CalibrationAccept | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    session_id = payload.session_id if payload else None
    with _calibration_route_lock:
        try:
            with hardware_runtime._lock:
                _require_service_mode()
                run = hardware_runtime.calibration
                if session_id is not None and (run is None or run.id != session_id):
                    raise PermissionError("Сохранение относится к другой сессии калибровки")
                if run is None or run.status != "done":
                    raise _conflict("Нет завершённой калибровки для сохранения")
                if run.saved_version is not None:
                    raise _conflict(f"Результат уже сохранён (версия {run.saved_version})")
                if not any(item["changed"] for item in run.changes()):
                    raise _conflict("Новых значений нет")
                runtime_version = hardware_runtime.profile.version
        except PermissionError as error:
            raise _conflict(str(error)) from error

        bundle = store.load_active(session)
        if bundle.machine.version != runtime_version:
            raise _conflict(
                f"Применённый профиль v{runtime_version} не совпадает с сохранённым активным v{bundle.machine.version}: "
                "обновите профиль и повторите сохранение"
            )
        if run.base.version != runtime_version:
            raise _conflict(
                f"Профиль изменился во время калибровки (v{run.base.version} → v{runtime_version}): перезапустите калибровку"
            )
        candidate = replace(bundle, machine=run.profile)
        travel_limit_report = None
        if payload and payload.fit_travel_limit:
            proposed = run.stages[0].result.get("suggestedSoftMaxMm") if run.code == "B8" else None
            if proposed is None or proposed >= bundle.envelope.soft_max_mm:
                raise _conflict("Для этого замера уменьшение верхнего предела не предложено")
            try:
                candidate = apply_changes(candidate, [{"scope": "envelope", "key": "soft_max_mm", "value": proposed}])
            except ValueError as exc:
                raise _conflict(str(exc)) from exc
            measured = run.stages[0].result
            travel_limit_report = {**measured, "appliedSoftMaxMm": proposed, "report": [
                *measured["report"], {"label": "Сохранённый верхний предел", "value": f"{bundle.envelope.soft_max_mm:g} → {proposed:g} мм", "ok": True},
            ]}
        version = store.save_version(session, candidate, note=f"Калибровка {run.code}", source_run_id=run.id)
        _persist_run(session, run, "saved", saved_version=version, travel_limit_report=travel_limit_report)
        session.commit()
        with hardware_runtime._lock:
            if hardware_runtime.calibration is run:
                run.saved_version = version
                run.persisted_status = "saved"
                if travel_limit_report is not None:
                    run.stages[0].result = travel_limit_report
        try:
            hardware_runtime.apply_profile(replace(run.profile, version=version), envelope=candidate.envelope if payload and payload.fit_travel_limit else None)
        except PermissionError as error:
            raise _conflict(f"Профиль v{version} сохранён, но не применён: {error}") from error
        return {"version": version, "session": run.to_payload()}


@router.post("/calibration/discard")
def discard_calibration(payload: CalibrationSessionCommand | None = None, session: Session = Depends(get_session)) -> dict[str, bool]:
    session_id = payload.session_id if payload else None
    with _calibration_route_lock:
        try:
            with hardware_runtime._lock:
                run = hardware_runtime.calibration
                if session_id is not None and (run is None or run.id != session_id):
                    raise PermissionError("Отклонение относится к другой сессии калибровки")
                persist = run is not None and not run.running and run.saved_version is None
                if persist:
                    changed = run.status == "done" and any(item["changed"] for item in run.changes())
                    discard_status = "discarded" if changed else run.status
        except PermissionError as error:
            raise _conflict(str(error)) from error

        if persist:
            _persist_run(session, run, discard_status)
            session.commit()
            with hardware_runtime._lock:
                if hardware_runtime.calibration is run and run.persisted_status is None:
                    run.persisted_status = discard_status
        hardware_runtime.discard_calibration(session_id)
        return {"ok": True}


@router.get("/calibration/runs")
def calibration_runs(session: Session = Depends(get_session), limit: int = Query(30, ge=1, le=200), code: str | None = Query(None, max_length=16)) -> list[dict[str, Any]]:
    _persist_finished(session)
    metrics = CalibrationRun.metrics
    query = select(
        CalibrationRun.id, CalibrationRun.procedure, CalibrationRun.status, CalibrationRun.started_at, CalibrationRun.finished_at,
        metrics["title"].as_string().label("title"), metrics["reason"].as_string().label("reason"),
        metrics["savedVersion"].as_integer().label("saved_version"), metrics["changes"].label("changes"),
    )
    if code:
        query = query.where(CalibrationRun.procedure == code)
    rows = session.execute(query.order_by(CalibrationRun.started_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "code": row.procedure,
            "title": row.title,
            "status": row.status,
            "startedAt": _utc(row.started_at).isoformat(),
            "finishedAt": _utc(row.finished_at).isoformat() if row.finished_at else None,
            "reason": row.reason,
            "savedVersion": row.saved_version,
            "changes": row.changes or [],
        }
        for row in rows
    ]


def _profile_friction_track(run_id: str, maps: dict) -> dict:
    # Early S10 fitted both forces against the bar height and stored its measured points
    # only in the accepted profile. A map carried over from a different run is not evidence.
    values = {side: dict(m.get("value") or []) if m and m.get("run_id") == run_id and m.get("provenance") == "measured" else {}
              for side, m in maps.items()}
    recorded = values["left"].keys() | values["right"].keys()
    centers = list(range(int(min(recorded)), int(max(recorded)) + 1, 20))
    return {"heightsMm": centers, "binMm": 20, "heightBasis": "bar",
            "sides": {side: [points.get(h) for h in centers] for side, points in values.items()}}


ArchiveSource = Literal["modbus", "canopen", "twin", "unknown"]


def _archive_source(source: ArchiveSource | None):
    sources = {"modbus": ("modbus", "modbus-torque"), "canopen": ("canopen", "canopen-torque"), "twin": ("twin",)}
    active = hardware_runtime.transport.adapter
    selected = source or next((key for key, names in sources.items() if active in names), "unknown")
    adapter = CalibrationRun.metrics["adapter"].as_string()
    condition = (adapter.in_(sources[selected]) if selected in sources else
                 or_(adapter.is_(None), adapter.not_in([name for names in sources.values() for name in names])))
    return selected, condition


@router.get("/calibration/friction-tracks")
def friction_tracks(source: ArchiveSource | None = None,
                    limit: int = Query(10, ge=1, le=50), offset: int = Query(0, ge=0),
                    session: Session = Depends(get_session)) -> dict[str, Any]:
    """Return S10 maps, including measured stages of series, without loading their telemetry logs."""
    _persist_finished(session)
    selected, condition = _archive_source(source)
    track = CalibrationRun.estimate["S10"]["track"]
    machine = MachineProfileRecord.payload["machine"]
    maps = {s: machine[s]["friction_map"] for s in ("left", "right")}
    own_points = [and_(m["run_id"].as_string() == CalibrationRun.id, m["provenance"].as_string() == "measured",
                       m["value"][0][0].as_float().is_not(None)) for m in maps.values()]
    query = select(CalibrationRun.id, CalibrationRun.procedure, CalibrationRun.status, CalibrationRun.started_at,
                   track.label("track"), *(m.label(s) for s, m in maps.items())).outerjoin(MachineProfileRecord, and_(
                       MachineProfileRecord.version == CalibrationRun.metrics["savedVersion"].as_integer(),
                       MachineProfileRecord.source_run_id == CalibrationRun.id))
    legacy = and_(CalibrationRun.estimate["S10"]["bins"].as_integer().is_not(None), or_(*own_points))
    query = query.where(condition, or_(track["heightsMm"][0].as_float().is_not(None), legacy))
    rows = session.execute(query.order_by(CalibrationRun.started_at.desc(), CalibrationRun.id.desc())
                           .offset(offset).limit(limit + 1)).all()
    return {"source": selected, "hasMore": len(rows) > limit,
            "items": [{"id": r.id, "code": r.procedure, "status": r.status, "startedAt": _utc(r.started_at).isoformat(),
                       "track": r.track or _profile_friction_track(r.id, {"left": r.left, "right": r.right})} for r in rows[:limit]]}


@router.get("/calibration/measurement-plots")
def measurement_plots(stage: PlotStage, source: ArchiveSource | None = None,
                      limit: int = Query(10, ge=1, le=50), offset: int = Query(0, ge=0),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
    """Page through runs with measurements for this stage, including stages completed inside a series."""
    _persist_finished(session)
    selected, condition = _archive_source(source)
    evidence = CalibrationRun.estimate[stage]
    query = select(CalibrationRun.id, CalibrationRun.procedure, CalibrationRun.status, CalibrationRun.started_at,
                   CalibrationRun.metrics["stages"].label("stages"), evidence.label("evidence")).where(
                       condition, evidence[PLOT_ROOT[stage]].as_string().is_not(None))
    rows = session.execute(query.order_by(CalibrationRun.started_at.desc(), CalibrationRun.id.desc())
                           .offset(offset).limit(limit + 1)).all()
    items = []
    for row in rows[:limit]:
        meta = next((s for s in row.stages or [] if s.get("code") == stage), {})
        items.append({"id": row.id, "code": row.procedure, "status": row.status, "startedAt": _utc(row.started_at).isoformat(),
                      "stageStatus": meta.get("status"), "reason": meta.get("reason"), "workingZone": meta.get("workingZone"),
                      "result": plot_result(stage, row.evidence)})
    spec = BY_CODE[stage]
    return {"source": selected, "priority": spec.priority, "priorityReason": spec.priority_reason,
            "hasMore": len(rows) > limit, "items": items}


@router.get("/calibration/runs/{run_id}")
def calibration_record(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _persist_finished(session)
    row = session.get(CalibrationRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Запуск калибровки не найден")
    metrics, estimates = row.metrics or {}, row.estimate or {}
    stages = []
    for stage in metrics.get("stages", []):
        code = stage["code"]
        spec = BY_CODE.get(code)
        result = estimates.get(code, {})
        stages.append({
            **stage, "title": spec.title if spec else code, "verification": bool(spec and not spec.produces),
            "progress": stage.get("progress", float(stage["status"] == "done")),
            "note": stage.get("note", ""), "result": {**plot_result(code, result), **{k: result[k] for k in ("report", "track") if k in result}},
        })
    return {"id": row.id, "code": row.procedure, "title": metrics.get("title"), "status": row.status,
            "startedAt": _utc(row.started_at).isoformat(), "savedVersion": metrics.get("savedVersion"), "changes": metrics.get("changes", []),
            "log": metrics.get("log"), "stageLogs": metrics.get("stageLogs", {}), "stages": stages, "workingZone": metrics.get("workingZone"),
            "baseVersion": metrics.get("baseVersion"), "adapter": metrics.get("adapter")}


@router.get("/calibration/fault-rehearsal")
def calibration_fault_rehearsal() -> dict[str, Any]:
    with hardware_runtime._lock:
        profile, envelope = hardware_runtime.profile, hardware_runtime.envelope
    return fault_rehearsal(profile, envelope)


@router.get("/calibration/speed-study")
def calibration_speed_study(target_mm_s: float = Query(1500, alias="targetMmS", ge=50, le=1500), session: Session = Depends(get_session)) -> dict[str, Any]:
    with hardware_runtime._lock:
        profile, envelope = hardware_runtime.profile, hardware_runtime.envelope
        adapter = hardware_runtime.transport.adapter
    run_id = profile.fast_brake_lag_s.run_id
    row = session.get(CalibrationRun, run_id) if run_id else None
    saved = row is not None and row.procedure == "M5" and row.status == "saved"
    source = (row.metrics or {}).get("adapter") if saved else None
    result = (row.estimate or {}).get("M5", {}) if saved else {}
    study = speed_study(profile, envelope, target_mm_s, result.get("runs", []), braking_matches_source=source == adapter)
    return {**study, "adapter": adapter, "m5Source": source, "m5RunId": run_id}


# ------------------------------------------------------------------ parameters
class ParameterChange(BaseModel):
    scope: Literal["side", "machine", "tunables", "envelope"]
    key: str = Field(max_length=64)
    side: Literal["left", "right"] | None = None
    value: float | int | bool


class ParametersUpdate(BaseModel):
    changes: list[ParameterChange] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=200)
    base_version: int | None = Field(default=None, alias="baseVersion", ge=0)


@router.get("/parameters")
def get_parameters(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {**describe(store.load_active(session)), "runtimeVersion": hardware_runtime.profile.version}


def _proposed_parameters(payload: ParametersUpdate, session: Session) -> tuple[store.ProfileBundle, store.ProfileBundle]:
    bundle = store.load_active(session)
    if payload.base_version is not None and bundle.machine.version != payload.base_version:
        raise _conflict(f"Профиль изменился с v{payload.base_version} до v{bundle.machine.version}. Проверьте правки на текущей версии.")
    try:
        return bundle, apply_changes(bundle, [change.model_dump() for change in payload.changes])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/parameters/preview")
def preview_parameters(payload: ParametersUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    before, after = _proposed_parameters(payload, session)
    versions = [{(item["scope"], item["key"]): item for group in describe(bundle)["groups"] for item in group["items"]}
                for bundle in (before, after)]
    rows = []
    for scope, key, side in dict.fromkeys((c.scope, c.key, c.side if c.scope == "side" else None) for c in payload.changes):
        old, new = (items[(scope, key)] for items in versions)
        rows.append({"scope": scope, "key": key, "side": side, "label": new["label"], "unit": new["unit"], "kind": new["kind"],
                     "before": old["values"][side] if side else old["value"], "after": new["values"][side] if side else new["value"],
                     "effective": new.get("effective"), "restart": new["restart"]})
    statuses = []
    if before != after:
        checks = _checks(session)
        previous = {row["code"]: row["status"] for row in graph(before.machine, _reviewed_checks(checks, before))}
        for item in graph(after.machine, _reviewed_checks(checks, after)):
            if item["status"] != previous[item["code"]]:
                statuses.append({"code": item["code"], "title": item["title"], "before": previous[item["code"]], "after": item["status"]})
    return {"baseVersion": before.machine.version, "changes": rows, "statusChanges": statuses}


@router.put("/parameters")
def update_parameters(payload: ParametersUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    with _calibration_route_lock:
        with hardware_runtime._lock:
            _require_service_mode()
            if hardware_runtime.calibration is not None and hardware_runtime.calibration.running:
                raise _conflict("Идёт калибровка — параметры нельзя менять")
            if hardware_runtime.workout.active:
                raise _conflict("Идёт упражнение — параметры нельзя менять")
        bundle, updated = _proposed_parameters(payload, session)
        try:
            version = store.save_version(session, updated, note=payload.note or "Ручная настройка параметров", expected_version=bundle.machine.version)
        except ValueError as error:
            session.rollback()
            raise _conflict(str(error)) from error
        session.commit()
        try:
            hardware_runtime.apply_profile(replace(updated.machine, version=version), updated.envelope, updated.tunables)
        except PermissionError as error:
            raise _conflict(f"Профиль v{version} сохранён, но не применён: {error}") from error
        return {**describe(replace(updated, machine=replace(updated.machine, version=version))), "runtimeVersion": hardware_runtime.profile.version}


class ResetRequest(BaseModel):
    scope: Literal["calibrations", "parameters", "all"]


@router.post("/profile/reset")
def reset_profile(payload: ResetRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    with _calibration_route_lock:
        with hardware_runtime._lock:
            _require_service_mode()
            if hardware_runtime.calibration is not None and hardware_runtime.calibration.running:
                raise _conflict("Идёт калибровка — сброс недоступен")
            if hardware_runtime.workout.active:
                raise _conflict("Идёт упражнение — сброс недоступен")
        version = store.reset(session, payload.scope)
        session.commit()
        saved = store.load_active(session)
        try:
            hardware_runtime.apply_profile(saved.machine, saved.envelope, saved.tunables)
        except PermissionError as error:
            raise _conflict(f"Профиль v{version} сохранён, но не применён: {error}") from error
        return {**describe(saved), "runtimeVersion": hardware_runtime.profile.version}
