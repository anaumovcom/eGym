import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import get_session_factory
from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.seed import seed_dev_data, seed_stage7_data, seed_stage8_data
from app.db.session import SessionLocal, engine
from app.motor.store import ProfileBundle, load_active
from app.services.coach.request_guard import CoachRequestGuard
from app.services.coach.schema import ensure_columns
from app.services.drive_transport_settings import load_transport
from app.services.exercise_library import EXERCISES_ROOT
from app.services.hardware_runtime import hardware_runtime
from app.services.motor_observations import ObservationWriter
from app.services.scale_service import ScaleService


def bootstrap_local_data() -> None:
    settings = get_settings()
    Path(settings.media_root).mkdir(parents=True, exist_ok=True)
    if settings.app_env not in {"local", "test"} or not settings.database_url.startswith("sqlite"):
        return

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        ensure_columns(connection)
    with SessionLocal() as session:
        seed_dev_data(session)
        seed_stage7_data(session)
        seed_stage8_data(session)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    bootstrap_local_data()
    bundle = load_motor_profile()
    sessions = app.dependency_overrides.get(get_session_factory, get_session_factory)()
    with sessions() as session:
        transport = load_transport(session)
    try:
        hardware_runtime.reset(profile=bundle.machine, envelope=bundle.envelope, tunables=bundle.tunables, transport=transport)
        await hardware_runtime.start()
        scale_service = ScaleService(sessions, activity_blocker=hardware_runtime.scale_monitoring_block_reason)
        app.state.scale_service = scale_service
        await scale_service.start()
        writer = ObservationWriter(sessions, hardware_runtime)
        writer_task = asyncio.create_task(writer.run())
        try:
            yield
        finally:
            writer.stopping.set()
            try:
                await writer_task
            finally:
                await scale_service.close()
    finally:
        try:
            await hardware_runtime.stop()
        finally:
            hardware_runtime.close_transport()


def load_motor_profile() -> ProfileBundle:
    with SessionLocal() as session:
        return load_active(session)


class PublicMediaFiles(StaticFiles):
    """Static media without achievement assets: those need the owner-checked API route."""

    async def get_response(self, path: str, scope):
        if path.replace("\\", "/").lstrip("/").split("/", 1)[0].casefold() == "achievements":
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


def create_app() -> FastAPI:
    settings = get_settings()
    Path(settings.media_root).mkdir(parents=True, exist_ok=True)
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CoachRequestGuard)
    app.mount(f"{settings.media_url_prefix}/exercises", StaticFiles(directory=EXERCISES_ROOT), name="exercise-media")
    app.mount(settings.media_url_prefix, PublicMediaFiles(directory=settings.media_root), name="media")
    app.include_router(api_router, prefix=settings.api_prefix)
    return app



app = create_app()
