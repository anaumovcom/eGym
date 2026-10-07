# AI-тренер: настройки, диагностика, частые фразы и микшер

Версия 0.3, 07.10.2026. Проект, не реализованный UI/API.
Связи: [обзор](13-live-ai-coach.md), [техническая спецификация](13-live-ai-coach-spec.md),
[триггеры и промпты](13-live-ai-coach-behavior-prompts.md).
Платные тесты разрешены пользователем; API key будет указан в настройках.
Реальных запросов в рамках подготовки этого документа нет.

## 1. Структура настроек

Раздел «AI-тренер» в Общих настройках, не спрятанный в механике.
Шесть карточек: Включение / Голос и характер / Общение / Частые фразы /
Модели и расходы / Диагностика. Advanced controls раскрываются отдельно.
Provider secret — отдельная операторская карточка, не обычный per-user JSON.

### 1.1. Области хранения

| Scope | Что хранится | Поведение |
|---|---|---|
| System/operator | API secret reference, provider policy, hard caps, packs | Не экспортируется в пользовательский профиль |
| Per-user | Enabled/consent, style/voice, частота, счёт, история, звук | Не наследовать между пользователями |
| Workout override | Меньше/больше говорить, count toggle, временный mute | Явно «только на эту тренировку» |
| Ephemeral | AudioContext, текущие голоса, UI diagnostics | Не восстанавливать как будто речь ещё звучит |
| Persisted run ledger | Attempts/usage/reservations/dedup | Не сбрасывается при reconnect |

Персональные настройки можно хранить в существующем
[AppSetting](../backend/app/models/settings.py) с user_id и schemaVersion,
но secret туда не кладётся в plaintext. Workout override не изменяет профиль
молча; кнопка «Сохранить как мои настройки» отдельно.

### 1.2. Основные настройки

| Настройка | Варианты / default proposal | Когда применяется |
|---|---|---|
| Тренер | Off до consent | Off немедленно отменяет ordinary audio/tasks |
| Режим | Гибрид / только локально / текст без звука | Новый источник требует актуального согласия |
| Голос | Выбранные русские male/female; конкретный provider voice после A/B | Смена после save, отменяет старый voice pipeline |
| Характер | Весёлый энергичный напарник / спокойнее | Будущие тексты; уже звучащее не переписываем |
| Разговорчивость | Тише / Напарник / Очень разговорчивый | Следующие opportunities, без replay |
| Юмор | Нет / лёгкий / часто | Частота joke intents, не больше requests вне density |
| Резкость | Обычный / дерзкий opt-in | Policy limits неизменны |
| Обращение по имени | Off / редко | Только подтверждённое имя/предпочтительное обращение |
| Комментарии в подходе | On proposal | Off не выключает count и обязательные local cues |
| Отдых | On | Настраиваем отдельно от in-set speech |
| Итог подхода | Короткий / с разбором | Локальный факт + один main feedback |
| Итог упражнения/тренировки | On независимо от in-set frequency | Сохраняет partial/aborted semantics |
| Общие подсказки каталога | Off до выбора | Не медицинская оценка и не наблюдение за телом |
| Анализ измеренного темпа | On при валидной metric policy | Поддержка без diagnosis |
| Сравнение с историей | On после отдельного согласия | Сопоставимость проверяет backend |
| Сюжетные callbacks | On | Только completed мотив, всё понятно само по себе |
| Язык | Русский в первом релизе | Без обещаний неготовых локализаций |

Текстовый режим не требует AudioContext, но это **явный отдельный режим**,
а не способ продолжать платные voice requests при autoplay block.
Его text-only calls учитываются в том же ledger; обычный mute не включает его автоматически.
Если нет consent на сетевую обработку, только локальный текст/звук.

### 1.3. Счёт и таймер

| Настройка | Варианты |
|---|---|
| Счёт repetitions | Каждый / последние 3 / ключевые отметки / off |
| Формат | Выполненные reps / оставшиеся до точной цели |
| Интонация | Нейтральная / энергичная при готовом pack |
| Последний rep cue | On только с надёжным rep-start |
| Временные отметки | Половина / последние 10 / последние 3 / off |
| Подготовка в конце rest | 10 с / 5 с / только 0 / off |
| Rep beep | Авто fallback / отдельно on / off |

Профиль формата счёта применяется только к новым events. Нельзя озвучить накопленные
reps при включении count. Countdown выключается для неоднозначной min/max цели.
При paused timer нет временного счёта. Отдельное countVolume по умолчанию равно voiceVolume;
не хранить бессмысленный «энергичный голос», если соответствующих файлов нет.

### 1.4. Звук и микшер

| Настройка | Default proposal / диапазон |
|---|---|
| Общая громкость тренера | Наследует signalVolume до ручного override |
| Наложение реплик | On, ключевое требование пользователя |
| Совокупный фон | 65% gain; advanced 35–75% |
| Duck attack | 50 мс; advanced 20–120 мс |
| Restore | 150 мс; advanced 80–300 мс |
| Темп речи | Normal / немного быстрее в доступных controls adapter |
| Субтитры | On/off, отдельно count и comment |
| Скрытая вкладка | Stop ordinary по умолчанию; background режим не MVP |

65% gain не означает «на 35% менее громко по восприятию». Дать кнопку
«Послушать наложение» с одинаково нормализованными local clips.
Не предлагать ручной compressor threshold обычному пользователю.
Резкость и громкость независимы: более дерзкий тренер не автоматически громче.

### 1.5. Расширенная частота без поломки presets

Advanced: live slots/set, content gap, rest extra slots, maxWords по фазам,
name cooldown, локальная micro-support frequency. Ограниченные диапазоны сервера.
Изменение переводит preset в «Пользовательский»; «Вернуть preset» восстанавливает
его значения и показывает diff. Safety, source freshness, ownership, budget и
anti-replay не выключаются advanced-переключателем.

### 1.6. Модели и расходы

Text model — Luna candidate; voice — Realtime mini или TTS после A/B.
Operator whitelist поддерживаемых IDs/voices, без произвольного URL от пользователя.
На UI доступны budget/workout $2 default, local mode, daily/monthly cap optional,
retry максимум один, paid fallback off, лимит подготовки pack отдельно.
Модель не переключается автоматически при ошибке доступа.

Смена text/style — только будущие запросы. Смена provider/voice делает pending
speech generation устаревшей, отменяет воспроизведение старого голоса и загружает
новый готовый pack; отсутствующий pack не подменяется прежним.
Лимит можно уменьшить ниже spent: новые paid requests блокируются, refund не обещается.
Increase cap во время run требует явного подтверждения и operator policy.

### 1.7. Save, миграция, конфликт вкладок

[Settings screen](../frontend/src/screens/settings/system-settings-screen.tsx)
сейчас использует draft/saved и hydration. Coach требует своих typed schema,
revision/ETag и per-user hydration, чтобы поздний ответ пользователя A не заменил B.
Save атомарный; server validation сообщает поля, значения не «исправляются» молча.
Фоновая hydration не затирает несохранённый dirty draft.
Schema migration: unknown legacy consent/model не активирует платные requests.
Reset user prefs не удаляет общий ключ, packs и оплаченный ledger.

## 2. API key через настройки

### 2.1. Пользовательский сценарий

Оператор открывает «Provider», вводит API key в password input и нажимает
«Сохранить на сервере». При вставке не писать key в Zustand persist,
localStorage, URL, analytics, diagnostics или общий settings JSON.
В browser key существует только в transient input до отправки; очистить после
успешного save/закрытия, DOM не должен содержать возвращённый сохранённый ключ.

Backend отвечает только `configured`, `credentialVersion`, source=server-vault|env
и `lastCheckStatus`. Не возвращать полный key или его префикс.
Кнопки: заменить, удалить сохранённый key, проверить доступ.
Удаление не обещает удалить оплаченный usage; env fallback не используется
молча после явного disable credential — UI показывает источник и состояние.

### 2.2. Secure storage

- Предпочтительно OS secret service/credential store либо encrypted vault.
- Encryption master key вне DB, вне Git и вне browser; привилегии только backend process.
- Для unattended Linux отдельно проверить доступ к keyring без desktop session.
- Нет безопасного хранилища → env-only mode или ошибка setup, не plaintext fallback в AppSetting.
- Vault backup, key rotation и restore документированы; ciphertext без master не восстанавливается.
- Отправка remote key только по HTTPS; localhost исключение допустимо на одном устройстве,
  LAN HTTP не считается безопасным, особенно с общим киоском.
- Auth operator endpoint + CSRF/origin validation; выбранный user/PIN UI сам по себе не auth.
- До operator auth нельзя публично включить secret-edit API.
- Request bodies этого endpoint редактируются/исключаются в ASGI, reverse proxy и error logs.
- Не отражать provider response/error, содержащий секрет, в UI; normalized error code.
- Ключ в чужом браузере/модели/субагенте не передаётся для проверки.

### 2.3. Проверка доступа отдельно от платного голоса

«Проверить подключение» — metadata/auth запрос, если endpoint доступен;
metadata не доказывает paid inference доступ к каждой модели.
«Проверить текст» и «Проверить живой голос» — явно платные кнопки с cap и attempt ledger.
Сохранение ключа само по себе не генерирует пакеты и не произносит demo.
Key rotation отменяет новые dispatch со старой credentialVersion;
уже sent attempts учитываются и reconciliation не теряется.

## 3. Мини-кнопка диагностики в хедере

### 3.1. Место и вид

Встроить единую Coach-группу в `TopSystemBar` перед `MotorForceReadout`
в [Forma shell](../frontend/src/shared/ui/layout/forma-shell.tsx).
Так она видна в normal и compact header, включая exercise-session.
Не дублировать отдельную панель на каждом экране и не переносить в profile menu.

Пример компактной строки: **AI ● · 24 req · 18.4k tok · ~$0.38**.
Одно нажатие на мини-кнопку раскрывает diagnostics popover, не меняет тренера
и не отправляет API request. На узком экране label сокращается до **AI ●**;
счётчики в popover. Red/amber/green — состояние, текст/иконка дополняют цвет.
Локальный режим: **AI local**, confirmed отсутствие paid usage — 0,
неизвестные tokens — «—», неизвестная стоимость — «~ / данные ожидаются».

Миниатюрный текст 11–12 px, но hit target ≥32 px desktop, ≥44 px touch/TV.
aria-label содержит назначение; live announcements не читают каждое обновление токенов.
Keyboard Enter/Space, Escape закрывает, focus возвращается на trigger.
В popover ширина min(90vw, 30rem), max-height, scroll и portal, чтобы не обрезало header.

Стоп, статусы приводов и MotorForceReadout не вытесняются debug строкой.
Проверить 360/722/1024/1920/3840 px и scale 100/125/150%; coach text сворачивается первым.
Существующий safety dock может быть portal внутри safety dialog:
нельзя поднять Coach popover поверх аварийной формы с permissive focus trap.
При active safety modal закрывать Coach popover; STOP и hardware controls независимы.

Во время modal trigger Coach недоступен для открытия, аварийный focus scope не
обходится portal-ом. Если latch активен, но modal закрыт существующим штатным UI,
read-only diagnostics можно открыть: причина блокировки должна быть доступна,
не только «молчит». Кнопки playback/paid test/pack generation disabled при активной
safety-блокировке; просмотр не снимает её и не подменяет hardware fault journal.

### 3.2. Уровень 1: ответ «почему молчит?»

Вверху три строки:

1. Статус: готов / локально / ожидает звук / нет ключа / safety / network / budget.
2. Последний фактический звук: LOCAL / CACHE / REALTIME / TTS, когда started.
3. Последний повод: trigger ID + decision/skip reason, коротко по-русски.

Readiness: выбранный user/run, consent, voice/model, готовность required pack,
AudioContext state, actual volume, вкладка, speaking owner, freshness/safety.
Это диагностика тренера, не дубликат полного журнала аппаратуры.

### 3.3. Уровень 2: запросы и tokens

| Метрика | Точное определение |
|---|---|
| Triggers observed | События интерпретатора, включая подавленные |
| Opportunities admitted | Допущенные кандидаты до paid dispatch |
| Text requests | Реально отправленные попытки генерации текста |
| Voice requests | Реально отправленные попытки озвучки |
| Total generation requests | Text + voice attempts, retry тоже считается |
| Metadata/network requests | Отдельно auth/models/handshake, не смешивать с inference |
| Local/cache playback | Число actual starts, не paid requests |
| Generated / started / completed | Разные speech lifecycle counters |
| Cancelled / expired / rejected / failed | Раздельные причины, не один «ошибка» |
| Text tokens | Input/output/cached и provider-reported reasoning subset |
| Audio tokens | Input/output/cached отдельно, только reported |
| Provider total tokens | Reported total и полнота данных, без двойного суммирования |
| PCM seconds/bytes | Получено/проиграно отдельно; не API tokens и не цена |
| Cost | Оценка по usage и pricing snapshot, settled/pending/reserved отдельно |

В общей строке `req` = total generation requests, tooltip объясняет число.
Socket open не voice request; request с silence может быть text request без voice.
Local count не увеличивает `req`. Provider aggregate и response usage не складываются
вдвоём: reconciliation выбирает непересекающуюся авторитетную основу.
Text + audio reported total не суммировать поверх provider total.
Reasoning обычно subset output, cached subset input; адаптер документирует семантику.

Полнота: complete / partial / unavailable. Если известны только некоторые токены,
header показывает например **≥18.4k tok** с пояснением, не псевдоточный общий total.
Никакого перевода audio seconds в tokens. Фактически API-reported ноль — 0.
Счётчики по моделям и stages доступны таблицей; смена модели не сбрасывает run usage.
Сокет умер после sent attempt — ledger хранит pending, отчёт догружается REST.

### 3.4. Уровень 3: timeline и latency

Ring buffer 200 записей, последние 30 в UI, max record payload bounded.
Запись: monotonic time + wall display, run/event/utterance сокращённые IDs,
trigger/intent/topic, стадия, source, reason, scopeEpoch/promptVersion/packVersion.
Латентности: event→admission→text ready→voice first byte→actual start→completed.
Показать text wait, voice wait, jitter buffering и phase-window wait раздельно.
Для каждой фразы: deadline, playbackStart, scope validity и фактически used fact IDs.

Skip reason enum: disabled, no_consent, mute, audio_locked, hidden, safety,
stale_source, mock_source, owner_mismatch, scope_changed, no_window,
cooldown, density_cap, topic_repeat, pipeline_busy, budget, provider_circuit,
validation_failed, missing_clip, decode_failed, expired.
Один primary reason + secondary flags, без бесконечных одинаковых сообщений на tick.

Full texts/context по умолчанию не сохраняются; временный opt-in debug показывает
только текущему пользователю, истекает после run. Secret никогда не включается.

Тексты debug только ephemeral browser RAM, не IndexedDB/CacheStorage/localStorage,
не server diagnostic log. Максимум 100 коротких текстовых записей,
до 60 минут возраста каждой, очистка по monotonic TTL и при user switch,
consent revoke, run end, tab reload/close. Зависший run не продлевает TTL.
Финансовые агрегаты отдельно persistent, без текстов; опциональный экспорт
создаёт файл только после явного действия и предупреждения о данных.
Export redacted JSON: timestamps, versions, enum reasons, usage, агрегаты;
имя/фразы/notes/history только дополнительный явный opt-in, API key исключён безусловно.
Кнопка «Очистить диагностику» очищает ring buffer, **не финансовый ledger**.
Нельзя сбросить расходы кнопкой reset counters.

### 3.5. Микшер в diagnostics

AudioContext running/suspended, sample rate, master effective gain,
active/audible utterances, foreground ID, startOrdinal, background sum,
gain envelopes, buffer depth ms, underruns, received PCM, stream gaps,
clipping/peak observations. Last speech source меняется только actual start.
Определение audible activity не выдаётся за физическую слышимость динамиков.

Кнопки: local preview, mixer demo, reload ready pack, export, full settings.
Paid live test отдельный action с ценой/cap; недоступен в реальном active set,
при fault/pain/spotter и в safety overlay. Проверять и route, и actual hardware state:
persisted runtime view сам по себе не active workout, idle snapshot сам по себе
не разрешение мешать упражнению без машинного движения.
Тест не запускает `reset_fault`, движение или новую workout history.

## 4. Подготовка частых фраз по клику

### 4.1. Не путать три операции

1. **Сгенерировать** — платно создать новые audio files на backend.
2. **Скачать на устройство** — получить готовые файлы без inference.
3. **Подготовить к воспроизведению** — проверить/decode/cache нужное в RAM.

На основной кнопке «Подготовить частые фразы» сначала dry-run plan:
что уже есть, совместимо, отсутствует/повреждено, сколько файлов/байтов требуется.
Если всё готово — кнопка только download/decode, **не платная генерация**.
Если не хватает — UI показывает отдельный явный paid шаг с выбранным voice,
числом новых clips и cap. Клик согласия не автоматически включает Coach.

### 4.2. Каталог пакета

Предлагаемый базовый pack на voice: около 150–220 clips, точный manifest формируется
по редакторскому каталогу и audit имеющихся файлов, не произвольному target count.

| Группа | Содержимое |
|---|---|
| Count | 1–30 required, 31–100 optional expanded |
| Временные отметки | Половина/10/5/3/2/1/готово, проверенные тексты |
| Жизненный цикл | Start/resume/end/final set/exercise/workout, 2–4 variants |
| Честные исходы | Partial/skipped/aborted без fake success |
| Micro-support | 20–35 неперсональных текстов с eligibility по механике |
| Rest | Краткий отдых/подготовка, без длинных лекций |
| Safety | Утверждённые сообщения, без юмора и произвольных советов |
| Preview | Voice и overlap demo |

Для второго энергичного count варианта только нужный диапазон, не обязательный
двойной pack 1–100. «Дави» допускается только при проверенной соответствующей
механике; fallback neutral support, не случайная команда тяговому упражнению.
Bodyweight/timed/isometric отдельная eligibility; личные имена/результаты в общий pack не входят.

### 4.3. Dry-run и состояние UI

Показывать: selected profile/provider/model/styleVersion,
required/optional clip coverage, generated/verified/ downloaded/decoded counts,
local storage/free quota, bytes и известную реальную duration.
Состояния: not_prepared / planning / waiting_confirmation / generating /
verifying / downloading / decoding / ready / partial / failed / paused.
Не считать ready по наличию manifest с битым или отсутствующим обязательным файлом.

На кнопке прогресс: «Подготовлено 82/174 · 19 MB»; details показывают фазу.
Честно «загружено» отдельно от «готово к звуку» и «сгенерировано».
Decode не зависит от audible unlock, но реальный звук требует жеста.

### 4.4. Server job

План содержит generation fingerprint: clip text, voice/model, instructions version,
format, style version, locale. Изменение конкретного текста инвалидирует только его
artifact и новый pack manifest, не оплачивает весь pack заново.
Semantic clip ID стабильный, artifact ID content-addressed по fingerprint.

POST generation job с plan fingerprint, idempotency key, cap, выбранными clip IDs.
Если такой job уже идёт, return existing job, не duplicate paid generation.
Concurrency default 1 voice request, при поддержке лимитов можно 2; не мешать
workout live pipeline, generation deprioritized/paused между requests при активном упражнении.
Job ledger отдельно от workout, но учитывает общий operator daily cap.

После clip: atomic temporary write → checksum/decode verify → publish artifact →
save progress receipt. Complete compatible pack публикуется atomic manifest pointer.
Старый verified pack остаётся доступным до готовности нового.
Partial generation не публикуется как complete; explicit partial fallback использует
только совместимые verified clips и показывает missing required.

Активный run закрепляет packVersion. Новый complete pack предлагается после
подхода либо применяется со следующего run, не заменяет buffers посреди речи.
Partial job никогда не вытесняет закреплённый verified pack. Сменили voice сами —
старый голос уже несовместим, не использовать его как «бесплатный fallback».
Нет ни одного пригодного local clip — UI и обычные разрешённые live comments
могут работать, но честно без local count; это не фиктивный «local-only готов».

Кнопки pause/resume/cancel. Cancel не возвращает деньги за отправленный request.
Закрытие страницы не отменяет ограниченный server job; UI сообщает это до старта.
Key rotation может остановить новые dispatch; resume после обновления credential
использует существующие совместимые artifacts.
Crash после paid generation, но до progress receipt: сначала сверить saved artifact,
не регенерировать автоматически неизвестный paid clip. Unsettled attempts сохраняются.

### 4.5. Storage

- Backend private pack artifacts, immutable URLs/ETag/checksum, no secrets in paths.
- Доставка через whitelist API, без path traversal и arbitrary voice URLs.
- Browser CacheStorage/IndexedDB для encoded files, per-pack/profile version namespace.
- AudioBuffer RAM отдельно, LRU; sample-rate handling через общий AudioContext.
- Никаких base64 WAV в localStorage и Zustand persist.
- Required count/start/end/safety preload при prepare и до active подхода.
- Optional variants warm/decode on demand по budget, не full pack RAM автоматически.
- Предлагаемый cap encoded cache 100 MB, decoded RAM 32 MB; фактическая quota адаптивна.
- `navigator.storage.estimate()` и запрос persistence по действию пользователя,
  но браузер может отказать/очистить cache. Не обещать вечное offline хранение.
- Новый пользователь не получает чужой personal speech cache; общий неперсональный
  approved pack может быть общий на устройстве.
- Кнопка «Удалить локальные файлы» не удаляет server pack и не сбрасывает paid ledger.
- Кнопка «Удалить серверный пакет» операторская; предупреждение об offline отсутствии.

Подготовка по клику может автоматически обеспечить дальнейший warm cache до каждой
тренировки, если pack version готов; это **бесплатный fetch/decode**, не paid regeneration.
Если pack исчез/новый голос несовместим, показать действие prepare, не заказывать API молча.

### 4.6. Проверка качества и длительности

Нормализовать loudness offline; проверять decoded duration, leading/trailing silence,
checksum и clipping. WAV streaming sentinel header не источник duration.
Числа целимся ≤1 с, не режем окончание слова ради target. Clips count 20–30 могут
быть длиннее при правильном произношении; deadline выбирается по actual duration.
Safety required клипы прослушаны человеком до выпуска; approval catalog version.
Fast count тест 0,8–1,2 с между reps: не ускоряем произношение незаметно,
late clips пропускаем, а не накладываем длинную очередь.

## 5. Микшер: детальный алгоритм

### 5.1. Граф

Local buffer source и сетевой PCM source → per-utterance gain → voice bus →
master headroom/dynamics → destination. Отдельный system signal bus;
safety state отменяет ordinary voice и запускает только утверждённый сигнал при разрешённом звуке.
Нет одного `<audio>` с постоянно заменяемым src: он обрывает предыдущую речь.

Shared AudioContext один; disposal одного provider не закрывает контекст,
который ещё используют остальные источники. Sources owned by utterance ID.
Gain automation на audio timeline, а не setInterval, чтобы UI jank не дёргал звук.

### 5.2. Правило latest-start

В Map active utterances: id, scope, source, state, startOrdinal,
scheduledUntil, baseGain, currentGain, background weight, watchdog deadline.
`startOrdinal` выдаётся при первом audio sample. Reservation/request/first byte
сам по себе не foreground и не приглушает старый голос.

Foreground среди звучащих — максимальный startOrdinal. Новые PCM chunks не
перенумеровывают utterance. Счёт и сеть равноправны по правилу «новая начавшаяся громче».
Предлагаемый foreground coefficient 1; суммарный background coefficient B=0,65.
Для N background с одинаковым weight каждому B/N. Если различаются заранее
нормализованные loudness или countVolume, итоговый gain учитывает baseGain,
но background не усиливается выше его исходного foreground gain.
Общий уровень ограничен master headroom и проверенной dynamics chain.

### 5.3. Пример

| Время | Событие | Итог коэффициентов до master |
|---|---|---|
| 0 с | Comment A начал | A=1 |
| 2 с | Число N начало | N=1; A=0,65 |
| 2,7 с | N закончилось | A плавно →1 |
| 4 с | Comment B начал, A ещё играет | B=1; A=0,65 |
| 5 с | Число M начало | M=1; A=B=0,325 |
| 5,7 с | M закончилось | B→1; A→0,65 |
| 7 с | B закончилось, A ещё играет | A→1 |

Коэффициенты не гарантируют отсутствие суммарных пиков: true-peak проверка отдельно.
Начатая A не отменяется ради B/M. Новая фраза не обязана ждать playback complete;
paid generation single-flight — лишь ограничение requests.

### 5.4. Envelopes и release

На новом foreground отменить/зафиксировать предыдущую gain automation,
начать ramp из текущего фактического gain, не из предполагаемого old target.
Attack/restore finite, при cancellation нескольких voices пересчитать один раз.
Источник окончен только после буфера и хвоста; завершение HTTP не завершает звучание.
Zero volume означает реальное отсутствие аудио; обычный preview volume не обходит mute.

Не использовать exponential ramp к 0 напрямую без допустимого floor/linear mute:
Web Audio API имеет ограничения, обработать явно. Gain duck не playbackRate.

### 5.5. Network gaps и sample scheduling

На first PCM bounded jitter buffer; source sample rate из adapter metadata.
Resample если нужно корректно, без изменения тембра/скорости.
Decode/format error изолирует utterance, не весь shared context.
Sequence/generation identity проверяется до enqueue.

При scheduled buffer пуст >250 мс temporarily foreground среди действительно
звучащих; это не completed. При возобновлении old comment сохраняет старый ordinal,
не вытесняет новое число. Не анализировать каждую паузу в словах как новый speech start.
Max stall watchdog и byte/duration limit не продлеваются infinite PCM trickle.
В UI active count отдельно от audible count, gap отдельный reason.

Realtime adapter проверяет final transcript по нормализованному approved speechText
и ожидаемым числам; completion считается verified только при protocol done и
согласии transcript. В streaming режиме часть текста могла уже прозвучать:
это **post-factum verification**, не гарантия pre-playback correctness за 100 мс.
Обнаруженный mismatch отменяет оставшееся аудио и помечает failed/verbal_mismatch,
без автоматического paid перечитывания. Speech, требующая предварительной
дословной проверки, направляется в TTS/local или в явно более медленный режим
полной буферизации Realtime с проверкой до start; capability/latency видны в UI.
Сам TTS также не даёт абсолютной гарантии произношения: русские числа и pack
проверяются corpus-тестом и прослушиванием.

### 5.6. Density guard

Не заказан третий content voice при двух активных content voices;
при трёх любых voices optional request также удерживается в пределах original deadline.
Нет возможности — skipped, не unlimited queue. Count continues по fresh events.
Этот guard управляет будущими requests, а не обрывает существующие.
Пользователь может выбрать foreground/background balance, но не unlimited provider tasks.

### 5.7. Переходы и отмена

Подход→rest→summary одного exercise сохраняет started обычные фразы.
Не начатые фразы переоцениваются по semantic validity: «ещё три» нельзя перенести в rest.
Смена exercise/workout/user/model/voice, consent revoke, mute/disable, hidden policy,
safety отменяют источники и pending generations; late chunks не принимаются.
Обычная hardware pause и правка rest timer не считаются safety cancel.
Новый set может отменить ещё не начавшуюся rest speech; начатая короткая rest
доигрывает, но режиссёр заранее избегает длинного старта рядом с boundary.

### 5.8. Громкость и clipping

Master volume применяется один раз, background/foreground как относительные множители.
Pack нормализуется с запасом, network voice loudness контролируется консервативно,
не бесконечным AGC по первым 20 мс. Dynamics не должна делать слово громче после паузы.
Offline rendering overlap suite: 1/2/3 voices, loud number + long phrase,
смена foreground каждые 0,8 с, cancel/safety, gaps. Измерить sample peaks,
true peaks выбранным анализатором, intelligibility слушателем.
Не обещать quality по одному AudioContext `started`.

## 6. Платные тесты: как запускать и учитывать

Пользователь разрешил paid tests и указание key в настройках. Больше не требуется
спрашивать разрешение на каждый маленький тест после согласованного capped job.
Но нельзя считать это безлимитным разрешением на любой pack/provider/retry.

Предлагаемый wizard:

1. Secure key saved, auth status и model access по нужным моделям.
2. «Проверить автора» — 8–12 текстовых ситуаций, выбранный cap.
3. «Сравнить два голоса» — 4–8 одинаковых коротких проверенных текстов.
4. «Расширенный A/B» — 30 texts только после выбора shortlist, оба adapters/voices.
5. «Подготовить пакет» — только missing compatible clips, cap per job.
6. «Тренировка в replay» — без двигателей, usage как отдельный test run.

«Проверить автора» здесь означает **платную генерацию** текста; бесплатная
schema/prompt fixture validation — отдельная кнопка/CI, без обещания показать
реальное поведение Luna без inference. До dispatch UI показывает estimate/cap.
Voice preview/tests пишутся в отдельный test ledger, не в workout $2 ledger.
Звуковые тесты запрещены при незавершённой реальной workout без явного штатного
выхода из неё, даже на rest: не конкурируют с Coach и не портят session memory.
Техническая read-only диагностика и сохранение настроек без playback при этом доступны.
Metadata auth check не создаёт exercise result и не звучит.

Caps предлагаются UI из худшего доступного estimate, пользователь выбирает;
план не выдаёт $2/workout за автоматически утверждённый лимит $20 на пакеты.
Тестовые, pack и workout расходы раздельны, суммируются в operator monthly ledger.
Results показывают usage completeness, request stages, latency, transcript agreement,
audio started/completed и необходимость физического прослушивания.
Никаких key values в exported report.

## 7. Дополнительные критерии приёмки

- Secret никогда не читается GET settings и не хранится в browser persist.
- Auth/CSRF/HTTPS/secret redaction tests для key endpoint; operator privilege real, не selectedUserId.
- Mini debug в normal/compact, popover доступен и не перекрывает STOP/аварийный диалог.
- Counters в header корректны после silence, retry, cancel, reconnect, model switch.
- Unknown usage не 0, reasoning/cached/aggregate не учитываются дважды.
- Clear diagnostics не сбрасывает cap/ledger.
- Prepare click на готовом pack не создаёт inference request.
- Missing pack generation требует явного paid action и cap; repeated click return same job.
- Cancel/crash/resume не оплачивают всё снова и не publish partial как ready.
- Download/decode readiness различимы; quotas/eviction не приводят к скрытой paid регенерации.
- Mixer timeline из примера подтверждён offline render и реальным прослушиванием.
- Pipeline reservation не duck; PCM chunk не новый foreground; gaps корректно восстанавливают фон.
- Safety/mute cancel все ordinary voices и late PCM; ordinary phases не обрывают started.
- Новая setting count применяется только к новым rep events.
- Paid tests доступны без hardware movement и не пишут настоящие тренировочные достижения.

## 8. Порядок реализации этого блока

Сначала typed settings/secret vault и budget primitives; затем local packs/job UI
и shared mixer; мини-debug появляется одновременно с первым local playback,
не в конце проекта. Потом text provider и voice A/B, после него полный triggers pipeline.
Обязательная diagnostics позволяет выяснять отсутствие голоса без paid угадывания.
Все пункты здесь — требования к будущей реализации, а не утверждение о готовом функционале.