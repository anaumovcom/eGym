import type { FatigueMuscle } from '@/entities/stage4/model/types'

export type BodyMapView = 'front' | 'back'

export const svgIdsByView: Record<BodyMapView, string[]> = {
  front: [
    'abdominals',
    'ankles',
    'biceps',
    'calves',
    'chest',
    'elbow',
    'forearms',
    'front-shoulders',
    'hands',
    'hips',
    'knees',
    'obliques',
    'quads',
    'shoulders',
    'traps',
    'wrist',
  ],
  back: [
    'ankles',
    'calves',
    'elbow',
    'forearms',
    'glutes',
    'hamstrings',
    'hands',
    'knees',
    'lats',
    'lower-spine',
    'lowerback',
    'rear-shoulders',
    'scapula',
    'traps',
    'traps-middle',
    'triceps',
    'upper-spine',
    'wrist',
  ],
}

export const exerciseMuscleToSvgIds: Record<string, string[]> = {
  abdominals: ['abdominals'],
  biceps: ['biceps'],
  calves: ['calves'],
  chest: ['chest'],
  forearms: ['forearms'],
  'front-shoulders': ['front-shoulders'],
  glutes: ['glutes'],
  hamstrings: ['hamstrings'],
  hips: ['hips'],
  lats: ['lats'],
  obliques: ['obliques'],
  quads: ['quads'],
  'rear-shoulders': ['rear-shoulders'],
  traps: ['traps'],
  'traps-middle': ['traps-middle'],
  triceps: ['triceps'],
}

export const fatigueMuscleToSvgIds: Record<string, string[]> = {
  abdominals: ['abdominals'],
  'front-shoulders': ['front-shoulders'],
  lats: ['lats'],
  lowerback: ['lowerback'],
  obliques: ['obliques'],
  'rear-shoulders': ['rear-shoulders'],
  traps: ['traps'],
  'traps-middle': ['traps-middle'],
  chest: ['chest'],
  triceps: ['triceps'],
  'front-delta': ['front-shoulders'],
  abs: ['abdominals'],
  quads: ['quads'],
  back: ['lats', 'traps-middle'],
  'rear-delta': ['rear-shoulders'],
  glutes: ['glutes'],
  hamstrings: ['hamstrings'],
  calves: ['calves'],
}

export function resolveSvgIdsForMuscle(muscleId: string) {
  return fatigueMuscleToSvgIds[muscleId] ?? exerciseMuscleToSvgIds[muscleId] ?? []
}

const bodyMapLabelAliases: Record<string, string[]> = {
  'бицепс': ['biceps'],
  'бицепс бедра': ['hamstrings'],
  'грудь': ['chest'],
  'задняя дельта': ['rear-shoulders'],
  'задние дельты': ['rear-shoulders'],
  'верх спины': ['traps', 'traps-middle'],
  'дельты': ['front-shoulders', 'rear-shoulders'],
  'икры': ['calves'],
  'кор': ['abdominals', 'obliques'],
  'косые': ['obliques'],
  'косые мышцы': ['obliques'],
  'косые мышцы живота': ['obliques'],
  'квадрицепс': ['quads'],
  'квадрицепсы': ['quads'],
  'низ спины': ['lowerback'],
  'ноги': ['quads', 'hamstrings', 'calves', 'glutes'],
  'передняя дельта': ['front-shoulders'],
  'передние дельты': ['front-shoulders'],
  'плечи': ['front-shoulders', 'rear-shoulders', 'traps'],
  'предплечья': ['forearms'],
  'приводящие': ['hips'],
  'пресс': ['abdominals'],
  'сгибатели бедра': ['hips'],
  'средняя трапеция': ['traps-middle'],
  'спина': ['back'],
  'трапеции': ['traps', 'traps-middle'],
  'трицепс': ['triceps'],
  'отводящие': ['hips'],
  'широчайшие': ['lats'],
  'ягодицы': ['glutes'],
}

export function resolveSvgIdsForBodyMapLabel(label: string) {
  const normalizedLabel = label.trim().toLowerCase()
  const muscleIds = bodyMapLabelAliases[normalizedLabel] ?? [normalizedLabel]

  return Array.from(new Set(muscleIds.flatMap((muscleId) => resolveSvgIdsForMuscle(muscleId))))
}

export function muscleIsVisibleOnView(muscleId: string, view: BodyMapView) {
  const visibleIds = new Set(svgIdsByView[view])
  return resolveSvgIdsForMuscle(muscleId).some((svgId) => visibleIds.has(svgId))
}

type PlaceholderMuscleConfig = Pick<FatigueMuscle, 'id' | 'name' | 'shortName' | 'group' | 'area'>

function createFatiguePlaceholder(config: PlaceholderMuscleConfig): FatigueMuscle {
  return {
    ...config,
    score: 0,
    readinessPercent: 0,
    status: 'no_data',
    recoveryHours: 0,
    lastLoadAt: 'Нет данных',
    impact: [],
    recommendation: 'По этой мышце пока нет накопленных данных усталости.',
    recommendedExercises: [],
    avoidExercises: [],
  }
}

const fatiguePlaceholderConfigs: PlaceholderMuscleConfig[] = [
  { id: 'abdominals', name: 'Пресс', shortName: 'Пресс', group: 'front', area: 'middle' },
  { id: 'biceps', name: 'Бицепс', shortName: 'Бицепс', group: 'front', area: 'upper' },
  { id: 'calves', name: 'Икры', shortName: 'Икры', group: 'back', area: 'lower' },
  { id: 'chest', name: 'Грудь', shortName: 'Грудь', group: 'front', area: 'upper' },
  { id: 'forearms', name: 'Предплечья', shortName: 'Предплечья', group: 'front', area: 'upper' },
  { id: 'front-shoulders', name: 'Передние дельты', shortName: 'Передние дельты', group: 'front', area: 'upper' },
  { id: 'glutes', name: 'Ягодицы', shortName: 'Ягодицы', group: 'back', area: 'middle' },
  { id: 'hamstrings', name: 'Бицепс бедра', shortName: 'Бицепс бедра', group: 'back', area: 'lower' },
  { id: 'lats', name: 'Широчайшие', shortName: 'Широчайшие', group: 'back', area: 'upper' },
  { id: 'lowerback', name: 'Низ спины', shortName: 'Низ спины', group: 'back', area: 'middle' },
  { id: 'obliques', name: 'Косые мышцы живота', shortName: 'Косые', group: 'front', area: 'middle' },
  { id: 'quads', name: 'Квадрицепсы', shortName: 'Квадрицепсы', group: 'front', area: 'lower' },
  { id: 'rear-shoulders', name: 'Задние дельты', shortName: 'Задние дельты', group: 'back', area: 'upper' },
  { id: 'traps', name: 'Трапеции', shortName: 'Трапеции', group: 'back', area: 'upper' },
  { id: 'traps-middle', name: 'Средняя трапеция', shortName: 'Средняя трапеция', group: 'back', area: 'upper' },
  { id: 'triceps', name: 'Трицепс', shortName: 'Трицепс', group: 'back', area: 'upper' },
]

const fatiguePlaceholderMuscles: FatigueMuscle[] = fatiguePlaceholderConfigs.map(createFatiguePlaceholder)

export function ensureFatigueMuscleCoverage(muscles: FatigueMuscle[]) {
  const existingIds = new Set(muscles.map((muscle) => muscle.id))
  const coveredSvgIds = new Set(muscles.flatMap((muscle) => resolveSvgIdsForMuscle(muscle.id)))

  const missingPlaceholders = fatiguePlaceholderMuscles.filter((muscle) => {
    if (existingIds.has(muscle.id)) {
      return false
    }

    return resolveSvgIdsForMuscle(muscle.id).some((svgId) => !coveredSvgIds.has(svgId))
  })

  return [...muscles, ...missingPlaceholders]
}