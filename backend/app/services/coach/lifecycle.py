"""Bounded, process-local AFTER-COMMIT observations. No I/O or external subscribers."""

from collections import deque
from collections.abc import Callable

from app.core.config import get_settings
from app.schemas.coach import CoachRuntimeNotice


class RuntimeObservationBuffer:
    def __init__(self, enabled: Callable[[], bool], capacity: int = 256):
        if not 1 <= capacity <= 1024:
            raise ValueError("Invalid observation capacity")
        self.enabled = enabled
        self.notices: deque[CoachRuntimeNotice] = deque(maxlen=capacity)
        self.failures = 0

    def record(self, **fields: object) -> None:
        # Feature-off does not validate/store user results or perform any I/O.
        # Observer failure must never turn a successful commit into a failed save.
        try:
            if self.enabled():
                self.notices.append(CoachRuntimeNotice.model_validate(fields))
        except Exception:
            self.failures += 1

    def clear(self) -> None:
        self.notices.clear()


runtime_observations = RuntimeObservationBuffer(lambda: get_settings().coach_enabled)