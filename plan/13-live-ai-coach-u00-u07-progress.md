# AI-тренер — итоговый срез U00–U07

> **Дополнено реальной live-проверкой:** пользователь разрешил до $10;
> [новый отчёт](13-live-ai-coach-live-tuning-2026-10-17.md) фиксирует исправления,
> prompt 0.12, 1015 backend / 543 frontend PASS, 129 paid requests и общую liability
> $0.203885. U07.5 A/B выполнен (14/14 transcript match); остаётся пользовательское
> прослушивание U07.6 и promotion U07.7. Candidate production OFF.
> Остальной текст ниже — предыдущий **offline historical срез**, его утверждения
> «paid $0», «cap не согласован», «CLI plan-only», prompt 0.11 больше не текущие.

Дата: **17.10.2026**. Текущее незакоммиченное дерево; это сводка реализации и
последних проверок, не приёмка релиза или звучания. Заменяет текущие выводы раннего
[отчёта U00–U02](13-live-ai-coach-u00-u02-report.md), сохраняя его historical evidence.
[Трекер](13-live-ai-coach-implementation.md) · [U-план](13-live-ai-coach-improvement-plan.md) ·
[решения](13-live-ai-coach-decisions.md).

## Статус и доказательства

**U00–U06 реализованы и проверены offline. U07.1–U07.4 — только подготовленный
disabled candidate; U07 заблокирован. U08–U10 не начаты.** Строгая зависимость
U06 → U07 → U08 → U09 → U10 сохраняется; документационная сверка не закрывает U10.

| Этап | Фактический результат / evidence |
|---|---|
| U00 | 70 synthetic сценариев / 12 групп, двойной replay; [driver](../backend/app/tests/test_coach_u00_replay.py). Пять baseline skips — отсутствующие browser/delete workflows driver, не принятые функции |
| U01 | Immutable capture-time identity/phase/versions до text/PCM/ACK, terminal invalidation и раздельные bounded server/browser latency; [live tests](../backend/app/tests/test_coach_e10_live.py), [browser tests](../frontend/src/features/coach/live/coach-network-client.test.ts). Mixer start не акустическое измерение |
| U02 | Provenance и известные условия сравнения, planned ≠ measured, partial/unknown fail-closed; [facts tests](../backend/app/tests/test_coach_u02_facts.py). U02.4 positive/negative full-plan path: [snapshot tests](../backend/app/tests/test_coach_u02_workout_plan.py) |
| U03 | **Local-first** подтверждение, live только с новой фактической добавкой, не повторной похвалой; bounded opportunity FSM/priority queue, идемпотентные ACK, natural/interrupted отдельно, duration/attempt budgets. [Backend tests](../backend/app/tests/test_coach_u03_completion.py), [browser FSM](../frontend/src/features/coach/live/opportunity.test.ts). Latest-start foreground/одновременный микшер сохранён, очередь opportunities не serial-аудиомикшер; слышимость требует доступных пакета и аудио |
| U04 | Bounded context и один применимый versioned tip из ограниченного engineering-reviewed machine pilot; не весь каталог и не human/medical certification. [Context tests](../backend/app/tests/test_coach_u04_context.py), [feedback UI tests](../frontend/src/screens/rest/set-feedback.test.tsx) |
| U05 | Heard/attempted/started/completed/interrupted разделены, tip считается объяснённым после natural completion; ограниченные мотив/callback и память reconnect без replay. [Отчёт](13-live-ai-coach-u05-report.md), [tests](../backend/app/tests/test_coach_u05_memory.py) |
| U06 | Speech actions, необязательный юмор, bounded density/coalescing, quantity/provenance/negation/partial guards, безопасный fallback/молчание без recursive funny retry. [Tests](../backend/app/tests/test_coach_u06_direction.py), [positive/negative corpus](../backend/app/tests/fixtures/coach_u06_validation.json). Прохождение корпуса не гарантирует идеальную валидацию произвольной речи |
| U07 | Отдельные presentation profiles и статические A/B пары; [offline report](13-live-ai-coach-u07-report.md), [tests](../backend/app/tests/test_coach_u07_delivery.py). Платного A/B, прослушивания и promotion нет |

## U02.4: optional migration, не применённая к рабочей БД

[Миграция 0012](../backend/alembic/versions/20261017_0012_coach_workout_plans.py)
добавляет optional `coach_workout_plans`. [Модель](../backend/app/models/analytics.py)
имеет отдельную metadata и **исключена из startup `Base.create_all`**;
[runtime path](../backend/app/services/coach/workout_plan.py) таблицу не создаёт.
Миграция проверена только на временной БД; здесь не запускалась.

Положительный full-workout путь доступен **только после явного применения миграции**,
для **новых** in-progress workouts с declared-client snapshot до любых результатов,
неизменным baseline и совпадающими сохранёнными упражнениями/подходами/целями/условиями.
Это декларация плана, не telemetry физически применённой нагрузки. Отсутствующая таблица,
существующие workouts без baseline, missing/partial/unknown результаты остаются limited;
поздний snapshot не backfill. Изменение/удаление/undo не восстанавливает full eligibility.
Persisted dependencies перечитываются после author и перед первым непустым PCM,
не на каждом chunk и не атомарно до динамика.

## U04–U05: UI, согласие, TTL и удаление

[Отдых](../frontend/src/screens/rest/rest-screen.tsx) содержит
[необязательный ввод effort/discomfort](../frontend/src/screens/rest/set-feedback.tsx):
только явное нажатие, **без значений по умолчанию**; неизвестное не считается нормой.
Feedback привязан к пользователю/подходу, имеет проверку свежести, не сбрасывает safety.
Микрофона нет: это UI-самооценка, не услышанный ответ или медицинский вывод.

[RunMemoryStore / CrossWorkoutStore](../backend/app/services/coach/memory.py):
- Current-run cache: максимум **32 user/run entries на процесс**, hard **24 h** monotonic TTL,
  reconnect его не продлевает; нет повторного воспроизведения pending events/audio/ACK.
- `memoryEnabled` default **true**, независимо от `historyConsent`;
  `crossWorkoutMemory` default **false**, отдельный явный opt-in плюс consent gate.
- Межтренировочный cache: максимум **128 пользователей**, только четыре сохранённых enum
  `style`, `humor`, `verbosity`, `praise`, срок **7 дней**; неизменные данные не продлевают TTL.
  Нет достижений, биографии, самочувствия или свободного текста. Оба cache process-local,
  теряются при restart; существующее хранение preferences не делает их durable memory.
- TTL удаляет записи лениво при обращении/prune, не фоновым точным таймером.
  Forget/disable очищают live/cached/cross memory и инвалидируют pending контекст;
  analytics/settings/billing и safety/pacing не удаляются. Forget не отзывает согласие:
  при оставшемся enabled последующая активность может снова пополнять память.

## Проверенные source versions и U07 gate

Проверены исходники, **не effective env/preferences**:
[author prompt](../backend/app/services/coach/prompts.py) **`coach-prompts-0.11`**;
[voice](../backend/app/services/coach/voice.py) accepted **`coach-voice-0.5`**, candidate
**`coach-situational-candidate-0.1`**; [packs](../backend/app/services/coach/packs.py)
catalog **`coach-pack-catalog-0.1`**, style **`coach-pack-style-0.3`**, без изменений.
Исторические prompt 0.8/0.9/0.10 — ранние срезы, не текущая source version.

[Source flag](../backend/app/core/config.py) `COACH_SITUATIONAL_DELIVERY_ENABLED=false`,
`SITUATIONAL_DELIVERY_ACCEPTED=False`, default `Delivery.profile=legacy`.
Production требует обоих gates; candidate не включён и не принят. Legacy voice/count/safety
instructions и записи не заменены. [Preparation CLI](../backend/scripts/coach_delivery_pilot.py)
только планирует: 10 статических пар, count/safety local-only, до 14 будущих requests
для семи остальных пар; generation сейчас недоступна.

Следующий запрос пользователю — **отдельное разрешение paid cap и human listening**.
**$0.10 — предложение, не одобренный cap**, не обещание выполнить все пары за эту сумму.
U07.5–U07.7 pending; без A/B, учёта расходов и принятия человеком нет promotion и U08.
Существующий cap **$2/workout** не повышен, прошлые E-разрешения не принимают новый candidate.

## Последний проверенный срез

Результаты последнего завершённого прогона предоставлены для этой сверки;
**в документационном проходе код/тесты/сборка не запускались**.

| Проверка | Фактический результат |
|---|---|
| Safe backend runner | **958 passed, 5 skipped, 9 warnings, 36.59 s** |
| Targeted frontend, реальные тесты | **543 passed / 24 files, 13.30 s**: coach + runtime-persistence + exercise-session + rest/set-feedback; не весь frontend |
| Scoped Ruff | **PASS**: все изменённые coach/runtime файлы, включая migration 0012; не утверждение о всём repo |
| `git diff --check` | **PASS** |
| Vite | **PASS**, **1871 modules, 4 s**; large-chunk warning остаётся |
| TypeScript | **23 существующие ошибки / 7 non-coach files, 0 changed-file errors**; последняя команда завершилась ошибкой baseline. **Type-clean/build gate не заявляется**, Vite его не заменяет |

## Границы прохода и незакрытые gates

Только документы в plan: без кода/тестов, env/vault/секретов/рабочей БД/log contents,
paid calls (**$0**), генерации пакетов, миграций, hardware commands или restart watchers.
Изначальные пользовательские изменения, рабочая БД, логи и остальные dirty files
не записывались агентом в этом проходе, не откатывались и не приписываются документации.
Исторические E evidence/checklists сохранены, не выданы за свежую проверку.

Остаются: отдельный paid cap и human listening U07; все U08–U10 по зависимости;
пять replay-driver gaps, TypeScript baseline, warnings, отсутствие acoustic/end-to-end
приёмки и durable conversational memory. Optional migration — отдельное явное действие,
не разрешённое этим отчётом. Проверка ссылок не заменяет эти gates.
