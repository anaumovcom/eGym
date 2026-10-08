from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.seed import seed_dev_data, seed_stage7_data, seed_stage8_data
from app.db.session import SessionLocal, engine
from app.motor.store import ProfileBundle, load_active
from app.schemas.modbus import ModbusConnectionParamsSchema
from app.services.coach.request_guard import CoachRequestGuard
from app.services.exercise_library import EXERCISES_ROOT
from app.services.hardware_runtime import hardware_runtime
from app.services.modbus_service import modbus_service


def bootstrap_local_data() -> None:
    settings = get_settings()
    Path(settings.media_root).mkdir(parents=True, exist_ok=True)
    if settings.app_env not in {"local", "test"} or not settings.database_url.startswith("sqlite"):
        return

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_dev_data(session)
        seed_stage7_data(session)
        seed_stage8_data(session)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    bootstrap_local_data()
    settings = get_settings()
    bundle = load_motor_profile()
    if settings.hardware_adapter == "modbus":
        # the first PA_12C written at startup is upward support, never 0 (R1)
        modbus_service.connect(ModbusConnectionParamsSchema(
            port=settings.modbus_port,
            baud_rate=settings.modbus_baud_rate,
            slave_id=settings.modbus_left_slave_id,
            right_slave_id=settings.modbus_right_slave_id,
        ), initial_commands={
            settings.modbus_left_slave_id: int(bundle.machine.left.support_raw.value) * bundle.machine.left.sign,
            settings.modbus_right_slave_id: int(bundle.machine.right.support_raw.value) * bundle.machine.right.sign,
        })
    try:
        hardware_runtime.reset(profile=bundle.machine, envelope=bundle.envelope)
        await hardware_runtime.start()
        yield
    finally:
        try:
            await hardware_runtime.stop()
        finally:
            if settings.hardware_adapter == "modbus":
                # Closing the serial port must not overwrite backup support
                # with zero, including a partially failed application startup.
                modbus_service.disconnect(preserve_torque=True)


def load_motor_profile() -> ProfileBundle:
    with SessionLocal() as session:
        return load_active(session)


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
    app.mount(settings.media_url_prefix, StaticFiles(directory=settings.media_root), name="media")
    app.include_router(api_router, prefix=settings.api_prefix)
    return app



app = create_app()
