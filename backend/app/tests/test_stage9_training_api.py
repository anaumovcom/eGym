from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.analytics import MuscleFatigueSnapshot


def test_exercise_catalog_and_details_use_real_backend(client: TestClient) -> None:
    catalog_response = client.get("/api/exercises", params={"userId": "alexey", "search": "pulldown"})

    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert catalog_payload["total"] >= 1
    assert any(item["slug"] == "machine-pulldown" for item in catalog_payload["items"])

    details_response = client.get("/api/exercises/machine-pulldown", params={"userId": "alexey"})
    assert details_response.status_code == 200
    details_payload = details_response.json()
    assert details_payload["slug"] == "machine-pulldown"
    assert details_payload["loadSettings"]["weight"] >= 0
    assert details_payload["compatibility"]["title"]


def test_exercise_catalog_preview_video_matches_user_gender(client: TestClient) -> None:
    male_response = client.get("/api/exercises", params={"userId": "alexey", "search": "machine-pulldown"})
    female_response = client.get("/api/exercises", params={"userId": "elena", "search": "machine-pulldown"})

    assert male_response.status_code == 200
    assert female_response.status_code == 200

    male_item = next(item for item in male_response.json()["items"] if item["slug"] == "machine-pulldown")
    female_item = next(item for item in female_response.json()["items"] if item["slug"] == "machine-pulldown")

    assert "male-" in male_item["previewVideoUrl"]
    assert "female-" in female_item["previewVideoUrl"]


def test_stage2_real_api_routes_return_frontend_shapes(client: TestClient) -> None:
    quick_start = client.get("/api/quick-start", params={"userId": "alexey", "selected": "machine-pulldown"})
    today = client.get("/api/today", params={"userId": "alexey", "scenario": "planned", "selected": "machine-pulldown"})
    programs = client.get("/api/programs", params={"selected": "back-biceps"})
    calendar = client.get("/api/calendar", params={"mode": "week", "selectedDayId": "2026-05-14"})
    builder = client.get("/api/builder", params={"selectedExerciseId": "group-pullups-1"})

    assert quick_start.status_code == 200
    assert quick_start.json()["selectedExercise"]["exercise"]["slug"] == "machine-pulldown"

    assert today.status_code == 200
    assert today.json()["selectedExerciseId"] == "machine-pulldown"
    assert len(today.json()["exerciseRows"]) >= 3

    assert programs.status_code == 200
    assert programs.json()["selectedProgram"]["id"] == "back-biceps"

    assert calendar.status_code == 200
    calendar_payload = calendar.json()
    assert calendar_payload["mode"] == "week"
    assert calendar_payload["selectedDayId"] == "2026-05-14"
    assert len(calendar_payload["days"]) >= 5

    assert builder.status_code == 200
    builder_payload = builder.json()
    assert builder_payload["selectedExerciseId"] == "group-pullups-1"
    assert builder_payload["selectedExercise"]["loadType"] == "weighted"
    assert builder_payload["groups"][1]["items"][-1]["loadType"] == "timed"
    assert builder_payload["groups"][1]["items"][-1]["load"] == "вес тела"
    assert len(builder_payload["strengthModes"]) == 10
    assert builder_payload["selectedExercise"]["strengthModeId"] == "basic"
    assert builder_payload["selectedExercise"]["strengthPlan"]


def test_strength_modes_route_returns_selection_cards(client: TestClient) -> None:
    response = client.get("/api/strength-modes")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 10
    assert {item["id"] for item in payload} >= {"basic", "double_progression", "periodized_day"}
    periodized = next(item for item in payload if item["id"] == "periodized_day")
    assert [option["id"] for option in periodized["dayOptions"]] == ["light", "medium", "heavy"]


def test_today_plan_replacement_persists_between_requests(client: TestClient) -> None:
    save_response = client.put(
        "/api/today/plan",
        json={
            "userId": "alexey",
            "slugs": ["machine-seated-cable-row", "machine-pulldown", "barbell-curl"],
        },
    )

    assert save_response.status_code == 200
    assert save_response.json()["status"] == "saved"

    today_response = client.get("/api/today", params={"userId": "alexey", "scenario": "planned", "selected": "machine-seated-cable-row"})

    assert today_response.status_code == 200
    payload = today_response.json()
    assert [item["slug"] for item in payload["exerciseRows"]] == ["machine-seated-cable-row", "machine-pulldown", "barbell-curl"]
    assert payload["selectedExerciseId"] == "machine-seated-cable-row"


def test_builder_replacement_persists_between_requests(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "alternating",
                    "title": "Тяга сверху + Присед",
                    "rounds": "3 круга • 8–12 мин",
                    "betweenExercisesRest": "30 сек",
                    "betweenRoundsRest": "90 сек",
                    "items": [
                        {"id": "group-pullups-1", "slug": "machine-seated-cable-row", "name": "Тяга горизонтального блока", "muscleGroup": "Спина", "sets": "3×10", "rest": "30 сек", "load": "45 кг"},
                        {"id": "group-squat-1", "slug": "barbell-heels-up-back-squat", "name": "Присед", "muscleGroup": "Ноги", "sets": "3×8", "rest": "30 сек", "load": "60 кг"},
                    ],
                }
            ],
        },
    )

    assert save_response.status_code == 200
    assert save_response.json()["status"] == "saved"

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "group-pullups-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert payload["groups"][0]["items"][0]["slug"] == "machine-seated-cable-row"
    assert payload["selectedExercise"]["name"] == "Тяга горизонтального блока"


def test_builder_added_exercise_persists_between_requests(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "alternating",
                    "title": "Тяга сверху + Присед",
                    "rounds": "3 круга • 8–12 мин",
                    "betweenExercisesRest": "30 сек",
                    "betweenRoundsRest": "90 сек",
                    "items": [
                        {"id": "group-pullups-1", "slug": "machine-pulldown", "name": "Тяга сверху", "muscleGroup": "Спина", "sets": "3×10", "rest": "30 сек", "load": "45 кг"},
                        {"id": "group-squat-1", "slug": "barbell-heels-up-back-squat", "name": "Присед", "muscleGroup": "Ноги", "sets": "3×8", "rest": "30 сек", "load": "60 кг"},
                        {"id": "group-added-1", "slug": "barbell-curl", "name": "Сгибание рук", "muscleGroup": "Бицепс", "sets": "3", "rest": "60 сек", "load": "20 кг x 10"},
                    ],
                }
            ],
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "group-added-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert any(item["id"] == "group-added-1" and item["slug"] == "barbell-curl" for item in payload["groups"][0]["items"])
    assert payload["selectedExerciseId"] == "group-added-1"
    added_item = next(item for item in payload["groups"][0]["items"] if item["id"] == "group-added-1")
    assert added_item["load"] == "20 кг"
    assert added_item["sets"] == "3×10"
    assert added_item["loadType"] == "weighted"


def test_builder_bodyweight_exercise_does_not_show_kilograms(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Bodyweight",
                    "items": [
                        {"id": "bodyweight-1", "slug": "assisted-bulgarian-split-squat", "name": "Болгарский сплит-присед с поддержкой", "muscleGroup": "Ноги", "sets": "3×12", "rest": "60 сек", "load": "20 кг"},
                    ],
                }
            ],
            "selectedExerciseId": "bodyweight-1",
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "bodyweight-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    bodyweight_item = payload["groups"][0]["items"][0]
    assert bodyweight_item["load"] == "вес тела"
    assert bodyweight_item["loadType"] == "bodyweight"
    assert payload["selectedExercise"]["loadType"] == "bodyweight"
    assert payload["selectedExercise"]["setParams"]["weight"] == 0


def test_builder_timed_exercise_exposes_and_preserves_duration(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Static",
                    "items": [
                        {"id": "plank-1", "slug": "forearm-plank", "name": "Планка", "muscleGroup": "Кор", "sets": "3×60 сек", "rest": "45 сек", "load": "вес тела", "loadType": "timed"},
                    ],
                }
            ],
            "selectedExerciseId": "plank-1",
            "selectedExercise": {
                "name": "Планка",
                "subtitle": "Кор",
                "setParams": {"reps": 12, "weight": 7, "restSeconds": 45, "durationSeconds": 60},
                "loadType": "timed",
                "loadMode": "Контроль техники",
                "tempo": "Плавный",
                "note": "Держать корпус ровно.",
            },
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "plank-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    timed_item = payload["groups"][0]["items"][0]
    assert timed_item["sets"] == "3×59 сек"
    assert timed_item["rest"] == "75 сек"
    assert payload["selectedExercise"]["loadType"] == "timed"
    assert payload["selectedExercise"]["setParams"]["durationSeconds"] == 60
    assert payload["selectedExercise"]["setParams"]["weight"] == 7
    assert payload["selectedExercise"]["effectiveSetParams"]["durationSeconds"] == 59
    assert payload["selectedExercise"]["effectiveSetParams"]["restSeconds"] == 75


def test_builder_load_mode_and_tempo_change_effective_plan_values(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Weighted",
                    "items": [
                        {"id": "pulldown-1", "slug": "machine-pulldown", "name": "Тяга сверху", "muscleGroup": "Спина", "sets": "3×10", "rest": "60 сек", "load": "50 кг", "loadType": "weighted"},
                    ],
                }
            ],
            "selectedExerciseId": "pulldown-1",
            "selectedExercise": {
                "name": "Тяга сверху",
                "subtitle": "Спина",
                "setParams": {"reps": 10, "weight": 50, "restSeconds": 60},
                "loadType": "weighted",
                "loadMode": "Лёгкий режим",
                "tempo": "Контроль эксцентрики",
                "note": "Снизить нагрузку и контролировать фазу вниз.",
            },
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "pulldown-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    item = payload["groups"][0]["items"][0]
    assert item["sets"] == "3×7"
    assert item["load"] == "36 кг"
    assert item["rest"] == "105 сек"
    assert payload["selectedExercise"]["setParams"] == {"reps": 10, "weight": 50, "restSeconds": 60}
    assert payload["selectedExercise"]["effectiveSetParams"] == {"reps": 7, "weight": 36, "restSeconds": 105}
    assert "снижает" in payload["selectedExercise"]["loadModeDescription"]
    assert "эксцентрики" in payload["selectedExercise"]["tempoDescription"]


def test_builder_strength_mode_persists_between_requests(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Weighted",
                    "items": [
                        {"id": "pulldown-1", "slug": "machine-pulldown", "name": "Тяга сверху", "muscleGroup": "Спина", "sets": "3×10", "rest": "60 сек", "load": "50 кг", "loadType": "weighted"},
                    ],
                }
            ],
            "selectedExerciseId": "pulldown-1",
            "selectedExercise": {
                "name": "Тяга сверху",
                "subtitle": "Спина",
                "setParams": {"reps": 10, "weight": 50, "restSeconds": 90},
                "loadType": "weighted",
                "loadMode": "Обычный вес",
                "tempo": "Обычный",
                "strengthModeId": "double_progression",
                "note": "Добрать 12 / 12 / 12.",
            },
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "pulldown-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert payload["selectedExercise"]["strengthModeId"] == "double_progression"
    assert [item["targetRepsLabel"] for item in payload["selectedExercise"]["strengthPlan"]] == ["8–12", "8–12", "8–12"]


def test_runtime_exercise_summary_recommends_double_progression_increase(client: TestClient) -> None:
    response = client.post(
        "/api/runtime/exercises",
        json={
            "userId": "alexey",
            "exerciseSlug": "machine-pulldown",
            "exerciseName": "Тяга сверху",
            "exerciseSecondaryName": "Pulldown",
            "kind": "machine",
            "orderIndex": 1,
            "status": "completed",
            "startedAt": "2026-05-25T10:00:00Z",
            "finishedAt": "2026-05-25T10:12:00Z",
            "calibrationState": "saved",
            "targetSets": 3,
            "trainingMode": "double_progression",
            "muscles": [{"muscleId": "back", "name": "Спина", "role": "primary"}],
            "sets": [
                {"setNumber": 1, "plannedValue": 12, "actualValue": 12, "setType": "work", "targetMinReps": 8, "targetMaxReps": 12, "reps": 12, "weightKg": 45, "tempoLabel": "хорошо", "subjectiveEffort": 7},
                {"setNumber": 2, "plannedValue": 12, "actualValue": 12, "setType": "work", "targetMinReps": 8, "targetMaxReps": 12, "reps": 12, "weightKg": 45, "tempoLabel": "хорошо", "subjectiveEffort": 7},
                {"setNumber": 3, "plannedValue": 12, "actualValue": 12, "setType": "work", "targetMinReps": 8, "targetMaxReps": 12, "reps": 12, "weightKg": 45, "tempoLabel": "хорошо", "subjectiveEffort": 8},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["volume"] == "1620 кг"
    assert "Можно увеличить вес" in payload["recommendation"]


def test_runtime_exercise_summary_blocks_progress_on_pain(client: TestClient) -> None:
    response = client.post(
        "/api/runtime/exercises",
        json={
            "userId": "alexey",
            "exerciseSlug": "machine-pulldown",
            "exerciseName": "Тяга сверху",
            "kind": "machine",
            "orderIndex": 1,
            "status": "completed",
            "startedAt": "2026-05-25T11:00:00Z",
            "finishedAt": "2026-05-25T11:10:00Z",
            "targetSets": 3,
            "trainingMode": "hypertrophy",
            "sets": [
                {"setNumber": 1, "plannedValue": 12, "actualValue": 12, "setType": "work", "targetMinReps": 8, "targetMaxReps": 12, "reps": 12, "weightKg": 45, "tempoLabel": "хорошо"},
                {"setNumber": 2, "plannedValue": 12, "actualValue": 10, "setType": "work", "targetMinReps": 8, "targetMaxReps": 12, "reps": 10, "weightKg": 45, "tempoLabel": "техника просела", "pain": True, "techniqueBreakdown": True, "discomfortLevel": 6},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Не увеличивай вес" in payload["recommendation"]
    assert payload["setResults"][1]["pain"] is True


def test_builder_deleted_exercise_persists_between_requests(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "alternating",
                    "title": "Тяга сверху + Присед",
                    "rounds": "3 круга • 8–12 мин",
                    "betweenExercisesRest": "30 сек",
                    "betweenRoundsRest": "90 сек",
                    "items": [
                        {"id": "group-squat-1", "slug": "barbell-heels-up-back-squat", "name": "Присед", "muscleGroup": "Ноги", "sets": "3×8", "rest": "30 сек", "load": "60 кг"},
                    ],
                }
            ],
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "group-squat-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert len(payload["groups"][0]["items"]) == 1
    assert payload["groups"][0]["items"][0]["id"] == "group-squat-1"


def test_builder_marks_recovery_exercises_as_non_fatiguing(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Recovery mix",
                    "items": [
                        {"id": "row-1", "slug": "machine-pulldown", "name": "Тяга сверху", "muscleGroup": "Спина", "sets": "3×10", "rest": "60 сек", "load": "45 кг"},
                        {"id": "row-2", "slug": "ankle-circle", "name": "Круги стопой", "muscleGroup": "Икры", "sets": "3×30 сек", "rest": "30 сек", "load": "вес тела"},
                    ],
                }
            ],
            "selectedExerciseId": "row-1",
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "selectedExerciseId": "row-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    recovery_item = next(item for item in payload["groups"][0]["items"] if item["slug"] == "ankle-circle")
    assert recovery_item["affectsFatigue"] is False


def test_builder_workout_name_persists_between_requests(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "programId": "back-biceps",
            "workoutName": "Спина и руки",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Основной блок",
                    "items": [
                        {"id": "row-1", "slug": "machine-pulldown", "name": "Тяга сверху", "muscleGroup": "Спина", "sets": "3×10", "rest": "60 сек", "load": "45 кг"},
                    ],
                }
            ],
            "selectedExerciseId": "row-1",
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "programId": "back-biceps", "selectedExerciseId": "row-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert payload["info"]["name"] == "Спина и руки"
    program_tab = next(program for program in payload["programs"] if program["id"] == "back-biceps")
    assert program_tab["name"] == "Спина и руки"


def test_builder_duration_is_calculated_from_exercises(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "programId": "back-biceps",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Короткий блок",
                    "items": [
                        {"id": "row-1", "slug": "machine-pulldown", "name": "Тяга сверху", "muscleGroup": "Спина", "sets": "3×10", "rest": "60 сек", "load": "45 кг"},
                    ],
                }
            ],
            "selectedExerciseId": "row-1",
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "programId": "back-biceps", "selectedExerciseId": "row-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    duration_card = next(card for card in payload["summaryCards"] if card["label"] == "минут")
    assert duration_card["value"] == "6"
    assert payload["info"]["duration"] == "≈ 6 минут"


def test_builder_preserves_empty_group(client: TestClient) -> None:
    save_response = client.put(
        "/api/builder/plan",
        json={
            "userId": "alexey",
            "programId": "back-biceps",
            "groups": [
                {
                    "id": "group-a",
                    "kind": "single",
                    "title": "Основной блок",
                    "items": [
                        {"id": "row-1", "slug": "machine-pulldown", "name": "Тяга сверху", "muscleGroup": "Спина", "sets": "3×10", "rest": "60 сек", "load": "45 кг"},
                    ],
                },
                {
                    "id": "group-empty",
                    "kind": "superset",
                    "title": "Пустая группа",
                    "betweenRoundsRest": "90 сек",
                    "items": [],
                },
            ],
            "selectedExerciseId": "row-1",
        },
    )

    assert save_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "programId": "back-biceps", "selectedExerciseId": "row-1"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    empty_group = next(group for group in payload["groups"] if group["id"] == "group-empty")
    assert empty_group["kind"] == "superset"
    assert empty_group["items"] == []


def test_builder_can_create_empty_custom_program(client: TestClient) -> None:
    create_response = client.post(
        "/api/programs",
        json={
            "userId": "alexey",
            "name": "Новая тренировка",
            "subtitle": "Пустая тренировка",
            "programType": "strength",
            "difficulty": "easy",
            "durationMinutes": 45,
            "exerciseCount": 0,
            "setCount": 0,
            "focusTags": [],
            "description": "Пустая программа для ручной сборки.",
            "structure": {
                "builderGroups": [
                    {
                        "id": "new-group-1",
                        "kind": "single",
                        "title": "Новая группа",
                        "betweenRoundsRest": "90 сек",
                        "items": [],
                    }
                ]
            },
        },
    )

    assert create_response.status_code == 201
    program_id = create_response.json()["id"]

    builder_response = client.get("/api/builder", params={"userId": "alexey", "programId": program_id})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert payload["selectedProgramId"] == program_id
    assert payload["selectedExerciseId"] == ""
    assert payload["info"]["duration"] == ""
    minutes_summary = next(card for card in payload["summaryCards"] if card["label"] == "минут")
    assert minutes_summary["value"] == "0"
    assert payload["groups"] == [
        {
            "id": "new-group-1",
            "kind": "single",
            "title": "Новая группа",
            "rounds": None,
            "betweenExercisesRest": None,
            "betweenRoundsRest": "90 сек",
            "items": [],
        }
    ]
    assert {program["id"] for program in payload["programs"]} >= {"back-biceps", "fullbody-base", "mobility-recovery", program_id}


def test_builder_can_delete_custom_program_without_removing_templates(client: TestClient) -> None:
    create_response = client.post(
        "/api/programs",
        json={
            "userId": "alexey",
            "name": "Временная тренировка",
            "subtitle": "Пустая тренировка",
            "programType": "strength",
            "difficulty": "easy",
            "durationMinutes": 45,
            "focusTags": [],
            "description": "Пустая программа для ручной сборки.",
            "structure": {
                "builderGroups": [
                    {
                        "id": "new-group-1",
                        "kind": "single",
                        "title": "Новая группа",
                        "betweenRoundsRest": "90 сек",
                        "items": [],
                    }
                ]
            },
        },
    )

    program_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/programs/{program_id}", params={"userId": "alexey"})

    assert delete_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey", "programId": "back-biceps"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert {program["id"] for program in payload["programs"]} == {"back-biceps", "fullbody-base", "mobility-recovery"}


def test_builder_can_recreate_deleted_custom_program_without_id_conflict(client: TestClient) -> None:
    create_response = client.post(
        "/api/programs",
        json={
            "userId": "alexey",
            "name": "Новая тренировка",
            "subtitle": "Пустая тренировка",
            "programType": "strength",
            "difficulty": "easy",
            "durationMinutes": 45,
            "focusTags": [],
            "description": "Пустая программа для ручной сборки.",
            "structure": {
                "builderGroups": [
                    {
                        "id": "new-group-1",
                        "kind": "single",
                        "title": "Новая группа",
                        "betweenRoundsRest": "90 сек",
                        "items": [],
                    }
                ]
            },
        },
    )

    assert create_response.status_code == 201
    first_program_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/programs/{first_program_id}", params={"userId": "alexey"})
    assert delete_response.status_code == 200

    recreate_response = client.post(
        "/api/programs",
        json={
            "userId": "alexey",
            "name": "Новая тренировка",
            "subtitle": "Пустая тренировка",
            "programType": "strength",
            "difficulty": "easy",
            "durationMinutes": 45,
            "focusTags": [],
            "description": "Пустая программа для ручной сборки.",
            "structure": {
                "builderGroups": [
                    {
                        "id": "new-group-1",
                        "kind": "single",
                        "title": "Новая группа",
                        "betweenRoundsRest": "90 сек",
                        "items": [],
                    }
                ]
            },
        },
    )

    assert recreate_response.status_code == 201
    assert recreate_response.json()["id"] != first_program_id


def test_builder_creates_empty_custom_program_after_all_programs_were_deleted(client: TestClient) -> None:
    for program_id in ["back-biceps", "fullbody-base", "mobility-recovery"]:
        delete_response = client.delete(f"/api/programs/{program_id}", params={"userId": "alexey"})
        assert delete_response.status_code == 200

    create_response = client.post(
        "/api/programs",
        json={
            "userId": "alexey",
            "name": "Новая тренировка",
            "subtitle": "Пустая тренировка",
            "programType": "strength",
            "difficulty": "easy",
            "durationMinutes": 45,
            "focusTags": [],
            "description": "Пустая программа для ручной сборки.",
            "structure": {
                "builderGroups": [
                    {
                        "id": "new-group-1",
                        "kind": "single",
                        "title": "Новая группа",
                        "betweenRoundsRest": "90 сек",
                        "items": [],
                    }
                ]
            },
        },
    )

    assert create_response.status_code == 201
    program_id = create_response.json()["id"]

    builder_response = client.get("/api/builder", params={"userId": "alexey", "programId": program_id})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert payload["selectedProgramId"] == program_id
    assert payload["selectedExerciseId"] == ""
    assert payload["groups"] == [
        {
            "id": "new-group-1",
            "kind": "single",
            "title": "Новая группа",
            "rounds": None,
            "betweenExercisesRest": None,
            "betweenRoundsRest": "90 сек",
            "items": [],
        }
    ]


def test_builder_can_delete_template_program_only_for_current_user(client: TestClient) -> None:
    delete_response = client.delete("/api/programs/back-biceps", params={"userId": "alexey"})

    assert delete_response.status_code == 200

    alexey_builder = client.get("/api/builder", params={"userId": "alexey"})
    guest_builder = client.get("/api/builder", params={"userId": "guest"})

    assert alexey_builder.status_code == 200
    assert guest_builder.status_code == 200
    assert {program["id"] for program in alexey_builder.json()["programs"]} == {"fullbody-base", "mobility-recovery"}
    assert {program["id"] for program in guest_builder.json()["programs"]} == {"back-biceps", "fullbody-base", "mobility-recovery"}
    assert all(program["canDelete"] for program in alexey_builder.json()["programs"])


def test_builder_can_delete_all_programs_and_returns_empty_state(client: TestClient) -> None:
    for program_id in ["back-biceps", "fullbody-base", "mobility-recovery"]:
        delete_response = client.delete(f"/api/programs/{program_id}", params={"userId": "alexey"})
        assert delete_response.status_code == 200

    builder_response = client.get("/api/builder", params={"userId": "alexey"})

    assert builder_response.status_code == 200
    payload = builder_response.json()
    assert payload["programs"] == []
    assert payload["selectedProgramId"] == ""
    assert payload["groups"] == []
    assert payload["info"]["name"] == "Нет тренировок"
    assert payload["warnings"] == []


def test_runtime_recovery_exercise_does_not_create_fatigue(client: TestClient, db_session) -> None:
    before = db_session.scalars(
        select(MuscleFatigueSnapshot).where(
            MuscleFatigueSnapshot.user_id == "alexey",
            MuscleFatigueSnapshot.muscle_id == "quads",
        )
    ).all()

    response = client.post(
        "/api/runtime/exercises",
        json={
            "userId": "alexey",
            "exerciseSlug": "ankle-circle",
            "exerciseName": "Круги стопой",
            "kind": "bodyweight",
            "orderIndex": 1,
            "status": "completed",
            "startedAt": "2026-05-25T11:00:00Z",
            "finishedAt": "2026-05-25T11:05:00Z",
            "targetSets": 2,
            "trainingMode": "technique_light",
            "muscles": [{"muscleId": "quads", "name": "Квадрицепсы", "role": "primary"}],
            "sets": [
                {"setNumber": 1, "plannedValue": 30, "actualValue": 30, "reps": 30, "tempoLabel": "хорошо", "subjectiveEffort": 4},
                {"setNumber": 2, "plannedValue": 30, "actualValue": 30, "reps": 30, "tempoLabel": "хорошо", "subjectiveEffort": 4},
            ],
        },
    )

    assert response.status_code == 200

    after = db_session.scalars(
        select(MuscleFatigueSnapshot).where(
            MuscleFatigueSnapshot.user_id == "alexey",
            MuscleFatigueSnapshot.muscle_id == "quads",
        )
    ).all()

    assert before == []
    assert after == []
