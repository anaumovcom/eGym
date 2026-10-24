# AI-тренер — решения, принятые самостоятельно (E07–E12, U00–U10)

Создан: 08.10.2026. Основание: поручение пользователя «по непонятным вопросам прими решения
самостоятельно и зафиксируй их в файле». Каждое решение обратимо; при несогласии меняем
здесь, затем код/спецификацию и трекер [13-live-ai-coach-implementation.md](13-live-ai-coach-implementation.md).

Не принимались самостоятельно (остаются за пользователем): оценка утомляемости (E12.5), принятие релиза (E12.8).
Принято пользователем 08.10.2026: прослушивание голоса и пакета ash включая safety-клипы
(«всё хорошо»), голос «побрутальнее, поувереннее», платные флаги включены по умолчанию.

## Live-приоритет и paid-проверка — 17.10.2026

Актуальное дополнение: [реальный live-отчёт](13-live-ai-coach-live-tuning-2026-10-17.md).
Пользователь явно разрешил **до $10** для live-отладки; это не принятие candidate на слух.
U07.5 выполнен, U07.6/U07.7 pending; старые упоминания «cap pending» ниже исторические.

| ID | Решение | Основание / ограничение |
|---|---|---|
| D-LIVE.1 | Общая campaign sandbox DB, production ledger, отдельные per-run caps; общая liability $0.203885, включая timeout reserve $0.002268. | Пользовательский $2/workout неизменен; никаких paid вне ledger/скрытой генерации пакетов. |
| D-LIVE.2 | Только T21 ledger key различает code-selected topic hash; разные slots работают, event ID не обходит dedup. | Реальный второй повод ранее отвергался duplicate_attempt; cooldown/density/replay остаются. |
| D-LIVE.3 | Нет нового reviewed tip → короткая общая live-поддержка без technique claims и tip metadata. | Соответствует U04 unknown → support или silence, не вечное молчание всех упражнений вне пилота. |
| D-LIVE.4 | Handshake после admission параллельно text author, ни одной speculative paid реплики. | Узкая безопасная transport-подготовка; U08 prepared generation не реализован и не принят. |
| D-LIVE.5 | Luna low остаётся default. Prompt 0.12 ограничивает факты до author, убирает дословные шутки-примеры; фактические guards сохраняются. | none в малом эксперименте дал unreviewed_tip, итоговый low continuity 9/9; это не закрывает весь U09. |
| D-LIVE.6 | Candidate только в sandbox, A/B 14/14 transcript match; рабочие voice 0.5 и pack style 0.3 сохранены. | Нужен пользовательский выбор на локальной странице; accepted=False, production flag default false. |

## Голос и озвучка

| ID | Решение | Причина |
|---|---|---|
| D-E08.7 | Голос выбирается в настройках из 10 голосов Realtime (`ash, alloy, ballad, cedar, coral, echo, marin, sage, shimmer, verse`); по умолчанию **ash**. Старые `female`/`male` мигрируют в `ash`. | Прямое указание пользователя (Ash по умолчанию); отдельные male/female слоты больше не нужны. |
| D-E08.7a | Живая речь и пакеты используют один adapter — Realtime (`gpt-realtime-2.1-mini`), один тембр. TTS остаётся только как pilot-сравнение. | TTS закрывается 06.01.2027; warm Realtime дал 0,5–0,7 s first audio и 79/79 дословно (E08.6). |
| D-E09.slot | Один пакет на голос: slot = voice ID. Смена голоса не подменяет пакет другим тембром. | Сохраняет «один напарник» и исключает смешение голосов. |
| D-E09.1 | Редакторский каталог `coach-pack-catalog-0.1` (count 1–30 обязательны, 31–100 optional, countdown, 21 lifecycle/outcome/rest фраза, 2 safety) принят как v1. Safety-клипы выпущены: `APPROVED_SAFETY_CATALOG = CATALOG_VERSION` после прослушивания пользователем (08.10.2026). Новая версия каталога снова требует прослушивания. | Тексты нейтральны и проверены transcript verification; safety-аудио — решение человека, не агента. |
| D-E09.7 | Сгенерирован обязательный пакет `ash` (56 клипов, $0.065, manifest `3e373f457fc4a07a`), прослушан и принят. После смены стиля (D-E08.8) перегенерирован (см. трекер §17). Optional 31–100 не генерировались. | Для E10 fast path достаточно required; optional — отдельный явный prepare. |
| D-E08.8 | Характер голоса `coach-voice-0.4`: низкий, плотный, уверенный, твёрдая атака, понижение интонации в конце фразы, без «улыбки» и крика; запрет мета-вступлений («Сейчас озвучу…» появилось в 1 из 18 A/B-фраз). Меняется только подача; текстовый характер P1 («тёплый, энергичный») не тронут. `STYLE_VERSION` → `coach-pack-style-0.2` (пакеты перегенерируются). | Запрос пользователя «побрутальнее, по увереннее»; тексты уже приняты. |
| D-E08.9 | Высокое начало фразы. Измерено (F0 первых слогов / медиана F0 клипа, порог 1,15): live/A-B ash — 30–50 % фраз стартуют на 170–235 Hz при теле 110–140 Hz; пакет `0826034bbeeb36ae` — 10/56. Промпт `coach-voice-0.5` (низкое ровное начало, энергия атакой, а не высотой) **статистически не помог** (контроль 4–6/12 до и после; calm/plain-input/reasoning low/другие формулировки — то же). Поэтому: (1) пакеты — `coach-pack-style-0.3` с отбором дублей: клип с onset > 1,15 перегенерируется, до 3 дублей, сохраняется самый низкий (`packs.onset_ratio`); новый пакет `cbf9c5512caed39c` — 1/56 (`count-21`, лучший из 3); (2) live-поток не переозвучить без задержки — оставлен промпт 0.5; голоса с меньшим эффектом: marin 2/12, cedar 3/12, TTS 3/12. | Замечание пользователя «начало фраз иногда со слишком высокой интонацией»; эффект — свойство генеративной модели, не текста промпта. |

## Сценарии и триггеры (E10)

| ID | Решение | Причина |
|---|---|---|
| D-E10.1 | Открытие: T01 на `workout_started`, T04 на `exercise_ready` (контекст `exerciseName`), P2-задача `setup/opening` (prompts 0.5). | Минимальный набор, который даёт «напарника» с первых секунд. |
| D-E10.2 | T21 (поддержка в подходе) только на тренажёре с точной целью ≥ 8 повторений, в окне `ceil(target/2)…target−2`, при `duringSets`. | Короче 8 — речь мешает счёту; ближе к концу перекрывает «ещё три»/финиш. |
| D-E10.3 | T36/T37/T39/T40 — только из сохранённых в БД подходов (`refs.backendSetId`); T38 (skipped) — локальный клип; T41 (анализ техники) не предлагается. | Браузер не источник фактов; анализ требует отдельного opt-in. |
| D-E10.4 | Сравнения с прошлым (T39/T40) только при `historyConsent`; иначе T36/T37 без истории. | Приватность истории. |
| D-E10.5 | T46 (длинный отдых): сервер требует ≥35 s до конца отдыха; клиент отправляет при прошедших ≥15 s и оставшихся ≥40 s, только `duringRest` и не на паузе. T47 пропущен. | Запас на генерацию (3,5–7 s в pilot) и речь до `rest-ten`. |
| D-E10.6 | Историческое queue/owner решение заменено D-U03.1: итоги T55–T59 по-прежнему только из БД (`backendExerciseId`/`backendWorkoutId`), но подтверждение local-first, live — fact supplement, очередь bounded priority вместо одного перезаписываемого слота. | Сохраняем источник фактов, устраняем потерю и дублирование итогов. |
| D-E10.7 | Single-flight: один paid pipeline на run; новое событие при занятом pipeline → `silence: pipeline_busy` (кроме итогов). | Бюджет и отсутствие наложений. |
| D-E10.8 | `during_sets`/`during_rest`/`humor` отображаются на допуск триггеров и intents на сервере; `humor: off` убирает humor-intent. | Настройки действуют независимо от клиента. |
| D-E10.9 | Режим `text-only` возвращает текст в `decision` без голоса; клиент показывает его в диагностике. Событие в text-only не глушится gate `mute`. | Text-only всегда содержит gate `mute`, иначе режим был бы бесполезен. |

## Протокол и надёжность (E10–E11)

| ID | Решение | Причина |
|---|---|---|
| D-E10.P1 | WebSocket `/api/coach/runs/{id}/live`; первое сообщение `configure {runToken, ownerId}`; токен никогда не в URL. | URL попадает в логи/историю. |
| D-E10.P2 | Generation читается на сервере; lease обновляется каждые 5 s; изменение настроек → `stale_run` → клиент переподключается и получает новые настройки. | Один источник правды, нет устаревших реплик. |
| D-E10.P3 | Сокет принимает ledger `workout` и `test`; `pack` — нет. | Pack-задания идут отдельным REST-путём с собственным cap. |
| D-E10.P4 | Ограничения: 40 сообщений/с, сообщение ≤ 32 KB, ≤ 1024 запомненных event id, ≤ 32 ожидающих ack. | Защита от флуда и роста памяти. |
| D-E10.P5 | Run и токен хранятся в `sessionStorage` (`coach-run:<user>:<workout>`); перезагрузка вкладки продолжает тот же run, cap не обнуляется. | Нельзя обойти $2/workout перезагрузкой; другая вкладка — другой owner. |
| D-E10.P6 | `workout_started` не отправляется повторно после reconnect, если прогресс уже есть; lifecycle-события до `ready` помечаются отправленными и не воспроизводятся задним числом. | Нет устаревших реплик после recovery. |
| D-E10.P7 | Пока есть gate (кроме `mute` в text-only) или safety latch — события не отправляются; latch передаётся серверу сообщением `safety`. | Safety выше речи. |
| D-E10.P8 | Reconnect backoff 1/2/4/8/16/30 s; `owner_mismatch` (вторая вкладка) — повтор через 16 s; `run_not_found/run_not_live/run_closed` — новый run; `local_mode` — отказ до изменения настроек. | Без шторма переподключений и без захвата чужого lease. |
| D-E10.P9 | **Историческое; заменено D-U01.1–D-U01.3 от 17.10.2026.** Ранее клиент при `speech_start` переписывал scope потока на текущий scope интерпретатора; `revalidate` проверял тот же `scopeEpoch` и отсутствие gate. Теперь source scope/identity неизменны. | Rebinding скрывал происхождение позднего ответа; актуальность проверяется отдельным cursor, не подменой источника. |
| D-E10.P10 | `ownerId` из `crypto.getRandomValues` (не `randomUUID`). | Киоск открывается по LAN HTTP, где `randomUUID` недоступен. |
| D-E11.M | Исторические session-only границы расширены D-U05.1: delete очищает live/cached/cross память пользователя, pacing и safety сохраняются. Кнопка «Забыть разговор» остаётся. | Process-local reconnect/opt-in enum caches не являются долговечной памятью. |
| D-E11.R | «Скопировать отчёт» в диагностике содержит только состояние, счётчики, причины, usage и latency — без текстов реплик, токенов и id пользователя. | Отчёт можно пересылать. |

## Платные флаги и выпуск (E12)

| ID | Решение | Причина |
|---|---|---|
| D-E12.1 | Платные флаги **включены по умолчанию** (решение пользователя 08.10.2026): `COACH_PAID_TEXT_ENABLED`, `COACH_TEXT_PRICING_VERIFIED`, `COACH_PAID_VOICE_ENABLED`, `COACH_VOICE_PRICING_VERIFIED` = `true`. Платный запрос всё равно требует `COACH_ENABLED`/`VITE_COACH_ENABLED`, ключ в vault, согласие + network consent и cap $2/workout. В тестах флаги закреплены `false` (conftest), тесты включают их явно. | Остальные гейты сохраняют fail-closed; отключение — env `=false`. |
| D-E12.2 | Rollback: выключить `VITE_COACH_ENABLED` (фронт) или `COACH_ENABLED`/paid-флаги (сервер); пользователь — режим «локальный». Ledger не удаляется. | Мгновенное безопасное выключение без потери учёта. |
| D-E12.3 | Шапка с отдельным счётчиком стоимости не добавлялась: расход виден в mini-debug, раздел «Сеть». | Минимальный UI до пользовательской оценки (E12.5). |
| D-E12.4 | Контрольный paid end-to-end прогон — `coach_pilot.py live` в sandbox-БД, ledger `test`, без оборудования. | E12.6 без моторных экспериментов. |

## Цикл улучшений U00–U07 — 17.10.2026

Основание: [последовательный план](13-live-ai-coach-improvement-plan.md),
[итоговые исходники/тесты, версии и проверки](13-live-ai-coach-u00-u07-progress.md).
[Ранний U00–U02 отчёт](13-live-ai-coach-u00-u02-report.md) сохраняет historical evidence.
U00–U06 реализованы offline; это не приёмка нового звучания. U07 заблокирован,
U08–U10 не начаты; прежние E-чекбоксы сохраняются.

| ID | Решение | Причина / граница |
|---|---|---|
| D-U00.1 | Baseline — synthetic корпус 70 сценариев / 12 групп, повторяемый дважды; пять отсутствующих browser/delete workflows явно skipped, не passed. Safe runner изолирует DB/media/packs, запрещает paid/network/serial/Modbus до collection. | Baseline limitations не должны превращаться в ложную готовность функций. Source defaults не выдаются за effective user preferences. |
| D-U01.1 | Вместо D-E10.P9 сохраняем immutable event identity, исходный scope и зависимости до text/`speech_start`/PCM/ACK; capture time/phase/plan/context versions фиксируются до async save. Без live provenance событие local-only; нет присвоения publication versions или zero-version fallback при backend context. | Validation cursor может двигаться, source identity — нет. Существующий wire schemaVersion 1 расширен связанной identity; original PCM scope не переименовывается. |
| D-U01.2 | Pending exact-context, кроме подтверждённых result refs: set `active-set → finalizing-set → rest`, exercise `active-set → finalizing-set → exercise-summary`, workout только `workout-summary`; монотонный epoch, один same-summary remap. Нет setup/waiting-start исключения, origin phase rewrite или resurrection. | Результат сначала подтверждается сохранённой строкой/владельцем. Ordinary support не получает result-права. Started речь переживает обычные переходы, но не plan/owner/run/gate/safety invalidation. |
| D-U01.3 | ACK и terminal receipts идемпотентны; natural completion отличается от interrupted после start. Исчезновение из mixer не означает completion. | Это foundation U01, не готовый fallback/очередь/полная opportunity machine U03. Требование latest-start foreground и одновременного микширования сохраняется. |
| D-U01.4 | Original browser TTL не продлевается. Server receipt TTL использует исходный interval минус elapsed-at-send, но не знает transit. Browser/server monotonic durations и bounded p50/p95 раздельны; voice-first-PCM не event-to-start. Cold/warm — результат actual voice send, иначе unknown/fake. | Не вычитать несогласованные абсолютные часы и не заявлять акустическую latency по mixer ACK. Новые paid/acoustic прогоны для этих offline gates не нужны. |
| D-U02.1 | `metric-policy-0.2`: только достаточные известные условия kind/mode/working-warmup/ordinal/count/range/calibration/declared load; dynamic machine требует идентичного load profile. Неизвестное → limited/unavailable без delta; N/A только по явной kind/mode политике. | Заменяет прежнее фактическое допущение сравнимости при совпадении неизвестных полей. Readiness calibration не identity; `None == None` не доказательство. |
| D-U02.2 | Provenance/unit/quantity kind/timestamp/sufficiency передаются в allowed facts; сохранённый analytics weight объявляется плановым, не applied/measured. `target_met` проверяет цель, диапазон или explicit open target, не один completion label. | Не повышать достоверность старых или неполных данных; unknown сохраняется. Partial movement — только факт незачёта без вывода причины/ошибки тела. |
| D-U02.3 | Exercise full требует persisted plan count, unique contiguous ordinals, completed exercise и target-proven rows. Ранний always-limited workout gate дополнен U02.4: optional 0012, immutable declared-client baseline до результатов, полная сверка saved rows/targets/settings и fail-closed revalidation. | U02 реализован offline. Таблица отдельной metadata исключена из startup create_all; рабочая миграция не запускалась. Positive full-plan только после явной миграции для новых workouts с declared snapshot; existing/absent-table остаются limited, нет backfill или re-blessing после edit/undo. Декларация не physical telemetry. |
| D-U02.4 | Persisted source signature и semantic package перечитываются свежими sessions после author до text/`speech_start`, затем перед первым непустым PCM; изменение → `facts_changed`. | Защита async handoff, включая редактирование/удаление результатов, плана, истории и условий. Не DB query на каждом chunk и не гарантия атомарности вплоть до динамика. |

| ID | Решение | Причина / граница |
|---|---|---|
| D-U03.1 | Вместо прежнего live-owner/одного слота: local-first подтверждение завершения, live только с новой фактической добавкой; bounded priority queue/FSM, natural completion отдельно от interruption, duration/attempt budgets. | Нет live-first wait window; failed/silent/busy не отнимают local cue. Нужны актуальность, доступные local pack/audio; latest-start foreground и одновременный микшер неизменны. |
| D-U04.1 | Только ограниченный engineering-reviewed machine tips pilot: один применимый versioned tip до LLM; неизвестное → support/silence. Effort/discomfort только реально введённые в optional rest UI, без default, с ownership/TTL. | Не human/medical certification и не аудит всего каталога. Нет микрофона, body vision или автоматического сброса safety latch. |
| D-U05.1 | Memory default true независимо от historyConsent; cross-workout default false, отдельный consent opt-in. Current-run max32 user/run entries/process, hard24h; cross max128 users, 7 дней, только style/humor/verbosity/praise enum. | Сужает исходный U05 scope: достижения не храним. Cache process-local/restart-lost, не durable DB memory; reconnect не продлевает run TTL, неизменные enum не продлевают cross TTL, expiry lazy. Delete/disable чистят live/cached/cross и pending context, не analytics/settings/billing/safety/pacing; forget при enabled допускает новые записи. |
| D-U06.1 | Speech actions/необязательный bounded humor, density по observed playback, corpus-tested quantity/provenance/negation/partial validator, fallback/silence без recursive funny retry. | Прохождение positive/negative корпуса — engineering evidence, не идеальная гарантия для любого текста. Source author prompt теперь coach-prompts-0.11; старые версии остаются historical. |
| D-U07.1 | U07.1–.4 только offline candidate coach-situational-candidate-0.1. Source flag false И SITUATIONAL_DELIVERY_ACCEPTED=False; default legacy. Accepted voice0.5/packstyle0.3/count/safety не заменены. | U07.5–.7 blocked: отдельный paid cap и human listening; $0.10 — лишь не одобренное предложение, paid $0. Нет promotion или запуска U08–U10 до предыдущих gates; $2/workout не повышается. |
| D-V01.1 | Голос и характер (решение пользователя 24.10.2026). Голосовые модели переключаются в настройках: OpenAI Realtime / OpenAI TTS / Fish Audio drama-3 (по умолчанию). Fish — свой ключ в vault (`?provider=fish`), цена $50/1M UTF-8 байт входа (промо $10 до 12.11.2026 не закладывается); без ключа — фолбэк на OpenAI Realtime с причиной `voice_fallback`. Характеры — реестр `services/coach/personas.py` (персонаж = модуль характера + голос Fish); по умолчанию «Дерзкий стример» с голосом fish.audio `0a690dbeb3984a9f88cd39353880775f`, «Классический» сохраняет P0/P1 дословно. По умолчанию: мат без цензуры, подколы (`roast`), humor often, чёрный юмор; старые настройки без `persona` один раз получают этот набор (явное «без шуток» сохраняется). Автор возвращает блок `voice` (ремарка/звук/подача) только для drama-3; текст остаётся чистым и проходит прежние проверки фактов. | Неизменно: факты/числа/план, запрет «через боль»/сверх плана, оскорбления внешности/тела/здоровья/защищённых групп, при риске/боли мат и юмор выключены, safety/count/partial — фиксированный тон. Реальная проверка Fish 24.10.2026: мат произносится без цензуры, ремарки не озвучиваются, первый звук 0.3–0.7 с. Текстовую модель проверяет `coach_text_pilot.py --persona streamer [--speak]` на устройстве с vault. |
