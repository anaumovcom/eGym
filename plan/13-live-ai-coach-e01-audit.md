# E01 — аудит AI-тренера и безопасный baseline

Дата: 07.10.2026. Проверенная рабочая версия: Git HEAD `7ab499a` (`main`).
Исторический Coach: commit `ed20a6e0869b1e5a824b3a63b9182a2dcf35fcba` (`back2`).
Связи: [трекер](13-live-ai-coach-implementation.md),
[спецификация](13-live-ai-coach-spec.md), [обзор](13-live-ai-coach.md).

**Итог: E01 завершён. Можно переходить к E02.**
Это аудит, не запуск работающего Coach. Paid calls: **0**.
Физические подключения/команды тренажёру от этого аудита: **0**.
Старые голоса не приняты: доступных аудиопакетов сейчас нет.

## 1. Исходное состояние и границы изменений — E01.1/E01.2

Проверены `git status --short`, refs, история путей и реальные каталоги,
а не только открытые вкладки редактора, память или результаты старых тестов.
На начало аудита изменены только два runtime watch log. Во время аудита появились
удаления watch PID-файлов; эти файлы не редактировались и не восстанавливались.
Не запускались start/stop-watch, app servers, migrations или hardware diagnostics.

В текущем дереве нет исходных Coach routes/services/schemas/frontend feature.
Остались отдельные `__pycache__` от старого Coach; они не используются для восстановления.
В доступной Git-истории 27 commits; поиск только по названию commit не находил Coach,
но история соответствующих путей обнаружила **исходники в `ed20a6e`**.
Этот commit добавляет Coach; его родитель не является источником Coach.
Ничего из исторического дерева не checkout/cherry-pick/restored.
Приватный старый coach log не читался и не считается доказательством готовности.

**Выбранный путь: новые модули по контрактам v0.3 + выборочный перенос проверенных
паттернов/тестовых случаев из исторического commit. Не полное восстановление ветки.**
**Последующее решение пользователя перед E02:** selective reuse отменён;
реализация и тесты пишутся с нуля, старые ветки не используются. Ниже —
исторические результаты аудита, не рекомендация переносить код.
Причины: старые provider orchestration, события и in-memory usage не заменяют
детерминированного режиссёра, persisted reservations, consent/vault и новые schemas.
Перенос ветки целиком также затронул бы посторонние изменения hardware/runtime.

### Что можно использовать из истории, но не копировать без проверки

| Исторический компонент в `ed20a6e` | Пригодная идея | Необходимая переработка |
|---|---|---|
| `CoachAudioManager` | Map источников, GainNode каждой фразы, startOrder, общий background budget, reservations не duck | Audible/gap semantics, actual-start acknowledgement, bounded buffers/LRU, раздельные attack/restore, peak checks |
| `WorkoutInterpreter` | Rebaseline, scope/deadline, cases partial/skip/safety/reconnect | Новый event contract, canonical aliases, save ack, settings future-only, проверенная семантика метрик |
| `CoachSession` / `RealtimeCoachSession` | Cancellation/retirement, bounded context, отдельные decision/speech стадии | Director вне LLM, provider interface, ledger, vault, ownership и новый протокол |
| `CoachUsage` | Response dedup и reconciliation test cases | Persisted attempt/reserve/settle, pricing version, категории cached/audio/reasoning и separate ledgers |
| Старые unit tests | Регрессионные сценарии streaming/scope/cancel/late packets | Перенести отдельные fixtures после E02 schemas, не выдавать старое число тестов за текущий PASS |

Пример конкретного несовпадения: исторический `updateMix()` выбирает все started
utterances с gain, даже при пустом потоке. Это **не доказывает** восстановление
foreground после >250 мс gap. `schedule()` отмечает started при планировании
source, поэтому actual-start semantics нужно проверить отдельно.
Исторические исходники исследованы через Git; они не существуют в текущем workspace,
поэтому здесь не создаются неработающие ссылки на них.

## 2. Карта интеграции — E01.3/E01.6

| Область | Проверенная точка | Будущая интеграция / ограничение |
|---|---|---|
| UI runtime | [startExercise / finishCurrentSet](../frontend/src/stores/runtime-store.ts#L361-L410) | View не подтверждает hardware activation; fallback simulate и промежуточный completed не достижения |
| Snapshot | [snapshot_payload](../backend/app/services/hardware_runtime.py#L1077-L1124) | Read-only control/motion/user/safety; без вызова command API |
| Control metrics | [control payload](../backend/app/services/hardware_runtime.py#L1126-L1159) | Reps/partial/load/mode/spotter/failure; provenance и freshness обязательны |
| Snapshot receive | [HardwareRealtimeProvider](../frontend/src/features/hardware/lib/hardware-realtime-provider.tsx#L19-L103), [hardware store](../frontend/src/stores/hardware-store.ts#L64-L67) | WS + REST fallback 500 мс; пока нет monotonic receive age/order/source guard для Coach |
| Normal finish | [handleAutoCompleteCurrentSet](../frontend/src/screens/exercise-session/exercise-session-screen.tsx#L412-L456) | Capture IDs до await; раздельные stopped/persisted/finalized |
| Manual partial/skip | [handleRecordFact](../frontend/src/screens/exercise-session/exercise-session-screen.tsx#L458-L525) | Истинный outcome + save ack, не догадки из view |
| Set persistence | [saveSetResultToBackend](../frontend/src/screens/exercise-session/exercise-session-screen.tsx#L920-L929), [RuntimeService.save_set_result](../backend/app/services/runtime_service.py#L51-L66) | REST returns setId после commit; сейчас response не превращается в Coach event |
| Exercise persistence | [saveExerciseResultToBackend](../frontend/src/screens/exercise-session/exercise-session-screen.tsx#L931-L953) | `preserve`/`replace`, status и summary — отдельные стадии |
| Workout persistence | [saveWorkoutToBackend](../frontend/src/features/runtime/lib/runtime-persistence.ts#L44-L60), [summary save effect](../frontend/src/screens/workout-summary/workout-summary-screen.tsx#L59-L72) | Итог после успешного сохранения, не только открытия summary screen |
| API contracts | [runtime routes](../backend/app/api/routes/runtime.py#L22-L70) | Existing app writes сохраняются; Coach только получает подтверждённые результаты |
| History | [ExerciseSession/SetResult](../backend/app/models/analytics.py#L42-L86) | user/slug/kind/ordinal/load/training mode доступны; строгая сопоставимость пока не доказана |
| Preferences | [AppSetting](../backend/app/models/settings.py#L7-L13), [settings UI](../frontend/src/screens/settings/system-settings-screen.tsx) | SchemaVersion, per-user revision/consent требуется; plaintext key запрещён |
| Operator access | [ServiceAccessGate](../frontend/src/shared/ui/layout/service-access.tsx#L12-L58) | UI acknowledgement прямо не является backend authorization/PIN; нельзя использовать для vault write |
| Header | [TopSystemBar](../frontend/src/shared/ui/layout/forma-shell.tsx#L169-L206) | Mini AI перед MotorForceReadout; общий normal/compact dock, не обходить safety portal/focus |
| Existing audio | [playRepCountedSound](../frontend/src/screens/exercise-session/exercise-session-screen.tsx#L100-L132) | Сейчас отдельный AudioContext на beep; shared Coach mixer не реализован |
| Configuration | [Settings](../backend/app/core/config.py) | Coach feature flags, provider config, safe secret storage ещё отсутствуют |

### Фактическая последовательность завершения

**Обычное auto-complete:** построить result → для machine `complete_set` →
ensure workout ID → ensure exercise ID → save set → на последнем подходе
save exercise summary (`preserve`) → `finishCurrentSet(result)` →
`markExerciseSaved` / replace summary → navigation.
`saveSetResultToBackend` может вернуть null для нулевого результата — тогда
никакого `set_persisted` нет. Positive save возвращает ID, но handler сейчас его игнорирует.

**Ручное завершение / partial:** status выбирается из факта относительно плана;
machine `complete_set` → ensure IDs → save только ненулевого currentResult →
непоследний подход: `finishCurrentSet` и rest; последний: save exercise summary,
`finishExerciseWithResults`, mark saved и summary. Partial не равен full success.

**«Пропустить упражнение»:** currentResult=null, completedForExercise=[];
ветка сама не вызывает `complete_set`, не сохраняет set; ensure IDs →
save exercise status skipped с `replace` → finalize UI.
Это пропуск **упражнения**, не только одного подхода. Coach не должен добавлять
в эту ветку motor command или исправлять workout history самостоятельно.

**Аварийное завершение:** UI action делает `completeWorkout('aborted')` и переход;
workout summary effect отдельно сохраняет итог. Сам UI переход не save ack.

**Ошибка:** catch сохраняет saveError и снимает pendingAction.
Set уже мог быть committed до ошибки summary; повтор всей процедуры может создать
другую запись set: в просмотренной `_create_set_result` нет idempotency lookup.
Это известная зависимость runtime, не право Coach повторять сохранение.
Для Coach один canonical event + alias backend ID, no repeated praise, late scope check.

## 3. Проверенная семантика фактов

| Данные | Что реально означает / решение |
|---|---|
| `selectedUserId` | Есть в app-store и hardware snapshot. Сверять оба с captured run; UI fallback «alexey» не identity/consent. Hardcoded getUserName не источник персонального имени |
| `emittedAt` | UTC в момент построения snapshot, не timestamp каждого сенсорного измерения. Controller time отдельно; browser receive monotonic age ещё добавить |
| `repetitionCount` / `partialReps` | Подтверждённый счётчик существующего controller по выбранному count source. Count не пересчитывать из q/скорости; UI repAdjustment не незаметная подмена hardware count |
| `loadTargetKg` | Настройка/целевая величина, не факт измеренного усилия |
| `loadEffectiveKg` | Расчёт controller: ramp × direction/curve/slow/levitation с уменьшением при spotter; не универсально измеренный фактический вес. Isometric path имеет другую семантику |
| `userForceKg` / drive forces | Другие каналы; не подменять ими applied load или доказанное усилие тела |
| `amplitudePercent` | Сейчас нормализованная **текущая позиция** в диапазоне, не амплитуда полного rep/set. Нельзя хвалить «амплитуду 95%» по этому полю |
| `concentricS` / `eccentricS` | Последние интервалы направления в controller time; mapping зависит от start_point. Это не array метрик каждого rep и не body technique |
| `repQuality` | Эвристика excursion и длительности, не наблюдение техники тела; универсальную оценку не произносить |
| Controller `rep` events | Для motion count есть payload repetition/durationS; для load count duration может отсутствовать. `events_payload` ограничен, snapshot не включает эти events. Не заявлять, что timings вообще отсутствуют; для Coach пока нет гарантированной полной доставки и накопления |
| `last_rep_pending` | Публичный надёжный event rep-start не найден. Private `_rep_started_at` не speech API. Cue выключен до появления проверенного источника |
| Сохранённый `weightKg` | Сейчас frontend actualWeight из плана/ручной правки, не persisted серия effective load; источник нужно маркировать |
| Сохранённый `tempoLabel` | `buildCurrentSetResult` ставит «хорошо»/«частично», это scaffold, не измеренная aggregate tempo policy |
| Сохранённые effort/pain | Effort/RIR могут вычисляться шаблонно, pain/techniqueBreakdown ставятся false. Отсутствие explicit pain input не доказывает отсутствие боли |
| Сохранённая длительность | Модель допускает duration_seconds, но текущий toBackendSetPayload её не передаёт; exercise startedAt синтетически вычитается по числу подходов. Не делать точные duration claims из scaffold |
| `calibration_state` / training_mode | Есть label/status и strengthMode ID; нет доказанной исторической серии аппаратных диапазонов/версии калибровки/load mode в текущем payload |

Доказательства: [расчёт позиции](../backend/app/services/motion/controller.py#L438-L460),
[dynamic load](../backend/app/services/motion/controller.py#L920-L975),
[fixed/isometric](../backend/app/services/motion/controller.py#L977-L1014),
[rep/phase metrics](../backend/app/services/motion/controller.py#L1230-L1297),
[events_payload](../backend/app/services/hardware_runtime.py#L1072-L1074),
[frontend result и payload](../frontend/src/screens/exercise-session/exercise-session-screen.tsx#L860-L953),
[DB creation](../backend/app/services/runtime_service.py#L68-L131).

### Что неизвестно и как не блокировать E02

- Нужны monotonic freshness/ordering, captured scope и нормализованный result provenance.
- Нужен отдельный confirmed event contract для stop/save/finalization и result aliases.
- Для comparable history пока не хватает доказанных calibration/range/load/count-source
  условий: по умолчанию limited/unavailable, не рекорд и не процент улучшения.
- Within-set median tempo только после bounded сборщика пригодных observations
  с continuity policy; sensor tick sampling не заменяет per-rep observations.
- Kinds остаются machine/bodyweight/timed/stretch/group; isometric/fixed_hold —
  control modes. Не использовать чужой гриф для bodyweight/time прогресса.
- Consent/revision/real operator auth/vault ещё делать в E03, ledger в E04.
- Count default и голоса остаются proposals; для E02 можно тестировать разные profiles.
- Никаких body vision, диагнозов, советов терпеть боль или команд нагрузки от Coach.

Это обнаруженные ограничения, не запрос изменить согласованные требования.
Без отсутствующих prerequisites соответствующий trigger получает skip reason.

## 4. Аудиопакеты — E01.4

| Проверка | Результат |
|---|---|
| Ожидаемый private pack root | Отсутствует на диске |
| Coach media/public directories | Отсутствуют |
| Аудиофайлы в текущих backend media и frontend public | 0 файлов с .wav/.mp3/.ogg/.pcm/.flac |
| Pack artifacts в tree `ed20a6e` | 0 tracked paths |
| Pack paths в `git rev-list --objects --all` | Не найдены во всех доступных refs |
| Manifest/receipt/checksum/decode | N/A: артефактов нет, нечего принять |
| Russian pronunciation/voice/style/model provenance | Не проверено, нет доступной записи |
| Права/условия использования исторических записей | Не подтверждены; старые заметки/названия профилей не доказательство |
| ffmpeg / ffprobe на этой машине | Не найдены; node/npm доступны |

**Пригодных пакетов к reuse: 0.** Никакие файлы не объявлены ready.
В E05 допустимы явно тестовые audio fixtures/локально синтезированный тестовый
сигнал без API; это не выбранный голос. В E08 выбрать реальные голоса, в E09 —
явная capped generation либо повторный аудит найденных артефактов.
Отсутствие pack не блокирует E02 contracts/fakes/replay.
Если записи позднее восстановятся из внешнего backup, checksum/decode/provenance
и человеческое прослушивание должны быть выполнены заново до использования.

## 5. Baseline — E01.5

Проверки выполнены на текущем дереве, не на историческом Coach.
Приложение не перезапускалось; не использовались пользовательская DB/media.
Не читались API keys, dotenv contents, private transcript/logs или персональные результаты.

### Изоляция backend

Использован текущий virtualenv Python. До импорта app задавались:
APP_ENV=test, HARDWARE_ADAPTER=emulator, panel=false, keyboard simulation=false;
DATABASE_URL/MEDIA_ROOT/OPENAPI_EXPORT_PATH в TemporaryDirectory.
`Settings.model_config['env_file']=None`, cache очищен, значения emulator/DB
проверены assert. `modbus_service.connect`, `socket.socket.connect/connect_ex`
заменены fail-fast запретом. API TestClient работает in-process.
Существующий fixture создаёт собственные временные seeded DB; lifespan bootstrap
тоже работает только с временной DB. Запуск pytest с `-p no:cacheprovider`.

### Результаты

| Проверка | Область / команда | Итог |
|---|---|---|
| Backend pytest | stage9_training_api, stage9_qa, users_api, `-q --disable-warnings -p no:cacheprovider` под описанной изоляцией | **30 passed**, 1 warning; 4,50 с |
| Frontend Vitest | 10 файлов: runtime-store; exercise-session/setup/summary; rest; workout-summary; settings; forma-shell; safety-dialog; hardware-realtime-provider | **76 passed, 1 failed**; 7,89 с |
| TypeScript | frontend local tsc `--noEmit` | **FAIL, 23 diagnostics** в 7 существующих файлах; exit 2 |
| Vite production bundling | local vite build в TemporaryDirectory, отдельный от tsc | **PASS**, 1839 modules; 4,00 с; chunk size warning |
| Backend scoped Ruff | runtime_service, hardware_runtime, analytics, settings model, runtime routes, config, conftest | **PASS** |
| Frontend lint | [package scripts](../frontend/package.json), конфигурация | lint script / eslint.config отсутствуют; **не запускался**, не PASS |

Важно: [npm build](../frontend/package.json#L11) = tsc && vite build.
Из-за tsc ошибок общий build gate **не проходит**, несмотря на успешный отдельный Vite.
Все времена — один measured run, не SLA/benchmark. Первый frontend запуск не вернул
доступный вывод, поэтому подтверждённый результат получен повторным scoped запуском.

### Существующие проблемы, не исправляемые в аудите

- Frontend failure: [settings test](../frontend/src/screens/settings/system-settings-screen.test.tsx#L190)
  ожидает Modbus link в main navigation; фактический header его не содержит.
  Остальные 9 файлов scoped suite прошли.
- 12 TS2740: [photo mocks](../frontend/src/mocks/stage4-data.ts#L48-L50)
  и [photo history mock](../frontend/src/mocks/stage4-data.ts#L77), неполный ProfilePhotoShot.
- 2 TS18048/TS18047: [photo progress](../frontend/src/screens/photo-progress/photo-progress-screen.tsx#L261-L262).
- 1 TS2322: [quick-start](../frontend/src/screens/quick-start/quick-start-screen.tsx#L201), unsupported listMode.
- 5 TS2322: [settings metrics](../frontend/src/screens/settings/system-settings-screen.tsx#L307),
  [metrics](../frontend/src/screens/settings/system-settings-screen.tsx#L336),
  [cards](../frontend/src/screens/settings/system-settings-screen.tsx#L394-L395),
  [cards](../frontend/src/screens/settings/system-settings-screen.tsx#L508), tone widened to string.
- 1 TS2783: [today](../frontend/src/screens/today/today-workout-screen.tsx#L92), duplicate id.
- 2 TS6133: [details dialog](../frontend/src/shared/ui/training/exercise-details-dialog.tsx#L26)
  и [runtime store](../frontend/src/stores/runtime-store.ts#L556), unused variables.
- Vitest warnings: jsdom HTMLMediaElement.play not implemented, некоторые React
  updates вне act. Не считать это acoustic validation.
- Vite single large JS chunk ~3,82 MB minified/~587 kB gzip; отдельно учесть при
  планировании lazy Coach UI, не объявлять текущую загрузку оптимизированной.

Этот baseline не требует «всё зелёное» для завершения аудита: он фиксирует исходные
ошибки, чтобы в дальнейших этапах отличать новые регрессии. Не запускались full
hardware suites, настоящая workout, provider pilots или browser acoustic tests.

## 6. Приёмка E01.G и следующий шаг

- Исходники/history проверены; reuse/new выбран явно.
- Существующие/параллельные пользовательские runtime изменения не откатывались.
- Lifecycle, stop/save distinction и unsafe factual sources описаны с ссылками.
- Отсутствие packs проверено; аудио не принято по старым заметкам.
- Baseline выполнен безопасно, failures/warnings явно перечислены.
- Границы hardware, privacy, paid calls не нарушены.

**E02.1:** contracts settings/run/event/facts/decision/audio/usage с schemaVersion,
provenance/unknown и documented enum reasons. Далее fakes/clocks/replay, read-only
event hooks и feature flags off. По последующему указанию пользователя E02
реализуется полностью с нуля, без исходников и тестов back/back2.