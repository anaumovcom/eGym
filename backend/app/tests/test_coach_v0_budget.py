"""V0: task routing, budget buckets (summary reserve, prebuild/scenario ceilings) and degradation tiers."""

import json

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.coach import CoachAttempt
from app.schemas.coach_control import CoachPreferences, Pricing, UsageBounds
from app.services.coach import ledger, routing
from app.services.coach.luna import FakeTextAuthor, TextAuthor
from app.services.coach.prompts import AuthorRequest
from app.tests.test_coach_e07_author import PRICE
from app.tests.test_coach_e10_live import HYBRID, echo, event, make_coach, seed, settle

BOUNDS = UsageBounds(input_tokens=5000, output_tokens=5000)  # PRICE: 500 + 2 500 = 3 000 micro-USD per attempt


def workout_run(session_factory, cap="0.01", kind="workout"):
    with session_factory() as db:
        row, _ = ledger.create_run(db, "alexey", kind, cap)
        run_id = row.id
        db.rollback()
        generation = ledger.lease(db, run_id, "tab-a", 0)["generation"]
    return run_id, generation


def spend(session_factory, run_id, generation, key, *, purpose="live", stage="text"):
    with session_factory() as db:
        return ledger.reserve(db, run_id, "tab-a", generation, key, stage, PRICE, BOUNDS, purpose=purpose)


def settle_attempt(session_factory, attempt_id):
    """Mark a reservation as sent and settled at its full bound (synthetic usage, no provider)."""
    with session_factory() as db:
        row = db.get(CoachAttempt, attempt_id)
        row.status, row.cost_micros, row.sent_at = "settled", row.reserve_micros, 1.0
        db.commit()


# ---------- routing ----------

@pytest.mark.parametrize(("task", "expected"), [
    ("active/support", "live"), ("active/general-tip", "live"), ("paused", "live"),
    ("rest/full-feedback", "narrative"), ("setup/opening", "narrative"), ("summary/workout", "narrative"),
    ("scenario/propose", "plan"), ("episode/workout", "plan"), ("judge/pick", "judge")])
def test_task_classes(task, expected):
    assert routing.task_class(task) == expected


def test_strong_route_needs_verified_pricing(monkeypatch):
    routes = routing.default_routes(PRICE)
    assert routes["plan"].reasoning_effort == "medium" and routes["narrative"].reasoning_effort == "low"
    assert routes["plan"].max_output_tokens > routes["narrative"].max_output_tokens > routes["judge"].max_output_tokens
    monkeypatch.setenv("COACH_TEXT_MODEL_STRONG", "gpt-strong-test")
    monkeypatch.setenv("COACH_TEXT_STRONG_PRICING_VERIFIED", "false")
    get_settings.cache_clear()
    try:
        fallback = routing.default_routes(PRICE)
        assert fallback["narrative"].model == PRICE.model and fallback["narrative"].pricing == PRICE
    finally:
        get_settings.cache_clear()


def test_degrade_only_lowers_reasoning():
    route = routing.default_routes(PRICE)["narrative"]
    assert routing.degrade(route, 1) == route
    assert routing.degrade(route, 2).reasoning_effort == "low"
    assert routing.degrade(routing.default_routes(PRICE)["live"], 4).reasoning_effort == "low"


async def test_author_sends_route_model_reasoning_and_budget(session_factory):
    run_id, generation = workout_run(session_factory, "2.00", kind="test")  # synthetic dispatch needs a test ledger
    strong = Pricing(**{**PRICE.model_dump(), "model": "gpt-strong-test"})
    routes = {**routing.default_routes(PRICE)}
    routes["narrative"] = routing.Route("narrative", strong.model, strong, "medium", 4096, 5)
    seen = []

    def script(body):
        seen.append(body)
        data = json.loads(body["input"][0]["content"])
        return {"action": "silence", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": [],
                "silenceReason": "no_useful_content", "text": "",
                "delivery": {"energy": "calm", "pace": "normal", "emphasis": "none"}}

    author = TextAuthor(session_factory, FakeTextAuthor(script), PRICE, model=PRICE.model, timeout_s=2, routes=routes)
    rest = AuthorRequest("T46", "rest", "rest/playful", ("motivation",), "route-rest", 20)
    await author.author(run_id=run_id, owner="tab-a", generation=generation, opportunity="r1", request=rest)
    assert seen[-1]["model"] == "gpt-strong-test" and seen[-1]["reasoning"] == {"effort": "medium"}
    assert seen[-1]["max_output_tokens"] == 4096
    await author.author(run_id=run_id, owner="tab-a", generation=generation, opportunity="r2", request=rest, tier=2)
    assert seen[-1]["reasoning"] == {"effort": "low"}
    live = AuthorRequest("T21", "active", "active/support", ("motivation",), "route-live", 10)
    await author.author(run_id=run_id, owner="tab-a", generation=generation, opportunity="r3", request=live)
    assert seen[-1]["model"] == PRICE.model
    with session_factory() as db:
        models = {a.model for a in db.query(CoachAttempt).filter_by(run_id=run_id)}
    assert models == {"gpt-strong-test", PRICE.model}


# ---------- buckets ----------

def test_summary_reserve_is_kept_for_summaries(session_factory):
    run_id, generation = workout_run(session_factory, "0.01")  # 10 000 µUSD, reserve 1 000
    for index in range(3):
        settle_attempt(session_factory, spend(session_factory, run_id, generation, f"live-{index}"))
    # 9 000 used: another live attempt (3 000) would cross into the summary reserve and the cap.
    with pytest.raises(HTTPException, match="budget"):
        spend(session_factory, run_id, generation, "live-3")
    with session_factory() as db:
        state = ledger.run_budget(db, run_id)
    assert state["summaryReserveMicros"] == 1000 and state["byPurpose"] == {"live": 9000}
    assert state["tier"] == 4 and state["liveAvailableMicros"] == 0


def test_summary_may_use_reserve_and_test_ledgers_have_none(session_factory):
    run_id, generation = workout_run(session_factory, "0.0115")  # cap 11 500, reserve 1 150
    for index in range(3):
        settle_attempt(session_factory, spend(session_factory, run_id, generation, f"live-{index}"))
    with pytest.raises(HTTPException, match="budget"):
        spend(session_factory, run_id, generation, "live-3")
    # 9 000 + 3 000 > cap: even a summary cannot exceed the cap itself.
    with pytest.raises(HTTPException, match="budget"):
        spend(session_factory, run_id, generation, "summary-1", purpose="summary")
    run2, gen2 = workout_run(session_factory, "0.0125")
    for index in range(3):
        settle_attempt(session_factory, spend(session_factory, run2, gen2, f"live-{index}"))
    spend(session_factory, run2, gen2, "summary", purpose="summary")  # 12 000 ≤ 12 500, inside the reserve
    with session_factory() as db:
        test_row, _ = ledger.create_run(db, "alexey", "test", "0.01")
        assert ledger.summary_reserve(test_row) == 0


def test_prebuild_and_scenario_ceilings(session_factory):
    run_id, generation = workout_run(session_factory, "0.02")  # prebuild ≤ 5 000, scenario ≤ 1 000
    settle_attempt(session_factory, spend(session_factory, run_id, generation, "pre-1", purpose="prebuild"))
    with pytest.raises(HTTPException, match="budget_bucket"):
        spend(session_factory, run_id, generation, "pre-2", purpose="prebuild")
    with pytest.raises(HTTPException, match="budget_bucket"):
        spend(session_factory, run_id, generation, "scn-1", purpose="scenario")
    with pytest.raises(HTTPException, match="invalid_attempt"):
        spend(session_factory, run_id, generation, "bad", purpose="unknown")
    spend(session_factory, run_id, generation, "live-ok")


@pytest.mark.parametrize(("used", "tier"), [(0, 0), (5_000, 0), (6_000, 1), (7_500, 2), (8_500, 3), (8_990, 4)])
def test_tier_bounds(session_factory, used, tier):
    run_id, _ = workout_run(session_factory, "0.01")  # live cap 9 000
    with session_factory() as db:
        run = ledger.get_run(db, run_id)
        fake = CoachAttempt(id="x", run_id=run_id, opportunity="o", stage="text", model="m", status="settled",
                            reserve_micros=used, cost_micros=used, pricing={}, bounds={}, generation=0,
                            credential_version=0, created_at=0, purpose="live")
        assert ledger.budget_state(run, [fake] if used else [])["tier"] == tier


# ---------- live coach ----------

async def test_low_tier_keeps_results_and_drops_support(session_factory):
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID))
    coach._tier_cache = (coach.monotonic_ms(), 3)
    await coach.handle(event("exercise_ready", run_id, context={"exerciseName": "Тяга сверху"}))
    await settle(coach)
    assert sink.of("decision")[-1]["reason"] == "budget_tier" and not sink.of("speech_start")
    with session_factory() as db:
        _, _, set_id = seed(db, actual=10, planned=10, status="completed")
    coach._tier_cache = (coach.monotonic_ms(), 3)
    await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id},
                             context={"restMs": 90_000}))
    await settle(coach)
    assert sink.of("speech_start") and sink.of("speech_start")[0]["triggerId"] in {"T36", "T39", "T40"}
    await coach.handle({"type": "ping"})
    assert sink.of("pong")[-1]["stats"]["budgetTier"] == 3
    await coach.close()


async def test_summary_lines_spend_the_summary_bucket(session_factory):
    coach, _, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(echo()))
    with session_factory() as db:
        workout_id, _, _ = seed(db, actual=10, planned=10, status="completed")
    await coach.handle(event("workout_finalized", run_id, exercise=None, phase="workout-summary",
                             refs={"backendWorkoutId": workout_id}))
    await settle(coach)
    with session_factory() as db:
        purposes = {(a.stage, a.purpose) for a in db.query(CoachAttempt).filter_by(run_id=run_id)}
    assert ("text", "summary") in purposes
    await coach.close()
