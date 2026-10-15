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
    _trough: float | None = None
    events: list[RepEvent] = field(default_factory=list)

    def update(self, x_mm: float) -> RepEvent | None:
        if self._start is None or self._peak is None or self._trough is None:
            self._start = self._peak = self._trough = x_mm
            return None
        if self._direction >= 0 and x_mm > self._peak:
            self._peak = x_mm
            self._direction = 1
        elif self._direction == 1 and x_mm < self._peak - self.hysteresis_mm:
            # top reversal: the concentric part is done, the rep closes on the way down
            self._direction = -1
            self._trough = x_mm
        if self._direction == -1:
            self._trough = min(self._trough, x_mm)
            amplitude = self._peak - max(self._start, self._trough)
            full_mm = self.full_percent / 100 * self._range_mm
            # a bottom deeper than the next ones must not block counting: the lower bound is enough
            bottom = max(self._start, self.lower_mm) + self.hysteresis_mm
            if x_mm <= bottom or amplitude >= full_mm:
                self._start = self._peak = x_mm
                self._direction = 0
                return self._record(amplitude)
            if x_mm > self._trough + self.hysteresis_mm:
                if self._peak - self._trough < self.partial_percent / 100 * self._range_mm:
                    # a wobble or pause at the top, not a rep: keep climbing from the real bottom
                    self._peak = max(self._peak, x_mm)
                    self._direction = 1
                    return None
                # bottom reversal short of the start: the next rep began from the trough
                self._start, self._peak = self._trough, x_mm
                self._direction = 1
                return self._record(amplitude)
            return None
        if self._direction <= 0 and x_mm < self._start:
            self._start = self._peak = x_mm
        return None

    @property
    def _range_mm(self) -> float:
        return max(self.upper_mm - self.lower_mm, 1e-6)

    def _record(self, amplitude_mm: float) -> RepEvent | None:
        event = self._classify(amplitude_mm)
        if event:
            self.events.append(event)
        return event

    def _classify(self, amplitude_mm: float) -> RepEvent | None:
        share = 100 * amplitude_mm / self._range_mm
        if share >= self.full_percent:
            self.full += 1
            return "full"
        if share >= self.partial_percent:
            self.partial += 1
            return "partial"
        return None
