# E02 — контракты, наблюдение lifecycle и тестовый replay

Дата проверки: 07.10.2026. Реализовано с нуля: исходники и тесты back/back2 не использованы.
Прогресс: [единый трекер](13-live-ai-coach-implementation.md).
Это snapshot приёмки E02. После E03–E04 settings/vault/run API и capabilities
расширены; актуальная граница/API: [control-plane отчёт](13-live-ai-coach-e03-e04-control-plane.md).

## 1. Граница этапа

Это рабочий тестируемый каркас, **не готовый говорящий тренер**. В приложении
нет подписчика, запускающего генерацию или звук по наблюдаемым событиям.
Нет production LLM/TTS adapter, paid dispatch, WebSocket Coach, key storage,
persisted settings/run/ledger, pack generation, AudioContext или UI тренера.
Они относятся к E03–E11. Ни одна модель или запись голоса не выбрана этим этапом.

Новые модули Coach не импортируют motor command API или сетевые клиенты;
это проверено AST-тестом. Существующие тренировочные команды/порядок сохранения
не заменены. Watch-процессы не запускались; чужие изменения логов/PID не откатывались.

## 2. Контракты schemaVersion 1

- Backend: [Pydantic schemas](../backend/app/schemas/coach.py).
- Frontend: [readonly TypeScript contracts](../frontend/src/features/coach/model/contracts.ts).
- Общее тестовое событие: [synthetic fixture](../backend/app/tests/fixtures/coach_e02_replay.json).

Wire names — camelCase, включая вложенные модели; `schemaVersion: 1`.
Backend запрещает неизвестные поля, NaN/Infinity, ограничивает строки и массивы,
проверяет cross-field зависимости. TypeScript types сами не являются runtime
валидатором внешнего JSON. До добавления сетевого клиента потребуется его validation.

| Модель | Назначение / ключевые ограничения |
|---|---|
| `CoachSettings` | enabled=false, consent=null, local, companion, count=off, voice=null, history=false, revision=0, budget="2.00" |
| `CoachScope` | user/run, nullable exercise/setOrdinal, scopeEpoch; set требует exercise |
| `CoachRun` | scope, backend workout ID, live/test, idle/active/closed, pricingVersion |
| `CoachFact` | strict scalar value, unit, source, confidence, observedAtMs/validUntilMs, scopeEpoch; unknown только null; unit/value совместимы |
| `CoachEvent` | kind/phase/source, отдельные exerciseKind/controlMode/progressUnit, ordinal, revisions, deadline, ≤12 facts/dependencies |
| `CoachDecision` | speak/silence, text ≤600, intent/delivery/topic, usedFactIds; silence без текста/фактов |
| `CoachAudio` | utterance/generation/scope/sequence, codec/rate/channels, length/duration/final; metadata, не PCM внутри JSON |
| `CoachUsage` | attempt/ledger/stage/status/completeness, nullable tokens/cost/pricing; cached/reasoning — subsets, не отдельные суммы |
| `CoachRuntimeNotice` | captured backend IDs после commit; persisted set требует set/exercise/ordinal; finalized требует identity/outcome |
| `CoachCapabilities` | безопасный публичный ответ о каркасе; paidDispatch всегда false |

`exerciseKind`: machine/bodyweight/timed/stretch/group. Isometric/fixed_hold —
control modes, не виды упражнения. Метрики scaffold/позиции не превращены в
«измеренный темп/технику»; ограничения из [E01](13-live-ai-coach-e01-audit.md) сохранены.
`count=off` — безопасный default каркаса, не финальное продуктовое решение.
Budget здесь только контракт: ограничение расходов реализуется в E04.
Usage completeness не вычисляется из отсутствующих данных; null не заменяется нулём.

Reasons: disabled, no_consent, mute, audio_locked, hidden, safety, stale_source,
mock_source, owner_mismatch, scope_changed, no_window, cooldown, density_cap,
topic_repeat, pipeline_busy, budget, provider_circuit, validation_failed,
missing_clip, decode_failed, expired, duplicate, cancelled, queue_full.
Общий словарь не означает, что все будущие gate/policies уже реализованы.

## 3. Идентичность и окна

Canonical key — JSON array `[userId, runId, exerciseId, setOrdinal, kind, ordinal]`.
Для workout events exercise/set нормализуются в null; для exercise events set=null.
Backend IDs и revisions не входят в key: ack/revision не дают новую возможность речи.
`set_stopped` и `set_persisted` — разные keys. Backend set ID добавляется как alias
к уже потреблённой идентичности, без очистки receipts. Alias conflict отклоняется.

`scopeEpoch` инвалидирует async capture при смене user/run/exercise/set, включая A→B→A.
Обычный rest/view transition того же подхода его не меняет. Plan/context revisions
присутствуют в контракте; lifecycle foundation пока ставит 0, полноценная связь с
редактированием плана — следующий интерпретатор. В replay revision tick сам по себе
не отменяет событие: сравниваются только зависимости value/unit/provenance/confidence/epoch
и их validity. Изменённый или неизвестный dependent fact запрещает речь.

Все времена — monotonic milliseconds одного процесса/clock domain, не UTC и
не переносимый между клиентом и сервером timestamp. Replay использует fake clock.
Deadline ограничивает **начало** речи; реальный started-audio lifecycle будет в E05/E08.
Тестовый replay целиком собирает fake audio до возврата и отвергает поздний результат.

## 4. Read-only lifecycle

Frontend [observer](../frontend/src/features/coach/lib/lifecycle-observer.ts) и
[runtime subscriptions](../frontend/src/features/coach/lib/runtime-observation.ts):

- Capture до await с текущими IDs, выбранным user и epoch; anonymous/mock игнорируются.
- [Exercise screen](../frontend/src/screens/exercise-session/exercise-session-screen.tsx):
  set_stopped после штатного complete_set success (для немашинного — действия пользователя),
  set_persisted только после положительного save ID, exercise_finalized после summary ack.
- [Workout summary](../frontend/src/screens/workout-summary/workout-summary-screen.tsx):
  workout_finalized после summary ack с workout-only capture.
- Partial/skipped различаются; нулевой/неподтверждённый save не создаёт persisted ack.
  Ошибка позднего summary не отменяет уже успешный set ack и не создаёт finalized.
- Перед publish повторно проверяются текущие owner identities/mock/epoch; поздний ответ
  другого пользователя не попадает в Coach buffer. Observer ошибки не мешают тренировке.
- Outcome/actual value — сохранённый client result с provenance, не новая hardware measurement.

Backend [buffer](../backend/app/services/coach/lifecycle.py) подключён в
[RuntimeService](../backend/app/services/runtime_service.py). IDs захватываются до commit,
notice записывается **после** успешного commit. При commit=False notices передаются parent
save; вложенные set→exercise→workout появляются только после parent commit.
In-progress не создаёт finalized. Failed commit не создаёт notice.
Buffer не вызывает subscribers, network, audio или DB writes; ошибки подсчитываются
и подавляются. Это процессная наблюдательная память, не durable outbox/delivery guarantee.

## 5. Ports, fakes и replay

[Backend ports](../backend/app/services/coach/ports.py) и
[frontend ports](../frontend/src/features/coach/lib/ports.ts): clock, text provider,
voice adapter, verified pack storage, audio manager. Production implementation отсутствует.
[Fakes](../backend/app/services/coach/fakes.py) возвращают детерминированный текст и
короткий PCM silence; fake audio manager только хранит chunks, не проигрывает их.
Это не подтверждение озвучки или качества звука.

[ReplayCoordinator](../backend/app/services/coach/replay.py) — только test harness,
не импортируется startup и не mounted в API. Принимает explicit test_only providers
и synthetic/recorded события; live/hardware источник отвергается. Проверяет gates до/
после text await, каждого chunk и окончания stream; cancel инвалидирует generation.
Single-flight, bounded timeout ≤5s, без retry. Timeout/error потребляет opportunity,
возвращает provider_circuit, не пишет provider body в logs. Используемые факты должны
быть подмножеством event dependencies; silence не обращается к voice adapter.
Sequence/scope/generation/source/byteLength/final и общие audio caps проверяются.
Это admission/transport scaffold, не полноценная semantic validation LLM текста или audio decoder.

| Ресурс | Предел |
|---|---|
| Replay receipts / aliases | 1024, не вытесняются для повторной речи |
| Replay pending | 32 |
| Fake audio manager | 256 chunks |
| Replay одна генерация | ≤256 chunks, ≤2 880 000 bytes, ≤60 000 ms |
| Frontend records / consumed keys | 200 / 1024 на текущую identity |
| Backend observation deque | 256 по умолчанию; config capacity 1–1024 |

Replay не подключён к runtime saves, не записывает achievements и не имеет secret input.
Fixtures содержат только искусственные IDs/данные.

## 6. API и flags

Единственный новый endpoint: **GET /api/coach/capabilities**,
[route](../backend/app/api/routes/coach.py), response 200:

```json
{
  "schemaVersion": 1,
  "enabled": false,
  "implementation": "contracts-only",
  "paidDispatch": false,
  "lifecycleObservation": false,
  "replay": "test-only"
}
```

Это публичный неперсональный endpoint: без ключей, user IDs, history или tokens.
`enabled`/`lifecycleObservation` отражают только backend COACH_ENABLED; не effective
user consent, не frontend build flag и не readiness голоса. Даже при true paidDispatch=false.
Settings/credentials/replay/generation/write endpoints отсутствуют (404).
Frontend пока не интегрирует HTTP capabilities; контракт опубликован до клиента.

- Backend COACH_ENABLED по умолчанию false, включает только after-commit buffer.
- Frontend VITE_COACH_ENABLED включает buffer только при точном значении `true`;
  переменная compile-time, отсутствие/false ничего не включает.
- Флаги независимы, ни один не запускает inference или звук. Env/секреты не изменены.

## 7. Проверки и воспроизведение

Безопасный runner: [check_coach_e02.py](../backend/scripts/check_coach_e02.py),
запускается Python из корневого virtualenv. Сам выставляет emulator/temp DB/media,
отключает dotenv/panel/keyboard и запрещает socket/Modbus connect **до app import**.
Обычного app/tests fixture недостаточно для гарантии изоляции startup;
runner не использовать как production launcher.

| Проверка 07.10.2026 | Результат |
|---|---|
| Backend E02 + runtime/users regression, 5 файлов | **70 passed**, 2 warnings; 40 новых E02 cases + 30 baseline |
| Frontend Coach/runtime/exercise/rest/summaries, 7 файлов | **55 passed**; 22 новых cases + 33 regression |
| Scoped Ruff (новые модули + затронутые backend файлы) | PASS |
| TypeScript tsc --noEmit | 23 прежних diagnostics, 0 в Coach/изменённых screens; full build gate остаётся FAIL |
| Vite test-mode bundle, Coach off, temporary outDir | PASS; прежний large-chunk warning |
| AST no motor/network imports, fixture roundtrip, TS/backend vocabulary | PASS в suite |
| Editor changed-code diagnostics / git diff --check | PASS |

Покрыты happy/silence/dedup/alias, hard gates, scope/cancel/stale/deadline, revision
tick без изменений facts, undeclared facts, поздние chunks, bounded queues, timeout,
single-flight и mock guard. Integration tests проверяют post-commit identity/order,
failed commit, partial stop→persist→summary, summary failure и late ack после user switch.
Jsdom media warnings не являются acoustic validation. Проверялись scoped suites,
не full hardware suite. Paid запросов и физических hardware commands: **0**.

**E02.G принят технически. Следующий этап — E03: persisted per-user settings,
consent, operator authorization и безопасное server secret storage.**