"""V4 scenario counters: the story's game numbers (glory points, donations, boss health…) computed only from
saved results. The bible picks a label and a source; the formula and coefficient are fixed here, so the model can
voice a value but never invent one.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession
from app.models.analytics import SetResult as SetRow
from app.services.coach.facts import AllowedFact, number_words

# source → points per unit. «plan» is the share of planned sets done, in percent.
COEFFICIENTS = {"reps": 10, "tonnage": 1, "sets": 100, "records": 1000, "steady": 250, "plan": 1}
BOSS_ARCHETYPES = {"rpg": "Здоровье босса", "kaiju": "Здоровье монстра"}
MAX_VALUE = 999_999


@dataclass(frozen=True, slots=True)
class Totals:
    reps: int = 0
    tonnage: int = 0
    sets: int = 0


def workout_totals(db: Session, workout_id: int | None, user_id: str) -> Totals:
    if workout_id is None:
        return Totals()
    rows = db.execute(select(SetRow, ExerciseSession).join(ExerciseSession, SetRow.exercise_session_id == ExerciseSession.id)
                      .where(ExerciseSession.workout_session_id == workout_id, ExerciseSession.user_id == user_id)).all()
    reps = tonnage = sets = 0
    for row, exercise in rows:
        value = row.actual_value if row.actual_value and row.actual_value > 0 else 0
        if not value:
            continue
        sets += 1
        if str(exercise.kind) not in {"timed", "stretch"}:
            reps += value
            if row.weight_kg and row.weight_kg > 0:
                tonnage += round(value * row.weight_kg)
    return Totals(reps, tonnage, sets)


def values(bible: dict, totals: Totals, *, records: int, steady: int) -> list[dict]:
    planned = sum(e.get("sets", 0) for e in bible.get("plan", [])) or 0
    raw = {"reps": totals.reps, "tonnage": totals.tonnage, "sets": totals.sets, "records": records, "steady": steady,
           "plan": min(100, round(100 * totals.sets / planned)) if planned else 0}
    found = []
    for counter in bible.get("counters", []):
        source = counter.get("source")
        if source in COEFFICIENTS:
            found.append({"id": counter["id"], "label": counter["label"], "source": source,
                          "value": min(MAX_VALUE, raw[source] * COEFFICIENTS[source])})
    return found


def boss_health(bible: dict, archetype: str, exercise_id: str | None, boss_sets_done: int) -> dict | None:
    """Boss worlds: the last exercise is the boss; each of its finished sets takes an equal share of its health."""
    plan = bible.get("plan", [])
    if archetype not in BOSS_ARCHETYPES or not plan or plan[-1]["id"] != exercise_id or not plan[-1].get("sets"):
        return None
    health = max(0, 100 - round(100 * boss_sets_done / plan[-1]["sets"]))
    return {"id": "boss", "label": BOSS_ARCHETYPES[archetype], "source": "boss", "value": health}


def boss_sets_done(db: Session, exercise_session_id: int | None) -> int:
    if exercise_session_id is None:
        return 0
    return len(db.scalars(select(SetRow.id).where(SetRow.exercise_session_id == exercise_session_id,
                                                  SetRow.actual_value > 0)).all())


def facts(counters: list[dict], common: dict) -> list[AllowedFact]:
    found = []
    for counter in counters:
        value = counter["value"]
        if counter["id"] == "boss":
            claim = (f"{counter['label']}: осталось {number_words(value)} процентов" if value else
                     f"{counter['label']} на нуле: босс повержен")
        else:
            claim = f"{counter['label']}: {number_words(value)}"
        found.append(AllowedFact(f"counter-{counter['id']}", claim[:200], "derived-validated", value,
                                 numbers=(value,) if value else (),
                                 **{**common, "provenance": "scenario-counter", "quantity_kind": "derived",
                                    "sufficiency": "sufficient"}))
    return found
