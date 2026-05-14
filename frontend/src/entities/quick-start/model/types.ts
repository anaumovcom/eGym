import type { ExerciseCompatibilityTone, ExerciseLoadSettings, ExerciseSummary } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'

export type QuickStartRecommendation = {
  title: string
  description: string
  cta: string
}

export type QuickStartExerciseListItem = ExerciseSummary & {
  reason: string
  lastResult: string
  lastPerformed: string
}

export type QuickStartSelectedExercise = {
  exercise: ExerciseSummary
  readiness: Array<{ label: string; tone: ExerciseCompatibilityTone; description: string }>
  lastResult: string
  formaRecommendation: string
  settings: ExerciseLoadSettings
  warnings: Array<{ tone: 'warning' | 'blocked'; title: string; description: string }>
}

export type QuickStartData = {
  recommendation: QuickStartRecommendation
  machine: MachineHealth
  filterGroups: {
    audience: string[]
    muscleFocus: string[]
    equipment: string[]
  }
  recommended: QuickStartExerciseListItem[]
  recent: QuickStartExerciseListItem[]
  favorites: QuickStartExerciseListItem[]
  selectedExerciseSlug: string | null
  selectedExercise: QuickStartSelectedExercise | null
}