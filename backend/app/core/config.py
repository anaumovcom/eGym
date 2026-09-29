from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
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
    hardware_adapter: str = Field(default="modbus", alias="HARDWARE_ADAPTER")
    modbus_port: str = Field(default="/dev/ttyUSB0", alias="MODBUS_PORT")
    modbus_baud_rate: int = Field(default=19200, alias="MODBUS_BAUD_RATE")
    modbus_left_slave_id: int = Field(default=1, ge=1, le=247, alias="MODBUS_LEFT_SLAVE_ID")
    modbus_right_slave_id: int = Field(default=2, ge=1, le=247, alias="MODBUS_RIGHT_SLAVE_ID")
    hardware_limit_switches_enabled: bool = Field(default=True, alias="HARDWARE_LIMIT_SWITCHES_ENABLED")
    hardware_panel_enabled: bool = Field(default=False, alias="HARDWARE_PANEL_ENABLED")
    hardware_panel_port: str | None = Field(default=None, alias="HARDWARE_PANEL_PORT")
    hardware_panel_baud: int = Field(default=115200, ge=1200, le=3_000_000, alias="HARDWARE_PANEL_BAUD")
    hardware_panel_heartbeat_interval_seconds: float = Field(
        default=0.5,
        ge=0.05,
        le=1.0,
        alias="HARDWARE_PANEL_HEARTBEAT_INTERVAL_SECONDS",
    )
    hardware_panel_reconnect_delay_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        alias="HARDWARE_PANEL_RECONNECT_DELAY_SECONDS",
    )
    hardware_panel_status_interval_seconds: float = Field(
        default=0.25,
        ge=0.05,
        le=10.0,
        alias="HARDWARE_PANEL_STATUS_INTERVAL_SECONDS",
    )
    hardware_panel_rx_watchdog_seconds: float = Field(
        default=2.0,
        gt=0.05,
        le=30.0,
        alias="HARDWARE_PANEL_RX_WATCHDOG_SECONDS",
    )
    hardware_panel_load_step_kg: float = Field(default=2.5, gt=0, le=25, alias="HARDWARE_PANEL_LOAD_STEP_KG")
    hardware_panel_service_move_mm: float = Field(default=5.0, gt=0, le=50, alias="HARDWARE_PANEL_SERVICE_MOVE_MM")
    hardware_panel_night_mode: bool = Field(default=False, alias="HARDWARE_PANEL_NIGHT_MODE")
    hardware_panel_brightness: float = Field(default=1.0, ge=0.1, le=1.0, alias="HARDWARE_PANEL_BRIGHTNESS")
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

    @field_validator("database_url")
    @classmethod
    def normalize_sqlite_url(cls, value: str) -> str:
        for prefix in ("sqlite:///", "sqlite+pysqlite:///"):
            if not value.startswith(prefix):
                continue

            database_path = value.removeprefix(prefix)
            if database_path == ":memory:" or Path(database_path).is_absolute():
                return value

            return f"{prefix}{(BACKEND_ROOT / database_path).resolve().as_posix()}"

        return value

    @field_validator("hardware_panel_port", mode="before")
    @classmethod
    def normalize_panel_port(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
