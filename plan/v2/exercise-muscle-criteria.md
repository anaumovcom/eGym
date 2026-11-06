# V2: упражнения из сохранённых программ и канонические мышечные группы

> Обновление после интеграции: 32 линии уже входят в общий каталог **152 / 515**.
> Канонические tier ID имеют вид `exercise.<slug>:t1` … `:t4` (двоеточие).
> Ниже сохранён исторический read-only аудит метаданных. Сейчас код также использует
> проверенную консервативную карту `CURATED_PRIMARY` для 14 силовых упражнений;
> это отдельная явная разметка, а не угадывание роли по позиции legacy-массива.
> Группы без такой карты и без явных canonical primary остаются insufficient_data.
> Актуальная перебалансировка исходных 120 линий описана в [difficulty-rebalance.md](difficulty-rebalance.md).

## Источник и границы

Срез **2026-11-05**, эффективная SQLite БД из `get_settings().database_url`:
[backend/egym_local.db](../../backend/egym_local.db). Проверка выполнена через URI
`mode=ro`, `PRAGMA query_only=ON`; без bootstrap приложения, миграций, обновления
достижений, оборудования, сетевых запросов и платной генерации. Секреты не выводились.

В `workout_programs`: **11 записей, 3 активные, 8 удалённых**, один владелец
активных программ. У всех трёх активных программ `structure.builderGroups[].items`
пусты. Настоящие сохранённые планы находятся в **AppSetting**:
`training.builder.plan.<program_id>`, `value.groups[].items[]`. Для всех трёх
настроек проверено совпадение `user_id` с `owner_user_id` программы.

| ID программы | Ключ настройки | Позиций |
|---|---|---:|
| 2 | training.builder.plan.2 | 6 |
| workout-9 | training.builder.plan.workout-9 | 6 |
| workout-10 | training.builder.plan.workout-10 | 6 |

Итого **18 позиций, 17 уникальных упражнений**: румынская тяга присутствует в двух
программах. Не включены удалённые программы, оставшийся план `back-biceps`,
виртуальные шаблоны, произвольные упражнения из каталога или старой истории.
Список фиксирован в коде; правила при импорте **не читают БД**. Новая программа
не расширяет коллекцию автоматически: требуется новый проверенный append-only срез.

## Инвентарь и стабильные ID линий

Четыре порога каждой новой линии: **12 / 30 / 75 / 150 квалифицирующих дней**.
Ступени имеют обычные ID `<line-id>.t1` … `<line-id>.t4` после согласования каталога
родительской задачей. Все существующие ID и пороги сохранены этим расширением.

| ID линии | Программы | Тип сохранённого плана |
|---|---|---|
| exercise.butt-kick | 2 | timed / Cardio |
| exercise.cardio-knee-taps | workout-10 | timed / Cardio |
| exercise.cardio-quick-feet | workout-9 | timed / Cardio |
| exercise.smith-machine-bench-press | workout-9 | weighted |
| exercise.smith-machine-calf-raise | workout-9 | weighted |
| exercise.smith-machine-close-grip-bench-press | 2 | weighted |
| exercise.smith-machine-drag-curl | workout-10 | weighted |
| exercise.smith-machine-incline-bench-press | workout-10 | bodyweight (так сохранено) |
| exercise.smith-machine-inverted-row | workout-10 | weighted |
| exercise.smith-machine-narrow-stance-squat | 2 | weighted |
| exercise.smith-machine-overhand-row | workout-9 | weighted |
| exercise.smith-machine-romanian-deadlift | 2, workout-10 | weighted |
| exercise.smith-machine-seated-overhead-press | 2 | weighted |
| exercise.smith-machine-skullcrusher | workout-10 | weighted |
| exercise.smith-machine-squat | workout-9 | weighted |
| exercise.smith-machine-upright-row | workout-9 | weighted |
| exercise.underhand-pulldown | 2 | weighted |

Факты: `exercise_practice_days:<slug>`. Основание — реальные результаты по slug,
не наличие упражнения в плане и не число стартов/сохранений.

## Все канонические группы

Источник — `CANONICAL_MUSCLE_DEFINITIONS`, **15 групп**, без широких legacy-групп
`back`, `core`, `legs`, `shoulders` и без их пропорционального разбиения.

| ID линии | Группа |
|---|---|
| muscle.abdominals | Пресс |
| muscle.biceps | Бицепс |
| muscle.calves | Икры |
| muscle.chest | Грудь |
| muscle.forearms | Предплечья |
| muscle.front-shoulders | Передние дельты |
| muscle.glutes | Ягодицы |
| muscle.hamstrings | Бицепс бедра |
| muscle.lats | Широчайшие |
| muscle.obliques | Косые мышцы живота |
| muscle.quads | Квадрицепсы |
| muscle.rear-shoulders | Задние дельты |
| muscle.traps | Трапеции |
| muscle.traps-middle | Средняя трапеция |
| muscle.triceps | Трицепс |

Факты: `muscle_primary_days:<canonical-id>`. Принимаются только явные
`ExerciseSession.muscle_targets` с `role="primary"` и точным каноническим
`muscle_id`. Несколько явно основных групп могут получить день; повтор той же
группы в массиве не удваивает работу. `secondary`, `assisting`, `stabilizer`,
неизвестные/переведённые ID и цели без роли дают **ноль**, а не подразумеваемое
участие. Силовая работа по группе может происходить в любом реально сохранённом
упражнении с такой явной ролью; это не добавляет новых exercise-линий.

## Квалифицирующий день

- Минимум **2 полных рабочих подхода с положительными повторениями** либо
  **60 фактических секунд** полного рабочего выполнения на время за день.
  Один подход, один старт или одна тренировка сами по себе награды не дают.
- Подходы можно накопить в нескольких сессиях одного дня. Один день на scope
  считается максимум один раз. Первую ступень даёт только двенадцатый такой день;
  последовательные дни не требуются, повышение веса и работа до отказа не нужны.
- День определяется по сохранённому времени подхода (`created_at`, fallback
  `ExerciseSession.started_at`), граница **03:00 локального времени сервера**,
  через общий `training_day`. В SQLite timestamps интерпретируются как UTC.
  Это текущая серверная временная модель, не новая персональная IANA timezone.
- Только `WorkoutSession.status=completed|partial` с `finished_at`. Незавершённые
  и целиком aborted тренировки исключены. В финализированной partial тренировке
  полные подходы частичного/прерванного упражнения засчитываются.
- Нужны `completionStatus=completed`, известный рабочий `setType=work|working|failure`,
  положительный `planned_value`, `actual_value >= planned_value` и положительная
  фактическая величина. `failure` — историческая метка рабочего подхода, не требование.
  `warmup`, partial, skipped, неизвестный setType/completionStatus и нулевые значения
  исключены. Если числовое поле reps/duration есть, используется минимум его и
  actual_value; если нет — документированная единица actual_value.
- `sourceClass=simulated|simulation|test|emulator|synthetic`, явные simulation/isTest/
  isSimulated и hardwareAdapter=emulator исключаются. Отсутствие sourceClass не
  превращается в sensor_verified: это сохранённая legacy/manual практика.
  Исторические симуляции без каких-либо маркеров отличить от ручного ввода нельзя;
  им не приписывается доказанное датчиковое происхождение.
- Bodyweight не требует положительного веса. Секунды не превращаются в повторения.
  Кардио и растяжка могут давать exercise-practice, но **не muscle strength exposure**.
  Для исключения растяжки проверяется не только session.kind, но и каталог:
  `force=Stretch` или `equipment=Stretches`; для кардио — `equipment=Cardio`.
  В актуальном инвентаре три cardio-упражнения и **нет растяжки**.
- Односторонняя работа: только полная пара left+right с явным положительным целым
  `roundNumber`, в одной ExerciseSession и одном тренировочном дне. Пара = один
  рабочий подход. Несовпадающие/отсутствующие стороны или roundNumber не угадываются
  по ordinal. Для времени пара даёт **min(left_seconds, right_seconds)**: две стороны
  по 30 секунд дают 30 секунд сопоставимой практики, не 60. Нужны две такие пары
  либо одна пара по 60 секунд на каждую сторону. Это консервативный критерий наград,
  а не изменение UI-суммы фактически проведённого времени.
- ID результата дедуплицируется; повторный ordinal или повтор одной стороны одного
  раунда не создаёт дополнительные рабочие единицы. Владелец тренировки, упражнения
  и запрошенного профиля должен совпадать, связь workout/exercise проверяется.

## Подтверждённые пробелы метаданных

1. **17/17** JSON упражнений инвентаря не содержат явных primary/secondary ролей.
   **16/17** имеют лишь неупорядоченно интерпретируемый массив muscles;
   у `smith-machine-inverted-row` он **пуст**. Роли не назначались по первому элементу.
2. В истории **56 ExerciseSession** из этого инвентаря: **0** с каноническим primary,
   **3** с пустыми targets. Прочие primary muscle_id — русские display names.
   Текущий frontend создаёт primary по `index===0` в runtime persistence; эти записи
   **не подходят** для анатомического зачёта. Русские ID намеренно не транслируются.
   Следствие: muscle-линии доступны как правила, но этим legacy-записям прогресс
   не начисляется. Нужна отдельная проверенная разметка ролей и её producer, не догадки.
3. Сохранённый incline bench имеет loadType=bodyweight при оборудовании Smith-Machine.
   Запись не исправлялась, положительный вес не подразумевается.
4. Во всей истории **41 WorkoutSession**: completed=10, partial=4, in_progress=27.
   **103 SetResult**: completed/work=56, completed/warmup=24,
   completed/без setType=17, partial/без setType=3, partial/work=2,
   partial/warmup=1. **103/103 без sourceClass**. Неизвестные рабочие типы не
   восстанавливаются по позиции подхода; тренировочные и тестовые provenance не выдумываются.

## Изменения и проверка

- [training_scope.py](../../backend/app/services/achievements/training_scope.py):
  статический инвентарь, строгие роли/полнота/стороны/дневной зачёт.
- [rules.py](../../backend/app/services/achievements/rules.py): только append-only
  **17 exercise + 15 muscle = 32 линии, 128 ступеней** и две группы отображения.
  Старый блок правил не перебалансирован этим изменением.
- [facts.py](../../backend/app/services/achievements/facts.py): отдельное подключение
  scoped-counter, без изменения нормализации старых метрик.
- [test_achievement_training_scope.py](../../backend/app/tests/test_achievement_training_scope.py):
  offline fixtures, граничные условия, owner isolation и повторная выдача evaluator.

Генерированный каталог, media, content/generation, generator scripts и старые
progression-тесты **не изменены**. Согласование каталога с новыми RULES выполняет
родительская задача, с сохранением оплаченного контента и существующих grants.
Тест evaluator отключает только sync_definitions, чтобы не зависеть от этой
параллельной работы; настоящий подсчёт/пороги/уникальность grant исполняются.
Реальная БД и существующие выданные достижения не пересчитывались.

Проверено: **48 focused offline tests passed**, Ruff — **All checks passed**;
Pylance не сообщает ошибок в новых фактах/правилах. Тесты охватывают отдельно
каждую из 15 канонических групп. Полный каталог/старые progression-тесты здесь
не запускались: их согласование относится к родительской задаче.