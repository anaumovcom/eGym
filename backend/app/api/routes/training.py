from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.exercise import ExerciseCatalogResponseSchema, ExerciseDetailsSchema
from app.schemas.training import (
    BuilderPlanMutationSchema,
    ProgramMutationResultSchema,
    ProgramMutationSchema,
    ProgramLibraryDataSchema,
    QuickStartDataSchema,
    StrengthTrainingModeSchema,
    TodayWorkoutPlanMutationSchema,
    TrainingPlanMutationResultSchema,
    TodayWorkoutDataSchema,
    WorkoutBuilderDataSchema,
    WorkoutCalendarDataSchema,
)
from app.services.training_service import TrainingService

router = APIRouter()

training_service = TrainingService()


def _csv_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


@router.get("/exercises", response_model=ExerciseCatalogResponseSchema)
def list_exercises(
    user_id: str = Query("alexey", alias="userId"),
    search: str | None = Query(default=None),
    muscles: str | None = Query(default=None),
    equipment: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    force: str | None = Query(default=None),
    mechanic: str | None = Query(default=None),
    grips: str | None = Query(default=None),
    favorites: str | None = Query(default=None),
    blacklist: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ExerciseCatalogResponseSchema:
    return training_service.get_exercise_catalog(
        session,
        user_id=user_id,
        search=search,
        muscles=_csv_list(muscles),
        equipment=_csv_list(equipment),
        difficulty=_csv_list(difficulty),
        force=_csv_list(force),
        mechanic=_csv_list(mechanic),
        grips=_csv_list(grips),
        favorites=_csv_list(favorites),
        blacklist=_csv_list(blacklist),
    )


@router.get("/exercises/{slug}", response_model=ExerciseDetailsSchema)
def get_exercise_details(
    slug: str,
    user_id: str = Query("alexey", alias="userId"),
    favorites: str | None = Query(default=None),
    blacklist: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ExerciseDetailsSchema:
    return training_service.get_exercise_details(
        session,
        user_id=user_id,
        slug=slug,
        favorites=_csv_list(favorites),
        blacklist=_csv_list(blacklist),
    )


@router.get("/quick-start", response_model=QuickStartDataSchema)
def get_quick_start(
    user_id: str = Query("alexey", alias="userId"),
    selected: str | None = Query(default=None),
    favorites: str | None = Query(default=None),
    blacklist: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> QuickStartDataSchema:
    return training_service.get_quick_start(
        session,
        user_id=user_id,
        selected=selected,
        favorites=_csv_list(favorites),
        blacklist=_csv_list(blacklist),
    )


@router.get("/today", response_model=TodayWorkoutDataSchema)
def get_today_workout(
    user_id: str = Query("alexey", alias="userId"),
    scenario: str = Query("planned"),
    selected: str | None = Query(default=None),
    favorites: str | None = Query(default=None),
    blacklist: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> TodayWorkoutDataSchema:
    return training_service.get_today_workout(
        session,
        user_id=user_id,
        scenario=scenario,
        selected=selected,
        favorites=_csv_list(favorites),
        blacklist=_csv_list(blacklist),
    )


@router.get("/programs", response_model=ProgramLibraryDataSchema)
def get_programs(
    selected: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ProgramLibraryDataSchema:
    return training_service.get_program_library(session, selected_program_id=selected)


@router.post("/programs", response_model=ProgramMutationResultSchema, status_code=status.HTTP_201_CREATED)
def create_program(
    payload: ProgramMutationSchema,
    session: Session = Depends(get_session),
) -> ProgramMutationResultSchema:
    return training_service.create_program(session, payload)


@router.delete("/programs/{program_id}", response_model=ProgramMutationResultSchema)
def delete_program(
    program_id: str,
    user_id: str = Query("alexey", alias="userId"),
    session: Session = Depends(get_session),
) -> ProgramMutationResultSchema:
    deleted = training_service.delete_program(session, program_id=program_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return ProgramMutationResultSchema(id=program_id, status="deleted")


@router.get("/calendar", response_model=WorkoutCalendarDataSchema)
def get_calendar(
    mode: str = Query("month"),
    selected_day_id: str | None = Query(default=None, alias="selectedDayId"),
    session: Session = Depends(get_session),
) -> WorkoutCalendarDataSchema:
    return training_service.get_calendar(session, mode=mode, selected_day_id=selected_day_id)


@router.get("/builder", response_model=WorkoutBuilderDataSchema)
def get_builder(
    user_id: str = Query("alexey", alias="userId"),
    program_id: str | None = Query(default=None, alias="programId"),
    selected_exercise_id: str | None = Query(default=None, alias="selectedExerciseId"),
    session: Session = Depends(get_session),
) -> WorkoutBuilderDataSchema:
    return training_service.get_builder(session, user_id=user_id, program_id=program_id, selected_exercise_id=selected_exercise_id)


@router.get("/strength-modes", response_model=list[StrengthTrainingModeSchema])
def get_strength_modes() -> list[StrengthTrainingModeSchema]:
    return training_service.get_strength_modes()


@router.put("/today/plan", response_model=TrainingPlanMutationResultSchema)
def save_today_workout_plan(
    payload: TodayWorkoutPlanMutationSchema,
    session: Session = Depends(get_session),
) -> TrainingPlanMutationResultSchema:
    return training_service.save_today_workout_plan(session, payload)


@router.put("/builder/plan", response_model=TrainingPlanMutationResultSchema)
def save_builder_plan(
    payload: BuilderPlanMutationSchema,
    session: Session = Depends(get_session),
) -> TrainingPlanMutationResultSchema:
    return training_service.save_builder_plan(session, payload)
