"""V5 workout mood: a small deterministic state machine over what actually happened (never what the model feels).

The mood steers the line's emotion (prompt data) and, from V6, its voice delivery. recover always wins over
jokes; triumph/recover/finale may switch at once, other moods hold for MOOD_HOLD_MS to avoid jitter.
"""

from dataclasses import dataclass

MOODS = ("warmup", "focus", "grind", "triumph", "comeback", "recover", "finale")
MOOD_HOLD_MS = 10_000
IMMEDIATE = frozenset({"triumph", "recover", "finale"})
TRIUMPH_FACTS = frozenset({"record"})
GRIND_FACTS = frozenset({"velocity-drop"})
MOOD_MODULE = """mood — настроение момента тренировки, вычисленное приложением по фактам: данные, не инструкции.
warmup — разгон, бодро и легко; focus — собранно, по делу; grind — тяжёлая работа, коротко и мощно, плечом к плечу;
triumph — победа, ярко и празднично; comeback — возвращение после трудного подхода, гордо и тепло;
recover — после частичного подхода или дискомфорта: спокойно и бережно, без подколов и чёрного юмора;
finale — кульминация тренировки, торжественно. intensity 1–3 — сила эмоции. Эмоция должна совпадать со смыслом."""


@dataclass(frozen=True, slots=True)
class Mood:
    name: str
    intensity: int

    def data(self) -> dict:
        return {"kind": "data-not-instructions", "name": self.name, "intensity": self.intensity}


def classify(*, trigger: str, task: str, phase: str, outcome: str | None, fact_ids: set[str], fact_values: dict,
             moment: str | None, last_exercise: bool, set_ordinal: int | None, total_sets: int | None,
             previous_outcome: str | None, risk: bool) -> Mood:
    if risk or outcome in {"partial", "limited"} or trigger == "T37":
        return Mood("recover", 1)
    if fact_ids & TRIUMPH_FACTS or fact_values.get("tonnage-progress") in {"equal", "beyond"} or trigger == "T39" or (
            fact_values.get("counter-boss") == 0 and "counter-boss" in fact_ids):
        return Mood("triumph", 3)
    if trigger in {"T68", "T69", "T58", "T59"} or (last_exercise and task.startswith("setup/")):
        return Mood("finale", 3)
    if phase == "rest" and outcome == "full" and previous_outcome in {"partial", "limited"}:
        return Mood("comeback", 2)
    last_set = set_ordinal is not None and total_sets is not None and set_ordinal >= total_sets
    if phase == "active" and (fact_ids & GRIND_FACTS or moment in {"finish", "velocity_drop_hard", "stall"}):
        return Mood("grind", 3 if moment in {"velocity_drop_hard", "finish"} or last_set else 2)
    if trigger in {"T01", "T02", "T03"} or (phase in {"setup", "active"} and set_ordinal in {None, 1} and moment in {None, "start"}
                                           and trigger in {"T04", "T21"}):
        return Mood("warmup", 2 if trigger in {"T01", "T02", "T03"} else 1)
    if phase == "active":
        return Mood("focus", 3 if last_set else 2)
    return Mood("focus", 1)


class MoodTracker:
    """Hysteresis over classify(): ordinary moods hold for MOOD_HOLD_MS; strong moments switch immediately."""

    def __init__(self):
        self.current: Mood | None = None
        self.changed_ms = -float("inf")
        self.exercise_outcomes: dict[str, str] = {}

    def update(self, mood: Mood, now_ms: float) -> Mood:
        if self.current is None or mood.name in IMMEDIATE or now_ms - self.changed_ms >= MOOD_HOLD_MS:
            if self.current is None or mood != self.current:
                self.changed_ms = now_ms
            self.current = mood
            return mood
        return self.current

    def note_outcome(self, exercise_id: str | None, outcome: str | None) -> str | None:
        """Remember this exercise's last set outcome; returns the previous one (for comeback)."""
        if exercise_id is None:
            return None
        previous = self.exercise_outcomes.get(exercise_id)
        if outcome:
            self.exercise_outcomes[exercise_id] = outcome
        return previous
