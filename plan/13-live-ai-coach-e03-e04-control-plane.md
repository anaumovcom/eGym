# E03–E04 — настройки, безопасный ключ и durable control plane

Дата: 07.10.2026. Реализовано с нуля, без исходников/тестов back/back2.
Статус и чекбоксы: [трекер реализации](13-live-ai-coach-implementation.md).

## 1. Что готово и что не запускалось

E03: личные настройки с consent/revision, отдельный draft/save, operator login,
encrypted vault, transient key input и безопасная metadata/auth проверка.
E04: persisted runs/attempts/receipts/jobs, SQLite atomic reservations, ownership
lease, reconciliation/recovery, caps/общие квоты и bounded synthetic job runner.

**Production inference по-прежнему недоступен.** Нет платного провайдера, рабочего
голоса, автоматического pack generation, live sockets или управления тренажёром
от Coach. Server API не принимает произвольные provider URLs/pricing/dispatch
инструкции от браузера. `paidDispatch: false`, capabilities implementation теперь
`control-plane`. Связь control plane с будущими audio/director adapters — E05–E10.

Не читались существующие env/API keys/private logs/пользовательская БД.
Существующее приложение/watch не запускалось и не перезапускалось.
Миграция проверялась только на временной БД. Vault/operator provisioning на этом
устройстве **не выполнялось**: оператор задаёт пароль и master-файл самостоятельно.
Платных inference requests и физических hardware commands: **0**.

## 2. E03 — персональные настройки

[Schemas](../backend/app/schemas/coach_control.py),
[preferences service](../backend/app/services/coach/preferences.py),
[таблицы](../backend/app/models/coach.py),
[frontend preferences](../frontend/src/features/coach/model/preferences.ts).

`CoachPreferences` расширяет schemaVersion 1: current consentVersion=1/null,
networkConsentVersion=1/null, historyConsent, local/hybrid/text-only, density/count,
style/humor, duringSets/duringRest, nullable voiceVolume, budgetUsd >0 и ≤2.
Voice остаётся nullable до A/B; edgyOptIn пока только false (расширенный UX — E11).
Legacy sound/voice flags не означают согласие или включение Coach.

Отдельная таблица `coach_preferences` с user PK и CAS revision. Сервер проверяет
существование user. PUT expectedRevision не совпал — 409, без молчаливой перезаписи.
GET/PUT имеют ETag revision и no-store. Неизвестный/непригодный legacy schema
читается как disabled defaults без согласий, сохраняя revision для исправления.
Настройки не разделяются между users и не содержат provider secret.

[Панель](../frontend/src/features/coach/ui/coach-settings-panel.tsx) встроена в
[Общие настройки](../frontend/src/screens/settings/system-settings-screen.tsx).
Coach сохраняется отдельно от общих настроек. Dirty draft не затёрт hydration;
явная reload заменяет его. Revision conflict сохраняет draft на экране.
User switch очищает draft; epoch и AbortController отклоняют старые ответы,
включая A→B→A. Новый пользователь никогда не видит данные прежнего.

Effective helper учитывает feature flag и **saved**, не несохранённый draft,
consent/network consent и общие soundEnabled/voiceHintsEnabled/volume. Volume
наследуется, если Coach override=null. Mute блокирует audio и не включает text-only.
Явный text-only независим от AudioContext и звуковых flags; paid readiness всегда false.
Этот helper — будущий admission primitive, не уже работающий audio controller.
Save/opt-out инвалидирует поколения server runs, отменяет unsent reservations;
sent превращаются в unsettled, без забывания оплаченных попыток.

## 3. E03 — operator auth и vault

[Security service](../backend/app/services/coach/security.py),
[operator panel](../frontend/src/features/coach/ui/coach-operator-panel.tsx),
[safe browser client](../frontend/src/features/coach/lib/settings-api.ts),
[request guard](../backend/app/services/coach/request_guard.py).

- Настоящий пароль оператора проверяется backend через scrypt; user/PIN/service
  acknowledgement не даёт operator rights.
- Хранится только scrypt hash в приватном внешнем файле. Session token случайный;
  в БД только SHA-256 digest, TTL 15 минут, HttpOnly SameSite=Strict cookie,
  Secure при HTTPS. Password rotation меняет auth version и инвалидирует cookies.
- Login rate limit 5/min/IP, bounded 1024 entries, ≤64 active sessions. Rate limit
  процессный; multi-worker deployment требует отдельного proxy rate limit.
- Provider key шифруется Fernet authenticated encryption; в БД только ciphertext,
  version/disabled/status. Master key в другом файле вне Git/repo/media, не в БД/browser.
  Требуются regular file, current-process owner, private permissions 0600 и no symlink.
- Хранилище не зависит от desktop keyring, пригодно для unattended Linux process.
  Нет подходящего файла/permissions/decryption — fail closed 503. Plaintext/env
  fallback отсутствует, delete key не включает скрытый env key.
- Save/replace/delete CAS credentialVersion. Key rotation инвалидирует generation
  всех runs; unsent отменяются, sent liability сохраняется. Поздний metadata check
  прежней версии не записывает результат в новую версию.
- API возвращает только configured/version/source/storageAvailable/checkStatus;
  ни ключ, ни префикс, ни token digest не возвращаются.
- Password/key только transient DOM state и один outgoing request; очищаются сразу
  при submit, закрытии панели, logout/user switch/unmount. Не Zustand persist,
  localStorage, URL, analytics, export, UI error или console.
- Coach request body ≤16 KiB. 422 полностью заменяется normalized response без
  Pydantic raw input; unexpected exceptions не дают debug traceback. Browser не
  читает error body и не сохраняет provider/network exception/cause.
- Mutations требуют разрешённый Origin; cross-site Fetch Metadata запрещён.
  HTTPS обязателен кроме настоящего loopback/local device. LAN HTTP запрещён.
  Forwarded/X-Forwarded-Proto headers намеренно запрещены: нельзя выдать plain
  transport за TLS. Для remote use нужен TLS на backend boundary; proxy должен
  удалять такие headers и использовать TLS до backend. Не выставлять insecure
  global forwarded-allow-ips ради обхода. Dev localhost Vite proxy поддерживается.

`metadata_check` отправляет только явный GET https://api.openai.com/v1/models,
timeout 5s, trust_env=false, redirects=false; body не читается/не возвращается.
Статусы: not_checked / auth_ok_models_not_verified / auth_failed / provider_unavailable.
Успешный models/auth check **не доказывает** доступ к конкретной inference model/voice.
Сохранение ключа не выполняет даже metadata check автоматически и не генерирует demo.
В тестах check adapter подменён fake; реальных provider requests не было.

### Первичная установка и backup

[Локальный setup script](../backend/scripts/setup_coach_security.py) запускается
оператором в терминале текущего virtualenv, не через чат. Он запрашивает новый
пароль через getpass (≥12 символов и confirmation), создаёт приватный каталог
в пользовательском data directory, master key 0600 (никогда не перезаписывает
существующий) и operator hash. Печатает **только пути** для окружения backend:
COACH_OPERATOR_HASH_FILE и COACH_MASTER_KEY_FILE. Provider key вводится позже
непосредственно в password input Общих настроек. Значения в чат не передавать.

Для service account файлы должны принадлежать именно backend UID. Перед restart
применить migration 0007 обычной процедурой backup/maintenance. Это не выполнялось
автоматически в данной задаче и не оправдывает запуск/сброс оборудования ради Coach.
При отсутствии setup UI показывает, что серверный доступ/хранилище не настроены.

Backup включает ciphertext DB и **отдельный защищённый backup master key**;
ciphertext без master не восстанавливается. Не класть их совместно в публичный
архив/repo/media. Provider key rotation выполняется через UI, master rotation
требует explicit decrypt/re-encrypt maintenance; автоматический master replacement
не реализован и запрещён. Operator password можно переустановить setup script;
старые sessions становятся непригодными.

Внешний reverse proxy/observability находится вне workspace: оператор обязан
отключить request/response body и Authorization/Cookie/X-Coach-Run-Token logging
для /api/coach. Приложение эти поля не логирует, но не может управлять чужим proxy.

## 4. E04 — run, ownership, reserves

[Ledger](../backend/app/services/coach/ledger.py),
[models](../backend/app/models/coach.py),
[migration 0007](../backend/alembic/versions/20261007_0007_coach_control_plane.py).

Persistent `coach_runs`, `coach_attempts`, `coach_receipts`,
`coach_response_receipts`, `coach_jobs`; никакого speech text/context archive.
Run ledger — workout/test/pack; test/pack create/job controls требуют operator.
Каждый run получает случайный access token, в DB только digest. Token возвращается
только при create, далее X-Coach-Run-Token (не URL); usage endpoint не раскрывает его.
Client token не operator credential и не доказательство identity выбранного user;
пользовательский kiosk profile не является общей системой user authentication.

Provisional run привязывается к реальному workout ID того же user, unique workout
binding, без сброса расходов/receipts. Связь с будущей browser workout — E10.
REST snapshot позволяет восстановить состояние по сохранённому run capability;
frontend end-to-end hydration этого run ещё не подключена.

Lease: ownerId + generation CAS, 15 секунд; обновление тем же owner — heartbeat,
другая вкладка до expiry получает owner_mismatch. Takeover/recover увеличивает
generation и отменяет unsent, но sent остаются unsettled. Для долгого browser run
нужен heartbeat чаще TTL (будущий клиент), не увеличение lease при каждом PCM.
Cancel/close/settings/key/cap changes не удаляют attempt/receipts/history.

SQLite BEGIN IMMEDIATE сериализует reserve/lease/cap между независимыми соединениями,
не только внутри процесса. Никакой DB transaction не держится через provider await.
Это реализация для текущего SQLite; другой DB dialect fail closed, не фиктивная
«универсальная» atomic guarantee. PostgreSQL locking требует отдельной реализации.

Деньги — integer micro-USD. Workout cap >0, ≤user budget ≤$2. Общие operator
COACH_OPERATOR_DAILY_USD / COACH_OPERATOR_MONTHLY_USD defaults $10/$100.
Каждый test/pack/workout reserve входит в общий cap. Старые unsettled liabilities
также удерживают quota после календарной границы; reconnect/model switch не refund.
Резерв освобождается только за **unsent** cancelled attempt или окончательно
сверяется с complete reported usage. Lower cap ниже spent допустим: available=0,
не обещание refund. Increase требует operator и явное confirmIncrease.

Attempt pricing/version/model и token bounds pinned, cached rate ≤input rate.
Worst-case reserve — uncached max input+max output, отдельно text/audio, ceiling
до micro-USD. Reserve запрещён, если verified/enforceableBounds не подтверждены
trusted adapter policy. Browser не может поставить эти flags через API.
Реальные adapters/цены ещё не подтверждены: ни одному реальному provider здесь
не обещан строгий $2 cap. Snapshot без пригодных attempts честно target-no-paid-adapter.
Будущий adapter обязан доказать input/output/audio bounds или оставаться blocked,
а не произвольно объявлять estimated target строгим ограничением.

Paid single-flight на run: одна reserved/sent попытка. Receipt key — hash canonical
opportunity + stage/ordinal; backend set ID alias проверяет user и не создаёт новую
opportunity. Одна дополнительная retry ordinal=1, только после terminal/unsettled/
cancelled первой, с новым reserve. Model switch создаёт новый attempt pricing,
не очищает старый ledger. Dedup/jobs idempotency **run-scoped**, не глобальный кеш.

Production dispatch намеренно возвращает paid_adapter_unavailable. Synthetic
dispatch разрешён только явным test_only внутренним runner в test ledger;
HTTP dispatch/settle/reserve endpoint отсутствуют. Будущие E07/E08 adapters
должны связать generation/credential/consent/safety проверки с transport cancel.

## 5. E04 — usage и recovery

Complete normalized usage требует explicit text input/output/audio input/output
totals; PartialUsage сохраняет неизвестные поля null. Никакого seconds→tokens.
Cached input/reasoning — subsets, не добавляются поверх input/output. Audio totals
заданы отдельно; adapter обязан нормализовать provider aggregate в непересекающиеся
категории. Непригодный/неполный provider report не становится выдуманным нулём.

Response IDs dedup в attempt; partial/unavailable receipt может быть дополнен
complete report с тем же ID после restart. Response sum и alternate aggregate
**не складываются**: выбирается консервативная authoritative basis по стоимости;
reported usage соответствует выбранной basis. Estimate округляется вверх.
При partial известна только нижняя оценка, полный reserve остаётся в pending.
Если actual usage нарушает bound/reserve, run blocked, дальнейшие dispatch
запрещены, liability не «возвращается». Это defect pricing/adapter для расследования.

sent→timeout/cancel/restart = unsettled с retained reserve, requests не исчезает.
Expired lease recovery отменяет только unsent, потом разрешает нового owner.
REST usage возвращает settled/pending/available, requests, stage/model/pricing,
completeness и nullable usage/cost. Записи не очищаются reset settings/debug/cancel.

## 6. E04 — bounded jobs

[TestJobRunner](../backend/app/services/coach/jobs.py): explicit synthetic adapter,
≤4 running test jobs/process, single-flight ledger, timeout ≤5s, provider cancellation
вне DB lock. Job ≤256 unique item IDs, ≤32 jobs/run; attempts ≤1024/run,
response receipts ≤256/attempt, ≤64 active runs. Job circuit failure count persisted,
3 failures блокируют job; auto retry отсутствует, explicit retry primitive максимум 1.
Timeout/cancel не делает unknown paid attempt бесплатным.

Submit idempotencyKey/fingerprint/items возвращает existing job или conflict;
pause/resume/cancel и progress сохраняются. Completed items не повторяются.
После crash sent/settled item без progress marker не генерируется слепо повторно:
duplicate attempt блокирует runner до reconciliation. Настоящие artifacts/atomic
pack publish и richer recovery UI — E09, не fabricated completion в E04.
HTTP resume только queued state, **не запускает background inference**; status
явно dispatchAvailable=false. Этот runner — infrastructure для будущих capped jobs,
не уже готовая платная подготовка голосов.

## 7. HTTP contract

Все новые routes в [Coach router](../backend/app/api/routes/coach.py).
Wire schemaVersion=1, camelCase, extra fields запрещены, errors normalized.
Secret paths требуют operator; mutations — Origin/TLS policy выше.

| Endpoint | Назначение |
|---|---|
| GET /api/coach/capabilities | implementation=control-plane, paidDispatch=false |
| GET/PUT /api/coach/users/{userId}/settings | prefs; PUT expectedRevision/settings, 409 conflict |
| GET/POST/DELETE /api/coach/operator/session | status / password login / logout |
| GET/PUT/DELETE /api/coach/credentials | status / key+expectedVersion / expectedVersion delete |
| POST /api/coach/credentials/check | явная auth/metadata check без inference |
| POST /api/coach/runs | userId/ledger/capUsd; runToken только create |
| GET /api/coach/runs/{id}/usage | run-token protected snapshot |
| POST /api/coach/runs/{id}/lease | ownerId/expectedGeneration, heartbeat/CAS |
| POST /api/coach/runs/{id}/bind | workoutSessionId, same user/unique binding |
| POST /api/coach/runs/{id}/cancel, /close, /recover | generation/recovery без reset денег |
| PUT /api/coach/runs/{id}/cap | capUsd/confirmIncrease; increase операторский |
| POST /api/coach/runs/{id}/jobs | operator+run token; idempotencyKey/fingerprint/items |
| GET /api/coach/runs/{id}/jobs/{jobId} | counts/state, dispatchAvailable=false |
| POST /api/coach/runs/{id}/jobs/{jobId}/action | operator+run token; pause/resume/cancel |

Нет provider inference, generation/voice preview или arbitrarily priced reserve API.
Browser client работает через same-origin /api proxy с credentials=include;
бездумный cross-origin key transport не поддерживается.

## 8. Проверки

Изоляция: [расширенный runner E02–E04](../backend/scripts/check_coach_e02.py),
dotenv disabled **до app import**, temporary DB/media/OpenAPI, emulator,
panel/keyboard off, socket и physical Modbus connect forbidden. Cryptography
установлена из package dependency; никаких секретов установщику не передавалось.

| Проверка 07.10.2026 | Итог |
|---|---|
| Backend Coach E02–E04 + runtime/users, 6 test files | 108 passed, 2 warnings; 38 новых E03/E04 cases |
| Frontend Coach + runtime/exercise/rest/summaries, 10 files | 120 passed; 65 новых E03 cases |
| Settings common integration, scoped name filter | 1 passed / 13 unrelated skipped |
| Scoped backend Ruff | PASS |
| TypeScript | 23 исходных diagnostics, 0 Coach; full npm build всё ещё blocked baseline |
| Отдельный Vite test-mode bundle во временную папку | PASS, прежний large-chunk warning |
| Migration upgrade→downgrade→upgrade | PASS, только temporary DB, не user DB |

Проверены encrypted-at-rest/no-secret-echo, origin/TLS/forwarded-header denial,
auth/logout/rate-limit, bad vault permissions/symlink/missing, prefs CAS/migration/
user isolation и frontend late hydration/dirty/conflict/DOM cleanup. Ledger tests
покрывают independent-connection contention, usage subsets/reconciliation/dedup,
unknown/partial enrichment после restart, retained sent liability, model/retry,
settings/key invalidation, cap/quota/overflow, lease recovery/bind/alias и job
idempotency/timeout/cancel/персистентный circuit. UI tested через jsdom/mocked fetch,
не human speaker test и не production deployment/security penetration test.

**E03.G и E04.G приняты по offline control-plane критериям. M1 закрыта технически.
Следующий этап — E05: локальное аудио, микшер и первый mini-debug.**