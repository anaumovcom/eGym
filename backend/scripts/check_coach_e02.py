"""Run coach regressions and the synthetic U00 corpus without paid/network/hardware I/O."""

import os
import socket
import sys
import tempfile
from pathlib import Path


def main() -> int:
    backend = Path(__file__).resolve().parents[1]
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    with tempfile.TemporaryDirectory(prefix="egym-e02-") as root:
        os.environ.update(
            APP_ENV="test", APP_DEBUG="false", COACH_ENABLED="false", HARDWARE_ADAPTER="emulator",
            HARDWARE_PANEL_ENABLED="false", HARDWARE_KEYBOARD_SIMULATION_ENABLED="false",
            COACH_PAID_TEXT_ENABLED="false", COACH_PAID_VOICE_ENABLED="false",
            COACH_TEXT_PRICING_VERIFIED="false", COACH_VOICE_PRICING_VERIFIED="false",
            COACH_SITUATIONAL_DELIVERY_ENABLED="false",
            COACH_OPERATOR_HASH_FILE="", COACH_MASTER_KEY_FILE="", COACH_PACK_ROOT=f"{root}/packs",
            DATABASE_URL=f"sqlite:///{root}/bootstrap.db", MEDIA_ROOT=f"{root}/media",
            OPENAPI_EXPORT_PATH=f"{root}/openapi.json",
        )
        from app.core.config import Settings, get_settings

        Settings.model_config["env_file"] = None
        get_settings.cache_clear()
        settings = get_settings()
        assert settings.hardware_adapter == "emulator" and not settings.hardware_panel_enabled
        assert settings.database_url == f"sqlite:///{root}/bootstrap.db"
        assert not settings.coach_paid_text_enabled and not settings.coach_paid_voice_enabled
        assert not settings.coach_operator_hash_file and not settings.coach_master_key_file
        assert settings.coach_pack_root == f"{root}/packs"

        def forbidden(*args, **kwargs):
            raise AssertionError("Coach offline runner prohibits network and physical serial/Modbus opens")

        socket.socket.connect = forbidden
        socket.socket.connect_ex = forbidden
        socket.create_connection = forbidden
        # Patch the actual POSIX open method, not Serial's constructor: fake/emulator
        # tests can still construct unopened serial objects. No app.main import here.
        try:
            import serial
        except ModuleNotFoundError as exc:
            if exc.name != "serial":
                raise
        else:
            serial.Serial.open = forbidden
            serial.serial_for_url = forbidden
        from app.services.modbus_service import modbus_service

        modbus_service.connect = forbidden
        import pytest

        print("Coach offline: dotenv off; paid off; vault empty; temporary DB/media/packs; network/serial/Modbus forbidden")
        return pytest.main([
            "app/tests/test_coach_contracts_replay.py", "app/tests/test_coach_lifecycle.py",
            "app/tests/test_coach_u00_replay.py",
            "app/tests/test_coach_u02_facts.py",
            "app/tests/test_coach_u02_workout_plan.py",
            "app/tests/test_coach_u03_completion.py",
            "app/tests/test_coach_u04_context.py",
            "app/tests/test_coach_u05_memory.py",
            "app/tests/test_coach_u06_direction.py",
            "app/tests/test_coach_u07_delivery.py",
            "app/tests/test_coach_live_pilot_tools.py",
            "app/tests/test_coach_control_plane.py", "app/tests/test_coach_e07_corpus.py",
            "app/tests/test_coach_e07_author.py", "app/tests/test_coach_e08_voice.py", "app/tests/test_coach_e09_packs.py",
            "app/tests/test_coach_e10_live.py",
            "app/tests/test_coach_live_scope_binding.py",
            "app/tests/test_coach_live_continuity.py",
            "app/tests/test_stage9_training_api.py", "app/tests/test_stage9_qa.py", "app/tests/test_users_api.py",
            "-q", "--disable-warnings", "-p", "no:cacheprovider",
        ])


if __name__ == "__main__":
    raise SystemExit(main())