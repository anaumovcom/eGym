import type { RuntimeExercisePlan } from '@/entities/runtime/model/types'

export function hasMovableMachineLoad(exercise: Pick<RuntimeExercisePlan, 'kind' | 'loadSettings'>) {
  return exercise.kind === 'machine' && exercise.loadSettings.weight > 0
}

export function requiresMachineCalibration(exercise: Pick<RuntimeExercisePlan, 'kind' | 'loadSettings'>) {
  return hasMovableMachineLoad(exercise)
}