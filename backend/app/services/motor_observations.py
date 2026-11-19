"""Checkpoint exercise data away from the hardware and asyncio control loops."""

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.motor import MotorSetObservation
from app.services.hardware_runtime import HardwareRuntime

logger = logging.getLogger(__name__)


class ObservationWriter:
    def __init__(self, sessions: Callable[[], Session], runtime: HardwareRuntime) -> None:
        self.sessions, self.runtime = sessions, runtime
        self.stopping = asyncio.Event()

    def recover(self) -> None:
        with self.sessions() as db:
            for row in db.scalars(select(MotorSetObservation).where(MotorSetObservation.status == "recording")):
                row.status = "interrupted"
                row.summary = {**row.summary, "reason": "Контроллер перезапущен. Сохранены кадры до последней записи."}
            db.commit()

    def flush(self, *, shutdown: bool = False) -> None:
        batch = self.runtime.observation_checkpoints(shutdown=shutdown)
        if not batch:
            return
        with self.sessions() as db:
            for item in batch:
                db.merge(MotorSetObservation(**item.payload()))
            db.commit()
        self.runtime.observations_saved([item.id for item in batch if item.status != "recording"])

    async def run(self) -> None:
        recovered = False
        while True:
            if not recovered:
                try:
                    await asyncio.to_thread(self.recover)
                    recovered = True
                except Exception:
                    logger.exception("Could not recover motor exercise observations")
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=3)
            except TimeoutError:
                pass
            stopping = self.stopping.is_set()
            try:
                if recovered or stopping:
                    await asyncio.to_thread(self.flush, shutdown=stopping)
            except Exception:
                logger.exception("Could not persist motor exercise observations")
            if stopping:
                return
