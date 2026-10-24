"""Explicit operator-paid pack preparation. No generation on GET or workout auto-restore."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.coach_control import Pricing
from app.services.coach import ledger, packs, security
from app.services.coach.voice import (
    FishVoiceAdapter,
    RealtimeVoiceAdapter,
    TtsVoiceAdapter,
    voice_pricing,
    websocket_connect,
)


@dataclass
class PackProvider:
    voice: packs.PackVoice
    pricing: Pricing
    close: Callable[[], Awaitable[None]]


def provider(sessions: Callable[[], Session], slot: str) -> PackProvider:
    cfg = get_settings()
    kind, voice = packs.pack_kind(slot), packs.provider_voice(slot)
    price = voice_pricing(kind)
    if not cfg.coach_enabled or not cfg.coach_paid_voice_enabled or not price.verified:
        raise HTTPException(503, "pack_generation_disabled")
    with sessions() as db:
        # The ledger pins the OpenAI operator credential even on Fish-only runs.
        key, _ = security.read_credential(db)
        fish_key, _ = security.read_credential(db, "fish") if kind == "fish" else (None, None)
    client = httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False)
    if kind == "fish":
        adapter = FishVoiceAdapter(client, fish_key, model=price.model, reference_id="" if voice == "default" else voice)
    elif kind == "tts":
        adapter = TtsVoiceAdapter(client, key, model=price.model, voice=voice)
    else:
        adapter = RealtimeVoiceAdapter(websocket_connect, key, model=price.model, voice=voice, keep_alive=True,
                                       reasoning_effort=cfg.coach_voice_realtime_reasoning_effort)

    async def close():
        try:
            if kind == "realtime":
                await adapter.aclose()
        finally:
            await client.aclose()

    return PackProvider(packs.ProviderPackVoice(adapter), price, close)


ProviderFactory = Callable[[Callable[[], Session], str], PackProvider]
# Bound concurrent provider work in this worker. Database ledger limits remain authoritative for spending.
active_slots: set[str] = set()


def require_job_schema(sessions: Callable[[], Session]) -> None:
    with sessions() as db:
        schema = inspect(db.get_bind())
        if not schema.has_table("coach_jobs") or "failures" not in {col["name"] for col in schema.get_columns("coach_jobs")}:
            raise HTTPException(503, "coach_schema_outdated")


async def generate(sessions: Callable[[], Session], selected: PackProvider, store: packs.PackStore,
                   slot: str, run_id: str, job_id: str, owner: str, generation: int) -> None:
    try:
        runner = packs.PackJobRunner(sessions, selected.voice, selected.pricing, store,
                                     slot=slot, model=selected.pricing.model)
        await runner.run(job_id, owner, generation)
    except Exception as error:
        # Runner persists paused/failed and settles or marks outstanding usage. Never expose provider bodies/secrets.
        packs.logger.error("pack_generation_stopped job=%s slot=%s reason=%s error_type=%s",
                           job_id, slot, packs.safe_error_reason(error), type(error).__name__)
    finally:
        try:
            await selected.close()
        except Exception as error:
            packs.logger.error("pack_cleanup_failed job=%s stage=close_provider error_type=%s", job_id, type(error).__name__)
        try:
            with sessions() as db:
                ledger.cancel_run(db, run_id, close=True)
        except Exception as error:
            packs.logger.error("pack_cleanup_failed job=%s stage=close_run error_type=%s", job_id, type(error).__name__)
        active_slots.discard(slot)