import type { RuntimeExercisePlan } from '@/entities/runtime/model/types'

const CALIBRATION_EXEMPT_EQUIPMENT = new Set([
  'Bosu-Ball',
  'Cardio',
  'Dumbbells',
  'Kettlebells',
  'Medicine-Ball',
  'Plate',
  'Recovery',
  'Stretches',
  'TRX',
  'Yoga',
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