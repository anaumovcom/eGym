from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.analytics import MuscleFatigueEvent, MuscleFatigueSnapshot, ProgressPhoto, WorkoutSession
from app.models.audit import AuditLog
from app.models.enums import (
    AccessRole,
    AuditAction,
    AuditSeverity,
    DriveState,
    FatigueEventSource,
    GoalType,
    MachineState,
    MuscleRole,
    RuntimePhotoMode,
    RuntimePhotoView,
    SafetySeverity,
    SafetyState,
    UserAccent,
)
from app.models.machine import DriveStatusSnapshot, MachineStatusSnapshot, SafetyEvent
from app.models.profile import BodyMeasurement, UserGoal, UserProfile
from app.models.settings import AppSetting
from app.models.user import User


def seed_dev_data(session: Session) -> None:
    existing_user = session.scalar(select(User.id).limit(1))
    if existing_user is not None:
        return

    now = datetime.now(UTC)
    users = [
        User(
            id="alexey",
            name="Алексей",
            role=AccessRole.member,
            is_active=True,
            is_current=True,
            readiness_percent=78,
            last_workout="Вчера — грудь и трицепс",
            today_focus="спина или лёгкая тренировка",
            week_progress="+4% к объёму",
            accent=UserAccent.gold,
        ),
        User(
            id="elena",
            name="Елена",
            role=AccessRole.member,
            is_active=True,
            is_current=False,
            readiness_percent=84,
            last_workout="12 мая — ноги",
            today_focus="верх тела",
            week_progress="+3% к стабильности",
            accent=UserAccent.green,
        ),
    ]
    session.add_all(users)
    session.flush()

    profiles = [
        UserProfile(
            user_id="alexey",
            birth_date=date(1991, 6, 12),
            height_cm=182,
            weight_kg=84.2,
            photo_url=None,
            notes="Возвращение к плановому объёму",
        ),
        UserProfile(
            user_id="elena",
            birth_date=date(1994, 2, 3),
            height_cm=168,
            weight_kg=61.8,
            photo_url=None,
            notes="Контроль техники ног и стабилизации",
        ),
    ]
    session.add_all(profiles)

    session.add_all(
        [
            UserGoal(
                user_id="alexey",
                goal_type=GoalType.strength,
                label="Подтянуть тягу сверху",
                target_value=55,
                target_unit="кг",
                is_primary=True,
            ),
            UserGoal(
                user_id="alexey",
                goal_type=GoalType.habit,
                label="3 тренировки в неделю",
                target_value=3,
                target_unit="сессии",
                is_primary=False,
            ),
            UserGoal(
                user_id="elena",
                goal_type=GoalType.body_composition,
                label="Снизить жировую массу",
                target_value=19,
                target_unit="%",
                is_primary=True,
            ),
            UserGoal(
                user_id="elena",
                goal_type=GoalType.strength,
                label="Удерживать присед",
                target_value=70,
                target_unit="кг",
                is_primary=False,
            ),
        ]
    )

    session.add_all(
        [
            BodyMeasurement(
                user_id="alexey",
                measured_at=now - timedelta(days=14),
                weight_kg=85.1,
                body_fat_percent=18.4,
                chest_cm=108.0,
                waist_cm=88.0,
                hips_cm=98.0,
            ),
            BodyMeasurement(
                user_id="alexey",
                measured_at=now - timedelta(days=1),
                weight_kg=84.2,
                body_fat_percent=17.9,
                chest_cm=108.4,
                waist_cm=87.0,
                hips_cm=98.0,
            ),
            BodyMeasurement(
                user_id="elena",
                measured_at=now - timedelta(days=12),
                weight_kg=62.4,
                body_fat_percent=24.1,
                chest_cm=92.0,
                waist_cm=71.4,
                hips_cm=99.3,
            ),
            BodyMeasurement(
                user_id="elena",
                measured_at=now - timedelta(days=1),
                weight_kg=61.8,
                body_fat_percent=23.6,
                chest_cm=92.1,
                waist_cm=70.8,
                hips_cm=98.9,
            ),
        ]
    )

    session.add_all(
        [
            AppSetting(user_id=None, key="safety.prompts", value={"audio": True}),
            AppSetting(user_id="alexey", key="dashboard.defaultScenario", value={"scenario": "default"}),
            AppSetting(user_id="elena", key="dashboard.defaultScenario", value={"scenario": "default"}),
        ]
    )

    ready_snapshot = MachineStatusSnapshot(
        scenario_name="ready",
        machine_state=MachineState.ready,
        machine_label="Тренажёр готов",
        calibration="Калибровка: перед упражнением",
        captured_at=now - timedelta(minutes=5),
    )
    warning_snapshot = MachineStatusSnapshot(
        scenario_name="warning",
        machine_state=MachineState.warning,
        machine_label="Требуется внимание",
        calibration="Калибровка: рекомендуется перед стартом",
        captured_at=now - timedelta(minutes=3),
    )
    blocked_snapshot = MachineStatusSnapshot(
        scenario_name="blocked",
        machine_state=MachineState.blocked,
        machine_label="Тренажёр заблокирован",
        calibration="Калибровка недоступна до сервисной проверки",
        captured_at=now - timedelta(minutes=1),
    )
    session.add_all([ready_snapshot, warning_snapshot, blocked_snapshot])
    session.flush()

    session.add_all(
        [
            DriveStatusSnapshot(
                machine_status_id=ready_snapshot.id, side="left", drive_state=DriveState.connected, message="Норма"
            ),
            DriveStatusSnapshot(
                machine_status_id=ready_snapshot.id, side="right", drive_state=DriveState.connected, message="Норма"
            ),
            DriveStatusSnapshot(
                machine_status_id=warning_snapshot.id, side="left", drive_state=DriveState.connected, message="Норма"
            ),
            DriveStatusSnapshot(
                machine_status_id=warning_snapshot.id,
                side="right",
                drive_state=DriveState.warning,
                message="Датчик люфта требует внимания",
            ),
            DriveStatusSnapshot(
                machine_status_id=blocked_snapshot.id, side="left", drive_state=DriveState.connected, message="Норма"
            ),
            DriveStatusSnapshot(
                machine_status_id=blocked_snapshot.id,
                side="right",
                drive_state=DriveState.error,
                message="Сервисная ошибка привода",
            ),
        ]
    )

    session.add(
        SafetyEvent(
            machine_status_id=blocked_snapshot.id,
            safety_state=SafetyState.emergency_stop,
            severity=SafetySeverity.critical,
            title="Ошибка правого привода",
            description="Старт тренировки блокируется, пока не будет завершена сервисная проверка оборудования.",
            is_active=True,
            created_at=now - timedelta(minutes=1),
            cleared_at=None,
        )
    )

    session.add(
        AuditLog(
            actor_user_id="alexey",
            action=AuditAction.user_selected,
            target_type="user",
            target_id="alexey",
            severity=AuditSeverity.info,
            details={"seed": True},
            created_at=now - timedelta(minutes=10),
        )
    )

    session.commit()


def seed_stage7_data(session: Session) -> None:
    if session.scalar(select(User.id).limit(1)) is None:
        return
    if session.scalar(select(WorkoutSession.id).limit(1)) is not None:
        return

    now = datetime.now(UTC)
    settings = get_settings()
    media_root = Path(settings.media_root)
    media_root.mkdir(parents=True, exist_ok=True)

    workout = WorkoutSession(
        user_id="alexey",
        source="today",
        title="Силовая верх тела",
        subtitle="Грудь, спина, трицепс",
        status="completed",
        started_at=now - timedelta(hours=2),
        finished_at=now - timedelta(hours=1, minutes=18),
        duration_seconds=42 * 60,
        feeling="hard",
        discomfort="none",
        notes="Seeded stage 7 workout",
    )
    session.add(workout)
    session.flush()

    snapshots = [
        MuscleFatigueSnapshot(
            user_id="alexey",
            muscle_id="back",
            fatigue_score=7.0,
            calculated_at=now,
            recovery_half_life_hours=24.0,
            last_load_at=now - timedelta(hours=20),
        ),
        MuscleFatigueSnapshot(
            user_id="alexey",
            muscle_id="chest",
            fatigue_score=72.0,
            calculated_at=now,
            recovery_half_life_hours=24.0,
            last_load_at=now - timedelta(hours=8),
        ),
        MuscleFatigueSnapshot(
            user_id="alexey",
            muscle_id="triceps",
            fatigue_score=150.0,
            calculated_at=now,
            recovery_half_life_hours=24.0,
            last_load_at=now - timedelta(hours=2),
        ),
    ]
    session.add_all(snapshots)
    session.add_all(
        [
            MuscleFatigueEvent(
                user_id="alexey",
                muscle_id="back",
                source=FatigueEventSource.exercise_set,
                workout_session_id=workout.id,
                occurred_at=now - timedelta(hours=20),
                fatigue_delta=7.0,
                role=MuscleRole.secondary,
                recovery_half_life_hours=24.0,
                note="Тяга сверху",
            ),
            MuscleFatigueEvent(
                user_id="alexey",
                muscle_id="chest",
                source=FatigueEventSource.exercise_set,
                workout_session_id=workout.id,
                occurred_at=now - timedelta(hours=8),
                fatigue_delta=72.0,
                role=MuscleRole.primary,
                recovery_half_life_hours=24.0,
                note="Жим с пола",
            ),
            MuscleFatigueEvent(
                user_id="alexey",
                muscle_id="triceps",
                source=FatigueEventSource.exercise_set,
                workout_session_id=workout.id,
                occurred_at=now - timedelta(hours=2),
                fatigue_delta=150.0,
                role=MuscleRole.primary,
                recovery_half_life_hours=24.0,
                note="Разгибание на блоке",
            ),
        ]
    )

    photo_dir = media_root / "progress-photos" / "alexey"
    thumb_dir = photo_dir / "thumbs"
    photo_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    photo_specs = [
        ("front", now - timedelta(days=28)),
        ("side", now - timedelta(days=28)),
        ("front", now - timedelta(days=1)),
    ]
    for view, taken_at in photo_specs:
        file_name = f"seed-{view}-{taken_at.strftime('%Y%m%d')}.png"
        photo_path = photo_dir / file_name
        thumb_path = thumb_dir / file_name
        if not photo_path.exists():
            Image.new("RGB", (480, 720), color=(220, 228, 235)).save(photo_path)
        if not thumb_path.exists():
            Image.new("RGB", (240, 360), color=(200, 208, 215)).save(thumb_path)
        session.add(
            ProgressPhoto(
                user_id="alexey",
                workout_session_id=workout.id,
                mode=RuntimePhotoMode.manual,
                view=RuntimePhotoView(view),
                taken_at=taken_at,
                storage_path=str(photo_path.relative_to(media_root)),
                thumbnail_path=str(thumb_path.relative_to(media_root)),
                mime_type="image/png",
                file_size=photo_path.stat().st_size,
                width=480,
                height=720,
                note="Seeded photo",
            )
        )

    session.commit()
