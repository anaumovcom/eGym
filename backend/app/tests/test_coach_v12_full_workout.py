"""V12 acceptance: one whole synthetic workout through the live coach — every V-stage together, offline.

Story choice → opening → prepared lines → sets with machine telemetry → results with records and counters →
«why» on the first rest → exercise and workout summaries → episode. Fake text author, real Fish wire format
on a mocked transport (expressive markup, multi-speaker), a controllable clock.
"""

import asyncio
import json
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.models.coach import CoachAttempt, CoachEpisode
from app.schemas.coach_control import CoachPreferences
from app.schemas.runtime import ExerciseSessionCreateSchema, SetResultSaveSchema, WorkoutSessionCreateSchema
from app.services.coach import ledger, live
from app.services.coach.live import LiveCoach
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.voice import FishVoiceAdapter, VoiceStreamer, decode_frame
from app.services.runtime_service import RuntimeService
from app.tests.test_coach_e07_author import PRICE as TEXT_PRICE
from app.tests.test_coach_e08_voice import PRICE as VOICE_PRICE
from app.tests.test_coach_e10_live import HYBRID, Sink, new_run, settle
from app.tests.test_coach_v1_scenarios import cards_for

MAIN, SECOND = "0a690dbeb3984a9f88cd39353880775f", "6d23d3209d6849e0b24ddae6f734afe9"
PLAN = [{"id": "ex-1", "name": "Тяга сверху", "sets": 2}, {"id": "ex-2", "name": "Жим от груди", "sets": 2}]
SLUGS = {"ex-1": "machine-pulldown", "ex-2": "machine-chest-press"}


def bible(data):
    ids = [e["id"] for e in data["plan"]]
    return {"premise": "Мы в прямом эфире, чат следит за каждым повтором, донаты летят рекой.",
            "coachRole": "стример-ведущий", "userRole": "звезда эфира",
            "lexicon": [{"from": "подход", "to": "занос"}, {"from": "отдых", "to": "рекламная пауза"},
                        {"from": "упражнение", "to": "раунд"}],
            "motifs": ["чат требует продолжения", "модератор плачет от восторга", "рекорд онлайна близко"],
            "acts": [{"act": 1, "title": "Разогрев эфира", "goal": "Собрать чат", "exerciseIds": ids[:1]},
                     {"act": 2, "title": "Финальный занос", "goal": "Побить рекорд онлайна", "exerciseIds": ids[1:]}],
            "exerciseRoles": [{"exerciseId": i, "role": "раунд эфира"} for i in ids],
            "counters": [{"id": "c1", "label": "Донаты чата", "source": "reps"}],
            "finale": "Эфир закрывается под овации чата", "coHost": {"role": "голос чата", "name": "Модератор"},
            "forbidden": ["без политики"]}


class Author:
    """Answers every schema the coach asks for with a valid, fact-bound line (variants, judge, story, episode)."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.lines = 0

    def __call__(self, body):
        name = body["text"]["format"]["name"]
        data = json.loads(body["input"][0]["content"])
        self.calls.append((name, data))
        if name == "coach_scenarios":
            return cards_for(data)
        if name == "coach_scenario_bible":
            return bible(data)
        if name == "coach_judge":
            return {"best": len(data["candidates"]) - 1, "reason": "свежее"}
        if name == "coach_episode":
            return {"title": "Эфир века", "highlights": ["Донаты чата льются рекой"], "finale": "Эфир закрыт под овации."}
        schema = body["text"]["format"]["schema"]
        self.lines += 1
        if "candidates" in schema["properties"]:
            return {"candidates": [self.line(data, variant, self.lines) for variant in range(3)]}
        return self.line(data, 0, self.lines)

    @staticmethod
    def line(data, variant, serial):
        ids = {f["id"] for f in data["allowedFacts"]}
        locked = list(data["lockedFactIds"])
        preferred = next((i for i in ("record", "counter-c1", "velocity-drop", "tempo-ratio", "muscles", "set-steady")
                          if i in ids), None)
        used = locked or ([preferred] if preferred else [])
        text = {"record": "Личный рекорд! Чат в шоке.", "velocity-drop": "Держим занос, гриф идёт тяжелее.",
                "tempo-ratio": "Опускай медленнее, чат смотрит.", "muscles": "Работают бицепс и широчайшие — спина скажет спасибо.",
                "set-steady": "Ровно, как метроном, красиво."}.get(preferred or "", "Эфир живёт, работаем дальше.")
        if preferred == "counter-c1":
            fact = next(f for f in data["allowedFacts"] if f["id"] == "counter-c1")
            text = fact["claim"].replace("Донаты чата: ", "Донаты чата уже ") + "!"
        # A real author never repeats itself; give each line its own colour so anti-repeat checks stay quiet.
        flavour = ("Огонь", "Красота", "Мощь", "Сила", "Класс", "Пушка", "Бомба", "Шедевр", "Ракета", "Магия",
                   "Гроза", "Буря", "Лава", "Титан", "Комета", "Вулкан")[serial % 16]
        text = f"{flavour}! {text}"
        if variant:
            text = text.replace("!", ".", 1) if variant == 1 else text
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        out = {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": used,
               "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"},
               key: "" if locked and key == "framingText" and variant == 2 else text}
        if "coHost" in data:
            out["coHost"] = "Модератор в восторге."
        out["voice"] = {"direction": "", "sound": "none", "stress": "none", "segments": [
            {"emotion": "excited", "intensity": "none", "tone": "none", "direction": "", "soundBefore": "none",
             "pauseAfter": "none", "tags": []}]}
        return out


async def test_full_workout_end_to_end(session_factory, monkeypatch):
    monkeypatch.setattr(live, "PREBUILD_START_DELAY_S", 0)
    clock = [time.time() * 1000]
    author_script = Author()
    bodies = []

    def fish(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=bytes(9600), headers={"content-type": "audio/pcm"})

    run_id, generation, _ = new_run(session_factory)
    with session_factory() as db:
        ledger.get_run(db, run_id).cap_micros = 10_000_000
        db.commit()
    sink = Sink()
    prefs = CoachPreferences(**HYBRID, history_consent=True, density="show", co_host=True, scenario_picker=True)
    from app.services.coach.luna import TextAuthor
    from app.services.coach.routing import default_routes
    author = TextAuthor(session_factory, FakeTextAuthor(author_script), TEXT_PRICE, model=TEXT_PRICE.model, timeout_s=5,
                        routes=default_routes(TEXT_PRICE))
    async with httpx.AsyncClient(transport=httpx.MockTransport(fish)) as client:
        adapter = FishVoiceAdapter(client, "k", model="drama-3", reference_id=MAIN, co_host_reference_id=SECOND)
        adapter.test_only = True
        coach = LiveCoach(session_factory, run_id=run_id, owner="tab-a", generation=generation, user_id="alexey",
                          settings=prefs, author=author, voice=VoiceStreamer(session_factory, adapter,
                                                                             VOICE_PRICE.model_copy(update={"model": "drama-3"})),
                          send_json=sink.send_json, send_bytes=sink.send_bytes,
                          now_ms=lambda: clock[0], monotonic_ms=lambda: clock[0])

        async def send(kind, *, exercise=None, set_ordinal=None, phase="setup", refs=None, context=None, epoch=1):
            created = time.time() * 1000
            message = {"type": "event", "event": {
                "id": f"{kind}-{len(sink.json)}-{set_ordinal}-{exercise}", "kind": kind, "phase": phase,
                "source": "runtime_ack", "scope": {"userId": "alexey", "runId": run_id, "exerciseId": exercise,
                                                   "setOrdinal": set_ordinal, "scopeEpoch": epoch},
                "createdAtMs": created, "startDeadlineMs": created + 20_000, "exerciseKind": "machine"},
                "context": context or {}, **({"refs": refs} if refs else {})}
            await coach.handle(message)
            await settle(coach)
            for start in [m for m in sink.json if m["type"] == "speech_start" and m["generationId"] not in acked]:
                acked.add(start["generationId"])
                ack = {"generationId": start["generationId"], "durationMs": 2_000}
                await coach.handle({"type": "playback_started", **ack})
                await coach.handle({"type": "playback_completed", **ack})
            clock[0] += 12_000

        acked: set[str] = set()
        await coach.announce()
        await coach.handle({"type": "scenario_propose", "plan": PLAN})
        while not sink.of("scenarios"):
            await asyncio.sleep(0.01)
        await coach.handle({"type": "scenario_select", "index": 0})
        while not any(m.get("state") == "ready" for m in sink.of("scenario")):
            await asyncio.sleep(0.01)
        await send("workout_started", exercise="ex-1", context={"exerciseCount": 2, "exerciseName": "Тяга сверху"})
        for _ in range(500):
            if coach.prebuild_job is not None and coach.prebuild_job.done():
                break
            await asyncio.sleep(0.01)
        with session_factory() as db:
            journal_rows = [(a.task, a.stage, a.outcome, a.error_code) for a in db.query(CoachAttempt).filter_by(run_id=run_id).order_by(CoachAttempt.created_at)]
        # Story lines and (V12) plan-only in-set lines of both exercises (the lookahead covers the next one).
        assert {"T68:ex-2", "T69:ex-2", "T21:ex-1:1:start", "T21:ex-1:1:finish", "T19:ex-1:fast-descent",
                "T21:ex-2:1:start"} <= set(coach.prebuilt), (coach.prebuilt.keys(), journal_rows)

        service = RuntimeService()
        with session_factory() as db:
            history_start = datetime.now(UTC) - timedelta(days=7)
            old = service.save_workout_session(db, WorkoutSessionCreateSchema(
                user_id="alexey", source="catalog", title="Old", started_at=history_start, status="completed"))
            old_ex = service.save_exercise_session(db, ExerciseSessionCreateSchema(
                user_id="alexey", workout_session_id=old.workout_session_id, exercise_slug="machine-pulldown",
                exercise_name="Тяга сверху", kind="machine", status="completed", started_at=history_start, target_sets=1,
                training_mode="constant")).exercise_session.id
            service.save_set_result(db, SetResultSaveSchema(exercise_session_id=old_ex, set_number=1, planned_value=10,
                                                            actual_value=10, reps=10, weight_kg=20, tempo_label="unknown",
                                                            machine_metrics={"completionStatus": "completed", "loadMode": "constant"}))
            workout = service.save_workout_session(db, WorkoutSessionCreateSchema(
                user_id="alexey", source="catalog", title="Live", started_at=datetime.now(UTC), status="in_progress"))
            workout_id = workout.workout_session_id

        for index, exercise in enumerate(("ex-1", "ex-2"), 1):
            if index == 2:
                await send("exercise_ready", exercise=exercise, context={"exerciseName": "Жим от груди", "exerciseIndex": 2,
                                                                        "exerciseCount": 2, "totalSets": 2,
                                                                        "exerciseSlug": SLUGS[exercise]})
            with session_factory() as db:
                exercise_db = service.save_exercise_session(db, ExerciseSessionCreateSchema(
                    user_id="alexey", workout_session_id=workout_id, exercise_slug=SLUGS[exercise],
                    exercise_name=PLAN[index - 1]["name"], kind="machine", status="completed",
                    started_at=datetime.now(UTC), target_sets=2, training_mode="constant")).exercise_session.id
            for set_ordinal in (1, 2):
                context = {"exerciseName": PLAN[index - 1]["name"], "totalSets": 2, "exerciseSlug": SLUGS[exercise]}
                await send("set_activated", exercise=exercise, set_ordinal=set_ordinal, phase="active-set",
                           context={**context, "moment": "start", "phaseElapsedMs": 3_000, "targetReps": 10})
                await send("rep_milestone", exercise=exercise, set_ordinal=set_ordinal, phase="active-set",
                           context={**context, "moment": "velocity_drop", "phaseElapsedMs": 25_000,
                                    "telemetry": {"reps": 6, "velocityDropPct": 20}})
                with session_factory() as db:
                    set_id = service.save_set_result(db, SetResultSaveSchema(
                        exercise_session_id=exercise_db, set_number=set_ordinal, planned_value=10, actual_value=10,
                        reps=10, weight_kg=25, tempo_label="unknown",
                        machine_metrics={"completionStatus": "completed", "loadMode": "constant"})).set_id
                await send("set_persisted", exercise=exercise, set_ordinal=set_ordinal, phase="rest",
                           refs={"backendSetId": set_id},
                           context={"restMs": 90_000, "restElapsedMs": 1_000, "setMetrics": {
                               "reps": 10, "velocityDropPct": 12, "steady": True, "eccentricS": 1.5, "concentricS": 1.0}})
                if set_ordinal == 1:
                    await send("rest_long_opportunity", exercise=exercise, set_ordinal=1, phase="rest",
                               refs={"backendSetId": set_id},
                               context={**context, "restMs": 120_000, "restElapsedMs": 20_000})
            await send("exercise_finalized", exercise=exercise, phase="exercise-summary",
                       refs={"backendExerciseId": exercise_db})
        await send("workout_finalized", exercise=None, phase="workout-summary", refs={"backendWorkoutId": workout_id})
        for _ in range(500):
            if coach.episode_job is not None and coach.episode_job.done():
                break
            await asyncio.sleep(0.01)
        await coach.close()

    starts = sink.of("speech_start")
    triggers = [m["triggerId"] for m in starts]
    decisions = [(d["triggerId"], d["reason"]) for d in sink.of("decision")]
    report = {"triggers": triggers, "decisions": decisions}
    import os
    if os.environ.get("COACH_V12_REPORT"):
        Path(os.environ["COACH_V12_REPORT"]).write_text(json.dumps({**report, "texts": [m["text"] for m in starts],
                                                                    "rejected": sink.of("event_rejected")},
                                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    # Every stage left its mark in one workout.
    for expected in ("T01", "T21", "T43", "T70", "T68", "T69"):
        assert expected in triggers, (expected, report)
    assert any(t in triggers for t in ("T55", "T56")) and any(t in triggers for t in ("T58", "T59")), report
    assert [m for m in starts if m.get("prebuilt")], report
    assert [m for m in starts if m["triggerId"] == "T21" and m.get("prebuilt")], report  # set starts were prepared
    assert all(e["status"] == "complete" for e in sink.of("speech_end")), sink.of("speech_end")
    assert coach.stats.reasons.get("internal_error", 0) == 0, coach.stats.as_dict()
    assert sink.of("scenario_state")[-1]["counters"][0]["value"] > 0
    assert any("<|speaker:1|>" in b["text"] for b in bodies)  # the co-host spoke once
    assert all(b["text"].count("[") <= 12 for b in bodies)
    frames = [decode_frame(b) for b in sink.bytes]
    assert frames and all(f.metadata.scope.run_id == run_id for f in frames)
    with session_factory() as db:
        attempts = list(db.query(CoachAttempt).filter_by(run_id=run_id))
        purposes = Counter(a.purpose for a in attempts)
        assert {"scenario", "prebuild", "live", "summary", "judge", "episode"} <= set(purposes), purposes
        assert sum(ledger.committed(a) for a in attempts) <= 10_000_000
        assert not [a for a in attempts if a.status in {"reserved", "sent", "unsettled"}]
        assert db.get(CoachEpisode, workout_id).payload["source"] == "generated"
        assert {"record", "plan"} & {a["id"] for a in db.get(CoachEpisode, workout_id).payload["achievements"]}
