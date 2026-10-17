"""U00.5 synthetic baseline, NOT acceptance of U01–U10 or browser/acoustic behavior.

Every case consumes fixture inputs and checks executable current expectations twice.
Known gaps are explicitly named baseline_limitation in pytest IDs and properties.
Unavailable browser/delete workflows are skipped AFTER checking the fake's missing
capability, rather than counted as passing implemented behavior. No DB fixture,
app startup, paid adapter, real clock measurement or production recording is used.
Run via backend/scripts/check_coach_e02.py for isolation before conftest collection.
"""

import asyncio
import json
import socket
from pathlib import Path

import pytest

from app.schemas.coach import CoachEvent, CoachFact, CoachScope, CoachSettings
from app.services.coach.facts import AllowedFact, SetResult, compare, saved_set_facts, target_fact
from app.services.coach.fakes import FakeAudioManager, FakeClock, FakePackStorage, FakeTextProvider, FakeVoiceAdapter
from app.services.coach.memory import CoachMemory, Utterance
from app.services.coach.prompts import AuthorRequest
from app.services.coach.replay import ReplayContext, ReplayCoordinator
from app.services.coach.validation import validate

FIXTURE = Path(__file__).parent / "fixtures" / "coach_u00_replay.json"
CORPUS = json.loads(FIXTURE.read_text(encoding="utf-8"))
SCENARIOS = CORPUS["scenarios"]
PROVIDER_TIMEOUT_SECONDS = 0.02
SCENARIO_TIMEOUT_SECONDS = 2

# Independent manifest: deleting a matrix row/variant must fail corpus integrity.
REQUIRED = {
    "start": {"new", "first-exercise", "next-exercise", "restore"},
    "set": {"short", "long", "exact", "range", "open-target", "invented-remainder"},
    "work": {"machine", "timed", "bodyweight", "stretch", "mode-eccentric"},
    "completion": {"full", "partial", "skipped", "unsaved", "fallback"},
    "history": {"empty", "unknown", "comparable", "weight", "mode", "calibration", "null-conditions", "other-user"},
    "wellbeing": {"unspecified", "easy", "hard", "discomfort", "no-inference"},
    "lifecycle": {"plan", "exercise", "user", "cancel", "safety", "fact-change"},
    "network": {"cold", "warm", "delay", "disconnect", "reorder", "reconnect", "timeout"},
    "audio": {"locked", "mute", "hidden", "no-pack", "underrun", "overlap"},
    "memory": {"long", "interrupt", "reload", "forget", "user-isolation", "semantic-repeat"},
    "budget": {"exhausted", "cancel-dispatched", "unused-pregen", "cancel-unsent"},
    "validator": {"safe", "unsafe", "number", "comparison", "partial", "relations", "negation", "safe-metaphor"},
}
DRIVERS = {"replay", "saved", "compare", "target", "validation", "fact", "pack", "memory", "accounting", "unavailable"}


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch):
    """Defense in depth for this module; the runner also guards collection time."""
    def forbidden(*args, **kwargs):
        raise AssertionError("U00 synthetic replay forbids network and physical serial opens")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    try:
        import serial
    except ModuleNotFoundError as exc:
        if exc.name != "serial":
            raise
    else:
        monkeypatch.setattr(serial.Serial, "open", forbidden)
        monkeypatch.setattr(serial, "serial_for_url", forbidden)


def test_corpus_integrity_and_synthetic_identity():
    assert CORPUS["schema_version"] == 1 and CORPUS["mode"] == "synthetic-test-only"
    assert "Hand-authored fictitious" in CORPUS["provenance"]
    assert len(REQUIRED) == 12
    ids = [case["id"] for case in SCENARIOS]
    assert len(ids) == len(set(ids))
    assert set(ids) == {f"{group}-{variant}" for group, variants in REQUIRED.items() for variant in variants}
    for case in SCENARIOS:
        assert case["group"] in REQUIRED and case["id"].startswith(case["group"] + "-")
        assert case["driver"] in DRIVERS
        assert isinstance(case["input"], dict) and case["expect"]
        assert case.get("status", "baseline") in {"baseline", "baseline_limitation"}
        if case.get("status") == "baseline_limitation":
            assert len(case["limitation"]) >= 30
        if case["driver"] == "unavailable":
            assert case["status"] == "baseline_limitation"
            assert case["expect"]["capability_present"] is False
            assert case["expect"]["future_result"]

    # A provenance assertion is not a universal PII detector. All identity-bearing
    # fields are deliberately constrained to our fictitious namespace as well.
    def identities(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"user_id", "run_id", "exercise_id", "exercise_slug", "set_id", "range_id", "calibration_id"}:
                    assert item is None or item.startswith("synthetic-"), (key, item)
                identities(item)
        elif isinstance(value, list):
            for item in value:
                identities(item)

    identities(CORPUS)
    wire = FIXTURE.read_text(encoding="utf-8").lower()
    assert not any(marker in wire for marker in ("@", "sk-", "api_key", "/home/", "authorization", "https://"))


class FaultText(FakeTextProvider):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    async def generate(self, event):
        self.calls += 1
        if self.mode == "stalled":
            await asyncio.Event().wait()  # bounded by ReplayCoordinator.wait_for
        raise RuntimeError("synthetic provider disconnect")


class ReorderedVoice(FakeVoiceAdapter):
    async def stream(self, text, scope, generation_id):
        async for chunk in super().stream(text, scope, generation_id):
            yield type(chunk)(chunk.metadata.model_copy(update={"sequence": 1}), chunk.data)


async def replay_case(data):
    scope = CoachScope.model_validate(CORPUS["scope"])
    wire = {**CORPUS["event"], **data.get("event", {}), "scope": scope.model_dump()}
    if data.get("dependency"):
        fact = CoachFact(id="synthetic-reps", value=10, unit="reps", source="synthetic", confidence="confirmed",
                         observed_at_ms=1000, valid_until_ms=5000, scope_epoch=1)
        wire.update(facts=[fact.model_dump()], fact_dependencies=[fact.id])
    event = CoachEvent.model_validate(wire)
    clock = FakeClock(1000)
    text = FaultText(data["provider"]) if "provider" in data else FakeTextProvider()
    voice = ReorderedVoice() if data.get("voice") == "reordered" else FakeVoiceAdapter()
    context = ReplayContext(scope, CoachSettings(enabled=True, consent_version=1), {f.id: f for f in event.facts})
    coordinator = ReplayCoordinator(clock, text, voice, context, timeout_seconds=PROVIDER_TIMEOUT_SECONDS)
    assert text.test_only and voice.test_only

    def mutate(changes):
        assert set(changes) <= {"scope", "cancel", "advance_ms", "fact_value", "plan_revision", "context_version",
                                "safety_blocked", "muted"}
        for key, value in changes.items():
            if key == "scope":
                context.scope = CoachScope.model_validate({**context.scope.model_dump(), **value})
            elif key == "cancel":
                assert value is True
                coordinator.cancel()
            elif key == "advance_ms":
                clock.advance(value)
            elif key == "fact_value":
                fact = context.facts["synthetic-reps"]
                context.facts[fact.id] = CoachFact.model_validate({**fact.model_dump(), "value": value})
            else:
                setattr(context, key, value)

    mutate(data.get("context", {}))
    text.after_generate = lambda: mutate(data.get("after_text", {}))
    voice.before_chunk = lambda: mutate(data.get("after_voice", {}))
    result = await coordinator.process(event)
    assert not coordinator.busy and not coordinator.pending
    if result.reason is None:
        assert result.decision is not None and result.decision.action == "speak"
        assert result.decision.text == text.decision.text
    else:
        assert result.decision is None and not result.chunks
    for index, chunk in enumerate(result.chunks):
        assert chunk.metadata.source == "fake" and chunk.metadata.scope == event.scope
        assert chunk.metadata.sequence == index and chunk.metadata.final
        assert chunk.data == bytes(320)  # silence, not generated speech or a voice-quality claim
    actual = {"reason": result.reason, "chunks": len(result.chunks)}
    if data.get("repeat"):
        redelivery = CoachEvent.model_validate({**event.model_dump(), "id": "synthetic-redelivery"})
        actual["repeat_reason"] = (await coordinator.process(redelivery)).reason
    if data.get("next_exercise"):
        next_scope = CoachScope.model_validate({**scope.model_dump(), "exercise_id": "synthetic-exercise-b"})
        context.scope = next_scope
        next_event = CoachEvent.model_validate({**event.model_dump(), "id": "synthetic-next", "scope": next_scope.model_dump()})
        actual["next_reason"] = (await coordinator.process(next_event)).reason
    if data.get("restart"):
        restarted = ReplayCoordinator(clock, text, voice, context, timeout_seconds=PROVIDER_TIMEOUT_SECONDS)
        actual["restart_reason"] = (await restarted.process(event)).reason
    actual.update(text_calls=text.calls, voice_calls=voice.calls)
    return actual


def set_result(changes=None):
    return SetResult(**{**CORPUS["set_result"], **(changes or {})})


def memory_case(data):
    memory = CoachMemory()
    operation = data["operation"]
    text = data.get("text", "Работа пошла, ровно и спокойно.")
    utterance = Utterance("synthetic-utterance", "T21", "synthetic-topic", text, 1000, 100,
                          exercise_id="synthetic-exercise-a", motif="synthetic-motif")
    if operation == "long":
        for i in range(data["count"]):
            memory.note_started(Utterance(f"synthetic-{i}", "T21", f"synthetic-topic-{i}",
                                          f"Работа продолжается {i}.", 1000 + i, 100))
        return {"started": len(memory.started), "topics": len(memory.topics), "fingerprints": len(memory.fingerprints)}
    memory.note_started(utterance)
    if operation == "interrupt":
        # A started-but-uncompleted utterance is not a completed callback source.
        assert utterance.utterance_id in memory.started
        return {"callback": memory.callback_allowed("synthetic-motif"), "completed": len(memory.completed)}
    if operation in {"reload", "isolation"}:
        other = CoachMemory()
        assert memory.repeated(text)
        return {"repeated": other.repeated(text), "started": len(other.started)}
    assert operation == "semantic"
    return {"repeated": memory.repeated(data["candidate"]), "opening_blocked": memory.opening_blocked(data["candidate"])}


def local_pack(present):
    packs = FakePackStorage()
    if present:
        packs.clips[("synthetic-v1", "synthetic-completion")] = bytes(320)
    clip = packs.get_verified("synthetic-v1", "synthetic-completion")
    assert clip is None or clip == bytes(320)
    return clip is not None


async def run_case(case):
    data, driver = case["input"], case["driver"]
    if driver == "replay":
        return await replay_case(data)
    if driver == "target":
        fact = target_fact(**data)
        return {"absent": True} if fact is None else {"value": fact.value, "unit": fact.unit, "numbers": list(fact.numbers)}
    if driver == "compare":
        current = set_result(data.get("current"))
        previous = set_result({"set_id": "synthetic-set-previous", "value": 9, "target": 9, **data.get("previous", {})})
        comparison = compare(current, previous, data.get("history", "available"))
        return {"status": comparison.status, "delta": comparison.delta, "differences": list(comparison.differences)}
    if driver == "saved":
        current = set_result(data.get("current"))
        comparison = compare(current, None, "unavailable")
        if not current.confirmed:
            with pytest.raises(ValueError) as error:
                saved_set_facts(current, comparison, scope_epoch=1, valid_until_ms=5000)
            return {"error": str(error.value)}
        package = saved_set_facts(current, comparison, scope_epoch=1, valid_until_ms=5000)
        facts = {fact.id: fact for fact in package.facts}
        if "saved-set" in facts:
            assert facts["saved-set"].value == current.value
        return {"trigger": package.trigger_id, "outcome": package.outcome,
                "saved_unit": facts["saved-set"].unit if "saved-set" in facts else None,
                "weight": "weight" in facts, "comparison": "comparison" in facts}
    if driver == "fact":
        fact = CoachFact(id="synthetic-effort", unit="text", source="synthetic", observed_at_ms=1000,
                         valid_until_ms=5000, scope_epoch=1, **data)
        return {"value": fact.value, "confidence": fact.confidence}
    if driver == "validation":
        facts = tuple(AllowedFact(**{**item, "numbers": tuple(item["numbers"])}) for item in CORPUS["validation_facts"])
        request = AuthorRequest("T21", "active", "active/support", ("motivation", "factual-feedback"),
                                "synthetic-topic", data.get("max_words", 30), facts,
                                outcome=data.get("outcome", "full"))
        output = {"action": "speak", "intent": "motivation", "topicKey": request.topic_key,
                  "text": data["text"], "usedFactIds": data.get("used", []), "silenceReason": None,
                  "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}
        verdict = validate(output, request, CoachMemory())
        assert verdict.speech == (data["text"] if verdict.ok else "")
        return {"ok": verdict.ok, "reason": verdict.reason}
    if driver == "memory":
        return memory_case(data)
    if driver == "pack":
        return {"found": local_pack(data["present"])}
    if driver == "accounting":
        # Use the real pure liability policy on a transient object: no Session,
        # create_run, credential lookup, dispatch, real DB or provider calls.
        from app.models.coach import CoachAttempt
        from app.services.coach.ledger import committed

        attempt = CoachAttempt(status=data["status"], reserve_micros=data["reserve"], cost_micros=data["cost"])
        liability = committed(attempt)
        return {"committed": liability, "available": max(0, data["cap"] - liability), "local_clip": local_pack(True)}
    assert driver == "unavailable"
    context = ReplayContext(CoachScope.model_validate(CORPUS["scope"]))
    component = {"audio": FakeAudioManager(), "context": context, "memory": CoachMemory()}[data["component"]]
    return {"capability_present": hasattr(component, data["missing"])}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", SCENARIOS, ids=[
    f"{case.get('status', 'baseline')}/{case['id']}" for case in SCENARIOS
])
async def test_synthetic_matrix_baseline(case, record_property):
    record_property("matrix_group", case["group"])
    record_property("coverage_status", case.get("status", "baseline"))
    if case.get("status") == "baseline_limitation":
        record_property("baseline_limitation", case["limitation"])
    if "baseline_expect" in case:
        record_property("original_baseline_expectation", json.dumps(case["baseline_expect"], sort_keys=True))
        record_property("u02_current_expectation", json.dumps(case["expect"], sort_keys=True))
    expected = {key: value for key, value in case["expect"].items() if key != "future_result"}
    first = await asyncio.wait_for(run_case(case), timeout=SCENARIO_TIMEOUT_SECONDS)
    second = await asyncio.wait_for(run_case(case), timeout=SCENARIO_TIMEOUT_SECONDS)
    assert first == second == expected, case["id"]
    if case["driver"] == "unavailable":
        pytest.skip(f"baseline limitation: {case['limitation']} Future expectation: {case['expect']['future_result']}")