from app.schemas.training import BuilderExerciseItemSchema, BuilderStrengthSetPlanSchema
from app.services.exercise_library import get_imported_exercise
from app.services.workout_duration import (
    BENCH_ADJUST_SECONDS,
    BENCH_MOVE_SECONDS,
    DISTRACTION_SECONDS,
    TRANSITION_SECONDS,
    bench_position,
    estimate_workout_duration,
    transition_seconds,
)


def item(slug: str, sets: str = "3×10", load: str = "20 кг", rest: str = "90 сек", **extra: object) -> BuilderExerciseItemSchema:
    load_type = extra.pop("load_type", "timed" if "сек" in sets else "weighted")
    return BuilderExerciseItemSchema(id=slug, slug=slug, name=slug, muscle_group="", sets=sets, rest=rest, load=load, load_type=load_type, **extra)


def plan(reps: str, weight: str, rir: str, rest: int = 90, set_type: str = "work") -> BuilderStrengthSetPlanSchema:
    return BuilderStrengthSetPlanSchema(
        set_number=1, set_type=set_type, label="", target_reps_label=reps, recommended_weight_label=weight,
        rest_seconds=rest, rir_label=rir, note="",
    )


def test_bench_position_is_read_from_slug_and_steps() -> None:
    def position(slug: str) -> str:
        return bench_position(get_imported_exercise(slug), slug)

    assert position("smith-machine-bench-press") == "flat"
    assert position("smith-machine-incline-bench-press") == "incline"
    assert position("smith-machine-seated-overhead-press") == "seated"
    assert position("smith-machine-skullcrusher") == "flat"
    assert position("smith-machine-squat") == "none"
    assert position("cardio-quick-feet") == "none"


def test_transitions_charge_for_moving_and_adjusting_the_bench() -> None:
    squat, bench, incline = item("smith-machine-squat"), item("smith-machine-bench-press"), item("smith-machine-incline-bench-press")
    base = TRANSITION_SECONDS["weighted"] + DISTRACTION_SECONDS

    assert transition_seconds(None, squat) == TRANSITION_SECONDS["weighted"]
    assert transition_seconds(None, bench) == TRANSITION_SECONDS["weighted"] + BENCH_MOVE_SECONDS
    assert transition_seconds(squat, bench) == base + BENCH_MOVE_SECONDS
    assert transition_seconds(bench, incline) == base + BENCH_ADJUST_SECONDS
    assert transition_seconds(bench, bench) < base
    # Floor cardio → Smith machine is also a walk to another station.
    assert transition_seconds(item("cardio-quick-feet", sets="1×45 сек"), squat) > base


def test_ordering_that_keeps_the_bench_in_place_is_faster() -> None:
    squat, bench, incline, row = (item(slug) for slug in (
        "smith-machine-squat", "smith-machine-bench-press", "smith-machine-incline-bench-press", "smith-machine-overhand-row",
    ))

    grouped = estimate_workout_duration([squat, row, bench, incline])
    scattered = estimate_workout_duration([bench, squat, incline, row])

    assert grouped.work_seconds == scattered.work_seconds
    assert grouped.transition_seconds < scattered.transition_seconds


def test_heavier_sets_take_longer_than_light_sets_with_the_same_reps() -> None:
    def seconds(weight: str, rir: str) -> int:
        return estimate_workout_duration([item("smith-machine-squat", strength_plan=[plan("6", weight, rir)] * 3)]).total_seconds

    assert seconds("100 кг", "0") > seconds("100 кг", "3") > seconds("60 кг", "6")


def test_history_e1rm_makes_the_planned_weight_lighter_but_never_heavier() -> None:
    squat = item("smith-machine-squat", strength_plan=[plan("10", "60 кг", "2")] * 3)
    planned = estimate_workout_duration([squat])

    assert estimate_workout_duration([squat], e1rm_by_slug={squat.slug: 140}).work_seconds < planned.work_seconds
    assert estimate_workout_duration([squat], e1rm_by_slug={squat.slug: 40}) == planned


def test_rest_counts_only_between_sets_with_overrun() -> None:
    estimate = estimate_workout_duration([item("smith-machine-squat", sets="3×10", rest="120 сек")])

    assert 240 < estimate.rest_seconds < 300


def test_tempo_per_side_and_timed_sets() -> None:
    curl = item("smith-machine-drag-curl", sets="3×12", load="10 кг")
    normal = estimate_workout_duration([curl]).work_seconds

    assert estimate_workout_duration([curl], tempo_by_slug={curl.slug: "Контроль эксцентрики"}).work_seconds > normal
    assert estimate_workout_duration([curl.model_copy(update={"per_side": True})]).work_seconds > 2 * normal
    quick_feet = estimate_workout_duration([item("cardio-quick-feet", sets="2×60 сек", load="вес тела", rest="30 сек")])
    assert quick_feet.work_seconds >= 120 and 30 <= quick_feet.rest_seconds < 45


def test_failure_set_without_reps_inherits_previous_target() -> None:
    sets = [plan("8–12", "40 кг", "1"), plan("максимум", "40 кг", "0", set_type="failure")]
    estimate = estimate_workout_duration([item("smith-machine-bench-press", strength_plan=sets)])

    assert estimate.work_seconds > 2 * 10 * 2.8


def test_empty_workout_has_no_duration() -> None:
    assert estimate_workout_duration([]).minutes == 0
