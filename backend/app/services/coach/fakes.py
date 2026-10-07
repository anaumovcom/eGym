"""Explicit synthetic-only fixtures. No browser playback, network or DB persistence."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from app.schemas.coach import CoachAudio, CoachDecision, CoachEvent, CoachScope
from app.services.coach.ports import AudioChunk


@dataclass
class FakeClock:
    value_ms: float = 0

    def now_ms(self) -> float:
        return self.value_ms

    def advance(self, delta_ms: float) -> None:
        if delta_ms < 0:
            raise ValueError("Clock must be monotonic")
        self.value_ms += delta_ms


@dataclass
class FakeTextProvider:
    test_only: bool = field(default=True, init=False)
    decision: CoachDecision = field(default_factory=lambda: CoachDecision(action="speak", text="Работаем в своём ритме."))
    after_generate: Callable[[], None] | None = None
    calls: int = field(default=0, init=False)

    async def generate(self, event: CoachEvent) -> CoachDecision:
        self.calls += 1
        if self.after_generate:
            self.after_generate()
        return self.decision


@dataclass
class FakeVoiceAdapter:
    test_only: bool = field(default=True, init=False)
    before_chunk: Callable[[], None] | None = None
    calls: int = field(default=0, init=False)

    async def stream(self, text: str, scope: CoachScope, generation_id: str) -> AsyncIterator[AudioChunk]:
        self.calls += 1
        if self.before_chunk:
            self.before_chunk()
        data = bytes(320)  # 10 ms of silence, explicitly fake; not a chosen voice
        yield AudioChunk(CoachAudio(
            utterance_id=generation_id, generation_id=generation_id, scope=scope, sequence=0,
            source="fake", codec="pcm_s16le", sample_rate=16_000,
            byte_length=len(data), duration_ms=10, final=True,
        ), data)


@dataclass
class FakePackStorage:
    clips: dict[tuple[str, str], bytes] = field(default_factory=dict)

    def get_verified(self, pack_version: str, clip_id: str) -> bytes | None:
        return self.clips.get((pack_version, clip_id))


@dataclass
class FakeAudioManager:
    received: list[AudioChunk] = field(default_factory=list)

    def enqueue(self, chunk: AudioChunk) -> None:
        if len(self.received) >= 256:
            raise ValueError("Fake audio buffer full")
        self.received.append(chunk)

    def cancel_scope(self, scope: CoachScope) -> None:
        self.received = [chunk for chunk in self.received if chunk.metadata.scope != scope]