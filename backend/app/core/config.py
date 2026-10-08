from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    coach_enabled: bool = Field(default=False, alias="COACH_ENABLED")
    coach_operator_hash_file: str | None = Field(default=None, alias="COACH_OPERATOR_HASH_FILE")
    coach_master_key_file: str | None = Field(default=None, alias="COACH_MASTER_KEY_FILE")
    coach_operator_daily_usd: str = Field(default="10.00", alias="COACH_OPERATOR_DAILY_USD")
    coach_operator_monthly_usd: str = Field(default="100.00", alias="COACH_OPERATOR_MONTHLY_USD")
    # Paid text dispatch is on by default (user decision 08.10.2026); it still needs a vault key, network consent and
    # the per-workout cap. Set COACH_PAID_TEXT_ENABLED=false to fall back to the local coach.
    coach_paid_text_enabled: bool = Field(default=True, alias="COACH_PAID_TEXT_ENABLED")
    coach_text_model: str = Field(default="gpt-6-luna", max_length=80, alias="COACH_TEXT_MODEL")
    # Rates checked against the official pricing page on 2026-10-08 (verified by default; re-check on price changes).
    coach_text_pricing_version: str = Field(default="openai-2026-10-08", max_length=80, alias="COACH_TEXT_PRICING_VERSION")
    coach_text_input_rate: int = Field(default=100_000, ge=0, alias="COACH_TEXT_INPUT_RATE")
    coach_text_cached_rate: int = Field(default=10_000, ge=0, alias="COACH_TEXT_CACHED_RATE")
    coach_text_output_rate: int = Field(default=500_000, ge=0, alias="COACH_TEXT_OUTPUT_RATE")
    coach_text_pricing_verified: bool = Field(default=True, alias="COACH_TEXT_PRICING_VERIFIED")
    coach_text_max_output_tokens: int = Field(default=400, ge=64, le=2000, alias="COACH_TEXT_MAX_OUTPUT_TOKENS")
    # Documented gpt-6-luna values: none|low|medium(default)|high|xhigh|max. Low keeps rest-phase latency short.
    coach_text_reasoning_effort: Literal["none", "low", "medium"] = Field(default="low", alias="COACH_TEXT_REASONING_EFFORT")
    # E08 voice: paid dispatch on by default (user decision 08.10.2026); same vault/consent/cap gates as text.
    coach_paid_voice_enabled: bool = Field(default=True, alias="COACH_PAID_VOICE_ENABLED")
    coach_voice_pricing_verified: bool = Field(default=True, alias="COACH_VOICE_PRICING_VERIFIED")
    coach_voice_realtime_model: str = Field(default="gpt-realtime-2.1-mini", max_length=80, alias="COACH_VOICE_REALTIME_MODEL")
    # Realtime 2 prompting guide: minimal|low|medium|high|xhigh. Unset by default: the probe of 08.10.2026 showed that
    # "minimal" makes response.done report input_tokens=0 (billing basis unknown) while saving only ~12 reasoning tokens.
    coach_voice_realtime_reasoning_effort: Literal["minimal", "low", "medium"] | None = Field(
        default=None, alias="COACH_VOICE_REALTIME_REASONING_EFFORT")
    # gpt-4o-mini-tts is deprecated (shutdown 2027-01-06): kept only for A/B and pack generation before that date.
    coach_voice_tts_model: str = Field(default="gpt-4o-mini-tts", max_length=80, alias="COACH_VOICE_TTS_MODEL")
    coach_voice_pricing_version: str = Field(default="openai-2026-10-08", max_length=80, alias="COACH_VOICE_PRICING_VERSION")
    # E09 packs: private directory (never under the public media mount). One pack per provider voice;
    # generated with the live adapter (Realtime) so prepared phrases and live speech share one timbre.
    coach_pack_root: str = Field(default=str(BACKEND_ROOT / "coach_packs"), alias="COACH_PACK_ROOT")
    coach_pack_adapter: Literal["realtime", "tts"] = Field(default="realtime", alias="COACH_PACK_ADAPTER")
    hardware_keyboard_simulation_enabled: bool = Field(default=False, alias="HARDWARE_KEYBOARD_SIMULATION_ENABLED")
    hardware_adapter: str = Field(default="modbus", alias="HARDWARE_ADAPTER")
    modbus_port: str = Field(default="/dev/ttyUSB0", alias="MODBUS_PORT")
    modbus_baud_rate: int = Field(default=115200, alias="MODBUS_BAUD_RATE")
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
