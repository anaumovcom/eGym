# Live-тренер: реальная проверка и исправления

Дата: **17.10.2026**. Дополнение к [срезу U00–U07](13-live-ai-coach-u00-u07-progress.md).
Основание: пользователь явно приоритизировал **live**, разрешил до **$10** на проверки.
Это разрешение paid-пилотов, **не пользовательское принятие нового звучания**.

## Дополнение: тишина в настоящей тренировке и приоритет речи

### Уточнение пользователя: речь обрывается при движении грифа — причина НЕ подтверждена

Предыдущее исправление burst ACK не доказывает устранение этого отдельного
сценария. Сквозной тест с реальными `CoachLiveRuntime`, `CoachNetworkClient`,
интерпретатором и микшером проводит уже звучащую речь через смену view и
`start_hold → moving → training`, включая локальные start/count-клипы: live stream
сохраняется; emergency его отменяет. Само движение в этом тесте обрыв не вызывает.
Нельзя объявлять причиной нестабильный run ID или изменение calibrationState
при каждом движении: такого факта в исходниках/телеметрии не установлено.

Обнаружен дефект диагностики: основной AI popover показывал отдельный preview
audio manager вместо тренировочного live manager. Теперь при наличии live audio
показывается его состояние. Terminal receipt микшера сохраняет точную причину
удаления, которую последующие volume/scope диагностические события уже не
затирают. Отмены started speech отражаются в network decisions/redacted report:
pause, plan change, safety/gate, mixer cancellation, provider termination и closure.
Пользовательские ID, текст речи и токены в экспорт не добавлены.

**521 frontend PASS / 21 files; Vite build, scoped diff/editor checks PASS.**
Аппаратные команды, restart, paid calls и изменения safety policy не выполнялись.
Текущая доступная browser-вкладка находится на выборе профиля; пользовательская
тренировка в ней недоступна. Запрошен отчёт сразу после обрыва или доступ к
соответствующей вкладке; пользователь сейчас недоступен. **Исправление исходного
movement-cutoff остаётся открытым до получения фактической причины отмены.**

### Обрыв начавшейся речи: burst PCM и подтверждения

После следующего сообщения пользователя об обрыве обнаружен воспроизводимый
механизм: frontend отправлял `playback_started` с обновлённой длительностью после
**каждого** PCM frame уже начавшегося потока. Frame содержит 100 ms аудио, но
провайдер может отдавать их значительно быстрее real time. Более 40 входящих
control messages за серверное секундное окно закрывают socket как `rate_limited`,
после чего frontend удаляет звучащий stream. Исходящие server PCM сами по себе
в этот лимит не входят — проблему создавали обратные ACK.

Исправление: немедленный ACK actual start, progress не чаще одного раза в 500 ms
по browser monotonic clock, обязательный ACK final duration и прежний terminal
completion/failure. Серверный лимит не повышен, PCM не задерживается, safety и
проверки owner/scope не ослаблены. `rate_limited` разрешён в redacted diagnostics.

Новый тест доставляет 60 PCM frames burst после actual start и имитирует
серверное закрытие после 40 control messages: теперь отправляются только start
и final ACK, вся реплика доигрывает и получает completed. Отдельный тест проверяет
progress interval и final вне интервала. **514 frontend PASS / 21 files,
Vite build и scoped diff/editor checks PASS.** Это воспроизведение механизма в
изолированном тесте, не захват причины обрыва в браузере пользователя; прослушивание
на устройстве ещё не подтверждено. Новых paid/hardware действий не было.

После сообщения пользователя об offline-only речи обнаружен отдельный integration
дефект: browser runtime run ID сравнивался с ID платёжного ledger-run. В реальной
тренировке это разные значения, поэтому live events отклонялись как `owner_mismatch`.
Предыдущий direct-call sandbox использовал одинаковые ID и не выявлял эту ошибку.

- Browser configure теперь передаёт `runtimeRunId`, захваченный для конкретного
   socket/user/run. Поздний `onopen` старого socket не связывается с новым пользователем.
- Authenticated backend хранит runtime scope binding отдельно от ledger ID;
   context/events проверяют runtime run и пользователя, а токен, lease, billing и memory
   по-прежнему привязаны к ledger. Исходные identity и PCM scope не переписываются.
- `configured.degraded` теперь boolean, `degradedReason` — отдельная причина;
   frontend понимает также старый string contract. Недоступный голос не маскируется
   статусом без причины и не заменяется browser speech synthesis.
- Обычные exercise effects (pop-up/down, form-error, success) имеют коэффициент
   **0.12**, во время реально звучащего coach — **0.012**. Для pop-up/down отдельно
   применяется множитель **0.3** от этого уровня (эффективно **0.036** / **0.0036**).
   Счёт и countdown имеют base gain **0.4**: даже начавшийся позже счёт остаётся
   тише live-комментария (gain **0.65** у комментария против **0.4** у счёта).
   Меняется громкость уже
   играющих и новых эффектов. Пользовательская громкость/ноль сохранены; ожидание
   PCM и stream gaps без звучащих источников не удерживают ducking. Приоритет
   освобождается при finish/cancel/mute/suspension/dispose. Coach headroom сохранён.

- Правки параметров упражнения больше не прерывают начатую фразу: browser и server
   разрешают started speech завершиться при новой planRevision. Подпись плана по-прежнему
   учитывает вес/повторы, pending speech отменяется без восстановления. Исходные
   identity/PCM/ACK версии не переписываются. Если звук уже начал играть между ticks,
   playback_started отправляется до нового context, чтобы сервер не отменил поток как
   pending. Safety, mute/text-only, pause, user/run и blocked gates сохранены.

Регрессии: отдельный TestClient WS с разными runtime/ledger ID и fake providers,
проверки чужого user/run, сохранения scope/identity/billing; frontend тесты binding,
устаревшего socket, degradation и audio priority. **1032 backend PASS / 5 skips,
576 frontend PASS / 25 files; Vite build, scoped Ruff, diff check PASS.** Диагностика
изменённых файлов чистая. Сохраняются известные jsdom media и Vite chunk warnings.

Этот этап не отправлял новых платных запросов, не мигрировал рабочую БД и не
перезапускал/командовал оборудование. Реальная слышимость из динамика во время
пользовательской тренировки всё ещё требует прослушивания; прежние server PCM
метрики не являются такой проверкой. Phase, safety, consent и budget gates сохранены.

## Что исправлено в рабочем коде

1. **Несколько live-поводов одного подхода действительно работают.**
   [Opportunity.key](../backend/app/services/coach/live.py) раньше совпадал для всех
   T21 одного set. Director разрешал следующий slot, но ledger запрещал его как
   `duplicate_attempt`. Теперь только T21 получает bounded hash code-selected topic;
   event ID не позволяет обойти dedup. Saved-result keys не изменены.
   [Интеграционные проверки](../backend/app/tests/test_coach_live_continuity.py)
   подтверждают два text/voice dispatch, completion ACK, replay/cooldown/density gates.
2. **Поддержка не зависит от наличия technique tip.** Нет подходящего tip, неизвестен
   вариант/режим или совет уже дослушан — короткий `active/support`, motivation-only,
   без tip/fact metadata. Не создаются непроверенные технические советы. Body/breathing
   claims по-прежнему отвергаются. Источники повторно сверяются перед PCM.
3. **Handshake Realtime перекрывается с подготовкой текста.** Только после admission,
   bounded task/lock, без `response.create`, session update или платной речи.
   Reserve → dispatch → generation не перенесены и не обходятся. Отмена чистит task,
   unclean stream по-прежнему закрывает socket против утечки старого ответа.
   Это узкая transport-оптимизация live, не полная реализация prepared-аудио U08.
4. **Меньше заведомо отклоняемых авторских ответов.**
   [Промпт 0.12](../backend/app/services/coach/prompts.py) ограничивает `usedFactIds`
   прямо в strict JSON-schema; уже исчерпанные heard facts не предлагаются автору,
   обязательные locked IDs остаются. Validator сохраняет собственную проверку.
   Вторая самостоятельная тёплая мотивация больше не автоматически diversity failure;
   третья одинаковая комбинация, повтор текста/opening/topic по-прежнему ограничены.
5. **Исправлен узкий false positive quantity parser.** Подтверждённое
   «Десять повторений — план подхода выполнен» не считается плановой величиной только
   из-за следующего слова «план». Исключение требует full outcome, использованный
   подтверждённый outcome и reps/seconds; partial, kg и подмена actual → target не проходят.
6. **Убраны копируемые моделью шутки-шаблоны из manner examples.** В реальных ранних
   прогонах модель постоянно возвращала пример про «рабочее место отдыха».
   Теперь передаётся описание манеры, а не одна готовая шутка.

Изменения не дают coach права управлять оборудованием, менять план или выводить
положение тела из грифа. Local count/safety, local-first completion и latest-start
simultaneous mixer сохранены. При недостатке новой информации silence остаётся нормой.

## Реальные проверки, не fake-провайдеры

[Live CLI](../backend/scripts/coach_pilot.py) обновлён под текущий production contract:
versioned context перед событиями, capture active → rest для saved set,
immutable identity в ACK, heartbeat lease каждые 5 s, отдельные event→PCM и voice→PCM.
Continuity scenario включает три разных support slot одного set и localCompletion.
Playback ACK **синтетический после записи PCM**, не доказательство звука из динамика.
Author output/transcript сохраняются только для synthetic sandbox inputs в ignored artifacts;
ключи, provider bodies и реальная пользовательская история туда не выводятся.

Модели: **gpt-6-luna / low → gpt-realtime-2.1-mini / ash**. Проверены актуальные
[официальные тарифы](https://developers.openai.com/api/docs/pricing) 17.10.2026:
Luna text $0.10/$0.01/$0.50; mini text $0.60/$0.06/$2.40,
audio $10/$0.30/$20 за миллион input/cached/output tokens соответственно.
Новые модели/цены не подставлялись молча.

| Срез / synthetic сценарий | Завершённая voice generation | Paid requests | Settled µUSD | Pending µUSD |
|---|---:|---:|---:|---:|
| Исходный legacy live, старый direct-call pilot | 4/7 | 12 | 15 285 | 0 |
| Версионированный контекст, диагностический прогон | 4/7 | 11 | 15 516 | 2 268 |
| После initial fixes, low | 7/7 | 14 | 20 127 | 0 |
| Эксперимент none + candidate | 6/7 | 13 | 23 334 | 0 |
| Warmup + continuity, промежуточный | 7/9 | 16 | 23 768 | 0 |
| После нового manner prompt, continuity | 8/9 | 17 | 25 287 | 0 |
| Контрольный baseline на промежуточном parser | 6/7 | 13 | 20 109 | 0 |
| **Финальный low / continuity** | **9/9** | **19** | **28 766** | **0** |
| Отдельное одинаковое voice A/B | **14/14** | **14** | **29 425** | **0** |

19 requests в финальном live вместо 18: один разрешённый существующим pipeline
summary retry; это не 19 реплик и не бесплатные неудачи. Все попытки входят в ledger.
Один ранний text timeout остаётся **unsettled reserve $0.002268**; не прощён и не обнулён.

**Общий sandbox ledger: 129 отправленных requests, settled $0.201617 + pending
$0.002268 = $0.203885 учтённой стоимости/обязательств.** Не $10 и не стоимость
реальной тренировки. Все команды использовали одну campaign DB вне репозитория,
per-run cap ≤$1.50, обычные sandbox operator limits $3/day/$5/month не повышались.
Рабочий пользовательский cap **$2/workout не менялся**. Реальная provider invoice
не читается; unsettled liability и округление до micro-USD указаны отдельно.

### Задержка: что действительно измерено

- До overlap cold voice-first-PCM: **1.64–2.18 s** в отдельных live-прогонах.
  При handshake во время текста первый live voice запрос: около **0.79–0.89 s**.
  Connection classification остаётся по actual send: preconnected socket → warm.
- В последнем continuity voice-first-PCM median **1.007 s**, но одна реплика **2.355 s**.
- **Event→первый server PCM median 3.598 s, nearest-rank p95 7.980 s, n=9**
  в последнем прогоне. Предыдущий n=8: median 2.871 s, max 4.442 s.
  Облако вариативно, text author/summary retry остаются основной задержкой.
  **Стабильные <1 s end-to-end не достигнуты и не заявляются.**
- Это не browser accepted PCM/start, не speaker latency и не статистически строгий
  benchmark. Прогоны малы и промпт менялся; причинного p95 улучшения по ним не доказать.
- `none` дал unreviewed_tip rejection на pilot tip; глобально оставлен **low**.
  Это предварительная проверка, не завершённое сравнение моделей U09.

## U07 A/B и прослушивание

[Delivery CLI](../backend/scripts/coach_delivery_pilot.py) теперь имеет `generate`,
требующий explicit confirmation и positive finite cap ≤$2 до ключа/settings/DB.
`plan` остаётся offline. Семь одинаковых текстов × A/B, balanced order, фиксированные
Ash/mini/energy/pace, без автоматических retries; count/safety исключены двумя guards.
**14/14 complete, 14/14 transcript match, pending 0; $0.029425**.
Целые пакеты не генерировались, принятый count/safety не тронут.

Локальная [страница прослушивания](../backend/coach_packs/pilot/u07-u7hwzu_x/listen.html)
открыта в браузере через **http://127.0.0.1:8787/listen.html**. Временный localhost-only
static server предоставляет только synthetic pilot artifacts; он не является backend,
не имеет provider/hardware API. Оба сборника декодируются в браузере (`readyState=4`,
23.8 s каждый, media error отсутствует). Автозапуск не включён.

**Нужен выбор пользователя A/B на слух.** `SITUATIONAL_DELIVERY_ACCEPTED=False`,
source deployment flag false, production `legacy`. Paid approval не является listening
approval. Candidate включался только в sandbox adapters. U07.5 выполнен; U07.6/U07.7
не закрыты. U08–U10 не объявлены готовыми; предгенерации U08 нет.

## Финальная проверка

| Проверка | Результат |
|---|---|
| Safe backend runner | **1015 passed, 5 skipped, 9 warnings, 41.22 s** |
| Targeted frontend: coach + runtime persistence + exercise-session + rest | **543 passed / 24 files, 14.02 s** |
| Scoped Ruff: coach, pilot scripts, новые regression tests | **PASS** |
| `git diff --check` | **PASS** |
| Vite | **PASS**, 1871 modules, 4.60 s; large-chunk warning сохраняется |
| TypeScript | **23 прежние ошибки / 7 non-coach files**, 0 coach errors; exit 2, не type-clean |
| Browser listening artifacts | Два WAV загружены и декодированы, человеческая/акустическая оценка pending |

Five replay skips, jsdom media-play warnings и существующие TypeScript ошибки не
выданы за исправленные. Основная рабочая БД не читалась/не мигрировалась, optional 0012
не применена; реальные workout-plan claims остаются fail-closed без baseline.
Проверены только allowlisted несекретные env-флаги: backend/frontend coach enabled true;
effective user settings/vault/рабочий audio device не проверены, env не изменён.
Watchers/оборудование не перезапускались, аппаратных команд не было. Пользовательские
staged/unstaged правки, DB и watch logs сохранены. Новый ключ не записывался в репозиторий.
