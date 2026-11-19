from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.routes.motor import exercise_observation, exercise_observations
from app.models.motor import MotorSetObservation
from app.motor.calibration.graph import CATALOG, RUN_SPECS
from app.motor.calibration.runner import Frame
from app.motor.drive.protocol import DriveSample
from app.motor.exercise_observation import TRACE_LIMIT, ExerciseObservation
from app.motor.parameters import BY_KEY, PARAMS, apply_changes, describe
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, SideProfile, Tunables
from app.motor.store import ProfileBundle
from app.motor.workout import SetPlan
from app.services.motor_observations import ObservationWriter


def test_every_profile_parameter_producer_and_illustration_is_accounted_for():
    for scope, cls in (("side", SideProfile), ("machine", MachineProfile), ("tunables", Tunables), ("envelope", SafetyEnvelope)):
        assert {f.name for f in fields(cls)} - {"version", "left", "right"} == {p.key for p in PARAMS if p.scope == scope}
    assert len(PARAMS) == len(BY_KEY)
    for spec in CATALOG:
        for path in spec.produces:
            parts = path.split(".")
            assert spec.code in BY_KEY[("side" if len(parts) == 2 else "machine", parts[-1])].produced_by
    guide = Path(__file__).resolve().parents[4] / "frontend/public/calibration-guide"
    assert {p.stem for p in guide.glob("*.webp")} == set(RUN_SPECS)
    assert all(p.read_bytes()[8:12] == b"WEBP" for p in guide.glob("*.webp"))


def test_profile_audit_checks_sides_table_order_and_repetition_thresholds():
    bundle = ProfileBundle(MachineProfile(), Tunables(), SafetyEnvelope())
    audit = describe(bundle)["audit"]
    assert audit["values"] == len(PARAMS) + len(fields(SideProfile)) and audit["unset"] > 0
    assert not audit["issues"]
    table = Measured([(80, 40), (40, 20)], None, "measured")
    machine = bundle.machine.with_side("right", replace(bundle.machine.right, friction_table_up=table))
    result = describe(replace(bundle, machine=machine))
    assert len(result["audit"]["issues"]) == 1 and result["audit"]["issues"][0]["side"] == "right"
    item = next(p for group in result["groups"] for p in group["items"] if p["key"] == "friction_table_up")
    assert item["values"]["right"]["rows"] == table.value
    calibrated = replace(bundle.machine, sync_k_n_per_mm=Measured(1.0, None, "measured"),
                         sync_k_train_n_per_mm=Measured(2.0, None, "measured"))
    effective = next(p for g in describe(replace(bundle, machine=calibrated))["groups"] for p in g["items"]
                     if p["scope"] == "tunables" and p["key"] == "sync_k_n_per_mm")
    assert effective["value"]["value"] != 2 and effective["effective"]["value"] == 2 and effective["effective"]["procedure"] == "X4"
    with pytest.raises(ValueError, match="частичного повторения"):
        apply_changes(bundle, [{"scope": "tunables", "key": "reps_partial_percent", "value": 90}])


def test_working_frames_only_extrema_survive_decimation_and_data_loss():
    obs = ExerciseObservation(SetPlan(100, 1000, 50), "row", "twin", 3, 0, 1, SafetyEnvelope())
    workout = SimpleNamespace(observing_work=True, load_n=50, target_load_n=50)

    def add(i, *, stale=False):
        t = i / 20
        speed = -750 if i == 1999 else 20
        sides = {s: DriveSample(s, t - (1 if stale else 0), ok=True, position_mm=500 + (3 if s == "left" else 0),
                                speed_mm_s=speed, motor_force_n=67) for s in ("left", "right")}
        obs.sample(Frame(t, sides), workout, .15)

    for i in range(2400):
        workout.observing_work = not 100 <= i < 120
        add(i, stale=i == 400)
    result = obs.payload()
    assert result["summary"]["validFrames"] == 2379 and result["summary"]["invalidFrames"] == 1
    assert result["summary"]["segments"] == 3 and result["summary"]["downMmS"] == [750, 750]
    assert result["summary"]["encoderDownMmS"] == [0, 0]  # a speed-register spike while both carriages stand still
    assert result["summary"]["maxSkewMm"] == 3 and result["summary"]["skewHeightMm"] == 501.5
    assert len(result["trace"]["t"]) <= TRACE_LIMIT + 1 and result["trace"]["t"][-1] == 2399 / 20
    assert len(set(result["trace"]["segment"])) == 3


def test_checkpoints_are_durable_retryable_and_recovered_after_restart(session_factory, monkeypatch):
    from app.services.hardware_runtime import HardwareRuntime
    runtime = HardwareRuntime()
    writer = ObservationWriter(session_factory, runtime)
    item = ExerciseObservation(SetPlan(100, 1000, 50, target_set=2), "barbell-floor-press", "twin", 4, 0, 1, runtime.envelope)
    runtime.observation = item
    writer.flush()
    # A completed set arriving during the DB commit must survive acknowledgment of its previous live checkpoint.
    snapshot = item.snapshot()
    runtime._finish_observation("completed")
    with monkeypatch.context() as patch:
        patch.setattr(runtime, "observation_checkpoints", lambda **kw: [snapshot])
        writer.flush()
    assert runtime.observation_checkpoints() == [item]
    with monkeypatch.context() as patch:
        patch.setattr(writer, "sessions", lambda: (_ for _ in ()).throw(OSError("disk")))
        with pytest.raises(OSError):
            writer.flush()
    writer.flush()
    writer.flush()
    with session_factory() as db:
        listed = exercise_observations("twin", 20, 0, db)
        assert len(listed["items"]) == 1 and "trace" not in listed["items"][0]
        assert not exercise_observations("modbus", 20, 0, db)["items"]
        record = exercise_observation(item.id, db)
        assert record["status"] == "completed" and record["exerciseName"] and record["profileVersion"] == 4
        assert record["setNumber"] == 2 and record["trace"]["t"] == []
        db.get(MotorSetObservation, item.id).status = "recording"
        db.commit()
    writer.recover()
    with session_factory() as db:
        recovered = exercise_observation(item.id, db)
        assert recovered["status"] == "interrupted" and "перезапущен" in recovered["reason"]
