import type { ExerciseSummary } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard, MuscleStatus } from '@/entities/muscle/model/types'
import type { FatigueData, FatigueMode, FatigueMuscle, ProfileTab, ProgressData, ProgressExerciseDetails, ProgressTab, SettingsTab, Stage4DevFlags, Stage4Period, SystemSettingsData, UserProfileData } from '@/entities/stage4/model/types'
import { generatedExerciseEntries } from '@/mocks/generated/exercises.generated'

export const defaultStage4DevFlags: Stage4DevFlags = {
  machineReady: true,
  leftDriveError: false,
  rightDriveError: false,
  emergencyStop: false,
  safetyDisabled: false,
  noCalibration: false,
  highFatigue: false,
  criticalFatigue: false,
  noHistory: false,
  noPhotos: false,
  offlineHours: 0,
}

const baseProfiles: Record<string, UserProfileData> = {
  alexey: {
    id: 'alexey',
    name: 'Алексей',
    avatarLabel: 'А',
    goal: 'сила + общая форма',
    heightCm: 183,
    weightKg: 92.4,
    level: 'средний',
    email: '',
    notes: 'Тренировки вечером, предпочитает базовые упражнения и умеренный объём.',
    locale: 'Русский',
    units: 'kg / cm',
    theme: 'Тёмная',
    createdAt: '03 мая 2024',
    trainingFrequency: '3 раза в неделю',
    workoutDuration: '45 минут',
    workoutStyle: 'классическая силовая тренировка',
    autoPrograms: true,
    priorityMuscles: ['Грудь', 'Спина', 'Ноги'],
    considerationNotes: ['Избегать слишком длинных тренировок', 'Баланс силовых и лёгких дней'],
    bodyMeasurements: [
      { date: '12 мая 2024', weight: 92.4, waistCm: 97, chestCm: 108, hipsCm: 101, shouldersCm: 122, bicepsCm: 36 },
      { date: '05 мая 2024', weight: 93.1, waistCm: 98, chestCm: 108, hipsCm: 101, shouldersCm: 121.5, bicepsCm: 36 },
      { date: '28 апреля 2024', weight: 94.2, waistCm: 99, chestCm: 109, hipsCm: 102, shouldersCm: 121, bicepsCm: 35.8 },
    ],
    photos: [
      { id: '12may', date: '12 мая 2024', views: [{ id: 'front', label: 'Спереди' }, { id: 'side', label: 'Сбоку' }, { id: 'back', label: 'Сзади' }] },
      { id: '1may', date: '1 мая 2024', views: [{ id: 'front', label: 'Спереди' }, { id: 'side', label: 'Сбоку' }, { id: 'back', label: 'Сзади' }] },
      { id: '20apr', date: '20 апреля 2024', views: [{ id: 'front', label: 'Спереди' }, { id: 'side', label: 'Сбоку' }, { id: 'back', label: 'Сзади' }] },
    ],
  },
  elena: {
    id: 'elena',
    name: 'Елена',
    avatarLabel: 'Е',
    goal: 'поддержание активности',
    heightCm: 170,
    weightKg: 67.8,
    level: 'начальный+',
    email: 'elena@example.com',
    notes: 'Предпочитает короткие тренировки и аккуратное наращивание нагрузки.',
    locale: 'Русский',
    units: 'kg / cm',
    theme: 'Тёмная',
    createdAt: '14 февраля 2025',
    trainingFrequency: '4 раза в неделю',
    workoutDuration: '35 минут',
    workoutStyle: 'умеренная функциональная тренировка',
    autoPrograms: true,
    priorityMuscles: ['Ноги', 'Кор'],
    considerationNotes: ['Добавлять больше мобильности', 'Не перегружать плечи'],
    bodyMeasurements: [
      { date: '12 мая 2024', weight: 67.8, waistCm: 73, chestCm: 93, hipsCm: 98, shouldersCm: 107, bicepsCm: 29 },
      { date: '05 мая 2024', weight: 68.1, waistCm: 73.5, chestCm: 93, hipsCm: 98.5, shouldersCm: 107, bicepsCm: 29 },
    ],
    photos: [{ id: '12may', date: '12 мая 2024', views: [{ id: 'front', label: 'Спереди' }, { id: 'side', label: 'Сбоку' }, { id: 'back', label: 'Сзади' }] }],
  },
  guest: {
    id: 'guest',
    name: 'Гость',
    avatarLabel: 'Г',
    goal: 'ознакомительный режим',
    heightCm: 178,
    weightKg: 0,
    level: 'не задан',
    email: '',
    notes: '',
    locale: 'Русский',
    units: 'kg / cm',
    theme: 'Тёмная',
    createdAt: 'Сегодня',
    trainingFrequency: 'не задано',
    workoutDuration: 'не задано',
    workoutStyle: 'не задано',
    autoPrograms: false,
    priorityMuscles: [],
    considerationNotes: [],
    bodyMeasurements: [],
    photos: [],
  },
}

const fatigueSeed: Omit<FatigueMuscle, 'score' | 'readinessPercent' | 'status' | 'recoveryHours'>[] = [
  { id: 'chest', name: 'Грудь', shortName: 'Грудь', group: 'front', area: 'upper', lastLoadAt: 'Вчера, 18:20', impact: [{ exercise: 'Жим с пола со штангой', date: 'вчера, 18:20', share: '70%', status: 'high' }, { exercise: 'Жим лёжа', date: '10 мая, 17:40', share: '20%', status: 'medium' }, { exercise: 'Отжимания на брусьях', date: '8 мая, 16:10', share: '10%', status: 'light' }], recommendation: 'Сегодня не выполнять тяжёлые жимовые упражнения. Выберите спину, ноги или лёгкий кор.', recommendedExercises: [{ name: 'Тяга верхнего блока', note: 'Отличный выбор', status: 'ready' }, { name: 'Планка', note: 'Лёгкая нагрузка на кор', status: 'light' }], avoidExercises: [{ name: 'Жим лёжа со штангой', note: 'Высокая усталость', status: 'high' }, { name: 'Жим с пола со штангой', note: 'Высокая усталость', status: 'high' }] },
  { id: 'triceps', name: 'Трицепс', shortName: 'Трицепс', group: 'front', area: 'upper', lastLoadAt: 'Вчера, 18:20', impact: [{ exercise: 'Жим с пола', date: 'вчера, 18:20', share: '58%', status: 'high' }], recommendation: 'Снизьте прямую нагрузку на трицепс.', recommendedExercises: [{ name: 'Тяга к поясу', note: 'Нейтрально', status: 'ready' }], avoidExercises: [{ name: 'Французский жим', note: 'Лучше отложить', status: 'high' }] },
  { id: 'front-delta', name: 'Передняя дельта', shortName: 'Передняя дельта', group: 'front', area: 'upper', lastLoadAt: 'Вчера, 18:20', impact: [{ exercise: 'Жим стоя', date: '11 мая, 13:20', share: '65%', status: 'medium' }], recommendation: 'Можно тренировать умеренно.', recommendedExercises: [{ name: 'Тяга сверху', note: 'Подходит', status: 'ready' }], avoidExercises: [] },
  { id: 'abs', name: 'Пресс', shortName: 'Пресс', group: 'front', area: 'middle', lastLoadAt: '12 мая, 18:00', impact: [{ exercise: 'Планка', date: '12 мая, 18:00', share: '42%', status: 'medium' }], recommendation: 'Лёгкая усталость, допустима умеренная работа.', recommendedExercises: [{ name: 'Планка', note: 'Можно повторить в лёгком режиме', status: 'light' }], avoidExercises: [] },
  { id: 'quads', name: 'Квадрицепсы', shortName: 'Квадрицепсы', group: 'front', area: 'lower', lastLoadAt: '10 мая, 16:30', impact: [{ exercise: 'Присед', date: '10 мая, 16:30', share: '72%', status: 'medium' }], recommendation: 'Можно тренировать умеренно или оставить лёгкий день.', recommendedExercises: [{ name: 'Выпады', note: 'Хороший выбор', status: 'light' }], avoidExercises: [] },
  { id: 'back', name: 'Спина', shortName: 'Спина', group: 'back', area: 'upper', lastLoadAt: '9 мая, 17:10', impact: [{ exercise: 'Тяга сверху', date: '9 мая, 17:10', share: '76%', status: 'light' }], recommendation: 'Спина готова к нагрузке.', recommendedExercises: [{ name: 'Тяга сверху', note: 'Отличный выбор', status: 'ready' }, { name: 'Тяга к поясу', note: 'Отличный выбор', status: 'ready' }], avoidExercises: [] },
  { id: 'rear-delta', name: 'Задняя дельта', shortName: 'Задняя дельта', group: 'back', area: 'upper', lastLoadAt: '9 мая, 17:10', impact: [{ exercise: 'Тяга к поясу', date: '9 мая, 17:10', share: '48%', status: 'light' }], recommendation: 'Низкая усталость.', recommendedExercises: [{ name: 'Face Pull', note: 'Подходит', status: 'light' }], avoidExercises: [] },
  { id: 'glutes', name: 'Ягодицы', shortName: 'Ягодицы', group: 'back', area: 'middle', lastLoadAt: '10 мая, 16:30', impact: [{ exercise: 'Присед', date: '10 мая, 16:30', share: '55%', status: 'light' }], recommendation: 'Готовы к умеренной нагрузке.', recommendedExercises: [{ name: 'Глют-мост', note: 'Нормально', status: 'light' }], avoidExercises: [] },
  { id: 'hamstrings', name: 'Бицепс бедра', shortName: 'Бицепс бедра', group: 'back', area: 'lower', lastLoadAt: '10 мая, 16:30', impact: [{ exercise: 'Румынская тяга', date: '10 мая, 16:30', share: '46%', status: 'light' }], recommendation: 'Низкая усталость, можно работать.', recommendedExercises: [{ name: 'Румынская тяга', note: 'Подходит', status: 'ready' }], avoidExercises: [] },
  { id: 'calves', name: 'Икры', shortName: 'Икры', group: 'back', area: 'lower', lastLoadAt: '8 мая, 14:10', impact: [{ exercise: 'Подъём на носки', date: '8 мая, 14:10', share: '60%', status: 'light' }], recommendation: 'Полностью готовы.', recommendedExercises: [{ name: 'Подъём на носки', note: 'Готовы', status: 'ready' }], avoidExercises: [] },
]

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function fatigueStatus(score: number): MuscleStatus {
  if (score >= 100) {
    return 'critical'
  }

  if (score >= 60) {
    return 'high'
  }

  if (score >= 30) {
    return 'medium'
  }

  if (score >= 10) {
    return 'light'
  }

  return 'ready'
}

function toReadiness(score: number) {
  return clamp(100 - score, 0, 100)
}

function decayFatigue(score: number, elapsedHours: number) {
  return Math.round(score * 0.5 ** (elapsedHours / 24))
}

function makeMachine(dev: Stage4DevFlags): MachineHealth {
  if (dev.emergencyStop) {
    return {
      machineState: 'blocked',
      machineLabel: 'Аварийная остановка активна',
      leftDrive: dev.leftDriveError ? 'error' : 'connected',
      rightDrive: dev.rightDriveError ? 'error' : 'connected',
      safety: 'emergency_stop',
      calibration: dev.noCalibration ? 'Калибровка отсутствует' : 'Калибровка заблокирована',
    }
  }

  if (!dev.machineReady || dev.leftDriveError || dev.rightDriveError || dev.safetyDisabled) {
    return {
      machineState: dev.leftDriveError || dev.rightDriveError ? 'blocked' : 'warning',
      machineLabel: dev.leftDriveError || dev.rightDriveError ? 'Требуется проверка системы' : 'Есть предупреждения',
      leftDrive: dev.leftDriveError ? 'error' : 'connected',
      rightDrive: dev.rightDriveError ? 'error' : 'connected',
      safety: dev.safetyDisabled ? 'disabled' : 'enabled',
      calibration: dev.noCalibration ? 'Калибровка отсутствует' : 'Калибровка готова',
    }
  }

  return {
    machineState: 'ready',
    machineLabel: 'Тренажёр готов',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: dev.noCalibration ? 'Нет калибровки' : 'Калибровка сохранена',
  }
}

export function getProfileSeed(userId: string | null) {
  return structuredClone(baseProfiles[userId ?? 'alexey'] ?? baseProfiles.alexey)
}

function buildSelectedExercise(blacklistedSlugs: string[], noHistory: boolean): ProgressExerciseDetails {
  const muscles: MuscleCard[] = [
    { name: 'Широчайшие', status: 'high', score: 78 },
    { name: 'Бицепс', status: 'medium', score: 54 },
    { name: 'Задняя дельта', status: 'medium', score: 49 },
  ]

  return {
    slug: blacklistedSlugs[0] ? 'machine-pulldown' : 'machine-pulldown',
    lastResult: noHistory ? 'Нет данных' : '45 кг × 10 × 3',
    bestResult: noHistory ? 'Нет данных' : '50 кг × 8',
    bestVolume: noHistory ? 'Нет данных' : '1 500 кг',
    completedTimes: noHistory ? '0 раз' : '8 раз',
    averageAmplitude: noHistory ? '—' : '92%',
    tempoTrend: noHistory ? '—' : 'Стабильный',
    workWeightSeries: noHistory ? [] : [
      { label: '22 апр', value: 35 },
      { label: '26 апр', value: 32 },
      { label: '30 апр', value: 34 },
      { label: '4 мая', value: 36 },
      { label: '8 мая', value: 40 },
      { label: '12 мая', value: 41 },
      { label: '16 мая', value: 44 },
      { label: '20 мая', value: 45, accent: true },
    ],
    volumeSeries: noHistory ? [] : [
      { label: '22 апр', value: 380 },
      { label: '4 мая', value: 720 },
      { label: '12 мая', value: 980 },
      { label: '20 мая', value: 1220, accent: true },
    ],
    history: noHistory ? [] : [
      { date: '21 мая 2025', weight: '45 кг', sets: '3', reps: '10 / 10 / 10', volume: '1 350 кг', amplitude: '93%' },
      { date: '18 мая 2025', weight: '45 кг', sets: '3', reps: '10 / 9 / 9', volume: '1 260 кг', amplitude: '91%' },
      { date: '16 мая 2025', weight: '42.5 кг', sets: '3', reps: '10 / 10 / 8', volume: '1 190 кг', amplitude: '90%' },
      { date: '12 мая 2025', weight: '50 кг', sets: '4', reps: '8 / 8 / 8 / 8', volume: '1 600 кг', amplitude: '93%' },
      { date: '8 мая 2025', weight: '47.5 кг', sets: '3', reps: '8 / 8 / 7', volume: '1 140 кг', amplitude: '90%' },
    ],
    affectedMuscles: muscles,
    recommendation: 'Отличная динамика. Попробуйте увеличить рабочий вес до 47.5–50 кг и удерживать 8–10 повторений для дальнейшего прогресса.',
  }
}

export function buildProgressData(options: { user: UserProfileData; period: Stage4Period; blacklistedSlugs: string[]; dev: Stage4DevFlags }): ProgressData {
  const machine = makeMachine(options.dev)
  const noHistory = options.dev.noHistory || options.user.id === 'guest'
  const noPhotos = options.dev.noPhotos || options.user.photos.length === 0
  const selectedExercise = buildSelectedExercise(options.blacklistedSlugs, noHistory)
  const muscleLoad: MuscleCard[] = [
    { name: 'Спина', status: 'high', score: 88 },
    { name: 'Бицепс', status: 'high', score: 82 },
    { name: 'Грудь', status: 'medium', score: 58 },
    { name: 'Ноги', status: 'medium', score: 52 },
    { name: 'Плечи', status: 'light', score: 34 },
    { name: 'Кор (пресс)', status: 'light', score: 32 },
    { name: 'Трицепс', status: 'medium', score: 46 },
    { name: 'Ягодицы', status: 'medium', score: 44 },
    { name: 'Предплечья', status: 'light', score: 28 },
  ]

  return {
    machine,
    updatedAt: 'сегодня, 08:30',
    periodLabel: options.period === '7d' ? '7 дней' : options.period === '30d' ? '30 дней' : options.period === '3m' ? '3 месяца' : options.period === '6m' ? '6 месяцев' : options.period === '1y' ? 'Год' : 'Всё время',
    title: 'Прогресс',
    subtitle: 'Отслеживайте свои результаты и динамику тренировок.',
    summaryCards: noHistory
      ? [
          { label: 'тренировок', value: '0', hint: 'недостаточно данных' },
          { label: 'подходов', value: '0', hint: 'история пуста' },
          { label: 'повторов', value: '0', hint: 'история пуста' },
          { label: 'общий объём', value: '0 кг', hint: 'история пуста' },
          { label: 'серия', value: '0 недель', hint: 'нет активности' },
          { label: 'изменение', value: '—', hint: 'недостаточно данных' },
        ]
      : [
          { label: 'тренировок', value: '8', hint: 'за 30 дней' },
          { label: 'подходов', value: '142', hint: 'выполнено' },
          { label: 'повторов', value: '1 284', hint: 'всего' },
          { label: 'общий объём', value: '42 600 кг', hint: 'за период' },
          { label: 'серия', value: '3 недели', hint: 'регулярности' },
          { label: '+4%', value: 'к объёму', hint: 'к прошлому периоду', tone: 'good' },
        ],
    summaryVolumeSeries: noHistory ? [] : [
      { label: '22 апр', value: 5 },
      { label: '26 апр', value: 18 },
      { label: '30 апр', value: 14 },
      { label: '4 мая', value: 28 },
      { label: '8 мая', value: 32 },
      { label: '12 мая', value: 27 },
      { label: '16 мая', value: 36 },
      { label: '20 мая', value: 42.6, accent: true },
    ],
    mainProgress: {
      exercise: 'Тяга сверху',
      from: '35 кг × 10 × 3',
      to: '45 кг × 10 × 3',
      delta: '+10 кг к рабочему весу',
      muscleFocus: [
        { name: 'Спина', status: 'high', score: 82 },
        { name: 'Грудь', status: 'medium', score: 44 },
        { name: 'Ноги', status: 'medium', score: 48 },
        { name: 'Плечи', status: 'medium', score: 41 },
      ],
    },
    improvements: ['Увеличился общий объём на 4%', 'Повысилась сила в базовых упражнениях', 'Стабильнее регулярность тренировок', 'Лучше восстановление между сессиями', 'Больше качественных повторов'],
    periodSummary: [
      { label: 'Период', value: '21 апр — 20 мая 2025' },
      { label: 'Тренировок', value: noHistory ? '0' : '8' },
      { label: 'Прирост объёма', value: noHistory ? '—' : '+4%', tone: 'good' },
      { label: 'Главный прирост', value: noHistory ? '—' : 'Тяга сверху +10 кг', tone: 'good' },
    ],
    recommendation: noHistory ? 'Сначала накопите несколько тренировок, чтобы увидеть динамику силы и объёма.' : 'Продолжайте в том же темпе. Рекомендуем добавить 1–2 подхода в базовых упражнениях для дальнейшего роста силы.',
    exerciseOptions: [
      { slug: 'machine-pulldown', name: 'Тяга сверху' },
      { slug: 'barbell-floor-press', name: 'Жим с пола' },
      { slug: 'barbell-heels-up-back-squat', name: 'Присед' },
    ],
    selectedExercise,
    strengthCards: [
      { label: 'Общий объём', value: noHistory ? '0 кг' : '42 600 кг' },
      { label: 'Средний объём', value: noHistory ? '0 кг' : '5 325 кг' },
      { label: 'Средний рабочий вес', value: noHistory ? '0 кг' : '38 кг' },
      { label: 'Подходы', value: noHistory ? '0' : '142' },
      { label: 'Повторы', value: noHistory ? '0' : '1 284' },
      { label: 'Самый объёмный день', value: noHistory ? '—' : '7 200 кг' },
    ],
    volumeTopExercises: [
      { rank: 1, name: 'Тяга сверху', value: '9 450 кг' },
      { rank: 2, name: 'Присед', value: '8 100 кг' },
      { rank: 3, name: 'Жим с пола', value: '6 800 кг' },
      { rank: 4, name: 'Тяга к поясу', value: '5 600 кг' },
      { rank: 5, name: 'Жим гантелей лёжа', value: '4 200 кг' },
    ],
    regularityCards: [
      { label: 'тренировок', value: noHistory ? '0' : '8' },
      { label: 'в неделю', value: noHistory ? '0' : '2' },
      { label: 'недели подряд', value: noHistory ? '0' : '3' },
      { label: 'пропущено', value: noHistory ? '0' : '1' },
      { label: 'средняя длительность', value: noHistory ? '0 мин' : '47 минут' },
    ],
    activityCalendar: Array.from({ length: 35 }, (_, index) => {
      const map: Array<'done' | 'partial' | 'missed' | 'rest'> = ['done', 'done', 'rest', 'done', 'done', 'rest', 'rest']
      const state = noHistory ? 'rest' : index === 26 ? 'missed' : index === 15 ? 'partial' : map[index % map.length]
      return { id: `day-${index + 1}`, day: 21 + index > 31 ? index - 10 : 21 + index, state }
    }),
    weeklyTrainingSeries: noHistory ? [] : [
      { label: '24 мар', value: 2 },
      { label: '31 мар', value: 3 },
      { label: '7 апр', value: 4 },
      { label: '14 апр', value: 2 },
      { label: '21 апр', value: 2 },
    ],
    weeklyMinuteSeries: noHistory ? [] : [
      { label: '24 мар', value: 44 },
      { label: '31 мар', value: 66 },
      { label: '7 апр', value: 92 },
      { label: '14 апр', value: 55 },
      { label: '21 апр', value: 47 },
    ],
    dayDistribution: noHistory ? [] : [
      { label: 'Пн', value: 2 },
      { label: 'Вт', value: 1 },
      { label: 'Ср', value: 1 },
      { label: 'Чт', value: 2 },
      { label: 'Пт', value: 2 },
      { label: 'Сб', value: 0 },
      { label: 'Вс', value: 0 },
    ],
    recentWeeks: noHistory ? [] : [
      { label: '21 апр — 27 апр', trainings: '2 тренировки', minutes: '40 мин', completion: '67%', status: 'medium' },
      { label: '14 апр — 20 апр', trainings: '2 тренировки', minutes: '55 мин', completion: '89%', status: 'ready' },
      { label: '7 апр — 13 апр', trainings: '4 тренировки', minutes: '92 мин', completion: '100%', status: 'ready' },
      { label: '31 мар — 6 апр', trainings: '3 тренировки', minutes: '66 мин', completion: '75%', status: 'medium' },
      { label: '24 мар — 30 мар', trainings: '2 тренировки', minutes: '40 мин', completion: '67%', status: 'medium' },
    ],
    muscleLoad,
    muscleSplit: muscleLoad.map((item, index) => ({ rank: index + 1, name: item.name, status: item.status, value: item.status === 'high' ? 'Очень высокая' : item.status === 'medium' ? 'Средняя' : 'Низкая' })),
    muscleCoverage: [
      { name: 'Спина', count: '7 трен.' },
      { name: 'Бицепс', count: '6 трен.' },
      { name: 'Грудь', count: '6 трен.' },
      { name: 'Ноги', count: '6 трен.' },
      { name: 'Плечи', count: '4 трен.' },
      { name: 'Кор', count: '4 трен.' },
      { name: 'Трицепс', count: '4 трен.' },
      { name: 'Ягодицы', count: '3 трен.' },
      { name: 'Предплечья', count: '3 трен.' },
    ],
    muscleRecommendation: 'Если восстановление в норме, рекомендуем добавить больше работы на плечи и кор.',
    bodyCards: [
      { label: 'Вес', value: `${options.user.weightKg} кг` },
      { label: 'Изменение', value: options.user.id === 'guest' ? '—' : '-1.2 кг', tone: 'good' },
      { label: 'Талия', value: options.user.id === 'guest' ? '—' : '97 см' },
      { label: 'Изменение талии', value: options.user.id === 'guest' ? '—' : '-1 см', tone: 'good' },
      { label: 'Последнее измерение', value: options.user.bodyMeasurements[0]?.date ?? 'Нет данных' },
    ],
    bodyWeightSeries: options.user.bodyMeasurements.length === 0 ? [] : [
      { label: '12 апр', value: 94.0 },
      { label: '19 апр', value: 93.5 },
      { label: '26 апр', value: 93.0 },
      { label: '3 мая', value: 92.6 },
      { label: '10 мая', value: 91.9 },
      { label: '12 мая', value: 92.4, accent: true },
    ],
    bodyMeasurements: options.user.bodyMeasurements.length === 0
      ? []
      : [
          { label: 'Талия', current: '97 см', delta: '-1 см', tone: 'good' },
          { label: 'Грудь', current: '108 см', delta: '0 см', tone: 'neutral' },
          { label: 'Плечи', current: '122 см', delta: '+0.5 см', tone: 'warning' },
          { label: 'Бёдра', current: '104 см', delta: '-1 см', tone: 'good' },
          { label: 'Бицепс', current: '36 см', delta: '0 см', tone: 'neutral' },
        ],
    smartScale: {
      connected: options.user.id !== 'guest',
      label: options.user.id === 'guest' ? 'Умные весы не подключены' : 'Умные весы подключены',
      hint: options.user.id === 'guest' ? 'Можно подключить устройство или ввести данные вручную.' : 'Последняя синхронизация: сегодня 08:40. Автоматическая синхронизация включена.',
    },
    photoEntries: noPhotos ? [] : options.user.photos.map((item, index) => ({ id: item.id, date: item.date.split(' ')[0] + ' ' + item.date.split(' ')[1], year: '2025', views: [{ id: 'front', label: 'Спереди' }, { id: 'side', label: 'Сбоку' }, { id: 'back', label: 'Сзади' }], isLatest: index === 0 })),
    photoStats: noPhotos
      ? [
          { label: 'Фиксаций сделано', value: '0' },
          { label: 'Дней отслеживания', value: '0' },
          { label: 'Средний интервал', value: '—' },
          { label: 'Последовательность', value: '—' },
        ]
      : [
          { label: 'Фиксаций сделано', value: '7' },
          { label: 'Дней отслеживания', value: '42' },
          { label: 'Средний интервал', value: '6 дней' },
          { label: 'Последовательность', value: '14 дней', tone: 'good' },
        ],
    photoRecommendation: noPhotos ? 'Сделайте первую фотофиксацию, чтобы начать отслеживать визуальные изменения.' : 'Продолжайте фиксировать прогресс каждые 2–4 недели. Регулярная фотофиксация помогает лучше отслеживать изменения и сохранять мотивацию.',
    emptyState: noHistory ? { title: 'Недостаточно данных для аналитики', description: 'История тренировок пока пуста. После нескольких завершённых тренировок здесь появятся графики, таблицы и рекомендации.' } : undefined,
  }
}

export function buildFatigueData(options: { dev: Stage4DevFlags }): FatigueData {
  const machine = makeMachine(options.dev)
  const elapsedHours = options.dev.offlineHours

  const muscles = fatigueSeed.map((item) => {
    const baseScore = options.dev.criticalFatigue ? (item.id === 'chest' || item.id === 'triceps' ? 118 : 74) : options.dev.highFatigue ? (item.id === 'chest' || item.id === 'triceps' ? 82 : 48) : item.id === 'chest' ? 66 : item.id === 'triceps' ? 62 : item.id === 'front-delta' ? 38 : item.id === 'abs' ? 26 : item.id === 'quads' ? 24 : item.id === 'back' ? 8 : item.id === 'rear-delta' ? 12 : item.id === 'glutes' ? 16 : item.id === 'hamstrings' ? 14 : 9
    const score = clamp(decayFatigue(baseScore, elapsedHours), 0, 180)
    return {
      ...item,
      score,
      readinessPercent: toReadiness(score),
      status: fatigueStatus(score),
      recoveryHours: Math.max(6, Math.round(score * 0.58)),
    }
  })

  const criticalCount = muscles.filter((item) => item.status === 'critical').length
  const highCount = muscles.filter((item) => item.status === 'high').length
  const mediumCount = muscles.filter((item) => item.status === 'medium').length
  const readyCount = muscles.filter((item) => item.status === 'ready' || item.status === 'light').length
  const readinessPercent = Math.round(muscles.reduce((sum, item) => sum + item.readinessPercent, 0) / muscles.length)

  return {
    machine,
    updatedAt: 'сегодня, 08:30',
    readinessPercent,
    overview: [
      { label: 'Готовность', value: `${readinessPercent}%`, hint: 'общая готовность организма к нагрузке', tone: readinessPercent >= 70 ? 'good' : readinessPercent >= 45 ? 'warning' : 'danger' },
      { label: 'Мышцы с высокой усталостью', value: `${criticalCount > 0 ? criticalCount : highCount}`, hint: 'лучше не нагружать', tone: 'danger' },
      { label: 'Мышцы со средней усталостью', value: `${mediumCount}`, hint: 'снизьте нагрузку', tone: 'warning' },
      { label: 'Мышцы готовы к нагрузке', value: `${readyCount}`, hint: 'можно тренировать', tone: 'good' },
    ],
    muscles,
    recommendedPlan: 'Сегодня лучше избегать нагрузки на грудь и трицепс. Оптимальный вариант — тренировка на спину, бицепс или ноги.',
    recoveryNote: `Усталость рассчитывается по фактическому времени восстановления. Последний пересчёт учитывает ${elapsedHours} ч офлайн-времени.`,
  }
}

export function buildSystemSettingsData(dev: Stage4DevFlags): SystemSettingsData {
  const machine = makeMachine(dev)

  return {
    machine,
    overviewCards: [
      { label: 'Статус системы', value: machine.machineState === 'ready' ? 'Готов к работе' : 'Есть предупреждения', tone: machine.machineState === 'ready' ? 'good' : 'warning' },
      { label: 'Безопасность', value: machine.safety === 'enabled' ? 'Включена' : 'Отключена', tone: machine.safety === 'enabled' ? 'good' : 'danger' },
      { label: 'Левый привод', value: machine.leftDrive === 'connected' ? 'Подключён' : 'Ошибка', tone: machine.leftDrive === 'connected' ? 'good' : 'danger' },
      { label: 'Правый привод', value: machine.rightDrive === 'connected' ? 'Подключён' : 'Ошибка', tone: machine.rightDrive === 'connected' ? 'good' : 'danger' },
      { label: 'Последняя диагностика', value: 'Сегодня, 08:40', tone: 'good' },
      { label: 'Запуск упражнений', value: machine.machineState === 'ready' ? 'Разрешён' : 'Ограничен', tone: machine.machineState === 'ready' ? 'good' : 'warning' },
    ],
    overviewEvents: [
      { time: '08:40', title: 'Диагностика завершена успешно', tone: 'good' },
      { time: '08:39', title: 'Приводы: проверка синхронности — норма', tone: 'good' },
      { time: '08:38', title: 'Калибровка положения: проверка пройдена', tone: 'good' },
      { time: '08:30', title: 'Питание восстановлено после отключения', tone: 'warning' },
    ],
    safety: {
      emergencyReady: !dev.emergencyStop,
      childLock: true,
      workoutPin: true,
      servicePin: true,
      idleLockMinutes: '2 минуты',
      guestMode: true,
      guestWeightLimit: '30 кг',
      maxLoad: '80 кг',
      maxSpeed: 'Средняя',
      syncLimit: '5 мм',
      desyncAction: 'Остановить движение',
    },
    mechanics: {
      statusSummary: [
        { label: 'Статус', value: machine.machineState === 'ready' ? 'Готов к работе' : 'Есть предупреждения', tone: machine.machineState === 'ready' ? 'good' : 'warning' },
        { label: 'Запуск движения', value: machine.machineState === 'ready' ? 'Разрешён' : 'Ограничен' },
        { label: 'Температура приводов', value: '36 °C / 35 °C' },
        { label: 'Напряжение питания', value: '230 V' },
        { label: 'Безопасность', value: machine.safety === 'enabled' ? 'Активна' : 'Отключена', tone: machine.safety === 'enabled' ? 'good' : 'danger' },
      ],
      leftDrive: [
        { label: 'Позиция', value: '862.4 мм' },
        { label: 'Скорость', value: '0 мм/с' },
        { label: 'Ток', value: '1.20 A' },
        { label: 'Пиковый ток', value: '3.18 A' },
        { label: 'Отклик', value: '6.2 мс' },
        { label: 'Ошибки', value: machine.leftDrive === 'connected' ? 'Нет ошибок' : 'Ошибка связи', tone: machine.leftDrive === 'connected' ? 'good' : 'danger' },
      ],
      rightDrive: [
        { label: 'Позиция', value: '862.0 мм' },
        { label: 'Скорость', value: '0 мм/с' },
        { label: 'Ток', value: '1.18 A' },
        { label: 'Пиковый ток', value: '3.15 A' },
        { label: 'Отклик', value: '6.3 мс' },
        { label: 'Ошибки', value: machine.rightDrive === 'connected' ? 'Нет ошибок' : 'Ошибка связи', tone: machine.rightDrive === 'connected' ? 'good' : 'danger' },
      ],
      sync: [
        { label: 'Позиция слева', value: '862.4 мм' },
        { label: 'Позиция справа', value: '862.0 мм' },
        { label: 'Разница', value: '0.4 мм', tone: 'good' },
        { label: 'Допуск', value: '5.0 мм' },
      ],
      motion: [
        { label: 'Макс. скорость', value: '1200 мм/с' },
        { label: 'Скорость калибровки', value: '200 мм/с' },
        { label: 'Ускорение', value: '4000 мм/с²' },
        { label: 'Плавность', value: 'включена', tone: 'good' },
      ],
      screw: [
        { label: 'Модель ШВП', value: 'SFE3232' },
        { label: 'Шаг', value: '32 мм/оборот' },
        { label: 'Рабочий ход', value: '1850 мм' },
        { label: 'Компенсация люфта', value: 'включена', tone: 'good' },
      ],
      profiles: ['Тренировка', 'Калибровка', 'Показ диапазона', 'Сервис'],
      service: [
        { label: 'Смазка ШВП (левая)', value: 'актуально', tone: 'good' },
        { label: 'Смазка ШВП (правая)', value: 'актуально', tone: 'good' },
        { label: 'Ресурс ШВП', value: '128 ч 47 мин' },
      ],
    },
    diagnostics: {
      lastRun: 'Сегодня, 08:40',
      checked: '8',
      success: '8',
      errors: machine.leftDrive === 'error' || machine.rightDrive === 'error' ? '1' : '0',
      systemStatus: machine.machineState === 'ready' ? 'Готова к работе' : 'Нужна проверка',
      checklist: ['Связь с левым приводом', 'Связь с правым приводом', 'Аварийная остановка', 'Система безопасности', 'Синхронность сторон', 'Датчики позиции', 'Сохранённые калибровки', 'Журнал ошибок'].map((label) => ({ label, result: 'OK' })),
      quickTests: [
        { title: 'Тест связи', description: 'Проверка связи с приводами и контроллерами' },
        { title: 'Тест чтения позиции', description: 'Проверка датчиков и энкодеров' },
        { title: 'Тест синхронности', description: 'Проверка синхронизации сторон' },
        { title: 'Тест удержания позиции', description: 'Проверка удержания без движения' },
        { title: 'Тест низкомоментного движения', description: 'Проверка плавности и сопротивления' },
      ],
      history: [
        { label: 'Сегодня, 08:40', result: '8 / 8', hint: 'Диагностика завершена успешно' },
        { label: 'Вчера, 18:22', result: '8 / 8', hint: '0 ошибок' },
        { label: '18 мая 2025, 09:14', result: '8 / 8', hint: '0 ошибок' },
        { label: '17 мая 2025, 21:47', result: '8 / 8', hint: '1 предупреждение' },
      ],
    },
    calibrations: {
      entries: [
        { id: 'floor-press', exercise: 'Жим с пола', muscle: 'Грудь', lowerPoint: '50 мм', upperPoint: '560 мм', updatedAt: '24.05.2024, 10:12', status: 'actual' },
        { id: 'squat', exercise: 'Присед', muscle: 'Ноги', lowerPoint: '120 мм', upperPoint: '620 мм', updatedAt: '22.05.2024, 16:45', status: 'actual' },
        { id: 'oh-press', exercise: 'Жим стоя', muscle: 'Плечи', lowerPoint: '60 мм', upperPoint: '540 мм', updatedAt: '18.05.2024, 09:30', status: 'stale' },
        { id: 'pulldown', exercise: 'Тяга сверху', muscle: 'Спина', lowerPoint: '80 мм', upperPoint: '680 мм', updatedAt: '15.05.2024, 14:20', status: dev.noCalibration ? 'stale' : 'actual' },
      ],
      total: '4',
      lastUpdate: '24.05.2024, 10:12',
      staleCount: dev.noCalibration ? '2' : '1',
      missingCount: dev.noCalibration ? '1' : '0',
    },
    service: {
      unlocked: true,
      positions: [
        { label: 'Левый привод', value: '1250.45 мм' },
        { label: 'Правый привод', value: '1251.10 мм' },
        { label: 'Разница синхронизации', value: '0.65 мм', tone: 'good' },
      ],
      driveHealth: [
        { label: 'Левый привод', value: machine.leftDrive === 'connected' ? 'Без ошибок' : 'Ошибка', tone: machine.leftDrive === 'connected' ? 'good' : 'danger' },
        { label: 'Правый привод', value: machine.rightDrive === 'connected' ? 'Без ошибок' : 'Ошибка', tone: machine.rightDrive === 'connected' ? 'good' : 'danger' },
        { label: 'Температура', value: '36 °C / 35 °C' },
        { label: 'Напряжение', value: '230 V' },
      ],
      actions: [
        { title: 'Сбросить ошибку', description: 'Сброс активных ошибок' },
        { title: 'Проверить нулевую позицию', description: 'Проверка датчика нуля' },
        { title: 'Переустановить ноль', description: 'Установка текущей позиции как ноль' },
        { title: 'Тест связи', description: 'Проверка связи с приводами' },
      ],
      journal: [
        { time: '08:42:17', action: 'Вход в сервисный режим', result: 'Сегодня, 08:42' },
        { time: '08:41:59', action: 'Тест связи — успешно', result: 'Сегодня, 08:41' },
        { time: '08:41:32', action: 'Проверка нулевой позиции — OK', result: 'Сегодня, 08:41' },
        { time: '08:40:21', action: 'Сброс ошибки — не требуется', result: 'Сегодня, 08:40' },
      ],
    },
    journal: {
      stats: [
        { label: 'Ошибок', value: '3', tone: 'danger' },
        { label: 'Предупреждений', value: '8', tone: 'warning' },
        { label: 'Информационных', value: '42' },
        { label: 'Успешных событий', value: '536', tone: 'good' },
      ],
      entries: [
        { id: '1', date: '12 мая, 18:42', category: 'Калибровки', level: 'info', title: 'Калибровка упражнения «Жим с пола» обновлена', description: 'Успешно сохранены новые параметры: диапазон движения и ограничители усилия.' },
        { id: '2', date: '12 мая, 18:40', category: 'Сервис', level: 'success', title: 'Диагностика завершена успешно', description: 'Проверка всех систем завершена без ошибок.' },
        { id: '3', date: '12 мая, 17:58', category: 'Тренировки', level: 'info', title: 'Тренировка завершена', description: 'Пользователь Алексей завершил программу «Сила — Нижняя часть тела».' },
        { id: '4', date: '12 мая, 16:22', category: 'Настройки', level: 'warning', title: 'Изменены параметры безопасности', description: 'Порог усилия повышен с 1200 Н до 1400 Н.' },
        { id: '5', date: '11 мая, 20:15', category: 'Безопасность', level: 'critical', title: 'Аварийная остановка активирована', description: 'Нажата кнопка аварийной остановки на панели управления.' },
      ],
    },
    common: {
      interfaceTheme: 'dark',
      interfaceScale: '100%',
      language: 'Русский',
      units: 'kg / cm',
      brightnessMode: 'Авто',
      autoReturnMinutes: '5 минут',
      soundEnabled: true,
      voiceHintsEnabled: true,
      signalVolume: '70%',
      wifiMode: 'Wi-Fi',
      networkStatus: 'Подключено',
      ssid: 'Forma_Network',
      ipAddress: '192.168.1.58',
      signalStrength: 'Отличный',
      version: 'v2.4.1',
      serialNumber: 'FORMA-SM-001284',
      workTime: '125 ч 47 мин',
    },
  }
}

export function getExerciseChoices(): ExerciseSummary[] {
  const slugs = ['machine-pulldown', 'barbell-floor-press', 'barbell-heels-up-back-squat', 'forearm-plank']
  return generatedExerciseEntries.filter((exercise) => slugs.includes(exercise.slug)).map((exercise) => ({
    ...exercise,
    secondaryName: exercise.name,
    name: exercise.nameRu,
    favorite: false,
    blacklisted: false,
    recommended: true,
    compatibilityTone: 'recommended',
    readinessStatus: 'ready',
    difficultyLabel: exercise.difficulty,
    badges: ['Прогресс'],
  }))
}

export const stage4Periods: Array<{ id: Stage4Period; label: string }> = [
  { id: '7d', label: '7 дней' },
  { id: '30d', label: '30 дней' },
  { id: '3m', label: '3 месяца' },
  { id: '6m', label: '6 месяцев' },
  { id: '1y', label: 'Год' },
  { id: 'all', label: 'Всё время' },
]

export const progressTabs: Array<{ id: ProgressTab; label: string }> = [
  { id: 'summary', label: 'Сводка' },
  { id: 'exercise', label: 'Упражнения' },
  { id: 'strength', label: 'Сила и объём' },
  { id: 'regularity', label: 'Регулярность' },
  { id: 'muscles', label: 'Мышцы' },
  { id: 'body', label: 'Тело' },
  { id: 'photo', label: 'Фото прогресса' },
]

export const profileTabs: Array<{ id: ProfileTab; label: string }> = [
  { id: 'summary', label: 'Сводка' },
  { id: 'general', label: 'Общее' },
  { id: 'goals', label: 'Цели' },
  { id: 'body', label: 'Данные тела' },
  { id: 'photo', label: 'Фото прогресса' },
  { id: 'blacklist', label: 'Чёрный список упражнений' },
]

export const settingsTabs: Array<{ id: SettingsTab; label: string }> = [
  { id: 'overview', label: 'Обзор' },
  { id: 'safety', label: 'Безопасность' },
  { id: 'mechanics', label: 'Приводы и ШВП' },
  { id: 'diagnostics', label: 'Диагностика' },
  { id: 'calibrations', label: 'Калибровки' },
  { id: 'service', label: 'Сервис' },
  { id: 'journal', label: 'Журнал' },
  { id: 'common', label: 'Общие' },
]

export const fatigueModes: Array<{ id: FatigueMode; label: string }> = [
  { id: 'current', label: 'Сейчас' },
  { id: 'after-workout', label: 'После последней тренировки' },
  { id: '7d', label: 'За 7 дней' },
  { id: '30d', label: 'За 30 дней' },
]