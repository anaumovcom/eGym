"""Audibility memory: attempted/started/completed ledgers, diversity state and fact-mention guard."""

import hashlib
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, replace

_WORD = re.compile(r"[а-яёa-z0-9-]+", re.IGNORECASE)


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("ё", "е"))


def opening(text: str) -> str:
    return " ".join(words(text)[:2])


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(words(text)).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Utterance:
    utterance_id: str
    trigger_id: str
    topic_key: str
    text: str
    started_ms: float
    duration_ms: float
    exercise_id: str | None = None
    topic_family: str = ""
    form: str = ""
    energy: str = ""
    motif: str | None = None
    humor: bool = False
    content: bool = True
    intent: str | None = None
    tip_id: str | None = None
    tip_version: str | None = None
    discussed_facts: tuple[tuple[str, str, str], ...] = ()  # id, source record, provenance
    callback: bool = False
    phase_key: str = ""


class CoachMemory:
    def __init__(self, *, recent: int = 6, enabled: bool = True):
        self.enabled = enabled
        self.revision = 0
        self.attempted_topics: deque[str] = deque(maxlen=1024)
        self.attempted: dict[str, dict] = {}  # Metadata only; failed drafts never become heard speech.
        self.started: dict[str, Utterance] = {}
        self.completed: set[str] = set()
        self.interrupted: set[str] = set()
        self.fact_mentions: dict[tuple[str, str], int] = {}
        self.openings: deque[str] = deque(maxlen=recent)
        self.topics: deque[str] = deque(maxlen=recent)
        self.fingerprints: deque[str] = deque(maxlen=64)
        self.combinations: deque[tuple[str, str, str]] = deque(maxlen=2)
        self.humor_streak = 0
        self.motif_by_exercise: dict[str, str] = {}
        self.callbacks: set[str] = set()
        self.completed_tips: dict[tuple[str, str], str] = {}
        self.motif: str | None = None

    def clear(self) -> None:
        # Clear in place: cached and active references must not resurrect old memory.
        revision = self.revision + 1
        self.__init__(enabled=self.enabled)
        self.revision = revision

    # attempted: never re-request a topic that already timed out / was rejected.
    def note_attempted(self, topic_key: str, *, tip_id: str | None = None, tip_version: str | None = None,
                       category: str = "", intent: str | None = None) -> None:
        if self.enabled and topic_key not in self.attempted_topics:
            self.attempted_topics.append(topic_key[:600])
        if self.enabled:
            key = topic_key[:600]
            previous = self.attempted.get(key, {})
            self.attempted[key] = {"tipId": tip_id or previous.get("tipId"),
                                   "tipVersion": tip_version or previous.get("tipVersion"),
                                   "category": category[:80] or previous.get("category", ""),
                                   "intent": intent or previous.get("intent")}
            while len(self.attempted) > 1024:
                self.attempted.pop(next(iter(self.attempted)))

    def topic_blocked(self, topic_key: str) -> bool:
        return topic_key in self.topics or topic_key in self.attempted_topics

    def opening_blocked(self, text: str) -> bool:
        head = opening(text)
        return bool(head) and head in self.openings

    def repeated(self, text: str) -> bool:
        return fingerprint(text) in self.fingerprints

    def combination_blocked(self, family: str, form: str, energy: str) -> bool:
        # A new exercise can reasonably share warmth/intent with the greeting.
        # Reject the third identical combination, not every adjacent motivation;
        # exact text/opening/topic repetition has independent stricter guards.
        return len(self.combinations) == 2 and all(c == (family, form, energy) for c in self.combinations)

    def humor_allowed(self) -> bool:
        return self.humor_streak < 2

    def motif_allowed(self, exercise_id: str | None, motif: str) -> bool:
        return self.enabled and self.motif in {None, motif}

    def callback_allowed(self, motif: str, *, now_ms: float | None = None, phase_key: str = "") -> bool:
        done = {u.motif for u in self.started.values() if u.utterance_id in self.completed and u.motif}
        intros = [u for u in self.started.values() if u.motif == motif and not u.callback
                  and u.utterance_id in self.completed]
        return (self.enabled and motif in done and motif not in self.callbacks and bool(intros)
                and (now_ms is None or now_ms - intros[-1].started_ms >= 60_000)
                and (not phase_key or phase_key != intros[-1].phase_key))

    def tip_completed(self, tip_id: str, version: str) -> bool:
        return (tip_id, version) in self.completed_tips

    def heard(self) -> tuple[dict, ...]:
        """Started ACK means some audio was heard, not that the whole draft was heard."""
        return tuple({"text": u.text[:600], "intent": u.intent, "category": u.topic_family[:80],
                      "status": "completed" if u.utterance_id in self.completed else
                      "interrupted" if u.utterance_id in self.interrupted else "started",
                      "fullTextHeard": u.utterance_id in self.completed,
                      "tipId": u.tip_id, "tipVersion": u.tip_version,
                      "facts": [{"id": f[0], "record": f[1], "provenance": f[2]}
                                for f in u.discussed_facts[:12]]}
                     for u in list(self.started.values())[-5:]) if self.enabled else ()

    def fact_allowed(self, fact_id: str, value: object, *, summary: bool) -> bool:
        # One main feedback plus one short summary highlight per result value.
        count = self.fact_mentions.get((fact_id[:600], repr(value)[:600]), 0)
        return count == 0 or (summary and count == 1)

    def note_started(self, utterance: Utterance, facts: dict[str, object] | None = None, *, callback: bool = False) -> None:
        if not self.enabled or utterance.utterance_id in self.started:
            return
        if utterance.motif and not self.motif_allowed(utterance.exercise_id, utterance.motif):
            utterance = replace(utterance, motif=None)
        utterance = replace(utterance, text=utterance.text[:600],
                            discussed_facts=tuple(tuple(str(v)[:200] for v in f) for f in utterance.discussed_facts[:12]))
        self.started[utterance.utterance_id] = utterance
        if len(self.started) > 256:
            oldest = next(iter(self.started))
            self.started.pop(oldest)
            self.completed.discard(oldest)
            self.interrupted.discard(oldest)
        if not utterance.content:
            return
        self.openings.append(opening(utterance.text))
        self.topics.append(utterance.topic_key)
        self.fingerprints.append(fingerprint(utterance.text))
        self.combinations.append((utterance.topic_family, utterance.form, utterance.energy))
        joking = utterance.intent == "humor" if utterance.intent is not None else utterance.humor
        self.humor_streak = self.humor_streak + 1 if joking else 0
        if utterance.motif and self.motif_allowed(utterance.exercise_id, utterance.motif):
            self.motif = utterance.motif
        if utterance.motif and utterance.exercise_id:
            self.motif_by_exercise.setdefault(utterance.exercise_id, utterance.motif)
        if callback and utterance.motif:
            self.callbacks.add(utterance.motif)
        for fact_id, value in (facts or {}).items():
            key = (fact_id[:600], repr(value)[:600])
            self.fact_mentions[key] = self.fact_mentions.get(key, 0) + 1
        while len(self.fact_mentions) > 1024:
            self.fact_mentions.pop(next(iter(self.fact_mentions)))
        while len(self.motif_by_exercise) > 256:
            self.motif_by_exercise.pop(next(iter(self.motif_by_exercise)))

    def note_completed(self, utterance_id: str) -> None:
        # API completion is not playback completion; only the audio manager reports this.
        if utterance_id in self.started and utterance_id not in self.interrupted:
            self.completed.add(utterance_id)
            u = self.started[utterance_id]
            if u.tip_id and u.tip_version:
                self.completed_tips[(u.tip_id, u.tip_version)] = u.utterance_id
                while len(self.completed_tips) > 256:
                    self.completed_tips.pop(next(iter(self.completed_tips)))

    def note_interrupted(self, utterance_id: str) -> None:
        if utterance_id in self.started and utterance_id not in self.completed:
            self.interrupted.add(utterance_id)

    def update_duration(self, utterance_id: str, duration_ms: float) -> None:
        if utterance_id in self.started:
            self.started[utterance_id] = replace(self.started[utterance_id], duration_ms=duration_ms)

    def recent_topics(self) -> list[str]:
        return list(self.topics)

    def recent_openings(self) -> list[str]:
        return list(self.openings)


class RunMemoryStore:
    """Process-local, no event/audio replay. Hard 24h TTL (not renewed on reconnect)."""

    def __init__(self, *, capacity: int = 32, ttl_s: float = 86400, clock=time.monotonic):
        self.capacity, self.ttl_s, self.clock = capacity, ttl_s, clock
        self.entries: OrderedDict[tuple[str, str], tuple[float, CoachMemory, object, set[str]]] = OrderedDict()

    def prune(self) -> None:
        for key, entry in list(self.entries.items()):
            if self.clock() >= entry[0]:
                entry[1].clear()
                del self.entries[key]

    def attach(self, user: str, run: str, memory: CoachMemory, director: object, seen: set[str]):
        self.prune()
        key = (user, run)
        if key in self.entries:
            return self.entries[key][1:]
        while len(self.entries) >= self.capacity:
            _, entry = self.entries.popitem(last=False)
            entry[1].clear()
        self.entries[key] = (self.clock() + self.ttl_s, memory, director, seen)
        return memory, director, seen

    def forget(self, user: str) -> int:
        keys = [key for key in self.entries if key[0] == user]
        for key in keys:
            self.entries.pop(key)[1].clear()
        return len(keys)


class CrossWorkoutStore:
    """Separate opt-in, enum preferences only. No speech, bio, feelings or inferred achievements.

    At most 128 users; fixed seven-day retention; backend restart loses this cache.
    Saved preferences remain in the existing preference DB, not a new memory table.
    """

    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.entries: OrderedDict[str, tuple[float, str, dict]] = OrderedDict()

    def forget(self, user: str) -> None:
        self.entries.pop(user, None)

    def exchange(self, user: str, run: str, prefs) -> dict:
        for key, entry in list(self.entries.items()):
            if self.clock() >= entry[0]:
                self.forget(key)
        if not (prefs.memory_enabled and prefs.cross_workout_memory and prefs.consent_version == 1):
            self.forget(user)
            return {}
        previous = self.entries.get(user)
        result = dict(previous[2]) if previous and previous[1] != run else {}
        # Explicitly saved enum preferences, never user free text or analytics.
        data = {key: getattr(prefs, key) for key in ("style", "humor", "verbosity", "praise")}
        if previous is None or previous[2] != data:
            self.entries[user] = (self.clock() + 7 * 86400, run, data)
        while len(self.entries) > 128:
            self.entries.popitem(last=False)
        return result

    def current(self, user: str) -> dict:
        entry = self.entries.get(user)
        if entry and self.clock() < entry[0]:
            return dict(entry[2])
        self.forget(user)
        return {}
