# E05 — локальный микшер и мини-диагностика

Дата: 07.10.2026. **Статус: готов в границах E05.** Новая реализация без
исходников и тестов back/back2. Русская речь, события счёта и реальные пакеты
ещё не подключены; проверенные клипы — явно TEST-тоны, не выбранный голос.

## Реализация

- [Shared AudioContext](../frontend/src/features/coach/audio/shared-audio-context.ts):
  lazy singleton, unlock непосредственно из пользовательского жеста; менеджер
  не закрывает/не приостанавливает общий контекст.
- [Микшер](../frontend/src/features/coach/audio/local-coach-audio-manager.ts):
  независимые BufferSource/GainNode в Map; последний наблюдаемый старт получает
  коэффициент 1, N старых — каждый 0.65/N. Reservation не приглушает звук.
  Рампы 50 мс attack / 150 мс restore с непрерывным anchoring; master headroom
  0.5 и compressor. Deadline ограничивает старт, не завершение начатой реплики.
- [Подготовка](../frontend/src/features/coach/audio/fixture-pack-storage.ts):
  whitelist, SHA256 до decode, проверка длительности/каналов/rate/samples,
  копирование и нормализация пика до 0.25 без усиления. LRU до 32 MiB;
  отменённые native decode не переиспользуются и учитываются в outstanding limit.
- [Runtime](../frontend/src/features/coach/audio/local-audio-runtime.ts):
  стабильный immutable snapshot для React, только сохранённые настройки,
  consent/feature/general sound/volume gates. Preview запрещён на всей
  незавершённой тренировке и при фактическом training/isometric/fixed_hold/moving.
  Safety latches снимаются только явными валидными значениями; отсутствие
  telemetry не снимает блокировку. Mute, hidden, safety, user/run/exercise и
  изменение конфигурации отменяют звук; обычная смена set/rest сохраняет started.
- [UI](../frontend/src/features/coach/ui/coach-mini-debug.tsx): AI перед моторами
  в normal/compact header; фактический LOCAL/CACHE только после старта,
  bounded timeline и local counters. Usage неизвестен, а не вымышленный ноль.
  Открытие read-only popover не делает запросов и не запускает звук.
  Popover anchored ниже всей строки защищённых controls: даже в узком режиме
  не закрывает STOP/моторы. Safety modal закрывает его и блокирует trigger,
  без обхода modal focus scope через portal.

Ресурсы менеджера: 16 pending, 8 sources, 1024 lifetime IDs без eviction;
клип до 60 s / 2,880,000 decoded bytes, фиксированный watchdog 125 s.
Cache cap не является глобальным cap всех копий буферов; число и размер
manager-owned копий ограничены отдельно. Native decode нельзя прервать,
но outstanding tasks остаются ограниченными четырьмя на preparer.

## Beep и дальнейшая интеграция

Существующий rep beep не изменён. E05 не создаёт автоматические голосовые
count-события, а preview невозможен внутри незавершённой тренировки: нового
двойного сигнала по умолчанию нет. Перед подключением count в E06 требуется
арбитраж одного rep-event между beep fallback и голосовым count; одного
shared context недостаточно для dedup. Legacy beep использует отдельный
контекст и не наследует Coach volume — это не новый голосовой fallback.

## Проверки и воспроизведение

- Frontend Coach + header + safety + exercise-session/workout-summary:
  **226 PASS** (14 suites, финальный повтор); audio из них **102 PASS**. После исправления
  popover повторены settings/mini/header/safety: **41 PASS**.
- Безопасный backend runner [check_coach_e02.py](../backend/scripts/check_coach_e02.py):
  **108 PASS**, временные DB/media, dotenv off, socket/Modbus connect запрещены.
- [Изолированный Playwright config](../frontend/playwright.e05.config.ts):
  **64 PASS**, повторно после защиты STOP. Запускает только loopback Vite 5179
  без API proxy, backend, app bootstrap и HMR; network audit отвергает любые
  внешние/API/store requests. Ноль hardware commands. Сервер после тестов закрыт.
- Matrix: widths 360/722/1024/1920/3840, scale 100/125/150%, normal/compact,
  отдельно rem scaling и desktop zoom emulation (не browser-menu zoom).
  Escape/focus return, modal focus containment, STOP bounds/actionability и
  motor hit-tests проверены **также при открытом popover**.
- Real AudioContext: trusted activation, checksum/decode, один и три клипа,
  cancellation mute/safety/stop, отсутствие автоматического replay.
- Native OfflineAudioContext: 72,000 samples @48 kHz на render; 1/2/3
  коррелированных тона. Native AudioParams и PCM, observer/end callbacks
  детерминированно bridged через suspend clock. Sample peaks:
  **0.1726856083 / 0.2849274278 / 0.2849274874**; finite samples, continuous
  restore; коэффициенты **[1] / [0.65,1] / [0.325,0.325,1]**.
  Native post-GainNode PCM соответствует envelopes, max error <0.0001.
- Harness TypeScript **PASS**; полный TypeScript — **23 прежних diagnostics**,
  ноль Coach. Отдельная Vite bundling **PASS**, прежнее large chunk warning.
  Scoped Ruff/editor/whitespace checks **PASS**.

Команды из frontend: `npm run test:run -- src/features/coach
src/shared/ui/layout/forma-shell.test.tsx src/shared/ui/overlays/safety-dialog.test.tsx
src/screens/exercise-session/exercise-session-screen.test.tsx
src/screens/workout-summary/workout-summary-screen.test.tsx`;
`npx playwright test --config playwright.e05.config.ts`;
`npx tsc --noEmit -p e05-harness/tsconfig.json --pretty false`.
Browser JSON/screenshots сохраняются локально в ignored test-results и
воспроизводятся тестами; они не являются production pack artifacts.

## Что не доказано / не выполнено

Физические динамики и пользовательское прослушивание не проверены;
inter-sample true peak и разборчивость русской речи не оценены.
Observed start означает пересечение audio clock и открытие gain после
revalidation, не подтверждение слышимости. Throttled observer может опустить
начало клипа; полностью истёкший silent buffer не получает ordinal/ducking.
Реальные voices — E08, packs — E09, count interpreter — E06, полный Coach — E10.
Paid/provider requests, migration пользовательской DB, security provisioning,
перезапуск backend/watch и команды физическому оборудованию не выполнялись.