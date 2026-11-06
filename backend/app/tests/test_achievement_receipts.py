"""Owner-scoped receipts, privacy, badges and update ordering for achievements."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementGrant, AchievementProgress, AchievementReceipt
from app.services.achievements.content import load_catalog
from app.services.achievements.service import catalog, detail, evaluate_user, overview, record_receipt
from app.tests.test_achievements import result, workout


def grant(definition_id: str, tier: int, awarded_at: datetime, *, user_id: str = "alexey") -> AchievementGrant:
    return AchievementGrant(
        user_id=user_id, definition_id=definition_id, tier=tier, scope_key="lifetime", status="earned",
        earned_at=awarded_at - timedelta(minutes=1), awarded_at=awarded_at, evidence_digest="test",
    )


def test_locked_tier_text_images_and_audio_are_not_serialized(client: TestClient, db_session: Session):
    source = load_catalog()["lines"][0]
    hidden = source["tiers"][0]
    # An undiscovered line cannot be opened at all and exposes no description in the collection.
    assert client.get(f"/api/achievements/{source['id']}?userId=alexey").status_code == 404
    listing = client.get("/api/achievements/catalog?userId=alexey&limit=200")
    assert listing.status_code == 200 and listing.json()["total"] == len(load_catalog()["lines"])
    for text in (hidden["title"], hidden["phrase"], hidden["description"] if "description" in hidden else "",
                 source["description"], hidden.get("audioText", "")):
        assert not text or text not in listing.text
    for line in listing.json()["lines"]:
        assert line["description"] == ""
        for tier in line["tiers"]:
            assert tier["title"] == tier["phrase"] == ""
            assert tier["imageUrl"] is tier["thumbnailUrl"] is tier["audioUrl"] is None
            assert tier["audioState"] == "locked"
    # Hidden text is not searchable either.
    assert client.get("/api/achievements/catalog", params={"userId": "alexey", "query": source["description"][:20]}
                      ).json()["total"] == 0
    # Only the first tier is earned: its audio is reachable, higher locked tiers are not.
    db_session.add(grant(source["id"], 1, datetime(2026, 1, 1, tzinfo=UTC)))
    db_session.commit()
    opened = client.get(f"/api/achievements/{source['id']}?userId=alexey").json()
    assert opened["tiers"][0]["audioUrl"].endswith("/audio?userId=alexey")
    assert all(tier["audioUrl"] is None and tier["title"] == "" for tier in opened["tiers"][1:])
    earned_audio = client.get(opened["tiers"][0]["audioUrl"])
    assert earned_audio.status_code == 200 and earned_audio.headers["content-type"] == "audio/wav"
    assert client.get(opened["tiers"][0]["imageUrl"]).status_code == 200
    second = source["tiers"][1]["id"]
    assert client.get(f"/api/achievements/tiers/{second}/audio?userId=alexey").status_code == 404
    assert client.get(f"/api/achievements/tiers/{second}/image?userId=alexey").status_code == 404
    assert client.get(f"/api/achievements/tiers/{source['tiers'][0]['id']}/audio?userId=guest").status_code == 404


def test_achievement_files_are_not_publicly_static(client: TestClient):
    from app.services.achievements.media import MEDIA_ROOT
    audio = next((MEDIA_ROOT / "audio").glob("*.wav"))
    assert client.get(f"/media/achievements/v2/audio/{audio.name}").status_code == 404
    assert client.get("/media/achievements/v2/manifest.json").status_code == 404


def test_overview_upcoming_never_reveals_unknown_lines(client: TestClient, db_session: Session):
    db_session.add(AchievementProgress(user_id="alexey", definition_id="start.two_weeks", scope_key="lifetime",
                                       current_value=1, highest_tier=0, data_state="available"))
    db_session.commit()
    assert client.get("/api/achievements/overview?userId=alexey").json()["upcoming"] == []



def test_receipt_is_owner_scoped_and_idempotent(client: TestClient, db_session: Session):
    db_session.add(grant("start.first_set", 1, datetime(2026, 1, 1, tzinfo=UTC)))
    db_session.commit()
    path = "/api/achievements/start.first_set/receipts/detail?userId=alexey"
    first = client.post(path)
    second = client.post(path)
    assert first.status_code == second.status_code == 200
    assert first.json()["viewedAt"] == second.json()["viewedAt"]
    assert db_session.scalars(select(AchievementReceipt)).one().surface == "detail"
    assert client.post("/api/achievements/start.first_set/receipts/detail?userId=guest").status_code == 404
    listened = client.post("/api/achievements/start.first_set/receipts/audio?userId=alexey&tier=1")
    assert listened.status_code == 200
    assert listened.json()["isNew"] is False
    assert len(db_session.scalars(select(AchievementReceipt)).all()) == 2


def test_new_badge_uses_latest_tier_and_unseen_or_unheard(db_session: Session):
    db_session.add_all([
        grant("start.first_set", 1, datetime(2026, 1, 1, tzinfo=UTC)),
        grant("start.first_set", 2, datetime(2026, 1, 2, tzinfo=UTC)),
    ])
    db_session.commit()
    record_receipt(db_session, "alexey", "start.first_set", "detail", tier=1)
    record_receipt(db_session, "alexey", "start.first_set", "audio", tier=1)
    assert detail(db_session, "alexey", "start.first_set")["isNew"] is True
    assert overview(db_session, "alexey")["recent"][0]["isNew"] is True
    assert record_receipt(db_session, "alexey", "start.first_set", "detail")["isNew"] is True
    assert record_receipt(db_session, "alexey", "start.first_set", "audio", tier=2)["isNew"] is False
    assert detail(db_session, "alexey", "start.first_set")["isNew"] is False
    assert overview(db_session, "alexey")["recent"][0]["isNew"] is False


def test_catalog_sorts_newest_update_then_next_progress_then_stable_id(db_session: Session):
    db_session.add_all([
        grant("start.first_set", 1, datetime(2026, 1, 1, tzinfo=UTC)),
        grant("start.first_workout", 1, datetime(2026, 1, 3, tzinfo=UTC)),
        AchievementProgress(user_id="alexey", definition_id="start.two_weeks", scope_key="lifetime",
                            current_value=1, highest_tier=0, data_state="available"),
        AchievementProgress(user_id="alexey", definition_id="start.two_weeks", scope_key="evidence",
                            current_value=100, highest_tier=0, data_state="available"),
        AchievementProgress(user_id="alexey", definition_id="start.three_days", scope_key="lifetime",
                            current_value=1, highest_tier=0, data_state="available"),
        AchievementProgress(user_id="alexey", definition_id="start.three_days", scope_key="evidence",
                            current_value=100, highest_tier=0, data_state="available"),
    ])
    db_session.commit()
    lines = catalog(db_session, "alexey", limit=500)["lines"]
    assert [line["id"] for line in lines[:4]] == [
        "start.first_workout", "start.first_set", "start.two_weeks", "start.three_days",
    ]


def test_first_tiers_are_awarded_after_proof_days_and_evaluation_stays_idempotent(db_session: Session):
    for day in range(12):
        row = workout(db_session, "alexey", datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(days=day))
        for _ in range(2):
            result(db_session, row, "alexey", metrics={"setType": "working", "completionStatus": "completed"})
    db_session.commit()
    evaluate_user(db_session, "alexey")
    earned = {(row.definition_id, row.tier) for row in db_session.scalars(select(AchievementGrant))
              if row.status == "earned"}
    assert ("start.first_set", 1) in earned
    assert ("start.first_workout", 1) in earned
    before = len(earned)
    assert evaluate_user(db_session, "alexey")["awarded"] == []
    assert len(db_session.scalars(select(AchievementGrant).where(AchievementGrant.status == "earned")).all()) == before
