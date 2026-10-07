"""Dependency-injected ports; no HTTP, secrets, database writes or motor commands."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.schemas.coach import CoachAudio, CoachDecision, CoachEvent, CoachScope


class Clock(Protocol):
    def now_ms(self) -> float: ...


class TextProvider(Protocol):
    test_only: bool

    async def generate(self, event: CoachEvent) -> CoachDecision: ...


@dataclass(frozen=True)
class AudioChunk:
    metadata: CoachAudio
    data: bytes


class VoiceAdapter(Protocol):
    test_only: bool

    def stream(self, text: str, scope: CoachScope, generation_id: str) -> AsyncIterator[AudioChunk]: ...


class PackStorage(Protocol):
    def get_verified(self, pack_version: str, clip_id: str) -> bytes | None: ...


class AudioManager(Protocol):
    """Start/completed acknowledgements belong to playback, not generation."""

    def enqueue(self, chunk: AudioChunk) -> None: ...

    def cancel_scope(self, scope: CoachScope) -> None: ...