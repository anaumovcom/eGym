# Реализация достижений Forma: 120 линий, 360 наград

Дата: 04.11.2026. Статус: реализуется.

Связанные документы: [продуктовый дизайн](18-achievements-and-rewards.md),
[визуальный конвейер](17-gpt-image-story-visuals.md), [полный каталог контента](19-achievements-content.md).

## 1. Зафиксированный объём

- 120 независимых линий; 12 смысловых групп по 10 линий.
- У каждой линии 3 ступени: «Начало», «Практика», «Мастерство». Всего 360 наград.
- Для каждой ступени заранее создаются уникальные название, фраза, изображение и озвучка.
- Тон: дерзко, смешно и поддерживающе, без мата, унижения, оценки тела и давления.
- Показ: отдельная `/achievements` и новые награды конкретной тренировки на `/workout-summary`.
- Никаких XP, магазина, лутбоксов, рейтингов, ежедневных обязательств и автопроигрывания.

## 2. Канонический контент

`backend/app/services/achievements/rules.py` — неизменяемые условия, IDs, метрики, пороги,
applicability и распределение редкости. `content/v1/catalog.json` — versioned editorial snapshot.
`plan/19-achievements-content.md` генерируется из JSON и не редактируется независимо.

Валидатор проверяет 120/360, уникальность IDs и фраз, неизменность правил, возрастание порогов,
редкости и дословное соответствие `phrase = audioText = strip(fishMarkup)`.

Редкость назначена заранее и не зависит от оплаты:

| Редкость | Количество ступеней | Цвет |
|---|---:|---|
| Обычная | 144 | Золото Forma |
| Редкая | 108 | Бирюза/сапфир |
| Эпичная | 72 | Фиолетовый/пурпур |
| Легендарная | 36 | Огненное золото/оранжевый |

## 3. Генерация контента

### GPT 6.1 Sol

`backend/scripts/generate_achievement_content.py`: Responses API, strict JSON schema, батчи по 5 линий.
Передаются только правила, никаких профилей, тренировочной истории, фото или заметок. После каждой
партии catalog и Markdown атомарно обновляются. Изменённые GPT правила отклоняются.

### GPT Image 2.5 Flare

`backend/scripts/generate_achievement_media.py`: Images API, 1024×1024. Сначала 3 low + 3 medium
с фактическим usage и визуальной проверкой. Основной профиль выбирается только после pilot.
Если выбранный профиль не помещается в cap — остановка с partial manifest, а не скрытое удешевление.

Стиль по `example-icons/`: глянцевая 3D-эмблема, массивная металлическая оправа, эмаль/стекло,
предмет-герой, насыщенный rim light, тёмно-синий фон, искры, читаемый силуэт на 96 px.
Без букв, чисел, логотипов, людей и пользовательских изображений. Варианты 256/512/1024 WebP.

### Fish Drama 3

Существующий `FishVoiceAdapter` и pre-tagged `Delivery`; PCM 24 kHz mono → WAV. Эмоции и паузы
соответствуют редкости и тексту. Используется утверждённый persona voice либо явный operator voice.
Проверяются WAV frames, длительность, громкость, тишина, края и clipping. Прослушиваются
представители групп/редкостей и acoustic outliers.

### Идемпотентность и расходы

`generation.py` хранит локальный durable journal попыток: reserve → sent → settle/unsettled.
Успешный checksum повторно не оплачивается. Неизвестный исход запрещает автоматический повтор.
Секреты берутся из environment/vault/env file, не записываются в журнал, MD, manifests или логи.

Жёсткие cap, подтверждённые пользователем: **OpenAI $36 суммарно на Sol + Image; Fish $15 на TTS**.
Fish тарифицируется по всем UTF-8 bytes, включая разметку: $10/M до 12.11.2026 17:00 UTC,
затем $50/M. Одновременно не более 3 image/TTS запросов. 403/quota/moderation не повторять автоматически.
Один retry 429/5xx разрешён только со свободным резервом. На cap — остановка и список missing IDs.

## 4. Backend

### Персистентность

Новые таблицы: definition snapshots, progress, grants, evidence, outbox, receipts.
Уникальность grant: `(user_id, definition_id, tier, scope_key)`; версия правила не создаёт дубль.
`source_workout_id` связывает награду с итогом конкретной тренировки. `earned_at` и `awarded_at` различны.

### Нормализация и evaluator

QS: положительные фактические reps или seconds, не skipped/test. QW: completed/partial/aborted с QS.
QD: 03:00 local, календарные операции; недели/месяцы не заменяются постоянными 86400 секундами.
Секунды не считаются повторениями. Per-side не удваивается без канонического basis.
Объём суммируется в грамм-повторениях; порог применяется до округления.

PR требует предыдущую сопоставимую сессию. PF требует baseline до старта и исходные цели.
Feedback оценивается только по факту наличия. Sensor-линии без доказанного provenance получают
`insufficient_data`, а не выдуманный прогресс. GPT/картинки/озвучка не участвуют в выдаче.

Финализация пишет outbox в той же транзакции. Bounded worker после commit пересчитывает зависимости;
GET не начисляет награды. Повторная финализация — no-op. Коррекция/удаление сохраняет валидные grants
или создаёт понятный `under_review/revoked` переход. Backfill — dry-run на копии, checkpoint, один итог.

### API

- `GET /api/achievements/overview?userId=...`
- `GET /api/achievements/catalog?userId=...&category=...&status=...&rarity=...&cursor=...`
- `GET /api/achievements/{definitionId}?userId=...`
- `GET /api/runtime/workouts/{id}/awards?userId=...`
- Старый `GET /api/achievements` остаётся адаптером четырёх legacy IDs.

Ответы содержат `computedThrough`, `isRebuilding`, прогресс и asset states. GET не вызывает
платные запросы и hardware. Детали evidence не содержат приватные заметки.

## 5. Frontend

`frontend/src/screens/achievements/`: обзор, фильтры, каталог 120 линий, дорожка I–III,
прогресс, детальная карточка, изображения и audio. Цвет редкости повторяется в рамке/glow/badge,
но смысл дублируется текстом. Lazy images, до 5 одновременных downloads. Audio `preload=none`,
один активный клип, только по клику, stop при смене профиля/уходе/STOP; громкость из настроек.

`WorkoutAwards` на итоговом экране: bounded poll awards endpoint, до 3 новых наград + «Ещё N».
Pending не утверждает «ничего не заработано»; ошибка не мешает итогу; ноль наград скрывает блок.
Эпизодные Coach badges не смешиваются с постоянными grants.

## 6. Проверка

1. Offline: 120/360, JSON↔MD, IDs, пороги, редкости, safe wording, text↔markup, dry-run без сети.
2. Media: Pillow decode, WebP sizes, WAV checksum/duration/loudness/silence/clipping, resume без оплаты.
3. Backend: QS/QW, partial/aborted/skipped/timed/bodyweight/per-side/legacy, 02:59/03:00, ISO weeks,
   exact volume, PR/PF insufficient data, owner isolation, двойная финализация, corrections, backfill.
4. Frontend: QueryClientProvider, фильтры, редкости, один audio/no autoplay, user switch, pending/error,
   workout awards, keyboard/focus/reduced motion, 360 px/1920×1080/3840×2160.
5. Команды: backend `D:\eGym\.venv\Scripts\python.exe -m pytest` из `backend`, Ruff/mypy изменённых модулей;
   frontend `npm run test:run`, `npm run build`, целевой Playwright.
6. Ручной сценарий: завершить тренировку → увидеть только её новые награды → прослушать →
   открыть линию → проверить прогресс следующей ступени. Offline не запускает генерацию.

## 7. Release gates

- Каталог проходит валидацию и редакционную проверку до media batch.
- Pilot images просмотрены; стоимость и доступность модели подтверждены фактическим response usage.
- Полная генерация останавливается на cap; missing resources явно перечислены.
- Отсутствие media не лишает награды. Ошибка evaluator не ломает сохранение тренировки.
- В отчёте раздельно указаны: готовые тексты, готовые изображения, готовые WAV, missing IDs,
  фактические расходы и остаток cap. Набор не называется полным при partial manifest.
