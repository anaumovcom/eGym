import type { RuntimeExercisePlan } from '@/entities/runtime/model/types'

const CALIBRATION_EXEMPT_EQUIPMENT = new Set([
  'Bosu-Ball',
  'Босу',
  'Cardio',
  'Кардио',
  'Dumbbells',
  'Гантели',
  'Kettlebells',
  'Гири',
  'Гиря',
  'Medicine-Ball',
  'Медбол',
  'Plate',
  'Диск',
  'Recovery',
  'Восстановление',
  'Stretches',
  'Растяжка',
  'TRX',
  'Петли TRX',
  'Yoga',
  'Йога',
  'Резина',
  'Собственный вес',
])

export function hasMovableMachineLoad(exercise: Pick<RuntimeExercisePlan, 'kind' | 'loadSettings'>) {
  return exercise.kind === 'machine' && exercise.loadSettings.weight > 0
}

export function requiresMachineCalibration(exercise: Pick<RuntimeExercisePlan, 'kind' | 'loadSettings' | 'details'>) {
  if (CALIBRATION_EXEMPT_EQUIPMENT.has(exercise.details.equipment)) {
    return false
  }

  return hasMovableMachineLoad(exercise)
}

export function supportsFixedBarSetup(exercise: Pick<RuntimeExercisePlan, 'slug' | 'kind' | 'loadSettings' | 'details'>) {
  return (exercise.kind === 'machine' && !CALIBRATION_EXEMPT_EQUIPMENT.has(exercise.details.equipment))
    || /(?:pull-?up|chin-?up)/i.test(exercise.slug)
}