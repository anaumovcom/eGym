"""V3 progress facts read from the DB by owner: personal records, live tonnage against the last similar workout,
regularity (jubilees, weekly streaks, gaps) and muscle readiness. All need the user's history consent.

Records compare only comparable sets (same exercise and load mode, completed, with a known planned weight) and
never call the first session of an exercise a record. Claims are fixed server text; numbers appear only where
the validator can bind them to the fact.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, WorkoutSession
from app.models.analytics import SetResult as SetRow
from app.services.coach import facts
from app.services.coach.facts import AllowedFact, number_words, plural_ru, spoken_quantity
from app.services.exercise_library import get_imported_exercise
from app.services.fatigue_service import FatigueService
from app.services.muscle_catalog import CANONICAL_MUSCLE_DEFINITIONS

E1RM_MAX_REPS = 12
RECORD_MARGIN = 1.01
JUBILEES = frozenset({5, 10, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500, 750, 1000})
GAP_DAYS = 14
TONNAGE_MARKS = ((1.2, "beyond"), (1.0, "equal"), (0.8, "most"), (0.5, "half"))
TONNAGE_CLAIMS = {"half": "Пройдена половина объёма прошлой похожей тренировки",
                  "most": "Пройдено уже больше трёх четвертей объёма прошлой похожей тренировки",
                  "equal": "Объём прошлой похожей тренировки уже повторён",
                  "beyond": "Объём прошлой похожей тренировки превышен больше чем на пятую часть"}
SIMILAR_OVERLAP = 0.6
LOADED_SCORE, FRESH_SCORE = 30.0, 10.0


def _common(ref: str, scope_epoch: int, valid_until_ms: float, **extra) -> dict:
    return {"scope_epoch": scope_epoch, "valid_until_ms": valid_until_ms, "ref": ref, "provenance": "persisted-analytics",
            "quantity_kind": "derived", "sufficiency": "sufficient", **extra}


def _e1rm(weight: float, reps: int) -> float | None:
    return weight * (1 + reps / 30) if 0 < reps <= E1RM_MAX_REPS and weight > 0 else None


def personal_records(db: Session, user_id: str, set_id: int, *, scope_epoch: int, valid_until_ms: float) -> list[AllowedFact]:
    """#15: a weight record, a rep record at this weight or better estimated strength — at most one, the strongest."""
    row = db.get(SetRow, set_id)
    exercise = db.get(ExerciseSession, row.exercise_session_id) if row else None
    if row is None or exercise is None or exercise.user_id != user_id:
        return []
    from app.services.coach.history import to_fact_set  # Local import: history imports the live coach's helpers.
    current = to_fact_set(row, exercise)
    if (current.progress_unit != "reps" or not current.value or not current.weight_kg
            or current.outcome != "completed"):
        return []
    mode = current.load_mode
    earlier_rows = db.execute(
        select(SetRow, ExerciseSession).join(ExerciseSession, SetRow.exercise_session_id == ExerciseSession.id)
        .where(ExerciseSession.user_id == user_id, ExerciseSession.exercise_slug == exercise.exercise_slug,
               SetRow.id != row.id)).all()
    earlier, past_sessions = [], set()
    for other, session in earlier_rows:
        before = (session.started_at < exercise.started_at) or (session.id == exercise.id and other.set_number < row.set_number)
        if before and (result := to_fact_set(other, session)) and (
                result.progress_unit == "reps" and result.value and result.value > 0 and result.weight_kg
                and result.weight_kg > 0 and result.outcome == "completed" and result.load_mode == mode):
            earlier.append(result)
            if session.id != exercise.id:
                past_sessions.add(session.id)
    if not earlier or not past_sessions:
        return []  # The first session of an exercise is a start, not a record (even if set 2 beats set 1).
    common = _common(f"set:{set_id}", scope_epoch, valid_until_ms, observed_at_ms=current.observed_at_ms)
    top_weight = max(e.weight_kg for e in earlier)
    if current.weight_kg > top_weight + 0.25:
        return [AllowedFact("record", "Личный рекорд: с таким рабочим весом это упражнение ещё не выполнялось",
                            "derived-validated", "weight", permits=("record",), **common)]
    heavier = [e.value for e in earlier if e.weight_kg >= current.weight_kg - 1e-6]
    if heavier and current.value > max(heavier):
        best = max(heavier)
        return [AllowedFact("record", f"Личный рекорд повторений с этим весом: прежний максимум — "
                            f"{spoken_quantity(best, 'reps')}", "derived-validated", "reps",
                            permits=("record", "record-comparison"), numbers=(best,), unit="reps", **common)]
    now_e1rm = _e1rm(current.weight_kg, current.value)
    past = [v for e in earlier if (v := _e1rm(e.weight_kg, e.value)) is not None]
    if now_e1rm and past and now_e1rm > max(past) * RECORD_MARGIN:
        return [AllowedFact("record", "Личный рекорд силы в этом упражнении: лучшее сочетание веса и повторений",
                            "derived-validated", "e1rm", permits=("record",), **common)]
    return []


def _volume(rows: list[facts.SetResult]) -> float:
    return sum(r.value * r.weight_kg for r in rows if r.progress_unit == "reps" and r.value and r.weight_kg
               and r.outcome != "skipped")


def _session_sets(db: Session, exercise: ExerciseSession) -> list[facts.SetResult]:
    from app.services.coach.history import to_fact_set
    return [to_fact_set(row, exercise) for row in db.scalars(select(SetRow).where(SetRow.exercise_session_id == exercise.id))]


def exercise_volume_record(db: Session, user_id: str, exercise_id: int, *, scope_epoch: int,
                           valid_until_ms: float) -> AllowedFact | None:
    exercise = db.get(ExerciseSession, exercise_id)
    if exercise is None or exercise.user_id != user_id:
        return None
    volume = _volume(_session_sets(db, exercise))
    if volume <= 0:
        return None
    previous = db.scalars(select(ExerciseSession).where(
        ExerciseSession.user_id == user_id, ExerciseSession.exercise_slug == exercise.exercise_slug,
        ExerciseSession.id != exercise.id, ExerciseSession.started_at < exercise.started_at)).all()
    volumes = [v for session in previous if (v := _volume(_session_sets(db, session))) > 0]
    if volumes and volume > max(volumes) * RECORD_MARGIN:
        return AllowedFact("record", "Рекорд объёма в этом упражнении: столько ещё не поднималось за одну тренировку",
                           "derived-validated", "volume", permits=("record",),
                           **_common(f"exercise:{exercise_id}", scope_epoch, valid_until_ms))
    return None


@dataclass(frozen=True, slots=True)
class Tonnage:
    today: float
    previous: float | None

    @property
    def share(self) -> float | None:
        return self.today / self.previous if self.previous else None


def _workout_slugs(db: Session, workout: WorkoutSession) -> set[str]:
    from app.services.coach.workout_plan import load_plan
    plan = load_plan(db, workout.id)
    baseline = plan.baseline if plan is not None and isinstance(plan.baseline, dict) else {}
    slugs = {e.get("slug") for e in baseline.get("exercises", []) if isinstance(e, dict) and isinstance(e.get("slug"), str)}
    if not slugs:
        slugs = set(db.scalars(select(ExerciseSession.exercise_slug).where(ExerciseSession.workout_session_id == workout.id)))
    return slugs


def _workout_volume(db: Session, workout_id: int) -> float:
    sessions = db.scalars(select(ExerciseSession).where(ExerciseSession.workout_session_id == workout_id)).all()
    return sum(_volume(_session_sets(db, session)) for session in sessions)


def tonnage(db: Session, user_id: str, workout_id: int) -> Tonnage | None:
    """#16: today's lifted tonnage vs the most recent earlier workout with mostly the same exercises."""
    workout = db.get(WorkoutSession, workout_id)
    if workout is None or workout.user_id != user_id:
        return None
    today = _workout_volume(db, workout_id)
    slugs = _workout_slugs(db, workout)
    if today <= 0 or not slugs:
        return Tonnage(today, None)
    candidates = db.scalars(select(WorkoutSession).where(
        WorkoutSession.user_id == user_id, WorkoutSession.id != workout_id,
        WorkoutSession.started_at < workout.started_at).order_by(WorkoutSession.started_at.desc()).limit(20)).all()
    for candidate in candidates:
        other = _workout_slugs(db, candidate)
        if other and len(slugs & other) / len(slugs) >= SIMILAR_OVERLAP and (volume := _workout_volume(db, candidate.id)) > 0:
            return Tonnage(today, volume)
    return Tonnage(today, None)


def tonnage_mark(share: float | None) -> str | None:
    if share is None:
        return None
    return next((mark for bound, mark in TONNAGE_MARKS if share >= bound), None)


def tonnage_fact(mark: str, *, ref: str, scope_epoch: int, valid_until_ms: float) -> AllowedFact:
    return AllowedFact("tonnage-progress", TONNAGE_CLAIMS[mark], "derived-validated", mark,
                       **_common(ref, scope_epoch, valid_until_ms))


def _week(value: datetime) -> tuple[int, int]:
    iso = value.isocalendar()
    return iso[0], iso[1]


def regularity(db: Session, user_id: str, *, current_workout_id: int | None, now: datetime | None = None,
               scope_epoch: int, valid_until_ms: float) -> tuple[list[AllowedFact], str]:
    """#17: jubilee number, weekly streak, a long gap, or the very first workout (history status for the validator)."""
    now = now or datetime.now(UTC)
    workouts = db.scalars(select(WorkoutSession).where(WorkoutSession.user_id == user_id)
                          .order_by(WorkoutSession.started_at)).all()
    done = []
    for workout in workouts:
        if workout.id == current_workout_id:
            continue
        has_sets = db.scalar(select(SetRow.id).join(ExerciseSession).where(
            ExerciseSession.workout_session_id == workout.id, SetRow.actual_value > 0).limit(1))
        if has_sets is not None:
            done.append(workout)
    common = _common(f"regularity:{user_id}", scope_epoch, valid_until_ms)
    if not done:
        return [AllowedFact("first-workout", "Это первая тренировка в приложении", "derived-validated", True, **common)], \
            "empty_confirmed"
    found = []
    number = len(done) + 1
    if number in JUBILEES:
        found.append(AllowedFact("jubilee", f"Сегодня юбилей: это тренировка номер {number_words(number)}",
                                 "derived-validated", number, numbers=(number,), **common))
    weeks = {_week(w.started_at.replace(tzinfo=w.started_at.tzinfo or UTC)) for w in done} | {_week(now)}
    streak, cursor = 0, now
    while _week(cursor) in weeks:
        streak += 1
        cursor -= timedelta(days=7)
    if streak >= 2:
        found.append(AllowedFact("week-streak", f"Тренировки идут {number_words(streak, 'f')} "
                                 f"{plural_ru(streak, 'неделю', 'недели', 'недель')} подряд", "derived-validated",
                                 streak, numbers=(streak,), **common))
    last = done[-1].started_at
    last = last if last.tzinfo else last.replace(tzinfo=UTC)
    gap = (now - last).days
    if gap >= GAP_DAYS:
        found.append(AllowedFact("gap", f"Прошлая тренировка была {number_words(gap)} "
                                 f"{plural_ru(gap, 'день', 'дня', 'дней')} назад", "derived-validated", gap,
                                 numbers=(gap,), **common))
    return found, "available"


def muscles(slug: str | None) -> tuple[str, ...]:
    entry = get_imported_exercise(slug) if slug else None
    return tuple(m for m in (entry.muscles if entry else ()) if m in CANONICAL_MUSCLE_DEFINITIONS)


def muscle_facts(db: Session, user_id: str, slug: str | None, *, scope_epoch: int, valid_until_ms: float,
                 now: datetime | None = None) -> list[AllowedFact]:
    """#18: which muscles work (catalog) and whether today's workout has already loaded them (fatigue snapshots)."""
    targets = muscles(slug)
    if not targets:
        return []
    names = [CANONICAL_MUSCLE_DEFINITIONS[m].name.lower() for m in targets[:2]]
    listed = names[0] if len(names) == 1 else f"{names[0]} и {names[1]}"
    common = _common(f"muscles:{slug}", scope_epoch, valid_until_ms, provenance="exercise-catalog-muscles",
                     sufficiency="limited")
    found = [AllowedFact("muscles", f"Работают {listed}", "confirmed", listed, **common)]
    now = now or datetime.now(UTC)
    scores = {s.muscle_id: s for s in FatigueService().list_current_scores(db, user_id, now)}
    relevant = [scores[m] for m in targets if m in scores]
    today = [s for s in relevant if s.last_load_at is not None
             and (s.last_load_at if s.last_load_at.tzinfo else s.last_load_at.replace(tzinfo=UTC)) > now - timedelta(hours=6)]
    if today and max(s.fatigue_score for s in today) >= LOADED_SCORE:
        found.append(AllowedFact("muscle-readiness", "Эти мышцы сегодня уже поработали в прошлых упражнениях",
                                 "derived-validated", "loaded", **{**common, "provenance": "fatigue-snapshots"}))
    elif not relevant or max(s.fatigue_score for s in relevant) < FRESH_SCORE:
        found.append(AllowedFact("muscle-readiness", "Эти мышцы сегодня ещё свежие", "derived-validated", "fresh",
                                 **{**common, "provenance": "fatigue-snapshots"}))
    return found
