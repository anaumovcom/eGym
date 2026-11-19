"""Bundled Russian recordings. Reads never synthesize; the native engine is loaded only by an explicit edit/build."""

import ctypes as c
import json
import os
import threading
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

SLOT = "ru-base"
VOICE = "ru"
MODEL = "espeak-ng-ru-v1"
BUNDLE = Path(__file__).with_name("data") / "ru-base.zip"
_lock = threading.Lock()  # eSpeak's voice, parameters and callback are process-global.
_callback = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_int, c.c_void_p)


def manifest() -> dict:
    # The builder can atomically replace BUNDLE while this process is alive.
    with ZipFile(BUNDLE) as archive:
        return json.loads(archive.read("manifest.json"))


def history_member(version: str) -> str:
    return f"versions/{version}.json"


def archived_manifest(version: str) -> dict | None:
    with ZipFile(BUNDLE) as archive:
        try:
            raw = archive.read(history_member(version))
        except KeyError:
            return None
        return json.loads(raw)


def recording(fingerprint: str) -> bytes | None:
    with ZipFile(BUNDLE) as archive:
        try:
            return archive.read(f"{fingerprint}.wav")
        except KeyError:
            return None


@lru_cache(maxsize=1)
def _engine():
    from espeakng_loader import get_data_path, get_library_path

    lib = c.CDLL(get_library_path())
    lib.espeak_Initialize.argtypes = [c.c_int, c.c_int, c.c_char_p, c.c_int]
    lib.espeak_SetVoiceByName.argtypes = [c.c_char_p]
    lib.espeak_SetParameter.argtypes = [c.c_int, c.c_int, c.c_int]
    lib.espeak_SetSynthCallback.argtypes = [_callback]
    lib.espeak_SetSynthCallback.restype = None
    lib.espeak_Synth.argtypes = [c.c_char_p, c.c_size_t, c.c_uint, c.c_int, c.c_uint, c.c_uint, c.c_void_p, c.c_void_p]
    # AUDIO_OUTPUT_SYNCHRONOUS: captures PCM, never opens a speaker. DONT_EXIT on a missing data directory.
    rate = lib.espeak_Initialize(2, 0, os.fsencode(Path(get_data_path()).parent), 0x8000)
    if not 8000 <= rate <= 48000 or lib.espeak_SetVoiceByName(VOICE.encode()) != 0:
        raise RuntimeError("local_voice_unavailable")
    return lib, rate


def synthesize(text: str, pace: str = "normal") -> tuple[bytes, int]:
    speed = {"normal": 158, "slow": 135, "brisk": 180}[pace]
    chunks: list[bytes] = []

    @_callback
    def collect(ptr, samples, _events):
        if ptr and samples > 0:
            chunks.append(c.string_at(ptr, samples * 2))
        return 0

    with _lock:
        lib, rate = _engine()
        lib.espeak_SetSynthCallback(collect)
        try:
            encoded = text.encode("utf-8")
            if lib.espeak_SetParameter(1, speed, 0) or lib.espeak_Synth(encoded, len(encoded) + 1, 0, 1, 0, 1, None, None) or not chunks:
                raise RuntimeError("local_voice_unavailable")
        finally:
            lib.espeak_SetSynthCallback(_callback())
    return b"".join(chunks), rate