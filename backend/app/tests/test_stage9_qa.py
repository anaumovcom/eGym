from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.analytics import MuscleFatigueSnapshot


def test_fatigue_endpoint_decays_from_persisted_snapshot_timestamp(client, db_session) -> None:
    snapshot = MuscleFatigueSnapshot(
        user_id="alexey",
        muscle_id="chest",
        fatigue_score=96.0,
        recovery_half_life_hours=24.0,
        calculated_at=datetime.now(UTC) - timedelta(hours=24),
        last_load_at=datetime.now(UTC) - timedelta(hours=30),
    )
    db_session.add(snapshot)
    db_session.commit()

    persisted = db_session.scalars(
        select(MuscleFatigueSnapshot).where(
            MuscleFatigueSnapshot.user_id == "alexey",
            MuscleFatigueSnapshot.muscle_id == "chest",
        )
    ).first()

    assert persisted is not None

    response = client.get('/api/fatigue', params={'userId': 'alexey', 'mode': 'current'})

    assert response.status_code == 200
    payload = response.json()
    chest = next(item for item in payload['muscles'] if item['id'] == 'chest')

    assert chest['score'] == 48
    assert payload['recoveryNote'] == 'Восстановление рассчитывается по persisted timestamp и фактической разнице времени, без таймеров в памяти.'