import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard, MuscleStatus } from '@/entities/muscle/model/types'

export type Stage4Period = '7d' | '30d' | '3m' | '6m' | '1y' | 'all'
export type ProgressTab = 'summary' | 'exercise' | 'strength' | 'regularity' | 'muscles' | 'body' | 'photo'
export type ProfileTab = 'summary' | 'general' | 'goals' | 'body' | 'photo' | 'blacklist'
export type SettingsTab = 'overview' | 'safety' | 'mechanics' | 'diagnostics' | 'calibrations' | 'service' | 'journal' | 'common' | 'coach'
export type FatigueMode = 'current' | 'after-workout' | '7d' | '30d'

export type MetricCard = {
  label: string
  value: string
  hint?: string
  tone?: 'neutral' | 'good' | 'warning' | 'danger'
}

export type ChartPoint = {
  label: string
  value: number
  accent?: boolean
}

export type ProgressExerciseHistoryRow = {
  date: string
  weight: string
  sets: string
  reps: string
  volume: string
  amplitude: string
}

export type ProgressExerciseOption = {
  slug: string
  name: string
}

export type ProgressExerciseDetails = {
  slug: string
  lastResult: string
  bestResult: string
  bestVolume: string
  completedTimes: string
  averageAmplitude: string
  tempoTrend: string
  workWeightSeries: ChartPoint[]
  volumeSeries: ChartPoint[]
  history: ProgressExerciseHistoryRow[]
  affectedMuscles: MuscleCard[]
  recommendation: string
}

export type ProgressPhotoEntry = {
  id: string
  date: string
  year: string
  views: Array<{ id: 'front' | 'side' | 'back'; label: string }>
  isLatest?: boolean
}

export type ProgressBodyMeasurementRow = {
  label: string
  current: string
  delta: string
  tone: 'good' | 'neutral' | 'warning'
}

export type ProgressKpi = { id: 'days' | 'volume' | 'minutes' | 'records'; label: string; value: number; unit: string; previous?: number | null; deltaPct?: number | null; spark: number[] }
export type ProgressActivityDay = { date: string; level: number; sets: number; volumeKg: number; future?: boolean }
export type ProgressTimelinePoint = { start: string; label: string; volumeKg: number; sets: number; days: number }
export type ProgressRecord = { exerciseSlug: string; exerciseName: string; date: string; e1rm: number; previous: number; weightKg: number; repsPerSet: number }
export type ProgressMover = { slug: string; name: string; fromValue: number; toValue: number; deltaPct: number; series: number[] }
export type ProgressMuscleShare = { id: string; name: string; sets: number; share: number }
export type ProgressInsight = { tone: 'good' | 'warning' | 'info'; title: string; text: string; href?: string | null }
export type ProgressExerciseSession = { date: string; weightKg: number; sets: number; reps: number; repsPerSet: number; volumeKg: number; rpe: number; e1rm?: number | null; isPr?: boolean }
export type ProgressExerciseInsight = {
  slug: string
  name: string
  kind: 'weighted' | 'bodyweight'
  unit: string
  sessionsInPeriod: number
  lastDate: string
  bestE1rm?: number | null
  bestWeight: number
  bestVolume: number
  bestReps: number
  trendPct?: number | null
  sessions: ProgressExerciseSession[]
  nextTarget?: { weightKg: number; sets: number; repsPerSet: number; note: string } | null
}
export type ProgressInsights = {
  periodStart?: string | null
  previousLabel?: string | null
  kpis: ProgressKpi[]
  activity: { weeks: ProgressActivityDay[][]; activeDays: number; streakWeeks: number; daysSinceLast?: number | null }
  timeline: { granularity: 'day' | 'week' | 'month'; points: ProgressTimelinePoint[] }
  records: ProgressRecord[]
  recordCount: number
  movers: ProgressMover[]
  muscleBalance: ProgressMuscleShare[]
  insights: ProgressInsight[]
  exercises: ProgressExerciseInsight[]
}

export type ProgressData = {
  machine: MachineHealth
  updatedAt: string
  periodLabel: string
  title: string
  subtitle: string
  summaryCards: MetricCard[]
  summaryVolumeSeries: ChartPoint[]
  mainProgress: {
    exercise: string
    from: string
    to: string
    delta: string
    muscleFocus: MuscleCard[]
  }
  improvements: string[]
  periodSummary: MetricCard[]
  recommendation: string
  exerciseOptions: ProgressExerciseOption[]
  selectedExercise: ProgressExerciseDetails
  strengthCards: MetricCard[]
  volumeTopExercises: Array<{ rank: number; name: string; value: string }>
  regularityCards: MetricCard[]
  activityCalendar: Array<{ id: string; day: number; state: 'done' | 'partial' | 'missed' | 'rest' }>
  weeklyTrainingSeries: ChartPoint[]
  weeklyMinuteSeries: ChartPoint[]
  dayDistribution: ChartPoint[]
  recentWeeks: Array<{ label: string; trainings: string; minutes: string; completion: string; status: MuscleStatus }>
  muscleLoad: MuscleCard[]
  muscleSplit: Array<{ rank: number; name: string; status: MuscleStatus; value: string }>
  muscleCoverage: Array<{ name: string; count: string }>
  muscleRecommendation: string
  bodyCards: MetricCard[]
  bodyWeightSeries: ChartPoint[]
  bodyMeasurements: ProgressBodyMeasurementRow[]
  smartScale: {
    connected: boolean
    label: string
    hint: string
  }
  photoEntries: ProgressPhotoEntry[]
  photoStats: MetricCard[]
  photoRecommendation: string
  insights?: ProgressInsights | null
  emptyState?: {
    title: string
    description: string
  }
}

export type ProfilePhotoShot = {
  id: 'front' | 'side' | 'back'
  photoId: number
  label: string
  takenAt: string
  imageUrl: string
  thumbnailUrl: string
  width: number
  height: number
}

export type UserProfileData = {
  id: string
  name: string
  avatarLabel: string
  goal: string
  heightCm: number
  weightKg: number
  level: string
  email: string
  notes: string
  locale: string
  units: string
  theme: string
  createdAt: string
  trainingFrequency: string
  workoutDuration: string
  workoutStyle: string
  autoPrograms: boolean
  priorityMuscles: string[]
  considerationNotes: string[]
  bodyMeasurements: Array<{ date: string; weight: number; waistCm: number; chestCm: number; hipsCm: number; shouldersCm: number; bicepsCm: number }>
  photos: Array<{ id: string; date: string; views: ProfilePhotoShot[] }>
}

export type FatigueMuscle = {
  id: string
  name: string
  shortName: string
  group: 'front' | 'back'
  area: 'upper' | 'middle' | 'lower'
  score: number
  readinessPercent: number
  status: MuscleStatus
  recoveryHours: number
  lastLoadAt: string
  impact: Array<{ exercise: string; date: string; share: string; status: MuscleStatus }>
  recommendation: string
  recommendedExercises: Array<{ name: string; note: string; status: MuscleStatus }>
  avoidExercises: Array<{ name: string; note: string; status: MuscleStatus }>
}

export type FatigueData = {
  machine: MachineHealth
  updatedAt: string
  readinessPercent: number
  overview: MetricCard[]
  muscles: FatigueMuscle[]
  recommendedPlan: string
  recoveryNote: string
}

export type SystemLogEntry = {
  id: string
  date: string
  category: string
  level: 'info' | 'success' | 'warning' | 'critical'
  title: string
  description: string
}

export type SystemCalibrationEntry = {
  id: string
  exercise: string
  muscle: string
  lowerPoint: string
  upperPoint: string
  updatedAt: string
  status: 'actual' | 'stale'
}

export type SystemSettingsData = {
  machine: MachineHealth
  overviewCards: MetricCard[]
  overviewEvents: Array<{ time: string; title: string; tone: 'neutral' | 'good' | 'warning' }>
  safety: {
    emergencyReady: boolean
    childLock: boolean
    workoutPin: boolean
    servicePin: boolean
    idleLockMinutes: string
    guestMode: boolean
    guestWeightLimit: string
    maxLoad: string
    maxSpeed: string
    syncLimit: string
    desyncAction: string
  }
  mechanics: {
    statusSummary: MetricCard[]
    leftDrive: MetricCard[]
    rightDrive: MetricCard[]
    sync: MetricCard[]
    motion: MetricCard[]
    screw: MetricCard[]
    profiles: string[]
    service: MetricCard[]
  }
  diagnostics: {
    lastRun: string
    checked: string
    success: string
    errors: string
    systemStatus: string
    checklist: Array<{ label: string; result: string }>
    quickTests: Array<{ title: string; description: string }>
    history: Array<{ label: string; result: string; hint: string }>
  }
  calibrations: {
    entries: SystemCalibrationEntry[]
    total: string
    lastUpdate: string
    staleCount: string
    missingCount: string
  }
  service: {
    unlocked: boolean
    positions: MetricCard[]
    driveHealth: MetricCard[]
    actions: Array<{ title: string; description: string }>
    journal: Array<{ time: string; action: string; result: string }>
  }
  journal: {
    stats: MetricCard[]
    entries: SystemLogEntry[]
  }
  common: {
    interfaceTheme: 'dark' | 'light'
    interfaceScale: '100%' | '125%' | '150%'
    language: 'Русский' | 'English'
    units: 'kg / cm' | 'lb / in'
    brightnessMode: 'Авто' | 'Вручную'
    autoReturnMinutes: string
    soundEnabled: boolean
    voiceHintsEnabled: boolean
    signalVolume: string
    wifiMode: string
    networkStatus: string
    ssid: string
    ipAddress: string
    signalStrength: string
    version: string
    serialNumber: string
    workTime: string
  }
}

export type Stage4DevFlags = {
  machineReady: boolean
  leftDriveError: boolean
  rightDriveError: boolean
  emergencyStop: boolean
  safetyDisabled: boolean
  noCalibration: boolean
  highFatigue: boolean
  criticalFatigue: boolean
  noHistory: boolean
  noPhotos: boolean
  offlineHours: number
}