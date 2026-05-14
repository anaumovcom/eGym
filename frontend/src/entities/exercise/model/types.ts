import type { MuscleCard, MuscleStatus } from '@/entities/muscle/model/types'

export type ExerciseDifficulty = 'Beginner' | 'Intermediate' | 'Advanced'
export type ExerciseForce = 'Push' | 'Pull' | 'Static' | 'Stretch'
export type ExerciseMechanic = 'Compound' | 'Isolation' | 'Mobility'
export type ExerciseViewMode = 'grid' | 'list'
export type ExerciseVideoView = 'side' | 'front'
export type ExerciseVideoGender = 'male' | 'female'
export type ExerciseCompatibilityTone = 'recommended' | 'okay' | 'caution' | 'blocked'
export type ExerciseCalibrationStatus = 'ready' | 'required' | 'recommended' | 'unavailable'
export type ExerciseTabId = 'overview' | 'technique' | 'muscles' | 'load' | 'history' | 'similar'

export type ExerciseGuide = {
  setup: string[]
  howToPerform: string[]
  technique: string[]
  thingsToAvoid: string[]
  keyTips: string[]
}

export type ExerciseVideoAsset = {
  url: string
  label: string
  view: ExerciseVideoView
  gender: ExerciseVideoGender
}

export type ExerciseHistoryEntry = {
  date: string
  weight: string
  reps: string
  sets: number
  volume: string
  rpe: number
  note: string
}

export type ExerciseLoadPoint = {
  label: string
  value: number
  caption?: string
}

export type ExerciseAlternative = {
  slug: string
  name: string
  secondaryName: string
  muscles: string[]
  equipment: string
}

export type ExerciseCompatibility = {
  tone: ExerciseCompatibilityTone
  title: string
  description: string
  affectedMuscles: MuscleCard[]
}

export type ExerciseLoadSettings = {
  weight: number
  sets: number
  reps: number
  restSeconds: number
  mode: string
  tempo: string
  recommendation: string
  safeRange: [number, number]
  calibration: ExerciseCalibrationStatus
}

export type ExerciseSummary = {
  slug: string
  name: string
  secondaryName: string
  equipment: string
  difficulty: ExerciseDifficulty
  force: ExerciseForce
  grips: string
  mechanic: ExerciseMechanic
  muscles: string[]
  favorite: boolean
  blacklisted: boolean
  recommended: boolean
  compatibilityTone: ExerciseCompatibilityTone
  readinessStatus: MuscleStatus
  difficultyLabel: string
  imageUrl?: string
  previewVideoUrl?: string
  badges: string[]
}

export type ExerciseDetails = ExerciseSummary & {
  description: string
  shortSteps: string[]
  guide: ExerciseGuide
  videos: ExerciseVideoAsset[]
  primaryMuscles: string[]
  secondaryMuscles: string[]
  stabilizers: string[]
  muscleRoleText: string
  compatibility: ExerciseCompatibility
  loadSettings: ExerciseLoadSettings
  history: ExerciseHistoryEntry[]
  loadProgress: ExerciseLoadPoint[]
  similar: ExerciseAlternative[]
  equipmentAlternatives: string[]
  whenToChooseAlternative: string[]
}

export type ExerciseCatalogResponse = {
  items: ExerciseSummary[]
  total: number
  availableFilters: {
    muscles: string[]
    equipment: string[]
    difficulty: ExerciseDifficulty[]
    force: ExerciseForce[]
    mechanic: ExerciseMechanic[]
    grips: string[]
  }
}