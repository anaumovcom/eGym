import type { ExerciseDetails, ExerciseLoadSettings, ExerciseSummary } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'
import type { StrengthSetType } from '@/entities/strength/model/types'

export type RuntimeFlowSource = 'quick-start' | 'today' | 'calendar' | 'programs' | 'builder' | 'catalog' | 'progress'
export type RuntimeExerciseKind = 'machine' | 'bodyweight' | 'timed' | 'stretch' | 'group'
export type RuntimeView = 'photo-progress' | 'exercise-setup' | 'exercise-session' | 'rest' | 'exercise-summary' | 'workout-summary'
export type RuntimeWorkoutOutcome = 'completed' | 'partial' | 'aborted'
export type RuntimePhotoMode = 'pre-workout' | 'post-workout' | 'manual'
export type RuntimePhotoView = 'front' | 'side' | 'back'
export type RuntimeCalibrationState = 'saved' | 'missing' | 'not-needed'
export type RuntimeExerciseOutcome = 'completed' | 'partial' | 'aborted'

export type RuntimeSetPlan = {
  setType?: StrengthSetType
  targetReps?: number
  targetMinReps?: number
  targetMaxReps?: number
  targetSeconds?: number
  weightLabel: string
  recommendedWeightKg?: number
  restSeconds: number
  rirLabel?: string
  note?: string
  warning?: string
}

export type RuntimeSetResult = {
  setNumber: number
  plannedValue: number
  actualValue: number
  setType?: StrengthSetType | string | null
  targetMinReps?: number | null
  targetMaxReps?: number | null
  reps?: number | null
  weightKg?: number | null
  rir?: number | null
  subjectiveEffort?: number | null
  discomfortLevel?: number | null
  pain?: boolean
  techniqueBreakdown?: boolean
  comment?: string | null
  volumeKg?: number | null
  amplitudePercent?: number
  tempoLabel: string
  syncLabel?: string
  correction?: number
}

export type RuntimeExercisePlan = {
  id: string
  slug: string
  order: number
  name: string
  secondaryName: string
  kind: RuntimeExerciseKind
  muscles: string[]
  summary: ExerciseSummary
  details: ExerciseDetails
  loadSettings: ExerciseLoadSettings
  calibrationState: RuntimeCalibrationState
  movementRangeLabel?: string
  movementRangeSaved?: boolean
  plan: RuntimeSetPlan[]
  strengthMode: {
    id: string
    title: string
    dayType?: string | null
  }
  recommendation: string
  nextExerciseId?: string
  previewLabel?: string
  groupMeta?: {
    groupName: string
    currentRound: number
    totalRounds: number
    currentStep: number
    totalSteps: number
    nextStepLabel: string
  }
}

export type RuntimePhotoShot = {
  view: RuntimePhotoView
  status: 'pending' | 'ready'
  title: string
  hint: string
  imageUrl?: string
  takenAt?: string
}

export type RuntimePhotoProgressState = {
  mode: RuntimePhotoMode
  autoPrompt: boolean
  completed: boolean
  currentView: RuntimePhotoView
  shots: RuntimePhotoShot[]
  timerSeconds: 3 | 5 | 10 | 0
  readyMessage: string
  privacyNote: string
}

export type RuntimeExerciseSessionState = {
  exerciseId: string
  kind: RuntimeExerciseKind
  setNumber: number
  totalSets: number
  targetLabel: string
  currentValue: number
  targetValue: number
  setType?: StrengthSetType
  targetMinReps?: number
  targetMaxReps?: number
  rirLabel?: string
  setNote?: string
  setWarning?: string
  weightLabel: string
  hints: string[]
  machine: MachineHealth
  metrics: Array<{ label: string; value: string; tone: 'good' | 'warning' | 'neutral' }>
  motionTrack?: {
    minLabel: string
    maxLabel: string
    currentLabel: string
    points: Array<{ phase: 'up' | 'down' | 'current'; value: number }>
  }
  groupMeta?: RuntimeExercisePlan['groupMeta']
}

export type RuntimeRestState = {
  mode: 'between-sets' | 'next-exercise' | 'group-step' | 'after-error'
  title: string
  subtitle: string
  totalSeconds: number
  remainingSeconds: number
  timerPaused: boolean
  completedSet: RuntimeSetResult
  recommendation: string
  nextActionLabel: string
  nextExercise?: { name: string; target: string; restLabel?: string }
  groupProgress?: RuntimeExercisePlan['groupMeta']
}

export type RuntimeExerciseSummaryState = {
  outcome: RuntimeExerciseOutcome
  exerciseId: string
  title: string
  subtitle: string
  setResults: RuntimeSetResult[]
  totals: {
    setsCompleted: string
    repsOrTime: string
    volume: string
    bestSet?: string
    averageAmplitude?: string
    tempo: string
  }
  planVsFact: Array<{ label: string; plan: string; fact: string; delta: string }>
  recommendation: string
  nextStepLabel: string
}

export type RuntimeWorkoutSummaryState = {
  outcome: RuntimeWorkoutOutcome
  title: string
  subtitle: string
  metrics: Array<{ label: string; value: string; hint: string }>
  exercises: Array<{ name: string; result: string; status: 'done' | 'skipped' | 'moved' }>
  muscleLoad: MuscleCard[]
  recommendation: string
  nextWorkout: string
  feeling: 'easy' | 'normal' | 'hard'
  discomfort: 'none' | 'minor' | 'reduce-next-time'
}

export type RuntimeWorkoutSession = {
  id: string
  source: RuntimeFlowSource
  view: RuntimeView
  machine: MachineHealth
  workoutTitle: string
  workoutSubtitle: string
  currentExerciseId: string
  currentSetIndex: number
  photoProgress: RuntimePhotoProgressState
  exercises: RuntimeExercisePlan[]
  completedSets: Record<string, RuntimeSetResult[]>
  completedExerciseIds: string[]
  workoutSummary: RuntimeWorkoutSummaryState
  exerciseSummary?: RuntimeExerciseSummaryState
  restState?: RuntimeRestState
  sessionState?: RuntimeExerciseSessionState
}