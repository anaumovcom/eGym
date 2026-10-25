"""V11: the workout episode — computed achievements, fact-bound wording, local template, API and live generation."""

import asyncio
import json

from app.models.coach import CoachEpisode
from app.schemas.coach_control import CoachPreferences
from app.services.coach import episode
from app.services.coach.luna import FakeTextAuthor
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, seed, settle

SOURCE = episode.EpisodeInput((("record", "Личный рекорд: такого веса ещё не было", ()),
                               ("sets-done", "Всего шесть подходов", (6,)),
                               ("counter-c1", "Очки славы: двести сорок", (240,))),
                              ("record", "plan"), "Гонка героев", "Клетчатый флаг и рёв трибун")


def test_achievements_are_computed_not_written():
    assert episode.achievements(fact_ids={"outcome", "jubilee"}, fact_values={"outcome": "full", "week-streak": 4},
                                records=1, steady_sets=3, boss_defeated=True) == (
        "record", "boss", "plan", "steady", "streak", "jubilee")
    assert episode.achievements(fact_ids=set(), fact_values={}, records=0, steady_sets=1, boss_defeated=False) == ()


def test_wording_must_stay_within_facts():
    good = {"title": "Финиш героя", "highlights": ["Шесть подходов без пощады", "Очки славы — двести сорок"],
            "finale": "Клетчатый флаг поднят, трибуны ревут."}
    assert episode.validate(good, SOURCE) == good
    assert episode.validate({**good, "highlights": ["Девять подходов!"]}, SOURCE) is None
    assert episode.validate({**good, "finale": "Гарантируем рост мышц"}, SOURCE) is None
    assert episode.validate({**good, "title": "Final lap"}, SOURCE) is None
    local = episode.local(SOURCE)
    assert local["title"] == "Гонка героев" and local["highlights"][0].startswith("Личный рекорд")


async def test_live_episode_after_the_workout_summary(session_factory):
    def script(body):
        name = body["text"]["format"]["name"]
        data = json.loads(body["input"][0]["content"])
        if name == "coach_episode":
            return {"title": "Финал сезона", "highlights": ["Десять повторений в копилку"], "finale": "Занавес, овации."}
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": list(data["lockedFactIds"]), "silenceReason": None,
                "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}, key: "Тренировка закрыта красиво."}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    with session_factory() as db:
        workout_id, _, _ = seed(db, actual=10, planned=10, status="completed")
    await coach.handle(event("workout_finalized", run_id, exercise=None, phase="workout-summary",
                             refs={"backendWorkoutId": workout_id}))
    await settle(coach)
    for _ in range(200):
        if coach.episode_job is not None and coach.episode_job.done():
            break
        await asyncio.sleep(0.01)
    assert sink.of("episode") and sink.of("episode")[-1]["workoutId"] == workout_id
    with session_factory() as db:
        row = db.get(CoachEpisode, workout_id)
        assert row.payload["source"] == "generated" and row.payload["title"] == "Финал сезона"
    await coach.close()


def test_episode_api_serves_saved_or_local(client, session_factory):
    client.base_url = "http://localhost"
    with session_factory() as db:
        workout_id, _, _ = seed(db, actual=10, planned=10, status="completed")
    local = client.get(f"/api/coach/workouts/{workout_id}/episode", params={"userId": "alexey"})
    assert local.status_code == 200 and local.json()["source"] == "local" and local.json()["highlights"]
    with session_factory() as db:
        episode.save(db, workout_id=workout_id, user_id="alexey", run_id=None,
                     payload={"title": "Эпизод", "highlights": ["Раз"], "finale": "Конец"}, source="generated",
                     achievement_ids=("plan",))
    saved = client.get(f"/api/coach/workouts/{workout_id}/episode", params={"userId": "alexey"}).json()
    assert saved["title"] == "Эпизод" and saved["achievements"] == [{"id": "plan", "label": "Весь план выполнен"}]
    assert client.get(f"/api/coach/workouts/{workout_id}/episode", params={"userId": "elena"}).status_code == 404
    assert client.get("/api/coach/workouts/999999/episode", params={"userId": "alexey"}).status_code == 404
