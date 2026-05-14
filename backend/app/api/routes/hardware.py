from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.hardware import (
    CalibrationListResponseSchema,
    CalibrationSaveSchema,
    CalibrationSummarySchema,
    HardwareCommandRequestSchema,
    HardwareCommandResponseSchema,
    HardwareDiagnosticRecordSchema,
    HardwareSafetySettingsSchema,
    HardwareSnapshotSchema,
    SafetyGateRequestSchema,
    SafetyGateResponseSchema,
)
from app.services.hardware_runtime import hardware_runtime
from app.services.hardware_service import HardwareService

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


@router.get("/calibrations/current", response_model=CalibrationSummarySchema)
def get_current_calibration(
    user_id: str = Query(..., alias="userId"),
    exercise_slug: str = Query(..., alias="exerciseSlug"),
    session: Session = Depends(get_session),
) -> CalibrationSummarySchema:
    calibration = hardware_service.get_current_calibration(session, user_id, exercise_slug)
    if calibration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calibration not found")
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
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        hardware_runtime.unsubscribe(queue)