# AI-тренер — поэтапная реализация и прогресс

Создан: 07.10.2026. Версия плана: 1.0. Спецификация: v0.3.

**Текущее состояние: E06 готов; E07, E08 и E09 offline готовы; paid pilot, выбор голоса, генерация пакетов и прослушивание заблокированы.**
**Закрыто этапов реализации: 6 из 12.** Это не процент трудозатрат.
Следующий этап: **E10 — полный живой тренер** (не начат: зависит от E07–E09; ждут ключ, pilot и прослушивание E07.7/E07.G, E08.1, E08.5–E08.G, E09.1, E09.7/E09.G).
Доказательства E01: [отчёт аудита](13-live-ai-coach-e01-audit.md).
Контракты/API и доказательства E02: [отчёт реализации](13-live-ai-coach-e02-contracts.md).
Контракты/API, setup и доказательства E03–E04: [control-plane отчёт](13-live-ai-coach-e03-e04-control-plane.md).
Код, браузерная приёмка и ограничения E05: [локальное аудио](13-live-ai-coach-e05-local-audio.md).
Интерпретатор и локальные cue E06: [отчёт](13-live-ai-coach-e06-interpreter.md).

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
| E01 | Аудит исходников, пакетов и baseline | E00 | Готов | [Аудит и baseline](13-live-ai-coach-e01-audit.md); packs отсутствуют, исходные failures записаны |
| E02 | Контракты, каркас и тестовый replay | E01 | Готов | [Контракты и проверки](13-live-ai-coach-e02-contracts.md); без reuse back/back2 |
| E03 | Настройки, согласие и безопасный ключ | E02 | Готов | [Отчёт](13-live-ai-coach-e03-e04-control-plane.md); provisioning оператором ещё не выполнялся |
| E04 | Серверный run, учёт расходов и ownership | E02, E03 | Готов | [Отчёт](13-live-ai-coach-e03-e04-control-plane.md); SQLite durable ledger, synthetic adapters |
| E05 | Локальный звук, микшер и первый debug | E02, E03 | Готов | [Отчёт](13-live-ai-coach-e05-local-audio.md); TEST tones, не русские voices |
| E06 | Интерпретатор и локальные события тренировки | E04, E05 | Готов | [Отчёт](13-live-ai-coach-e06-interpreter.md); TEST buffers, русские клипы — E09 |
| E07 | Режиссёр, промпты и генерация текста | E04, E06 | Offline готов / pilot заблокирован | E07.7 |
| E08 | Сетевая озвучка и платный выбор голосов | E03–E05, E07 | Offline готов / pilot и выбор голоса заблокированы | [Отчёт](13-live-ai-coach-e08-voice.md); E08.1 |
| E09 | Подготовка голосовых пакетов по кнопке | E04, E05, E08 | Offline готов / каталог, генерация и прослушивание заблокированы | [Отчёт](13-live-ai-coach-e09-voice-packs.md); E09.1, E09.7 |
| E10 | Полный живой тренер, история и все сценарии | E06–E09 | Не начат | — |
| E11 | Полные настройки, диагностика и отказоустойчивость | E09, E10 | Не начат | — |
| E12 | Приёмка, настройка качества и выпуск | E01–E11 | Не начат | — |

### Контрольные вехи

- [x] **M1:** безопасные настройки + бюджетные primitives, до любых paid calls — E03–E04 (offline проверено; paid adapters ещё отсутствуют).
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

**Статус: Готов, 07.10.2026.** [Доказательства всех пунктов](13-live-ai-coach-e01-audit.md).

- [x] **E01.1** Проверить текущие исходники, Git/history и доступность прежнего Coach;
  выбрать восстановление пригодного кода или новый модуль. Не использовать bytecode как архитектуру.
- [x] **E01.2** Зафиксировать уже изменённые пользователем файлы и границы задачи;
  не откатывать чужие изменения в runtime, приводах и watch-скриптах.
- [x] **E01.3** Проверить события начала/паузы/завершения, save ack, фактическую
  нагрузку, selected user и timestamp semantics на текущей версии кода.
- [x] **E01.4** Аудировать приватные voice packs: manifest, checksum, decode,
  русский голос, style/model versions и разрешённое использование; без paid регенерации.
  Результат: артефакты отсутствуют на диске и в доступных refs; checksum/decode/
  прослушивание N/A, пригодных packs 0. Это завершённый аудит отсутствия, не приёмка звука.
- [x] **E01.5** Записать baseline scoped backend/frontend tests, build/typecheck/lint
  и существующие unrelated ошибки. Тесты не запускают реальный мотор.
- [x] **E01.6** Создать карту интеграции и список неизвестных данных/метрик;
  не предполагать per-rep timestamps, body vision или достоверность UI labels.
- [x] **E01.G** Приёмка: выбран путь реализации, известны ограничения и baseline;
  нет запуска движения/снятия аварии/изменения hardware config ради аудио.

**Результат этапа:** аудит завершён; по уточнению пользователя реализация полностью новая,
без reuse исходников/тестов back/back2;
backend 30 passed, frontend 76 passed/1 baseline failed, TypeScript 23 baseline
diagnostics, Vite отдельно PASS, scoped Ruff PASS. Общий build gate не зелёный;
исходные ошибки не скрыты и не исправлялись в рамках аудита.

## 5. E02 — контракты, каркас и replay

**Цель:** создать основу, которую можно тестировать без ключа и тренажёра.

**Статус: Готов, 07.10.2026.** [Контракты/API, границы и доказательства](13-live-ai-coach-e02-contracts.md).

- [x] **E02.1** Утвердить schemas Coach settings/run/event/facts/decision/audio/usage,
  enum reasons и schemaVersion. Реальные runtime kinds отдельно от control modes.
- [x] **E02.2** Определить canonical dedup keys, scopeEpoch/planRevision/contextVersion,
  fact dependencies, start deadline и bounded queues.
- [x] **E02.3** Создать interfaces text provider/voice adapter/pack storage/audio manager;
  fake providers, clocks и store fixtures для детерминированных тестов.
- [x] **E02.4** Создать read-only точки событий `set_stopped`, `set_persisted`,
  `exercise_finalized`, `workout_finalized` с captured IDs; не менять поведение привода.
- [x] **E02.5** Настроить изолированные tests и безопасный replay recorded/synthetic
  telemetry. Synthetic помечена тестовой и не пишет реальные достижения.
- [x] **E02.6** Добавить feature flags; по умолчанию Coach off, никакого paid dispatch.
  Документировать новые endpoints до интеграции клиента.
- [x] **E02.G** Приёмка: happy path, stale/scope/cancel и mock-source проверяются
  без сети; каркас не импортирует motor command API для тренерских действий.

**Результат:** versioned backend/frontend contracts, ports/fakes, bounded test-only replay,
read-only lifecycle с after-commit server observations, flags off и публичный
GET /api/coach/capabilities (paidDispatch всегда false). Backend 70 PASS, frontend
55 PASS, scoped Ruff/Vite/editor/diff checks PASS; TS — только 23 исходных diagnostics.
Production генерация, звук, persisted настройки/ledger и credentials ещё не реализованы.

## 6. E03 — настройки, consent и API key

**Цель:** пользователь безопасно настраивает тренера; секрет доступен только серверу.

**Статус: Готов, 07.10.2026.** [Контракты, security/setup и доказательства](13-live-ai-coach-e03-e04-control-plane.md).

- [x] **E03.1** Реализовать typed per-user settings, draft/save, migrations,
  revision conflicts и защиту от поздней hydration другого пользователя.
- [x] **E03.2** Реализовать consent, local/hybrid режимы и единое effective enabled
  с существующими soundEnabled/voiceHintsEnabled/volume; legacy true не включает paid Coach.
- [x] **E03.3** Реализовать настоящую operator authorization для credential write;
  выбранный user/PIN в UI не считается достаточной аутентификацией.
- [x] **E03.4** Выбрать server vault/keyring или encrypted storage с master key
  вне DB/Git. Проверить unattended Linux; при недоступности не сохранять plaintext.
- [x] **E03.5** Добавить transient password input, save/replace/delete/status,
  key redaction в error/proxy/app logs, HTTPS/origin/CSRF policy.
- [x] **E03.6** Реализовать read-only auth/metadata check без генерации речи;
  статус честно не обещает доступ ко всем inference models.
- [x] **E03.7** Проверить user switch, opt-out, удалить secret из DOM после save,
  отсутствие key в GET settings/persist/export и отмену задач старой credentialVersion.
- [x] **E03.G** Приёмка: настройки переживают restart без утечки между пользователями;
  ключ не раскрывается; сохранение/проверка ключа не запускает paid inference.

**Внешнее действие:** пользователь вводит ключ непосредственно в будущую форму;
не присылает его в чат и не передаёт через вопросы агента.
Форма уже доступна в Общих настройках; перед вводом требуется самостоятельный
operator/vault setup и обычное применение migration 0007. На текущем устройстве
эти deployment действия не выполнялись. Ни save, ни check не запускают inference.
External proxy logging/TLS policy описана в отчёте и требует настройки оператором.

## 7. E04 — run, расходы и владение сессией

**Цель:** до первого платного теста обеспечить server-side контроль расходов.

**Статус: Готов, 07.10.2026.** SQLite control-plane primitives; production paid adapter не подключён.

- [x] **E04.1** Реализовать persisted CoachRun, UsageAttempt, EventReceipt;
  provisional run привязывается к backend workout без сброса ledger.
- [x] **E04.2** Реализовать atomic reserve/dispatch/settle/unsettled, pricing snapshot,
  caps и отдельные ledgers workout/test/pack плюс общую operator квоту.
- [x] **E04.3** Нормализовать text/audio/cached/reasoning usage; dedup response IDs,
  исключить двойной учёт aggregate+response и учитывать unknown вместо вымышленного нуля.
- [x] **E04.4** Проверить консервативный worst-case reserve; если строгий cap API
  недоказуем, явно показать target-limit и stop threshold с запасом.
- [x] **E04.5** Реализовать paid single-flight, cancellation вне state lock,
  bounded timeouts/retry/circuit breaker и stale guards до/после await.
- [x] **E04.6** Реализовать speaking owner/lease для нескольких вкладок,
  reconnect/restart recovery и REST usage snapshot.
- [x] **E04.7** Создать bounded job runner/receipts для будущих paid pilots и pack
  generation; idempotent submit, pause/cancel, без обязательного Redis/Celery.
- [x] **E04.G** Приёмка: fake paid scenarios доказывают, что reconnect/model switch,
  cancel/timeout/повтор submit не сбрасывают расходы и не создают двойной dispatch.

**Результат:** можно безопасно открыть ограниченные платные тесты, но пока их не запускать.
Control plane проверен на synthetic adapters: реальные pricing/cap enforceability
и production dispatch требуют E07/E08 и остаются fail-closed. Job resume сейчас
только сохраняет queued state; не запускает фоновую paid генерацию. Ledger/run
клиент будет связан с end-to-end тренировкой на следующих этапах.

## 8. E05 — локальное аудио, микшер и mini-debug

**Цель:** первый работающий звук без LLM, с обязательным одновременным микшированием.

**Статус: Готов, 07.10.2026.** [Реализация и проверки](13-live-ai-coach-e05-local-audio.md).

- [x] **E05.1** Реализовать shared AudioContext, жест unlock, master volume,
  local decode/preload и clip eligibility. Для теста использовать verified audit clips
  или явно тестовые fixtures; не считать их окончательно выбранным голосом.
- [x] **E05.2** Реализовать active utterance Map, per-utterance GainNode,
  actual startOrdinal, latest-start foreground и суммарный background gain.
- [x] **E05.3** Реализовать attack/restore envelopes, нормализацию/headroom,
  восстановление после окончания foreground и bounded resources.
- [x] **E05.4** Реализовать cancellation/disposal, safety/mute/hidden policy;
  ordinary переходы одного exercise не обрывают started speech.
- [x] **E05.5** Добавить local preview и overlap demo без paid запросов;
  согласовать rep beep fallback без двойного сигнала по умолчанию.
- [x] **E05.6** Добавить мини-кнопку AI в TopSystemBar перед MotorForceReadout,
  normal/compact, readiness, last actual source и local playback counters.
- [x] **E05.7** Проверить focus/portal/safety modal, STOP виден, узкие экраны,
  масштабирование; offline render 1/2/3 voices и базовое браузерное playback.
- [x] **E05.G** Приёмка: новая фраза приглушает старые только на actual start,
  count и comment не прерывают друг друга, mute/safety прекращают ordinary звук.

**Результат:** проверяемый локальный микшер и ранняя диагностика отсутствия звука.
Gate проверен на TEST buffers; реальные count/comment producers будут в E06/E07.
Legacy beep пока единственный автоматический сигнал; при E06 нужен rep-event
арбитраж с голосом. Физическое прослушивание не отмечено — остаётся E08/E12.

## 9. E06 — интерпретатор и локальные тренировочные события

**Цель:** счёт и сигналы привязаны к реальным событиям, не к навигации UI.

- [x] **E06.1** Реализовать coach phase machine с UI/hardware agreement,
  freshness/monotonic receive time и отдельными safety latches.
- [x] **E06.2** Реализовать подтверждённый count/start/resume/end, baseline на
  reconnect/new set; скачок 5→8 не создаёт пачку старых чисел.
- [x] **E06.3** Реализовать milestones/countdown только по однозначной цели;
  late «Последний» запрещён, без пригодного rep-start этот cue не создаётся.
- [x] **E06.4** Реализовать timed/bodyweight/stretch/group/isometric/fixed_hold
  eligibility, progress unit и временные отметки без счёта по чужому грифу.
- [x] **E06.5** Интегрировать stopped/persisted/rest/finalized события;
  различать полный/частичный/пропущенный результат и save delay/error.
- [x] **E06.6** Реализовать dedup/receipt aliases, не сбрасывать opportunities
  при revisit/timer edits; изменения count применяются только к новым событиям.
- [x] **E06.7** Прогнать pause/stale/failure/spotter/fault/pain/recovery matrix,
  mock/service guards и отсутствие motor commands от Coach.
- [x] **E06.G** Приёмка M2: целая replay-тренировка звучит локально корректно,
  не повторяет старые события и остаётся безопасной при потере сети.

**Статус: Готов, 07.10.2026.** [Реализация и проверки](13-live-ai-coach-e06-interpreter.md).
Replay принят на TEST buffers; русские клипы счёта появятся только после E08/E09,
поэтому веха M2 не отмечена (нужны pack и прослушивание).

## 10. E07 — режиссёр, память и автор текста

**Цель:** разнообразные уместные реплики с проверяемыми фактами, пока без обязательной сети голоса.

- [x] **E07.1** Реализовать registry всех T01–T66 и source prerequisites;
  unsupported данные означают skipped reason, не фиктивное наблюдение.
- [x] **E07.2** Реализовать profiles, cooldown groups, coalescing, content/acoustic
  budgets и slots по фактическому времени/прогрессу, не случайный монолог по таймеру.
- [x] **E07.3** Реализовать topics/openings/intents, attempted/started/completed
  memory, мотивы/callbacks и factMention guard.
- [x] **E07.4** Добавить версионированные P0–P5 prompts, ordinary/locked-fact schemas,
  fact templates, безопасное отделение notes от инструкций и prompt hashes.
- [x] **E07.5** Реализовать server fact builder/validators, history comparison policy
  и валидные tempo aggregates; несуществующие метрики исключить из речи.
- [x] **E07.6** Подключить Luna adapter с caps/usage/cancel, fake и opt-in paid mode;
  corpus ≥150 случаев, включая negative/injection/partial/unavailable history.
- [x] **E07.7** Провести малый разрешённый paid text pilot после E03–E04:
  8–12 случаев с выбранным cap, без голоса/движения; сохранить redacted результат.
- [x] **E07.G** Приёмка: schema/facts проверены, разнообразие оценено, критичных
  выдумок в контрольном наборе нет; rejection даёт local/silence, не endless retry.

**Платный gate:** ключ существует server-side, выбран test cap, actual usage записан.
Если доступа к модели нет — этап заблокирован по paid pilot, остальные offline проверки сохраняются.

**Статус: Готов, 08.10.2026.** [Реализация, pilot и проверки](13-live-ai-coach-e07-director-author.md).
Pilot 3 прогона × 12 случаев, $0.0063 всего; итоговый (`coach-prompts-0.4`, effort `low`): 10/10 speech, 0 выдумок, 1.6–3.3 с.

## 11. E08 — streaming voice и выбор моделей/голосов

**Цель:** измерить качество русского и выбрать экономичный voice path до массовой генерации пакетов.

- [x] **E08.1** Реализовать Realtime mini и streaming TTS adapters через один
  capability interface; проверить реальные model IDs/voices/pricing/account access.
- [x] **E08.2** Реализовать tagged PCM framing, codec/sample rate, jitter/ring buffer,
  underrun/gap handling, end/drain и ограниченные byte/duration/watchdogs.
- [x] **E08.3** Интегрировать network utterances в микшер: chunks не новый start,
  reservations не duck, late generationId отвергается, gaps не держат фон в тишине.
- [x] **E08.4** Реализовать transcript verification и явное различие streaming
  post-factum контроля от предварительной проверки; без ложной гарантии дословности.
- [x] **E08.5** Провести малый paid voice pilot 4–8 текстов с capped test job;
  измерить стадии latency, usage и match, без настоящей workout/hardware commands.
- [ ] **E08.6** После shortlist провести 30-текстовый русский A/B с двумя голосами
  и adapters; cold/warm conditions, числа, юмор, partial, overlap и длинное прослушивание.
- [ ] **E08.7** Пользователь прослушал примеры; записать выбранный text/voice path,
  male/female voice IDs, причины выбора, цену/latency и ограничения.
- [ ] **E08.G** Приёмка M3: выбранный голос естественен, числа понятны, actual costs
  измерены; factual speech направляется в подходящий verified path.

**Важно:** не строить окончательный pack выбранным наугад голосом до этой приёмки.

**Статус: Offline готов, pilot и выбор голоса заблокированы, 07.10.2026.** [Реализация и проверки](13-live-ai-coach-e08-voice.md).
E08.1 не отмечен: adapters реализованы, но model IDs/voices/pricing/access не проверены без ключа в vault.
E08.5–E08.7/E08.G не отмечены: нет ключа и подтверждённой цены, A/B и выбор голоса требуют прослушивания пользователем.

## 12. E09 — голосовые пакеты и подготовка по кнопке

**Цель:** частые фразы готовятся явно, работают быстро и не оплачиваются повторно без причины.

- [ ] **E09.1** Утвердить редакторский каталог required/optional clips и safety texts,
  mechanical eligibility; проверить совместимость audited старых записей.
- [x] **E09.2** Реализовать dry-run plan: coverage, fingerprints, sizes, missing/corrupt,
  отдельно generated/downloaded/decoded readiness и estimate/cap.
- [x] **E09.3** Реализовать «Подготовить частые фразы»: готовое только fetch/decode;
  missing generation — отдельный явный paid action с выбранными clip IDs.
- [x] **E09.4** Реализовать resumable capped generation job, idempotent submit,
  pause/cancel/progress/receipts; crash recovery не blindly оплачивает всё снова.
- [x] **E09.5** Реализовать atomic artifact/manifest publish, checksums, decoded duration,
  loudness verification, pinned packVersion и сохранение старого compatible pack.
- [x] **E09.6** Реализовать whitelist serving, encoded browser cache, decoded RAM LRU,
  quota/eviction, preload required clips, deletion и честный offline статус.
- [ ] **E09.7** Подготовить оба выбранных voice packs в пределах отдельных caps;
  проверить required clips decode и прослушать count/start/safety/overlap.
- [ ] **E09.G** Приёмка: repeated prepare готового pack не вызывает inference,
  partial не считается ready, voice switch не подменяет голос, quota не запускает paid regenerate.

**Платный gate:** pack cap отдельно от $2/workout; пользователь видит число новых клипов.

**Статус: Offline готов; каталог, генерация и прослушивание заблокированы, 07.10.2026.** [Реализация и проверки](13-live-ai-coach-e09-voice-packs.md).
E09.1 не отмечен: черновик каталога в коде, safety-тексты не утверждены (`approved: false`) — нужно прослушивание пользователем.
E09.7/E09.G не отмечены: нет ключа, проверенной цены и выбранных голосов (E08.1, E08.7); paid generation fail-closed.

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

E01 закрыт; ниже — зависимости следующих этапов, **не отметки их реализации**.

| ID | Что необходимо | Когда нужно | Состояние |
|---|---|---|---|
| D01 | Выбор reuse/new после проверки исходников | E01 | Закрыто: полностью новая реализация; пользователь исключил старые ветки |
| D02 | Operator auth и пригодное server secret storage | E03 | Реализованы и offline проверены; deployment setup оператором ещё не выполнен |
| D03 | Ввод ключа пользователем в безопасную форму | Paid E07–E09 | UI готов; сначала operator/vault provisioning, значение не хранить здесь |
| D04 | Доступ аккаунта к моделям/voices и актуальные цены | E08 | Не подтверждён реальным пилотом |
| D05 | Выбранные male/female voices и adapter | E08 | Выбираются по A/B |
| D06 | Caps текстового/voice/pack заданий | Перед каждым новым paid job | Выбираются явно, внутри job попытки разрешены |
| D07 | Типовая длительность/отдых и count default | E12, можно уточнить раньше | Пока proposals |
| D08 | Прослушивание и пользовательская приёмка | E08/E09/E12 | Не выполнены |
| D09 | Пригодные voice pack artifacts | E05/E09 | Нет на диске/в refs; E05 fixtures, E08 голоса, E09 capped prepare |
| D10 | Исходные frontend test/typecheck ошибки | Интеграция и E12 | [Baseline E01](13-live-ai-coach-e01-audit.md); общий build пока FAIL, не блокирует contracts/fakes E02 |

При фактической блокировке добавлять: stage/task, причина, дата, следующий шаг.
Не просить ключ в чате и не читать существующие секреты, чтобы «ускорить проектирование».

## 17. Журнал проверок и решений

| Дата | Этап/пункт | Выполнено | Доказательство / проверка | Следующий шаг |
|---|---|---|---|---|
| 07.10.2026 | E00 | Подготовлены документы v0.3 и этот трекер | Проектные документы существуют; не свидетельство работающего Coach | E01.1 |
| 07.10.2026 | E01.1–E01.6, E01.G | Проверены disk/Git, lifecycle, метрики, отсутствие packs; первоначальный selective reuse исключён последующим решением пользователя | [Отчёт](13-live-ai-coach-e01-audit.md): backend 30 PASS; frontend 76 PASS/1 FAIL; TS 23 baseline diagnostics; Vite/scoped Ruff PASS; 0 paid/physical calls | E02.1 |
| 07.10.2026 | E02.1–E02.6, E02.G | С нуля contracts/ports/fakes/replay, lifecycle capture/after-commit, safe runner, flags/API | [Отчёт E02](13-live-ai-coach-e02-contracts.md): backend 70 PASS; frontend 55 PASS; Ruff/Vite/editor/diff PASS; TS 23 baseline, 0 новых; 0 paid/physical calls | E03.1 |
| 07.10.2026 | E03.1–E03.7, E03.G; E04.1–E04.7, E04.G | Per-user CAS prefs/consent, transient UI/operator/vault, durable SQLite runs/reserves/usage/leases/jobs | [Отчёт E03–E04](13-live-ai-coach-e03-e04-control-plane.md): backend 108 PASS; frontend 120 PASS + common integration 1 PASS; Ruff/Vite PASS; TS 23 baseline; temporary migration roundtrip PASS; 0 paid/physical calls, user DB/setup не изменены | E05.1 |
| 07.10.2026 | E05.1–E05.7, E05.G | Shared context, latest-start mixer, guarded TEST preview, AI mini-debug, защищённые STOP/моторы | [Отчёт E05](13-live-ai-coach-e05-local-audio.md): frontend 226 PASS; Chromium 64 PASS; native offline render 1/2/3; backend 108 PASS; Ruff/Vite PASS; TS 23 baseline, 0 новых; 0 paid/hardware calls | E06.1 |
| 07.10.2026 | E06.1–E06.7, E06.G | Чистый интерпретатор, live cue runtime, beep-арбитраж, mini-debug E06 | [Отчёт E06](13-live-ai-coach-e06-interpreter.md): frontend 270 PASS (новые 44), whole-workout replay 8/8 actual starts на TEST buffers; static no-motor PASS; TS 23 baseline, 0 новых; 0 paid/hardware calls | E07.1 |
| 07.10.2026 | E07.1–E07.6 | Registry T01–T66, режиссёр/coalescer, память, P0–P5 prompts, facts/validators, Luna adapter + TextAuthor; paid dispatch fail-closed | [Отчёт E07](13-live-ai-coach-e07-director-author.md): backend safe runner 333 PASS (новые 225, corpus ≥150); Ruff PASS; 0 paid/hardware calls. E07.7/E07.G заблокированы: нет ключа в vault/подтверждённой цены, pilot требует пользователя | E08.1 |
| 07.10.2026 | E08.2–E08.4 | Capability interface, TTS/Realtime adapters (fail-closed), tagged PCM frames, streaming mixer, transcript verification | [Отчёт E08](13-live-ai-coach-e08-voice.md): backend safe runner 352 PASS (E08 19); frontend 283 PASS; TS 23 baseline; Ruff PASS; 0 paid/hardware calls. E08.1 проверка, E08.5–E08.G заблокированы | E09.1 |
| 07.10.2026 | E09.2–E09.6 | Каталог-черновик, dry-run plan, resumable pack job, verified WAV/atomic manifests, whitelist serving, browser pack client + UI | [Отчёт E09](13-live-ai-coach-e09-voice-packs.md): backend safe runner 364 PASS (E09 12); frontend 296 PASS; TS 23 baseline; Ruff/Vite PASS; ESLint не установлен; 0 paid/hardware calls. E09.1, E09.7/E09.G заблокированы | E10 после разблокировки E07–E09 |

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