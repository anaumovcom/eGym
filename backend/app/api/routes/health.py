from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.schemas.health import HealthResponseSchema

router = APIRouter()


@router.get("/health", response_model=HealthResponseSchema)
def health_check(session: Session = Depends(get_session)) -> HealthResponseSchema:
    settings = get_settings()
    session.execute(text("SELECT 1"))
    return HealthResponseSchema(
        status="ok",
        environment=settings.app_env,
        database="ok",
        redis="configured" if settings.redis_url else "disabled",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
