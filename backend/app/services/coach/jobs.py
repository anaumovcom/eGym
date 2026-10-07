"""Bounded test job runner, lock-independent cancel and durable attempt reconciliation."""

import asyncio
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.coach import CoachAttempt, CoachJob
from app.schemas.coach_control import Pricing, ReportedUsage, UsageBounds
from app.services.coach import ledger


class TestJobRunner:
    __test__ = False

    def __init__(self, sessions: Callable[[], Session], timeout: float = 5):
        if not 0 < timeout <= 5:
            raise ValueError("Invalid bounded timeout")
        self.sessions, self.timeout = sessions, timeout
        self.tasks: dict[str, asyncio.Task] = {}

    async def cancel(self, job_id: str) -> None:
        with self.sessions() as db:
            ledger.job_state(db, job_id, "cancelled")
        # DB transaction is already released before awaiting any provider task.
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def run(self, job_id: str, owner: str, generation: int, provider, pricing: Pricing, bounds: UsageBounds) -> None:
        if not getattr(provider, "test_only", False):
            raise ValueError("Only synthetic test adapters; paid providers require E07/E08")
        if job_id in self.tasks or len(self.tasks) >= 4:
            raise HTTPException(409, "pipeline_busy_or_circuit")
        self.tasks[job_id] = asyncio.current_task()
        attempt_id = None
        try:
            with self.sessions() as db:
                job = db.get(CoachJob, job_id)
                if job and job.failures >= 3:
                    raise HTTPException(409, "provider_circuit")
                if not job or job.state != "queued":
                    return
                items, completed, run_id = job.items[:], set(job.completed), job.run_id
            for item in items:
                if item in completed:
                    continue
                with self.sessions() as db:
                    current = db.get(CoachJob, job_id)
                    if current.state != "queued":
                        return
                    attempt_id = ledger.reserve(db, run_id, owner, generation, f"job:{job_id}:{item}", "text", pricing, bounds)
                    ledger.dispatch(db, attempt_id, owner, test_only=True)
                # No DB lock spans transport awaits.
                usage = await asyncio.wait_for(provider.generate(item, bounds), timeout=self.timeout)
                usage = ReportedUsage.model_validate(usage)
                with self.sessions() as db:
                    ledger.settle(db, attempt_id, f"job:{item}", usage, terminal=True)
                    current = db.get(CoachJob, job_id)
                    attempt = db.get(CoachAttempt, attempt_id)
                    run = ledger.get_run(db, run_id)
                    if current.state != "queued" or run.generation != generation or attempt.status != "settled":
                        return
                    current.completed = [*current.completed, item]
                    db.commit()
                attempt_id = None
            with self.sessions() as db:
                current = db.get(CoachJob, job_id)
                if current.state == "queued":
                    current.state = "completed"
                    db.commit()
        except (Exception, asyncio.CancelledError):
            if attempt_id:
                with self.sessions() as db:
                    ledger.mark_unsettled(db, attempt_id)
            with self.sessions() as db:
                current = db.get(CoachJob, job_id)
                if current:
                    current.failures += 1
                    if current.state == "queued":
                        current.state = "failed" if current.failures >= 3 else "paused"
                    db.commit()
            raise
        finally:
            self.tasks.pop(job_id, None)