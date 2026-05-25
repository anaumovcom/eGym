import type { StrengthSetPlan, StrengthTrainingMode } from '@/entities/strength/model/types'

export type BuilderGroupKind = 'single' | 'alternating' | 'superset' | 'circuit'
export type BuilderLoadType = 'weighted' | 'bodyweight' | 'timed'

export type BuilderSetParams = {
  reps: number
  weight: number
  restSeconds: number
  durationSeconds?: number
}

export type BuilderExerciseItem = {
  id: string
  slug: string
  name: string
  muscleGroup: string
  muscles?: string[]
  affectsFatigue?: boolean
  sets: string
  rest: string
  load: string
  loadType?: BuilderLoadType
  previewVideoUrl?: string
  strengthModeId?: string
  strengthDayType?: string | null
  strengthPlan?: StrengthSetPlan[]
}

export type BuilderProgramTab = {
  id: string
  name: string
  subtitle: string
  recommendedToday: boolean
  canDelete?: boolean
}

export type BuilderWorkoutGroup = {
  id: string
  kind: BuilderGroupKind
  title: string
  rounds?: string
  betweenExercisesRest?: string
  betweenRoundsRest?: string
  items: BuilderExerciseItem[]
}

export type BuilderExerciseEditor = {
  name: string
  subtitle: string
  setParams: BuilderSetParams
  effectiveSetParams?: BuilderSetParams
  loadType?: BuilderLoadType
  loadMode: string
  loadModeDescription?: string
  tempo: string
  tempoDescription?: string
  strengthModeId: string
  strengthDayType?: string | null
  strengthPlan: StrengthSetPlan[]
  note: string
}

export type BuilderSummaryCard = {
  label: string
  value: string
  hint: string
}

export type WorkoutBuilderData = {
  title: string
  subtitle: string
  programs: BuilderProgramTab[]
  strengthModes: StrengthTrainingMode[]
  selectedProgramId: string
  info: {
    name: string
    type: string
    duration: string
    difficulty: string
    description: string
  }
  groups: BuilderWorkoutGroup[]
  selectedExerciseId: string
  selectedExercise: BuilderExerciseEditor
  addSuggestions: Array<{ slug: string; name: string; muscles: string }>
  summaryCards: BuilderSummaryCard[]
  warnings: Array<{ tone: 'warning' | 'blocked' | 'success'; title: string; description: string }>
}