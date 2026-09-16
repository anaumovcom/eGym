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
    ProcedureStartSchema,
    SafetyGateCheckSchema,
    SafetyGateRequestSchema,
    SafetyGateResponseSchema,
    TuningPresetDiffSchema,
    TuningPresetSaveSchema,
    TuningPresetSchema,
    TuningUpdateResultSchema,
    TuningUpdateSchema,
    TuningValuesSchema,
)
from app.schemas.machine import MachineHealthSchema, SafetyStatusSchema
from app.services.exercise_library import get_imported_exercise
from app.services.hardware_runtime import hardware_runtime
from app.services.motion.parameters import PARAMETER_SPECS, get_spec
from app.repositories.audit_repository import AuditRepository
from app.repositories.settings_repository import SettingsRepository


CALIBRATION_EXEMPT_EQUIPMENT = {
    "Bosu-Ball",
    "BOSU Ball",
    "Cardio",
    "Dumbbells",
    "Dumbbell",
    "Kettlebells",
    "Kettlebell",
    "Medicine-Ball",
    "Medicine Ball",
    "Plate",
    "Recovery",
    "Stretches",
    "TRX",
    "Yoga",
    "Band",
    "Резина",
    "Bodyweight",
    "Собственный вес",
}


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

    def _requires_calibration(self, exercise_slug: str, calibration_required: bool) -> bool:
        if not calibration_required:
            return False

        exercise = get_imported_exercise(exercise_slug)
        if exercise and exercise.equipment in CALIBRATION_EXEMPT_EQUIPMENT:
            return False

        return True

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
        control = runtime.control or {}
        parameters = hardware_runtime.parameters
        calibration_required = self._requires_calibration(payload.exercise_slug, payload.calibration_required)
        calibration = self.get_current_calibration(session, payload.user_id or "", payload.exercise_slug) if payload.user_id else None
        service_action = payload.mode == "service"
        soft_min = float(parameters.get("limits.softMinMm"))
        soft_max = float(parameters.get("limits.softMaxMm"))
        within_limits = soft_min - 1 <= runtime.motion.bar_position_mm <= soft_max + 1
        max_load_kg = min(self._parse_kg(settings.max_load), float(parameters.get("load.maxKg")))
        if payload.mode == "guest":
            max_load_kg = min(max_load_kg, float(parameters.get("load.guestMaxKg")))
        post_ok = control.get("postStatus") in {"passed", "skipped"} or not bool(parameters.get("safety.postRequired"))
        position_known = bool(control.get("positionKnown", True))
        sync_ok = control.get("syncStatus") != "critical"
        not_faulted = control.get("mode") != "fault"
        thermal_ok = all(drive.status != "error" for drive in runtime.drives)
        checks = [
            self._check("user-selected", "Пользователь выбран", payload.user_id is not None and payload.user_id != "", "critical", "Пользователь выбран" if payload.user_id else "Сначала выберите пользователя."),
            self._check("safety-enabled", "Безопасность включена", runtime.safety.state == SafetyState.enabled, "critical", "Безопасность активна" if runtime.safety.state == SafetyState.enabled else "Система безопасности выключена."),
            self._check("estop", "СТОП не активен", runtime.safety.state != SafetyState.emergency_stop, "critical", "Аварийная остановка не активна" if runtime.safety.state != SafetyState.emergency_stop else "Сначала снимите аварийную остановку."),
            self._check("drives", "Оба привода доступны", all(drive.connected and drive.status != "error" for drive in runtime.drives), "critical", "Приводы доступны" if all(drive.connected and drive.status != "error" for drive in runtime.drives) else "Есть ошибка подключения или состояния привода."),
            self._check("critical-errors", "Нет критических ошибок", runtime.machine.machine_state != MachineState.blocked and not_faulted, "critical", "Критических ошибок нет" if runtime.machine.machine_state != MachineState.blocked and not_faulted else str(control.get("faultCode") or "Тренажёр заблокирован критической ошибкой.")),
            self._check("post", "Самотест пройден", post_ok, "critical", "Самотест пройден" if post_ok else "Самотест приводов не пройден — запуск заблокирован."),
            self._check("position-known", "Позиция определена", position_known or payload.mode == "homing", "critical", "Нулевая позиция известна" if position_known else "Позиция не определена — выполните homing."),
            self._check("sync", "Стороны синхронны", sync_ok, "critical", "Рассинхрон в допуске" if sync_ok else f"Критический рассинхрон {runtime.motion.sync_delta_mm:.1f} мм — выровняйте стороны."),
            self._check("thermal", "Ток и температура в норме", thermal_ok, "critical", "Приводы в тепловой норме" if thermal_ok else "Превышение тока или температуры привода."),
            self._check("calibration", "Калибровка актуальна", not calibration_required or (calibration is not None and self._is_calibration_actual(calibration)), "critical", "Калибровка найдена" if not calibration_required or calibration is not None else "Для запуска нужна актуальная калибровка."),
            self._check("range", "Диапазон подтверждён", (not calibration_required) or payload.range_confirmed or bool(calibration and calibration.movement_range_confirmed), "warning", "Диапазон движения подтверждён" if (not calibration_required) or payload.range_confirmed or bool(calibration and calibration.movement_range_confirmed) else "Подтвердите диапазон движения."),
            self._check("weight", "Нагрузка допустима", payload.weight_kg <= max_load_kg, "critical", "Нагрузка допустима" if payload.weight_kg <= max_load_kg else f"Превышен лимит нагрузки {max_load_kg:.0f} кг."),
            self._check("service-mode", "Сервисный режим не конфликтует", not runtime.service_mode or service_action, "critical", "Сервисный режим не активен" if not runtime.service_mode else ("Сервисная операция" if service_action else "Отключите сервисный режим перед тренировкой.")),
            self._check("limits", "Лимиты движения не нарушены", within_limits or payload.mode == "homing", "critical", "Позиция в пределах лимитов" if within_limits else f"Текущая позиция вне мягких лимитов {soft_min:.0f}–{soft_max:.0f} мм."),
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
        training_actions = {"start_motion", "move_to_start", "start_fixed_position", "resume"}
        service_actions = {"manual_move", "home", "reset_zero_position", "range_preview", "enter_weightless", "align_sides"}
        guarded_actions = training_actions | service_actions | {"complete_set"}
        if payload.action in guarded_actions:
            gate_mode = payload.mode
            if payload.action in service_actions and gate_mode == "machine":
                gate_mode = "service"
            if payload.action == "home":
                gate_mode = "homing"
            if payload.guest and gate_mode == "machine":
                gate_mode = "guest"
            safety_gate = self.evaluate_safety_gate(
                session,
                SafetyGateRequestSchema(
                    user_id=payload.user_id,
                    exercise_slug=payload.exercise_slug or "manual-control",
                    calibration_required=payload.calibration_required and payload.action in training_actions,
                    range_confirmed=payload.range_confirmed,
                    weight_kg=payload.weight_kg,
                    mode=gate_mode,
                ),
            )
            if not safety_gate.allowed:
                raise PermissionError(safety_gate.blocking_reasons[0])

        calibration = self.get_current_calibration(session, payload.user_id or "", payload.exercise_slug or "") if payload.user_id and payload.exercise_slug else None
        calibration_required = self._requires_calibration(payload.exercise_slug or "", payload.calibration_required)
        captured_position: float | None = None
        lower_bound = payload.lower_mm if payload.lower_mm is not None else (calibration.lower_point_mm if calibration else 640.0)
        upper_bound = payload.upper_mm if payload.upper_mm is not None else (calibration.upper_point_mm if calibration else 1320.0)
        load_kg = payload.weight_kg
        load_mode = payload.load_mode or ("normal_weight" if payload.mode in {"machine", "training"} else payload.mode)

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
            if calibration is None and calibration_required:
                raise PermissionError("Calibration is required to start movement")
            command = hardware_runtime.start_motion(
                calibration_id=calibration.id if calibration else None,
                lower_bound_mm=lower_bound,
                upper_bound_mm=upper_bound,
                target_set=payload.target_set,
                target_reps=payload.target_reps,
                motion_profile="training" if payload.mode == "machine" else payload.mode,
                load_kg=load_kg,
                load_mode=load_mode,
                start_point=payload.start_point or "lower",
                warmup=payload.warmup,
                guest=payload.guest,
                asymmetric_allowed=payload.asymmetric_allowed,
                rep_count_source=payload.rep_count_source or "motion",
                fixed_position_mm=payload.position_mm,
                isometric_duration_s=payload.isometric_duration_s or 20.0,
                wait_for_grip=payload.wait_for_grip,
                auto_user=payload.auto_user,
            )
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "move_to_start":
            if calibration is None and calibration_required and payload.lower_mm is None:
                raise PermissionError("Calibration is required to move to the start point")
            command = hardware_runtime.move_to_start(
                lower_bound_mm=lower_bound,
                upper_bound_mm=upper_bound,
                start_point=payload.start_point or "lower",
                custom_mm=payload.position_mm,
                load_kg=load_kg,
                load_mode=load_mode,
                target_reps=payload.target_reps,
                target_set=payload.target_set,
                guest=payload.guest,
                warmup=payload.warmup,
                calibration_id=calibration.id if calibration else None,
            )
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "start_fixed_position":
            if payload.position_mm is None:
                raise ValueError("Fixed position requires positionMm")
            command = hardware_runtime.start_fixed_position(
                position_mm=payload.position_mm,
                target_reps=payload.target_reps,
                rep_count_source=payload.rep_count_source or "load",
                body_weight_kg=payload.body_weight_kg,
            )
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "range_preview":
            command = hardware_runtime.range_preview(lower_bound, upper_bound)
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "enter_weightless":
            command = hardware_runtime.enter_weightless()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "capture_point":
            if payload.which not in {"lower", "upper", "fixed"}:
                raise ValueError("capture_point requires which = lower | upper | fixed")
            command, captured_position = hardware_runtime.capture_point(payload.which)
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "hold":
            command = hardware_runtime.hold()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "pause":
            command = hardware_runtime.pause()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "resume":
            command = hardware_runtime.resume()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "park":
            command = hardware_runtime.park()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "set_load":
            command = hardware_runtime.set_load(payload.weight_kg)
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "manual_rep":
            command = hardware_runtime.manual_rep()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.info
        elif payload.action == "reset_fault":
            command = hardware_runtime.reset_fault()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.warning
        elif payload.action == "align_sides":
            command = hardware_runtime.align_sides()
            audit_action = AuditAction.hardware_command
            severity = AuditSeverity.warning
        elif payload.action == "run_self_test":
            command = hardware_runtime.run_self_test()
            audit_action = AuditAction.diagnostics_run
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
            captured_position_mm=captured_position,
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
            "run_self_test": "Самотест запущен",
            "home": "Homing запущен",
            "reset_zero_position": "Нулевая позиция обновлена",
            "manual_move": "Команда ручного движения выполнена",
            "start_motion": "Тренировочное движение запущено",
            "move_to_start": "Гриф выходит в стартовую точку",
            "start_fixed_position": "Гриф выходит на высоту фиксации",
            "range_preview": "Показ диапазона запущен",
            "enter_weightless": "Режим невесомого грифа включён",
            "capture_point": "Точка зафиксирована",
            "hold": "Гриф удерживается",
            "pause": "Пауза",
            "resume": "Движение продолжено",
            "park": "Гриф паркуется",
            "set_load": "Нагрузка обновлена",
            "manual_rep": "Повтор засчитан",
            "reset_fault": "Ошибка сброшена",
            "align_sides": "Выравнивание сторон запущено",
            "complete_set": "Подход завершён",
        }.get(action, "Команда выполнена")

    # ------------------------------------------------------------- tuning
    PARAMETERS_KEY = "hardware.tuning.parameters"
    PRESETS_KEY = "hardware.tuning.presets"

    def load_parameters_from_db(self, session: Session) -> None:
        setting = session.scalars(select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key == self.PARAMETERS_KEY)).first()
        if setting is not None and isinstance(setting.value, dict):
            hardware_runtime.load_parameters(setting.value)

    def get_tuning(self, session: Session) -> TuningValuesSchema:
        payload = hardware_runtime.parameters_payload()
        return TuningValuesSchema(
            values=payload["values"],
            persisted=payload["persisted"],
            temporary=payload["temporary"],
            service_mode=hardware_runtime.state.service_mode,
            adapter=hardware_runtime.adapter.name,
        )

    def update_tuning(self, session: Session, payload: TuningUpdateSchema) -> TuningUpdateResultSchema:
        if not hardware_runtime.state.service_mode:
            raise PermissionError("Изменение параметров механики доступно только в сервисном режиме")
        temporary = payload.apply != "persist"
        control_mode = str(hardware_runtime.snapshot_payload()["control"].get("mode"))
        if control_mode in {"training", "fixed_hold", "isometric"}:
            critical = [key for key in payload.values if get_spec(key).safety_critical]
            if critical:
                raise PermissionError(f"Во время подхода нельзя менять параметры безопасности: {', '.join(critical)}")
        changes = hardware_runtime.update_parameters(payload.values, temporary=temporary)
        if not temporary:
            self._persist_parameters(session, payload.actor_user_id)
        if changes:
            self.audit_repository.record(
                session,
                actor_user_id=payload.actor_user_id,
                action=AuditAction.settings_changed,
                target_type="hardware_tuning",
                target_id="temporary" if temporary else "persist",
                severity=AuditSeverity.warning if any(get_spec(key).safety_critical for key in changes) else AuditSeverity.info,
                details={key: {"from": old, "to": new} for key, (old, new) in changes.items()},
            )
            session.commit()
        payload_values = hardware_runtime.parameters_payload()
        return TuningUpdateResultSchema(
            changed={key: {"from": old, "to": new} for key, (old, new) in changes.items()},
            values=payload_values["values"],
            temporary=payload_values["temporary"],
        )

    def revert_temporary_tuning(self, session: Session) -> TuningValuesSchema:
        hardware_runtime.revert_temporary_parameters()
        return self.get_tuning(session)

    def reset_tuning(self, session: Session, actor_user_id: str | None) -> TuningValuesSchema:
        if not hardware_runtime.state.service_mode:
            raise PermissionError("Сброс параметров доступен только в сервисном режиме")
        hardware_runtime.reset_parameters()
        self._persist_parameters(session, actor_user_id)
        self.audit_repository.record(session, actor_user_id=actor_user_id, action=AuditAction.settings_changed, target_type="hardware_tuning", target_id="reset", severity=AuditSeverity.warning, details={"reset": True})
        session.commit()
        return self.get_tuning(session)

    def _persist_parameters(self, session: Session, actor_user_id: str | None) -> None:
        del actor_user_id
        setting = session.scalars(select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key == self.PARAMETERS_KEY)).first()
        values = dict(hardware_runtime.parameters.persisted)
        if setting is None:
            session.add(AppSetting(user_id=None, key=self.PARAMETERS_KEY, value=values))
        else:
            setting.value = values
        session.flush()
        hardware_runtime.parameters_dirty = False

    def list_presets(self, session: Session) -> list[TuningPresetSchema]:
        presets = [
            TuningPresetSchema(id="factory", title="Заводские", description="Значения по умолчанию из реестра параметров.", created_at="", values={spec.key: spec.default for spec in PARAMETER_SPECS}, builtin=True),
            TuningPresetSchema(
                id="soft",
                title="Мягкие",
                description="Низкие скорости и моменты для первых запусков на железе.",
                created_at="",
                values={
                    "limits.maxSpeedMmPerSec": 300,
                    "limits.maxDescentSpeedMmPerSec": 250,
                    "profile.training.torqueLimitPercent": 60,
                    "profile.return.speedMmPerSec": 30,
                    "load.maxKg": 60,
                    "safety.torqueRateLimitPercentPerSec": 120,
                    "detection.spotterAssistPercent": 70,
                },
                builtin=True,
            ),
            TuningPresetSchema(
                id="bench",
                title="Тестовый стенд",
                description="Эмулятор без реальных ограничений безопасности по POST/homing.",
                created_at="",
                values={"safety.postRequired": False, "safety.homingRequiredAfterPowerLoss": False, "screw.encoderType": "absolute"},
                builtin=True,
            ),
        ]
        for item in self._stored_presets(session):
            presets.append(TuningPresetSchema.model_validate(item))
        return presets

    def save_preset(self, session: Session, payload: TuningPresetSaveSchema) -> TuningPresetSchema:
        stored = self._stored_presets(session)
        preset_id = f"preset-{int(datetime.now(UTC).timestamp() * 1000)}"
        values = payload.values if payload.values is not None else hardware_runtime.parameters.effective()
        preset = {"id": preset_id, "title": payload.title, "description": payload.description, "createdAt": datetime.now(UTC).isoformat(), "values": values, "builtin": False}
        stored.append(preset)
        self._write_presets(session, stored[-20:])
        self.audit_repository.record(session, actor_user_id=payload.actor_user_id, action=AuditAction.settings_changed, target_type="hardware_tuning_preset", target_id=preset_id, severity=AuditSeverity.info, details={"title": payload.title})
        session.commit()
        return TuningPresetSchema.model_validate(preset)

    def delete_preset(self, session: Session, preset_id: str) -> None:
        stored = self._stored_presets(session)
        remaining = [item for item in stored if item.get("id") != preset_id]
        if len(remaining) == len(stored):
            raise LookupError("Пресет не найден")
        self._write_presets(session, remaining)
        session.commit()

    def apply_preset(self, session: Session, preset_id: str, *, apply: str, actor_user_id: str | None) -> TuningUpdateResultSchema:
        preset = next((item for item in self.list_presets(session) if item.id == preset_id), None)
        if preset is None:
            raise LookupError("Пресет не найден")
        return self.update_tuning(session, TuningUpdateSchema(values=preset.values, apply=apply, actor_user_id=actor_user_id))

    def diff_preset(self, session: Session, preset_id: str) -> TuningPresetDiffSchema:
        preset = next((item for item in self.list_presets(session) if item.id == preset_id), None)
        if preset is None:
            raise LookupError("Пресет не найден")
        current = hardware_runtime.parameters.effective()
        differences = [
            {"key": key, "current": current.get(key), "preset": value, "label": get_spec(key).label}
            for key, value in preset.values.items()
            if key in current and current.get(key) != value
        ]
        return TuningPresetDiffSchema(preset_id=preset_id, differences=differences)

    def _stored_presets(self, session: Session) -> list[dict[str, object]]:
        setting = session.scalars(select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key == self.PRESETS_KEY)).first()
        if setting is None or not isinstance(setting.value, dict):
            return []
        items = setting.value.get("items", [])
        return list(items) if isinstance(items, list) else []

    def _write_presets(self, session: Session, items: list[dict[str, object]]) -> None:
        setting = session.scalars(select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key == self.PRESETS_KEY)).first()
        if setting is None:
            session.add(AppSetting(user_id=None, key=self.PRESETS_KEY, value={"items": items}))
        else:
            setting.value = {"items": items}
        session.flush()

    def start_procedure(self, session: Session, name: str, payload: ProcedureStartSchema) -> dict[str, object]:
        if not hardware_runtime.state.service_mode:
            raise PermissionError("Процедуры отладки доступны только в сервисном режиме")
        status = hardware_runtime.start_procedure(name, **payload.args)
        self.audit_repository.record(session, actor_user_id=payload.actor_user_id, action=AuditAction.diagnostics_run, target_type="hardware_procedure", target_id=name, severity=AuditSeverity.info, details={"args": payload.args})
        session.commit()
        return status.to_payload()