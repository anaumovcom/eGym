export type UserSummary = {
  id: string
  name: string
  readinessPercent: number
  lastWorkout: string
  todayFocus: string
  weekProgress: string
  accent: 'gold' | 'green'
}