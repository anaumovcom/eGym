import type { MachineHealth } from '@/entities/machine/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'

export type DashboardWorkout = {
  title: string
  exercises: number
  sets: number
  duration: string
  list: string[]
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
  machine: MachineHealth
  alerts: DashboardAlert[]
  recommendedExercises: DashboardRecommendation[]
  quickStart: DashboardQuickStartItem[]
  progress: DashboardProgressMetric[]
  muscles: MuscleCard[]
}