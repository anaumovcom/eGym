# U07.1–U07.4 — offline candidate delivery preparation

> **Новый статус после разрешения $10:** [реальный live/A/B отчёт](13-live-ai-coach-live-tuning-2026-10-17.md).
> U07.5 выполнен: 14 paid takes, 14 transcript match, $0.029425, без count/safety.
> `generate` реализован с confirmation/cap/ledger. Остаются U07.6 прослушивание
> и U07.7 promotion; production candidate OFF. Текст ниже — историческая подготовка,
> не актуальное утверждение об отсутствии paid approval или выполнения CLI.

> Доказательства ниже относятся к подготовке U07. Последний общий verified срез,
> актуальные source versions и сверка исторических документов — в
> [итоговом отчёте U00–U07](13-live-ai-coach-u00-u07-progress.md).
> Указанные ниже «frontend не запускался» и «полная сверка позже» описывают только
> тот проход, не финальный срез. U07 по-прежнему заблокирован, не завершён.

Дата: **17.10.2026**. **U07 заблокирован на отдельном paid cap и прослушивании.**
U07.1–U07.4 реализованы только как offline preparation; U07.5–U07.7 не выполнены.
U08–U10 **НЕ НАЧАТЫ**. Это не разрешение платных вызовов и не акустическая приёмка.

## Неизменный baseline и gates

- Accepted `coach-voice-0.5`, `coach-pack-style-0.3`, provider voice и текущие записи
  сохранены. `TTS_TEMPLATE`, `REALTIME_INSTRUCTIONS`, `COUNT_INSTRUCTIONS` остаются
  byte-exact; старые verbatim/hash tests проходят. Пакеты и их версии не менялись.
- Новый `coach-situational-candidate-0.1` имеет отдельную версию, не заменяет baseline.
- В [code config](../backend/app/core/config.py) `COACH_SITUATIONAL_DELIVERY_ENABLED`
  по умолчанию **false**. Файлы реальных env не читались и не менялись.
- В [voice](../backend/app/services/coach/voice.py) `SITUATIONAL_DELIVERY_ACCEPTED`
  остаётся **False**. Production требует одновременно acceptance после будущей
  пользовательской приёмки и explicit flag; один flag или просьба реализовать не включает candidate.
- `Delivery.profile` по умолчанию `legacy`. Adapter construction также default-off;
  явный `situational_enabled=True` допускает только осознанную подготовку/моки.
  Будущий paid execution всё равно обязан пройти ledger/confirmation/cap gates.
- Откат: flag false / профиль legacy; accepted prompt и файлы пакетов сохранены.
  Промоция и выпуск новых пакетов U07.7 не реализованы и не имитируются.

## Профили и граница данных

Стабильный timbre/низкое ровное начало отделены от presentation. Шесть профилей:
count/support/result/playful/partial/safety. Warm smile и playful допустимы в
уместной подаче; никаких добавленных слов, искусственного смеха или новых шуток от диктора.
Count/safety строгие; их маршрутизация и текущие локальные записи не менялись.

[Live](../backend/app/services/coach/live.py) выбирает candidate по **выбранному
валидированному intent, speech action и outcome**, не по broad trigger:
humor → playful, result/summary с partial/limited/unknown → partial прежде юмора,
подтверждённый full → result, иначе support. Offered playful slot сам по себе
не делает реплику юмором. Ручные energy/pace пользователя имеют приоритет и при legacy.

Голосовой Realtime payload остаётся только `speechText` + bounded delivery;
в нём нет полного workout, истории, пользовательской оценки, invoice или author context.
Названия/числа уже представлены русским утверждённым текстом; дополнительные
pronunciation hints пока не нужны (в плане пустой список для обеих сторон).
Candidate instructions заменяют, а не дописывают противоречащий им baseline запрет улыбки.
TTS применяет тот же gate. Ledger-bound streaming консервативно включает candidate
instruction bytes в input reserve; paid gates и output/time bounds не ослаблены.

## Статические A/B артефакты — никаких генераций

[Fixture](../backend/app/tests/fixtures/coach_u07_delivery.json): **10 пар** с одинаковыми
русскими текстами A/B: два числа, поддержка, два partial, юмор, итог, два названия
упражнений, safety. Это фиксированный разрешённый для offline чтения корпус, не
факты о реальной тренировке; никакой новый текст не запрашивается у провайдера.

[Preparation CLI](../backend/scripts/coach_delivery_pilot.py) имеет только `plan`
и help. Он использует stdlib и читает только fixture; не импортирует application,
settings, dotenv, vault, DB или paid pilot. Выводит JSON, не пишет WAV/пакеты/ledger.
Paid flags/команда generation отвергаются parser ещё до какого-либо доступа к API.

План содержит одинаковые text/energy/pace/pronunciation для A/B, отдельные версии,
`providerRequests=0`, `paidUsd=0.00`, `approvedCapUsd=null`, `generationAvailable=false`.
Два count и safety — **local-only, current recordings, generation forbidden**.
Для остальных семи пар будущий верхний предел — **14 запросов**, без автоповторов.
Это только preparation ceiling, не существующий paid dispatch и не смета расходов.

## Paid cap и следующий gate

**Потрачено $0.00. Разрешённого paid cap нет.** Предложение: небольшой **$0.10**
на отдельно согласованный будущий capped pilot — **не одобрение**. Такой cap может
позволить лишь часть пар из-за консервативных reserves; полнота за $0.10 не обещается.

Перед будущим пилотом нужен отдельный explicit paid confirmation + positive cap,
проверенные модель/тарифы, reserve → dispatch → settle для каждой попытки. Рекомендуется
расширить существующий capped pilot особыми candidate options после согласования;
его текущий `voice` режим не является U07 A/B и здесь не запускался/не менялся.
Help/plan остаются без ключей/API. Никакой скрытой предгенерации или full-pack job.

Будущий отчёт должен записать usage/completeness/cost, voice-first-PCM отдельно от
generation time, точность transcript/чисел/названий и отсутствие добавленных слов.
Пользователь слушает stable timbre, низкий onset, тепло, естественность, ясность,
уместность юмора. Только после принятия — отдельное решение U07.7 и explicit opt-in;
safety/count не перегенерировать. Сейчас этот gate **не пройден**.

## Проверки и актуализация U00–U06

Входной срез пользователя: **918 backend / 543 targeted frontend PASS**.
Текущий safe runner: **958 PASS / 5 baseline skips / 9 warnings**; U07 добавляет
40 offline tests. [Runner](../backend/scripts/check_coach_e02.py) отключает dotenv,
paid, vault, network/socket, serial/Modbus; использует temporary DB/media/packs и emulator.
Scoped Ruff **PASS**, scoped diff whitespace **PASS**, preparation plan **PASS**.
Frontend не менялся и повторно не запускался; 543 — сообщённый предыдущий срез,
не новый результат этой задачи. Нет новых замеров звука или provider latency.

Старые U02 «нет snapshot», U03/U04/U06 «не начаты» в overview плана устарели.
Ниже inspected source/tests, входящие в текущий безопасный прогон:

| Этап | Актуальное offline evidence и ограничения |
|---|---|
| U00–U01 | [Replay corpus](../backend/app/tests/test_coach_u00_replay.py), [live identity/lifecycle](../backend/app/tests/test_coach_e10_live.py), [ранний отчёт](13-live-ai-coach-u00-u02-report.md); acoustic output не измеряется |
| U02 | [Workout-plan tests](../backend/app/tests/test_coach_u02_workout_plan.py): positive full-workout, repeated slugs/sides, missing migration fallback, edit/undo invalidation, both speech handoffs. [Snapshot](../backend/app/services/coach/workout_plan.py) — persisted declared-client plan, не physical telemetry; [optional migration](../backend/alembic/versions/20261017_0012_coach_workout_plans.py) не запускалась на рабочей БД |
| U03 | [Completion tests](../backend/app/tests/test_coach_u03_completion.py): local-first additional facts, duplicate guards, natural/interrupted FSM, duration/attempt budgets, bounded priority queue и terminal failures; frontend local package/audio availability всё ещё условие слышимости |
| U04 | [Context tests](../backend/app/tests/test_coach_u04_context.py): reviewed machine pilot, unknown/mismatch silence, explicit effort/discomfort ownership/TTL, opt-outs/revalidation; raw guides не объявлены clinically certified |
| U05 | [Memory report](13-live-ai-coach-u05-report.md), [tests](../backend/app/tests/test_coach_u05_memory.py): bounded heard/ACK memory, process-local reconnect/cache и enum-only opt-in cross-workout preferences, не achievements/биография |
| U06 | [Direction tests](../backend/app/tests/test_coach_u06_direction.py), [corpus](../backend/app/tests/fixtures/coach_u06_validation.json): speech actions, optional humor, acoustic interval union/local observations, bounded density/coalescing, quantity provenance/negation/partial guards; no recursive funny retry |

Исправлены только текущие статусы [improvement plan](13-live-ai-coach-improvement-plan.md)
и краткая ссылка основного трекера. Полная сверка historical reports/spec/decisions
оставлена отдельной последующей документационной задаче; этот отчёт заменяет их
устаревшие утверждения об отсутствии U02.4 или начале U03–U06, но не переписывает
исторические E-статусы и не повышает степень акустической приёмки.

Рабочие env/keys/DB/hardware не читались и не изменялись. Существовавшие до задачи
изменения в DB/watch logs/frontend и других файлах не откатывались.
