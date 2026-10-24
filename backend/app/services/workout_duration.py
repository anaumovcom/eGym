"""Workout duration estimate for the builder and the home screen.

Time is split into three parts, each modelled separately:

* work — reps × rep time plus per-set overhead (taking position, unracking, confirming the set).
  Rep time depends on the movement (compound vs isolation), the tempo setting and how heavy
  the set is: relative intensity comes from the user's e1RM when history exists, otherwise from
  the planned reps + reps in reserve (inverse Epley). Sets close to failure add grinding reps.
* rest — planned rest between sets plus the overrun people actually take (more after heavy sets).
* transitions — between exercises: summary/setup screens and the pre-start check, walking to
  another station, rolling the bench in/out or changing its angle, and a distraction allowance
  (water, towel, phone). Rest after the last set of an exercise is absorbed by the transition.

Coefficients were sanity-checked against real sessions in the local DB: the old formula
(reps × 4 s + planned rest) underestimated a 5-exercise workout by ~35%, almost all of it
in transitions (2–5 min each) and rest overrun.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from app.schemas.training import BuilderExerciseItemSchema
from app.services.exercise_library import ImportedExercise, get_imported_exercise

BenchPosition = Literal["none", "flat", "incline", "decline", "seated"]

REP_SECONDS = {"Compound": 2.8, "Isolation": 2.4}
TEMPO_FACTORS = {"Обычный": 1.0, "Плавный": 1.25, "Контроль эксцентрики": 1.4}
SET_SETUP_SECONDS = 10
HEAVY_SET_SETUP_SECONDS = 6
TIMED_SET_SETUP_SECONDS = 10
SIDE_SWITCH_SECONDS = 8
DEFAULT_RIR = 2.0
# Extra time per grinding rep near failure, in rep-times (the last reps are about twice as slow).
GRIND_REPS = 2.0

REST_OVERRUN_SECONDS = 5
REST_OVERRUN_SHARE = 0.08
HEAVY_REST_OVERRUN_SHARE = 0.12

TRANSITION_SECONDS = {"weighted": 75, "bodyweight": 50, "timed": 40}
SAME_EXERCISE_TRANSITION_SECONDS = 30
STATION_CHANGE_SECONDS = 30
BENCH_MOVE_SECONDS = 45
BENCH_ADJUST_SECONDS = 25
DISTRACTION_SECONDS = 45

FLOOR_EQUIPMENT = frozenset({"Bodyweight", "Cardio", "Stretches", "Yoga", "Recovery", "Band", "TRX", "Bosu-Ball", "Medicine-Ball"})
FLAT_BENCH_SLUG_MARKERS = ("bench", "skullcrusher", "lying", "hip-thrust", "pullover", "prone", "chest-supported")


@dataclass(frozen=True)
class DurationEstimate:
    work_seconds: int = 0
    rest_seconds: int = 0
    transition_seconds: int = 0

    @property
    def total_seconds(self) -> int:
        return self.work_seconds + self.rest_seconds + self.transition_seconds

    @property
    def minutes(self) -> int:
        return max(1, int(round(self.total_seconds / 60))) if self.total_seconds > 0 else 0


@dataclass(frozen=True)
class _PlannedSet:
    reps: float | None
    seconds: int | None
    weight_kg: float
    rest_seconds: int
    rir: float | None


def estimate_workout_duration(
    items: Iterable[BuilderExerciseItemSchema],
    *,
    tempo_by_slug: Mapping[str, str] | None = None,
    e1rm_by_slug: Mapping[str, float] | None = None,
) -> DurationEstimate:
    """Items in execution order; the runtime walks groups sequentially, so groups do not matter here."""
    tempo_by_slug = tempo_by_slug or {}
    e1rm_by_slug = e1rm_by_slug or {}
    work = rest = transition = 0.0
    previous: BuilderExerciseItemSchema | None = None
    for item in items:
        exercise = get_imported_exercise(item.slug)
        transition += transition_seconds(previous, item)
        item_work, item_rest = _exercise_seconds(item, exercise, tempo_by_slug.get(item.slug), e1rm_by_slug.get(item.slug))
        work += item_work
        rest += item_rest
        previous = item
    return DurationEstimate(int(round(work)), int(round(rest)), int(round(transition)))


def transition_seconds(previous: BuilderExerciseItemSchema | None, item: BuilderExerciseItemSchema) -> float:
    """Time from the last set of ``previous`` to the first set of ``item`` (or from the workout start)."""
    exercise = get_imported_exercise(item.slug)
    bench = bench_position(exercise, item.slug)
    if previous is None:
        return TRANSITION_SECONDS[_load_type(item)] + _bench_change_seconds("none", bench)
    if previous.slug == item.slug:
        return SAME_EXERCISE_TRANSITION_SECONDS
    previous_exercise = get_imported_exercise(previous.slug)
    seconds = TRANSITION_SECONDS[_load_type(item)] + DISTRACTION_SECONDS
    if _station(previous_exercise) != _station(exercise):
        seconds += STATION_CHANGE_SECONDS
    return seconds + _bench_change_seconds(bench_position(previous_exercise, previous.slug), bench)


def bench_position(exercise: ImportedExercise | None, slug: str) -> BenchPosition:
    """The catalog has no bench field, so it is read from the slug and the setup steps."""
    steps = " ".join(exercise.steps).lower() if exercise is not None else ""
    if exercise is not None and exercise.equipment in FLOOR_EQUIPMENT and "скамь" not in steps:
        return "none"
    if "incline" in slug or "под углом" in steps:
        return "incline"
    if "decline" in slug:
        return "decline"
    if "seated" in slug or "сядьте на скамью" in steps:
        return "seated"
    if any(marker in slug for marker in FLAT_BENCH_SLUG_MARKERS) or "скамь" in steps:
        return "flat"
    return "none"


def _bench_change_seconds(before: BenchPosition, after: BenchPosition) -> int:
    if before == after:
        return 0
    if before == "none" or after == "none":
        return BENCH_MOVE_SECONDS
    return BENCH_ADJUST_SECONDS


def _station(exercise: ImportedExercise | None) -> str:
    if exercise is None or exercise.equipment in FLOOR_EQUIPMENT:
        return "floor"
    return exercise.equipment


def _load_type(item: BuilderExerciseItemSchema) -> str:
    if item.load_type:
        return item.load_type
    if "сек" in item.sets:
        return "timed"
    return "bodyweight" if "вес" in item.load.lower() else "weighted"


def _exercise_seconds(item: BuilderExerciseItemSchema, exercise: ImportedExercise | None, tempo: str | None, e1rm: float | None) -> tuple[float, float]:
    sets = _planned_sets(item)
    if not sets:
        return 0.0, 0.0
    rep_seconds = REP_SECONDS.get(exercise.mechanic if exercise is not None else "", REP_SECONDS["Compound"]) * TEMPO_FACTORS.get(tempo or "", 1.0)
    sides = 2 if item.per_side else 1
    work = rest = 0.0
    for index, planned in enumerate(sets):
        if planned.seconds is not None:
            set_work, heaviness = planned.seconds + TIMED_SET_SETUP_SECONDS, 0.0
        else:
            set_work, heaviness = _rep_set_seconds(planned, rep_seconds, e1rm)
        work += set_work * sides + (SIDE_SWITCH_SECONDS if sides == 2 else 0)
        if index < len(sets) - 1:
            rest += planned.rest_seconds * (1 + REST_OVERRUN_SHARE + HEAVY_REST_OVERRUN_SHARE * heaviness) + REST_OVERRUN_SECONDS
    return work, rest


def _rep_set_seconds(planned: _PlannedSet, rep_seconds: float, e1rm: float | None) -> tuple[float, float]:
    """Seconds for one set of reps and its heaviness (0 — light, 1 — near-maximal or to failure)."""
    reps = planned.reps or 1.0
    rir = planned.rir if planned.rir is not None else DEFAULT_RIR
    intensity = _plan_intensity(reps, rir)
    if planned.weight_kg > 0:
        # History can only make the set easier than the plan implies: a stale or warm-up-only e1RM
        # must not turn a 12-rep set into a near-maximal one.
        plan_e1rm = planned.weight_kg / intensity
        intensity = planned.weight_kg / max(e1rm or 0.0, plan_e1rm)
        rir = max(0.0, 30 * (1 / intensity - 1) - reps)
    load = _clamp((intensity - 0.6) / 0.4)
    grind = _clamp((3 - rir) / 3)
    seconds = reps * rep_seconds * (1 + 0.35 * load) + GRIND_REPS * grind * rep_seconds
    return seconds + SET_SETUP_SECONDS + HEAVY_SET_SETUP_SECONDS * load, max(load, grind)


def _plan_intensity(reps: float, rir: float) -> float:
    """Inverse Epley: share of 1RM that allows reps + rir repetitions."""
    return 1 / (1 + min(reps + rir, 30) / 30)


def _planned_sets(item: BuilderExerciseItemSchema) -> list[_PlannedSet]:
    timed = _load_type(item) == "timed"
    if item.strength_plan:
        result: list[_PlannedSet] = []
        last_reps: float | None = None
        for plan in item.strength_plan:
            if timed:
                result.append(_PlannedSet(None, _seconds(plan.target_reps_label) or _seconds(item.sets) or 45, 0.0, plan.rest_seconds, None))
                continue
            reps = _range_middle(plan.target_reps_label)
            if reps is None:
                # "максимум": a failure set after work sets lands a couple of reps past their target.
                reps = (last_reps or _range_middle(item.sets.split("×", 1)[-1]) or 10) + 2
            last_reps = reps
            rir = 0.0 if plan.set_type == "failure" else _range_middle(plan.rir_label)
            result.append(_PlannedSet(reps, None, _weight(plan.recommended_weight_label), plan.rest_seconds, rir))
        return result

    head, _, tail = item.sets.partition("×")
    count = int(head) if head.strip().isdigit() else 1
    rest = _first_int(item.rest) or 90
    if timed:
        return [_PlannedSet(None, _seconds(item.sets) or 45, 0.0, rest, None)] * count
    return [_PlannedSet(_range_middle(tail) or 1.0, None, _weight(item.load), rest, None)] * count


def _range_middle(label: str) -> float | None:
    """'12' → 12, '8–12' → 10: people land mid-range (reps and reps in reserve alike)."""
    values = [int(value) for value in re.findall(r"\d+", label)][:2]
    return sum(values) / len(values) if values else None




def _seconds(label: str) -> int | None:
    matches = re.findall(r"(\d+)\s*сек", label, re.IGNORECASE)
    return max(1, int(matches[-1])) if matches else None


def _weight(label: str) -> float:
    match = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*кг", label)
    return float(match.group(1).replace(",", ".")) if match else 0.0


def _first_int(label: str) -> int | None:
    match = re.search(r"\d+", label)
    return int(match.group(0)) if match else None


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
