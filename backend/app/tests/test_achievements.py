from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.achievement import AchievementDefinition, AchievementEvidence, AchievementGrant
from app.models.analytics import ExerciseSession, SetResult, WorkoutSession
from app.models.enums import ExerciseSessionStatus, RuntimeExerciseKind, RuntimeFlowSource, WorkoutSessionStatus
from app.services.achievements.collection import CONTENT_VERSION, VERSION, collection
from app.services.achievements.content import load_catalog, validate_catalog
from app.services.achievements.facts import training_day
from app.services.achievements.media import manifest_summary
from app.services.achievements.rules import CATALOG_VERSION, RULES
from app.services.achievements.service import catalog, detail, evaluate_user, overview, sync_definitions, workout_awards


def workout(db: Session, user_id: str, started: datetime, *, status=WorkoutSessionStatus.completed) -> WorkoutSession:
    row = WorkoutSession(user_id=user_id, source=RuntimeFlowSource.catalog, title="Test", status=status,
                         started_at=started, finished_at=started + timedelta(minutes=30), duration_seconds=1800)
    db.add(row)
    db.flush()
    return row


def result(db: Session, workout_row: WorkoutSession, user_id: str, *, kind=RuntimeExerciseKind.machine,
           actual=10, weight=20.0, slug="press", metrics=None) -> SetResult:
    exercise = ExerciseSession(workout_session_id=workout_row.id, user_id=user_id, exercise_slug=slug,
                               exercise_name=slug, kind=kind, order_index=1, status=ExerciseSessionStatus.completed,
                               started_at=workout_row.started_at, finished_at=workout_row.finished_at,
                               target_sets=1, set_results=[])
    db.add(exercise)
    db.flush()
    row = SetResult(exercise_session_id=exercise.id, set_number=1, planned_value=actual, actual_value=actual,
                    reps=actual if kind not in {RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch} else None,
                    duration_seconds=actual if kind in {RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch} else None,
                    weight_kg=weight, tempo_label="normal", created_at=workout_row.started_at,
                    machine_metrics=metrics or {"setType": "working", "completionStatus": "completed"})
    db.add(row)
    db.flush()
    return row


def test_illustrated_catalog_keeps_its_editorial_rules_and_tiers():
    catalog = load_catalog()
    assert len(catalog["lines"]) == len(RULES)
    assert sum(len(line["tiers"]) for line in catalog["lines"]) == sum(len(rule['thresholds']) for rule in RULES)
    assert len({rule["metric"] for rule in RULES}) > 100
    complete = all(tier["contentOrigin"] == "gpt-6.1-sol" for line in catalog["lines"] for tier in line["tiers"])
    if complete:
        assert validate_catalog(catalog, generated=True) == []


def test_training_day_resets_at_three():
    zone = datetime.now().astimezone().tzinfo
    assert training_day(datetime(2026, 1, 2, 2, 59, tzinfo=zone)).isoformat() == "2026-01-01"
    assert training_day(datetime(2026, 1, 2, 3, 0, tzinfo=zone)).isoformat() == "2026-01-02"


def test_evaluation_is_idempotent_and_scoped_to_workout(db_session: Session):
    user_id = "alexey"
    for day in range(12):
        first = workout(db_session, user_id, datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(days=day))
        for _ in range(2):
            result(db_session, first, user_id, actual=10, weight=20,
                   metrics={'setType': 'working', 'completionStatus': 'completed'})
    db_session.commit()

    evaluation = evaluate_user(db_session, user_id, source_workout_id=first.id)
    assert evaluation["awarded"]
    assert len(db_session.scalars(select(AchievementGrant).where(AchievementGrant.user_id == user_id)).all()) == len(evaluation["awarded"])
    assert evaluate_user(db_session, user_id, source_workout_id=first.id)["awarded"] == []
    awards = workout_awards(db_session, user_id, first.id)
    assert awards is not None and len(awards["awards"]) == len(evaluation["awarded"])
    assert all(award["sourceWorkoutId"] == first.id for award in awards["awards"])
    assert workout_awards(db_session, "elena", first.id) is None


def test_seconds_are_not_reps_and_volume_uses_exact_grams(db_session: Session):
    user_id = "alexey"
    row = workout(db_session, user_id, datetime(2026, 1, 1, 12, tzinfo=UTC))
    result(db_session, row, user_id, kind=RuntimeExerciseKind.timed, actual=45, weight=None)
    db_session.commit()
    evaluate_user(db_session, user_id, source_workout_id=row.id)
    grants = {(grant.definition_id, grant.tier) for grant in db_session.scalars(select(AchievementGrant))}
    assert ("variety.timed_seconds", 1) not in grants
    assert ("practice.reps", 1) not in grants
    assert ("start.first_workout", 1) in grants


def test_simulated_sets_never_award(db_session: Session):
    user_id = "alexey"
    row = workout(db_session, user_id, datetime(2026, 1, 1, 12, tzinfo=UTC))
    result(db_session, row, user_id, metrics={"sourceClass": "simulated", "setType": "working"})
    db_session.commit()
    evaluation = evaluate_user(db_session, user_id, source_workout_id=row.id)
    assert evaluation["awarded"] == []
    assert workout_awards(db_session, user_id, row.id)["awards"] == []


def test_media_summary_has_expected_catalog_size():
    assert manifest_summary()["lines"] == len(RULES)
    assert manifest_summary()["tiers"] == sum(len(rule['thresholds']) for rule in RULES)


def test_summary_and_detail_cover_the_whole_active_collection(db_session):
    active = [line for line in collection().values() if not line.get("archived")]
    summary = overview(db_session, 'alexey')
    assert summary['totalLines'] == len(active) >= 90
    assert summary['totalTiers'] == sum(len(line['tiers']) for line in active) >= 350
    assert summary['completedLines'] == 0
    assert detail(db_session, 'alexey', active[-1]['id'])['highestTier'] == 0
    assert len(catalog(db_session, 'alexey', limit=200)['lines']) == len(active)
    assert detail(db_session, 'alexey', 'start.first_set') is None


def test_series_and_tier_names_are_distinct_and_the_original_movements_remain_searchable(db_session):
    names = [name.casefold().replace("ё", "е") for line in collection().values()
             for name in (line["name"], *(tier["title"] for tier in line["tiers"]))]
    assert all(names) and len(names) == len(set(names))
    for query, key in (("Предплечья", "muscle.forearms"), ("Французский жим", "exercise.smith-machine-skullcrusher")):
        assert key in {line["id"] for line in catalog(db_session, "alexey", query=query)["lines"]}


def test_title_update_preserves_an_existing_grant_when_only_content_version_changes(db_session):
    key = "start.first_workout"
    row = workout(db_session, "alexey", datetime(2026, 1, 1, 12, tzinfo=UTC))
    definition = AchievementDefinition(id=key, rules_version=VERSION, content_version=VERSION, active=True,
                                       value={"id": key, "name": "Первая запись"})
    grant = AchievementGrant(user_id="alexey", definition_id=key, tier=1, scope_key="lifetime", status="earned",
                             source_workout_id=row.id, earned_at=row.finished_at, awarded_at=row.finished_at,
                             evidence_digest="existing")
    db_session.add_all([definition, grant])
    db_session.commit()
    sync_definitions(db_session)
    db_session.refresh(definition)
    assert (definition.rules_version, definition.content_version) == (VERSION, CONTENT_VERSION)
    assert definition.value["name"] == "Кроссовки голосуют ногами"
    assert definition.value["tiers"][0]["title"] == "Диван взял отгул"
    [award] = workout_awards(db_session, "alexey", row.id)["awards"]
    assert (award["grantId"], award["sourceWorkoutId"], award["earnedAt"]) == (grant.id, row.id, row.finished_at.isoformat())
    assert award["tier"]["title"] == definition.value["tiers"][0]["title"]
    assert db_session.scalars(select(AchievementGrant)).all() == [grant]


def test_rebalance_preserves_historical_but_revokes_new_invalid_evidence(db_session):
    row = workout(db_session, 'alexey', datetime(2026, 1, 1, 12, tzinfo=UTC))
    result(db_session, row, 'alexey')
    old = AchievementGrant(user_id='alexey', definition_id='start.first_set', tier=1, scope_key='lifetime',
                           status='earned', source_workout_id=row.id, earned_at=row.started_at,
                           awarded_at=row.started_at, evidence_digest='historical')
    new = AchievementGrant(user_id='alexey', definition_id='start.first_set', tier=2, scope_key='lifetime',
                           status='earned', source_workout_id=row.id, earned_at=row.started_at,
                           awarded_at=row.started_at, evidence_digest='new')
    db_session.add_all([old, new])
    db_session.flush()
    for grant, revision in ((old, 'achievements-rules-1.1.0'), (new, CATALOG_VERSION)):
        db_session.add(AchievementEvidence(grant_id=grant.id, source_type='workout', source_id=str(row.id),
                                          source_revision=revision, metric_value=1, unit='test'))
    db_session.commit()
    evaluate_user(db_session, 'alexey')
    assert old.status == 'earned'
    assert new.status == 'revoked'
    archived = detail(db_session, 'alexey', old.definition_id)
    assert archived['archived'] and [tier['tier'] for tier in archived['tiers']] == [1]
    assert archived['name'] == 'У подхода есть подход'
    assert archived['tiers'][0]['title'] == 'А вот и сам подход'
    assert archived['nextTierId'] is None


def test_public_runtime_only_grants_on_finish_and_retries_keep_the_same_awards(client, db_session):
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    draft = dict(userId="alexey", source="catalog", title="Тренировка", status="in_progress", startedAt=start.isoformat())
    workout_id = client.post("/api/runtime/workouts", json=draft).json()["workoutSessionId"]
    exercise = dict(userId="alexey", workoutSessionId=workout_id, exerciseSlug="press", exerciseName="Жим",
                    kind="machine", status="in_progress", startedAt=start.isoformat(), targetSets=1)
    exercise_id = client.post("/api/runtime/exercises", json=exercise).json()["exerciseSessionId"]
    assert client.post("/api/runtime/sets", json=dict(exerciseSessionId=exercise_id, setNumber=1, plannedValue=10,
        actualValue=8, reps=8, tempoLabel="обычный", machineMetrics={"completionStatus": "partial"})).status_code == 200
    finish_time = (start + timedelta(minutes=20)).isoformat()
    assert client.post("/api/runtime/exercises", json={**exercise, "exerciseSessionId": exercise_id,
                                                       "status": "partial", "finishedAt": finish_time}).status_code == 200
    url = f"/api/runtime/workouts/{workout_id}/awards"
    assert client.get(url, params={"userId": "alexey"}).json()["awards"] == []
    assert client.get("/api/achievements/overview?userId=alexey").json()["earnedTiers"] == 0
    assert not any(a["unlocked"] for a in client.get("/api/achievements?userId=alexey").json()["achievements"])
    assert not db_session.scalars(select(AchievementGrant)).all()

    finish = {**draft, "workoutSessionId": workout_id, "status": "partial", "finishedAt": finish_time}
    assert client.post("/api/runtime/workouts", json=finish).status_code == 200
    awards = client.get(url, params={"userId": "alexey"}).json()["awards"]
    assert [a["tier"]["id"] for a in awards] == ["start.first_workout:t1"]
    assert awards[0]["tier"]["title"] == "Диван взял отгул"
    assert awards[0]["sourceWorkoutId"] == workout_id
    assert client.post("/api/runtime/workouts", json=finish).status_code == 200
    assert client.get(url, params={"userId": "alexey"}).json()["awards"] == awards
    assert client.get(url, params={"userId": "elena"}).status_code == 404
    assert client.get("/api/achievements/overview?userId=elena").json()["earnedTiers"] == 0


def test_empty_active_and_foreign_finishes_cannot_claim_existing_history(db_session):
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    historical = workout(db_session, "alexey", start)
    result(db_session, historical, "alexey")
    empty = workout(db_session, "alexey", start + timedelta(days=1))
    draft = workout(db_session, "alexey", start + timedelta(days=2), status=WorkoutSessionStatus.in_progress)
    result(db_session, draft, "alexey")
    stranger = workout(db_session, "elena", start)
    for source in (empty, draft):
        assert evaluate_user(db_session, "alexey", source_workout_id=source.id)["awarded"] == []
    draft.status, draft.finished_at = WorkoutSessionStatus.completed, None
    assert evaluate_user(db_session, "alexey", source_workout_id=draft.id)["awarded"] == []
    with pytest.raises(LookupError):
        evaluate_user(db_session, "alexey", source_workout_id=stranger.id)
    with pytest.raises(LookupError):
        evaluate_user(db_session, "alexey", source_workout_id=99999)
    assert not db_session.scalars(select(AchievementGrant)).all()


def test_duets_count_distinct_days_within_one_workout_and_delayed_events_stop_at_their_finish(db_session):
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    for index, kinds in enumerate([["machine"], ["stretch"], ["machine", "stretch"], ["machine", "stretch"],
                                   ["machine", "stretch"]]):
        # Two separate workouts on day zero, two identical combinations on day one, one on day two.
        day = (0, 0, 1, 1, 2)[index]
        row = workout(db_session, "alexey", start + timedelta(days=day, hours=index))
        for kind in kinds:
            result(db_session, row, "alexey", kind=RuntimeExerciseKind(kind), slug=kind)
        if index == 3:
            earlier = row
    db_session.commit()
    evaluate_user(db_session, "alexey", source_workout_id=earlier.id)
    assert detail(db_session, "alexey", "duet.machine_stretch")["highestTier"] == 0
    awards = evaluate_user(db_session, "alexey", source_workout_id=row.id)["awarded"]
    assert [(a.tier, a.source_workout_id) for a in awards if a.definition_id == "duet.machine_stretch"] == [(1, row.id)]
    assert detail(db_session, "alexey", "duet.machine_stretch")["currentValue"] == 2


def test_repertoire_returns_and_seasons_use_actual_workout_dates(db_session):
    from app.services.achievements.facts import FactBuilder

    for at, slugs in [
        ((2025, 12, 12), ("press", "curl")), ((2026, 1, 18), ("press", "curl")),
        ((2026, 3, 1), ("press", "curl", "row")), ((2026, 6, 3), ("press", "curl")),
        ((2026, 9, 16), ("press", "curl")),
    ]:
        row = workout(db_session, "alexey", datetime(*at, 12, tzinfo=UTC))
        for slug in slugs:
            result(db_session, row, "alexey", slug=slug)
    values = FactBuilder(db_session, "alexey", collection_only=True).finish()
    assert values["return.rediscovered"] == 2
    assert values["signature.reunited_pairs"] == values["discovery.old_and_new"] == 1
    assert values["signature.same_setlist"] == values["signature.familiar_only"] == 3
    assert values["calendar.month_bridge"] == 1
    assert values["calendar.season_turns"] == 4 and values["calendar.four_colours"] == 1
    assert values["discovery.seasoned"] == 2


def test_remixes_hosts_and_relays_respect_workouts_days_and_weeks(db_session):
    from app.services.achievements.facts import FactBuilder

    monday = datetime(2026, 1, 5, 12, tzinfo=UTC)
    def add(day, slugs, kind="machine"):
        row = workout(db_session, "alexey", monday + timedelta(days=day))
        for slug in slugs:
            result(db_session, row, "alexey", slug=slug, kind=RuntimeExerciseKind(kind))
        return row

    def counts():
        facts = FactBuilder(db_session, "alexey", collection_only=True).finish()
        return tuple(facts.get(key, 0) for key in ("signature.remix", "discovery.club_host", "calendar.format_relay"))

    add(0, ["press", "curl", "row"])
    add(0, ["press", "curl", "squat"])
    add(0, ["stretch"], "stretch")
    assert counts() == (0, 0, 0)
    add(1, ["press", "curl", "lunge"])
    add(1, ["lunge", "press", "curl"])
    assert counts() == (1, 0, 1)
    add(7, ["press"])
    add(7, ["pull"])
    assert counts() == (1, 0, 1)
    add(8, ["press", "pull"])
    assert counts() == (1, 1, 1)
    add(9, ["curl", "press", "lunge"])
    assert counts()[0] == 1


def test_each_active_and_archived_tier_has_a_distinct_decodable_published_picture():
    from PIL import Image

    from app.services.achievements.media import asset_file

    active = [line for line in collection().values() if not line.get("archived")]
    assert manifest_summary(active)["images"] == sum(len(line["tiers"]) for line in active)
    paths = set()
    for line in collection().values():
        for tier in line["tiers"]:
            path = asset_file(tier["id"], "image")
            assert path is not None and path not in paths, tier["id"]
            paths.add(path)
            with Image.open(path) as picture:
                assert picture.format == "WEBP" and picture.size == (512, 512)
                picture.load()
