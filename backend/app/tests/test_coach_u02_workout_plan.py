"""U02.4 optional migration and end-to-end intent, temporary databases only."""

import copy
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.analytics import CoachWorkoutPlan, ExerciseSession, SetResult, WorkoutSession
from app.schemas.runtime import (
    CoachWorkoutPlanSchema,
    ExerciseSessionCreateSchema,
    SetResultSaveSchema,
    WorkoutSessionCreateSchema,
)
from app.services.coach import history
from app.services.coach.prompts import AuthorRequest
from app.services.coach.validation import validate
from app.services.runtime_service import RuntimeService
from app.tests.test_coach_e10_live import event, make_coach, settle, voice
from app.tests.test_coach_u02_facts import AfterAuthor, BeforePCM


def migration():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/20261017_0012_coach_workout_plans.py"
    spec = importlib.util.spec_from_file_location("coach_plan_0012", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plan_table(session_factory):
    with session_factory().get_bind().begin() as connection:
        assert not inspect(connection).has_table("coach_workout_plans")
        with Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()


def declared(*, count=1, goal="exact", per_side=False):
    return {"schemaVersion": 1, "origin": "declared-client-plan", "exercises": [
        {"exerciseId": f"occurrence-{i}", "orderIndex": i, "slug": "machine-pulldown", "kind": "machine",
         "perSide": per_side, "trainingMode": "constant", "trainingDayType": None,
         "sets": [{"ordinal": j, "side": ("left" if j == 1 else "right") if per_side else None,
                   "roundNumber": 1 if per_side else None, "setType": "working", "targetType": goal,
                   "unit": "reps", "minimum": 8 if goal == "range" else 10 if goal == "exact" else None,
                   "maximum": 12 if goal == "range" else 10 if goal == "exact" else None,
                   "plannedWeightKg": 20, "restSeconds": 60} for j in range(1, 3 if per_side else 2)]}
        for i in range(1, count + 1)]}


def payload(plan=None, **changes):
    return WorkoutSessionCreateSchema(user_id="alexey", source="catalog", title="Synthetic",
                                      started_at=datetime.now(UTC), status=changes.pop("status", "in_progress"),
                                      coach_plan=CoachWorkoutPlanSchema.model_validate(plan) if plan else None, **changes)


def populate(db, plan, *, create=True):
    service = RuntimeService()
    workout_id = service.save_workout_session(db, payload(plan if create else None)).workout_session_id
    for intended in plan["exercises"]:
        ex = service.save_exercise_session(db, ExerciseSessionCreateSchema(
            user_id="alexey", workout_session_id=workout_id, exercise_slug=intended["slug"],
            exercise_name="Тяга сверху", kind=intended["kind"], order_index=intended["orderIndex"],
            status="completed", started_at=datetime.now(UTC), target_sets=len(intended["sets"]),
            per_side=intended["perSide"], training_mode=intended["trainingMode"])).exercise_session
        for target in intended["sets"]:
            goal = target["targetType"]
            service.save_set_result(db, SetResultSaveSchema(
                exercise_session_id=ex.id, set_number=target["ordinal"],
                planned_value=target["maximum"] or 0, actual_value=target["minimum"] or 6,
                weight_kg=target["plannedWeightKg"], tempo_label="unknown", set_type="work",
                target_min_reps=target["minimum"] if goal == "range" else None,
                target_max_reps=target["maximum"] if goal == "range" else None,
                machine_metrics={"completionStatus": "completed", "side": target["side"],
                                 "roundNumber": target["roundNumber"],
                                 **({"targetType": "open"} if goal == "open" else {})}))
    service.save_workout_session(db, payload(plan, workout_session_id=workout_id, status="completed"))
    return workout_id


def summary(db, workout_id):
    return history.workout_summary(db, "alexey", workout_id, scope_epoch=1, valid_until_ms=10**13)


def test_optional_table_not_in_startup_metadata_and_migration_roundtrip(db_session):
    connection = db_session.connection()
    assert "coach_workout_plans" not in WorkoutSession.metadata.tables
    assert not inspect(connection).has_table("coach_workout_plans")
    with Operations.context(MigrationContext.configure(connection)):
        migration().upgrade()
        assert inspect(connection).has_table("coach_workout_plans")
        fk = inspect(connection).get_foreign_keys("coach_workout_plans")[0]
        assert fk["referred_table"] == "workout_sessions" and fk["options"]["ondelete"] == "CASCADE"
        migration().downgrade()
    assert not inspect(connection).has_table("coach_workout_plans")


def test_missing_migration_preserves_runtime_saves_but_cannot_certify(db_session):
    workout_id = populate(db_session, declared())
    assert summary(db_session, workout_id).outcome == "limited"
    assert not inspect(db_session.connection()).has_table("coach_workout_plans")


@pytest.mark.parametrize("goal", ["exact", "range", "open"])
@pytest.mark.parametrize("per_side", [False, True])
def test_snapshot_positive_targets_repeated_slug_occurrences_and_sides(db_session, plan_table, goal, per_side):
    workout_id = populate(db_session, declared(count=2, goal=goal, per_side=per_side))
    plan = db_session.get(CoachWorkoutPlan, workout_id)
    assert plan.revision == 1 and not plan.stale and plan.baseline["origin"] == "declared-client-plan"
    package = summary(db_session, workout_id)
    assert package.outcome == "full" and package.trigger_id == "T58"
    fact = next(f for f in package.facts if f.id == "outcome")
    assert "workout-plan-complete" in fact.permits and fact.provenance == "persisted-declared-client-plan"
    req = AuthorRequest("T58", "summary", "summary/workout", ("summary",), "result", 30,
                        package.facts, outcome=package.outcome, summary=True)
    assert validate({"action": "speak", "intent": "summary", "topicKey": "result", "text": "Весь план выполнен.",
                     "usedFactIds": ["outcome"], "silenceReason": None,
                     "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}, req).ok


@pytest.mark.parametrize("kind", ["bodyweight", "timed", "stretch"])
@pytest.mark.parametrize("goal", ["exact", "range", "open"])
def test_nonmachine_snapshot_targets(db_session, plan_table, kind, goal):
    plan = declared(goal=goal)
    exercise = plan["exercises"][0]
    exercise.update(kind=kind, trainingMode="bodyweight" if kind == "bodyweight" else "unloaded")
    exercise["sets"][0].update(unit="reps" if kind == "bodyweight" else "seconds", plannedWeightKg=0)
    assert summary(db_session, populate(db_session, plan)).outcome == "full"


@pytest.mark.parametrize("field", ["weight", "mode", "set-type", "goal"])
def test_unknown_plan_settings_stay_limited(db_session, plan_table, field):
    plan = declared()
    exercise = plan["exercises"][0]
    if field == "mode":
        exercise["trainingMode"] = None
    else:
        target = exercise["sets"][0]
        target[{"weight": "plannedWeightKg", "set-type": "setType", "goal": "targetType"}[field]] = (
            "unknown" if field == "goal" else None)
        if field == "goal":
            target.update(minimum=None, maximum=None)
    assert summary(db_session, populate(db_session, plan)).outcome != "full"


@pytest.mark.parametrize("mutation", ["missing-exercise", "extra-exercise", "wrong-slug", "wrong-order", "wrong-kind",
                                     "missing-set", "extra-set", "duplicate-set", "short", "forged-row-target",
                                     "skipped", "unfinished", "weight", "side", "unknown-goal", "corrupt", "owner"])
def test_snapshot_never_blesses_mismatched_results(db_session, plan_table, mutation):
    workout_id = populate(db_session, declared(count=2))
    workout = db_session.get(WorkoutSession, workout_id)
    ex = sorted(workout.exercise_sessions, key=lambda e: e.order_index)[0]
    row = ex.set_results[0]
    if mutation == "missing-exercise":
        db_session.delete(ex)
    elif mutation == "extra-exercise":
        clone = {c.key: getattr(ex, c.key) for c in ex.__table__.columns if c.key not in {"id", "created_at", "updated_at"}}
        db_session.add(ExerciseSession(**{**clone, "order_index": 3}))
    elif mutation == "wrong-slug":
        ex.exercise_slug = "different"
    elif mutation == "wrong-order":
        ex.order_index = 2
    elif mutation == "wrong-kind":
        ex.kind = "bodyweight"
    elif mutation == "missing-set":
        db_session.delete(row)
    elif mutation in {"extra-set", "duplicate-set"}:
        clone = {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key not in {"id", "created_at", "updated_at"}}
        db_session.add(SetResult(**{**clone, "set_number": 1 if mutation == "duplicate-set" else 2}))
    elif mutation in {"short", "forged-row-target"}:
        row.actual_value = 5
        if mutation == "forged-row-target":
            row.planned_value = 5
    elif mutation == "skipped":
        ex.status = "skipped"
    elif mutation == "unfinished":
        workout.status = "in_progress"
    elif mutation == "weight":
        row.weight_kg = 21
    elif mutation == "side":
        row.machine_metrics = {**row.machine_metrics, "side": "left"}
    else:
        record = db_session.get(CoachWorkoutPlan, workout_id)
        if mutation == "owner":
            record.user_id = "foreign"
        elif mutation == "corrupt":
            record.baseline = {"unexpected": True}
        else:
            data = copy.deepcopy(record.baseline)
            data["exercises"][0]["sets"][0].update(target_type="unknown", minimum=None, maximum=None)
            record.baseline = data
            record.current = data
    db_session.commit()
    if mutation == "duplicate-set":
        with pytest.raises(history.HistoryError, match="ambiguous_results"):
            summary(db_session, workout_id)
    else:
        assert summary(db_session, workout_id).outcome != "full"


def test_edits_omission_and_undo_are_permanent_invalidation(db_session, plan_table):
    plan = declared(count=2)
    workout_id = populate(db_session, plan)
    baseline = copy.deepcopy(db_session.get(CoachWorkoutPlan, workout_id).baseline)
    edited = declared(count=1)  # dropping an unperformed occurrence must never re-certify
    for revision, changed in enumerate([edited, None, plan], start=2):
        RuntimeService().save_workout_session(db_session, payload(changed, workout_session_id=workout_id, status="completed"))
        db_session.expire_all()
        record = db_session.get(CoachWorkoutPlan, workout_id)
        assert record.revision == revision and record.stale and record.baseline == baseline
        assert summary(db_session, workout_id).outcome != "full"


def test_legacy_and_final_creation_cannot_retroactively_capture(db_session, plan_table):
    workout_id = populate(db_session, declared(), create=False)
    assert db_session.get(CoachWorkoutPlan, workout_id) is None and summary(db_session, workout_id).outcome != "full"
    final = RuntimeService().save_workout_session(db_session, payload(declared(), status="completed"))
    assert db_session.get(CoachWorkoutPlan, final.workout_session_id) is None


@pytest.mark.parametrize("identity", ["unknown", " ", "undefined"])
def test_unknown_identity_never_full(db_session, plan_table, identity):
    plan = declared()
    plan["exercises"][0]["exerciseId"] = identity
    assert summary(db_session, populate(db_session, plan)).outcome != "full"


def test_preexisting_results_cannot_be_linked_and_certified(db_session, plan_table):
    plan = declared()
    workout_id = populate(db_session, plan)
    ex = db_session.query(ExerciseSession).filter_by(workout_session_id=workout_id).one()
    ex.set_results[0].created_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    assert summary(db_session, workout_id).outcome != "full"


def test_capture_with_nested_or_linked_exercises_is_not_pre_result(db_session, plan_table):
    plan = declared()
    existing_id = populate(db_session, plan)
    ex = db_session.query(ExerciseSession).filter_by(workout_session_id=existing_id).one()
    linked = RuntimeService().save_workout_session(db_session, payload(plan, exercise_session_ids=[ex.id]))
    assert db_session.get(CoachWorkoutPlan, linked.workout_session_id) is None
    nested = RuntimeService().save_workout_session(db_session, payload(plan, exercises=[ExerciseSessionCreateSchema(
        user_id="alexey", exercise_slug="machine-pulldown", exercise_name="Тяга", kind="machine",
        started_at=datetime.now(UTC), status="in_progress")]))
    assert db_session.get(CoachWorkoutPlan, nested.workout_session_id) is None


def test_total_set_budget(db_session):
    plan = declared(count=21)
    for exercise in plan["exercises"]:
        prototype = exercise["sets"][0]
        exercise["sets"] = [{**prototype, "ordinal": i} for i in range(1, 101)]
    with pytest.raises(ValidationError, match="budget"):
        CoachWorkoutPlanSchema.model_validate(plan)


@pytest.mark.parametrize("bad", ["extra", "ordinal", "identity", "nan", "too-many", "bounds", "side"])
def test_strict_snapshot_bounds(bad):
    plan = declared()
    target = plan["exercises"][0]["sets"][0]
    if bad == "extra":
        plan["telemetryVerified"] = True
    elif bad == "ordinal":
        target["ordinal"] = 2
    elif bad == "identity":
        plan["exercises"] *= 2
    elif bad == "nan":
        target["plannedWeightKg"] = float("nan")
    elif bad == "too-many":
        plan["exercises"][0]["sets"] *= 101
    elif bad == "bounds":
        target["minimum"] = 9
    else:
        plan["exercises"][0]["perSide"] = True
    with pytest.raises(ValidationError):
        CoachWorkoutPlanSchema.model_validate(plan)


@pytest.mark.parametrize("stage", ["after-author", "before-pcm"])
@pytest.mark.parametrize("mutation", ["changed", "missing"])
async def test_snapshot_revalidated_at_both_speech_handoffs(session_factory, plan_table, stage, mutation):
    with session_factory() as db:
        workout_id = populate(db, declared())

    def mutate():
        with session_factory() as db:
            record = db.get(CoachWorkoutPlan, workout_id)
            if mutation == "missing":
                db.delete(record)
            else:
                record.stale, record.revision = True, 2
            db.commit()

    coach, sink, run_id = make_coach(session_factory)
    if stage == "after-author":
        coach.author = AfterAuthor(coach.author, mutate)
    else:
        coach.voice = voice(session_factory, BeforePCM(mutate))
    await coach.handle(event("workout_finalized", run_id, phase="workout-summary", refs={"backendWorkoutId": workout_id}))
    await settle(coach)
    assert not sink.bytes and not coach.acks and not coach.memory.started
    assert any(m["reason"] == "facts_changed" for m in sink.of("decision")), sink.json


def test_runtime_api_captures_only_owner_and_validates_plan(client, session_factory, plan_table):
    body = payload(declared()).model_dump(mode="json", by_alias=True)
    response = client.post("/api/runtime/workouts", json=body)
    assert response.status_code == 200, response.text
    workout_id = response.json()["workoutSessionId"]
    with session_factory() as db:
        assert db.get(CoachWorkoutPlan, workout_id).revision == 1
    body.update(workoutSessionId=workout_id, userId="foreign")
    assert client.post("/api/runtime/workouts", json=body).status_code == 404
    body.update(userId="alexey", coachPlan={"schemaVersion": 2})
    assert client.post("/api/runtime/workouts", json=body).status_code == 422


def test_openapi_snapshot_contract_matches_static_artifact(client):
    generated = client.get("/api/openapi.json").json()["components"]["schemas"]
    artifact = Path(__file__).resolve().parents[2] / "openapi/openapi.json"
    exported = json.loads(artifact.read_text())["components"]["schemas"]
    for name in ("CoachPlanSetSchema", "CoachPlanExerciseSchema", "CoachWorkoutPlanSchema", "WorkoutSessionCreateSchema"):
        assert generated[name] == exported[name]