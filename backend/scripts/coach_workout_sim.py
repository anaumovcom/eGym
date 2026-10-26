"""V12 operator tool: one whole simulated workout through the production live coach (paid when not --fake).

Sandbox like coach_pilot.py (private state dir outside the repo, keys from OPENAI_API_KEY / FISH_API_KEY or
backend/.env.local, encrypted into the sandbox vault, never printed). Every request goes reserve → dispatch →
provider → settle. No hardware, no user DB. Output: WAV per line + report.json under backend/coach_packs/pilot/.

  .venv/Scripts/python backend/scripts/coach_workout_sim.py --fake                       # offline dry run
  .venv/Scripts/python backend/scripts/coach_workout_sim.py --confirm-paid --cap-usd 1.00 --scenario 0
  .venv/Scripts/python backend/scripts/coach_workout_sim.py --confirm-paid --cap-usd 1.00 --persona classic --density companion

The flow: propose 3 stories → choose → opening → prepared lines → per exercise: intro, sets with start /
fading-speed / tempo moments and the saved result (with telemetry summary), «why» on the first rest, the
exercise summary → workout summary → episode. Playback is acknowledged synthetically (no speakers).
"""

import argparse
import asyncio
import contextlib
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

PLAN = [{"id": "sim-1", "name": "Тяга верхнего блока", "sets": 2, "slug": "machine-pulldown", "kg": 30},
        {"id": "sim-2", "name": "Жим от груди в тренажёре", "sets": 2, "slug": "machine-chest-press", "kg": 25},
        {"id": "sim-3", "name": "Разгибание ног", "sets": 2, "slug": "machine-leg-extension", "kg": 35}]


def fake_author_script():
    """Offline dry run: a deterministic, varied author answering every schema the coach asks for."""
    serial = [0]
    words = ("Огонь", "Красота", "Мощь", "Сила", "Класс", "Пушка", "Бомба", "Шедевр", "Ракета", "Магия", "Гроза", "Буря")

    def line(data, variant, voice=False):
        serial[0] += 1
        locked = list(data["lockedFactIds"])
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        out = {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": locked,
               "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"},
               key: f"{words[serial[0] % len(words)]}! Работаем дальше, вариант {['первый', 'второй', 'третий'][variant]}."}
        if "coHost" in data:
            out["coHost"] = "Чат в восторге." if serial[0] % 5 == 0 else ""
        if voice:
            out["voice"] = {"direction": "", "sound": "none", "stress": "none", "segments": [
                {"emotion": "excited", "intensity": "none", "tone": "none", "direction": "", "soundBefore": "none",
                 "pauseAfter": "none", "tags": []}]}
        return out

    def script(body):
        name = body["text"]["format"]["name"]
        data = json.loads(body["input"][0]["content"])
        if name == "coach_scenarios":
            return {"cards": [{"archetype": a["id"], "title": f"Сюжет {n}", "tagline": "Тренировка как приключение",
                               "tone": "дерзко"} for a, n in zip(data["archetypes"], ("один", "два", "три"), strict=True)]}
        if name == "coach_scenario_bible":
            ids = [e["id"] for e in data["plan"]]
            return {"premise": "Тренировка превращается в большое приключение.", "coachRole": "ведущий",
                    "userRole": "герой", "lexicon": [{"from": "подход", "to": "раунд"}, {"from": "отдых", "to": "пауза"},
                                                     {"from": "упражнение", "to": "этап"}],
                    "motifs": ["чат ревёт", "свет софитов"], "acts": [{"act": 1, "title": "Старт", "goal": "Разогнаться",
                                                                         "exerciseIds": ids}],
                    "exerciseRoles": [], "counters": [], "finale": "Финал под овации", "coHost": {"role": "чат", "name": "Чат"},
                    "forbidden": []}
        if name == "coach_judge":
            return {"best": 0, "reason": "ok"}
        if name == "coach_episode":
            return {"title": "Эпизод", "highlights": ["Тренировка завершена"], "finale": "Занавес."}
        schema = body["text"]["format"]["schema"]
        if "candidates" in schema["properties"]:
            voice = "voice" in schema["properties"]["candidates"]["items"]["properties"]
            return {"candidates": [line(data, v, voice) for v in range(3)]}
        return line(data, 0, "voice" in schema["properties"])
    return script


async def run(args) -> int:
    from coach_pilot import OWNER, USER, bootstrap, new_run, out_dir, renew, snapshot

    from app.db.session import SessionLocal
    from app.schemas.coach_control import CoachPreferences
    from app.schemas.runtime import ExerciseSessionCreateSchema, SetResultSaveSchema, WorkoutSessionCreateSchema
    from app.services.coach import ledger, live
    from app.services.coach.luna import FakeTextAuthor, TextAuthor, text_pricing
    from app.services.coach.packs import pcm_to_wav
    from app.services.coach.routing import default_routes
    from app.services.coach.voice import FishVoiceAdapter, VoiceStreamer, decode_frame, voice_pricing
    from app.services.runtime_service import RuntimeService

    bootstrap("openai") if not args.fake else bootstrap_fake()
    if not args.fake:
        bootstrap("fish")
    run_id, generation = new_run("test", args.cap_usd)
    prefs = CoachPreferences(enabled=True, consent_version=1, network_consent_version=1, mode="hybrid",
                             history_consent=True, density=args.density, persona=args.persona, co_host=True,
                             scenario_picker=True, voice_model="fish-drama-3", memory_enabled=True,
                             budget_usd=args.cap_usd)
    if args.fake:
        import httpx

        pricing = text_pricing()
        author = TextAuthor(SessionLocal, FakeTextAuthor(fake_author_script()), pricing, model=pricing.model, timeout_s=5,
                            routes=default_routes(pricing))
        # The real Fish adapter (markup, multi-speaker, exact byte reservations) over a mocked transport.
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=bytes(24_000),
                                                                       headers={"content-type": "audio/pcm"}))
        client = httpx.AsyncClient(transport=transport)
        fish = FishVoiceAdapter(client, "fake", model="drama-3", reference_id=live.MELLSTROY,
                                co_host_reference_id=live.EKATERINA)
        fish.test_only = True
        pipeline = live.Pipeline(author, VoiceStreamer(SessionLocal, fish, voice_pricing("fish")), None, [client.aclose])
    else:
        pipeline = await live.default_pipeline(SessionLocal, prefs)
        if pipeline.author is None or pipeline.voice is None:
            print(f"Refusing: pipeline unavailable ({pipeline.reason})")
            return 2
    outputs: list[dict] = []
    inner = pipeline.author.adapter

    class Recorder:
        """Sandbox-only: keep the structured author answers (no headers/keys) to review rejected lines."""
        test_only, name = inner.test_only, inner.name

        async def author(self, body):
            started = time.monotonic()
            result = await inner.author(body)
            outputs.append({"schema": body["text"]["format"]["name"], "reasoning": body.get("reasoning"),
                            "ms": round((time.monotonic() - started) * 1000), "output": result.output,
                            "error": result.error, "usage": getattr(result.usage, "model_dump", lambda: None)()})
            return result

    pipeline.author.adapter = Recorder()
    markups: list[str] = []
    voice_adapter = pipeline.voice.adapter
    if hasattr(voice_adapter, "request"):
        original_request = voice_adapter.request

        def recording_request(text, delivery):
            body = original_request(text, delivery)
            if markups and markups[-1].startswith(body["text"]):
                return body  # The ledger sizes the request first; record each line once.
            markups.append(body["text"] + (f"  ‖ {json.dumps(body.get('prosody'))} t={body.get('temperature')}"
                                           f" {body.get('latency')}" if body.get("prosody") else ""))
            return body

        voice_adapter.request = recording_request
    offset = [0.0]
    messages: list[dict] = []
    pcm: dict[str, bytearray] = {}
    sent_at: dict[str, float] = {}

    async def send_json(payload: dict) -> None:
        messages.append({**payload, "_at": time.monotonic()})

    first_pcm: dict[str, float] = {}

    async def send_bytes(data: bytes) -> None:
        frame = decode_frame(data)
        if frame.data:
            first_pcm.setdefault(frame.metadata.generation_id, time.monotonic())
        pcm.setdefault(frame.metadata.generation_id, bytearray()).extend(frame.data)

    coach = live.LiveCoach(SessionLocal, run_id=run_id, owner=OWNER, generation=generation, user_id=USER, settings=prefs,
                           author=pipeline.author, voice=pipeline.voice, send_json=send_json, send_bytes=send_bytes,
                           now_ms=lambda: time.time() * 1000 + offset[0],
                           monotonic_ms=lambda: time.monotonic() * 1000 + offset[0])

    async def heartbeat():
        while True:
            await asyncio.sleep(5)
            coach.generation = renew(run_id, coach.generation)

    beat = asyncio.create_task(heartbeat())
    acked: set[str] = set()

    async def settle():
        for _ in range(3000):
            busy = (coach.task is not None and not coach.task.done()) or coach.queue or any(
                j is not None and not j.done() for j in (coach.scenario_job,))
            if not busy:
                return
            await asyncio.sleep(0.05)

    async def acknowledge():
        for start in [m for m in messages if m["type"] == "speech_start" and m["generationId"] not in acked]:
            acked.add(start["generationId"])
            audio_ms = round(len(pcm.get(start["generationId"], b"")) / 48)
            ack = {"generationId": start["generationId"], "durationMs": max(500, audio_ms)}
            await coach.handle({"type": "playback_started", **ack})
            await coach.handle({"type": "playback_completed", **ack})
            offset[0] += audio_ms  # virtual time: the line was heard

    async def send(kind, *, exercise=None, set_ordinal=None, phase="setup", refs=None, context=None, gap_ms=15_000):
        created = time.time() * 1000 + offset[0]
        event_id = f"{kind}-{len(messages)}"
        sent_at[event_id] = time.monotonic()
        await coach.handle({"type": "event", "event": {
            "id": event_id, "kind": kind, "phase": phase, "source": "runtime_ack",
            "scope": {"userId": USER, "runId": run_id, "exerciseId": exercise, "setOrdinal": set_ordinal, "scopeEpoch": 1},
            "createdAtMs": created, "startDeadlineMs": created + (20_000 if phase == "active-set" else 35_000),
            "exerciseKind": "machine"},
            "context": context or {}, **({"refs": refs} if refs else {})})
        await settle()
        await acknowledge()
        offset[0] += gap_ms

    try:
        await coach.announce()
        await coach.handle({"type": "scenario_propose", "plan": [{k: e[k] for k in ("id", "name", "sets")} for e in PLAN]})
        await settle()
        proposal = next((m for m in reversed(messages) if m["type"] == "scenarios"), {})
        for index, card in enumerate(proposal.get("cards", [])):
            print(f"  [{index}] {card['title']} — {card['tagline']} ({card['tone']})")
        if proposal.get("cards"):
            preferred = [i for i, c in enumerate(proposal["cards"]) if c["archetype"] == args.prefer]
            choice = preferred[0] if preferred else min(args.scenario, len(proposal["cards"]) - 1)
            print(f"  → choosing [{choice}]")
            await coach.handle({"type": "scenario_select", "index": choice})
            await settle()
        await send("workout_started", exercise=PLAN[0]["id"], context={"exerciseCount": len(PLAN),
                                                                        "exerciseName": PLAN[0]["name"]})
        if coach.prebuild_job is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(coach.prebuild_job, 300)
        service = RuntimeService()
        with SessionLocal() as db:
            if args.history:
                past = datetime.now(UTC) - timedelta(days=7)
                old = service.save_workout_session(db, WorkoutSessionCreateSchema(
                    user_id=USER, source="catalog", title="Прошлая", started_at=past, status="completed"))
                for item in PLAN:
                    old_ex = service.save_exercise_session(db, ExerciseSessionCreateSchema(
                        user_id=USER, workout_session_id=old.workout_session_id, exercise_slug=item["slug"],
                        exercise_name=item["name"], kind="machine", status="completed", started_at=past,
                        target_sets=1, training_mode="constant")).exercise_session.id
                    service.save_set_result(db, SetResultSaveSchema(
                        exercise_session_id=old_ex, set_number=1, planned_value=10, actual_value=10, reps=10,
                        weight_kg=item["kg"] - 5, tempo_label="unknown",
                        machine_metrics={"completionStatus": "completed", "loadMode": "constant"}))
            workout_id = service.save_workout_session(db, WorkoutSessionCreateSchema(
                user_id=USER, source="catalog", title="Симуляция", started_at=datetime.now(UTC),
                status="in_progress")).workout_session_id
        for position, item in enumerate(PLAN, 1):
            context = {"exerciseName": item["name"], "totalSets": item["sets"], "exerciseSlug": item["slug"],
                       "exerciseIndex": position, "exerciseCount": len(PLAN)}
            if position > 1:
                await send("exercise_ready", exercise=item["id"], context=context)
            with SessionLocal() as db:
                exercise_db = service.save_exercise_session(db, ExerciseSessionCreateSchema(
                    user_id=USER, workout_session_id=workout_id, exercise_slug=item["slug"], exercise_name=item["name"],
                    kind="machine", status="completed", started_at=datetime.now(UTC), target_sets=item["sets"],
                    training_mode="constant")).exercise_session.id
            for set_ordinal in range(1, item["sets"] + 1):
                await send("set_activated", exercise=item["id"], set_ordinal=set_ordinal, phase="active-set",
                           context={**context, "moment": "start", "phaseElapsedMs": 3_000, "targetReps": 10}, gap_ms=10_000)
                await send("rep_milestone", exercise=item["id"], set_ordinal=set_ordinal, phase="active-set",
                           context={**context, "moment": "tempo" if set_ordinal == 1 else "velocity_drop_hard",
                                    "phaseElapsedMs": 22_000, "telemetry": {"reps": 6, "velocityDropPct": 34,
                                                                            "eccentricS": 0.6, "concentricS": 1.2}},
                           gap_ms=10_000)
                with SessionLocal() as db:
                    set_id = service.save_set_result(db, SetResultSaveSchema(
                        exercise_session_id=exercise_db, set_number=set_ordinal, planned_value=10, actual_value=10,
                        reps=10, weight_kg=item["kg"], tempo_label="unknown",
                        machine_metrics={"completionStatus": "completed", "loadMode": "constant"})).set_id
                await send("set_persisted", exercise=item["id"], set_ordinal=set_ordinal, phase="rest",
                           refs={"backendSetId": set_id}, context={"restMs": 90_000, "restElapsedMs": 1_000, "setMetrics": {
                               "reps": 10, "velocityDropPct": 18, "steady": set_ordinal == 2, "eccentricS": 1.4,
                               "concentricS": 1.0}})
                if set_ordinal == 1:
                    await send("rest_long_opportunity", exercise=item["id"], set_ordinal=1, phase="rest",
                               refs={"backendSetId": set_id}, context={**context, "restMs": 120_000, "restElapsedMs": 20_000})
            await send("exercise_finalized", exercise=item["id"], phase="exercise-summary",
                       refs={"backendExerciseId": exercise_db})
        await send("workout_finalized", phase="workout-summary", refs={"backendWorkoutId": workout_id})
        if coach.episode_job is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(coach.episode_job, 120)
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        await coach.close()
        await pipeline.close()
        with SessionLocal() as db:
            ledger.cancel_run(db, run_id, close=True)
    path = out_dir("workout-sim" + ("-fake" if args.fake else ""))
    rows = []
    for index, start in enumerate(m for m in messages if m["type"] == "speech_start"):
        audio = bytes(pcm.get(start["generationId"], b""))
        if audio:
            (path / f"{index + 1:02d}-{start['triggerId']}.wav").write_bytes(pcm_to_wav(audio))
        sent = sent_at.get(start.get("eventId", ""))
        first = first_pcm.get(start["generationId"])
        rows.append({"trigger": start["triggerId"], "text": start["text"], "coHost": start.get("coHostText"),
                     "prebuilt": bool(start.get("prebuilt")), "audioMs": round(len(audio) / 48),
                     "eventToFirstAudioMs": round((first - sent) * 1000) if sent and first else None})
    decisions = [{"trigger": m.get("triggerId"), "reason": m.get("reason")} for m in messages if m["type"] == "decision"]
    snap = snapshot(run_id)
    report = {"runId": run_id, "fake": args.fake, "lines": rows, "decisions": decisions,
              "scenario": next((m for m in messages if m["type"] == "scenario" and m.get("state") == "ready"), None),
              "episode": next((m for m in messages if m["type"] == "episode"), None),
              "usage": {k: snap[k] for k in ("requests", "settledMicros", "pendingMicros", "capMicros", "budget")},
              "stats": coach.stats.as_dict(), "authorOutputs": outputs, "fishMarkup": markups}
    (path / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for row in rows:
        mark = "●" if row["prebuilt"] else " "
        delay = f"{row['eventToFirstAudioMs'] / 1000:4.1f}s" if row["eventToFirstAudioMs"] is not None else "  —  "
        print(f"{mark} {row['trigger']:4} {delay} {row['text']}" + (f"  ↳ {row['coHost']}" if row["coHost"] else ""))
    print(f"lines {len(rows)}, silenced {len(decisions)}, requests {snap['requests']}, "
          f"settled ${snap['settledMicros'] / 1e6:.4f}, pending ${snap['pendingMicros'] / 1e6:.4f} -> {path}")
    return 0


def bootstrap_fake() -> None:
    """--fake: sandbox tables and the pilot user only, no keys (synthetic dispatch on a test ledger)."""
    from coach_pilot import USER

    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.models.enums import AccessRole, UserAccent
    from app.models.user import User

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.get(User, USER) is None:
            db.add(User(id=USER, name="Pilot", role=AccessRole.service, readiness_percent=0, last_workout="",
                        today_focus="", week_progress="", accent=UserAccent.gold))
            db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--fake", action="store_true", help="offline dry run with synthetic providers")
    parser.add_argument("--cap-usd", default="1.00")
    parser.add_argument("--scenario", type=int, default=0)
    parser.add_argument("--persona", choices=("streamer", "classic"), default="streamer")
    parser.add_argument("--density", choices=("quiet", "companion", "talkative", "show"), default="show")
    parser.add_argument("--no-history", dest="history", action="store_false", help="skip the seeded past workout")
    parser.add_argument("--fresh", action="store_true", help="new empty sandbox (records against the seeded past only)")
    parser.add_argument("--prefer", default="", help="choose the card with this archetype if offered (e.g. stream)")
    args = parser.parse_args()
    if not args.fake and not args.confirm_paid:
        print("Refusing: a paid simulation requires --confirm-paid (or use --fake)")
        return 2
    from coach_pilot import prepare_sandbox

    extra = {"COACH_OPERATOR_DAILY_USD": "20.00", "COACH_OPERATOR_MONTHLY_USD": "100.00"}
    if args.fake:
        extra.update({"COACH_PILOT_STATE": str(Path.home() / ".local" / "state" / "egym-coach-sim-fake")})
    import os
    if args.fake:
        os.environ["COACH_PILOT_STATE"] = extra.pop("COACH_PILOT_STATE")
    elif args.fresh:
        os.environ["COACH_PILOT_STATE"] = str(Path.home() / ".local" / "state" / f"egym-coach-sim-{time.strftime('%Y%m%d-%H%M%S')}")
    prepare_sandbox(extra)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
