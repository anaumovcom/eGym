import type { WorkoutBuilderData } from '@/entities/builder/model/types'
import type { WorkoutCalendarData } from '@/entities/calendar/model/types'
import type { ExerciseCatalogResponse, ExerciseCompatibility, ExerciseDetails, ExerciseDifficulty, ExerciseForce, ExerciseMechanic, ExerciseSummary } from '@/entities/exercise/model/types'
import type { ProgramDetails, ProgramSummary } from '@/entities/program/model/types'
import type { QuickStartData, QuickStartExerciseListItem } from '@/entities/quick-start/model/types'
import type { TodayWorkoutData, WorkoutExercisePanel } from '@/entities/workout/model/types'
import type { MuscleCard, MuscleStatus } from '@/entities/muscle/model/types'
import type { KnownUserId } from '@/mocks/data'
import { machineScenarios } from '@/mocks/data'
import { generatedExerciseEntries } from '@/mocks/generated/exercises.generated'

type PreferenceState = {
  favorites: string[]
  blacklist: string[]
}

export type TodayScenario = TodayWorkoutData['startState']
export type CatalogQuery = {
  search?: string
  muscles?: string[]
  equipment?: string[]
  difficulty?: ExerciseDifficulty[]
  force?: ExerciseForce[]
  mechanic?: ExerciseMechanic[]
  grips?: string[]
}

export type ProgramLibraryData = {
  searchPlaceholder: string
  categoryFilters: string[]
  durationFilters: string[]
  levelFilters: string[]
  equipmentFilters: string[]
  recommended: ProgramSummary[]
  allPrograms: ProgramSummary[]
  selectedProgram: ProgramDetails
}

type GeneratedEntry = (typeof generatedExerciseEntries)[number]

const mediaSupportedSlugs = new Set([
  'barbell-floor-press',
  'barbell-bench-press',
  'machine-pulldown',
  'machine-seated-cable-row',
  'underhand-pulldown',
  'barbell-curl',
  'forearm-plank',
  'forward-lunges',
  'barbell-front-squat-olympic',
  'barbell-heels-up-back-squat',
  'smith-machine-bench-press',
])

const defaultPreferences: PreferenceState = {
  favorites: ['barbell-floor-press', 'barbell-bench-press', 'machine-pulldown', 'forearm-plank'],
  blacklist: ['smith-machine-bench-press'],
}

const stage2FeaturedSlugs = {
  quickStart: ['machine-pulldown', 'machine-seated-cable-row', 'barbell-curl'],
  recent: ['barbell-bench-press', 'barbell-floor-press', 'machine-pulldown'],
  catalog: ['barbell-floor-press', 'machine-pulldown', 'barbell-heels-up-back-squat', 'barbell-curl', 'barbell-bench-press', 'forward-lunges', 'machine-seated-cable-row', 'forearm-plank'],
  today: ['machine-pulldown', 'machine-seated-cable-row', 'barbell-curl', 'underhand-pulldown', 'forearm-plank'],
} as const

const muscleTranslations: Record<string, string> = {
  chest: 'Грудь',
  triceps: 'Трицепс',
  shoulders: 'Плечи',
  delts: 'Дельты',
  biceps: 'Бицепс',
  back: 'Спина',
  lats: 'Широчайшие',
  upper_back: 'Верх спины',
  lower_back: 'Низ спины',
  traps: 'Трапеции',
  abs: 'Пресс',
  obliques: 'Косые мышцы',
  glutes: 'Ягодицы',
  quads: 'Квадрицепс',
  hamstrings: 'Бицепс бедра',
  adductors: 'Приводящие',
  abductors: 'Отводящие',
  calves: 'Икры',
  forearms: 'Предплечья',
  neck: 'Шея',
  core: 'Кор',
  serratus_anterior: 'Передняя зубчатая',
  hip_flexors: 'Сгибатели бедра',
}

const equipmentTranslations: Record<string, string> = {
  Barbell: 'Штанга',
  Dumbbell: 'Гантели',
  Machine: 'Тренажёр',
  Cable: 'Кроссовер',
  Bodyweight: 'Собственный вес',
  'Smith Machine': 'Машина Смита',
  Band: 'Резина',
  Kettlebell: 'Гиря',
  'BOSU Ball': 'BOSU',
  'Stability Ball': 'Фитбол',
  'EZ Curl Bar': 'EZ-штанга',
}

const difficultyLabels: Record<ExerciseDifficulty, string> = {
  Beginner: 'Новичок',
  Intermediate: 'Средний',
  Advanced: 'Продвинутый',
}

const gripTranslations: Record<string, string> = {
  Overhand: 'Прямой',
  Underhand: 'Обратный',
  Neutral: 'Нейтральный',
  Mixed: 'Смешанный',
}

const statusSeverity: Record<MuscleStatus, number> = {
  ready: 0,
  light: 1,
  medium: 2,
  high: 3,
  critical: 4,
  no_data: 5,
}

const baseMuscleProfiles: Record<KnownUserId, Record<string, MuscleCard>> = {
  alexey: {
    lats: { name: 'Широчайшие', status: 'ready', score: 16 },
    back: { name: 'Спина', status: 'ready', score: 12 },
    upper_back: { name: 'Верх спины', status: 'light', score: 24 },
    lower_back: { name: 'Низ спины', status: 'light', score: 22 },
    biceps: { name: 'Бицепс', status: 'light', score: 26 },
    forearms: { name: 'Предплечья', status: 'light', score: 19 },
    chest: { name: 'Грудь', status: 'medium', score: 54 },
    triceps: { name: 'Трицепс', status: 'medium', score: 48 },
    shoulders: { name: 'Плечи', status: 'medium', score: 44 },
    delts: { name: 'Дельты', status: 'medium', score: 42 },
    abs: { name: 'Пресс', status: 'light', score: 18 },
    core: { name: 'Кор', status: 'light', score: 20 },
    glutes: { name: 'Ягодицы', status: 'ready', score: 15 },
    quads: { name: 'Квадрицепс', status: 'ready', score: 18 },
    hamstrings: { name: 'Бицепс бедра', status: 'ready', score: 17 },
    calves: { name: 'Икры', status: 'light', score: 21 },
  },
  elena: {
    lats: { name: 'Широчайшие', status: 'light', score: 24 },
    back: { name: 'Спина', status: 'light', score: 28 },
    upper_back: { name: 'Верх спины', status: 'light', score: 26 },
    biceps: { name: 'Бицепс', status: 'ready', score: 16 },
    chest: { name: 'Грудь', status: 'ready', score: 18 },
    triceps: { name: 'Трицепс', status: 'ready', score: 19 },
    shoulders: { name: 'Плечи', status: 'light', score: 24 },
    delts: { name: 'Дельты', status: 'light', score: 25 },
    abs: { name: 'Пресс', status: 'ready', score: 14 },
    core: { name: 'Кор', status: 'ready', score: 12 },
    glutes: { name: 'Ягодицы', status: 'medium', score: 36 },
    quads: { name: 'Квадрицепс', status: 'medium', score: 42 },
    hamstrings: { name: 'Бицепс бедра', status: 'medium', score: 40 },
    calves: { name: 'Икры', status: 'light', score: 20 },
  },
  guest: {
    chest: { name: 'Грудь', status: 'no_data', score: 0 },
    triceps: { name: 'Трицепс', status: 'no_data', score: 0 },
    back: { name: 'Спина', status: 'no_data', score: 0 },
    biceps: { name: 'Бицепс', status: 'no_data', score: 0 },
    shoulders: { name: 'Плечи', status: 'no_data', score: 0 },
    core: { name: 'Кор', status: 'no_data', score: 0 },
    glutes: { name: 'Ягодицы', status: 'no_data', score: 0 },
    quads: { name: 'Квадрицепс', status: 'no_data', score: 0 },
  },
}

const entryMap = new Map(generatedExerciseEntries.map((entry) => [entry.slug, entry]))

function titleCase(value: string) {
  return value
    .replace(/_/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ')
}

function translateMuscle(key: string) {
  return muscleTranslations[key] ?? titleCase(key)
}

function translateEquipment(value: string) {
  return equipmentTranslations[value] ?? value
}

function translateGrip(value: string) {
  return gripTranslations[value] ?? value
}

function hashString(value: string) {
  let hash = 0

  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index)
    hash |= 0
  }

  return Math.abs(hash)
}

function getPreferences(preferences?: Partial<PreferenceState>): PreferenceState {
  return {
    favorites: preferences?.favorites ?? defaultPreferences.favorites,
    blacklist: preferences?.blacklist ?? defaultPreferences.blacklist,
  }
}

function getMuscleCard(userId: KnownUserId, key: string): MuscleCard {
  const profile = baseMuscleProfiles[userId] ?? baseMuscleProfiles.alexey
  return profile[key] ?? { name: translateMuscle(key), status: 'light', score: 22 }
}

function getReadinessCards(userId: KnownUserId, muscles: string[]): MuscleCard[] {
  return muscles.map((muscle) => getMuscleCard(userId, muscle))
}

function getWorstMuscleStatus(cards: MuscleCard[]): MuscleStatus {
  return cards.reduce<MuscleStatus>((worst, card) => {
    return statusSeverity[card.status] > statusSeverity[worst] ? card.status : worst
  }, 'ready')
}

function getCompatibilityTone(entry: GeneratedEntry, userId: KnownUserId, preferences: PreferenceState): ExerciseSummary['compatibilityTone'] {
  if (preferences.blacklist.includes(entry.slug)) {
    return 'blocked'
  }

  const cards = getReadinessCards(userId, entry.muscles)
  const worstStatus = getWorstMuscleStatus(cards)

  if (stage2FeaturedSlugs.quickStart.some((slug) => slug === entry.slug)) {
    return 'recommended'
  }

  if (worstStatus === 'critical' || worstStatus === 'high') {
    return 'caution'
  }

  return 'okay'
}

function buildBadges(entry: GeneratedEntry, preferences: PreferenceState, tone: ExerciseSummary['compatibilityTone']) {
  const badges: string[] = []

  if (preferences.favorites.includes(entry.slug)) {
    badges.push('Избранное')
  }

  if (preferences.blacklist.includes(entry.slug)) {
    badges.push('В чёрном списке')
  }

  if (tone === 'recommended') {
    badges.push('Рекомендуется')
  }

  return badges
}

function getAvailableVideos(entry: GeneratedEntry) {
  if (!mediaSupportedSlugs.has(entry.slug)) {
    return []
  }

  return entry.videos
}

function getPreviewVideoUrl(entry: GeneratedEntry) {
  const videos = getAvailableVideos(entry)
  return videos.find((video) => video.gender === 'male' && video.view === 'side')?.url ?? videos[0]?.url
}

function buildSummary(entry: GeneratedEntry, userId: KnownUserId, preferences?: Partial<PreferenceState>): ExerciseSummary {
  const resolvedPreferences = getPreferences(preferences)
  const readinessCards = getReadinessCards(userId, entry.muscles)
  const readinessStatus = getWorstMuscleStatus(readinessCards)
  const compatibilityTone = getCompatibilityTone(entry, userId, resolvedPreferences)

  return {
    slug: entry.slug,
    name: entry.nameRu,
    secondaryName: entry.name,
    equipment: translateEquipment(entry.equipment),
    difficulty: entry.difficulty,
    force: entry.force,
    grips: translateGrip(entry.grips),
    mechanic: entry.mechanic,
    muscles: entry.muscles.map(translateMuscle),
    favorite: resolvedPreferences.favorites.includes(entry.slug),
    blacklisted: resolvedPreferences.blacklist.includes(entry.slug),
    recommended: compatibilityTone === 'recommended',
    compatibilityTone,
    readinessStatus,
    difficultyLabel: difficultyLabels[entry.difficulty],
    imageUrl: undefined,
    previewVideoUrl: getPreviewVideoUrl(entry),
    badges: buildBadges(entry, resolvedPreferences, compatibilityTone),
  }
}

function buildDescription(entry: GeneratedEntry) {
  const muscles = entry.muscles.slice(0, 2).map(translateMuscle).join(' и ').toLowerCase()
  return `${entry.nameRu} — упражнение для группы ${muscles || 'основных мышц'}, которое выполняется с оборудованием «${translateEquipment(entry.equipment)}». В mock-сценарии экран показывает технику, совместимость и рекомендуемую нагрузку на сегодня.`
}

function buildCompatibility(entry: GeneratedEntry, userId: KnownUserId, preferences?: Partial<PreferenceState>): ExerciseCompatibility {
  const resolvedPreferences = getPreferences(preferences)
  const cards = getReadinessCards(userId, entry.muscles)
  const tone = getCompatibilityTone(entry, userId, resolvedPreferences)

  switch (tone) {
    case 'blocked':
      return {
        tone,
        title: 'Упражнение находится в чёрном списке',
        description: 'Форма показывает блокирующее предупреждение: упражнение сохранено в нежелательных для текущего пользователя.',
        affectedMuscles: cards,
      }
    case 'caution':
      return {
        tone,
        title: 'Совместимость сегодня: осторожно',
        description: 'Некоторые целевые мышцы уже утомлены. Рекомендуется снизить рабочий вес или выбрать альтернативу.',
        affectedMuscles: cards,
      }
    case 'recommended':
      return {
        tone,
        title: 'Совместимость: хорошо подходит сегодня',
        description: 'Выбранное упражнение совпадает с целью дня и доступным оборудованием, а профиль усталости не мешает старту.',
        affectedMuscles: cards,
      }
    case 'okay':
    default:
      return {
        tone: 'okay',
        title: 'Совместимость: можно выполнять',
        description: 'Явных ограничений не найдено. Упражнение можно добавить в тренировку и скорректировать нагрузку при необходимости.',
        affectedMuscles: cards,
      }
  }
}

function buildLoadSettings(entry: GeneratedEntry): ExerciseDetails['loadSettings'] {
  const hash = hashString(entry.slug)
  const baseWeight = entry.equipment === 'Barbell' ? 40 : entry.equipment === 'Machine' ? 45 : entry.equipment === 'Cable' ? 32 : 0
  const weight = baseWeight + (hash % 4) * 2.5
  const minWeight = Math.max(0, weight - 10)
  const maxWeight = weight + 5

  const calibration: ExerciseDetails['loadSettings']['calibration'] = entry.equipment === 'Machine' ? 'required' : 'recommended'

  return {
    weight,
    sets: 3 + (hash % 2),
    reps: 8 + (hash % 5),
    restSeconds: 60 + (hash % 3) * 15,
    mode: entry.force === 'Push' || entry.force === 'Pull' ? 'Обычный вес' : 'Контроль техники',
    tempo: entry.mechanic === 'Mobility' ? 'Плавный' : 'Обычный',
    recommendation: entry.difficulty === 'Advanced' ? 'Оставить рабочий вес и контролировать амплитуду' : 'Можно добавить 2.5 кг при хорошем самочувствии',
    safeRange: [minWeight, maxWeight] as [number, number],
    calibration,
  }
}

function buildHistory(entry: GeneratedEntry) {
  const hash = hashString(entry.slug)
  const load = buildLoadSettings(entry)
  const dates = ['23.05.2025', '20.05.2025', '17.05.2025', '14.05.2025', '11.05.2025', '08.05.2025']

  return dates.map((date, index) => {
    const offset = (dates.length - index - 1) * 2.5
    const currentWeight = Math.max(0, load.weight - offset)

    return {
      date,
      weight: `${currentWeight} кг`,
      reps: `${load.reps} × ${load.sets}`,
      sets: load.sets,
      volume: `${Math.round(currentWeight * load.reps * load.sets)} кг`,
      rpe: 6 + ((hash + index) % 3),
      note: index === 0 ? 'Чувствовал себя уверенно' : index === 1 ? 'Хороший контроль' : 'Плановый прогресс',
    }
  })
}

function buildProgress(entry: GeneratedEntry) {
  const load = buildLoadSettings(entry)
  return ['26 апр', '3 мая', '9 мая', '16 мая', 'Сегодня'].map((label, index) => ({
    label,
    value: Number((load.weight - 7.5 + index * 2.5).toFixed(1)),
    caption: index === 4 ? `${load.weight}-${load.weight + 5} кг` : undefined,
  }))
}

function buildSimilar(entry: GeneratedEntry, limit = 4) {
  return generatedExerciseEntries
    .filter((candidate) => candidate.slug !== entry.slug)
    .map((candidate) => ({
      entry: candidate,
      score: candidate.muscles.filter((muscle) => entry.muscles.includes(muscle)).length,
    }))
    .filter((candidate) => candidate.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, limit)
    .map(({ entry: candidate }) => ({
      slug: candidate.slug,
      name: candidate.nameRu,
      secondaryName: candidate.name,
      muscles: candidate.muscles.map(translateMuscle),
      equipment: translateEquipment(candidate.equipment),
    }))
}

function getEntry(slug: string) {
  return entryMap.get(slug) ?? entryMap.get('barbell-floor-press') ?? generatedExerciseEntries[0]
}

export function getExerciseDetails(slug: string, userId: KnownUserId = 'alexey', preferences?: Partial<PreferenceState>): ExerciseDetails {
  const entry = getEntry(slug)
  const summary = buildSummary(entry, userId, preferences)
  const compatibility = buildCompatibility(entry, userId, preferences)
  const loadSettings = buildLoadSettings(entry)
  const availableVideos = getAvailableVideos(entry)
  const shortSteps = entry.steps.slice(0, 3)
  const primaryMuscles = entry.muscles.slice(0, 2).map(translateMuscle)
  const secondaryMuscles = entry.muscles.slice(2, 4).map(translateMuscle)

  return {
    ...summary,
    description: buildDescription(entry),
    shortSteps,
    guide: {
      setup: entry.guide.setup,
      howToPerform: entry.guide.howToPerform,
      technique: entry.guide.technique,
      thingsToAvoid: entry.guide.thingsToAvoid,
      keyTips: entry.guide.technique.slice(0, 5),
    },
    videos: availableVideos.map((video) => ({
      url: video.url,
      label: `${video.gender === 'male' ? 'Мужчина' : 'Женщина'} · ${video.view === 'side' ? 'Сбоку' : 'Спереди'}`,
      view: video.view,
      gender: video.gender,
    })),
    primaryMuscles,
    secondaryMuscles,
    stabilizers: ['Кор', 'Плечевой пояс'],
    muscleRoleText: `${summary.name} нагружает ${primaryMuscles.join(' и ').toLowerCase()} и использует ${secondaryMuscles.join(', ').toLowerCase() || 'стабилизаторы корпуса'} как вспомогательную группу.`,
    compatibility,
    loadSettings,
    history: buildHistory(entry),
    loadProgress: buildProgress(entry),
    similar: buildSimilar(entry),
    equipmentAlternatives: [`${translateEquipment(entry.equipment)} → ${translateEquipment('Machine')}`, `${translateEquipment(entry.equipment)} → ${translateEquipment('Bodyweight')}`],
    whenToChooseAlternative: ['Нет подходящего оборудования', 'Нужно снизить нагрузку на суставы', 'Пользователь хочет изменить акцент по мышцам'],
  }
}

function matchesSearch(entry: GeneratedEntry, search: string) {
  if (!search) {
    return true
  }

  const haystack = [
    entry.slug,
    entry.name,
    entry.nameRu,
    entry.equipment,
    entry.difficulty,
    entry.force,
    entry.grips,
    entry.mechanic,
    ...entry.muscles,
    ...entry.steps,
    ...entry.guide.setup,
    ...entry.guide.howToPerform,
    ...entry.guide.technique,
    ...entry.guide.thingsToAvoid,
  ]
    .join(' ')
    .toLowerCase()

  return haystack.includes(search.toLowerCase())
}

function includesAny<T>(values: T[], expected?: T[]) {
  return !expected || expected.length === 0 || expected.some((item) => values.includes(item))
}

function includesOne<T>(value: T, expected?: T[]) {
  return !expected || expected.length === 0 || expected.includes(value)
}

export function getExerciseCatalog(userId: KnownUserId = 'alexey', query: CatalogQuery = {}, preferences?: Partial<PreferenceState>): ExerciseCatalogResponse {
  const filtered = generatedExerciseEntries.filter((entry) => {
    return (
      matchesSearch(entry, query.search ?? '') &&
      includesAny(entry.muscles.map(translateMuscle), query.muscles) &&
      includesOne(translateEquipment(entry.equipment), query.equipment) &&
      includesOne(entry.difficulty, query.difficulty) &&
      includesOne(entry.force, query.force) &&
      includesOne(entry.mechanic, query.mechanic) &&
      includesOne(translateGrip(entry.grips), query.grips)
    )
  })

  return {
    items: filtered.map((entry) => buildSummary(entry, userId, preferences)),
    total: filtered.length,
    availableFilters: {
      muscles: Array.from(new Set(generatedExerciseEntries.flatMap((entry) => entry.muscles.map(translateMuscle)))).sort((left, right) => left.localeCompare(right)),
      equipment: Array.from(new Set(generatedExerciseEntries.map((entry) => translateEquipment(entry.equipment)))).sort((left, right) => left.localeCompare(right)),
      difficulty: ['Beginner', 'Intermediate', 'Advanced'],
      force: ['Push', 'Pull', 'Static', 'Stretch'],
      mechanic: ['Compound', 'Isolation', 'Mobility'],
      grips: Array.from(new Set(generatedExerciseEntries.map((entry) => translateGrip(entry.grips)))).sort((left, right) => left.localeCompare(right)),
    },
  }
}

function toQuickStartListItem(slug: string, reason: string, userId: KnownUserId, preferences?: Partial<PreferenceState>): QuickStartExerciseListItem {
  const summary = buildSummary(getEntry(slug), userId, preferences)
  const load = buildLoadSettings(getEntry(slug))

  return {
    ...summary,
    reason,
    lastResult: `${load.weight} кг × ${load.reps} × ${load.sets}`,
    lastPerformed: `${3 + (hashString(slug) % 4)} дней назад`,
  }
}

function buildSelectedExercisePanel(slug: string, userId: KnownUserId, preferences?: Partial<PreferenceState>) {
  const details = getExerciseDetails(slug, userId, preferences)
  return {
    exercise: details,
    readiness: details.compatibility.affectedMuscles.slice(0, 3).map((muscle) => {
      const tone: 'caution' | 'recommended' | 'okay' = muscle.status === 'high' || muscle.status === 'critical' ? 'caution' : muscle.status === 'ready' ? 'recommended' : 'okay'

      return {
        label: muscle.name,
        tone,
        description: muscle.status === 'ready' ? 'Готова' : muscle.status === 'light' ? 'Лёгкая усталость' : muscle.status === 'medium' ? 'Нужен контроль' : 'Снизьте нагрузку',
      }
    }),
    lastResult: `${details.loadSettings.weight} кг × ${details.loadSettings.reps} × ${details.loadSettings.sets}`,
    formaRecommendation: details.loadSettings.recommendation,
    settings: details.loadSettings,
    warnings:
      details.compatibility.tone === 'blocked'
        ? [{ tone: 'blocked' as const, title: 'Упражнение заблокировано', description: details.compatibility.description }]
        : details.compatibility.tone === 'caution'
          ? [{ tone: 'warning' as const, title: 'Нужна осторожность', description: details.compatibility.description }]
          : [],
  }
}

export function getQuickStartData(userId: KnownUserId = 'alexey', selectedExerciseSlug?: string | null, preferences?: Partial<PreferenceState>): QuickStartData {
  const resolvedPreferences = getPreferences(preferences)
  const chosenSlug = selectedExerciseSlug ?? stage2FeaturedSlugs.quickStart[0]

  return {
    recommendation: {
      title: userId === 'guest' ? 'Гостевой режим: быстрый выбор' : 'Сегодня лучше: спина + бицепс',
      description:
        userId === 'guest'
          ? 'История пользователя не используется. Можно выбрать любое упражнение из каталога и сразу перейти к настройке.'
          : 'Грудь и трицепс ещё восстанавливаются, поэтому система рекомендует тяговые движения и умеренную работу на бицепс.',
      cta: 'Подробнее',
    },
    machine: machineScenarios.ready,
    filterGroups: {
      audience: ['Рекомендовано', 'Последние', 'Избранные'],
      muscleFocus: ['Спина', 'Бицепс', 'Грудь', 'Ноги', 'Плечи', 'Кор'],
      equipment: ['Смит', 'Кроссовер', 'Без инвентаря'],
    },
    recommended: [
      toQuickStartListItem(stage2FeaturedSlugs.quickStart[0], 'Причина: спина готова к нагрузке', userId, resolvedPreferences),
      toQuickStartListItem(stage2FeaturedSlugs.today[1], 'Причина: подходит под цель «сила + форма»', userId, resolvedPreferences),
      toQuickStartListItem(stage2FeaturedSlugs.today[2], 'Причина: лёгкая усталость, можно выполнить', userId, resolvedPreferences),
    ],
    recent: stage2FeaturedSlugs.recent.map((slug) => toQuickStartListItem(slug, 'Последняя удачная сессия', userId, resolvedPreferences)),
    favorites: resolvedPreferences.favorites.slice(0, 4).map((slug) => toQuickStartListItem(slug, 'В избранном', userId, resolvedPreferences)),
    selectedExerciseSlug: chosenSlug,
    selectedExercise: buildSelectedExercisePanel(chosenSlug, userId, resolvedPreferences),
  }
}

function toWorkoutPanel(slug: string, userId: KnownUserId, preferences?: Partial<PreferenceState>): WorkoutExercisePanel {
  const details = getExerciseDetails(slug, userId, preferences)
  return {
    id: slug,
    slug,
    name: details.name,
    muscles: details.muscles.slice(0, 2).join(', '),
    lastResult: `${details.loadSettings.weight} кг × ${details.loadSettings.reps} × ${details.loadSettings.sets}`,
    formaRecommendation: details.loadSettings.recommendation,
    readiness: details.compatibility.affectedMuscles.slice(0, 3).map((muscle) => ({
      label: muscle.name,
      value: muscle.status === 'ready' ? 'Готова' : muscle.status === 'light' ? 'Лёгкая усталость' : muscle.status === 'medium' ? 'Средняя усталость' : 'Нужен контроль',
      tone: muscle.status === 'ready' ? 'recommended' : muscle.status === 'medium' || muscle.status === 'high' ? 'caution' : 'okay',
    })),
    settings: details.loadSettings,
    alerts: details.compatibility.tone === 'caution' ? [details.compatibility.description] : [],
  }
}

export function getTodayWorkoutData(
  userId: KnownUserId = 'alexey',
  scenario: TodayScenario = 'planned',
  selectedExerciseId: string = stage2FeaturedSlugs.today[0],
  preferences?: Partial<PreferenceState>,
): TodayWorkoutData {
  const rows: TodayWorkoutData['exerciseRows'] = stage2FeaturedSlugs.today.map((slug, index) => {
    const details = getExerciseDetails(slug, userId, preferences)
    const isSelected = slug === selectedExerciseId
    const baseStatus: TodayWorkoutData['exerciseRows'][number]['status'] = index === 0 ? 'up-next' : index < 3 ? 'planned' : 'warning'

    return {
      id: slug,
      slug,
      name: details.name,
      muscles: details.muscles.slice(0, 2).join(', '),
      imageUrl: undefined,
      load: `${details.loadSettings.weight} кг • ${details.loadSettings.sets}×${details.loadSettings.reps}`,
      rest: `${details.loadSettings.restSeconds} сек`,
      status:
        scenario === 'completed'
          ? index < 4
            ? 'completed'
            : 'planned'
          : scenario === 'in-progress'
            ? isSelected
              ? 'in-progress'
              : index === 0
                ? 'completed'
                : baseStatus
            : scenario === 'recovery'
              ? index === 0
                ? 'warning'
                : baseStatus
              : scenario === 'blocked'
                ? 'warning'
                : baseStatus,
      calibration: details.loadSettings.calibration === 'required' ? 'Потребуется перед упражнением' : 'Сохранена',
      note: index === 0 ? 'Следующее' : undefined,
    }
  })

  const warnings =
    scenario === 'blocked'
      ? [{ tone: 'blocked' as const, title: 'Тренажёр не готов к старту', description: 'Один из приводов недоступен. Запуск упражнений временно заблокирован.' }]
      : scenario === 'recovery'
        ? [{ tone: 'warning' as const, title: 'Высокая усталость груди', description: 'Сегодня лучше держать объём под контролем и при необходимости заменить жимовые движения.' }]
        : []

  return {
    title: 'Спина + бицепс',
    subtitle: 'План на сегодня с учётом целей, усталости мышц и ваших последних результатов.',
    readinessPercent: scenario === 'recovery' ? 42 : 78,
    machine: scenario === 'blocked' ? machineScenarios.blocked : machineScenarios.ready,
    startState: scenario,
    summary: {
      exercises: 5,
      sets: 18,
      duration: '45 мин',
    },
    mainAction:
      scenario === 'in-progress'
        ? 'Продолжить тренировку'
        : scenario === 'completed'
          ? 'Открыть результат'
          : scenario === 'blocked'
            ? 'Старт заблокирован'
            : 'Начать тренировку',
    exerciseRows: rows,
    selectedExerciseId,
    selectedExercise: toWorkoutPanel(selectedExerciseId, userId, preferences),
    warnings,
    muscles: Object.values(baseMuscleProfiles[userId] ?? baseMuscleProfiles.alexey),
    progress: {
      completedExercises: scenario === 'completed' ? 5 : scenario === 'in-progress' ? 2 : 0,
      totalExercises: 5,
      completedSets: scenario === 'completed' ? 18 : scenario === 'in-progress' ? 7 : 0,
      totalSets: 18,
      minutesLeft: scenario === 'completed' ? 0 : scenario === 'in-progress' ? 27 : 45,
      percent: scenario === 'completed' ? 100 : scenario === 'in-progress' ? 39 : 0,
      nextStep: scenario === 'completed' ? 'Тренировка завершена' : 'Сгибание рук',
    },
    quickActions: ['Изменить тренировку', 'Заменить упражнение', 'Сохранить как программу', 'Перенести тренировку'],
  }
}

const programTemplates = [
  {
    id: 'back-biceps',
    name: 'Спина + бицепс',
    subtitle: 'Силовая тренировка',
    difficulty: 'medium' as const,
    exerciseSlugs: stage2FeaturedSlugs.today,
    focusTags: ['Спина', 'Бицепс', 'Предплечья'],
    recommendedToday: true,
    compatibility: {
      tone: 'great' as const,
      title: 'Совместимость: хорошо подходит сегодня',
      description: 'Спина готова к нагрузке, бицепс имеет лёгкую усталость, грудь и трицепс почти не нагружаются.',
    },
  },
  {
    id: 'leg-day',
    name: 'День ног',
    subtitle: 'Силовая тренировка',
    difficulty: 'medium' as const,
    exerciseSlugs: ['barbell-back-squat', 'forward-lunges', 'barbell-front-squat-olympic'],
    focusTags: ['Бёдра', 'Ягодицы', 'Икры'],
    recommendedToday: false,
    compatibility: {
      tone: 'caution' as const,
      title: 'Совместимость: осторожно',
      description: 'Ноги ещё восстанавливаются после прошлой сессии, поэтому сегодня лучше снизить объём.',
    },
  },
  {
    id: 'fullbody-45',
    name: 'Фуллбоди 45',
    subtitle: 'Поддержание формы',
    difficulty: 'easy' as const,
    exerciseSlugs: ['barbell-floor-press', 'machine-pulldown', 'forward-lunges', 'forearm-plank'],
    focusTags: ['Фуллбоди'],
    recommendedToday: false,
    compatibility: {
      tone: 'okay' as const,
      title: 'Совместимость: можно адаптировать',
      description: 'Программу можно использовать после небольшой настройки нагрузки под текущую готовность.',
    },
  },
  {
    id: 'recovery-mobility',
    name: 'Восстановительная',
    subtitle: 'Мобилизация и лёгкая работа',
    difficulty: 'novice' as const,
    exerciseSlugs: ['forearm-plank', 'forward-lunges'],
    focusTags: ['Мобилность', 'Растяжка'],
    recommendedToday: false,
    compatibility: {
      tone: 'great' as const,
      title: 'Совместимость: идеально для восстановления',
      description: 'Программа подходит для дня с повышенной усталостью и не требует тяжёлого оборудования.',
    },
  },
]

function toProgramSummary(template: (typeof programTemplates)[number]): ProgramSummary {
  return {
    id: template.id,
    name: template.name,
    subtitle: template.subtitle,
    exerciseCount: template.exerciseSlugs.length,
    setCount: template.exerciseSlugs.length * 3 + 3,
    durationMinutes: 20 + template.exerciseSlugs.length * 5,
    difficulty: template.difficulty,
    focusTags: template.focusTags,
    recommendedToday: template.recommendedToday,
    imageUrl: undefined,
  }
}

function toProgramDetails(programId = 'back-biceps'): ProgramDetails {
  const template = programTemplates.find((item) => item.id === programId) ?? programTemplates[0]
  const summary = toProgramSummary(template)
  return {
    ...summary,
    compatibility: template.compatibility,
    equipmentCoverage: 'Доступно 100%',
    blacklistIssues: 0,
    exerciseLines: template.exerciseSlugs.map((slug, index) => {
      const details = getExerciseDetails(slug)
      return {
        order: index + 1,
        name: details.name,
        load: `${details.loadSettings.weight} кг × ${details.loadSettings.sets}×${details.loadSettings.reps}`,
        rest: `${details.loadSettings.restSeconds} сек`,
      }
    }),
    actions: {
      primary: 'Начать сегодня',
      secondary: 'Адаптировать под меня',
      save: 'Сохранить в мои программы',
      calendar: 'Назначить в календарь',
      builder: 'Открыть в конструкторе',
    },
  }
}

export function getProgramLibraryData(selectedProgramId = 'back-biceps'): ProgramLibraryData {
  const programs = programTemplates.map(toProgramSummary)
  return {
    searchPlaceholder: 'Найти программу...',
    categoryFilters: ['Все', 'Для меня', 'Силовые', 'Фуллбоди', 'Восстановление'],
    durationFilters: ['30 минут', '45 минут'],
    levelFilters: ['Новичок', 'Средний'],
    equipmentFilters: ['Машина Смита', 'Кроссовер'],
    recommended: programs.slice(0, 4),
    allPrograms: programs,
    selectedProgram: toProgramDetails(selectedProgramId),
  }
}

const monthDays: WorkoutCalendarData['days'] = [
  { id: '2026-04-27', dateLabel: '27', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-04-28', dateLabel: '28', title: 'Спина', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-04-29', dateLabel: '29', title: 'Ноги', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-04-30', dateLabel: '30', title: 'Грудь', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-01', dateLabel: '1', title: 'Кор', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-02', dateLabel: '2', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-03', dateLabel: '3', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-04', dateLabel: '4', title: 'Спина', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-05-05', dateLabel: '5', title: 'Ноги', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-05-06', dateLabel: '6', title: 'Грудь', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-05-07', dateLabel: '7', title: 'Кор', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-05-08', dateLabel: '8', title: 'Плечи', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-09', dateLabel: '9', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-10', dateLabel: '10', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-11', dateLabel: '11', title: 'Спина', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-12', dateLabel: '12', title: 'Плечи', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-13', dateLabel: '13', title: 'Спина', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-05-14', dateLabel: '14', title: 'Спина + бицепс', badges: ['Сегодня'], status: 'today', selected: true, readinessPercent: 78, duration: '45 мин', exerciseCount: 5 },
  { id: '2026-05-15', dateLabel: '15', title: 'Ноги', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-16', dateLabel: '16', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-17', dateLabel: '17', title: 'Грудь', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-18', dateLabel: '18', title: 'Спина', badges: ['Перегруз'], status: 'overload' },
  { id: '2026-05-19', dateLabel: '19', title: 'Плечи', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-20', dateLabel: '20', title: 'Фуллбоди', badges: ['Выполнено'], status: 'completed' },
  { id: '2026-05-21', dateLabel: '21', title: 'Кор', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-22', dateLabel: '22', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-23', dateLabel: '23', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-24', dateLabel: '24', title: 'Кор', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-25', dateLabel: '25', title: 'Ноги', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-26', dateLabel: '26', title: 'Спина', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-27', dateLabel: '27', title: 'Грудь', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-28', dateLabel: '28', title: 'Плечи', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-29', dateLabel: '29', title: 'Фуллбоди', badges: ['Запланировано'], status: 'planned' },
  { id: '2026-05-30', dateLabel: '30', title: 'Отдых', badges: [], status: 'rest' },
  { id: '2026-05-31', dateLabel: '31', title: 'Отдых', badges: [], status: 'rest' },
]

const weekDays: WorkoutCalendarData['days'] = [
  { id: '2026-05-13', dateLabel: 'Пн 13', title: 'Спина + бицепс', badges: ['Выполнено'], status: 'completed', duration: '45 мин', exerciseCount: 5 },
  { id: '2026-05-14', dateLabel: 'Вт 14', title: 'Спина + бицепс', badges: ['Сегодня'], status: 'today', readinessPercent: 78, duration: '45 мин', exerciseCount: 5, selected: true },
  { id: '2026-05-15', dateLabel: 'Ср 15', title: 'День отдыха', badges: ['Запланировано'], status: 'rest' },
  { id: '2026-05-16', dateLabel: 'Чт 16', title: 'Нет тренировки', badges: ['Свободный день'], status: 'empty' },
  { id: '2026-05-17', dateLabel: 'Пт 17', title: 'Грудь + плечи', badges: ['Запланировано'], status: 'planned', duration: '40 мин', exerciseCount: 4 },
  { id: '2026-05-18', dateLabel: 'Сб 18', title: 'Ноги + кор', badges: ['Запланировано'], status: 'planned', duration: '50 мин', exerciseCount: 5 },
  { id: '2026-05-19', dateLabel: 'Вс 19', title: 'Отдых', badges: ['Восстановление'], status: 'rest' },
]

export function getWorkoutCalendarData(mode: 'week' | 'month' = 'month', selectedDayId = '2026-05-14'): WorkoutCalendarData {
  const days = (mode === 'week' ? weekDays : monthDays).map((day) => ({ ...day, selected: day.id === selectedDayId }))
  return {
    mode,
    title: mode === 'week' ? 'Неделя 13–19 мая' : 'Май 2026',
    legend: ['Выполнено', 'Запланировано', 'Пропущено', 'Отдых'],
    days,
    selectedDayId,
    selectedDay: {
      dateLabel: '14 мая',
      title: 'Спина + бицепс',
      subtitle: 'Сегодня',
      exerciseCount: 5,
      setCount: 18,
      duration: '45 минут',
      targetMuscles: 'спина, бицепс, предплечья',
      statusText: 'запланирована',
      readinessPercent: 78,
      recommendation: 'Грудь лучше не нагружать до пятницы — так вы избежите избыточной нагрузки и улучшите прогресс.',
    },
    quickActions: ['Сгенерировать месяц', 'Добавить тренировку', 'Скопировать прошлый месяц'],
    summary: [
      { label: 'запланировано', value: '22' },
      { label: 'выполнено', value: '16' },
      { label: 'минут', value: '780' },
      { label: 'выполнение', value: '72%' },
    ],
    muscleBalance: [
      { label: 'Спина', value: 'Высокая', tone: 'high' },
      { label: 'Грудь', value: 'Средняя', tone: 'medium' },
      { label: 'Ноги', value: 'Высокая', tone: 'high' },
      { label: 'Кор', value: 'Средняя', tone: 'medium' },
    ],
  }
}

export function getWorkoutBuilderData(selectedExerciseId = 'group-pullups-1'): WorkoutBuilderData {
  return {
    title: 'Конструктор тренировок',
    subtitle: 'Соберите тренировку из упражнений, настройте нагрузку и сохраните программу.',
    info: {
      name: 'День спины',
      type: 'Силовая',
      duration: '≈ 45 минут',
      difficulty: 'Средняя',
      description: 'Тренировка на спину и бицепс с умеренным объёмом.',
    },
    groups: [
      {
        id: 'group-a',
        kind: 'alternating',
        title: 'Подтягивания + Присед',
        rounds: '3 круга • 8–12 мин',
        betweenExercisesRest: '30 сек',
        betweenRoundsRest: '90 сек',
        items: [
          { id: 'group-pullups-1', slug: 'machine-pulldown', name: 'Тяга сверху', muscleGroup: 'Спина', sets: '3×10', rest: '30 сек', load: '45 кг' },
          { id: 'group-squat-1', slug: 'barbell-heels-up-back-squat', name: 'Присед', muscleGroup: 'Ноги', sets: '3×8', rest: '30 сек', load: '60 кг' },
        ],
      },
      {
        id: 'group-b',
        kind: 'single',
        title: 'Основной блок',
        items: [
          { id: 'row-1', slug: 'machine-seated-cable-row', name: 'Тяга горизонтального блока', muscleGroup: 'Спина', sets: '3×10', rest: '90 сек', load: '45 кг' },
          { id: 'row-2', slug: 'underhand-pulldown', name: 'Тяга к поясу в тренажёре', muscleGroup: 'Спина', sets: '4×12', rest: '90 сек', load: '40 кг' },
          { id: 'curl-1', slug: 'barbell-curl', name: 'Сгибание рук с гантелями', muscleGroup: 'Бицепс', sets: '3×12', rest: '75 сек', load: '20 кг' },
          { id: 'plank-1', slug: 'forearm-plank', name: 'Планка', muscleGroup: 'Кор', sets: '3×45 сек', rest: '45 сек', load: 'вес тела' },
        ],
      },
    ],
    selectedExerciseId,
    selectedExercise: {
      name: 'Подтягивания',
      subtitle: 'Спина, бицепс',
      setParams: {
        reps: 10,
        weight: 0,
        restSeconds: 30,
      },
      loadMode: 'Обычный вес',
      tempo: 'Обычный',
      note: 'Следить за лопатками, не дёргать корпусом.',
    },
    addSuggestions: [
      { slug: 'machine-pulldown', name: 'Тяга сверху', muscles: 'Спина, бицепс' },
      { slug: 'machine-seated-cable-row', name: 'Тяга к поясу', muscles: 'Спина' },
      { slug: 'underhand-pulldown', name: 'Тяга прямыми руками', muscles: 'Широчайшие' },
      { slug: 'barbell-curl', name: 'Сгибание рук', muscles: 'Бицепс' },
    ],
    summaryCards: [
      { label: 'упражнений', value: '5', hint: 'структура тренировки' },
      { label: 'подходов', value: '18', hint: 'общий объём' },
      { label: 'минут', value: '45', hint: 'оценка длительности' },
      { label: 'кг', value: '5 620', hint: 'общий тоннаж' },
    ],
    warnings: [
      { tone: 'warning', title: 'Длинная тренировка', description: 'Расчётное время больше цели на 10 минут. Можно убрать один вспомогательный блок.' },
      { tone: 'warning', title: 'Короткий отдых', description: 'Для тяжёлых подходов рекомендуется отдых 60–90 секунд.' },
      { tone: 'success', title: 'Упражнения из чёрного списка отсутствуют', description: 'Текущая версия плана безопасна для пользователя.' },
    ],
  }
}