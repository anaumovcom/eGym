"""Small durable budget ledger for explicit offline achievement generation jobs.

Provider calls never happen inside this module. Every sent request leaves a durable liability.
Secrets are read from the environment or backend env files but are never logged or persisted here.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from filelock import FileLock

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LEDGER = BACKEND_ROOT / "achievement_generation" / "ledger.json"


def durable_bytes(path: Path, data: bytes) -> None:
    """Unique temp, fsync, atomic replace; retry only local sharing violations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    replaced = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(8):
            try:
                os.replace(temp, path)
                replaced = True
                break
            except PermissionError:
                if attempt == 7:
                    raise
                threading.Event().wait(0.025 * (attempt + 1))
    finally:
        # A complete fsynced response is recovery evidence even if Windows keeps
        # the destination locked. Never discard it after exhausting local retries.
        if replaced:
            temp.unlink(missing_ok=True)


def durable_json(path: Path, value: Any) -> None:
    durable_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


OPENAI_RATES = {
    "gpt-6.1-sol": {"input": 2.0, "cached": 0.1, "output": 10.0},
    "gpt-image-2.5-flare": {"input": 8.0, "cached": 2.0, "output": 30.0, "text_input": 5.0},
}


def read_credential(provider: str) -> str:
    names = ("OPENAI_API_KEY", "OPENAPI_KEY") if provider == "openai" else ("FISH_API_KEY",)
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    for filename in (".env.local", ".env"):
        path = BACKEND_ROOT / filename
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in names and value.strip():
                return value.strip().strip('"').strip("'")
    raise RuntimeError(f"credential_unavailable:{provider}")


def micros(usd: float) -> int:
    return int(round(usd * 1_000_000))


def token_cost(model: str, usage: dict[str, Any]) -> int:
    rates = OPENAI_RATES[model]
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    details = usage.get("input_tokens_details") or {}
    cached = int(details.get("cached_tokens") or 0)
    if "text_input" in rates:
        # Conservative upper estimate: never drop image-reference tokens when text detail exists.
        text_rate = rates["input"]
    else:
        text_rate = rates["input"]
    value = ((input_tokens - cached) * text_rate + cached * rates["cached"] + output_tokens * rates["output"]) / 1_000_000
    return max(0, int(value * 1_000_000 + 0.999999))


def fish_rate_per_byte(now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    promo_end = datetime(2026, 11, 12, 17, 0, tzinfo=UTC)
    return 10.0 / 1_000_000 if now < promo_end else 50.0 / 1_000_000


@dataclass
class BudgetLedger:
    path: Path = DEFAULT_LEDGER
    openai_cap_usd: float = 36.0
    fish_cap_usd: float = 15.0

    def __post_init__(self) -> None:
        self.caps = {"openai": micros(self.openai_cap_usd), "fish": micros(self.fish_cap_usd)}
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.is_file():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"schemaVersion": 1, "attempts": []}

    def _save(self) -> None:
        # All mutations are synchronous on the generator's coordinator/event-loop thread.
        # A job-wide FileLock excludes other processes; unique temps avoid stale collisions.
        durable_json(self.path, self.data)

    def job_lock(self) -> FileLock:
        """One offline generator owns the ledger/catalog/manifest at a time.

        Acquire BEFORE constructing a ledger snapshot for a job. OS releases the lock
        after a crash; the lock file itself is not evidence that a job is still running.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return FileLock(str(self.path.with_suffix(".job.lock")), timeout=0)

    def attempts(self, provider: str | None = None) -> list[dict[str, Any]]:
        return [row for row in self.data["attempts"] if provider is None or row["provider"] == provider]

    def committed(self, provider: str) -> int:
        return sum((row.get("costMicros") if row.get("costMicros") is not None else row["reserveMicros"])
                   if row["status"] in {"reserved", "sent", "unsettled"} else (row.get("costMicros") or 0)
                   for row in self.attempts(provider) if row["status"] not in {"cancelled", "refused"})

    def summary(self) -> dict[str, Any]:
        result = {}
        for provider, cap in self.caps.items():
            spent = self.committed(provider)
            result[provider] = {"capMicros": cap, "committedMicros": spent, "availableMicros": max(0, cap - spent),
                                "requests": sum(row["status"] in {"sent", "settled", "unsettled"} for row in self.attempts(provider))}
        return result

    def find(self, key: str) -> dict[str, Any] | None:
        return next((row for row in self.data["attempts"] if row["key"] == key), None)

    def reserve(self, key: str, provider: str, kind: str, model: str, reserve_micros: int) -> dict[str, Any] | None:
        existing = self.find(key)
        if existing:
            if existing["status"] == "settled":
                return None
            if existing["status"] in {"sent", "unsettled"}:
                raise RuntimeError(f"previous_attempt_outcome_unknown:{key}")
            if existing["status"] == "reserved":
                return existing
            raise RuntimeError(f"previous_attempt_failed:{key}")
        if self.committed(provider) + reserve_micros > self.caps[provider]:
            raise RuntimeError(f"budget_exhausted:{provider}")
        row = {"key": key, "provider": provider, "kind": kind, "model": model, "reserveMicros": reserve_micros,
               "status": "reserved", "createdAt": time.time(), "requestId": None, "usage": None, "costMicros": None}
        self.data["attempts"].append(row)
        self._save()
        return row

    def sent(self, key: str) -> None:
        row = self.find(key)
        if row is None:
            raise KeyError(key)
        row["status"] = "sent"
        row["sentAt"] = time.time()
        self._save()

    def settle(self, key: str, cost_micros: int, *, request_id: str = "", usage: dict[str, Any] | None = None) -> None:
        row = self.find(key)
        if row is None:
            raise KeyError(key)
        if cost_micros > row["reserveMicros"]:
            # Record actual liability before stopping; never erase an over-reserve bill.
            row.update(status="settled", costMicros=cost_micros, requestId=request_id[:120],
                       usage=usage, settledAt=time.time(), exceededReserve=True)
            self._save()
            raise RuntimeError(f"actual_cost_exceeds_reserve:{key}")
        row.update(status="settled", costMicros=cost_micros, requestId=request_id[:120], usage=usage, settledAt=time.time())
        self._save()

    def unsettled(self, key: str) -> None:
        row = self.find(key)
        if row is not None and row["status"] in {"sent", "reserved"}:
            row["status"] = "unsettled" if row["status"] == "sent" else "cancelled"
            self._save()
