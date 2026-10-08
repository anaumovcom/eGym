"""Repetition counting: full/partial by range share with hysteresis (pure)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RepEvent = Literal["full", "partial"]


@dataclass
class RepCounter:
    lower_mm: float
    upper_mm: float
    full_percent: float = 85.0
    partial_percent: float = 40.0
    hysteresis_mm: float = 15.0
    full: int = 0
    partial: int = 0
    _direction: int = 0
    _start: float | None = None
    _peak: float | None = None
    events: list[RepEvent] = field(default_factory=list)

    def update(self, x_mm: float) -> RepEvent | None:
        if self._start is None:
            self._start = self._peak = x_mm
            return None
        assert self._peak is not None
        if self._direction >= 0 and x_mm > self._peak:
            self._peak = x_mm
            self._direction = 1
        elif self._direction == 1 and x_mm < self._peak - self.hysteresis_mm:
            # top reversal: the concentric part is done, evaluate on return to the bottom
            self._direction = -1
        if self._direction == -1 and x_mm <= self._start + self.hysteresis_mm:
            event = self._classify(self._peak - self._start)
            self._start = self._peak = x_mm
            self._direction = 0
            if event:
                self.events.append(event)
            return event
        if self._direction <= 0 and x_mm < self._start:
            self._start = self._peak = x_mm
        return None

    def _classify(self, amplitude_mm: float) -> RepEvent | None:
        share = 100 * amplitude_mm / max(self.upper_mm - self.lower_mm, 1e-6)
        if share >= self.full_percent:
            self.full += 1
            return "full"
        if share >= self.partial_percent:
            self.partial += 1
            return "partial"
        return None
