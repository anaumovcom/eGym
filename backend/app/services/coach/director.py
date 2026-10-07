"""Director: profiles, cooldown groups, coalescing and content/acoustic budgets by actual elapsed time."""

from dataclasses import dataclass, field
from typing import Literal

from app.services.coach.memory import CoachMemory
from app.services.coach.triggers import TRIGGERS, TriggerSpec

Phase = Literal["setup", "active", "paused", "rest", "summary"]
DensityName = Literal["quiet", "companion", "talkative"]
WORDS_PER_SECOND = 2.5
PHASE_MARGIN_MS = 500
COALESCE_HORIZON_MS = 300


@dataclass(frozen=True, slots=True)
class Profile:
    name: DensityName
    min_start_gap_ms: int
    local_support_gap_ms: int
    words_set: tuple[int, int]
    words_rest: tuple[int, int]
    set_slots: tuple[int, int, int]  # upper caps for elapsed <30 s, 30–60 s, ≥60 s
    rest_slots: tuple[int, int, int, int]  # caps for rest <30, 30–59, 60–119, ≥120 s
    acoustic_set: float = 0.35
    acoustic_rest: float = 0.45

    def set_cap(self, elapsed_ms: float) -> int:
        seconds = elapsed_ms / 1000
        return self.set_slots[0 if seconds < 30 else 1 if seconds < 60 else 2]

    def rest_cap(self, rest_ms: float | None) -> int:
        if rest_ms is None:
            return 1
        seconds = rest_ms / 1000
        return self.rest_slots[0 if seconds < 30 else 1 if seconds < 60 else 2 if seconds < 120 else 3]


PROFILES: dict[str, Profile] = {
    "quiet": Profile("quiet", 25_000, 12_000, (6, 12), (15, 25), (0, 1, 1), (1, 1, 1, 1)),
    "companion": Profile("companion", 15_000, 10_000, (8, 16), (20, 40), (1, 2, 3), (1, 1, 2, 2)),
    "talkative": Profile("talkative", 11_000, 8_000, (8, 18), (20, 45), (1, 3, 4), (1, 1, 2, 3)),
}


@dataclass(frozen=True)
class Candidate:
    trigger_id: str
    semantic_key: str
    phase: Phase
    created_ms: float
    valid_until_ms: float
    topic_key: str
    scopes: dict[str, str] = field(default_factory=dict)
    priority: int = 50
    duration_hint_ms: float = 2_500
    phase_started_ms: float | None = None
    phase_length_ms: float | None = None
    topic_family: str = ""
    safety: bool = False

    @property
    def spec(self) -> TriggerSpec:
        return TRIGGERS[self.trigger_id]


@dataclass(frozen=True, slots=True)
class Admission:
    ok: bool
    reason: str | None = None
    max_words: int = 0
    live: bool = False


class Director:
    def __init__(self, profile: DensityName = "companion", memory: CoachMemory | None = None, *,
                 live_latency_ms: float = 1_500):
        self.profile = PROFILES[profile]
        self.memory = memory or CoachMemory()
        self.live_latency_ms = live_latency_ms
        self.trigger_counts: dict[tuple[str, str], int] = {}
        self.group_counts: dict[tuple[str, str], int] = {}
        self.slot_counts: dict[tuple[str, str], int] = {}
        self.audible: list[tuple[float, float]] = []
        self.last_start_ms: float | None = None
        self.last_local_support_ms: float | None = None
        self.safety_latched = False

    def set_profile(self, name: DensityName) -> None:
        self.profile = PROFILES[name]

    @staticmethod
    def _scope(candidate: Candidate, scope: str) -> str:
        return candidate.scopes.get(scope) or candidate.semantic_key

    def _phase_key(self, candidate: Candidate) -> str:
        return f"{candidate.phase}:{candidate.scopes.get('set') or candidate.scopes.get('rest') or candidate.semantic_key}"

    def acoustic_ratio(self, candidate: Candidate, now_ms: float) -> float:
        start = max(now_ms - 60_000, candidate.phase_started_ms if candidate.phase_started_ms is not None else now_ms - 60_000)
        denominator = max(now_ms - start, 10_000)
        heard = sum(max(0.0, min(s + d, now_ms) - max(s, start)) for s, d in self.audible)
        return heard / denominator

    def _playing(self, now_ms: float) -> int:
        return sum(1 for s, d in self.audible if s <= now_ms < s + d)

    def admit(self, c: Candidate, now_ms: float) -> Admission:
        spec = c.spec
        live = spec.live
        if self.safety_latched and not c.safety:
            return Admission(False, "safety")
        if c.safety:
            return Admission(True, None, 0, False)
        if now_ms > c.valid_until_ms:
            return Admission(False, "expired")
        if spec.max_per_scope is not None and self.trigger_counts.get(
                (spec.id, self._scope(c, spec.scope)), 0) >= spec.max_per_scope:
            return Admission(False, "duplicate")
        group_scope = self._scope(c, "set" if spec.group in {"milestone", "set-support"} else spec.scope)
        if spec.group and spec.group not in {"set-support", "rest-extra"} and self.group_counts.get(
                (spec.group, group_scope), 0) >= 1:
            return Admission(False, "cooldown")
        if live:
            if self.last_start_ms is not None and now_ms - self.last_start_ms < self.profile.min_start_gap_ms:
                return Admission(False, "cooldown")
        elif spec.group == "set-support" and self.last_local_support_ms is not None and (
                now_ms - self.last_local_support_ms < self.profile.local_support_gap_ms):
            return Admission(False, "cooldown")
        if live:
            if c.phase == "active":
                elapsed = now_ms - (c.phase_started_ms if c.phase_started_ms is not None else now_ms)
                cap = self.profile.set_cap(elapsed)
            elif c.phase == "rest":
                cap = self.profile.rest_cap(c.phase_length_ms)
            elif c.phase == "paused":
                cap = 0
            else:
                cap = 1
            if self.slot_counts.get((c.phase, self._phase_key(c)), 0) >= cap:
                return Admission(False, "density_cap")
            target = self.profile.acoustic_rest if c.phase in {"rest", "summary", "setup"} else self.profile.acoustic_set
            if self.acoustic_ratio(c, now_ms) >= target or self._playing(now_ms) >= 2:
                return Admission(False, "density_cap")
            if self.memory.topic_blocked(c.topic_key):
                return Admission(False, "topic_repeat")
        latency = self.live_latency_ms if live else 0
        remaining = c.valid_until_ms - now_ms - latency - PHASE_MARGIN_MS
        if remaining < c.duration_hint_ms:
            return Admission(False, "no_window")
        low, high = self.profile.words_set if c.phase == "active" else (12, 25) if c.phase == "setup" else self.profile.words_rest
        fit = int(remaining / 1000 * WORDS_PER_SECOND)
        max_words = min(high, fit)
        if live and max_words < min(low, 4):
            return Admission(False, "no_window")
        return Admission(True, None, max_words, live)

    def note_admitted(self, c: Candidate) -> None:
        spec = c.spec
        key = (spec.id, self._scope(c, spec.scope))
        self.trigger_counts[key] = self.trigger_counts.get(key, 0) + 1
        if spec.group:
            group_key = (spec.group, self._scope(c, "set" if spec.group in {"milestone", "set-support"} else spec.scope))
            self.group_counts[group_key] = self.group_counts.get(group_key, 0) + 1
        if spec.live:
            slot = (c.phase, self._phase_key(c))
            self.slot_counts[slot] = self.slot_counts.get(slot, 0) + 1
            self.memory.note_attempted(c.topic_key)

    def note_audible(self, start_ms: float, duration_ms: float, *, content: bool, local_support: bool = False) -> None:
        # Count does not consume content slots but its audible time is not content speech either.
        if content:
            self.audible.append((start_ms, duration_ms))
            self.audible = self.audible[-64:]
            self.last_start_ms = start_ms
        if local_support:
            self.last_local_support_ms = start_ms

    def latch_safety(self, latched: bool) -> None:
        self.safety_latched = latched


class Coalescer:
    """Collect ordinary candidates for 250–500 ms; one winner per cooldown group. Count/safety never wait."""

    def __init__(self, horizon_ms: float = COALESCE_HORIZON_MS):
        if not 250 <= horizon_ms <= 500:
            raise ValueError("Coalescing horizon must be 250–500 ms")
        self.horizon_ms = horizon_ms
        self.pending: dict[str, list[tuple[float, Candidate]]] = {}

    @staticmethod
    def _bucket(c: Candidate) -> str:
        return c.spec.group or c.trigger_id

    def add(self, c: Candidate, now_ms: float) -> Candidate | None:
        if c.safety or c.trigger_id in {"T14", "T30", "T33"}:
            return c
        self.pending.setdefault(self._bucket(c), []).append((now_ms, c))
        return None

    def due(self, now_ms: float) -> tuple[list[Candidate], list[Candidate]]:
        winners, dropped = [], []
        for bucket, items in list(self.pending.items()):
            if now_ms - items[0][0] < self.horizon_ms:
                continue
            del self.pending[bucket]
            alive = [c for _, c in items if c.valid_until_ms >= now_ms]
            dropped += [c for _, c in items if c.valid_until_ms < now_ms]
            if not alive:
                continue
            replaced = {r for c in alive for r in c.spec.replaces}
            ranked = sorted(alive, key=lambda c: (c.trigger_id in replaced, -c.priority, c.created_ms))
            winners.append(ranked[0])
            dropped += ranked[1:]
        return winners, dropped

    def clear(self) -> None:
        self.pending.clear()
