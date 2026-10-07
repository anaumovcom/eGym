"""Luna text author: opt-in Responses API adapter, synthetic fake, reserve→dispatch→settle→validate flow."""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.coach_control import PartialUsage, Pricing, ReportedUsage, UsageBounds
from app.services.coach import ledger
from app.services.coach.memory import CoachMemory
from app.services.coach.prompts import PROMPT_VERSION, AuthorRequest, BuiltPrompt, build_prompt
from app.services.coach.validation import facts_current, validate

RESPONSES_URL = "https://api.openai.com/v1/responses"
INPUT_FRAMING_TOKENS = 256


def text_pricing() -> Pricing:
    cfg = get_settings()
    return Pricing(version=cfg.coach_text_pricing_version, model=cfg.coach_text_model,
                   input_rate=cfg.coach_text_input_rate, cached_rate=cfg.coach_text_cached_rate,
                   output_rate=cfg.coach_text_output_rate, verified=cfg.coach_text_pricing_verified,
                   enforceable_bounds=True)


def request_body(model: str, built: BuiltPrompt, max_output_tokens: int, reasoning_effort: str | None = None) -> dict:
    # Only documented parameters (no temperature). store=false keeps no provider copy.
    body = {"model": model, "store": False, "instructions": built.instructions,
            "input": [{"role": "user", "content": built.data}],
            "text": {"format": {"type": "json_schema", "name": "coach_line", "schema": built.schema, "strict": True}},
            "max_output_tokens": max_output_tokens}
    if reasoning_effort is not None:
        body["reasoning"] = {"effort": reasoning_effort}
    return body


def text_bounds(body: dict, max_output_tokens: int) -> UsageBounds:
    size = len(json.dumps(body, ensure_ascii=False).encode())
    # Every text token covers ≥1 UTF-8 byte; doubling plus framing also covers schema rendering overhead.
    # Output (including billable reasoning) is capped by max_output_tokens on the provider side.
    return UsageBounds(input_tokens=min(1_000_000, 2 * size + INPUT_FRAMING_TOKENS), output_tokens=max_output_tokens)


@dataclass(frozen=True, slots=True)
class AuthorResult:
    output: dict | None
    usage: ReportedUsage | PartialUsage | None
    response_id: str
    complete: bool
    error: str | None = None


def parse_response(payload: object) -> AuthorResult:
    if not isinstance(payload, dict):
        return AuthorResult(None, None, "malformed", False, "provider_malformed")
    response_id = str(payload.get("id") or "unknown")[:120]
    usage: ReportedUsage | PartialUsage | None = None
    raw = payload.get("usage")
    if isinstance(raw, dict):
        details_in, details_out = raw.get("input_tokens_details") or {}, raw.get("output_tokens_details") or {}
        try:
            usage = ReportedUsage(input_tokens=raw["input_tokens"], output_tokens=raw["output_tokens"],
                                  audio_input_tokens=0, audio_output_tokens=0,
                                  cached_input_tokens=details_in.get("cached_tokens", 0),
                                  reasoning_tokens=details_out.get("reasoning_tokens", 0))
        except (KeyError, TypeError, ValueError):
            try:
                usage = PartialUsage(input_tokens=raw.get("input_tokens"), output_tokens=raw.get("output_tokens"))
            except ValueError:
                usage = None
    complete = payload.get("status") == "completed" and isinstance(usage, ReportedUsage)
    text, refused = None, False
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                text = part["text"]
            elif isinstance(part, dict) and part.get("type") == "refusal":
                refused = True
    if payload.get("status") != "completed" or refused or text is None:
        return AuthorResult(None, usage, response_id, complete, "provider_refusal" if refused else "provider_incomplete")
    try:
        output = json.loads(text)
    except ValueError:
        return AuthorResult(None, usage, response_id, complete, "provider_malformed")
    return AuthorResult(output if isinstance(output, dict) else None, usage, response_id, complete,
                        None if isinstance(output, dict) else "provider_malformed")


class LunaTextAdapter:
    """Real Responses API call. Requires injected client and vault key; dispatch gate stays in the ledger."""

    test_only = False
    name = "luna-text"

    def __init__(self, client: httpx.AsyncClient, key: str, *, model: str, url: str = RESPONSES_URL):
        if not url.startswith("https://api.openai.com/"):
            raise ValueError("Fixed provider URL only")
        self.client, self._key, self.model, self.url = client, key, model, url

    def __repr__(self) -> str:
        return f"LunaTextAdapter(model={self.model!r})"

    async def author(self, body: dict) -> AuthorResult:
        response = await self.client.post(self.url, json=body, headers={"Authorization": f"Bearer {self._key}"})
        if response.status_code != 200:
            # Provider bodies are never forwarded; usage unknown keeps the reservation as liability.
            return AuthorResult(None, None, f"http-{response.status_code}", False, "provider_error")
        try:
            return parse_response(response.json())
        except ValueError:
            return AuthorResult(None, None, "malformed", False, "provider_malformed")


class FakeTextAuthor:
    """Synthetic author for tests/corpus. Never touches the network."""

    test_only = True
    name = "fake-text"

    def __init__(self, script: Callable[[dict], object], *, delay_s: float = 0,
                 usage: ReportedUsage | None = None):
        self.script, self.delay_s = script, delay_s
        self.usage = usage or ReportedUsage(input_tokens=600, output_tokens=60, audio_input_tokens=0, audio_output_tokens=0)
        self.calls: list[dict] = []

    async def author(self, body: dict) -> AuthorResult:
        self.calls.append(body)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        output = self.script(body)
        if isinstance(output, Exception):
            raise output
        if isinstance(output, AuthorResult):
            return output
        return AuthorResult(output if isinstance(output, dict) else None, self.usage, f"fake-{len(self.calls)}", True,
                            None if isinstance(output, dict) else "provider_malformed")


_REASONS = {"budget": "budget", "operator_budget": "budget", "strict_cap_unprovable": "budget",
            "pipeline_busy": "pipeline_busy", "owner_mismatch": "owner_mismatch", "stale_attempt": "owner_mismatch",
            "paid_adapter_unavailable": "provider_unavailable", "duplicate_attempt": "duplicate"}


@dataclass(frozen=True, slots=True)
class AuthorOutcome:
    kind: Literal["speech", "local", "silence"]
    reason: str | None
    text: str = ""
    used_fact_ids: tuple[str, ...] = ()
    delivery: dict | None = None
    attempt_ids: tuple[str, ...] = ()
    prompt_version: str = PROMPT_VERSION
    prompt_hash: str = ""
    schema_hash: str = ""


class TextAuthor:
    def __init__(self, sessions: Callable[[], Session], adapter, pricing: Pricing, *, model: str,
                 max_output_tokens: int = 400, timeout_s: float = 8.0, reasoning_effort: str | None = None,
                 now_ms: Callable[[], float] = lambda: time.time() * 1000):
        if not 0 < timeout_s <= 15:
            raise ValueError("Bounded timeout required")
        self.sessions, self.adapter, self.pricing, self.model = sessions, adapter, pricing, model
        self.max_output_tokens, self.timeout_s, self.now_ms = max_output_tokens, timeout_s, now_ms
        self.reasoning_effort = reasoning_effort

    async def author(self, *, run_id: str, owner: str, generation: int, opportunity: str, request: AuthorRequest,
                     memory: CoachMemory | None = None, scope_epoch: int = 0, deadline_ms: float | None = None,
                     local_available: bool = False) -> AuthorOutcome:
        built = build_prompt(request)
        body = request_body(self.model, built, self.max_output_tokens, self.reasoning_effort)
        bounds = text_bounds(body, self.max_output_tokens)
        attempts: list[str] = []

        def fallback(reason: str) -> AuthorOutcome:
            return AuthorOutcome("local" if local_available else "silence", reason, attempt_ids=tuple(attempts),
                                 prompt_hash=built.instructions_hash, schema_hash=built.schema_hash)

        if memory is not None:
            memory.note_attempted(request.topic_key)
        for retry in (0, 1):
            attempt_id = None
            try:
                with self.sessions() as db:
                    attempt_id = ledger.reserve(db, run_id, owner, generation, opportunity, "text", self.pricing,
                                                bounds, retry=retry)
                    attempts.append(attempt_id)
                    ledger.dispatch(db, attempt_id, owner, test_only=self.adapter.test_only,
                                    adapter=None if self.adapter.test_only else self.adapter.name)
            except HTTPException as error:
                if attempt_id is not None:
                    with self.sessions() as db:
                        ledger.cancel_reserved(db, attempt_id)
                return fallback(_REASONS.get(str(error.detail), "provider_unavailable"))
            try:
                # No DB transaction spans the provider await.
                result = await asyncio.wait_for(self.adapter.author(body), timeout=self.timeout_s)
            except (asyncio.CancelledError, Exception) as error:
                with self.sessions() as db:
                    ledger.mark_unsettled(db, attempt_id)
                if isinstance(error, asyncio.CancelledError):
                    raise
                return fallback("provider_timeout" if isinstance(error, TimeoutError) else "provider_error")
            with self.sessions() as db:
                try:
                    ledger.settle(db, attempt_id, result.response_id, result.usage, terminal=True,
                                  complete=result.complete)
                except HTTPException:
                    ledger.mark_unsettled(db, attempt_id)
                    return fallback("usage_unsettled")
                run = ledger.get_run(db, run_id)
                if run.generation != generation or run.state != "active":
                    return fallback("scope_changed")
            if not facts_current(request, scope_epoch, self.now_ms()):
                return fallback("scope_changed")
            if result.output is None:
                return fallback(result.error or "provider_error")
            verdict = validate(result.output, request, memory)
            if verdict.ok:
                if verdict.action == "silence":
                    return AuthorOutcome("silence", verdict.reason, attempt_ids=tuple(attempts),
                                         prompt_hash=built.instructions_hash, schema_hash=built.schema_hash)
                return AuthorOutcome("speech", None, verdict.speech, verdict.used_fact_ids, verdict.delivery,
                                     tuple(attempts), PROMPT_VERSION, built.instructions_hash, built.schema_hash)
            # One calm summary retry with a new reserve and enough time; never a recursive joke hunt.
            time_left = deadline_ms is None or deadline_ms - self.now_ms() >= self.timeout_s * 1000
            if not (request.summary and retry == 0 and time_left):
                return fallback(f"validation_failed:{verdict.reason}")
        return fallback("validation_failed")
