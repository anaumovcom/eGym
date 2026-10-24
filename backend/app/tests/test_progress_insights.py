from datetime import UTC, datetime, timedelta

from app.models.analytics import WorkoutSession
from app.models.enums import RuntimeFlowSource, WorkoutSessionStatus
from app.models.training import ExerciseHistoryRecord
from app.services.progress_insights import ProgressInsightsBuilder, estimate_one_rep_max, next_target

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def record(days_ago: float, slug: str, weight: float, reps_per_set: int, sets: int = 3, rpe: int = 6) -> ExerciseHistoryRecord:
    return ExerciseHistoryRecord(
        user_id="alexey", exercise_slug=slug, performed_at=NOW - timedelta(days=days_ago), weight_kg=weight,
        reps=reps_per_set * sets, sets=sets, volume_kg=weight * reps_per_set * sets, rpe=rpe, note="",
    )


def workout(days_ago: float, minutes: int) -> WorkoutSession:
    return WorkoutSession(
        user_id="alexey", source=RuntimeFlowSource.quick_start,
        title="", status=WorkoutSessionStatus.completed, started_at=NOW - timedelta(days=days_ago), duration_seconds=minutes * 60,
    )


def test_one_rep_max_and_double_progression() -> None:
    assert estimate_one_rep_max(0, 10) is None
    assert estimate_one_rep_max(100, 1) == 100
    assert estimate_one_rep_max(60, 10) == 80
    assert next_target(40, 10, 3, 6).weight_kg == 42
    assert next_target(40, 10, 3, 8).reps_per_set == 11
    assert next_target(40, 10, 3, 9).weight_kg == 40


def test_insights_compare_periods_and_detect_records() -> None:
    bench = "smith-machine-bench-press"
    history = [
        record(40, bench, 40, 10),  # previous period
        record(20, bench, 42, 10),  # record over 40
        record(10, bench, 41, 10),
        record(3, bench, 45, 10),  # record over 42
        record(3, "smith-machine-overhand-row", 30, 12),
        record(2, "cardio-quick-feet", 0, 60, sets=1),
    ]
    insights = ProgressInsightsBuilder(period="30d", history=history, workouts=[workout(3, 45), workout(40, 30), workout(1, 0)], now=NOW).build()

    kpis = {item.id: item for item in insights.kpis}
    assert kpis["days"].value == 4 and kpis["days"].previous == 1 and kpis["days"].delta_pct == 300
    assert kpis["minutes"].value == 45
    assert kpis["records"].value == 2
    assert insights.record_count == 2 and insights.records[0].e1rm == 60 and insights.records[0].previous == 56
    assert insights.timeline.granularity == "day" and len(insights.timeline.points) == 31
    assert insights.movers[0].slug == bench and insights.movers[0].from_value == 53.3 and insights.movers[0].to_value == 60

    zones = {item.id: item.sets for item in insights.muscle_balance}
    assert zones["chest"] == 9 and zones["back"] == 3 and zones["legs"] == 0  # cardio does not count as leg work

    exercises = {item.slug: item for item in insights.exercises}
    assert exercises["cardio-quick-feet"].kind == "bodyweight" and exercises["cardio-quick-feet"].unit == "сек"
    assert [item.is_pr for item in exercises[bench].sessions] == [False, True, False, True]
    assert exercises[bench].next_target is not None and exercises[bench].next_target.weight_kg > 45

    assert sum(day.level > 0 for week in insights.activity.weeks for day in week) == 5
    assert insights.activity.days_since_last == 2


def test_all_time_period_has_no_comparison() -> None:
    insights = ProgressInsightsBuilder(period="all", history=[record(5, "smith-machine-bench-press", 40, 10)], workouts=[], now=NOW).build()
    assert all(item.previous is None and item.delta_pct is None for item in insights.kpis)
    assert insights.period_start is None


def test_manual_measurement_updates_profile_weight_and_can_be_deleted(client) -> None:
    def profile_weight() -> float | None:
        return client.get("/api/users/current").json()["profile"]["weightKg"]

    client.post("/api/users/select", json={"userId": "alexey"})
    before = profile_weight()
    created = client.post("/api/body-measurements", json={"userId": "alexey", "measuredAt": datetime.now(UTC).isoformat(), "weightKg": 77.7, "waistCm": 81})
    assert created.status_code == 200
    newest = max(created.json()["measurements"], key=lambda item: item["measuredAt"])
    assert newest["weightKg"] == 77.7 and profile_weight() == 77.7

    assert client.delete(f"/api/body-measurements/{newest['id']}", params={"userId": "alexey"}).status_code == 400
    assert client.delete(f"/api/body-measurements/{newest['id']}", params={"userId": "elena", "confirm": "true"}).status_code == 404
    assert client.delete(f"/api/body-measurements/{newest['id']}", params={"userId": "alexey", "confirm": "true"}).status_code == 204
    remaining = client.get("/api/body-measurements", params={"userId": "alexey"}).json()["measurements"]
    assert all(item["id"] != newest["id"] for item in remaining)
    assert profile_weight() != 77.7
    assert before is None or profile_weight() is not None
