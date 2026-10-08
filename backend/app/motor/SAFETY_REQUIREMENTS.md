# Требования безопасности управления двигателями (T6)

Перенесено из удалённых `test_motion_backup_torque.py`,
`test_modbus_torque_runtime.py` и `docs/common/backup-torque.md`
(план 16, задача 1.1). Каждый пункт покрыт тестом в `app/tests/motor/`.

| ID | Требование | Тест |
|---|---|---|
| R1 | Старт, перезапуск lifespan и сброс ошибок никогда не пишут промежуточный PA_12C = 0: первая запись — поддержка `support_raw` | `test_safe_runtime.py::test_startup_writes_support_first`, `::test_twin_startup_writes_support_first` |
| R2 | Поддержка направлена против гравитации и учитывает `direction_sign` стороны | `test_drive.py::test_support_respects_direction` |
| R3 | Отказ одной стороны: попытка поддержки на **обе** стороны независимо; ошибка записи одной не пропускает другую | `test_safe_runtime.py::test_support_attempts_both_sides` |
| R4 | Ошибка чтения/записи/исключение тика → latch FAULT + поддержка; выход только явным сбросом | `test_safe_runtime.py::test_read_failure_latches_fault_and_keeps_support`, `::test_tick_exception_latches_fault_with_support` |
| R5 | Overspeed → PA_12C = 0 на обе стороны, latch не перекрывается ESTOP/idle/shutdown/поддержкой | `test_safe_runtime.py::test_overspeed_zero_latch`, `test_supervisor.py::test_overspeed_zero_latch_survives_estop_and_clear` |
| R6 | ESTOP → поддержка на обе стороны, завершает ручной момент, latch; снятие ESTOP снимает только latch ESTOP | `test_safe_runtime.py::test_estop_support_and_release` |
| R7 | Shutdown: поддержка пишется после последнего тика (сериализация по lock), закрытие порта не обнуляет момент | `test_safe_runtime.py::test_shutdown_writes_support` |
| R8 | Ручной PA_12C из debug-панели не перезаписывается циклом, пока активен | `test_safe_runtime.py::test_manual_torque_not_overwritten` |
| R9 | Код никогда не пишет PA_000, PA_002, PA_00B, PA_08F, PA_090, PA_1A0, PA_1A7 и EEPROM | `test_drive.py::test_forbidden_registers`, `::test_only_whitelisted_registers_are_writable` |
| R10 | Команда в raw всегда в `[-max_raw, max_raw]` (PA_05E) | `test_drive.py::test_raw_is_always_clamped` |
| R11 | Момент никогда не толкает за мягкий предел хода | `test_safety.py::test_soft_limit_never_pushes_out_bottom`, `::test_soft_limit_never_pushes_out_top` |
| R12 | `|ΔF| ≤ R·dt` (кроме переходов в поддержку/ноль по аварии) | `test_safety.py::test_rate_limit` |
| R13 | При устаревшем кадре момент не растёт | `test_safety.py::test_stale_frame_no_growth` |
| R14 | Отказ одной стороны переводит обе стороны в одинаковый безопасный режим | `test_supervisor.py::test_one_side_fault_both_sides` |
| R15 | STOP принимается от любого источника всегда; ESTOP нельзя обойти | `test_supervisor.py::test_estop_from_any_mode`, `test_core_twin.py::test_estop_always_support` |
| R16 | Политика деградации связи: 1 кадр — экстраполяция; 2–5 — заморозка и спад к поддержке; > 5 или ошибка записи — FAULT | `test_safety.py::test_comm_degradation_policy`, `test_core_twin.py::test_lost_frames_fault_to_support` |

Ограничения, которые софт не снимает: нет механического тормоза; при потере
питания, обрыве RS-485, SIGKILL или зависании ОС последняя команда остаётся в
драйвере. Нужны сторожевой таймер драйвера (Err 3, проверка C-WD) и процесс
`motor-rt` (план 16, этап 5).
