"""Exercise control on the drives, stepped by the hardware runtime tick.

* force modes by ``MotorCore`` (free-weight law with the calibrated profile): weightless, hold, training, fixed hold;
* scripted moves by the calibration motion primitives (fast transit, landing, jog) through a ``CalibrationRunner``:
  to the start point of a set, back to the stops after a set, jog while held.

A set: move to the start point → hold until the user takes the bar (force or a shift; from the upper point only
down) → the load ramps in →
training (reps counted over the user's range) → ``complete_set``: the load ramps out, the bar floats weightless
where it is for the rest (the next set moves it to its start point); a rest left alone ``REST_PARK_S`` parks it.
A set never pauses by itself: the core's release detection (F11) is off in training (a released bar is held by the
range guard at the lower point); only the user's pause and the runtime latches (STOP, faults) end training.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from dataclasses import dataclass, replace
from typing import Any, Literal

from app.motor.calibration.procedures.motion import Balance, _governed, hold_still, land, travel
from app.motor.calibration.runner import CalibrationRunner, Command, Frame, ProcedureEnvelope
from app.motor.core import CoreOutput, MotorCore
from app.motor.drive.protocol import TorqueDrive
from app.motor.force.load_models import LoadMode, LoadSetpoint
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, Tunables
from app.motor.supervisor.modes import Mode
from app.motor.supervisor.reps import RepCounter
from app.motor.units import SIDES, G, Side, clamp

WorkoutMode = Literal["idle", "parked", "moving", "weightless", "start_hold", "training", "paused", "fixed_hold"]
Gen = Generator[Command, Frame, Any]

logger = logging.getLogger(__name__)

ABORT_RAW = 100  # the core's overspeed "zero" output: no brake, 0 would drop the bar (R5)
JOG_SPEED_MM_S = 40.0
JOG_TIMEOUT_S = 0.6  # no keepalive (every 0.2 s) this long → the jog stops
JOG_LIMIT_MARGIN_MM = 5.0
GRIP_FORCE_N = 40.0  # both sides: the user pushes or pulls the held bar
GRIP_MOVE_MM = 8.0  # …or shifts it this far from the hold point
GRIP_S = 0.2
LIFTED_GRIP_MOVE_MM = 40.0  # the bar pushed above the upper start point: taken down past the point this far
STILL_MM_S = 2.0
CAPTURE_STILL_S = 0.3
START_TOLERANCE_MM = 8.0  # closer to the start point: no move
ON_STOPS_MM = 15.0
DEFAULT_CUSHION_MM = 120.0  # F10 not measured: still brake fast motion near the ends of the travel
MOVE_MAX_S = 120.0
MOVE_MARGIN_MM = 60.0
MOVE_START_MM_S = 25.0  # a scripted move starts from a (nearly) still bar…
SETTLE_MAX_S = 3.0  # …caught by the hold first, at most this long
UNLOADED_N = 1.0
FIXED_PRESS_SHARE = 0.5  # fixed position: a rep = the user force rises above this share of the load…
FIXED_RELEASE_SHARE = 0.25  # …and falls below this one
FIXED_MIN_FORCE_N = 100.0
FIXED_DEBOUNCE_S = 0.3
REST_PARK_S = 900.0  # a weightless rest after a set nobody came back to: the bar goes to the stops
REST_CATCH_MM_S = 5.0  # the rest starts weightless from a bar (nearly) at rest
TAKEN_MAX_MM_S = 300.0  # the move to the start aborted by its envelope at a speed below this, in the range: the user took the bar


class WorkoutError(PermissionError):
    """A command that cannot run now; the message is shown to the user."""


@dataclass(frozen=True)
class SetPlan:
    lower_mm: float
    upper_mm: float
    load_n: float  # per side
    load_mode: LoadMode = "constant"
    start_point: Literal["lower", "upper"] = "lower"
    target_reps: int = 10
    target_set: int = 1
    fixed_mm: float | None = None  # fixed position: hold here, reps by the user force

    @property
    def start_mm(self) -> float:
        if self.fixed_mm is not None:
            return self.fixed_mm
        return self.upper_mm if self.start_point == "upper" else self.lower_mm


def load_mode(label: str | None) -> LoadMode:
    """The builder's load mode label (Russian or English) → the core load model."""

    text = (label or "").lower()
    if "эксцентр" in text or "eccentric" in text:
        return "eccentric"
    if "помощ" in text or "assist" in text:
        return "assist_up"
    return "constant"


def per_side_n(weight_kg: float) -> float:
    """The bar weight the user wants to feel, split between the two sides (the bar itself is compensated)."""

    return max(0.0, weight_kg) * G / 2


def _with_cushions(profile: MachineProfile) -> MachineProfile:
    measured = {key: getattr(profile, key) for key in ("cushion_bottom_mm", "cushion_top_mm")}
    defaults = {key: Measured(DEFAULT_CUSHION_MM, None, "default") for key, item in measured.items() if item.value is None}
    return replace(profile, **defaults) if defaults else profile


# ---------------------------------------------------------------- scripted moves
def _goto(balance: Balance, frame0: Frame, target_mm: float, note: str) -> Gen:
    frame = yield Command(balance.mid(frame0), note=note)
    yield from travel(balance, frame, target_mm, note=note)
    return {}


def _park(balance: Balance, frame0: Frame) -> Gen:
    frame = yield Command(balance.mid(frame0), note="опускание на упоры")
    yield from land(balance, frame)
    return {}


def _jog(balance: Balance, frame0: Frame, direction: int, active: Callable[[Frame], bool], limit_mm: float) -> Gen:
    note = "гриф вверх" if direction > 0 else "гриф вниз"
    frame = yield Command(balance.mid(frame0), note=note)

    def done(f: Frame, _extra: dict[Side, float]) -> bool:
        return not active(f) or direction * (f.x_mean - limit_mm) >= 0

    if direction * (limit_mm - frame.x_mean) > 0:
        frame = yield from _governed(balance, frame, direction, JOG_SPEED_MM_S, done, note=note, progress=lambda _f: None, drive_limit=direction > 0)
    yield from hold_still(balance, frame, note="остановка")
    return {}


# ---------------------------------------------------------------- controller
class WorkoutController:
    def __init__(self, drives: dict[Side, TorqueDrive], profile: MachineProfile, tunables: Tunables, envelope: SafetyEnvelope) -> None:
        self.drives = drives
        self.mode: WorkoutMode = "idle"
        self.reason: str | None = None
        self.core: MotorCore | None = None
        self.runner: CalibrationRunner | None = None
        self.plan: SetPlan | None = None
        self.reps: RepCounter | None = None
        self.fixed_reps = 0
        self.frame: Frame | None = None
        self.output: CoreOutput | None = None
        self._after: Callable[[], None] | None = None
        self._unloaded: Callable[[], None] | None = None
        self._jog: dict[str, Any] | None = None
        self._pending: tuple[Callable[[Frame], Gen], float] | None = None
        self._last_jog_id: str | None = None
        self._load_n = 0.0
        self._grip_since: float | None = None
        self._lifted = False
        self._still_since: float | None = None
        self._fixed_pressed = False
        self._fixed_flip_since: float | None = None
        self._t: float | None = None
        self._rest_since: float | None = None
        self._rest_catch = False
        self._start_arrived: Callable[[], None] | None = None
        self.configure(profile, tunables, envelope)

    # ------------------------------------------------------------ state
    def configure(self, profile: MachineProfile, tunables: Tunables, envelope: SafetyEnvelope) -> None:
        if self.active:
            raise WorkoutError("Идёт упражнение — профиль нельзя менять")
        self.profile = _with_cushions(profile)
        self.tunables = tunables
        self.envelope = envelope
        self.balance = Balance.from_profile(profile)

    @property
    def active(self) -> bool:
        return self.mode not in ("idle", "parked")

    @property
    def still_s(self) -> float:
        return 0.0 if self._still_since is None or self.frame is None else self.frame.t - self._still_since

    @property
    def load_n(self) -> float:
        return self._load_n

    @property
    def target_load_n(self) -> float:
        return self.plan.load_n if self.plan is not None else 0.0

    def user_force_n(self) -> float:
        if self.output is None or not self.output.user_force:
            return 0.0
        return sum(item.value_n for item in self.output.user_force.values())

    # ------------------------------------------------------------ commands
    def enter_weightless(self) -> None:
        self._require_frame()
        self._unload_then(lambda: self._to_core(Mode.WEIGHTLESS, "weightless"))

    def hold(self) -> None:
        self._require_frame()
        self._unload_then(lambda: self._to_core(Mode.HOLD, "paused"))

    def capture_point(self) -> float:
        frame = self._require_frame()
        if self.mode not in ("weightless", "paused", "start_hold", "fixed_hold"):
            raise WorkoutError("Точку можно зафиксировать в невесомости или при удержании грифа")
        if self.still_s < CAPTURE_STILL_S:
            raise WorkoutError("Гриф ещё движется: остановите его и повторите")
        return round(frame.x_mean, 1)

    def jog_start(self, jog_id: str, direction: int) -> None:
        frame = self._require_frame()
        if self.mode == "training":
            raise WorkoutError("Во время подхода гриф двигается только руками: поставьте подход на паузу")
        if self._moving and self._jog is None:
            raise WorkoutError("Гриф уже перемещается")
        resume: WorkoutMode = "weightless" if self.mode == "weightless" else "paused"
        self._cancel_move()
        self._jog = {"id": jog_id, "until": frame.t + JOG_TIMEOUT_S}
        self._last_jog_id = jog_id
        jog = self._jog
        limit = self.envelope.soft_max_mm - JOG_LIMIT_MARGIN_MM if direction > 0 else self.envelope.soft_min_mm + JOG_LIMIT_MARGIN_MM

        def active(f: Frame) -> bool:
            return self._jog is jog and f.t <= jog["until"]

        self._move(lambda f: _jog(self.balance, f, direction, active, limit), after=lambda: self._jog_done(resume))

    def jog_keepalive(self, jog_id: str) -> None:
        if self._jog is not None and self._jog["id"] == jog_id and self.frame is not None:
            self._jog["until"] = self.frame.t + JOG_TIMEOUT_S
        elif jog_id != self._last_jog_id:
            raise WorkoutError("Перемещение грифа уже остановлено")
        # the jog of this button ended by itself (soft limit): the screen still holds the button — nothing to do

    def jog_stop(self, jog_id: str | None) -> None:
        if self._jog is not None and (jog_id is None or self._jog["id"] == jog_id):
            self._jog["until"] = 0.0

    def start_set(self, plan: SetPlan) -> None:
        self._require_frame()
        if plan.fixed_mm is None and not plan.lower_mm < plan.upper_mm:
            raise WorkoutError("Нижняя точка амплитуды должна быть ниже верхней: повторите настройку грифа")
        start = clamp(plan.start_mm, self.envelope.soft_min_mm, self.envelope.soft_max_mm)
        self.plan = plan
        self.reps = RepCounter(plan.lower_mm, plan.upper_mm, self.tunables.reps_full_percent, self.tunables.reps_partial_percent, self.tunables.reps_hysteresis_mm)
        self.fixed_reps = 0
        self.reason = None

        def arrived() -> None:
            self._to_core(Mode.HOLD, "paused" if plan.fixed_mm is not None else "start_hold")
            frame = self._require_frame()
            if abs(frame.v_mean) <= MOVE_START_MM_S and self.core is not None:
                self.core.hold_at({side: frame.x(side) for side in SIDES})
            if plan.fixed_mm is not None:
                self._begin_fixed()
            else:
                self._grip_since, self._lifted = None, False

        self._start_arrived = arrived

        def go() -> None:
            frame = self._require_frame()
            if abs(frame.x_mean - start) <= START_TOLERANCE_MM:
                arrived()
            else:
                self._move(lambda f: _goto(self.balance, f, start, f"к стартовой точке {start:.0f} мм"), after=arrived)

        self._cancel_move()
        self._unload_then(go)

    def set_load(self, weight_kg: float) -> None:
        if self.plan is None:
            raise WorkoutError("Подход не начат")
        self.plan = replace(self.plan, load_n=per_side_n(weight_kg))

    def pause(self) -> None:
        self._require_frame()
        if self._moving and self._jog is None:
            self._cancel_move()
            self._to_core(Mode.HOLD, "paused")
            return
        self._unload_then(lambda: self._to_core(Mode.HOLD, "paused"))

    def resume(self, weight_kg: float | None = None) -> None:
        self._require_frame()
        if self.plan is None:
            raise WorkoutError("Подход не начат: запустите упражнение заново")
        if self.mode not in ("paused", "start_hold", "fixed_hold", "weightless"):
            raise WorkoutError("Подход уже идёт")
        if weight_kg is not None and weight_kg > 0:
            self.set_load(weight_kg)
        self.reason = None
        if self.plan.fixed_mm is not None:
            self._to_core(Mode.HOLD, "paused")
            self._begin_fixed()
        else:
            self._to_core(Mode.HOLD, "start_hold")
            self._grip_since, self._lifted = None, False

    def complete_set(self) -> None:
        self._require_frame()
        if self._moving:
            self._cancel_move()
            self._to_core(Mode.HOLD, "paused")
        self._unload_then(self._rest)

    def _rest(self) -> None:
        """Between sets / exercises: weightless at the current height (the user may move the bar by hand).

        A bar still moving (the set ended mid-rep) is first caught by the hold, so it floats where it stopped.
        """

        frame = self._require_frame()
        self._rest_since = frame.t
        if abs(frame.v_mean) > REST_CATCH_MM_S:
            self._to_core(Mode.HOLD, "paused")
            self._rest_catch = True
        else:
            self._to_core(Mode.WEIGHTLESS, "weightless")

    def park(self) -> None:
        self._require_frame()
        self._cancel_move()
        self._unload_then(self._park)

    def abort(self, reason: str) -> None:
        """STOP / fault / overspeed: drop everything; the runtime writes the safe output."""

        if self.runner is not None:
            self.runner.cancel(reason, support=False)
            self.runner = None
        self._pending = None
        if self.core is not None:
            self._restore_speed_limits()
        self.core = None
        self._after = self._unloaded = None
        self._jog = None
        self._load_n = 0.0
        self._rest_since, self._rest_catch = None, False
        if self.active:
            self.mode = "idle"
            self.reason = reason

    # ------------------------------------------------------------ tick
    def step(self, frame: Frame) -> str | None:
        """One tick; returns a fault reason (the runtime latches it) or ``None``. Writes the drives while active."""

        dt = 0.0 if self._t is None else max(frame.t - self._t, 0.0)
        self._t = frame.t
        self.frame = frame
        moving = abs(frame.v_mean) > STILL_MM_S
        self._still_since = None if moving else (self._still_since if self._still_since is not None else frame.t)
        if not self.active:
            return None
        if self.core is not None:
            self.output = self.core.step(frame.samples, frame.t)
            if self.output.mode in (Mode.FAULT, Mode.ESTOP):
                reason = self.core.supervisor.reason or "Ошибка управления приводами"
                self.abort(reason)
                return reason
        if self.runner is not None:
            result = self.runner.feed(frame)
            if result is None:
                return None
            last = self.runner.command.forces_n
            self.runner = None
            if result.status != "done" and not (result.status == "aborted" and self._taken_at_start(frame)):
                reason = f"Перемещение грифа прервано: {result.reason}"
                self.abort(reason)
                return reason
            if result.status != "done":
                # the user took the bar at the start point before the move settled (bench press: pressed off the chest):
                # the hold catches the moving bar and the set starts on the grip, as after an arrival
                logger.info("Move to the start handed over to the hold: %s", result.reason)
            if self.core is not None:
                # the move put PA_056 back to the connect value: training needs the envelope limit
                for side in SIDES:
                    self.drives[side].limit_speed_rpm(self.envelope.speed_limit_rpm)
            if self.core is not None and last is not None:
                self.core.previous = dict(last)  # the core continues from the force the move left in the drives
            after, self._after = self._after, None
            if after is not None:
                after()
            return None  # the drives keep the move's last command for this frame
        assert self.core is not None and self.output is not None
        if self._rest_catch and self.mode == "paused" and self._rest_since is not None:
            if abs(frame.v_mean) <= REST_CATCH_MM_S or frame.t - self._rest_since >= SETTLE_MAX_S:
                self._to_core(Mode.WEIGHTLESS, "weightless")
        if self.mode != "weightless" and not self._rest_catch:
            self._rest_since = None
        elif self._rest_since is not None and frame.t - self._rest_since >= REST_PARK_S and self._pending is None:
            self._rest_since = None
            self._park()
            return None  # a landing writes from the next frame; parked on the stops: the runtime writes support
        if self._pending is not None:
            factory, deadline = self._pending
            if abs(frame.v_mean) <= MOVE_START_MM_S or frame.t >= deadline:
                self._launch(factory, frame)
                return None  # the move writes from the next frame; the drives keep the hold output
            return self._write(self.output)
        self._advance(frame, dt)
        return self._write(self.output)

    def _advance(self, frame: Frame, dt: float) -> None:
        core = self.core
        assert core is not None
        if self.mode == "training" and core.supervisor.mode == Mode.HOLD:
            # F11: the user let go — the core holds the bar (a pending pause / park goes on from the hold)
            self.mode, self.reason, self._load_n = "paused", "Гриф отпущен — подход на паузе", 0.0
            then, self._unloaded = self._unloaded, None
            if then is not None:
                self.reason = None
                then()
            return
        if self.mode == "start_hold":
            self._watch_grip(frame)
        elif self.mode == "training":
            self._ramp_load(dt)
            if self.reps is not None and self.plan is not None:
                # a set from the upper point (squat, bench press) is the mirror of one from the lower point: a rep is
                # counted at the far turn either way
                x = frame.x_mean
                if self.plan.start_point == "upper":
                    x = self.plan.lower_mm + self.plan.upper_mm - x
                self.reps.update(x)
        elif self.mode == "fixed_hold":
            self._count_fixed()

    def _ramp_load(self, dt: float) -> None:
        core = self.core
        assert core is not None and self.plan is not None
        target = 0.0 if self._unloaded is not None else self.plan.load_n
        step = self.tunables.load_ramp_n_per_s * dt
        load = self._load_n + clamp(target - self._load_n, -step, step)
        if load != self._load_n or core.load.load_n != load:
            self._set_core_load(load)
        if self._unloaded is not None and self._load_n <= UNLOADED_N:
            then, self._unloaded = self._unloaded, None
            core.command("pause")
            then()

    def _set_core_load(self, load_n: float) -> None:
        core = self.core
        assert core is not None and self.plan is not None
        core.set_load(LoadSetpoint(mode=self.plan.load_mode, load_n=load_n, alpha=self.tunables.assist_alpha, beta=self.tunables.eccentric_beta, lower_mm=self.plan.lower_mm, upper_mm=self.plan.upper_mm, range_guard=True))
        self._load_n = core.load.load_n  # capped by what the drives can make

    def _watch_grip(self, frame: Frame) -> None:
        core = self.core
        assert core is not None
        assert self.plan is not None
        targets = [core.hold_target[side] for side in SIDES]
        offsets = [frame.x(side) - target for side, target in zip(SIDES, targets, strict=True) if target is not None]
        if self.plan.start_point == "upper":
            # the bar waits at the upper point until the user takes it down: a push up or a lift does not start the set,
            # nor does the hold's rebound when the lifted bar is let go (it overshoots below the point for a moment)
            if max(offsets, default=0.0) > GRIP_MOVE_MM:
                self._lifted = True
            elif self._lifted and abs(frame.v_mean) <= STILL_MM_S:
                # back from the lift: the hold stays where the bar came to rest (friction may stop it short of the point)
                self._lifted = False
                core.hold_at({side: frame.x(side) for side in SIDES})
                offsets = [0.0]
            shift = max((-offset for offset in offsets), default=0.0)
            if self._lifted:
                gripped = shift > LIFTED_GRIP_MOVE_MM
            else:
                gripped = self.user_force_n() < -GRIP_FORCE_N or shift > GRIP_MOVE_MM
        else:
            shift = max((abs(offset) for offset in offsets), default=0.0)
            gripped = abs(self.user_force_n()) > GRIP_FORCE_N or shift > GRIP_MOVE_MM
        self._grip_since = (self._grip_since if self._grip_since is not None else frame.t) if gripped else None
        if self._grip_since is not None and frame.t - self._grip_since >= GRIP_S:
            # the hold already resists the user's push: the load starts from it, no jump on the handover
            pushed = clamp(self.user_force_n() / len(SIDES), 0.0, self.plan.load_n)
            core.command("train")
            self.mode = "training"
            self.reason = None
            self._load_n = 0.0
            if pushed > UNLOADED_N:
                self._set_core_load(pushed)

    def _begin_fixed(self) -> None:
        core = self.core
        assert core is not None
        core.command("fixed")
        self.mode = "fixed_hold"
        self._fixed_pressed = False
        self._fixed_flip_since = None

    def _count_fixed(self) -> None:
        """A rep = a press held ≥ FIXED_DEBOUNCE_S, then a release held as long (the estimate rings while the bar settles)."""

        target = max(2 * self.target_load_n, FIXED_MIN_FORCE_N)
        force = abs(self.user_force_n())
        flip = force <= FIXED_RELEASE_SHARE * target if self._fixed_pressed else force >= FIXED_PRESS_SHARE * target
        t = self.frame.t if self.frame is not None else 0.0
        if not flip:
            self._fixed_flip_since = None
            return
        if self._fixed_flip_since is None:
            self._fixed_flip_since = t
        if t - self._fixed_flip_since < FIXED_DEBOUNCE_S:
            return
        self._fixed_flip_since = None
        self._fixed_pressed = not self._fixed_pressed
        if not self._fixed_pressed:
            self.fixed_reps += 1

    # ------------------------------------------------------------ plumbing
    def _require_frame(self) -> Frame:
        if self.frame is None:
            raise WorkoutError("Нет данных о положении грифа")
        return self.frame

    def _ensure_core(self) -> MotorCore:
        if self.core is None:
            self.core = MotorCore(self.profile, self.tunables, self.envelope)
            # no automatic pause in a set (F11 off): a released bar sinks to the set's lower point and the range guard
            # holds it there; the set goes on (reps counted) when the user lifts again
            self.core.release_enabled = False
            self.core.command("ready")
            for side in SIDES:
                error = self.drives[side].limit_speed_rpm(self.envelope.speed_limit_rpm)  # the user may move fast; PA_056 ≤ envelope
                if error:
                    raise WorkoutError(f"Предел скорости привода не записан: {error}")
        return self.core

    def _to_core(self, target: Mode, mode: WorkoutMode) -> None:
        """Walk the supervisor to ``target`` through its transitions (down to IDLE, then up)."""

        core = self._ensure_core()
        down = {Mode.TRAINING: "pause", Mode.FIXED: "pause", Mode.ISOMETRIC: "pause", Mode.JOG: "jog_end", Mode.HOLD: "idle", Mode.WEIGHTLESS: "idle", Mode.SUPPORT: "ready"}
        for _ in range(4):
            if core.supervisor.mode in (target, Mode.IDLE):
                break
            if core.supervisor.mode not in down:
                raise WorkoutError(f"Управление в состоянии «{core.supervisor.mode.value}»: сбросьте ошибку")
            core.command(down[core.supervisor.mode])
        if core.supervisor.mode != target:
            core.command("hold" if target in (Mode.HOLD, Mode.TRAINING, Mode.FIXED) else target.value)
        if target == Mode.TRAINING and core.supervisor.mode != Mode.TRAINING:
            core.command("train")
        self.mode = mode
        self._rest_catch = False
        self._load_n = 0.0 if target != Mode.TRAINING else self._load_n

    def _unload_then(self, then: Callable[[], None]) -> None:
        """In training the load ramps out first (a held weight never vanishes at once), then ``then``."""

        if self.mode == "training" and self.core is not None and self._load_n > UNLOADED_N:
            self._unloaded = then
            return
        if self.mode == "training" and self.core is not None:
            self.core.command("pause")
        self._unloaded = None
        then()

    def _move(self, factory: Callable[[Frame], Gen], *, after: Callable[[], None]) -> None:
        """A scripted move (``factory(frame)``); a bar still in motion is first caught by the hold and stopped."""

        frame = self._require_frame()
        self._after = after
        if abs(frame.v_mean) > MOVE_START_MM_S:
            self._to_core(Mode.HOLD, "moving")
            self._pending = (factory, frame.t + SETTLE_MAX_S)
            return
        self._launch(factory, frame)

    def _launch(self, factory: Callable[[Frame], Gen], frame: Frame) -> None:
        self._pending = None
        core = self._ensure_core()
        if core.supervisor.mode not in (Mode.IDLE,):
            self._to_core(Mode.IDLE, self.mode)
        self.mode = "moving"
        # the bar may start above the soft limit (pushed up by hand in weightless, where nothing stops it):
        # every move goes to a point at or below the limit, so the envelope covers the start height
        top = max([self.envelope.soft_max_mm, *(frame.x(side) for side in SIDES)])
        envelope = ProcedureEnvelope(min_x_mm=-5.0, max_x_mm=top + MOVE_MARGIN_MM, max_force_n=self.envelope.max_force_n_per_side)
        self.runner = CalibrationRunner(self.drives, envelope=envelope)
        result = self.runner.begin(factory(frame), max_s=MOVE_MAX_S, envelope=envelope)
        if result is not None:  # ended at once
            self.runner = None
            after_, self._after = self._after, None
            if after_ is not None:
                after_()

    def _taken_at_start(self, frame: Frame) -> bool:
        """The move to the set's start ended by its envelope with the bar in the set's range, moving at a sane speed."""

        plan = self.plan
        if plan is None or plan.fixed_mm is not None or self._after is None or self._after is not self._start_arrived:
            return False
        lo = max(plan.lower_mm - MOVE_MARGIN_MM, self.envelope.soft_min_mm)
        hi = min(plan.upper_mm + MOVE_MARGIN_MM, self.envelope.soft_max_mm)
        return all(
            side in frame.samples and frame.samples[side].ok and lo <= frame.x(side) <= hi and abs(frame.v(side)) <= TAKEN_MAX_MM_S
            for side in SIDES
        )

    @property
    def _moving(self) -> bool:
        return self.runner is not None or self._pending is not None

    def _cancel_move(self) -> None:
        if self._pending is not None:
            self._pending = None
            self._after = None
        if self.runner is not None:
            self.runner.cancel("остановлено", support=False)
            self.runner = None
            self._after = None
        self._jog = None
        if self.core is not None:
            for side in SIDES:
                self.drives[side].limit_speed_rpm(self.envelope.speed_limit_rpm)

    def _jog_done(self, resume: WorkoutMode) -> None:
        self._jog = None
        for side in SIDES:
            self.drives[side].limit_speed_rpm(self.envelope.speed_limit_rpm)
        if resume == "weightless":
            self._to_core(Mode.WEIGHTLESS, "weightless")
        else:
            self._to_core(Mode.HOLD, "paused")

    def _park(self) -> None:
        def parked() -> None:
            self._restore_speed_limits()
            self.core = None
            self.output = None
            self.mode = "parked"

        frame = self._require_frame()
        if frame.x_mean <= ON_STOPS_MM:
            parked()
            return
        self._move(lambda f: _park(self.balance, f), after=parked)

    def _restore_speed_limits(self) -> None:
        for side in SIDES:
            self.drives[side].limit_speed_rpm(None)

    def _write(self, output: CoreOutput) -> str | None:
        errors = []
        for side in SIDES:
            drive = self.drives[side]
            if output.kind == "support":
                error = drive.support()
            elif output.kind == "zero":
                error = drive.write_raw(ABORT_RAW * self.profile.side(side).sign)
            else:
                error = drive.write_force(output.forces_n[side])
            if error:
                errors.append(f"{side}: {error}")
        if errors:
            reason = "Запись PA_12C: " + "; ".join(errors)
            self.abort(reason)
            return reason
        return None

    # ------------------------------------------------------------ telemetry
    def amplitude_percent(self) -> int:
        if self.plan is None or self.frame is None or self.plan.upper_mm <= self.plan.lower_mm:
            return 0
        return int(round(clamp(100 * (self.frame.x_mean - self.plan.lower_mm) / (self.plan.upper_mm - self.plan.lower_mm), 0.0, 100.0)))

    def repetitions(self) -> tuple[int, int]:
        if self.plan is not None and self.plan.fixed_mm is not None:
            return self.fixed_reps, 0
        if self.reps is None:
            return 0, 0
        return self.reps.full, self.reps.partial

    def message(self) -> str | None:
        if self.reason:
            return self.reason
        return {
            "moving": "Гриф перемещается",
            "weightless": "Невесомый гриф: двигайте его руками",
            "start_hold": "Гриф удерживается в стартовой точке: возьмитесь за гриф и начните движение",
            "training": "Подход идёт",
            "paused": "Гриф удерживается",
            "fixed_hold": "Гриф зафиксирован: давите на него",
            "parked": "Гриф на упорах",
        }.get(self.mode)
