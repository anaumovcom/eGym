import type { FatigueMuscle } from '@/entities/stage4/model/types'
import './fatigue-map-regions.css'

export type BodyMapView = 'front' | 'back'

export const fatigueStatusPriority: Record<FatigueMuscle['status'], number> = {
  no_data: 0, ready: 1, light: 2, medium: 3, high: 4, critical: 5,
}

export const svgIdsByView: Record<BodyMapView, string[]> = {
  front: [
    'adductors', 'hip-flexors', 'side-delts', 'serratus', 'anterior-shin', 'foot',
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
    'neck', 'rotator-cuff',
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

// Region membership mirrors backend LEGACY_MUSCLE_SPLITS; the API owns score weighting.
const legacyTargets: Record<string, string[]> = {
  'front-delta': ['front-shoulders'],
  abs: ['abdominals'],
  back: ['lats', 'traps-middle'],
  'rear-delta': ['rear-shoulders'],
  shoulders: ['front-shoulders', 'rear-shoulders'],
  core: ['abdominals', 'obliques'],
  legs: ['quads', 'hamstrings', 'glutes', 'calves'],
}

// Names supplied instead of IDs by compact maps (including old exercise labels).
const bodyMapLabelAliases: Record<string, string[]> = {
  delts: legacyTargets.shoulders,
  'lower-back': ['lowerback'],
  'upper-back': ['traps', 'traps-middle'],
  adductors: ['adductors'],
  abductors: ['hips'],
  'hip-flexors': ['hip-flexors'],
  'задняя дельта': ['rear-shoulders'],
  'верх спины': ['traps', 'traps-middle'],
  'дельты': legacyTargets.shoulders,
  'кор': legacyTargets.core,
  'косые мышцы': ['obliques'],
  'квадрицепс': ['quads'],
  'ноги': legacyTargets.legs,
  'передняя дельта': ['front-shoulders'],
  'плечи': legacyTargets.shoulders,
  'приводящие': ['adductors'],
  'сгибатели бедра': ['hip-flexors'],
  'спина': legacyTargets.back,
  'отводящие': ['hips'],
}

function normalizeTarget(value: string) {
  return value.trim().toLowerCase().replace(/[\s_-]+/g, '-')
}

export function resolveSvgIdsForMuscle(muscleId: string) {
  return regionsByTarget.get(normalizeTarget(muscleId)) ?? []
}

export const resolveSvgIdsForBodyMapLabel = resolveSvgIdsForMuscle

export function muscleIsVisibleOnView(muscleId: string, view: BodyMapView) {
  const visibleIds = new Set(svgIdsByView[view])
  return resolveSvgIdsForMuscle(muscleId).some((svgId) => visibleIds.has(svgId))
}

export function fatigueRegionKey(id: string) {
  const regions = resolveSvgIdsForMuscle(id)
  return regions.length ? regions.join('/') : id
}

function outranks(muscle: Pick<FatigueMuscle, 'status' | 'score'>, other: Pick<FatigueMuscle, 'status' | 'score'>) {
  return fatigueStatusPriority[muscle.status] > fatigueStatusPriority[other.status]
    || (muscle.status === other.status && muscle.score > other.score)
}

/** Multiple historical IDs may claim the same patch. Status comes from the API,
 * not from a UI score threshold; never let a no-data placeholder mask a load. */
export function fatigueRegionOwners<T extends Pick<FatigueMuscle, 'id' | 'status' | 'score'>>(muscles: readonly T[], view?: BodyMapView) {
  const owners = new Map<string, T>()
  for (const muscle of muscles) {
    for (const id of resolveSvgIdsForMuscle(muscle.id)) {
      if (view && !svgIdsByView[view].includes(id)) continue
      const previous = owners.get(id)
      if (!previous || outranks(muscle, previous)) owners.set(id, muscle)
    }
  }
  return owners
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
  { id: 'adductors', name: 'Приводящие мышцы бедра', shortName: 'Приводящие', group: 'front', area: 'lower' },
  { id: 'hip-flexors', name: 'Сгибатели бедра', shortName: 'Сгибатели бедра', group: 'front', area: 'lower' },
  { id: 'side-delts', name: 'Средние дельты', shortName: 'Средние дельты', group: 'front', area: 'upper' },
  { id: 'serratus', name: 'Передняя зубчатая мышца', shortName: 'Передняя зубчатая', group: 'front', area: 'middle' },
  { id: 'anterior-shin', name: 'Передняя группа голени', shortName: 'Передняя группа голени', group: 'front', area: 'lower' },
  { id: 'foot', name: 'Мышцы стопы', shortName: 'Мышцы стопы', group: 'front', area: 'lower' },
  { id: 'neck', name: 'Мышцы шеи', shortName: 'Шея', group: 'back', area: 'upper' },
  { id: 'rotator-cuff', name: 'Ротаторная манжета', shortName: 'Ротаторная манжета', group: 'back', area: 'upper' },
  { id: 'biceps', name: 'Бицепс', shortName: 'Бицепс', group: 'front', area: 'upper' },
  { id: 'calves', name: 'Икры', shortName: 'Икры', group: 'back', area: 'lower' },
  { id: 'chest', name: 'Грудь', shortName: 'Грудь', group: 'front', area: 'upper' },
  { id: 'forearms', name: 'Предплечья', shortName: 'Предплечья', group: 'front', area: 'upper' },
  { id: 'front-shoulders', name: 'Передние дельты', shortName: 'Передние дельты', group: 'front', area: 'upper' },
  { id: 'glutes', name: 'Ягодицы', shortName: 'Ягодицы', group: 'back', area: 'middle' },
  { id: 'hamstrings', name: 'Бицепс бедра', shortName: 'Бицепс бедра', group: 'back', area: 'lower' },
  { id: 'hips', name: 'Тазобедренные мышцы', shortName: 'Тазобедренные мышцы', group: 'front', area: 'lower' },
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

// Individual catalog IDs are also SVG IDs. Both renderers must resolve translated
// names to precisely the same region (in particular traps is not traps-middle).
export const exerciseMuscleToSvgIds: Record<string, string[]> = Object.fromEntries(
  fatiguePlaceholderConfigs.map(({ id }) => [id, [id]]),
)
export const fatigueMuscleToSvgIds = { ...exerciseMuscleToSvgIds, ...legacyTargets }
const regionsByTarget = new Map<string, string[]>()
for (const [label, ids] of Object.entries({ ...fatigueMuscleToSvgIds, ...bodyMapLabelAliases })) {
  regionsByTarget.set(normalizeTarget(label), ids)
}
for (const { id, name, shortName } of fatiguePlaceholderConfigs) {
  for (const label of [name, shortName]) regionsByTarget.set(normalizeTarget(label), exerciseMuscleToSvgIds[id])
}

export function ensureFatigueMuscleCoverage(muscles: FatigueMuscle[]) {
  // Saved workouts can contain both a translated name and a catalog ID for the same area.
  const unique = new Map<string, FatigueMuscle>()
  for (const muscle of muscles) {
    const key = fatigueRegionKey(muscle.id)
    const previous = unique.get(key)
    if (!previous || outranks(muscle, previous)) unique.set(key, muscle)
  }
  const covered = fatigueRegionOwners(muscles)
  return [...unique.values(), ...fatiguePlaceholderMuscles.filter(({ id }) => !covered.has(id))]
}
