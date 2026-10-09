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
| R17 | Пусконаладка (PA_002, PA_00B, PA_08F, PA_090, PA_080, PA_1A0 bit0) только читается; любое расхождение — отказ инициализации с именами регистров, момент и SRV-ON не пишутся | `test_modbus_two_drives.py::test_commissioning_mismatch_refuses_init_and_names_registers` |
| R18 | SRV-ON (PA_1A4 bit0) — только в сервисном режиме, без защёлки/СТОП; поддержка в PA_12C до SRV-ON; обе стороны или откат обеих | `test_safe_runtime.py::test_servo_requires_service_mode`, `::test_servo_on_writes_support_first_and_switches_both`, `::test_servo_on_failure_rolls_back_both_sides`, `::test_servo_on_rejected_while_latched` |
| R19 | Калибровка из интерфейса — только в сервисном режиме, Servo ON, без защёлки, штанга на упорах; запуск одним нажатием, экран калибровки шлёт пульс каждые 0,3 с; нет пульса 1,5 с (страница закрыта/скрыта, нет сети) — прерывание. Кнопка «СТОП», СТОП/защёлка, Servo OFF, выход из сервиса, ручной момент — прерывание в поддержку. Новые значения не активны до явного сохранения | `test_calibration_session.py::test_preconditions_block_start`, `::test_dead_man_release_aborts_to_support`, `motor-calibration-screen.test.tsx`, `::test_estop_and_operator_abort`, `::test_wizard_session_runs_stages_and_proposes_changes` |
| R20 | Калибровки с подъёмом грифа выше ~60 мм (S7, D2, B8) требуют измеренного C3 (ток плавного опускания); каждая процедура ограничена своей огибающей по высоте и скорости (80 мм/с) и заканчивается посадкой на упоры. B8 поднимается до верхнего упора (огибающая 2000 мм) с силой сверх окна ≤ 0,6·Fc и считает упором остановку при прижатии. Ловля после трогания ускоряется со скоростью грифа, трогание по скорости > 5 мм/с — чтобы трение покоя не разгоняло гриф. S9/G1 запускаются только с указанной массой эталона 2–60 кг | `test_calibrations_all.py`, `test_calibration_session.py::test_preconditions_block_start` |
| R21 | Абсолютный ноль B7 подменяет ноль инициализации только вне калибровки и при расхождении ≤ 50 мм; больше — ноль инициализации остаётся, событие «повторите B7» | `hardware_runtime.py::_sync_zero` (ручная проверка на стенде) |
| R22 | Огибающая скорости калибровки срабатывает, только если превышение подтверждено энкодером (Δx/Δt ≥ ½ предела) или держится 3 кадра (одиночные выбросы PA_1C1 на стоящем грифе — не авария). Только в момент отрыва от упоров и только ниже 60 мм предел временно 150 мм/с (рывок при освобождении залипания длится 1–3 кадра задержки шины); выше 60 мм — всегда обычный предел | `test_calibrations_all.py::test_envelope_ignores_a_single_speed_spike`, `::test_c3_leaves_sticky_stops_without_m1` |
| R23 | Управляемое перемещение: запас силы сверх окна растёт ступенями до +1·трение только при неподвижном грифе, после трогания сразу сбрасывается; при скорости выше min(2,5·цель, 70 мм/с) — остановка серединой окна; 20 с без движения — отказ процедуры | `test_calibrations_all.py::test_m1_measures_liftoff_and_moves_start_at_once`, `::test_m2_m3_m4_governed_motion` |
| R24 | Действия оператора (вопросы калибровки): пока ждём ответа, гриф удерживается (H2, W2 — в режиме удержания/невесомости с огибающей процедуры) или стоит на упорах (груз, рулетка); ответ «Готово»/число проверяется по диапазону; ожидание дольше 5 мин — прерывание в поддержку. Испытания удержания H1/W1 прекращают кандидата при скорости > 65 мм/с (до огибающей 80 мм/с) и не пробуют более жёсткие; нагрузка H1 нарастает плавно до первого прогиба | `test_calibrations_all.py::test_holding_h1_h2_w1_w2_x3`, `::test_loaded_friction_l1_l2`, `::test_operator_reply_validation` |

Ограничения, которые софт не снимает: нет механического тормоза; при потере
питания, обрыве RS-485, SIGKILL или зависании ОС последняя команда остаётся в
драйвере. Нужны сторожевой таймер драйвера (Err 3, проверка C-WD) и процесс
`motor-rt` (план 16, этап 5).
