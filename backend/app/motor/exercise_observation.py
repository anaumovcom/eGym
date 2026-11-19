"""Passive set recorder. Summaries see every working frame, traces have a bounded size."""

from __future__ import annotations

import math
from copy import copy
from datetime import UTC, datetime
from uuid import uuid4

from app.motor.calibration.runner import Frame
from app.motor.profile import SafetyEnvelope
from app.motor.supervisor.pair import PairMonitor
from app.motor.units import SIDES, G
from app.motor.workout import SetPlan, WorkoutController

TRACE_LIMIT = 480
ENCODER_WINDOW_S = 0.1
TRACE_COLUMNS = ("t", "xL", "xR", "vL", "vR", "fL", "fR", "loadKg", "targetKg", "rawL", "rawR", "skewMm", "segment")


class ExerciseObservation:
    def __init__(self, plan: SetPlan, slug: str | None, source: str, version: int, start: float, load_scale: float, envelope: SafetyEnvelope) -> None:
        self.id = uuid4().hex
        self.started_at = datetime.now(UTC)
        self.source, self.version, self.slug = source, version, slug
        self.start = start
        self.kg_per_n = 2 / (G * load_scale)
        self.context = {
            "setNumber": plan.target_set, "targetReps": plan.target_reps, "mode": plan.load_mode,
            "loadDirection": plan.load_direction, "initialKg": round(plan.load_n * self.kg_per_n, 2),
            "lowerMm": plan.lower_mm, "upperMm": plan.upper_mm, "fixedMm": plan.fixed_mm,
            "startPoint": plan.start_point,
            "skewWarningMm": envelope.sync_warning_mm, "ascentLimitMmS": envelope.max_speed_mm_s,
            "descentLimitMmS": envelope.max_descent_mm_s,
        }
        self.status, self.reason = "recording", None
        self.valid = self.invalid = self.segment = 0
        self.work_s = self.max_gap_s = self.elapsed = 0.0
        self.last_work: float | None = None
        self.height_min: float | None = None
        self.height_max: float | None = None
        self.max_skew = self.skew_height = 0.0
        self.pair = PairMonitor()
        self.has_skew = False
        self.fixed_error = [0.0, 0.0]
        self.approach: dict | None = None
        self._approach_start = start
        self.up = [0.0, 0.0]
        self.down = [0.0, 0.0]
        self.encoder_anchor: tuple[float, float, float] | None = None
        self.encoder_windows = 0
        self.encoder_up = [0.0, 0.0]
        self.encoder_down = [0.0, 0.0]
        self.full = self.partial = 0
        self.rows: list[tuple] = []
        self.last_row: tuple | None = None
        self.interval = 0.1

    def same_preparation(self, other: ExerciseObservation) -> bool:
        keys = ("workoutRunId", "exerciseId", "setNumber")
        return bool(self.valid == 0 and self.approach is None and self.slug == other.slug and self.context.get("workoutRunId")
                    and self.context.get("exerciseId") and all(self.context.get(k) == other.context.get(k) for k in keys))

    def sample_approach(self, frame: Frame, workout: WorkoutController, stale_s: float) -> None:
        if self.approach and self.approach["status"] != "moving":
            return
        if not workout.approaching_start:
            if self.approach:
                self.approach["status"] = "hold" if workout.mode in ("start_hold", "fixed_hold", "training") else "interrupted"
            return
        if any(s not in frame.samples or not frame.samples[s].ok or not 0 <= frame.t - frame.samples[s].t <= stale_s or
               not (math.isfinite(frame.x(s)) and math.isfinite(frame.v(s))) for s in SIDES):
            return
        plan = workout.plan
        if plan is None:
            return
        target = min(workout.envelope.soft_max_mm, max(workout.envelope.soft_min_mm, plan.start_mm))
        if self.approach is None:
            self._approach_start = frame.t
            self.approach = {"targetMm": target, "fromMm": round(frame.x_mean, 1), "peakMmS": 0.0, "status": "moving"}
        self.approach.update(seconds=round(frame.t - self._approach_start, 3), peakMmS=round(max(self.approach["peakMmS"], frame.max_abs_speed), 2),
                             errorsMm=[round(frame.x(s) - target, 2) for s in SIDES])

    def sample(self, frame: Frame, workout: WorkoutController, stale_s: float) -> None:
        self.elapsed = max(0.0, frame.t - self.start)
        if not workout.observing_work:
            self.last_work = None
            return
        if self.last_work is None:
            self.pair = PairMonitor()
        if self.pair.check(frame.samples, frame.t, stale_s, None):
            self.invalid += 1
            self.last_work = None
            return
        gap = frame.t - self.last_work if self.last_work is not None else None
        if gap is None or not 0 < gap <= stale_s:
            self.segment += 1
            self.encoder_anchor = (frame.t, frame.x("left"), frame.x("right"))
        else:
            self.work_s += gap
        if gap is not None:
            self.max_gap_s = max(self.max_gap_s, gap)
        self.last_work = frame.t
        self.valid += 1
        sides = [frame.samples[s] for s in SIDES]
        x, delta = frame.x_mean, self.pair.delta_mm
        self.height_min = x if self.height_min is None else min(x, self.height_min)
        self.height_max = x if self.height_max is None else max(x, self.height_max)
        if delta is not None and (not self.has_skew or abs(delta) > self.max_skew):
            self.max_skew, self.skew_height, self.has_skew = abs(delta), x, True
        for i, side in enumerate(sides):
            self.up[i] = max(self.up[i], side.speed_mm_s)
            self.down[i] = max(self.down[i], -side.speed_mm_s)
            if self.context["fixedMm"] is not None:
                self.fixed_error[i] = max(self.fixed_error[i], abs(side.position_mm - self.context["fixedMm"]))
        anchor = self.encoder_anchor
        if anchor is not None and frame.t - anchor[0] >= ENCODER_WINDOW_S:
            for i, side in enumerate(sides):
                speed = (side.position_mm - anchor[i + 1]) / (frame.t - anchor[0])
                self.encoder_up[i] = max(self.encoder_up[i], speed)
                self.encoder_down[i] = max(self.encoder_down[i], -speed)
            self.encoder_windows += 1
            self.encoder_anchor = (frame.t, frame.x("left"), frame.x("right"))
        left, right = sides
        self.last_row = (round(self.elapsed, 3), round(left.position_mm, 2), round(right.position_mm, 2),
                         round(left.speed_mm_s, 2), round(right.speed_mm_s, 2),
                         round(left.motor_force_n, 2), round(right.motor_force_n, 2),
                         round(workout.load_n * self.kg_per_n, 2), round(workout.target_load_n * self.kg_per_n, 2),
                         left.command_raw, right.command_raw, round(delta, 2) if delta is not None else None, self.segment)
        if not self.rows or self.elapsed - self.rows[-1][0] >= self.interval or self.rows[-1][-1] != self.segment:
            if len(self.rows) >= TRACE_LIMIT:
                self.rows = self.rows[::2]
                self.interval *= 2
            self.rows.append(self.last_row)

    def finish(self, status: str, reason: str | None, now: float) -> None:
        self.status, self.reason, self.elapsed = status, reason, max(0, now - self.start)
        if self.approach and self.approach["status"] == "moving":
            self.approach["status"] = "interrupted"

    def payload(self) -> dict:
        rows = self.rows.copy()
        if self.last_row is not None and (not rows or rows[-1] != self.last_row):
            rows.append(self.last_row)
        return {
            "id": self.id, "started_at": self.started_at, "source": self.source, "profile_version": self.version,
            "exercise_slug": self.slug, "status": self.status,
            "summary": {**self.context, "reason": self.reason, "elapsedS": round(self.elapsed, 2),
                        "workS": round(self.work_s, 2), "validFrames": self.valid, "invalidFrames": self.invalid,
                        "segments": self.segment, "maxGapMs": round(1000 * self.max_gap_s, 1),
                        "fullReps": self.full, "partialReps": self.partial,
                        "minHeightMm": self.height_min, "maxHeightMm": self.height_max,
                        "maxSkewMm": self.max_skew if self.has_skew else None, "skewHeightMm": self.skew_height if self.has_skew else None,
                        "approach": self.approach, "fixedPeakErrorMm": self.fixed_error.copy() if self.valid and self.context["fixedMm"] is not None else None,
                        "upMmS": self.up.copy() if self.valid else None, "downMmS": self.down.copy() if self.valid else None,
                        "encoderWindowS": ENCODER_WINDOW_S, "encoderWindows": self.encoder_windows,
                        "encoderUpMmS": self.encoder_up.copy() if self.encoder_windows else None,
                        "encoderDownMmS": self.encoder_down.copy() if self.encoder_windows else None},
            "trace": {key: [row[i] for row in rows] for i, key in enumerate(TRACE_COLUMNS)},
        }

    def snapshot(self) -> ExerciseObservation:
        snapshot = copy(self)
        snapshot.rows = self.rows.copy()
        snapshot.up, snapshot.down = self.up.copy(), self.down.copy()
        snapshot.fixed_error = self.fixed_error.copy()
        snapshot.approach = self.approach.copy() if self.approach else None
        snapshot.encoder_up, snapshot.encoder_down = self.encoder_up.copy(), self.encoder_down.copy()
        return snapshot
