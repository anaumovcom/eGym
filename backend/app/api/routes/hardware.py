from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.hardware import (
    CalibrationListResponseSchema,
    CalibrationSaveSchema,
    CalibrationSummarySchema,
    EmulatorControlSchema,
    HardwareCommandRequestSchema,
    HardwareCommandResponseSchema,
    HardwareDiagnosticRecordSchema,
    HardwareSafetySettingsSchema,
    HardwareSnapshotSchema,
    ProcedureStartSchema,
    RecordingControlSchema,
    SafetyGateRequestSchema,
    SafetyGateResponseSchema,
    TuningPresetDiffSchema,
    TuningPresetSaveSchema,
    TuningPresetSchema,
    TuningUpdateResultSchema,
    TuningUpdateSchema,
    TuningValuesSchema,
)
from app.services.hardware_runtime import hardware_runtime
from app.services.hardware_service import HardwareService
from app.services.motion.parameters import ParameterValidationError, schema_payload
from app.services.motion.procedures import MEASUREMENTS, PROCEDURE_LABELS, SCENARIOS

router = APIRouter(prefix="/hardware")

hardware_service = HardwareService()


@router.get("/status", response_model=HardwareSnapshotSchema)
def get_hardware_status(
    user_id: str | None = Query(default=None, alias="userId"),
    session: Session = Depends(get_session),
) -> HardwareSnapshotSchema:
    return hardware_service.get_snapshot(session, user_id)


@router.get("/settings")
def get_hardware_settings(
    user_id: str | None = Query(default=None, alias="userId"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return hardware_service.get_system_settings(session, user_id)


@router.put("/settings/safety", response_model=HardwareSafetySettingsSchema)
def update_hardware_safety_settings(
    payload: HardwareSafetySettingsSchema,
    user_id: str | None = Query(default=None, alias="userId"),
    session: Session = Depends(get_session),
) -> HardwareSafetySettingsSchema:
    return hardware_service.update_safety_settings(session, user_id, payload)


@router.get("/diagnostics", response_model=list[HardwareDiagnosticRecordSchema])
def list_hardware_diagnostics(session: Session = Depends(get_session)) -> list[HardwareDiagnosticRecordSchema]:
    return hardware_service.list_diagnostics(session)


@router.post("/safety-gate/check", response_model=SafetyGateResponseSchema)
def check_safety_gate(payload: SafetyGateRequestSchema, session: Session = Depends(get_session)) -> SafetyGateResponseSchema:
    return hardware_service.evaluate_safety_gate(session, payload)


@router.post("/commands", response_model=HardwareCommandResponseSchema)
def execute_hardware_command(
    payload: HardwareCommandRequestSchema,
    session: Session = Depends(get_session),
) -> HardwareCommandResponseSchema:
    try:
        return hardware_service.execute_command(session, payload)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/calibrations", response_model=CalibrationListResponseSchema)
def list_calibrations(
    user_id: str = Query(..., alias="userId"),
    session: Session = Depends(get_session),
) -> CalibrationListResponseSchema:
    return hardware_service.list_calibrations(session, user_id)


@router.get("/calibrations/current", response_model=CalibrationSummarySchema | None)
def get_current_calibration(
    user_id: str = Query(..., alias="userId"),
    exercise_slug: str = Query(..., alias="exerciseSlug"),
    session: Session = Depends(get_session),
) -> CalibrationSummarySchema | None:
    calibration = hardware_service.get_current_calibration(session, user_id, exercise_slug)
    if calibration is None:
        return None
    return CalibrationSummarySchema.model_validate(calibration)


@router.post("/calibrations", response_model=CalibrationSummarySchema)
def save_calibration(payload: CalibrationSaveSchema, session: Session = Depends(get_session)) -> CalibrationSummarySchema:
    return hardware_service.save_calibration(session, payload)


@router.delete("/calibrations/{calibration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calibration(
    calibration_id: int,
    confirm: bool = Query(default=False),
    actor_user_id: str | None = Query(default=None, alias="actorUserId"),
    session: Session = Depends(get_session),
) -> None:
    try:
        hardware_service.delete_calibration(session, calibration_id, actor_user_id, confirm)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.websocket("/realtime")
async def hardware_realtime(websocket: WebSocket) -> None:
    user_id = websocket.query_params.get("userId")
    await websocket.accept()
    if user_id:
        hardware_runtime.set_selected_user(user_id, broadcast=False)
    queue = await hardware_runtime.subscribe()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(HardwareSnapshotSchema.model_validate(payload).model_dump(mode="json", by_alias=True))
    except WebSocketDisconnect:
        hardware_runtime.unsubscribe(queue)


# ---------------------------------------------------------------- tuning


def _raise_for(error: Exception) -> None:
    if isinstance(error, PermissionError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if isinstance(error, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, ParameterValidationError | ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    raise error


@router.get("/tuning/schema")
def get_tuning_schema() -> dict[str, object]:
    return {
        **schema_payload(),
        "procedures": {
            "measurements": [{"id": key, "label": PROCEDURE_LABELS.get(key, key)} for key in MEASUREMENTS],
            "scenarios": [{"id": key, "label": PROCEDURE_LABELS.get(key, key)} for key in SCENARIOS],
        },
    }


@router.get("/tuning", response_model=TuningValuesSchema)
def get_tuning(session: Session = Depends(get_session)) -> TuningValuesSchema:
    return hardware_service.get_tuning(session)


@router.put("/tuning", response_model=TuningUpdateResultSchema)
def update_tuning(payload: TuningUpdateSchema, session: Session = Depends(get_session)) -> TuningUpdateResultSchema:
    try:
        return hardware_service.update_tuning(session, payload)
    except (PermissionError, LookupError, ValueError) as error:
        _raise_for(error)
        raise


@router.post("/tuning/revert", response_model=TuningValuesSchema)
def revert_tuning(session: Session = Depends(get_session)) -> TuningValuesSchema:
    return hardware_service.revert_temporary_tuning(session)


@router.post("/tuning/reset", response_model=TuningValuesSchema)
def reset_tuning(actor_user_id: str | None = Query(default=None, alias="actorUserId"), session: Session = Depends(get_session)) -> TuningValuesSchema:
    try:
        return hardware_service.reset_tuning(session, actor_user_id)
    except PermissionError as error:
        _raise_for(error)
        raise


@router.get("/tuning/presets", response_model=list[TuningPresetSchema])
def list_presets(session: Session = Depends(get_session)) -> list[TuningPresetSchema]:
    return hardware_service.list_presets(session)


@router.post("/tuning/presets", response_model=TuningPresetSchema)
def save_preset(payload: TuningPresetSaveSchema, session: Session = Depends(get_session)) -> TuningPresetSchema:
    return hardware_service.save_preset(session, payload)


@router.delete("/tuning/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(preset_id: str, session: Session = Depends(get_session)) -> None:
    try:
        hardware_service.delete_preset(session, preset_id)
    except LookupError as error:
        _raise_for(error)


@router.get("/tuning/presets/{preset_id}/diff", response_model=TuningPresetDiffSchema)
def diff_preset(preset_id: str, session: Session = Depends(get_session)) -> TuningPresetDiffSchema:
    try:
        return hardware_service.diff_preset(session, preset_id)
    except LookupError as error:
        _raise_for(error)
        raise


@router.post("/tuning/presets/{preset_id}/apply", response_model=TuningUpdateResultSchema)
def apply_preset(
    preset_id: str,
    apply: str = Query(default="temporary"),
    actor_user_id: str | None = Query(default=None, alias="actorUserId"),
    session: Session = Depends(get_session),
) -> TuningUpdateResultSchema:
    try:
        return hardware_service.apply_preset(session, preset_id, apply=apply, actor_user_id=actor_user_id)
    except (PermissionError, LookupError, ValueError) as error:
        _raise_for(error)
        raise


@router.post("/tuning/procedures/{name}")
def start_procedure(name: str, payload: ProcedureStartSchema, session: Session = Depends(get_session)) -> dict[str, object]:
    try:
        return hardware_service.start_procedure(session, name, payload)
    except (PermissionError, LookupError, ValueError, TypeError) as error:
        _raise_for(error if not isinstance(error, TypeError) else ValueError(str(error)))
        raise


@router.post("/tuning/procedures/abort")
def abort_procedure() -> dict[str, object]:
    return hardware_runtime.abort_procedure().to_payload()


@router.get("/tuning/procedure")
def get_procedure() -> dict[str, object]:
    return hardware_runtime.procedure.to_payload()


@router.get("/tuning/events")
def get_events(limit: int = Query(default=100, ge=1, le=400)) -> list[dict[str, object]]:
    return hardware_runtime.events_payload(limit)


@router.get("/tuning/emulator")
def get_emulator() -> dict[str, object]:
    return hardware_runtime.emulator_payload()


@router.post("/tuning/emulator")
def control_emulator(payload: EmulatorControlSchema) -> dict[str, object]:
    data = payload.model_dump(exclude_none=True)
    action = data.pop("action")
    if action == "physics":
        data = dict(payload.physics or {})
    try:
        return hardware_runtime.emulator_control(action, **data)
    except (PermissionError, ValueError) as error:
        _raise_for(error)
        raise


@router.get("/tuning/recordings")
def list_recordings() -> dict[str, object]:
    recorder = hardware_runtime.recorder
    return {
        "recording": recorder.manual_active,
        "recordings": [item.to_summary() for item in recorder.recordings],
        "incidents": [item.to_summary() for item in recorder.incidents],
    }


@router.post("/tuning/recordings")
def control_recording(payload: RecordingControlSchema) -> dict[str, object]:
    try:
        return hardware_runtime.recording_control(payload.action, **payload.model_dump(exclude_none=True, exclude={"action"}))
    except ValueError as error:
        _raise_for(error)
        raise


@router.get("/tuning/recordings/{recording_id}")
def get_recording(recording_id: int) -> dict[str, object]:
    recording = hardware_runtime.recorder.get(recording_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    return recording.to_payload()


@router.delete("/tuning/recordings/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(recording_id: int) -> None:
    if not hardware_runtime.recorder.delete(recording_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")


@router.websocket("/telemetry-debug")
async def telemetry_debug(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await hardware_runtime.subscribe_debug()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        hardware_runtime.unsubscribe_debug(queue)