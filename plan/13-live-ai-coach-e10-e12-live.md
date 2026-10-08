# AI-тренер — E10–E12: живой тренер, диагностика и приёмка

Дата: 08.10.2026. Решения: [13-live-ai-coach-decisions.md](13-live-ai-coach-decisions.md).
Трекер: [13-live-ai-coach-implementation.md](13-live-ai-coach-implementation.md).

## 1. Что сделано

### Backend (E10)

- `backend/app/services/coach/live.py` — `LiveCoach`: событие браузера → факты из БД по owner →
  Director (pacing/memory) → `TextAuthor` (Luna) → валидация → `VoiceStreamer` (Realtime) → tagged PCM.
  Single-flight pipeline, очередь итогов на 1 слот, ack (`playback_started/completed/failed`) двигает
  память/pacing только по фактическому воспроизведению. `default_pipeline` fail-closed: без paid-флагов,
  verified pricing или ключа в vault возвращает причину (`provider_unavailable`, `credential_unavailable`, `voice_unavailable`).
- `backend/app/api/routes/coach.py` — WebSocket `/api/coach/runs/{id}/live` (configure-first, lease renew 5 s,
  `stale_run` при смене настроек, лимиты 40 msg/s и 32 KB) и `DELETE /api/coach/users/{id}/memory`.
- Тесты `backend/app/tests/test_coach_e10_live.py` (16) подключены к safe runner.

### Frontend (E10–E11)

- `frontend/src/features/coach/live/coach-network-client.ts` — `CoachNetworkClient`: eligibility
  (флаг, backend-сессия, согласия, не local), run + token в `sessionStorage`, сокет без токена в URL,
  backoff/recovery, отправка событий (T01/T04/T21/T46 + lifecycle `set_persisted`/`exercise_finalized`/`workout_finalized`
  с backend refs), safety latch, ping 20 s, usage 15 s, потоковая речь через общий микшер с acks.
- `coach-live-runtime.ts` — передаёт состояние интерпретатора в сетевой порт и делит один микшер
  с локальными cue; snapshot содержит `network`.
- `lifecycle-observer.ts` — хранит backend refs по event id.
- Mini-debug: раздел «Сеть · E10» — состояние, режим, голос, счётчики, first audio, settled/pending/cap,
  последние 10 решений с причинами молчания, «Скопировать отчёт» (без текстов/токенов), «Забыть разговор».
- `vite.config.ts` — `ws: true` для прокси `/api`.

### Pilot

- `backend/scripts/coach_pilot.py live` — полный `LiveCoach` через production pipeline в sandbox-БД,
  ledger `test`, синтетические события и один сохранённый подход 10/10; без оборудования.

## 2. Проверки (08.10.2026)

| Область | Команда | Итог |
|---|---|---|
| Backend coach | `.venv/bin/python backend/scripts/check_coach_e02.py` | 397 PASS |
| Ruff (scoped) | `cd backend && ../.venv/bin/ruff check app/services/coach app/api/routes/coach.py app/api/dependencies.py app/schemas/coach*.py app/core/config.py app/tests/test_coach_*.py app/tests/conftest.py scripts/coach_pilot.py` | PASS |
| Frontend | `npx vitest run src/features/coach` + shell/safety/exercise-session/workout-summary | 21 файлов, 310 PASS |
| TypeScript | `npx tsc --noEmit -p .` | 23 baseline, 0 в coach/vite.config |
| Build | `npx vite build` | PASS (предупреждение о размере chunk — baseline) |
| Секреты | grep бандла `dist/` на ключ/имена env | 0 совпадений; `.env.local` и `coach_packs/` в `.gitignore` |

## 3. Paid прогоны

| Прогон | Что | Cap | Итог |
|---|---|---|---|
| `live-ash-20261008-022225` | Первый live pilot | $0.15 | 3/7 речь, затем `owner_mismatch`: pilot не продлевал lease (в сокете продлевается каждые 5 s). Исправлено в pilot. $0.0089 |
| `live-ash-20261008-022259` | Live pilot, 7 событий | $0.15 | **7/7 complete**, 15 запросов, **$0.0222**; first audio 0,58–0,78 s (холодный T01 1,85 s); событие→конец речи 3,5–7,3 s |
| `pack-ash-20261008-022623` | Обязательный пакет ash | $0.25 | 56/56, $0.065, 1 повтор после `transcript_mismatch` («Дваадцать два») — verification сработала |

Реплики live pilot (T01, T04, T21, T40, T46, T55, T58) фактически корректны; T40 сравнил с подходом
из первого прогона (та же sandbox-история). Замечание по качеству: шутка T46 упомянула гантели при
тренажёре — не факт о результате, но кандидат на уточнение humor-промпта после прослушивания.

Суммарно за сессию ≈ $0.64 (все прогоны ≤ cap).

## 4. Setup

1. Сервер: `COACH_ENABLED=true`, `COACH_MASTER_KEY_FILE`, operator hash; ключ вводится через форму оператора в vault.
2. Платные флаги `COACH_PAID_TEXT_ENABLED`, `COACH_TEXT_PRICING_VERIFIED`, `COACH_PAID_VOICE_ENABLED`,
   `COACH_VOICE_PRICING_VERIFIED` **по умолчанию `true`** (D-E12.1); выключение — `=false` в env.
3. Фронт: `VITE_COACH_ENABLED=true`; пользователь даёт согласие и сетевое согласие, режим «гибрид» или «только текст».
4. Пакет голоса: «Подготовить частые фразы» в настройках (missing — отдельное платное действие с cap).

## 5. Troubleshooting и rollback

- «Отклонена сервером · Сервер в локальном режиме» — в настройках режим «локальный»; смена режима снимает отказ.
- `provider_unavailable`/`credential_unavailable` — нет флагов/verified pricing/ключа; работает локальный тренер.
- `owner_mismatch` («Тренажёр у другого пользователя») — run занят другой вкладкой; повтор через 16 s.
- Rollback: `VITE_COACH_ENABLED` off или paid-флаги off; ledger и история не удаляются.
- Ротация ключа: ввести новый в форме оператора (версия vault растёт), старый отозвать у провайдера.

## 6. Не сделано / ждёт пользователя

- E12.4/E12.5 — прослушивание live-реплик и оценка утомляемости. Пакет ash и safety-клипы приняты 08.10.2026;
  после смены стиля голоса (`coach-voice-0.4`) — контрольное прослушивание нового пакета.
- E10.6 — 12 сценариев и 10–15 целых replay workouts с paid речью; E11.1 presets/overrides, E11.6 вёрстка 360–3840 px, E11.7 test wizard.
