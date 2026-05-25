from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = BACKEND_ROOT / "egym_local.db"
DEFAULT_OPENAPI_EXPORT_PATH = BACKEND_ROOT / "openapi" / "openapi.json"
DEFAULT_MEDIA_ROOT = BACKEND_ROOT / "media"


class Settings(BaseSettings):
    app_name: str = "eGym Forma API"
    app_env: str = Field(default="local", alias="APP_ENV")
    debug: bool = Field(default=True, alias="APP_DEBUG")
    hardware_keyboard_simulation_enabled: bool = Field(default=False, alias="HARDWARE_KEYBOARD_SIMULATION_ENABLED")
    api_prefix: str = "/api"
    database_url: str = Field(default=f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    openapi_export_path: str = Field(default=str(DEFAULT_OPENAPI_EXPORT_PATH), alias="OPENAPI_EXPORT_PATH")
    media_root: str = Field(default=str(DEFAULT_MEDIA_ROOT), alias="MEDIA_ROOT")
    media_url_prefix: str = Field(default="/media", alias="MEDIA_URL_PREFIX")

    model_config = SettingsConfigDict(
        env_file=(
            BACKEND_ROOT / ".env",
            BACKEND_ROOT / ".env.local",
            BACKEND_ROOT / ".env.test",
            BACKEND_ROOT / ".env.staging",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
