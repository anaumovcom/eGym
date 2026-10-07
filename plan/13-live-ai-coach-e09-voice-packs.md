# E09 — голосовые пакеты и подготовка по кнопке: реализация и проверки

Дата: 07.10.2026 (обновлено 08.10.2026). Статус: **код готов, offline-проверки PASS, платный путь проверен в E08; утверждение каталога, выбор голосов и генерация ждут пользователя.**

## Что сделано

| Пункт | Реализация |
|---|---|
| E09.1 (черновик) | Каталог `coach-pack-catalog-0.1` в [packs.py](../backend/app/services/coach/packs.py): count-1..30, countdown-1..3 и 21 фраза событий обязательны; count-31..100 опциональны. Тексты без цифр («Раз.», «Двадцать один.»), ID совпадают с [local-cues.ts](../frontend/src/features/coach/interpreter/local-cues.ts). `safety-stop`, `pain-stop` помечены `needs_approval`; `APPROVED_SAFETY_CATALOG = None` → в манифесте `approved: false`, браузер их не загружает и не играет. Старых audited записей нет (D09), совместимость проверять не с чем. |
| E09.2 | `plan()` и `GET /api/coach/packs/{slot}/plan`: статус каждой фразы (ready/missing/corrupt/unselected), отпечатки, `planFingerprint`, required/optional, байты, `estimate` по числу фраз и символов; `usd: null, priced: false`, пока цена не проверена. |
| E09.3 | Кнопка «Подготовить частые фразы» ([coach-voice-pack.tsx](../frontend/src/features/coach/ui/coach-voice-pack.tsx)) только загружает и декодирует готовое. Генерация — отдельный `POST /api/coach/packs/{slot}/jobs`: оператор, run-token, ledger `pack`/`test`, совпадение `planFingerprint`, clip IDs только из missing/corrupt, выбранный голос; ответ `dispatchAvailable: false`. |
| E09.4 | `PackJobRunner`: по одному запросу; reserve → dispatch → synthesize → проверка → атомарная запись → settle → receipt. Проверенный файл на диске повторно не оплачивается (восстановление после сбоя, повторная подготовка). Ошибка → `mark_unsettled`, пауза задачи, после 3 сбоев — failed. Отклонённый звук оплачен и учтён, но не сохраняется. Платный адаптер: `paid_adapter_unavailable` / нужен test ledger. |
| E09.5 | Артефакты `artifacts/<fingerprint>.wav` в приватном `COACH_PACK_ROOT` (не в публичном `media`). `verify_wav`: mono s16, длительность по реальным сэмплам, клиппинг, RMS −35…−10 dBFS, тишина по краям ≤0,5 с. Манифест публикуется только целиком, `current.json` заменяется атомарно (tmp + fsync + replace), старые версии остаются. Смена текста меняет отпечаток только этой фразы. |
| E09.6 | Раздача по whitelist: slot, версия `[0-9a-f]{16}`, clip ID из манифеста; `immutable` + ETag только для клипов, остальной Coach — `no-store`. [pack-client.ts](../frontend/src/features/coach/audio/pack-client.ts): строгий разбор манифеста, sha256 и размер, CacheStorage `coach-pack-v1`, decode с проверкой длительности, лимит 32 MB (required не вытесняются optional), QuotaExceeded → `failed/quota` без генерации, offline из кэша, удаление, атомарная замена версии, без подмены голоса. Live runtime берёт клипы из `coachPackClient.clipsFor(saved.voiceProfile)`. Голос фраз (Женский/Мужской) хранится в per-user `voiceProfile`. |

## Проверки

- Backend safe runner: **364 PASS** (E09: 12, E08: 19). Ruff PASS.
- Frontend coach и смежные: **296 PASS** (новые: pack-client 9, voice-pack UI 3, settings 1).
- TypeScript: 23 baseline-ошибки, в Coach 0; test-tsconfig audio — 0 новых.
- `vite build` PASS.
- ESLint не установлен в проекте (`npx` предлагает установку), не запускался.
- 0 paid-вызовов, 0 команд оборудования, миграций БД нет (используются существующие таблицы E04).

## Заблокировано

- **E09.1** — тексты, особенно safety, утверждает пользователь после прослушивания выбранного голоса.
- **E09.7** — ключ, цены и pilot уже есть (E08, 08.10.2026), `coach_pilot.py pack --slot female|male --voice X
  --adapter realtime|tts --cap-usd 0.30` готов; не хватает выбора голосов (E08.7). `COACH_PACK_VOICE_FEMALE/MALE` пусты.
- **E09.G** — зависит от E09.1 и E09.7. Свойства приёмки уже покрыты тестами: повторная подготовка не вызывает генерацию, partial не считается ready, при смене голоса другой голос не подставляется, quota не запускает регенерацию.

## Изменения после pilot (08.10.2026)

- Генерация передаёт провайдеру `max_output_tokens` из `clip_bounds` — Realtime сам остановит лишнюю речь, резерв доказуем.
- Realtime-адаптер в генераторе держит одну тёплую сессию на раунд (≈0,8 s handshake один раз) и закрывает её в конце.
- Выбор адаптера: TTS дословен, быстрее и дешевле (≈330 µUSD/s звука), но закрывается 06.01.2027 (готовые файлы
  останутся рабочими); Realtime (≈450 µUSD/s marin) проходит transcript gate — промах отклоняется и перегенерируется
  в следующем раунде.

## Следующие шаги

1. E08.7: выбрать голоса и адаптер.
2. Задать `COACH_PACK_VOICE_*`, сгенерировать required фразы в отдельном cap.
3. Прослушать count/start/safety/overlap, установить `APPROVED_SAFETY_CATALOG`, отметить E09.1/E09.7/E09.G.
