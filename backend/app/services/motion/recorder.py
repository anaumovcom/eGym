"""High-frequency telemetry ring buffer, incident black box and saved recordings."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

SAMPLE_FIELDS = (
    "t",
    "mode",
    "posL",
    "posR",
    "velL",
    "velR",
    "vel",
    "acc",
    "forceL",
    "forceR",
    "userForce",
    "loadTarget",
    "loadEffective",
    "syncDelta",
    "currentL",
    "currentR",
    "tempL",
    "tempR",
    "reps",
    "amplitude",
    "cmdL",
    "cmdR",
)


@dataclass
class Recording:
    id: int
    title: str
    comment: str
    created_at: str
    parameters: dict[str, Any]
    samples: list[list[Any]]
    events: list[dict[str, Any]]
    kind: str = "manual"

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "comment": self.comment,
            "createdAt": self.created_at,
            "kind": self.kind,
            "sampleCount": len(self.samples),
            "durationS": round((self.samples[-1][0] - self.samples[0][0]), 2) if len(self.samples) > 1 else 0.0,
        }

    def to_payload(self) -> dict[str, Any]:
        return {**self.to_summary(), "fields": list(SAMPLE_FIELDS), "parameters": self.parameters, "samples": self.samples, "events": self.events}


class TelemetryRecorder:
    def __init__(self, *, buffer_seconds: float = 60.0, tick_seconds: float = 0.02, max_recordings: int = 12) -> None:
        capacity = int(buffer_seconds / tick_seconds)
        self.buffer: deque[list[Any]] = deque(maxlen=capacity)
        self.recordings: list[Recording] = []
        self.incidents: list[Recording] = []
        self.max_recordings = max_recordings
        self._counter = 0
        self._manual_start_index: int | None = None
        self._manual_events_start = 0
        self._last_incident_time = -1e9

    def append(self, sample: list[Any]) -> None:
        self.buffer.append(sample)

    def recent(self, count: int) -> list[list[Any]]:
        if count >= len(self.buffer):
            return list(self.buffer)
        return list(self.buffer)[-count:]

    def start_manual(self, events_length: int) -> None:
        self._manual_start_index = len(self.buffer)
        self._manual_events_start = events_length

    @property
    def manual_active(self) -> bool:
        return self._manual_start_index is not None

    def stop_manual(self, title: str, comment: str, parameters: dict[str, Any], events: list[dict[str, Any]]) -> Recording:
        start = self._manual_start_index or 0
        samples = list(self.buffer)
        # the deque may have rotated: fall back to the whole buffer if the start index is stale
        selected = samples[start:] if start < len(samples) else samples
        recording = self._make(title, comment, parameters, selected, events[self._manual_events_start :], kind="manual")
        self.recordings.append(recording)
        self.recordings = self.recordings[-self.max_recordings :]
        self._manual_start_index = None
        return recording

    def save_snapshot(self, title: str, comment: str, parameters: dict[str, Any], events: list[dict[str, Any]], *, seconds: float, tick: float, kind: str = "manual") -> Recording:
        samples = self.recent(int(seconds / tick))
        recording = self._make(title, comment, parameters, samples, events[-60:], kind=kind)
        self.recordings.append(recording)
        self.recordings = self.recordings[-self.max_recordings :]
        return recording

    def capture_incident(self, reason: str, parameters: dict[str, Any], events: list[dict[str, Any]], *, now: float) -> Recording | None:
        if now - self._last_incident_time < 2.0:
            return None
        self._last_incident_time = now
        recording = self._make(f"Инцидент: {reason}", reason, parameters, list(self.buffer), events[-80:], kind="incident")
        self.incidents.append(recording)
        self.incidents = self.incidents[-self.max_recordings :]
        return recording

    def get(self, recording_id: int) -> Recording | None:
        for item in [*self.recordings, *self.incidents]:
            if item.id == recording_id:
                return item
        return None

    def delete(self, recording_id: int) -> bool:
        before = len(self.recordings) + len(self.incidents)
        self.recordings = [item for item in self.recordings if item.id != recording_id]
        self.incidents = [item for item in self.incidents if item.id != recording_id]
        return before != len(self.recordings) + len(self.incidents)

    def _make(self, title: str, comment: str, parameters: dict[str, Any], samples: list[list[Any]], events: list[dict[str, Any]], *, kind: str) -> Recording:
        self._counter += 1
        return Recording(
            id=self._counter,
            title=title,
            comment=comment,
            created_at=datetime.now(UTC).isoformat(),
            parameters=dict(parameters),
            samples=[list(sample) for sample in samples],
            events=list(events),
            kind=kind,
        )
