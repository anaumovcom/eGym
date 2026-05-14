from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.models.enums import AuditAction, AuditSeverity
from app.repositories.audit_repository import AuditRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    CurrentUserSchema,
    SelectUserRequestSchema,
    SelectUserResponseSchema,
    UsersResponseSchema,
    UserSummarySchema,
)

router = APIRouter()

user_repository = UserRepository()
audit_repository = AuditRepository()


@router.get("", response_model=UsersResponseSchema)
def list_users(session: Session = Depends(get_session)) -> UsersResponseSchema:
    users = user_repository.list_users(session)
    return UsersResponseSchema(users=[UserSummarySchema.model_validate(user) for user in users])


@router.get("/current", response_model=CurrentUserSchema)
def get_current_user(session: Session = Depends(get_session)) -> CurrentUserSchema:
    user = user_repository.get_current_user(session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Current user is not selected")
    return CurrentUserSchema.model_validate(user)


@router.post("/select", response_model=SelectUserResponseSchema)
def select_user(payload: SelectUserRequestSchema, session: Session = Depends(get_session)) -> SelectUserResponseSchema:
    user = user_repository.set_current_user(session, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    audit_repository.record(
        session,
        actor_user_id=payload.user_id,
        action=AuditAction.user_selected,
        target_type="user",
        target_id=payload.user_id,
        severity=AuditSeverity.info,
        details={"source": "selection_screen"},
    )
    session.commit()
    return SelectUserResponseSchema(current_user=CurrentUserSchema.model_validate(user))
