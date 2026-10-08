from __future__ import annotations

from app.models.settings import AppSetting
from app.motor import store
from app.motor.profile import Measured
from app.motor.store import ProfileBundle


def test_profile_store_versions_and_legacy_direction(db_session) -> None:
    db_session.add(AppSetting(user_id=None, key=store.LEGACY_PARAMETERS_KEY, value={"screw.rightDirectionInverted": True}))
    db_session.commit()
    bundle = store.load_active(db_session)
    assert bundle.machine.left.sign == 1
    assert bundle.machine.right.sign == -1
    assert bundle.machine.right.direction_sign.provenance == "manual"

    first = store.save_version(db_session, bundle, note="legacy")
    measured = bundle.machine.with_side("left", bundle.machine.left.__class__(direction_sign=Measured(-1, None, "measured", "B5-1")))
    second = store.save_version(db_session, ProfileBundle(machine=measured), note="B5")
    db_session.commit()
    assert (first, second) == (1, 2)
    assert store.load_active(db_session).machine.left.sign == -1
    store.activate(db_session, 1)
    assert store.load_active(db_session).machine.version == 1


def test_motor_api_profile_and_catalog(client) -> None:
    profile = client.get("/api/motor/profile")
    assert profile.status_code == 200
    assert profile.json()["machine"]["left"]["support_raw"]["value"] == 100
    catalog = client.get("/api/motor/calibrations").json()
    codes = {item["code"]: item for item in catalog}
    assert codes["S3"]["implemented"] and codes["S3"]["status"] == "missing"
    assert codes["D4"]["implemented"] and codes["D4"]["status"] == "missing"
    assert client.post("/api/motor/profile/1/activate").status_code == 409
