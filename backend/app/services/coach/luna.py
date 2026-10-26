"""Luna text author: opt-in Responses API adapter, synthetic fake, reserve→dispatch→settle→validate flow."""

import asyncio
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.coach_limits import COACH_TEXT_OUTPUT_TOKENS
from app.core.config import get_settings
from app.schemas.coach_control import PartialUsage, Pricing, ReportedUsage, UsageBounds
from app.services.coach import journal, ledger
from app.services.coach.memory import CoachMemory, opening
from app.services.coach.prompts import JUDGE_INSTRUCTIONS, PROMPT_VERSION, AuthorRequest, BuiltPrompt, build_prompt
from app.services.coach.routing import Route, TaskClass, degrade, task_class
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
    # VD journal only: HTTP status and a short sanitized provider error message.
    http_status: int | None = None
    detail: str | None = None


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


def provider_error_detail(response: httpx.Response) -> str | None:
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return None
    if not isinstance(error, dict):
        return None
    head = " ".join(str(error.get(key)) for key in ("type", "code") if isinstance(error.get(key), str))
    message = error.get("message") if isinstance(error.get("message"), str) else ""
    return journal.sanitize(f"{head}: {message}" if head else message, 300)


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
            # Only the documented error code/message reaches the journal, sanitized and bounded.
            return AuthorResult(None, None, f"http-{response.status_code}", False, "provider_error",
                                http_status=response.status_code, detail=provider_error_detail(response))
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


# Live runs 26.10.2026: the judge adds ~3.5 s. Only the few headline moments wait for it; frequent lines
# (set results, summaries of an exercise, «why») pick locally: a fresh opening and a change of technique.
JUDGED_TASKS = frozenset({"setup/opening", "setup/act", "setup/boss", "rest/record", "summary/workout"})


def _opening(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split()[:2])


def _stems(text: str) -> set[str]:
    # A crude Russian stem: drop up to two ending letters, keep 4–6 («трос», «тросу» → «трос»).
    return {word[:min(6, max(4, len(word) - 2))] for word in re.findall(r"[а-яё]{4,}", text.lower())}


def local_pick(valid: list, request: AuthorRequest) -> int:
    heard = request.recent_heard[-6:]
    openings = {_opening(str(u.get("text", ""))) for u in heard}
    last_intent = heard[-1].get("intent") if heard else None
    # Words already heard in two recent lines are a worn-out joke (live run 26.10.2026: «трос» in five lines).
    counts: dict[str, int] = {}
    for u in heard:
        for stem in _stems(str(u.get("text", ""))):
            counts[stem] = counts.get(stem, 0) + 1
    worn = {stem for stem, count in counts.items() if count >= 2}
    scored = []
    for index, (candidate, verdict) in enumerate(valid):
        score = 2 * (_opening(verdict.speech) not in openings) + (candidate.get("intent") != last_intent)
        score += 0.5 * (candidate.get("intent") == "humor" and request.humor not in {None, "off"})
        score -= 0.5 * len(_stems(verdict.speech) & worn)
        scored.append((score, -index))
    return -max(scored)[1]


# Documented overload/rate answers carry no work: one fresh attempt (a new reserve) may follow.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503})
RETRY_PAUSE_S = 0.3
# Live runs 26.10.2026: on a degraded API three variants took 13 s and judges timed out. A variant line slower
# than SLOW_LINE_MS, or timing out, switches to single lines for SLOW_PAUSE_S; a judge timeout pauses the judge.
SLOW_LINE_MS = 12_000
SLOW_PAUSE_S = 180.0
_REASONS = {"budget": "budget", "operator_budget": "budget", "strict_cap_unprovable": "budget",
            "budget_bucket": "budget",
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
    intent: str | None = None  # Validated chosen intent, never inferred from the trigger.


class TextAuthor:
    def __init__(self, sessions: Callable[[], Session], adapter, pricing: Pricing, *, model: str,
                 max_output_tokens: int = COACH_TEXT_OUTPUT_TOKENS, timeout_s: float = 8.0, reasoning_effort: str | None = None,
                 now_ms: Callable[[], float] = lambda: time.time() * 1000,
                 routes: dict[TaskClass, Route] | None = None):
        if not 0 < timeout_s <= 15:
            raise ValueError("Bounded timeout required")
        self.sessions, self.adapter, self.pricing, self.model = sessions, adapter, pricing, model
        self.max_output_tokens = max(COACH_TEXT_OUTPUT_TOKENS, max_output_tokens)
        self.timeout_s, self.now_ms = timeout_s, now_ms
        self.reasoning_effort = reasoning_effort
        # V0.4: per task class model/reasoning/output budget. Without routes every task uses the fields above.
        self.routes = routes
        self.last_route: Route | None = None
        # Slow-provider guard (monotonic seconds): while it lasts, lines skip variants and the judge.
        self.slow_until = self.judge_paused_until = 0.0

    def route(self, task: str, tier: int = 0) -> Route:
        cls = task_class(task)
        if self.routes and cls in self.routes:
            return degrade(self.routes[cls], tier)
        return degrade(Route(cls, self.model, self.pricing, self.reasoning_effort, self.max_output_tokens,
                             self.timeout_s), tier)

    def _journal(self, attempt_id: str | None, **fields) -> None:
        """VD: best-effort request journal; never fails the line that reports it."""
        if not attempt_id:
            return
        try:
            with self.sessions() as db:
                journal.annotate(db, attempt_id, **fields)
        except Exception:  # noqa: BLE001 - diagnostics only
            pass

    def _refusal(self, run_id: str, reason: str, purpose: str, model: str, meta: dict) -> None:
        try:
            with self.sessions() as db:
                journal.record_refusal(db, run_id, stage="text", purpose=purpose, reason=reason, model=model, meta=meta)
        except Exception:  # noqa: BLE001 - diagnostics only
            pass

    async def generate(self, *, run_id: str, owner: str, generation: int, opportunity: str, task: str, name: str,
                       instructions: str, data: str, schema: dict, purpose: str, meta: dict | None = None,
                       reasoning_effort: str | None = None, tier: int = 0,
                       retry_overload: bool = True) -> tuple[dict | None, str | None]:
        """Structured whole-workout generation (scenario, bible, episode, judge) on the same paid path:
        reserve → dispatch → provider → settle, journaled. The caller validates the returned JSON."""
        route = self.route(task, tier)
        if reasoning_effort is not None and tier < 2:
            route = Route(route.task_class, route.model, route.pricing, reasoning_effort, route.max_output_tokens,
                          route.timeout_s)
        meta = {"task": task, **(meta or {})}
        body = {"model": route.model, "store": False, "instructions": instructions,
                "input": [{"role": "user", "content": data}],
                "text": {"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
                "max_output_tokens": route.max_output_tokens}
        if route.reasoning_effort is not None:
            body["reasoning"] = {"effort": route.reasoning_effort}
        bounds = text_bounds(body, route.max_output_tokens)
        for retry in (0, 1):
            attempt_id = None
            try:
                with self.sessions() as db:
                    attempt_id = ledger.reserve(db, run_id, owner, generation, opportunity, "text", route.pricing,
                                                bounds, retry=retry, purpose=purpose, meta=meta)
                    ledger.dispatch(db, attempt_id, owner, test_only=self.adapter.test_only,
                                    adapter=None if self.adapter.test_only else self.adapter.name)
            except HTTPException as error:
                if attempt_id is not None:
                    with self.sessions() as db:
                        ledger.cancel_reserved(db, attempt_id)
                    self._journal(attempt_id, outcome="cancelled", error_code=str(error.detail),
                                  finished_at=time.time())
                else:
                    self._refusal(run_id, str(error.detail), purpose, route.model, meta)
                return None, _REASONS.get(str(error.detail), "provider_unavailable")
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(self.adapter.author(body), timeout=route.timeout_s)
            except (asyncio.CancelledError, Exception) as error:
                with self.sessions() as db:
                    ledger.mark_unsettled(db, attempt_id)
                cancelled = isinstance(error, asyncio.CancelledError)
                reason = ("cancelled" if cancelled else "provider_timeout" if isinstance(error, TimeoutError)
                          else "provider_error")
                self._journal(attempt_id, outcome="cancelled" if cancelled else "error", error_code=reason,
                              duration_ms=(time.monotonic() - started) * 1000, finished_at=time.time())
                if cancelled:
                    raise
                return None, reason
            self._journal(attempt_id, duration_ms=(time.monotonic() - started) * 1000,
                          http_status=result.http_status, error_detail=result.detail)
            with self.sessions() as db:
                try:
                    ledger.settle(db, attempt_id, result.response_id, result.usage, terminal=True,
                                  complete=result.complete)
                except HTTPException:
                    ledger.mark_unsettled(db, attempt_id)
                    self._journal(attempt_id, outcome="error", error_code="usage_unsettled", finished_at=time.time())
                    return None, "usage_unsettled"
            if result.output is None:
                self._journal(attempt_id, outcome="error", error_code=result.error or "provider_error",
                              finished_at=time.time())
                if retry == 0 and retry_overload and result.http_status in RETRYABLE_STATUS:
                    await asyncio.sleep(RETRY_PAUSE_S)
                    continue
                return None, result.error or "provider_error"
            self._journal(attempt_id, outcome="speech", finished_at=time.time())
            self.last_generation_attempt = attempt_id
            return result.output, None
        return None, "provider_error"

    async def _pick_variant(self, output: dict, request: AuthorRequest, memory: CoachMemory | None, *, run_id: str,
                            owner: str, generation: int, opportunity: str, tier: int):
        """V7.1: every variant passes the full validator; two or more go to a cheap judge, the first valid one wins
        when the judge is unavailable. Returns (variant output, verdict) or None if no variant is valid."""
        candidates = output.get("candidates") if isinstance(output, dict) else None
        if candidates is None and isinstance(output, dict):
            candidates = [output]  # A single-line answer is one variant (fakes, legacy providers).
        if not isinstance(candidates, list):
            return None, "schema"
        valid, silence, first_failure = [], None, None
        for candidate in candidates[:3]:
            verdict = validate(candidate, request, memory)
            if verdict.ok and verdict.action == "speak":
                valid.append((candidate, verdict))
            elif verdict.ok:
                silence = silence or (candidate, verdict)  # A deliberate silence is a decision, not a failure.
            elif first_failure is None:
                first_failure = verdict.reason
        if len(valid) < 2:
            return (valid[0] if valid else silence), first_failure
        if request.task not in JUDGED_TASKS or time.monotonic() < self.judge_paused_until:
            index = local_pick(valid, request)
            self.last_judge = {"best": index, "options": len(valid), "local": True}
            return valid[index], None
        heard = [str(u.get("text", ""))[:200] for u in request.recent_heard[-6:]]
        data = json.dumps({"task": request.task, "mood": request.mood, "intent": list(request.intents),
                           "scenario": (request.scenario or {}).get("title"), "recentHeard": heard,
                           "candidates": [{"index": i, "text": v.speech, "intent": c.get("intent")}
                                          for i, (c, v) in enumerate(valid)]}, ensure_ascii=False)
        schema = {"type": "object", "additionalProperties": False, "required": ["best", "reason"],
                  "properties": {"best": {"type": "integer", "enum": list(range(len(valid)))}, "reason": {"type": "string"}}}
        choice, error = await self.generate(run_id=run_id, owner=owner, generation=generation,
                                        opportunity=f"{opportunity}:judge", task="judge/pick", name="coach_judge",
                                        instructions=JUDGE_INSTRUCTIONS, data=data, schema=schema, purpose="judge",
                                        meta={"trigger_id": request.trigger_id}, tier=tier, retry_overload=False)
        if error == "provider_timeout":
            self.judge_paused_until = time.monotonic() + SLOW_PAUSE_S
        best = choice.get("best") if isinstance(choice, dict) else None
        if not (type(best) is int and 0 <= best < len(valid)):
            # The judge is an improvement, not a gate: without it the local pick still prefers a fresh line.
            best = local_pick(valid, request)
            self.last_judge = {"best": best, "options": len(valid), "local": True}
            return valid[best], None
        self.last_judge = {"best": best, "options": len(valid)}
        return valid[best], None

    def slow(self) -> bool:
        return time.monotonic() < self.slow_until

    def reject_generation(self, reason: str) -> None:
        """The caller's validation refused the JSON returned by generate()."""
        self._journal(getattr(self, "last_generation_attempt", None), outcome="rejected",
                      error_code=f"validation_failed:{reason}")

    async def author(self, *, run_id: str, owner: str, generation: int, opportunity: str, request: AuthorRequest,
                     memory: CoachMemory | None = None, scope_epoch: int = 0, deadline_ms: float | None = None,
                     local_available: bool = False, tier: int = 0, purpose: str | None = None,
                     meta: dict | None = None, timeout_s: float | None = None) -> AuthorOutcome:
        built = build_prompt(request)
        route = self.route(request.task, tier)
        if timeout_s is not None:
            # Prepared lines have no listener waiting: they may use the longest spoken-line bound.
            route = Route(route.task_class, route.model, route.pricing, route.reasoning_effort, route.max_output_tokens,
                          min(15.0, timeout_s))
        self.last_route = route
        purpose = purpose or ("summary" if request.summary else "live")
        meta = {"trigger_id": request.trigger_id, "task": request.task, **(meta or {})}
        # All phases need room for reasoning + structured JSON, even a short cue.
        # Reserve the same full cap sent to the provider BEFORE every dispatch.
        body = request_body(route.model, built, route.max_output_tokens, route.reasoning_effort)
        bounds = text_bounds(body, route.max_output_tokens)
        attempts: list[str] = []
        memory_revision = memory.revision if memory is not None else None

        def fallback(reason: str, outcome: str = "error", **fields) -> AuthorOutcome:
            if attempts:
                self._journal(attempts[-1], outcome=outcome, error_code=reason, finished_at=time.time(), **fields)
            return AuthorOutcome("local" if local_available else "silence", reason, attempt_ids=tuple(attempts),
                                 prompt_hash=built.instructions_hash, schema_hash=built.schema_hash)

        if memory is not None:
            tip = request.coach_context.tip if request.coach_context else None
            memory.note_attempted(request.topic_key, category=request.category,
                                  tip_id=tip.tip_id if tip else None, tip_version=tip.version if tip else None)
        for retry in (0, 1):
            attempt_id = None
            try:
                with self.sessions() as db:
                    attempt_id = ledger.reserve(db, run_id, owner, generation, opportunity, "text", route.pricing,
                                                bounds, retry=retry, purpose=purpose, meta=meta)
                    attempts.append(attempt_id)
                    ledger.dispatch(db, attempt_id, owner, test_only=self.adapter.test_only,
                                    adapter=None if self.adapter.test_only else self.adapter.name)
            except HTTPException as error:
                reason = _REASONS.get(str(error.detail), "provider_unavailable")
                if attempt_id is not None:
                    with self.sessions() as db:
                        ledger.cancel_reserved(db, attempt_id)
                    return fallback(reason, "cancelled", error_detail=str(error.detail))
                self._refusal(run_id, str(error.detail), purpose, route.model, meta)
                return fallback(reason)
            started = time.monotonic()
            try:
                # No DB transaction spans the provider await.
                result = await asyncio.wait_for(self.adapter.author(body), timeout=route.timeout_s)
            except (asyncio.CancelledError, Exception) as error:
                with self.sessions() as db:
                    ledger.mark_unsettled(db, attempt_id)
                elapsed = (time.monotonic() - started) * 1000
                if isinstance(error, asyncio.CancelledError):
                    self._journal(attempt_id, outcome="cancelled", error_code="cancelled", duration_ms=elapsed,
                                  finished_at=time.time())
                    raise
                timeout = isinstance(error, TimeoutError)
                if timeout and request.variants > 1:  # A short in-set cue timing out once is not a slow provider.
                    self.slow_until = time.monotonic() + SLOW_PAUSE_S
                return fallback("provider_timeout" if timeout else "provider_error", duration_ms=elapsed,
                                error_detail=None if timeout else type(error).__name__)
            elapsed = (time.monotonic() - started) * 1000
            if request.variants > 1 and elapsed > SLOW_LINE_MS:
                self.slow_until = time.monotonic() + SLOW_PAUSE_S
            self._journal(attempt_id, duration_ms=elapsed, http_status=result.http_status,
                          error_detail=result.detail)
            with self.sessions() as db:
                try:
                    ledger.settle(db, attempt_id, result.response_id, result.usage, terminal=True,
                                  complete=result.complete)
                except HTTPException:
                    ledger.mark_unsettled(db, attempt_id)
                    return fallback("usage_unsettled")
                run = ledger.get_run(db, run_id)
                if run.generation != generation or run.state != "active":
                    return fallback("scope_changed", "stale")
            if not facts_current(request, scope_epoch, self.now_ms()):
                return fallback("scope_changed", "stale")
            if memory is not None and memory.revision != memory_revision:
                return fallback("scope_changed", "stale")  # Deletion/expiry while awaiting must not refill memory.
            if result.output is None:
                # Live run 26.10.2026: «503 server_is_overloaded» answers in under a second — one fresh attempt
                # when the moment still has a full route timeout left.
                time_left = deadline_ms is None or deadline_ms - self.now_ms() >= route.timeout_s * 1000
                if retry == 0 and result.http_status in RETRYABLE_STATUS and time_left:
                    self._journal(attempt_id, outcome="error", error_code=result.error or "provider_error",
                                  finished_at=time.time())
                    await asyncio.sleep(RETRY_PAUSE_S)
                    continue
                return fallback(result.error or "provider_error")
            if request.variants > 1:
                picked = await self._pick_variant(result.output, request, memory, run_id=run_id, owner=owner,
                                                  generation=generation, opportunity=opportunity, tier=tier)
                if picked[0] is None:
                    reason = f"validation_failed:{picked[1] or 'schema'}"
                    self._journal(attempt_id, outcome="rejected", error_code=reason, finished_at=time.time())
                    return AuthorOutcome("local" if local_available else "silence", reason,
                                         attempt_ids=tuple(attempts), prompt_hash=built.instructions_hash,
                                         schema_hash=built.schema_hash)
                result_output, verdict = picked[0]
                result = AuthorResult(result_output, result.usage, result.response_id, result.complete)
            else:
                verdict = validate(result.output, request, memory)
            if verdict.ok:
                if verdict.action == "silence":
                    self._journal(attempt_id, outcome="silence", error_code=verdict.reason, finished_at=time.time())
                    return AuthorOutcome("silence", verdict.reason, attempt_ids=tuple(attempts),
                                         prompt_hash=built.instructions_hash, schema_hash=built.schema_hash)
                if memory is not None:
                    memory.note_attempted(request.topic_key, intent=result.output["intent"])
                self._journal(attempt_id, outcome="speech", finished_at=time.time())
                return AuthorOutcome("speech", None, verdict.speech, verdict.used_fact_ids, verdict.delivery,
                                     tuple(attempts), PROMPT_VERSION, built.instructions_hash, built.schema_hash,
                                     intent=result.output["intent"])
            # The rejected draft stays out of the journal: only the reason is recorded.
            self._journal(attempt_id, outcome="rejected", error_code=f"validation_failed:{verdict.reason}",
                          finished_at=time.time())
            # One calm summary retry with a new reserve and enough time; never a recursive joke hunt.
            time_left = deadline_ms is None or deadline_ms - self.now_ms() >= route.timeout_s * 1000
            # Live run 26.10.2026: a single rest line that opened like a recent one was lost to silence. One retry
            # that names the worn opening (never in a set: its moment is short).
            draft = str(result.output.get("text") or result.output.get("framingText") or "")
            reopen = (verdict.reason == "topic_repeat" and request.variants == 1 and request.phase != "active"
                      and retry == 0 and time_left and bool(opening(draft)))
            if reopen:
                worn = re.sub(r"[^\w\s-]", "", opening(draft))[:40]
                request = replace(request, retry_note=f"Черновик начинался как недавняя реплика («{worn}»). "
                                                      "Начни с другого слова и другого образа.")
                built = build_prompt(request)
                body = request_body(route.model, built, route.max_output_tokens, route.reasoning_effort)
                bounds = text_bounds(body, route.max_output_tokens)
            if not ((request.summary or reopen) and retry == 0 and time_left):
                attempts_snapshot = tuple(attempts)
                return AuthorOutcome("local" if local_available else "silence", f"validation_failed:{verdict.reason}",
                                     attempt_ids=attempts_snapshot, prompt_hash=built.instructions_hash,
                                     schema_hash=built.schema_hash)
        return AuthorOutcome("local" if local_available else "silence", "validation_failed", attempt_ids=tuple(attempts),
                             prompt_hash=built.instructions_hash, schema_hash=built.schema_hash)
