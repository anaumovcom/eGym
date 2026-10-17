"""U07 offline plan and explicitly authorized, sandboxed A/B listening pilot.

Imports stay offline until generate authorization passes. Never promotes a candidate.
"""

import argparse
import asyncio
import json
import sys
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "app/tests/fixtures/coach_u07_delivery.json"


def build_plan() -> dict:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pairs = []
    for case in fixture["cases"]:
        base = {"speechText": case["text"], "pronunciation": [],
                "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}
        pairs.append({
            "id": case["id"], "localOnly": case["localOnly"],
            "a": {**base, "profile": "legacy", "version": fixture["baselineVersion"]},
            "b": {**base, "profile": case["profile"], "version": fixture["candidateVersion"]},
            "generation": "forbidden-current-recordings-only" if case["localOnly"] else "blocked-pending-cap",
        })
    return {
        "schemaVersion": 1, "mode": "offline-plan-only", "status": "blocked-pending-paid-cap-and-listening",
        "paidUsd": "0.00", "approvedCapUsd": None, "proposedCapUsd": "0.10",
        "proposalIsApproval": False, "providerRequests": 0, "generationAvailable": False,
        "baselineVersion": fixture["baselineVersion"], "candidateVersion": fixture["candidateVersion"],
        "packStyleVersion": fixture["packStyleVersion"], "defaultChanged": False,
        "futureNonLocalRequestCeiling": 2 * sum(not case["localOnly"] for case in fixture["cases"]),
        "futureRequirements": [
            "Separate explicit paid-cap approval; proposal is not approval.",
            "Future execution must require explicit confirmation AND positive cap before any key/settings/API access.",
            "Same voice/model/text/energy/pace/order-balanced takes; ledger reserve-dispatch-settle for every attempt.",
            "Cap may stop comparison early; no retries, full-pack generation or regeneration of count/safety.",
            "Record usage/completeness, voice-first-PCM, total generation time, exact transcript and added words.",
            "User listens for warmth/naturalness/clarity/humor/low onset/stable timbre; no automatic promotion.",
            "Only later accepted code change plus explicit deployment flag may select candidate in live speech.",
        ],
        "pairs": pairs,
    }


def load_helpers():
    # Only reached after confirmation/cap validation; helper import itself is app-free.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import coach_pilot

    return coach_pilot


def generation_pairs() -> list[dict]:
    # Defense in depth: count/safety stay excluded even if fixture metadata regresses.
    return [pair for pair in build_plan()["pairs"]
            if not pair["localOnly"] and pair["b"]["profile"] not in {"count", "safety"}]


def disable_send_retry(adapter) -> None:
    """Pilot-only: retain warm sockets but never resend after a failed warm send.

    Production's reconnect-on-send-error is useful normally, but this experiment
    must not risk a second send when delivery of the first is ambiguous.
    """
    async def send_once(message):
        from app.services.coach.voice import VoiceError

        if adapter._socket is not None and adapter._now_s() - adapter._opened_at >= adapter.MAX_SESSION_S:
            await adapter._drop()
        adapter.last_connection_class = "cold" if adapter._socket is None else "warm"
        socket = adapter._socket if adapter._socket is not None else await adapter._open()
        try:
            await socket.send(message)
        except Exception as error:
            raise VoiceError("provider_disconnected") from error
        return socket

    adapter._send = send_once


async def record_take(streamer, adapter, helpers, run_id, generation, pair, variant, path):
    from app.schemas.coach import CoachScope
    from app.services.coach.packs import pcm_to_wav
    from app.services.coach.voice import SAMPLE_RATE, Delivery, VoiceOutcome, decode_frame

    take = pair[variant]
    outcome = VoiceOutcome()
    pcm = bytearray()
    # Reserve/dispatch refusal never enters the adapter; do not inherit a prior take.
    adapter.last_transcript = None
    started = time.monotonic()
    raised = False
    try:
        async for frame in streamer.stream(
                run_id=run_id, owner=helpers.OWNER, generation=generation,
                opportunity=f"u07:{pair['id']}:{variant}", text=take["speechText"],
                scope=CoachScope(user_id=helpers.USER, run_id=run_id),
                generation_id=f"u07-{time.time_ns()}", outcome=outcome,
                delivery=Delivery(**take["delivery"], profile=take["profile"])):
            pcm.extend(decode_frame(frame).data)
    except Exception:
        # Never serialize exception messages: SDK errors can contain bodies/credentials.
        raised = True
        outcome.status = "failed"
    total_ms = round((time.monotonic() - started) * 1000, 1)
    name = f"{pair['id']}-{variant}.wav"
    (path / name).write_bytes(pcm_to_wav(bytes(pcm)))
    check = outcome.transcript
    row = {
        "case": pair["id"], "variant": variant, "profile": take["profile"], "version": take["version"],
        "text": take["speechText"], "voice": "ash", "model": adapter.capability.model,
        "status": outcome.status,
        "budgetRefusal": not raised and outcome.status == "refused" and outcome.reason in {"budget", "operator_budget"},
        "error": "provider_failure" if raised or outcome.status == "failed" else None,
        "firstPCMms": outcome.first_audio_ms, "connectionClass": outcome.connection_class,
        "totalMs": total_ms, "audioMs": round(len(pcm) / 2 / SAMPLE_RATE * 1000, 1),
        "transcript": adapter.last_transcript if outcome.attempt_id else None,
        "transcriptStatus": check.status if check else None,
        "similarity": check.similarity if check else None,
        "attemptId": outcome.attempt_id, "file": name,
    }
    return row, bytes(pcm)


async def run_generate(args) -> int:
    helpers = load_helpers()
    # Caller campaign path is deliberately untouched; keep normal $3/$5 limits.
    helpers.prepare_sandbox({})
    path = Path(tempfile.mkdtemp(prefix="u07-", dir=_report_root(helpers)))
    report = {"schemaVersion": 1, "mode": "u07-ab-listening", "capUsd": args.cap_usd,
              "voice": "ash", "defaultChanged": False, "candidatePromoted": False,
              "results": [], "pairOrder": [], "ledger": None, "runId": None, "status": "failed"}
    failed = False
    run_id = None
    adapters = {}
    parts = {"a": [], "b": []}
    try:
        import httpx

        from app.db.session import SessionLocal
        from app.services.coach.packs import pcm_to_wav
        from app.services.coach.voice import SAMPLE_RATE, VoiceStreamer, voice_pricing

        key = helpers.bootstrap()
        run_id, generation = helpers.new_run("test", args.cap_usd)
        report["runId"] = run_id
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
            for variant in ("a", "b"):
                adapter = helpers.make_adapter("realtime", "ash", key, client, keep_alive=True)
                # Explicit per-instance pilot override, never production settings/acceptance.
                adapter.situational_enabled = variant == "b"
                disable_send_retry(adapter)
                adapters[variant] = adapter
            del key
            report["model"] = adapters["a"].capability.model
            if adapters["a"].capability.model != adapters["b"].capability.model:
                raise ValueError("A/B model mismatch")
            streamers = {v: VoiceStreamer(SessionLocal, a, voice_pricing("realtime"),
                                          first_audio_timeout_s=8, total_timeout_s=30)
                         for v, a in adapters.items()}
            for index, pair in enumerate(generation_pairs()):
                order = ("a", "b") if index % 2 == 0 else ("b", "a")
                manifest = {"case": pair["id"], "plannedOrder": list(order), "files": []}
                report["pairOrder"].append(manifest)
                stop = False
                for variant in order:
                    generation = helpers.renew(run_id, generation)
                    row, pcm = await record_take(streamers[variant], adapters[variant], helpers,
                                                 run_id, generation, pair, variant, path)
                    report["results"].append(row)
                    manifest["files"].append(row["file"])
                    parts[variant].append(pcm)
                    if row["status"] != "complete":
                        failed |= not row["budgetRefusal"]
                        stop = True
                        break
                if stop:
                    break
        gap = bytes(int(0.6 * SAMPLE_RATE) * 2)
        for variant, label in (("a", "baseline"), ("b", "candidate")):
            (path / f"listen-{label}.wav").write_bytes(pcm_to_wav(gap.join(parts[variant])))
        report["status"] = "failed" if failed else (
            "budget-refused" if any(r["budgetRefusal"] for r in report["results"]) else "complete")
    except Exception:
        failed = True
        report["error"] = "pilot_failure"
    finally:
        for adapter in adapters.values():
            try:
                await helpers.close_adapter(adapter)
            except Exception:
                failed = True
                report["cleanupError"] = "adapter_close_failure"
        if run_id is not None:
            try:
                from app.db.session import SessionLocal
                from app.services.coach import ledger

                with SessionLocal() as db:
                    ledger.cancel_run(db, run_id, close=True)
                # Closing does not forgive unsettled reservations or reset campaign spend.
                report["ledger"] = helpers.snapshot(run_id)
                attempts = {a["attemptId"]: a for a in report["ledger"]["attempts"]}
                for row in report["results"]:
                    attempt = attempts.get(row["attemptId"], {})
                    row.update({k: attempt.get(k) for k in ("usage", "costMicros", "completeness")})
                    row["ledgerStatus"] = attempt.get("status")
            except Exception:
                failed = True
                report["ledgerError"] = "ledger_finalize_failure"
        if failed:
            report["status"] = "failed"
        helpers.write_report(path, report)
        (path / "manifest.json").write_text(json.dumps(report["pairOrder"], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"U07 {report['status']}: {path}")
    return int(failed)


def _report_root(helpers) -> Path:
    root = helpers.BACKEND / "coach_packs" / "pilot"
    root.mkdir(parents=True, exist_ok=True)
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="Offline preparation JSON; never spends money")
    generate = commands.add_parser("generate", help="Explicitly paid, bounded U07 A/B only; never a full pack")
    generate.add_argument("--confirm-paid", action="store_true")
    generate.add_argument("--cap-usd", required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
        return 0
    try:
        cap = Decimal(args.cap_usd)
        valid = cap.is_finite() and 0 < cap <= 2
    except InvalidOperation:
        valid = False
    if not args.confirm_paid or not valid:
        parser.error("generate requires --confirm-paid and a finite cap greater than zero and at most $2")
    return asyncio.run(run_generate(args))


if __name__ == "__main__":
    raise SystemExit(main())
