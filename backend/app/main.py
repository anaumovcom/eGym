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
from app.services.exercise_library import EXERCISES_ROOT
from app.services.hardware_runtime import hardware_runtime


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
    hardware_runtime.reset()
    bootstrap_local_data()
    await hardware_runtime.start()
    yield
    await hardware_runtime.stop()


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
    app.mount(f"{settings.media_url_prefix}/exercises", StaticFiles(directory=EXERCISES_ROOT), name="exercise-media")
    app.mount(settings.media_url_prefix, StaticFiles(directory=settings.media_root), name="media")
    app.include_router(api_router, prefix=settings.api_prefix)
    return app



app = create_app()
