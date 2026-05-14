from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.machine import (
    DriveStatusesResponseSchema,
    EmergencyStopResponseSchema,
    MachineHealthSchema,
    SafetyStatusSchema,
)
from app.services.machine_service import MachineService

router = APIRouter()

machine_service = MachineService()


@router.get("/status", response_model=MachineHealthSchema)
def get_machine_status(
    scenario: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> MachineHealthSchema:
    try:
        return machine_service.get_machine_health(session, scenario)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/drives", response_model=DriveStatusesResponseSchema)
def get_drive_statuses(
    scenario: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> DriveStatusesResponseSchema:
    try:
        return machine_service.get_drive_statuses(session, scenario)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/safety", response_model=SafetyStatusSchema)
def get_safety_status(
    scenario: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> SafetyStatusSchema:
    try:
        return machine_service.get_safety_status(session, scenario)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/emergency-stop", response_model=EmergencyStopResponseSchema)
def trigger_emergency_stop(
    actor_user_id: str | None = Query(default=None, alias="actorUserId"),
    session: Session = Depends(get_session),
) -> EmergencyStopResponseSchema:
    return machine_service.trigger_emergency_stop(session, actor_user_id)
