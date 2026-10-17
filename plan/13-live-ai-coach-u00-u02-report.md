# AI-тренер — отчёт U00–U02

> **Исторический срез; текущие выводы заменены 17.10.2026.**
> См. [итоговый отчёт U00–U07](13-live-ai-coach-u00-u07-progress.md).
> Ниже сохранены исходные evidence/цифры без переписывания. Выводы «U02.4 частично»,
> «snapshot/миграции нет», «U03 не начат» и старые source versions больше не актуальны:
> U00–U06 реализованы offline; optional 0012 не применялась к рабочей БД, full-plan
> доступен лишь новым workouts с declared snapshot после явной миграции.
> U07 лишь подготовлен и заблокирован, U08–U10 не начаты.

Дата: **17.10.2026**. Снимок: **HEAD `178999a` + незакоммиченные изменения**.
Основание: [план улучшения](13-live-ai-coach-improvement-plan.md),
[аудит](13-live-ai-coach-audit-2026-10-17.md), проверка текущих исходников и тестов.

**U00 — готов; U01 — готов; U02 — в работе (U02.4 частично).**
Защитный критерий U02 проверен, но положительное подтверждение выполнения
всего плана тренировки недоступно. U03–U10 этим отчётом не принимаются;
чекбоксы E00–E12 не переоцениваются.

## 1. Baseline, версии и границы

- Исходный offline baseline до U-изменений: **433 backend / 329 frontend PASS**
  (зафиксированный результат предыдущего прогона, не повторный запуск старого commit).
  «Чисто» относится к тестам, не к Git: дерево уже содержало пользовательские правки
  [author-тестов](../backend/app/tests/test_coach_e07_author.py),
  [behavior-промптов](13-live-ai-coach-behavior-prompts.md) и runtime/watch-логов.
  Они не откатывались и не перезаписывались ради документации.
- При возобновлении дерево уже включало U00–U02 и изменение рабочей БД,
  наблюдавшееся позднее при активном пользовательском watcher. Агент рабочую БД
  не читал и не менял; её внешнее изменение не относится к реализации U.
  Watch-процессы пользователя уже работали: агент их не запускал и не перезапускал.
- В этом документирующем проходе правятся только пять плановых документов.
  Нет чтения env/vault/пользовательских preferences/рабочей БД, команд оборудованию,
  миграций, генерации пакетов или новых paid-запросов. **Paid: $0**.
- Source defaults, не effective настройки пользователя: `gpt-6-luna`, reasoning `low`;
  `gpt-realtime-2.1-mini`, голос `ash`; пользовательский cap **$2/workout** не повышался.
  Основание: [конфигурация](../backend/app/core/config.py),
  [контракт настроек](../backend/app/schemas/coach.py).
- Source versions: `coach-prompts-0.8`, `coach-voice-0.5`,
  `coach-pack-catalog-0.1`, `coach-pack-style-0.3`, новая `metric-policy-0.2`.
  См. [prompts](../backend/app/services/coach/prompts.py),
  [voice](../backend/app/services/coach/voice.py), [packs](../backend/app/services/coach/packs.py),
  [facts](../backend/app/services/coach/facts.py).
  Версия промпта не равна хешу всего файла: voice менялся ради telemetry;
  старый whole-file hash не выдаётся за актуальный fingerprint промпта.
- Из приватного указателя пакета и его manifest прочитаны только безопасные
  version/model metadata: `ash`, `cbf9c5512caed39c`, `gpt-realtime-2.1-mini`,
  catalog `0.1`, style `0.3`. Manifest доступен; новый пакет не создавался,
  checksum/decode/прослушивание заново не принимались.

## 2. U00 — воспроизводимый baseline

[Корпус](../backend/app/tests/fixtures/coach_u00_replay.json): **70 synthetic-сценариев,
12 групп**. [Тест](../backend/app/tests/test_coach_u00_replay.py) проверяет независимую
матрицу, фиктивные identity и каждое текущее ожидание **дважды** с одинаковым результатом.
Это не production recording и не доказательство полной реализации будущих U-этапов.

Пять явных baseline skips: `audio-locked`, `audio-hidden`, `audio-underrun`,
`audio-overlap`, `memory-forget`. Перед skip проверяется отсутствие соответствующей
возможности у fake: эти browser/delete workflows не реализованы в данном replay driver,
а не успешно приняты. Другие, в том числе frontend overlap-тесты, не заменяют этот gap.
Ограничения остальных сценариев явно названы `baseline_limitation`.
Изменившиеся при U02 ожидания сравнений сохраняют `baseline_expect`, а не стирают baseline.

[Безопасный runner](../backend/scripts/check_coach_e02.py) отключает dotenv и paid,
использует временные DB/media/packs, пустые vault paths, emulator; запрещает
network connect, serial open и Modbus connect **до pytest collection**.
Исходная метрика `firstAudioMs` — voice-first-PCM, не event-to-playback и не акустика.

## 3. U01 — identity, допустимые переходы, время и telemetry

- Immutable identity сохраняет исходные event/run/exercise/set/scope epoch,
  plan/context versions, время создания, deadline и fact dependencies через
  text decision, `speech_start`, original-scope PCM и playback ACK. PCM scope не
  переписывается на текущий; исходная identity связана с generation registry.
- Lifecycle фиксирует время, phase и версии **при capture до async save**,
  а не при publication. Нет live provenance — событие остаётся local-only;
  сеть не присваивает ему новые версии, backend с context не ищет zero-version fallback.
- Pending обычной поддержки требует точного контекста. Только подтверждённые
  result refs позволяют монотонные пути: set `active-set → finalizing-set → rest`,
  exercise `active-set → finalizing-set → exercise-summary`, workout — только
  `workout-summary`. Допустим пропуск промежуточного render; один same-summary epoch
  remap. Нет setup/waiting-start исключения, обратного перехода и resurrection.
  Backend сначала проверяет сохранённые строки/владельца; origin phase/scope не подменяет.
- Уже started речь переживает обычный переход того же user/run при прежнем плане;
  plan/owner/run/gate/safety invalidation терминальна. ACK duplicate/reorder/mismatch
  не создают повторного старта/завершения. Локальные terminal receipts различают
  естественное окончание и interruption после start; исчезновение из mixer не считается completion.
- Browser monotonic deadline исходный, не продлевается на доставке/reconnect.
  Server receipt TTL использует исходный интервал минус `elapsedAtSendMs`;
  время transit ему неизвестно. Абсолютные часы браузера и сервера не вычитаются;
  окончательная проверка original deadline перед стартом остаётся в браузере.
- Server: receive, text start/end/duration, first PCM, speech end, ACK start/end/cancel.
  Browser: event→send, первый принятый PCM, наблюдаемый mixer start, completed/failed.
  Отдельные bounded p50/p95 (до 128 samples/group), source/model/connection labels;
  server durations и browser durations не объединяются в синхронизированную шкалу.
  Cold/warm определяется по **фактической отправке** Realtime; reconnect после idle
  failure — cold, не warm по наличию socket. Где данных нет — unknown/fake.
  Mixer start/ACK не доказывают звук из динамика; paid/acoustic latency не измерялась.

Доказательства: [backend policy](../backend/app/services/coach/identity.py),
[live pipeline](../backend/app/services/coach/live.py),
[voice send classification](../backend/app/services/coach/voice.py),
[capture](../frontend/src/features/coach/lib/lifecycle-observer.ts),
[browser policy](../frontend/src/features/coach/live/coach-scope-policy.ts),
[network client](../frontend/src/features/coach/live/coach-network-client.ts),
[local receipts](../frontend/src/features/coach/audio/local-coach-audio-manager.ts).
Проверки: [backend U01/lifecycle/telemetry](../backend/app/tests/test_coach_e10_live.py),
[voice](../backend/app/tests/test_coach_e08_voice.py),
[browser capture→publish→PCM/ACK](../frontend/src/features/coach/live/coach-network-client.test.ts),
[policy](../frontend/src/features/coach/live/coach-scope-policy.test.ts),
[terminal receipts](../frontend/src/features/coach/audio/local-coach-stream.test.ts),
[mini-debug](../frontend/src/features/coach/ui/coach-mini-debug.test.tsx).
Последняя начавшаяся реплика по-прежнему громче; sequential queue не вводилась.

## 4. U02 — факты и консервативная полнота

- `metric-policy-0.2`: comparison требует известных kind, режима, working/warmup,
  ordinal, метода счёта, диапазона, calibration identity и declared weight для machine.
  Для dynamic machine нужен одинаковый `loadProfileId`; non-machine unloaded/load и
  calibration N/A определяются явно политикой, не совпадением `None == None`.
  Неизвестное обязательное условие даёт limited/unavailable без delta/прогресса.
  `calibration_state=calibrated` не считается identity использованной калибровки.
- У факта есть bounded provenance, unit, quantity kind, timestamp (может быть unknown),
  sufficiency. Analytics weight — **плановый/declared**, не applied/measured;
  произвольные одноимённые machine metrics это не доказывают. Эти metadata доходят до
  промпта; валидатор запрещает подмену. Старые результаты часто остаются limited.
- `target_met` проверяет точную цель, нижнюю границу диапазона или explicit open target;
  completion label не перекрывает недостигнутую/неизвестную цель. Exercise full требует
  persisted `target_sets`, уникальных непрерывных ordinal, completed exercise и
  подтверждения целей всех строк. Missing/skipped/partial/unfinished/unknown не дают full;
  duplicate ordinal отклоняется как ambiguous.
- **U02.4 частично:** workout schema/runtime save не хранит авторитетный снимок
  всего плана/число всех запланированных упражнений. Поэтому workout summary всегда
  partial/limited с `authoritative_workout_plan_unavailable`; даже observed-full и
  `status=completed` не разрешают «весь план выполнен». Подсчёт сохранённых результатов
  работает; положительного full-plan пути **нет**. Новый snapshot/миграция не создавались.
- Про partial movement допустимо только «Последнее движение не засчитано»;
  причина, амплитуда и оценка тела не выводятся из входного label.
- Persisted source signature + semantic package повторно загружаются свежей DB session
  после author перед text/`speech_start` и перед первым непустым PCM. Изменение/удаление
  результата, плана, условий, истории/набора упражнений отменяет ответ как `facts_changed`.
  Это два async handoff gate, не транзакционная блокировка до акустического старта
  и не запрос БД на каждый chunk.

Доказательства: [facts](../backend/app/services/coach/facts.py),
[history и summaries](../backend/app/services/coach/history.py),
[revalidation](../backend/app/services/coach/live.py),
[prompt metadata](../backend/app/services/coach/prompts.py),
[validator](../backend/app/services/coach/validation.py),
[U02 goal/kind/summary/mutation matrix](../backend/app/tests/test_coach_u02_facts.py).

## 5. Проверки 17.10.2026 и следующий шаг

| Проверка | Результат / область |
|---|---|
| `.venv/bin/python backend/scripts/check_coach_e02.py` | Повторно **694 passed, 5 skipped, 9 warnings, 27.42 s**; ранее зафиксировано около 27.9 s. Warnings не объявляются устранёнными. |
| `npm exec -- vitest run src/features/coach` | Повторно **446 passed / 18 files**, 8.49 s; после U01 и telemetry UI. |
| Ruff | PASS: весь coach service, U00/U02 tests, E08/E10 tests и safe runner. |
| Vite | Повторно PASS **после telemetry UI**: 1868 modules, 3.69 s; dotenv off, output во временный каталог, затем удалён. Есть large-chunk warning. |
| `npm exec -- tsc --noEmit --incremental false` | **23 существующие ошибки / 7 non-coach files; 0 coach**. Общий TypeScript/build gate не зелёный; успешный Vite не заменяет его. |

Для закрытия U02.4 нужно определить и реализовать авторитетный versioned workout-plan
snapshot (включая отсутствующие упражнения/подходы), его save/revalidation contract и
positive/negative тесты полного workout summary. До этого активен **U02**, U03 не начат.
Безусловный отказ от full-plan claim — достигнутый safety gate, не выполнение этой feature.
Paid pilot и пользовательское прослушивание остаются позднейшими gates U07/U09/U10,
а не причиной незакрытого U02.4. Fallback, очередь итогов, semantic memory, ситуативная
подача и выбор моделей не принимаются за готовые по этим unit/replay-проверкам.
