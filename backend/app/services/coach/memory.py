"""Audibility memory: attempted/started/completed ledgers, diversity state and fact-mention guard."""

import hashlib
import re
from collections import deque
from dataclasses import dataclass

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


class CoachMemory:
    def __init__(self, *, recent: int = 6):
        self.attempted_topics: deque[str] = deque(maxlen=16)
        self.started: dict[str, Utterance] = {}
        self.completed: set[str] = set()
        self.fact_mentions: dict[tuple[str, str], int] = {}
        self.openings: deque[str] = deque(maxlen=recent)
        self.topics: deque[str] = deque(maxlen=recent)
        self.fingerprints: deque[str] = deque(maxlen=64)
        self.combinations: deque[tuple[str, str, str]] = deque(maxlen=1)
        self.humor_streak = 0
        self.motif_by_exercise: dict[str, str] = {}
        self.callbacks: set[str] = set()

    # attempted: never re-request a topic that already timed out / was rejected.
    def note_attempted(self, topic_key: str) -> None:
        self.attempted_topics.append(topic_key)

    def topic_blocked(self, topic_key: str) -> bool:
        return topic_key in self.topics or topic_key in self.attempted_topics

    def opening_blocked(self, text: str) -> bool:
        head = opening(text)
        return bool(head) and head in self.openings

    def repeated(self, text: str) -> bool:
        return fingerprint(text) in self.fingerprints

    def combination_blocked(self, family: str, form: str, energy: str) -> bool:
        return bool(self.combinations) and self.combinations[-1] == (family, form, energy)

    def humor_allowed(self) -> bool:
        return self.humor_streak < 2

    def motif_allowed(self, exercise_id: str | None, motif: str) -> bool:
        return exercise_id is None or self.motif_by_exercise.get(exercise_id) in {None, motif}

    def callback_allowed(self, motif: str) -> bool:
        done = {u.motif for u in self.started.values() if u.utterance_id in self.completed and u.motif}
        return motif in done and motif not in self.callbacks

    def fact_allowed(self, fact_id: str, value: object, *, summary: bool) -> bool:
        # One main feedback plus one short summary highlight per result value.
        count = self.fact_mentions.get((fact_id, repr(value)), 0)
        return count == 0 or (summary and count == 1)

    def note_started(self, utterance: Utterance, facts: dict[str, object] | None = None, *, callback: bool = False) -> None:
        self.started[utterance.utterance_id] = utterance
        if len(self.started) > 256:
            self.started.pop(next(iter(self.started)))
        if not utterance.content:
            return
        self.openings.append(opening(utterance.text))
        self.topics.append(utterance.topic_key)
        self.fingerprints.append(fingerprint(utterance.text))
        self.combinations.append((utterance.topic_family, utterance.form, utterance.energy))
        self.humor_streak = self.humor_streak + 1 if utterance.humor else 0
        if utterance.motif and utterance.exercise_id:
            self.motif_by_exercise.setdefault(utterance.exercise_id, utterance.motif)
        if callback and utterance.motif:
            self.callbacks.add(utterance.motif)
        for fact_id, value in (facts or {}).items():
            key = (fact_id, repr(value))
            self.fact_mentions[key] = self.fact_mentions.get(key, 0) + 1

    def note_completed(self, utterance_id: str) -> None:
        # API completion is not playback completion; only the audio manager reports this.
        if utterance_id in self.started:
            self.completed.add(utterance_id)

    def recent_topics(self) -> list[str]:
        return list(self.topics)

    def recent_openings(self) -> list[str]:
        return list(self.openings)
