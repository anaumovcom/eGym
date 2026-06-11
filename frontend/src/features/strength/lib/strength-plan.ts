import type { ExerciseLoadSettings } from '@/entities/exercise/model/types'
import type { RuntimeExerciseKind, RuntimeSetPlan, RuntimeSetResult } from '@/entities/runtime/model/types'
import type { StrengthSetPlan, StrengthSetType, StrengthTrainingMode } from '@/entities/strength/model/types'

const STRENGTH_MODE_TITLES: Record<string, string> = {
  basic: 'Базовый режим',
  last_set_failure: 'Последний подход до отказа',
  straight_pyramid: 'Прямая пирамида',
  reverse_pyramid: 'Обратная пирамида',
  strength: 'Силовой режим',
  hypertrophy: 'Мышечный рост',
  double_progression: 'Двойная прогрессия',
  strength_circuit: 'Круговая тренировка',
  technique_light: 'Техника / лёгкая тренировка',
  periodized_day: 'Лёгкий / средний / тяжёлый день',
}

export const FALLBACK_STRENGTH_MODES: StrengthTrainingMode[] = [
  { id: 'basic', title: 'Базовый режим', shortDescription: 'Разминка и 2–4 рабочих подхода без полного отказа.', goal: 'Стабильность, техника и регулярный прогресс.', level: 'Новичок / средний', audience: 'Новички, пользователи после перерыва и регулярные занятия.', dayOptions: [] },
  { id: 'last_set_failure', title: 'Последний подход до отказа', shortDescription: 'Основные подходы почти до отказа, последний — до технического отказа.', goal: 'Повысить интенсивность без отказа в каждом подходе.', level: 'Средний', audience: 'Тренажёры, изоляция, руки, плечи, тяги блока, жим ногами и пресс.', dayOptions: [], safetyNote: 'Не выбирать по умолчанию для тяжёлого приседа, становой тяги и жима без страховки.' },
  { id: 'straight_pyramid', title: 'Прямая пирамида', shortDescription: 'Вес растёт от подхода к подходу, количество повторений снижается.', goal: 'Плавно войти в рабочий вес и найти нагрузку дня.', level: 'Новичок / средний', audience: 'Пользователи, которые ещё подбирают точный рабочий вес.', dayOptions: [] },
  { id: 'reverse_pyramid', title: 'Обратная пирамида', shortDescription: 'После разминки первым идёт самый тяжёлый подход, затем вес снижается.', goal: 'Сохранить максимум сил для главного тяжёлого подхода.', level: 'Опытный', audience: 'Пользователи с устойчивой техникой и известным рабочим весом.', dayOptions: [] },
  { id: 'strength', title: 'Силовой режим', shortDescription: '3–5 тяжёлых подходов по 3–6 повторений с длинным отдыхом.', goal: 'Развитие максимальной силы без отказных подходов.', level: 'Средний / опытный', audience: 'Присед, жим, тяга, подтягивания с весом и уверенная техника.', dayOptions: [] },
  { id: 'hypertrophy', title: 'Мышечный рост', shortDescription: '3–4 подхода в диапазоне повторений с умеренным отдыхом.', goal: 'Гипертрофия и понятный прогресс по верхней границе диапазона.', level: 'Новичок / средний', audience: 'Большинство регулярных силовых тренировок.', dayOptions: [] },
  { id: 'double_progression', title: 'Двойная прогрессия', shortDescription: 'Сначала добрать повторы в диапазоне, затем повышать вес.', goal: 'Понятное правило прогресса: 12 / 12 / 12 — увеличить вес.', level: 'Новичок / средний', audience: 'Большинство упражнений и регулярные тренировки.', dayOptions: [] },
  { id: 'strength_circuit', title: 'Круговая тренировка', shortDescription: '10–15 повторений, короткий отдых между упражнениями и 3–4 круга.', goal: 'Общая физическая подготовка, тонус и расход энергии.', level: 'Новичок / средний', audience: 'Короткие занятия, домашние тренировки и выносливость.', dayOptions: [] },
  { id: 'technique_light', title: 'Техника / лёгкая тренировка', shortDescription: '2–3 подхода без отказа с большим запасом повторов.', goal: 'Восстановление, техника и возвращение после перерыва.', level: 'Любой', audience: 'После болезни, перерыва или в лёгкий тренировочный день.', dayOptions: [] },
  { id: 'periodized_day', title: 'Лёгкий / средний / тяжёлый день', shortDescription: 'Периодизация нагрузки: лёгкий, средний или тяжёлый день.', goal: 'Менять нагрузку от тренировки к тренировке и не перегружаться.', level: 'Средний', audience: 'Пользователи, которые тренируются примерно 3 раза в неделю.', defaultDayType: 'medium', dayOptions: [{ id: 'light', label: 'Лёгкий', description: '2–3 подхода по 10–12 повторений, 3–4 повтора в запасе.' }, { id: 'medium', label: 'Средний', description: '3 подхода по 8–12 повторений, 1–3 повтора в запасе.' }, { id: 'heavy', label: 'Тяжёлый', description: '3–5 подходов по 4–8 повторений, 1–2 повтора в запасе.' }] },
]

export function getStrengthModeTitle(modeId?: string | null) {
  return STRENGTH_MODE_TITLES[modeId ?? 'basic'] ?? STRENGTH_MODE_TITLES.basic
}

export function normalizeStrengthModeId(modeId?: string | null) {
  return modeId && modeId in STRENGTH_MODE_TITLES ? modeId : 'basic'
}

export function normalizeStrengthDayType(modeId: string, dayType?: string | null) {
  if (modeId !== 'periodized_day') {
    return null
  }

  return dayType === 'light' || dayType === 'medium' || dayType === 'heavy' ? dayType : 'medium'
}

function formatWeight(weight: number, factor: number, kind?: RuntimeExerciseKind | 'weighted' | 'bodyweight' | 'timed') {
  if (kind === 'bodyweight' || kind === 'timed' || weight <= 0) {
    return { label: 'вес тела', value: 0 }
  }

  const value = Math.max(0, Math.round(weight * factor))
  return { label: `${value} кг`, value }
}

function parseTargetRange(label: string) {
  const numbers = [...label.matchAll(/\d+/g)].map((match) => Number(match[0]))
  if (numbers.length >= 2) {
    return { min: numbers[0], max: numbers[1] }
  }

  if (numbers.length === 1) {
    return { min: numbers[0], max: numbers[0] }
  }

  return { min: undefined, max: undefined }
}

function planItem(
  setNumber: number,
  setType: StrengthSetType,
  label: string,
  targetRepsLabel: string,
  factor: number,
  restSeconds: number,
  rirLabel: string,
  note: string,
  settings: Pick<ExerciseLoadSettings, 'weight'>,
  kind?: RuntimeExerciseKind | 'weighted' | 'bodyweight' | 'timed',
): StrengthSetPlan {
  const weight = formatWeight(settings.weight, factor, kind)
  return {
    setNumber,
    setType,
    label,
    targetRepsLabel,
    recommendedWeightLabel: weight.label,
    restSeconds,
    rirLabel,
    note,
  }
}

export function buildStrengthPlan(modeId: string | undefined, dayType: string | null | undefined, settings: Pick<ExerciseLoadSettings, 'weight' | 'reps' | 'restSeconds'>, kind?: RuntimeExerciseKind | 'weighted' | 'bodyweight' | 'timed'): StrengthSetPlan[] {
  const normalizedModeId = normalizeStrengthModeId(modeId)
  const normalizedDayType = normalizeStrengthDayType(normalizedModeId, dayType)
  const restSeconds = Math.max(15, settings.restSeconds)
  const item = (setNumber: number, setType: StrengthSetType, label: string, targetRepsLabel: string, factor: number, rest: number, rirLabel: string, note: string) =>
    planItem(setNumber, setType, label, targetRepsLabel, factor, rest, rirLabel, note, settings, kind)

  if (normalizedModeId === 'last_set_failure') {
    return [
      item(1, 'warmup', 'Разминка', '10–12', 0.5, 60, '4–5 в запасе', 'Лёгкий вход в движение.'),
      item(2, 'work', 'Рабочий подход', '8–12', 1, 120, '2 в запасе', 'Не доводить до отказа.'),
      item(3, 'work', 'Рабочий подход', '8–12', 1, 120, '1 в запасе', 'Остановиться при ухудшении техники.'),
      item(4, 'failure', 'До отказа', 'максимум', 1, 120, '0', 'Только технический отказ без боли.'),
    ]
  }

  if (normalizedModeId === 'straight_pyramid') {
    return [
      item(1, 'work', 'Рабочий подход', '12', 0.7, 90, '3 в запасе', 'Лёгкий вес.'),
      item(2, 'work', 'Рабочий подход', '10', 0.8, 90, '2 в запасе', 'Средний вес.'),
      item(3, 'work', 'Рабочий подход', '8', 0.9, 120, '1–2 в запасе', 'Тяжёлый вес.'),
      item(4, 'work', 'Рабочий подход', '6–8', 1, 120, '1–2 в запасе', 'Самый тяжёлый подход без потери техники.'),
    ]
  }

  if (normalizedModeId === 'reverse_pyramid') {
    return [
      item(1, 'warmup', 'Подводящий', '8–10', 0.5, 60, '4–5 в запасе', 'Разогреть движение.'),
      item(2, 'warmup', 'Подводящий', '5–6', 0.75, 90, '3–4 в запасе', 'Подготовиться к тяжёлому весу.'),
      item(3, 'work', 'Рабочий подход', '6–8', 1, 180, '1–2 в запасе', 'Самый тяжёлый рабочий подход.'),
      item(4, 'work', 'Рабочий подход', '8–10', 0.9, 150, '1–2 в запасе', 'Снизить вес примерно на 10%.'),
      item(5, 'work', 'Рабочий подход', '10–12', 0.8, 150, '1–2 в запасе', 'Ещё снизить вес примерно на 10%.'),
    ]
  }

  if (normalizedModeId === 'strength') {
    return Array.from({ length: 4 }, (_, index) => item(index + 1, 'work', 'Рабочий подход', '3–6', 1, Math.max(restSeconds, 180), '1–3 в запасе', 'Без отказа; увеличивать вес только при уверенном выполнении.'))
  }

  if (normalizedModeId === 'hypertrophy') {
    return Array.from({ length: 3 }, (_, index) => item(index + 1, 'work', 'Рабочий подход', '8–12', 1, Math.max(60, Math.min(restSeconds, 120)), '1–2 в запасе', 'Держать диапазон повторений, а не одно число.'))
  }

  if (normalizedModeId === 'double_progression') {
    return Array.from({ length: 3 }, (_, index) => item(index + 1, 'work', 'Рабочий подход', '8–12', 1, Math.max(60, Math.min(restSeconds, 120)), '1–2 в запасе', 'Вес повышается только после 12 / 12 / 12.'))
  }

  if (normalizedModeId === 'strength_circuit') {
    return Array.from({ length: 3 }, (_, index) => item(index + 1, 'work', `Круг ${index + 1}`, '10–15', 0.75, 30, '2–3 в запасе', 'Короткий отдых перед следующим упражнением.'))
  }

  if (normalizedModeId === 'technique_light') {
    return Array.from({ length: 2 }, (_, index) => item(index + 1, 'work', 'Техника', '8–12', 0.7, Math.max(60, Math.min(restSeconds, 90)), '3–5 в запасе', 'Цель — чистая техника, не максимальный вес.'))
  }

  if (normalizedModeId === 'periodized_day') {
    if (normalizedDayType === 'light') {
      return Array.from({ length: 3 }, (_, index) => item(index + 1, 'work', 'Лёгкий день', '10–12', 0.75, 75, '3–4 в запасе', 'Не форсировать увеличение веса.'))
    }

    if (normalizedDayType === 'heavy') {
      return Array.from({ length: 4 }, (_, index) => item(index + 1, 'work', 'Тяжёлый день', '4–8', 1, 180, '1–2 в запасе', 'Отдых длиннее, отказ не нужен.'))
    }

    return Array.from({ length: 3 }, (_, index) => item(index + 1, 'work', 'Средний день', '8–12', 0.9, 90, '1–3 в запасе', 'Средняя нагрузка без перегруза.'))
  }

  return [
    item(1, 'warmup', 'Разминка', '10–12', 0.5, 60, '4–5 в запасе', 'Лёгкий разминочный подход.'),
    item(2, 'work', 'Рабочий подход', '8–12', 1, Math.max(60, Math.min(restSeconds, 120)), '1–3 в запасе', 'Стабильная техника без отказа.'),
    item(3, 'work', 'Рабочий подход', '8–12', 1, Math.max(60, Math.min(restSeconds, 120)), '1–3 в запасе', 'Сохранять амплитуду.'),
    item(4, 'work', 'Рабочий подход', '8–12', 1, Math.max(60, Math.min(restSeconds, 120)), '1–3 в запасе', 'Остановиться до потери техники.'),
  ]
}

export function toRuntimeSetPlan(plan: StrengthSetPlan, fallbackTargetReps = 1): RuntimeSetPlan {
  const target = parseTargetRange(plan.targetRepsLabel)
  const weight = Number(plan.recommendedWeightLabel.replace(',', '.').match(/\d+(?:\.\d+)?/)?.[0] ?? '0')
  const resolvedTargetMax = target.max ?? (plan.setType === 'failure' ? Math.max(1, fallbackTargetReps) : undefined)
  return {
    setType: plan.setType,
    targetReps: resolvedTargetMax,
    targetMinReps: target.min,
    targetMaxReps: resolvedTargetMax,
    weightLabel: plan.recommendedWeightLabel,
    recommendedWeightKg: weight,
    restSeconds: plan.restSeconds,
    rirLabel: plan.rirLabel,
    note: plan.note,
    warning: plan.setType === 'failure' ? 'До технического отказа: остановитесь при потере техники или боли.' : undefined,
  }
}

export function getSetTypeLabel(setType?: string | null) {
  if (setType === 'warmup') {
    return 'Разминка'
  }

  if (setType === 'failure') {
    return 'До отказа'
  }

  return 'Рабочий подход'
}

export function getBestSetLabel(results: RuntimeSetResult[]) {
  if (results.length === 0) {
    return '—'
  }

  const best = results.reduce((current, item) => ((item.volumeKg ?? 0) > (current.volumeKg ?? 0) ? item : current), results[0])
  if (best.weightKg && (best.reps ?? best.actualValue)) {
    const reps = best.reps ?? best.actualValue
    return `Подход ${best.setNumber}: ${best.weightKg} кг × ${reps} = ${Math.round(best.weightKg * reps)} кг`
  }

  return `Подход ${best.setNumber}: ${best.actualValue}`
}
