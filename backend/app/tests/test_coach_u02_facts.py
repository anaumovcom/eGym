"""U02 factual safety: temporary DB, explicit conditions, fake authors/PCM only."""

import asyncio
import json
from dataclasses import replace

import pytest

from app.models.analytics import ExerciseSession, WorkoutSession
from app.models.analytics import SetResult as SetRow
from app.schemas.coach import CoachEvent
from app.schemas.coach_control import CoachPreferences
from app.services.coach import history
from app.services.coach.facts import AllowedFact, compare, saved_set_facts, target_met
from app.services.coach.prompts import AuthorRequest, build_prompt
from app.services.coach.validation import validate
from app.services.coach.voice import FakeVoiceStream
from app.tests.test_coach_e07_corpus import current
from app.tests.test_coach_e10_live import (
    HYBRID,
    add_set,
    event,
    make_coach,
    seed,
    settle,
    voice,
)


def pair(**changes):
    now = current(**changes)
    return now, replace(now, set_id="previous", value=9, target=9)


@pytest.mark.parametrize("field", ["exercise_kind", "set_type", "load_mode", "range_id", "calibration_id", "count_method",
                                  "weight_kg"])
@pytest.mark.parametrize("side", ["both", "current", "previous"])
def test_missing_required_conditions_never_equal_comparable(field, side):
    now, previous = pair()
    if side in {"both", "current"}:
        now = replace(now, **{field: None})
    if side in {"both", "previous"}:
        previous = replace(previous, **{field: None})
    result = compare(now, previous, "available")
    assert result.status == "limited" and result.delta is None and result.differences
    package = saved_set_facts(now, result, scope_epoch=1, valid_until_ms=5000)
    assert not package.locked_clause and not any(f.id == "comparison" for f in package.facts)


@pytest.mark.parametrize("kind,unit,mode,method", [
    ("machine", "reps", "constant", "sensor"),
    ("bodyweight", "reps", "bodyweight", "manual"),
    ("timed", "seconds", "unloaded", "clock"),
    ("stretch", "seconds", "stretch", "clock"),
])
@pytest.mark.parametrize("set_type", ["working", "warmup"])
def test_kind_policy_explicit_known_conditions(kind, unit, mode, method, set_type):
    now, previous = pair(exercise_kind=kind, progress_unit=unit, load_mode=mode, set_type=set_type,
                         count_method=method, weight_kg=40 if kind == "machine" else None,
                         calibration_id="c1" if kind == "machine" else None)
    result = compare(now, previous, "available")
    assert result.status == "comparable" and result.delta == 1
    package = saved_set_facts(now, result, scope_epoch=1, valid_until_ms=5000)
    assert "плановом весе" in package.locked_clause if kind == "machine" else "При тех же условиях" in package.locked_clause
    assert compare(now, replace(previous, set_type="warmup" if set_type == "working" else "working"),
                   "available").status == "limited"
    assert compare(now, replace(previous, count_method=None), "available").status == "limited"
    assert compare(now, replace(previous, range_id=None), "available").status == "limited"


@pytest.mark.parametrize("mode", ["eccentric", "isometric", "adaptive", "unknown", "n/a", ""])
def test_dynamic_and_unknown_machine_modes_fail_closed_without_profile(mode):
    now, previous = pair(load_mode=mode)
    assert compare(now, previous, "available").status == "limited"


@pytest.mark.parametrize("mode", ["eccentric", "isometric", "adaptive"])
def test_dynamic_mode_needs_explicit_identical_profile(mode):
    now, previous = pair(load_mode=mode, load_profile_id="complete-profile-v1")
    assert compare(now, previous, "available").status == "comparable"
    assert compare(now, replace(previous, load_profile_id="different"), "available").status == "limited"


@pytest.mark.parametrize("kind", ["bodyweight", "timed", "stretch"])
def test_nonmachine_external_load_is_not_implicitly_unloaded(kind):
    now, previous = pair(exercise_kind=kind, load_mode="external", weight_kg=None,
                         progress_unit="reps" if kind == "bodyweight" else "seconds")
    assert compare(now, previous, "available").status == "limited"


@pytest.mark.parametrize("kind", ["bodyweight", "timed", "stretch"])
def test_nonmachine_mode_or_load_contradictions_fail_closed(kind):
    now, previous = pair(exercise_kind=kind, load_mode="bodyweight", weight_kg=None)
    assert compare(now, replace(previous, weight_kg=40), "available").status == "limited"
    assert compare(replace(now, load_mode="constant"), replace(previous, load_mode="constant"),
                   "available").status == "limited"


def test_unknown_result_is_not_zero_or_skipped():
    with pytest.raises(ValueError, match="Confirmed result value required"):
        saved_set_facts(current(value=None), compare(current(), None, "unavailable"), scope_epoch=1, valid_until_ms=5000)
    zero = saved_set_facts(current(value=0), compare(current(), None, "unavailable"), scope_epoch=1, valid_until_ms=5000)
    assert zero.outcome == "partial" and zero.trigger_id == "T37"


@pytest.mark.parametrize("kind,unit", [("machine", "reps"), ("bodyweight", "reps"),
                                       ("timed", "seconds"), ("stretch", "seconds")])
@pytest.mark.parametrize("goal,value,expected", [
    ("exact", 10, "full"), ("exact", 9, "partial"),
    ("range", 8, "full"), ("range", 7, "partial"),
    ("open", 6, "full"), ("unknown", 6, "limited"),
])
def test_saved_goal_matrix_no_label_overrides_missed_goal(kind, unit, goal, value, expected):
    now = current(exercise_kind=kind, progress_unit=unit, value=value,
                  target=10 if goal == "exact" else 12 if goal == "range" else None,
                  target_exact=goal != "range", target_min=8 if goal == "range" else None,
                  target_open=goal == "open")
    result = saved_set_facts(now, compare(now, None, "unavailable"), scope_epoch=1, valid_until_ms=5000)
    assert result.outcome == expected
    assert target_met(now) is (expected == "full")
    claims = {f.id: f.claim for f in result.facts}
    assert ("target" in claims) is (goal in {"exact", "range"})
    assert ("План подхода выполнен" == claims["outcome"]) is (expected == "full" and goal != "open")


def test_weight_and_provenance_are_not_measurement(db_session):
    _, exercise_id, set_id = seed(db_session, actual=10, status="completed")
    exercise = db_session.get(ExerciseSession, exercise_id)
    row = db_session.get(SetRow, set_id)
    exercise.calibration_state = "calibrated"
    row.machine_metrics = {"completionStatus": "completed", "measuredWeightKg": 999, "appliedWeightKg": 888}
    db_session.commit()
    saved = history.load_saved_set(db_session, "alexey", set_id, history_consent=True)
    assert saved.current.calibration_id is None and saved.current.set_type is None
    assert saved.current.applied_weight_kg is None and saved.current.measured_weight_kg is None
    package = saved_set_facts(saved.current, saved.comparison, scope_epoch=1, valid_until_ms=5000)
    weight = next(f for f in package.facts if f.id == "weight")
    assert weight.value == 20 and weight.unit == "kg" and "Плановый" in weight.claim
    assert weight.quantity_kind == "declared" and weight.provenance == "persisted-plan"
    assert weight.observed_at_ms is not None and weight.sufficiency == "sufficient"
    req = AuthorRequest("T36", "rest", "rest/full-feedback", ("factual-feedback",), "result", 30,
                        package.facts, outcome=package.outcome)
    data = json.loads(build_prompt(req).data)
    sent = next(f for f in data["allowedFacts"] if f["id"] == "weight")
    assert sent["quantityKind"] == "declared" and sent["observedAtMs"] == weight.observed_at_ms
    assert sent["unit"] == "kg" and sent["provenance"] == "persisted-plan"
    for text, ok in [("Плановый вес — двадцать килограммов.", True),
                     ("Измеренный вес — двадцать килограммов.", False),
                     ("Двадцать килограммов применено.", False)]:
        payload = {"action": "speak", "intent": "factual-feedback", "topicKey": "result", "text": text,
                   "usedFactIds": ["weight"], "silenceReason": None,
                   "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}
        assert validate(payload, req).ok is ok


@pytest.mark.parametrize("kwargs", [{"provenance": "x" * 121}, {"unit": "x" * 33},
                                   {"observed_at_ms": -1}, {"observed_at_ms": float("nan")}])
def test_fact_provenance_is_optional_and_bounded(kwargs):
    assert AllowedFact("test", "Результат сохранён", "confirmed").observed_at_ms is None
    with pytest.raises(ValueError):
        AllowedFact("test", "Результат сохранён", "confirmed", **kwargs)


@pytest.mark.parametrize("case,expected", [
    ("full", "full"), ("missing-set", "partial"), ("gapped", "partial"), ("extra", "partial"),
    ("unknown-count", "limited"), ("unfinished", "limited"), ("partial", "partial"),
    ("skipped", "partial"), ("unknown-target", "limited"), ("explicit-open", "full"),
])
def test_exercise_summary_uses_plan_count_unique_contiguous_ordinals(db_session, case, expected):
    _, exercise_id, set_id = seed(db_session, actual=10, status="completed")
    exercise = db_session.get(ExerciseSession, exercise_id)
    row = db_session.get(SetRow, set_id)
    if case in {"missing-set", "gapped"}:
        exercise.target_sets = 2
    if case == "gapped":
        add_set(db_session, exercise_id, 3)
    if case == "extra":
        add_set(db_session, exercise_id, 2)
    if case == "unknown-count":
        exercise.target_sets = 0
    if case == "unfinished":
        exercise.status = "in_progress"
    if case == "partial":
        row.actual_value = 7  # stale completionStatus=completed cannot certify this
    if case == "skipped":
        exercise.target_sets = 2
        second = add_set(db_session, exercise_id, 2, actual=0)
        db_session.get(SetRow, second).machine_metrics = {"completionStatus": "skipped"}
    if case in {"unknown-target", "explicit-open"}:
        row.planned_value = 0
        if case == "explicit-open":
            row.machine_metrics = {**row.machine_metrics, "targetType": "open"}
    db_session.commit()
    package = history.exercise_summary(db_session, "alexey", exercise_id, scope_epoch=1, valid_until_ms=5000)
    assert package.outcome == expected
    assert package.trigger_id == ("T55" if expected == "full" else "T56")
    assert any(f.claim == "Все подходы выполнены" for f in package.facts) is (expected == "full")


@pytest.mark.parametrize("kind,unit", [("machine", "reps"), ("bodyweight", "reps"),
                                       ("timed", "seconds"), ("stretch", "seconds")])
@pytest.mark.parametrize("goal", ["exact", "range", "open", "unknown"])
def test_persisted_goal_kind_matrix(db_session, kind, unit, goal):
    _, exercise_id, set_id = seed(db_session, actual=10, status="completed")
    exercise = db_session.get(ExerciseSession, exercise_id)
    exercise.kind = kind
    row = db_session.get(SetRow, set_id)
    if goal == "range":
        row.actual_value, row.planned_value = 8, 12
        row.machine_metrics = {**row.machine_metrics, "targetMinReps": 8, "targetMaxReps": 12}
    if goal in {"open", "unknown"}:
        row.planned_value = 0
        row.machine_metrics = {"targetType": "open", "completionStatus": "completed"} if goal == "open" else {}
    db_session.commit()
    package = history.exercise_summary(db_session, "alexey", exercise_id, scope_epoch=1, valid_until_ms=5000)
    assert package.outcome == ("limited" if goal == "unknown" else "full")
    assert next(f.unit for f in package.facts if f.id == "best-set") == unit
    saved = history.load_saved_set(db_session, "alexey", set_id, history_consent=False)
    assert saved.current.outcome == ("unknown" if goal == "unknown" else "completed")


def test_duplicate_ordinals_cannot_be_counted_twice_or_compared(db_session):
    workout_id, exercise_id, set_id = seed(db_session, actual=10, status="completed")
    source = db_session.get(SetRow, set_id)
    values = {c.key: getattr(source, c.key) for c in source.__table__.columns if c.key not in {"id", "created_at", "updated_at"}}
    db_session.add(SetRow(**values))
    db_session.commit()
    for query in [lambda: history.exercise_summary(db_session, "alexey", exercise_id, scope_epoch=1, valid_until_ms=5000),
                  lambda: history.workout_summary(db_session, "alexey", workout_id, scope_epoch=1, valid_until_ms=5000),
                  lambda: history.load_saved_set(db_session, "alexey", set_id, history_consent=True)]:
        with pytest.raises(history.HistoryError, match="ambiguous_results"):
            query()


@pytest.mark.parametrize("case", ["observed-full", "missing-exercise", "missing-set", "unfinished-exercise",
                                 "skipped-exercise", "duplicate-slug"])
def test_workout_never_certifies_unpersisted_entire_plan(db_session, case):
    workout_id, exercise_id, _ = seed(db_session, actual=10, status="completed")
    workout = db_session.get(WorkoutSession, workout_id)
    workout.status = "completed"
    exercise = db_session.get(ExerciseSession, exercise_id)
    if case == "missing-exercise":
        exercise.order_index = 2  # no legitimate inference that the observed list is the full plan
    if case == "missing-set":
        exercise.target_sets = 2
    if case == "unfinished-exercise":
        exercise.status = "in_progress"
    if case in {"skipped-exercise", "duplicate-slug"}:
        _, extra_id, _ = seed(db_session, actual=10, status="completed")
        extra = db_session.get(ExerciseSession, extra_id)
        extra.workout_session_id = workout_id
        extra.order_index = 2
        if case == "skipped-exercise":
            extra.status = "skipped"
            for row in extra.set_results:
                db_session.delete(row)
    db_session.commit()
    package = history.workout_summary(db_session, "alexey", workout_id, scope_epoch=1, valid_until_ms=5000)
    assert package.outcome in {"partial", "limited"} and package.trigger_id == "T59"
    assert package.notes == ("authoritative_workout_plan_unavailable",)
    assert not any("Все подходы выполнены" in f.claim for f in package.facts)
    if case == "duplicate-slug":
        assert next(f.value for f in package.facts if f.id == "exercises-done") == 2
    req = AuthorRequest("T59", "summary", "summary/workout", ("summary",), "result", 30,
                        package.facts, outcome=package.outcome, summary=True)
    for text in ["Весь план выполнен.", "Все подходы выполнены.", "Все упражнения выполнены."]:
        payload = {"action": "speak", "intent": "summary", "topicKey": "result", "text": text,
                   "usedFactIds": [], "silenceReason": None,
                   "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}
        assert not validate(payload, req).ok


class AfterAuthor:
    def __init__(self, inner, mutate):
        self.inner, self.mutate, self.model = inner, mutate, inner.model

    async def author(self, **kwargs):
        result = await self.inner.author(**kwargs)
        await asyncio.sleep(0)  # explicit asynchronous boundary, after validation/ledger settlement
        self.mutate()
        return result


class BeforePCM(FakeVoiceStream):
    def __init__(self, mutate):
        super().__init__()
        self.mutate = mutate

    async def stream(self, *args, **kwargs):
        await asyncio.sleep(0)
        self.mutate()
        async for chunk in super().stream(*args, **kwargs):
            yield chunk


@pytest.mark.parametrize("stage", ["after-author", "before-pcm"])
@pytest.mark.parametrize("kind,mutation", [
    ("set_persisted", "value"), ("set_persisted", "delete"), ("set_persisted", "plan"),
    ("set_persisted", "conditions"), ("set_persisted", "history"),
    ("exercise_finalized", "value"), ("exercise_finalized", "delete"), ("exercise_finalized", "plan"),
    ("workout_finalized", "value"), ("workout_finalized", "delete"), ("workout_finalized", "plan"),
    ("workout_finalized", "add-exercise"),
])
async def test_source_changes_cannot_start_or_deliver_first_pcm(session_factory, stage, kind, mutation):
    with session_factory() as db:
        _, _, previous_id = seed(db, days_ago=7, actual=9, planned=9, status="completed")
        workout_id, exercise_id, set_id = seed(db, actual=10, status="completed")

    def mutate():
        with session_factory() as db:
            if mutation == "value":
                db.get(SetRow, set_id).actual_value = 6
            elif mutation == "delete":
                db.delete(db.get(SetRow, set_id))
            elif mutation == "plan":
                db.get(ExerciseSession, exercise_id).target_sets = 2
            elif mutation == "conditions":
                row = db.get(SetRow, set_id)
                row.machine_metrics = {**row.machine_metrics, "calibrationId": "new-calibration"}
            elif mutation == "history":
                db.get(SetRow, previous_id).actual_value = 8
            else:
                _, extra, _ = seed(db, actual=10, status="completed")
                db.get(ExerciseSession, extra).workout_session_id = workout_id
            db.commit()

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, history_consent=True))
    if stage == "after-author":
        coach.author = AfterAuthor(coach.author, mutate)
    else:
        coach.voice = voice(session_factory, BeforePCM(mutate))
    refs = {"backendSetId": set_id, "backendExerciseId": exercise_id, "backendWorkoutId": workout_id}
    await coach.handle(event(kind, run_id, set_ordinal=1, phase="rest" if kind == "set_persisted" else
                             "exercise-summary" if kind == "exercise_finalized" else "workout-summary", refs=refs,
                             context={"restMs": 90_000, "restElapsedMs": 0}))
    await settle(coach)
    assert not sink.bytes and not coach.memory.started and not coach.acks
    assert any(m["reason"] == "facts_changed" for m in sink.of("decision")), sink.json
    if stage == "after-author":
        assert not sink.of("speech_start")
    else:
        assert len(sink.of("speech_start")) == 1 and sink.of("speech_end")[-1]["status"] == "cancelled"


async def test_unchanged_dependencies_checked_only_at_two_handoffs(session_factory):
    with session_factory() as db:
        _, _, set_id = seed(db, actual=10, status="completed")
    coach, sink, run_id = make_coach(session_factory)
    coach.voice = voice(session_factory, FakeVoiceStream(parts=(bytes(4800),) * 20))
    original = coach._sources_current
    checks = []

    def checked(op):
        checks.append(op.event_id)
        return original(op)

    coach._sources_current = checked
    await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id},
                             context={"restMs": 90_000}))
    await settle(coach)
    assert len(checks) == 2 and len(sink.bytes) > 2
    assert sink.of("speech_end")[-1]["status"] == "complete"


@pytest.mark.parametrize("text_only", [True, False])
async def test_source_invalidation_also_applies_to_text_and_hidden_numeric_facts(session_factory, text_only):
    with session_factory() as db:
        _, exercise_id, set_id = seed(db, actual=10, status="completed")

    def mutate():
        with session_factory() as db:
            db.get(ExerciseSession, exercise_id).target_sets = 3
            db.commit()

    prefs = CoachPreferences(**{**HYBRID, "mode": "text-only" if text_only else "hybrid", "say_numbers": False})
    coach, sink, run_id = make_coach(session_factory, prefs)
    coach.author = AfterAuthor(coach.author, mutate)
    await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id}))
    await settle(coach)
    assert not sink.of("speech_start") and not sink.bytes
    assert not any(m["action"] == "text" for m in sink.of("decision"))
    assert sink.of("decision")[-1]["reason"] == "facts_changed"


async def test_partial_movement_claim_has_no_inferred_cause(session_factory):
    coach, _, run_id = make_coach(session_factory)
    message = event("rep_completed", run_id, set_ordinal=1, phase="active-set",
                    context={"counterReason": "short-range", "amplitudePercent": 22})
    with session_factory() as db:
        opportunity = coach.plan(db, CoachEvent.model_validate(message["event"]), None, message["context"])
    assert next(f.claim for f in opportunity.package.facts if f.id == "milestone") == "Последнее движение не засчитано"
    req = coach._request(opportunity, 30)
    for text, ok in [("Последнее движение не засчитано.", True),
                     ("Последнее движение не засчитано из-за неполной амплитуды.", False)]:
        output = {"action": "speak", "intent": req.intents[0], "topicKey": req.topic_key, "text": text,
                  "usedFactIds": ["milestone"], "silenceReason": None,
                  "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}
        assert validate(output, req).ok is ok