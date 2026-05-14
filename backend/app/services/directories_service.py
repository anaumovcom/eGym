from app.models.enums import AccessRole, DriveState, MachineState, SafetyState, UserAccent
from app.schemas.directory import CommonDirectoriesSchema, DirectoryItemSchema


class DirectoriesService:
    def get_common_directories(self) -> CommonDirectoriesSchema:
        return CommonDirectoriesSchema(
            roles=self._items(
                {
                    AccessRole.member.value: "Пользователь",
                    AccessRole.coach.value: "Тренер",
                    AccessRole.admin.value: "Администратор",
                    AccessRole.service.value: "Сервис",
                }
            ),
            accents=self._items({UserAccent.gold.value: "Gold", UserAccent.green.value: "Green"}),
            machine_states=self._items(
                {
                    MachineState.ready.value: "Тренажёр готов",
                    MachineState.warning.value: "Требуется внимание",
                    MachineState.blocked.value: "Тренажёр заблокирован",
                }
            ),
            drive_states=self._items(
                {
                    DriveState.connected.value: "Подключён",
                    DriveState.warning.value: "Предупреждение",
                    DriveState.error.value: "Ошибка",
                }
            ),
            safety_states=self._items(
                {
                    SafetyState.enabled.value: "Безопасность включена",
                    SafetyState.disabled.value: "Безопасность отключена",
                    SafetyState.emergency_stop.value: "Аварийная остановка",
                }
            ),
        )

    @staticmethod
    def _items(values: dict[str, str]) -> list[DirectoryItemSchema]:
        return [DirectoryItemSchema(value=value, label=label) for value, label in values.items()]
