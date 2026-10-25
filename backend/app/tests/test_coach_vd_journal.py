"""VD request journal: attempt annotations, refusals, sanitized provider errors and the panel API."""

import json

import httpx
import pytest

from app.models.coach import CoachAttempt
from app.schemas.coach_control import CoachPreferences
from app.services.coach import journal, ledger
from app.services.coach.luna import AuthorResult, FakeTextAuthor, LunaTextAdapter, TextAuthor
from app.services.coach.prompts import AuthorRequest
from app.services.coach.voice import Delivery, FakeVoiceStream, FishVoiceAdapter, VoiceOutcome, VoiceStreamer
from app.tests.test_coach_control_plane import ORIGIN
from app.tests.test_coach_e07_author import PRICE
from app.tests.test_coach_e08_voice import PRICE as VOICE_PRICE
from app.tests.test_coach_e08_voice import SCOPE, make_run
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, seed, settle

REQ = AuthorRequest("T46", "rest", "rest/playful", ("motivation",), "journal-topic", 20)


def silence(body):
    data = json.loads(body["input"][0]["content"])
    return {"action": "silence", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": [],
            "silenceReason": "no_useful_content", "text": "",
            "delivery": {"energy": "calm", "pace": "normal", "emphasis": "none"}}


def speak(text):
    def script(body):
        data = json.loads(body["input"][0]["content"])
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": [],
                "silenceReason": None, "text": text, "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}
    return script


def rows(session_factory, run_id):
    with session_factory() as db:
        return [{c.name: getattr(a, c.name) for c in CoachAttempt.__table__.columns}
                for a in db.query(CoachAttempt).filter_by(run_id=run_id).order_by(CoachAttempt.created_at)]


def author(session_factory, script):
    return TextAuthor(session_factory, FakeTextAuthor(script), PRICE, model=PRICE.model, timeout_s=1)


# ---------- sanitize ----------

@pytest.mark.parametrize("raw", ["Incorrect API key provided: sk-proj-abc123def456ghi", "Bearer abcdef.ghijk",
                                 "org-AbCdEf12345 over quota", "contact admin@example.com",
                                 "token AbCdEfGhIjKlMnOpQrStUvWxYz012345"])
def test_sanitize_redacts_credentials(raw):
    clean = journal.sanitize(raw)
    for secret in ("sk-proj-abc123def456ghi", "abcdef.ghijk", "org-AbCdEf12345", "admin@example.com",
                   "AbCdEfGhIjKlMnOpQrStUvWxYz012345"):
        assert secret not in clean
    assert "[скрыто]" in clean


def test_clean_fields_drops_unknown_and_unbounded():
    assert journal.clean_fields({"outcome": "speech", "set_ordinal": 3, "duration_ms": -1, "hack": "x",
                                 "outcome_x": 1}) == {"outcome": "speech", "set_ordinal": 3}
    assert journal.clean_fields({"outcome": "weird"}) == {}
    assert len(journal.clean_fields({"error_detail": "ошибка " * 200})["error_detail"]) == 300


# ---------- text attempts ----------

async def test_text_outcomes_are_journaled(session_factory):
    run_id, generation = make_run(session_factory)
    await author(session_factory, speak("Спокойно, пауза работает на тебя.")).author(
        run_id=run_id, owner="tab-a", generation=generation, opportunity="o1", request=REQ,
        meta={"exercise_label": "Тяга сверху", "set_ordinal": 2})
    await author(session_factory, silence).author(run_id=run_id, owner="tab-a", generation=generation,
                                                  opportunity="o2", request=REQ)
    await author(session_factory, speak("Ещё один повтор сверх плана.")).author(
        run_id=run_id, owner="tab-a", generation=generation, opportunity="o3", request=REQ)
    first, second, third = rows(session_factory, run_id)
    assert (first["outcome"], first["trigger_id"], first["task"], first["exercise_label"], first["set_ordinal"]) == (
        "speech", "T46", "rest/playful", "Тяга сверху", 2)
    assert first["duration_ms"] is not None and first["finished_at"] and first["text_preview"] is None
    assert (second["outcome"], second["error_code"]) == ("silence", "no_useful_content")
    assert third["outcome"] == "rejected" and third["error_code"].startswith("validation_failed:")
    assert journal.category(db_row(session_factory, third["id"])) == "error"


def db_row(session_factory, attempt_id):
    with session_factory() as db:
        row = db.get(CoachAttempt, attempt_id)
        db.expunge(row)
        return row


async def test_provider_http_error_keeps_status_and_sanitized_message(session_factory):
    def handler(request):
        return httpx.Response(429, json={"error": {"type": "rate_limit", "code": "rate_limit_exceeded",
                                                   "message": "Slow down. Key sk-live-abcdefghijk used too fast."}})

    run_id, generation = make_run(session_factory)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LunaTextAdapter(client, "secret", model=PRICE.model)
        result = await adapter.author({"x": 1})
        assert result.http_status == 429 and "rate_limit" in result.detail and "sk-live" not in result.detail
    scripted = FakeTextAuthor(lambda body: AuthorResult(None, None, "http-429", False, "provider_error",
                                                        http_status=429, detail=result.detail))
    outcome = await TextAuthor(session_factory, scripted, PRICE, model=PRICE.model, timeout_s=1).author(
        run_id=run_id, owner="tab-a", generation=generation, opportunity="o1", request=REQ)
    assert outcome.reason == "provider_error"
    row = rows(session_factory, run_id)[0]
    assert (row["outcome"], row["error_code"], row["http_status"]) == ("error", "provider_error", 429)
    assert "Slow down" in row["error_detail"] and "sk-live" not in row["error_detail"]


async def test_timeout_is_an_error_with_duration(session_factory):
    run_id, generation = make_run(session_factory)
    slow = FakeTextAuthor(silence, delay_s=2)
    await TextAuthor(session_factory, slow, PRICE, model=PRICE.model, timeout_s=0.05).author(
        run_id=run_id, owner="tab-a", generation=generation, opportunity="o1", request=REQ)
    row = rows(session_factory, run_id)[0]
    assert (row["outcome"], row["error_code"]) == ("error", "provider_timeout") and row["duration_ms"] >= 40


async def test_budget_refusal_is_recorded_at_zero_cost(session_factory):
    run_id, generation = make_run(session_factory)
    with session_factory() as db:
        ledger.get_run(db, run_id).cap_micros = 1
        db.commit()
    outcome = await author(session_factory, silence).author(run_id=run_id, owner="tab-a", generation=generation,
                                                            opportunity="o1", request=REQ)
    assert outcome.reason == "budget"
    [row] = rows(session_factory, run_id)
    assert (row["status"], row["outcome"], row["error_code"], row["reserve_micros"]) == ("refused", "refused", "budget", 0)
    with session_factory() as db:
        snap = ledger.snapshot(db, run_id)
        assert snap["requests"] == 0 and snap["pendingMicros"] == 0 and snap["settledMicros"] == 0
        assert ledger.daily_usage(db, 0)["requests"] == 0
        ledger.get_run(db, run_id).cap_micros = 2_000_000
        db.commit()
    # A refusal row never blocks the next real reservation of the same run.
    await author(session_factory, silence).author(run_id=run_id, owner="tab-a", generation=generation,
                                                  opportunity="o1", request=REQ)
    assert [r["status"] for r in rows(session_factory, run_id)] == ["refused", "settled"]


# ---------- voice attempts ----------

async def test_voice_journal_has_first_byte_and_fish_markup_share(session_factory):
    run_id, generation = make_run(session_factory)

    def handler(request):
        return httpx.Response(200, content=bytes(4800), headers={"content-type": "audio/pcm"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fish = FishVoiceAdapter(client, "k", model="drama-3")
        fish.test_only = True  # synthetic dispatch on a test ledger, real wire format
        price = VOICE_PRICE.model_copy(update={"model": "drama-3"})
        streamer = VoiceStreamer(session_factory, fish, price)
        outcome = VoiceOutcome()
        async for _ in streamer.stream(run_id=run_id, owner="tab-a", generation=generation, opportunity="v1",
                                       text="Отличный подход.", scope=SCOPE, generation_id="g1", outcome=outcome,
                                       delivery=Delivery(profile="result"), meta={"trigger_id": "T36"}):
            pass
    row = rows(session_factory, run_id)[0]
    assert (row["outcome"], row["trigger_id"]) == ("spoken", "T36")
    assert row["first_byte_ms"] is not None and row["text_bytes"] == len("Отличный подход.".encode())
    assert row["markup_bytes"] > 0


async def test_voice_http_error_detail(session_factory):
    run_id, generation = make_run(session_factory)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(402, json={"status": 402, "message": "Insufficient balance"}))) as client:
        fish = FishVoiceAdapter(client, "k", model="drama-3", emotion="off")
        fish.test_only = True
        streamer = VoiceStreamer(session_factory, fish, VOICE_PRICE.model_copy(update={"model": "drama-3"}))
        outcome = VoiceOutcome()
        async for _ in streamer.stream(run_id=run_id, owner="tab-a", generation=generation, opportunity="v1",
                                       text="Хорошо.", scope=SCOPE, generation_id="g1", outcome=outcome):
            pass
    row = rows(session_factory, run_id)[0]
    assert (row["outcome"], row["error_code"], row["http_status"]) == ("error", "http-402", 402)
    assert "Insufficient balance" in row["error_detail"]


async def test_voice_refusal_is_recorded(session_factory):
    run_id, generation = make_run(session_factory)
    with session_factory() as db:
        ledger.get_run(db, run_id).cap_micros = 1
        db.commit()
    outcome = VoiceOutcome()
    async for _ in VoiceStreamer(session_factory, FakeVoiceStream(), VOICE_PRICE).stream(
            run_id=run_id, owner="tab-a", generation=generation, opportunity="v1", text="Хорошо.", scope=SCOPE,
            generation_id="g1", outcome=outcome):
        pass
    assert outcome.status == "refused"
    assert [(r["stage"], r["status"], r["error_code"]) for r in rows(session_factory, run_id)] == [
        ("voice", "refused", "budget")]


# ---------- live coach + API ----------

async def test_live_preview_only_with_memory(session_factory):
    coach, _, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, memory_enabled=True))
    await coach.handle(event("workout_started", run_id))
    await settle(coach)
    text_rows = [r for r in rows(session_factory, run_id) if r["stage"] == "text"]
    assert text_rows and text_rows[0]["text_preview"] and text_rows[0]["trigger_id"] == "T01"
    await coach.close()
    coach2, _, run2 = make_coach(session_factory, CoachPreferences(**HYBRID, memory_enabled=False))
    await coach2.handle(event("workout_started", run2))
    await settle(coach2)
    assert all(r["text_preview"] is None for r in rows(session_factory, run2))
    await coach2.close()


def test_journal_api_sorts_filters_and_pages(client, session_factory):
    client.base_url = "http://localhost"
    run_id, generation = make_run(session_factory)
    with session_factory() as db:
        for index in range(5):
            attempt = ledger.reserve(db, run_id, "tab-a", generation, f"o{index}", "text", PRICE,
                                     ledger.UsageBounds(input_tokens=10, output_tokens=10),
                                     meta={"trigger_id": f"T0{index + 1}"})
            ledger.cancel_reserved(db, attempt)
            journal.annotate(db, attempt, outcome="error" if index == 3 else "speech",
                             error_code="provider_error" if index == 3 else None)
        journal.record_refusal(db, run_id, stage="voice", purpose="live", reason="budget", model="drama-3")
    response = client.get("/api/coach/requests", params={"userId": "alexey", "period": "7d", "limit": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totals"]["total"] == 6 and body["totals"]["refused"] == 1
    assert [r["createdAt"] for r in body["rows"]] == sorted([r["createdAt"] for r in body["rows"]], reverse=True)
    assert len(body["rows"]) == 2 and body["nextCursor"]
    rest = client.get("/api/coach/requests", params={"userId": "alexey", "period": "7d", "cursor": body["nextCursor"],
                                                     "limit": 10}).json()
    assert len(rest["rows"]) == 4 and not {r["id"] for r in rest["rows"]} & {r["id"] for r in body["rows"]}
    errors = client.get("/api/coach/requests", params={"userId": "alexey", "period": "run", "runId": run_id,
                                                       "status": "cancelled"}).json()
    assert errors["rows"] and all(r["status"] == "cancelled" for r in errors["rows"])
    card = client.get(f"/api/coach/requests/{body['rows'][0]['id']}", params={"userId": "alexey"})
    assert card.status_code == 200 and "errorDetail" in card.json()
    assert client.get(f"/api/coach/requests/{body['rows'][0]['id']}", params={"userId": "elena"}).status_code == 404
    summary = client.get("/api/coach/usage/summary", params={"userId": "alexey", "period": "run", "runId": run_id}).json()
    assert {"byKind", "byModel", "limits", "budget", "top"} <= set(summary)
    assert summary["limits"]["day"]["capMicros"] == 20_000_000 and summary["limits"]["workout"]["capMicros"] == 2_000_000
    assert client.get("/api/coach/requests", params={"userId": "alexey", "period": "year"}).status_code == 422
    assert client.get("/api/coach/requests", params={"userId": "alexey", "status": "weird"}).status_code == 422


def test_previews_are_erased_with_memory(client, session_factory):
    client.base_url = "http://localhost"
    run_id, generation = make_run(session_factory)
    with session_factory() as db:
        attempt = ledger.reserve(db, run_id, "tab-a", generation, "o", "text", PRICE,
                                 ledger.UsageBounds(input_tokens=10, output_tokens=10))
        journal.annotate(db, attempt, text_preview="Реплика тренера.")
    assert client.delete("/api/coach/users/alexey/memory", headers=ORIGIN).status_code == 200
    with session_factory() as db:
        assert db.get(CoachAttempt, attempt).text_preview is None
        journal.annotate(db, attempt, text_preview="Снова.")
    current = client.get("/api/coach/users/alexey/settings").json()
    saved = client.put("/api/coach/users/alexey/settings", headers=ORIGIN, json={
        "expectedRevision": current["revision"], "settings": {**current, "memoryEnabled": False,
                                                              "crossWorkoutMemory": False}})
    assert saved.status_code == 200, saved.text
    with session_factory() as db:
        assert db.get(CoachAttempt, attempt).text_preview is None
        journal.annotate(db, attempt, text_preview="Ещё раз.")
        journal.prune(db, now=10**10)
        assert db.get(CoachAttempt, attempt).text_preview is None


def test_seeded_rows_survive_the_journal_query(client, session_factory):
    client.base_url = "http://localhost"
    with session_factory() as db:
        seed(db)
    assert client.get("/api/coach/requests", params={"userId": "alexey"}).status_code == 200
