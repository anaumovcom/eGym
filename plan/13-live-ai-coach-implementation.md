# AI-тренер — поэтапная реализация и прогресс

Создан: 07.10.2026. Версия плана: 1.0. Спецификация: v0.3.

**Текущее состояние: проектирование подготовлено; реализация по этому плану не начата.**
**Закрыто этапов реализации: 0 из 12.** Это не процент трудозатрат.
Следующий этап: **E01 — аудит и фиксация исходного состояния**.

Этот файл — единственный рабочий трекер реализации. После каждого завершённого
пункта обновляем его чекбокс, статус этапа и доказательства проверки.
Технические решения и подробности остаются в спецификациях:

- [Обзор и требования](13-live-ai-coach.md).
- [Архитектура и контракты](13-live-ai-coach-spec.md).
- [66 триггеров, сценарии и промпты](13-live-ai-coach-behavior-prompts.md).
- [Настройки, API key, диагностика, пакеты и микшер](13-live-ai-coach-controls-audio.md).

## 1. Как отмечаем прогресс

- `[ ]` — ещё не принято; `[x]` — результат получен и проверен.
- Статус этапа: **Не начат / В работе / Заблокирован / На приёмке / Готов**.
- Одновременно один основной этап «В работе». Независимую подзадачу можно
  делать параллельно, но не объявлять весь зависимый этап готовым заранее.
- Перед началом указать активный пункт в таблице; после проверки отметить его сразу.
- «Код написан» не равно «готов»: нужны тесты и критерий выхода этапа.
- Чекбокс пользовательского прослушивания отмечается только после подтверждения
  пользователя. Логи `playback_started` не доказывают слышимость динамиков.
- Для блокировки указать причину, что уже сделано и что нужно для продолжения.
- При изменении решений сначала обновить соответствующую спецификацию,
  затем зависимости/пункты здесь. Не менять согласованные требования молча.
- Регрессию помечаем снятием соответствующего чекбокса и записью причины.
- Результаты проверок записываем с датой, областью, командой/методом и итогом;
  старые результаты не выдаём за проверку новой версии.
- Подробные отчёты можно вынести в отдельные файлы после их создания;
  секреты и полные персональные данные в трекер не добавлять.

Число «закрыто этапов» вверху обновляется при переходе этапа в «Готов».
Проектирование E00 не включается в 12 этапов реализации.

## 2. Панель прогресса

| Этап | Результат | Зависит от | Статус | Активный пункт / блокировка |
|---|---|---|---|---|
| E00 | Проектные документы | — | Готов | v0.3 подготовлена; defaults требуют пилота |
| E01 | Аудит исходников, пакетов и baseline | E00 | Не начат | Следующий этап |
| E02 | Контракты, каркас и тестовый replay | E01 | Не начат | — |
| E03 | Настройки, согласие и безопасный ключ | E02 | Не начат | — |
| E04 | Серверный run, учёт расходов и ownership | E02, E03 | Не начат | — |
| E05 | Локальный звук, микшер и первый debug | E02, E03 | Не начат | — |
| E06 | Интерпретатор и локальные события тренировки | E04, E05 | Не начат | — |
| E07 | Режиссёр, промпты и генерация текста | E04, E06 | Не начат | — |
| E08 | Сетевая озвучка и платный выбор голосов | E03–E05, E07 | Не начат | — |
| E09 | Подготовка голосовых пакетов по кнопке | E04, E05, E08 | Не начат | — |
| E10 | Полный живой тренер, история и все сценарии | E06–E09 | Не начат | — |
| E11 | Полные настройки, диагностика и отказоустойчивость | E09, E10 | Не начат | — |
| E12 | Приёмка, настройка качества и выпуск | E01–E11 | Не начат | — |

### Контрольные вехи

- [ ] **M1:** безопасные настройки + бюджетные primitives, до любых paid calls — E03–E04.
- [ ] **M2:** локальный тренер со счётом, микшером и mini-debug без сети — E05–E06.
- [ ] **M3:** проверенные тексты и выбранная русская озвучка — E07–E08.
- [ ] **M4:** пакеты готовятся по кнопке, вся тренировка контекстная — E09–E10.
- [ ] **M5:** полный UX, recovery, проверки и пользовательское прослушивание — E11–E12.

## 3. E00 — проектирование

**Статус: Готов как документирование, не как реализация или финальный выбор моделей.**

- [x] Зафиксированы требования пользователя: характер, русский male/female голос,
  частое общение, память, отсутствие микрофона, бюджет и одновременные фразы.
- [x] Описаны архитектура, runtime-нюансы, факты, safety и жизненный цикл.
- [x] Подготовлены 66 поводов, плотность, сценарии и конкретные промпты.
- [x] Спроектированы настройки, key flow, mini-debug, пакеты и микшер.
- [x] Разрешение на платные тесты зафиксировано; реальные запросы не выполнялись.
- [x] Подготовлен этот трекер реализации.

**Не принято автоматически:** конкретные голоса/provider, default счёта,
комфортная плотность речи, цены реальной тренировки и пригодность старых пакетов.

## 4. E01 — аудит и безопасный baseline

**Цель:** понять, что действительно есть на диске, что можно использовать и какие
проблемы относятся к тренеру, не затрагивая текущую работу оборудования.

- [ ] **E01.1** Проверить текущие исходники, Git/history и доступность прежнего Coach;
  выбрать восстановление пригодного кода или новый модуль. Не использовать bytecode как архитектуру.
- [ ] **E01.2** Зафиксировать уже изменённые пользователем файлы и границы задачи;
  не откатывать чужие изменения в runtime, приводах и watch-скриптах.
- [ ] **E01.3** Проверить события начала/паузы/завершения, save ack, фактическую
  нагрузку, selected user и timestamp semantics на текущей версии кода.
- [ ] **E01.4** Аудировать приватные voice packs: manifest, checksum, decode,
  русский голос, style/model versions и разрешённое использование; без paid регенерации.
- [ ] **E01.5** Записать baseline scoped backend/frontend tests, build/typecheck/lint
  и существующие unrelated ошибки. Тесты не запускают реальный мотор.
- [ ] **E01.6** Создать карту интеграции и список неизвестных данных/метрик;
  не предполагать per-rep timestamps, body vision или достоверность UI labels.
- [ ] **E01.G** Приёмка: выбран путь реализации, известны ограничения и baseline;
  нет запуска движения/снятия аварии/изменения hardware config ради аудио.

**Результат этапа:** короткий аудит с проверенными фактами и решением reuse/new.

## 5. E02 — контракты, каркас и replay

**Цель:** создать основу, которую можно тестировать без ключа и тренажёра.

- [ ] **E02.1** Утвердить schemas Coach settings/run/event/facts/decision/audio/usage,
  enum reasons и schemaVersion. Реальные runtime kinds отдельно от control modes.
- [ ] **E02.2** Определить canonical dedup keys, scopeEpoch/planRevision/contextVersion,
  fact dependencies, start deadline и bounded queues.
- [ ] **E02.3** Создать interfaces text provider/voice adapter/pack storage/audio manager;
  fake providers, clocks и store fixtures для детерминированных тестов.
- [ ] **E02.4** Создать read-only точки событий `set_stopped`, `set_persisted`,
  `exercise_finalized`, `workout_finalized` с captured IDs; не менять поведение привода.
- [ ] **E02.5** Настроить изолированные tests и безопасный replay recorded/synthetic
  telemetry. Synthetic помечена тестовой и не пишет реальные достижения.
- [ ] **E02.6** Добавить feature flags; по умолчанию Coach off, никакого paid dispatch.
  Документировать новые endpoints до интеграции клиента.
- [ ] **E02.G** Приёмка: happy path, stale/scope/cancel и mock-source проверяются
  без сети; каркас не импортирует motor command API для тренерских действий.

**Результат:** согласованные контракты и рабочая тестовая инфраструктура.

## 6. E03 — настройки, consent и API key

**Цель:** пользователь безопасно настраивает тренера; секрет доступен только серверу.

- [ ] **E03.1** Реализовать typed per-user settings, draft/save, migrations,
  revision conflicts и защиту от поздней hydration другого пользователя.
- [ ] **E03.2** Реализовать consent, local/hybrid режимы и единое effective enabled
  с существующими soundEnabled/voiceHintsEnabled/volume; legacy true не включает paid Coach.
- [ ] **E03.3** Реализовать настоящую operator authorization для credential write;
  выбранный user/PIN в UI не считается достаточной аутентификацией.
- [ ] **E03.4** Выбрать server vault/keyring или encrypted storage с master key
  вне DB/Git. Проверить unattended Linux; при недоступности не сохранять plaintext.
- [ ] **E03.5** Добавить transient password input, save/replace/delete/status,
  key redaction в error/proxy/app logs, HTTPS/origin/CSRF policy.
- [ ] **E03.6** Реализовать read-only auth/metadata check без генерации речи;
  статус честно не обещает доступ ко всем inference models.
- [ ] **E03.7** Проверить user switch, opt-out, удалить secret из DOM после save,
  отсутствие key в GET settings/persist/export и отмену задач старой credentialVersion.
- [ ] **E03.G** Приёмка: настройки переживают restart без утечки между пользователями;
  ключ не раскрывается; сохранение/проверка ключа не запускает paid inference.

**Внешнее действие:** пользователь вводит ключ непосредственно в будущую форму;
не присылает его в чат и не передаёт через вопросы агента.

## 7. E04 — run, расходы и владение сессией

**Цель:** до первого платного теста обеспечить server-side контроль расходов.

- [ ] **E04.1** Реализовать persisted CoachRun, UsageAttempt, EventReceipt;
  provisional run привязывается к backend workout без сброса ledger.
- [ ] **E04.2** Реализовать atomic reserve/dispatch/settle/unsettled, pricing snapshot,
  caps и отдельные ledgers workout/test/pack плюс общую operator квоту.
- [ ] **E04.3** Нормализовать text/audio/cached/reasoning usage; dedup response IDs,
  исключить двойной учёт aggregate+response и учитывать unknown вместо вымышленного нуля.
- [ ] **E04.4** Проверить консервативный worst-case reserve; если строгий cap API
  недоказуем, явно показать target-limit и stop threshold с запасом.
- [ ] **E04.5** Реализовать paid single-flight, cancellation вне state lock,
  bounded timeouts/retry/circuit breaker и stale guards до/после await.
- [ ] **E04.6** Реализовать speaking owner/lease для нескольких вкладок,
  reconnect/restart recovery и REST usage snapshot.
- [ ] **E04.7** Создать bounded job runner/receipts для будущих paid pilots и pack
  generation; idempotent submit, pause/cancel, без обязательного Redis/Celery.
- [ ] **E04.G** Приёмка: fake paid scenarios доказывают, что reconnect/model switch,
  cancel/timeout/повтор submit не сбрасывают расходы и не создают двойной dispatch.

**Результат:** можно безопасно открыть ограниченные платные тесты, но пока их не запускать.

## 8. E05 — локальное аудио, микшер и mini-debug

**Цель:** первый работающий звук без LLM, с обязательным одновременным микшированием.

- [ ] **E05.1** Реализовать shared AudioContext, жест unlock, master volume,
  local decode/preload и clip eligibility. Для теста использовать verified audit clips
  или явно тестовые fixtures; не считать их окончательно выбранным голосом.
- [ ] **E05.2** Реализовать active utterance Map, per-utterance GainNode,
  actual startOrdinal, latest-start foreground и суммарный background gain.
- [ ] **E05.3** Реализовать attack/restore envelopes, нормализацию/headroom,
  восстановление после окончания foreground и bounded resources.
- [ ] **E05.4** Реализовать cancellation/disposal, safety/mute/hidden policy;
  ordinary переходы одного exercise не обрывают started speech.
- [ ] **E05.5** Добавить local preview и overlap demo без paid запросов;
  согласовать rep beep fallback без двойного сигнала по умолчанию.
- [ ] **E05.6** Добавить мини-кнопку AI в TopSystemBar перед MotorForceReadout,
  normal/compact, readiness, last actual source и local playback counters.
- [ ] **E05.7** Проверить focus/portal/safety modal, STOP виден, узкие экраны,
  масштабирование; offline render 1/2/3 voices и базовое браузерное playback.
- [ ] **E05.G** Приёмка: новая фраза приглушает старые только на actual start,
  count и comment не прерывают друг друга, mute/safety прекращают ordinary звук.

**Результат:** проверяемый локальный микшер и ранняя диагностика отсутствия звука.

## 9. E06 — интерпретатор и локальные тренировочные события

**Цель:** счёт и сигналы привязаны к реальным событиям, не к навигации UI.

- [ ] **E06.1** Реализовать coach phase machine с UI/hardware agreement,
  freshness/monotonic receive time и отдельными safety latches.
- [ ] **E06.2** Реализовать подтверждённый count/start/resume/end, baseline на
  reconnect/new set; скачок 5→8 не создаёт пачку старых чисел.
- [ ] **E06.3** Реализовать milestones/countdown только по однозначной цели;
  late «Последний» запрещён, без пригодного rep-start этот cue не создаётся.
- [ ] **E06.4** Реализовать timed/bodyweight/stretch/group/isometric/fixed_hold
  eligibility, progress unit и временные отметки без счёта по чужому грифу.
- [ ] **E06.5** Интегрировать stopped/persisted/rest/finalized события;
  различать полный/частичный/пропущенный результат и save delay/error.
- [ ] **E06.6** Реализовать dedup/receipt aliases, не сбрасывать opportunities
  при revisit/timer edits; изменения count применяются только к новым событиям.
- [ ] **E06.7** Прогнать pause/stale/failure/spotter/fault/pain/recovery matrix,
  mock/service guards и отсутствие motor commands от Coach.
- [ ] **E06.G** Приёмка M2: целая replay-тренировка звучит локально корректно,
  не повторяет старые события и остаётся безопасной при потере сети.

## 10. E07 — режиссёр, память и автор текста

**Цель:** разнообразные уместные реплики с проверяемыми фактами, пока без обязательной сети голоса.

- [ ] **E07.1** Реализовать registry всех T01–T66 и source prerequisites;
  unsupported данные означают skipped reason, не фиктивное наблюдение.
- [ ] **E07.2** Реализовать profiles, cooldown groups, coalescing, content/acoustic
  budgets и slots по фактическому времени/прогрессу, не случайный монолог по таймеру.
- [ ] **E07.3** Реализовать topics/openings/intents, attempted/started/completed
  memory, мотивы/callbacks и factMention guard.
- [ ] **E07.4** Добавить версионированные P0–P5 prompts, ordinary/locked-fact schemas,
  fact templates, безопасное отделение notes от инструкций и prompt hashes.
- [ ] **E07.5** Реализовать server fact builder/validators, history comparison policy
  и валидные tempo aggregates; несуществующие метрики исключить из речи.
- [ ] **E07.6** Подключить Luna adapter с caps/usage/cancel, fake и opt-in paid mode;
  corpus ≥150 случаев, включая negative/injection/partial/unavailable history.
- [ ] **E07.7** Провести малый разрешённый paid text pilot после E03–E04:
  8–12 случаев с выбранным cap, без голоса/движения; сохранить redacted результат.
- [ ] **E07.G** Приёмка: schema/facts проверены, разнообразие оценено, критичных
  выдумок в контрольном наборе нет; rejection даёт local/silence, не endless retry.

**Платный gate:** ключ существует server-side, выбран test cap, actual usage записан.
Если доступа к модели нет — этап заблокирован по paid pilot, остальные offline проверки сохраняются.

## 11. E08 — streaming voice и выбор моделей/голосов

**Цель:** измерить качество русского и выбрать экономичный voice path до массовой генерации пакетов.

- [ ] **E08.1** Реализовать Realtime mini и streaming TTS adapters через один
  capability interface; проверить реальные model IDs/voices/pricing/account access.
- [ ] **E08.2** Реализовать tagged PCM framing, codec/sample rate, jitter/ring buffer,
  underrun/gap handling, end/drain и ограниченные byte/duration/watchdogs.
- [ ] **E08.3** Интегрировать network utterances в микшер: chunks не новый start,
  reservations не duck, late generationId отвергается, gaps не держат фон в тишине.
- [ ] **E08.4** Реализовать transcript verification и явное различие streaming
  post-factum контроля от предварительной проверки; без ложной гарантии дословности.
- [ ] **E08.5** Провести малый paid voice pilot 4–8 текстов с capped test job;
  измерить стадии latency, usage и match, без настоящей workout/hardware commands.
- [ ] **E08.6** После shortlist провести 30-текстовый русский A/B с двумя голосами
  и adapters; cold/warm conditions, числа, юмор, partial, overlap и длинное прослушивание.
- [ ] **E08.7** Пользователь прослушал примеры; записать выбранный text/voice path,
  male/female voice IDs, причины выбора, цену/latency и ограничения.
- [ ] **E08.G** Приёмка M3: выбранный голос естественен, числа понятны, actual costs
  измерены; factual speech направляется в подходящий verified path.

**Важно:** не строить окончательный pack выбранным наугад голосом до этой приёмки.

## 12. E09 — голосовые пакеты и подготовка по кнопке

**Цель:** частые фразы готовятся явно, работают быстро и не оплачиваются повторно без причины.

- [ ] **E09.1** Утвердить редакторский каталог required/optional clips и safety texts,
  mechanical eligibility; проверить совместимость audited старых записей.
- [ ] **E09.2** Реализовать dry-run plan: coverage, fingerprints, sizes, missing/corrupt,
  отдельно generated/downloaded/decoded readiness и estimate/cap.
- [ ] **E09.3** Реализовать «Подготовить частые фразы»: готовое только fetch/decode;
  missing generation — отдельный явный paid action с выбранными clip IDs.
- [ ] **E09.4** Реализовать resumable capped generation job, idempotent submit,
  pause/cancel/progress/receipts; crash recovery не blindly оплачивает всё снова.
- [ ] **E09.5** Реализовать atomic artifact/manifest publish, checksums, decoded duration,
  loudness verification, pinned packVersion и сохранение старого compatible pack.
- [ ] **E09.6** Реализовать whitelist serving, encoded browser cache, decoded RAM LRU,
  quota/eviction, preload required clips, deletion и честный offline статус.
- [ ] **E09.7** Подготовить оба выбранных voice packs в пределах отдельных caps;
  проверить required clips decode и прослушать count/start/safety/overlap.
- [ ] **E09.G** Приёмка: repeated prepare готового pack не вызывает inference,
  partial не считается ready, voice switch не подменяет голос, quota не запускает paid regenerate.

**Платный gate:** pack cap отдельно от $2/workout; пользователь видит число новых клипов.

## 13. E10 — полный живой тренер на тренировке

**Цель:** все этапы звучат как один внимательный напарник, а не отдельные демо.

- [ ] **E10.1** Подключить end-to-end admission→text→validation→voice→mixer→acks;
  повторные проверки scope/dependencies/deadline перед actual start.
- [ ] **E10.2** Подключить setup/active/pause/resume/rest/exercise/workout сценарии,
  полные/частичные/aborted/skipped, bodyweight/timed/stretch/group/hold modes.
- [ ] **E10.3** Подключить авторитетную историю, comparable/limited/unavailable,
  highlights/records только от app detectors, без чтения всей истории в prompt.
- [ ] **E10.4** Подключить антиштампы, распределение intents и сюжетные callbacks
  по actual playback; save feedback/end summary coalescing без дублей похвалы.
- [ ] **E10.5** Подключить pack local fast path + live contextual, budget degradation,
  no paid auto-fallback и отсутствие старых реплик после recovery.
- [ ] **E10.6** Проверить 12 продуктовых сценариев и 10–15 целых replay workouts;
  долю речи, интервал, переключение settings и цена по actual usage при opt-in pilot.
- [ ] **E10.G** Приёмка M4: целая тренировка проходит с контекстом и всеми
  сценариями; Coach не меняет hardware, не выдумывает историю и не надоедает повторами.

## 14. E11 — полный UX, debug и recovery

**Цель:** довести ранний mini-debug и основные настройки до полного пользовательского интерфейса.

- [ ] **E11.1** Завершить карточки настроек, advanced/presets/diff, workout overrides,
  быстрые controls и доступность, без молчаливого сохранения override в профиль.
- [ ] **E11.2** Завершить header counters req/tokens/cost, stage/model breakdown,
  complete/partial/unknown usage, settled/pending/reserved; local/cache не paid.
- [ ] **E11.3** Завершить причины молчания, timeline/latency, prompt/pack versions,
  active/audible voices/foreground/gains/buffer metrics и redacted export.
- [ ] **E11.4** Завершить ephemeral debug TTL/privacy, owner/user switch,
  consent revoke/delete memory; clear diagnostics не сбрасывает ledger.
- [ ] **E11.5** Протестировать restart/reconnect/key rotation/two tabs/provider outage,
  incomplete usage, interrupted jobs и отсутствие блокировок state lock.
- [ ] **E11.6** Проверить normal/compact header 360/722/1024/1920/3840 px,
  scale 100/125/150%, keyboard/touch, safety modal и видимость STOP.
- [ ] **E11.7** Завершить capped test wizard с отдельным ledger; звуковые тесты
  не мешают незавершённой реальной workout и не пишут training achievements.
- [ ] **E11.G** Приёмка: пользователь понимает, почему тренер молчит, сколько
  потрачено и как подготовить звук; debug/настройки не обходят privacy/safety/budget.

## 15. E12 — приёмка и выпуск

**Цель:** подтвердить, что тренера хочется слушать целую тренировку, и зафиксировать release defaults.

- [ ] **E12.1** Полные scoped unit/integration/replay tests, build/lint/typecheck;
  unrelated baseline failures отмечены отдельно, новых Coach ошибок нет.
- [ ] **E12.2** Security/privacy review: key vault/redaction/auth, private cache,
  secret endpoints, no browser persisted key и no cross-user данные.
- [ ] **E12.3** Budget/usage review: sent/cancel/retry/reconnect, cap reservation,
  test/pack/workout segregation, отсутствие phantom free/zero usage.
- [ ] **E12.4** Offline audio render/peak checks, реальные динамики, русский count,
  overlap ≥10–15 минут и целая workout ≥45–60 минут либо фактическая типовая длина.
- [ ] **E12.5** Пользователь оценил уместность/естественность/понятность/утомляемость;
  подобрать density, count default, voices, ducking и rest windows, обновить спецификации.
- [ ] **E12.6** Контрольный capped end-to-end paid run с actual usage и latency;
  без live motor experiments ради теста. При последующей настоящей workout Coach
  остаётся read-only наблюдателем существующего штатного процесса.
- [ ] **E12.7** Описать setup/key/prepare/troubleshooting/backup/rotation/rollback,
  release flags и действия при отсутствии provider/pack.
- [ ] **E12.8** Закрыть критичные defects, подтвердить принятие пользователем;
  deferred улучшения перечислить отдельно, не скрывать как «готово».
- [ ] **E12.G** Приёмка M5: согласованные требования реализованы и подтверждены;
  нет critical safety/privacy/fact/budget дефектов, есть безопасное выключение/rollback.

## 16. Блокировки и нерешённые решения

Пока перечислены будущие зависимости, **они не означают, что реализация начата**.

| ID | Что необходимо | Когда нужно | Состояние |
|---|---|---|---|
| D01 | Выбор reuse/new после проверки исходников | E01 | Не проверено заново |
| D02 | Operator auth и пригодное server secret storage | E03 | Требует реализации |
| D03 | Ввод ключа пользователем в безопасную форму | Paid E07–E09 | Ожидает готового UI, значение не хранить здесь |
| D04 | Доступ аккаунта к моделям/voices и актуальные цены | E08 | Не подтверждён реальным пилотом |
| D05 | Выбранные male/female voices и adapter | E08 | Выбираются по A/B |
| D06 | Caps текстового/voice/pack заданий | Перед каждым новым paid job | Выбираются явно, внутри job попытки разрешены |
| D07 | Типовая длительность/отдых и count default | E12, можно уточнить раньше | Пока proposals |
| D08 | Прослушивание и пользовательская приёмка | E08/E09/E12 | Не выполнены |

При фактической блокировке добавлять: stage/task, причина, дата, следующий шаг.
Не просить ключ в чате и не читать существующие секреты, чтобы «ускорить проектирование».

## 17. Журнал проверок и решений

| Дата | Этап/пункт | Выполнено | Доказательство / проверка | Следующий шаг |
|---|---|---|---|---|
| 07.10.2026 | E00 | Подготовлены документы v0.3 и этот трекер | Проектные документы существуют; не свидетельство работающего Coach | E01.1 |

При завершении реализации каждого пункта добавляем запись. Для paid:
job/run ID, stage/model, cap, reported usage completeness, estimated cost,
latency/результат. Не key и не полный персональный transcript.

## 18. Вне первого релиза

- Голосовой микрофонный диалог и постоянный listening.
- Автоматическое управление весом/движением от LLM.
- Оценка техники тела по камере и медицинские рекомендации.
- Fine-tuning, обязательная vector DB и распределённая инфраструктура без необходимости.
- Автоматическая paid регенерация при включении/отсутствии pack.
- Неограниченная речь/бюджет или скрытый дорогой provider fallback.

Эти направления не обязательны для классного первого релиза и не отвлекают
от уместности, разнообразия, быстрого счёта и качественного микшера.