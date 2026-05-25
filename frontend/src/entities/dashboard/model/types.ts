import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'

export type DashboardWorkout = {
  title: string
  exercises: number
  sets: number
  duration: string
  list: DashboardWorkoutExercise[]
}

export type DashboardBuilderWorkout = {
  id: string
  title: string
  exercises: string[]
  duration: string
}

export type DashboardWorkoutSnapshot = {
  label: string
  primary: string
  secondary: string
  meta?: string | null
}

export type DashboardWorkoutExercise = {
  slug: string
  name: string
  previewVideoUrl?: string | null
  previous: DashboardWorkoutSnapshot
  planned: DashboardWorkoutSnapshot
}

export type DashboardRecommendation = {
  name: string
  muscles: string
  status: string
}

export type DashboardQuickStartItem = {
  name: string
  stats: string
  last: string
}

export type DashboardProgressMetric = {
  label: string
  value: string
}

export type DashboardAlert = {
  tone: 'warning' | 'blocked'
  title: string
  description: string
}

export type DashboardData = {
  greeting: string
  recommendationTitle: string
  recommendationText: string
  readinessPercent: number
  todayWorkout: DashboardWorkout | null
  workouts?: DashboardBuilderWorkout[]
  machine: MachineHealth
  alerts: DashboardAlert[]
  recommendedExercises: DashboardRecommendation[]
  quickStart: DashboardQuickStartItem[]
  progress: DashboardProgressMetric[]
  muscles: MuscleCard[]
}