"""Stage 12 — motion control: emulator physics, controller behaviour and tuning API."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.models.settings import AppSetting
from app.schemas.hardware import TuningUpdateSchema
from app.services.hardware_runtime import HardwareRuntime, hardware_runtime
from app.services.hardware_service import HardwareService
from app.services.motion.adapter import AdapterTelemetry, SideTelemetry
from app.services.motion.controller import ControlMode, HomingPhase, MotionController
from app.services.motion.parameters import MotionParameters, ParameterValidationError


def _run(runtime: HardwareRuntime, seconds: float, *, until=None) -> None:  # noqa: ANN001
    ticks = int(seconds / runtime.tick_seconds)
    for _ in range(ticks):
        runtime._tick_motion()
        if until is not None and until():
            return


def _telemetry(position: float, *, low: tuple[bool, bool] = (False, False), high: tuple[bool, bool] = (False, False)) -> AdapterTelemetry:
    return AdapterTelemetry(
        timestamp=0.0,
        left=SideTelemetry(side="left", position_mm=position, limit_switch_low=low[0], limit_switch_high=high[0]),
        right=SideTelemetry(side="right", position_mm=position, limit_switch_low=low[1], limit_switch_high=high[1]),
    )


@pytest.fixture()
def runtime(monkeypatch) -> HardwareRuntime:  # noqa: ANN001
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "false")
    get_settings.cache_clear()
    instance = HardwareRuntime()
    _run(instance, 0.5)
    yield instance
    get_settings.cache_clear()


# ---------------------------------------------------------------- parameters
def test_parameter_registry_validates_hard_limits_and_relations() -> None:
    params = MotionParameters()
    with pytest.raises(ParameterValidationError):
        params.set_many({"limits.maxSpeedMmPerSec": 5000}, temporary=True)
    with pytest.raises(ParameterValidationError):
        params.set_many({"sync.warningMm": 10, "sync.criticalMm": 4}, temporary=True)
    with pytest.raises(ParameterValidationError):
        params.set_many({"unknown.key": 1}, temporary=True)
    changes = params.set_many({"compensation.barMassKg": 22.5}, temporary=True)
    assert changes == {"compensation.barMassKg": (20.0, 22.5)}
    assert params.get("compensation.barMassKg") == 22.5
    assert params.revert_temporary() == ["compensation.barMassKg"]
    assert params.get("compensation.barMassKg") == 20.0


# ------------------------------------------------------------------ safety
def test_power_on_self_test_leads_to_idle_with_brakes(runtime: HardwareRuntime) -> None:
    control = runtime.controller.state
    assert control.post_status == "passed"
    assert control.mode == ControlMode.idle
    assert control.brake_engaged is True
    assert control.position_known is True


def test_start_without_limit_switches_does_not_require_homing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARDWARE_LIMIT_SWITCHES_ENABLED", "false")
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        runtime = HardwareRuntime()
        homing_calls = []
        monkeypatch.setattr(runtime.controller, "request_homing", lambda: homing_calls.append(True))
        _run(runtime, 0.5)
        state = runtime.controller.state
        assert homing_calls == []
        assert state.post_status == "passed"
        assert state.mode == ControlMode.idle
        assert state.homing_phase == HomingPhase.complete
        assert state.position_known
        assert runtime.last_telemetry.left.position_mm == pytest.approx(0, abs=1.0)
        assert runtime.last_telemetry.right.position_mm == pytest.approx(0, abs=1.0)
        assert not any(command.mode != "brake" for command in (runtime.last_command.left, runtime.last_command.right))
        assert not any("homing" in alert for alert in runtime.snapshot_payload()["alerts"])
    finally:
        get_settings.cache_clear()


def test_without_limit_switches_unzeroed_encoders_are_zeroed_silently_and_failures_do_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARDWARE_LIMIT_SWITCHES_ENABLED", "false")
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        runtime = HardwareRuntime()
        _run(runtime, 0.5)
        for side in ("left", "right"):
            runtime.emulator._sides[side].homed = False
        calls = []

        def failing_home() -> None:
            calls.append(True)
            raise RuntimeError("no zero yet")

        monkeypatch.setattr(runtime.adapter, "home", failing_home)
        _run(runtime, 0.5)
        assert calls, "unzeroed encoders must be retried"
        assert runtime.controller.state.mode == ControlMode.idle
        assert runtime.controller.state.position_known
        assert runtime.controller.state.fault_code is None
    finally:
        get_settings.cache_clear()


def test_service_setting_is_persisted_and_only_applied_on_next_start(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    runtime = HardwareRuntime()
    monkeypatch.setattr("app.services.hardware_service.hardware_runtime", runtime)
    service = HardwareService()
    key = "homing.limitSwitchesEnabled"

    with pytest.raises(PermissionError, match="сервисном режиме"):
        service.update_tuning(db_session, TuningUpdateSchema(values={key: False}, apply="persist"))
    runtime.set_service_mode(True)
    with pytest.raises(PermissionError, match="после перезапуска"):
        service.update_tuning(db_session, TuningUpdateSchema(values={key: False}, apply="temporary"))
    result = service.update_tuning(db_session, TuningUpdateSchema(values={key: False}, apply="persist"))
    assert result.values[key] is False
    assert runtime.controller.limit_switches_enabled is True
    assert runtime.controller.homing_ready_to_zero is False

    saved = db_session.query(AppSetting).filter_by(key=service.PARAMETERS_KEY, user_id=None).one().value
    assert saved[key] is False
    runtime.reset(persisted_parameters=saved)
    assert runtime.controller.limit_switches_enabled is False
    assert runtime.controller.state.homing_phase == HomingPhase.complete
    assert runtime.controller.state.mode == ControlMode.idle


def test_pair_based_two_pass_homing_calibrates_both_physical_limits() -> None:
    params = MotionParameters()
    params.set_many(
        {
            "homing.stopSettleMs": 10,
            "homing.pairTimeWindowMs": 100,
            "homing.releaseTimeoutMs": 500,
            "homing.phaseTimeoutSec": 5,
            "homing.totalTimeoutSec": 30,
            "homing.maximumSearchDistanceMm": 2000,
        },
        temporary=True,
    )
    controller = MotionController(params)
    controller.request_homing()

    controller.tick(_telemetry(100), 0.01)
    controller.tick(_telemetry(50, low=(True, False)), 0.01)
    assert controller.state.homing_phase == HomingPhase.bottom_creep
    controller.tick(_telemetry(49, low=(True, True)), 0.01)
    assert controller.state.homing_phase == HomingPhase.bottom_stop
    controller.tick(_telemetry(49, low=(True, True)), 0.02)
    controller.tick(_telemetry(58), 0.01)
    assert controller.state.homing_phase == HomingPhase.bottom_fine
    controller.tick(_telemetry(51, low=(False, True)), 0.01)
    controller.tick(_telemetry(50, low=(True, True)), 0.01)
    assert controller.homing_ready_to_zero is True
    controller.mark_homing_reference_applied()

    controller.tick(_telemetry(500), 0.01)
    controller.tick(_telemetry(989, high=(True, False)), 0.01)
    controller.tick(_telemetry(990, high=(True, True)), 0.01)
    assert controller.state.homing_phase == HomingPhase.top_stop
    controller.tick(_telemetry(990, high=(True, True)), 0.02)
    controller.tick(_telemetry(981), 0.01)
    assert controller.state.homing_phase == HomingPhase.top_fine
    controller.tick(_telemetry(989, high=(False, True)), 0.01)
    controller.tick(_telemetry(990, high=(True, True)), 0.01)
    assert controller.state.homing_phase == HomingPhase.move_safe_top
    controller.tick(_telemetry(985), 0.01)

    assert controller.state.mode == ControlMode.idle
    assert controller.state.homing_phase == HomingPhase.complete
    assert controller.state.physical_bottom_mm == pytest.approx(0)
    assert controller.state.physical_top_mm == pytest.approx(990)
    assert controller.state.working_bottom_mm == pytest.approx(5)
    assert controller.state.working_top_mm == pytest.approx(985)
    assert controller.state.full_travel_mm == pytest.approx(990)


def test_homing_rejects_pair_that_completes_outside_first_edge_window() -> None:
    params = MotionParameters()
    params.set_many({"homing.pairTimeWindowMs": 50}, temporary=True)
    controller = MotionController(params)
    controller.request_homing()
    controller.tick(_telemetry(100), 0.01)
    controller.tick(_telemetry(50, low=(True, False)), 0.01)
    controller.tick(_telemetry(49, low=(True, True)), 0.05)

    assert controller.state.mode == ControlMode.fault
    assert controller.state.homing_phase == HomingPhase.fault
    assert "sensor_pair_timeout" in (controller.state.fault_code or "")


def test_weightless_bar_stays_put_and_follows_hand(runtime: HardwareRuntime) -> None:
    runtime.enter_weightless()
    start = runtime.controller.state.position_mm
    _run(runtime, 2.0)
    assert abs(runtime.controller.state.position_mm - start) < 3, "gravity compensation must hold the bar"
    assert runtime.controller.state.mode == ControlMode.weightless

    runtime.emulator.set_user_force(4.0)
    _run(runtime, 1.5)
    moved = runtime.controller.state.position_mm
    assert moved > start + 30, "a light push must move the weightless bar"
    runtime.emulator.set_user_force(0.0)
    _run(runtime, 2.0)
    assert runtime.controller.state.mode == ControlMode.weightless
    assert abs(runtime.controller.state.velocity_mm_s) < 5
    assert runtime.controller.state.still_ms >= float(runtime.parameters.get("regulator.stillnessMs"))


def test_capture_points_in_weightless_mode_requires_stillness(runtime: HardwareRuntime) -> None:
    with pytest.raises(PermissionError):
        runtime.capture_point("lower")
    runtime.enter_weightless()
    _run(runtime, 1.5)
    _, lower = runtime.capture_point("lower")
    runtime.emulator.set_user_force(5.0)
    _run(runtime, 1.0)
    with pytest.raises(PermissionError):
        runtime.capture_point("upper")
    runtime.emulator.set_user_force(0.0)
    _run(runtime, 2.0)
    _, upper = runtime.capture_point("upper")
    assert upper > lower + 20
    assert runtime.snapshot_payload()["motion"]["lower_bound_mm"] == lower
    assert runtime.snapshot_payload()["motion"]["upper_bound_mm"] == upper


def test_training_with_virtual_user_counts_full_reps_and_estimates_force(runtime: HardwareRuntime) -> None:
    runtime.start_motion(
        calibration_id=None,
        lower_bound_mm=700,
        upper_bound_mm=1000,
        target_set=1,
        target_reps=3,
        motion_profile="training",
        load_kg=30,
        auto_user=True,
    )
    _run(runtime, 25.0, until=lambda: runtime.controller.state.target_reached)
    control = runtime.controller.state
    assert control.repetition_count == 3
    assert control.target_reached is True
    assert control.load_effective_kg == pytest.approx(30.0, abs=0.5)
    assert 20 < control.user_force_kg < 40, "estimated user force must be close to the load"
    assert control.sync_status in {"norm", "ok"}
    kinds = [event.kind for event in runtime.controller.events]
    assert kinds.count("rep") == 3
    assert "target" in kinds


def test_start_hold_detects_grip_and_switches_to_training(runtime: HardwareRuntime) -> None:
    runtime.move_to_start(lower_bound_mm=700, upper_bound_mm=1000, start_point="lower", load_kg=20)
    _run(runtime, 30.0, until=lambda: runtime.controller.state.mode == ControlMode.start_hold)
    assert runtime.controller.state.mode == ControlMode.start_hold
    assert abs(runtime.controller.state.position_mm - 700) < 5
    runtime.emulator.set_user_force(12.0)
    _run(runtime, 1.0, until=lambda: runtime.controller.state.mode == ControlMode.training)
    assert runtime.controller.state.mode == ControlMode.training
    assert runtime.controller.state.grip_detected is True


def test_released_bar_under_load_goes_to_hold(runtime: HardwareRuntime) -> None:
    runtime.start_motion(calibration_id=None, lower_bound_mm=700, upper_bound_mm=1000, target_set=1, target_reps=5, motion_profile="training", load_kg=30, auto_user=True)
    _run(runtime, 4.0)
    runtime.emulator.set_scenario("none")
    runtime.emulator.set_user_force(0.0)
    _run(runtime, 3.0, until=lambda: runtime.controller.state.mode == ControlMode.paused)
    assert runtime.controller.state.mode == ControlMode.paused
    assert runtime.controller.state.released or runtime.controller.state.failure_detected
    _run(runtime, 1.0)  # let the position servo settle after catching the bar
    position = runtime.controller.state.position_mm
    _run(runtime, 1.0)
    assert abs(runtime.controller.state.position_mm - position) < 3, "held bar must not sag"


def test_hold_catches_a_moving_bar_where_it_stops_without_swinging_back(runtime: HardwareRuntime) -> None:
    runtime.start_motion(calibration_id=None, lower_bound_mm=700, upper_bound_mm=1000, target_set=1, target_reps=5, motion_profile="training", load_kg=30, auto_user=True)
    _run(runtime, 20.0, until=lambda: runtime.controller.state.velocity_mm_s < -150)
    assert runtime.controller.state.velocity_mm_s < -150
    runtime.emulator.set_scenario("none")
    runtime.emulator.set_user_force(0.0)
    requested_at = runtime.controller.state.position_mm
    runtime.controller.request_hold("Спасение")
    _run(runtime, 1.0)
    caught_at = runtime.controller._hold_position_mm
    assert caught_at is not None and caught_at < requested_at - 1, "the hold target must follow the bar until it stops"
    highest = runtime.controller.state.position_mm
    for _ in range(int(1.0 / runtime.tick_seconds)):
        runtime._tick_motion()
        highest = max(highest, runtime.controller.state.position_mm)
    assert highest < caught_at + 3, "the caught bar must not be pulled back up to the request point"
    assert runtime.controller.state.mode == ControlMode.paused


def test_regripping_released_bar_resumes_the_set_but_manual_pause_does_not(runtime: HardwareRuntime) -> None:
    runtime.start_motion(calibration_id=None, lower_bound_mm=700, upper_bound_mm=1000, target_set=1, target_reps=5, motion_profile="training", load_kg=0, auto_user=False)
    runtime.emulator.set_user_force(0.0)
    _run(runtime, 3.0, until=lambda: runtime.controller.state.mode == ControlMode.paused)
    assert runtime.controller.state.mode == ControlMode.paused
    assert runtime.controller.state.released
    _run(runtime, 1.0)
    assert runtime.controller.state.mode == ControlMode.paused, "a released bar stays held without a grip"

    runtime.emulator.set_user_force(12.0)
    _run(runtime, 1.0, until=lambda: runtime.controller.state.mode == ControlMode.training)
    assert runtime.controller.state.mode == ControlMode.training
    assert not runtime.controller.state.released
    assert "grip" in [event.kind for event in runtime.controller.events]

    runtime.pause()
    _run(runtime, 1.5)
    assert runtime.controller.state.mode == ControlMode.paused, "manual pause must wait for an explicit resume"


def test_spotter_engages_when_user_fails(runtime: HardwareRuntime) -> None:
    runtime.update_parameters({"detection.spotterDelaySec": 0.6}, temporary=True)
    runtime.start_motion(calibration_id=None, lower_bound_mm=700, upper_bound_mm=1000, target_set=1, target_reps=10, motion_profile="training", load_kg=40, auto_user=False)
    runtime.emulator.set_scenario("failure", strength_kg=55, lower_mm=700, upper_mm=1000, period_s=2.5, fail_after_reps=1)
    _run(runtime, 20.0, until=lambda: runtime.controller.state.spotter_active or runtime.controller.state.mode != ControlMode.training)
    kinds = [event.kind for event in runtime.controller.events]
    assert "spotter" in kinds or "failure" in kinds


def test_fixed_position_hold_test_and_load_based_reps(runtime: HardwareRuntime) -> None:
    runtime.start_fixed_position(position_mm=1500, target_reps=2, rep_count_source="load")
    _run(runtime, 40.0, until=lambda: runtime.controller.state.fixed_hold_test_passed)
    control = runtime.controller.state
    assert control.mode == ControlMode.fixed_hold
    assert control.fixed_hold_test_passed is True
    assert abs(control.position_mm - 1500) < 3
    # a pull-up: user hangs (pulls down) and releases twice
    for _ in range(2):
        runtime.emulator.set_user_force(-70.0)
        _run(runtime, 0.8)
        runtime.emulator.set_user_force(0.0)
        _run(runtime, 0.8)
    assert control.repetition_count == 2
    assert abs(control.position_mm - 1500) < float(runtime.parameters.get("fixed.driftToleranceMm")) * 3


def test_bar_jog_requires_hold_and_reaches_the_requested_step(runtime: HardwareRuntime) -> None:
    runtime.start_motion(calibration_id=9, lower_bound_mm=700, upper_bound_mm=1000, target_set=1, target_reps=8, motion_profile="training", auto_user=False)
    with pytest.raises(PermissionError):
        runtime.manual_move("up", 10, "service")
    runtime.pause()
    position = runtime.controller.state.position_mm
    with pytest.raises(ValueError):
        runtime.manual_move("up", 51, "service")
    runtime.controller.state.user_force_kg = 25
    with pytest.raises(PermissionError, match="Освободите гриф"):
        runtime.manual_move("up", 10, "service")
    runtime.controller.state.user_force_kg = 0
    runtime.manual_move("up", 10, "service")
    with pytest.raises(PermissionError):
        runtime.manual_move("down", 10, "service")
    _run(runtime, 8.0, until=lambda: runtime.controller.state.mode == ControlMode.paused)
    assert runtime.controller.state.mode == ControlMode.paused
    assert runtime.controller.state.position_mm == pytest.approx(position + 10, abs=3)
    runtime.resume(lower_mm=position + 10, upper_mm=1000)
    assert runtime.controller.config.lower_mm == pytest.approx(position + 10)
    assert runtime.controller.state.mode == ControlMode.training


def test_fixed_hold_cannot_be_moved_until_paused(runtime: HardwareRuntime) -> None:
    runtime.start_fixed_position(position_mm=860, calibration_id=12)
    _run(runtime, 5.0, until=lambda: runtime.controller.state.mode == ControlMode.fixed_hold)
    with pytest.raises(PermissionError):
        runtime.manual_move("up", 10, "service")
    runtime.pause()
    runtime.manual_move("up", 10, "service")
    _run(runtime, 8.0, until=lambda: runtime.controller.state.mode == ControlMode.paused)
    with pytest.raises(PermissionError):
        runtime.resume(fixed_position_mm=860)
    runtime.resume(fixed_position_mm=runtime.controller.state.position_mm)
    assert runtime.controller.state.mode == ControlMode.fixed_hold


def test_hold_to_jog_stops_on_release_and_watchdog(runtime: HardwareRuntime, monkeypatch) -> None:  # noqa: ANN001
    clock = [100.0]
    monkeypatch.setattr("app.services.hardware_runtime.time.monotonic", lambda: clock[0])
    runtime.start_jog("up", "press-1", "alexey", "barbell-floor-press")
    with pytest.raises(PermissionError):
        runtime.refresh_jog("press-1", "elena", "barbell-floor-press")
    start = runtime.controller.state.position_mm
    for _ in range(15):
        _run(runtime, 0.2)
        clock[0] += 0.2
        runtime.refresh_jog("press-1", "alexey", "barbell-floor-press")
    per_kg = float(runtime.parameters.get("torque.perKgRaw"))
    assert runtime.controller.state.components["jog"] == pytest.approx(2 * float(runtime.parameters.get("torque.jogUpRaw")) / per_kg, abs=0.05)
    assert runtime.controller.state.position_mm > start + 20
    assert runtime.controller.state.mode == ControlMode.weightless
    runtime.stop_jog("press-1", "alexey", "barbell-floor-press")
    assert runtime.controller.state.mode == ControlMode.weightless
    assert runtime.controller.jog_direction is None
    with pytest.raises(PermissionError):
        runtime.refresh_jog("press-1", "alexey", "barbell-floor-press")
    runtime.start_jog("down", "press-2", "alexey", "barbell-floor-press")
    _run(runtime, 0.2)
    assert runtime.controller.state.components["jog"] == pytest.approx(-2 * float(runtime.parameters.get("torque.jogDownRaw")) / per_kg, abs=0.05)
    clock[0] += 0.7
    runtime._tick_motion()
    assert runtime.controller.state.mode == ControlMode.weightless
    assert runtime.controller.jog_direction is None
    assert not runtime.jog_active


def test_power_loss_engages_brakes_and_requires_homing(runtime: HardwareRuntime) -> None:
    runtime.update_parameters({"safety.faultLockoutEnabled": True}, temporary=True)
    runtime.enter_weightless()
    _run(runtime, 0.5)
    position = runtime.controller.state.position_mm
    runtime.emulator_control("fault", fault="power_loss")
    _run(runtime, 1.0)
    control = runtime.controller.state
    assert control.mode == ControlMode.fault
    assert abs(control.position_mm - position) < 1, "bar must not drop on power loss"
    runtime.emulator_control("fault", fault="power_restore")
    _run(runtime, 0.2)
    assert runtime.last_telemetry.left.homed is False
    runtime.reset_fault()
    _run(runtime, 0.2)
    assert control.position_known is False
    assert any("homing" in alert for alert in runtime.snapshot_payload()["alerts"])
    runtime.home()
    _run(runtime, 120.0, until=lambda: control.mode in {ControlMode.idle, ControlMode.fault} and control.homed)
    assert control.homed is True
    assert control.position_known is True


def test_communication_loss_faults_and_incident_is_recorded(runtime: HardwareRuntime) -> None:
    runtime.update_parameters({"safety.faultLockoutEnabled": True}, temporary=True)
    runtime.enter_weightless()
    _run(runtime, 0.5)
    runtime.emulator_control("fault", fault="comm_lost", side="right")
    _run(runtime, 0.5)
    assert runtime.controller.state.mode == ControlMode.fault
    assert "E-COMM-02" in (runtime.controller.state.fault_code or "")
    assert runtime.recorder.incidents, "black box must capture the incident"
    snapshot = runtime.snapshot_payload()
    assert snapshot["drives"][1]["status"] == "error"


def test_lockout_disabled_reports_comm_loss_as_alert_only(runtime: HardwareRuntime) -> None:
    assert runtime.parameters.get("safety.faultLockoutEnabled") is False
    runtime.enter_weightless()
    _run(runtime, 0.5)
    runtime.emulator_control("fault", fault="comm_lost", side="right")
    _run(runtime, 0.5)
    assert runtime.controller.state.mode == ControlMode.weightless
    assert any("E-COMM-02" in alert for alert in runtime.controller.state.alerts)


def test_desync_hold_action_when_sides_tilt(runtime: HardwareRuntime) -> None:
    runtime.update_parameters({"sync.desyncAction": "hold", "sync.criticalMm": 6}, temporary=True)
    runtime.enter_weightless()
    _run(runtime, 0.5)
    runtime.emulator.set_physics(coupling_kg_per_mm=0.05, coupling_damping=0.01)
    runtime.emulator.set_user_force(20.0, bias=1.0)
    _run(runtime, 3.0, until=lambda: runtime.controller.state.mode == ControlMode.paused)
    assert runtime.controller.state.mode == ControlMode.paused
    assert any(event.kind == "desync" for event in runtime.controller.events)


def test_emergency_stop_blocks_motion_and_holds_position(runtime: HardwareRuntime) -> None:
    runtime.start_motion(calibration_id=None, lower_bound_mm=700, upper_bound_mm=1000, target_set=1, target_reps=5, motion_profile="training", load_kg=30, auto_user=True)
    _run(runtime, 2.0)
    runtime.trigger_emergency_stop()
    position = runtime.controller.state.position_mm
    _run(runtime, 1.0)
    assert runtime.controller.state.mode == ControlMode.estop
    assert abs(runtime.controller.state.position_mm - position) < 1
    assert runtime.last_telemetry.left.brake_engaged is True
    runtime.clear_emergency_stop()
    _run(runtime, 0.2)
    assert runtime.controller.state.mode == ControlMode.paused


def test_reset_fault_releases_emergency_stop_in_one_press(runtime: HardwareRuntime) -> None:
    runtime.trigger_emergency_stop()
    _run(runtime, 0.3)
    assert runtime.controller.state.mode == ControlMode.estop
    runtime.reset_fault()
    _run(runtime, 0.3)
    assert runtime.state.safety_state.value == "enabled"
    assert runtime.controller.state.mode == ControlMode.paused
    assert runtime.controller.state.fault_code is None


def test_measurement_wizard_estimates_bar_mass(runtime: HardwareRuntime) -> None:
    runtime.state.service_mode = True
    runtime.start_procedure("bar_mass")
    _run(runtime, 6.0, until=lambda: runtime.procedure.status != "running")
    assert runtime.procedure.status == "done"
    result = runtime.procedure.result or {}
    expected = runtime.emulator.physics.total_mass_kg
    assert result["measuredTotalMassKg"] == pytest.approx(expected, abs=1.5)
    assert "compensation.barMassKg" in result["suggested"]


def test_scenario_weightless_drift_passes(runtime: HardwareRuntime) -> None:
    runtime.start_procedure("weightless_drift")
    _run(runtime, 8.0, until=lambda: runtime.procedure.status != "running")
    assert runtime.procedure.status == "done"
    assert runtime.procedure.result["passed"] is True


# --------------------------------------------------------------------- API
def test_tuning_api_requires_service_mode_and_persists(client, db_session) -> None:  # noqa: ANN001
    schema = client.get("/api/hardware/tuning/schema").json()
    assert any(group["id"] == "compensation" for group in schema["groups"])
    assert any(param["key"] == "compensation.barMassKg" for param in schema["parameters"])
    assert schema["procedures"]["measurements"]

    denied = client.put("/api/hardware/tuning", json={"values": {"compensation.barMassKg": 21}, "apply": "temporary"})
    assert denied.status_code == 409

    toggled = client.post("/api/hardware/commands", json={"action": "toggle_service_mode", "serviceMode": True, "userId": "alexey"})
    assert toggled.status_code == 200

    temporary = client.put("/api/hardware/tuning", json={"values": {"compensation.barMassKg": 21}, "apply": "temporary"})
    assert temporary.status_code == 200
    assert temporary.json()["temporary"] == {"compensation.barMassKg": 21.0}

    invalid = client.put("/api/hardware/tuning", json={"values": {"limits.maxSpeedMmPerSec": 9999}, "apply": "temporary"})
    assert invalid.status_code == 400

    persisted = client.put("/api/hardware/tuning", json={"values": {"compensation.barMassKg": 22}, "apply": "persist", "actorUserId": "alexey"})
    assert persisted.status_code == 200
    current = client.get("/api/hardware/tuning").json()
    assert current["values"]["compensation.barMassKg"] == 22.0
    assert current["temporary"] == {}

    reverted = client.post("/api/hardware/tuning/revert").json()
    assert reverted["values"]["compensation.barMassKg"] == 22.0

    presets = client.get("/api/hardware/tuning/presets").json()
    assert any(item["id"] == "factory" for item in presets)
    saved = client.post("/api/hardware/tuning/presets", json={"title": "Мой стенд", "description": "test"})
    assert saved.status_code == 200
    diff = client.get("/api/hardware/tuning/presets/factory/diff").json()
    assert any(item["key"] == "compensation.barMassKg" for item in diff["differences"])

    # leaving service mode drops temporary values
    client.put("/api/hardware/tuning", json={"values": {"compensation.barMassKg": 25}, "apply": "temporary"})
    client.post("/api/hardware/commands", json={"action": "toggle_service_mode", "serviceMode": False, "userId": "alexey"})
    assert client.get("/api/hardware/tuning").json()["values"]["compensation.barMassKg"] == 22.0


def test_commands_weightless_capture_and_snapshot_control(client) -> None:  # noqa: ANN001
    response = client.post("/api/hardware/commands", json={"action": "enter_weightless", "userId": "alexey"})
    assert response.status_code == 200
    assert response.json()["snapshot"]["control"]["mode"] == "weightless"
    for _ in range(int(1.5 / hardware_runtime.tick_seconds)):
        hardware_runtime._tick_motion()
    captured = client.post("/api/hardware/commands", json={"action": "capture_point", "which": "lower", "userId": "alexey"})
    assert captured.status_code == 200, captured.text
    assert captured.json()["capturedPositionMm"] is not None
    snapshot = client.get("/api/hardware/status", params={"userId": "alexey"}).json()
    assert snapshot["control"]["mode"] == "weightless"
    assert "components" in snapshot["control"]
    hold = client.post("/api/hardware/commands", json={"action": "hold", "userId": "alexey"})
    assert hold.json()["snapshot"]["control"]["mode"] == "paused"


def test_emulator_and_recordings_endpoints(client) -> None:  # noqa: ANN001
    emulator = client.get("/api/hardware/tuning/emulator").json()
    assert emulator["active"] is True
    pushed = client.post("/api/hardware/tuning/emulator", json={"action": "user_force", "forceKg": 5})
    assert pushed.status_code == 200
    assert pushed.json()["userForceKg"] == 5.0
    started = client.post("/api/hardware/tuning/recordings", json={"action": "start"})
    assert started.json()["recording"] is True
    for _ in range(10):
        hardware_runtime._tick_motion()
    stopped = client.post("/api/hardware/tuning/recordings", json={"action": "stop", "title": "Проба"})
    assert stopped.status_code == 200
    recording_id = stopped.json()["id"]
    detail = client.get(f"/api/hardware/tuning/recordings/{recording_id}").json()
    assert detail["fields"][0] == "t"
    assert len(detail["samples"]) >= 10
    with client.websocket_connect("/api/hardware/telemetry-debug") as websocket:
        batch = websocket.receive_json()
        assert batch["eventType"] == "telemetry.batch"
        assert "fields" in batch
