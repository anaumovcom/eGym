"""Run E02–E04 contracts/control-plane regressions without network or physical hardware."""

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
            DATABASE_URL=f"sqlite:///{root}/bootstrap.db", MEDIA_ROOT=f"{root}/media",
            OPENAPI_EXPORT_PATH=f"{root}/openapi.json",
        )
        from app.core.config import Settings, get_settings

        Settings.model_config["env_file"] = None
        get_settings.cache_clear()
        settings = get_settings()
        assert settings.hardware_adapter == "emulator" and not settings.hardware_panel_enabled
        assert settings.database_url == f"sqlite:///{root}/bootstrap.db"

        def forbidden(*args, **kwargs):
            raise AssertionError("E02 prohibits network and physical Modbus connections")

        socket.socket.connect = forbidden
        socket.socket.connect_ex = forbidden
        from app.services.modbus_service import modbus_service

        modbus_service.connect = forbidden
        import pytest

        print("Coach E02–E04: dotenv off; temporary DB/media; emulator; network/Modbus connect forbidden")
        return pytest.main([
            "app/tests/test_coach_contracts_replay.py", "app/tests/test_coach_lifecycle.py",
            "app/tests/test_coach_control_plane.py", "app/tests/test_coach_e07_corpus.py",
            "app/tests/test_coach_e07_author.py", "app/tests/test_coach_e08_voice.py", "app/tests/test_coach_e09_packs.py",
            "app/tests/test_coach_e10_live.py",
            "app/tests/test_stage9_training_api.py", "app/tests/test_stage9_qa.py", "app/tests/test_users_api.py",
            "-q", "--disable-warnings", "-p", "no:cacheprovider",
        ])


if __name__ == "__main__":
    raise SystemExit(main())