# AI-тренер — E06: интерпретатор и локальные события

Дата: 07.10.2026. Статус: **Готов** (на TEST buffers; русские клипы появятся после E08/E09).

## Что сделано

| Файл | Назначение |
|---|---|
| [local-cues.ts](../frontend/src/features/coach/interpreter/local-cues.ts) | Каталог локальных cue: trigger ID, приоритет, deadline, стабильные clip ID (`count-N`, `countdown-N`, `set-start`…). Тот же список использует серверный каталог пакетов E09. |
| [coach-interpreter.ts](../frontend/src/features/coach/interpreter/coach-interpreter.ts) | Чистый интерпретатор без таймеров, сети, аудио и команд моторов. |
| [local-cue-player.ts](../frontend/src/features/coach/live/local-cue-player.ts) | cue → подготовленный клип → `LocalCoachAudioManager`; `missing_clip` вместо подмены; арбитраж rep beep. |
| [coach-live-runtime.ts](../frontend/src/features/coach/live/coach-live-runtime.ts) | Подписка на stores, receive time, gates (flag, consent, mute, hidden, AudioContext), диагностика. Запускается из shell только при `VITE_COACH_ENABLED=true`. |
| [coach-mini-debug.tsx](../frontend/src/features/coach/ui/coach-mini-debug.tsx) | Раздел «Интерпретатор · E06»: фаза, свежесть, блокировки, последняя фраза, причины пропуска. |

## Правила

- Фаза: `disabled` (нет пользователя/сессии, mock-данные) → `waiting-start` → `active-set` / `paused-set` → `rest` / summary; `suspended` при safety latch, emergency или боли.
- Свежесть: при открытом сокете неизменный snapshot актуален (backend шлёт только изменения); без сокета — возраст ≤ 1 с. Разрыв делает snapshot устаревшим до прихода нового. Out-of-order `emittedAt` отбрасывается.
- Safety latches: emergency/machine emergency/blocked/requiresService/panel stop/spotter/failure/fault, control/motion safety modes. Один `safety-stop` на фронт, не чаще раза в 30 с; ordinary речь отменяется.
- Счёт только для `machine` при свежем источнике своего пользователя, вне service/emulator (эмулятор — только `VITE_COACH_ALLOW_EMULATOR=true`). Baseline при первом наблюдении, reconnect и уменьшении; скачок не создаёт пачку старых чисел, остаётся только текущая веха.
- Режимы `count`: every / last-three (+ «половина» при цели ≥ 8) / milestones (half, three-left при цели > 6, target) / off. Диапазоны и failure-подходы — без вымышленной цели (`ambiguous_target`). Смена режима применяется только к новым повторам.
- «Последний повтор» (T18) не создаётся: нет пригодного rep-start источника.
- Удержания: hold-start, половина, «10 секунд», 3-2-1 только по возрастающему `isometricElapsedS`.
- Bodyweight/stretch/group: start только на наблюдаемом переходе, без счёта по чужому грифу (`no_source`); timed без runtime-таймера молчит (`T27 no_source`).
- Lifecycle: set_stopped → set-end/partial/skipped, set_persisted снимает ожидание, задержка > 5 с → `save_delayed`; exercise/workout finalized → итоговые cue. Устаревшие события → `expired`.
- Отдых: last-set-next при входе в отдых перед последним подходом; метки 10/0 только на реальном пересечении работающего таймера; крупная правка таймера поглощает метку без звука.
- Dedup: ключ `[user, run, exercise, set, kind, ordinal]`, без вытеснения; revisit, mute и смена настроек не воспроизводят старое. Одинаковая причина пропуска не повторяется на каждом tick.
- Rep beep: принятый голосовой счёт заменяет beep этого повтора; при отсутствии клипа beep остаётся единственным сигналом.

## Проверки

- `npm run test:run -- src/features/coach src/shared/ui/layout/forma-shell.test.tsx src/shared/ui/overlays/safety-dialog.test.tsx src/screens/exercise-session/exercise-session-screen.test.tsx src/screens/workout-summary/workout-summary-screen.test.tsx` — 16 файлов, 270 PASS (из них новые: интерпретатор 34, live runtime 10).
- Whole-workout replay через настоящий `LocalCoachAudioManager` с `FakeContext`/`FakeClock` и TEST buffers: 8 cue, 8 admitted, 8 actual starts.
- Статический тест: исходники `features/coach` не содержат hardware command API.
- `npx tsc --noEmit` — 23 baseline ошибки, 0 в Coach.
- 0 платных запросов, 0 hardware-команд.

## Ограничения

- Русские клипы счёта ещё не существуют (D09): до E09 live runtime сообщает `missing_clip`, и звучит legacy beep. Поэтому веха M2 не отмечена — нужен подготовленный pack и прослушивание.
- Таймеры timed-упражнений не являются источником событий (нет runtime-таймера в store).
