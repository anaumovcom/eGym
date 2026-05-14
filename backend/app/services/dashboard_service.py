from typing import TypedDict

from sqlalchemy.orm import Session

from app.models.enums import NotificationTone
from app.repositories.user_repository import UserRepository
from app.schemas.dashboard import (
    DashboardAlertSchema,
    DashboardDataSchema,
    DashboardProgressMetricSchema,
    DashboardQuickStartItemSchema,
    DashboardRecommendationSchema,
    DashboardWorkoutSchema,
    MuscleCardSchema,
)
from app.services.machine_service import MachineService


class DashboardProfile(TypedDict):
    greeting: str
    recommendation_title: str
    recommendation_text: str
    readiness_percent: int


class DashboardService:
    def __init__(self) -> None:
        self.user_repository = UserRepository()
        self.machine_service = MachineService()

    def get_dashboard(
        self,
        session: Session,
        user_id: str,
        scenario_name: str | None = None,
    ) -> DashboardDataSchema:
        user = self.user_repository.get_user(session, user_id)
        if user is None:
            raise LookupError(f"Unknown user: {user_id}")

        machine = self.machine_service.get_machine_health(session, self._machine_scenario(scenario_name))
        profile = self._profile_copy(user_id, user.readiness_percent)
        base_dashboard = DashboardDataSchema(
            greeting=profile["greeting"],
            recommendation_title=profile["recommendation_title"],
            recommendation_text=profile["recommendation_text"],
            readiness_percent=profile["readiness_percent"],
            today_workout=DashboardWorkoutSchema(
                title="Спина + бицепс",
                exercises=5,
                sets=18,
                duration="45 минут",
                list=["Тяга сверху", "Тяга к поясу", "Сгибание рук", "Тяга прямыми руками", "Планка"],
            ),
            machine=machine,
            alerts=[],
            recommended_exercises=[
                DashboardRecommendationSchema(name="Тяга сверху", muscles="Спина, бицепс", status="Рекомендуется"),
                DashboardRecommendationSchema(name="Тяга к поясу", muscles="Спина", status="Рекомендуется"),
                DashboardRecommendationSchema(name="Сгибание рук", muscles="Бицепс", status="Можно выполнить"),
            ],
            quick_start=[
                DashboardQuickStartItemSchema(name="Жим лёжа", stats="40 кг × 10 × 3", last="2 дн. назад"),
                DashboardQuickStartItemSchema(name="Присед", stats="60 кг × 10 × 3", last="3 дн. назад"),
                DashboardQuickStartItemSchema(name="Тяга сверху", stats="45 кг × 10 × 3", last="5 дн. назад"),
            ],
            progress=[
                DashboardProgressMetricSchema(label="тренировок за месяц", value="8"),
                DashboardProgressMetricSchema(label="недели подряд", value="3"),
                DashboardProgressMetricSchema(label="к объёму за неделю", value="+4%"),
                DashboardProgressMetricSchema(label="кг за месяц", value="-1.2"),
            ],
            muscles=[
                MuscleCardSchema(name="Грудь", status="high", score=72),
                MuscleCardSchema(name="Трицепс", status="medium", score=41),
                MuscleCardSchema(name="Плечи", status="medium", score=36),
                MuscleCardSchema(name="Спина", status="ready", score=9),
                MuscleCardSchema(name="Бицепс", status="light", score=18),
                MuscleCardSchema(name="Предплечья", status="ready", score=6),
                MuscleCardSchema(name="Пресс", status="light", score=14),
                MuscleCardSchema(name="Ягодицы", status="ready", score=7),
                MuscleCardSchema(name="Ноги", status="ready", score=12),
            ],
        )
        return self._apply_scenario(base_dashboard, scenario_name)

    @staticmethod
    def _machine_scenario(scenario_name: str | None) -> str | None:
        if scenario_name == "machine-warning":
            return "warning"
        if scenario_name == "drive-error":
            return "blocked"
        return "ready"

    @staticmethod
    def _profile_copy(user_id: str, readiness_percent: int) -> DashboardProfile:
        profiles: dict[str, DashboardProfile] = {
            "alexey": {
                "greeting": "Добрый день, Алексей",
                "recommendation_title": "Сегодня лучше: Спина + бицепс",
                "recommendation_text": "Грудь и трицепс ещё восстанавливаются после прошлой тренировки. Ноги готовы к умеренной нагрузке.",
                "readiness_percent": readiness_percent,
            },
            "elena": {
                "greeting": "Добрый день, Елена",
                "recommendation_title": "Сегодня лучше: Верх тела",
                "recommendation_text": "Ноги ещё утомлены после прошлой сессии. Верх тела готов к плановой нагрузке и контролю техники.",
                "readiness_percent": readiness_percent,
            },
            "guest": {
                "greeting": "Добро пожаловать",
                "recommendation_title": "Сегодня лучше: Быстрый старт",
                "recommendation_text": "Гостевой режим не использует персональную историю. Можно выбрать упражнение из каталога и начать тренировку на моках.",
                "readiness_percent": readiness_percent,
            },
        }
        return profiles.get(user_id, profiles["alexey"])

    def _apply_scenario(self, dashboard: DashboardDataSchema, scenario_name: str | None) -> DashboardDataSchema:
        if scenario_name == "no-workout":
            dashboard.recommendation_title = "Сегодня лучше: Выбрать новый старт"
            dashboard.recommendation_text = "На сегодня не найдено сохранённой тренировки. Можно перейти в быстрый старт или открыть каталог упражнений."
            dashboard.today_workout = None
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.warning,
                    title="План на сегодня не найден",
                    description="Backend показывает состояние без назначенной тренировки, но с доступным быстрым стартом.",
                )
            ]
        elif scenario_name == "high-fatigue":
            dashboard.readiness_percent = 34
            dashboard.recommendation_title = "Сегодня лучше: Восстановление"
            dashboard.recommendation_text = "Уровень усталости слишком высок для полноценной силовой тренировки. Рекомендуется облегчённая сессия или отдых."
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.blocked,
                    title="Высокая усталость мышц",
                    description="Старт силовой тренировки должен быть пересмотрен.",
                )
            ]
            dashboard.muscles = [
                MuscleCardSchema(name="Грудь", status="critical", score=128),
                MuscleCardSchema(name="Трицепс", status="high", score=94),
                MuscleCardSchema(name="Плечи", status="high", score=88),
                MuscleCardSchema(name="Спина", status="medium", score=41),
                MuscleCardSchema(name="Бицепс", status="medium", score=39),
                MuscleCardSchema(name="Предплечья", status="light", score=20),
                MuscleCardSchema(name="Пресс", status="light", score=18),
                MuscleCardSchema(name="Ягодицы", status="medium", score=36),
                MuscleCardSchema(name="Ноги", status="high", score=91),
            ]
        elif scenario_name == "machine-warning":
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.warning,
                    title="Требуется внимание к приводу",
                    description="Правый привод сообщает предупреждение перед началом упражнения.",
                )
            ]
        elif scenario_name == "drive-error":
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.blocked,
                    title="Ошибка правого привода",
                    description="Старт тренировки блокируется, пока не будет завершена сервисная проверка оборудования.",
                )
            ]
        return dashboard
