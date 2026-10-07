# E07 — режиссёр, память и автор текста

**Дата:** 07.10.2026 (pilot 08.10.2026). **Статус:** E07.1–E07.7 готовы; E07.G пройден на синтетических случаях (см. «Paid pilot»).

## Что сделано

| Пункт | Реализация | Проверка |
|---|---|---|
| E07.1 | [triggers.py](../backend/app/services/coach/triggers.py): T01–T66, sources, groups, scopes, replaces/merge; unsupported источники дают `unsupported:<reason>` (T12, T18–T20, T22, T43, T44, T57, T60, T61), отсутствие данных — `no_source:<key>` | 66 registry cases |
| E07.2 | [director.py](../backend/app/services/coach/director.py): profiles quiet/companion/talkative, group cooldowns, LIVE/LOCAL gaps, slots по фактическому elapsed/длине отдыха, acoustic budget (set 35%, rest 45%), no_window с latency+margin, safety latch; `Coalescer` 250–500 мс | director/coalescer tests |
| E07.3 | [memory.py](../backend/app/services/coach/memory.py): attempted/started/completed, topics/openings/fingerprints, humor streak, motifs/callbacks только после completed, factMention guard | memory diversity tests |
| E07.4 | [prompts.py](../backend/app/services/coach/prompts.py) `coach-prompts-0.4`: P0/P1/P1-sharp/P2 дословно из документа (тест сверяет с текстом), P3 facts + `lockedFactIds`, P4 recent, notes как `data-not-instructions`, strict ordinary/locked-fact schemas (locked: механические `description` «не повторять clause»), hashes | verbatim + schema tests |
| E07.5 | [facts.py](../backend/app/services/coach/facts.py), [validation.py](../backend/app/services/coach/validation.py): saved-set facts, comparison policy (unavailable/limited/comparable), locked clauses T39/T40, числа словами, запрет amplitude/tempoLabel/repQuality/concentric/eccentric; tempo aggregate только при verified policy (сейчас выключено) | 20 comparison + number round-trips + validators |
| E07.6 | [luna.py](../backend/app/services/coach/luna.py): Responses adapter (`store:false`, strict json_schema, bounded timeout), reserve→dispatch→settle, cancel/timeout→unsettled, overflow→scope_changed, retry ровно один и только для summary; rejection → local/silence. [ledger.py](../backend/app/services/coach/ledger.py) dispatch по-прежнему fail-closed без flags+verified pricing+vault key | corpus 150+ случаев, author flows |

Новые настройки в [config.py](../backend/app/core/config.py) по умолчанию выключены:
`COACH_PAID_TEXT_ENABLED=false`, `COACH_TEXT_PRICING_VERIFIED=false`, модель `gpt-6-luna`, цены из плана (unverified).

## Проверки

- `backend/scripts/check_coach_e02.py` (temp DB, emulator, socket/Modbus запрещены): **333 PASS** (новые E07: 225).
- Тесты: [test_coach_e07_corpus.py](../backend/app/tests/test_coach_e07_corpus.py), [test_coach_e07_author.py](../backend/app/tests/test_coach_e07_author.py).
- Ruff по `app/services/coach`, тестам, `config.py`, `scripts`: PASS.
- 0 paid-запросов, 0 hardware-команд; Coach не импортирует motor/hardware API.

## Блокировки

- Нет. Production по-прежнему требует ключ в vault и оба env-флага (по умолчанию выключены).

## Paid pilot (E07.7/E07.G, 08.10.2026)

Запуск: `.venv/bin/python backend/scripts/coach_pilot.py text --confirm-paid --cap-usd 0.05 [--effort none|low|medium]`
(sandbox DB/vault в `~/.local/state/egym-coach-pilot`, отчёт в `backend/coach_packs/pilot/text-<ts>/`, gitignored).
12 синтетических случаев: full, partial, improved, equal, hold, partial-low, worse-partial, improved-big, intro, support, playful, injection.

| Прогон | Результат | Стоимость | Латентность |
|---|---|---|---|
| 1 (`coach-prompts-0.3`, effort default=medium) | 7 speech, 3 locked → `facts`, support → `comparison`, 2 silence | $0.0026 | 2.0–4.5 с |
| 2 (`0.4`, effort `low`) | **10/10 speech**, intro/injection → `insufficient_facts` (верно) | $0.0021 | 1.6–3.3 с |
| 3 (`0.4`, effort `none`) | 7 speech; partial → `provider_incomplete` (400 токенов без JSON), partial-low/worse-partial → выдуманная цель «из десяти» (поймано validator) | $0.0016 + 1 unsettled | 1.3–2.2 с |

Исправлено по итогам прогона 1:
- locked-fact: модель повторяла `lockedFactClause` в `framingText` и не включала все locked ID → в P3 добавлен `lockedFactIds`,
  в schema — описания; validator отбрасывает дословное эхо clause (иначе числа clause проверялись бы как новые).
- `tempo`: «держи свой темп» — побуждение, а не утверждение о темпе; добавлены lookbehind-исключения.
- topicKey pilot-случаев утекал в текст («пилот отдыхает») → нейтральные ключи.
- `COACH_TEXT_REASONING_EFFORT=low` (документированные значения gpt-6-luna: none/low/medium(default)/high/xhigh/max):
  `none` быстрее, но выдумывает факты; `medium` медленнее без выигрыша.

E07.G: выдуманных чисел/сравнений в принятых фразах 0; reject → silence без бесконечных retry; фразы разнообразны, но
часто повторяют «подход выполнен частично» / «хорошая работа» — далее покрывается memory (openings/fingerprints) в E10.
Старый [coach_text_pilot.py](../backend/scripts/coach_text_pilot.py) заменён `coach_pilot.py text`.
