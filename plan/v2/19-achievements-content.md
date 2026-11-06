# Достижения Forma: 152 линий и 515 наград

Версия правил: `achievements-rules-1.3.0`. Версия контента: `achievements-content-1.1.0`.

Каждая линия имеет независимое условие и от 3 до 6 ступеней. Ступени не считаются отдельными линиями.
Фразы создаются заранее; условия и прогресс всегда вычисляет детерминированный backend.

Редкость: **обычная** — стальной синий (steel-blue), **редкая** — циан (cyan), **эпичная** — фиолетовый (violet), **легендарная** — янтарное золото (amber-gold).
Шестиугольные значки с чистым нижним краем: без нижних ромбов, корон и декоративных украшений.

## Начало пути

### `start.first_set`

**Правило:** Закрепить выполненные подходы многодневной рабочей практикой; первый подход сам по себе не награда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** подход. **Источник:** `available`.

#### 1. Рычаг старта

- **ID:** `start.first_set:t1`
- **Порог:** 1 подход
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Первый подход выполнен — ты включаешь режим «делаю». Лень пока ищет кнопку отмены.
- **Fish Drama 3:** `[playful] Первый подход выполнен — ты включаешь режим «делаю». Лень пока ищет кнопку отмены.`
- **Image prompt:** Premium glossy 3D achievement emblem, first tier of a cohesive mechanical workshop series. One clear hero object: a stout vintage toggle lever flipped upward, with a rounded amber glass grip and polished warm-gold metal base. Chunky beveled hexagonal metal frame, translucent honey-gold enamel inlays, restrained common-rarity warm-gold palette. Simple compact silhouette, a few tiny stars and delicate sparks around the lever. Saturated cinematic golden rim light, dark navy studio background, soft contact shadow, crisp readable design at 96px. Stylized product render, not photography. No letters, numerals, inscriptions, logos, people, bodies, or user photos.

#### 2. Ключ к практике

- **ID:** `start.first_set:t2`
- **Порог:** 5 подход
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** За твоими плечами уже 5 выполненных подходов. Ты копишь практику, а железо привыкает к знакомству.
- **Fish Drama 3:** `[confident] За твоими плечами уже <emphasis>5 выполненных подходов</emphasis>. Ты копишь практику, а железо привыкает к знакомству.`
- **Image prompt:** Premium glossy 3D achievement emblem, second tier of the same mechanical workshop series. One clear hero object: an oversized wind-up key floating diagonally, with a broad butterfly-shaped bow, a short square shaft, polished warm-gold edges, and translucent amber glass inset panels. Chunky beveled hexagonal metal frame matching the series, now double-ridged with richer honey-gold enamel details. Common-rarity warm-gold palette, slightly grander depth and stronger silhouette than the first tier. Tiny stars and a small spiral of sparks suggest gentle winding motion. Saturated cinematic golden rim light, dark navy studio background, soft contact shadow, readable at 96px. Stylized glossy product render. No letters, numerals, inscriptions, logos, people, bodies, or user photos.

#### 3. Маховик набирает ход

- **ID:** `start.first_set:t3`
- **Порог:** 20 подход
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 20 выполненных подходов — ты собрал целую коллекцию действий. Железо просит автограф.
- **Fish Drama 3:** `[excited] В твоей истории уже <emphasis>20 выполненных подходов</emphasis> — ты собрал целую коллекцию действий. Железо просит автограф.`
- **Image prompt:** Premium glossy 3D achievement emblem, third and most impressive tier of the same mechanical workshop series. One clear hero object: a substantial industrial flywheel with a thick polished warm-gold rim, broad sculptural spokes, a domed central hub, and translucent honey-amber glass sections between the spokes. Tilted three-quarter view with a subtle luminous arc suggesting accumulated momentum. Chunky beveled hexagonal metal frame matching the earlier tiers, now with deeper layered bevels and refined radial enamel accents. Keep the common-rarity warm-gold palette, without legendary flames. Tiny stars and clustered sparks accent the wheel, with generous negative space for readability at 96px. Saturated cinematic golden rim light, dark navy studio background, soft contact shadow, premium stylized 3D product render. No letters, numerals, inscriptions, logos, people, bodies, or user photos.

### `start.first_workout`

**Правило:** Закрепить сохранённые тренировки многодневной рабочей практикой; одна тренировка не даёт награду. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** тренировка. **Источник:** `available`.

#### 1. Старт записан

- **ID:** `start.first_workout:t1`
- **Порог:** 1 тренировка
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Первая тренировка с работой сохранена — ты перевёл «когда-нибудь» в прошедшее время!
- **Fish Drama 3:** `[excited] Первая тренировка с работой сохранена — ты перевёл «когда-нибудь» в прошедшее время!`
- **Image prompt:** Premium glossy 3D achievement emblem, opening tier of a collectible archive-themed series. One chunky golden floppy disk with a translucent honey-glass inset is the sole hero, tilted slightly forward inside a rounded-square beveled metal frame. Simple bold silhouette, polished warm gold surfaces, a small celebratory glint at the disk corner, tiny stars and sparks. Saturated amber cinematic rim light, dark navy studio background, soft contact shadow, readable at 96px. No letters, digits, writing, logos, people, bodies, or photographs.

#### 2. Сезон в архиве

- **ID:** `start.first_workout:t2`
- **Порог:** 3 тренировка
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты сохранил 3 тренировки, на которых поработал. В архиве уже мини-сериал, а не один пилот!
- **Fish Drama 3:** `[playful] Ты сохранил 3 тренировки, на которых поработал. В архиве уже мини-сериал, а не один пилот!`
- **Image prompt:** Premium glossy 3D achievement emblem, middle tier of the same warm-gold archive collection. One substantial golden film reel is the sole hero, with a short curling ribbon of translucent amber film emerging from it; the film has blank panels and no imagery. Rounded-square chunky beveled metal frame, richer layered construction than the opening tier, glossy honey enamel, tiny stars and sparks. Saturated golden cinematic rim light, dark navy studio background, soft contact shadow, readable at 96px. No letters, digits, writing, logos, people, bodies, or photographs.

#### 3. Архив с характером

- **ID:** `start.first_workout:t3`
- **Порог:** 10 тренировка
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В архиве уже 10 сохранённых тренировок с работой — ты собрал коллекцию, которой тесно в одной папке.
- **Fish Drama 3:** `[confident] В архиве уже 10 сохранённых тренировок с работой — ты собрал коллекцию, которой тесно в одной папке.`
- **Image prompt:** Premium glossy 3D achievement emblem, grand final tier of the warm-gold archive series. One miniature monumental vault is the sole hero, its thick circular door slightly ajar around a luminous honey-glass interior, no separate contents. The familiar rounded-square chunky beveled metal frame now has deep stepped layers and broad polished shoulders. Translucent amber enamel inlays, tiny stars and sparks, saturated warm-gold cinematic rim light, dark navy studio background, soft contact shadow, readable at 96px. No letters, digits, writing, logos, people, bodies, or photographs.

### `start.three_days`

**Правило:** Потренироваться в разных днях и постепенно познакомиться со своим ритмом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** тренировочный день. **Источник:** `available`.

#### 1. Кроссовки ловят ритм

- **ID:** `start.three_days:t1`
- **Порог:** 3 тренировочный день
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 3 разных тренировочных дня — кроссовки нащупали ритм и теперь просят барабанные палочки.
- **Fish Drama 3:** `[warm] У тебя уже <emphasis>3 разных тренировочных дня</emphasis> — кроссовки нащупали ритм и теперь просят барабанные палочки.`
- **Image prompt:** An animated sneaker drummer sits on an overturned gym chalk bucket, using its shoelaces as hands to tap a small practice drum. One lace holds a drumstick aloft while the sneaker leans forward, listening to its first beat.

#### 2. Железо на подыгровке

- **ID:** `start.three_days:t2`
- **Порог:** 7 тренировочный день
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 7 разных тренировочных дней. Ты задаёшь ритм, а железо подыгрывает — пока ложками.
- **Fish Drama 3:** `[confident] В твоей истории уже <emphasis>7 разных тренировочных дней</emphasis>. Ты задаёшь ритм, а железо подыгрывает — пока ложками.`
- **Image prompt:** The sneaker drummer commands a compact percussion kit assembled from hollow kettlebells and an upturned chalk bucket. Its shoelace hands swing two soup spoons while a hanging frying pan waits for the next cymbal crash.

#### 3. Лень купила билет

- **ID:** `start.three_days:t3`
- **Порог:** 14 тренировочный день
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** 14 разных тренировочных дней уже в твоей истории. Ты за ударной установкой, а лень в первом ряду — пришла послушать.
- **Fish Drama 3:** `[triumphant] 14 разных тренировочных дней уже в твоей истории. Ты за ударной установкой, а лень в первом ряду — [playful] <slow>пришла послушать.</slow>`
- **Image prompt:** The sneaker drummer leads a sprawling kettlebell percussion orchestra, lifting enormous soup ladles above its drum kit. In the front row, a sleepy pillow with tiny arms waves a blank concert ticket, sitting upright in delighted surprise.

### `start.two_weeks`

**Правило:** Оставить результаты в разных неделях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя. **Источник:** `available`.

#### 1. Первые папки истории

- **ID:** `start.two_weeks:t1`
- **Порог:** 2 неделя
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты оставил результаты в 2 разных неделях. Бобр-архивариус завёл две папки и уже шуршит с уважением.
- **Fish Drama 3:** `[warm] Ты оставил результаты в <emphasis>2 разных неделях</emphasis>. Бобр-архивариус завёл две папки и уже шуршит с уважением.`
- **Image prompt:** A small beaver archivist hugs two thick, unmarked workout folders beside a low wooden shelf. One folder has sprung open with loose sheets peeking out, and the beaver carefully steadies it with its broad tail.

#### 2. Полка держит историю

- **ID:** `start.two_weeks:t2`
- **Порог:** 4 неделя
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Результаты есть уже в 4 разных неделях — ты пополняешь свою историю. У бобра-архивариуса полка перешла на усиленный скрип.
- **Fish Drama 3:** `[confident] Результаты есть уже в <emphasis>4 разных неделях</emphasis> — ты пополняешь свою историю. У бобра-архивариуса полка перешла на усиленный скрип.`
- **Image prompt:** The beaver archivist slides a bulging blank folder into a handmade shelf with four occupied cubbies. Its broad tail braces the bowed bottom plank while a stray sheet curls over its nose, interrupting its serious inspection.

#### 3. Архив тяжёлой атлетики

- **ID:** `start.two_weeks:t3`
- **Порог:** 8 неделя
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В 8 разных неделях ты оставил результаты. Бобр-архивариус привёз погрузчик — папки перешли в тяжёлую атлетику.
- **Fish Drama 3:** `[triumphant] В 8 разных неделях ты оставил результаты. Бобр-архивариус привёз погрузчик — [playful] <slow>папки перешли в тяжёлую атлетику.</slow>`
- **Image prompt:** The beaver archivist drives a tiny forklift carrying a towering wooden cabinet with eight open cubbies, each stuffed with a bulging blank folder. Ahead waits an absurdly small office desk, barely wider than the beaver's tail.

### `start.exercise_return`

**Правило:** Возвращаться к одному упражнению в разные дни. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день с упражнением. **Источник:** `available`.

#### 1. Первый виток

- **ID:** `start.exercise_return:t1`
- **Порог:** 3 день с упражнением
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты вернулся к одному и тому же упражнению в 3 разных дня. Железо уже кивает при встрече.
- **Fish Drama 3:** `[warm] Ты вернулся к одному и тому же упражнению в 3 разных дня. Железо уже <emphasis>кивает при встрече.</emphasis>`
- **Image prompt:** A sneaker-wearing boomerang lands beside a squat dumbbell, its gym bag swinging from one tip. A curved chalk trail loops back toward the weight, and the boomerang leans in to greet its familiar training partner.

#### 2. Бумеранг с абонементом

- **ID:** `start.exercise_return:t2`
- **Порог:** 7 день с упражнением
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** За плечами уже 7 разных дней с одним и тем же упражнением. Ты здесь свой: бумеранг обзавёлся абонементом.
- **Fish Drama 3:** `[confident] За плечами уже 7 разных дней с одним и тем же упражнением. [playful] Ты здесь свой: бумеранг обзавёлся абонементом.`
- **Image prompt:** A sneaker-wearing boomerang confidently hooks its gym bag onto a squat dumbbell, one tip raised in greeting. Overlapping flight trails return to this familiar meeting spot; the dumbbell leans closer for a friendly fist bump.

#### 3. Тапочки для бумеранга

- **ID:** `start.exercise_return:t3`
- **Порог:** 15 день с упражнением
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 15 разных дней с одним и тем же упражнением. Ты возвращаешься — а железо выдаёт тапочки.
- **Fish Drama 3:** `[triumphant] В твоей истории уже 15 разных дней с одним и тем же упражнением. Ты возвращаешься — <slow>а железо выдаёт тапочки.</slow>`
- **Image prompt:** A boomerang lounges in a tiny armchair beside its familiar squat dumbbell, sneakers tucked underneath. The dumbbell presents slippers on a tea tray while the boomerang sets down its battered gym bag, welcomed home like an old friend.

### `start.first_plan`

**Правило:** Выполнить исходный план и собрать первую серию таких тренировок. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** тренировка по плану. **Источник:** `requires_plan`.

#### 1. План под крышкой

- **ID:** `start.first_plan:t1`
- **Порог:** 1 тренировка по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты впервые полностью выполнил исходный план тренировки. Шеф торжественно подаёт гантель под крышкой!
- **Fish Drama 3:** `[warm] Ты впервые полностью выполнил исходный план тренировки. Шеф торжественно подаёт <emphasis>гантель под крышкой!</emphasis>`
- **Image prompt:** A little robot chef lifts a serving dome to reveal a neatly placed dumbbell on a platter. Its other hand holds a recipe card covered in simple exercise pictograms, comparing the finished dish with the original recipe.

#### 2. Кухня плана работает

- **ID:** `start.first_plan:t2`
- **Порог:** 3 тренировка по плану
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 3 тренировки с полностью выполненным исходным планом. Ты держишься рецепта, а шеф жонглирует крышками.
- **Fish Drama 3:** `[confident] У тебя уже 3 тренировки с полностью выполненным исходным планом. [playful] Ты держишься рецепта, а шеф жонглирует крышками.`
- **Image prompt:** A little robot chef juggles serving domes above three finished platters, each carrying a neatly arranged dumbbell. The original pictogram recipe stands in a kitchen clip beside the robot, whose extra arm steadies the serving cart.

#### 3. Секрет большого колпака

- **ID:** `start.first_plan:t3`
- **Порог:** 10 тренировка по плану
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 10 тренировок с полностью выполненным исходным планом. Шеф снимает колпак — а под ним ещё один шеф!
- **Fish Drama 3:** `[triumphant] Ты накопил 10 тренировок с полностью выполненным исходным планом. Шеф снимает колпак — <slow>а под ним ещё один шеф!</slow>`
- **Image prompt:** A little robot chef bows beside a towering cart of dumbbell platters and lifts its tall hat. A miniature identical chef underneath bows too, proudly offering a tiny dumbbell; both robots hold matching copies of the original pictogram recipe.

### `start.first_feedback`

**Правило:** Сохранять самочувствие или дискомфорт после тренировки. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день с отметкой. **Источник:** `requires_reflection`.

#### 1. Ощущения в эфире

- **ID:** `start.first_feedback:t1`
- **Порог:** 1 день с отметкой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты впервые сохранил отметку о самочувствии или дискомфорте после тренировки — первый день в копилке. Ощущения получили право голоса.
- **Fish Drama 3:** `[warm]Ты впервые сохранил отметку о самочувствии или дискомфорте после тренировки — первый день в копилке. <soft>Ощущения получили право голоса.</soft>`
- **Image prompt:** A tiny listening robot with an oversized ear-shaped horn sits beside a rolled exercise mat, gently filing a speech-bubble-shaped card into a tray; its free hand welcomes the next report.

#### 2. Личная волна

- **ID:** `start.first_feedback:t2`
- **Порог:** 3 день с отметкой
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 3 дня с отметками о самочувствии или дискомфорте после тренировок. Ты даёшь ощущениям не разовый эфир, а собственную рубрику.
- **Fish Drama 3:** `[confident]У тебя уже 3 дня с отметками о самочувствии или дискомфорте после тренировок. [playful]Ты даёшь ощущениям не разовый эфир, а <emphasis>собственную рубрику</emphasis>.`
- **Image prompt:** A listening robot with an oversized ear-shaped horn hosts a miniature recording desk beside an exercise mat, arranging three speech-bubble-shaped cards in a fan while swiveling its horn toward a waiting dumbbell.

#### 3. Гантели просят слова

- **ID:** `start.first_feedback:t3`
- **Порог:** 10 день с отметкой
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты сохранил отметки о самочувствии или дискомфорте после тренировок в 10 разных дней. Теперь даже гантели стоят в очереди высказаться.
- **Fish Drama 3:** `[triumphant]Ты сохранил отметки о самочувствии или дискомфорте после тренировок в 10 разных дней. <slow>Теперь даже гантели</slow> стоят в очереди высказаться.`
- **Image prompt:** A listening robot with an oversized ear-shaped horn presides over an archive of speech-bubble cards; a queue of animated dumbbells leans toward its microphone, while the smallest dumbbell arrives dragging a giant speaking trumpet.

### `start.first_note`

**Правило:** Добавлять собственные заметки к тренировкам. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день с заметкой. **Источник:** `requires_reflection`.

#### 1. Записано тобой

- **ID:** `start.first_note:t1`
- **Порог:** 1 день с заметкой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Собственная заметка к тренировке сохранена: у тебя первый день с записью. Теперь ты не перекладываешь всю работу на память — у неё появился дублёр.
- **Fish Drama 3:** `[warm]Собственная заметка к тренировке сохранена: у тебя первый день с записью. Теперь ты не перекладываешь всю работу на память — <soft>у неё появился дублёр.</soft>`
- **Image prompt:** A stout pencil character with mitten-like hands kneels on an open exercise notebook resting across a workout bench, drawing a tiny dumbbell sketch; one curled page forms a little shelter over its head.

#### 2. Авторская версия

- **ID:** `start.first_note:t2`
- **Порог:** 3 день с заметкой
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 3 дня с собственными заметками к тренировкам. Ты собираешь свою версию событий — память больше не единственный свидетель.
- **Fish Drama 3:** `[confident]У тебя уже 3 дня с собственными заметками к тренировкам. [playful]Ты собираешь <emphasis>свою версию событий</emphasis> — память больше не единственный свидетель.`
- **Image prompt:** A stout pencil character with mitten-like hands unfolds three notebook pages into a standing panorama of exercise sketches, balancing on a workout bench and proudly presenting the newest page like a documentary director.

#### 3. Железо без спойлеров

- **ID:** `start.first_note:t3`
- **Порог:** 10 день с заметкой
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты добавлял собственные заметки к тренировкам в 10 разных дней. У железа теперь есть мемуары — и оно просит убрать спойлеры.
- **Fish Drama 3:** `[triumphant]Ты добавлял собственные заметки к тренировкам в 10 разных дней. У железа теперь есть мемуары — <slow>и оно просит убрать спойлеры.</slow>`
- **Image prompt:** A stout pencil character with mitten-like hands directs a towering pop-up notebook where a paper dumbbell takes a dramatic bow; real dumbbells crowd the footlights, one dragging an absurdly long illustrated manuscript.

### `start.first_program`

**Правило:** Завершать тренировки из сохранённых программ. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** программа. **Источник:** `available`.

#### 1. Бобр закрыл дело

- **ID:** `start.first_program:t1`
- **Порог:** 1 программа
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты завершил первую сохранённую программу. Бобр-архивариус закрыл папку — и впервые не стал её грызть.
- **Fish Drama 3:** `[warm] Ты завершил первую сохранённую программу. [playful] Бобр-архивариус закрыл папку — и впервые не стал её грызть.`
- **Image prompt:** A beaver archivist presses a thick workout binder shut with both paws, leaving tiny tooth dents along one corner. A rolled gym towel serves as a bookmark, and the beaver gives the intact cover a surprised sideways glance.

#### 2. Переправа из программ

- **ID:** `start.first_program:t2`
- **Порог:** 3 программа
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты завершил уже 3 сохранённые программы. Бобр-архивариус собрал из папок мост: теперь у прогресса есть собственная переправа.
- **Fish Drama 3:** `[confident] Ты завершил уже <emphasis>3 сохранённые программы</emphasis>. [playful] Бобр-архивариус собрал из папок мост: теперь у прогресса есть собственная переправа.`
- **Image prompt:** The beaver archivist crosses a narrow stream on a bridge made from three closed workout binders. He carries a rolled gym towel over one shoulder while loose sheets drift harmlessly beneath the improvised crossing.

#### 3. Плотина против волокиты

- **ID:** `start.first_program:t3`
- **Порог:** 8 программа
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** За всё время ты завершил 8 сохранённых программ. Бобр-архивариус возвёл плотину — бумажная волокита просит надувной круг.
- **Fish Drama 3:** `[triumphant] За всё время ты завершил <emphasis>8 сохранённых программ</emphasis>. Бобр-архивариус возвёл плотину — [pause] <slow>бумажная волокита просит надувной круг.</slow>`
- **Image prompt:** The beaver archivist braces a dam built from eight thick workout binders. On the upstream side, a flustered bundle of loose papers bobs inside an inflatable swim ring while the beaver calmly rests his paws on the top binder.

### `start.first_story`

**Правило:** Сохранять итоговые эпизоды тренировок. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** эпизод. **Источник:** `requires_story`.

#### 1. Первый эпизод в банке

- **ID:** `start.first_story:t1`
- **Порог:** 1 эпизод
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты сохранил первый итоговый эпизод тренировки. Осьминог-режиссёр убрал катушку в коробку: этот момент уже не уплывёт.
- **Fish Drama 3:** `[warm] Ты сохранил первый итоговый эпизод тренировки. [playful] Осьминог-режиссёр убрал катушку в коробку: этот момент уже не уплывёт.`
- **Image prompt:** An octopus film director lowers a single workout film reel into an open storage tin, using two tentacles to steady its edges. Another tentacle rescues a gym towel from the closing lid while his eyes follow the precious reel.

#### 2. Три серии в архиве

- **ID:** `start.first_story:t2`
- **Порог:** 3 эпизод
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты сохранил 3 итоговых эпизода тренировок. Осьминог-режиссёр разложил катушки по щупальцам: твоя тренировочная история уже не короткометражка.
- **Fish Drama 3:** `[confident] Ты сохранил <emphasis>3 итоговых эпизода тренировок</emphasis>. [playful] Осьминог-режиссёр разложил катушки по щупальцам: твоя тренировочная история уже не короткометражка.`
- **Image prompt:** The octopus film director raises three workout film reels in a proud fan above three open storage tins. His remaining tentacles unfold a tiny director's stool and drape a gym towel across its back, preparing for a longer screening.

#### 3. Щупальца заняты, кино идёт

- **ID:** `start.first_story:t3`
- **Порог:** 10 эпизод
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты сохранил 10 итоговых эпизодов тренировок. Осьминог-режиссёр держит восемь катушек, а ещё две везёт на тележке: кино победило анатомию.
- **Fish Drama 3:** `[triumphant] Ты сохранил <emphasis>10 итоговых эпизодов тренировок</emphasis>. Осьминог-режиссёр держит восемь катушек, а ещё две везёт на тележке: [pause] <slow>кино победило анатомию.</slow>`
- **Image prompt:** The octopus film director holds eight workout film reels, one per tentacle, while two more ride in a tiny cart. With every arm occupied, he pushes the cart handle with his forehead, wearing the expression of a very busy producer.

## Регулярность

### `rhythm.active_days`

**Правило:** Накопить дни с сохранённой работой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72, 144, 240, 400. Не подряд; без повышения нагрузки ради награды. **Единица:** тренировочный день. **Источник:** `available`.

#### 1. Архив на колёсах

- **ID:** `rhythm.active_days:t1`
- **Порог:** 5 тренировочный день
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 5 тренировочных дней с сохранённой работой. Первые записи на борту — архиву выдали погрузчик.
- **Fish Drama 3:** `[warm] У тебя уже 5 тренировочных дней с сохранённой работой. Первые записи на борту — архиву выдали <emphasis>погрузчик.</emphasis>`
- **Image prompt:** A squat forklift with oversized tires and expressive headlights gently lifts a small stack of closed workout logbooks. Its forks hover above a low pallet, with a loose bookmark peeking from the top book.

#### 2. Стеллаж занят

- **ID:** `rhythm.active_days:t2`
- **Порог:** 15 тренировочный день
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 15 тренировочных дней с сохранённой работой. Записи заняли стеллаж, а лень всё ещё ищет ключ от склада.
- **Fish Drama 3:** `[playful] Ты накопил 15 тренировочных дней с сохранённой работой. Записи заняли стеллаж, а лень всё ещё ищет ключ от склада.`
- **Image prompt:** The squat forklift slides a bundle of workout logbooks onto a sturdy shelving unit. More books wait on its rear cargo rack, while an oversized warehouse key dangles unnoticed from the shelf directly above its cab.

#### 3. Башня записей

- **ID:** `rhythm.active_days:t3`
- **Порог:** 30 тренировочный день
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории — 30 тренировочных дней с сохранённой работой. Погрузчик везёт башню записей и явно доволен карьерой.
- **Fish Drama 3:** `[confident] В твоей истории — <emphasis>30 тренировочных дней</emphasis> с сохранённой работой. Погрузчик везёт башню записей и явно доволен карьерой.`
- **Image prompt:** The squat forklift transports a tall tower of workout logbooks secured with broad cargo straps. Its expressive headlights glance upward at the topmost book, whose dangling bookmark nearly brushes the cab roof.

#### 4. Второй этаж истории

- **ID:** `rhythm.active_days:t4`
- **Порог:** 60 тренировочный день
- **Подтверждённая практика:** минимум 144 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** 60 тренировочных дней с сохранённой работой уже в твоём архиве. Погрузчик освоил второй этаж — без повышения голоса.
- **Fish Drama 3:** `[excited] 60 тренировочных дней с сохранённой работой уже в твоём архиве. Погрузчик освоил <emphasis>второй этаж</emphasis> — без повышения голоса.`
- **Image prompt:** The squat forklift stands on a raised freight platform, placing workout logbooks into an upper archive shelf. A tiny book elevator runs beside it, carrying a single oversized volume with a bookmark trailing like a scarf.

#### 5. Ангар личных хроник

- **ID:** `rhythm.active_days:t5`
- **Порог:** 120 тренировочный день
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 120 тренировочных дней с сохранённой работой. Для этой истории нужен целый ангар, а не папка «разное».
- **Fish Drama 3:** `[excited] Ты собрал <emphasis>120 тренировочных дней</emphasis> с сохранённой работой. Для этой истории нужен целый ангар, а не папка «разное».`
- **Image prompt:** The squat forklift nudges open enormous archive hangar doors with its padded forks. Inside, orderly banks of workout logbooks dwarf the vehicle; a comically small open folder waits beside the entrance, hopelessly outmatched.

#### 6. Зал с доставкой

- **ID:** `rhythm.active_days:t6`
- **Порог:** 240 тренировочный день
- **Подтверждённая практика:** минимум 400 разных дней; оба условия обязательны.
- **Ступень:** Большой путь
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя накопилось 240 тренировочных дней с сохранённой работой. Погрузчик поднял весь зал — гантели попросили подвезти.
- **Fish Drama 3:** `[triumphant] У тебя накопилось 240 тренировочных дней с сохранённой работой. [playful] Погрузчик поднял весь зал — <slow>гантели попросили подвезти.</slow>`
- **Image prompt:** The squat forklift lifts an entire miniature gym building on its forks. A cutaway wall reveals shelves of workout logbooks and a pair of dumbbells lounging on a bench, their tiny travel bags packed for the ride.

### `rhythm.active_weeks`

**Правило:** Оставить результаты в разных неделях, не обязательно подряд. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72, 144, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** активная неделя. **Источник:** `available`.

#### 1. Письма с маршрута

- **ID:** `rhythm.active_weeks:t1`
- **Порог:** 4 активная неделя
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Твои результаты есть в 4 разных неделях — им не нужно идти подряд. Улитка-почтальон бережно собирает твою историю.
- **Fish Drama 3:** `[warm] Твои результаты есть в 4 разных неделях — им <soft>не нужно идти подряд.</soft> Улитка-почтальон бережно собирает твою историю.`
- **Image prompt:** A cheerful postal snail balances a sealed envelope across its spiral shell, held by a little satchel strap. It reaches toward a small open mailbox while another envelope rests safely inside the satchel.

#### 2. Тележка для недель

- **ID:** `rhythm.active_weeks:t2`
- **Порог:** 12 активная неделя
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты оставил результаты в 12 разных неделях. Улитка заказала тележку: такая почта в карман уже не помещается.
- **Fish Drama 3:** `[playful] Ты оставил результаты в 12 разных неделях. Улитка заказала тележку: такая почта <emphasis>в карман уже не помещается.</emphasis>`
- **Image prompt:** The postal snail pulls a tiny two-wheeled cart piled with sealed envelopes. Its familiar satchel bulges over the spiral shell, and a particularly chunky letter rides in the cart like a passenger in a carriage.

#### 3. Сортировка приключений

- **ID:** `rhythm.active_weeks:t3`
- **Порог:** 26 активная неделя
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты сохранил результаты в 26 разных неделях — не обязательно подряд. У улитки теперь сортировочный стол, а конверты важничают.
- **Fish Drama 3:** `[confident] Ты сохранил результаты в <emphasis>26 разных неделях</emphasis> — не обязательно подряд. У улитки теперь сортировочный стол, а конверты важничают.`
- **Image prompt:** The postal snail carries a compact sorting desk across its spiral shell. Sealed envelopes stand neatly in wooden pigeonholes while one antenna nudges a large letter into place, like a conductor guiding an important guest.

#### 4. Почтамт в пути

- **ID:** `rhythm.active_weeks:t4`
- **Порог:** 52 активная неделя
- **Подтверждённая практика:** минимум 144 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 52 разные недели с результатами. Улитка открыла передвижной почтамт: паузы доставке не помеха.
- **Fish Drama 3:** `[excited] В твоей истории уже <emphasis>52 разные недели</emphasis> с результатами. Улитка открыла передвижной почтамт: паузы доставке не помеха.`
- **Image prompt:** The postal snail wears a miniature mobile post office over its spiral shell, complete with a folding awning and an outgoing mail tray. A neat stream of envelopes slides down a curved chute into the cart following behind.

#### 5. Доставка целого почтамта

- **ID:** `rhythm.active_weeks:t5`
- **Порог:** 104 активная неделя
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты оставил результаты в 104 разных неделях, не обязательно подряд. Улитка доставила весь почтамт — чтобы дважды не ползать.
- **Fish Drama 3:** `[triumphant] Ты оставил результаты в 104 разных неделях, не обязательно подряд. [playful] Улитка доставила весь почтамт — <slow>чтобы дважды не ползать.</slow>`
- **Image prompt:** The postal snail carries an entire miniature post office on its spiral shell, complete with bulging mail cubbies and a parcel chute. It has arrived beside a tiny mailbox, which leans backward under the absurd size of the delivery.

### `rhythm.week_streak`

**Правило:** Собрать серию недель с тренировками без требования заниматься ежедневно. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя подряд. **Источник:** `available`.

#### 1. Ритм тронулся с места

- **ID:** `rhythm.week_streak:t1`
- **Порог:** 3 неделя подряд
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 3 недели подряд с тренировками. Поезд тронулся — и билета на ежедневный марафон не требует.
- **Fish Drama 3:** `[warm] Ты собрал <emphasis>3 недели подряд</emphasis> с тренировками. Поезд тронулся — и билета на ежедневный марафон не требует.`
- **Image prompt:** A little locomotive with a dumbbell-shaped chimney pulls three wagons carrying bulging gym bags. Its front wheels have just left a folded station ramp, while a loose towel flutters from the last bag.

#### 2. Состав набирает ход

- **ID:** `rhythm.week_streak:t2`
- **Порог:** 6 неделя подряд
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 6 недель подряд с тренировками. Ритм набрал ход, а дни отдыха никто не высаживает.
- **Fish Drama 3:** `[confident] У тебя уже <emphasis>6 недель подряд</emphasis> с тренировками. Ритм набрал ход, а дни отдыха никто не высаживает.`
- **Image prompt:** A little locomotive with a dumbbell-shaped chimney hauls six gym-bag wagons across an accordion-folded bridge. Its front wheels crest the last fold while the trailing cars bend into a tight, orderly curve.

#### 3. Лень в багажном вагоне

- **ID:** `rhythm.week_streak:t3`
- **Порог:** 12 неделя подряд
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 12 недель подряд с тренировками! Лень больше не спорит с расписанием — она едет багажом.
- **Fish Drama 3:** `[triumphant] Ты собрал <emphasis>12 недель подряд</emphasis> с тренировками! Лень больше не спорит с расписанием — <slow>она едет багажом.</slow>`
- **Image prompt:** A little locomotive with a dumbbell-shaped chimney leads twelve gym-bag wagons in a sweeping spiral. A yawning sofa rides the luggage trolley at the tail, clutching a pillow while its slippers dangle over the edge.

### `rhythm.two_days_week`

**Правило:** Накопить недели, в каждой из которых было два тренировочных дня. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя с двумя днями. **Источник:** `available`.

#### 1. Дуэт на разогреве

- **ID:** `rhythm.two_days_week:t1`
- **Порог:** 2 неделя с двумя днями
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 2 недели с двумя тренировочными днями в каждой. У ритма теперь дуэт — и оба знают свою партию.
- **Fish Drama 3:** `[warm] Ты накопил <emphasis>2 недели с двумя тренировочными днями в каждой.</emphasis> У ритма теперь дуэт — и оба знают свою партию.`
- **Image prompt:** A squat kettlebell drummer and a tall kettlebell cymbalist share a tiny rehearsal platform made from an overturned cooking pot. One raises a wooden spoon above a saucepan while the other readies two small lids.

#### 2. Гастроли двух дней

- **ID:** `rhythm.two_days_week:t2`
- **Порог:** 6 неделя с двумя днями
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя накопилось 6 недель с двумя тренировочными днями в каждой. Этот дуэт уже не репетирует в шкафу — он даёт концерты.
- **Fish Drama 3:** `[confident] У тебя накопилось <emphasis>6 недель с двумя тренировочными днями в каждой.</emphasis> Этот дуэт уже не репетирует в шкафу — он даёт концерты.`
- **Image prompt:** A squat kettlebell drummer and a tall kettlebell cymbalist perform on a wheeled kitchen trolley holding six saucepans. Wooden spoons hover above the drum row, and the cymbalist balances on a rear wheel with lids spread wide.

#### 3. Кастрюли просят бис

- **ID:** `rhythm.two_days_week:t3`
- **Порог:** 12 неделя с двумя днями
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 12 недель с двумя тренировочными днями в каждой! Дуэт разыгрался так, что кастрюли сами записались в оркестр.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>12 недель с двумя тренировочными днями в каждой!</emphasis> Дуэт разыгрался так, что <slow>кастрюли сами записались в оркестр.</slow>`
- **Image prompt:** A squat kettlebell drummer and a tall kettlebell cymbalist command a towering kit of twelve cooking pots. The pots march into a semicircle on their own handles, offering up spoons, while a colander eagerly squeezes into the band.

### `rhythm.months`

**Правило:** Накопить календарные месяцы с минимум двумя тренировочными днями. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72, 144, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** активный месяц. **Источник:** `available`.

#### 1. Первые листы истории

- **ID:** `rhythm.months:t1`
- **Порог:** 3 активный месяц
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 3 календарных месяца минимум с двумя тренировочными днями в каждом. Календарь довольно шуршит: есть что подшить в историю!
- **Fish Drama 3:** `[warm] У тебя уже 3 календарных месяца минимум с двумя тренировочными днями в каждом. Календарь довольно шуршит: <soft>есть что подшить в историю!</soft>`
- **Image prompt:** A little walking desk calendar with a curled paper forelock carries three folded calendar leaves toward a tiny filing tray. Two dumbbell-shaped tabs peek from each leaf as the calendar steadies the wobbling pile with both arms.

#### 2. Архив набирает объём

- **ID:** `rhythm.months:t2`
- **Порог:** 6 активный месяц
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 6 календарных месяцев, в каждом — хотя бы два тренировочных дня. Это уже полка истории, а не случайный листочек.
- **Fish Drama 3:** `[playful] Ты собрал 6 календарных месяцев, в каждом — хотя бы два тренировочных дня. Это уже <emphasis>полка истории</emphasis>, а не случайный листочек.`
- **Image prompt:** A walking desk calendar with a curled paper forelock squeezes six plump paper folders onto a small archive shelf. Dumbbell-shaped tabs protrude from the folders, and one stubborn folder pushes the calendar backward.

#### 3. Летопись в движении

- **ID:** `rhythm.months:t3`
- **Порог:** 12 активный месяц
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** 12 календарных месяцев с минимум двумя тренировочными днями в каждом — ты ведёшь серьёзную летопись. Архив уже просит колёсики.
- **Fish Drama 3:** `[confident] 12 календарных месяцев с минимум двумя тренировочными днями в каждом — ты ведёшь <emphasis>серьёзную летопись</emphasis>. Архив уже просит колёсики.`
- **Image prompt:** A walking desk calendar with a curled paper forelock pushes an archive cart piled with folded calendar leaves. A runaway leaf curls around one wheel, and the calendar catches it with an improbably long paper arm.

#### 4. Хранилище больших дел

- **ID:** `rhythm.months:t4`
- **Порог:** 18 активный месяц
- **Подтверждённая практика:** минимум 144 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** За твоими плечами 18 календарных месяцев, в каждом — минимум два тренировочных дня. Календарь заказывает архив размером с ангар!
- **Fish Drama 3:** `[excited] За твоими плечами 18 календарных месяцев, в каждом — минимум два тренировочных дня. Календарь заказывает <emphasis>архив размером с ангар!</emphasis>`
- **Image prompt:** A walking desk calendar with a curled paper forelock operates a tiny archive crane. It swings a huge bundle of calendar leaves onto a towering shelf, while its feet brace against a rolling ladder.

#### 5. Время в приёмной

- **ID:** `rhythm.months:t5`
- **Порог:** 24 активный месяц
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 24 календарных месяца минимум с двумя тренировочными днями в каждом. А теперь… само время стоит к тебе за талончиком.
- **Fish Drama 3:** `[triumphant] Ты накопил 24 календарных месяца минимум с двумя тренировочными днями в каждом. <slow>А теперь…</slow> само время стоит к тебе за талончиком.`
- **Image prompt:** A walking desk calendar with a curled paper forelock sits behind an archive counter, holding a dumbbell-shaped stamp. A towering hourglass patiently offers it a tiny ticket; a mountain of filed calendar leaves rises behind the clerk.

### `rhythm.quarters`

**Правило:** Накопить кварталы, в каждом из которых было минимум шесть тренировочных дней. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72. Не подряд; без повышения нагрузки ради награды. **Единица:** квартал. **Источник:** `available`.

#### 1. Квартальный фундамент

- **ID:** `rhythm.quarters:t1`
- **Порог:** 2 квартал
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей копилке 2 квартала: в каждом было минимум шесть тренировочных дней. Бобр регулярности одобрительно стучит хвостом.
- **Fish Drama 3:** `[warm] В твоей копилке 2 квартала: в каждом было минимум шесть тренировочных дней. [playful] Бобр регулярности одобрительно стучит хвостом.`
- **Image prompt:** A bucktoothed beaver engineer with a broad paddle tail places a bundle of six short dumbbell beams across a narrow creek. A second bundle rests on the bank, and the beaver tests the little bridge with one cautious paw.

#### 2. Мост держит ритм

- **ID:** `rhythm.quarters:t2`
- **Порог:** 4 квартал
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 4 квартала, в каждом — хотя бы шесть тренировочных дней. Бобр-прораб строит мост с таким видом, будто реку заказал лично.
- **Fish Drama 3:** `[confident] У тебя уже 4 квартала, в каждом — хотя бы шесть тренировочных дней. Бобр-прораб строит мост с таким видом, будто <emphasis>реку заказал лично</emphasis>.`
- **Image prompt:** A bucktoothed beaver engineer with a broad paddle tail stands on scaffolding beside a growing dumbbell-beam bridge. It guides another bundled span into place with a rope, inspecting the river below with exaggerated authority.

#### 3. Утке тоже в зал

- **ID:** `rhythm.quarters:t3`
- **Порог:** 8 квартал
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 8 кварталов минимум с шестью тренировочными днями в каждом. Мост регулярности готов… даже резиновая утка идёт по нему в зал.
- **Fish Drama 3:** `[triumphant] Ты накопил 8 кварталов минимум с шестью тренировочными днями в каждом. <slow>Мост регулярности готов…</slow> даже резиновая утка идёт по нему в зал.`
- **Image prompt:** A bucktoothed beaver engineer with a broad paddle tail welcomes a gigantic rubber duck carrying a gym bag onto a grand dumbbell-beam bridge. The duck squeezes between the rails while the tiny beaver proudly gestures toward the far bank.

### `rhythm.return`

**Правило:** После перерыва от четырнадцати полных дней вернуться и продолжить тренировки. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72. Не подряд; без повышения нагрузки ради награды. **Единица:** день после возвращения. **Источник:** `available`.

#### 1. Сумка снова в деле

- **ID:** `rhythm.return:t1`
- **Порог:** 1 день после возвращения
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** После перерыва в 14 полных дней или дольше у тебя первый день с тренировкой. Сумка снова при деле!
- **Fish Drama 3:** `[warm] После перерыва в 14 полных дней или дольше у тебя <emphasis>первый день с тренировкой.</emphasis> Сумка снова при деле!`
- **Image prompt:** A squat gym duffel with sneaker feet and mitten hands steps through a half-open gym door, lifting its zipper flap in greeting. A dumbbell peeks around the doorframe, while a rolled exercise mat waits beside the bag.

#### 2. Возвращение с пропиской

- **ID:** `rhythm.return:t2`
- **Порог:** 3 день после возвращения
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 3 дня с тренировками после перерыва минимум в 14 полных дней. Сумка больше не гость — она знает, где лежит коврик.
- **Fish Drama 3:** `[confident] У тебя уже <emphasis>3 дня с тренировками</emphasis> после перерыва минимум в 14 полных дней. Сумка больше не гость — она знает, где лежит коврик.`
- **Image prompt:** The squat gym duffel plants its sneaker feet beside an open locker and pulls a full exercise mat from its own main compartment. Its mitten hands smooth the curled edge while a pair of dumbbells wait politely on either side.

#### 3. Багаж особой важности

- **ID:** `rhythm.return:t3`
- **Порог:** 7 день после возвращения
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 7 дней с тренировками после паузы минимум в 14 полных дней. Сумка теперь ездит на тележке: гантели нанялись носильщиками.
- **Fish Drama 3:** `[triumphant] Ты накопил 7 дней с тренировками после паузы минимум в 14 полных дней. Сумка теперь ездит на тележке: <slow>гантели нанялись носильщиками.</slow>`
- **Image prompt:** The squat gym duffel lounges on a luggage trolley, sneaker feet crossed and one mitten hand waving a towel. Two earnest dumbbell porters push it toward an open gym locker, while a third struggles behind with a tiny toiletry pouch.

### `rhythm.after_return`

**Правило:** После первого возвращения оставить результаты в нескольких неделях из следующих шести. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 20, 30. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя после возвращения. **Источник:** `available`.

#### 1. Ритм на рельсах

- **ID:** `rhythm.after_return:t1`
- **Порог:** 3 неделя после возвращения
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты оставил результаты в 3 из первых 6 недель после первого возвращения. У твоего ритма снова есть колёса.
- **Fish Drama 3:** `[warm] Ты оставил результаты в 3 из первых 6 недель после первого возвращения. У твоего ритма снова есть колёса.`
- **Image prompt:** A squat toy locomotive pulls six shallow wagons around a gentle curve. Three wagons carry neatly rolled exercise mats and three remain empty; the engine reaches back with a small mechanical arm to steady the nearest roll.

#### 2. Четыре попутные недели

- **ID:** `rhythm.after_return:t2`
- **Порог:** 4 неделя после возвращения
- **Подтверждённая практика:** минимум 20 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В 4 из первых 6 недель после первого возвращения ты оставил результаты. Паровозик ритма уже знает дорогу.
- **Fish Drama 3:** `[confident] В <emphasis>4 из первых 6 недель</emphasis> после первого возвращения ты оставил результаты. Паровозик ритма уже знает дорогу.`
- **Image prompt:** The squat toy locomotive guides six wagons through a sweeping rail junction, its mechanical arm holding the switch lever. Four wagons carry rolled mats beside upright dumbbells, while two empty wagons follow through the bend.

#### 3. Чай для гантелей

- **ID:** `rhythm.after_return:t3`
- **Порог:** 5 неделя после возвращения
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Твой счёт — 5 недель с результатами из первых 6 после первого возвращения. Паровозик ритма открыл вагон-ресторан: гантелям подан чай.
- **Fish Drama 3:** `[triumphant] Твой счёт — 5 недель с результатами из первых 6 после первого возвращения. Паровозик ритма открыл вагон-ресторан: <slow>гантелям подан чай.</slow>`
- **Image prompt:** The squat toy locomotive uses its mechanical arm to pour tea for dumbbell passengers seated in five open dining wagons; an empty sixth wagon trails behind. Its curved whistle holds a spare teacup, and rolled mats serve as seat cushions.

### `rhythm.three_days_week`

**Правило:** Накопить недели с тремя тренировочными днями, если такой ритм подходит пользователю. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя с тремя днями. **Источник:** `available`.

#### 1. Ритм на три удара

- **ID:** `rhythm.three_days_week:t1`
- **Порог:** 2 неделя с тремя днями
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 2 недели с тремя тренировочными днями в каждой. Личный ритм зазвучал — осьминог расчехляет барабаны.
- **Fish Drama 3:** `[warm] У тебя уже 2 недели с тремя тренировочными днями в каждой. [playful] Личный ритм зазвучал — осьминог расчехляет барабаны.`
- **Image prompt:** A small octopus unpacks three overturned gym buckets and raises a pair of padded drumsticks; two neatly folded towels sit beside the improvised drum kit, with another tentacle testing a bucket rim.

#### 2. Барабаны знают дирижёра

- **ID:** `rhythm.three_days_week:t2`
- **Порог:** 6 неделя с тремя днями
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 6 недель с тремя тренировочными днями в каждой. Барабаны уже не спрашивают, кто здесь задаёт ритм.
- **Fish Drama 3:** `[confident] Ты накопил <emphasis>6 недель</emphasis> с тремя тренировочными днями в каждой. [playful] Барабаны уже не спрашивают, кто здесь задаёт ритм.`
- **Image prompt:** An octopus conducts an improvised drum solo on three overturned gym buckets mounted on a sturdy equipment trolley; several tentacles swing padded mallets while another holds a baton above a stack of folded towels.

#### 3. Восемь рук аплодисментов

- **ID:** `rhythm.three_days_week:t3`
- **Порог:** 12 неделя с тремя днями
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 12 недель с тремя тренировочными днями в каждой. Осьминог устроил овацию: шесть рук хлопают, две держат чай.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>12 недель</emphasis> с тремя тренировочными днями в каждой. [playful] Осьминог устроил овацию: шесть рук хлопают, <slow>две держат чай.</slow>`
- **Image prompt:** A jubilant octopus rises behind three enormous overturned gym buckets, clapping with six tentacles while the remaining two hold a teacup and saucer; padded drumsticks rest across the rims after the grand performance.

### `rhythm.year_weeks`

**Правило:** Удерживать собственный ритм в течение длинной серии недель. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 32, 72. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя подряд. **Источник:** `available`.

#### 1. Большой путь своим ходом

- **ID:** `rhythm.year_weeks:t1`
- **Порог:** 26 неделя подряд
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 26 недель подряд в собственном тренировочном ритме. Черепаха-путешественница уважительно снимает походную панаму.
- **Fish Drama 3:** `[warm] У тебя <emphasis>26 недель подряд</emphasis> в собственном тренировочном ритме. [playful] Черепаха-путешественница уважительно снимает походную панаму.`
- **Image prompt:** A traveling tortoise lifts its floppy hiking hat beside a long arched footbridge; a compact backpack and brass compass rest on its shell, while the winding path behind crosses from spring shoots into summer grass.

#### 2. Свой темп, дальний маршрут

- **ID:** `rhythm.year_weeks:t2`
- **Порог:** 39 неделя подряд
- **Подтверждённая практика:** минимум 32 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** 39 недель подряд ты держишь собственный тренировочный ритм. Дистанция солидная, а командует темпом не календарь, а ты.
- **Fish Drama 3:** `[confident] <emphasis>39 недель подряд</emphasis> ты держишь собственный тренировочный ритм. Дистанция солидная, а командует темпом не календарь, <emphasis>а ты.</emphasis>`
- **Image prompt:** A traveling tortoise in a floppy hiking hat confidently unfolds a large map on its backpack; its brass compass points along a rising spiral footpath, with spring shoots and summer grass below and autumn leaves ahead.

#### 3. Навигатор для года

- **ID:** `rhythm.year_weeks:t3`
- **Порог:** 52 неделя подряд
- **Подтверждённая практика:** минимум 72 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты держишь собственный тренировочный ритм 52 недели подряд. Год сделал круг и теперь просит у тебя навигатор.
- **Fish Drama 3:** `[triumphant] Ты держишь собственный тренировочный ритм <emphasis>52 недели подряд.</emphasis> [playful] Год сделал круг и теперь просит у тебя <slow>навигатор.</slow>`
- **Image prompt:** A traveling tortoise opens a tiny front door built into its own shell, revealing slippers beside its backpack; still wearing its hiking hat, it holds a compass above a complete looping trail through four miniature seasons.

## Сила практики

### `practice.workouts`

**Правило:** Накопить сохранённые тренировки с фактической работой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90, 160, 260, 420. Не подряд; без повышения нагрузки ради награды. **Единица:** тренировка. **Источник:** `available`.

#### 1. Архив на колёсах

- **ID:** `practice.workouts:t1`
- **Порог:** 5 тренировка
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Первые 5 тренировок с фактической работой ты уже сохранил. Архив открывается не обещаниями, а делом.
- **Fish Drama 3:** `[warm]Первые 5 тренировок с фактической работой ты уже сохранил. Архив открывается не обещаниями, а <emphasis>делом</emphasis>.`
- **Image prompt:** A small orange forklift with expressive headlight eyes gently places a dumbbell-shaped block onto a short row of matching blocks. Its forks hover beside the neat little foundation, with an empty pallet waiting nearby.

#### 2. Поддон практики

- **ID:** `practice.workouts:t2`
- **Порог:** 20 тренировка
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты сохранил 20 тренировок с фактической работой — для этой истории уже нужен поддон, а не папочка.
- **Fish Drama 3:** `[playful]Ты сохранил 20 тренировок с фактической работой — для этой истории уже нужен <emphasis>поддон</emphasis>, а не папочка.`
- **Image prompt:** A small orange forklift with expressive headlight eyes balances a full pallet of dumbbell-shaped blocks. One block nestles neatly into the top of the stack, while a comically undersized empty filing tray sits beside the wheels.

#### 3. Стеллаж с характером

- **ID:** `practice.workouts:t3`
- **Порог:** 50 тренировка
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** 50 тренировок с фактической работой ты уже сохранил — полка держится, но уважительно поскрипывает.
- **Fish Drama 3:** `[confident]50 тренировок с фактической работой ты уже сохранил — полка держится, но <emphasis>уважительно</emphasis> поскрипывает.`
- **Image prompt:** A small orange forklift with expressive headlight eyes slots a pallet of dumbbell-shaped blocks into a tall storage rack. The shelves bow slightly beneath the orderly collection, while the forklift tilts its mast like a proud librarian.

#### 4. Склад больших дел

- **ID:** `practice.workouts:t4`
- **Порог:** 100 тренировка
- **Подтверждённая практика:** минимум 160 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории накопилось 100 сохранённых тренировок с фактической работой. Это уже склад дела, а не коробка с намерениями.
- **Fish Drama 3:** `[excited]В твоей истории накопилось 100 сохранённых тренировок с фактической работой. Это уже <emphasis>склад дела</emphasis>, а не коробка с намерениями.`
- **Image prompt:** A small orange forklift with expressive headlight eyes pushes open the broad doors of a warehouse packed with dumbbell-shaped blocks. Its fork tips hold the doors apart, revealing a deep central aisle between orderly storage racks.

#### 5. Тесно даже стенам

- **ID:** `practice.workouts:t5`
- **Порог:** 200 тренировка
- **Подтверждённая практика:** минимум 260 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Обычная (`common`)
- **Фраза:** 200 тренировок с фактической работой сохранены в твоей истории — архив занял целый ангар и деликатно интересуется соседним.
- **Fish Drama 3:** `[excited]200 тренировок с фактической работой сохранены в твоей истории — архив занял целый ангар и <emphasis>деликатно интересуется соседним</emphasis>.`
- **Image prompt:** A small orange forklift with expressive headlight eyes parks between a packed warehouse and a newly unfolded annex. Dumbbell-shaped blocks fill both structures, and its telescoping loading ramp reaches toward a tiny empty shed.

#### 6. Здание поехало

- **ID:** `practice.workouts:t6`
- **Порог:** 400 тренировка
- **Подтверждённая практика:** минимум 420 разных дней; оба условия обязательны.
- **Ступень:** Большой путь
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 400 сохранённых тренировок с фактической работой — архив разросся так, что погрузчик теперь возит само здание.
- **Fish Drama 3:** `[triumphant]У тебя 400 сохранённых тренировок с фактической работой — архив разросся так, что <slow>погрузчик теперь возит само здание</slow>.`
- **Image prompt:** A small orange forklift with expressive headlight eyes lifts an entire warehouse on its forks. Racks of dumbbell-shaped blocks show through the doorway, its tiny wheels peek beneath the building, and the loading ramp doubles as a driveway.

### `practice.sets`

**Правило:** Накопить выполненные подходы, включая разминочные и частичные. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** подход. **Источник:** `available`.

#### 1. Стопка без кастинга

- **ID:** `practice.sets:t1`
- **Порог:** 10 подход
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил 10 подходов — разминочные и частичные тоже в счёте. В этой стопке каждому есть место.
- **Fish Drama 3:** `[warm]Ты выполнил 10 подходов — разминочные и частичные тоже в счёте. В этой стопке <soft>каждому есть место</soft>.`
- **Image prompt:** A little octopus cook in a plain apron carefully stacks pancakes on a broad plate. Round pancakes and smaller crescent-shaped pancakes share the pile, while separate tentacles steady the plate and tuck each piece into place.

#### 2. Башня из дела

- **ID:** `practice.sets:t2`
- **Порог:** 50 подход
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 50 выполненных подходов, включая разминочные и частичные. Стопка подросла — повар переехал со сковородой на лестницу.
- **Fish Drama 3:** `[confident]В твоей истории уже 50 выполненных подходов, включая разминочные и частичные. Стопка подросла — повар переехал со сковородой <emphasis>на лестницу</emphasis>.`
- **Image prompt:** A little octopus cook in a plain apron climbs a stepladder beside a tall pancake tower. Several tentacles grip the steps while another holds a frying pan level with the summit; round and crescent-shaped pancakes form sturdy alternating layers.

#### 3. Стопка вышла в шефы

- **ID:** `practice.sets:t3`
- **Порог:** 150 подход
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 150 выполненных подходов, включая разминочные и частичные. Стопка доросла до шефа — теперь сама подаёт тебе завтрак.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 выполненных подходов, включая разминочные и частичные. Стопка доросла до шефа — <slow>теперь сама подаёт тебе завтрак</slow>.`
- **Image prompt:** A little octopus cook in a plain apron sits at a breakfast table, tentacles raised in delighted surprise. A towering stack of round and crescent-shaped pancakes has sprouted spatula arms and politely serves the cook a pancake on a plate.

### `practice.reps`

**Правило:** Накопить повторения в подходах повторного типа. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90, 160, 260, 420. Не подряд; без повышения нагрузки ради награды. **Единица:** повторение. **Источник:** `available`.

#### 1. Первые рельсы практики

- **ID:** `practice.reps:t1`
- **Порог:** 100 повторение
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 100 повторений в подходах — первые рельсы практики уже уложены. Маленькая тележка довольно скрипнула.
- **Fish Drama 3:** `[warm] Ты накопил 100 повторений в подходах — первые рельсы практики уже уложены. Маленькая тележка <soft>довольно скрипнула.</soft>`
- **Image prompt:** A small track-building robot with one square eye and clamp hands connects two short rail sections. An empty miniature cart waits beside a neat pile of track pieces, with the robot leaning forward to align the joint.

#### 2. Поворот с пассажиром

- **ID:** `practice.reps:t2`
- **Порог:** 500 повторение
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 500 повторений в подходах. Практика прошла первый поворот и даже не потеряла утку-пассажира.
- **Fish Drama 3:** `[playful] В твоей истории уже 500 повторений в подходах. Практика прошла первый поворот и даже не потеряла <emphasis>утку-пассажира.</emphasis>`
- **Image prompt:** The small track-building robot with one square eye and clamp hands fits a curved rail into a compact oval track. A rubber duck sits snugly in the miniature cart rounding the bend, its beak tilted toward the robot.

#### 3. Мост из повторений

- **ID:** `practice.reps:t3`
- **Порог:** 1500 повторение
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 1 500 повторений в подходах. Из отдельных движений вырос целый мост практики — уже есть на что оглянуться.
- **Fish Drama 3:** `[confident] Ты накопил 1 500 повторений в подходах. Из отдельных движений вырос <emphasis>целый мост практики</emphasis> — уже есть на что оглянуться.`
- **Image prompt:** The small track-building robot with one square eye and clamp hands secures the central span of an arched railway bridge. Above it, a miniature cart carrying the rubber duck crosses between sturdy supports made from interlocking track modules.

#### 4. Эстакада с характером

- **ID:** `practice.reps:t4`
- **Порог:** 3000 повторение
- **Подтверждённая практика:** минимум 160 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** 3 000 повторений в подходах уже в твоей истории. Рельсы практики вышли на эстакаду — утка пристегнулась серьёзнее.
- **Fish Drama 3:** `[excited] 3 000 повторений в подходах уже в твоей истории. Рельсы практики вышли на эстакаду — утка <emphasis>пристегнулась серьёзнее.</emphasis>`
- **Image prompt:** The small track-building robot with one square eye and clamp hands operates a lever beneath a sweeping elevated railway. The rubber duck rides a cart around a high banked turn, held snugly by an oversized lap bar.

#### 5. Башня больших виражей

- **ID:** `practice.reps:t5`
- **Порог:** 7500 повторение
- **Подтверждённая практика:** минимум 260 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 7 500 повторений в подходах — рельсы практики закрутились в башню. Утка репетирует победное «кря».
- **Fish Drama 3:** `[excited] Ты накопил 7 500 повторений в подходах — рельсы практики закрутились в башню. Утка репетирует <emphasis>победное «кря».</emphasis>`
- **Image prompt:** The small track-building robot with one square eye and clamp hands attaches the top curve of a towering spiral railway. Far below, the rubber duck's cart begins the climb, its open beak aimed toward the summit.

#### 6. Грандиозное кря

- **ID:** `practice.reps:t6`
- **Порог:** 15000 повторение
- **Подтверждённая практика:** минимум 420 разных дней; оба условия обязательны.
- **Ступень:** Большой путь
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 15 000 повторений в подходах — целый парк практики. И всё это величие возит одну резиновую утку.
- **Fish Drama 3:** `[triumphant] Ты накопил 15 000 повторений в подходах — целый парк практики. И всё это величие возит <slow>одну резиновую утку.</slow>`
- **Image prompt:** The small track-building robot with one square eye and clamp hands proudly opens a boarding gate beneath an enormous roller coaster of loops and spirals. Its only passenger is a tiny rubber duck in a single cart at the summit.

### `practice.working_sets`

**Правило:** Накопить рабочие подходы без разминочных. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** рабочий подход. **Источник:** `available`.

#### 1. Первый рабочий ритм

- **ID:** `practice.working_sets:t1`
- **Порог:** 10 рабочий подход
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 10 рабочих подходов без учёта разминочных. Ритм практики уже слышно — даже кастрюля подыгрывает.
- **Fish Drama 3:** `[warm] Ты накопил 10 рабочих подходов без учёта разминочных. Ритм практики уже слышно — даже кастрюля <soft>подыгрывает.</soft>`
- **Image prompt:** A raccoon drummer sits on a low stool, gently tapping an upside-down saucepan with wooden spoons. One striped tail curls around the stool leg, and a small pot lid rests nearby, ready to join the improvised drum kit.

#### 2. Кастрюли держат ритм

- **ID:** `practice.working_sets:t2`
- **Порог:** 50 рабочий подход
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 50 рабочих подходов, не считая разминочных. Кухонный оркестр практики уже уверенно держит ритм.
- **Fish Drama 3:** `[confident] Ты накопил 50 рабочих подходов, не считая разминочных. Кухонный оркестр практики уже <emphasis>уверенно держит ритм.</emphasis>`
- **Image prompt:** The raccoon drummer plays a semicircle of saucepans and stockpots with wooden spoons. A hanging frying pan swings from a fresh strike, while the striped tail steadies a pot lid used as a pedal cymbal.

#### 3. Кастрюля большого финала

- **ID:** `practice.working_sets:t3`
- **Порог:** 150 рабочий подход
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 150 рабочих подходов без учёта разминочных. Туш в твою честь — на главной кастрюле оркестра!
- **Fish Drama 3:** `[triumphant] Ты накопил 150 рабочих подходов без учёта разминочных. Туш в твою честь — <slow>на главной кастрюле оркестра!</slow>`
- **Image prompt:** The raccoon drummer stands inside a towering drum kit built from nested stockpots and suspended frying pans. Ignoring the gigantic cookware, it raises a soup ladle for a ceremonial strike on one tiny saucepan perched at the center.

### `practice.exercise_sessions`

**Правило:** Накопить завершённые записи упражнений с результатами. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение. **Источник:** `available`.

#### 1. Пять дел в папке

- **ID:** `practice.exercise_sessions:t1`
- **Порог:** 5 упражнение
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 5 завершённых записей упражнений с результатами. Осьминог-архивариус открыл папку: у практики теперь есть своя история.
- **Fish Drama 3:** `[warm]У тебя уже 5 завершённых записей упражнений с результатами. Осьминог-архивариус открыл папку: у практики теперь есть своя история.`
- **Image prompt:** A small octopus archivist gathers five blank workout slips into an open binder, carefully aligning their edges with several tentacles. Another tentacle steadies a tiny dumbbell used as a paperweight.

#### 2. Архив расправил щупальца

- **ID:** `practice.exercise_sessions:t2`
- **Порог:** 25 упражнение
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоём архиве уже 25 завершённых записей упражнений с результатами. Осьминог освоил картотеку и деловито шуршит всеми восемью руками.
- **Fish Drama 3:** `[confident]В твоём архиве уже <emphasis>25 завершённых записей упражнений с результатами.</emphasis> Осьминог освоил картотеку и деловито шуршит всеми восемью руками.`
- **Image prompt:** The small octopus archivist stands between open filing drawers, sorting thick bundles of blank workout slips with all eight tentacles. A tiny dumbbell pins down a stack that curls upward like a paper wave.

#### 3. Девятая рука занята

- **ID:** `practice.exercise_sessions:t3`
- **Порог:** 75 упражнение
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя накопилось 75 завершённых записей упражнений с результатами. Осьминог выпросил девятую руку — для чашки чая.
- **Fish Drama 3:** `[triumphant]У тебя накопилось <emphasis>75 завершённых записей упражнений с результатами.</emphasis> Осьминог выпросил девятую руку — <slow>для чашки чая.</slow>`
- **Image prompt:** The small octopus archivist balances an enormous open binder amid overflowing drawers, all eight tentacles occupied with blank workout slips. A tiny mechanical ninth arm attached to the desk calmly offers a steaming teacup.

### `practice.partial_workouts`

**Правило:** Сохранить частичные тренировки: выполненная работа тоже имеет значение. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** частичная тренировка. **Источник:** `available`.

#### 1. Сделанное остаётся

- **ID:** `practice.partial_workouts:t1`
- **Порог:** 1 частичная тренировка
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты сохранил 1 частичную тренировку. Сделанная работа остаётся в истории — енот-портной бережно подшивает первый лоскут.
- **Fish Drama 3:** `[warm]Ты сохранил 1 частичную тренировку. Сделанная работа остаётся в истории — енот-портной бережно подшивает первый лоскут.`
- **Image prompt:** A small raccoon tailor sits beside a low sewing table, carefully stitching one sturdy fabric patch onto a folded cloth backing. Its paws hold the seam flat, with a spool and pincushion close at hand.

#### 2. Полотно твоей практики

- **ID:** `practice.partial_workouts:t2`
- **Порог:** 5 частичная тренировка
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 5 сохранённых частичных тренировок. У енота-портного растёт полотно: каждой сделанной части нашлось место.
- **Fish Drama 3:** `[confident]В твоей истории уже <emphasis>5 сохранённых частичных тренировок.</emphasis> У енота-портного растёт полотно: каждой сделанной части нашлось место.`
- **Image prompt:** The small raccoon tailor spreads five joined fabric panels across a broad sewing table, smoothing their sturdy seams with both paws. One end of the growing quilt rolls over the table edge beside a large spool.

#### 3. Штанга под пледом

- **ID:** `practice.partial_workouts:t3`
- **Порог:** 15 частичная тренировка
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты сохранил уже 15 частичных тренировок. Енот сшил плед из этой истории и укрыл штангу — ей тоже можно отдыхать.
- **Fish Drama 3:** `[triumphant]Ты сохранил уже <emphasis>15 частичных тренировок.</emphasis> Енот сшил плед из этой истории и укрыл штангу — <slow>ей тоже можно отдыхать.</slow>`
- **Image prompt:** The small raccoon tailor tucks an oversized barbell into a tiny wooden bed beneath a generous patchwork quilt. The barbell plates protrude on either side, each resting on its own pillow, while the raccoon smooths the blanket.

### `practice.multi_set_days`

**Правило:** Накопить дни, в каждом из которых выполнено минимум пять подходов. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** день с пятью подходами. **Источник:** `available`.

#### 1. Палеты практики

- **ID:** `practice.multi_set_days:t1`
- **Порог:** 2 день с пятью подходами
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 2 дня, в каждом — минимум пять выполненных подходов. Хомяк-погрузчик принял первые палеты практики!
- **Fish Drama 3:** `[warm] У тебя уже 2 дня, в каждом — минимум пять выполненных подходов. [playful] Хомяк-погрузчик принял первые палеты практики!`
- **Image prompt:** A hamster in a work helmet drives a tiny forklift toward two wooden pallets, each holding five neatly stacked dumbbells. The hamster leans out of the cab to inspect the load, one paw raised in approval.

#### 2. Складу тесно

- **ID:** `practice.multi_set_days:t2`
- **Порог:** 8 день с пятью подходами
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** За твоими плечами 8 дней минимум с пятью выполненными подходами в каждом. Хомяк-погрузчик уже просит склад побольше.
- **Fish Drama 3:** `[confident] За твоими плечами 8 дней минимум с пятью выполненными подходами в каждом. [playful] Хомяк-погрузчик уже просит <emphasis>склад побольше</emphasis>.`
- **Image prompt:** A hamster in a work helmet maneuvers a tiny forklift between eight pallets loaded with dumbbells. The cargo forms a snug semicircle around the vehicle; the hamster holds up a folding ruler to measure the last sliver of space.

#### 3. Диван для лени

- **ID:** `practice.multi_set_days:t3`
- **Порог:** 20 день с пятью подходами
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 20 дней минимум с пятью выполненными подходами в каждом. Хомяк-погрузчик построил диван для лени — пусть сидит, не командует.
- **Fish Drama 3:** `[triumphant] Ты накопил 20 дней минимум с пятью выполненными подходами в каждом. [playful] Хомяк-погрузчик построил диван для лени — <slow>пусть сидит, не командует.</slow>`
- **Image prompt:** A hamster in a work helmet parks its tiny forklift beside a grand sofa built from twenty dumbbell-loaded pallets. Sleepy anthropomorphic slippers lounge on the cushions as the hamster delivers a miniature footrest with a theatrical bow.

### `practice.three_exercise_days`

**Правило:** Накопить дни с результатами по трём разным упражнениям. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** день с тремя упражнениями. **Источник:** `available`.

#### 1. Трио на пробе

- **ID:** `practice.three_exercise_days:t1`
- **Порог:** 2 день с тремя упражнениями
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей копилке 2 дня с результатами по трём разным упражнениям в каждом. Осьминог-дирижёр выводит трио на сцену!
- **Fish Drama 3:** `[warm] В твоей копилке 2 дня с результатами по трём разным упражнениям в каждом. [playful] Осьминог-дирижёр выводит трио на сцену!`
- **Image prompt:** A small octopus conductor stands on an overturned wooden crate before a trumpet, a violin and a drum. Three tentacles test the instruments while another raises a baton; the remaining arms carefully pull open a tiny stage curtain.

#### 2. Репертуар набирает ход

- **ID:** `practice.three_exercise_days:t2`
- **Порог:** 8 день с тремя упражнениями
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 8 дней с результатами по трём разным упражнениям в каждом. Осьминог-дирижёр сменил ящик на сцену — репертуар требует размаха.
- **Fish Drama 3:** `[confident] У тебя уже 8 дней с результатами по трём разным упражнениям в каждом. [playful] Осьминог-дирижёр сменил ящик на сцену — <emphasis>репертуар требует размаха.</emphasis>`
- **Image prompt:** An octopus conductor stretches across a tiered concert stage, simultaneously playing an oversized trumpet, violin and drum. One tentacle flourishes a baton while two others extend the sliding stage wings to make room for the growing trio.

#### 3. Бутерброд на бис

- **ID:** `practice.three_exercise_days:t3`
- **Порог:** 20 день с тремя упражнениями
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 20 дней с результатами по трём разным упражнениям в каждом. Оркестр разросся так, что осьминог заказал пюпитр для бутерброда.
- **Fish Drama 3:** `[triumphant] В твоей истории уже 20 дней с результатами по трём разным упражнениям в каждом. [playful] Оркестр разросся так, что осьминог заказал <slow>пюпитр для бутерброда.</slow>`
- **Image prompt:** An octopus conductor commands a towering trumpet, violin and drum from a raised podium, its tentacles sweeping through a grand finale. Beside it, an elaborate conductor's stand holds only a comically small sandwich, poised for a ceremonious bite.

### `practice.focus`

**Правило:** Возвращаться к одному любимому упражнению в разные дни. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** день с упражнением. **Источник:** `available`.

#### 1. Голубь знает адрес

- **ID:** `practice.focus:t1`
- **Порог:** 5 день с упражнением
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 5 разных дней с одним и тем же упражнением. Почтовый голубь одобряет: возвращаться по знакомому адресу — его тема.
- **Fish Drama 3:** `[warm] У тебя уже 5 разных дней с одним и тем же упражнением. Почтовый голубь одобряет: возвращаться по знакомому адресу — <soft>его тема.</soft>`
- **Image prompt:** A carrier pigeon with chunky wristbands and one curled head feather lands on a compact exercise bench beside a single dumbbell. Its open wings balance the landing, while familiar claw marks trace the bench edge.

#### 2. Маршрут без пересадок

- **ID:** `practice.focus:t2`
- **Порог:** 15 день с упражнением
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 15 разных дней с одним и тем же упражнением. Это не случайная встреча — у практики появился твой адрес.
- **Fish Drama 3:** `[confident] У тебя уже <emphasis>15 разных дней</emphasis> с одним и тем же упражнением. Это не случайная встреча — у практики появился твой адрес.`
- **Image prompt:** A carrier pigeon with chunky wristbands and one curled head feather confidently taxis down a tiny runway ending at its familiar exercise bench. A miniature windsock leans toward the dumbbell waiting on the seat.

#### 3. Аэропорт одного упражнения

- **ID:** `practice.focus:t3`
- **Порог:** 30 день с упражнением
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 30 разных дней с одним и тем же упражнением. Голубь постоянства открыл аэропорт — с рейсом «Опять сюда».
- **Fish Drama 3:** `[triumphant] У тебя уже 30 разных дней с одним и тем же упражнением. [playful] Голубь постоянства открыл аэропорт — <slow>с рейсом «Опять сюда».</slow>`
- **Image prompt:** A wristband-wearing carrier pigeon with a curled head feather lands beside its familiar dumbbell on an exercise bench. The bench is now an airport gate, with a tiny terminal underneath and a passenger jet absurdly queuing behind the bird.

### `practice.thousand_sets`

**Правило:** Продолжать накапливать большую историю практики. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** подход. **Источник:** `available`.

#### 1. Практика в переплёте

- **ID:** `practice.thousand_sets:t1`
- **Порог:** 400 подход
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя накопилось 400 подходов. История практики уже тянет на отдельный том — лень пока застряла в предисловии.
- **Fish Drama 3:** `[warm] У тебя накопилось 400 подходов. История практики уже тянет на отдельный том — <soft>лень пока застряла в предисловии.</soft>`
- **Image prompt:** A small octopus librarian in oversized reading glasses stacks thick exercise logbooks on a squat wheeled cart. One arm steadies the growing pile, another opens a fresh volume, and the remaining arms proudly present the little archive.

#### 2. Архив на восемь рук

- **ID:** `practice.thousand_sets:t2`
- **Порог:** 1000 подход
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты пополняешь историю практики: в ней уже 1000 подходов. Осьминог-библиотекарь задействовал все восемь рук.
- **Fish Drama 3:** `[confident] Ты пополняешь историю практики: в ней уже <emphasis>1000 подходов.</emphasis> Осьминог-библиотекарь задействовал все восемь рук.`
- **Image prompt:** An octopus librarian in oversized reading glasses uses all eight arms to shelve hefty exercise logbooks along a sweeping spiral bookcase. Its wheeled cart waits below, piled high, while a small dumbbell props up the lowest row.

#### 3. Аплодисменты с погрузчиком

- **ID:** `practice.thousand_sets:t3`
- **Порог:** 2500 подход
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя накопилось 2500 подходов. Осьминог-библиотекарь аплодирует всеми восемью руками — а твою летопись держит погрузчик.
- **Fish Drama 3:** `[triumphant] У тебя накопилось 2500 подходов. [playful] Осьминог-библиотекарь аплодирует всеми восемью руками — <slow>а твою летопись держит погрузчик.</slow>`
- **Image prompt:** An octopus librarian in oversized reading glasses applauds with four pairs of arms beside its tiny abandoned book cart. Behind it, a forklift hoists an enormous exercise logbook, its thick page block towering over the delighted librarian.

## Свобода движения

### `variety.timed_seconds`

**Правило:** Накопить фактические секунды упражнений на время. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** секунда. **Источник:** `available`.

#### 1. Время по песчинке

- **ID:** `variety.timed_seconds:t1`
- **Порог:** 300 секунда
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 300 секунд упражнений на время. Песочные часы принесли ведёрко: такая история начинается с первой горсти.
- **Fish Drama 3:** `[warm]У тебя уже <emphasis>300 секунд</emphasis> упражнений на время. Песочные часы принесли ведёрко: такая история начинается с первой горсти.`
- **Image prompt:** An animated hourglass with stubby arms kneels beside a tiny sand pile, carefully filling a small bucket with a scoop. A miniature stopwatch peeks over the bucket rim as if inspecting the first delivery.

#### 2. Секунды с прицепом

- **ID:** `variety.timed_seconds:t2`
- **Порог:** 1800 секунда
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 1 800 секунд упражнений на время. Песочные часы сменили ведёрко на тележку — у времени вырос багаж.
- **Fish Drama 3:** `[confident]Ты накопил <emphasis>1 800 секунд</emphasis> упражнений на время. [playful]Песочные часы сменили ведёрко на тележку — у времени вырос багаж.`
- **Image prompt:** The same animated hourglass leans into the handles of a cart heaped with sand, its original bucket hooked to the side. A tiny stopwatch rides on top with a toy shovel, while a short trail of spilled grains marks their route.

#### 3. Пляж из секунд

- **ID:** `variety.timed_seconds:t3`
- **Порог:** 7200 секунда
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 7 200 секунд упражнений на время. Песочные часы открыли собственный пляж — и выдали секундомеру шезлонг.
- **Fish Drama 3:** `[triumphant]В твоей истории уже <emphasis>7 200 секунд</emphasis> упражнений на время. Песочные часы открыли собственный пляж — [playful]<slow>и выдали секундомеру шезлонг.</slow>`
- **Image prompt:** The same animated hourglass hosts a miniature beach built from its collected sand, planting a parasol beside a tiny stopwatch reclining in a deckchair. The old bucket and cart now form a refreshment stand at the water's edge.

### `variety.timed_days`

**Правило:** Накопить дни с упражнениями на время или растяжкой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день на время. **Источник:** `available`.

#### 1. Первые ростки движения

- **ID:** `variety.timed_days:t1`
- **Порог:** 3 день на время
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 3 дня с упражнениями на время или растяжкой. Коврик решил отметить их посадкой цветов — по ростку на день.
- **Fish Drama 3:** `[warm]У тебя уже <emphasis>3 дня</emphasis> с упражнениями на время или растяжкой. Коврик решил отметить их посадкой цветов — по ростку на день.`
- **Image prompt:** A rolled exercise mat wearing small gardening gloves crouches beside three separate pots, each holding a young sunflower. It gently tips a squat watering can, sheltering the smallest sprout with its free hand.

#### 2. Коврик пустил корни

- **ID:** `variety.timed_days:t2`
- **Порог:** 10 день на время
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории 10 дней с упражнениями на время или растяжкой. У коврика уже целая клумба — лейка намекает на повышение.
- **Fish Drama 3:** `[confident]В твоей истории <emphasis>10 дней</emphasis> с упражнениями на время или растяжкой. [playful]У коврика уже целая клумба — лейка намекает на повышение.`
- **Image prompt:** The same rolled exercise mat in gardening gloves proudly pushes a wheelbarrow planter crowded with sunflowers. Its squat watering can balances on the front edge, raising its spout toward the tallest bloom like an eager assistant.

#### 3. Лейка в тренерском составе

- **ID:** `variety.timed_days:t3`
- **Порог:** 25 день на время
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 25 дней с упражнениями на время или растяжкой. Коврик вырастил целый сад — и назначил лейку тренером.
- **Fish Drama 3:** `[triumphant]Ты накопил <emphasis>25 дней</emphasis> с упражнениями на время или растяжкой. Коврик вырастил целый сад — [playful]<slow>и назначил лейку тренером.</slow>`
- **Image prompt:** The same rolled exercise mat proudly presents a flourishing sunflower garden. Its squat watering can stands on a low stool with a whistle, leading the flowers through synchronized side bends while the mat joins in beside them.

### `variety.stretch_seconds`

**Правило:** Накопить секунды сохранённых упражнений на растяжку. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** секунда растяжки. **Источник:** `available`.

#### 1. Первый вдох гармошки

- **ID:** `variety.stretch_seconds:t1`
- **Порог:** 300 секунда растяжки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 300 секунд растяжки в сохранённых упражнениях. Гармошка одобряет: наконец-то кто-то разделяет её увлечение.
- **Fish Drama 3:** `[warm] Ты накопил 300 секунд растяжки в сохранённых упражнениях. Гармошка одобряет: наконец-то кто-то разделяет её увлечение.`
- **Image prompt:** A little accordion with mitten hands opens its first bellows folds beside a neatly unrolled exercise mat. One foot steadies the mat while the other points forward, giving the instrument the earnest air of someone testing a new hobby.

#### 2. Купе для складок

- **ID:** `variety.stretch_seconds:t2`
- **Порог:** 1800 секунда растяжки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 1800 секунд растяжки из сохранённых упражнений. Гармошка развернулась так основательно, что просит отдельное купе.
- **Fish Drama 3:** `[confident] В твоей истории уже <emphasis>1800 секунд растяжки</emphasis> из сохранённых упражнений. Гармошка развернулась так основательно, что просит отдельное купе.`
- **Image prompt:** The little accordion pulls its bellows wide enough to form a tiny train compartment. A kettlebell passenger lounges on a built-in bench, while the accordion leans outward like a conductor surprised by the size of the carriage.

#### 3. Чайная на растяжке

- **ID:** `variety.stretch_seconds:t3`
- **Порог:** 7200 секунда растяжки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В сохранённых упражнениях ты накопил 7200 секунд растяжки. Гармошка развернулась — и открыла чайную для гирь.
- **Fish Drama 3:** `[triumphant] В сохранённых упражнениях ты накопил 7200 секунд растяжки. Гармошка развернулась — <slow>и открыла</slow> <emphasis>чайную для гирь</emphasis>.`
- **Image prompt:** The little accordion has unfolded its bellows into a long tea counter. It pours from a squat teapot for kettlebells perched on stools, with saucers tucked between the folds; the smallest kettlebell solemnly lifts an oversized cup.

### `variety.stretch_days`

**Правило:** Накопить дни с сохранённой растяжкой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** день растяжки. **Источник:** `available`.

#### 1. Черепаший дебют

- **ID:** `variety.stretch_days:t1`
- **Порог:** 3 день растяжки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 3 дня с сохранённой растяжкой. Черепаха выкатывает коврик — спешка сюда не записана.
- **Fish Drama 3:** `[warm] Ты накопил 3 дня с сохранённой растяжкой. Черепаха выкатывает коврик — <soft>спешка сюда не записана</soft>.`
- **Image prompt:** A small turtle with an exercise mat strapped across its shell gently pushes the loose end open beside a tiny sprout. Its front feet flatten the first corner while the remaining roll towers comically over its head.

#### 2. Коврик обживает пол

- **ID:** `variety.stretch_days:t2`
- **Порог:** 10 день растяжки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя накопилось 10 дней с сохранённой растяжкой. Черепаха прижала коврик камушками: теперь это почти недвижимость.
- **Fish Drama 3:** `[playful] У тебя накопилось 10 дней с сохранённой растяжкой. Черепаха прижала коврик камушками: теперь это <emphasis>почти недвижимость</emphasis>.`
- **Image prompt:** The small turtle anchors a longer exercise mat with smooth pebbles, carefully nudging the last pebble into place. A rolled spare mat rests across its shell, and its satisfied stance suggests a property owner inspecting a new home.

#### 3. Студия на панцире

- **ID:** `variety.stretch_days:t3`
- **Порог:** 25 день растяжки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** За всё время ты собрал 25 дней с сохранённой растяжкой. Черепаха ставит навес: у коврика теперь свой адрес.
- **Fish Drama 3:** `[confident] За всё время ты собрал <emphasis>25 дней</emphasis> с сохранённой растяжкой. Черепаха ставит навес: у коврика теперь свой адрес.`
- **Image prompt:** The small turtle balances a rolled mat on its shell while raising a plain fabric canopy over its exercise spot. It braces a canopy pole with one foot; neatly stacked mats and a low empty shelf mark the beginnings of a tiny studio.

#### 4. Место для размаха

- **ID:** `variety.stretch_days:t4`
- **Порог:** 50 день растяжки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя в копилке уже 50 дней с сохранённой растяжкой. Черепаха раскатывает большой коврик — ждёт очень домашнего гостя.
- **Fish Drama 3:** `[excited] У тебя в копилке уже <emphasis>50 дней</emphasis> с сохранённой растяжкой. Черепаха раскатывает большой коврик — ждёт очень домашнего гостя.`
- **Image prompt:** The small turtle rolls a broad exercise mat out from beneath its completed canopy, creating a landing space far larger than itself. With a spare mat tucked across its shell, it peers expectantly toward an approaching sofa-shaped shadow.

#### 5. Диван тоже записался

- **ID:** `variety.stretch_days:t5`
- **Порог:** 100 день растяжки
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 100 дней с сохранённой растяжкой. Черепаха открыла студию — и записала туда диван.
- **Fish Drama 3:** `[triumphant] Ты накопил 100 дней с сохранённой растяжкой. Черепаха открыла студию — <slow>и записала туда</slow> <emphasis>диван</emphasis>.`
- **Image prompt:** The small turtle proudly welcomes a sleepy sofa onto an enormous exercise mat beneath its canopy. The sofa stretches its short wooden legs while a loose cushion yawns; the turtle holds a second mat, clearly wondering where to put it.

### `variety.bodyweight_reps`

**Правило:** Накопить повторения в упражнениях с собственным весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** повторение. **Источник:** `available`.

#### 1. Сам себе снаряд

- **ID:** `variety.bodyweight_reps:t1`
- **Порог:** 50 повторение
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей копилке 50 повторений с собственным весом. Гантели пока отдыхают: главный снаряд здесь — ты.
- **Fish Drama 3:** `[warm] В твоей копилке <emphasis>50 повторений с собственным весом</emphasis>. Гантели пока отдыхают: главный снаряд здесь — ты.`
- **Image prompt:** A jointed wooden athlete performs a push-up on a small exercise mat. Beside the mat, an anthropomorphic dumbbell lounges on a folded towel, watching with curiosity, its short arms tucked comfortably behind its plates.

#### 2. Железо на скамейке

- **ID:** `variety.bodyweight_reps:t2`
- **Порог:** 300 повторение
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 300 повторений с собственным весом. Гантель заняла место зрителя — у тебя и без неё насыщенная программа.
- **Fish Drama 3:** `[confident] Ты накопил <emphasis>300 повторений с собственным весом</emphasis>. Гантель заняла место зрителя — у тебя и без неё насыщенная программа.`
- **Image prompt:** A jointed wooden athlete rises from a bodyweight squat on an exercise mat, arms reaching forward. An anthropomorphic dumbbell sits upright on a small spectator bench nearby, peering through opera glasses held in its short arms.

#### 3. Фанатка с блинами

- **ID:** `variety.bodyweight_reps:t3`
- **Порог:** 1000 повторение
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 1000 повторений с собственным весом. Гантель теперь твоя фанатка — сидит в первом ряду с ведром попкорна.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>1000 повторений с собственным весом</emphasis>. [playful] Гантель теперь твоя фанатка — <slow>сидит в первом ряду с ведром попкорна.</slow>`
- **Image prompt:** A jointed wooden athlete holds a handstand on an exercise mat spread across a tiny theater stage. In the lone front-row armchair, an anthropomorphic dumbbell hugs an absurdly oversized tub of popcorn, leaning forward with rapt attention.

### `variety.bodyweight_sets`

**Правило:** Накопить подходы с собственным весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** подход с весом тела. **Источник:** `available`.

#### 1. Первая глава коврика

- **ID:** `variety.bodyweight_sets:t1`
- **Порог:** 5 подход с весом тела
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Первые 5 подходов с собственным весом уже в твоей истории. Коврик открывает первую главу — и важно шуршит.
- **Fish Drama 3:** `[warm] Первые <emphasis>5 подходов с собственным весом</emphasis> уже в твоей истории. Коврик открывает первую главу — и важно шуршит.`
- **Image prompt:** An animated gym towel with a knotted head and two loose corners for arms carefully slides a folded exercise mat into a small empty bookshelf. The mat resembles a thick little book, its soft layered edges peeking from between the covers.

#### 2. Архив без железа

- **ID:** `variety.bodyweight_sets:t2`
- **Порог:** 25 подход с весом тела
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** 25 подходов с собственным весом уже в твоём архиве. Коврик явно рассчитывал на рассказ, а получается роман.
- **Fish Drama 3:** `[confident] <emphasis>25 подходов с собственным весом</emphasis> уже в твоём архиве. Коврик явно рассчитывал на рассказ, а получается роман.`
- **Image prompt:** An animated gym towel with a knotted head steers a library cart piled with exercise mats folded into chunky books. A curved bookshelf wraps around the towel, while one springy mat volume pops open on the cart like an eager new chapter.

#### 3. Мемуары с коврика

- **ID:** `variety.bodyweight_sets:t3`
- **Порог:** 75 подход с весом тела
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 75 подходов с собственным весом. Коврик выпускает мемуары — и требует отдельную книжную полку.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>75 подходов с собственным весом</emphasis>. [playful] Коврик выпускает мемуары — <slow>и требует отдельную книжную полку.</slow>`
- **Image prompt:** An animated gym towel with a knotted head perches on a library ladder, opening a colossal book made from folded exercise mats. Its springy pages spill across an entire bookcase, squeezing all the smaller mat books into a teetering stack at one end.

### `variety.bodyweight_days`

**Правило:** Накопить дни с упражнениями с собственным весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день с весом тела. **Источник:** `available`.

#### 1. Сам себе спортзал

- **ID:** `variety.bodyweight_days:t1`
- **Порог:** 3 день с весом тела
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя 3 дня с упражнениями с собственным весом. Ты и есть главный инвентарь — доставка не нужна.
- **Fish Drama 3:** `[warm] У тебя 3 дня с упражнениями с собственным весом. Ты и есть <emphasis>главный инвентарь</emphasis> — доставка не нужна.`
- **Image prompt:** A wristband-wearing gecko performs a bodyweight squat on a partly unrolled exercise mat, its curled tail balancing behind it. A pair of small dumbbells watches from the mat's edge with curious faces.

#### 2. Автономный режим включён

- **ID:** `variety.bodyweight_days:t2`
- **Порог:** 10 день с весом тела
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 10 дней с упражнениями с собственным весом. Железо взяло попкорн: ему интересно, что ты ещё придумаешь.
- **Fish Drama 3:** `[confident] Ты накопил <emphasis>10 дней</emphasis> с упражнениями с собственным весом. Железо взяло попкорн: ему интересно, что ты ещё придумаешь.`
- **Image prompt:** The wristband-wearing gecko holds a plank on its fully unfurled exercise mat. The two curious dumbbells now sit on tiny folding chairs beside the mat, sharing a tub of popcorn and leaning forward eagerly.

#### 3. Железо хлопает стоя

- **ID:** `variety.bodyweight_days:t3`
- **Порог:** 25 день с весом тела
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** За тобой 25 дней с упражнениями с собственным весом. Ты ведёшь шоу, а гантели нанялись аплодировать.
- **Fish Drama 3:** `[triumphant] За тобой 25 дней с упражнениями с собственным весом. [playful] Ты ведёшь шоу, а гантели <slow>нанялись аплодировать.</slow>`
- **Image prompt:** The wristband-wearing gecko takes a bow on an exercise mat unfurled into a theater stage. Rows of dumbbells stand and applaud with tiny arms, while a barbell in the front row struggles to clap around its own plates.

### `variety.mixed_kind_days`

**Правило:** Накопить дни с двумя разными типами упражнений. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** смешанный день. **Источник:** `available`.

#### 1. Первый фитнес-микс

- **ID:** `variety.mixed_kind_days:t1`
- **Порог:** 2 смешанный день
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты собрал 2 дня с двумя разными типами упражнений. Первый фитнес-микс готов: скука не попала в плейлист.
- **Fish Drama 3:** `[warm] Ты собрал 2 дня с двумя разными типами упражнений. Первый фитнес-микс готов: <emphasis>скука не попала в плейлист.</emphasis>`
- **Image prompt:** A cheerful octopus DJ tests a compact two-deck mixing console, with a kettlebell resting on one platter and a coiled jump rope on the other. Two tentacles hover over the controls while the others steady the equipment.

#### 2. Пульт разнообразия

- **ID:** `variety.mixed_kind_days:t2`
- **Порог:** 8 смешанный день
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 8 дней с двумя разными типами упражнений. Ты за пультом, однообразие — за дверью.
- **Fish Drama 3:** `[confident] В твоей истории уже <emphasis>8 дней</emphasis> с двумя разными типами упражнений. Ты за пультом, однообразие — за дверью.`
- **Image prompt:** The octopus DJ works a wider mixing console, spinning a kettlebell and a coiled jump rope on separate platters. Several tentacles adjust sliders while a small crowd of animated sneakers bounces in front of the booth.

#### 3. Лень просит автограф

- **ID:** `variety.mixed_kind_days:t3`
- **Порог:** 20 смешанный день
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 20 дней с двумя разными типами упражнений. На твой фитнес-микс даже лень пришла — просить автограф.
- **Fish Drama 3:** `[triumphant] Ты накопил 20 дней с двумя разными типами упражнений. [playful] На твой фитнес-микс даже лень пришла — <slow>просить автограф.</slow>`
- **Image prompt:** The octopus DJ hoists its two-deck console above a dancing crowd of kettlebells and jump ropes, still mixing with spare tentacles. At the front, a sleepy pillow holds out a blank autograph card and an oversized pen.

### `variety.machine_days`

**Правило:** Накопить дни с упражнениями на тренажёре. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день на тренажёре. **Источник:** `available`.

#### 1. Первый рейс железа

- **ID:** `variety.machine_days:t1`
- **Порог:** 3 день на тренажёре
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 3 дня с упражнениями на тренажёре. Железный экспресс тронулся — билет обратно в скуку можно не брать.
- **Fish Drama 3:** `[warm] В твоей истории уже <emphasis>3 дня</emphasis> с упражнениями на тренажёре. [playful] Железный экспресс тронулся — билет обратно в скуку можно не брать.`
- **Image prompt:** A squat locomotive built from a cable exercise machine rolls onto a short curved track. Twin pulley wheels drive it forward, a padded workout bench forms its hood, and a single carriage waits behind an oversized gym-handle coupler.

#### 2. Состав набирает ход

- **ID:** `variety.machine_days:t2`
- **Порог:** 10 день на тренажёре
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 10 дней с упражнениями на тренажёре. Железный экспресс уже везёт целый вагон опыта — и тот даже не скрипит.
- **Fish Drama 3:** `[confident] Ты накопил <emphasis>10 дней</emphasis> с упражнениями на тренажёре. Железный экспресс уже везёт целый вагон опыта — и тот даже не скрипит.`
- **Image prompt:** The cable-machine locomotive with twin pulley wheels and a padded bench hood pulls a winding chain of carriages carrying exercise stations. Its cable arm rings a departure bell while a neatly rolled workout towel occupies the driver's seat.

#### 3. Вокзал тоже едет

- **ID:** `variety.machine_days:t3`
- **Порог:** 25 день на тренажёре
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 25 дней с упражнениями на тренажёре! Железный экспресс так освоился, что прихватил с собой весь вокзал.
- **Fish Drama 3:** `[triumphant] У тебя уже <emphasis>25 дней</emphasis> с упражнениями на тренажёре! Железный экспресс так освоился, что прихватил с собой <slow>весь вокзал.</slow>`
- **Image prompt:** The cable-machine locomotive with twin pulley wheels and a padded bench hood proudly tows an entire railway station mounted on enormous wheels. Platform benches and a ticket booth ride inside the open station hall, with a tiny suitcase left on the track.

### `variety.bodyweight_exercises`

**Правило:** Познакомиться с разными упражнениями с собственным весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение с весом тела. **Источник:** `available`.

#### 1. Два хода без железа

- **ID:** `variety.bodyweight_exercises:t1`
- **Порог:** 2 упражнение с весом тела
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты познакомился с 2 разными упражнениями с собственным весом. Для входа в этот клуб даже гантель не понадобилась.
- **Fish Drama 3:** `[warm] Ты познакомился с <emphasis>2 разными упражнениями</emphasis> с собственным весом. [playful] Для входа в этот клуб даже гантель не понадобилась.`
- **Image prompt:** A curious octopus holds a low plank on a workout mat, using its own arms as supports. Two small cards beside the mat show the same octopus in a squat and a plank; one free tentacle curiously flips a card.

#### 2. Репертуар без гантелей

- **ID:** `variety.bodyweight_exercises:t2`
- **Порог:** 5 упражнение с весом тела
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты попробовал 5 разных упражнений с собственным весом. Репертуар растёт, а гантели всё ещё сидят в зрительном зале.
- **Fish Drama 3:** `[confident] Ты попробовал <emphasis>5 разных упражнений</emphasis> с собственным весом. Репертуар растёт, а гантели всё ещё сидят в зрительном зале.`
- **Image prompt:** The curious octopus balances in a side-support pose on its workout mat, fanning out cards depicting different bodyweight movements with its free tentacles. A pair of dumbbells sits on a miniature spectator bench, each draped with a small towel.

#### 3. Щупальца кончились первыми

- **ID:** `variety.bodyweight_exercises:t3`
- **Порог:** 10 упражнение с весом тела
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты познакомился с 10 разными упражнениями с собственным весом! Осьминог пытался пересчитать — закончились щупальца.
- **Fish Drama 3:** `[triumphant] Ты познакомился с <emphasis>10 разными упражнениями</emphasis> с собственным весом! Осьминог пытался пересчитать — <slow>закончились щупальца.</slow>`
- **Image prompt:** The octopus sits on its workout mat amid a fan of exercise-pose cards, all eight tentacles raised in a counting gesture. It stares in disbelief at two oven mitts mounted on wooden spoons beside it, improvised extra limbs for finishing the count.

## Атлас движений

### `repertoire.distinct_exercises`

**Правило:** Оставить результаты в разных упражнениях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение. **Источник:** `available`.

#### 1. Атлас приоткрылся

- **ID:** `repertoire.distinct_exercises:t1`
- **Порог:** 3 упражнение
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты записал результаты в 3 разных упражнениях. У атласа движений появились первые страницы — и ни одной скучной.
- **Fish Drama 3:** `[warm] Ты записал результаты в 3 разных упражнениях. У атласа движений появились первые страницы — <soft>и ни одной скучной.</soft>`
- **Image prompt:** A small walking exercise atlas in sturdy boots opens three illustrated foldout tabs, revealing a dumbbell, a kettlebell and a training bench; its little hands carefully hold the new pages apart.

#### 2. Страницы расправляют плечи

- **ID:** `repertoire.distinct_exercises:t2`
- **Порог:** 8 упражнение
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории есть результаты в 8 разных упражнениях. Ты расширил репертуар — атлас уже расправляет страницы.
- **Fish Drama 3:** `[playful] В твоей истории есть результаты в 8 разных упражнениях. Ты расширил репертуар — атлас уже <emphasis>расправляет страницы.</emphasis>`
- **Image prompt:** The booted exercise atlas strides across its own accordion-fold pages like a little bridge; illustrated training tools pop upright along the folds, and its hands stretch outward to keep the growing spread open.

#### 3. Разворот большого масштаба

- **ID:** `repertoire.distinct_exercises:t3`
- **Порог:** 15 упражнение
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Результаты в 15 разных упражнениях — уже часть твоей истории. Ты собрал репертуар, которому тесно на одном развороте.
- **Fish Drama 3:** `[confident] Результаты в 15 разных упражнениях — уже часть твоей истории. Ты собрал репертуар, которому <emphasis>тесно на одном развороте.</emphasis>`
- **Image prompt:** The walking exercise atlas climbs a spiral staircase made from its own unfolding pages; small pop-up stations for lifting, rowing and stretching occupy the steps, while one boot reaches for the next paper landing.

#### 4. Обложке нужна пристройка

- **ID:** `repertoire.distinct_exercises:t4`
- **Порог:** 25 упражнение
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя записаны результаты в 25 разных упражнениях. Атлас движений развернулся так широко, что обложка просит пристройку.
- **Fish Drama 3:** `[excited] У тебя записаны результаты в 25 разных упражнениях. Атлас движений развернулся так широко, что <emphasis>обложка просит пристройку.</emphasis>`
- **Image prompt:** The booted exercise atlas stretches its covers around a sprawling pop-up training pavilion; folded pages form roofs over varied equipment, and its little hands try to fasten a comically undersized cover clasp.

#### 5. Атлас требует погрузчик

- **ID:** `repertoire.distinct_exercises:t5`
- **Порог:** 40 упражнение
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты оставил результаты в 40 разных упражнениях. Твой атлас движений теперь листают погрузчиком.
- **Fish Drama 3:** `[triumphant] Ты оставил результаты в 40 разных упражнениях. Твой атлас движений теперь листают <slow>погрузчиком.</slow>`
- **Image prompt:** The booted exercise atlas steers a tiny forklift to lift one of its own enormous pages; an entire pop-up gym rises on the paper, while a dumbbell waits below in a miniature armchair for the page turn.

### `repertoire.familiar`

**Правило:** Накопить упражнения, каждое из которых выполнялось минимум в трёх днях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** знакомое упражнение. **Источник:** `available`.

#### 1. Первые знакомые среди железа

- **ID:** `repertoire.familiar:t1`
- **Порог:** 2 знакомое упражнение
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнял 2 разных упражнения, каждое — минимум в три разных дня. Железо начинает тебя узнавать.
- **Fish Drama 3:** `[warm] Ты выполнял 2 разных упражнения, каждое — минимум в три разных дня. <soft>Железо начинает тебя узнавать.</soft>`
- **Image prompt:** A round kettlebell with mitten-like hands arrives at a tiny gym cafe, greeting a friendly training bench behind the counter; a dumbbell and a resistance band wait beside plain cups on neighboring stools.

#### 2. Компания уже собралась

- **ID:** `repertoire.familiar:t2`
- **Порог:** 5 знакомое упражнение
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Уже 5 упражнений ты выполнял минимум в три разных дня каждое. Среди железа собралась своя компания — случайных знакомств всё меньше.
- **Fish Drama 3:** `[confident] Уже 5 упражнений ты выполнял минимум в три разных дня каждое. Среди железа собралась <emphasis>своя компания</emphasis> — случайных знакомств всё меньше.`
- **Image prompt:** The round kettlebell with mitten-like hands pulls extra stools toward its usual gym cafe table; a training bench pours tea while a dumbbell, resistance band and other familiar tools lean in for a lively reunion.

#### 3. Скамья помнит твой заказ

- **ID:** `repertoire.familiar:t3`
- **Порог:** 10 знакомое упражнение
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории 10 упражнений, каждое ты выполнял минимум в три разных дня. Скамья уже спрашивает: «Тебе как обычно?»
- **Fish Drama 3:** `[triumphant] В твоей истории 10 упражнений, каждое ты выполнял минимум в три разных дня. Скамья уже спрашивает: <slow>«Тебе как обычно?»</slow>`
- **Image prompt:** The round kettlebell opens its mitten-like hands in surprise as a smiling training bench rolls up with tea balanced on its own padded seat; familiar gym tools peek over a cafe counter, anticipating the usual order.

### `repertoire.exploration`

**Правило:** Выполнить разные упражнения, входившие в исходный согласованный план. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение по плану. **Источник:** `requires_plan`.

#### 1. План раскрыл карты

- **ID:** `repertoire.exploration:t1`
- **Порог:** 3 упражнение по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил 3 разных упражнения из исходного согласованного плана. Разведка состоялась: карта больше не просто красиво лежит.
- **Fish Drama 3:** `[curious]Ты выполнил 3 разных упражнения из исходного согласованного плана. Разведка состоялась: карта больше не просто красиво лежит.`
- **Image prompt:** Exactly one round convex achievement medallion filling the frame, nearly frontal with minimal perspective. Thick multilayer silver-gold metal rim, chunky silver outer bevel, polished gold inner bevel and tiny metal rivets. Inside a domed translucent warm-gold enamel/glass insert, show one large folded-map emblem occupying 65% of the inner circle. The map is a single integrated embossed symbol with two broad folds and one winding recessed route, completely unlettered. Shallow rounded relief and a gentle honey-gold glow establish the first tier. Two small cascading stars in sapphire and coral remain inside the coin. White-blue glossy highlights on the glass. Saturated stylized 3D premium mobile-game achievement coin, readable at 96px, dark almost uniform navy background. Keep this circular silhouette across the line. No letters, digits, inscriptions, logos, people, bodies, photographs, floating objects, exterior props, scene, diorama or realistic product photography.

#### 2. Маршрут с характером

- **ID:** `repertoire.exploration:t2`
- **Порог:** 8 упражнение по плану
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил 8 разных упражнений из исходного согласованного плана. Список перестал притворяться декорацией.
- **Fish Drama 3:** `[playful]Ты выполнил <emphasis>8 разных упражнений</emphasis> из исходного согласованного плана. Список перестал притворяться декорацией.`
- **Image prompt:** Exactly one round convex achievement medallion filling the frame, retaining the first tier's circular silhouette, nearly frontal with minimal perspective. Thick multilayer silver-gold metal rim with chunky silver outer bevel, polished gold inner bevel and tiny metal rivets. Domed translucent warm-gold enamel/glass insert carrying one large four-point compass-rose relief with an integrated circular hub, occupying 65% of the inner circle. Broad sculpted points, stepped ridges and deeper metallic relief than the map tier; a richer honey-colored edge glow, still common rarity. Three tiny cascading stars in coral, sapphire and mint are enclosed inside the medallion. White-blue glossy glass highlights. Saturated stylized 3D premium mobile-game icon, readable at 96px, dark almost uniform navy background. No letters, compass labels, digits, inscriptions, logos, people, bodies, photographs, floating objects, exterior props, scene, diorama or realistic product photography.

#### 3. Атлас вышел в зал

- **ID:** `repertoire.exploration:t3`
- **Порог:** 15 упражнение по плану
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил 15 разных упражнений из исходного согласованного плана. У этого атласа теперь есть биография, а не только обложка.
- **Fish Drama 3:** `[confident]Ты выполнил 15 разных упражнений из исходного согласованного плана. У этого атласа теперь есть <emphasis>биография</emphasis>, а не только обложка.`
- **Image prompt:** Exactly one round convex achievement medallion filling the frame, with the same circular silhouette as previous tiers, nearly frontal with minimal perspective. Thick multilayer silver-gold metal rim, chunky silver outer bevel, polished gold inner bevel and tiny metal rivets. A domed translucent warm-gold enamel/glass insert contains one large closed-atlas emblem occupying 65% of the inner circle. Render the atlas as integrated high relief: thick page-block grooves, rounded spine and a single branching-route design recessed into its blank cover. Rich layered bevels and the strongest honey-gold glow in this common-rarity line. Three tiny cascading stars in sapphire, coral and mint remain inside the coin. White-blue glossy highlights across the glass. Saturated stylized 3D premium mobile-game achievement coin, readable at 96px, dark almost uniform navy background. No letters, digits, inscriptions, logos, people, bodies, photographs, floating objects, exterior props, scene, diorama or realistic product photography.

### `repertoire.familiar_days`

**Правило:** Накопить дни с упражнением, уже встречавшимся ранее в трёх днях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день знакомой практики. **Источник:** `available`.

#### 1. Знакомый поворот

- **ID:** `repertoire.familiar_days:t1`
- **Порог:** 5 день знакомой практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 5 дней: в каждом было упражнение, которое ты уже выполнял минимум в 3 дня до этого. Возвращение к знакомому — тоже сюжетный ход.
- **Fish Drama 3:** `[warm]Ты накопил 5 дней: в каждом было упражнение, которое ты уже выполнял минимум в 3 дня до этого. Возвращение к знакомому — тоже сюжетный ход.`
- **Image prompt:** Exactly one round convex achievement medallion filling the frame, nearly frontal with minimal perspective. Thick multilayer silver-gold metal rim with chunky silver outer bevel, polished gold inner bevel and tiny metal rivets. Domed translucent warm-gold enamel/glass insert holding one large circular return-arrow relief occupying 65% of the inner circle. A single thick curved band ends in a broad blunt arrowhead, with a clean open center and simple rounded metallic edges. Modest relief and gentle honey-gold illumination for the first tier. Two small cascading stars in teal and rose sit inside the medallion. White-blue glossy highlights on the glass. Saturated stylized 3D premium mobile-game achievement coin, readable at 96px, dark almost uniform navy background. Keep this round coin silhouette for all tiers. No letters, digits, inscriptions, logos, people, bodies, photographs, floating objects, exterior props, scene, diorama or realistic product photography.

#### 2. Практика без представлений

- **ID:** `repertoire.familiar_days:t2`
- **Порог:** 15 день знакомой практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории 15 дней: в каждом было упражнение, уже выполненное минимум в 3 разных дня ранее. Знакомиться заново не пришлось — сразу к делу.
- **Fish Drama 3:** `[amused]В твоей истории <emphasis>15 дней</emphasis>: в каждом было упражнение, уже выполненное минимум в 3 разных дня ранее. Знакомиться заново не пришлось — сразу к делу.`
- **Image prompt:** Exactly one round convex achievement medallion filling the frame, preserving the first tier's circular silhouette, nearly frontal with minimal perspective. Thick multilayer silver-gold metal rim, chunky silver outer bevel, polished gold inner bevel and tiny metal rivets. Within a domed translucent warm-gold enamel/glass insert, place one large revolving-door emblem occupying 65% of the inner circle. It is a single integrated relief: a central rounded hub and three broad curved vanes enclosed by a thick circular outline, not an architectural scene. Deeper sculpting and richer honey-gold glow than the return-arrow tier. Three small cascading stars in teal, rose and sapphire stay inside the medallion. White-blue glossy glass highlights. Saturated stylized 3D premium mobile-game icon, readable at 96px, dark almost uniform navy background. No letters, digits, inscriptions, logos, people, bodies, photographs, floating objects, exterior props, scene, diorama or realistic product photography.

#### 3. Сорок тёплых встреч

- **ID:** `repertoire.familiar_days:t3`
- **Порог:** 40 день знакомой практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 40 дней: в каждом было упражнение, которое ты уже выполнял минимум в 3 дня до этого. У знакомой практики теперь целый сериал.
- **Fish Drama 3:** `[confident]Ты накопил <emphasis>40 дней</emphasis>: в каждом было упражнение, которое ты уже выполнял минимум в 3 дня до этого. У знакомой практики теперь целый сериал.`
- **Image prompt:** Exactly one round convex achievement medallion filling the frame, maintaining the earlier tiers' circular silhouette, nearly frontal with minimal perspective. Thick multilayer silver-gold metal rim with chunky silver outer bevel, polished gold inner bevel and tiny metal rivets. Domed translucent warm-gold enamel/glass insert featuring one large mechanical flywheel relief occupying 65% of the inner circle. Six broad sculpted spokes, a raised hub and one recessed circular return groove form a single unified symbol. The deepest stepped relief and richest honey-gold illumination in this common-rarity line, without fiery legendary coloring. Three tiny cascading stars in teal, rose and sapphire remain inside the coin. White-blue glossy highlights on the glass. Saturated stylized 3D premium mobile-game achievement coin, readable at 96px, dark almost uniform navy background. No letters, digits, inscriptions, logos, people, bodies, photographs, floating objects, exterior props, scene, diorama or realistic product photography.

### `repertoire.exercise_weeks`

**Правило:** Возвращаться к одному упражнению в разных неделях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя с упражнением. **Источник:** `available`.

#### 1. Знакомая скамья

- **ID:** `repertoire.exercise_weeks:t1`
- **Порог:** 3 неделя с упражнением
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты выполнил одно и то же упражнение в 3 разных неделях. Железо уже придерживает тебе дверь!
- **Fish Drama 3:** `[warm]Ты выполнил одно и то же упражнение в 3 разных неделях. Железо уже <emphasis>придерживает тебе дверь!</emphasis>`
- **Image prompt:** A small anthropomorphic kettlebell carrying a striped gym bag enters a tiny inn shaped like an exercise bench. Its handle tilts toward an open seat-lid doorway, where a folded towel waits on a little check-in shelf.

#### 2. Твоё обычное

- **ID:** `repertoire.exercise_weeks:t2`
- **Порог:** 8 неделя с упражнением
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 8 разных недель с одним и тем же упражнением. Оно узнаёт тебя без вопроса «Вам как обычно?».
- **Fish Drama 3:** `[confident]У тебя уже 8 разных недель с одним и тем же упражнением. Оно узнаёт тебя без вопроса <emphasis>«Вам как обычно?».</emphasis>`
- **Image prompt:** An anthropomorphic kettlebell with a striped gym bag confidently settles into its familiar nook inside an exercise-bench inn. A tiny towel valet has already pulled out its stool, and its bag fits a dedicated cubby.

#### 3. Пульт от спортзала

- **ID:** `repertoire.exercise_weeks:t3`
- **Порог:** 16 неделя с упражнением
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории — 16 разных недель с одним и тем же упражнением. Оно уже выдало тебе тапочки и пульт от спортзала!
- **Fish Drama 3:** `[triumphant]В твоей истории — 16 разных недель с одним и тем же упражнением. Оно уже выдало тебе <slow>тапочки и пульт от спортзала!</slow>`
- **Image prompt:** An anthropomorphic kettlebell lounges in a bathrobe inside an exercise-bench inn, its striped gym bag under the chair. A tiny towel butler presents giant fluffy slippers on a tray while the guest points a remote at a treadmill.

### `repertoire.new_exercise_months`

**Правило:** Накопить месяцы, в которых впервые выполнено новое упражнение. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** месяц открытий. **Источник:** `available`.

#### 1. Крот вышел в разведку

- **ID:** `repertoire.new_exercise_months:t1`
- **Порог:** 2 месяц открытий
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** В 2 разных месяцах ты впервые выполнял новые упражнения. Крот-картограф выглянул из привычного тоннеля: о, тут ещё целый зал!
- **Fish Drama 3:** `[warm]В 2 разных месяцах ты впервые выполнял новые упражнения. Крот-картограф выглянул из привычного тоннеля: <emphasis>о, тут ещё целый зал!</emphasis>`
- **Image prompt:** A curious mole cartographer in a headlamp emerges from a tunnel with an open folding atlas. Two freshly uncovered alcoves hold a resistance band and a step platform, and the mole marks their locations with blank tabs.

#### 2. Атласу тесно

- **ID:** `repertoire.new_exercise_months:t2`
- **Порог:** 4 месяц открытий
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Набралось 4 разных месяца, в которых ты впервые выполнял новые упражнения. Крот-картограф раскрыл атлас — на коленях уже тесно!
- **Fish Drama 3:** `[confident]Набралось 4 разных месяца, в которых ты впервые выполнял новые упражнения. Крот-картограф раскрыл атлас — <emphasis>на коленях уже тесно!</emphasis>`
- **Image prompt:** A mole cartographer in a headlamp wrestles with a folding atlas spilling across a worktable. Four branching tunnels reveal a band, a step, a bench and a bar; the mole uses both paws to stop the expanding map sliding away.

#### 3. Глобус с пропиской

- **ID:** `repertoire.new_exercise_months:t3`
- **Порог:** 8 месяц открытий
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В 8 разных месяцах ты впервые выполнял новые упражнения. Твой атлас разросся: крот-картограф теперь живёт в глобусе!
- **Fish Drama 3:** `[triumphant]В 8 разных месяцах ты впервые выполнял новые упражнения. Твой атлас разросся: <slow>крот-картограф теперь живёт в глобусе!</slow>`
- **Image prompt:** A mole cartographer in a headlamp lounges inside a huge hinged globe turned into a home. Its enormous folding atlas spills out as a front path, and a resistance band stretched between the globe's halves holds tiny freshly washed socks.

### `repertoire.machine_exercises`

**Правило:** Познакомиться с разными упражнениями на тренажёре. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение на тренажёре. **Источник:** `available`.

#### 1. Железо, будем знакомы

- **ID:** `repertoire.machine_exercises:t1`
- **Порог:** 2 упражнение на тренажёре
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя в атласе 2 разных упражнения на тренажёре. Робот-смотритель расставляет первые экспонаты — железо обживается.
- **Fish Drama 3:** `[warm]У тебя в атласе 2 разных упражнения на тренажёре. [playful]Робот-смотритель расставляет первые экспонаты — железо обживается.`
- **Image prompt:** A small square-headed robot with clamp hands places a lat pulldown bar and a braided cable rope in an open display cabinet, leaning back proudly while the rope curls over the shelf edge like a curious tail.

#### 2. Бюро железных знакомств

- **ID:** `repertoire.machine_exercises:t2`
- **Порог:** 5 упражнение на тренажёре
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Теперь в твоём атласе 5 разных упражнений на тренажёре. Робот-смотритель просит железо не толпиться у витрины.
- **Fish Drama 3:** `[confident]Теперь в твоём атласе 5 разных упражнений на тренажёре. [playful]Робот-смотритель просит железо не толпиться у витрины.`
- **Image prompt:** The square-headed robot extends its display cabinet into a fan of five shelves, sorting a pulldown bar, cable rope, V-handle, ankle cuff and single grip; two attachments crowd one shelf as its clamp ushers them apart.

#### 3. Билет в собственный музей

- **ID:** `repertoire.machine_exercises:t3`
- **Порог:** 10 упражнение на тренажёре
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоём атласе уже 10 разных упражнений на тренажёре. Робот-смотритель открыл целый музей — и сам купил билет.
- **Fish Drama 3:** `[triumphant]В твоём атласе уже 10 разных упражнений на тренажёре. [playful]Робот-смотритель открыл целый музей — <slow>и сам купил билет.</slow>`
- **Image prompt:** The square-headed robot feeds a blank ticket into the entrance turnstile of its own miniature exercise museum; ten distinct machine attachments fill curved display racks behind it, while its free clamp points proudly back at itself.

### `repertoire.timed_exercises`

**Правило:** Познакомиться с разными упражнениями на время и растяжку. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение на время. **Источник:** `available`.

#### 1. Знакомство с песком

- **ID:** `repertoire.timed_exercises:t1`
- **Порог:** 2 упражнение на время
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты знаешь уже 2 разных упражнения на время и растяжку. Песочные часы шуршат: «Приятно познакомиться!»
- **Fish Drama 3:** `[warm]Ты знаешь уже 2 разных упражнения на время и растяжку. [playful]Песочные часы шуршат: «Приятно познакомиться!»`
- **Image prompt:** A squat hourglass with mitten hands and short feet stands beside a half-unrolled exercise mat, offering a neatly looped stretching strap with one hand and a shy little greeting with the other.

#### 2. У времени есть варианты

- **ID:** `repertoire.timed_exercises:t2`
- **Порог:** 5 упражнение на время
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоём репертуаре 5 разных упражнений на время и растяжку. Песочные часы развернули коврик-гармошку: вариантов хватает!
- **Fish Drama 3:** `[confident]В твоём репертуаре 5 разных упражнений на время и растяжку. [playful]Песочные часы развернули коврик-гармошку: вариантов хватает!`
- **Image prompt:** The squat hourglass with mitten hands pulls open an accordion-fold exercise mat with five broad panels; a stretching strap loops loosely over one arm, while its short feet brace against the comically expanding mat.

#### 3. Будильник за первой партой

- **ID:** `repertoire.timed_exercises:t3`
- **Порог:** 10 упражнение на время
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоём атласе уже 10 разных упражнений на время и растяжку. Песочные часы открыли школу терпения — будильник сел за первую парту.
- **Fish Drama 3:** `[triumphant]В твоём атласе уже 10 разных упражнений на время и растяжку. [playful]Песочные часы открыли школу терпения — <slow>будильник сел за первую парту.</slow>`
- **Image prompt:** The squat hourglass with mitten hands teaches a tiny classroom of alarm clocks seated at desks made from rolled exercise mats; the front clock eagerly raises a bell like a hand, while the hourglass calmly rests its hands together.

### `repertoire.five_exercise_days`

**Правило:** Накопить дни с результатами по пяти разным упражнениям. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день с пятью упражнениями. **Источник:** `available`.

#### 1. Кастинг пяти движений

- **ID:** `repertoire.five_exercise_days:t1`
- **Порог:** 1 день с пятью упражнениями
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** За один день ты записал результаты по пяти разным упражнениям. Однообразие не прошло кастинг.
- **Fish Drama 3:** `[warm] За один день ты записал результаты по пяти разным упражнениям. Однообразие не прошло кастинг.`
- **Image prompt:** A badger stage manager lifts a small curtain to welcome a dumbbell, kettlebell, resistance band, step platform and medicine ball onto a compact stage. Each prop leans forward as if nervously waiting for its first cue.

#### 2. Кулисы набирают ход

- **ID:** `repertoire.five_exercise_days:t2`
- **Порог:** 5 день с пятью упражнениями
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 5 дней с результатами по пяти разным упражнениям в каждом. Репертуар освоился — теперь сам двигает кулисы.
- **Fish Drama 3:** `[confident] У тебя уже <emphasis>5 дней</emphasis> с результатами по пяти разным упражнениям в каждом. Репертуар освоился — теперь сам двигает кулисы.`
- **Image prompt:** A badger stage manager turns a hand crank beside a revolving stage carrying a dumbbell, kettlebell, resistance band, step platform and medicine ball. The exercise props take turns at the front edge like a newly organized troupe.

#### 3. Гантели вызывают такси

- **ID:** `repertoire.five_exercise_days:t3`
- **Порог:** 15 день с пятью упражнениями
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 15 дней с результатами по пяти разным упражнениям в каждом. Публика просит на бис, но гантели уже вызвали себе такси.
- **Fish Drama 3:** `[triumphant] Ты накопил 15 дней с результатами по пяти разным упражнениям в каждом. Публика просит на бис, но <slow>гантели уже вызвали себе такси.</slow>`
- **Image prompt:** A badger stage manager drives a tiny taxi away from a theater curtain. A kettlebell and medicine ball squeeze into the back seat, a dumbbell sticks through a side window, and a resistance band secures a step platform to the roof.

### `repertoire.repertoire_months`

**Правило:** Накопить месяцы с результатами минимум по трём разным упражнениям. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** месяц с тремя упражнениями. **Источник:** `available`.

#### 1. Первые ростки репертуара

- **ID:** `repertoire.repertoire_months:t1`
- **Порог:** 2 месяц с тремя упражнениями
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За плечами у тебя 2 месяца с результатами минимум по трём разным упражнениям в каждом. В теплице репертуара проклюнулись гантели.
- **Fish Drama 3:** `[warm] За плечами у тебя 2 месяца с результатами минимум по трём разным упражнениям в каждом. В теплице репертуара проклюнулись гантели.`
- **Image prompt:** A small snail carries a shell-shaped greenhouse containing two planting trays, each sprouting a dumbbell vine, a kettlebell stem and a curling resistance-band shoot. The snail carefully waters the nearest tray.

#### 2. Лейке нужна лестница

- **ID:** `repertoire.repertoire_months:t2`
- **Порог:** 6 месяц с тремя упражнениями
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В копилке уже 6 месяцев, в каждом ты записал результаты минимум по трём разным упражнениям. Репертуар разросся — лейка просит лестницу.
- **Fish Drama 3:** `[confident] В копилке уже <emphasis>6 месяцев</emphasis>, в каждом ты записал результаты минимум по трём разным упражнениям. Репертуар разросся — лейка просит лестницу.`
- **Image prompt:** A small snail carries an expanded shell greenhouse with six terraced planting beds. Dumbbell vines, kettlebell stems and resistance-band shoots lean outward as the snail uses a long watering spout to reach the highest bed.

#### 3. Гантелям нужен агроном

- **ID:** `repertoire.repertoire_months:t3`
- **Порог:** 12 месяц с тремя упражнениями
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 12 месяцев с результатами минимум по трём разным упражнениям в каждом. Репертуар разросся — гантелям нужен агроном.
- **Fish Drama 3:** `[triumphant] Ты накопил 12 месяцев с результатами минимум по трём разным упражнениям в каждом. Репертуар разросся — <slow>гантелям нужен агроном.</slow>`
- **Image prompt:** A small snail stands beside its enormous shell greenhouse, now bursting with exercise-shaped plants. A ripe kettlebell on a vine returns the favor by holding a watering can over the startled snail, while dumbbell sprouts peer out.

## Вес и объём

### `volume.volume`

**Правило:** Накопить учётный объём: повторения, умноженные на сохранённый вес. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** килограмм объёма. **Источник:** `available`.

#### 1. Погрузчик вышел на смену

- **ID:** `volume.volume:t1`
- **Порог:** 1000 килограмм объёма
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя в журнале уже 1 000 кг учётного объёма: повторы, умноженные на сохранённый вес. Погрузчик надел каску — теперь он при деле.
- **Fish Drama 3:** `[warm] У тебя в журнале уже 1 000 кг учётного объёма: повторы, умноженные на сохранённый вес. [playful] Погрузчик надел каску — теперь он при деле.`
- **Image prompt:** A compact forklift driven by a rubber duck in a work helmet raises a small pallet of barbell plates. The duck leans forward over the controls while one neatly stacked bundle balances just above the floor.

#### 2. Звезда грузового двора

- **ID:** `volume.volume:t2`
- **Порог:** 10000 килограмм объёма
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 10 000 кг учётного объёма — суммы повторов, умноженных на сохранённый вес. На складе железа погрузчик стал местной знаменитостью.
- **Fish Drama 3:** `[confident] В твоей истории уже 10 000 кг учётного объёма — суммы повторов, умноженных на сохранённый вес. [playful] На складе железа погрузчик стал местной знаменитостью.`
- **Image prompt:** A rubber duck in a work helmet steers a compact forklift carrying three tidy towers of barbell plates. It threads between packed storage racks, with one wheel turned and the duck proudly leaning out to check the load.

#### 3. Склад с доставкой

- **ID:** `volume.volume:t3`
- **Порог:** 50000 килограмм объёма
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 50 000 кг учётного объёма: повторы умножались на сохранённый вес и складывались в историю. Погрузчик решил не мелочиться — увёз склад целиком.
- **Fish Drama 3:** `[triumphant] Ты накопил 50 000 кг учётного объёма: повторы умножались на сохранённый вес и складывались в историю. [playful] Погрузчик решил не мелочиться — <slow>увёз склад целиком.</slow>`
- **Image prompt:** A rubber duck in a work helmet pilots a tiny forklift lifting an entire open-front weight warehouse on one enormous pallet. Racks of barbell plates ride inside; the duck calmly checks a miniature side mirror as the building tilts upward.

### `volume.weighted_sets`

**Правило:** Накопить подходы с положительным сохранённым весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** подход с весом. **Источник:** `available`.

#### 1. Первый взмах палочки

- **ID:** `volume.weighted_sets:t1`
- **Порог:** 10 подход с весом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты записал 10 подходов с сохранённым весом больше нуля. В железном оркестре первая гантель уже ждёт взмаха палочки.
- **Fish Drama 3:** `[warm] Ты записал 10 подходов с сохранённым весом больше нуля. [playful] В железном оркестре первая гантель уже ждёт взмаха палочки.`
- **Image prompt:** A little robot conductor on spring legs raises a baton toward a single animated dumbbell beside a small drum. The dumbbell grips two drumsticks with flexible metal arms, waiting attentively as the robot gives an encouraging nod.

#### 2. Железо вступает хором

- **ID:** `volume.weighted_sets:t2`
- **Порог:** 50 подход с весом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоём журнале уже 50 подходов с сохранённым весом больше нуля. Железный оркестр разросся: у каждой гантели своя партия.
- **Fish Drama 3:** `[confident] В твоём журнале уже 50 подходов с сохранённым весом больше нуля. [playful] Железный оркестр разросся: у каждой гантели своя партия.`
- **Image prompt:** A little robot conductor on spring legs directs a semicircle of animated dumbbells playing drums, cymbals and a xylophone. Its baton sweeps sideways while the dumbbell musicians lean into their instruments in coordinated rows.

#### 3. Аплодисменты тяжёлого состава

- **ID:** `volume.weighted_sets:t3`
- **Порог:** 150 подход с весом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** За всё время у тебя набралось 150 подходов с сохранённым весом больше нуля. Железный оркестр аплодирует — гантели хлопают блинами.
- **Fish Drama 3:** `[triumphant] За всё время у тебя набралось 150 подходов с сохранённым весом больше нуля. [playful] Железный оркестр аплодирует — <slow>гантели хлопают блинами.</slow>`
- **Image prompt:** A little robot conductor on spring legs takes a deep bow on a podium. Around it, an orchestra of animated dumbbells applauds by clapping detached weight plates together, while the robot holds a comically tiny dumbbell as its baton.

### `volume.weighted_reps`

**Правило:** Накопить повторения с положительным сохранённым весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** повторение с весом. **Источник:** `available`.

#### 1. Фундамент из повторений

- **ID:** `volume.weighted_reps:t1`
- **Порог:** 100 повторение с весом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 100 повторений с сохранённым весом больше нуля. Первый ряд железной плотины на месте!
- **Fish Drama 3:** `[warm] В твоей истории уже 100 повторений с сохранённым весом больше нуля. [playful] Первый ряд железной плотины на месте!`
- **Image prompt:** An industrious beaver with a broad paddle tail rolls a dumbbell into a low dam foundation across a narrow stream. Two more dumbbells lie neatly beside a wooden wheelbarrow, while a curious duck watches from the opposite bank.

#### 2. Плотина набирает размах

- **ID:** `volume.weighted_reps:t2`
- **Порог:** 500 повторение с весом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 500 повторений с сохранённым весом больше нуля. Плотина растёт, бобр уже ходит с видом главного инженера.
- **Fish Drama 3:** `[confident] Ты накопил <emphasis>500 повторений</emphasis> с сохранённым весом больше нуля. [playful] Плотина растёт, бобр уже ходит с видом главного инженера.`
- **Image prompt:** The same broad-tailed beaver stands on a scaffold beside a growing dam made of interlocked dumbbells. Holding a wooden mallet, it inspects the upper row with exaggerated seriousness as the duck tests the rising water behind the structure.

#### 3. Утка требует аквапарк

- **ID:** `volume.weighted_reps:t3`
- **Порог:** 1500 повторение с весом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей копилке 1500 повторений с сохранённым весом больше нуля. Железная плотина готова — утка требует аквапарк.
- **Fish Drama 3:** `[triumphant] В твоей копилке <emphasis>1500 повторений</emphasis> с сохранённым весом больше нуля. Железная плотина готова — <slow>утка требует аквапарк.</slow>`
- **Image prompt:** The broad-tailed beaver unveils a towering dumbbell dam with a curling water chute built into its spillway. The duck eagerly waits at the chute entrance with a tiny swimming ring, while the beaver stares at an enormous queue of ducklings.

### `volume.volume_days`

**Правило:** Накопить дни с положительным учётным объёмом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** день с объёмом. **Источник:** `available`.

#### 1. Лейка выходит на участок

- **ID:** `volume.volume_days:t1`
- **Порог:** 3 день с объёмом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 3 дня с учтённым объёмом больше нуля. Лейка вышла на участок и уже командует тремя ростками.
- **Fish Drama 3:** `[warm] Ты накопил 3 дня с учтённым объёмом больше нуля. [playful] Лейка вышла на участок и уже командует тремя ростками.`
- **Image prompt:** A squat enamel watering can with little boots and expressive eyes tends three seedlings in separate square pots. It raises its spout like a tiny foreman giving instructions, with a small trowel resting across a crate beside the pots.

#### 2. Подоконник больше не справляется

- **ID:** `volume.volume_days:t2`
- **Порог:** 10 день с объёмом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории 10 дней с учтённым объёмом больше нуля, не обязательно подряд. Лейка уже заведует целой оранжереей.
- **Fish Drama 3:** `[confident] В твоей истории <emphasis>10 дней</emphasis> с учтённым объёмом больше нуля, не обязательно подряд. [playful] Лейка уже заведует целой оранжереей.`
- **Image prompt:** The same booted enamel watering can strides down the aisle of a compact greenhouse containing ten square plant pots on stepped shelves. Its long spout reaches an upper seedling while curling vines spill through the open doorway.

#### 3. Повышение до фонтана

- **ID:** `volume.volume_days:t3`
- **Порог:** 25 день с объёмом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 25 дней с учтённым объёмом больше нуля. Сад разросся так, что лейка повысила себя до фонтана.
- **Fish Drama 3:** `[triumphant] У тебя уже <emphasis>25 дней</emphasis> с учтённым объёмом больше нуля. Сад разросся так, что <slow>лейка повысила себя до фонтана.</slow>`
- **Image prompt:** The booted enamel watering can reclines proudly in a deckchair at the center of a lush greenhouse garden. Water arcs from its spout into branching irrigation channels feeding twenty-five square pots, while its boots dangle over the chair edge.

### `volume.weighted_days`

**Правило:** Накопить дни с подходами с положительным весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90, 160, 260. Не подряд; без повышения нагрузки ради награды. **Единица:** день с весом. **Источник:** `available`.

#### 1. Железный гость

- **ID:** `volume.weighted_days:t1`
- **Порог:** 3 день с весом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 3 дня с подходами с весом больше нуля. Железо пока заходит в гости, но кружку уже присмотрело.
- **Fish Drama 3:** `[warm] Ты накопил 3 дня с подходами с весом больше нуля. Железо пока заходит в гости, но <emphasis>кружку уже присмотрело</emphasis>.`
- **Image prompt:** A squat kettlebell with short arms and feet stands at a gym doorway, offering a steaming mug with both hands. One foot hovers over the threshold, and a neatly packed gym bag rests beside the door.

#### 2. Тапочки для гири

- **ID:** `volume.weighted_days:t2`
- **Порог:** 10 день с весом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 10 дней с подходами с весом больше нуля. Железо освоилось и оставило у двери тапочки.
- **Fish Drama 3:** `[playful] В твоей истории уже 10 дней с подходами с весом больше нуля. Железо освоилось и оставило у двери <emphasis>тапочки</emphasis>.`
- **Image prompt:** A squat kettlebell with short arms and feet slips into oversized house slippers beside a gym doorway. It nudges its gym bag neatly under a bench, with a steaming mug waiting on the seat.

#### 3. Чайник знает своих

- **ID:** `volume.weighted_days:t3`
- **Порог:** 25 день с весом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя накопилось 25 дней с подходами с весом больше нуля. Железо уже знает, где чайник, и зовёт на чай.
- **Fish Drama 3:** `[confident] У тебя накопилось 25 дней с подходами с весом больше нуля. Железо уже знает, где чайник, и <emphasis>зовёт на чай</emphasis>.`
- **Image prompt:** A squat kettlebell with short arms and slippered feet pours tea from a kettle at a weight bench turned into a tea table. It confidently offers a second mug toward an empty stool, with a squat rack behind it.

#### 4. Диван между подходами

- **ID:** `volume.weighted_days:t4`
- **Порог:** 50 день с весом
- **Подтверждённая практика:** минимум 160 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей копилке 50 дней с подходами с весом больше нуля. Железо решило, что это надолго, и притащило в зал диван.
- **Fish Drama 3:** `[excited] В твоей копилке 50 дней с подходами с весом больше нуля. Железо решило, что это надолго, и притащило в зал <emphasis>диван</emphasis>.`
- **Image prompt:** A squat kettlebell with short arms and slippered feet proudly slides a plush sofa into place beside a squat rack. A tea tray balances on the armrest, and its old gym bag is already tucked underneath.

#### 5. Тише, зал уснул

- **ID:** `volume.weighted_days:t5`
- **Порог:** 100 день с весом
- **Подтверждённая практика:** минимум 260 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя накопилось 100 дней с подходами с весом больше нуля. Железо обжилось настолько, что теперь укладывает зал спать.
- **Fish Drama 3:** `[triumphant] У тебя накопилось 100 дней с подходами с весом больше нуля. [playful] Железо обжилось настолько, <slow>что теперь</slow> укладывает зал спать.`
- **Image prompt:** A large squat kettlebell with short arms and slippered feet tucks a miniature gym into a little bed. The squat rack and bench nestle under a blanket, while a tiny barbell rests on the pillow like a sleepy pet.

### `volume.volume_weeks`

**Правило:** Накопить недели с учётным объёмом от пятисот килограммов. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя с объёмом. **Источник:** `available`.

#### 1. Железо отчалило

- **ID:** `volume.volume_weeks:t1`
- **Порог:** 2 неделя с объёмом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 2 недели с учётным объёмом не меньше 500 кг в каждой. Первая партия железа отправилась в плавание.
- **Fish Drama 3:** `[warm] В твоей истории уже 2 недели с учётным объёмом не меньше 500 кг в каждой. Первая партия железа <emphasis>отправилась в плавание</emphasis>.`
- **Image prompt:** A small beaver with a broad flat tail steers a wooden raft across a washbasin. A tidy stack of weight plates sits at the center, and the beaver uses a long paddle to push away from a tiny loading dock.

#### 2. Каюты для блинов

- **ID:** `volume.volume_weeks:t2`
- **Порог:** 6 неделя с объёмом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 6 недель, в каждой — не меньше 500 кг учётного объёма. Железу уже тесно в лодке: пора выдавать ему каюту.
- **Fish Drama 3:** `[confident] Ты накопил 6 недель, в каждой — не меньше 500 кг учётного объёма. [playful] Железу уже тесно в лодке: пора выдавать ему <emphasis>каюту</emphasis>.`
- **Image prompt:** The small flat-tailed beaver stands at the wheel of a cargo barge packed with orderly stacks of weight plates. The vessel nearly fills its washbasin harbor, with a tiny gangplank resting across the rim.

#### 3. Ванне нужен океан

- **ID:** `volume.volume_weeks:t3`
- **Порог:** 12 неделя с объёмом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя накопилось 12 недель с учётным объёмом не меньше 500 кг в каждой. Твой железный флот вырос так, что ванна просит собственный океан.
- **Fish Drama 3:** `[triumphant] У тебя накопилось 12 недель с учётным объёмом не меньше 500 кг в каждой. [playful] Твой железный флот вырос так, <slow>что ванна просит</slow> собственный океан.`
- **Image prompt:** The small flat-tailed beaver commands an enormous cargo ship loaded with weight plates, wedged snugly inside a household bathtub. A rubber duck strains at a towrope ahead of the bow, acting as a miniature tugboat.

### `volume.weight_exercises`

**Правило:** Оставить результаты с положительным весом в разных упражнениях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение с весом. **Источник:** `available`.

#### 1. Два железных знакомства

- **ID:** `volume.weight_exercises:t1`
- **Порог:** 2 упражнение с весом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя сохранены результаты с положительным весом в 2 разных упражнениях. Два знакомства с железом — уже не случайная встреча.
- **Fish Drama 3:** `[warm] У тебя сохранены результаты с положительным весом в 2 разных упражнениях. [playful] Два знакомства с железом — уже не случайная встреча.`
- **Image prompt:** A beaver librarian in square spectacles slides a kettlebell and a dumbbell into two separate shelf cubbies. His broad tail props up a tiny catalog drawer while one paw holds an oversized blank index card.

#### 2. Каталог с характером

- **ID:** `volume.weight_exercises:t2`
- **Порог:** 5 упражнение с весом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей коллекции — сохранённые результаты с положительным весом в 5 разных упражнениях. Железу тесно в записной книжке — пора заводить каталог.
- **Fish Drama 3:** `[confident] В твоей коллекции — сохранённые результаты с положительным весом в 5 разных упражнениях. [playful] Железу тесно в записной книжке — пора заводить каталог.`
- **Image prompt:** The bespectacled beaver librarian rides a rolling ladder past five cubbies holding different weight-training tools. He sorts a fan of blank index cards while his broad tail catches a dumbbell rolling off the return trolley.

#### 3. Читательский билет для железа

- **ID:** `volume.weight_exercises:t3`
- **Порог:** 10 упражнение с весом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты сохранил результаты с положительным весом в 10 разных упражнениях. Штанга получила читательский билет — и обещала не гнуть страницы.
- **Fish Drama 3:** `[triumphant] Ты сохранил результаты с положительным весом в 10 разных упражнениях. [playful] <slow>Штанга получила читательский билет</slow> — и обещала не гнуть страницы.`
- **Image prompt:** A beaver librarian in square spectacles issues a blank library card to a barbell leaning eagerly across the counter. A dumbbell waits behind it, while shelves of training equipment curve around the beaver like a grand reading room.

### `volume.volume_months`

**Правило:** Накопить месяцы с учётным объёмом от пяти тысяч килограммов. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** месяц с объёмом. **Источник:** `available`.

#### 1. Две коробки истории

- **ID:** `volume.volume_months:t1`
- **Порог:** 2 месяц с объёмом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя накопилось 2 месяца с учётным объёмом от 5000 кг в каждом. Хомяк учёта принёс вторую коробку — склад открыт.
- **Fish Drama 3:** `[warm] У тебя накопилось 2 месяца с учётным объёмом от 5000 кг в каждом. [playful] Хомяк учёта принёс вторую коробку — склад открыт.`
- **Image prompt:** A hamster warehouse keeper drives a compact forklift carrying two open crates of weight plates. He leans forward over the steering wheel; a small lunchbox rides beside him, comically oversized compared with the driver.

#### 2. Хомяк расширяет склад

- **ID:** `volume.volume_months:t2`
- **Порог:** 6 месяц с объёмом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоём архиве уже 6 месяцев с учётным объёмом от 5000 кг в каждом. Хомяк учёта расширил склад, но место для обеда отстоял.
- **Fish Drama 3:** `[confident] В твоём архиве уже 6 месяцев с учётным объёмом от 5000 кг в каждом. [playful] Хомяк учёта расширил склад, но место для обеда отстоял.`
- **Image prompt:** A hamster warehouse keeper maneuvers six crates of weight plates on a compact forklift, arranged into two tidy towers. He peers around the load while his lunchbox occupies the entire passenger seat beside him.

#### 3. Склад едет на обед

- **ID:** `volume.volume_months:t3`
- **Порог:** 12 месяц с объёмом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 12 месяцев с учётным объёмом от 5000 кг в каждом. Хомяк перевозит уже сам склад — обед, конечно, едет в кабине.
- **Fish Drama 3:** `[triumphant] Ты накопил 12 месяцев с учётным объёмом от 5000 кг в каждом. [playful] <slow>Хомяк перевозит уже сам склад</slow> — обед, конечно, едет в кабине.`
- **Image prompt:** A hamster warehouse keeper uses his compact forklift to lift an entire miniature warehouse, its twelve open bays packed with weight plates. The building tilts above the forks while his lunchbox sits safely belted into the passenger seat.

### `volume.volume_milestones`

**Правило:** Продолжать большую историю учётного объёма без цели на одну тренировку. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** килограмм объёма. **Источник:** `available`.

#### 1. Первый рейс истории

- **ID:** `volume.volume_milestones:t1`
- **Порог:** 100000 килограмм объёма
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 100 000 кг учётного объёма за свои тренировки. Маленький погрузчик твоей истории уже завёл мотор.
- **Fish Drama 3:** `[warm] Ты накопил 100 000 кг учётного объёма за свои тренировки. Маленький погрузчик твоей истории уже <emphasis>завёл мотор.</emphasis>`
- **Image prompt:** A compact forklift with a square cab carries an open crate of barbell plates toward a low storage rack. One filled pallet already sits on the rack, while another crate waits beside it; each load is neatly stacked.

#### 2. Железный пентхаус

- **ID:** `volume.volume_milestones:t2`
- **Порог:** 250000 килограмм объёма
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 250 000 кг учётного объёма за тренировки. Погрузчик достроил второй этаж: у железа появился пентхаус.
- **Fish Drama 3:** `[confident] В твоей истории уже 250 000 кг учётного объёма за тренировки. [playful] Погрузчик достроил второй этаж: у железа появился <emphasis>пентхаус.</emphasis>`
- **Image prompt:** A compact square-cab forklift raises a pallet of barbell plates to the upper deck of a two-level storage rack. Packed crates fill the lower deck, while a barbell spans the upper edge like a penthouse balcony railing.

#### 3. Кабинет для погрузчика

- **ID:** `volume.volume_milestones:t3`
- **Порог:** 500000 килограмм объёма
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 500 000 кг учётного объёма за свои тренировки. Погрузчик поднял весь склад — и попросил кабинет.
- **Fish Drama 3:** `[triumphant] Ты накопил 500 000 кг учётного объёма за свои тренировки. Погрузчик поднял весь склад — <slow>и попросил кабинет.</slow>`
- **Image prompt:** A compact square-cab forklift hoists an entire open-front warehouse packed with crates of barbell plates. A tiny office desk and swivel chair sit on the warehouse roof, absurdly small above the colossal load.

### `volume.weighted_reps_milestones`

**Правило:** Накопить большую историю повторений с сохранённым весом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 16, 40, 90. Не подряд; без повышения нагрузки ради награды. **Единица:** повторение с весом. **Источник:** `available`.

#### 1. Первый том повторов

- **ID:** `volume.weighted_reps_milestones:t1`
- **Порог:** 5000 повторение с весом
- **Подтверждённая практика:** минимум 16 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** 5 000 повторений с сохранённым весом уже в твоей истории. Дятел-счётчик открыл первый том: стук есть, суеты нет.
- **Fish Drama 3:** `[warm] 5 000 повторений с сохранённым весом уже в твоей истории. Дятел-счётчик открыл первый том: <soft>стук есть, суеты нет.</soft>`
- **Image prompt:** A clockwork woodpecker with a long metal beak shelves a thick ledger in a small branch-shaped bookcase. Another open ledger rests on a desk beneath a dumbbell paperweight, with a tidy bundle of loose pages beside it.

#### 2. Библиотека с характером

- **ID:** `volume.weighted_reps_milestones:t2`
- **Порог:** 15000 повторение с весом
- **Подтверждённая практика:** минимум 40 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал историю из 15 000 повторений с сохранённым весом. Дятел-счётчик расселил их по полкам — библиотека довольно постукивает.
- **Fish Drama 3:** `[confident] Ты собрал историю из 15 000 повторений с сохранённым весом. [playful] Дятел-счётчик расселил их по полкам — библиотека <emphasis>довольно постукивает.</emphasis>`
- **Image prompt:** A clockwork woodpecker with a long metal beak balances on a rolling ladder, sorting thick ledgers into a tall branching bookcase. Several loaded shelves curve around the bird, and a dumbbell anchors the ladder at its base.

#### 3. Гантели в читальном зале

- **ID:** `volume.weighted_reps_milestones:t3`
- **Порог:** 50000 повторение с весом
- **Подтверждённая практика:** минимум 90 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За твои тренировки накопилось 50 000 повторений с сохранённым весом. Теперь дятел-счётчик выдаёт читательские билеты — гантелям.
- **Fish Drama 3:** `[triumphant] За твои тренировки накопилось 50 000 повторений с сохранённым весом. Теперь дятел-счётчик выдаёт читательские билеты — <slow>гантелям.</slow>`
- **Image prompt:** A clockwork woodpecker sits at a library counter, handing a blank borrowing card to a dumbbell with tiny arms. A second dumbbell waits in line, while a towering tree-shaped bookcase of thick ledgers rises behind the bird.

## По намеченному пути

### `plan.complete`

**Правило:** Выполнить исходный план тренировки без заднего уменьшения целей. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** тренировка по плану. **Источник:** `requires_plan`.

#### 1. Маршрут ожил

- **ID:** `plan.complete:t1`
- **Порог:** 1 тренировка по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил первую тренировку по исходному плану, не снижая цели задним числом. У бумажного маршрута появились следы твоих кроссовок.
- **Fish Drama 3:** `[warm]Ты выполнил первую тренировку по исходному плану, не снижая цели задним числом. У бумажного маршрута появились <soft>следы твоих кроссовок.</soft>`
- **Image prompt:** A lively rolled-paper route map with little gloved hands and hiking boots steps onto a low finish platform beside a tiny dumbbell. Its loose paper tail stretches back across a simple winding path.

#### 2. Бумажный попутчик

- **ID:** `plan.complete:t2`
- **Порог:** 5 тренировка по плану
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории 5 тренировок по исходному плану без снижения целей задним числом. Ты превратил план из бумажки в бывалого попутчика.
- **Fish Drama 3:** `[confident]В твоей истории <emphasis>5 тренировок</emphasis> по исходному плану без снижения целей задним числом. Ты превратил план из бумажки в бывалого попутчика.`
- **Image prompt:** The same rolled-paper map explorer climbs a staircase built from closed workout folders, hauling a compact backpack. A long accordion-folded route spills from the pack and neatly follows every step below.

#### 3. План пишет мемуары

- **ID:** `plan.complete:t3`
- **Порог:** 15 тренировка по плану
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил 15 тренировок по исходному плану без снижения целей задним числом. План сел писать мемуары — разумеется, о тебе.
- **Fish Drama 3:** `[triumphant]Ты выполнил <emphasis>15 тренировок</emphasis> по исходному плану без снижения целей задним числом. План сел писать мемуары — <slow>разумеется, о тебе.</slow>`
- **Image prompt:** The same rolled-paper map perches on a tower of workout folders at an enormous blank open book. It grips an absurdly oversized quill like a grand biographer, while a tiny dumbbell holds a curling page flat.

### `plan.exercise`

**Правило:** Завершить обязательные подходы упражнений с исходными целями. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение по плану. **Источник:** `requires_plan`.

#### 1. Первые крепкие стыки

- **ID:** `plan.exercise:t1`
- **Порог:** 5 упражнение по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты завершил 5 упражнений: все обязательные подходы выполнены по исходным целям. Первые кирпичики на месте — прораб-бобр одобряет.
- **Fish Drama 3:** `[warm]Ты завершил 5 упражнений: все обязательные подходы выполнены по исходным целям. Первые кирпичики на месте — <soft>прораб-бобр одобряет.</soft>`
- **Image prompt:** A beaver carpenter in a hard hat assembles a small wooden dumbbell on a low workbench. One paw steadies the handle while the other taps a squared weight block into place with a wooden mallet.

#### 2. Стройка набрала ход

- **ID:** `plan.exercise:t2`
- **Порог:** 20 упражнение по плану
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей копилке 20 упражнений со всеми обязательными подходами по исходным целям. Ты строишь историю — у прораба-бобра уже каска подпрыгивает.
- **Fish Drama 3:** `[confident]В твоей копилке <emphasis>20 упражнений</emphasis> со всеми обязательными подходами по исходным целям. Ты строишь историю — у прораба-бобра уже каска подпрыгивает.`
- **Image prompt:** The same beaver carpenter operates a hand-cranked hoist beside a huge wooden dumbbell under construction. A squared weight block rises toward the handle, scaffolding hugs both ends, and the beaver's hard hat bounces above its head.

#### 3. Гантельная прописка

- **ID:** `plan.exercise:t3`
- **Порог:** 60 упражнение по плану
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** За это время ты завершил 60 упражнений со всеми обязательными подходами по исходным целям. Бобр сдал гантельный дворец — и тут же заселился.
- **Fish Drama 3:** `[triumphant]За это время ты завершил <emphasis>60 упражнений</emphasis> со всеми обязательными подходами по исходным целям. Бобр сдал гантельный дворец — <slow>и тут же заселился.</slow>`
- **Image prompt:** The same beaver carpenter relaxes in a hammock inside a colossal wooden dumbbell turned into a house. Its handle forms a porch between two blocky weight rooms; a mallet and hard hat rest beside the doorway.

### `plan.repeat_program`

**Правило:** Выполнить одну и ту же версию программы в разные дни. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день с программой. **Источник:** `requires_plan`.

#### 1. Знакомый поворот

- **ID:** `plan.repeat_program:t1`
- **Порог:** 3 день с программой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил одну и ту же версию программы в 3 разных дня. Карта знакомая, а каждая отметка — новая история.
- **Fish Drama 3:** `[warm]Ты выполнил одну и ту же версию программы в <emphasis>3 разных дня</emphasis>. [playful]Карта знакомая, а каждая отметка — новая история.`
- **Image prompt:** A small tortoise with a canvas satchel unrolls a route map beside an arched trail gate. Three footprint-shaped paving stones mark separate arrivals, and the tortoise happily recognizes the bend drawn on its map.

#### 2. Свой на маршруте

- **ID:** `plan.repeat_program:t2`
- **Порог:** 8 день с программой
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Одна и та же версия программы выполнена в 8 разных дней — ты возвращаешься к знакомому маршруту. Карта уже встречает тебя как своего.
- **Fish Drama 3:** `[confident]Одна и та же версия программы выполнена в <emphasis>8 разных дней</emphasis> — ты возвращаешься к знакомому маршруту. [playful]Карта уже встречает тебя как своего.`
- **Image prompt:** A small tortoise with a canvas satchel lounges beside an arched trail gate, holding its familiar route map like a welcome placard. Eight footprint-shaped paving stones curve toward the gate, where its walking stick rests.

#### 3. Навигатор для маршрута

- **ID:** `plan.repeat_program:t3`
- **Порог:** 20 день с программой
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил одну и ту же версию программы в 20 разных дней. Теперь маршрут сам спрашивает у тебя дорогу.
- **Fish Drama 3:** `[triumphant]Ты выполнил одну и ту же версию программы в <emphasis>20 разных дней</emphasis>. <slow>Теперь</slow> [playful]маршрут сам спрашивает у тебя дорогу.`
- **Image prompt:** A small tortoise with a canvas satchel runs a tiny directions desk beneath an arched trail gate, spreading its familiar map across the counter. A winding ribbon of road with little arms leans forward and shrugs helplessly, seeking guidance.

### `plan.chapters`

**Правило:** Выполнить исходные планы разных шаблонов программы. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** шаблон программы. **Источник:** `requires_plan`.

#### 1. Два тома движения

- **ID:** `plan.chapters:t1`
- **Порог:** 2 шаблон программы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил исходные планы 2 разных шаблонов программы. Библиотека тренировок открыта — шептать не обязательно!
- **Fish Drama 3:** `[warm]Ты выполнил исходные планы <emphasis>2 разных шаблонов программы</emphasis>. [playful]Библиотека тренировок открыта — шептать не обязательно!`
- **Image prompt:** A cheerful beaver librarian in a pocketed waistcoat opens two chunky workout binders on a low reading desk. Their pages show distinct exercise diagrams, and the beaver holds its paws wide to welcome the first visitors.

#### 2. Тележка новых глав

- **ID:** `plan.chapters:t2`
- **Порог:** 4 шаблон программы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Уже 4 разных шаблона программы: ты выполнил их исходные планы. Бобр-библиотекарь везёт пополнение на тележке.
- **Fish Drama 3:** `[confident]Уже <emphasis>4 разных шаблона программы</emphasis>: ты выполнил их исходные планы. [playful]Бобр-библиотекарь везёт пополнение на тележке.`
- **Image prompt:** A beaver librarian in a pocketed waistcoat proudly pushes a compact library trolley carrying four thick workout binders with distinct exercise diagrams. Its broad tail steadies the rear wheel as it rounds a reading desk.

#### 3. Гантель с читательским билетом

- **ID:** `plan.chapters:t3`
- **Порог:** 6 шаблон программы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил исходные планы 6 разных шаблонов программы. Даже гантель пришла к тебе за читательским билетом.
- **Fish Drama 3:** `[triumphant]Ты выполнил исходные планы <emphasis>6 разных шаблонов программы</emphasis>. <slow>Даже гантель</slow> [playful]пришла к тебе за читательским билетом.`
- **Image prompt:** A beaver librarian in a pocketed waistcoat sits behind a desk built from six chunky workout binders. It hands a blank library card to an eager anthropomorphic dumbbell, which stands on tiptoe and carries a tiny book bag.

### `plan.full_weeks`

**Правило:** Накопить недели с минимум одной полностью выполненной исходной тренировкой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя с планом. **Источник:** `requires_plan`.

#### 1. Первые шорохи плана

- **ID:** `plan.full_weeks:t1`
- **Порог:** 2 неделя с планом
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей копилке 2 недели, в каждой — хотя бы одна полностью выполненная исходная тренировка. Хомяк-архивариус довольно шуршит.
- **Fish Drama 3:** `[warm]В твоей копилке 2 недели, в каждой — хотя бы одна полностью выполненная исходная тренировка. <soft>Хомяк-архивариус довольно шуршит.</soft>`
- **Image prompt:** A tuft-haired hamster archivist lowers two rolled workout plans into a small open filing crate, standing on tiptoe with puffed cheeks. The rolls lean together while the hamster steadies the crate with one hind paw.

#### 2. Тележка полных недель

- **ID:** `plan.full_weeks:t2`
- **Порог:** 6 неделя с планом
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Накоплено 6 недель, в каждой ты полностью выполнил хотя бы одну исходную тренировку. Хомяк выкатил тележку: папки пошли оптом.
- **Fish Drama 3:** `[confident]Накоплено 6 недель, в каждой ты полностью выполнил хотя бы одну исходную тренировку. [playful]Хомяк выкатил тележку: папки пошли оптом.`
- **Image prompt:** A tuft-haired hamster archivist pushes a low filing cart stacked with six rolled workout plans. It braces both paws against the handle while one hind foot rides the cart, turning a careful delivery into a tiny scooter trip.

#### 3. Архив за щеками

- **ID:** `plan.full_weeks:t3`
- **Порог:** 12 неделя с планом
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 12 недель с хотя бы одной полностью выполненной исходной тренировкой в каждой. Хомяк открыл архив. Запасной — за щеками.
- **Fish Drama 3:** `[triumphant]Ты накопил 12 недель с хотя бы одной полностью выполненной исходной тренировкой в каждой. Хомяк открыл архив. <slow>Запасной — за щеками.</slow>`
- **Image prompt:** A tuft-haired hamster archivist stands before an open cabinet packed with rolled workout plans. Its enormous puffed cheeks each unfold into a miniature filing drawer, and it calmly files one last roll into this ridiculous backup archive.

### `plan.plan_streak`

**Правило:** Собрать серию недель с полностью выполненной исходной тренировкой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя подряд с планом. **Источник:** `requires_plan`.

#### 1. Первый пых по плану

- **ID:** `plan.plan_streak:t1`
- **Порог:** 2 неделя подряд с планом
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** За 2 недели подряд ты каждую неделю полностью выполнил хотя бы одну исходную тренировку. Чайник-паровоз дал первый довольный пых.
- **Fish Drama 3:** `[warm]За 2 недели подряд ты каждую неделю полностью выполнил хотя бы одну исходную тренировку. Чайник-паровоз дал первый <soft>довольный пых.</soft>`
- **Image prompt:** A squat kettle locomotive pulls two coupled carriages along a short curve of track. Its spout releases a single plump puff of steam, while the tilted lid reveals a tiny empty driver's cab with a lever waiting inside.

#### 2. Рейс для печеньки

- **ID:** `plan.plan_streak:t2`
- **Порог:** 4 неделя подряд с планом
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя 4 недели подряд с хотя бы одной полностью выполненной исходной тренировкой в каждой. Чайник-паровоз набрал ход, печенька ждёт посадки.
- **Fish Drama 3:** `[confident]У тебя 4 недели подряд с хотя бы одной полностью выполненной исходной тренировкой в каждой. [playful]Чайник-паровоз набрал ход, печенька ждёт посадки.`
- **Image prompt:** A squat kettle locomotive draws four coupled carriages past a tiny platform. An eager biscuit with little arms and legs reaches for the cab handrail, one foot raised toward the step, as steam curls from the kettle spout.

#### 3. Крошечный машинист экспресса

- **ID:** `plan.plan_streak:t3`
- **Порог:** 8 неделя подряд с планом
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя 8 недель подряд, в каждой — хотя бы одна полностью выполненная исходная тренировка. Чайник-паровоз стал экспрессом. Машинист — печенька.
- **Fish Drama 3:** `[triumphant]У тебя 8 недель подряд, в каждой — хотя бы одна полностью выполненная исходная тренировка. Чайник-паровоз стал экспрессом. <slow>Машинист — печенька.</slow>`
- **Image prompt:** A squat kettle locomotive leads eight coupled carriages around a sweeping bend. Beneath its flipped-open lid, a biscuit driver grips an oversized control lever with both arms, shedding a few crumbs onto the cab floor as the spout whistles.

### `plan.planned_sets`

**Правило:** Достичь исходной цели в запланированных подходах. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** подход по цели. **Источник:** `requires_plan`.

#### 1. Первая опора

- **ID:** `plan.planned_sets:t1`
- **Порог:** 10 подход по цели
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Первые 10 запланированных подходов с достигнутой исходной целью — в твоей копилке. Ты заложил мост от «намечено» к «сделано».
- **Fish Drama 3:** `[warm] Первые 10 запланированных подходов с достигнутой исходной целью — в твоей копилке. [playful] Ты заложил мост от «намечено» к «сделано».`
- **Image prompt:** A squat beaver with a broad paddle tail carefully fits the first wooden beam between two bridge supports, checking its curve against a matching wooden template; a few fitted planks form a short walkway beside its paws.

#### 2. План нанял прораба

- **ID:** `plan.planned_sets:t2`
- **Порог:** 50 подход по цели
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 50 запланированных подходов, в которых достигнута исходная цель. План перестал быть бумажкой и устроился прорабом.
- **Fish Drama 3:** `[confident] У тебя уже 50 запланированных подходов, в которых достигнута исходная цель. [playful] План перестал быть бумажкой и устроился прорабом.`
- **Image prompt:** The broad-tailed beaver stands on a growing arched wooden bridge, guiding a suspended beam into its matching slot with a hooked pole; completed spans curve behind it, while a rolled construction drawing rests at its feet.

#### 3. Мост для важной утки

- **ID:** `plan.planned_sets:t3`
- **Порог:** 150 подход по цели
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты достиг исходной цели в 150 запланированных подходах за всё время. Мост открыт для особо важной персоны: резиновой утки.
- **Fish Drama 3:** `[triumphant] Ты достиг исходной цели в 150 запланированных подходах за всё время. Мост открыт для особо важной персоны: [playful] <slow>резиновой утки.</slow>`
- **Image prompt:** The broad-tailed beaver operates an enormous drawbridge crank, raising two mighty wooden bridge leaves so a single rubber duck in a tiny soap dish can sail beneath; the minute passenger sits directly below the grand opening.

### `plan.planned_days`

**Правило:** Накопить дни с результатами по исходному согласованному плану. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** день по плану. **Источник:** `requires_plan`.

#### 1. Маршрут проснулся

- **ID:** `plan.planned_days:t1`
- **Порог:** 3 день по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 3 дня с результатами по исходному согласованному плану. Маршрут ожил — спешка в билет не входит.
- **Fish Drama 3:** `[warm] В твоей истории уже 3 дня с результатами по исходному согласованному плану. [playful] Маршрут ожил — спешка в билет не входит.`
- **Image prompt:** A small turtle opens an accordion-fold route map across a ridged wheeled suitcase, holding one corner with its front foot; the map's winding path aligns with a short stretch of stepping stones just ahead.

#### 2. Чемодан в деле

- **ID:** `plan.planned_days:t2`
- **Порог:** 10 день по плану
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 10 дней с результатами по исходному согласованному плану. Чемодан уже освоился: теперь возит не носки, а кусочек маршрута.
- **Fish Drama 3:** `[playful] Ты накопил 10 дней с результатами по исходному согласованному плану. Чемодан уже освоился: теперь возит <emphasis>не носки, а кусочек маршрута.</emphasis>`
- **Image prompt:** The small turtle pulls its ridged wheeled suitcase as the open lid feeds out a winding ribbon of miniature road; the accordion map sits in an inner pocket, and the new road curls neatly around a pebble ahead.

#### 3. Курс без суеты

- **ID:** `plan.planned_days:t3`
- **Порог:** 25 день по плану
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** За твоими плечами 25 дней с результатами по исходному согласованному плану. Даже чемодан понял: маршрут здесь не для красоты.
- **Fish Drama 3:** `[confident] За твоими плечами 25 дней с результатами по исходному согласованному плану. [playful] Даже чемодан понял: маршрут здесь не для красоты.`
- **Image prompt:** The turtle checks its accordion map beside the same ridged suitcase, now unfolded into a compact wheeled camper with a hinged roof and foldout doorway; a ribbon road winds around the camper and continues beyond it.

#### 4. Горизонт на колёсиках

- **ID:** `plan.planned_days:t4`
- **Порог:** 50 день по плану
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя накопилось 50 дней с результатами по исходному согласованному плану. Маршрут разросся так, что чемодану понадобилась развязка.
- **Fish Drama 3:** `[excited] У тебя накопилось 50 дней с результатами по исходному согласованному плану. Маршрут разросся так, что чемодану понадобилась <emphasis>развязка.</emphasis>`
- **Image prompt:** The turtle pulls the familiar ridged suitcase beneath a sweeping road interchange unfolding from its open compartments; stacked ramps loop over the extended handle, while the accordion map hangs across the turtle's shell.

#### 5. Вокзал ручной клади

- **ID:** `plan.planned_days:t5`
- **Порог:** 100 день по плану
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 100 дней с результатами по исходному согласованному плану. Багаж вырос: теперь в чемодане ездит целый вокзал.
- **Fish Drama 3:** `[triumphant] Ты накопил 100 дней с результатами по исходному согласованному плану. Багаж вырос: [playful] <slow>теперь в чемодане ездит целый вокзал.</slow>`
- **Image prompt:** The turtle proudly opens its familiar ridged suitcase to reveal an entire miniature railway terminal; a locomotive noses out along a folding track, platforms nest inside the lid, and the turtle's accordion map serves as the station canopy.

### `plan.plan_exercises_many`

**Правило:** Продолжать историю полностью выполненных упражнений из исходного плана. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение по плану. **Источник:** `requires_plan`.

#### 1. Сто поводов для стройки

- **ID:** `plan.plan_exercises_many:t1`
- **Порог:** 100 упражнение по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** За всё время ты полностью выполнил 100 упражнений из исходного плана. Бобёр с чертежом довольно потирает лапы: фундамент есть!
- **Fish Drama 3:** `[warm]За всё время ты полностью выполнил 100 упражнений из исходного плана. Бобёр с чертежом довольно потирает лапы: <soft>фундамент есть!</soft>`
- **Image prompt:** A beaver in a work apron presses a timber block into the foundation of a small dam. An unrolled construction plan lies beside it, held flat by a dumbbell, while a tidy stack of matching blocks waits within reach.

#### 2. Чертежу тесно на пеньке

- **ID:** `plan.plan_exercises_many:t2`
- **Порог:** 200 упражнение по плану
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты полностью выполнил уже 200 упражнений из исходного плана за всё время. Бобёр развернул стройку: чертёж больше не помещается на пеньке.
- **Fish Drama 3:** `[confident]Ты полностью выполнил уже 200 упражнений из исходного плана за всё время. [playful]Бобёр развернул стройку: чертёж больше не помещается на пеньке.`
- **Image prompt:** A beaver in a work apron fits a long beam across a growing timber dam. Its sprawling construction plan spills off a tiny stump onto a workbench, while a barbell waits on the newly completed deck.

#### 3. Абонемент по хвосту

- **ID:** `plan.plan_exercises_many:t3`
- **Порог:** 400 упражнение по плану
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории — 400 полностью выполненных упражнений из исходного плана. Бобёр открыл на плотине спортзал: абонемент выдают по хвосту.
- **Fish Drama 3:** `[triumphant]В твоей истории — 400 полностью выполненных упражнений из исходного плана. Бобёр открыл на плотине спортзал: абонемент выдают <slow>по хвосту.</slow>`
- **Image prompt:** A beaver in a work apron runs a gym atop an enormous timber dam, using its broad tail as a turnstile for a queue of eager ducks. A bench and barbell stand behind it; a rolled construction plan rests on the admission desk.

### `plan.plan_workouts_many`

**Правило:** Продолжать историю полностью выполненных исходных тренировок. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** тренировка по плану. **Источник:** `requires_plan`.

#### 1. План на рельсах

- **ID:** `plan.plan_workouts_many:t1`
- **Порог:** 25 тренировка по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты полностью завершил 25 тренировок из исходного плана за всё время. Паровоз твоей истории довольно пыхтит: багаж-то солидный!
- **Fish Drama 3:** `[warm]Ты полностью завершил 25 тренировок из исходного плана за всё время. Паровоз твоей истории довольно пыхтит: <soft>багаж-то солидный!</soft>`
- **Image prompt:** A squat steam locomotive with a kettle-shaped boiler pulls an open wagon packed with a workout bench, dumbbells, and a rolled exercise mat. A small puff of steam curls over its chimney as it leaves a station platform.

#### 2. Состав с характером

- **ID:** `plan.plan_workouts_many:t2`
- **Порог:** 50 тренировка по плану
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории уже 50 тренировок, полностью завершённых по исходному плану. Ты собрал целый состав — даже вокзал просится прокатиться.
- **Fish Drama 3:** `[confident]В твоей истории уже 50 тренировок, полностью завершённых по исходному плану. [playful]Ты собрал целый состав — даже вокзал просится прокатиться.`
- **Image prompt:** A squat steam locomotive with a kettle-shaped boiler leads a long curve of wagons carrying gym equipment. Beside the rear coupling, a little station building waits on a wheeled platform with a suitcase on its doorstep.

#### 3. Вокзал едет зайцем

- **ID:** `plan.plan_workouts_many:t3`
- **Порог:** 100 тренировка по плану
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За всё время ты полностью завершил 100 тренировок из исходного плана. Состав такой внушительный, что вокзал поехал с ним — зайцем.
- **Fish Drama 3:** `[triumphant]За всё время ты полностью завершил 100 тренировок из исходного плана. Состав такой внушительный, что вокзал поехал с ним — <slow>зайцем.</slow>`
- **Image prompt:** A squat steam locomotive with a kettle-shaped boiler hauls an entire station building on a giant flatcar behind its gym wagons. The station's platform bench holds a suitcase, and its entrance canopy flutters like a passenger's scarf.

## Личный прогресс

### `progress.first_pr`

**Правило:** Получать подтверждённые улучшения после предыдущих сопоставимых сессий. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день улучшения. **Источник:** `requires_comparison`.

#### 1. Прогресс высунул рожки

- **ID:** `progress.first_pr:t1`
- **Порог:** 1 день улучшения
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Первый день с подтверждённым улучшением относительно прошлой сопоставимой сессии — у тебя в копилке. Прогресс высунул рожки!
- **Fish Drama 3:** `[warm] Первый день с подтверждённым улучшением относительно прошлой сопоставимой сессии — у тебя в копилке. [playful] Прогресс высунул рожки!`
- **Image prompt:** A curious snail pulls a small folding staircase from its shell and checks the first raised step with oversized calipers. Its eyestalks lean toward the gap between the new step and a lower comparison block.

#### 2. Лестница раскладывается

- **ID:** `progress.first_pr:t2`
- **Порог:** 2 день улучшения
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 2 дня с подтверждёнными улучшениями относительно прошлых сопоставимых сессий. Это не эхо: лестница правда подросла.
- **Fish Drama 3:** `[confident] У тебя уже <emphasis>2 дня</emphasis> с подтверждёнными улучшениями относительно прошлых сопоставимых сессий. [playful] Это не эхо: лестница правда подросла.`
- **Image prompt:** The snail turns a crank on its shell, extending the folding staircase into a taller zigzag. Oversized calipers hang from the crank handle, while the lowest stair remains tucked inside the open shell.

#### 3. Лифт для лестницы

- **ID:** `progress.first_pr:t3`
- **Порог:** 5 день улучшения
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 5 дней с подтверждёнными улучшениями относительно прошлых сопоставимых сессий. Лестница прогресса заказала себе лифт!
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>5 дней</emphasis> с подтверждёнными улучшениями относительно прошлых сопоставимых сессий. Лестница прогресса <slow>заказала себе лифт!</slow>`
- **Image prompt:** The snail operates a crank-powered freight lift beside its unfolded shell staircase. A folded section of stairs rides inside, lounging in a tiny armchair with its lowest step resting on a footstool.

### `progress.rep_pr`

**Правило:** Улучшить повторения при том же весе и сопоставимых условиях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день рекорда повторений. **Источник:** `requires_comparison`.

#### 1. Первый щелчок счётов

- **ID:** `progress.rep_pr:t1`
- **Порог:** 1 день рекорда повторений
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Первый день рекорда повторений: ты сделал больше повторов, чем в прошлой сопоставимой сессии, при том же весе. Железо даже не переодевалось!
- **Fish Drama 3:** `[warm] Первый день рекорда повторений: ты сделал больше повторов, чем в прошлой сопоставимой сессии, при том же весе. [playful] Железо даже не переодевалось!`
- **Image prompt:** A small octopus slides a bead across a wooden abacus with the tip of a curled tentacle. A dumbbell rests horizontally on a squat stand beside it, while another tentacle steadies the abacus frame.

#### 2. Счёт с характером

- **ID:** `progress.rep_pr:t2`
- **Порог:** 3 день рекорда повторений
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** На твоём счету 3 дня рекорда повторений при том же весе и сопоставимых условиях. Счёты раскрыли дополнительные секции — вот это поворот!
- **Fish Drama 3:** `[confident] На твоём счету <emphasis>3 дня</emphasis> рекорда повторений при том же весе и сопоставимых условиях. [playful] Счёты раскрыли дополнительные секции — вот это поворот!`
- **Image prompt:** The octopus unfolds hinged wings from its wooden abacus, revealing extra bead rails like a concertina. Several tentacles slide beads in different sections; the familiar dumbbell remains on its squat stand.

#### 3. Туш на счётах

- **ID:** `progress.rep_pr:t3`
- **Порог:** 8 день рекорда повторений
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 8 дней рекорда повторений при том же весе и сопоставимых условиях. Счёты теперь играют туш!
- **Fish Drama 3:** `[triumphant] Ты собрал <emphasis>8 дней</emphasis> рекорда повторений при том же весе и сопоставимых условиях. Счёты теперь <slow>играют туш!</slow>`
- **Image prompt:** The octopus performs with its fully expanded abacus held like an enormous accordion, tentacles sweeping the bead rails. The familiar dumbbell sits upright on its squat stand, listening through a tiny ear trumpet.

### `progress.weight_pr`

**Правило:** Увеличить рабочий вес в выполненном сопоставимом подходе. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день рекорда веса. **Источник:** `requires_comparison`.

#### 1. Первый рейс железа

- **ID:** `progress.weight_pr:t1`
- **Порог:** 1 день рекорда веса
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя первый день рекорда: рабочий вес в выполненном сопоставимом подходе вырос. Блины тихонько вызвали погрузчик.
- **Fish Drama 3:** `[warm] У тебя первый день рекорда: рабочий вес в выполненном сопоставимом подходе вырос. Блины <soft>тихонько вызвали погрузчик.</soft>`
- **Image prompt:** A compact forklift with expressive headlights eases its forks beneath a single upright weight plate, leaning forward with careful curiosity; a short barbell rests on a low loading stand beside it.

#### 2. Блинная логистика

- **ID:** `progress.weight_pr:t2`
- **Порог:** 3 день рекорда веса
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории — 3 дня рекорда рабочего веса в выполненных сопоставимых подходах. Блины завели отдел логистики.
- **Fish Drama 3:** `[confident] В твоей истории — <emphasis>3 дня рекорда рабочего веса</emphasis> в выполненных сопоставимых подходах. [playful] Блины завели отдел логистики.`
- **Image prompt:** The compact forklift carries a neatly secured stack of weight plates up a short loading ramp toward a waiting barbell; its forks hover above an unloading stand, with coiled lifting straps ready beside it.

#### 3. Погрузчик для погрузчика

- **ID:** `progress.weight_pr:t3`
- **Порог:** 8 день рекорда веса
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 8 дней рекорда рабочего веса в выполненных сопоставимых подходах. Погрузчику для блинов понадобился свой погрузчик.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>8 дней рекорда рабочего веса</emphasis> в выполненных сопоставимых подходах. Погрузчику для блинов понадобился <slow>свой погрузчик.</slow>`
- **Image prompt:** The compact forklift proudly holds a stack of weight plates while riding on the raised forks of a much larger forklift; both vehicles lean forward in matching poses, turning a routine plate delivery into an absurd nested convoy.

### `progress.estimate_pr`

**Правило:** Улучшить оценочный показатель силы более чем на один процент. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день расчётного рекорда. **Источник:** `requires_comparison`.

#### 1. Костяшки разминаются

- **ID:** `progress.estimate_pr:t1`
- **Порог:** 1 день расчётного рекорда
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Твой первый день расчётного рекорда: оценочный показатель силы вырос больше чем на 1%. Счёты довольно потёрли костяшки.
- **Fish Drama 3:** `[warm] Твой первый день расчётного рекорда: оценочный показатель силы вырос больше чем на 1%. [playful] Счёты довольно потёрли костяшки.`
- **Image prompt:** A small abacus with mitten hands and stubby feet slides a single bead along its lowest rod as if testing a piano key; the other hand hovers expectantly, and one foot reaches toward a tiny practice pedal.

#### 2. Расчёт набрал темп

- **ID:** `progress.estimate_pr:t2`
- **Порог:** 3 день расчётного рекорда
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 3 дня расчётного рекорда: оценочный показатель силы в каждый из них вырос больше чем на 1%. Счёты играют всё увереннее.
- **Fish Drama 3:** `[confident] У тебя уже <emphasis>3 дня расчётного рекорда</emphasis>: оценочный показатель силы в каждый из них вырос больше чем на 1%. Счёты играют всё увереннее.`
- **Image prompt:** The little abacus balances on a piano stool and plays its own bead rows with both mitten hands; several beads bunch into rhythmic clusters while a stubby foot presses a wooden pedal beneath the frame.

#### 3. Костяшки на бис

- **ID:** `progress.estimate_pr:t3`
- **Порог:** 8 день расчётного рекорда
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 8 дней расчётного рекорда: оценочный показатель силы каждый раз рос больше чем на 1%. Счёты дали концерт и сами себе заказали бис.
- **Fish Drama 3:** `[triumphant] Ты собрал <emphasis>8 дней расчётного рекорда</emphasis>: оценочный показатель силы каждый раз рос больше чем на 1%. Счёты дали концерт и <slow>сами себе заказали бис.</slow>`
- **Image prompt:** The lively abacus has unfolded its own frame into a concert grand piano, with bead-covered rods serving as keys; its mitten hands strike a final chord while several beads leap into the open lid like cheering spectators.

### `progress.multi_exercise`

**Правило:** Получить подтверждённые улучшения в разных упражнениях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение с улучшением. **Источник:** `requires_comparison`.

#### 1. Дуэт без фальстарта

- **ID:** `progress.multi_exercise:t1`
- **Порог:** 2 упражнение с улучшением
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** В 2 разных упражнениях у тебя уже есть подтверждённые улучшения. Прогресс собрал дуэт — железо, вступай по очереди!
- **Fish Drama 3:** `[warm] В 2 разных упражнениях у тебя уже есть подтверждённые улучшения. [playful] Прогресс собрал дуэт — железо, вступай по очереди!`
- **Image prompt:** A small octopus conductor raises a baton before a kettlebell and a dumbbell standing like a musical duo. Both pieces of equipment lean toward the cue, while a tiny closed tea flask waits beside the podium.

#### 2. Квартет набрал ход

- **ID:** `progress.multi_exercise:t2`
- **Порог:** 4 упражнение с улучшением
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал подтверждённые улучшения в 4 разных упражнениях. У прогресса уже квартет: лень в состав не прошла.
- **Fish Drama 3:** `[confident] Ты собрал подтверждённые улучшения в 4 разных упражнениях. [playful] У прогресса уже квартет: лень в состав не прошла.`
- **Image prompt:** The octopus conductor leads a quartet of a kettlebell, dumbbell, rowing handle and coiled battle rope. Several arms cue separate entrances while another steadies a teacup that has become impossible to sip.

#### 3. Восемь партий прогресса

- **ID:** `progress.multi_exercise:t3`
- **Порог:** 8 упражнение с улучшением
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Подтверждённые улучшения в 8 разных упражнениях — ты собрал целый оркестр! Дирижёр-осьминог занят: чай ему подаёт стажёр.
- **Fish Drama 3:** `[triumphant] Подтверждённые улучшения в 8 разных упражнениях — ты собрал <emphasis>целый оркестр!</emphasis> [playful] Дирижёр-осьминог занят: <slow>чай ему подаёт стажёр.</slow>`
- **Image prompt:** The octopus conducts eight distinct exercise implements arranged as a compact orchestra, every arm busy giving a cue. A tiny shrimp intern climbs a step stool to serve tea directly to the conductor's delighted mouth.

### `progress.after_month`

**Правило:** Улучшить результат относительно baseline возрастом минимум двадцать восемь дней. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение с длинной дугой. **Источник:** `requires_comparison`.

#### 1. Время предъявить разницу

- **ID:** `progress.after_month:t1`
- **Порог:** 1 упражнение с длинной дугой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты улучшил результат в 1 упражнении относительно исходного замера давностью не меньше 28 дней. Улитка-архивариус довольно шуршит папкой.
- **Fish Drama 3:** `[warm] Ты улучшил результат в 1 упражнении относительно исходного замера давностью не меньше 28 дней. [playful] Улитка-архивариус довольно шуршит папкой.`
- **Image prompt:** A bespectacled snail archivist opens a weathered folder on a low desk. Inside, a curled old picture and a fresh picture show the same kettlebell, with the newer result represented by a taller plain bar.

#### 2. Архив пошёл на выезд

- **ID:** `progress.after_month:t2`
- **Порог:** 3 упражнение с длинной дугой
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В 3 упражнениях ты превзошёл исходные результаты давностью не меньше 28 дней. Улитка-архивариус уже выкатила целую тележку доказательств.
- **Fish Drama 3:** `[confident] В 3 упражнениях ты превзошёл исходные результаты давностью не меньше 28 дней. [playful] Улитка-архивариус уже выкатила целую тележку доказательств.`
- **Image prompt:** The snail archivist pushes a trolley carrying three open folders, each pairing a curled old equipment picture with a fresh one. Its shell supports a foldout sorting desk, and loose blank dividers nearly engulf the determined clerk.

#### 3. Прошлое водит экскурсии

- **ID:** `progress.after_month:t3`
- **Порог:** 6 упражнение с длинной дугой
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В 6 упражнениях ты превзошёл исходные результаты давностью не меньше 28 дней. Архив стал музеем — прежние результаты теперь водят экскурсии.
- **Fish Drama 3:** `[triumphant] В 6 упражнениях ты превзошёл исходные результаты давностью не меньше 28 дней. [playful] Архив стал музеем — <slow>прежние результаты теперь водят экскурсии.</slow>`
- **Image prompt:** The snail's shell has unfolded into a miniature museum with six paired equipment exhibits. A retired kettlebell acts as the tour guide, pointing at its own old portrait while the snail ceremoniously pulls open the entrance curtains.

### `progress.retained`

**Правило:** Повторить новый личный результат ещё в двух последующих днях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** закреплённый результат. **Источник:** `requires_comparison`.

#### 1. Рекорд с пропиской

- **ID:** `progress.retained:t1`
- **Порог:** 1 закреплённый результат
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты закрепил 1 новый личный результат: повторил его ещё в два последующих дня. Случайность пожала плечами и ушла.
- **Fish Drama 3:** `[warm] Ты закрепил <emphasis>1 новый личный результат</emphasis>: повторил его ещё в два последующих дня. [playful] Случайность пожала плечами и ушла.`
- **Image prompt:** A squat rubber stamp with mitten-like hands presses the third matching footprint into a single clay tile, two earlier impressions visible beside it; the stamp leans back with a small, satisfied bounce.

#### 2. Повтор вошёл во вкус

- **ID:** `progress.retained:t2`
- **Порог:** 3 закреплённый результат
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты закрепил уже 3 новых личных результата: каждый повторён ещё в два последующих дня. Случайности тут негде припарковаться.
- **Fish Drama 3:** `[confident] Ты закрепил уже <emphasis>3 новых личных результата</emphasis>: каждый повторён ещё в два последующих дня. Случайности тут негде припарковаться.`
- **Image prompt:** A squat rubber stamp with mitten-like hands works a lever beside three clay tiles, each holding three matching footprints; the tiles form a tidy staircase, and the stamp plants one boot on the top step.

#### 3. Фабрика неслучайных чудес

- **ID:** `progress.retained:t3`
- **Порог:** 5 закреплённый результат
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории 5 закреплённых личных результатов: каждый повторён ещё в два последующих дня. Случайность уволилась — говорит, у тебя тут серийное производство.
- **Fish Drama 3:** `[triumphant] В твоей истории <emphasis>5 закреплённых личных результатов</emphasis>: каждый повторён ещё в два последующих дня. [playful] Случайность уволилась — <slow>говорит, у тебя тут серийное производство.</slow>`
- **Image prompt:** A squat rubber stamp with mitten-like hands rides an enormous stamping press like a rodeo bull, gripping its lever with both hands; five finished clay tiles fan out below, each bearing three identical footprints.

### `progress.pr_weeks`

**Правило:** Накопить недели с подтверждёнными личными улучшениями. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя с улучшением. **Источник:** `requires_comparison`.

#### 1. Календарь оживает

- **ID:** `progress.pr_weeks:t1`
- **Порог:** 2 неделя с улучшением
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя накопились 2 недели с подтверждёнными личными улучшениями. Календарь приосанился: теперь он не просто бумага.
- **Fish Drama 3:** `[warm] У тебя накопились <emphasis>2 недели с подтверждёнными личными улучшениями</emphasis>. [playful] Календарь приосанился: теперь он не просто бумага.`
- **Image prompt:** A small desk calendar with stubby boots carefully steps across two folded weekly sheets, each divided into seven blank cells and bearing a raised upward arrow; its free hand reaches forward for balance.

#### 2. Листы идут в отрыв

- **ID:** `progress.pr_weeks:t2`
- **Порог:** 6 неделя с улучшением
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 6 недель с подтверждёнными личными улучшениями. Календарь уже не листается, а делает кульбиты от гордости.
- **Fish Drama 3:** `[confident] Ты накопил <emphasis>6 недель с подтверждёнными личными улучшениями</emphasis>. [playful] Календарь уже не листается, а делает кульбиты от гордости.`
- **Image prompt:** A small desk calendar with stubby boots vaults over a rising ramp of six folded weekly sheets, each marked by a raised upward arrow and blank day cells; its loose pages curl behind it like an acrobat's limbs.

#### 3. Календарь на бис

- **ID:** `progress.pr_weeks:t3`
- **Порог:** 12 неделя с улучшением
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 12 недель с подтверждёнными личными улучшениями. Календарь вызвали на бис — а он вышел колесом.
- **Fish Drama 3:** `[triumphant] В твоей истории уже <emphasis>12 недель с подтверждёнными личными улучшениями</emphasis>. [playful] Календарь вызвали на бис — <slow>а он вышел колесом.</slow>`
- **Image prompt:** A small desk calendar acrobat balances upside down atop a huge rolling wheel made from twelve folded weekly sheets, every sheet carrying a raised upward arrow; its stubby boots point skyward as one hand flourishes a bow.

### `progress.pr_months`

**Правило:** Накопить месяцы с подтверждёнными личными улучшениями. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** месяц с улучшением. **Источник:** `requires_comparison`.

#### 1. Второй том пошёл

- **ID:** `progress.pr_months:t1`
- **Порог:** 2 месяц с улучшением
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 2 месяца с подтверждёнными личными улучшениями. Улитка-архивариус открывает второй том — история набирает ход.
- **Fish Drama 3:** `[warm]У тебя уже 2 месяца с подтверждёнными личными улучшениями. Улитка-архивариус открывает второй том — история набирает ход.`
- **Image prompt:** A bespectacled snail archivist tucks two bundled stacks of calendar leaves into shell-mounted cubbies. A lettuce-leaf bookmark peeks from one stack while the snail steadies a tiny rolling library ladder.

#### 2. Архив просит шкаф

- **ID:** `progress.pr_months:t2`
- **Порог:** 4 месяц с улучшением
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 4 месяца с подтверждёнными личными улучшениями. Архиву понадобился ещё один шкаф — и это не для печенья.
- **Fish Drama 3:** `[confident]В твоей истории уже 4 месяца с подтверждёнными личными улучшениями. Архиву понадобился ещё один шкаф — и это не для печенья.`
- **Image prompt:** A bespectacled snail archivist climbs a rolling ladder beside its shell, now an expanding cabinet with four deep cubbies of calendar bundles. A lettuce leaf rests on the reading ledge as another stack slides into place.

#### 3. Погрузчик для салата

- **ID:** `progress.pr_months:t3`
- **Порог:** 8 месяц с улучшением
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 8 месяцев с подтверждёнными личными улучшениями. Улитка купила архиву погрузчик — и первым делом погрузила салат.
- **Fish Drama 3:** `[triumphant]Ты накопил 8 месяцев с подтверждёнными личными улучшениями. Улитка купила архиву погрузчик — <slow>и первым делом погрузила салат.</slow>`
- **Image prompt:** A bespectacled snail archivist pilots a tiny forklift beside its shell, now a towering archive of calendar bundles. The forks proudly carry one enormous lettuce leaf while a queue of loaded book carts waits behind.

### `progress.pr_days_many`

**Правило:** Продолжать историю сопоставимых личных улучшений. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 24, 48. Не подряд; без повышения нагрузки ради награды. **Единица:** день улучшения. **Источник:** `requires_comparison`.

#### 1. Первый состав улучшений

- **ID:** `progress.pr_days_many:t1`
- **Порог:** 5 день улучшения
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории уже 5 дней с подтверждёнными личными улучшениями в сопоставимых условиях. Пингвин-диспетчер выпускает первый состав!
- **Fish Drama 3:** `[warm]В твоей истории уже 5 дней с подтверждёнными личными улучшениями в сопоставимых условиях. Пингвин-диспетчер выпускает первый состав!`
- **Image prompt:** A penguin dispatcher in a railway cap waves a paddle beside a miniature locomotive pulling five little carriages. The train curves around the penguin's feet as it carefully connects the final carriage with one flipper.

#### 2. Хвост за горизонтом

- **ID:** `progress.pr_days_many:t2`
- **Порог:** 15 день улучшения
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя уже 15 дней с личными улучшениями, подтверждёнными сравнением. Состав подрос — пингвин-диспетчер ищет хвост поезда в бинокль.
- **Fish Drama 3:** `[confident]У тебя уже 15 дней с личными улучшениями, подтверждёнными сравнением. Состав подрос — пингвин-диспетчер ищет хвост поезда в бинокль.`
- **Image prompt:** A penguin dispatcher in a railway cap leans from a tall signal cabin with oversized binoculars. A long miniature train winds around the cabin in stacked loops, its last carriage peeking out directly behind the penguin.

#### 3. Вокзал едет с нами

- **ID:** `progress.pr_days_many:t3`
- **Порог:** 30 день улучшения
- **Подтверждённая практика:** минимум 48 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 30 дней с подтверждёнными личными улучшениями в сопоставимых условиях. Поезд разросся: пингвин-диспетчер прицепил к нему целый вокзал!
- **Fish Drama 3:** `[triumphant]Ты накопил 30 дней с подтверждёнными личными улучшениями в сопоставимых условиях. Поезд разросся: пингвин-диспетчер прицепил к нему <slow>целый вокзал!</slow>`
- **Image prompt:** A penguin dispatcher in a railway cap rings a handbell from the porch of an entire station building riding on a train flatcar. The locomotive pulls the station around a tight curve, with a platform bench strapped aboard.

## Дневник ощущений

### `reflection.checkin`

**Правило:** Сохранять отметку самочувствия или дискомфорта; её содержание не оценивается. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день с отметкой. **Источник:** `requires_reflection`.

#### 1. Дневник навострил страницы

- **ID:** `reflection.checkin:t1`
- **Порог:** 3 день с отметкой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты сохранил отметки самочувствия или дискомфорта в 3 разных дня. Дневник слушает — оценок не ставит.
- **Fish Drama 3:** `[warm]Ты сохранил отметки самочувствия или дискомфорта в 3 разных дня. Дневник слушает — <soft>оценок не ставит.</soft>`
- **Image prompt:** A small anthropomorphic accordion notebook with two stubby feet cups one page beside its cover like a listening ear. A short pencil rests across its open pages, ready to record whatever comes next.

#### 2. Записано как есть

- **ID:** `reflection.checkin:t2`
- **Порог:** 10 день с отметкой
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 10 дней с отметками самочувствия или дискомфорта. Ты записываешь, как есть, — у дневника нет любимых ответов.
- **Fish Drama 3:** `[confident]В твоей истории уже <emphasis>10 дней</emphasis> с отметками самочувствия или дискомфорта. Ты записываешь, как есть, — у дневника нет любимых ответов.`
- **Image prompt:** An anthropomorphic accordion notebook with two stubby feet pushes a handcart carrying its own expanding pages. A short pencil serves as the cart handle, while one loose page curls upward like an attentive ear.

#### 3. Архив без экзаменов

- **ID:** `reflection.checkin:t3`
- **Порог:** 30 день с отметкой
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 30 дней с отметками самочувствия или дискомфорта. Ты собрал целый архив ощущений — без экзамена на бодрость.
- **Fish Drama 3:** `[triumphant]У тебя уже <emphasis>30 дней</emphasis> с отметками самочувствия или дискомфорта. Ты собрал целый архив ощущений — <slow>без экзамена на бодрость.</slow>`
- **Image prompt:** An anthropomorphic accordion notebook with two stubby feet drives a tiny forklift, lifting the towering folds of its own paper tail. A short pencil rides the raised forks like a librarian reporting for an absurdly oversized shift.

### `reflection.months`

**Правило:** Оставлять отметки ощущений в разных календарных месяцах. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** месяц наблюдений. **Источник:** `requires_reflection`.

#### 1. Улитка листает месяцы

- **ID:** `reflection.months:t1`
- **Порог:** 2 месяц наблюдений
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты оставил отметки ощущений в 2 разных календарных месяцах. У дневника появилась история с продолжением, а не норматив по скорости.
- **Fish Drama 3:** `[warm]Ты оставил отметки ощущений в 2 разных календарных месяцах. У дневника появилась <soft>история с продолжением</soft>, а не норматив по скорости.`
- **Image prompt:** A curious snail carries a shell formed from two overlapping blank calendar leaves. It gently lifts the front leaf with a feeler, revealing the second beneath, while its eyestalks peer around the newly opened edge.

#### 2. Календарь на борту

- **ID:** `reflection.months:t2`
- **Порог:** 4 месяц наблюдений
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты отмечал ощущения в 4 разных календарных месяцах. Твоя история обзавелась главами — календарь уже устраивается поудобнее.
- **Fish Drama 3:** `[confident]Ты отмечал ощущения в <emphasis>4 разных календарных месяцах.</emphasis> Твоя история обзавелась главами — календарь уже устраивается поудобнее.`
- **Image prompt:** A snail carries four blank calendar leaves arranged into a roomy shell. One leaf folds outward into a little reading ledge; the snail leans back beneath it, using a curled leaf corner as an unexpectedly practical headrest.

#### 3. Летопись на ракушке

- **ID:** `reflection.months:t3`
- **Порог:** 8 месяц наблюдений
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты оставил отметки ощущений в 8 разных календарных месяцах. Это уже летопись — календарь просит у тебя автограф.
- **Fish Drama 3:** `[triumphant]Ты оставил отметки ощущений в <emphasis>8 разных календарных месяцах.</emphasis> Это уже летопись — <slow>календарь просит у тебя автограф.</slow>`
- **Image prompt:** A snail's shell unfolds into an enormous fan of eight blank calendar leaves, dwarfing its delighted owner. Beneath the sweeping pages, the snail solemnly presents a comically tiny pencil and a blank autograph card toward the viewer.

### `reflection.weeks`

**Правило:** Оставлять отметки ощущений в разных неделях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя наблюдений. **Источник:** `requires_reflection`.

#### 1. Погода по ощущениям

- **ID:** `reflection.weeks:t1`
- **Порог:** 4 неделя наблюдений
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Отметки ощущений есть в 4 разных неделях — ты знакомишься со своей внутренней погодой. Без гадания на гантелях.
- **Fish Drama 3:** `[warm]Отметки ощущений есть в 4 разных неделях — ты знакомишься со своей внутренней погодой. Без гадания на гантелях.`
- **Image prompt:** A small frog weather keeper in oversized rain boots stands on a low stool, holding a tray of four tiny clouds with different expressions. One cloud drizzles into the tray while the frog leans closer to greet it.

#### 2. Архив облачных дел

- **ID:** `reflection.weeks:t2`
- **Порог:** 12 неделя наблюдений
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Отметки ощущений охватили 12 разных недель — ты собираешь историю внутренней погоды. Тучам и солнцу нашлось место в одной сводке.
- **Fish Drama 3:** `[confident]Отметки ощущений охватили <emphasis>12 разных недель</emphasis> — ты собираешь историю внутренней погоды. [playful]Тучам и солнцу нашлось место в одной сводке.`
- **Image prompt:** A small frog weather keeper in oversized rain boots tends a stepped shelf of open cloud cubbies. Puffy clouds, a sleepy sun and a busy raincloud occupy separate nooks; the frog carefully slides a tray beneath the dripping visitor.

#### 3. Туча со своим зонтом

- **ID:** `reflection.weeks:t3`
- **Порог:** 26 неделя наблюдений
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя отметки ощущений за 26 разных недель — ты ведёшь целую летопись внутренней погоды. Даже грозовая туча пришла с зонтиком.
- **Fish Drama 3:** `[triumphant]У тебя отметки ощущений за <emphasis>26 разных недель</emphasis> — ты ведёшь целую летопись внутренней погоды. [playful]Даже грозовая туча <slow>пришла с зонтиком.</slow>`
- **Image prompt:** A small frog weather keeper in oversized rain boots welcomes an enormous thundercloud at a tiny reception desk. The cloud squeezes onto a visitor stool beneath its own absurdly small umbrella, while smaller clouds peek around it.

### `reflection.note`

**Правило:** Добавлять собственные заметки к тренировкам. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день с заметкой. **Источник:** `requires_reflection`.

#### 1. Первое слово за тобой

- **ID:** `reflection.note:t1`
- **Порог:** 1 день с заметкой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Есть первый день с твоей собственной заметкой к тренировке — ты даёшь слово не только железу.
- **Fish Drama 3:** `[warm]Есть первый день с твоей собственной заметкой к тренировке — ты даёшь слово <soft>не только железу.</soft>`
- **Image prompt:** A stubby pencil reporter in oversized sneakers holds a tiny microphone beside a gym bench. A single open notebook serves as a lectern, its pages blank; one dumbbell rests opposite like an exceptionally quiet interview guest.

#### 2. Репортаж между гантелями

- **ID:** `reflection.note:t2`
- **Порог:** 5 день с заметкой
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Собственные заметки к тренировкам есть уже за 5 разных дней. Ты пишешь свою историю, пока гантели старательно хранят молчание.
- **Fish Drama 3:** `[confident]Собственные заметки к тренировкам есть уже за <emphasis>5 разных дней.</emphasis> [playful]Ты пишешь свою историю, пока гантели старательно хранят молчание.`
- **Image prompt:** A stubby pencil reporter in oversized sneakers builds a compact interview desk from stacked blank notebooks. Leaning across the top, it offers a microphone to two dumbbells, both sitting stubbornly motionless on a gym bench.

#### 3. Железо требует слова

- **ID:** `reflection.note:t3`
- **Порог:** 15 день с заметкой
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Собственные заметки к тренировкам есть уже за 15 разных дней — ты ведёшь настоящую хронику. Гантели требуют право на ответ.
- **Fish Drama 3:** `[triumphant]Собственные заметки к тренировкам есть уже за <emphasis>15 разных дней</emphasis> — ты ведёшь настоящую хронику. [playful]Гантели требуют <slow>право на ответ.</slow>`
- **Image prompt:** A stubby pencil reporter in oversized sneakers hosts a press conference behind a giant unfurled blank notebook. Dumbbells crowd the gym bench, leaning eagerly toward its tiny microphone; a long barbell tries to squeeze into the front row.

### `reflection.adjusted`

**Правило:** Явно сохранять корректировки плана с допустимой причиной. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** корректировка. **Источник:** `requires_reflection`.

#### 1. План включил поворотник

- **ID:** `reflection.adjusted:t1`
- **Порог:** 1 корректировка
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты сохранил 1 корректировку плана с допустимой причиной. Даже у плана бывает поворотник.
- **Fish Drama 3:** `[warm] Ты сохранил <emphasis>1 корректировку плана</emphasis> с допустимой причиной. Даже у плана бывает поворотник.`
- **Image prompt:** A folded paper-map navigator braces a large pencil against a toy railway switch, turning the track toward a clear passage. A small train waits beside a pebble blocking the original route.

#### 2. Маршрут умеет слушать

- **ID:** `reflection.adjusted:t2`
- **Порог:** 3 корректировка
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 3 сохранённые корректировки плана с допустимыми причинами. План умеет слушать, хоть ушей ему и не выдали.
- **Fish Drama 3:** `[confident] В твоей истории уже <emphasis>3 сохранённые корректировки плана</emphasis> с допустимыми причинами. [playful] План умеет слушать, хоть ушей ему и не выдали.`
- **Image prompt:** The paper-map navigator stands on a low signal platform, using a large pencil as a lever to connect several looping toy tracks. A small train follows the revised route around a row of oversized pebbles.

#### 3. План объезжает абсурд

- **ID:** `reflection.adjusted:t3`
- **Порог:** 8 корректировка
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** За твоими плечами 8 сохранённых корректировок плана с допустимыми причинами. План научился объезжать препятствия — даже резиновую утку с характером.
- **Fish Drama 3:** `[triumphant] За твоими плечами <emphasis>8 сохранённых корректировок плана</emphasis> с допустимыми причинами. План научился объезжать препятствия — [playful] даже <slow>резиновую утку с характером.</slow>`
- **Image prompt:** The paper-map navigator rides the front of a toy train, wielding a giant pencil to curve the rails around an enormous sleeping rubber duck. The duck lounges across the old route while the new track loops neatly around its tail.

### `reflection.effort_sets`

**Правило:** Сохранять субъективную оценку усилия после подходов. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** подход с оценкой. **Источник:** `requires_reflection`.

#### 1. Микрофон для ощущений

- **ID:** `reflection.effort_sets:t1`
- **Порог:** 3 подход с оценкой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты сохранил свою оценку усилия после 3 подходов. Ощущения получили микрофон — железо, не перебивай!
- **Fish Drama 3:** `[warm] Ты сохранил свою оценку усилия после <emphasis>3 подходов.</emphasis> [playful] Ощущения получили микрофон — железо, не перебивай!`
- **Image prompt:** A small microphone reporter with mitten hands leans toward a resting dumbbell, holding an open pocket notebook. Three folded feedback cards stand beside the dumbbell like tiny audience seats.

#### 2. Слово за тобой

- **ID:** `reflection.effort_sets:t2`
- **Порог:** 15 подход с оценкой
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоём дневнике уже 15 подходов с оценкой усилия. Ты описываешь, как было тебе, а гантели могут оставить своё мнение при себе.
- **Fish Drama 3:** `[confident] В твоём дневнике уже <emphasis>15 подходов с оценкой усилия.</emphasis> Ты описываешь, как было тебе, а гантели могут оставить своё мнение при себе.`
- **Image prompt:** The microphone reporter operates a broad mixing desk, collecting folded feedback cards in a tidy tray. Several dumbbells queue beside the desk while the reporter raises one mitten hand to moderate their chatter.

#### 3. Железу слово не давали

- **ID:** `reflection.effort_sets:t3`
- **Порог:** 50 подход с оценкой
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты сохранил свои оценки усилия для 50 подходов. Ощущения ведут ток-шоу, а штанга сидит в тапочках — и не перебивает.
- **Fish Drama 3:** `[triumphant] Ты сохранил свои оценки усилия для <emphasis>50 подходов.</emphasis> Ощущения ведут ток-шоу, [playful] а штанга сидит в тапочках — <slow>и не перебивает.</slow>`
- **Image prompt:** The microphone reporter hosts a tiny talk show from a swivel chair, facing a barbell sprawled across an oversized guest sofa in soft slippers. A towering stack of folded feedback cards serves as the host's desk.

### `reflection.feedback_days`

**Правило:** Накопить дни с явной обратной связью о подходах. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день обратной связи. **Источник:** `requires_reflection`.

#### 1. Железо, к микрофону

- **ID:** `reflection.feedback_days:t1`
- **Порог:** 2 день обратной связи
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты оставляешь обратную связь о подходах: таких дней уже 2. Железо молчит, а у тебя есть что сказать.
- **Fish Drama 3:** `[warm] Ты оставляешь обратную связь о подходах: таких дней уже <emphasis>2</emphasis>. Железо молчит, а у тебя есть что сказать.`
- **Image prompt:** A stubby-legged handheld microphone leans toward a small dumbbell perched on a folded gym towel, holding a tiny blank cue card; the dumbbell tilts one plate toward the microphone as if ready to answer.

#### 2. Корреспондент между подходами

- **ID:** `reflection.feedback_days:t2`
- **Порог:** 8 день обратной связи
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 8 дней с обратной связью о подходах. Ты не просто двигаешь железо — ты даёшь ему рецензию.
- **Fish Drama 3:** `[confident] В твоей истории уже <emphasis>8 дней</emphasis> с обратной связью о подходах. Ты не просто двигаешь железо — ты даёшь ему рецензию.`
- **Image prompt:** A stubby-legged microphone reporter balances on a stack of weight plates, extending its cable arm toward a barbell at a tiny press table; several dumbbells lean in like curious reporters.

#### 3. Штанга просит слова

- **ID:** `reflection.feedback_days:t3`
- **Порог:** 20 день обратной связи
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 20 дней с обратной связью о подходах. Микрофон твой, а штанга на пресс-конференции просит вопрос полегче.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>20 дней</emphasis> с обратной связью о подходах. Микрофон твой, а штанга на пресс-конференции <slow>просит вопрос полегче</slow>.`
- **Image prompt:** A giant stubby-legged microphone hosts a grand press conference, leaning over a barbell hiding behind a towel; the barbell raises one plate like a timid hand while a crowd of dumbbells waits for its answer.

### `reflection.note_weeks`

**Правило:** Оставлять собственные заметки в разных неделях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя с заметкой. **Источник:** `requires_reflection`.

#### 1. Раковина с полями

- **ID:** `reflection.note_weeks:t1`
- **Порог:** 2 неделя с заметкой
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты оставил собственные заметки уже в 2 разных неделях. У твоих наблюдений появилось место на странице — пусть обживаются.
- **Fish Drama 3:** `[warm] Ты оставил собственные заметки уже в <emphasis>2 разных неделях</emphasis>. У твоих наблюдений появилось место на странице — пусть обживаются.`
- **Image prompt:** A small snail carries a spiral notebook instead of a shell, gently tucking two loose blank pages under its cover with a feeler; a curled page corner forms a tiny ramp beside its trail.

#### 2. Страницы едут дальше

- **ID:** `reflection.note_weeks:t2`
- **Порог:** 6 неделя с заметкой
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты оставляешь свои заметки: в копилке уже 6 разных недель. Дневник вылез из раковины и присматривает себе полку.
- **Fish Drama 3:** `[playful] Ты оставляешь свои заметки: в копилке уже <emphasis>6 разных недель</emphasis>. Дневник вылез из раковины и присматривает себе полку.`
- **Image prompt:** The notebook-shelled snail pulls a little cart piled with loose blank pages, using a ribbon bookmark as a towline; its feelers point toward an empty shelf that looks comically large beside it.

#### 3. Архив на усиках

- **ID:** `reflection.note_weeks:t3`
- **Порог:** 12 неделя с заметкой
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Свои заметки ты оставил уже в 12 разных неделях. Это личный архив: даже «сегодня было странно» здесь важнее чужих умных цитат.
- **Fish Drama 3:** `[confident] Свои заметки ты оставил уже в <emphasis>12 разных неделях</emphasis>. Это личный архив: даже «сегодня было странно» здесь важнее чужих умных цитат.`
- **Image prompt:** The notebook-shelled snail opens its cover into a rotating file rack, sorting curled blank pages with both feelers; a small desk lamp rides on top while a tidy fan of paper follows its trail.

#### 4. Библиотека набирает ход

- **ID:** `reflection.note_weeks:t4`
- **Порог:** 26 неделя с заметкой
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоём дневнике уже 26 разных недель с собственными заметками. Ты собрал столько наблюдений, что полка задумалась о расширении.
- **Fish Drama 3:** `[excited] В твоём дневнике уже <emphasis>26 разных недель</emphasis> с собственными заметками. Ты собрал столько наблюдений, что полка задумалась о расширении.`
- **Image prompt:** The notebook-shelled snail carries a branching library of compact shelves, bridging a gap between them with an open blank notebook; its feelers carefully guide a rolling ladder along the growing archive.

#### 5. Лень просит абонемент

- **ID:** `reflection.note_weeks:t5`
- **Порог:** 52 неделя с заметкой
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты оставил собственные заметки в 52 разных неделях. Личная библиотека открыта — лень просит читательский билет.
- **Fish Drama 3:** `[triumphant] Ты оставил собственные заметки в <emphasis>52 разных неделях</emphasis>. Личная библиотека открыта — <slow>лень просит читательский билет</slow>.`
- **Image prompt:** The notebook-shelled snail has become a mobile library, its open cover forming a checkout counter; a sleepy pillow presents a blank borrowing card while tiny dumbbells queue beside shelves built into the enormous shell.

### `reflection.feedback_exercises`

**Правило:** Оставить явную обратную связь в разных упражнениях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** упражнение с отзывом. **Источник:** `requires_reflection`.

#### 1. Микрофон для ощущений

- **ID:** `reflection.feedback_exercises:t1`
- **Порог:** 2 упражнение с отзывом
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты оставил отзывы о 2 разных упражнениях. Железо молчит, а ты говоришь по делу.
- **Fish Drama 3:** `[warm]Ты оставил отзывы о 2 разных упражнениях. [playful]Железо молчит, а ты говоришь по делу.`
- **Image prompt:** A little kettlebell reporter holds a microphone between an animated dumbbell and a coiled resistance band; the dumbbell leans toward the microphone while the band raises one loop, eagerly waiting for its turn.

#### 2. Корреспондент между подходами

- **ID:** `reflection.feedback_exercises:t2`
- **Порог:** 5 упражнение с отзывом
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты оставил отзывы о 5 разных упражнениях — у ощущений появился собственный пресс-центр.
- **Fish Drama 3:** `[confident]Ты оставил отзывы о <emphasis>5 разных упражнениях</emphasis> — [playful]у ощущений появился собственный пресс-центр.`
- **Image prompt:** A kettlebell reporter hosts a roundtable with a dumbbell, resistance band, jump rope, exercise mat, and low step; its microphone reaches toward the five animated guests as the mat leans forward with an eager curl.

#### 3. Железо просит слова

- **ID:** `reflection.feedback_exercises:t3`
- **Порог:** 10 упражнение с отзывом
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты оставил отзывы о 10 разных упражнениях. Железо созвало пресс-конференцию — и снова отвечаешь ты!
- **Fish Drama 3:** `[triumphant]Ты оставил отзывы о <emphasis>10 разных упражнениях</emphasis>. Железо созвало пресс-конференцию — <slow>и снова отвечаешь ты!</slow>`
- **Image prompt:** A kettlebell reporter stands on a low exercise step as ten animated workout props lean in with microphones; a towering squat rack stoops to hear the tiny speaker, turning the interview into an unexpectedly crowded press conference.

### `reflection.reflection_year`

**Правило:** Продолжать необязательный дневник ощущений в течение длинной истории. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя наблюдений. **Источник:** `requires_reflection`.

#### 1. Архив на прогулке

- **ID:** `reflection.reflection_year:t1`
- **Порог:** 39 неделя наблюдений
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 39 недель наблюдений в дневнике ощущений. История растёт в твоём темпе — улитка-архивариус одобряет.
- **Fish Drama 3:** `[warm]Ты собрал 39 недель наблюдений в дневнике ощущений. История растёт <soft>в твоём темпе</soft> — [playful]улитка-архивариус одобряет.`
- **Image prompt:** A curious snail carries a small clothbound diary as its shell, pausing to inspect a leaf with one raised eyestalk; a short accordion of diary pages trails behind it, holding little pressed leaves from earlier stops.

#### 2. Тетрадь раздвигает стены

- **ID:** `reflection.reflection_year:t2`
- **Порог:** 52 неделя наблюдений
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Уже 52 недели наблюдений в твоём дневнике ощущений — ты собрал историю, которой тесно в одной тетради.
- **Fish Drama 3:** `[confident]Уже <emphasis>52 недели наблюдений</emphasis> в твоём дневнике ощущений — [excited]ты собрал историю, которой тесно в одной тетради.`
- **Image prompt:** A snail carries a thick diary shell opened into two great fans of pages; it uses a broad leaf as a reading desk while its eyestalks examine a long accordion insert spilling neatly around its foot.

#### 3. Читальный зал на спине

- **ID:** `reflection.reflection_year:t3`
- **Порог:** 78 неделя наблюдений
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 78 недель наблюдений в дневнике ощущений. Улитка открывает читальный зал — прямо у себя на спине!
- **Fish Drama 3:** `[triumphant]Ты собрал <emphasis>78 недель наблюдений</emphasis> в дневнике ощущений. Улитка открывает читальный зал — <slow>прямо у себя на спине!</slow>`
- **Image prompt:** A snail's enormous diary shell opens into a reading room with bookshelves and a tiny armchair; the snail curls around to sit inside its own shell, reading a leaf-shaped book while its tail politely holds the door open.

## Мир историй

### `story.world_days`

**Правило:** Возвращаться в один сюжетный мир в разные дни. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день в одном мире. **Источник:** `requires_story`.

#### 1. Коврик тебя помнит

- **ID:** `story.world_days:t1`
- **Порог:** 3 день в одном мире
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 3 разных дня в одном сюжетном мире. Даже местный коврик узнаёт твои шаги.
- **Fish Drama 3:** `[warm] В твоей истории уже 3 разных дня в одном сюжетном мире. [playful] Даже местный коврик узнаёт твои шаги.`
- **Image prompt:** A small fox with an oversized satchel knocks on a crooked mushroom cottage door. The welcome mat curls up to greet its familiar boots, while a little porch stool waits beside the entrance.

#### 2. Крючок для своих

- **ID:** `story.world_days:t2`
- **Порог:** 7 день в одном мире
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты возвращаешься в один сюжетный мир уже 7 разных дней. Для твоего рюкзака здесь явно пора выделить личный крючок.
- **Fish Drama 3:** `[confident] Ты возвращаешься в один сюжетный мир уже 7 разных дней. [playful] Для твоего рюкзака здесь явно пора выделить <emphasis>личный крючок.</emphasis>`
- **Image prompt:** A small fox hangs its oversized satchel on a dedicated wooden hook beside a crooked mushroom cottage door. The door leans open expectantly, and the curled welcome mat offers a tiny leaf in greeting.

#### 3. Домик подаёт тапочки

- **ID:** `story.world_days:t3`
- **Порог:** 15 день в одном мире
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 15 разных дней в одном сюжетном мире. Теперь домик сам выносит тебе тапочки.
- **Fish Drama 3:** `[triumphant] В твоей истории уже 15 разных дней в одном сюжетном мире. <slow>Теперь домик</slow> [pause] сам выносит тебе тапочки.`
- **Image prompt:** A small fox with an oversized satchel watches a crooked mushroom cottage bend down on root legs and extend a tray of fluffy slippers in its root arms. The familiar welcome mat has rolled itself into a tiny footstool.

### `story.explorer`

**Правило:** Сохранить тренировки в разных сюжетных архетипах. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** сюжетный мир. **Источник:** `requires_story`.

#### 1. Багаж с сюжетом

- **ID:** `story.explorer:t1`
- **Порог:** 3 сюжетный мир
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты сохранил тренировки в 3 разных сюжетных мирах. Твой спортивный чемодан явно вместительнее, чем кажется.
- **Fish Drama 3:** `[warm] Ты сохранил тренировки в 3 разных сюжетных мирах. [playful] Твой спортивный чемодан явно <emphasis>вместительнее, чем кажется.</emphasis>`
- **Image prompt:** A walking suitcase with gloved hands and hiking boots holds its lid open, revealing a jungle vine, a tiny rocket, and a castle turret tucked into separate compartments. Its handle curls upward in surprise.

#### 2. Чемодан широких взглядов

- **ID:** `story.explorer:t2`
- **Порог:** 6 сюжетный мир
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В 6 разных сюжетных мирах уже есть твои сохранённые тренировки. Чемодан освоил профессию межмирового грузчика.
- **Fish Drama 3:** `[confident] В 6 разных сюжетных мирах уже есть твои сохранённые тренировки. [playful] Чемодан освоил профессию <emphasis>межмирового грузчика.</emphasis>`
- **Image prompt:** A walking suitcase with gloved hands and hiking boots balances six miniature doorways on a fold-out luggage rack. Jungle leaves, lunar rocks, ocean spray, desert dunes, castle stairs, and snowy peaks spill from the openings.

#### 3. Сам себе туроператор

- **ID:** `story.explorer:t3`
- **Порог:** 10 сюжетный мир
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В 10 разных сюжетных мирах ты сохранил тренировки. Чемодан теперь сам выдаёт порталы — вот тебе и ручная кладь.
- **Fish Drama 3:** `[triumphant] В 10 разных сюжетных мирах ты сохранил тренировки. Чемодан теперь сам выдаёт порталы — [pause] <emphasis>вот тебе и ручная кладь.</emphasis>`
- **Image prompt:** A walking suitcase with gloved hands and hiking boots unfolds into a travel counter surrounded by ten tiny world portals. One hand reaches into a jungle portal and emerges from a lunar portal to shake its other hand.

### `story.acts`

**Правило:** Выполнить обязательные baseline-условия сюжетных актов. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** акт истории. **Источник:** `requires_story`.

#### 1. Сюжет выходит на мост

- **ID:** `story.acts:t1`
- **Порог:** 3 акт истории
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил обязательные базовые условия 3 актов истории. Бобёр за кулисами установил мост: сюжет может топать дальше.
- **Fish Drama 3:** `[warm] Ты выполнил обязательные базовые условия 3 актов истории. [playful] Бобёр за кулисами установил мост: сюжет может топать дальше.`
- **Image prompt:** A small beaver stagehand with a canvas tool belt pushes a wooden bridge section into place on a miniature theater stage, one paw resting on a lever while a shy dragon puppet peeks through a partly opened curtain.

#### 2. За рычагами сюжета

- **ID:** `story.acts:t2`
- **Порог:** 10 акт истории
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Уже в 10 актах истории ты выполнил обязательные базовые условия. Бобёр крутит рычаги, а ты двигаешь сюжет — без тебя дракон просто мебель.
- **Fish Drama 3:** `[confident] Уже в 10 актах истории ты выполнил обязательные базовые условия. [playful] Бобёр крутит рычаги, а ты двигаешь сюжет — без тебя дракон просто <emphasis>мебель</emphasis>.`
- **Image prompt:** The same tool-belted beaver stands at a bank of levers, lifting a jointed wooden dragon over a rotating bridge set; taut control ropes converge around its paws as the compact stage becomes a busy storytelling machine.

#### 3. Дракон с чайной начинкой

- **ID:** `story.acts:t3`
- **Порог:** 30 акт истории
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты выполнил обязательные базовые условия 30 актов истории. Дракон раскрыл пасть, а там — бобёр с чаем: у сюжета антракт.
- **Fish Drama 3:** `[triumphant] Ты выполнил обязательные базовые условия 30 актов истории. Дракон раскрыл пасть, <slow>а там —</slow> [playful] бобёр с чаем: у сюжета антракт.`
- **Image prompt:** The same tool-belted beaver lounges with a teacup inside the open jaws of an enormous hinged stage dragon, its control levers still within reach; the dragon's folded wooden body fills the stage behind this tiny surprise operator.

### `story.finale`

**Правило:** Завершить исходный план тренировки с выбранным сценарием. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** финал по плану. **Источник:** `requires_story`.

#### 1. Титры на месте

- **ID:** `story.finale:t1`
- **Порог:** 1 финал по плану
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты завершил исходный план тренировки с выбранным сценарием — это твой первый такой финал. Титры можно отпускать со смены.
- **Fish Drama 3:** `[warm] Ты завершил исходный план тренировки с выбранным сценарием — это твой <emphasis>первый такой финал</emphasis>. [playful] Титры можно отпускать со смены.`
- **Image prompt:** A small penguin projectionist in a plain waistcoat lifts a freshly rewound film reel from a hand-cranked projector, holding it with both flippers as the last loose strip curls neatly back onto the spool.

#### 2. Катушки знают порядок

- **ID:** `story.finale:t2`
- **Порог:** 5 финал по плану
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты уже 5 раз завершил исходный план тренировки с выбранным сценарием. Катушки строятся в очередь: знают, кто здесь ведёт сюжет.
- **Fish Drama 3:** `[confident] Ты уже <emphasis>5 раз</emphasis> завершил исходный план тренировки с выбранным сценарием. [playful] Катушки строятся в очередь: знают, кто здесь ведёт сюжет.`
- **Image prompt:** The same waistcoated penguin projectionist guides a row of completed film reels into a compact rack beside its projector, using a long winding handle as if conducting a very orderly mechanical orchestra.

#### 3. Проектор тоже артист

- **ID:** `story.finale:t3`
- **Порог:** 15 финал по плану
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты уже 15 раз завершил исходный план тренировки с выбранным сценарием. Проектор показал титры и… сам вышел на поклон.
- **Fish Drama 3:** `[triumphant] Ты уже <emphasis>15 раз</emphasis> завершил исходный план тренировки с выбранным сценарием. Проектор показал титры и… <slow>сам вышел на поклон.</slow>`
- **Image prompt:** The same waistcoated penguin projectionist bows beside a movie projector standing on its own articulated legs; the projector bends its lens in an exaggerated bow while a broad loop of film curls behind the unlikely performing duo.

### `story.return_world`

**Правило:** Вернуться в знакомый архетип после двадцати восьми дней. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** возвращение в мир. **Источник:** `requires_story`.

#### 1. Рукопожатие с дверью

- **ID:** `story.return_world:t1`
- **Порог:** 1 возвращение в мир
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты впервые вернулся в знакомый архетип спустя 28 дней. Дверь узнала тебя и пожала чемодану ручку.
- **Fish Drama 3:** `[warm]Ты впервые вернулся в знакомый архетип спустя 28 дней. Дверь узнала тебя и пожала чемодану ручку.`
- **Image prompt:** A scuffed walking suitcase pauses at a familiar arched doorway. The door bends its handle outward to shake the suitcase handle, while the suitcase lifts one little foot over the well-worn threshold.

#### 2. Чемодан знает дорогу

- **ID:** `story.return_world:t2`
- **Порог:** 3 возвращение в мир
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 3 возвращения в знакомые архетипы спустя 28 дней разлуки. Чемодан проходит знакомые двери без навигатора.
- **Fish Drama 3:** `[confident]У тебя уже <emphasis>3 возвращения</emphasis> в знакомые архетипы спустя 28 дней разлуки. Чемодан проходит знакомые двери без навигатора.`
- **Image prompt:** The scuffed walking suitcase strides through three familiar arched doorways arranged in a zigzag. It confidently reaches backward to close one door while another swings open ahead, its bent handle held high.

#### 3. Двери идут в гости

- **ID:** `story.return_world:t3`
- **Порог:** 6 возвращение в мир
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 6 возвращений в знакомые архетипы после 28 дней разлуки. Теперь двери сами приходят к твоему чемодану — соскучились!
- **Fish Drama 3:** `[triumphant]Ты накопил 6 возвращений в знакомые архетипы после 28 дней разлуки. Теперь двери сами приходят к твоему чемодану — <slow>соскучились!</slow>`
- **Image prompt:** The scuffed walking suitcase holds its lid open like a welcoming host. Six familiar arched doors on tiny feet queue to climb inside, the first folding its hinges inward to squeeze through the unexpectedly small entrance.

### `story.archive`

**Правило:** Накопить дни с сохранённым локальным или облачным эпизодом. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** день с эпизодом. **Источник:** `requires_story`.

#### 1. Первый ящик историй

- **ID:** `story.archive:t1`
- **Порог:** 5 день с эпизодом
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** За твоей спиной уже 5 дней с сохранённым эпизодом — локально или в облаке. Маленький архив открыл первый ящик.
- **Fish Drama 3:** `[warm]За твоей спиной уже 5 дней с сохранённым эпизодом — локально или в облаке. Маленький архив открыл первый ящик.`
- **Image prompt:** A small octopus librarian slides a closed episode folder into a single open drawer, steadying the cabinet with another arm. A few more folders wait in a neat fan beside it, each with a plain tab.

#### 2. Архив на колёсах

- **ID:** `story.archive:t2`
- **Порог:** 20 день с эпизодом
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 20 дней с сохранёнными эпизодами, локально или в облаке. Архив уже катается на тележке: у историй появился багаж.
- **Fish Drama 3:** `[playful]Ты собрал 20 дней с сохранёнными эпизодами, локально или в облаке. Архив уже катается на тележке: у историй появился багаж.`
- **Image prompt:** The small octopus librarian balances episode folders across its arms while sorting them into a rolling cabinet. One arm catches a folder slipping from the top, and another quietly closes an overstuffed drawer.

#### 3. Восемь рук памяти

- **ID:** `story.archive:t3`
- **Порог:** 50 день с эпизодом
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя накопилось 50 дней с сохранённым эпизодом — локально или в облаке. Архиву нужен библиотекарь с восемью руками.
- **Fish Drama 3:** `[confident]У тебя накопилось <emphasis>50 дней</emphasis> с сохранённым эпизодом — локально или в облаке. Архиву нужен библиотекарь с восемью руками.`
- **Image prompt:** The small octopus librarian conducts a semicircle of tall filing cabinets, opening drawers with several arms at once. A low cart carries the next stack of episode folders, and one free arm points it toward an empty shelf.

#### 4. Стеллажи разевают рты

- **ID:** `story.archive:t4`
- **Порог:** 100 день с эпизодом
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 100 дней с сохранёнными эпизодами, локально или в облаке. Архив вырос выше стеллажей и впервые зевнул.
- **Fish Drama 3:** `[excited]В твоей истории уже 100 дней с сохранёнными эпизодами, локально или в облаке. Архив вырос выше стеллажей и впервые зевнул.`
- **Image prompt:** The small octopus librarian stands beneath an arch of towering filing cabinets, guiding episode folders down a spiral chute into open drawers. A huge cabinet begins to yawn while the octopus peers up in surprise.

#### 5. Сказка для архива

- **ID:** `story.archive:t5`
- **Порог:** 200 день с эпизодом
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 200 дней с сохранённым эпизодом — локально или в облаке. Архив вырос и требует сказку на ночь!
- **Fish Drama 3:** `[triumphant]Ты собрал 200 дней с сохранённым эпизодом — локально или в облаке. Архив вырос и требует <slow>сказку на ночь!</slow>`
- **Image prompt:** The small octopus librarian reads an open book beside a gigantic living filing cabinet tucked into a bed. The cabinet hugs a stack of episode folders as it dozes, while one octopus arm gently shuts its last yawning drawer.

### `story.world_return`

**Правило:** Встретить один сюжетный архетип в разных календарных месяцах. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** месяц одного мира. **Источник:** `requires_story`.

#### 1. Мир припас тапочки

- **ID:** `story.world_return:t1`
- **Порог:** 2 месяц одного мира
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Один сюжетный архетип встретился тебе в 2 разных календарных месяцах. Этот мир уже припас для тебя тапочки.
- **Fish Drama 3:** `[warm] Один сюжетный архетип встретился тебе в 2 разных календарных месяцах. [playful] Этот мир уже припас для тебя тапочки.`
- **Image prompt:** A tiny cottage with an open-book roof leans forward, offering oversized slippers through its doorway with two gloved hands; two blank calendar leaves curl around the doorstep like arriving visitors.

#### 2. Кресло за тобой

- **ID:** `story.world_return:t2`
- **Порог:** 4 месяц одного мира
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 4 разных календарных месяца с одним сюжетным архетипом. В этом мире твоё кресло больше никому не выдают.
- **Fish Drama 3:** `[confident] У тебя уже 4 разных календарных месяца с одним сюжетным архетипом. [playful] В этом мире <emphasis>твоё кресло</emphasis> больше никому не выдают.`
- **Image prompt:** The little open-book-roof cottage uses both gloved hands to install a plush armchair on its expanding porch; slippers wait beneath the seat, while four blank calendar leaves fan out above the doorway.

#### 3. Мир с чемоданом

- **ID:** `story.world_return:t3`
- **Порог:** 8 месяц одного мира
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Один сюжетный архетип встретился тебе в 8 разных календарных месяцах. Теперь мир пришёл к тебе с чемоданом — пожить.
- **Fish Drama 3:** `[triumphant] Один сюжетный архетип встретился тебе в 8 разных календарных месяцах. [playful] Теперь мир пришёл к тебе с чемоданом <slow>— пожить.</slow>`
- **Image prompt:** The open-book-roof cottage stands in enormous slippers outside a much larger apartment door, knocking with one gloved hand and gripping a bulging suitcase with the other; blank calendar leaves poke out of its luggage.

### `story.world_chapters`

**Правило:** Собирать триптихи: минимум три дня в каждом из трёх разных архетипов. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** триптих миров. **Источник:** `requires_story`.

#### 1. Театр на три мира

- **ID:** `story.world_chapters:t1`
- **Порог:** 1 триптих миров
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты собрал 1 триптих: минимум по 3 дня в каждом из 3 разных сюжетных архетипов. У твоего театра миров уже три сцены.
- **Fish Drama 3:** `[warm] Ты собрал 1 триптих: минимум по 3 дня в каждом из 3 разных сюжетных архетипов. [playful] У твоего театра миров уже <emphasis>три сцены.</emphasis>`
- **Image prompt:** A small stagehand crab unfolds a single hinged triptych stage with its claws; the panels contain a forest, a rolling sea and a mountain pass, each reached by a neat trail of three stepping stones.

#### 2. Битва за гримёрку

- **ID:** `story.world_chapters:t2`
- **Порог:** 2 триптих миров
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Теперь у тебя 2 триптиха; для каждого — минимум по 3 дня в каждом из 3 разных сюжетных архетипов. Сюжеты уже спорят за гримёрку.
- **Fish Drama 3:** `[confident] Теперь у тебя 2 триптиха; для каждого — минимум по 3 дня в каждом из 3 разных сюжетных архетипов. [playful] Сюжеты уже спорят за <emphasis>гримёрку.</emphasis>`
- **Image prompt:** The stagehand crab balances two open triptych stages on opposite sides of a tiny dressing table; each stage holds forest, sea and mountain scenery, and both sets of curtains tug toward the same mirror.

#### 3. Чайник возглавил многомирье

- **ID:** `story.world_chapters:t3`
- **Порог:** 3 триптих миров
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя 3 триптиха: в каждом — минимум по 3 дня в каждом из 3 разных сюжетных архетипов. Многомирье требует главного, и ты назначаешь чайник.
- **Fish Drama 3:** `[triumphant] У тебя 3 триптиха: в каждом — минимум по 3 дня в каждом из 3 разных сюжетных архетипов. [playful] Многомирье требует главного, <slow>и ты назначаешь</slow> <emphasis>чайник.</emphasis>`
- **Image prompt:** The stagehand crab hoists a steaming kettle into a tall director's chair amid three open triptych stages, each containing forest, sea and mountain scenes; the crab solemnly offers the kettle a megaphone.

### `story.world_months`

**Правило:** Сохранять эпизоды в разных календарных месяцах. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** месяц историй. **Источник:** `requires_story`.

#### 1. Улитка открывает архив

- **ID:** `story.world_months:t1`
- **Порог:** 2 месяц историй
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В 2 разных календарных месяцах ты сохранил эпизоды. Улитка-архивариус завела вторую папку — дело набирает ход!
- **Fish Drama 3:** `[warm]В 2 разных календарных месяцах ты сохранил эпизоды. Улитка-архивариус завела вторую папку — <emphasis>дело набирает ход!</emphasis>`
- **Image prompt:** A bespectacled snail opens a tiny filing drawer built into its spiral shell, placing a saved episode reel into the second of two folders. Its feelers lean eagerly toward the new folder while the first bulges with keepsakes.

#### 2. Ракушка с читальным залом

- **ID:** `story.world_months:t2`
- **Порог:** 6 месяц историй
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Уже в 6 разных календарных месяцах ты сохранял эпизоды. У улитки-архивариуса теперь не ракушка, а филиал библиотеки.
- **Fish Drama 3:** `[confident]Уже в 6 разных календарных месяцах ты сохранял эпизоды. У улитки-архивариуса теперь не ракушка, а <emphasis>филиал библиотеки.</emphasis>`
- **Image prompt:** A bespectacled snail tends a growing library inside its spiral shell, with six open drawers holding episode reels. It balances on a sliding ladder to shelve a fresh reel, while a leaf-shaped bookmark pokes from an overstuffed folder.

#### 3. Календарь в очереди

- **ID:** `story.world_months:t3`
- **Порог:** 12 месяц историй
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты сохранил эпизоды в 12 разных календарных месяцах! Улитка-архивариус открыла приём: теперь календарь стоит к ней в очереди.
- **Fish Drama 3:** `[triumphant]Ты сохранил эпизоды в 12 разных календарных месяцах! Улитка-архивариус открыла приём: [pause]<slow>теперь календарь стоит к ней в очереди.</slow>`
- **Image prompt:** A bespectacled snail runs a check-in counter beneath its enormous spiral-shell archive. A queue of walking blank calendar pads waits with episode reels; the snail calmly stamps a folder while the last calendar drags a folding stool.

### `story.story_weeks`

**Правило:** Сохранять эпизоды в разных неделях. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** неделя историй. **Источник:** `requires_story`.

#### 1. Хвост в первом ряду

- **ID:** `story.story_weeks:t1`
- **Порог:** 4 неделя историй
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты сохранил эпизоды в 4 разных неделях. Бобр-киномеханик включил проектор — даже хвост занял место в первом ряду.
- **Fish Drama 3:** `[warm]Ты сохранил эпизоды в 4 разных неделях. Бобр-киномеханик включил проектор — <emphasis>даже хвост занял место в первом ряду.</emphasis>`
- **Image prompt:** A beaver projectionist threads a film strip through a compact projector beside four saved episode reels. Its broad tail accidentally occupies the only audience chair, and it twists around to shoo its own tail away.

#### 2. Премьера на плотине

- **ID:** `story.story_weeks:t2`
- **Порог:** 12 неделя историй
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Эпизоды ты сохранял уже в 12 разных неделях. Бобр-киномеханик развернул экран на плотине: твоей истории тесно в будке.
- **Fish Drama 3:** `[confident]Эпизоды ты сохранял уже в 12 разных неделях. Бобр-киномеханик развернул экран на плотине: <emphasis>твоей истории тесно в будке.</emphasis>`
- **Image prompt:** A beaver projectionist hauls a wide folded screen onto its wooden dam beside a tall rack of saved episode reels and a larger projector. Its tail pins down the screen's stand as curious fish gather at the waterline.

#### 3. Река требует продолжения

- **ID:** `story.story_weeks:t3`
- **Порог:** 26 неделя историй
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты сохранил эпизоды в 26 разных неделях — бобр-киномеханик открыл речной кинотеатр! Рыбы требуют продолжения — и водостойкий попкорн.
- **Fish Drama 3:** `[triumphant]Ты сохранил эпизоды в 26 разных неделях — бобр-киномеханик открыл речной кинотеатр! Рыбы требуют продолжения — [pause]<slow>и водостойкий попкорн.</slow>`
- **Image prompt:** A beaver projectionist operates a giant reel-powered projector atop its dam, turning a waterfall into a cinema screen. Fish queue below at a submerged popcorn hatch, each carrying a sealed snack jar, while the beaver's tail serves as the ticket ramp.

## Большие главы

### `chapter.30_days`

**Правило:** Тридцать дней пути и шесть тренировочных дней; прогресс учитывает обе части. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 18, 24. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Закладка обживается

- **ID:** `chapter.30_days:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 50% главы с целями в 30 дней пути и 6 тренировочных дней. Закладка уже обжилась, но тапочки пока не принесла.
- **Fish Drama 3:** `[warm]Ты собрал 50% главы с целями в 30 дней пути и 6 тренировочных дней. [playful]Закладка уже обжилась, но тапочки пока не принесла.`
- **Image prompt:** A chunky blank journal with stubby legs hikes along a curling paper trail, holding a dumbbell-shaped bookmark as a walking stick; half its pages fan upward, and a tiny pair of slippers peeks from between the leaves.

#### 2. Сюжет набрал ход

- **ID:** `chapter.30_days:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 18 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 75% главы с целями в 30 дней пути и 6 тренировочных дней. Сюжет разогнался так, что закладка пристегнулась.
- **Fish Drama 3:** `[confident]У тебя <emphasis>75% главы</emphasis> с целями в 30 дней пути и 6 тренировочных дней. [playful]Сюжет разогнался так, что закладка пристегнулась.`
- **Image prompt:** The chunky blank journal rides a sled folded from its own loose pages down a sweeping paper ramp; its stubby legs point forward, and the dumbbell-shaped bookmark sits snugly beneath a ribbon seat belt.

#### 3. Книжный шезлонг

- **ID:** `chapter.30_days:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 24 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты прошёл 30 дней пути и набрал 6 тренировочных дней — глава закрыта на 100%. Книга так довольна финалом, что разложилась в шезлонг.
- **Fish Drama 3:** `[triumphant]Ты прошёл 30 дней пути и набрал 6 тренировочных дней — глава закрыта на 100%. [playful]Книга так довольна финалом, что <slow>разложилась в шезлонг</slow>.`
- **Image prompt:** The chunky blank journal reclines in a deckchair folded from its own final pages, stubby legs crossed; its dumbbell-shaped bookmark supports a page parasol while two pocket notebooks wait beside it with tiny towels.

### `chapter.90_days`

**Правило:** Девяносто дней пути и восемнадцать тренировочных дней; прогресс учитывает обе части. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Чайник в экспедиции

- **ID:** `chapter.90_days:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Позади 50% главы с целями в 90 дней пути и 18 тренировочных дней — ты проложил маршрут. Черепаха-экспедитор ставит чайник: есть что отметить.
- **Fish Drama 3:** `[warm]Позади 50% главы с целями в 90 дней пути и 18 тренировочных дней — ты проложил маршрут. [playful]Черепаха-экспедитор ставит чайник: есть что отметить.`
- **Image prompt:** A small tortoise explorer pulls a wagon carrying a camping kettle across a bridge made from a folded blank map; it pauses with one foot on a smooth stone, holding a teacup toward the kettle's curling steam.

#### 2. Компас доверия

- **ID:** `chapter.90_days:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты освоил 75% главы с целями в 90 дней пути и 18 тренировочных дней. Черепаха доверила тебе компас, но печенье всё ещё держит под охраной.
- **Fish Drama 3:** `[confident]Ты освоил <emphasis>75% главы</emphasis> с целями в 90 дней пути и 18 тренировочных дней. [playful]Черепаха доверила тебе компас, но печенье всё ещё держит под охраной.`
- **Image prompt:** The tortoise explorer stands on its kettle wagon to offer a compass outward; a biscuit tin is tucked securely beneath one foreleg, while a long blank map unfurls behind the wheels and climbs over a ridge.

#### 3. Слово предоставляется печенью

- **ID:** `chapter.90_days:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты прошёл 90 дней пути и набрал 18 тренировочных дней — глава закрыта на 100%. Экспедиция объявляет привал с главным докладчиком — печеньем.
- **Fish Drama 3:** `[triumphant]Ты прошёл 90 дней пути и набрал 18 тренировочных дней — глава закрыта на 100%. [playful]Экспедиция объявляет привал с главным докладчиком — <slow>печеньем</slow>.`
- **Image prompt:** The tortoise explorer sits at a picnic table folded from its blank map, kettle wagon parked alongside; a single biscuit stands upright at the head of the table while the tortoise listens attentively with a teacup poised.

### `chapter.365_days`

**Правило:** Год пути и сорок тренировочных дней; прогресс учитывает обе части. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Закладка в пути

- **ID:** `chapter.365_days:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 50% главы о годе пути и 40 тренировочных днях: в зачёт идут обе части. Календарь уже придерживает закладку.
- **Fish Drama 3:** `[warm]У тебя 50% главы о годе пути и 40 тренировочных днях: в зачёт идут обе части. Календарь уже придерживает закладку.`
- **Image prompt:** A tortoise pushes a little wooden book cart carrying an enormous half-open journal; a spring twig and an autumn leaf peek between its pages, while the tortoise steadies a loose bookmark with one determined paw.

#### 2. Сюжет набирает ход

- **ID:** `chapter.365_days:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** На твоём счету 75% главы о годе пути и 40 тренировочных днях. Время и тренировочные дни вместе двигают сюжет — календарь читает стоя.
- **Fish Drama 3:** `[confident]На твоём счету <emphasis>75% главы</emphasis> о годе пути и 40 тренировочных днях. [playful]Время и тренировочные дни вместе двигают сюжет — календарь читает стоя.`
- **Image prompt:** A tortoise climbs a staircase of thick journals stacked on its wooden book cart, using a long bookmark as a handrail; near the top, it reaches toward an open volume with a pine sprig tucked between its pages.

#### 3. Календарь просит автограф

- **ID:** `chapter.365_days:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** За тобой год пути и 40 тренировочных дней — ты закрыл 100% главы. Календарь встал за автографом — с раскладушкой.
- **Fish Drama 3:** `[triumphant]За тобой год пути и 40 тренировочных дней — ты закрыл <emphasis>100% главы</emphasis>. [playful]Календарь встал за автографом — <slow>с раскладушкой.</slow>`
- **Image prompt:** A tortoise turns its wooden book cart into an author signing booth, sitting behind an enormous open journal with a quill; an eager walking desk calendar with blank pages unfolds a camping cot at the head of the queue.

### `chapter.foundation`

**Правило:** Пятнадцать тренировочных дней и четыре активные недели. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Первый замес

- **ID:** `chapter.foundation:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Твои 50% главы «Фундамент» складываются из прогресса к 15 тренировочным дням и 4 активным неделям. Ты строишь базу, а не декорацию для гантели.
- **Fish Drama 3:** `[warm]Твои 50% главы «Фундамент» складываются из прогресса к 15 тренировочным дням и 4 активным неделям. [playful]Ты строишь базу, а не декорацию для гантели.`
- **Image prompt:** A beaver builder kneels beside a partially laid square brick foundation, carefully placing a corner brick with a small trowel; a tiny kettlebell waits nearby on a wooden handcart as if expecting its own house.

#### 2. Кирпичи с характером

- **ID:** `chapter.foundation:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 75% главы «Фундамент», где учитываются и 15 тренировочных дней, и 4 активные недели. Кирпичи уже перестали делать вид, что они просто интерьер.
- **Fish Drama 3:** `[confident]Ты собрал <emphasis>75% главы «Фундамент»</emphasis>, где учитываются и 15 тренировочных дней, и 4 активные недели. [playful]Кирпичи уже перестали делать вид, что они просто интерьер.`
- **Image prompt:** A beaver builder uses a small lever to slide a broad slab onto a nearly completed brick foundation; the tiny kettlebell waits on its wooden handcart beside a short access ramp, with one unfinished corner still visible.

#### 3. Приёмка в тапочках

- **ID:** `chapter.foundation:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал фундамент на 100%: 15 тренировочных дней и 4 активные недели. Лень пришла на приёмку — в каске и тапочках.
- **Fish Drama 3:** `[triumphant]Ты собрал фундамент на <emphasis>100%</emphasis>: 15 тренировочных дней и 4 активные недели. [playful]Лень пришла на приёмку — <slow>в каске и тапочках.</slow>`
- **Image prompt:** A beaver builder proudly presents a massive completed brick foundation supporting one tiny kettlebell; a sloth inspector wearing a hard hat and oversized fluffy slippers examines it with a blank clipboard tucked under one arm.

### `chapter.craft`

**Правило:** Тридцать дней, сто пятьдесят подходов и двенадцать активных недель. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Каркас большой истории

- **ID:** `chapter.craft:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 50% главы с целями: 30 дней, 150 подходов и 12 активных недель. В мастерской твоей истории уже шуршит стружка.
- **Fish Drama 3:** `[warm]Ты собрал <emphasis>50% главы</emphasis> с целями: 30 дней, 150 подходов и 12 активных недель. [playful]В мастерской твоей истории уже шуршит стружка.`
- **Image prompt:** A beaver carpenter in a pocket apron braces a half-built rocking chair and fits its first curved runner. Wooden dumbbell-shaped armrests lie beside a compact toolbox, ready for the next stage.

#### 2. Столярный размах

- **ID:** `chapter.craft:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя 75% главы с целями: 30 дней, 150 подходов и 12 активных недель. Кресло мастерства обретает форму — можно примерять важный вид.
- **Fish Drama 3:** `[confident]У тебя <emphasis>75% главы</emphasis> с целями: 30 дней, 150 подходов и 12 активных недель. [playful]Кресло мастерства обретает форму — можно примерять важный вид.`
- **Image prompt:** A beaver carpenter in a pocket apron tightens a dumbbell-shaped armrest on a nearly finished rocking chair. Both curved runners are fitted; a tiny teacup waits on the workbench beside the final seat cushion.

#### 3. Молоток подаёт чай

- **ID:** `chapter.craft:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты закрыл 100% главы: 30 дней, 150 подходов и 12 активных недель в твоей истории. Садись в кресло мастера — молоток теперь подаёт чай.
- **Fish Drama 3:** `[triumphant]Ты закрыл <emphasis>100% главы</emphasis>: 30 дней, 150 подходов и 12 активных недель в твоей истории. Садись в кресло мастера — [playful]<slow>молоток теперь подаёт чай.</slow>`
- **Image prompt:** A beaver in a pocket apron lounges in the completed rocking chair with dumbbell-shaped armrests. A walking claw hammer solemnly serves a teacup on a tray, while the beaver props its feet on the toolbox.

### `chapter.atlas`

**Правило:** Шестьдесят дней и двадцать шесть активных недель. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Панцирь дальних маршрутов

- **ID:** `chapter.atlas:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты прошёл 50% главы с целями: 60 дней и 26 активных недель. Черепаха-картограф расправила карту: у этой истории есть размах.
- **Fish Drama 3:** `[warm]Ты прошёл <emphasis>50% главы</emphasis> с целями: 60 дней и 26 активных недель. [playful]Черепаха-картограф расправила карту: у этой истории есть размах.`
- **Image prompt:** A tortoise cartographer with a rolled-map backpack fits a curved map panel onto a small unfinished globe in a wheeled cradle. An unfurled map trails from the backpack, curling around one patient forefoot.

#### 2. Глобусу стало тесно

- **ID:** `chapter.atlas:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** За тобой 75% главы с целями: 60 дней и 26 активных недель. У черепахи-картографа глобус уже не помещается под мышкой.
- **Fish Drama 3:** `[confident]За тобой <emphasis>75% главы</emphasis> с целями: 60 дней и 26 активных недель. [playful]У черепахи-картографа глобус уже не помещается под мышкой.`
- **Image prompt:** A tortoise cartographer with a rolled-map backpack leans into a much larger globe on its wheeled cradle. One forefoot steadies the globe while the other holds a map that now looks comically tiny beside it.

#### 3. Экскурсия для планеты

- **ID:** `chapter.atlas:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 60 дней и 26 активных недель — глава закрыта на 100%. Теперь глобус записался к тебе на экскурсию.
- **Fish Drama 3:** `[triumphant]В твоей истории уже 60 дней и 26 активных недель — глава закрыта на <emphasis>100%</emphasis>. Теперь [playful]<slow>глобус записался к тебе на экскурсию.</slow>`
- **Image prompt:** A tortoise cartographer with a rolled-map backpack leads an enormous walking globe along a curling map path, pointing ahead with a guide stick. The globe wears hiking boots and clutches a tiny folded map upside down.

### `chapter.balance`

**Правило:** Базовые ступени регулярности, практики и наблюдений или плана. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Щупальца порядка

- **ID:** `chapter.balance:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты прошёл 50% главы баланса: регулярность, практика и наблюдения или план складываются в систему. Осьминог-организатор уже перестал путать гантель с блокнотом.
- **Fish Drama 3:** `[warm]Ты прошёл 50% главы баланса: регулярность, практика и наблюдения или план складываются в систему. [playful]Осьминог-организатор уже перестал путать гантель с блокнотом.`
- **Image prompt:** A round-headed octopus steadies a small seesaw with a dumbbell on one end and an open notebook on the other. A rolled exercise mat rests beside it; two curled arms cautiously adjust the plank.

#### 2. Восемь рук в деле

- **ID:** `chapter.balance:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории — 75% главы баланса с её регулярностью, практикой и наблюдениями или планом. Осьминог навёл порядок даже среди собственных щупалец.
- **Fish Drama 3:** `[confident]В твоей истории — <emphasis>75% главы баланса</emphasis> с её регулярностью, практикой и наблюдениями или планом. [playful]Осьминог навёл порядок даже среди собственных щупалец.`
- **Image prompt:** A round-headed octopus operates a revolving three-tray stand carrying a dumbbell, a rolled exercise mat, and an open notebook. Its arms weave neatly between the trays, with one spare arm catching a slipping pencil.

#### 3. Всё схвачено, чай заварен

- **ID:** `chapter.balance:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты завершил главу баланса на 100%: базовые ступени регулярности, практики и наблюдений или плана пройдены. Осьминог всё схватил — и оставил щупальце для чая.
- **Fish Drama 3:** `[triumphant]Ты завершил главу баланса на 100%: базовые ступени регулярности, практики и наблюдений или плана пройдены. [playful]Осьминог всё схватил — <slow>и оставил щупальце для чая.</slow>`
- **Image prompt:** A round-headed octopus reclines in a rocking chair woven from four of its own arms. Three other arms neatly hold a dumbbell, a rolled exercise mat, and an open notebook; the last arm raises a tiny teacup with absolute composure.

### `chapter.worlds`

**Правило:** Десять миров, тридцать сюжетных дней и двенадцать активных недель. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `requires_story`.

#### 1. Ракушка с пересадкой

- **ID:** `chapter.worlds:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты прошёл 50% главы о 10 мирах, 30 сюжетных днях и 12 активных неделях. Улитка-проводник уложила приключения в чемодан — носок тоже влез.
- **Fish Drama 3:** `[warm]Ты прошёл 50% главы о 10 мирах, 30 сюжетных днях и 12 активных неделях. [playful]Улитка-проводник уложила приключения в чемодан — носок тоже влез.`
- **Image prompt:** A tiny explorer snail peers into its half-open suitcase-shaped shell, where a winding path crosses miniature island worlds. One feeler props up the lid as the snail tests a little bridge; a rolled sock sits in a side pocket.

#### 2. Миры ручной клади

- **ID:** `chapter.worlds:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** За твоими плечами 75% главы о 10 мирах, 30 сюжетных днях и 12 активных неделях. В чемодане улитки у носка уже появились соседи.
- **Fish Drama 3:** `[confident]За твоими плечами <emphasis>75% главы</emphasis> о 10 мирах, 30 сюжетных днях и 12 активных неделях. [playful]В чемодане улитки у носка уже появились соседи.`
- **Image prompt:** A tiny explorer snail unfolds its suitcase-shaped shell into a branching network of miniature worlds connected by arched bridges. It stretches between two islands to rearrange them; a rolled sock is squeezed into a narrow gap.

#### 3. Вселенная помещается, носок нет

- **ID:** `chapter.worlds:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты завершил главу на 100%: 10 миров, 30 сюжетных дней и 12 активных недель в твоей истории. Вселенная в чемодан влезла, а носок — нет!
- **Fish Drama 3:** `[triumphant]Ты завершил главу на 100%: 10 миров, 30 сюжетных дней и 12 активных недель в твоей истории. [playful]Вселенная в чемодан влезла, <slow>а носок — нет!</slow>`
- **Image prompt:** A tiny explorer snail tries to close its suitcase-shaped shell around a swirling cluster of miniature worlds linked by winding paths. One oversized sock sticks out and blocks the lid; the snail presses down with a baffled expression.

### `chapter.second_year`

**Правило:** Два года пути, восемьдесят дней и пятьдесят две активные недели. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Календарь обулся

- **ID:** `chapter.second_year:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты прошёл 50% главы о двух годах пути, 80 днях тренировок и 52 активных неделях. Календарь надел походные ботинки!
- **Fish Drama 3:** `[warm]Ты прошёл 50% главы о двух годах пути, 80 днях тренировок и 52 активных неделях. Календарь надел <emphasis>походные ботинки!</emphasis>`
- **Image prompt:** A walking desk calendar in chunky hiking boots crosses a bridge made of folded calendar sheets, gripping a rope anchored to a kettlebell. Its blank grid face tilts upward toward a distant paper mountain.

#### 2. Выше настенной должности

- **ID:** `chapter.second_year:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя 75% главы «Второй год»: три четверти длинного маршрута уже позади. Календарь больше не считает себя настенным жителем.
- **Fish Drama 3:** `[confident]У тебя <emphasis>75% главы «Второй год»</emphasis>: три четверти длинного маршрута уже позади. [playful]Календарь больше не считает себя настенным жителем.`
- **Image prompt:** The booted desk calendar climbs a steep spiral staircase of folded pages, hauling a tiny alarm clock on a sled. One boot rests on a high landing, while the last paper switchback curls toward the summit.

#### 3. Будильник, подай тапочки

- **ID:** `chapter.second_year:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты завершил 100% главы: два года пути, 80 дней тренировок и 52 активные недели. Календарь на вершине, будильник — в должности подставки для ног.
- **Fish Drama 3:** `[triumphant]Ты завершил 100% главы: два года пути, 80 дней тренировок и 52 активные недели. Календарь на вершине, <slow>будильник —</slow> [playful]в должности подставки для ног.`
- **Image prompt:** The booted desk calendar lounges in a folding chair atop the paper mountain, resting both feet on an enormous sleeping alarm clock. A loose calendar page serves as its sunshade, and the tiny sled is parked beside the chair.

### `chapter.veteran`

**Правило:** Сто двадцать дней, тысяча подходов и пятьдесят две активные недели. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** % главы. **Источник:** `available`.

#### 1. Архив на лапах

- **ID:** `chapter.veteran:t1`
- **Порог:** 50 % главы
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 50% главы на пути к 120 дням тренировок, 1000 подходам и 52 активным неделям. Архив твоей истории уже просит отдельную полку.
- **Fish Drama 3:** `[warm]Ты собрал 50% главы на пути к 120 дням тренировок, 1000 подходам и 52 активным неделям. Архив твоей истории уже просит <emphasis>отдельную полку.</emphasis>`
- **Image prompt:** A sturdy tortoise carries a small wooden shelf across its shell, with plain-spined training journals tucked between dumbbell bookends. It carefully slides one more journal into place with a front foot.

#### 2. Тихо, подходы записываются

- **ID:** `chapter.veteran:t2`
- **Порог:** 75 % главы
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В главе «Ветеран» у тебя уже 75% пути к 120 дням тренировок, 1000 подходам и 52 активным неделям. Железо в твоём архиве само переходит на шёпот.
- **Fish Drama 3:** `[confident]В главе «Ветеран» у тебя уже <emphasis>75% пути</emphasis> к 120 дням тренировок, 1000 подходам и 52 активным неделям. [playful]Железо в твоём архиве само переходит на шёпот.`
- **Image prompt:** The tortoise now carries a two-tier library shelf fitted neatly around its shell. Two tiny walking dumbbells push a cart of plain-spined journals up a short ramp, while the tortoise raises one foot in a gentle shushing gesture.

#### 3. Железо в читальном зале

- **ID:** `chapter.veteran:t3`
- **Порог:** 100 % главы
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За твоими 100% главы «Ветеран» — 120 дней тренировок, 1000 подходов и 52 активные недели. Железо пришло за опытом — и получило читательский билет.
- **Fish Drama 3:** `[triumphant]За твоими 100% главы «Ветеран» — 120 дней тренировок, 1000 подходов и 52 активные недели. Железо пришло за опытом <slow>— и получило</slow> [playful]читательский билет.`
- **Image prompt:** The tortoise's shell has become a grand mobile library packed with plain-spined training journals. It sits at a checkout desk built into the shell, handing a tiny library card to a barbell as dumbbells queue with books.

## Точность тренажёра

### `measured.rhythm`

**Правило:** Накопить подходы с валидным коэффициентом вариации длительности повторений. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** стабильный подход. **Источник:** `requires_sensor`.

#### 1. Железо на репетиции

- **ID:** `measured.rhythm:t1`
- **Порог:** 3 стабильный подход
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 3 стабильных подхода по данным датчика. Железо поймало ритм — и пока не просит сольную партию.
- **Fish Drama 3:** `[warm] У тебя уже 3 стабильных подхода по данным датчика. [playful] Железо поймало ритм — и пока не просит сольную партию.`
- **Image prompt:** A lively wooden metronome with stubby feet and a conductor's baton cues a small dumbbell tapping a saucepan drum. Its pendulum leans into the beat while the dumbbell waits attentively beside a low rehearsal stand.

#### 2. Оркестр набирает ход

- **ID:** `measured.rhythm:t2`
- **Порог:** 10 стабильный подход
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** На твоём счету 10 стабильных подходов по данным датчика. У железного оркестра уже есть репертуар, а не только «бум».
- **Fish Drama 3:** `[confident] На твоём счету <emphasis>10 стабильных подходов</emphasis> по данным датчика. [playful] У железного оркестра уже есть репертуар, а не только «бум».`
- **Image prompt:** A wooden metronome conductor stands on a rehearsal stool, directing a trio of animated dumbbells playing pots and pans. Its baton sweeps above the players as one dumbbell eagerly raises a ladle for its carefully timed entrance.

#### 3. Железная филармония

- **ID:** `measured.rhythm:t3`
- **Порог:** 30 стабильный подход
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 30 стабильных подходов по данным датчика. Железо доигралось: теперь у штанги сольная партия на треугольнике.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>30 стабильных подходов</emphasis> по данным датчика. [playful] Железо доигралось: теперь у штанги сольная партия <slow>на треугольнике.</slow>`
- **Image prompt:** A wooden metronome conductor presents an enormous barbell musician delicately striking a tiny triangle. The conductor stretches its baton toward the absurdly small instrument while dumbbell percussionists lean forward in hushed anticipation.

### `measured.rhythm_days`

**Правило:** Накопить дни с двумя валидными стабильными подходами. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день стабильности. **Источник:** `requires_sensor`.

#### 1. Пара в папке

- **ID:** `measured.rhythm_days:t1`
- **Порог:** 3 день стабильности
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории — 3 дня с двумя стабильными подходами по данным датчика. Улитка-архивариус бережно подшила каждую пару.
- **Fish Drama 3:** `[warm] В твоей истории — 3 дня с двумя стабильными подходами по данным датчика. Улитка-архивариус <soft>бережно подшила каждую пару.</soft>`
- **Image prompt:** A bespectacled snail archivist slides an open folder holding two miniature dumbbells into a low wooden filing tray. Its simple spiral shell tilts with the effort, and one eyestalk checks that the paired contents sit neatly together.

#### 2. Раковина с картотекой

- **ID:** `measured.rhythm_days:t2`
- **Порог:** 10 день стабильности
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя накопилось 10 дней с двумя стабильными подходами по данным датчика. Улитка-архивариус уже просит не полку, а шкаф.
- **Fish Drama 3:** `[confident] У тебя накопилось <emphasis>10 дней</emphasis> с двумя стабильными подходами по данным датчика. [playful] Улитка-архивариус уже просит не полку, а шкаф.`
- **Image prompt:** A bespectacled snail archivist carries a compact filing cabinet balanced over its spiral shell. Open drawers reveal folders holding paired miniature dumbbells, while the snail uses a long grabber to tuck another folder into the highest drawer.

#### 3. Филиал на рожках

- **ID:** `measured.rhythm_days:t3`
- **Порог:** 25 день стабильности
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 25 дней с двумя стабильными подходами по данным датчика. Улитка-архивариус открыла филиал — в собственной раковине.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>25 дней</emphasis> с двумя стабильными подходами по данным датчика. [playful] Улитка-архивариус открыла филиал — <slow>в собственной раковине.</slow>`
- **Image prompt:** A bespectacled snail proudly rings a tiny reception bell as its enormous spiral shell unfolds into a bustling archive. Curving shelves hold folders of paired dumbbells, and a miniature cargo lift delivers another folder to the top.

### `measured.repeatable`

**Правило:** Повторить ритм одного упражнения в разные дни с близкой медианой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** сопоставимая пара. **Источник:** `requires_sensor`.

#### 1. Маятник узнал ритм

- **ID:** `measured.repeatable:t1`
- **Порог:** 1 сопоставимая пара
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 1 сопоставимую пару: ритм одного упражнения в разные дни дал близкие медианы. Метроном улыбается маятником.
- **Fish Drama 3:** `[warm] Ты собрал 1 сопоставимую пару: ритм одного упражнения в разные дни дал близкие медианы. [playful] Метроном улыбается маятником.`
- **Image prompt:** A small wooden metronome with expressive eyes and tiny arms stands between two suspended kettlebells, carefully matching their swing arcs with its hands; its own pendulum leans into the shared rhythm.

#### 2. Гири держат такт

- **ID:** `measured.repeatable:t2`
- **Порог:** 5 сопоставимая пара
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 5 сопоставимых пар: ритм одного упражнения в разные дни — с близкими медианами. Метроном достал дирижёрскую палочку.
- **Fish Drama 3:** `[confident] У тебя уже <emphasis>5 сопоставимых пар</emphasis>: ритм одного упражнения в разные дни — с близкими медианами. [playful] Метроном достал дирижёрскую палочку.`
- **Image prompt:** The wooden metronome raises a conductor's baton before a compact row of kettlebell pendulums; their matching swings form parallel arcs while its free hand confidently cues the next movement.

#### 3. Оркестр скрипучего железа

- **ID:** `measured.repeatable:t3`
- **Порог:** 15 сопоставимая пара
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 15 сопоставимых пар: ритм одного упражнения в разные дни — с близкими медианами. Метроном собрал оркестр гирь, а солирует скрипучая гантель.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>15 сопоставимых пар</emphasis>: ритм одного упражнения в разные дни — с близкими медианами. Метроном собрал оркестр гирь, [playful] <slow>а солирует скрипучая гантель.</slow>`
- **Image prompt:** The wooden metronome conducts a semicircle of swinging kettlebells from a tiny podium; a jointed dumbbell soloist leans into an absurdly dramatic bow at center stage while the conductor throws both arms wide.

### `measured.verified_workouts`

**Правило:** Накопить тренировки с доказанным датчиковым происхождением. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** подтверждённая тренировка. **Источник:** `requires_sensor`.

#### 1. Датчик с квитанцией

- **ID:** `measured.verified_workouts:t1`
- **Порог:** 3 подтверждённая тренировка
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 3 тренировки с подтверждённым датчиковым происхождением. Датчик принёс квитанции — железное алиби.
- **Fish Drama 3:** `[warm] Ты накопил 3 тренировки с подтверждённым датчиковым происхождением. [playful] Датчик принёс квитанции — железное алиби.`
- **Image prompt:** A small spool-shaped sensor robot balances on a single roller, proudly offering a neat stack of blank record cards; its other arm steadies a tiny filing cart with one open drawer.

#### 2. Архив на колёсах

- **ID:** `measured.verified_workouts:t2`
- **Порог:** 10 подтверждённая тренировка
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 10 тренировок с подтверждённым датчиковым происхождением. Датчик катит архив: у каждого занятия своё дело.
- **Fish Drama 3:** `[confident] В твоей истории уже <emphasis>10 тренировок</emphasis> с подтверждённым датчиковым происхождением. [playful] Датчик катит архив: у каждого занятия своё дело.`
- **Image prompt:** The spool-shaped sensor robot leans forward to push a tall filing trolley, its drawers packed with blank folders; one arm catches a fanned stack of record cards before they tumble over the front wheel.

#### 3. Личный кабинет датчика

- **ID:** `measured.verified_workouts:t3`
- **Порог:** 25 подтверждённая тренировка
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 25 тренировок с подтверждённым датчиковым происхождением. Датчик завёл личный кабинет — и сел в шкаф.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>25 тренировок</emphasis> с подтверждённым датчиковым происхождением. Датчик завёл личный кабинет — [playful] <slow>и сел в шкаф.</slow>`
- **Image prompt:** The spool-shaped sensor robot sits inside the oversized open drawer of a filing cabinet, using it as a private office; a miniature desk rests across its lap, with blank folders forming stairs up to the drawer.

### `measured.verified_sets`

**Правило:** Накопить подходы с валидным датчиковым provenance. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** подтверждённый подход. **Источник:** `requires_sensor`.

#### 1. Железные улики

- **ID:** `measured.verified_sets:t1`
- **Порог:** 10 подтверждённый подход
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 10 подходов, подтверждённых датчиком. Железо пришло не с отговоркой, а с уликами.
- **Fish Drama 3:** `[warm] У тебя уже 10 подходов, подтверждённых датчиком. Железо пришло не с отговоркой, <emphasis>а с уликами.</emphasis>`
- **Image prompt:** A small robot archivist with a bent antenna receives a curling sensor strip from a barbell and files it into a plain folder; a chunky stamp rests beside its first neat stack of workout records.

#### 2. Досье толще блинов

- **ID:** `measured.verified_sets:t2`
- **Порог:** 50 подтверждённый подход
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 50 подходов, подтверждённых датчиком. На штангу уже собрано досье толще её блинов.
- **Fish Drama 3:** `[confident] Ты накопил <emphasis>50 подходов</emphasis>, подтверждённых датчиком. На штангу уже собрано досье толще её блинов.`
- **Image prompt:** The bent-antenna robot archivist rides a sliding ladder along a shelf packed with thick folders; a barbell props up an enormous open dossier, while a long sensor strip curls into the next waiting folder.

#### 3. Справка для железа

- **ID:** `measured.verified_sets:t3`
- **Порог:** 150 подтверждённый подход
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя накопилось 150 подходов, подтверждённых датчиком! Железо явилось за справкой, что оно действительно железо.
- **Fish Drama 3:** `[triumphant] У тебя накопилось <emphasis>150 подходов</emphasis>, подтверждённых датчиком! [playful] Железо явилось за справкой, <slow>что оно действительно железо.</slow>`
- **Image prompt:** The bent-antenna robot archivist presides over a counter built from bulging folders, handing a blank certificate to a hulking barbell with tiny feet; the barbell bows politely to fit beneath the desk lamp.

### `measured.verified_days`

**Правило:** Накопить дни с валидными датчиковыми результатами. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150, 240. Не подряд; без повышения нагрузки ради награды. **Единица:** подтверждённый день. **Источник:** `requires_sensor`.

#### 1. Дни в ручной клади

- **ID:** `measured.verified_days:t1`
- **Порог:** 3 подтверждённый день
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Твои 3 дня с подтверждёнными датчиком результатами уже в копилке. Календарная черепаха пакует первый багаж.
- **Fish Drama 3:** `[warm] Твои 3 дня с подтверждёнными датчиком результатами уже в копилке. Календарная черепаха пакует <soft>первый багаж.</soft>`
- **Image prompt:** A round-shelled tortoise with a tiny travel satchel pulls a small handcart carrying three thick blank calendar leaves; one folded corner peeks over the rim as the tortoise glances back with a pleased little grin.

#### 2. Календарь с багажником

- **ID:** `measured.verified_days:t2`
- **Порог:** 10 подтверждённый день
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 10 дней с подтверждёнными датчиком результатами. Черепаха прицепила календарю багажник: история уже не помещается в карман.
- **Fish Drama 3:** `[playful] Ты собрал 10 дней с подтверждёнными датчиком результатами. Черепаха прицепила календарю багажник: история уже <emphasis>не помещается в карман.</emphasis>`
- **Image prompt:** The round-shelled tortoise fastens a rear luggage rack to its calendar cart; thick blank calendar leaves fill the basket, and a neatly tied stack rides above the wheels as the tortoise checks the balance.

#### 3. Дни на полках

- **ID:** `measured.verified_days:t3`
- **Порог:** 25 подтверждённый день
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории 25 дней с результатами, подтверждёнными датчиком. Черепаха превратила тележку в библиотеку: дни теперь стоят на полках.
- **Fish Drama 3:** `[confident] В твоей истории <emphasis>25 дней</emphasis> с результатами, подтверждёнными датчиком. Черепаха превратила тележку в библиотеку: дни теперь стоят на полках.`
- **Image prompt:** The tortoise has converted its calendar cart into a rolling library of thick blank calendar leaves; standing on a low step, it slides one leaf onto a shelf while its familiar travel satchel rests by a wheel.

#### 4. Верхняя палуба календаря

- **ID:** `measured.verified_days:t4`
- **Порог:** 50 подтверждённый день
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** За тобой уже 50 дней с подтверждёнными датчиком результатами! Календарная тележка стала двухэтажной — черепаха открыла верхнюю палубу.
- **Fish Drama 3:** `[excited] За тобой уже <emphasis>50 дней</emphasis> с подтверждёнными датчиком результатами! Календарная тележка стала двухэтажной — черепаха открыла верхнюю палубу.`
- **Image prompt:** The calendar cart has grown into a double-decker wagon, its shelves loaded with blank calendar leaves; the round-shelled tortoise unfolds an upper deck beside a tiny staircase, with its travel satchel at its feet.

#### 5. Календарь на побегушках

- **ID:** `measured.verified_days:t5`
- **Порог:** 100 подтверждённый день
- **Подтверждённая практика:** минимум 240 разных дней; оба условия обязательны.
- **Ступень:** Наследие
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 100 дней с подтверждёнными датчиком результатами! Календарь отрастил лапы и сам повёз черепаху — вот это сервис.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>100 дней</emphasis> с подтверждёнными датчиком результатами! [playful] Календарь отрастил лапы и сам повёз черепаху — <slow>вот это сервис.</slow>`
- **Image prompt:** The cart of blank calendar leaves now strides on folded-paper legs, carrying the round-shelled tortoise in a cushioned deck chair; its travel satchel rests nearby while a page-shaped arm offers a drink on a tray.

### `measured.verified_reps`

**Правило:** Накопить повторения с валидным датчиковым provenance. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** подтверждённое повторение. **Источник:** `requires_sensor`.

#### 1. У повторов есть алиби

- **ID:** `measured.verified_reps:t1`
- **Порог:** 100 подтверждённое повторение
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал первые 100 повторений, подтверждённых датчиком. У каждого теперь железное алиби.
- **Fish Drama 3:** `[warm] Ты собрал первые <emphasis>100 повторений</emphasis>, подтверждённых датчиком. У каждого теперь железное алиби.`
- **Image prompt:** A small single-lens robot clerk stamps a blank paper strip emerging from a gym cable handle. One hand holds the strip steady while a neatly folded tail of approved paper rests beside a tiny filing tray.

#### 2. Бюро честных повторов

- **ID:** `measured.verified_reps:t2`
- **Порог:** 500 подтверждённое повторение
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоём архиве уже 500 повторений, подтверждённых датчиком. Бюро учёта просит второй шкаф.
- **Fish Drama 3:** `[confident] В твоём архиве уже <emphasis>500 повторений</emphasis>, подтверждённых датчиком. [playful] Бюро учёта просит второй шкаф.`
- **Image prompt:** A single-lens robot clerk packs an accordion-folded blank paper trail into twin filing cabinets. A gym cable handle feeds fresh paper beside the crowded desk, while the robot holds its rubber stamp ready above the next fold.

#### 3. Погрузчик для печати

- **ID:** `measured.verified_reps:t3`
- **Порог:** 1500 подтверждённое повторение
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 1500 повторений, подтверждённых датчиком. В бюро учёта печать теперь ставят погрузчиком.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>1500 повторений</emphasis>, подтверждённых датчиком. В бюро учёта печать теперь ставят <slow>погрузчиком</slow>.`
- **Image prompt:** A single-lens robot clerk drives a tiny forklift, lowering an enormous rubber stamp onto a broad blank paper trail from a gym cable handle. The robot's old hand stamp sits on an abandoned desk like a retired employee.

### `measured.calibrated`

**Правило:** Накопить тренировки с зафиксированной валидной калибровкой. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** калиброванная тренировка. **Источник:** `requires_sensor`.

#### 1. Ключ к настройке

- **ID:** `measured.calibrated:t1`
- **Порог:** 3 калиброванная тренировка
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 3 тренировки с подтверждённой калибровкой. Выдра-механик довольно хмыкнула и убрала ключ.
- **Fish Drama 3:** `[warm] У тебя уже <emphasis>3 тренировки</emphasis> с подтверждённой калибровкой. Выдра-механик довольно хмыкнула и убрала ключ.`
- **Image prompt:** An otter mechanic hangs an adjustable wrench on a small tool rack beside a gym cable machine. Its other paw closes a sensor housing near the pulley, and its whiskered face carries a satisfied little smile.

#### 2. Репетиция без суеты

- **ID:** `measured.calibrated:t2`
- **Порог:** 10 калиброванная тренировка
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты собрал 10 тренировок с подтверждённой калибровкой. У выдры-механика уже не мастерская, а репетиционный зал.
- **Fish Drama 3:** `[confident] Ты собрал <emphasis>10 тренировок</emphasis> с подтверждённой калибровкой. [playful] У выдры-механика уже не мастерская, а репетиционный зал.`
- **Image prompt:** An otter mechanic stands before a semicircle of gym cable machines, raising an adjustable wrench like a rehearsal baton. Open sensor housings rest beside each pulley, and the exercise handles lean inward like attentive musicians.

#### 3. Соло разводного ключа

- **ID:** `measured.calibrated:t3`
- **Порог:** 25 калиброванная тренировка
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** За тобой 25 тренировок с подтверждённой калибровкой. Выдра дирижирует тренажёрами, а соло исполняет разводной ключ.
- **Fish Drama 3:** `[triumphant] За тобой <emphasis>25 тренировок</emphasis> с подтверждённой калибровкой. Выдра дирижирует тренажёрами, а соло исполняет <slow>разводной ключ</slow>.`
- **Image prompt:** An otter mechanic conducts a sweeping orchestra of gym cable machines from a tool crate. An oversized adjustable wrench stands at a microphone as the soloist, its open jaws tilted upward, while pulley handles bow toward it.

### `measured.paired_sides`

**Правило:** Накопить дни с канонически подтверждёнными подходами на обе стороны. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день двух сторон. **Источник:** `requires_sensor`.

#### 1. Обе в деле

- **ID:** `measured.paired_sides:t1`
- **Порог:** 2 день двух сторон
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 2 дня с подтверждёнными датчиком подходами на обе стороны. Краб-учётчик проверил: левая и правая в деле.
- **Fish Drama 3:** `[warm] Ты накопил 2 дня с подтверждёнными датчиком подходами на обе стороны. Краб-учётчик проверил: <emphasis>левая и правая в деле.</emphasis>`
- **Image prompt:** A clerk crab stands between two opposing exercise levers, gripping one in each claw; two blank workout slips rest in an open ledger, each beside a matching pair of illuminated sensor indicators.

#### 2. Парность набирает обороты

- **ID:** `measured.paired_sides:t2`
- **Порог:** 8 день двух сторон
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 8 дней с подтверждёнными датчиком подходами на обе стороны. Краб-учётчик ставит печати двумя клешнями — очередь движется!
- **Fish Drama 3:** `[confident] В твоей истории уже 8 дней с подтверждёнными датчиком подходами на обе стороны. [playful] Краб-учётчик ставит печати двумя клешнями — очередь движется!`
- **Image prompt:** The clerk crab balances on a swivel stool between twin streams of blank workout cards, pressing a stamp with each claw; paired exercise levers flank the desk, and neatly matched card stacks rise behind it.

#### 3. Отдел двух клешней

- **ID:** `measured.paired_sides:t3`
- **Порог:** 20 день двух сторон
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 20 дней с подтверждёнными датчиком подходами на обе стороны. Краб-учётчик открыл отдел парности — штат: две клешни.
- **Fish Drama 3:** `[triumphant] У тебя уже 20 дней с подтверждёнными датчиком подходами на обе стороны. [playful] Краб-учётчик открыл отдел парности — <slow>штат:</slow> <emphasis>две клешни.</emphasis>`
- **Image prompt:** The clerk crab towers over two miniature office booths, inserting one claw into each booth to stamp paired exercise records; its body waits proudly between them as long chains of blank paired tickets curl outward.

### `measured.range_days`

**Правило:** Накопить дни с валидной сохранённой моделью границ каждого повторения. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75. Не подряд; без повышения нагрузки ради награды. **Единица:** день диапазона. **Источник:** `requires_sensor`.

#### 1. Первое дело улитки

- **ID:** `measured.range_days:t1`
- **Порог:** 2 день диапазона
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 2 дня с сохранённой моделью границ каждого повтора, которая прошла проверку. Улитка-архивариус открывает ящик.
- **Fish Drama 3:** `[warm] Ты накопил 2 дня с сохранённой моделью границ каждого повтора, которая прошла проверку. Улитка-архивариус <soft>открывает ящик.</soft>`
- **Image prompt:** An archivist snail slides a translucent curved motion strip with two endpoint tabs into a drawer in its shell; a small open storage tray holds another neatly secured strip, and the snail checks the fit with one antenna.

#### 2. Полки держат строй

- **ID:** `measured.range_days:t2`
- **Порог:** 8 день диапазона
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Уже 8 дней в твоей копилке — с сохранённой и корректной моделью границ каждого повтора. У архивной улитки шкаф пошёл на расширение.
- **Fish Drama 3:** `[confident] Уже 8 дней в твоей копилке — с сохранённой и корректной моделью границ каждого повтора. [playful] У архивной улитки шкаф пошёл <emphasis>на расширение.</emphasis>`
- **Image prompt:** The archivist snail braces against an expanding drawer-shell, sorting curved motion strips with paired endpoint tabs into several open compartments; its antennae stretch in opposite directions to keep the busy drawers organized.

#### 3. Шкаф на выгуле

- **ID:** `measured.range_days:t3`
- **Порог:** 20 день диапазона
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории 20 дней с сохранённой и проверенной моделью границ каждого повтора. Архивная улитка доросла до отдела — теперь шкаф выгуливает её.
- **Fish Drama 3:** `[triumphant] В твоей истории 20 дней с сохранённой и проверенной моделью границ каждого повтора. [playful] Архивная улитка доросла до отдела — <slow>теперь</slow> <emphasis>шкаф выгуливает её.</emphasis>`
- **Image prompt:** A tiny archivist snail rides beneath its enormous drawer-shell, now walking on folding mechanical legs; open drawers reveal curved motion records with paired endpoint tabs, while the snail calmly steers with two antennae.

## Практика конкретных упражнений

### `exercise.butt-kick`

**Правило:** Практиковать butt-kick в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Пятки вышли на связь

- **ID:** `exercise.butt-kick:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 12 разных дней практики захлёстов голени: в каждый — минимум два полных рабочих подхода или 60 фактических секунд. Пятки передают привет, диван слегка озадачен.
- **Fish Drama 3:** `[warm] У тебя уже 12 разных дней практики захлёстов голени: в каждый — минимум два полных рабочих подхода или 60 фактических секунд. Пятки передают привет, диван слегка озадачен.`
- **Image prompt:** A small wind-up rabbit in oversized sneakers practices a backward heel kick on a folded exercise mat. One long ear follows the lifted heel, while a curious house slipper peeks around the mat beside a couch leg.

#### 2. Пятки в рабочем составе

- **ID:** `exercise.butt-kick:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Захлёсты голени с тобой уже 30 разных тренировочных дней — минимум два полных рабочих подхода или 60 фактических секунд в каждый. Пятки стали постоянными героями, а не случайными гостями.
- **Fish Drama 3:** `[playful] Захлёсты голени с тобой уже <emphasis>30 разных тренировочных дней</emphasis> — минимум два полных рабочих подхода или 60 фактических секунд в каждый. Пятки стали постоянными героями, а не случайными гостями.`
- **Image prompt:** The same wind-up rabbit alternates backward heel kicks on a small rehearsal platform, its long ears swinging in opposite directions. Two house slippers act as stagehands, tugging open a pair of oversized couch cushions like curtains.

#### 3. Пятки держат сцену

- **ID:** `exercise.butt-kick:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** 75 разных дней практики захлёстов голени — ты собрал солидную историю, не марафон без выходных. В каждом дне — минимум два полных рабочих подхода или 60 фактических секунд. Диван уже просит автограф.
- **Fish Drama 3:** `[confident] <emphasis>75 разных дней</emphasis> практики захлёстов голени — ты собрал солидную историю, не марафон без выходных. В каждом дне — минимум два полных рабочих подхода или 60 фактических секунд. [playful] Диван уже просит автограф.`
- **Image prompt:** The wind-up rabbit performs backward heel kicks at center stage, one sneaker lifted behind its body. A large couch leans eagerly toward the performer, extending a cushion and a pencil, while slipper stagehands watch from the wings.

#### 4. Диван аплодирует подушками

- **ID:** `exercise.butt-kick:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 150 разных дней практики захлёстов голени, в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Пятки дают большой концерт, а диван — аплодирует подушками!
- **Fish Drama 3:** `[triumphant] У тебя <emphasis>150 разных дней</emphasis> практики захлёстов голени, в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [playful] Пятки дают большой концерт, <slow>а диван —</slow> аплодирует подушками!`
- **Image prompt:** The wind-up rabbit takes center stage with a jubilant backward heel kick and ears flung wide. A gigantic couch in the front row claps two plump cushions together, while a crowd of house slippers rises onto its toes in applause.

### `exercise.cardio-knee-taps`

**Правило:** Практиковать cardio-knee-taps в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Колено, дай пять

- **ID:** `exercise.cardio-knee-taps:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 12 разных дней подъёмов коленей с касанием ладонями: минимум два полных рабочих подхода или 60 фактических секунд в каждый. Колени и ладони представились — можно без визиток.
- **Fish Drama 3:** `[warm] Ты накопил 12 разных дней подъёмов коленей с касанием ладонями: минимум два полных рабочих подхода или 60 фактических секунд в каждый. Колени и ладони представились — можно без визиток.`
- **Image prompt:** A little kettle robot with hinged legs and mitten hands lifts one knee to meet its open palm. Its curved spout points toward the contact, while a curious soup ladle leans out of a nearby utensil holder to watch.

#### 2. Ритм без барабана

- **ID:** `exercise.cardio-knee-taps:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 30 разных дней практики подъёмов коленей с касанием ладонями. Каждый засчитан за минимум два полных рабочих подхода или 60 фактических секунд. Ритм уже свой, барабан пока не нужен.
- **Fish Drama 3:** `[playful] У тебя <emphasis>30 разных дней</emphasis> практики подъёмов коленей с касанием ладонями. Каждый засчитан за минимум два полных рабочих подхода или 60 фактических секунд. Ритм уже свой, барабан пока не нужен.`
- **Image prompt:** The kettle robot taps a raised knee with one mitten hand, its other hand ready for the next alternating lift. Two teacups balance on little stools as an audience, and the soup ladle keeps time with a gentle sideways swing.

#### 3. Кухня ловит ритм

- **ID:** `exercise.cardio-knee-taps:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** За 75 разных дней подъёмов коленей с касанием ладонями ты собрал целый репертуар: в каждый — минимум два полных рабочих подхода или 60 фактических секунд. Кастрюли требуют сольный номер!
- **Fish Drama 3:** `[confident] За <emphasis>75 разных дней</emphasis> подъёмов коленей с касанием ладонями ты собрал целый репертуар: в каждый — минимум два полных рабочих подхода или 60 фактических секунд. [excited] Кастрюли требуют сольный номер!`
- **Image prompt:** The kettle robot performs alternating knee taps in front of a semicircle of saucepan musicians. Pot lids hover like waiting cymbals, the soup ladle conducts from a wooden spoon rest, and every handle points toward the robot's lifted knee.

#### 4. Барабан ушёл пить чай

- **ID:** `exercise.cardio-knee-taps:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** 150 разных дней подъёмов коленей с касанием ладонями — твой большой концерт: в каждый день минимум два полных рабочих подхода или 60 фактических секунд. Колени держат ритм, а барабан — ушёл пить чай!
- **Fish Drama 3:** `[triumphant] <emphasis>150 разных дней</emphasis> подъёмов коленей с касанием ладонями — твой большой концерт: в каждый день минимум два полных рабочих подхода или 60 фактических секунд. [playful] Колени держат ритм, <slow>а барабан —</slow> ушёл пить чай!`
- **Image prompt:** The kettle robot taps its raised knee atop a conductor's podium as saucepan musicians applaud with their lids. Beside the podium, an enormous bass drum lounges in a tiny kitchen chair, delicately sipping tea from a comically small cup.

### `exercise.cardio-quick-feet`

**Правило:** Практиковать cardio-quick-feet в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Воробей выходит на бит

- **ID:** `exercise.cardio-quick-feet:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты набрал 12 разных тренировочных дней с «Быстрыми ногами»: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Воробьиный степ начался.
- **Fish Drama 3:** `[warm]Ты набрал 12 разных тренировочных дней с «Быстрыми ногами»: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. <soft>Воробьиный степ начался.</soft>`
- **Image prompt:** A sparrow in oversized training sneakers taps both feet on a small practice drum, wings spread for balance; a lone drumstick rests across the rim, and shallow dents beneath the shoes reveal its busy rhythm.

#### 2. Два барабана счастья

- **ID:** `exercise.cardio-quick-feet:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 30 разных тренировочных дней «Быстрых ног»: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Воробью выдали второй барабан.
- **Fish Drama 3:** `[playful]У тебя уже 30 разных тренировочных дней «Быстрых ног»: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Воробью выдали <emphasis>второй барабан.</emphasis>`
- **Image prompt:** A sparrow in oversized training sneakers straddles two snare drums, one foot on each, sending loose drumsticks spinning upward; a little metronome leans in from the side as if trying to follow the duet.

#### 3. Пернатый хедлайнер

- **ID:** `exercise.cardio-quick-feet:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** 75 разных тренировочных дней с «Быстрыми ногами» у тебя в истории: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Воробей дорос до сольного концерта.
- **Fish Drama 3:** `[confident]75 разных тренировочных дней с «Быстрыми ногами» у тебя в истории: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [excited]Воробей дорос до сольного концерта.`
- **Image prompt:** A sparrow in oversized training sneakers performs atop a sprawling drum kit, feet landing on separate drumheads and wings lifting cymbals; a metronome in the front row holds its pendulum still to watch.

#### 4. Беруши для метронома

- **ID:** `exercise.cardio-quick-feet:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 150 разных тренировочных дней «Быстрых ног»: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Метроном заказал беруши.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 разных тренировочных дней «Быстрых ног»: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [playful]Метроном заказал <slow>беруши.</slow>`
- **Image prompt:** A sparrow in oversized training sneakers tap-dances on a towering bass drum; beside it, a tall metronome struggles to fit enormous padded earmuffs over its pointed top while a spare drumstick hangs midair.

### `exercise.smith-machine-bench-press`

**Правило:** Практиковать smith-machine-bench-press в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Первый этаж Смита

- **ID:** `exercise.smith-machine-bench-press:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты практиковал жим лёжа в Смите 12 разных тренировочных дней: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Гриф уже знает свой этаж.
- **Fish Drama 3:** `[warm]Ты практиковал жим лёжа в Смите 12 разных тренировочных дней: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. <soft>Гриф уже знает свой этаж.</soft>`
- **Image prompt:** A beaver in work gloves lies on a bench, gripping a bar guided by the twin rails of a Smith machine; a tiny elevator call button is fitted to one upright, and the beaver eyes it with mild curiosity.

#### 2. Лифтёр уже в курсе

- **ID:** `exercise.smith-machine-bench-press:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 30 разных тренировочных дней жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Бобёр-лифтёр уже узнаёт тебя без звонка.
- **Fish Drama 3:** `[playful]У тебя 30 разных тренировочных дней жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Бобёр-лифтёр уже узнаёт тебя <emphasis>без звонка.</emphasis>`
- **Image prompt:** A work-gloved beaver stands beside the bench of a Smith machine and presses an oversized elevator call button on its upright; the racked bar waits between the rails, with a tiny suitcase tucked under the bench.

#### 3. Смит открывает отель

- **ID:** `exercise.smith-machine-bench-press:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории — 75 разных тренировочных дней жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Бобёр превратил станок в отель с лифтом.
- **Fish Drama 3:** `[confident]В твоей истории — 75 разных тренировочных дней жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [excited]Бобёр превратил станок в отель с лифтом.`
- **Image prompt:** A work-gloved beaver slides open little elevator doors fitted between the rails of a Smith machine, presenting its racked bar like a hotel lift; the bench serves as a reception counter with a single service bell.

#### 4. Пентхаус для утки

- **ID:** `exercise.smith-machine-bench-press:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 150 разных тренировочных дней жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Гриф теперь возит резиновую утку в пентхаус.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 разных тренировочных дней жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [playful]Гриф теперь возит <slow>резиновую утку в пентхаус.</slow>`
- **Image prompt:** A work-gloved beaver acts as lift attendant beside a Smith machine turned into a miniature hotel; a rubber duck in a bathrobe rides an open cabin attached to the bar, clutching a tiny suitcase while the bench doubles as the lobby desk.

### `exercise.smith-machine-calf-raise`

**Правило:** Практиковать smith-machine-calf-raise в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Первый рейс на носках

- **ID:** `exercise.smith-machine-calf-raise:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Подъёмы на носки в Смите ты практикуешь уже 12 разных дней: минимум два полных рабочих подхода или 60 секунд работы за день. Лифт на цыпочках запущен!
- **Fish Drama 3:** `[warm] Подъёмы на носки в Смите ты практикуешь уже 12 разных дней: минимум два полных рабочих подхода или 60 секунд работы за день. <emphasis>Лифт на цыпочках запущен!</emphasis>`
- **Image prompt:** A small elevator robot in oversized sneakers rises onto its toes between Smith-machine rails, a guided bar across its shoulders. Its chest hatch opens like a lift door, with a mouse waiting beside a miniature suitcase.

#### 2. Лифт с перерывами

- **ID:** `exercise.smith-machine-calf-raise:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 30 разных дней подъёмов на носки в Смите, в каждом — минимум два полных рабочих подхода или 60 секунд работы. Этот лифт признаёт остановки на отдых.
- **Fish Drama 3:** `[playful] У тебя уже 30 разных дней подъёмов на носки в Смите, в каждом — минимум два полных рабочих подхода или 60 секунд работы. Этот лифт признаёт <emphasis>остановки на отдых.</emphasis>`
- **Image prompt:** An elevator robot in oversized sneakers holds its heels raised beneath a guided Smith bar. A penguin carrying a teacup steps from its open chest cabin onto a tiny landing, where an unfolded deck chair awaits.

#### 3. Этаж для чаек

- **ID:** `exercise.smith-machine-calf-raise:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории — 75 разных дней подъёмов на носки в Смите: минимум два полных рабочих подхода или 60 секунд работы за день. Лифт дошёл до облаков — чайкам непривычно!
- **Fish Drama 3:** `[confident] В твоей истории — 75 разных дней подъёмов на носки в Смите: минимум два полных рабочих подхода или 60 секунд работы за день. [excited] Лифт дошёл до облаков — чайкам непривычно!`
- **Image prompt:** An oversized-sneakered elevator robot rises on tiptoe beneath a guided shoulder bar, its Smith rails extending through a cloud. Two startled gulls queue at its open chest doors while a third peers inside with a folded map.

#### 4. Тапочки для Луны

- **ID:** `exercise.smith-machine-calf-raise:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** 150 разных дней подъёмов на носки в Смите у тебя в копилке: каждый — минимум два полных рабочих подхода или 60 секунд работы. Луна вызвала лифт — за тапочками.
- **Fish Drama 3:** `[triumphant] 150 разных дней подъёмов на носки в Смите у тебя в копилке: каждый — минимум два полных рабочих подхода или 60 секунд работы. [playful] Луна вызвала лифт — <slow>за тапочками.</slow>`
- **Image prompt:** An elevator robot in oversized sneakers stands on tiptoe under a guided Smith shoulder bar. A sleepy crescent moon in a nightcap reaches into its open chest cabin for fluffy slippers, while the tiny mouse holds the lift door.

### `exercise.smith-machine-close-grip-bench-press`

**Правило:** Практиковать smith-machine-close-grip-bench-press в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Клешни за пультом

- **ID:** `exercise.smith-machine-close-grip-bench-press:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя есть 12 разных дней жима лёжа узким хватом в Смите: в каждом — минимум два полных рабочих подхода или 60 секунд работы. Гриф явно метит в дирижёры.
- **Fish Drama 3:** `[warm] У тебя есть 12 разных дней жима лёжа узким хватом в Смите: в каждом — минимум два полных рабочих подхода или 60 секунд работы. Гриф явно метит <emphasis>в дирижёры.</emphasis>`
- **Image prompt:** A small crab lies on a flat bench, pressing a guided Smith bar with its claws close together. One rubber duck watches from a folding theatre seat, while an unused conductor's baton rests across an empty music stand.

#### 2. Репетиция с утками

- **ID:** `exercise.smith-machine-close-grip-bench-press:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** Уже 30 разных дней ты находишь время для жима лёжа узким хватом в Смите: минимум два полных рабочих подхода или 60 секунд работы за день. Утки заняли первый ряд.
- **Fish Drama 3:** `[playful] Уже 30 разных дней ты находишь время для жима лёжа узким хватом в Смите: минимум два полных рабочих подхода или 60 секунд работы за день. <emphasis>Утки заняли первый ряд.</emphasis>`
- **Image prompt:** A small crab performs a close-claw bench press inside Smith rails on a miniature rehearsal stage. Four rubber ducks lean forward from the front row, their beaks opening in sequence as they follow the rising bar.

#### 3. Оркестр узкого хвата

- **ID:** `exercise.smith-machine-close-grip-bench-press:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** 75 разных дней жима лёжа узким хватом в Смите — твоя история: каждый день засчитан за минимум два полных рабочих подхода или 60 секунд работы. Гриф дирижирует, утки берут высокую ноту!
- **Fish Drama 3:** `[confident] 75 разных дней жима лёжа узким хватом в Смите — твоя история: каждый день засчитан за минимум два полных рабочих подхода или 60 секунд работы. [excited] Гриф дирижирует, утки берут высокую ноту!`
- **Image prompt:** A small crab lies beneath a Smith bar, its closely spaced claws conducting an orchestra through a bench press. Rubber ducks hold tiny cellos and trumpets in a semicircle; one duck stretches its open beak above the ensemble.

#### 4. Отпуск дирижёрской палочки

- **ID:** `exercise.smith-machine-close-grip-bench-press:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** За плечами у тебя 150 разных дней жима лёжа узким хватом в Смите: в каждом — минимум два полных рабочих подхода или 60 секунд работы. Гриф вышел на бис — палочка ушла в отпуск.
- **Fish Drama 3:** `[triumphant] За плечами у тебя 150 разных дней жима лёжа узким хватом в Смите: в каждом — минимум два полных рабочих подхода или 60 секунд работы. [playful] Гриф вышел на бис — <slow>палочка ушла в отпуск.</slow>`
- **Image prompt:** A small crab conducts a rubber-duck opera by bench-pressing a guided Smith bar with close-set claws. A huge duck soprano sings beside the bench, while an anthropomorphic conductor's baton lounges in a deck chair with its feet up.

### `exercise.smith-machine-drag-curl`

**Правило:** Практиковать smith-machine-drag-curl в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Первый рейс бицепса

- **ID:** `exercise.smith-machine-drag-curl:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 12 разных дней сгибаний рук с отведением локтей назад в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. Привычка выехала с платформы!
- **Fish Drama 3:** `[warm] Ты собрал 12 разных дней сгибаний рук с отведением локтей назад в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. Привычка <emphasis>выехала с платформы!</emphasis>`
- **Image prompt:** A little locomotive with jointed arms curls a Smith bar close to its boiler, elbows drawn backward; a short railway track ends beneath the machine, and a folded gym towel rests on the front coupler.

#### 2. Локти едут назад

- **ID:** `exercise.smith-machine-drag-curl:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя уже 30 разных дней сгибаний рук с отведением локтей назад в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждый. Локти назад, практика вперёд!
- **Fish Drama 3:** `[playful] У тебя уже 30 разных дней сгибаний рук с отведением локтей назад в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждый. Локти назад, <emphasis>практика вперёд!</emphasis>`
- **Image prompt:** The same little locomotive returns to its Smith machine platform, curling the bar close to its boiler with elbows swept back; a parked carriage holds a water bottle, and its open door forms a tiny boarding ramp.

#### 3. Личный локомотив практики

- **ID:** `exercise.smith-machine-drag-curl:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** За тобой 75 разных дней сгибаний рук с отведением локтей назад в Смите: каждый с минимум двумя полными рабочими подходами или 60 фактическими секундами. У этой практики уже целый состав!
- **Fish Drama 3:** `[confident] За тобой 75 разных дней сгибаний рук с отведением локтей назад в Смите: каждый с минимум двумя полными рабочими подходами или 60 фактическими секундами. [excited] У этой практики уже <emphasis>целый состав!</emphasis>`
- **Image prompt:** The little locomotive curls its Smith bar beneath a station canopy, keeping the bar near its boiler and elbows back; a winding row of parked carriages carries rolled gym mats, with towels hanging neatly from open windows.

#### 4. Смит покупает проездной

- **ID:** `exercise.smith-machine-drag-curl:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 150 разных дней сгибаний рук с отведением локтей назад в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. Теперь Смит просит у тебя проездной!
- **Fish Drama 3:** `[triumphant] Ты накопил 150 разных дней сгибаний рук с отведением локтей назад в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. [playful] Теперь Смит просит у тебя <slow>проездной!</slow>`
- **Image prompt:** The little locomotive curls a Smith bar close to its boiler, elbows swept back, while the machine's uprights sprout polite hands offering it a blank commuter pass; tiny carriages queue along a bustling gym platform.

### `exercise.smith-machine-incline-bench-press`

**Правило:** Практиковать smith-machine-incline-bench-press в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Космодром на наклоне

- **ID:** `exercise.smith-machine-incline-bench-press:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты отметил 12 разных дней наклонного жима лёжа в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждый. Космодром привычки принимает первый сигнал!
- **Fish Drama 3:** `[warm] Ты отметил 12 разных дней наклонного жима лёжа в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждый. Космодром привычки принимает <emphasis>первый сигнал!</emphasis>`
- **Image prompt:** A small penguin astronaut lies on an incline bench inside a Smith machine, flippers gripping the guided bar; a miniature rocket stands beside the foot of the bench like a patient training companion.

#### 2. Орбита знакомого жима

- **ID:** `exercise.smith-machine-incline-bench-press:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоём журнале 30 разных дней наклонного жима лёжа в Смите — каждый с минимум двумя полными рабочими подходами или 60 фактическими секундами. Это уже не пробный вылет!
- **Fish Drama 3:** `[playful] В твоём журнале 30 разных дней наклонного жима лёжа в Смите — каждый с минимум двумя полными рабочими подходами или 60 фактическими секундами. Это уже <emphasis>не пробный вылет!</emphasis>`
- **Image prompt:** The same penguin astronaut presses the guided bar from an incline bench beside a launch gantry; the little rocket peeks around a support, holding a rolled gym towel between its fins as if asking to join.

#### 3. Космос на проводе

- **ID:** `exercise.smith-machine-incline-bench-press:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** За плечами у тебя 75 разных дней наклонного жима лёжа в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. Даже космос узнал твой рабочий маршрут!
- **Fish Drama 3:** `[confident] За плечами у тебя 75 разных дней наклонного жима лёжа в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. [excited] Даже космос узнал <emphasis>твой рабочий маршрут!</emphasis>`
- **Image prompt:** The penguin astronaut performs an incline Smith press aboard an orbital training bay; beyond a wide window, the familiar rocket hovers nose-first toward the bench, balancing a neatly folded towel on one fin.

#### 4. Ракета заняла очередь

- **ID:** `exercise.smith-machine-incline-bench-press:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя 150 разных дней наклонного жима лёжа в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждый. Ракета ждёт с полотенцем — ей тоже к скамье!
- **Fish Drama 3:** `[triumphant] У тебя 150 разных дней наклонного жима лёжа в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждый. [playful] Ракета ждёт с полотенцем — <slow>ей тоже к скамье!</slow>`
- **Image prompt:** The penguin astronaut presses on an incline bench inside a Smith frame in an orbital hangar; a full-size rocket waits on a nearby bench with a tiny gym towel draped over its nose and its fins neatly tucked in.

### `exercise.smith-machine-inverted-row`

**Правило:** Практиковать smith-machine-inverted-row в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Знакомство под грифом

- **ID:** `exercise.smith-machine-inverted-row:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории 12 разных тренировочных дней горизонтальных подтягиваний в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Ты и гриф теперь знакомы снизу.
- **Fish Drama 3:** `[warm]В твоей истории <emphasis>12 разных тренировочных дней</emphasis> горизонтальных подтягиваний в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Ты и гриф теперь знакомы снизу.`
- **Image prompt:** A small square-headed robot performs an inverted row beneath a fixed Smith machine bar, heels resting on a mat. A squat little teapot waits beside one upright, its spout pointed curiously toward the robot.

#### 2. Гриф помнит гостя

- **ID:** `exercise.smith-machine-inverted-row:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** На счету у тебя 30 разных тренировочных дней горизонтальных подтягиваний в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Смит уже достал чашку.
- **Fish Drama 3:** `[playful]На счету у тебя <emphasis>30 разных тренировочных дней</emphasis> горизонтальных подтягиваний в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Смит уже достал чашку.`
- **Image prompt:** The same square-headed robot pulls its chest toward the fixed Smith bar. A jointed arm emerging from the rack offers a tiny teacup, while the familiar squat teapot sits on a shelf attached to the opposite upright.

#### 3. Чайник наготове

- **ID:** `exercise.smith-machine-inverted-row:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** 75 разных тренировочных дней горизонтальных подтягиваний в Смите — уже твоя история: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Пока ты тянешься к грифу, Смит учится заваривать чай.
- **Fish Drama 3:** `[confident]<emphasis>75 разных тренировочных дней</emphasis> горизонтальных подтягиваний в Смите — уже твоя история: минимум два полных рабочих подхода или 60 фактических секунд в каждом. [excited]Пока ты тянешься к грифу, Смит учится заваривать чай.`
- **Image prompt:** The square-headed robot rows beneath the Smith bar as two mechanical rack arms fuss over the familiar teapot. One arm steadies a tray of cups; the other holds an oversized tea strainer above the tiny pot.

#### 4. Дворецкий из железа

- **ID:** `exercise.smith-machine-inverted-row:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты собрал 150 разных тренировочных дней горизонтальных подтягиваний в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Теперь Смит подаёт тебе чай — железо тоже нашло призвание.
- **Fish Drama 3:** `[triumphant]Ты собрал <emphasis>150 разных тренировочных дней</emphasis> горизонтальных подтягиваний в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Теперь Смит подаёт тебе чай — <slow>железо тоже нашло призвание.</slow>`
- **Image prompt:** The square-headed robot rests beneath the fixed Smith bar with a tiny cup balanced on its chest. Enormous rack arms solemnly pour tea from the familiar pot, one forearm draped with a folded waiter's towel.

### `exercise.smith-machine-narrow-stance-squat`

**Правило:** Практиковать smith-machine-narrow-stance-squat в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Первый этаж практики

- **ID:** `exercise.smith-machine-narrow-stance-squat:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 12 разных тренировочных дней приседа в Смите с узкой постановкой ног: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Лифт практики тронулся.
- **Fish Drama 3:** `[warm]У тебя <emphasis>12 разных тренировочных дней</emphasis> приседа в Смите с узкой постановкой ног: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Лифт практики тронулся.`
- **Image prompt:** A penguin with close-set feet squats beneath a Smith bar inside a modest open elevator cage. Beside the rack sits a tiny luggage trolley carrying a closed fish cooler, ready for the first stop.

#### 2. Смит придержит лифт

- **ID:** `exercise.smith-machine-narrow-stance-squat:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** 30 разных тренировочных дней приседа в Смите с узкой постановкой ног уже в твоей копилке: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Смит придержал тебе лифт.
- **Fish Drama 3:** `[playful]<emphasis>30 разных тренировочных дней</emphasis> приседа в Смите с узкой постановкой ног уже в твоей копилке: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Смит придержал тебе лифт.`
- **Image prompt:** The same penguin squats with close-set feet under the Smith bar as the elevator reaches an icy landing. A walrus porter holds the sliding door open with one flipper and wheels the familiar fish cooler aboard.

#### 3. Консьерж на борту

- **ID:** `exercise.smith-machine-narrow-stance-squat:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Узкая постановка ног, широкая история: у тебя 75 разных тренировочных дней приседа в Смите, в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Лифт уже обзавёлся консьержем.
- **Fish Drama 3:** `[confident]Узкая постановка ног, широкая история: у тебя <emphasis>75 разных тренировочных дней</emphasis> приседа в Смите, в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [excited]Лифт уже обзавёлся консьержем.`
- **Image prompt:** The penguin continues its close-stance Smith squat inside an open lift high on an iceberg tower. The walrus porter stands beside the fish cooler, solemnly polishing a huge serving tray for the approaching top landing.

#### 4. Этаж с селёдкой

- **ID:** `exercise.smith-machine-narrow-stance-squat:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 150 разных тренировочных дней приседа в Смите с узкой постановкой ног: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Смит, на этаж с селёдкой!
- **Fish Drama 3:** `[triumphant]Ты собрал <emphasis>150 разных тренировочных дней</emphasis> приседа в Смите с узкой постановкой ног: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [playful]Смит, <slow>на этаж с селёдкой!</slow>`
- **Image prompt:** The penguin squats with close-set feet beneath the Smith bar as the lift opens at an iceberg penthouse. The walrus porter presents one tiny herring on an absurdly enormous tray, with the open fish cooler at his feet.

### `exercise.smith-machine-overhand-row`

**Правило:** Практиковать smith-machine-overhand-row в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Буксир выходит из гавани

- **ID:** `exercise.smith-machine-overhand-row:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 12 разных тренировочных дней тяги в Смите прямым хватом: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Буксир практики отошёл от дивана.
- **Fish Drama 3:** `[warm]Ты собрал 12 разных тренировочных дней тяги в Смите прямым хватом: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Буксир практики <emphasis>отошёл от дивана.</emphasis>`
- **Image prompt:** A tiny tugboat with articulated arms pulls a Smith-machine bar toward its wheelhouse, moored between the guide rails. A neatly coiled rope and a sleepy rubber duck wait beside the dock.

#### 2. Гриф узнаёт капитана

- **ID:** `exercise.smith-machine-overhand-row:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 30 разных тренировочных дней тяги в Смите прямым хватом — минимум по два полных рабочих подхода или 60 фактических секунд в день. Гриф уже узнаёт своего капитана.
- **Fish Drama 3:** `[playful]У тебя 30 разных тренировочных дней тяги в Смите прямым хватом — минимум по два полных рабочих подхода или 60 фактических секунд в день. Гриф уже узнаёт <emphasis>своего капитана.</emphasis>`
- **Image prompt:** The little tugboat draws the Smith bar toward its wheelhouse while opening a canal gate. The familiar rubber duck slips through first, towing a miniature gym bench on a raft behind it.

#### 3. Флотилия твоего опыта

- **ID:** `exercise.smith-machine-overhand-row:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За твоими плечами 75 разных тренировочных дней тяги в Смите прямым хватом, в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Это уже флотилия опыта, а не разовый заплыв.
- **Fish Drama 3:** `[confident]За твоими плечами 75 разных тренировочных дней тяги в Смите прямым хватом, в каждом — минимум два полных рабочих подхода или 60 фактических секунд. [excited]Это уже <emphasis>флотилия опыта,</emphasis> а не разовый заплыв.`
- **Image prompt:** The little tugboat works the Smith bar as a harbor gate lever, ushering a flotilla of gym benches on tiny pontoons. The familiar rubber duck sits in a lookout basket, surveying the orderly traffic.

#### 4. Капитан служебной уточки

- **ID:** `exercise.smith-machine-overhand-row:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 150 разных тренировочных дней тяги в Смите прямым хватом: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Флот встречает капитана — на служебной уточке.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 разных тренировочных дней тяги в Смите прямым хватом: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Флот встречает капитана — [playful]<slow>на служебной уточке.</slow>`
- **Image prompt:** The little tugboat grips the Smith bar from a tiny dock mounted on an enormous rubber duck. A flotilla of bench-rafts follows behind, while the duck calmly steers with its ridiculous webbed feet.

### `exercise.smith-machine-romanian-deadlift`

**Правило:** Практиковать smith-machine-romanian-deadlift в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Первая нота практики

- **ID:** `exercise.smith-machine-romanian-deadlift:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 12 разных тренировочных дней румынской тяги в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Оркестр практики взял первую ноту.
- **Fish Drama 3:** `[warm]У тебя 12 разных тренировочных дней румынской тяги в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Оркестр практики взял <soft>первую ноту.</soft>`
- **Image prompt:** A small accordion-bodied robot hinges at the hips inside a Smith machine, holding the bar near its shins with straight arms. A rubber duck beside one foot tilts its head toward a tiny piano with one raised key.

#### 2. Репертуар без суеты

- **ID:** `exercise.smith-machine-romanian-deadlift:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты практиковал румынскую тягу в Смите в 30 разных тренировочных дней: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Репертуар уже не на одну ноту.
- **Fish Drama 3:** `[playful]Ты практиковал румынскую тягу в Смите в 30 разных тренировочных дней: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Репертуар уже <emphasis>не на одну ноту.</emphasis>`
- **Image prompt:** The accordion robot holds the Smith bar below its knees, hips hinged back as its side bellows spread into a fan. The rubber duck listens through an oversized ear trumpet, while a loose towel flutters nearby.

#### 3. Большой концерт возвращений

- **ID:** `exercise.smith-machine-romanian-deadlift:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории 75 разных тренировочных дней румынской тяги в Смите — минимум по два полных рабочих подхода или 60 фактических секунд в день. Практика играет уверенно, железо слушает.
- **Fish Drama 3:** `[confident]В твоей истории 75 разных тренировочных дней румынской тяги в Смите — минимум по два полных рабочих подхода или 60 фактических секунд в день. [excited]Практика играет уверенно, <emphasis>железо слушает.</emphasis>`
- **Image prompt:** The accordion robot performs a hip hinge with the Smith bar before rows of attentive kettlebells on little chairs. Its side bellows stretch into organ pipes, and the rubber duck conducts with an absurdly long baton.

#### 4. Писк на бис

- **ID:** `exercise.smith-machine-romanian-deadlift:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 150 разных тренировочных дней румынской тяги в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Оркестр встаёт, дирижёр пищит — он резиновый.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 разных тренировочных дней румынской тяги в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Оркестр встаёт, дирижёр пищит — [playful]<slow>он резиновый.</slow>`
- **Image prompt:** The accordion robot makes a grand hip-hinge bow with the Smith bar at its shins. Its side bellows unfold into a concert stage; kettlebells rise from their seats as the rubber-duck conductor pokes its own belly with the baton.

### `exercise.smith-machine-seated-overhead-press`

**Правило:** Практиковать smith-machine-seated-overhead-press в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Лифт пошёл

- **ID:** `exercise.smith-machine-seated-overhead-press:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 12 разных дней жима над головой сидя в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Лифт практики тронулся!
- **Fish Drama 3:** `[warm] У тебя 12 разных дней жима над головой сидя в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. <soft>Лифт практики тронулся!</soft>`
- **Image prompt:** A square-headed robot sits on a tiny lift bench, raising a horizontal control bar between two guide rails. The open lift has just cleared its ground landing, where a small toolbox waits beside an unused upper platform.

#### 2. Знакомый пассажир

- **ID:** `exercise.smith-machine-seated-overhead-press:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За тобой уже 30 разных дней жима над головой сидя в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Лифт узнаёт тебя без кнопки вызова.
- **Fish Drama 3:** `[playful] За тобой уже <emphasis>30 разных дней</emphasis> жима над головой сидя в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Лифт узнаёт тебя без кнопки вызова.`
- **Image prompt:** The square-headed robot rides its bench lift past stacked landings, pressing the overhead crossbar along twin rails. A small delivery trolley waits on the middle landing, its parcel almost level with the robot's seat.

#### 3. Высотный абонемент

- **ID:** `exercise.smith-machine-seated-overhead-press:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории — 75 разных дней жима над головой сидя в Смите, в каждом минимум два полных рабочих подхода или 60 фактических секунд. Лифт практики уже здоровается с голубями на крыше!
- **Fish Drama 3:** `[confident] В твоей истории — 75 разных дней жима над головой сидя в Смите, в каждом минимум два полных рабочих подхода или 60 фактических секунд. [excited] Лифт практики уже здоровается с голубями на крыше!`
- **Image prompt:** The square-headed robot brings its bench lift above a cluster of rooftops, hands beneath the raised crossbar. Twin guide rails extend past a weather vane, and a curious pigeon leans toward the arriving cabin.

#### 4. Облаку тоже наверх

- **ID:** `exercise.smith-machine-seated-overhead-press:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 150 разных дней жима над головой сидя в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. На верхнем этаже в лифт вошло облако — просит подвезти домой.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>150 разных дней</emphasis> жима над головой сидя в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. На верхнем этаже в лифт вошло облако — <slow>просит подвезти домой.</slow>`
- **Image prompt:** The square-headed robot holds its bench lift at a cloud landing as a plump cloud squeezes into the open cabin. The cloud carries a tiny house key, while the robot makes room on the bench beneath the raised crossbar.

### `exercise.smith-machine-skullcrusher`

**Правило:** Практиковать smith-machine-skullcrusher в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Первый утиный проход

- **ID:** `exercise.smith-machine-skullcrusher:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 12 разных дней французского жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Бобр-смотритель открыл первый пролёт!
- **Fish Drama 3:** `[warm] Ты собрал 12 разных дней французского жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. <soft>Бобр-смотритель открыл первый пролёт!</soft>`
- **Image prompt:** A flat-tailed beaver operates an elbow-shaped lever beside a tiny drawbridge. The first wooden span rises between two guide posts, letting a lone rubber duck nose through the narrow water channel below.

#### 2. Бобр открывает навигацию

- **ID:** `exercise.smith-machine-skullcrusher:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За плечами у тебя 30 разных дней французского жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Бобр-смотритель уже машет тебе с моста.
- **Fish Drama 3:** `[playful] За плечами у тебя <emphasis>30 разных дней</emphasis> французского жима лёжа в Смите: в каждом — минимум два полных рабочих подхода или 60 фактических секунд. Бобр-смотритель уже машет тебе с моста.`
- **Image prompt:** The flat-tailed beaver leans back on the drawbridge control bench, folding its hinged lever to lift a wider span. A pair of rubber ducks tow a little supply raft through the opening beneath the timber deck.

#### 3. Пропуск для флотилии

- **ID:** `exercise.smith-machine-skullcrusher:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей копилке 75 разных дней французского жима лёжа в Смите, в каждом минимум два полных рабочих подхода или 60 фактических секунд. Мост практики пропускает уже целую утиную флотилию!
- **Fish Drama 3:** `[confident] В твоей копилке 75 разных дней французского жима лёжа в Смите, в каждом минимум два полных рабочих подхода или 60 фактических секунд. [excited] Мост практики пропускает уже целую утиную флотилию!`
- **Image prompt:** The flat-tailed beaver braces at a large hinged control lever while a tall drawbridge opens above a canal. A whole flotilla of rubber ducks passes underneath, with the lead duck towing a tiny tugboat twice its size.

#### 4. Ванна дальнего плавания

- **ID:** `exercise.smith-machine-skullcrusher:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** 150 разных дней французского жима лёжа в Смите — твоя история: в каждом минимум два полных рабочих подхода или 60 фактических секунд. Бобр поднял мост ради флагмана — ванны с уткой-капитаном.
- **Fish Drama 3:** `[triumphant] <emphasis>150 разных дней</emphasis> французского жима лёжа в Смите — твоя история: в каждом минимум два полных рабочих подхода или 60 фактических секунд. Бобр поднял мост ради флагмана — <slow>ванны с уткой-капитаном.</slow>`
- **Image prompt:** The flat-tailed beaver folds an enormous elbow-shaped lever, raising both halves of the drawbridge for a bathtub ship. A rubber duck commands the bow from a soap dish, while the bath plug trails behind like an anchor.

### `exercise.smith-machine-squat`

**Правило:** Практиковать smith-machine-squat в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Знакомство с железным лифтом

- **ID:** `exercise.smith-machine-squat:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя уже 12 разных дней приседаний в Смите: за каждый — минимум два полных рабочих подхода или 60 фактических секунд. Железный лифт запомнил пассажира.
- **Fish Drama 3:** `[warm] У тебя уже 12 разных дней приседаний в Смите: за каждый — минимум два полных рабочих подхода или 60 фактических секунд. Железный лифт запомнил пассажира.`
- **Image prompt:** A bellows-bodied robot greets a Smith machine as if it were an elevator, one hand resting on the stationary bar and the other holding a tiny empty suitcase; the guide rails resemble welcoming lift doors.

#### 2. Постоянный пассажир

- **ID:** `exercise.smith-machine-squat:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** 30 разных дней приседаний в Смите — твоя история практики: минимум два полных рабочих подхода или 60 фактических секунд за день. Похоже, железный лифт уже придерживает тебе дверь.
- **Fish Drama 3:** `[playful] 30 разных дней приседаний в Смите — твоя история практики: минимум два полных рабочих подхода или 60 фактических секунд за день. Похоже, железный лифт уже придерживает тебе дверь.`
- **Image prompt:** The bellows-bodied robot returns to the Smith frame with its tiny suitcase; a mechanical hand on one guide rail holds an imaginary lift door while the robot offers the stationary bar a friendly fist bump.

#### 3. Почётный лифтёр Смита

- **ID:** `exercise.smith-machine-squat:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 75 разных дней приседаний в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Железный лифт явно хочет взять тебя в напарники.
- **Fish Drama 3:** `[confident] Ты накопил 75 разных дней приседаний в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. [excited] Железный лифт явно хочет взять тебя в напарники.`
- **Image prompt:** The bellows-bodied robot wears a lift attendant's cap beside the Smith frame, proudly accepting an oversized elevator key from a mechanical rail-hand; its familiar tiny suitcase now serves as an attendant's stool.

#### 4. Смит просит печеньку

- **ID:** `exercise.smith-machine-squat:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории уже 150 разных дней приседаний в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Теперь Смит подаёт тебе чай — и просит печеньку.
- **Fish Drama 3:** `[triumphant] В твоей истории уже 150 разных дней приседаний в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Теперь Смит подаёт тебе чай — <slow>и просит печеньку.</slow>`
- **Image prompt:** The bellows-bodied robot relaxes on its tiny suitcase while the Smith machine acts as a tea waiter, its stationary bar supporting a tray with two cups; a small rail-hand shyly reaches toward the robot's biscuit.

### `exercise.smith-machine-upright-row`

**Правило:** Практиковать smith-machine-upright-row в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Первый утиный рейс

- **ID:** `exercise.smith-machine-upright-row:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 12 разных дней тяги к подбородку в Смите: в каждом минимум два полных рабочих подхода или 60 фактических секунд. Мостик для утиного флота открыт.
- **Fish Drama 3:** `[warm] У тебя 12 разных дней тяги к подбородку в Смите: в каждом минимум два полных рабочих подхода или 60 фактических секунд. Мостик для утиного флота открыт.`
- **Image prompt:** A small folded-paper pelican operates a miniature drawbridge built from Smith machine rails and a horizontal bar; a single rubber duck waits below the raised span, watched closely by the pelican's long beak.

#### 2. Капитан знакомого маршрута

- **ID:** `exercise.smith-machine-upright-row:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За тобой 30 разных дней тяги к подбородку в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Утиный флот уже узнаёт своего капитана.
- **Fish Drama 3:** `[playful] За тобой 30 разных дней тяги к подбородку в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Утиный флот уже узнаёт своего капитана.`
- **Image prompt:** The folded-paper pelican works a lever beside the Smith-rail drawbridge as a short queue of rubber ducks floats underneath; a mooring post and coiled rope turn the crossing into a tiny working harbor.

#### 3. Буксир большого уважения

- **ID:** `exercise.smith-machine-upright-row:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Уже 75 разных дней ты практиковал тягу к подбородку в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. Утиный флот прислал тебе буксир почёта.
- **Fish Drama 3:** `[confident] Уже 75 разных дней ты практиковал тягу к подбородку в Смите: минимум два полных рабочих подхода или 60 фактических секунд за день. [excited] Утиный флот прислал тебе буксир почёта.`
- **Image prompt:** The folded-paper pelican stands at the Smith-rail bridge controls while a little tugboat carries a stack of rubber ducks through the open span; its long beak extends over the pier like a harbor traffic barrier.

#### 4. Утки принесли хлеб

- **ID:** `exercise.smith-machine-upright-row:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 150 разных дней тяги к подбородку в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Утки устроили тебе банкет — и впервые сами принесли хлеб.
- **Fish Drama 3:** `[triumphant] Ты собрал 150 разных дней тяги к подбородку в Смите: минимум два полных рабочих подхода или 60 фактических секунд в каждом. Утки устроили тебе банкет — <slow>и впервые сами принесли хлеб.</slow>`
- **Image prompt:** The folded-paper pelican sits at a tiny banquet table beside the Smith-rail drawbridge; rubber ducks arrive by tugboat carrying an absurdly large loaf of bread, with one duck proudly offering the pelican a single crumb.

### `exercise.underhand-pulldown`

**Правило:** Практиковать underhand-pulldown в разные тренировочные дни: минимум два полных рабочих подхода или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день практики. **Источник:** `available`.

#### 1. Один носок из тучи

- **ID:** `exercise.underhand-pulldown:t1`
- **Порог:** 12 день практики
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 12 разных тренировочных дней тяги верхнего блока обратным хватом: в каждом — минимум 2 полных рабочих подхода или 60 фактических секунд. Первая туча уже просится в стирку.
- **Fish Drama 3:** `[warm]У тебя 12 разных тренировочных дней тяги верхнего блока обратным хватом: в каждом — минимум 2 полных рабочих подхода или 60 фактических секунд. Первая туча уже просится в стирку.`
- **Image prompt:** A small cloud laundromat attendant draws a cable bar toward its chest, palms facing its face. A single fluffy sock dangles from the overhead pulley, dripping into a tiny bucket beside the attendant's seat.

#### 2. Корзина небесных дел

- **ID:** `exercise.underhand-pulldown:t2`
- **Порог:** 30 день практики
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты практикуешь тягу верхнего блока обратным хватом уже 30 разных тренировочных дней: в каждом — минимум 2 полных рабочих подхода или 60 фактических секунд. Тучи несут тебе корзину облачных носков.
- **Fish Drama 3:** `[playful]Ты практикуешь тягу верхнего блока обратным хватом уже <emphasis>30 разных тренировочных дней</emphasis>: в каждом — минимум 2 полных рабочих подхода или 60 фактических секунд. Тучи несут тебе корзину облачных носков.`
- **Image prompt:** A small cloud laundromat attendant sits pulling a cable bar with palms facing its face. The overhead pulley carries a laundry basket packed with cloud socks; one runaway sock dives into a washbasin beside the seat.

#### 3. Карусель большой стирки

- **ID:** `exercise.underhand-pulldown:t3`
- **Порог:** 75 день практики
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоём багаже 75 разных тренировочных дней тяги верхнего блока обратным хватом: каждый — минимум 2 полных рабочих подхода или 60 фактических секунд. Тучи открывают прачечную самообслуживания.
- **Fish Drama 3:** `[confident]В твоём багаже <emphasis>75 разных тренировочных дней</emphasis> тяги верхнего блока обратным хватом: каждый — минимум 2 полных рабочих подхода или 60 фактических секунд. Тучи открывают прачечную самообслуживания.`
- **Image prompt:** A seated cloud laundromat attendant pulls an underhand cable bar beneath a broad rotary drying rack. Puffy towels and tiny thundercloud socks orbit the pulley, while a runaway sock desperately clings to a wooden clothespin.

#### 4. Солнце просит не будить

- **ID:** `exercise.underhand-pulldown:t4`
- **Порог:** 150 день практики
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Твоя история тяги верхнего блока обратным хватом — 150 разных тренировочных дней, в каждом минимум 2 полных рабочих подхода или 60 фактических секунд. Большая стирка: в машинке дремлет солнце.
- **Fish Drama 3:** `[triumphant]Твоя история тяги верхнего блока обратным хватом — <emphasis>150 разных тренировочных дней</emphasis>, в каждом минимум 2 полных рабочих подхода или 60 фактических секунд. Большая стирка: <slow>в машинке дремлет солнце.</slow>`
- **Image prompt:** A small cloud laundromat attendant pulls an underhand cable bar to hoist a giant washing machine door. Inside, a sleepy sun hugs a cloud towel; a sock beside the attendant's seat holds an absurdly tiny alarm clock.

## Практика мышечных групп

### `muscle.abdominals`

**Правило:** Пресс: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Пресс получает роль

- **ID:** `muscle.abdominals:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 12 разных дней, где пресс — основная рабочая группа: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. Пресс выходит на сцену, а не машет из массовки.
- **Fish Drama 3:** `[warm]У тебя 12 разных дней, где пресс — <emphasis>основная рабочая группа</emphasis>: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. Пресс выходит на сцену, а не машет из массовки.`
- **Image prompt:** A small rolled exercise mat with mitten hands steps into a tiny theater spotlight, carrying a plain rehearsal stool. One curtain edge peeks around the doorway like a curious stagehand; the mat has the stage entirely to itself.

#### 2. Реквизит просит автограф

- **ID:** `muscle.abdominals:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** За 30 разных дней ты даёшь прессу главную рабочую роль: минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждом. Реквизит уже просит автограф.
- **Fish Drama 3:** `[playful]За 30 разных дней ты даёшь прессу главную рабочую роль: минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждом. Реквизит уже просит автограф.`
- **Image prompt:** A small rolled exercise mat with mitten hands stands atop a rehearsal stool, delivering a theatrical gesture to an audience of two kettlebells. A curtain edge leans in, holding a teacup as an overly serious stage prop.

#### 3. Бенефис на орбите

- **ID:** `muscle.abdominals:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории 75 разных дней с прессом в роли основной рабочей группы: каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. У спектакля солидный послужной список.
- **Fish Drama 3:** `[confident]В твоей истории <emphasis>75 разных дней</emphasis> с прессом в роли основной рабочей группы: каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. У спектакля солидный послужной список.`
- **Image prompt:** A small rolled exercise mat with mitten hands pilots a cardboard rocket on a miniature theater stage. A visible hand crank moves paper planets past the window, while the curtain edge eagerly operates a tiny wind fan.

#### 4. Занавес тоже кланяется

- **ID:** `muscle.abdominals:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** За плечами у тебя 150 разных дней с прессом в основной рабочей роли: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. На поклон выходит даже занавес.
- **Fish Drama 3:** `[triumphant]За плечами у тебя <emphasis>150 разных дней</emphasis> с прессом в основной рабочей роли: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. На поклон выходит <slow>даже занавес.</slow>`
- **Image prompt:** A small rolled exercise mat with mitten hands takes a bow on its tiny theater stage. Both curtains bend down in a deeper bow, dragging the spotlight with them, while the audience of kettlebells watches the theater itself steal the encore.

### `muscle.biceps`

**Правило:** Бицепс: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Локтевой отдел открыт

- **ID:** `muscle.biceps:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** За тобой 12 разных дней, где бицепс был основной мышцей: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. Ты открыл локтевой отдел!
- **Fish Drama 3:** `[warm]За тобой 12 разных дней, где бицепс был основной мышцей: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. Ты открыл <emphasis>локтевой отдел!</emphasis>`
- **Image prompt:** A square-headed service robot with accordion elbow joints sits at a compact workbench, curling a single dumbbell toward its shoulder. Its free hand opens a tiny toolbox containing a neatly folded training towel.

#### 2. Приёмная для гантелей

- **ID:** `muscle.biceps:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты собрал 30 разных дней с бицепсом в главной роли: в каждом — от 2 полных рабочих подходов или от 60 секунд силового удержания. У локтевого отдела уже своя приёмная.
- **Fish Drama 3:** `[playful]Ты собрал 30 разных дней с бицепсом в главной роли: в каждом — от 2 полных рабочих подходов или от 60 секунд силового удержания. У локтевого отдела уже <emphasis>своя приёмная.</emphasis>`
- **Image prompt:** The square-headed robot with accordion elbows runs a miniature service counter, cradling a dumbbell in each bent arm. Two more dumbbells wait on short wire legs beside an empty tray, like visitors at a very unusual reception.

#### 3. Совет локтевых дел

- **ID:** `muscle.biceps:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Уже 75 разных дней ты давал бицепсу основную работу: от 2 полных рабочих подходов или от 60 секунд силового удержания за день. Гантели слушают твои локти с уважением.
- **Fish Drama 3:** `[confident]Уже <emphasis>75 разных дней</emphasis> ты давал бицепсу основную работу: от 2 полных рабочих подходов или от 60 секунд силового удержания за день. [excited]Гантели слушают твои локти с уважением.`
- **Image prompt:** The square-headed robot with accordion elbows chairs a compact meeting of three dumbbells on stools. It demonstrates an elbow bend while the dumbbells raise their skinny wire arms, eagerly asking for muscles of their own.

#### 4. Профсоюз требует бицепсы

- **ID:** `muscle.biceps:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 150 разных дней основной работы на бицепс: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. Гантели создали профсоюз: требуют себе бицепсы.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 разных дней основной работы на бицепс: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. <slow>Гантели создали профсоюз:</slow> [playful]требуют себе бицепсы.`
- **Image prompt:** The square-headed robot with accordion elbows coaches two dumbbells with newly sprouted wire arms at a tiny workout bench. Each dumbbell curls a miniature toy version of the robot, while the original watches with a teacup in its own bent arm.

### `muscle.calves`

**Правило:** Икры: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Икры нажали кнопку

- **ID:** `muscle.calves:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя 12 разных дней основной работы на икры: в каждом — от 2 полных рабочих подходов или от 60 секунд силового удержания. Маленький лифт практики уже приехал.
- **Fish Drama 3:** `[warm]У тебя 12 разных дней основной работы на икры: в каждом — от 2 полных рабочих подходов или от 60 секунд силового удержания. <soft>Маленький лифт практики уже приехал.</soft>`
- **Image prompt:** A small penguin elevator operator holds a support rail and raises both heels beside a tiny open lift platform. A single fish passenger waits with a rolled exercise mat, peering curiously at the penguin's feet.

#### 2. Этажом выше, пожалуйста

- **ID:** `muscle.calves:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** В твоей истории уже 30 разных дней с икрами в основной роли: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. Лифт уважительно придержал двери.
- **Fish Drama 3:** `[playful]В твоей истории уже 30 разных дней с икрами в основной роли: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. Лифт <emphasis>уважительно придержал двери.</emphasis>`
- **Image prompt:** The small penguin elevator operator rises onto its toes with one flipper on a support rail and the other on a lever. Beside it, a tiny lift cabin carries a fish and a rolled exercise mat halfway up a short shaft.

#### 3. Подъёмный стаж

- **ID:** `muscle.calves:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 75 разных дней, когда икры работали как основная мышечная группа: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. У лифта появился наставник.
- **Fish Drama 3:** `[confident]Ты накопил <emphasis>75 разных дней</emphasis>, когда икры работали как основная мышечная группа: от 2 полных рабочих подходов или от 60 секунд силового удержания в каждом. [excited]У лифта появился наставник.`
- **Image prompt:** The small penguin elevator operator stands on raised heels at a support rail beside a compact three-level lift. Fish passengers queue with rolled exercise mats while a cabin pauses level with the penguin's beak.

#### 4. Лифт пришёл учиться

- **ID:** `muscle.calves:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** 150 разных дней ты отдавал икрам основную роль: в каждом — от 2 полных рабочих подходов или от 60 секунд силового удержания. Лифт записался к тебе на подъёмы без кнопок.
- **Fish Drama 3:** `[triumphant]150 разных дней ты отдавал икрам основную роль: в каждом — от 2 полных рабочих подходов или от 60 секунд силового удержания. <slow>Лифт записался к тебе</slow> [playful]на подъёмы без кнопок.`
- **Image prompt:** The small penguin elevator operator demonstrates a heel raise at a support rail. Beside it, a tiny elevator cabin on sneakered legs copies the movement, while a fish passenger leans out of the doorway holding a workout towel.

### `muscle.chest`

**Правило:** Грудь: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Грудь выходит на сцену

- **ID:** `muscle.chest:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 12 разных дней основной нагрузки на грудь: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Дебют есть, штанга учит реплики.
- **Fish Drama 3:** `[warm]Ты накопил 12 разных дней основной нагрузки на грудь: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Дебют есть, <soft>штанга учит реплики.</soft>`
- **Image prompt:** A badger sits upright at a compact chest press machine, forepaws on its handles. A tiny theater curtain has just opened, and a single toy duck drags a little spectator bench toward the new performer.

#### 2. Фан-клуб у скамьи

- **ID:** `muscle.chest:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Обычная (`common`)
- **Фраза:** У тебя уже 30 разных дней основной нагрузки на грудь — минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. У скамьи появился фан-клуб, и это не склад блинов.
- **Fish Drama 3:** `[playful]У тебя уже 30 разных дней основной нагрузки на грудь — минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. У скамьи появился фан-клуб, и это <emphasis>не склад блинов.</emphasis>`
- **Image prompt:** The badger operates the same compact chest press on a small theater platform. Toy ducks arrange spectator benches around the machine, while one eager duck leans over the stage edge holding an oversized opera glass.

#### 3. Аншлаг в театре жима

- **ID:** `muscle.chest:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Обычная (`common`)
- **Фраза:** 75 разных дней основной нагрузки на грудь уже в твоей истории: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. В театре жима аншлаг, даже блины заняли ложу.
- **Fish Drama 3:** `[confident]75 разных дней основной нагрузки на грудь уже в твоей истории: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. [excited]В театре жима аншлаг, даже блины заняли ложу.`
- **Image prompt:** The badger and its compact chest press headline a miniature theater. A toy duck orchestra crowds the foot of the stage, while a pair of weight plates sits upright in a balcony box, peering through shared opera glasses.

#### 4. Скамейки требуют бис

- **ID:** `muscle.chest:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Обычная (`common`)
- **Фраза:** Ты накопил 150 разных дней основной нагрузки на грудь — минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Занавес, овации… скамейки требуют бис.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 разных дней основной нагрузки на грудь — минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Занавес, овации… [playful]<slow>скамейки требуют бис.</slow>`
- **Image prompt:** The badger takes a seated bow at its compact chest press as theater curtains sweep apart. Animated workout benches clap their padded cushions; even the balcony is packed with tiny benches leaning forward for an encore.

### `muscle.forearms`

**Правило:** Предплечья: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Хват знакомства

- **ID:** `muscle.forearms:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** Знакомство состоялось: у тебя 12 разных дней основной нагрузки на предплечья, в каждый — минимум два полных рабочих подхода или 60 секунд силового удержания. Банка солений насторожилась.
- **Fish Drama 3:** `[warm]Знакомство состоялось: у тебя 12 разных дней основной нагрузки на предплечья, в каждый — минимум два полных рабочих подхода или 60 секунд силового удержания. <soft>Банка солений насторожилась.</soft>`
- **Image prompt:** A raccoon sits at a small repair bench with a spring hand gripper in one paw. A closed pickle jar waits opposite it on a folded work cloth, with one curious pickle pressed against the glass beneath the stubborn lid.

#### 2. Банка держит оборону

- **ID:** `muscle.forearms:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В копилке у тебя 30 разных дней основной нагрузки на предплечья: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Банка солений официально перешла к переговорам.
- **Fish Drama 3:** `[playful]В копилке у тебя 30 разных дней основной нагрузки на предплечья: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Банка солений официально <emphasis>перешла к переговорам.</emphasis>`
- **Image prompt:** The raccoon squeezes its spring hand gripper beside the same pickle jar, now perched on a rotating repair stand. Tiny wrenches form a defensive barricade around the jar, and a pickle inside raises a cautious open palm.

#### 3. Переговорщик с ключом

- **ID:** `muscle.forearms:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 75 разных дней основной нагрузки на предплечья — минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Банка вызвала переговорщика: огурец с гаечным ключом.
- **Fish Drama 3:** `[confident]Ты собрал 75 разных дней основной нагрузки на предплечья — минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. [excited]Банка вызвала переговорщика: <emphasis>огурец с гаечным ключом.</emphasis>`
- **Image prompt:** The raccoon pauses with its spring hand gripper beside the pickle jar on the repair stand. The lid tilts open just enough for a tiny pickle mechanic to emerge carrying a wrench, one hand raised to begin negotiations.

#### 4. У солений свои соленья

- **ID:** `muscle.forearms:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** За тобой 150 разных дней основной нагрузки на предплечья: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Банка открылась, а внутри… огурец со своей неподдающейся банкой.
- **Fish Drama 3:** `[triumphant]За тобой 150 разных дней основной нагрузки на предплечья: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Банка открылась, а внутри… [playful]<slow>огурец со своей неподдающейся банкой.</slow>`
- **Image prompt:** The raccoon stares into the now-open pickle jar, its spring hand gripper resting beside the lid. Inside, a pickle mechanic struggles with a smaller sealed pickle jar and sheepishly offers it upward, requesting another round.

### `muscle.front-shoulders`

**Правило:** Передние дельты: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Дебют передних дельт

- **ID:** `muscle.front-shoulders:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя 12 разных дней с передними дельтами в основной роли: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. Плечевой театр открылся!
- **Fish Drama 3:** `[warm] У тебя <emphasis>12 разных дней</emphasis> с передними дельтами в основной роли: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. Плечевой театр открылся!`
- **Image prompt:** A small forklift with expressive headlights and short forks gently draws aside a theater curtain, revealing a lone dumbbell on a tiny wooden stage. A folded rehearsal chair waits beside the forklift.

#### 2. Плечи в главной роли

- **ID:** `muscle.front-shoulders:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** За твоими плечами 30 разных дней основной работы передних дельт: каждый — минимум два полных рабочих подхода или 60 секунд силового удержания. Даже прожектор повернулся посмотреть.
- **Fish Drama 3:** `[playful] За твоими плечами <emphasis>30 разных дней</emphasis> основной работы передних дельт: каждый — минимум два полных рабочих подхода или 60 секунд силового удержания. Даже прожектор повернулся посмотреть.`
- **Image prompt:** The small forklift with expressive headlights and short forks wheels a stage spotlight toward two dumbbell actors peeking around a curtain. The spotlight bends forward inquisitively, almost joining their rehearsal.

#### 3. Аншлаг у железа

- **ID:** `muscle.front-shoulders:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты собрал 75 разных дней, где передние дельты — основная группа: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. Железо уже просит место в первом ряду.
- **Fish Drama 3:** `[confident] Ты собрал <emphasis>75 разных дней</emphasis>, где передние дельты — основная группа: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. [excited] Железо уже просит место в первом ряду.`
- **Image prompt:** The small forklift with expressive headlights and short forks ushers animated dumbbells into packed rows of theater seats. One eager dumbbell leans toward the front row while the forklift holds a curtain open.

#### 4. Гантельные овации

- **ID:** `muscle.front-shoulders:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя 150 разных дней основной работы передних дельт — по два рабочих подхода или 60 секунд удержания в каждом. Гантели аплодируют ручками!
- **Fish Drama 3:** `[triumphant] У тебя <emphasis>150 разных дней</emphasis> основной работы передних дельт — по два рабочих подхода или 60 секунд удержания в каждом. [playful] Гантели аплодируют ручками!`
- **Image prompt:** The small forklift with expressive headlights and short forks takes a bow beneath descending theater curtains. Dumbbells applaud with tiny handle-shaped hands; one delighted spectator holds opera glasses upside down.

### `muscle.glutes`

**Правило:** Ягодицы: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Первый пролёт

- **ID:** `muscle.glutes:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Редкая (`rare`)
- **Фраза:** У тебя 12 разных дней основной работы ягодиц: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. Первый пролёт готов, бобр одобрительно стучит хвостом.
- **Fish Drama 3:** `[warm] У тебя <emphasis>12 разных дней</emphasis> основной работы ягодиц: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. Первый пролёт готов, бобр одобрительно стучит хвостом.`
- **Image prompt:** A broad-tailed beaver kneels beside a narrow stream, fitting the last plank into a tiny footbridge. Its flat tail taps a spare board in approval, while a small wooden mallet rests within reach.

#### 2. Мостовой размах

- **ID:** `muscle.glutes:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей истории уже 30 разных дней с ягодицами в основной роли: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. У бобра теперь мост, а не доска с амбициями.
- **Fish Drama 3:** `[playful] В твоей истории уже <emphasis>30 разных дней</emphasis> с ягодицами в основной роли: минимум два полных рабочих подхода или 60 секунд силового удержания в каждый. У бобра теперь мост, а не доска с амбициями.`
- **Image prompt:** The broad-tailed beaver fastens a sturdy handrail onto its completed wooden footbridge. It stands proudly beside the entrance, with the original lone plank propped nearby like a modest reminder of the beginning.

#### 3. Переправа с характером

- **ID:** `muscle.glutes:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Редкая (`rare`)
- **Фраза:** В твоей копилке 75 разных дней основной работы ягодиц: каждый — минимум два полных рабочих подхода или 60 секунд силового удержания. Бобр открыл переправу и деловито проверяет поток уточек.
- **Fish Drama 3:** `[confident] В твоей копилке <emphasis>75 разных дней</emphasis> основной работы ягодиц: каждый — минимум два полных рабочих подхода или 60 секунд силового удержания. [excited] Бобр открыл переправу и деловито проверяет поток уточек.`
- **Image prompt:** The broad-tailed beaver operates a wooden crank beside its upgraded drawbridge, testing the hinged deck above a stream. A neat procession of rubber ducks approaches below as the beaver watches with serious concentration.

#### 4. Разводной мост для уточки

- **ID:** `muscle.glutes:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Редкая (`rare`)
- **Фраза:** Ты накопил 150 разных дней основной работы ягодиц: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. Бобр разводит целый мост… ради одной резиновой уточки!
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>150 разных дней</emphasis> основной работы ягодиц: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. [playful] Бобр разводит <slow>целый мост…</slow> ради одной резиновой уточки!`
- **Image prompt:** The broad-tailed beaver proudly cranks both towering leaves of its wooden drawbridge fully open. Far below, a single tiny rubber duck sails through on a bar of soap, receiving absurdly grand passage.

### `muscle.hamstrings`

**Правило:** Бицепс бедра: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Пуск закулисной лебёдки

- **ID:** `muscle.hamstrings:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 12 разных дней основной нагрузки на бицепс бедра: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Закулисная лебёдка ожила!
- **Fish Drama 3:** `[warm] Ты накопил 12 разных дней основной нагрузки на бицепс бедра: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. [playful] Закулисная лебёдка ожила!`
- **Image prompt:** A beaver stagehand turns the handle of a compact rope winch, lifting one corner of a heavy theater curtain. A kettlebell peeks underneath, waiting beside a tiny rehearsal stool and a neatly coiled spare rope.

#### 2. Железная премьера

- **ID:** `muscle.hamstrings:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя уже 30 разных дней основной работы бицепса бедра: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Гиря за кулисами репетирует поклон!
- **Fish Drama 3:** `[playful] У тебя уже 30 разных дней основной работы бицепса бедра: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Гиря за кулисами репетирует <emphasis>поклон</emphasis>!`
- **Image prompt:** A beaver stagehand operates a rope winch beside a small theater stage, drawing both curtain panels apart. At center stage, a kettlebell with little arms rehearses an exaggerated bow toward a lone dumbbell in the audience.

#### 3. Сезон железной драмы

- **ID:** `muscle.hamstrings:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** 75 разных дней основной нагрузки на бицепс бедра — в твоей истории: в каждый было минимум 2 полных рабочих подхода или 60 секунд силового удержания. У железа целый театральный сезон!
- **Fish Drama 3:** `[confident] 75 разных дней основной нагрузки на бицепс бедра — в твоей истории: в каждый было минимум 2 полных рабочих подхода или 60 секунд силового удержания. [excited] У железа целый театральный сезон!`
- **Image prompt:** A beaver stagehand works a rope winch above a bustling theater stage. Below, a kettlebell actor delivers a grand dramatic gesture beside a sofa hidden under a sheet, while rows of dumbbell spectators lean forward.

#### 4. Диванный бенефис гири

- **ID:** `muscle.hamstrings:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты накопил 150 разных дней основной нагрузки на бицепс бедра: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Занавес: в главной роли — гиря на диване!
- **Fish Drama 3:** `[triumphant] Ты накопил 150 разных дней основной нагрузки на бицепс бедра: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Занавес: <slow>в главной роли —</slow> [playful] гиря на диване!`
- **Image prompt:** A beaver stagehand triumphantly cranks a rope winch, sweeping the grand curtain upward to reveal a kettlebell lounging on a sofa with its little feet on a footstool. An audience of dumbbells applauds as the beaver presents the relaxed star.

### `muscle.lats`

**Правило:** Широчайшие: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Чашка на старте

- **ID:** `muscle.lats:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Эпичная (`epic`)
- **Фраза:** На твоём счету 12 разных дней основной нагрузки на широчайшие: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Чашка спущена на воду!
- **Fish Drama 3:** `[warm] На твоём счету 12 разных дней основной нагрузки на широчайшие: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. [playful] Чашка спущена на воду!`
- **Image prompt:** A small octopus sits in a floating teacup, dipping two teaspoons into the water as oars. Gentle ripples spread from its first rowing stroke, while a biscuit on a saucer serves as the little boat's departure dock.

#### 2. Осьминожья гребная школа

- **ID:** `muscle.lats:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Эпичная (`epic`)
- **Фраза:** Ты собрал 30 разных дней, где широчайшие были главными: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Осьминог гребёт, ложки завидуют!
- **Fish Drama 3:** `[playful] Ты собрал 30 разных дней, где широчайшие были главными: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Осьминог гребёт, <emphasis>ложки завидуют</emphasis>!`
- **Image prompt:** A small octopus rows its teacup boat around a sugar-cube island using two teaspoons. Several spare spoons lean over the rim like curious passengers, and a second empty cup bobs nearby, waiting to join the voyage.

#### 3. Адмирал чайной флотилии

- **ID:** `muscle.lats:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Эпичная (`epic`)
- **Фраза:** У тебя за плечами 75 разных дней основной работы широчайших: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Чайная флотилия держит курс!
- **Fish Drama 3:** `[confident] У тебя за плечами 75 разных дней основной работы широчайших: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. [excited] Чайная флотилия держит курс!`
- **Image prompt:** A small octopus rows the leading teacup of a winding flotilla, pointing the way with a spare tentacle. Cups with spoon oars follow between biscuit islands, while a curious kettle watches from the edge of a saucer harbor.

#### 4. Чайник берётся за вёсла

- **ID:** `muscle.lats:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Эпичная (`epic`)
- **Фраза:** В твоей истории уже 150 разных дней основной нагрузки на широчайшие: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Теперь даже чайник взялся за вёсла!
- **Fish Drama 3:** `[triumphant] В твоей истории уже 150 разных дней основной нагрузки на широчайшие: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. <slow>Теперь даже</slow> [playful] чайник взялся за вёсла!`
- **Image prompt:** A small octopus in its teacup boat leads an entire rowing tea set. Behind it, an enormous earnest kettle paddles with serving spoons held in little arms, its lid bouncing open as a teabag dangles from the spout like a panting tongue.

### `muscle.obliques`

**Правило:** Косые мышцы живота: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Косые открывают сезон

- **ID:** `muscle.obliques:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 12 разных дней основной нагрузки на косые мышцы живота — минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Занавес пошёл, чайник волнуется.
- **Fish Drama 3:** `[warm] У тебя 12 разных дней основной нагрузки на косые мышцы живота — минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. [playful] Занавес пошёл, чайник волнуется.`
- **Image prompt:** A crab stagehand with oversized angled pincers pulls two diagonal ropes to open a tiny tabletop curtain; a nervous kettle waits on a wooden stool, its spout peeking through the opening.

#### 2. Сюжет пошёл наискосок

- **ID:** `muscle.obliques:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории уже 30 разных дней основной нагрузки на косые мышцы живота: минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Чайник требует гримёрку.
- **Fish Drama 3:** `[playful] В твоей истории уже <emphasis>30 разных дней</emphasis> основной нагрузки на косые мышцы живота: минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Чайник требует гримёрку.`
- **Image prompt:** A crab stagehand with oversized angled pincers rolls a kettle's stool onto a larger theater stage; beside the open curtain stands a tiny dressing booth containing a towel and a spout-shaped mirror.

#### 3. Гравитация берёт антракт

- **ID:** `muscle.obliques:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Косые мышцы живота получили у тебя 75 разных дней основной нагрузки: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. Теперь чайник собирает целый театр.
- **Fish Drama 3:** `[confident] Косые мышцы живота получили у тебя <emphasis>75 разных дней</emphasis> основной нагрузки: в каждом — минимум два полных рабочих подхода или 60 секунд силового удержания. [excited] Теперь чайник собирает целый театр.`
- **Image prompt:** A crab stagehand with oversized angled pincers turns a revolving stage beneath a performing kettle; folded city scenery fans outward behind the soloist, while rows of wooden spoons fill the audience seats.

#### 4. Кипящие овации

- **ID:** `muscle.obliques:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 150 разных дней основной нагрузки на косые мышцы живота — минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Оперный театр построен — ради чайника.
- **Fish Drama 3:** `[triumphant] Ты накопил <emphasis>150 разных дней</emphasis> основной нагрузки на косые мышцы живота — минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Оперный театр построен — <slow>ради чайника.</slow>`
- **Image prompt:** A crab stagehand with oversized angled pincers parts towering opera curtains to reveal a tiny kettle bowing on a saucer; balconies packed with wooden spoons applaud as a soup ladle offers the soloist a biscuit.

### `muscle.quads`

**Правило:** Квадрицепсы: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Первый рейс квадрицепсов

- **ID:** `muscle.quads:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоём маршруте 12 разных дней основной нагрузки на квадрицепсы: минимум два полных рабочих подхода или 60 секунд силового удержания за день. Локомотив тронулся, тапочки заняли места.
- **Fish Drama 3:** `[warm] В твоём маршруте 12 разных дней основной нагрузки на квадрицепсы: минимум два полных рабочих подхода или 60 секунд силового удержания за день. [playful] Локомотив тронулся, тапочки заняли места.`
- **Image prompt:** A square-nosed locomotive with four chunky side pistons emerges from a small depot, pulling a single open wagon; a pair of slippers sits upright on a cushion, with a tiny suitcase tucked between them.

#### 2. Тапочки едут отдельно

- **ID:** `muscle.quads:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** 30 разных дней с основной нагрузкой на квадрицепсы уже в твоём журнале: минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Тапочкам выдали отдельный вагон.
- **Fish Drama 3:** `[playful] <emphasis>30 разных дней</emphasis> с основной нагрузкой на квадрицепсы уже в твоём журнале: минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Тапочкам выдали отдельный вагон.`
- **Image prompt:** A square-nosed locomotive with four chunky side pistons crosses an arched bridge, towing a roomy passenger carriage; two slippers occupy oversized seats while their small suitcase rides alone in a luggage wagon.

#### 3. Кресло встречает экспресс

- **ID:** `muscle.quads:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За тобой 75 разных дней основной нагрузки на квадрицепсы — в каждом минимум два полных рабочих подхода или 60 секунд силового удержания. Даже кресло приехало посмотреть на этот состав.
- **Fish Drama 3:** `[confident] За тобой <emphasis>75 разных дней</emphasis> основной нагрузки на квадрицепсы — в каждом минимум два полных рабочих подхода или 60 секунд силового удержания. [excited] Даже кресло приехало посмотреть на этот состав.`
- **Image prompt:** A square-nosed locomotive with four chunky side pistons rounds a sweeping viaduct with its slipper carriage; an enormous armchair waits beside the track on a tiny wheeled trolley, leaning forward like an eager spectator.

#### 4. Вокзал берём с собой

- **ID:** `muscle.quads:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 150 разных дней основной нагрузки на квадрицепсы: минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Поезд готов — вокзал тоже едет.
- **Fish Drama 3:** `[triumphant] Ты собрал <emphasis>150 разных дней</emphasis> основной нагрузки на квадрицепсы: минимум два полных рабочих подхода или 60 секунд силового удержания в каждом. Поезд готов — <slow>вокзал тоже едет.</slow>`
- **Image prompt:** A square-nosed locomotive with four chunky side pistons hauls an entire station building on a flatbed; two slippers lean from its ticket window waving handkerchiefs, while an abandoned platform bench tilts in surprise.

### `muscle.rear-shoulders`

**Правило:** Задние дельты: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Первый свет за кулисами

- **ID:** `muscle.rear-shoulders:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 12 разных дней основной нагрузки на задние дельты — в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. У кулис появился свой прожектор!
- **Fish Drama 3:** `[warm] Ты накопил 12 разных дней основной нагрузки на задние дельты — в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. У кулис появился <emphasis>свой прожектор!</emphasis>`
- **Image prompt:** A small stagehand robot guides a single articulated spotlight from behind a half-open theater curtain. Its beam lands on a lone dumbbell waiting onstage, while the robot peeks around the fabric with one hand on the lamp handle.

#### 2. Репетиция заднего плана

- **ID:** `muscle.rear-shoulders:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя уже 30 разных дней основной работы на задние дельты: в каждом — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Задний план явно метит в солисты.
- **Fish Drama 3:** `[playful] У тебя уже <emphasis>30 разных дней</emphasis> основной работы на задние дельты: в каждом — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Задний план явно метит в солисты.`
- **Image prompt:** A small stagehand robot rolls a twin-spotlight trolley behind a theater curtain, aiming both lamps toward a pair of dumbbell actors. A coiled cable trails beside its feet as it cues their entrance with one raised hand.

#### 3. Кулисы ведут спектакль

- **ID:** `muscle.rear-shoulders:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За твоими плечами 75 разных дней основной нагрузки на задние дельты — минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждом. Прожекторы уже репетируют овацию.
- **Fish Drama 3:** `[confident] За твоими плечами <emphasis>75 разных дней</emphasis> основной нагрузки на задние дельты — минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждом. [excited] Прожекторы уже репетируют овацию.`
- **Image prompt:** A small stagehand robot conducts a semicircle of articulated spotlights from a compact lever console. Onstage, dumbbell actors cast enormous dancing shadows across the curtain while the robot raises a cable like a conductor's baton.

#### 4. Автограф для прожектора

- **ID:** `muscle.rear-shoulders:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 150 разных дней основной работы на задние дельты: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. Прожектор просит автограф — и светится от счастья.
- **Fish Drama 3:** `[triumphant] Ты собрал <emphasis>150 разных дней</emphasis> основной работы на задние дельты: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. <slow>Прожектор просит автограф</slow> — и светится от счастья.`
- **Image prompt:** A small stagehand robot holds a pen above an empty autograph book offered by a towering spotlight. The lamp bends its jointed neck toward the robot, gripping the book with its barn doors, while dumbbells in theater seats lean forward to watch.

### `muscle.traps`

**Правило:** Трапеции: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Трапеции приняли посылку

- **ID:** `muscle.traps:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 12 разных дней основной нагрузки на трапеции: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. Погрузчик доставил первую подушку — деликатный груз!
- **Fish Drama 3:** `[warm] Ты накопил 12 разных дней основной нагрузки на трапеции: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. Погрузчик доставил первую подушку — <soft>деликатный груз!</soft>`
- **Image prompt:** A tiny forklift with a trapezoid-shaped cab carefully carries a plump square pillow across a loading dock. The pillow rests on both forks like precious cargo, while the forklift peers around its fluffy edge.

#### 2. Подушка едет по плану

- **ID:** `muscle.traps:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** В твоей истории 30 разных дней основной работы на трапеции — минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждом. На складе подушек появился отдел логистики.
- **Fish Drama 3:** `[playful] В твоей истории <emphasis>30 разных дней</emphasis> основной работы на трапеции — минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждом. На складе подушек появился отдел логистики.`
- **Image prompt:** A tiny forklift with a trapezoid-shaped cab steers a single pillow between tall shelves of neatly folded bedding. A low ramp and a waiting flatbed cart turn the snug warehouse aisle into an elaborate delivery route.

#### 3. Вокзал мягких отправлений

- **ID:** `muscle.traps:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты собрал 75 разных дней основной нагрузки на трапеции: в каждом — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Погрузчик управляет целым подушечным вокзалом.
- **Fish Drama 3:** `[confident] Ты собрал <emphasis>75 разных дней</emphasis> основной нагрузки на трапеции: в каждом — минимум 2 полных рабочих подхода или 60 секунд силового удержания. [excited] Погрузчик управляет целым подушечным вокзалом.`
- **Image prompt:** A tiny forklift with a trapezoid-shaped cab directs a train of low carts piled with pillows at a miniature freight platform. One pillow sits on its raised forks like a dispatcher's paddle as the soft cargo curves around the dock.

#### 4. Подушка везёт начальство

- **ID:** `muscle.traps:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя 150 разных дней основной нагрузки на трапеции: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. Теперь подушка возит погрузчик — логистика сдалась.
- **Fish Drama 3:** `[triumphant] У тебя <emphasis>150 разных дней</emphasis> основной нагрузки на трапеции: в каждом минимум 2 полных рабочих подхода или 60 секунд силового удержания. <slow>Теперь подушка возит погрузчик</slow> — логистика сдалась.`
- **Image prompt:** A tiny forklift with a trapezoid-shaped cab lounges atop a giant pillow riding on a flatbed trolley. Its forks cradle a miniature blanket while smaller pillows push the trolley from behind, reversing every rule of the warehouse.

### `muscle.traps-middle`

**Правило:** Средняя трапеция: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Первый выход трапеции

- **ID:** `muscle.traps-middle:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 12 дней основной работы средней трапеции: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Занавес пошёл, железо выглянуло.
- **Fish Drama 3:** `[warm]Ты накопил 12 дней основной работы средней трапеции: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Занавес пошёл, <soft>железо выглянуло.</soft>`
- **Image prompt:** A beaver stagehand with rolled sleeves draws two curtain handles toward its chest, opening a miniature theater. A shy dumbbell peeks through the gap, balancing on a low wooden stool beside a coiled stage rope.

#### 2. Гримёрка для железа

- **ID:** `muscle.traps-middle:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** У тебя уже 30 разных дней со средней трапецией в главной роли: минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждый. Железо просит отдельную гримёрку.
- **Fish Drama 3:** `[playful]У тебя уже 30 разных дней со средней трапецией в главной роли: минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждый. Железо просит <emphasis>отдельную гримёрку.</emphasis>`
- **Image prompt:** A beaver stagehand with rolled sleeves pulls twin curtain handles inward, revealing a busy theater. Kettlebell actors gather around a dumbbell inspecting its reflection at a dressing table; a prop cart waits in the wings.

#### 3. Трапеция зовёт оркестр

- **ID:** `muscle.traps-middle:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** 75 дней основной нагрузки на среднюю трапецию ты собрал не за один выход: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Оркестр, туш!
- **Fish Drama 3:** `[confident]75 дней основной нагрузки на среднюю трапецию ты собрал не за один выход: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. [excited]Оркестр, <emphasis>туш!</emphasis>`
- **Image prompt:** A beaver stagehand with rolled sleeves draws two curtain handles inward from a catwalk, unveiling a vast concert stage. A barbell conducts rows of kettlebell musicians, while one tiny kettlebell sits at an absurdly oversized piano.

#### 4. Космический занавес

- **ID:** `muscle.traps-middle:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** За твоими плечами 150 разных дней основной работы средней трапеции: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Ты открыл занавес, а там… штанга в пижаме.
- **Fish Drama 3:** `[triumphant]За твоими плечами 150 разных дней основной работы средней трапеции: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Ты открыл занавес, <slow>а там…</slow> [playful]штанга в пижаме.`
- **Image prompt:** A beaver stagehand with rolled sleeves pulls twin handles toward its chest, parting theater curtains stretched across the night sky. An enormous barbell in pajamas hugs a teddy bear in a hilariously undersized bed at center stage.

### `muscle.triceps`

**Правило:** Трицепс: накопить дни с явной канонической ролью primary, минимум два полных рабочих подхода или 60 секунд силового удержания. Вспомогательные роли, кардио и растяжка не засчитываются. Дополнительно для ступеней нужны разные дни подтверждённой практики: 12, 30, 75, 150. Не подряд; без повышения нагрузки ради награды. **Единица:** день основной нагрузки. **Источник:** `requires_primary`.

#### 1. Первый тост трицепса

- **ID:** `muscle.triceps:t1`
- **Порог:** 12 день основной нагрузки
- **Подтверждённая практика:** минимум 12 разных дней; оба условия обязательны.
- **Ступень:** Начало
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Трицепсу ты отвёл главную роль в 12 разных днях: минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждый. Тостер практики выдал первый хруст!
- **Fish Drama 3:** `[warm]Трицепсу ты отвёл главную роль в 12 разных днях: минимум 2 полных рабочих подхода или 60 секунд силового удержания в каждый. Тостер практики выдал <soft>первый хруст!</soft>`
- **Image prompt:** A square-headed robot chef in a floppy chef hat presses a long toaster lever with one hand; a single dumbbell-shaped slice of toast springs upward. A tiny butter dish waits beside the toaster on a neatly folded napkin.

#### 2. Пекарня рабочих подходов

- **ID:** `muscle.triceps:t2`
- **Порог:** 30 день основной нагрузки
- **Подтверждённая практика:** минимум 30 разных дней; оба условия обязательны.
- **Ступень:** Практика
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Уже 30 разных дней ты работал с трицепсом как основной мышцей: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. У тостера теперь своя пекарня.
- **Fish Drama 3:** `[playful]Уже 30 разных дней ты работал с трицепсом как основной мышцей: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. У тостера теперь <emphasis>своя пекарня.</emphasis>`
- **Image prompt:** A square-headed robot chef in a floppy chef hat pushes down a bakery toaster lever, sending dumbbell-shaped toast slices onto a serving rack. Two kettlebell customers lean eagerly over the counter, holding empty breakfast plates.

#### 3. Банкет для железа

- **ID:** `muscle.triceps:t3`
- **Порог:** 75 день основной нагрузки
- **Подтверждённая практика:** минимум 75 разных дней; оба условия обязательны.
- **Ступень:** Мастерство
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Банкет практики готов: ты накопил 75 разных дней основной работы трицепса, в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Железо, к столу!
- **Fish Drama 3:** `[confident]Банкет практики готов: ты накопил 75 разных дней основной работы трицепса, в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. [excited]Железо, <emphasis>к столу!</emphasis>`
- **Image prompt:** A square-headed robot chef in a floppy chef hat operates a banquet-sized toaster with a long press-down lever. Dumbbell-shaped toast arcs onto a tiered serving cart, while kettlebell waiters arrange an enormous breakfast table.

#### 4. Лунный заказ принят

- **ID:** `muscle.triceps:t4`
- **Порог:** 150 день основной нагрузки
- **Подтверждённая практика:** минимум 150 разных дней; оба условия обязательны.
- **Ступень:** Горизонт
- **Редкость:** Легендарная (`legendary`)
- **Фраза:** Ты накопил 150 разных дней основной нагрузки на трицепс: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Тостер вышел на орбиту, а Луна заказала хрустящий полумесяц.
- **Fish Drama 3:** `[triumphant]Ты накопил 150 разных дней основной нагрузки на трицепс: в каждый — минимум 2 полных рабочих подхода или 60 секунд силового удержания. Тостер вышел на орбиту, <slow>а Луна заказала</slow> [playful]хрустящий полумесяц.`
- **Image prompt:** A square-headed robot chef in a floppy chef hat presses an orbital toaster lever; crescent-shaped toast sails toward a sleepy Moon holding a breakfast plate. A tiny butter pat follows in its own saucepan-shaped capsule.
