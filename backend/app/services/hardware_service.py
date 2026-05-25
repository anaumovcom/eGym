from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import AuditAction, AuditSeverity, DriveState, MachineState, SafetyState
from app.models.hardware import ExerciseCalibration, HardwareDiagnosticRecord
from app.models.settings import AppSetting
from app.schemas.hardware import (
    CalibrationListResponseSchema,
    CalibrationSaveSchema,
    CalibrationSummarySchema,
    HardwareCommandRequestSchema,
    HardwareCommandResponseSchema,
    HardwareDiagnosticRecordSchema,
    HardwareSafetySettingsSchema,
    HardwareSnapshotSchema,
    SafetyGateCheckSchema,
    SafetyGateRequestSchema,
    SafetyGateResponseSchema,
)
from app.schemas.machine import MachineHealthSchema, SafetyStatusSchema
from app.services.hardware_runtime import hardware_runtime
from app.repositories.audit_repository import AuditRepository
from app.repositories.settings_repository import SettingsRepository


class HardwareService:
    def __init__(self) -> None:
        self.audit_repository = AuditRepository()
        self.settings_repository = SettingsRepository()

    def get_snapshot(self, session: Session, user_id: str | None = None) -> HardwareSnapshotSchema:
        if user_id:
            hardware_runtime.set_selected_user(user_id, broadcast=False)
        return HardwareSnapshotSchema.model_validate(hardware_runtime.snapshot_payload())

    def list_calibrations(self, session: Session, user_id: str) -> CalibrationListResponseSchema:
        statement = (
            select(ExerciseCalibration)
            .where(ExerciseCalibration.user_id == user_id, ExerciseCalibration.is_active.is_(True))
            .order_by(ExerciseCalibration.captured_at.desc())
        )
        rows = list(session.scalars(statement))
        return CalibrationListResponseSchema(items=[CalibrationSummarySchema.model_validate(row) for row in rows])

    def get_current_calibration(self, session: Session, user_id: str, exercise_slug: str) -> ExerciseCalibration | None:
        statement = (
            select(ExerciseCalibration)
            .where(
                ExerciseCalibration.user_id == user_id,
                ExerciseCalibration.exercise_slug == exercise_slug,
                ExerciseCalibration.is_active.is_(True),
            )
            .order_by(ExerciseCalibration.captured_at.desc())
        )
        return session.scalars(statement).first()

    def save_calibration(self, session: Session, payload: CalibrationSaveSchema) -> CalibrationSummarySchema:
        calibration = session.scalars(
            select(ExerciseCalibration)
            .where(
                ExerciseCalibration.user_id == payload.user_id,
                ExerciseCalibration.exercise_slug == payload.exercise_slug,
            )
            .order_by(ExerciseCalibration.captured_at.desc())
        ).first()
        if calibration is None:
            calibration = ExerciseCalibration(
                user_id=payload.user_id,
                exercise_slug=payload.exercise_slug,
                lower_point_mm=payload.lower_point_mm,
                upper_point_mm=payload.upper_point_mm,
                zero_position_mm=payload.zero_position_mm,
                movement_range_confirmed=payload.movement_range_confirmed,
                calibration_required=payload.calibration_required,
                is_active=True,
                captured_at=datetime.now(UTC),
                expires_at=payload.expires_at,
                note=payload.note,
            )
            session.add(calibration)
        else:
            calibration.lower_point_mm = payload.lower_point_mm
            calibration.upper_point_mm = payload.upper_point_mm
            calibration.zero_position_mm = payload.zero_position_mm
            calibration.movement_range_confirmed = payload.movement_range_confirmed
            calibration.calibration_required = payload.calibration_required
            calibration.captured_at = datetime.now(UTC)
            calibration.expires_at = payload.expires_at
            calibration.note = payload.note
            calibration.is_active = True
        session.flush()
        self.audit_repository.record(
            session,
            actor_user_id=payload.user_id,
            action=AuditAction.calibration_saved,
            target_type="calibration",
            target_id=str(calibration.id),
            severity=AuditSeverity.info,
            details={"exerciseSlug": payload.exercise_slug, "lowerPointMm": payload.lower_point_mm, "upperPointMm": payload.upper_point_mm},
        )
        session.commit()
        hardware_runtime.set_calibration_state(calibration.id, payload.calibration_required, True)
        return CalibrationSummarySchema.model_validate(calibration)

    def delete_calibration(self, session: Session, calibration_id: int, actor_user_id: str | None, confirm: bool) -> None:
        if not confirm:
            raise ValueError("Deletion must be confirmed")
        calibration = session.get(ExerciseCalibration, calibration_id)
        if calibration is None:
            raise LookupError("Calibration not found")
        calibration.is_active = False
        session.flush()
        self.audit_repository.record(
            session,
            actor_user_id=actor_user_id,
            action=AuditAction.calibration_deleted,
            target_type="calibration",
            target_id=str(calibration_id),
            severity=AuditSeverity.warning,
            details={"exerciseSlug": calibration.exercise_slug},
        )
        session.commit()
        hardware_runtime.set_calibration_state(None, calibration.calibration_required, False)

    def evaluate_safety_gate(self, session: Session, payload: SafetyGateRequestSchema) -> SafetyGateResponseSchema:
        runtime = self.get_snapshot(session, payload.user_id)
        settings = self._get_safety_settings(session, payload.user_id)
        calibration = self.get_current_calibration(session, payload.user_id or "", payload.exercise_slug) if payload.user_id else None
        checks = [
            self._check("user-selected", "Пользователь выбран", payload.user_id is not None and payload.user_id != "", "critical", "Пользователь выбран" if payload.user_id else "Сначала выберите пользователя."),
            self._check("safety-enabled", "Безопасность включена", runtime.safety.state == SafetyState.enabled, "critical", "Безопасность активна" if runtime.safety.state == SafetyState.enabled else "Система безопасности выключена."),
            self._check("estop", "СТОП не активен", runtime.safety.state != SafetyState.emergency_stop, "critical", "Аварийная остановка не активна" if runtime.safety.state != SafetyState.emergency_stop else "Сначала снимите аварийную остановку."),
            self._check("drives", "Оба привода доступны", all(drive.connected and drive.status != "error" for drive in runtime.drives), "critical", "Приводы доступны" if all(drive.connected and drive.status != "error" for drive in runtime.drives) else "Есть ошибка подключения или состояния привода."),
            self._check("critical-errors", "Нет критических ошибок", runtime.machine.machine_state != MachineState.blocked, "critical", "Критических ошибок нет" if runtime.machine.machine_state != MachineState.blocked else "Тренажёр заблокирован критической ошибкой."),
            self._check("calibration", "Калибровка актуальна", not payload.calibration_required or (calibration is not None and self._is_calibration_actual(calibration)), "critical", "Калибровка найдена" if not payload.calibration_required or calibration is not None else "Для запуска нужна актуальная калибровка."),
            self._check("range", "Диапазон подтверждён", (not payload.calibration_required) or payload.range_confirmed or bool(calibration and calibration.movement_range_confirmed), "warning", "Диапазон движения подтверждён" if (not payload.calibration_required) or payload.range_confirmed or bool(calibration and calibration.movement_range_confirmed) else "Подтвердите диапазон движения."),
            self._check("weight", "Нагрузка допустима", payload.weight_kg <= self._parse_kg(settings.max_load), "critical", "Нагрузка допустима" if payload.weight_kg <= self._parse_kg(settings.max_load) else f"Превышен лимит нагрузки {settings.max_load}."),
            self._check("service-mode", "Сервисный режим не конфликтует", not runtime.service_mode, "critical", "Сервисный режим не активен" if not runtime.service_mode else "Отключите сервисный режим перед тренировкой."),
            self._check("limits", "Лимиты движения не нарушены", 0 <= runtime.motion.bar_position_mm <= 2100, "critical", "Позиция в пределах лимитов" if 0 <= runtime.motion.bar_position_mm <= 2100 else "Текущая позиция вне безопасного диапазона."),
        ]
        blocking_reasons = [check.message for check in checks if not check.passed and check.severity == "critical"]
        return SafetyGateResponseSchema(
            allowed=not blocking_reasons,
            checks=checks,
            blocking_reasons=blocking_reasons,
            calibration_id=calibration.id if calibration else None,
        )

    def execute_command(self, session: Session, payload: HardwareCommandRequestSchema) -> HardwareCommandResponseSchema:
        safety_gate: SafetyGateResponseSchema | None = None
        guarded_actions = {"manual_move", "home", "reset_zero_position", "start_motion", "complete_set"}
        if payload.action in guarded_actions:
            safety_gate = self.evaluate_safety_gate(
                session,
                SafetyGateRequestSchema(
                    user_id=payload.user_id,
                    exercise_slug=payload.exercise_slug or "manual-control",
                    calibration_required=payload.calibration_required,
                    range_confirmed=payload.range_confirmed,
                    weight_kg=payload.weight_kg,
                    mode=payload.mode,
                ),
            )
            if not safety_gate.allowed:
                raise PermissionError(safety_gate.blocking_reasons[0])

        calibration = self.get_current_calibration(session, payload.user_id or "", payload.exercise_slug or "") if payload.user_id and payload.exercise_slug else None

        if payload.action == "trigger_emergency_stop":
            command = hardware_runtime.trigger_emergency_stop()
            audit_action = AuditAction.emergency_stop
            severity = AuditSeverity.critical
        elif payload.action == "clear_emergency_stop":
            command = hardware_runtime.clear_emergency_stop()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.warning
        elif payload.action == "toggle_service_mode":
            command = hardware_runtime.set_service_mode(bool(payload.service_mode))
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.warning
        elif payload.action == "run_diagnostics":
            command = hardware_runtime.run_diagnostics()
            audit_action = AuditAction.diagnostics_run
            severity = AuditSeverity.info
            self._store_diagnostics(session)
        elif payload.action == "home":
            command = hardware_runtime.home()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "reset_zero_position":
            command = hardware_runtime.reset_zero_position()
            audit_action = AuditAction.zero_position_reset
            severity = AuditSeverity.warning
        elif payload.action == "manual_move":
            if payload.direction is None or payload.distance_mm is None:
                raise ValueError("Manual move requires direction and distance")
            command = hardware_runtime.manual_move(payload.direction, payload.distance_mm, "service" if payload.service_mode else "manual")
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "start_motion":
            if calibration is None and payload.calibration_required:
                raise PermissionError("Calibration is required to start movement")
            lower_bound = calibration.lower_point_mm if calibration else 640.0
            upper_bound = calibration.upper_point_mm if calibration else 1320.0
            command = hardware_runtime.start_motion(
                calibration_id=calibration.id if calibration else None,
                lower_bound_mm=lower_bound,
                upper_bound_mm=upper_bound,
                target_set=payload.target_set,
                target_reps=payload.target_reps,
                motion_profile="training" if payload.mode == "machine" else payload.mode,
            )
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "complete_set":
            command = hardware_runtime.complete_set()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        else:
            raise ValueError("Unsupported hardware action")

        self.audit_repository.record(
            session,
            actor_user_id=payload.user_id,
            action=audit_action,
            target_type="hardware",
            target_id=str(command.id),
            severity=severity,
            details={"action": payload.action, **payload.model_dump(mode="json", exclude_none=True)},
        )
        session.commit()
        snapshot = self.get_snapshot(session, payload.user_id)
        return HardwareCommandResponseSchema(
            command_id=command.id,
            status=command.status,
            message=self._message_for_action(payload.action),
            snapshot=snapshot,
            safety_gate=safety_gate,
        )

    def update_safety_settings(self, session: Session, user_id: str | None, payload: HardwareSafetySettingsSchema) -> HardwareSafetySettingsSchema:
        key = "hardware.safety.settings"
        statement = select(AppSetting).where(AppSetting.user_id == user_id, AppSetting.key == key)
        setting = session.scalars(statement).first()
        serialized = payload.model_dump(mode="json")
        if setting is None:
            setting = AppSetting(user_id=user_id, key=key, value=serialized)
            session.add(setting)
        else:
            setting.value = serialized
        self.audit_repository.record(
            session,
            actor_user_id=user_id,
            action=AuditAction.settings_changed,
            target_type="hardware_settings",
            target_id=key,
            severity=AuditSeverity.info,
            details=serialized,
        )
        session.commit()
        return payload

    def get_system_settings(self, session: Session, user_id: str | None) -> dict[str, object]:
        snapshot = self.get_snapshot(session, user_id)
        settings = self._get_safety_settings(session, user_id)
        calibrations = self.list_calibrations(session, user_id or "").items if user_id else []
        diagnostics_statement = select(HardwareDiagnosticRecord).order_by(HardwareDiagnosticRecord.ran_at.desc()).limit(8)
        diagnostics = list(session.scalars(diagnostics_statement))
        if not diagnostics:
            diagnostics = [self._store_diagnostics(session, commit=False)]
            session.rollback()
        journal_entries = list(session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(12)))
        payload = {
            "machine": jsonable_encoder(snapshot.machine),
            "overviewCards": [
                {"label": "Статус", "value": snapshot.machine.machine_label, "tone": "good" if snapshot.machine.machine_state == MachineState.ready else "warning"},
                {"label": "Эмулятор", "value": "Включён" if snapshot.emulator_mode else "Отключён", "hint": "mode"},
                {"label": "Синхронность", "value": f"{snapshot.motion.sync_delta_mm:.1f} мм", "hint": "разница сторон"},
                {"label": "Калибровка", "value": snapshot.machine.calibration, "hint": "диапазон"},
            ],
            "overviewEvents": [
                {"time": entry.created_at.astimezone(UTC).strftime("%d.%m %H:%M"), "title": str(entry.details.get("action", entry.action.value)), "tone": "warning" if entry.severity == AuditSeverity.warning else ("good" if entry.severity == AuditSeverity.info else "warning")}
                for entry in journal_entries[:4]
            ],
            "safety": jsonable_encoder(settings),
            "mechanics": {
                "statusSummary": [
                    {"label": "Механика", "value": snapshot.machine.machine_label, "hint": "общее состояние"},
                    {"label": "Запуск", "value": "Разрешён" if snapshot.safety.state == SafetyState.enabled and snapshot.machine.machine_state != MachineState.blocked else "Заблокирован", "hint": "safety gate"},
                ],
                "leftDrive": self._drive_metric_cards(snapshot.drives[0]),
                "rightDrive": self._drive_metric_cards(snapshot.drives[1]),
                "sync": [
                    {"label": "Разница сторон", "value": f"{snapshot.motion.sync_delta_mm:.1f} мм"},
                    {"label": "Допуск", "value": settings.sync_limit},
                    {"label": "Действие", "value": settings.desync_action},
                ],
                "motion": [
                    {"label": "Скорость", "value": f"{snapshot.drives[0].speed_mm_per_sec:.0f} мм/с"},
                    {"label": "Ускорение", "value": f"{snapshot.drives[0].acceleration_mm_per_sec2:.0f} мм/с²"},
                    {"label": "Jerk", "value": f"{snapshot.drives[0].jerk_mm_per_sec3:.0f} мм/с³"},
                    {"label": "Профиль", "value": snapshot.motion.motion_profile},
                ],
                "screw": [
                    {"label": "Ход", "value": "1400 мм"},
                    {"label": "Нулевая позиция", "value": f"{snapshot.motion.bar_position_mm:.1f} мм"},
                    {"label": "Лимит нагрузки", "value": settings.max_load},
                    {"label": "Макс. скорость", "value": settings.max_speed},
                ],
                "profiles": ["normal", "training", "service", "calibration"],
                "service": [
                    {"label": "Сервисный режим", "value": "Включён" if snapshot.service_mode else "Отключён"},
                    {"label": "Последняя диагностика", "value": snapshot.last_diagnostics_at or "нет данных"},
                    {"label": "Команд в очереди", "value": str(snapshot.command_queue_depth)},
                ],
            },
            "diagnostics": {
                "lastRun": snapshot.last_diagnostics_at or "нет данных",
                "checked": str(len(diagnostics)),
                "success": str(sum(1 for item in diagnostics if item.status == "passed")),
                "errors": str(sum(1 for item in diagnostics if item.severity == "critical")),
                "systemStatus": snapshot.diagnostics_status,
                "checklist": [{"label": item.title, "result": item.status} for item in diagnostics[:5]],
                "quickTests": [
                    {"title": "Проверка приводов", "description": "Оценивает связь, ток и температуру приводов."},
                    {"title": "Проверка аварийной остановки", "description": "Подтверждает блокировку движения при STOP."},
                    {"title": "Проверка диапазона", "description": "Сверяет калибровку и текущие лимиты движения."},
                ],
                "history": [
                    {"label": item.title, "result": item.status, "hint": item.description}
                    for item in diagnostics
                ],
            },
            "calibrations": {
                "entries": [
                    {
                        "id": str(item.id),
                        "exercise": item.exercise_slug,
                        "muscle": "machine",
                        "lowerPoint": f"{item.lower_point_mm:.0f} мм",
                        "upperPoint": f"{item.upper_point_mm:.0f} мм",
                        "updatedAt": item.captured_at.astimezone(UTC).strftime("%d.%m.%Y %H:%M"),
                        "status": "actual" if self._is_calibration_actual_model(item) else "stale",
                    }
                    for item in calibrations
                ],
                "total": str(len(calibrations)),
                "lastUpdate": calibrations[0].captured_at.astimezone(UTC).strftime("%d.%m.%Y %H:%M") if calibrations else "нет данных",
                "staleCount": str(sum(1 for item in calibrations if not self._is_calibration_actual_model(item))),
                "missingCount": "0" if calibrations else "1",
            },
            "service": {
                "unlocked": snapshot.service_mode,
                "positions": [
                    {"label": "Гриф", "value": f"{snapshot.motion.bar_position_mm:.1f} мм"},
                    {"label": "Левый привод", "value": f"{snapshot.motion.left_position_mm:.1f} мм"},
                    {"label": "Правый привод", "value": f"{snapshot.motion.right_position_mm:.1f} мм"},
                ],
                "driveHealth": [
                    {"label": "Левый привод", "value": snapshot.drives[0].status},
                    {"label": "Правый привод", "value": snapshot.drives[1].status},
                    {"label": "Безопасность", "value": snapshot.safety.label},
                ],
                "actions": [
                    {"title": "Homing", "description": "Перевести механику в нулевую позицию."},
                    {"title": "Сброс нуля", "description": "Подтвердить новую нулевую позицию грифа."},
                    {"title": "Запуск диагностики", "description": "Полный тест приводов, стопа и калибровки."},
                ],
                "journal": [
                    {"time": entry.created_at.astimezone(UTC).strftime("%d.%m %H:%M"), "action": entry.action.value, "result": entry.severity.value}
                    for entry in journal_entries[:6]
                ],
            },
            "journal": {
                "stats": [
                    {"label": "Событий", "value": str(len(journal_entries))},
                    {"label": "Критических", "value": str(sum(1 for item in journal_entries if item.severity == AuditSeverity.critical))},
                    {"label": "Предупреждений", "value": str(sum(1 for item in journal_entries if item.severity == AuditSeverity.warning))},
                ],
                "entries": [
                    {
                        "id": str(item.id),
                        "date": item.created_at.astimezone(UTC).strftime("%d.%m.%Y %H:%M"),
                        "category": item.target_type,
                        "level": "critical" if item.severity == AuditSeverity.critical else ("warning" if item.severity == AuditSeverity.warning else "info"),
                        "title": item.action.value,
                        "description": str(item.details),
                    }
                    for item in journal_entries
                ],
            },
            "common": {
                "interfaceTheme": "dark",
                "interfaceScale": "100%",
                "language": "Русский",
                "units": "kg / cm",
                "brightnessMode": "Авто",
                "autoReturnMinutes": settings.idle_lock_minutes,
                "soundEnabled": True,
                "voiceHintsEnabled": True,
                "signalVolume": "70%",
                "wifiMode": "Ethernet emulator",
                "networkStatus": "Подключено",
                "ssid": "Forma-Emulator",
                "ipAddress": "127.0.0.1",
                "signalStrength": "100%",
                "version": "stage8-emulator",
                "serialNumber": "FORMA-EMU-001",
                "workTime": "312 ч",
            },
        }
        return payload

    def list_diagnostics(self, session: Session) -> list[HardwareDiagnosticRecordSchema]:
        statement = select(HardwareDiagnosticRecord).order_by(HardwareDiagnosticRecord.ran_at.desc())
        return [HardwareDiagnosticRecordSchema.model_validate(item) for item in session.scalars(statement)]

    def _store_diagnostics(self, session: Session, commit: bool = True) -> HardwareDiagnosticRecord:
        record = HardwareDiagnosticRecord(
            category="drives",
            title="Полная диагностика",
            status="passed",
            severity="info",
            description="Проверены приводы, аварийная остановка, диапазон движения и связь с эмулятором.",
            payload_json={"emulator": True, "drives": ["left", "right"]},
            ran_at=datetime.now(UTC),
        )
        session.add(record)
        session.flush()
        if commit:
            session.commit()
        return record

    def _get_safety_settings(self, session: Session, user_id: str | None) -> HardwareSafetySettingsSchema:
        defaults = HardwareSafetySettingsSchema(
            child_lock=True,
            workout_pin=True,
            service_pin=True,
            idle_lock_minutes="2 минуты",
            guest_mode=True,
            guest_weight_limit="30 кг",
            max_load="80 кг",
            max_speed="Средняя",
            sync_limit="5 мм",
            desync_action="Остановить движение",
        )
        for setting in self.settings_repository.list_for_user(session, user_id or ""):
            if setting.key == "hardware.safety.settings" and isinstance(setting.value, dict):
                return HardwareSafetySettingsSchema.model_validate(setting.value)
        return defaults

    def _check(self, check_id: str, label: str, passed: bool, severity: str, message: str) -> SafetyGateCheckSchema:
        return SafetyGateCheckSchema(id=check_id, label=label, passed=passed, severity=severity, message=message)

    def _is_calibration_actual(self, calibration: ExerciseCalibration | None) -> bool:
        return calibration is not None and self._is_calibration_actual_model(calibration)

    def _is_calibration_actual_model(self, calibration: CalibrationSummarySchema | ExerciseCalibration) -> bool:
        expires_at = calibration.expires_at
        if expires_at is None:
            return True
        if expires_at.tzinfo is None:
            return expires_at.replace(tzinfo=UTC) > datetime.now(UTC)
        return expires_at.astimezone(UTC) > datetime.now(UTC)

    def _parse_kg(self, value: str) -> float:
        return float(value.split()[0].replace(",", "."))

    def _drive_metric_cards(self, drive: object) -> list[dict[str, str]]:
        return [
            {"label": "Статус", "value": str(getattr(drive, "status"))},
            {"label": "Позиция", "value": f"{getattr(drive, 'position_mm'):.1f} мм"},
            {"label": "Ток", "value": f"{getattr(drive, 'current_a'):.1f} А"},
            {"label": "Температура", "value": f"{getattr(drive, 'temperature_c'):.1f} °C"},
        ]

    def _message_for_action(self, action: str) -> str:
        return {
            "trigger_emergency_stop": "Аварийная остановка активирована",
            "clear_emergency_stop": "Аварийная остановка снята",
            "toggle_service_mode": "Сервисный режим обновлён",
            "run_diagnostics": "Диагностика выполнена",
            "home": "Homing выполнен",
            "reset_zero_position": "Нулевая позиция обновлена",
            "manual_move": "Команда ручного движения выполнена",
            "start_motion": "Тренировочное движение запущено",
            "complete_set": "Подход завершён",
        }[action]