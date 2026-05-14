import type { ExerciseCompatibilityTone, ExerciseLoadSettings } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'

export type WorkoutExerciseStatus = 'up-next' | 'planned' | 'in-progress' | 'completed' | 'skipped' | 'warning'

export type WorkoutExerciseRow = {
  id: string
  slug: string
  name: string
  muscles: string
  imageUrl?: string
  load: string
  rest: string
  status: WorkoutExerciseStatus
  calibration: string
  note?: string
}

export type WorkoutExercisePanel = {
  id: string
  slug: string
  name: string
  muscles: string
  lastResult: string
  formaRecommendation: string
  readiness: Array<{ label: string; value: string; tone: ExerciseCompatibilityTone }>
  settings: ExerciseLoadSettings
  alerts: string[]
}

export type WorkoutProgress = {
  completedExercises: number
  totalExercises: number
  completedSets: number
  totalSets: number
  minutesLeft: number
  percent: number
  nextStep: string
}

export type TodayWorkoutData = {
  title: string
  subtitle: string
  readinessPercent: number
  machine: MachineHealth
  startState: 'planned' | 'in-progress' | 'completed' | 'blocked' | 'recovery'
  summary: {
    exercises: number
    sets: number
    duration: string
  }
  mainAction: string
  exerciseRows: WorkoutExerciseRow[]
  selectedExerciseId: string
  selectedExercise: WorkoutExercisePanel
  warnings: Array<{ tone: 'warning' | 'blocked'; title: string; description: string }>
  muscles: MuscleCard[]
  progress: WorkoutProgress
  quickActions: string[]
}