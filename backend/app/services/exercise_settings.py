"""Per-user exercise load settings.

The exercise profile is the single source of load settings for an exercise: every workout in
"Мои тренировки", quick start and the runtime read it, and every edit or performed set updates it.
It stores raw builder controls; "effective" values are what a set is actually performed with after
the load mode and tempo modifiers. Runtime endpoints speak effective values, the builder speaks raw.
"""
import math

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, SetResult
from app.models.enums import RuntimeExerciseKind
from app.models.training import UserExerciseState
from app.schemas.runtime import ExerciseProfileSchema, ExerciseSettingsSchema
from app.services.exercise_library import ImportedExercise

PROFILE_KEY = "profile"

BUILDER_LOAD_MODE_RULES = {
    "Обычный вес": {"weight_factor": 1.0, "reps_factor": 1.0, "duration_factor": 1.0, "rest_delta": 0, "description": "Без корректировок: в план попадают заданные вес, повторы, длительность и отдых."},
    "Контроль техники": {"weight_factor": 0.9, "reps_factor": 0.9, "duration_factor": 0.9, "rest_delta": 15, "description": "Для техники план снижает вес и целевые повторы/секунды на 10%, а отдых увеличивает на 15 сек."},
    "Лёгкий режим": {"weight_factor": 0.8, "reps_factor": 0.8, "duration_factor": 0.8, "rest_delta": 15, "description": "Для разгрузки план снижает вес и целевые повторы/секунды на 20%, а отдых увеличивает на 15 сек."},
}

BUILDER_TEMPO_RULES = {
    "Обычный": {"weight_factor": 1.0, "reps_factor": 1.0, "duration_factor": 1.0, "rest_delta": 0, "description": "Без корректировок темпа: параметры остаются такими, как заданы выше."},
    "Плавный": {"weight_factor": 1.0, "reps_factor": 1.0, "duration_factor": 1.1, "rest_delta": 15, "description": "Плавный темп добавляет 15 сек отдыха; если задана длительность, цель по времени увеличивается на 10%."},
    "Контроль эксцентрики": {"weight_factor": 0.9, "reps_factor": 0.9, "duration_factor": 1.15, "rest_delta": 30, "description": "Контроль эксцентрики снижает вес и повторы на 10%, увеличивает заданную длительность на 15% и добавляет 30 сек отдыха."},
}


def load_mode_rule(load_mode: str) -> dict[str, float | int | str]:
    return BUILDER_LOAD_MODE_RULES.get(load_mode, BUILDER_LOAD_MODE_RULES["Обычный вес"])


def tempo_rule(tempo: str) -> dict[str, float | int | str]:
    return BUILDER_TEMPO_RULES.get(tempo, BUILDER_TEMPO_RULES["Обычный"])


def round_half_up(value: float) -> int:
    # Mirrors JavaScript Math.round, unlike Python's banker's rounding.
    return int(math.floor(value + 0.5))


def clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else float(value)


def scale_weight(weight: float, factor: float) -> int | float:
    """Exact working weight (e.g. 47.5 kg) for factor 1; scaled weights round to whole kilograms."""
    return clean_number(max(0.0, float(weight)) if factor == 1 else float(max(0, round_half_up(weight * factor))))


def builder_load_type(exercise: ImportedExercise | None) -> str:
    if exercise and exercise.force == "Static":
        return "timed"
    if exercise and exercise.equipment in {"Bodyweight", "Stretches", "Recovery"}:
        return "bodyweight"
    return "weighted"


def _factors(profile: ExerciseProfileSchema) -> tuple[float, float, float, int]:
    mode, tempo = load_mode_rule(profile.load_mode), tempo_rule(profile.tempo)
    return (
        float(mode["weight_factor"]) * float(tempo["weight_factor"]),
        float(mode["reps_factor"]) * float(tempo["reps_factor"]),
        float(mode["duration_factor"]) * float(tempo["duration_factor"]),
        int(mode["rest_delta"]) + int(tempo["rest_delta"]),
    )


def effective_set_params(load_type: str, set_params: dict[str, int | float], load_mode: str, tempo: str) -> dict[str, int | float]:
    mode, tempo_rules = load_mode_rule(load_mode), tempo_rule(tempo)
    weight_factor = float(mode["weight_factor"]) * float(tempo_rules["weight_factor"])
    result: dict[str, int | float] = {
        "reps": max(1, round_half_up(float(set_params.get("reps", 1)) * float(mode["reps_factor"]) * float(tempo_rules["reps_factor"]))),
        "weight": scale_weight(float(set_params.get("weight", 0)), weight_factor) if load_type == "weighted" else clean_number(max(0.0, float(set_params.get("weight", 0)))),
        "restSeconds": max(15, int(set_params.get("restSeconds", 60)) + int(mode["rest_delta"]) + int(tempo_rules["rest_delta"])),
    }
    duration_seconds = set_params.get("durationSeconds")
    if duration_seconds is not None:
        result["durationSeconds"] = max(1, round_half_up(float(duration_seconds) * float(mode["duration_factor"]) * float(tempo_rules["duration_factor"])))
    if set_params.get("sets") is not None:
        result["sets"] = max(1, int(set_params["sets"]))
    return result


def profile_set_params(profile: ExerciseProfileSchema) -> dict[str, int | float]:
    params: dict[str, int | float] = {
        "sets": profile.sets, "reps": profile.reps,
        # Timed sets ignore weight, but the builder keeps the control's value for a later switch back.
        "weight": clean_number(profile.weight),
        "restSeconds": profile.rest_seconds,
    }
    if profile.load_type == "timed":
        params["durationSeconds"] = profile.duration_seconds or profile.reps
    return params


def profile_settings(profile: ExerciseProfileSchema) -> ExerciseSettingsSchema:
    """Effective values for the runtime. Rest keeps runtime precision (no builder 15 s floor)."""
    weight_factor, reps_factor, duration_factor, rest_delta = _factors(profile)
    if profile.load_type == "timed":
        duration = profile.duration_seconds or profile.reps
        reps = duration if duration_factor == 1 else max(1, round_half_up(duration * duration_factor))
    else:
        reps = profile.reps if reps_factor == 1 else max(1, round_half_up(profile.reps * reps_factor))
    return ExerciseSettingsSchema(
        weight=scale_weight(profile.weight, weight_factor) if profile.load_type == "weighted" else 0,
        sets=profile.sets, reps=reps,
        rest_seconds=max(0, profile.rest_seconds + rest_delta) if rest_delta else profile.rest_seconds,
        mode=profile.load_mode, tempo=profile.tempo,
        training_mode=profile.strength_mode_id, training_day_type=profile.strength_day_type,
    )


def _raw_weight(weight: float, factor: float) -> float:
    return max(0.0, weight if factor == 1 else math.floor(weight / factor * 2 + 0.5) / 2)


def _raw_count(value: int, factor: float) -> int:
    return value if factor == 1 else max(1, round_half_up(value / factor))


def profile_from_effective(
    base: ExerciseProfileSchema, *, weight: float | None = None, reps: int | None = None,
    sets: int | None = None, rest_seconds: int | None = None, convert_all: bool = False,
) -> ExerciseProfileSchema:
    """Apply effective values to a profile.

    By default only fields that differ from the profile's current effective value are converted,
    so repeated round trips never drift through rounding. ``convert_all`` re-derives every given
    field, e.g. after the modifiers themselves changed.
    """
    current = profile_settings(base)
    weight_factor, reps_factor, duration_factor, rest_delta = _factors(base)
    timed = base.load_type == "timed"

    def changed(value: object, previous: object) -> bool:
        return value is not None and (convert_all or value != previous)

    update: dict[str, object] = {}
    if changed(sets, current.sets):
        update["sets"] = sets
    if not timed and changed(weight, current.weight):
        update["weight"] = _raw_weight(float(weight), weight_factor)
        if weight > 0:
            update["load_type"] = "weighted"
    if changed(reps, current.reps):
        raw_reps = _raw_count(int(reps), duration_factor if timed else reps_factor)
        update["reps"] = raw_reps
        if timed:
            update["duration_seconds"] = raw_reps
    if changed(rest_seconds, current.rest_seconds):
        update["rest_seconds"] = max(0, int(rest_seconds) - rest_delta)
    return base.model_copy(update=update) if update else base


def merge_settings(
    profile: ExerciseProfileSchema | None, settings: ExerciseSettingsSchema, exercise: ImportedExercise | None,
) -> ExerciseProfileSchema:
    """Fold effective runtime settings (setup, mid-set weight, load adjustment) into the profile."""
    seeded = profile is None
    if profile is None:
        load_type = builder_load_type(exercise)
        if load_type != "timed" and settings.weight > 0:
            load_type = "weighted"
        profile = ExerciseProfileSchema(load_type=load_type, sets=settings.sets, reps=settings.reps, weight=0,
                                        rest_seconds=settings.rest_seconds)
    base = profile.model_copy(update={
        "load_mode": settings.mode, "tempo": settings.tempo,
        "strength_mode_id": settings.training_mode, "strength_day_type": settings.training_day_type,
    })
    # Runtime values are what the person performs under the NEW modifiers: re-derive raw controls.
    modifiers_changed = (profile.load_mode, profile.tempo) != (base.load_mode, base.tempo)
    return profile_from_effective(base, weight=settings.weight, reps=settings.reps, sets=settings.sets,
                                  rest_seconds=settings.rest_seconds, convert_all=seeded or modifiers_changed)


def last_performed_working_weight(session: Session, user_id: str, slug: str) -> float | None:
    """Working weight of the latest performed working set with a weight, from the set history."""
    statement = (
        select(SetResult)
        .join(ExerciseSession, SetResult.exercise_session_id == ExerciseSession.id)
        .where(ExerciseSession.user_id == user_id, ExerciseSession.exercise_slug == slug,
               SetResult.actual_value > 0, SetResult.weight_kg.is_not(None))
        .order_by(ExerciseSession.started_at.desc(), SetResult.set_number.desc())
    )
    for row in session.scalars(statement):
        metrics = row.machine_metrics or {}
        if metrics.get("setType") == "warmup" or metrics.get("completionStatus") == "skipped":
            continue
        working = metrics.get("workingWeightKg")
        weight = float(working) if isinstance(working, int | float) and not isinstance(working, bool) else float(row.weight_kg or 0)
        # A set without weight (e.g. a bar-only test) does not replace a configured working weight.
        if 0 < weight <= 2000:
            return weight
    return None


def read_profile(state: UserExerciseState | None) -> ExerciseProfileSchema | None:
    if state is None:
        return None
    raw = (state.calibration_payload or {}).get(PROFILE_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return ExerciseProfileSchema.model_validate(raw)
    except ValidationError:
        return None


def store_profile(state: UserExerciseState, profile: ExerciseProfileSchema) -> ExerciseSettingsSchema:
    """Persist the profile with its effective runtime snapshot so every reader sees the same load."""
    settings = profile_settings(profile)
    state.working_weight = settings.weight
    state.working_sets = settings.sets
    state.working_reps = settings.reps
    state.rest_seconds = settings.rest_seconds
    state.calibration_payload = {
        **(state.calibration_payload or {}),
        PROFILE_KEY: profile.model_dump(mode="json", by_alias=True),
        "lastSettings": settings.model_dump(by_alias=True),
    }
    return settings


def remembered_settings(session: Session, state: UserExerciseState | None) -> ExerciseSettingsSchema | None:
    if state is None:
        return None
    profile = read_profile(state)
    if profile is not None:
        return profile_settings(profile)
    metadata = state.calibration_payload or {}
    snapshot = metadata.get("lastSettings")
    if isinstance(snapshot, dict):
        try:
            return ExerciseSettingsSchema.model_validate(snapshot)
        except ValidationError:
            pass
    legacy = metadata.get("lastResult")
    if not isinstance(legacy, dict):
        return None
    reps = legacy.get("repsPerSet", state.working_reps)
    exercise = session.get(ExerciseSession, legacy["exerciseSessionId"]) if legacy.get("exerciseSessionId") else None
    if exercise and exercise.kind in {RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch}:
        targets = [row.planned_value for row in sorted(exercise.set_results, key=lambda row: row.set_number)
                   if row.planned_value > 0 and row.machine_metrics.get("setType") != "warmup"]
        if targets:
            reps = targets[-1]
    try:
        return ExerciseSettingsSchema(
            weight=legacy.get("weightKg", state.working_weight),
            sets=legacy.get("sets", state.working_sets), reps=reps,
            rest_seconds=state.rest_seconds if state.rest_seconds is not None else 60,
            training_mode=legacy.get("trainingMode"), training_day_type=legacy.get("trainingDayType"),
        )
    except ValidationError:
        return None
