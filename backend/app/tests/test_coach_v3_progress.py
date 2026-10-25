"""V3: personal records, tonnage vs the last similar workout, regularity and muscle readiness — DB facts by owner."""

import json
from datetime import UTC, datetime, timedelta

from app.schemas.coach_control import CoachPreferences
from app.schemas.runtime import ExerciseSessionCreateSchema, SetResultSaveSchema, WorkoutSessionCreateSchema
from app.services.coach import progress
from app.services.coach.luna import FakeTextAuthor
from app.services.runtime_service import RuntimeService
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, settle

EPOCH = {"scope_epoch": 1, "valid_until_ms": 10**13}


def workout(db, *, days_ago=0, sets=((20, 8),), slug="machine-pulldown", name="Тяга сверху", status="completed"):
    """One workout with one exercise; `sets` are (planned weight kg, reps) all completed at target."""
    service = RuntimeService()
    started = datetime.now(UTC) - timedelta(days=days_ago)
    saved = service.save_workout_session(db, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Synthetic", started_at=started, status="in_progress"))
    exercise = service.save_exercise_session(db, ExerciseSessionCreateSchema(
        user_id="alexey", workout_session_id=saved.workout_session_id, exercise_slug=slug, exercise_name=name,
        kind="machine", status=status, started_at=started, target_sets=len(sets), training_mode="constant")).exercise_session.id
    ids = []
    for number, (weight, reps) in enumerate(sets, 1):
        ids.append(service.save_set_result(db, SetResultSaveSchema(
            exercise_session_id=exercise, set_number=number, planned_value=reps, actual_value=reps, reps=reps,
            weight_kg=weight, tempo_label="unknown", set_type="working",
            machine_metrics={"completionStatus": "completed", "loadMode": "constant"})).set_id)
    return saved.workout_session_id, exercise, ids


def test_no_record_in_the_first_session_even_if_set_two_beats_set_one(db_session):
    _, _, ids = workout(db_session, sets=((20, 8), (25, 8)))
    assert progress.personal_records(db_session, "alexey", ids[1], **EPOCH) == []


def test_weight_reps_and_strength_records(db_session):
    workout(db_session, days_ago=7, sets=((20, 10), (25, 6)))
    _, _, [heavier] = workout(db_session, days_ago=3, sets=((30, 5),))
    [weight] = progress.personal_records(db_session, "alexey", heavier, **EPOCH)
    assert weight.value == "weight" and "record" in weight.permits and not weight.numbers
    _, _, [reps] = workout(db_session, days_ago=2, sets=((25, 8),))
    [rep_record] = progress.personal_records(db_session, "alexey", reps, **EPOCH)
    assert rep_record.value == "reps" and rep_record.numbers == (6,) and "record-comparison" in rep_record.permits
    assert rep_record.claim.endswith("прежний максимум — шесть повторений")
    _, _, [same] = workout(db_session, days_ago=1, sets=((20, 9),))
    assert progress.personal_records(db_session, "alexey", same, **EPOCH) == []


def test_exercise_volume_record_and_tonnage_marks(db_session):
    previous, _, _ = workout(db_session, days_ago=7, sets=((20, 10), (20, 10)))  # 400 kg
    today, exercise, _ = workout(db_session, sets=((20, 10), (25, 10)))  # 450 kg
    assert progress.exercise_volume_record(db_session, "alexey", exercise, **EPOCH).value == "volume"
    tonnage = progress.tonnage(db_session, "alexey", today)
    assert tonnage.previous == 400 and tonnage.today == 450
    assert progress.tonnage_mark(tonnage.share) == "equal"
    assert [progress.tonnage_mark(x) for x in (0.4, 0.55, 0.85, 1.25)] == [None, "half", "most", "beyond"]
    assert progress.tonnage(db_session, "alexey", previous).previous is None


def test_regularity_first_jubilee_streak_and_gap(db_session):
    found, status = progress.regularity(db_session, "alexey", current_workout_id=None, **EPOCH)
    assert status == "empty_confirmed" and found[0].id == "first-workout"
    for days in (40, 39, 38, 37, 36, 35, 34, 33, 32):
        workout(db_session, days_ago=days)
    found, status = progress.regularity(db_session, "alexey", current_workout_id=None, **EPOCH)
    ids = {f.id: f for f in found}
    assert status == "available" and ids["jubilee"].numbers == (10,) and "десять" in ids["jubilee"].claim
    assert ids["gap"].numbers == (32,) and "week-streak" not in ids
    for days in (14, 7):
        workout(db_session, days_ago=days)
    found, _ = progress.regularity(db_session, "alexey", current_workout_id=None, **EPOCH)
    streak = next(f for f in found if f.id == "week-streak")
    assert streak.numbers[0] >= 3 and "недели" in streak.claim or "недель" in streak.claim


def test_muscle_facts_from_catalog_and_fatigue(db_session):
    found = progress.muscle_facts(db_session, "alexey", "machine-pulldown", **EPOCH)
    assert found[0].claim == "Работают бицепс и широчайшие"
    assert found[1].value == "fresh"
    assert progress.muscle_facts(db_session, "alexey", "no-such-exercise", **EPOCH) == []


async def test_live_record_leads_the_set_result(session_factory):
    seen = []

    def script(body):
        data = json.loads(body["input"][0]["content"])
        seen.append(data)
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        used = list(data["lockedFactIds"]) or ["record"]
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": used,
                "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "result"},
                key: "Личный рекорд! С таким весом ты ещё не работал."}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, history_consent=True),
                                     fake_text=FakeTextAuthor(script))
    with session_factory() as db:
        workout(db, days_ago=7, sets=((20, 10),))
        _, _, [set_id] = workout(db, sets=((30, 10),))
    await coach.handle(event("set_persisted", run_id, exercise="ex-1", set_ordinal=1, phase="rest",
                             refs={"backendSetId": set_id}, context={"restMs": 90_000}))
    await settle(coach)
    assert sink.of("speech_start") and sink.of("speech_start")[0]["triggerId"] == "T43", sink.of("decision")
    request = seen[-1]
    assert "личный рекорд" not in request["forbiddenClaims"]
    assert any(f["id"] == "record" for f in request["allowedFacts"])
    assert any(f["id"] == "tonnage-progress" for f in request["allowedFacts"])  # 300 vs 200 kg: beyond
    await coach.close()
