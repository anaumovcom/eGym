from fastapi import APIRouter

from app.api.routes.analytics import router as analytics_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.directories import router as directories_router
from app.api.routes.health import router as health_router
from app.api.routes.hardware import router as hardware_router
from app.api.routes.machine import router as machine_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.runtime import router as runtime_router
from app.api.routes.users import router as users_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(machine_router, prefix="/machine", tags=["machine"])
api_router.include_router(hardware_router, tags=["hardware"])
api_router.include_router(notifications_router, tags=["notifications"])
api_router.include_router(directories_router, prefix="/directories", tags=["directories"])
api_router.include_router(runtime_router, tags=["runtime"])
api_router.include_router(analytics_router, tags=["analytics"])
