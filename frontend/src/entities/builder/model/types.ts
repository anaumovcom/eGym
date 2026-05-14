export type BuilderGroupKind = 'single' | 'alternating' | 'superset' | 'circuit'

export type BuilderExerciseItem = {
  id: string
  slug: string
  name: string
  muscleGroup: string
  sets: string
  rest: string
  load: string
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
  setParams: {
    reps: number
    weight: number
    restSeconds: number
  }
  loadMode: string
  tempo: string
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