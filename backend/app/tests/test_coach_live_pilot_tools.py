"""Offline pilot CLI regression tests: no credentials, provider, or working database."""

import asyncio
import importlib.util
import json
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


def pilot_module():
    path = Path(__file__).resolve().parents[2] / "scripts/coach_delivery_pilot.py"
    spec = importlib.util.spec_from_file_location("delivery_pilot_tools_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("cap", ["0", "-1", "NaN", "Infinity", "-Infinity", "2.01", "bad", "sNaN"])
def test_authorization_invalid_cap_before_helpers(monkeypatch, cap):
    module = pilot_module()
    monkeypatch.setattr(module, "load_helpers", lambda: pytest.fail("No helper/settings/key access"))
    with pytest.raises(SystemExit) as exc:
        module.main(["generate", "--confirm-paid", "--cap-usd", cap])
    assert exc.value.code == 2


def test_confirmation_required_before_helpers(monkeypatch):
    module = pilot_module()
    monkeypatch.setattr(module, "load_helpers", lambda: pytest.fail("No helper/settings/key access"))
    for args in (["generate"], ["generate", "--cap-usd", "1.50"]):
        with pytest.raises(SystemExit) as exc:
            module.main(args)
        assert exc.value.code == 2


@pytest.mark.parametrize("cap", ["0.01", "1.50", "2"])
def test_valid_authorization_routes_only_generate(monkeypatch, cap):
    module = pilot_module()
    seen = []

    async def generate(args):
        seen.append((args.confirm_paid, args.cap_usd))
        return 0

    monkeypatch.setattr(module, "run_generate", generate)
    assert module.main(["generate", "--confirm-paid", "--cap-usd", cap]) == 0
    assert seen == [(True, cap)]


def test_local_profiles_excluded_even_if_local_only_flag_regresses(monkeypatch):
    module = pilot_module()
    plan = module.build_plan()
    for pair in plan["pairs"]:
        pair["localOnly"] = False
    monkeypatch.setattr(module, "build_plan", lambda: plan)
    pairs = module.generation_pairs()
    assert len(pairs) == 7
    assert all(p["b"]["profile"] not in {"count", "safety"} for p in pairs)


def test_warm_send_failure_never_reconnects_or_retries():
    from app.services.coach.voice import VoiceError

    module = pilot_module()
    calls = []

    async def send(message):
        calls.append(message)
        raise RuntimeError("ambiguous delivery")

    async def reopen():
        pytest.fail("No reconnect after an ambiguous send")

    adapter = SimpleNamespace(_socket=SimpleNamespace(send=send), _opened_at=1, _now_s=lambda: 2,
                              MAX_SESSION_S=100, _open=reopen)
    module.disable_send_retry(adapter)
    with pytest.raises(VoiceError, match="provider_disconnected"):
        asyncio.run(adapter._send("synthetic request"))
    assert calls == ["synthetic request"] and adapter.last_connection_class == "warm"


@pytest.fixture
def pilot_fakes(monkeypatch, tmp_path):
    from app.db import session
    from app.services.coach import ledger, voice

    module = pilot_module()
    events, takes, adapters, attempts = [], [], [], []
    behavior = {"status": "complete", "reason": "", "raise": False, "close_raise": False}
    monkeypatch.setenv("COACH_PILOT_STATE", str(tmp_path / "shared-campaign"))
    monkeypatch.setattr(session, "SessionLocal", lambda: nullcontext("fake-db"))

    def cancel(db, run_id, *, close):
        assert db == "fake-db" and close
        events.append("closed")

    monkeypatch.setattr(ledger, "cancel_run", cancel)

    class Streamer:
        def __init__(self, sessions, adapter, pricing, **kwargs):
            self.adapter = adapter
            assert sessions is session.SessionLocal
            assert kwargs == {"first_audio_timeout_s": 8, "total_timeout_s": 30}

        async def stream(self, **kwargs):
            outcome = kwargs["outcome"]
            takes.append(kwargs)
            assert kwargs["text"]
            assert self.adapter.situational_enabled == (kwargs["delivery"].profile != "legacy")
            events.extend(["reserve", "dispatch"])
            outcome.attempt_id = f"attempt-{len(takes)}"
            attempts.append({"attemptId": outcome.attempt_id, "status": "settled", "usage": {"audio": 20},
                             "completeness": "complete", "costMicros": 12})
            if behavior["raise"]:
                attempts[-1].update(status="unsettled", completeness="unknown")
                raise RuntimeError("SECRET provider response body MUST NOT APPEAR")
            outcome.status, outcome.reason = behavior["status"], behavior["reason"]
            outcome.first_audio_ms = 42
            outcome.connection_class = "cold" if len(takes) < 3 else "warm"
            outcome.transcript = SimpleNamespace(status="match", similarity=1)
            self.adapter.last_transcript = kwargs["text"]
            events.append("settle")
            yield b"frame"

    monkeypatch.setattr(voice, "VoiceStreamer", Streamer)
    monkeypatch.setattr(voice, "voice_pricing", lambda kind: "fake-pricing")
    monkeypatch.setattr(voice, "decode_frame", lambda frame: SimpleNamespace(data=b"\0\0" * 240))

    def prepare(extra):
        assert extra == {}  # Cannot increase normal operator daily/monthly limits.
        assert os.environ["COACH_PILOT_STATE"] == str(tmp_path / "shared-campaign")
        events.append("prepared")

    def bootstrap():
        assert events == ["prepared"]
        events.append("bootstrap")
        return "synthetic-key"

    def adapter(kind, name, key, client, *, keep_alive):
        assert (kind, name, key, keep_alive) == ("realtime", "ash", "synthetic-key", True)
        obj = SimpleNamespace(capability=SimpleNamespace(model="synthetic-model"), last_transcript=None)
        adapters.append(obj)
        return obj

    async def close(obj):
        events.append("adapter-closed")
        if behavior["close_raise"]:
            raise RuntimeError("SECRET close body")

    def snapshot(run_id):
        assert events[-1] == "closed"
        return {"runId": run_id, "state": "closed", "attempts": attempts,
                "settledMicros": 12 * len(attempts), "pendingMicros": 99 if behavior["raise"] else 0}

    helpers = SimpleNamespace(
        BACKEND=tmp_path, OWNER="pilot", USER="pilot", prepare_sandbox=prepare, bootstrap=bootstrap,
        new_run=lambda kind, cap: ("synthetic-run", 1), renew=lambda run, gen: gen + 1,
        make_adapter=adapter, close_adapter=close, snapshot=snapshot,
        write_report=lambda path, report: (path / "report.json").write_text(json.dumps(report)),
    )
    monkeypatch.setattr(module, "load_helpers", lambda: helpers)
    return SimpleNamespace(module=module, events=events, takes=takes, adapters=adapters,
                           behavior=behavior, root=tmp_path / "coach_packs/pilot", voice=voice)


def execute(fakes):
    code = asyncio.run(fakes.module.run_generate(SimpleNamespace(cap_usd="1.50")))
    paths = sorted(fakes.root.iterdir())
    path = paths[-1]
    return code, path, json.loads((path / "report.json").read_text())


def test_balanced_same_text_model_voice_no_promotion_and_report(pilot_fakes):
    fakes = pilot_fakes
    accepted = fakes.voice.SITUATIONAL_DELIVERY_ACCEPTED
    deployment_flag = os.environ.get("COACH_SITUATIONAL_DELIVERY_ENABLED")
    assert accepted is False
    code, path, report = execute(fakes)
    assert code == 0 and report["status"] == "complete"
    assert fakes.voice.SITUATIONAL_DELIVERY_ACCEPTED is accepted
    assert os.environ.get("COACH_SITUATIONAL_DELIVERY_ENABLED") == deployment_flag
    assert [a.situational_enabled for a in fakes.adapters] == [False, True]
    assert report["defaultChanged"] is report["candidatePromoted"] is False
    assert len(fakes.takes) == 14
    orders = [p["plannedOrder"] for p in report["pairOrder"]]
    assert orders == [["a", "b"] if i % 2 == 0 else ["b", "a"] for i in range(7)]
    assert abs(orders.count(["a", "b"]) - orders.count(["b", "a"])) == 1
    for offset in range(0, 14, 2):
        a, b = fakes.takes[offset:offset + 2]
        assert a["text"] == b["text"]
        assert a["delivery"].energy == b["delivery"].energy == "warm"
        assert a["delivery"].pace == b["delivery"].pace == "normal"
        assert a["delivery"].emphasis == b["delivery"].emphasis == "none"
    rows = report["results"]
    assert {r["connectionClass"] for r in rows} == {"cold", "warm"}
    for row in rows:
        assert row["firstPCMms"] == 42 and row["totalMs"] >= 0 and row["audioMs"] == 10
        assert row["transcript"] == row["text"] and row["transcriptStatus"] == "match"
        assert row["usage"] == {"audio": 20} and row["ledgerStatus"] == "settled"
        assert row["voice"] == "ash" and row["model"] == "synthetic-model"
        assert (path / row["file"]).read_bytes().startswith(b"RIFF")
    assert report["ledger"]["state"] == "closed"
    for name in ("listen-baseline.wav", "listen-candidate.wav"):
        assert (path / name).read_bytes().startswith(b"RIFF")
    assert json.loads((path / "manifest.json").read_text()) == report["pairOrder"]


@pytest.mark.parametrize("status,reason,expected", [
    ("failed", "provider_error", 1), ("cancelled", "scope_changed", 1),
    ("refused", "budget", 0), ("refused", "operator_budget", 0), ("refused", "disabled", 1),
])
def test_exact_failure_status_and_budget_refusal_no_retries(pilot_fakes, status, reason, expected):
    fakes = pilot_fakes
    fakes.behavior.update(status=status, reason=reason)
    code, path, report = execute(fakes)
    assert code == expected
    assert len(fakes.takes) == 1
    assert report["results"][0]["status"] == status
    assert report["ledger"]["state"] == "closed"
    assert report["status"] == ("budget-refused" if expected == 0 else "failed")
    assert (path / "manifest.json").is_file()


def test_provider_exception_report_redacted_reservations_preserved(pilot_fakes):
    fakes = pilot_fakes
    fakes.behavior["raise"] = True
    code, path, report = execute(fakes)
    assert code == 1 and len(fakes.takes) == 1
    assert report["results"][0]["status"] == "failed"
    assert report["results"][0]["ledgerStatus"] == "unsettled"
    assert report["ledger"]["pendingMicros"] == 99
    assert "SECRET" not in (path / "report.json").read_text()
    assert fakes.events.count("adapter-closed") == 2


def test_unique_directory_no_overwrite_even_same_timestamp(pilot_fakes):
    fakes = pilot_fakes
    first_code, first_path, _ = execute(fakes)
    first_content = (first_path / "report.json").read_bytes()
    fakes.events.clear()
    assert asyncio.run(fakes.module.run_generate(SimpleNamespace(cap_usd="1.50"))) == 0
    assert first_code == 0 and len(list(fakes.root.iterdir())) == 2
    assert (first_path / "report.json").read_bytes() == first_content


def test_close_failure_still_final_report(pilot_fakes):
    pilot_fakes.behavior["close_raise"] = True
    code, path, report = execute(pilot_fakes)
    assert code == 1 and report["status"] == "failed"
    assert report["ledger"]["state"] == "closed"
    assert "SECRET" not in (path / "report.json").read_text()


async def test_live_pilot_uses_versioned_context_real_identity_and_honest_acks(
        session_factory, monkeypatch, tmp_path):
    from app.db import session
    from app.services.coach import live
    from app.tests.test_coach_e10_live import make_coach, seed

    path = Path(__file__).resolve().parents[2] / "scripts/coach_pilot.py"
    spec = importlib.util.spec_from_file_location("sandbox_live_pilot_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(session, "SessionLocal", session_factory)
    monkeypatch.setattr(module, "USER", "alexey")
    monkeypatch.setattr(module, "bootstrap", lambda: None)
    monkeypatch.setattr(module, "out_dir", lambda kind: tmp_path)
    with session_factory() as db:
        wid, eid, sid = seed(db)
    monkeypatch.setattr(module, "seed_workout", lambda: (wid, eid, sid))
    fake_coach, _, _ = make_coach(session_factory)

    async def pipeline(sessions, prefs):
        return live.Pipeline(fake_coach.author, fake_coach.voice, None)

    monkeypatch.setattr(live, "default_pipeline", pipeline)
    result = await module.run_live(SimpleNamespace(
        cap_usd="0.50", voice="ash", effort=None, candidate=False, live_scenario="continuity"))
    report = json.loads((tmp_path / "report.json").read_text())
    assert result == 0 and len(report["results"]) == 9
    assert report["syntheticPlaybackAcks"] and not report["browserOrAcousticAcceptance"]
    assert report["ledger"]["state"] == "closed"
    assert report["stats"]["spoken"] > 0
    assert report["stats"]["opportunities"]["completed"] == report["stats"]["spoken"]
    assert not {"invalid_context", "scope_changed", "owner_mismatch"} & report["stats"]["reasons"].keys()


def test_prompt_guides_do_not_seed_a_repeated_canned_joke():
    from app.services.coach.prompts import AuthorRequest, build_prompt
    from app.services.coach.speech_actions import SCENARIO_EXAMPLES

    request = AuthorRequest("T46", "rest", "rest/playful", ("humor",), "rest-new", 20)
    built = build_prompt(request)
    assert SCENARIO_EXAMPLES["playful"] in built.instructions
    assert "У отдыха тоже есть рабочее место" not in built.instructions
    assert json.loads(built.data)["maxFactIds"] == 2
    assert built.schema["properties"]["usedFactIds"]["maxItems"] == 2