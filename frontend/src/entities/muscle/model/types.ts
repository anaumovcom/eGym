export type MuscleStatus = 'ready' | 'light' | 'medium' | 'high' | 'critical' | 'no_data'

export type MuscleCard = {
  name: string
  status: MuscleStatus
  score: number
}